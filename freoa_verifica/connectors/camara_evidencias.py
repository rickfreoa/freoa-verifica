"""Evidências administrativas da rota Câmara no snapshot (decisão 0080 §8.4; correções da 0081).

O snapshot transporta, além das capturas, o que sustenta a atribuição e a autorização de cada obtenção: termo (bytes e
recibo), revisão do auditor, política de robots (bytes e recibos), registros de obtenção (vínculo captura → política →
termo) e os registros de ativação como EVIDÊNCIA (instalar não ativa a rota). Tudo viaja em `camara/` sob o inventário
de hashes do manifesto; na instalação cada arquivo é conferido pelo nome (hash), pelo recibo e pela coerência com o
registro de ativação, e o conjunto é fundido ao home sem substituir o que já existe, de modo que snapshots com termos
diferentes coexistem e a atribuição por captura não se perde na anexação nem na reexportação.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from freoa_verifica.connectors import camara_ativacao as ativ
from freoa_verifica.connectors.camara_estado import (ATIVACAO, Estado, _escrever, sha256, validar_obtencao, validar_politica,
                                                     validar_recibo_do_termo)

_H = r"[0-9a-f]{64}"
_HOST = r"www2?\.camara\.leg\.br"
_PADROES = {
    "termo_corpo": re.compile(rf"termo/({_H})\.html"),
    "termo_recibo": re.compile(rf"termo/({_H})\.recibo\.json"),
    "revisao": re.compile(rf"revisao/({_H})\.json"),
    "robots": re.compile(rf"robots-({_HOST})-({_H})\.txt"),
    "politica": re.compile(rf"politicas/({_HOST})-({_H})-\d+\.json"),
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
        saida[relativo] = caminho.read_bytes()
    ativacao = estado.home / ATIVACAO if estado.home else None
    registros = []
    if ativacao is not None and ativacao.is_file():
        registros.append(ativacao.read_bytes())
    registros += [p.read_bytes() for p in sorted((pasta / "evidencias").glob("ativacao-*.json"))] \
        if (pasta / "evidencias").is_dir() else []
    for bruto in registros:
        try:
            registro = json.loads(bruto.decode("utf-8"))
        except ValueError:
            continue
        if isinstance(registro, dict) and isinstance(registro.get("registro_sha256"), str):
            saida[f"evidencias/ativacao-{registro['registro_sha256']}.json"] = bruto
    return saida


def _validar(arquivos: dict[str, bytes]) -> None:
    """Confere todas as evidências entre si; levanta `EvidenciaInvalida` no primeiro defeito."""
    memoria = Estado(None)
    termos, politicas_corpo = {}, set()
    for relativo, dados in arquivos.items():
        achado = _tipo(relativo)
        if achado is None:
            raise EvidenciaInvalida(f"camara_evidencia_nao_permitida:{relativo}")
        tipo, m = achado
        if tipo in {"termo_corpo", "revisao"} and sha256(dados) != m.group(1):
            raise EvidenciaInvalida(f"camara_evidencia_hash_diverge:{relativo}")
        if tipo == "robots":
            if sha256(dados) != m.group(2):
                raise EvidenciaInvalida(f"camara_evidencia_hash_diverge:{relativo}")
            politicas_corpo.add((m.group(1), m.group(2)))
        if tipo == "termo_corpo":
            termos[m.group(1)] = dados
        memoria._memoria[relativo] = dados
    try:
        for relativo, dados in arquivos.items():
            tipo, m = _tipo(relativo)
            if tipo == "termo_recibo":
                if m.group(1) not in termos:
                    raise EvidenciaInvalida(f"camara_recibo_sem_termo:{relativo}")
                validar_recibo_do_termo(json.loads(dados.decode("utf-8")), m.group(1), len(termos[m.group(1)]))
            elif tipo == "politica":
                registro = validar_politica(json.loads(dados.decode("utf-8")), m.group(1))
                if registro["sha256"] != m.group(2) or (m.group(1), m.group(2)) not in politicas_corpo:
                    raise EvidenciaInvalida(f"camara_politica_incoerente:{relativo}")
                memoria._memoria[relativo] = json.loads(dados.decode("utf-8"))
            elif tipo == "obtencoes":
                for linha in dados.decode("utf-8").splitlines():
                    if linha:
                        validar_obtencao(json.loads(linha))
        for relativo, dados in arquivos.items():
            tipo, m = _tipo(relativo)
            if tipo == "ativacao":
                registro = json.loads(dados.decode("utf-8"))
                if registro.get("registro_sha256") != m.group(1) or not ativ.validar_registro(memoria, registro):
                    raise EvidenciaInvalida(f"camara_ativacao_evidencia_invalida:{relativo}")
    except (ValueError, OSError, KeyError, TypeError) as exc:
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


def instalar(home: Path, arquivos: dict[str, bytes]) -> None:
    """Funde as evidências ao home sem substituir nada: arquivos nomeados pelo hash coexistem (termos diferentes de
    snapshots diferentes), as obtenções são unidas por registro e as ativações ficam só como evidência."""
    estado = Estado(home)
    for relativo, dados in arquivos.items():
        tipo, _ = _tipo(relativo)
        if tipo == "obtencoes":
            continue
        alvo = estado.pasta / relativo
        if alvo.exists():
            if alvo.read_bytes() != dados:
                raise EvidenciaInvalida(f"camara_evidencia_conflita_com_o_home:{relativo}")
            continue
        _escrever(alvo, dados)
    novas = arquivos.get("obtencoes.jsonl")
    if novas is None:
        return
    existentes = estado.obtencoes()
    vistos = {json.dumps(r, sort_keys=True, ensure_ascii=False) for r in existentes}
    linhas = [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in existentes]
    for linha in novas.decode("utf-8").splitlines():
        if not linha:
            continue
        canonica = json.dumps(json.loads(linha), sort_keys=True, ensure_ascii=False)
        if canonica not in vistos:
            vistos.add(canonica)
            linhas.append(canonica)
    _escrever(estado.pasta / "obtencoes.jsonl", ("\n".join(linhas) + "\n").encode("utf-8"))


__all__ = ["EvidenciaInvalida", "exportar", "preparar", "instalar", "PREFIXO"]
