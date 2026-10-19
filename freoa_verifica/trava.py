"""Trava de home entre processos (decisão 0040, A1).

Mecanismo único e portátil (POSIX e Windows), sem lock compartilhado: cada `Verifica` aberto cria
`<home>/.fv-uso/<pid>-<ulid>` e mantém lock EXCLUSIVO próprio nesse arquivo (fcntl.flock / msvcrt.locking).
Quem troca o banco (purga, instalação de snapshot, reconstrução) toma a porta `<home>/.fv.lock`
(registro de novos usuários espera enquanto a troca corre) e tenta travar cada arquivo de uso de OUTRO
pid: se não consegue, o dono está vivo e a operação é recusada; se consegue, o arquivo é resto de processo
morto e é removido. O lock morre com o processo, então não há resto "vivo" por crash.
Mesmo pid = mesmo processo, já coordenado por `Verifica.exclusivo()`.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

from freoa_verifica.ids import new_ulid

MOTIVO = "HOME_EM_USO_POR_OUTRO_PROCESSO"
PASTA_USO = ".fv-uso"
PORTA = ".fv.lock"


class HomeEmUso(RuntimeError):
    def __init__(self) -> None:
        super().__init__(MOTIVO)


if os.name == "nt":  # pragma: no cover - exercitado no CI windows-latest
    import msvcrt

    def _travar(fd: int) -> bool:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _soltar(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _travar(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _soltar(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _abrir(caminho: Path) -> int:
    return os.open(str(caminho), os.O_RDWR | os.O_CREAT, 0o600)


@contextmanager
def porta(home: Path, timeout: float = 30.0):
    """Lock exclusivo e curto de `<home>/.fv.lock`; serializa registro de usuários e trocas de banco."""
    fd = _abrir(Path(home) / PORTA)
    try:
        fim = time.monotonic() + timeout
        while not _travar(fd):
            if time.monotonic() > fim:
                raise HomeEmUso()
            time.sleep(0.02)
        try:
            yield
        finally:
            _soltar(fd)
    finally:
        os.close(fd)


def registrar(home: Path) -> tuple[int, Path]:
    """Marca este Verifica como usuário vivo do home. Devolve (fd, caminho) para `liberar`."""
    home = Path(home)
    pasta = home / PASTA_USO
    with porta(home):
        pasta.mkdir(exist_ok=True)
        caminho = pasta / f"{os.getpid()}-{new_ulid()}"
        fd = _abrir(caminho)
        if not _travar(fd):  # nome novo: não deveria falhar
            os.close(fd)
            raise OSError(f"não foi possível travar {caminho}")
    return fd, caminho


def liberar(marca: tuple[int, Path]) -> None:
    fd, caminho = marca
    try:
        _soltar(fd)
    except OSError:
        pass
    os.close(fd)
    try:
        caminho.unlink(missing_ok=True)  # Windows: só após fechar o descritor
    except OSError:
        pass


@contextmanager
def exclusivo_entre_processos(home: Path):
    """Garante que nenhum outro processo usa o home durante o bloco; senão levanta HomeEmUso."""
    home = Path(home)
    with porta(home):
        for arq in sorted((home / PASTA_USO).glob("*")) if (home / PASTA_USO).is_dir() else []:
            if arq.name.split("-", 1)[0] == str(os.getpid()):
                continue
            try:
                fd = _abrir(arq)
            except OSError:
                continue
            try:
                if not _travar(fd):
                    raise HomeEmUso()
                _soltar(fd)
            finally:
                os.close(fd)
            try:
                arq.unlink(missing_ok=True)  # resto de processo morto
            except OSError:
                pass
        yield
