"""Evidências administrativas da rota Câmara no snapshot (decisão 0080 §8.4; correções da 0081).

O snapshot transporta, além das capturas, o que sustenta a atribuição e a autorização de cada obtenção: termo (bytes e
recibo), revisão do auditor, política de robots (bytes e recibos), registros de obtenção (vínculo captura → política →
termo) e os registros de ativação como EVIDÊNCIA (instalar não ativa a rota). Tudo viaja em `camara/` sob o inventário
de hashes do manifesto.

Validação (`_validar`): cada arquivo pelo nome (hash), cada recibo de política como evidência dos seus bytes (a mesma
validação do portão), cada recibo de termo pelo termo, e o FECHAMENTO dos vínculos (0081 r3, R3-1): para cada obtenção,
a gramática e a DECISÃO do caminho são recompostas dos bytes da política apontada (mesmo motor RFC 9309 por token), a
decisão persistida correspondente tem de existir e permitir, a política tem de ter sido obtida antes da emissão e ser
válida nela, a captura não precede a política, e o termo (recibo da obtenção, não só o conteúdo) tem de existir, ter sido
capturado antes da emissão e sob política válida que permitia o caminho do termo. `termo_sha256=null` só com o marcador
explícito `sem_termo`. O nome do recibo arquivado tem de coincidir com o instante declarado. Evidência declarada com
referência quebrada é recusada, mesmo com checksums refeitos. Ausência TOTAL de evidência Câmara é legítima.

Instalação (`Publicacao`): preflight completo de TODOS os conflitos e VALIDAÇÃO da união (home + pacote) pela mesma `_validar` (home incoerente
com pacote íntegro é recusado: a instalação não conserta nem herda evidência quebrada), preparo em staging e
publicação com diário de desfazimento, de modo que entra na MESMA publicação/recuperação transacional do banco e dos
blobs (`snapshot.py`): falha em qualquer ponto restaura `camara/` ao estado anterior. Arquivos nomeados pelo hash
coexistem (termos de snapshots diferentes), as obtenções são unidas por registro, as decisões por caminho de uma mesma
política são unidas (conflito é recusa) e as ativações ficam só como evidência.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from freoa_verifica.connectors import camara_ativacao as ativ
from freoa_verifica.connectors import camara_robots as rb
from freoa_verifica.connectors.camara_estado import (ATIVACAO, Estado, EstadoIndisponivel, _de_iso, _escrever,
                                                     _json_bytes, iso, json_de_bytes, sha256, validar_obtencao,
                                                     validar_politica, validar_recibo_do_termo)
from freoa_verifica.connectors.camara_policy import HOSTS, TERMO_URL
from freoa_verifica.texto_resposta import texto_da_resposta
from freoa_verifica.transport import RespostaInvalida

_H = r"[0-9a-f]{64}"
_HOST = r"www2?\.camara\.leg\.br"
_PADROES = {
    "termo_corpo": re.compile(rf"termo/({_H})\.html"),
    "termo_recibo": re.compile(rf"termo/({_H})\.({_H})\.recibo\.json"),
    "revisao": re.compile(rf"revisao/({_H})\.json"),
    "robots": re.compile(rf"robots-({_HOST})-({_H})\.txt"),
    "politica": re.compile(rf"politicas/({_HOST})-({_H})-(\d+)\.json"),
    "obtencoes": re.compile(r"obtencoes\.jsonl"),
    "ativacao": re.compile(rf"evidencias/ativacao-({_H})\.json"),
}
PREFIXO = "camara/"


class EvidenciaInvalida(ValueError):
    """Evidência administrativa adulterada ou incoerente: a instalação do snapshot é recusada."""


def _tipo(relativo: str) -> tuple[str, re.Match] | None:
    for nome, padrao in _PADROES.items():
        achado = padrao.fullmatch(relativo)
        if achado:
            return nome, achado
    return None


def _arquivos_do_home(estado: Estado) -> dict[str, bytes]:
    """Evidências íntegras do home, por caminho relativo a `camara/`. O que não confere não viaja."""
    pasta = estado.pasta
    saida: dict[str, bytes] = {}
    if pasta is None or not pasta.is_dir():
        return saida
    for caminho in sorted(p for p in pasta.rglob("*") if p.is_file()):
        relativo = caminho.relative_to(pasta).as_posix()
        achado = _tipo(relativo)
        if achado is None or achado[0] == "ativacao":
            continue
        if achado[0] == "termo_corpo" and not any((pasta / "termo").glob(f"{achado[1].group(1)}.*.recibo.json")):
            continue  # resto de uma captura interrompida (corpo sem recibo): não é evidência e não viaja
        saida[relativo] = caminho.read_bytes()
    ativacao = estado.home / ATIVACAO if estado.home else None
    registros = []
    if ativacao is not None and ativacao.is_file():
        registros.append(ativacao.read_bytes())
    registros += [p.read_bytes() for p in sorted((pasta / "evidencias").glob("ativacao-*.json"))] \
        if (pasta / "evidencias").is_dir() else []
    for bruto in registros:
        try:
            registro = json_de_bytes(bruto)
        except ValueError:
            continue
        if isinstance(registro, dict) and isinstance(registro.get("registro_sha256"), str):
            saida[f"evidencias/ativacao-{registro['registro_sha256']}.json"] = bruto
    return saida


def _instante(texto) -> str:
    return iso(_de_iso(texto))


def _caminho(url: str) -> str:
    partes = urlsplit(url)
    return partes.path + ("?" + partes.query if partes.query else "")


def _recibos_vigentes_em(recibos: list[dict], instante) -> list[dict]:
    return [r for r in recibos if _de_iso(r["obtido_em"]) <= instante < _de_iso(r["valido_ate"])]


def _permite(recibo: dict, corpo: bytes, caminho: str) -> bool:
    """A decisão RECOMPOSTA dos bytes da política (mesma gramática e mesmo motor do portão) permite o caminho E a
    decisão persistida no recibo existe e é a mesma."""
    try:
        grupos = rb.interpretar(texto_da_resposta(corpo, recibo["content_type"]))
        decisao = rb.decidir(grupos, caminho).estado
    except (RespostaInvalida, rb.RobotsInconclusivo) as exc:
        raise EvidenciaInvalida("camara_politica_nao_interpretavel") from exc
    return decisao == rb.PERMITIDO and recibo["decisoes"].get(caminho) == rb.PERMITIDO


def _validar(arquivos: dict[str, bytes]) -> None:
    """Confere todas as evidências entre si e o fechamento dos vínculos; levanta `EvidenciaInvalida` no primeiro defeito."""
    memoria = Estado(None)
    termos, robots = {}, {}
    for relativo, dados in arquivos.items():
        achado = _tipo(relativo)
        if achado is None:
            raise EvidenciaInvalida(f"camara_evidencia_nao_permitida:{relativo}")
        tipo, m = achado
        if tipo in {"termo_corpo", "revisao"} and sha256(dados) != m.group(1):
            raise EvidenciaInvalida(f"camara_evidencia_hash_diverge:{relativo}")
        if tipo == "termo_recibo" and sha256(dados) != m.group(2):
            raise EvidenciaInvalida(f"camara_evidencia_hash_diverge:{relativo}")
        if tipo == "robots":
            if sha256(dados) != m.group(2):
                raise EvidenciaInvalida(f"camara_evidencia_hash_diverge:{relativo}")
            robots[(m.group(1), m.group(2))] = dados
        if tipo == "termo_corpo":
            termos[m.group(1)] = dados
        memoria._memoria[relativo] = dados
    recibos_de_termo: dict[tuple[str, str], dict] = {}
    politicas: dict[tuple[str, str], list[dict]] = {}
    obtencoes: list[dict] = []
    try:
        for relativo, dados in arquivos.items():
            tipo, m = _tipo(relativo)
            if tipo == "termo_recibo":
                if m.group(1) not in termos:
                    raise EvidenciaInvalida(f"camara_recibo_sem_termo:{relativo}")
                recibos_de_termo[(m.group(1), m.group(2))] = validar_recibo_do_termo(
                    json_de_bytes(dados), m.group(1), len(termos[m.group(1)]))
            elif tipo == "politica":
                corpo = robots.get((m.group(1), m.group(2)))
                if corpo is None:
                    raise EvidenciaInvalida(f"camara_politica_sem_corpo:{relativo}")
                registro = validar_politica(json_de_bytes(dados), m.group(1), corpo)  # a mesma validação do portão
                if registro["sha256"] != m.group(2):
                    raise EvidenciaInvalida(f"camara_politica_incoerente:{relativo}")
                if str(int(_de_iso(registro["obtido_em"]).timestamp())) != m.group(3):
                    raise EvidenciaInvalida(f"camara_politica_instante_do_nome_incoerente:{relativo}")
                memoria._memoria[relativo] = registro
                politicas.setdefault((m.group(1), m.group(2)), []).append(registro)
            elif tipo == "obtencoes":
                obtencoes += [validar_obtencao(json_de_bytes(linha)) for linha in dados.splitlines() if linha]
        # Fechamento dos vínculos: nada do que um registro aponta pode faltar ou contradizer o apontado.
        for digest in termos:
            if not any(d == digest for d, _ in recibos_de_termo):
                raise EvidenciaInvalida(f"camara_termo_sem_recibo:{digest}")
        for (digest, _), recibo in recibos_de_termo.items():
            candidatas = politicas.get(("www2.camara.leg.br", recibo["politica_robots_sha256"]))
            if candidatas is None:
                raise EvidenciaInvalida(f"camara_termo_sem_politica:{digest}")
            vigentes = _recibos_vigentes_em(candidatas, _de_iso(recibo["capturado_em"]))
            if not vigentes:
                raise EvidenciaInvalida(f"camara_termo_fora_da_validade_da_politica:{digest}")
            corpo = robots[("www2.camara.leg.br", recibo["politica_robots_sha256"])]
            if not any(_permite(r, corpo, urlsplit(TERMO_URL).path) for r in vigentes):
                raise EvidenciaInvalida(f"camara_termo_sem_decisao_que_o_permita:{digest}")
        for obtencao in obtencoes:
            host = urlsplit(obtencao["url"]).netloc
            if host not in HOSTS:
                raise EvidenciaInvalida("camara_obtencao_host_nao_admitido")
            termo = None
            if obtencao["termo_sha256"] is not None:
                termo = recibos_de_termo.get((obtencao["termo_sha256"], obtencao["termo_recibo_sha256"]))
                if termo is None:
                    raise EvidenciaInvalida(f"camara_obtencao_sem_termo:{obtencao['termo_sha256']}")
            recibos = politicas.get((host, obtencao["politica_sha256"]))
            if recibos is None:
                raise EvidenciaInvalida(f"camara_obtencao_sem_politica:{obtencao['politica_sha256']}")
            instante = _instante(obtencao["politica_obtida_em"])
            doc = [r for r in recibos if _instante(r["obtido_em"]) == instante]
            if not doc:
                raise EvidenciaInvalida("camara_obtencao_instante_da_politica_sem_recibo")
            recibo = doc[0]
            emitida = _de_iso(obtencao["emitida_em"])
            if not _de_iso(recibo["obtido_em"]) <= emitida < _de_iso(recibo["valido_ate"]):
                raise EvidenciaInvalida("camara_obtencao_fora_da_validade_da_politica")
            if _de_iso(obtencao["capturado_em"]) < _de_iso(recibo["obtido_em"]):
                raise EvidenciaInvalida("camara_obtencao_anterior_a_politica")
            if not _permite(recibo, robots[(host, obtencao["politica_sha256"])], _caminho(obtencao["url"])):
                raise EvidenciaInvalida("camara_obtencao_nao_autorizada_pela_politica")
            if termo is not None and _de_iso(termo["capturado_em"]) > emitida:
                raise EvidenciaInvalida("camara_obtencao_termo_posterior_a_emissao")
        for relativo, dados in arquivos.items():
            tipo, m = _tipo(relativo)
            if tipo == "ativacao":
                registro = json_de_bytes(dados)
                if registro.get("registro_sha256") != m.group(1) or not ativ.validar_registro(memoria, registro):
                    raise EvidenciaInvalida(f"camara_ativacao_evidencia_invalida:{relativo}")
    except (ValueError, OSError, LookupError, TypeError, ArithmeticError) as exc:
        if isinstance(exc, EvidenciaInvalida):
            raise
        raise EvidenciaInvalida("camara_evidencia_ilegivel") from exc


def exportar(home: Path, destino: Path) -> tuple[dict[str, str], dict | None]:
    """Copia as evidências do home para `destino/camara/` e devolve (hashes por caminho do snapshot, entrada do
    manifesto). Sem evidência administrativa, (`{}`, None). Levanta `EvidenciaInvalida` se o home as tem incoerentes."""
    arquivos = _arquivos_do_home(Estado(home))
    if not arquivos:
        return {}, None
    _validar(arquivos)  # evidência inconsistente no home recusa a exportação: nada é omitido em silêncio
    hashes = {}
    for relativo, dados in arquivos.items():
        alvo = destino / PREFIXO / relativo
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(dados)
        hashes[PREFIXO + relativo] = sha256(dados)
    termos = sorted(m.group(1) for r in arquivos if (m := _PADROES["termo_corpo"].fullmatch(r)))
    return hashes, {"arquivos": sorted(PREFIXO + r for r in arquivos), "termos": termos,
                    "ativacoes": sorted(m.group(1) for r in arquivos if (m := _PADROES["ativacao"].fullmatch(r)))}


def preparar(origem: Path, manifest: dict) -> dict[str, bytes]:
    """Valida as evidências administrativas do snapshot (já conferidas contra o inventário de hashes) e devolve
    `{caminho relativo a camara/: bytes}`; sem evidência, `{}`. Levanta `EvidenciaInvalida`."""
    entrada = manifest.get("camara_evidencias")
    if entrada is None:
        extras = [p for p in (origem / "camara").rglob("*") if p.is_file()] if (origem / "camara").is_dir() else []
        if extras:
            raise EvidenciaInvalida("camara_evidencias_fora_do_manifesto")
        return {}
    inventario = manifest.get("arquivos_sha256")
    if (not isinstance(entrada, dict) or not isinstance(entrada.get("arquivos"), list)
            or not isinstance(inventario, dict)):
        raise EvidenciaInvalida("camara_evidencias_manifesto_invalido")
    arquivos: dict[str, bytes] = {}
    for nome in entrada["arquivos"]:
        if not isinstance(nome, str) or not nome.startswith(PREFIXO) or inventario.get(nome) is None:
            raise EvidenciaInvalida("camara_evidencia_fora_do_inventario")
        dados = (origem / nome).read_bytes()
        if sha256(dados) != inventario[nome]:
            raise EvidenciaInvalida(f"camara_evidencia_hash_diverge:{nome}")
        arquivos[nome[len(PREFIXO):]] = dados
    declarados = {n for n in inventario if n.startswith(PREFIXO)}
    if declarados != set(entrada["arquivos"]):
        raise EvidenciaInvalida("camara_evidencias_inventario_divergente")
    _validar(arquivos)
    return arquivos


def _ancestrais_invalidos(alvo: Path, raiz: Path) -> bool:
    """Algum componente EXISTENTE do caminho (entre a raiz e o alvo) não é diretório: o arquivo não poderia ser criado."""
    atual = alvo.parent
    while atual != raiz.parent and atual != atual.parent:
        if atual.exists() and not atual.is_dir():
            return True
        atual = atual.parent
    return False


def _unir_decisoes(existente: bytes, novo: bytes, relativo: str) -> bytes:
    """Mesma política (mesmo nome) com decisões por caminho diferentes: a união, se não houver caminho com decisão
    contrária; qualquer outra diferença é conflito."""
    a, b = json_de_bytes(existente), json_de_bytes(novo)
    if not (isinstance(a, dict) and isinstance(b, dict)) or {**a, "decisoes": None} != {**b, "decisoes": None}:
        raise EvidenciaInvalida(f"camara_evidencia_conflita_com_o_home:{relativo}")
    da, db = a.get("decisoes"), b.get("decisoes")
    if not (isinstance(da, dict) and isinstance(db, dict)) or any(da[k] != db[k] for k in da.keys() & db.keys()):
        raise EvidenciaInvalida(f"camara_evidencia_conflita_com_o_home:{relativo}")
    return _json_bytes({**a, "decisoes": {**da, **db}})


class Publicacao:
    """Instalação transacional da evidência administrativa no home (0081 r2, R2-7).

    `preparar()` faz o preflight completo, SEM escrever no home: todos os conflitos (arquivo existente com bytes
    diferentes, componente de caminho que não é diretório, obtenções ilegíveis no home) e a união com o home, e deixa em
    staging só o que mudará. `publicar()` move do staging para o home (mesmo volume) guardando o que havia antes;
    `desfazer()` restaura o estado anterior, também depois de uma falha no meio da publicação ou de uma falha posterior
    do chamador. Instalar não ativa a rota."""

    def __init__(self, home: Path, arquivos: dict[str, bytes], staging: Path):
        self.estado = Estado(home)
        self.arquivos = arquivos
        self.staging = Path(staging)
        self.plano: dict[str, bytes] = {}
        self._anterior: dict[str, bytes | None] = {}
        self._diario: list[str] = []
        self._pastas: list[Path] = []

    @property
    def alterou(self) -> bool:
        return bool(self._diario)

    def preparar(self) -> "Publicacao":
        pasta = self.estado.pasta
        raiz = self.estado.home
        try:
            for relativo, dados in self.arquivos.items():
                tipo, _ = _tipo(relativo)
                if tipo == "obtencoes":
                    continue
                alvo = pasta / relativo
                if _ancestrais_invalidos(alvo, raiz):
                    raise EvidenciaInvalida(f"camara_evidencia_conflita_com_o_home:{relativo}")
                if alvo.is_file():
                    existente = alvo.read_bytes()
                    if existente == dados:
                        continue
                    if tipo != "politica":
                        raise EvidenciaInvalida(f"camara_evidencia_conflita_com_o_home:{relativo}")
                    self._anterior[relativo] = existente
                    self.plano[relativo] = _unir_decisoes(existente, dados, relativo)
                    continue
                if alvo.exists():
                    raise EvidenciaInvalida(f"camara_evidencia_conflita_com_o_home:{relativo}")
                self._anterior[relativo] = None
                self.plano[relativo] = dados
            novas = self.arquivos.get("obtencoes.jsonl")
            if novas is not None:
                alvo = pasta / "obtencoes.jsonl"
                if _ancestrais_invalidos(alvo, raiz):
                    raise EvidenciaInvalida("camara_evidencia_conflita_com_o_home:obtencoes.jsonl")
                existentes = self.estado.obtencoes()
                vistos = {json.dumps(r, sort_keys=True, ensure_ascii=False) for r in existentes}
                linhas = [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in existentes]
                for linha in novas.splitlines():
                    if not linha:
                        continue
                    canonica = json.dumps(json_de_bytes(linha), sort_keys=True, ensure_ascii=False)
                    if canonica not in vistos:
                        vistos.add(canonica)
                        linhas.append(canonica)
                uniao = ("\n".join(linhas) + "\n").encode("utf-8")
                atual = alvo.read_bytes() if alvo.is_file() else None
                if atual != uniao:
                    self._anterior["obtencoes.jsonl"] = atual
                    self.plano["obtencoes.jsonl"] = uniao
            # Preflight da UNIÃO (R3-2): o que o home tem, com o que será publicado por cima, validado pela mesma `_validar`
            # do snapshot. Home incoerente + pacote íntegro é recusado; não há tolerância a resto quebrado no destino.
            uniao = _arquivos_do_home(self.estado)
            uniao.update(self.plano)
            for relativo, dados in self.arquivos.items():
                uniao.setdefault(relativo, dados)
            _validar(uniao)
            for relativo, dados in self.plano.items():
                _escrever(self.staging / relativo, dados)
        except EvidenciaInvalida:
            raise
        except (OSError, ValueError, EstadoIndisponivel) as exc:
            raise EvidenciaInvalida("camara_instalacao_nao_preparada") from exc
        return self

    def publicar(self) -> None:
        """Move o preparado para o home. O diário registra cada arquivo ANTES de movê-lo, para o desfazimento cobrir também
        a falha no meio."""
        pasta = self.estado.pasta
        for relativo in self.plano:
            alvo = pasta / relativo
            faltantes = []
            atual = alvo.parent
            while not atual.exists() and atual != atual.parent:
                faltantes.append(atual)
                atual = atual.parent
            self._diario.append(relativo)
            alvo.parent.mkdir(parents=True, exist_ok=True)
            self._pastas += list(reversed(faltantes))
            os.replace(self.staging / relativo, alvo)

    def desfazer(self) -> None:
        """Restaura o `camara/` anterior. Tenta tudo e, se algo não pôde ser restaurado, levanta `OSError` agregado."""
        pasta = self.estado.pasta
        falhas = []
        for relativo in reversed(self._diario):
            alvo = pasta / relativo
            try:
                anterior = self._anterior.get(relativo)
                if anterior is None:
                    alvo.unlink(missing_ok=True)
                else:
                    _escrever(alvo, anterior)
            except (OSError, EstadoIndisponivel) as exc:
                falhas.append(f"{relativo}:{type(exc).__name__}")
        for diretorio in reversed(self._pastas):
            try:
                diretorio.rmdir()
            except OSError:
                pass  # não vazio ou já removido: o conteúdo não é nosso
        self._diario.clear()
        if falhas:
            raise OSError("camara_desfazimento_incompleto:" + ",".join(falhas))


def instalar(home: Path, arquivos: dict[str, bytes]) -> None:
    """Instalação atômica isolada (preflight, staging, publicação; desfaz se falhar), para uso fora do snapshot."""
    staging = Path(home) / f".camara-staging-{os.getpid()}-{id(arquivos)}"
    publicacao = Publicacao(home, arquivos, staging)
    try:
        publicacao.preparar()
        try:
            publicacao.publicar()
        except BaseException:
            publicacao.desfazer()
            raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


__all__ = ["EvidenciaInvalida", "Publicacao", "exportar", "preparar", "instalar", "PREFIXO"]
