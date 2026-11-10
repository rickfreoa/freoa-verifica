"""Reconstituição offline da proveniência; usa o mesmo preflight da captura.

Não descobre novas arestas a partir de metadados ou de páginas sem proveniência.
"""
import json
import re

from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.camara_legin import CamaraLeginConnector, _exigir_instante
from freoa_verifica.connectors.camara_policy import validar_url
from freoa_verifica.transport import Response


def resposta_capturada(cap, home, *, blob_dir=None):
    from freoa_verifica.store import blobs
    if not isinstance(cap["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", cap["sha256"]):
        raise Unavailable("hash_captura_divergente")
    body = (blob_dir / cap["sha256"][:2] / cap["sha256"][2:4] / cap["sha256"]).read_bytes() if blob_dir else blobs.get_blob(cap["sha256"], home=home)
    headers, redirects = json.loads(cap["headers_json"]), json.loads(cap["redirects_json"])
    if (not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items())
            or not isinstance(redirects, list) or not all(isinstance(v, str) for v in redirects)
            or cap["size"] != len(body)):
        raise Unavailable("resposta_camara_invalida")
    return Response(cap["url"], cap["final_url"], cap["status"], headers, body,
                    cap["sha256"], cap["fetched_at"], redirects, cap["mime"], size=len(body),
                    content_type=cap["content_type"] or "")


def reconstruir(document, response, carregar):
    """Reconstrói somente as arestas declaradas, preservando sua ordem e hashes."""
    con = CamaraLeginConnector()
    con.paginas[response.url] = response
    bodies = {(response.url, response.sha256): response}

    def reler(url, digest):
        key = (url, digest)
        page = bodies.get(key)
        if page is None:
            page = carregar(url, digest)
        if page.url != url or page.sha256 != digest:
            raise Unavailable("hash_ancestral_divergente")
        bodies[key] = page
        return page

    inv = next(json.loads(b.text) for b in document.editorial_blocks if b.kind == "camara_inventario")
    con._texto_url = response.url
    con._cadeia_declarada = inv.get("descoberta", [])
    con._pagina_declarada = inv["pagina"]
    for failure in inv.get("falhas_descoberta", []):
        con.falhas_descoberta.append(Unavailable(failure["motivo"]))
    unit = inv.get("conjunto_descoberta")
    if unit is not None:
        for page in unit["paginas"]:
            captured = reler(page["url"], page["sha256"])
            if captured.url in con.paginas and con.paginas[captured.url].sha256 != captured.sha256:
                raise Unavailable("hash_ancestral_divergente")
            con.paginas[captured.url] = captured
        for edge in unit["arestas"]:
            source = reler(edge["origem_url"], edge["origem_sha256"])
            if edge["url"] in con.links:
                raise Unavailable("cadeia_descoberta_invalida")
            con.links[edge["url"]] = (source, edge["href"], edge["rotulo"])
        return con
    cursor = response.url
    for edge in inv.get("descoberta", []):
        if edge["url"] != cursor or cursor in con.links:
            raise Unavailable("cadeia_descoberta_invalida")
        source = reler(edge["origem_url"], edge["origem_sha256"])
        captured = con.paginas.get(source.url)
        if captured is not None and captured.sha256 != source.sha256:
            raise Unavailable("hash_ancestral_divergente")
        con.paginas[source.url] = source
        con.links[cursor] = (source, edge["href"], edge["rotulo"])
        cursor = source.url
    return con


def validar_acervo(conn, home, *, blob_dir=None):
    """Snapshot: cada captura normativa precisa de cadeia recuperável no modelo.

    Capturas sem modelo (por falha local de parse) permanecem no home, mas não
    são exportáveis sem prova persistida de descoberta. Não se omitem do lote.
    Cada versão é validada separadamente: URL igual não mistura hashes antigos.
    """
    from freoa_verifica.parsers.model import document_from_dict
    cursor = conn.execute("SELECT * FROM capture WHERE source_id='camara_legin'")
    columns = [c[0] for c in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor]
    # URL/hash identifica os bytes, não os metadados de cada obtenção. Uma
    # captura válida posterior não pode encobrir outra com status/MIME inválido.
    responses = CamaraLeginConnector()
    checked = set()
    for cap in rows:
        page = resposta_capturada(cap, home, blob_dir=blob_dir)
        responses._validar_response(page, page.url, validadas=checked)
        _exigir_instante(page)  # cada recibo, antes da redução por URL/hash (conferência)
    by_key = {(r["url"], r["sha256"]): r for r in rows}
    covered = set()

    def carregar(url, digest):
        cap = by_key.get((url, digest))
        if cap is None:
            raise Unavailable("descoberta_sem_raiz")
        return resposta_capturada(cap, home, blob_dir=blob_dir)

    for cap in rows:
        model = conn.execute("SELECT model_json FROM parsed_document WHERE capture_id=?", (cap["id"],)).fetchone()
        if model is None:
            continue
        response = resposta_capturada(cap, home, blob_dir=blob_dir)
        con = reconstruir(document_from_dict(json.loads(model[0])), response, carregar)
        con.validar_conjunto()
        covered.update((p.url, p.sha256) for p in con.paginas.values())
    for cap in rows:
        if (cap["url"], cap["sha256"]) in covered:
            continue
        con = CamaraLeginConnector()
        page = carregar(cap["url"], cap["sha256"])
        con.paginas[page.url] = page
        # Busca, portal e robots independentes são evidência de obtenção, não
        # se tornam raiz de captura normativa órfã.
        con.validar_conjunto()
        if validar_url(page.url)["recurso"] not in {"busca", "portal", "robots"}:
            raise Unavailable("vinculo_descoberta_ausente")
