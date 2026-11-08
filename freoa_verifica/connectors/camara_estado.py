"""Estado persistido da rota Câmara no home (decisão 0080, §§2, 4, 5 e 6).

Layout de `<home>/camara/`: `robots-<host>.json` (política e recibo), `bloqueio-<host>.json` (barreiras do host e
dos seus recursos), `ritmo-<host>.json` (início da última requisição), `host-<host>.lock` (trava entre processos),
`obtencoes.jsonl` (vínculo de cada obtenção à política que a autorizou), `termo/` (captura do termo) e, no próprio
home, `camara_ativacao.json`. Sem `home`, o estado vive só em memória (replay e testes).

Toda escrita é atômica (arquivo temporário + `os.replace`). Falha de escrita levanta `EstadoIndisponivel`; quem
chama decide a falha fechada.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from freoa_verifica import trava

ATIVACAO = "camara_ativacao.json"
VALIDADE_ROBOTS = timedelta(hours=24)
BLOQUEIO_TRANSITORIO = timedelta(hours=1)
REVALIDACAO_INICIAL = timedelta(hours=1)
REVALIDACAO_MAXIMA = timedelta(hours=24)


class EstadoIndisponivel(OSError):
    """Falha local de persistência ou de leitura do estado."""


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


def _de_iso(texto: str) -> datetime:
    return datetime.fromisoformat(texto)


def sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


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
        return json.loads(caminho.read_bytes())
    except FileNotFoundError:
        return padrao
    except (OSError, ValueError) as exc:
        raise EstadoIndisponivel(f"estado ilegível: {caminho.name}") from exc


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
        _escrever(self.pasta / nome, json.dumps(valor, ensure_ascii=False, sort_keys=True, indent=1).encode())

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
    def ultimo_inicio(self, host: str) -> datetime | None:
        valor = self._ler(f"ritmo-{host}.json", {}).get("inicio")
        return None if valor is None else _de_iso(valor)

    def marcar_inicio(self, host: str, instante: datetime) -> None:
        self._gravar(f"ritmo-{host}.json", {"inicio": iso(instante)})

    # --- robots --------------------------------------------------------------------------------------------------
    def politica(self, host: str) -> dict | None:
        return self._ler(f"robots-{host}.json", None)

    def gravar_politica(self, host: str, registro: dict, corpo: bytes) -> None:
        self._gravar(f"robots-{host}.json", registro)
        if self.home is not None:
            _escrever(self.pasta / f"robots-{host}-{registro['sha256']}.txt", corpo)
        else:
            self._memoria[f"corpo-{registro['sha256']}"] = corpo.decode("utf-8", "replace")

    def descartar_politica(self, host: str) -> None:
        if self.home is None:
            self._memoria.pop(f"robots-{host}.json", None)
        else:
            with contextlib.suppress(FileNotFoundError):
                (self.pasta / f"robots-{host}.json").unlink()

    def politica_valida(self, host: str, agora: datetime) -> dict | None:
        registro = self.politica(host)
        if not registro:
            return None
        try:
            if not _de_iso(registro["obtido_em"]) <= agora < _de_iso(registro["valido_ate"]):
                return None
        except (KeyError, ValueError):
            return None
        return registro

    # --- barreiras (§6) ------------------------------------------------------------------------------------------
    def _bloqueios(self, host: str) -> dict:
        dados = self._ler(f"bloqueio-{host}.json", {})
        dados.setdefault("host", None)
        dados.setdefault("recursos", {})
        dados.setdefault("revalidacao", None)
        dados.setdefault("reaberturas", [])
        return dados

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

    def bloquear_recurso(self, host: str, url: str, registro: dict) -> None:
        dados = self._bloqueios(host)
        dados["recursos"].setdefault(url, registro)
        self._gravar(f"bloqueio-{host}.json", dados)

    def agendar_revalidacao(self, host: str, proxima: datetime, intervalo: timedelta) -> None:
        dados = self._bloqueios(host)
        dados["revalidacao"] = {"proxima": iso(proxima), "intervalo_s": intervalo.total_seconds()}
        self._gravar(f"bloqueio-{host}.json", dados)

    def limpar_robots_inconclusivo(self, host: str) -> None:
        """Leitura válida de robots encerra o bloqueio por robots inconclusivo (e só ele)."""
        dados = self._bloqueios(host)
        if dados["host"] is not None and dados["host"].get("classe") == "robots_inconclusivo":
            dados["host"], dados["revalidacao"] = None, None
            self._gravar(f"bloqueio-{host}.json", dados)

    def liberar_host(self, host: str, decisao: str, agora: datetime) -> bool:
        """Reabertura registrada do host: apaga bloqueio e política (nova leitura de robots obrigatória)."""
        dados = self._bloqueios(host)
        existia = dados["host"] is not None or dados["revalidacao"] is not None
        dados["reaberturas"].append({"escopo": "host", "decisao": decisao, "em": iso(agora),
                                     "anterior": dados["host"]})
        dados["host"], dados["revalidacao"] = None, None
        self._gravar(f"bloqueio-{host}.json", dados)
        self.descartar_politica(host)
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

    # --- vínculo obtenção → política --------------------------------------------------------------------------------
    def registrar_obtencao(self, registro: dict) -> None:
        if self.home is None:
            self._memoria.setdefault("obtencoes", []).append(registro)  # type: ignore[union-attr]
            return
        try:
            self.pasta.mkdir(parents=True, exist_ok=True)
            with (self.pasta / "obtencoes.jsonl").open("ab") as saida:
                saida.write(json.dumps(registro, ensure_ascii=False, sort_keys=True).encode() + b"\n")
        except OSError as exc:
            raise EstadoIndisponivel(str(exc)) from exc

    def obtencoes(self) -> list[dict]:
        if self.home is None:
            return list(self._memoria.get("obtencoes", []))  # type: ignore[arg-type]
        try:
            return [json.loads(linha) for linha in (self.pasta / "obtencoes.jsonl").read_text("utf-8").splitlines()]
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as exc:
            raise EstadoIndisponivel("obtencoes ilegíveis") from exc

    # --- ativação (§2) -------------------------------------------------------------------------------------------
    def ler_ativacao(self) -> dict | None:
        if self.home is None:
            return self._memoria.get(ATIVACAO)  # type: ignore[return-value]
        return _json_de(self.home / ATIVACAO, None)

    def gravar_ativacao(self, registro: dict) -> None:
        if self.home is None:
            self._memoria[ATIVACAO] = registro
            return
        _escrever(self.home / ATIVACAO, json.dumps(registro, ensure_ascii=False, sort_keys=True, indent=1).encode())

    def guardar_termo(self, corpo: bytes, recibo: dict) -> str:
        digest = sha256(corpo)
        if self.home is None:
            self._memoria[f"termo-{digest}"] = {"corpo": corpo, "recibo": recibo}
            return digest
        _escrever(self.pasta / "termo" / f"{digest}.html", corpo)
        _escrever(self.pasta / "termo" / f"{digest}.recibo.json",
                  json.dumps(recibo, ensure_ascii=False, sort_keys=True, indent=1).encode())
        return digest

    def termo_preservado(self, digest: str) -> dict | None:
        """Recibo do termo se os bytes preservados existem e conferem com o hash; senão None."""
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            return None
        if self.home is None:
            guardado = self._memoria.get(f"termo-{digest}")
            return guardado["recibo"] if guardado and sha256(guardado["corpo"]) == digest else None  # type: ignore[index]
        try:
            corpo = (self.pasta / "termo" / f"{digest}.html").read_bytes()
            recibo = json.loads((self.pasta / "termo" / f"{digest}.recibo.json").read_bytes())
        except (OSError, ValueError):
            return None
        return recibo if sha256(corpo) == digest and recibo.get("sha256") == digest else None

    def gravar_pre_ativacao(self, registro: dict) -> None:
        self._gravar("pre-ativacao.json", registro)

    def ler_pre_ativacao(self) -> dict | None:
        return self._ler("pre-ativacao.json", None)
