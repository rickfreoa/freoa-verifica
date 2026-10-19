"""Conector STJ — CKAN dados abertos + índice FTS local."""

from __future__ import annotations

import csv
import io
import json
import hashlib
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from freoa_verifica.connectors.base import (
    Candidate,
    Connector,
    HealthProbe,
    HealthReport,
    ParsedDecision,
    Unavailable,
    register,
)
from freoa_verifica.authority import normalize_species
from freoa_verifica.connectors.httputil import connector_fetch
from freoa_verifica.transport import Response

_MESES_REVALIDADOS = 2
_REVALIDAR_DIAS = 30


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _meta_ckan(res: dict[str, Any]) -> dict[str, Any]:
    """Metadados CKAN do recurso que, ao mudar, invalidam o checkpoint."""
    return {k: res[k] for k in ("last_modified", "metadata_modified", "size", "hash") if res.get(k) not in (None, "")}


def _parse_ts(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _ts_ok(estado: dict[str, Any]) -> datetime | None:
    """Última captura bem-sucedida; linhas anteriores à 0039 usam updated_at."""
    v = estado["info"].get("ultima_captura_ok") or (estado["updated_at"] if estado["status"] == "capturado" else None)
    return _parse_ts(v) if v else None


def resumo_atualizacao(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Agregado do estado por recurso: captura bem-sucedida mais recente e atraso em dias."""
    try:
        rows = conn.execute("SELECT status, updated_at, payload_json FROM sync_state "
                            "WHERE fonte='stj_resource' AND chave LIKE 'resource:%'").fetchall()
    except sqlite3.Error:
        return None
    estados = [{"status": r[0], "updated_at": r[1], "info": json.loads(r[2]) if r[2] else {}} for r in rows]
    oks = [t for t in (_ts_ok(e) for e in estados) if t]
    if not oks:
        return None
    ultimo = max(oks)
    tent = [t for t in (_parse_ts(e["info"].get("ultima_tentativa")) for e in estados) if t]
    return {"ultima_captura_ok": ultimo.isoformat(), "atraso_dias": (_agora() - ultimo).days,
            "ultima_tentativa": max(tent).isoformat() if tent else None}


_CKAN = "https://dadosabertos.web.stj.jus.br/api/3/action/package_show"
_ESPELHOS = (
    "espelhos-de-acordaos-corte-especial",
    "espelhos-de-acordaos-primeira-secao",
    "espelhos-de-acordaos-segunda-secao",
    "espelhos-de-acordaos-terceira-secao",
    "espelhos-de-acordaos-primeira-turma",
    "espelhos-de-acordaos-segunda-turma",
    "espelhos-de-acordaos-terceira-turma",
    "espelhos-de-acordaos-quarta-turma",
    "espelhos-de-acordaos-quinta-turma",
    "espelhos-de-acordaos-sexta-turma",
)
_INTEGRAS = "integras-de-decisoes-terminativas-e-acordaos-do-diario-da-justica"
_PRECEDENTES = "precedentes-qualificados"

_JSON_MIMES = frozenset(
    {
        "application/json",
        "text/json",
        "text/plain",
        "application/octet-stream",
        "application/zip",
        "application/x-zip-compressed",
        "text/csv",
        "text/html",
    }
)

_DEFAULT_DB = Path.home() / ".cache" / "freoa-verifica" / "stj_fts.sqlite"


@register
class StjConnector(Connector):
    id = "stj"
    authority = "Superior Tribunal de Justiça"
    hosts = frozenset(
        {
            "dadosabertos.web.stj.jus.br",
            "www.stj.jus.br",
            "stj.jus.br",
        }
    )
    path_prefixes = {
        "dadosabertos.web.stj.jus.br": ("/api/", "/dataset/"),
        "www.stj.jus.br": ("/websecstj/",),
        "stj.jus.br": ("/websecstj/",),
    }
    mimes = _JSON_MIMES
    user_agent = "browser"
    coverage = {
        # Declara só o que o sync adquire: espelhos (ementa) e precedentes qualificados. A coleção oficial
        # de íntegras existe no portal, mas a aquisição não está implementada (avaliação externa, A12).
        "colecoes": ["espelhos", "precedentes_qualificados"],
        "periodo": "espelhos mensais publicados no portal de dados abertos (recorte do acervo instalado)",
        "integras": "nao_implementado",
        "busca_textual": True,
        "busca_textual_ao_vivo": False,
        "ementa": True,
        "inteiro_teor": False,
        "atualizacao": "fv sync stj --desde AAAA-MM",
        "licenca": "CC BY",
    }

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB
        self.sync_state = None
        self._last_resource = None
        self._last_items = None
        self.resource_dir = self.db_path.parent / "stj-resources"

    def health(self) -> HealthReport:
        probes: list[HealthProbe] = []
        try:
            meta = self.package_show(_ESPELHOS[0])
            ok = bool(meta.get("resources"))
            probes.append(HealthProbe("positivo", "ok" if ok else "failed", _ESPELHOS[0]))
        except Exception as exc:
            probes.append(HealthProbe("positivo", "unavailable", str(exc)[:200]))
        try:
            # pacote inexistente
            self.package_show("fv-pacote-inexistente-xyz")
            probes.append(HealthProbe("negativo", "failed", "esperava erro"))
        except Unavailable as exc:
            probes.append(HealthProbe("negativo", "ok", exc.reason))
        except Exception as exc:
            probes.append(HealthProbe("negativo", "unavailable", str(exc)[:200]))
        try:
            # documento: baixar um JSON mensal pequeno se índice local vazio, senão FTS
            if self.db_path.is_file() and self._count() > 0:
                found = self.search("recurso especial", limite=1)
                probes.append(
                    HealthProbe("documento", "ok" if found else "zero", f"fts={self._count()}")
                )
            else:
                meta = self.package_show(_ESPELHOS[4])  # primeira turma
                resources = meta.get("resources") or []
                json_res = [
                    r
                    for r in resources
                    if str(r.get("format", "")).upper() == "JSON"
                    and str(r.get("name", "")).endswith(".json")
                ]
                if not json_res:
                    probes.append(HealthProbe("documento", "unavailable", "sem_resource_json"))
                else:
                    # pega o mais recente
                    json_res.sort(key=lambda r: str(r.get("name") or ""), reverse=True)
                    url = json_res[0]["url"]
                    resp = connector_fetch(
                        url,
                        hosts=self.hosts,
                        path_prefixes=self.path_prefixes,
                        mimes=self.mimes,
                        user_agent=self.user_agent,
                        timeout=120.0,
                        max_bytes=30 * 1024 * 1024,
                    )
                    data = json.loads(resp.body.decode("utf-8"))
                    ok = isinstance(data, list) and bool(data)
                    probes.append(
                        HealthProbe(
                            "documento",
                            "ok" if ok else "failed",
                            f"n={len(data) if isinstance(data, list) else 0}",
                        )
                    )
        except Exception as exc:
            probes.append(HealthProbe("documento", "unavailable", str(exc)[:200]))
        return HealthReport(
            self.id,
            tuple(probes),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def package_show(self, package_id: str) -> dict[str, Any]:
        cache_key = f"package_show:{package_id}"
        if self.sync_state:
            cached = self.sync_state.get("stj_cache", cache_key)
            if cached and cached["payload_json"]:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(cached["updated_at"])
                if age.total_seconds() < 86400:
                    return json.loads(cached["payload_json"])["result"]
        url = _CKAN + "?" + urlencode({"id": package_id})
        resp = connector_fetch(
            url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            timeout=180.0,
        )
        try:
            payload = json.loads(resp.body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise Unavailable("resposta_inesperada") from exc
        if not payload.get("success"):
            raise Unavailable("resposta_inesperada")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise Unavailable("resposta_inesperada")
        if self.sync_state:
            self.sync_state.set("stj_cache", cache_key, "metadados",
                                payload={"result": result, "sha256": resp.sha256,
                                         "url": resp.final_url, "fetched_at": resp.fetched_at})
        return result

    def search(self, q: str, **filtros: Any) -> list[Candidate]:
        """Busca = índice local FTS sobre o sincronizado."""
        if not self.db_path.is_file():
            raise Unavailable("stj_indice_local_ausente")
        limite = int(filtros.get("limite") or 10)
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.row_factory = sqlite3.Row
            # marcador estrutural de zero: COUNT do FTS
            cur = conn.execute(
                "SELECT COUNT(*) AS n FROM fts_stj WHERE fts_stj MATCH ?",
                (_fts_query(q),),
            )
            n = int(cur.fetchone()["n"])
            if n == 0:
                return []
            rows = conn.execute(
                """
                SELECT key, title, ementa, organ, rapporteur, decision_date, class_name, payload
                FROM fts_stj WHERE fts_stj MATCH ? LIMIT ?
                """,
                (_fts_query(q), limite),
            ).fetchall()
        finally:
            conn.close()
        out: list[Candidate] = []
        for row in rows:
            meta = json.loads(row["payload"]) if row["payload"] else {}
            meta["reuse_policy"] = "CC BY — atribuição ao STJ Dados Abertos"
            out.append(
                Candidate(
                    source_id=self.id,
                    key=row["key"],
                    title=row["title"] or row["key"],
                    snippet=(row["ementa"] or "")[:300] or None,
                    metadata=meta,
                )
            )
        return out

    def resolve(self, key: Any) -> Candidate | None:
        if isinstance(key, dict) and key.get('classe') and key.get('numero'):
            if not self.db_path.is_file():
                raise Unavailable('stj_indice_local_ausente')
            conn = sqlite3.connect(str(self.db_path))
            try:
                rows = conn.execute('SELECT payload FROM fts_stj').fetchall()
                hits = []
                for row in rows:
                    item = json.loads(row[0])
                    cls = str(item.get('siglaClasse') or '').upper()
                    num = re.sub(r'\D','',str(item.get('numeroProcesso') or ''))
                    requested = re.sub(r'\D','',str(key['numero']))
                    uf = str(item.get('siglaUF') or item.get('siglaUf') or item.get('uf') or '').upper()
                    if cls == str(key['classe']).upper() and num == requested and (not key.get('uf') or uf == str(key['uf']).upper()):
                        hits.append(str(item.get('id') or item.get('numeroDocumento')))
                if len(hits) != 1:
                    return None
                key = hits[0]
            finally:
                conn.close()
        elif isinstance(key, dict):
            key = key.get("numeroRegistro") or key.get("key")
        if not key:
            return None
        if not self.db_path.is_file():
            return Candidate(
                source_id=self.id,
                key=str(key),
                title=str(key),
                metadata={"reuse_policy": "CC BY — atribuição ao STJ Dados Abertos"},
            )
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT key, title, ementa, payload FROM fts_stj WHERE key = ? OR json_extract(payload,'$.numeroRegistro') = ?",
                (str(key), str(key)),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        meta = json.loads(row["payload"]) if row["payload"] else {}
        meta["reuse_policy"] = "CC BY — atribuição ao STJ Dados Abertos"
        return Candidate(
            source_id=self.id,
            key=row["key"],
            title=row["title"] or row["key"],
            snippet=(row["ementa"] or "")[:300] or None,
            metadata=meta,
        )

    def fetch(self, candidate: Candidate) -> Response:
        meta = candidate.metadata
        if meta.get("_resource_sha256"):
            digest = meta["_resource_sha256"]
            if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise Unavailable("stj_hash_recurso_invalido")
            if self._last_resource is not None and self._last_resource.sha256 == digest:
                return self._last_resource
            mime = "text/csv" if meta.get("_resource_kind") == "csv" else "application/json"
            body = (self.resource_dir / (digest + (".csv" if mime == "text/csv" else ".json"))).read_bytes()
            if hashlib.sha256(body).hexdigest() != digest:
                raise Unavailable("stj_hash_recurso_diverge")
            url = meta["_resource_url"]
            self._last_resource = Response(url, url, 200, {"content-type": mime}, body,
                            digest, meta["_resource_fetched_at"], [], mime)
            return self._last_resource
        url = candidate.metadata.get("resource_url") or candidate.url
        if not url:
            # devolve payload local como "resposta"
            payload = json.dumps(candidate.metadata, ensure_ascii=False).encode("utf-8")
            return Response(
                url=f"local://stj/{candidate.key}",
                final_url=f"local://stj/{candidate.key}",
                status=200,
                headers={"content-type": "application/json"},
                body=payload,
                sha256=__import__("hashlib").sha256(payload).hexdigest(),
                fetched_at=datetime.now(timezone.utc).isoformat(),
                redirects=[],
                mime="application/json",
            )
        return connector_fetch(
            url,
            hosts=self.hosts,
            path_prefixes=self.path_prefixes,
            mimes=self.mimes,
            user_agent=self.user_agent,
            timeout=120.0,
            max_bytes=30 * 1024 * 1024,
        )

    def parse_candidate(self, resp: Response, candidate: Candidate) -> ParsedDecision:
        if resp.mime == "text/csv":
            item = _precedentes_do_csv(resp.body).get(candidate.key)  # mesma política do sync: a última linha vale
            if item is None:
                raise Unavailable("stj_documento_ausente_no_recurso")
            return self._decision(item)
        return self.parse(resp, key=candidate.key)

    def parse(self, resp: Response, *, key: str | None = None) -> ParsedDecision:
        if key is not None:
            if self._last_items is None or self._last_items[0] is not resp.body:
                loaded = json.loads(resp.body.decode('utf-8'))
                if isinstance(loaded,list):
                    self._last_items = (resp.body, {str(i.get('id') or i.get('numeroDocumento')):i for i in loaded if isinstance(i,dict)})
                else:
                    self._last_items = (resp.body, {str(loaded.get('id') or loaded.get('numeroDocumento')):loaded})
            data = self._last_items[1].get(key)
            if data is None:
                raise Unavailable('stj_documento_ausente_no_recurso')
        else:
            data = json.loads(resp.body.decode("utf-8"))
        if key is not None and isinstance(data, list):
            data = next((item for item in data if isinstance(item, dict)
                         and str(item.get("id") or item.get("numeroDocumento")) == key), None)
            if data is None:
                raise Unavailable("stj_documento_ausente_no_recurso")
        if isinstance(data, list) and data:
            item = data[0]
        elif isinstance(data, dict):
            item = data
        else:
            item = {}
        return self._decision(item)

    def _decision(self, item: dict[str, Any]) -> ParsedDecision:
        # Identidade = id do documento/julgamento; processo/registro = proceeding.
        official = str(item.get("id") or item.get("numeroDocumento") or "")
        if not official:
            raise Unavailable("resposta_invalida")
        raw_kind = str(item.get("tipoDeDecisao") or "acordao")
        try:
            kind = normalize_species(raw_kind)
        except ValueError:
            kind = "acordao"
        return ParsedDecision(
            profile="stj_espelho",
            kind=kind,
            court="STJ",
            official_id=official,
            ementa=item.get("ementa"),
            text=str(item.get("decisao") or item.get("ementa") or ""),
            judgment_date=_iso_from_yyyymmdd(item.get("dataDecisao")),
            publication_date=item.get("dataPublicacao"),
            rapporteur=item.get("ministroRelator"),
            organ=item.get("nomeOrgaoJulgador"),
            class_name=item.get("siglaClasse") or item.get("descricaoClasse"),
            metadata={
                "reuse_policy": "CC BY — atribuição ao STJ Dados Abertos",
                "proceeding": item.get("numeroRegistro") or item.get("numeroProcesso"),
                "numeroRegistro": item.get("numeroRegistro"),
                "numeroProcesso": item.get("numeroProcesso"),
                "referenciasLegislativas": item.get("referenciasLegislativas"),
                "situacao_precedente": item.get("situacao_precedente"),
                "divergencia_na_fonte": item.get("divergenciaNaFonte"),
                "tema": item.get("tema"),
            },
        )

    def sync(self, *, desde: str | None = None, orgaos: list[str] | None = None, max_itens: int | None = None,
             precedentes: bool | None = None) -> int:
        """JSONs mensais recentes; max_itens por recurso; desde explícito amplia o recorte."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_stj USING fts5(
                    key UNINDEXED, title, ementa, organ, rapporteur,
                    decision_date UNINDEXED, class_name, payload UNINDEXED,
                    tokenize='unicode61 remove_diacritics 2'
                )
                """
            )
            rows_by_key = {}
            for rowid, existing_key in conn.execute('SELECT rowid,key FROM fts_stj'):
                rows_by_key.setdefault(str(existing_key), []).append(rowid)
            inserted = 0
            self.last_failures = []
            packages = [p for p in (orgaos or _ESPELHOS) if p != _PRECEDENTES]
            if precedentes is None:
                precedentes = not orgaos or _PRECEDENTES in orgaos
            ymin = int(desde.replace("-", "")[:6]) if desde else 0
            for pkg in packages:
                try:
                    meta = self.package_show(pkg)
                except Exception as exc:
                    if self.sync_state is None:
                        raise
                    key = f"package:{pkg}"
                    self.sync_state.set("stj_resource", key, "indisponivel", motivo=str(exc)[:200])
                    self.last_failures.append((key, str(exc)[:200]))
                    continue
                if self.sync_state:
                    self.sync_state.set("stj_resource", f"package:{pkg}", "metadados")
                monthly = [r for r in meta.get("resources", [])
                           if _monthly_name(str(r.get("name", "")))
                           and str(r.get("format", "")).upper() == "JSON"
                           and int(r["name"][:6]) >= ymin]
                monthly.sort(key=lambda r: r["name"], reverse=True)
                if not monthly:
                    reason = "stj_sem_recursos_json_mensais_no_recorte"
                    if self.sync_state is None:
                        raise Unavailable(reason)
                    key = f"package:{pkg}"
                    self.sync_state.set("stj_resource", key, "indisponivel", motivo=reason)
                    self.last_failures.append((key, reason))
                    continue
                if desde is None:
                    # Um único recurso por mês; descarta ZIPs e dicionários.
                    by_month = {}
                    for res in monthly:
                        by_month.setdefault(res["name"][:6], res)
                    monthly = list(by_month.values())[:12]
                recentes = set(sorted({r["name"][:6] for r in monthly}, reverse=True)[:_MESES_REVALIDADOS])
                for res in monthly:
                    url = res.get("url")
                    if not url:
                        continue
                    rid = res.get("id") or url
                    checkpoint = f"resource:{rid}:{max_itens}"
                    meta_ckan = _meta_ckan(res)
                    agora = _agora()
                    estados = self._estados_recurso(rid)
                    ultimo_ok = max((t for t in (_ts_ok(e) for e in estados) if t), default=None)
                    # Revalidação (decisão 0039): meses recentes e capturas velhas ignoram os dois caches.
                    forcar = (res["name"][:6] in recentes or ultimo_ok is None
                              or agora - ultimo_ok > timedelta(days=_REVALIDAR_DIAS))
                    saved = next((e for e in estados if e["chave"] == checkpoint), None)
                    saved_info = (saved or {}).get("info") or {}
                    saved_ok = bool(saved and saved["status"] == "capturado"
                                    and self._bytes_ok(saved_info.get("sha256")))
                    if saved_ok and not forcar and saved_info.get("meta", {}) == meta_ckan:
                        continue
                    novo_ok, novo_rev, tentativa = agora.isoformat(), agora.isoformat(), agora.isoformat()
                    try:
                        resp = None
                        if not forcar:
                            # O limite de indexação não muda o recurso oficial capturado.
                            for old in estados:
                                info = old["info"]
                                if old["status"] != "capturado" or info.get("meta", {}) != meta_ckan:
                                    continue
                                cached_body = self._bytes_ok(info.get("sha256"))
                                receipt = self.sync_state.conn.execute(
                                    "SELECT fetched_at FROM capture WHERE sha256=? AND url=? ORDER BY fetched_at LIMIT 1",
                                    (info["sha256"], url)).fetchone() if cached_body else None
                                if receipt:
                                    resp = Response(url, url, 200, {"content-type": "application/json"}, cached_body,
                                                    info["sha256"], receipt[0], [], "application/json")
                                    novo_ok = info.get("ultima_captura_ok") or old["updated_at"]
                                    novo_rev = info.get("revalidado_em") or novo_ok
                                    tentativa = info.get("ultima_tentativa") or novo_ok
                                    break
                        if resp is None:
                            resp = connector_fetch(
                                url, hosts=self.hosts, path_prefixes=self.path_prefixes,
                                mimes=self.mimes, user_agent=self.user_agent,
                                timeout=120.0, max_bytes=40 * 1024 * 1024)
                        rows = json.loads(resp.body.decode("utf-8"))
                        if not isinstance(rows, list):
                            raise Unavailable("stj_recurso_nao_lista")
                        self.resource_dir.mkdir(parents=True, exist_ok=True)
                        # Versões antigas permanecem em resource_dir (nome = sha256).
                        (self.resource_dir / (resp.sha256 + ".json")).write_bytes(resp.body)
                        selo = {"meta": meta_ckan, "ultima_tentativa": tentativa,
                                "ultima_captura_ok": novo_ok, "revalidado_em": novo_rev}
                        if saved_ok and saved_info.get("sha256") == resp.sha256:
                            # Mesmo conteúdo: só carimba a revalidação, sem reprocessar registros.
                            if self.sync_state:
                                self.sync_state.set("stj_resource", checkpoint, "capturado",
                                                    payload={**saved_info, **selo})
                            continue
                        resource_count = 0
                        for item in rows:
                            if max_itens is not None and resource_count >= max_itens:
                                break
                            if not isinstance(item, dict):
                                continue
                            # Chave estável = id documental (não numeroRegistro/processo).
                            key = str(item.get("id") or item.get("numeroDocumento") or "")
                            if not key:
                                continue
                            item = {**item, "_resource_sha256": resp.sha256,
                                    "_resource_url": resp.final_url, "_resource_fetched_at": resp.fetched_at}
                            self._put(conn, rows_by_key, key, item)
                            inserted += 1
                            resource_count += 1
                        conn.commit()
                        if self.sync_state:
                            self.sync_state.set("stj_resource", checkpoint, "capturado",
                                                payload={"sha256": resp.sha256, "url": resp.final_url,
                                                         "n": resource_count, "mes": res["name"][:6], **selo})
                    except Exception as exc:
                        if self.sync_state is None:
                            raise
                        self.sync_state.set("stj_resource", checkpoint, "indisponivel", motivo=str(exc)[:200],
                                            payload={"ultima_tentativa": agora.isoformat(),
                                                     "ultima_captura_ok": ultimo_ok.isoformat() if ultimo_ok else None,
                                                     "sha256": saved_info.get("sha256")})
                        self.last_failures.append((checkpoint, str(exc)[:200]))
                        continue
            if precedentes:
                try:
                    inserted += self._sync_precedentes(conn, rows_by_key, max_itens)
                except Exception as exc:
                    if self.sync_state is None:
                        raise
                    self.sync_state.set("stj_resource", f"package:{_PRECEDENTES}", "indisponivel", motivo=str(exc)[:200])
                    self.last_failures.append((f"package:{_PRECEDENTES}", str(exc)[:200]))
            conn.commit()
            return inserted
        finally:
            conn.close()

    def _estados_recurso(self, rid: str) -> list[dict[str, Any]]:
        if not self.sync_state:
            return []
        rows = self.sync_state.conn.execute(
            "SELECT chave, status, updated_at, payload_json FROM sync_state WHERE fonte='stj_resource' AND chave LIKE ?",
            (f"resource:{rid}:%",)).fetchall()
        return [{"chave": r[0], "status": r[1], "updated_at": r[2],
                 "info": json.loads(r[3]) if r[3] else {}} for r in rows]

    def _bytes_ok(self, sha: str | None) -> bytes | None:
        """Bytes capturados por sha256, se o arquivo local existe e confere."""
        path = self.resource_dir / f"{sha}.json" if sha else None
        if path and path.is_file():
            body = path.read_bytes()
            if hashlib.sha256(body).hexdigest() == sha:
                return body
        return None

    @staticmethod
    def _put(conn: sqlite3.Connection, rows_by_key: dict, key: str, item: dict[str, Any]) -> None:
        for rowid in rows_by_key.get(key, []):
            conn.execute("DELETE FROM fts_stj WHERE rowid = ?", (rowid,))
        cursor = conn.execute(
            """
            INSERT INTO fts_stj
            (key, title, ementa, organ, rapporteur, decision_date, class_name, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                f"{item.get('siglaClasse') or ''} {item.get('numeroProcesso') or ''}".strip(),
                item.get("ementa") or "",
                item.get("nomeOrgaoJulgador") or "",
                item.get("ministroRelator") or "",
                str(item.get("dataDecisao") or ""),
                item.get("siglaClasse") or "",
                json.dumps(item, ensure_ascii=False),
            ),
        )
        rows_by_key[key] = [cursor.lastrowid]

    def _sync_precedentes(self, conn: sqlite3.Connection, rows_by_key: dict, max_itens: int | None) -> int:
        """Temas.csv + Processos.csv (CKAN) -> mesmo FTS dos espelhos; paradigmas = leadingCase 'S'."""
        res = {r.get("name"): r.get("url") for r in self.package_show(_PRECEDENTES).get("resources", [])}
        got = {}
        for name in ("Temas.csv", "Processos.csv"):
            if not res.get(name):
                raise Unavailable("stj_precedentes_recurso_ausente")
            got[name] = connector_fetch(
                res[name], hosts=self.hosts, path_prefixes=self.path_prefixes, mimes=self.mimes,
                user_agent=self.user_agent, timeout=120.0, max_bytes=40 * 1024 * 1024)
        self.resource_dir.mkdir(parents=True, exist_ok=True)
        for r in got.values():
            (self.resource_dir / (r.sha256 + ".csv")).write_bytes(r.body)
        para: dict[str, list[str]] = {}
        for row in _csv_rows(got["Processos.csv"].body):
            if (row.get("leadingCase") or "").strip() == "S" and (row.get("Processo") or "").strip():
                para.setdefault(row["sequencialPrecedente"].strip(), []).append(row["Processo"].strip())
        temas = got["Temas.csv"]
        n = 0
        for key, item in _precedentes_do_csv(temas.body).items():
            if max_itens is not None and n >= max_itens:
                break
            self._put(conn, rows_by_key, key, {
                **item,
                # não autenticados: vêm de Processos.csv e nunca entram no texto probatório
                "processosParadigmaNaoAutenticados": para.get(item["_seq"], []),
                "_resource_sha256": temas.sha256, "_resource_url": temas.final_url,
                "_resource_fetched_at": temas.fetched_at, "_resource_kind": "csv",
                "_processos_sha256": got["Processos.csv"].sha256})
            n += 1
        conn.commit()
        if self.sync_state:
            self.sync_state.set("stj_resource", f"package:{_PRECEDENTES}", "capturado",
                                payload={"sha256": temas.sha256, "url": temas.final_url, "n": n})
        return n

    def _count(self) -> int:
        conn = sqlite3.connect(str(self.db_path))
        try:
            return int(conn.execute("SELECT COUNT(*) FROM fts_stj").fetchone()[0])
        except sqlite3.Error:
            return 0
        finally:
            conn.close()


# tipoPrecedente do CSV -> (classe, espécie). Só Tema (repetitivo) e IAC; Controvérsia/SIRDR/PUIL ficam fora.
_TIPOS_PRECEDENTE = {"Tema": ("Tema Repetitivo", "repetitivo"), "IAC": ("IAC", "irdr_iac")}


def _csv_rows(body: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"), newline="")))


def _situacao_estruturada(texto: str) -> dict[str, Any]:
    n = "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if not unicodedata.combining(c))
    if "cancel" in n:
        valor = "cancelada"
    elif "revis" in n:
        valor = "revisada"
    elif "supera" in n:
        valor = "superada"
    elif n.startswith(("transito em julgado", "acordao publicado")):
        valor = "vigente"
    else:  # afetado, em julgamento, sobrestado, vazio...: não é vigência demonstrada
        valor = "desconhecida"
    return {"valor": valor, "texto_oficial": texto or None}


def _precedentes_do_csv(body: bytes) -> dict[str, dict[str, Any]]:
    """Linhas repetidas da mesma chave: a última vale; divergência de tese/situação fica declarada."""
    items: dict[str, dict[str, Any]] = {}
    for row in _csv_rows(body):
        item = _precedente_item(row)
        if not item:
            continue
        anterior = items.get(item["id"])
        if anterior and ((anterior["teseFirmada"], anterior["situacao"]) != (item["teseFirmada"], item["situacao"])
                         or anterior.get("divergenciaNaFonte")):
            item["divergenciaNaFonte"] = True
        items[item["id"]] = item
    for item in items.values():
        if item.get("divergenciaNaFonte"):
            item["ementa"] += "\nDivergência na fonte: linhas repetidas com tese ou situação distintas; prevalece a última."
    return items


def _precedente_item(row: dict[str, str]) -> dict[str, Any] | None:
    tipo = _TIPOS_PRECEDENTE.get((row.get("tipoPrecedente") or "").strip())
    numero = (row.get("numeroPrecedente") or "").strip()
    if not tipo or not numero:
        return None
    classe, species = tipo

    def f(name: str) -> str:
        return " ".join((row.get(name) or "").split())

    partes = [f"{classe} {numero}. Situação: {f('situacao') or 'não informada'}."]
    for rotulo, campo in (("Questão submetida a julgamento", "questaoSubmetidaAJulgamento"),
                          ("Tese firmada", "teseFirmada"), ("Súmula originada", "sumulaOriginada")):
        if f(campo):
            partes.append(f"{rotulo}: {f(campo)}")
    return {
        "id": f"{'tema' if species == 'repetitivo' else 'iac'}:{numero}",
        "tipoDeDecisao": species,
        "siglaClasse": classe,
        "numeroProcesso": numero,
        "ementa": "\n".join(partes),
        "nomeOrgaoJulgador": f("orgaoJulgador"),
        "dataDecisao": f("dataJulgamento") or None,
        "situacao": f("situacao"),
        "teseFirmada": f("teseFirmada"),
        "situacao_precedente": _situacao_estruturada(f("situacao")),
        "_seq": (row.get("sequencialPrecedente") or "").strip(),
    }


def _fts_query(q: str) -> str:
    tokens = [t for t in q.replace('"', " ").split() if t]
    if not tokens:
        return '""'
    return " AND ".join(f'"{t}"' for t in tokens)


def _monthly_name(name: str) -> bool:
    if not re.fullmatch(r"\d{8}\.json", name):
        return False
    try:
        datetime.strptime(name[:8], "%Y%m%d")
    except ValueError:
        return False
    return True


def _iso_from_yyyymmdd(value: Any) -> str | None:
    if not value:
        return None
    s = str(value)
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s
