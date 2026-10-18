"""Sincronização do corpus semente — idempotente, retomável, com relatório."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any, Callable

from freoa_verifica.aliases import WorkKey
from freoa_verifica.citation import _MONTHS
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.stf import SUMULA_BASES
from freoa_verifica.ids import new_ulid
from freoa_verifica.parsers.model import ParsedDocument

log = logging.getLogger("freoa_verifica.semente")

_ACT_REF_RE = re.compile(
    r"(?i)\b(lei\s+complementar|lei|decreto-?lei|emenda\s+constitucional|"
    r"medida\s+provis[oó]ria|lcp|del|mpv)\s*"
    r"n?[ºo°.]?\s*([\d.]+)\s*(?:,?\s*de\s*)?(\d{4})?",
)

_TIPO_MAP = {
    "lei complementar": "LCP",
    "lcp": "LCP",
    "lei": "LEI",
    "decreto-lei": "DEL",
    "decreto lei": "DEL",
    "del": "DEL",
    "medida provisoria": "MPV",
    "medida provisória": "MPV",
    "mpv": "MPV",
    "emenda constitucional": "EMC",
}


def load_corpus() -> dict[str, Any]:
    root = resources.files("freoa_verifica").joinpath("data")
    raw = root.joinpath("corpus_semente.json").read_text(encoding="utf-8")
    return json.loads(raw)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FonteStats:
    fonte: str
    capturados: int = 0
    parseados: int = 0
    ambiguos: int = 0
    indisponiveis: int = 0
    motivos: dict[str, int] = field(default_factory=dict)
    pulados: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "fonte": self.fonte,
            "capturados": self.capturados,
            "parseados": self.parseados,
            "ambiguos": self.ambiguos,
            "indisponiveis": self.indisponiveis,
            "pulados": self.pulados,
            "motivos": dict(self.motivos),
        }


class SyncState:
    """Checkpoint em tabela sync_state."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def get(self, fonte: str, chave: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM sync_state WHERE fonte=? AND chave=?",
            (fonte, chave),
        ).fetchone()
        return dict(row) if row else None

    def set(
        self,
        fonte: str,
        chave: str,
        status: str,
        motivo: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        sid = f"{fonte}:{chave}"
        payload_json = (
            json.dumps(payload, ensure_ascii=False, sort_keys=True) if payload else None
        )
        self.conn.execute(
            "INSERT INTO sync_state(id, fonte, chave, status, motivo, updated_at, payload_json) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(fonte, chave) DO UPDATE SET "
            "status=excluded.status, motivo=excluded.motivo, "
            "updated_at=excluded.updated_at, payload_json=excluded.payload_json",
            (sid, fonte, chave, status, motivo, _now(), payload_json),
        )
        self.conn.commit()

    def done(self, fonte: str, chave: str) -> bool:
        row = self.get(fonte, chave)
        return row is not None and row["status"] in {
            "capturado",
            "parseado",
            "ambiguo",
        }


_MESES_EPIGRAFE = {unicodedata.normalize("NFKD", k).encode("ascii", "ignore").decode(): v for k, v in _MONTHS.items()}

_EPIGRAFE_DATA_RE = re.compile(
    r"\bDE\s+(\d{1,2})\s*[º°o]?\s+DE\s+([^\W\d_]+)\s+DE\s+(\d{4})\b", re.I
)


def data_da_epigrafe(epigrafe: str) -> str | None:
    """Data ISO do ato na epígrafe ("LEI Nº 14.195, DE 26 DE AGOSTO DE 2021"); inválida vira None."""
    m = _EPIGRAFE_DATA_RE.search(epigrafe or "")
    if not m:
        return None
    mes = _MESES_EPIGRAFE.get(unicodedata.normalize("NFKD", m[2].lower()).encode("ascii", "ignore").decode())
    if mes is None:
        return None
    try:
        return date(int(m[3]), mes, int(m[1])).isoformat()
    except ValueError:
        return None


def parse_act_ref(ref: str) -> tuple[str, str, int | None] | None:
    m = _ACT_REF_RE.search(ref or "")
    if not m:
        return None
    tipo_raw = re.sub(r"\s+", " ", m.group(1).lower().replace("ó", "o"))
    tipo = _TIPO_MAP.get(tipo_raw, "LEI")
    numero = m.group(2).replace(".", "")
    ano = int(m.group(3)) if m.group(3) else None
    return tipo, numero, ano


class SementeSync:
    """Orquestra captura do corpus semente via fachada Verifica."""

    def __init__(
        self,
        svc: Any,
        *,
        max_itens: int | None = None,
        fontes: list[str] | None = None,
        rate_delay: float = 0.35,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.svc = svc
        if max_itens is not None and max_itens < 1:
            raise ValueError("max_itens deve ser positivo")
        self.max_itens = max_itens
        self.fontes_filtro = set(fontes) if fontes else None
        self.rate_delay = rate_delay
        self.progress = progress or (lambda msg: log.info(msg))
        self.state = SyncState(svc.conn)
        self.corpus = load_corpus()
        self.stats: dict[str, FonteStats] = {}
        self.retry_backoff = 2.0 if rate_delay else 0.0
        self._failed: dict[tuple[str, str], str] = {}

    def _stats(self, fonte: str) -> FonteStats:
        fonte = fonte.removesuffix("_doc")
        if fonte == "stj_resource":
            fonte = "stj"
        if fonte in {"alterador", "alterador_data", "alterador_contexto"}:
            fonte = "planalto"
        if fonte not in self.stats:
            self.stats[fonte] = FonteStats(fonte=fonte)
        return self.stats[fonte]

    def _want(self, fonte: str) -> bool:
        if self.fontes_filtro is None:
            return True
        return fonte in self.fontes_filtro

    def _sleep(self) -> None:
        if self.rate_delay > 0:
            time.sleep(self.rate_delay)

    def _mark_indisponivel(self, fonte: str, chave: str, motivo: str) -> None:
        self._failed[fonte, chave] = motivo
        self.state.set(fonte, chave, "indisponivel", motivo=motivo)
        st = self._stats(fonte)
        st.indisponiveis += 1
        st.motivos[motivo] = st.motivos.get(motivo, 0) + 1

    def _index_legis(
        self,
        fonte: str,
        chave: str,
        *,
        connector_id: str,
        work_key: WorkKey,
        label: str,
    ) -> tuple[str, ParsedDocument | None]:
        """Captura e indexa obra legislativa. Retorna (status, documento|None)."""
        if self.state.done(fonte, chave):
            self._stats(fonte).pulados += 1
            return "pulado", None
        try:
            conn_obj = self.svc._get(connector_id)
            key = {
                "tipo": {"lei_complementar": "LCP", "decreto_lei": "DEL", "medida_provisoria": "MPV", "constituicao": "CF"}.get(
                    work_key.kind, work_key.kind.upper()),
                "numero": work_key.number,
                "ano": work_key.year or None,
                "authority": work_key.authority,
                "kind": work_key.kind,
                "number": work_key.number,
                "year": work_key.year or None,
            }
            if work_key.kind.lower() in {"cf", "constituicao"}:
                key = {"tipo": "CF", "numero": "1988", "ano": 1988}
            cand = conn_obj.resolve(key)
            if cand is None:
                self._mark_indisponivel(fonte, chave, "nao_resolvido")
                return "indisponivel", None
            self._sleep()
            resp = conn_obj.fetch(cand)
            st = self._stats(fonte)
            st.capturados += 1
            parsed = conn_obj.parse(resp)
            if not isinstance(parsed, ParsedDocument):
                self._mark_indisponivel(fonte, chave, "nao_documento")
                return "indisponivel", None
            if parsed.quarantined or parsed.ambiguous_paths:
                status = "ambiguo"
                st.ambiguos += 1
            else:
                status = "parseado"
                st.parseados += 1
            self.svc.indexar_obra(
                source_id=connector_id,
                work_key=work_key,
                document=parsed,
                body=resp.body,
                url=resp.final_url or resp.url,
                fetched_at=resp.fetched_at,
                label=label,
            )
            self.state.set(
                fonte,
                chave,
                status,
                payload={"url": resp.final_url or resp.url, "sha256": resp.sha256},
            )
            return status, parsed
        except Unavailable as exc:
            self._mark_indisponivel(fonte, chave, exc.reason[:200])
            return "indisponivel", None
        except Exception as exc:  # noqa: BLE001
            self._mark_indisponivel(fonte, chave, f"{type(exc).__name__}:{exc}"[:200])
            return "indisponivel", None

    def sync_planalto(self) -> None:
        if not self._want("planalto"):
            return
        # Checkpoints legados de contexto podiam estar concluídos com filhos pendentes.
        pending = self.svc.conn.execute("SELECT 1 FROM sync_state WHERE fonte='alterador' AND status='indisponivel' LIMIT 1").fetchone()
        if pending:
            contexts = self.svc.conn.execute("SELECT chave FROM sync_state WHERE fonte='alterador_contexto' AND status='concluido'").fetchall()
            for context in contexts:
                self.state.set('alterador_contexto',context[0],'indisponivel',motivo='ALTERADORES_PENDENTES')
        itens = list(self.corpus.get("planalto") or [])
        if self.max_itens is not None:
            itens = itens[: self.max_itens]
        for i, item in enumerate(itens):
            tipo = str(item["tipo"]).upper()
            numero = str(item["numero"]).replace(".", "")
            ano = int(item["ano"])
            rotulo = item.get("rotulo") or f"{tipo} {numero}/{ano}"
            chave = f"{tipo}:{numero}:{ano}"
            self.progress(f"planalto [{i+1}/{len(itens)}] {chave}")
            kind = {
                "CF": "constituicao",
                "LEI": "lei",
                "LCP": "lei_complementar",
                "DEL": "decreto_lei",
            }.get(tipo, tipo.lower())
            wk = WorkKey("federal", kind, numero if tipo != "CF" else "1988", ano)
            status, parsed = self._index_legis(
                "planalto",
                chave,
                connector_id="planalto",
                work_key=wk,
                label=rotulo,
            )
            if (
                status in {"parseado", "ambiguo", "pulado"}
                and self._is_principal(tipo, numero, ano)
            ):
                context = self.state.get("alterador_contexto", chave)
                if context and context["status"] == "concluido":
                    continue
                try:
                    complete = self._resolve_alteradores(chave, document=parsed)
                    self.state.set("alterador_contexto", chave, "indisponivel" if complete is False else "concluido", motivo="ALTERADORES_PENDENTES" if complete is False else None)
                except Exception as exc:
                    # Falha no contexto de uma obra não descarta as próximas obras.
                    self._mark_indisponivel("alterador_contexto", chave, str(exc)[:200])

        # Reexecuta também pendências legadas que já não aparecem nas remissões atuais.
        pending_rows = self.svc.conn.execute("SELECT chave,motivo FROM sync_state WHERE fonte='alterador' AND status='indisponivel' ORDER BY chave").fetchall()
        if self.max_itens is not None:
            pending_rows = pending_rows[:self.max_itens]
        for row in pending_rows:
            if not _transient(row['motivo'] or ''):
                continue
            parts = row['chave'].split(':')
            if len(parts) != 3 or not parts[2].isdigit():
                continue
            tipo, number, year = parts[0],parts[1],int(parts[2])
            kind = {'LEI':'lei','LCP':'lei_complementar','DEL':'decreto_lei','MPV':'medida_provisoria','EMC':'emenda_constitucional'}.get(tipo)
            if kind is None:
                continue
            self.progress(f"planalto pendente {row['chave']}")
            self._index_legis('alterador',row['chave'],connector_id='planalto',work_key=WorkKey('federal',kind,number,year),label=f"Alterador {row['chave']}")

    def _is_principal(self, tipo: str, numero: str, ano: int) -> bool:
        for p in self.corpus.get("leis_principais_alteradores") or []:
            if (
                str(p["tipo"]).upper() == tipo.upper()
                and str(p["numero"]).replace(".", "") == str(numero).replace(".", "")
                and int(p["ano"]) == ano
            ):
                return True
        return False

    def _resolve_alteradores(
        self, obra_chave: str, *, document: ParsedDocument | None = None
    ) -> bool:
        """Resolve datas Senado e captura texto dos atos alteradores (R6)."""
        parts = obra_chave.split(":")
        if len(parts) < 3:
            return False
        tipo, numero, ano = parts[0], parts[1], int(parts[2])
        kind = {"LEI": "lei", "LCP": "lei_complementar", "DEL": "decreto_lei", "CF": "constituicao"}.get(tipo, "lei")
        rw = self.svc._resolve(WorkKey("federal", kind, numero, ano))
        if not rw or isinstance(rw, list):
            return False
        doc = document or rw.document
        refs = {}
        for prov in doc.provisions:
            for red in prov.redactions:
                for ann in red.annotations:
                    parsed = parse_act_ref(ann.act_ref or ann.raw or "")
                    if parsed and parsed[2]:
                        refs.setdefault(parsed, []).append(ann)
        complete = True
        for i, ((atipo, anumero, aano), annotations) in enumerate(refs.items()):
            if self.max_itens is not None and i >= self.max_itens:
                break
            akey = f"{atipo}:{anumero}:{aano}"
            saved = self.state.get("alterador_data", akey)
            iso = (json.loads(saved["payload_json"] or "{}").get("data") if saved else None)
            if not iso:
                try:
                    self._sleep()
                    iso = self.svc._get("planalto").resolve_alterador_date(atipo, anumero, aano)
                    self.state.set("alterador_data", akey, "parseado" if iso else "indisponivel",
                                   motivo=None if iso else "senado_sem_data", payload={"data": iso})
                except Exception as exc:
                    self._mark_indisponivel("alterador_data", akey, str(exc)[:200])
            for ann in annotations:
                if iso and (ann.act_date is None or len(ann.act_date) == 4):
                    ann.act_date = iso
            akind = {"LEI": "lei", "LCP": "lei_complementar", "DEL": "decreto_lei",
                     "MPV": "medida_provisoria", "EMC": "emenda_constitucional"}.get(atipo, "lei")
            capture_status, _ = self._index_legis("alterador", akey, connector_id="planalto",
                              work_key=WorkKey("federal", akind, anumero, aano), label=f"Alterador {akey}")
            if capture_status not in {"parseado","ambiguo","pulado"}:
                complete = False
                continue
            try:
                alterador = self.svc._resolve(WorkKey("federal", akind, anumero, aano))
            except Exception as exc:
                complete = False
                self._mark_indisponivel("alterador", akey, str(exc)[:200])
                continue
            if alterador and not isinstance(alterador, list):
                # Senado sem data: a epígrafe capturada do próprio ato alterador; ano deve bater com a remissão.
                epigrafe_iso = None if iso else data_da_epigrafe(alterador.document.title)
                for ann in annotations:
                    if ann.act_ref:
                        rw.amending_act_texts[ann.act_ref] = alterador.document.text
                    if epigrafe_iso and epigrafe_iso[:4] == str(aano) and (ann.act_date is None or len(ann.act_date) == 4):
                        ann.act_date = epigrafe_iso
        from freoa_verifica.store import repo
        rw.document = doc
        repo.persist_parsed_document(self.svc.conn, capture_id=rw.capture_id,
                                     document=doc, work_id=rw.work_id, work_date=rw.work_date,
                                     amending_act_texts=rw.amending_act_texts)
        return complete

    def sync_cvm(self) -> None:
        if not self._want("cvm_normas"):
            return
        conn_obj = self.svc._get("cvm_normas")
        for tipo in ("resolucoes", "pareceres-orientacao"):
            seen = set()
            page = 1
            page_size = min(self.max_itens or 500, 500)
            while self.max_itens is None or len(seen) < self.max_itens:
                try:
                    self._sleep()
                    cands = conn_obj.search("", tipo=tipo, limite=page_size, pagina=page)
                    self.state.set("cvm_normas", f"indice:{tipo}:{page}", "metadados",
                                   payload={"candidatos": len(cands)})
                    fresh = [c for c in cands if c.key not in seen]
                    if not fresh:
                        break
                    for cand in fresh:
                        if self.max_itens is not None and len(seen) >= self.max_itens:
                            break
                        seen.add(cand.key)
                        if self.state.done("cvm_normas", cand.key):
                            self._stats("cvm_normas").pulados += 1
                        else:
                            self._capture_cvm_cand(conn_obj, cand)
                    if len(cands) < page_size:
                        break
                    page += 1
                except Exception as exc:
                    self._mark_indisponivel("cvm_normas", f"indice:{tipo}:{page}", str(exc)[:200])
                    break

        # Instruções históricas
        for num in self.corpus.get("cvm", {}).get("instrucoes_historicas") or []:
            chave = f"cvm:instrucoes:{int(num)}"
            if self.state.done("cvm_normas", chave):
                self._stats("cvm_normas").pulados += 1
                continue
            self.progress(f"cvm_normas instrução {num}")
            try:
                cand = conn_obj.resolve({"tipo": "instrucoes", "numero": int(num)})
                if cand is None:
                    self._mark_indisponivel("cvm_normas", chave, "nao_resolvido")
                    continue
                self._capture_cvm_cand(conn_obj, cand)
            except Exception as exc:  # noqa: BLE001
                self._mark_indisponivel("cvm_normas", chave, str(exc)[:200])

    def _capture_cvm_cand(self, conn_obj: Any, cand: Any) -> None:
        chave = cand.key
        try:
            from dataclasses import replace

            meta = cand.metadata or {}
            number = str(meta.get("numero") or chave.rsplit(":", 1)[-1])
            preferred = conn_obj.resolve({"tipo": meta.get("tipo") or "resolucoes", "numero": int(number)})
            if preferred:
                cand = replace(preferred, metadata={**preferred.metadata, **meta})
            self._sleep()
            resp = conn_obj.fetch(cand)
            st = self._stats("cvm_normas")
            st.capturados += 1
            parsed = conn_obj.parse(resp)
            if not isinstance(parsed, ParsedDocument):
                self._mark_indisponivel("cvm_normas", chave, "nao_documento")
                return
            meta = cand.metadata or {}
            number = str(meta.get("numero") or cand.key.split(":")[-1])
            year = int(meta.get("ano") or 0)
            tipo = str(meta.get("tipo") or "resolucoes")
            wk = WorkKey("cvm", {"resolucoes": "resolucao", "instrucoes": "instrucao", "pareceres-orientacao": "parecer_orientacao"}.get(tipo, tipo.replace("-", "_")), re.sub(r"\D", "", number) or number, year)
            if parsed.quarantined or parsed.ambiguous_paths:
                status = "ambiguo"
                st.ambiguos += 1
            else:
                status = "parseado"
                st.parseados += 1
            self.svc.indexar_obra(
                source_id="cvm_normas",
                work_key=wk,
                document=parsed,
                body=resp.body,
                url=resp.final_url or resp.url,
                fetched_at=resp.fetched_at,
                label=cand.title,
            )
            self.state.set(
                "cvm_normas",
                chave,
                status,
                payload={"url": resp.final_url or resp.url},
            )
        except Unavailable as exc:
            self._mark_indisponivel("cvm_normas", chave, exc.reason[:200])
        except Exception as exc:  # noqa: BLE001
            self._mark_indisponivel("cvm_normas", chave, f"{type(exc).__name__}:{exc}"[:200])

    def sync_bcb(self) -> None:
        if not self._want("bcb"):
            return
        conn_obj = self.svc._get("bcb")
        specs = list(self.corpus.get("bcb_cmn", {}).get("especificas") or [])
        recentes_cfg = self.corpus.get("bcb_cmn", {}).get("recentes") or {}
        qtd = int(recentes_cfg.get("quantidade") or 200)
        if self.max_itens is not None:
            qtd = min(qtd, self.max_itens)
            specs = specs[: self.max_itens]

        for item in specs:
            tipo = item["tipo"]
            numero = int(item["numero"])
            chave = f"bcb:{tipo}:{numero}"
            if self.state.done("bcb", chave):
                self._stats("bcb").pulados += 1
                continue
            self.progress(f"bcb {chave}")
            try:
                cand = conn_obj.resolve({"tipo": tipo, "numero": numero})
                if cand is None:
                    self._mark_indisponivel("bcb", chave, "nao_resolvido")
                    continue
                self._capture_bcb_cand(conn_obj, cand, chave)
            except Exception as exc:  # noqa: BLE001
                self._mark_indisponivel("bcb", chave, str(exc)[:200])

        for tipo in recentes_cfg.get("tipos") or []:
            try:
                self.progress(f"bcb recentes {tipo} (n={qtd})")
                self._sleep()
                cands = conn_obj.search("", tipo=tipo, limite=qtd, rowlimit=min(qtd, 100))
                # paginar se necessário
                collected = list(cands)
                start = len(collected)
                while len(collected) < qtd:
                    self._sleep()
                    more = conn_obj.search(
                        "",
                        tipo=tipo,
                        limite=min(100, qtd - len(collected)),
                        rowlimit=min(100, qtd - len(collected)),
                        startrow=start,
                    )
                    if not more:
                        break
                    collected.extend(more)
                    start += len(more)
                    if len(more) < 50:
                        break
                self.state.set("bcb", f"recentes:{tipo}", "metadados",
                               payload={"candidatos": len(collected[:qtd])})
                for cand in collected[:qtd]:
                    chave = cand.key
                    if self.state.done("bcb", chave):
                        self._stats("bcb").pulados += 1
                        continue
                    self._capture_bcb_cand(conn_obj, cand, chave)
            except Unavailable as exc:
                self._mark_indisponivel("bcb", f"recentes:{tipo}", exc.reason[:200])
            except Exception as exc:  # noqa: BLE001
                self._mark_indisponivel("bcb", f"recentes:{tipo}", str(exc)[:200])

    def _capture_bcb_cand(self, conn_obj: Any, cand: Any, chave: str) -> None:
        try:
            self._sleep()
            resp = conn_obj.fetch(cand)
            st = self._stats("bcb")
            st.capturados += 1
            parsed = conn_obj.parse(resp)
            if not isinstance(parsed, ParsedDocument):
                self._mark_indisponivel("bcb", chave, "nao_documento")
                return
            meta = cand.metadata or {}
            number = str(meta.get("numero") or meta.get("number") or cand.key.rsplit(":", 1)[-1])
            date_match = re.search(r"\bdata=(\d{4}-\d{2}-\d{2})", parsed.text)
            work_date = str(meta.get("data") or (date_match.group(1) if date_match else ""))[:10] or None
            year = int(meta.get("ano") or meta.get("year") or (work_date[:4] if work_date else 0))
            tipo = str(meta.get("tipo") or "resolucao").lower().replace(" ", "_")
            auth = "cmn" if "cmn" in tipo else "bcb"
            kind = "resolucao" if auth == "cmn" else "resolucao_bcb"
            wk = WorkKey(auth, kind, re.sub(r"\D", "", number) or number, year)
            if parsed.quarantined or parsed.ambiguous_paths:
                status = "ambiguo"
                st.ambiguos += 1
            else:
                status = "parseado"
                st.parseados += 1
            self.svc.indexar_obra(
                source_id="bcb",
                work_key=wk,
                document=parsed,
                body=resp.body,
                url=resp.final_url or resp.url,
                fetched_at=resp.fetched_at,
                label=cand.title,
                work_date=work_date,
            )
            self.state.set("bcb", chave, status, payload={"url": resp.final_url or resp.url})
        except Unavailable as exc:
            self._mark_indisponivel("bcb", chave, exc.reason[:200])
        except Exception as exc:  # noqa: BLE001
            self._mark_indisponivel("bcb", chave, f"{type(exc).__name__}:{exc}"[:200])

    def sync_stj(self) -> None:
        if not self._want("stj"):
            return
        cfg = self.corpus.get("jurisprudencia", {}).get("stj_espelhos") or {}
        desde = None  # padrão móvel: os doze meses disponíveis mais recentes
        orgaos = list(cfg.get("orgaos") or [])
        max_items = self.max_itens
        conn_obj = self.svc._get("stj")
        conn_obj.sync_state = self.state
        conn_obj.resource_dir = self.svc.home / "stj-resources"
        prec = bool(self.corpus.get("jurisprudencia", {}).get("stj_precedentes_qualificados"))
        collections = [(f"espelhos:recentes12:{datetime.now(timezone.utc):%Y-%m}:{max_items}" + (":prec" if prec else ""), orgaos, desde)]
        for chave, packages, start in collections:
            if self.state.done("stj", chave):
                self._stats("stj").pulados += 1
                continue
            try:
                self._sleep()
                n = conn_obj.sync(desde=start, orgaos=packages, max_itens=max_items, precedentes=prec)
                self._stats("stj").capturados += int(n or 0)
                self._index_stj_from_fts(conn_obj, max_items=None)
                failures = getattr(conn_obj, "last_failures", [])
                for resource_key, reason in failures:
                    self._mark_indisponivel("stj_resource", resource_key, reason)
                if failures:
                    self._mark_indisponivel("stj", chave, failures[0][1])
                else:
                    self.state.set("stj", chave, "capturado", payload={"inseridos_fts": n})
            except Exception as exc:
                self._mark_indisponivel("stj", chave, str(exc)[:200])
                self._index_stj_from_fts(conn_obj, max_items=None)

    def _index_stj_from_fts(self, conn_obj: Any, *, max_items: int | None) -> None:
        import sqlite3

        path = conn_obj.db_path
        if not Path(path).is_file():
            return
        db = sqlite3.connect(str(path))
        db.row_factory = sqlite3.Row
        try:
            rows = db.execute(
                "SELECT key, title, ementa, organ, rapporteur, decision_date, class_name, payload "
                "FROM fts_stj LIMIT ?",
                (max_items if max_items is not None else -1,),
            ).fetchall()
        except sqlite3.Error:
            db.close()
            return
        for row in rows:
            chave = f"stj:{row['key']}"
            # Checkpoint ligado à versão do conteúdo (campos do item, sem o hash do recurso): versão nova reprocessa.
            conteudo = {k: v for k, v in json.loads(row["payload"] or "{}").items() if not k.startswith("_")}
            versao = hashlib.sha256(json.dumps(conteudo, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
            saved = self.state.get("stj_doc", chave)
            if self.state.done("stj_doc", chave) and json.loads(saved["payload_json"] or "{}").get("versao") == versao:
                continue
            try:
                from freoa_verifica.connectors.base import Candidate

                payload = json.loads(row["payload"]) if row["payload"] else {}
                cand = Candidate(
                    source_id="stj",
                    key=str(row["key"]),
                    title=row["title"] or str(row["key"]),
                    snippet=row["ementa"],
                    metadata={
                        "court": "STJ",
                        "orgao": row["organ"],
                        "relator": row["rapporteur"],
                        "classe": row["class_name"],
                        "ementa": row["ementa"],
                        **payload,
                    },
                )
                item = self.svc._index_candidate_juris(conn_obj, cand)
                if item and item.get("capture_id"):
                    self.state.set("stj_doc", chave, "parseado", payload={"versao": versao})
                    self._stats("stj").parseados += 1
                else:
                    self._mark_indisponivel("stj_doc", chave, "sem_evidencia_capturada")
            except Exception as exc:  # noqa: BLE001
                self._mark_indisponivel("stj_doc", chave, str(exc)[:200])
        db.close()

    def sync_tcu(self) -> None:
        if not self._want("tcu"):
            return
        alvo = int(self.corpus.get("jurisprudencia", {}).get("tcu_acordaos") or 2000)
        if self.max_itens is not None:
            alvo = min(alvo, self.max_itens)
        conn_obj = self.svc._get("tcu")
        chave = f"acordaos:{alvo}"
        if self.state.done("tcu", chave):
            self._stats("tcu").pulados += 1
            return
        self.progress(f"tcu sync {alvo} acórdãos")
        try:
            pages = max(1, (alvo + 99) // 100)
            items = conn_obj.sync(inicio=0, quantidade=min(100, alvo), max_pages=pages)
            items = items[:alvo]
            for i, raw in enumerate(items):
                from freoa_verifica.connectors.base import Candidate
                from freoa_verifica.connectors.tcu import _official_id

                oid = _official_id(raw) or str(i)
                ckey = f"tcu:{oid}"
                if self.state.done("tcu_doc", ckey):
                    continue
                cand = Candidate(
                    source_id="tcu",
                    key=oid,
                    title=str(raw.get("titulo") or oid),
                    snippet=raw.get("sumario"),
                    url=raw.get("urlAcordao"),
                    metadata={
                        "court": "TCU",
                        "orgao": raw.get("colegiado"),
                        "relator": raw.get("relator"),
                        "ementa": raw.get("sumario"),
                        **{k: raw[k] for k in raw if k in {
                            "numeroAcordao", "anoAcordao", "key", "urlArquivoPdf",
                            "urlArquivo", "urlAcordao", "dataSessao",
                        }},
                    },
                )
                self._capture_juris("tcu", conn_obj, cand)
                if (i + 1) % 50 == 0:
                    self.progress(f"tcu indexados {i+1}/{len(items)}")
                # Itens já pertencem às páginas oficiais capturadas.
            complete = all(self.state.done("tcu_doc", f"{_official_id(raw)}") for raw in items)
            self.state.set("tcu", chave, "capturado" if complete else "indisponivel", payload={"n": len(items)})
        except Unavailable as exc:
            self._mark_indisponivel("tcu", chave, exc.reason[:200])
        except Exception as exc:  # noqa: BLE001
            self._mark_indisponivel("tcu", chave, str(exc)[:200])

    def sync_tjdft(self) -> None:
        if not self._want("tjdft"):
            return
        cfg = self.corpus.get("jurisprudencia", {}).get("tjdft") or {}
        por = int(cfg.get("por_consulta") or 20)
        if self.max_itens is not None:
            por = min(por, self.max_itens)
        conn_obj = self.svc._get("tjdft")
        for consulta in cfg.get("consultas") or []:
            chave = f"consulta:{consulta}:{por}"
            if self.state.done("tjdft", chave):
                self._stats("tjdft").pulados += 1
                continue
            try:
                self._sleep()
                cands = conn_obj.search(consulta, limite=por)
                ok = all([self._capture_juris("tjdft", conn_obj, c) for c in cands])
                if ok:
                    self.state.set("tjdft", chave, "capturado", payload={"n": len(cands), "total": cands.total})
                else:
                    self._mark_indisponivel("tjdft", chave, "candidato_sem_evidencia")
            except Unavailable as exc:
                self._mark_indisponivel("tjdft", chave, exc.reason[:200])
            except Exception as exc:  # noqa: BLE001
                self._mark_indisponivel("tjdft", chave, str(exc)[:200])

    def _capture_juris(self, fonte: str, connector: Any, cand: Any) -> bool:
        key = str(cand.key)
        checkpoint = fonte + "_doc"
        if self.state.done(checkpoint, key):
            self._stats(fonte).pulados += 1
            return True
        try:
            if not (fonte == "tcu" and cand.key in getattr(connector,"_captured_pages",{})):
                self._sleep()
            item = self.svc._index_candidate_juris(connector, cand)
            if not item or not item.get("capture_id"):
                raise Unavailable("sem_evidencia_capturada")
            self.state.set(checkpoint, key, "parseado")
            self._stats(fonte).capturados += 1
            self._stats(fonte).parseados += 1
            return True
        except Exception as exc:
            self._mark_indisponivel(checkpoint, key, str(exc)[:200])
            return False

    def sync_cvm_colegiado(self) -> None:
        if not self._want("cvm_colegiado"):
            return
        from dataclasses import replace
        from freoa_verifica.connectors.base import ParsedDecision
        desde = int(self.corpus.get("jurisprudencia", {}).get("cvm_colegiado_desde") or 2023)
        connector = self.svc._get("cvm_colegiado")
        processed = 0
        for ano in range(desde, datetime.now().year + 1):
            try:
                self._sleep()
                cands = connector.search("", ano=ano, limite=100_000)
                self.state.set("cvm_colegiado", f"colegiado:{ano}", "metadados",
                               payload={"candidatos": len(cands)})
                for cand in cands:
                    self._sleep()
                    parsed = connector.parse(connector.fetch(cand))
                    if not isinstance(parsed, ParsedDecision):
                        raise Unavailable("nao_decisao")
                    items = parsed.metadata.get("decisoes") or [{"official_id": parsed.official_id}]
                    for item in items:
                        oid = item["official_id"]
                        if self.state.done("cvm_colegiado_doc", oid):
                            self._stats("cvm_colegiado").pulados += 1
                            continue
                        if self.max_itens is not None and processed >= self.max_itens:
                            return
                        single = replace(cand, key=oid, metadata={**cand.metadata, **({"item": int(oid.rsplit("#", 1)[-1])} if "#" in oid else {})})
                        self._capture_juris("cvm_colegiado", connector, single)
                        processed += 1
            except Exception as exc:
                self._mark_indisponivel("cvm_colegiado", f"colegiado:{ano}", str(exc)[:200])

    def sync_stf(self) -> None:
        if not self._want("stf"):
            return
        cfg = self.corpus.get("jurisprudencia", {}).get("stf_temas_rg") or {}
        de = int(cfg.get("de") or 1)
        ate = int(cfg.get("ate") or 1400)
        if self.max_itens is not None:
            ate = min(ate, de + self.max_itens - 1)
        conn_obj = self.svc._get("stf")
        for tema in range(de, ate + 1):
            chave = f"tema:{tema}"
            if self.state.done("stf", chave):
                self._stats("stf").pulados += 1
                continue
            if tema % 50 == 1:
                self.progress(f"stf temas RG {tema}..{ate}")
            try:
                self._sleep()
                cands = conn_obj.resolve_tema(tema)
                if not cands:
                    self._mark_indisponivel("stf", chave, "vazio")
                    continue
                cand = cands[0]
                title = cand.title or f"Tema {tema}"
                thesis = (cand.metadata or {}).get("tese") or cand.snippet
                tid = new_ulid()
                existing = self.svc.conn.execute(
                    "SELECT id FROM theme WHERE court='STF' AND number=?",
                    (str(tema),),
                ).fetchone()
                if existing is None:
                    self.svc.conn.execute(
                        "INSERT INTO theme(id, court, number, title, thesis) VALUES (?,?,?,?,?)",
                        (tid, "STF", str(tema), title, thesis),
                    )
                    self.svc.conn.commit()
                self.state.set("stf", chave, "parseado", payload={"titulo": title})
                self._stats("stf").parseados += 1
                self._stats("stf").capturados += 1
            except Unavailable as exc:
                self._mark_indisponivel("stf", chave, exc.reason[:200])
            except Exception as exc:  # noqa: BLE001
                self._mark_indisponivel("stf", chave, str(exc)[:200])

        if self.corpus.get("jurisprudencia", {}).get("stf_sumulas"):
            for base in SUMULA_BASES:
                lista = f"sumulas:{base}"
                try:
                    self._sleep()
                    cands = conn_obj.list_sumulas(base)
                except Exception as exc:  # noqa: BLE001
                    self._mark_indisponivel("stf", lista, getattr(exc, "reason", str(exc))[:200])
                    continue
                for cand in cands[: self.max_itens]:
                    if self.state.done("stf", cand.key):
                        self._stats("stf").pulados += 1
                        continue
                    try:
                        self._sleep()
                        item = self.svc._index_candidate_juris(conn_obj, cand)
                        if item and item.get("capture_id"):
                            self.state.set("stf", cand.key, "parseado")
                            self._stats("stf").parseados += 1
                            self._stats("stf").capturados += 1
                        else:
                            self._mark_indisponivel("stf", cand.key, "sem_evidencia_capturada")
                    except Exception as exc:  # noqa: BLE001
                        self._mark_indisponivel("stf", cand.key, str(exc)[:200])

    def run(self) -> dict[str, Any]:
        self.progress("início sync semente")
        steps = [
            ("planalto", self.sync_planalto),
            ("cvm_normas", self.sync_cvm),
            ("bcb", self.sync_bcb),
            ("stj", self.sync_stj),
            ("tcu", self.sync_tcu),
            ("tjdft", self.sync_tjdft),
            ("cvm_colegiado", self.sync_cvm_colegiado),
            ("stf", self.sync_stf),
        ]
        queue = [(nome, fn, 0) for nome, fn in steps]
        for nome, fn, attempt in queue:
            if not self._want(nome):
                continue
            try:
                if attempt:
                    from freoa_verifica.transport import circuit_retry_after
                    wait_until = time.monotonic() + max(self.retry_backoff * 2 ** (attempt - 1), circuit_retry_after())
                    self.progress(f"{nome}: reagendado, tentativa {attempt + 1}")
                    while time.monotonic() < wait_until:
                        time.sleep(min(1.0, wait_until - time.monotonic()))
                if self.svc._offline():
                    self._mark_indisponivel(nome, "_fonte", "offline")
                    continue
                fn()
                if self.state.get(nome, "_fonte"):
                    self.state.set(nome, "_fonte", "concluido")
            except Exception as exc:  # noqa: BLE001 — falha não aborta o conjunto
                log.exception("falha em fonte %s", nome)
                self._mark_indisponivel(nome, "_fonte", str(exc)[:200])
            # Uma nova passagem ao fim da fila reaproveita checkpoints bem sucedidos.
            # Falhas permanentes e desafios não são repetidos automaticamente.
            failures = [(f, k, reason) for (f, k), reason in self._failed.items()
                        if self._stats(f).fonte == nome
                        and (self.state.get(f, k) or {}).get("status") == "indisponivel"]
            if attempt < 2 and any(_transient(reason) for _, _, reason in failures):
                queue.append((nome, fn, attempt + 1))
        for st in self.stats.values():
            st.indisponiveis = 0
            st.motivos = {}
        for fonte, chave in self._failed:
            row = self.state.get(fonte, chave)
            if row and row["status"] == "indisponivel":
                st = self._stats(fonte)
                reason = row["motivo"] or "sem_motivo"
                st.indisponiveis += 1
                st.motivos[reason] = st.motivos.get(reason, 0) + 1
        relatorio = {
            "sincronizado_em": _now(),
            "modo": "semente",
            "max_itens": self.max_itens,
            "fontes": [self._stats(n).as_dict() for n, _ in steps if n in self.stats or self._want(n)],
        }
        self.progress("fim sync semente")
        return relatorio


def _transient(reason: str) -> bool:
    return any(part in reason.lower() for part in (
        "timeout", "transportelento", "http_408", "http_429", "http_500",
        "http_502", "http_503", "http_504", "circuit breaker", "transitorio",
    ))
