"""Revalidação por metadados normas.leg.br (0091 emenda A): gatilho de renovação, não prova."""
from __future__ import annotations

import json
import os
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.normas_leg import normalizar_encoding
from freoa_verifica.connectors.normas_leg import HOST, NormasLegConnector, identidade, url_metadados, urn_da_chave
from freoa_verifica.texto_resposta import texto_do_response

FONTE_META = "normas_leg_meta"
FONTE_PENDENTE = "renovacao_pendente"
FONTE_CURSOR = "manutencao_cursor"
FONTE_RENOVACAO = "renovacao_cursor"
VERSAO_CURRENT = re.compile(r"@(\d{4}-\d{2}-\d{2})~")
_ESCOPO_NOME = "metadados_e_renovacao"

_ctx_manutencao: ContextVar[bool] = ContextVar("normas_leg_manutencao", default=False)


def em_manutencao_normas_leg() -> bool:
    return _ctx_manutencao.get()


class manutencao_normas_leg:
    """Permite normas_leg fora do escopo restrito só durante revalidar/renovar/manter."""

    def __enter__(self):
        self._token = _ctx_manutencao.set(True)
        return self

    def __exit__(self, *exc) -> None:
        _ctx_manutencao.reset(self._token)


def escopo_restrito(home: Path) -> bool:
    path = Path(home) / "normas_leg" / "escopo.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return data.get("escopo") == _ESCOPO_NOME


def gravar_escopo(home: Path, decisao: str) -> dict[str, Any]:
    if not isinstance(decisao, str) or not decisao.strip():
        raise ValueError("decisao_necessaria")
    agora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    registro = {"escopo": _ESCOPO_NOME, "decisao": decisao.strip(), "em": agora}
    destino = Path(home) / "normas_leg"
    destino.mkdir(parents=True, exist_ok=True)
    alvo = destino / "escopo.json"
    tmp = destino / "escopo.json.tmp"
    tmp.write_text(json.dumps(registro, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(tmp, alvo)
    return registro


def sinal_de_metadados(meta: dict) -> dict | None:
    if not isinstance(meta, dict):
        return None
    dm = meta.get("dateModified")
    if dm is not None and not isinstance(dm, str):
        dm = None
    versao = None
    try:
        encodings = normalizar_encoding(meta) or []
    except ValueError:
        encodings = []
    for item in encodings:
        if not isinstance(item, dict):
            continue
        if item.get("version") != "Current" or item.get("inLanguage") != "pt":
            continue
        ecw = item.get("encodesCreativeWork")
        cid = ecw.get("@id") if isinstance(ecw, dict) else (ecw if isinstance(ecw, str) else None)
        if isinstance(cid, str):
            match = VERSAO_CURRENT.search(cid)
            if match:
                versao = match.group(1)
        break
    if dm is None and versao is None:
        return None
    return {"date_modified": dm, "versao_current": versao}


def _sinal_armazenado(payload_json: str | None) -> dict | None:
    if not payload_json:
        return None
    try:
        payload = json.loads(payload_json)
    except (ValueError, TypeError):
        return None
    sinal = payload.get("sinal") if isinstance(payload, dict) else None
    return sinal if isinstance(sinal, dict) else None


def _gravar_sync(conn, fonte: str, chave: str, status: str, *, motivo: str | None = None, payload: dict | None = None):
    sid = f"{fonte}:{chave}"
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True) if payload else None
    agora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    conn.execute(
        "INSERT INTO sync_state(id, fonte, chave, status, motivo, updated_at, payload_json) "
        "VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(fonte, chave) DO UPDATE SET "
        "status=excluded.status, motivo=excluded.motivo, "
        "updated_at=excluded.updated_at, payload_json=excluded.payload_json",
        (sid, fonte, chave, status, motivo, agora, payload_json),
    )
    conn.commit()


def _obras_elegiveis(conn) -> list[Any]:
    rows = conn.execute(
        "SELECT w.id, w.authority, w.kind, w.number, w.year FROM work w "
        "JOIN parsed_document p ON p.work_id=w.id JOIN capture c ON c.id=p.capture_id "
        "WHERE w.authority='federal' AND w.year>0 AND p.candidato_ao_vivo=0 AND p.model_json IS NOT NULL "
        "GROUP BY w.id",
    ).fetchall()
    out = []
    for row in rows:
        work = WorkKey(row["authority"], row["kind"], row["number"], int(row["year"]))
        try:
            identidade(work)
        except Unavailable:
            continue
        out.append(row)

    def _chave(r):
        ant = conn.execute(
            "SELECT payload_json FROM sync_state WHERE fonte=? AND chave=?",
            (FONTE_META, r["id"]),
        ).fetchone()
        prev = _sinal_armazenado(ant[0] if ant else None)
        lido = ""
        if ant and ant[0]:
            try:
                lido = json.loads(ant[0]).get("lido_em") or ""
            except (ValueError, TypeError):
                lido = ""
        return (0 if prev is None else 1, lido, r["id"])

    return sorted(out, key=_chave)


def _cursor_ultimo(conn) -> str | None:
    row = conn.execute(
        "SELECT payload_json FROM sync_state WHERE fonte=? AND chave=?",
        (FONTE_CURSOR, "revalidar"),
    ).fetchone()
    if not row or not row[0]:
        return None
    try:
        payload = json.loads(row[0])
    except (ValueError, TypeError):
        return None
    return payload.get("ultimo_work_id") if isinstance(payload, dict) else None


def _gravar_cursor(conn, work_id: str | None) -> None:
    _gravar_sync(conn, FONTE_CURSOR, "revalidar", "registrado", payload={"ultimo_work_id": work_id})


def _validar_metadados_obra(meta: dict, work: WorkKey) -> str | None:
    if not isinstance(meta, dict):
        return "metadados_invalidos"
    try:
        esperada = identidade(work)
    except Unavailable as exc:
        return exc.reason
    try:
        enc = normalizar_encoding(meta)  # objeto único em obra de versão única (0092)
    except ValueError:
        return "metadados_invalidos"
    if isinstance(enc, list):
        for item in enc:
            if item is not None and not isinstance(item, dict):
                return "metadados_invalidos"
    dm = meta.get("dateModified")
    if dm is not None and not isinstance(dm, str):
        return "metadados_invalidos"
    if not isinstance(enc, list):
        return "metadados_invalidos"
    from freoa_verifica.connectors.normas_leg import TIPOS, URN

    alvo = (TIPOS[esperada.kind], esperada.year, esperada.number)
    # Todo identificador presente confere com a obra pedida, sem precedência que esconda contradição (0091, r3 achado 7).
    for chave in ("urn", "legislationIdentifier", "@id"):
        valor = meta.get(chave)
        if not isinstance(valor, str):
            continue
        if chave == "urn" and valor != urn_da_chave(esperada):
            return "identidade_divergente"
        match = URN.fullmatch(valor)
        if match is None:
            if chave != "@id" and valor.strip():
                return "identidade_divergente"
            continue
        if (match[1], int(match[2][:4]), match[3]) != alvo:
            return "identidade_divergente"
    currents: list[str] = []
    for item in enc or []:
        if not isinstance(item, dict) or item.get("version") != "Current" or item.get("inLanguage") != "pt":
            continue
        ecw = item.get("encodesCreativeWork")
        cid = ecw.get("@id") if isinstance(ecw, dict) else (ecw if isinstance(ecw, str) else None)
        if isinstance(cid, str):
            m = VERSAO_CURRENT.search(cid)
            currents.append(m.group(1) if m else cid)
    if len({c for c in currents if c}) > 1:
        return "sinal_ambiguo"
    return None



def _host_barrado(con: NormasLegConnector) -> bool:
    agora = con.portao().relogio.agora()
    return con.portao().estado.bloqueio_do_host(HOST, agora) is not None


def _ler_metadados(con: NormasLegConnector, work: WorkKey) -> tuple[dict, str, str]:
    w = identidade(work)
    urn = urn_da_chave(w)
    url = url_metadados(urn)
    resp = con.portao().obter(url)
    try:
        payload = json.loads(texto_do_response(resp))
    except (ValueError, TypeError) as exc:
        raise Unavailable("resposta_inesperada", evidencia={"url": resp.url}) from exc
    if not isinstance(payload, dict):
        raise Unavailable("resposta_inesperada", evidencia={"url": resp.url})
    con.paginas[resp.url] = resp
    return payload, resp.sha256, datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# Fim do orçamento da execução (teto por chamada ou de sessão): não é falha da obra; o resto fica para a próxima
# execução, que retoma pelo cursor (0092, teste em Debian: o timer ficava "failed" a cada execução).
MOTIVOS_ADIAMENTO = frozenset({"teto_de_chamada", "teto_de_sessao", "orcamento"})


def revalidar(svc, limite: int | None = None) -> dict[str, Any]:
    if svc._offline():
        return {"status": "indisponivel", "motivo": "offline", "obras": []}
    rows = _obras_elegiveis(svc.conn)
    ultimo = _cursor_ultimo(svc.conn)
    if ultimo and rows:
        ids = [r["id"] for r in rows]
        if ultimo in ids:
            off = ids.index(ultimo) + 1
            rows = rows[off:] + rows[:off]
    if limite is not None:
        rows = rows[:max(0, int(limite))]
    con: NormasLegConnector = svc._get("normas_leg")
    resultados: list[dict[str, Any]] = []
    host_parado = False
    ultimo_processado: str | None = ultimo
    for row in rows:
        work_id = row["id"]
        work = WorkKey(row["authority"], row["kind"], row["number"], int(row["year"]))
        obra = f"{row['kind']} {row['number']}/{row['year']}"
        if host_parado:
            resultados.append({"work_id": work_id, "obra": obra, "resultado": "indisponivel", "motivo": "host_barrado"})
            continue
        try:
            payload, sha256, lido_em = _ler_metadados(con, work)
        except Unavailable as exc:
            if exc.reason in MOTIVOS_ADIAMENTO:
                resultados.append({"work_id": work_id, "obra": obra, "resultado": "adiado", "motivo": exc.reason})
                break
            if _host_barrado(con):
                host_parado = True
            resultados.append({"work_id": work_id, "obra": obra, "resultado": "indisponivel",
                               "motivo": exc.reason[:200], "categoria": exc.categoria})
            continue
        try:
            if motivo := _validar_metadados_obra(payload, work):
                raise Unavailable(motivo)
            sinal = sinal_de_metadados(payload)
        except (Unavailable, TypeError, ValueError) as exc:
            motivo = exc.reason if isinstance(exc, Unavailable) else "metadados_invalidos"
            resultados.append({"work_id": work_id, "obra": obra, "resultado": "indisponivel", "motivo": motivo[:200]})
            continue
        anterior = svc.conn.execute(
            "SELECT payload_json FROM sync_state WHERE fonte=? AND chave=?",
            (FONTE_META, work_id),
        ).fetchone()
        prev = _sinal_armazenado(anterior[0] if anterior else None)
        if prev is not None and sinal is None:
            resultados.append({"work_id": work_id, "obra": obra, "resultado": "indisponivel", "motivo": "sinal_ausente"})
            continue
        registro = {"sinal": sinal, "sha256": sha256, "lido_em": lido_em}
        _gravar_sync(svc.conn, FONTE_META, work_id, "registrado", payload=registro)
        ultimo_processado = work_id
        if prev is None:
            resultados.append({"work_id": work_id, "obra": obra, "resultado": "primeira_leitura", "sinal": sinal})
            continue
        if prev == sinal:
            resultados.append({"work_id": work_id, "obra": obra, "resultado": "inalterado", "sinal": sinal})
            continue
        _gravar_sync(svc.conn, FONTE_PENDENTE, work_id, "pendente", motivo="metadados_alterados",
                     payload={"sinal_anterior": prev, "sinal_novo": sinal, "em": lido_em})
        resultados.append({"work_id": work_id, "obra": obra, "resultado": "alterado", "sinal": sinal})
    if rows and ultimo_processado:
        _gravar_cursor(svc.conn, ultimo_processado)
    contagem = {k: sum(1 for r in resultados if r["resultado"] == k)
                for k in ("inalterado", "alterado", "primeira_leitura", "indisponivel", "adiado")}
    if not resultados:
        status = "ok"
    elif contagem["indisponivel"] and contagem["indisponivel"] == len(resultados) - contagem["adiado"]:
        status = "indisponivel"
    elif contagem["indisponivel"]:
        status = "parcial"
    elif contagem["adiado"]:
        # Só adiamentos não é sucesso; com obras lidas antes do teto, é parcial (0092, Codex r-Debian).
        status = "adiado" if contagem["adiado"] == len(resultados) else "parcial"
    else:
        status = "ok"
    return {"status": status, "obras": len(rows), "contagens": contagem, "resultados": resultados}




def cursor_renovacao(conn) -> str | None:
    row = conn.execute(
        "SELECT payload_json FROM sync_state WHERE fonte=? AND chave=?",
        (FONTE_RENOVACAO, "renovar"),
    ).fetchone()
    if not row or not row[0]:
        return None
    try:
        payload = json.loads(row[0])
    except (ValueError, TypeError):
        return None
    return payload.get("ultimo_work_id") if isinstance(payload, dict) else None


def gravar_cursor_renovacao(conn, work_id: str | None) -> None:
    _gravar_sync(conn, FONTE_RENOVACAO, "renovar", "registrado", payload={"ultimo_work_id": work_id})


def registrar_falha_renovacao(conn, work_id: str) -> None:
    agora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _gravar_sync(conn, FONTE_RENOVACAO, work_id, "registrado", payload={"tentado_em": agora})


def ordenar_renovacao(conn, rows: list) -> list:
    falhas: dict[str, str] = {}
    for r in conn.execute("SELECT chave, payload_json FROM sync_state WHERE fonte=?", (FONTE_RENOVACAO,)):
        if r[0] == "renovar":
            continue
        try:
            payload = json.loads(r[1] or "{}")
        except (ValueError, TypeError):
            payload = {}
        if isinstance(payload, dict) and payload.get("tentado_em"):
            falhas[r[0]] = payload["tentado_em"]

    def _chave(row):
        wid = row["id"]
        ultima = row["ultima"] if "ultima" in row.keys() else ""
        if wid in falhas:
            return (1, falhas[wid], ultima or "", wid)
        return (0, ultima or "", wid)

    return sorted(rows, key=_chave)


def desmarcar_renovacao_pendente(conn, work_id: str) -> None:
    conn.execute("DELETE FROM sync_state WHERE fonte=? AND chave=?", (FONTE_PENDENTE, work_id))
    conn.commit()


def instante(valor) -> datetime | None:
    """ISO 8601 com fuso como instante; qualquer outra coisa (vazio, "sem-data", sem fuso) é None (0094, achado 5).

    Datas de captura e de sinal são comparadas como instantes, nunca como texto."""
    if not isinstance(valor, str) or not valor:
        return None
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def data_do_sinal_da_pendencia(conn, work_id: str) -> datetime | None:
    """Instante do sinal que abriu a pendência (`payload.em`); pendência antiga sem ele: a data do próprio registro."""
    row = conn.execute("SELECT payload_json, updated_at FROM sync_state WHERE fonte=? AND chave=?",
                       (FONTE_PENDENTE, work_id)).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row[0] or "{}")
    except (ValueError, TypeError):
        payload = {}
    em = instante(payload.get("em")) if isinstance(payload, dict) else None
    return em or instante(row[1])


def obras_pendentes(conn) -> list[str]:
    rows = conn.execute(
        "SELECT chave FROM sync_state WHERE fonte=?",
        (FONTE_PENDENTE,),
    ).fetchall()
    return [r[0] for r in rows]


def consulta_manutencao(home: Path) -> dict[str, Any]:
    """Checagem do doctor: última manutenção agendada gravada em manutencao.json."""
    path = Path(home) / "manutencao.json"
    if not path.is_file():
        return {"nome": "acervo_manutencao", "status": "alerta", "detalhe": {"motivo": "manutencao_ausente"}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"nome": "acervo_manutencao", "status": "falha", "detalhe": {"motivo": "manutencao_ilegivel"}}
    if not isinstance(data, dict):
        return {"nome": "acervo_manutencao", "status": "falha", "detalhe": {"motivo": "manutencao_ilegivel"}}
    if data.get("status") == "parcial" and data.get("falhas") is not False:
        return {"nome": "acervo_manutencao", "status": "alerta", "detalhe": data}  # obras falharam (0092)
    # "parcial" sem falha real (só teto/orçamento, com progresso) segue a regra de idade como "ok"; o restante
    # fica para a próxima execução, que retoma do cursor.
    if data.get("status") not in ("ok", "parcial"):
        return {"nome": "acervo_manutencao", "status": "falha", "detalhe": data}
    fim = data.get("fim")
    if not isinstance(fim, str):
        return {"nome": "acervo_manutencao", "status": "falha", "detalhe": data}
    try:
        instante = datetime.fromisoformat(fim.replace("Z", "+00:00"))
        if instante.tzinfo is None:
            instante = instante.replace(tzinfo=timezone.utc)
    except ValueError:
        return {"nome": "acervo_manutencao", "status": "falha", "detalhe": data}
    horas = (datetime.now(timezone.utc) - instante).total_seconds() / 3600
    if horas > 48:
        return {"nome": "acervo_manutencao", "status": "alerta",
                "detalhe": {**data, "horas_desde_fim": round(horas, 1)}}
    return {"nome": "acervo_manutencao", "status": "ok", "detalhe": data}