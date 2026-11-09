"""Estado persistido da rota Câmara no home (decisão 0080, §§2, 4, 5 e 6; correções da 0081).

Layout de `<home>/camara/`: `robots-<host>.json` (política vigente e recibo), `robots-<host>-<sha>.txt` (bytes
originais da resposta, nomeados pelo hash), `politicas/` (recibo de cada política obtida), `bloqueio-<host>.json`
(barreiras do host e dos seus recursos), `ritmo-<host>.json` (início da última requisição, civil e monotônico),
`host-<host>.lock` (trava entre processos), `obtencoes.jsonl` (vínculo de cada obtenção à política e ao termo
vigentes), `termo/` (corpo pelo conteúdo e um recibo por obtenção), `revisao/` (bytes da revisão do auditor) e, no próprio home,
`camara_ativacao.json`. Sem `home`, o estado vive só em memória (replay e testes).

Toda escrita é atômica (arquivo temporário + `os.replace`). Falha de escrita, de leitura ou de esquema levanta
`EstadoIndisponivel`; quem chama decide a falha fechada.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from freoa_verifica import trava
from freoa_verifica.connectors import camara_robots as rb
from freoa_verifica.connectors.camara_policy import HOSTS, TERMO_URL
from freoa_verifica.identidade_http import USER_AGENT_IDENTIFICADO
from freoa_verifica.texto_resposta import texto_da_resposta
from freoa_verifica.transport import RespostaInvalida

ATIVACAO = "camara_ativacao.json"
VALIDADE_ROBOTS = timedelta(hours=24)
BLOQUEIO_TRANSITORIO = timedelta(hours=1)
REVALIDACAO_INICIAL = timedelta(hours=1)
REVALIDACAO_MAXIMA = timedelta(hours=24)
JANELA_DO_REGISTRO = timedelta(minutes=5)  # `em` (escrito após a resposta) fica a até este tempo da emissão (timeout 60 s)
SEM_TERMO = "portao_sem_ativacao_exigida"  # única ausência legítima de termo numa obtenção (replay e instrumento sem ativação)
_HEX64 = re.compile(r"[0-9a-f]{64}")


class EstadoIndisponivel(OSError):
    """Falha local de persistência, de leitura ou de esquema do estado."""


class LeituraLocalFalhou(EstadoIndisponivel):
    """O sistema de arquivos não deixou LER um arquivo que existe (permissão, E/S, diretório no lugar do arquivo).

    É falha local terminal e nunca se confunde com registro AUSENTE ou INVÁLIDO (documentação que não existe ou não
    confere), que é condição documental: a rota segue pendente, sem encerrar a unidade (0081 r2, R2-3)."""


class Relogio:
    """Relógio injetável: `monotonic` mede intervalos, `agora` é o instante UTC, `sleep` espera."""

    def monotonic(self) -> float:
        return time.monotonic()

    def agora(self) -> datetime:
        return datetime.now(timezone.utc)

    def sleep(self, segundos: float) -> None:
        time.sleep(segundos)


def iso(instante: datetime) -> str:
    return instante.astimezone(timezone.utc).isoformat()


def _invalido(nome: str):
    raise EstadoIndisponivel(f"estado_invalido:{nome}")


def _de_iso(texto) -> datetime:
    """Instante com fuso; qualquer outra coisa é esquema inválido (nunca `ValueError`/`TypeError` soltos)."""
    try:
        instante = datetime.fromisoformat(texto)
        instante.astimezone(timezone.utc)  # fuso fora do intervalo representável é falha de esquema, não OverflowError
    except (TypeError, ValueError, OverflowError):
        _invalido("instante")
    if instante.tzinfo is None:
        _invalido("instante_sem_fuso")
    return instante


def eh_sha256(valor) -> bool:
    return isinstance(valor, str) and _HEX64.fullmatch(valor) is not None


def _numero(valor, *, minimo: float = 0.0) -> float:
    """Número finito e não menor que `minimo`. Total: inteiro JSON grande demais para `float` é esquema inválido, não
    `OverflowError` solto (0081 r2, R2-3)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        _invalido("numero")
    try:
        numero = float(valor)
    except (OverflowError, ValueError):
        _invalido("numero")
    if not math.isfinite(numero) or numero < minimo:
        _invalido("numero")
    return numero


def _texto(valor) -> str:
    if not isinstance(valor, str) or not valor:
        _invalido("texto")
    return valor


def sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def selo_do_recibo(recibo: dict) -> str:
    """Identidade da OBTENÇÃO do termo: hash dos bytes gravados do recibo (a do conteúdo é o hash do corpo)."""
    return sha256(_json_bytes(recibo))


def json_de_bytes(dados: bytes):
    """JSON de bytes preservados pela interpretação textual única (nunca bytes direto ao parser); inválido é ValueError."""
    try:
        return json.loads(texto_da_resposta(dados, "application/json; charset=utf-8"))
    except RespostaInvalida as exc:
        raise ValueError("json_ilegivel") from exc


def _escrever(caminho: Path, dados: bytes) -> None:
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = caminho.with_name(f".{caminho.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        temporario.write_bytes(dados)
        os.replace(temporario, caminho)
    except OSError as exc:
        raise EstadoIndisponivel(str(exc)) from exc


def _json_de(caminho: Path, padrao):
    try:
        return json_de_bytes(caminho.read_bytes())
    except FileNotFoundError:
        return padrao
    except OSError as exc:
        raise LeituraLocalFalhou(f"leitura local falhou: {caminho.name}") from exc
    except ValueError as exc:
        raise EstadoIndisponivel(f"estado ilegível: {caminho.name}") from exc


def _json_bytes(valor) -> bytes:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")


# --- esquemas persistidos ---------------------------------------------------------------------------------------------
_LIMITE_ROBOTS = 1024**2


def _media(content_type: str) -> str:
    return content_type.split(";", 1)[0].strip().lower()


def _conferir_com_o_corpo(registro: dict, corpo: bytes) -> None:
    """O recibo da política como EVIDÊNCIA dos bytes preservados (0081 r2, R2-2): hash, status 200, tamanho, MIME, UA
    efetivo, tokens, grupos considerados, atraso e decisões por caminho têm de ser exatamente os que os bytes produzem.
    O recibo nunca é fonte de verdade sobre o que os bytes dizem."""
    if sha256(corpo) != registro["sha256"]:
        _invalido("corpo_do_robots_diverge_do_hash")
    if (registro["status"] != 200 or registro["bytes"] != len(corpo) or not 0 < len(corpo) <= _LIMITE_ROBOTS
            or registro["mime"] != "text/plain" or _media(registro["content_type"]) != "text/plain"
            or registro["user_agent"] != USER_AGENT_IDENTIFICADO or registro["tokens"] != list(rb.TOKENS)):
        _invalido("politica_recibo_incoerente")
    try:
        grupos = rb.interpretar(texto_da_resposta(corpo, registro["content_type"]))
    except (RespostaInvalida, rb.RobotsInconclusivo):
        _invalido("politica_corpo_nao_interpretavel")
    geral = rb.decidir(grupos, "/")
    if (geral.estado == rb.INCONCLUSIVO or registro["grupos_considerados"] != [list(g) for g in geral.grupos_considerados]
            or float(registro["crawl_delay"]) != geral.crawl_delay):
        _invalido("politica_derivados_divergem_dos_bytes")
    if any(rb.decidir(grupos, caminho).estado != estado for caminho, estado in registro["decisoes"].items()):
        _invalido("politica_decisoes_divergem_dos_bytes")


def validar_politica(registro, host: str | None = None, corpo: bytes | None = None) -> dict:
    """Esquema do recibo de política (0080 §4.4). Estrutura inválida é falha local, não `KeyError`. Com `corpo`
    (bytes originais preservados) confere também a coerência integral do recibo com eles."""
    if not isinstance(registro, dict):
        _invalido("politica")
    if (not isinstance(registro.get("host"), str) or (host is not None and registro["host"] != host)
            or registro["host"] not in HOSTS or registro.get("url") != f"https://{registro['host']}/robots.txt"):
        _invalido("politica_host")
    if not eh_sha256(registro.get("sha256")):
        _invalido("politica_sha256")
    obtido, valido = _de_iso(registro.get("obtido_em")), _de_iso(registro.get("valido_ate"))
    try:
        limite = obtido + VALIDADE_ROBOTS
    except OverflowError:
        _invalido("politica_validade")
    if not obtido < valido <= limite:
        _invalido("politica_validade")
    _numero(registro.get("crawl_delay"))
    for campo in ("user_agent", "mime", "content_type"):
        _texto(registro.get(campo))
    if (not isinstance(registro.get("tokens"), list) or not all(isinstance(t, str) for t in registro["tokens"])
            or not isinstance(registro.get("grupos_considerados"), list)
            or not isinstance(registro.get("decisoes"), dict)
            or not all(isinstance(k, str) and v in {"permitido", "proibido", "inconclusivo"}
                       for k, v in registro["decisoes"].items())):
        _invalido("politica_campos")
    if (isinstance(registro.get("status"), bool) or not isinstance(registro.get("status"), int)
            or isinstance(registro.get("bytes"), bool) or not isinstance(registro.get("bytes"), int)):
        _invalido("politica_recibo")
    if corpo is not None:
        _conferir_com_o_corpo(registro, corpo)
    return registro


def _validar_bloqueio(registro) -> dict:
    if not isinstance(registro, dict):
        _invalido("bloqueio")
    _texto(registro.get("classe")), _texto(registro.get("motivo"))
    _de_iso(registro.get("desde"))
    if registro.get("ate") is not None:
        _de_iso(registro["ate"])
    if registro.get("categoria") is not None and not isinstance(registro["categoria"], str):
        _invalido("bloqueio_categoria")
    if not isinstance(registro.get("evidencia", {}), dict):
        _invalido("bloqueio_evidencia")
    return registro


def _validar_bloqueios(dados, host: str) -> dict:
    if not isinstance(dados, dict):
        _invalido("bloqueios")
    dados.setdefault("host", None)
    dados.setdefault("recursos", {})
    dados.setdefault("revalidacao", None)
    dados.setdefault("reaberturas", [])
    if dados["host"] is not None:
        _validar_bloqueio(dados["host"])
    if not isinstance(dados["recursos"], dict):
        _invalido("bloqueios_recursos")
    for url, registro in dados["recursos"].items():
        if not isinstance(url, str):
            _invalido("bloqueios_recursos")
        _validar_bloqueio(registro)
    revalidacao = dados["revalidacao"]
    if revalidacao is not None:
        if not isinstance(revalidacao, dict):
            _invalido("revalidacao")
        _de_iso(revalidacao.get("proxima"))
        _numero(revalidacao.get("intervalo_s"), minimo=1.0)
    if not isinstance(dados["reaberturas"], list) or not all(isinstance(r, dict) for r in dados["reaberturas"]):
        _invalido("reaberturas")
    return dados


def validar_obtencao(registro) -> dict:
    """Vínculo de uma obtenção: identifica a CAPTURA pela tripla (`sha256`, `url`, `capturado_em`) que o banco usa, a
    política que a autorizou (hash e instante), o instante da EMISSÃO (`emitida_em`, em que a política foi reconfirmada
    válida) e o termo vigente NA EMISSÃO, pelo conteúdo (`termo_sha256`) e pelo recibo da obtenção (`termo_recibo_sha256`).
    Termo nulo só com o marcador explícito `sem_termo` (0081 r3, R3-1 e R3-6). `em` é escrito depois da resposta: só se
    exige que não preceda a emissão e que a siga em até `JANELA_DO_REGISTRO`."""
    if (not isinstance(registro, dict) or not isinstance(registro.get("url"), str)
            or not eh_sha256(registro.get("sha256")) or not eh_sha256(registro.get("politica_sha256"))):
        _invalido("obtencao")
    termo, recibo, motivo = registro.get("termo_sha256"), registro.get("termo_recibo_sha256"), registro.get("sem_termo")
    if termo is None:
        if recibo is not None or motivo != SEM_TERMO:
            _invalido("obtencao_sem_termo_nao_marcada")
    elif not eh_sha256(termo) or not eh_sha256(recibo) or motivo is not None:
        _invalido("obtencao_termo")
    _de_iso(registro.get("politica_obtida_em")), _de_iso(registro.get("capturado_em"))
    emitida, em = _de_iso(registro.get("emitida_em")), _de_iso(registro.get("em"))
    if not emitida <= em <= emitida + JANELA_DO_REGISTRO:
        _invalido("obtencao_instantes")
    return registro


def validar_recibo_do_termo(recibo, digest: str, tamanho: int) -> dict:
    """Recibo íntegro do termo (0080 §2.2): URL exata, 200, MIME, tamanho, instante, hash e vínculo à política."""
    if (not isinstance(recibo, dict) or recibo.get("url") != TERMO_URL or recibo.get("status") != 200
            or isinstance(recibo.get("status"), bool) or recibo.get("mime") != "text/html"
            or recibo.get("bytes") != tamanho or isinstance(recibo.get("bytes"), bool)
            or recibo.get("sha256") != digest or not eh_sha256(recibo.get("politica_robots_sha256"))
            or recibo.get("user_agent") != USER_AGENT_IDENTIFICADO
            or (recibo.get("data_ou_versao_exibida") is not None and not isinstance(recibo["data_ou_versao_exibida"], str))):
        _invalido("recibo_do_termo")
    _de_iso(recibo.get("capturado_em"))
    return recibo


_TRAVAS_LOCAIS: dict[str, threading.RLock] = {}
_TRAVAS_LOCAIS_GUARDA = threading.Lock()


class Estado:
    def __init__(self, home: Path | str | None):
        self.home = None if home is None else Path(home)
        self._memoria: dict[str, object] = {}

    # --- armazenamento ---------------------------------------------------------------------------------------
    @property
    def pasta(self) -> Path | None:
        return None if self.home is None else self.home / "camara"

    def _ler(self, nome: str, padrao):
        if self.home is None:
            return json.loads(json.dumps(self._memoria.get(nome, padrao)))
        return _json_de(self.pasta / nome, padrao)

    def _gravar(self, nome: str, valor) -> None:
        if self.home is None:
            self._memoria[nome] = json.loads(json.dumps(valor))
            return
        _escrever(self.pasta / nome, _json_bytes(valor))

    def _bytes(self, nome: str) -> bytes | None:
        """Bytes de um arquivo do estado, lidos uma vez; ausente é None, ilegível é falha local."""
        if self.home is None:
            valor = self._memoria.get(nome)
            return None if valor is None else bytes(valor)  # type: ignore[arg-type]
        try:
            return (self.pasta / nome).read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise LeituraLocalFalhou(f"leitura local falhou: {nome}") from exc

    def _gravar_bytes(self, nome: str, dados: bytes) -> None:
        if self.home is None:
            self._memoria[nome] = bytes(dados)
            return
        _escrever(self.pasta / nome, dados)

    # --- trava por host (entre threads e processos do mesmo home) -------------------------------------------------
    @contextlib.contextmanager
    def trava_do_host(self, host: str, timeout: float = 600.0):
        chave = f"{self.home}|{host}"
        with _TRAVAS_LOCAIS_GUARDA:
            local = _TRAVAS_LOCAIS.setdefault(chave, threading.RLock())
        if not local.acquire(timeout=timeout):
            raise EstadoIndisponivel("trava_do_host_indisponivel")
        try:
            if self.home is None:
                yield
                return
            try:
                self.pasta.mkdir(parents=True, exist_ok=True)
                fd = trava._abrir(self.pasta / f"host-{host}.lock")
            except OSError as exc:
                raise EstadoIndisponivel(str(exc)) from exc
            try:
                fim = time.monotonic() + timeout
                while not trava._travar(fd):
                    if time.monotonic() > fim:
                        raise EstadoIndisponivel("trava_do_host_indisponivel")
                    time.sleep(0.02)
                try:
                    yield
                finally:
                    trava._soltar(fd)
            finally:
                os.close(fd)
        finally:
            local.release()

    # --- ritmo ---------------------------------------------------------------------------------------------------
    def ultimo_inicio(self, host: str) -> tuple[datetime, float] | None:
        """(instante civil, marca monotônica) do início da última requisição ao host, comparáveis entre processos."""
        dados = self._ler(f"ritmo-{host}.json", None)
        if dados is None:
            return None
        if not isinstance(dados, dict):
            _invalido("ritmo")
        return _de_iso(dados.get("inicio")), _numero(dados.get("mono"), minimo=-math.inf)

    def marcar_inicio(self, host: str, instante: datetime, mono: float) -> None:
        self._gravar(f"ritmo-{host}.json", {"inicio": iso(instante), "mono": mono})

    # --- robots --------------------------------------------------------------------------------------------------
    def politica(self, host: str) -> dict | None:
        """Recibo vigente validado COMO EVIDÊNCIA dos bytes preservados (hash, status, tamanho, MIME, UA, tokens, grupos,
        atraso e decisões recomputados dos bytes); qualquer divergência é falha local, nunca valor aceito."""
        registro = self._ler(f"robots-{host}.json", None)
        if registro is None:
            return None
        validar_politica(registro, host)
        return validar_politica(registro, host, self.corpo_da_politica(host, registro["sha256"]))

    @staticmethod
    def _nome_arquivado(host: str, registro: dict) -> str:
        try:
            instante = int(_de_iso(registro["obtido_em"]).timestamp())
        except (OverflowError, OSError, ValueError):
            _invalido("politica_instante")
        return f"politicas/{host}-{registro['sha256']}-{instante}.json"

    def gravar_politica(self, host: str, registro: dict, corpo: bytes) -> None:
        """`corpo` são os bytes ORIGINAIS da resposta; o recibo tem de ser coerente com eles (hash, tamanho, derivados)."""
        validar_politica(registro, host, corpo)
        nome = self._nome_arquivado(host, registro)
        self._gravar_bytes(f"robots-{host}-{registro['sha256']}.txt", corpo)
        self._gravar(nome, registro)
        self._gravar(f"robots-{host}.json", registro)

    def regravar_politica(self, host: str, registro: dict) -> None:
        """Atualiza o recibo vigente E o arquivado de mesmo nome (decisões por caminho): o artefato arquivado é o que
        viaja no snapshot e não pode ficar com as decisões iniciais. O corpo e o hash não mudam."""
        validar_politica(registro, host, self.corpo_da_politica(host, registro["sha256"]))
        self._gravar(self._nome_arquivado(host, registro), registro)
        self._gravar(f"robots-{host}.json", registro)

    def atraso_da_politica(self, registro: dict) -> float:
        """Atraso aplicável RECOMPUTADO dos bytes conferidos (nunca o campo declarado no recibo)."""
        corpo = self.corpo_da_politica(registro["host"], registro["sha256"])
        try:
            grupos = rb.interpretar(texto_da_resposta(corpo, registro["content_type"]))
        except (RespostaInvalida, rb.RobotsInconclusivo):
            _invalido("politica_corpo_nao_interpretavel")
        return rb.decidir(grupos, "/").crawl_delay

    def corpo_da_politica(self, host: str, digest: str) -> bytes:
        """Bytes originais do robots, conferidos contra o hash do recibo em TODA releitura."""
        corpo = self._bytes(f"robots-{host}-{digest}.txt")
        if corpo is None:
            raise EstadoIndisponivel("corpo_do_robots_ausente")
        if sha256(corpo) != digest:
            raise EstadoIndisponivel("corpo_do_robots_diverge_do_hash")
        return corpo

    def politicas_arquivadas(self, host: str) -> list[dict]:
        """Recibos de todas as políticas já obtidas para o host (a vigente e as anteriores)."""
        if self.home is None:
            nomes = sorted(n for n in self._memoria if n.startswith(f"politicas/{host}-"))
            registros = [self._memoria[n] for n in nomes]
        else:
            try:
                arquivos = sorted((self.pasta / "politicas").glob(f"{host}-*.json"))
            except OSError as exc:
                raise LeituraLocalFalhou(str(exc)) from exc
            registros = [_json_de(a, None) for a in arquivos]
        return [validar_politica(r, host, self.corpo_da_politica(host, r["sha256"])
                                 if isinstance(r, dict) and eh_sha256(r.get("sha256")) else None) for r in registros]

    def descartar_politica(self, host: str) -> None:
        if self.home is None:
            self._memoria.pop(f"robots-{host}.json", None)
            return
        try:
            (self.pasta / f"robots-{host}.json").unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise EstadoIndisponivel(str(exc)) from exc

    def politica_valida(self, host: str, agora: datetime) -> dict | None:
        """Política dentro da validade (24 h contadas do instante ORIGINAL da obtenção); expirada é None."""
        registro = self.politica(host)
        if registro is None:
            return None
        if not _de_iso(registro["obtido_em"]) <= agora < _de_iso(registro["valido_ate"]):
            return None
        return registro

    # --- barreiras (§6) ------------------------------------------------------------------------------------------
    def _bloqueios(self, host: str) -> dict:
        return _validar_bloqueios(self._ler(f"bloqueio-{host}.json", {}), host)

    def bloqueio_do_host(self, host: str, agora: datetime) -> dict | None:
        """Bloqueio vigente do host; o transitório (1 h) expira sozinho."""
        dados = self._bloqueios(host)["host"]
        if dados is None:
            return None
        if dados.get("ate") is not None and agora >= _de_iso(dados["ate"]):
            return None
        return dados

    def bloqueio_do_recurso(self, host: str, url: str) -> dict | None:
        return self._bloqueios(host)["recursos"].get(url)

    def revalidacao(self, host: str) -> dict | None:
        return self._bloqueios(host)["revalidacao"]

    def bloquear_host(self, host: str, registro: dict) -> None:
        dados = self._bloqueios(host)
        dados["host"] = registro
        if registro.get("classe") != "robots_inconclusivo":
            dados["revalidacao"] = None
        self._gravar(f"bloqueio-{host}.json", dados)

    def bloquear_robots_inconclusivo(self, host: str, registro: dict, proxima: datetime, intervalo: timedelta) -> None:
        """Bloqueio e agendamento da revalidação numa só gravação: nunca um sem o outro."""
        dados = self._bloqueios(host)
        dados["host"] = registro
        dados["revalidacao"] = {"proxima": iso(proxima), "intervalo_s": intervalo.total_seconds()}
        self._gravar(f"bloqueio-{host}.json", dados)

    def bloquear_recurso(self, host: str, url: str, registro: dict) -> None:
        dados = self._bloqueios(host)
        dados["recursos"].setdefault(url, registro)
        self._gravar(f"bloqueio-{host}.json", dados)

    def limpar_robots_inconclusivo(self, host: str) -> None:
        """Leitura válida de robots encerra o bloqueio por robots inconclusivo (e só ele)."""
        dados = self._bloqueios(host)
        if dados["host"] is not None and dados["host"].get("classe") == "robots_inconclusivo":
            dados["host"], dados["revalidacao"] = None, None
            self._gravar(f"bloqueio-{host}.json", dados)

    def liberar_host(self, host: str, decisao: str, agora: datetime) -> bool:
        """Reabertura registrada do host, indivisível: a política é descartada ANTES de o bloqueio cair.

        Se o descarte falha, o bloqueio permanece; se a gravação do desbloqueio falha, a política já se foi (nova
        leitura obrigatória) e o bloqueio permanece. Nenhum estado intermediário autoriza obtenção."""
        dados = self._bloqueios(host)
        existia = dados["host"] is not None or dados["revalidacao"] is not None
        self.descartar_politica(host)
        dados["reaberturas"].append({"escopo": "host", "decisao": decisao, "em": iso(agora),
                                     "anterior": dados["host"]})
        dados["host"], dados["revalidacao"] = None, None
        self._gravar(f"bloqueio-{host}.json", dados)
        return existia

    def liberar_recurso(self, host: str, url: str, revisao: str, agora: datetime) -> bool:
        dados = self._bloqueios(host)
        anterior = dados["recursos"].pop(url, None)
        dados["reaberturas"].append({"escopo": "recurso", "url": url, "revisao": revisao, "em": iso(agora),
                                     "anterior": anterior})
        self._gravar(f"bloqueio-{host}.json", dados)
        return anterior is not None

    def reaberturas(self, host: str) -> list[dict]:
        return self._bloqueios(host)["reaberturas"]

    # --- vínculo obtenção → política e termo ----------------------------------------------------------------------
    def registrar_obtencao(self, registro: dict) -> None:
        validar_obtencao(registro)
        linha = json.dumps(registro, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        if self.home is None:
            self._memoria.setdefault("obtencoes", []).append(registro)  # type: ignore[union-attr]
            return
        try:
            self.pasta.mkdir(parents=True, exist_ok=True)
            with (self.pasta / "obtencoes.jsonl").open("ab") as saida:
                saida.write(linha)
        except OSError as exc:
            raise EstadoIndisponivel(str(exc)) from exc

    def obtencoes(self) -> list[dict]:
        if self.home is None:
            return [validar_obtencao(r) for r in self._memoria.get("obtencoes", [])]  # type: ignore[union-attr]
        dados = self._bytes("obtencoes.jsonl")
        if dados is None:
            return []
        try:
            return [validar_obtencao(json_de_bytes(linha)) for linha in dados.splitlines() if linha]
        except ValueError as exc:
            raise EstadoIndisponivel("obtencoes ilegíveis") from exc

    # --- ativação (§2) -------------------------------------------------------------------------------------------
    def ler_ativacao(self) -> dict | None:
        """Registro gravado; ausente OU ilegível como JSON é `None` (não há registro válido). Falha local ao LER o arquivo
        existente levanta `LeituraLocalFalhou` (terminal), nunca vira ausência."""
        if self.home is None:
            return self._memoria.get(ATIVACAO)  # type: ignore[return-value]
        try:
            return _json_de(self.home / ATIVACAO, None)
        except LeituraLocalFalhou:
            raise
        except EstadoIndisponivel:
            return None

    def gravar_ativacao(self, registro: dict) -> None:
        if self.home is None:
            self._memoria[ATIVACAO] = registro
            return
        _escrever(self.home / ATIVACAO, _json_bytes(registro))

    def guardar_termo(self, corpo: bytes, recibo: dict) -> str:
        """Conserva os bytes (nomeados pelo conteúdo) e o recibo DESTA obtenção (nomeado pelo hash do próprio recibo):
        recapturar os mesmos bytes em outro instante ou sob outra política não sobrescreve a proveniência anterior
        (0081 r3, R3-6). Devolve o hash do conteúdo; o do recibo é `selo_do_recibo(recibo)`."""
        digest = sha256(corpo)
        validar_recibo_do_termo(recibo, digest, len(corpo))
        self._gravar_bytes(f"termo/{digest}.html", corpo)
        self._gravar_bytes(f"termo/{digest}.{selo_do_recibo(recibo)}.recibo.json", _json_bytes(recibo))
        return digest

    def termo_preservado(self, digest: str, recibo_sha256: str) -> dict | None:
        """Recibo do termo se os bytes preservados conferem com o hash e o recibo (identificado pelo hash dos seus
        próprios bytes) está íntegro; senão None.

        Cada arquivo é lido uma vez; recibo incompatível (URL, status, MIME, tamanho, instante, hash, vínculo à
        política) não é termo preservado."""
        if not eh_sha256(digest) or not eh_sha256(recibo_sha256):
            return None
        corpo = self._bytes(f"termo/{digest}.html")  # falha local de leitura NÃO é ausência: propaga
        bruto = self._bytes(f"termo/{digest}.{recibo_sha256}.recibo.json")
        if corpo is None or bruto is None or sha256(corpo) != digest or sha256(bruto) != recibo_sha256:
            return None
        try:
            return validar_recibo_do_termo(json_de_bytes(bruto), digest, len(corpo))
        except (EstadoIndisponivel, ValueError):
            return None

    def guardar_revisao(self, dados: bytes) -> str:
        digest = sha256(dados)
        self._gravar_bytes(f"revisao/{digest}.json", dados)
        return digest

    def revisao_preservada(self, digest: str) -> bytes | None:
        """Bytes da revisão do auditor se conferem com o hash; senão None."""
        if not eh_sha256(digest):
            return None
        dados = self._bytes(f"revisao/{digest}.json")  # falha local de leitura NÃO é ausência: propaga
        return dados if dados is not None and sha256(dados) == digest else None

    def gravar_pre_ativacao(self, registro: dict) -> None:
        self._gravar("pre-ativacao.json", registro)

    def ler_pre_ativacao(self) -> dict | None:
        return self._ler("pre-ativacao.json", None)
