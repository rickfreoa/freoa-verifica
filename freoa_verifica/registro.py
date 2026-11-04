"""Política de registro de entradas (C5/F09) e purga de execuções antigas."""

from __future__ import annotations

import contextvars
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLITICAS = ("completo", "sem_conteudo")

# Política da operação em curso; definida pela fachada em cada chamada pública.
PADRAO = "sem_conteudo"  # decisão 0040: `completo` só por opção explícita
politica_atual: contextvars.ContextVar[str] = contextvars.ContextVar("fv_registro", default=PADRAO)


def normalizar(valor: str | None) -> str:
    v = (valor or os.environ.get("FV_REGISTRO") or PADRAO).strip().lower()
    if v not in POLITICAS:
        raise ValueError(f"registro inválido: {v!r} (use {', '.join(POLITICAS)})")
    return v


ARQUIVO_CHAVE = "registro.key"
PREFIXO_HMAC = "hmac1:"  # versão do esquema; hashes antigos são sha256 puro (64 hex, sem prefixo)
_chaves_efemeras: dict[str, bytes] = {}


_cache_chaves: dict[str, tuple[bytes, tuple[int, int, int]]] = {}  # home -> (chave, (ino, size, mtime_ns))
META_IMPRESSAO = "registro_chave_sha256_16"


def _impressao(chave: bytes) -> str:
    return hashlib.sha256(chave).hexdigest()[:16]


def _assinatura(caminho: Path) -> tuple[int, int, int]:
    st = caminho.stat()
    return (st.st_ino, st.st_size, st.st_mtime_ns)


def _chave_ausente_com_historico(conn: sqlite3.Connection | None) -> bool:
    if conn is None:
        return False
    if conn.execute("SELECT 1 FROM meta WHERE key=?", (META_IMPRESSAO,)).fetchone():
        return True
    return conn.execute("SELECT 1 FROM run WHERE request_hash LIKE 'hmac1:%' LIMIT 1").fetchone() is not None


_TAG_ANCORA = b"\nlegado1:"  # arquivo da chave: 32 bytes, opcionalmente seguidos da âncora do legado (C8)


def _separar_chave(dados: bytes, caminho: Path) -> tuple[bytes, bytes]:
    """Chave (32 bytes) e o resto do arquivo (âncora do legado, vazio nos homes sem ela)."""
    chave, resto = dados[:32], dados[32:]
    if len(chave) != 32 or (resto and not resto.startswith(_TAG_ANCORA)):
        raise RuntimeError(f"{caminho} corrompida (esperado 32 bytes); remova-a ciente de que hashes antigos deixam de casar")
    return chave, resto


def ler_chave_do_home(home: Path) -> bytes:
    """Só leitura da chave (IL.0-R, C9): nunca cria o arquivo nem escreve no banco; ausente é erro.

    Serve à recuperação e à conferência de registros, que precisam funcionar em home somente leitura
    (`PRAGMA query_only=ON`). Criação e impressão digital ficam em `chave_do_home`.
    """
    caminho = Path(home) / ARQUIVO_CHAVE
    try:
        em_cache = _cache_chaves.get(str(caminho))
        if em_cache and em_cache[1] == _assinatura(caminho):
            return em_cache[0]
        dados = caminho.read_bytes()
        assinatura = _assinatura(caminho)
    except FileNotFoundError:
        raise RuntimeError(f"CHAVE_REGISTRO_AUSENTE: {caminho}") from None
    chave, _ = _separar_chave(dados, caminho)
    _cache_chaves[str(caminho)] = (chave, assinatura)
    return chave


def chave_do_home(home: Path, conn: sqlite3.Connection | None = None) -> bytes:
    """Segredo de 32 bytes do home (`<home>/registro.key`), criado atomicamente e com modo 0o600.

    Criação: grava em arquivo temporário no mesmo diretório (sincronizado) e `os.link` para o nome
    final; EEXIST (outro processo ganhou) lê o existente. Nunca existe estado de 0 byte. Com `conn`,
    a impressão digital (sha256, 16 hex) fica em `meta`; chave ausente com runs `hmac1:` ou impressão
    em `meta` é erro CHAVE_REGISTRO_AUSENTE (não se regenera em silêncio). Cache por home no processo,
    revalidado por stat (arquivo apagado, trocado ou corrompido não passa despercebido).
    Windows: o modo POSIX não se aplica; a proteção vem da ACL herdada da pasta do perfil.
    """
    caminho = Path(home) / ARQUIVO_CHAVE
    try:
        em_cache = _cache_chaves.get(str(caminho))
        if em_cache and em_cache[1] == _assinatura(caminho):
            return em_cache[0]
    except FileNotFoundError:
        pass
    criada = False
    if not caminho.exists():
        criada = True
        if _chave_ausente_com_historico(conn):
            raise RuntimeError(
                f"CHAVE_REGISTRO_AUSENTE: {caminho} sumiu mas o home tem registros com HMAC; "
                "restaure a chave original (uma nova invalidaria os hashes gravados)")
        tmp = caminho.with_name(f"{ARQUIVO_CHAVE}.{secrets.token_hex(8)}.tmp")
        fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(secrets.token_bytes(32))
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.link(tmp, caminho)
        except FileExistsError:
            pass
        finally:
            tmp.unlink(missing_ok=True)
    chave, _ = _separar_chave(caminho.read_bytes(), caminho)
    if conn is not None:
        conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)", (META_IMPRESSAO, _impressao(chave)))
    _cache_chaves[str(caminho)] = (chave, _assinatura(caminho))
    if conn is not None and criada:
        try:
            selar_legado(conn)  # C8: os registros sem MAC que já existem são os legados; os futuros terão MAC
        except OSError:
            pass  # sem âncora gravada, nenhum registro sem MAC passa por legado (falha fechada)
    return chave


def _home_da_conexao(conn: sqlite3.Connection) -> Path | None:
    arquivo = next((r[2] for r in conn.execute("PRAGMA database_list") if r[1] == "main"), "")
    return Path(arquivo).parent if arquivo else None


def hmac_entrada(conn: sqlite3.Connection, campo: str, valor: str, *, leitura: bool = False) -> str:
    """HMAC-SHA256 de conteúdo de entrada do usuário, com segredo do home e separação por campo.

    Só para entradas (citação, trecho, requisição). Hash de evidência pública (bytes de documento
    oficial, capturas) segue sha256 puro: é verificável por qualquer pessoa.

    `leitura=True` (C9) só lê a chave existente: não cria arquivo nem grava a impressão no banco.
    """
    home = _home_da_conexao(conn)
    if not home:
        chave = _chaves_efemeras.setdefault(str(id(conn)), secrets.token_bytes(32))
    else:
        chave = ler_chave_do_home(home) if leitura else chave_do_home(home, conn)
    mac = hmac.new(chave, campo.encode("utf-8") + b"\0" + valor.encode("utf-8"), hashlib.sha256)
    return PREFIXO_HMAC + mac.hexdigest()


def checkpoint_truncate(conn: sqlite3.Connection) -> None:
    """`wal_checkpoint(TRUNCATE)` que recusa quando o checkpoint não completou (busy != 0)."""
    busy = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]
    if busy:
        raise RuntimeError("wal_checkpoint_ocupado: há leitor/escritor ativo no banco")


def _fsync_arquivo(caminho: Path) -> None:
    with open(caminho, "r+b") as fh:  # Windows: fsync exige descritor gravável
        os.fsync(fh.fileno())


def _fsync_pasta(pasta: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(str(pasta), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def recuperar_purga(home: Path) -> bool:
    """Conclui uma purga interrompida entre mover o original e instalar o banco novo.

    O banco novo só existe pronto (íntegro e gravado em disco) quando o original é movido; portanto,
    sem `verifica.sqlite3` e com `verifica.sqlite3.purga-novo`, basta concluir a troca.
    """
    home = Path(home)
    db = home / "verifica.sqlite3"
    novo = home / "verifica.sqlite3.purga-novo"
    if db.exists() or not novo.exists():
        return False
    for suf in ("-wal", "-shm"):  # restos do original não podem acompanhar o banco novo
        resto = Path(str(db) + suf)
        if resto.exists():
            destino = home / "purgados" / "recuperado"
            destino.mkdir(parents=True, exist_ok=True)
            shutil.move(str(resto), str(destino / f"{resto.name}.{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}"))
    os.replace(novo, db)
    _fsync_pasta(home)
    return True


def purgar(home: Path, antes: str, apagar_original: bool = False) -> dict[str, Any]:
    """Reconstrói o banco sem as execuções anteriores a `antes` (AAAA-MM-DD).

    Ordem segura: constrói o banco novo e o grava em disco; só então move o original
    (com -wal/-shm) para `purgados/<data>/` e renomeia o novo para o lugar. Se o processo cair
    entre os dois renames, `recuperar_purga` conclui a troca na próxima abertura do serviço.
    Requer acesso exclusivo (o chamador fecha as conexões). Apagar o original, e seus
    backups externos, é responsabilidade do operador, salvo `apagar_original=True`: após a troca
    bem-sucedida, apaga o original movido (a purga em si não muda).
    """
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", antes):
        raise ValueError("data inválida: use AAAA-MM-DD")
    home = Path(home)
    db = home / "verifica.sqlite3"
    novo = home / "verifica.sqlite3.purga-novo"
    novo.unlink(missing_ok=True)
    src = sqlite3.connect(str(db))
    try:
        checkpoint_truncate(src)
        dst = sqlite3.connect(str(novo))
        try:
            src.backup(dst)
            trig = dst.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='run'"
            ).fetchall()
            for name, _ in trig:
                dst.execute(f'DROP TRIGGER "{name}"')
            n = dst.execute("DELETE FROM run WHERE created_at < ?", (antes,)).rowcount
            for _, sql in trig:
                dst.execute(sql)
            dst.commit()
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("purga: integridade do banco novo falhou")
            restantes = dst.execute("SELECT COUNT(*) FROM run").fetchone()[0]
            dst.execute("VACUUM")
            dst.execute("PRAGMA journal_mode=DELETE")
        finally:
            dst.close()
        _fsync_arquivo(novo)
    except Exception:
        novo.unlink(missing_ok=True)
        raise
    finally:
        src.close()
    agora = datetime.now(timezone.utc)
    pasta = home / "purgados" / agora.strftime("%Y-%m-%dT%H%M%S-%f")
    pasta.mkdir(parents=True)
    movidos = []
    for suf in ("-wal", "-shm", ""):  # o banco principal por último
        f = Path(str(db) + suf)
        if f.exists():
            shutil.move(str(f), str(pasta / f.name))
            movidos.append(str(pasta / f.name))
    os.replace(novo, db)
    _fsync_pasta(home)
    # A7: o registro da purga é gravado ANTES de apagar o original; depois da troca nada levanta exceção.
    registro = {"em": agora.isoformat(), "antes": antes, "removidas": n, "restantes": restantes,
                "original_movido_para": movidos, "original_apagado": False, "apagar_original_pedido": apagar_original}
    with (home / "purgas.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    apagados: list[str] = []
    falhas: list[dict[str, str]] = []
    if apagar_original:
        for m in movidos:
            try:
                Path(m).unlink(missing_ok=True)
                apagados.append(m)
            except OSError as exc:
                falhas.append({"arquivo": m, "erro": str(exc)[:120]})
        try:
            pasta.rmdir()
        except OSError as exc:
            if not falhas:
                falhas.append({"arquivo": str(pasta), "erro": str(exc)[:120]})
        registro.update(original_apagado=not falhas, original_movido_para=[f["arquivo"] for f in falhas])
        with (home / "purgas.jsonl").open("a", encoding="utf-8") as fh:  # desfecho da exclusão
            fh.write(json.dumps({"em": agora.isoformat(), "evento": "original_apagado", "apagados": apagados,
                                 "falhas": falhas}, ensure_ascii=False) + "\n")
    return {"status": "ok", **registro, "apagados": apagados, "falhas": falhas,
            "apagar_manualmente": [f["arquivo"] for f in falhas] if apagar_original else movidos}


# ----------------------------------------------------------------------
# Registro legado autenticado (IL.0-R, C8)
# ----------------------------------------------------------------------

META_LEGADO = "registro_legado_ids"
META_LEGADO_MAC = "registro_legado_mac"
_ancoras_efemeras: dict[int, tuple[sqlite3.Connection, str, str]] = {}  # banco sem home: a âncora vive no processo


def _canon_legado(ids: list[str]) -> str:
    return json.dumps(sorted(ids), ensure_ascii=False)


def _ancora_ler(conn: sqlite3.Connection) -> tuple[str, str] | None:
    """Âncora do conjunto legado, guardada FORA do banco: no arquivo da chave do home (trailer) ou, em banco sem home,
    na memória do processo. Quem altera o banco sem a chave não a apaga nem a recria. `None`: sem âncora."""
    home = _home_da_conexao(conn)
    if home is None:
        achada = _ancoras_efemeras.get(id(conn))
        return (achada[1], achada[2]) if achada and achada[0] is conn else None
    try:
        _, resto = _separar_chave((home / ARQUIVO_CHAVE).read_bytes(), home / ARQUIVO_CHAVE)
        if not resto:
            return None
        doc = json.loads(resto[len(_TAG_ANCORA):])
        return (doc["ids"], doc["mac"]) if isinstance(doc["ids"], str) and isinstance(doc["mac"], str) else ("", "")
    except (OSError, RuntimeError):
        return None
    except (ValueError, KeyError, TypeError):
        return ("", "")  # trailer presente e ilegível: existe âncora, e ela não autentica nada


def _ancora_gravar(conn: sqlite3.Connection, canon: str, mac: str) -> None:
    home = _home_da_conexao(conn)
    if home is None:
        _ancoras_efemeras[id(conn)] = (conn, canon, mac)
        return
    caminho = home / ARQUIVO_CHAVE
    chave, _ = _separar_chave(caminho.read_bytes(), caminho)
    trailer = _TAG_ANCORA + json.dumps({"ids": canon, "mac": mac}, ensure_ascii=False).encode("utf-8")
    tmp = caminho.with_name(f"{ARQUIVO_CHAVE}.{secrets.token_hex(8)}.tmp")
    fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(chave + trailer)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, caminho)
    finally:
        tmp.unlink(missing_ok=True)
    _cache_chaves.pop(str(caminho), None)


def _fronteira_estabelecida(conn: sqlite3.Connection) -> bool:
    """Indício, no banco, de que o legado já foi fixado: espelho do selo ou qualquer registro com MAC."""
    if conn.execute("SELECT 1 FROM meta WHERE key IN (?,?)", (META_LEGADO, META_LEGADO_MAC)).fetchone():
        return True
    return conn.execute("SELECT 1 FROM run WHERE registro_mac IS NOT NULL LIMIT 1").fetchone() is not None


def selar_legado(conn: sqlite3.Connection) -> bool:
    """Fixa, na âncora fora do banco e autenticado por HMAC do home, o conjunto dos `run.id` sem MAC existentes agora
    (anteriores à 1.4.0a2). Só fixa uma vez: com âncora presente não faz nada, e sem âncora mas com indício de que a
    fronteira já foi estabelecida (selo ou MAC no banco) FALHA FECHADO: não recompõe o conjunto a partir de um banco
    que pode ter sido adulterado (reaplicar a migração não reabre o legado). Devolve se fixou."""
    if _ancora_ler(conn) is not None or _fronteira_estabelecida(conn):
        return False
    ids = [r[0] for r in conn.execute("SELECT id FROM run WHERE registro_mac IS NULL")]
    canon = _canon_legado(ids)
    mac = hmac_entrada(conn, "registro_legado", canon)
    _ancora_gravar(conn, canon, mac)
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)", (META_LEGADO, canon))  # espelho: indício
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)", (META_LEGADO_MAC, mac))
    return True


def legado_autenticado(conn: sqlite3.Connection, run_id: str) -> bool:
    """O registro é legado só se a âncora autenticada o lista; âncora ausente, adulterada ou ilegível: não.

    Não depende de nenhuma coluna da própria linha nem de `meta` (apagáveis ou forjáveis por quem não tem a chave)."""
    ancora = _ancora_ler(conn)
    if ancora is None:
        return False
    canon, mac = ancora
    try:
        esperado = hmac_entrada(conn, "registro_legado", canon, leitura=True)
        ids = json.loads(canon)
    except (RuntimeError, ValueError, OSError):
        return False
    return hmac.compare_digest(esperado, mac) and isinstance(ids, list) and run_id in set(ids)
