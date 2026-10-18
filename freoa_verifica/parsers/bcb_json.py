"""Perfil BCB — JSON exibenormativo com HTML embutido."""

from __future__ import annotations

import json
import re
from typing import Any

from freoa_verifica.parsers.html_devices import PARSER_VERSION, parse_html_devices
from freoa_verifica.parsers.model import ParsedDocument
from freoa_verifica.parsers.sentinel import run_sentinels


def parse_bcb_json(data: bytes | str | dict[str, Any]) -> ParsedDocument:
    raw_bytes: bytes | None = None
    if isinstance(data, (bytes, bytearray)):
        raw_bytes = bytes(data)
        payload = json.loads(raw_bytes.decode("utf-8"))
    elif isinstance(data, str):
        payload = json.loads(data)
    else:
        payload = data

    item = _pick_item(payload)
    title = str(item.get("Titulo") or item.get("titulo") or "").strip()
    tipo = str(item.get("Tipo") or "").strip()
    numero = item.get("Numero")
    data_iso = item.get("Data")
    if isinstance(data_iso, str) and "T" in data_iso:
        data_iso = data_iso.split("T", 1)[0]
    revogado = bool(item.get("Revogado"))
    cancelado = bool(item.get("Cancelado"))
    assunto = item.get("Assunto")
    html_body = str(item.get("Texto") or "")
    # Antes de 2020 o BCB publica as resoluções do CMN como tipo "Resolução"; só vale como CMN
    # quando o próprio preâmbulo declara o Conselho Monetário Nacional (gold independente 1.1.0).
    if tipo == "Resolução" and re.search(r"Conselho\s+Monet[áa]rio\s+Nacional", html_body[:3000]):
        tipo = "Resolução CMN"

    # Envolve em html mínimo para sentinela de fecho
    wrapped = f"<html><body>{html_body}</body></html>"
    _t, _e, doc_text, provisions, local_issues, amendments, editorial_blocks = (
        parse_html_devices(
            wrapped,
            base_url="https://www.bcb.gov.br/",
        )
    )

    meta_bits = [tipo]
    if numero is not None:
        try:
            meta_bits.append(str(int(numero)))
        except (TypeError, ValueError):
            meta_bits.append(str(numero))
    if data_iso:
        meta_bits.append(str(data_iso))
    situacao = "revogado" if revogado else ("cancelado" if cancelado else "vigente")
    ementa = str(assunto).strip() if assunto else None
    if not title:
        title = " ".join(x for x in meta_bits if x)

    doc = ParsedDocument(
        profile="bcb_json",
        parser_version=PARSER_VERSION,
        title=title,
        ementa=ementa,
        text=doc_text,
        provisions=provisions,
        issues=list(local_issues),
        amendments=amendments,
        editorial_blocks=editorial_blocks,
    )
    # Metadados de situação como issue informativa não bloqueadora via texto
    doc.text = (
        f"[tipo={tipo}; numero={numero}; data={data_iso}; situacao={situacao}]\n"
        + doc.text
    )
    doc.issues.extend(run_sentinels(doc, raw=wrapped))
    return doc


def _pick_item(payload: dict[str, Any]) -> dict[str, Any]:
    conteudo = payload.get("conteudo")
    if isinstance(conteudo, list) and conteudo:
        first = conteudo[0]
        if isinstance(first, dict):
            return first
    if isinstance(conteudo, dict):
        return conteudo
    return payload
