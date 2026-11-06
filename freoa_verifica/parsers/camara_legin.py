"""Perfis HTML Legin. Projeção normativa com hierarquia; notas ficam recuperáveis."""
from __future__ import annotations

import re
import json
from datetime import date
from urllib.parse import urljoin
from lxml import html

from freoa_verifica.parsers.model import (ParsedDocument, Provision, Redaction, Annotation, Issue,
                                         EditorialBlock, QuotedAmendment, veto_stub)
from freoa_verifica.parsers.paths import roman_to_int

PARSER_VERSION = "camara-legin-4"
_LABEL = re.compile(r"^(?:(Art\.\s*(\d+[º°o]?(?:-[A-Z])?)[.]?)|"
                    r"(§\s*(\d+[º°o]?(?:-[A-Z])?)[.]?)|(Parágrafo\s+único[.]?)|"
                    r"([IVXLCDM]+)\s*[-–—]|([a-z])\)|([1-9]\d*)\.)\s*", re.I)
_NOTA = re.compile(r"\((?:[^()]|\([^()]*\))*\)", re.S)
_FAMILIA = re.compile(r"^(?:[“\"]?Caput[”\"]?(?: do artigo)?|Artigo|Inciso|Alínea|Item|"
                      r"Parágrafo(?: único)?|Primitivo|"
                      r"Redação|Revogad[oa]|Incluíd[oa]|Vide|VETAD[OA])\b", re.I)
_COMANDO_NOTA = re.compile(r"(?:com (?:nova )?redação dada|acrescid[oa](?: dada)?|incluíd[oa]|revogad[oa]|renumerad[oa])"
                           r"\s+(?:pel[ao]\s+)?(?:Lei(?: Complementar)?|Medida Provisória|Decreto(?:-lei)?)\s+(?:n[º°o]?\s*)?[\d.]+|"
                           r"transformad[oa] em §\s*\d+[º°o]? pel[ao] Lei(?: Complementar)?\s+n[º°o]?\s*[\d.]+|"
                           r"^Vide\s+(?:Lei(?: Complementar)?|Decreto(?:-lei)?|art\.)|VETAD[OA](?:\s+na\s+Lei(?: Complementar)?\s+n[º°o]?\s*[\d.]+"
                           r"(?:,\s*de\s*\d{1,2}/\d{1,2}/\d{4})?)?$|^Revogad[oa]$", re.I)


def _alvo_nota(inside, active, records):
    """O sujeito editorial nomeia o nível; a pilha só resolve seus ancestrais."""
    primitive = re.match(r'^Primitivo\s+(§\s*\d+[º°o]?|inciso\s+[IVXLCDM]+)\s+renumerad[oa]\b', inside, re.I)
    if primitive:
        level = 2 if primitive[1].startswith("§") else 3
        return next((r["path"] for r in reversed(records) if r["level"] == level and
                     (active["path"] == r["path"] or active["path"].startswith(r["path"] + "."))), None)
    subject = re.match(r'^[“"]?(Caput|Artigo|Parágrafo(?: único)?|Inciso|Alínea|Item)\b[”"]?', inside, re.I)
    if not subject:
        # Predicado sem sujeito explícito refere-se ao recorte em que foi publicado.
        return (active["path"] if re.match(r'^(?:NR$|Redação\b|Revogad[oa]\b|Incluíd[oa]\b|Vide\b|VETAD[OA]\b)', inside, re.I)
                else None)
    family = subject[1].lower()
    remainder = inside[subject.end():]
    if family == "caput":
        qualifier = re.match(r'\s+d[oa]\s+(artigo|parágrafo|inciso|alínea)\b', remainder, re.I)
        if not qualifier or qualifier[1].lower() != "artigo":
            return None
        remainder = remainder[qualifier.end():]
    if not re.match(r'\s+(?:com (?:nova )?redação dada|acrescid[oa]|incluíd[oa]|revogad[oa]|renumerad[oa]|transformad[oa]|VETAD[OA])\b', remainder, re.I):
        return None
    if family == "caput":
        level = 1
        for record in reversed(records):
            if record["level"] == level and (active["path"] == record["path"] or
                                            active["path"].startswith(record["path"] + ".")):
                return record["path"] + ".caput"
        return None
    level = {"artigo": 1, "parágrafo": 2, "parágrafo único": 2,
             "inciso": 3, "alínea": 4, "item": 5}[family]
    for record in reversed(records):
        if record["level"] == level and (active["path"] == record["path"] or
                                        active["path"].startswith(record["path"] + ".")):
            return record["path"]
    return None


def _blocos(root):
    pieces, current = [], []
    def flush():
        t = " ".join("".join(current).split())
        current.clear()
        if t:
            pieces.append(t)
    def visit(el):
        if not isinstance(el.tag, str) or el.tag.lower() in {"script", "style", "noscript", "head"}:
            return
        tag = el.tag.lower()
        block = tag in {"p", "div", "br", "td", "th", "tr", "h1", "h2", "h3", "h4", "center", "li"}
        if block:
            flush()
        if el.text:
            current.append(el.text)
        for child in el:
            visit(child)
            if child.tail:
                current.append(child.tail)
        if block:
            flush()
    visit(root)
    flush()
    return pieces


def parse_camara_legin(data: str, *, base_url=None):
    original = bool(base_url and "-publicacaooriginal-" in base_url)
    profile = "camara_original" if original else "camara_atualizado"
    doc = ParsedDocument(profile, PARSER_VERSION, "", None, "")
    if len(data.encode("utf-8")) > 30 * 1024**2:
        doc.issues.append(Issue("TRUNCATED", None, "entrada_excedida", "document"))
        return doc
    tree = html.fromstring(data, parser=html.HTMLParser(no_network=True, huge_tree=False))
    if max((len(list(e.iterancestors())) for e in tree.iter()), default=0) > 200:
        doc.issues.append(Issue("TRUNCATED", None, "profundidade_excedida", "document"))
        return doc
    if original:
        roots = tree.xpath('//*[@id="content"]//div[@class="textoNorma"]')
        titles = tree.xpath('//*[@id="content"]//h1')
        if len(roots) != 1 or len(titles) != 1:
            doc.issues.append(Issue("TRUNCATED", None, "perfil_original_desconhecido", "document"))
            return doc
        root = roots[0]
        doc.title = " ".join(titles[0].text_content().split())
    else:
        root = tree.find("body") if tree.find("body") is not None else tree
    lines = _blocos(root)
    lines = [part for line in lines for part in re.split(r"(?<=[.!?])\s+(?=§\s*\d+[º°o.])", line)]
    headings = {" ".join("".join(e.itertext()).split()) for e in root.iter()
                if isinstance(e.tag, str) and (e.tag.lower() in {"center", "h1", "h2", "h3", "h4"}
                or e.get("align", "").lower() == "center"
                or re.search(r"text-align\s*:\s*center", e.get("style", ""), re.I))}
    if not original:
        doc.title = next((t for t in lines if re.match(r"^(?:LEI|MEDIDA PROVISÓRIA|DECRETO)(?: COMPLEMENTAR)?\s+N", t)), "")
    doc.text = "\n".join(lines)
    # O lote também publica leis sem a linha "Brasília": terminam com autores em bloco próprio.
    # Reconhecer a forma editorial, não uma lista de nomes nem uma data inferida dela.
    name = re.compile(r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÀ-ÿ]+(?: (?:d[aeo]s?|e|[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÀ-ÿ]+)){1,8}")
    author_start = None
    for idx in range(max(0, len(lines) - 12), len(lines)):
        if (lines[idx].isupper() and name.fullmatch(lines[idx]) and idx + 1 < len(lines)
                and not re.match(r"(?:CAPÍTULO|SEÇÃO|TÍTULO|LIVRO|ANEXO|DISPOSIÇÕES|DO|DA|DOS|DAS)\b", lines[idx])
                and all(name.fullmatch(line) for line in lines[idx + 1:])):
            author_start = idx
            break
    if not re.search(r"(?:^|\n)Art\.\s*1[º°o.\s]", doc.text):
        doc.issues.append(Issue("TRUNCATED", None, "inicio_normativo_nao_reconhecido", "document"))
    if not re.search(r"^Brasília[,;]\s*\d{1,2}[º°]?\s+de\s+\w+\s+de\s+\d{4}", doc.text, re.M | re.I) and author_start is None:
        doc.issues.append(Issue("TRUNCATED", None, "fecho_documental_nao_identificado", "document"))
    if author_start is not None:
        start = sum(len(line) + 1 for line in lines[:author_start])
        doc.editorial_blocks.append(EditorialBlock("\n".join(lines[author_start:]), (start, len(doc.text)), "bloco_autoral_terminal"))
    links = [(" ".join("".join(a.itertext()).split()), urljoin(base_url or "", a.get("href"))) for a in root.xpath('.//a[@href]')]
    records = []
    art = par = inc = ali = None
    active = None
    offset = 0
    in_quote, pending_quote = False, False
    quote_host, quote_parts = "", []
    quote_close = None
    quote_open, quote_balance = None, 0
    last_article = None
    used_note_spans = set()
    pending_annotations = []
    for index, line in enumerate(lines):
        start, end = offset, offset + len(line)
        offset = end + 1
        if author_start is not None and index >= author_start:
            active = None
            continue
        if in_quote or (pending_quote and re.match(r'^[“"«‘\']', line)) or re.match(r'^[“"«‘\'](?:Art\.|CAPÍTULO|SEÇÃO|TÍTULO|LIVRO)', line, re.I):
            if not in_quote:
                quote_host = art or ""
                quote_parts = []
                quote_close = {"“": "”", "«": "»", "‘": "’"}.get(line[0], line[0])
                quote_open, quote_balance = line[0], 0
            in_quote = True
            quote_parts.append(line)
            if quote_open == quote_close:
                quote_balance = (quote_balance + line.count(quote_open)) % 2
            else:
                quote_balance += line.count(quote_open) - line.count(quote_close)
            if quote_balance == 0 and re.search(re.escape(quote_close) + r"\s*(?:\(NR\))?\s*$", line):
                doc.amendments.append(QuotedAmendment(quote_host, "atribuição pendente", "", "\n".join(quote_parts)))
                in_quote, pending_quote = False, False
            continue
        match = _LABEL.match(line)
        if pending_quote and match:
            doc.issues.append(Issue("SCOPE_COLLISION", art, "comando alterador sem escopo citado reconhecido", "document"))
        if match and match[1]:
            pending_quote = False
        if match:
            raw_label = match[0].strip()
            if match[1]:
                number = re.sub(r"[º°o]", "", match[2], flags=re.I)
                art = "art" + number.upper()
                numeric = re.fullmatch(r"(\d+)(?:-([A-Z]))?", number.upper())
                order = (int(numeric[1]), numeric[2] or "") if numeric else None
                if last_article is not None and order is not None and order < last_article:
                    doc.issues.append(Issue("ORDER", art, "ordem de artigos inexplicável", "document"))
                if last_article is not None and order is not None and order[0] > last_article[0] + 1:
                    doc.issues.append(Issue("TRUNCATED", art, "sequência de artigos com lacuna não explicada", "document"))
                last_article = order
                path, level = art, 1
                par = inc = ali = None
            elif match[3] or match[5]:
                if not art:
                    continue
                number = "unico" if match[5] else re.sub(r"[º°o]", "", match[4], flags=re.I).upper()
                par = art + ".par" + number
                path, level = par, 2
                inc = ali = None
            elif match[6]:
                if not art:
                    continue
                inc = (par or art) + ".inc" + str(roman_to_int(match[6].upper()))
                path, level = inc, 3
                ali = None
            elif match[7]:
                if not art:
                    continue
                ali = (inc or par or art) + ".ali-" + match[7].lower()
                path, level = ali, 4
            else:
                if not (ali or inc):
                    continue
                path, level = (ali or inc) + ".item" + match[8], 5
            active = {"path": path, "level": level, "label": raw_label, "start": start,
                      "end": end, "text": line[match.end():], "annotations": []}
            records.append(active)
        elif active and (re.match(r"^(?:CAPÍTULO|SEÇÃO|TÍTULO|LIVRO)\b|^Brasília[,;]", line, re.I)
                         or line in headings):
            # Rubrica/epígrafe encerra o recorte; não é continuação normativa.
            active = None
        elif active:
            active["text"] += "\n" + line
            active["end"] = end
        if active and re.search(r"passam? a vigorar|fica acrescid|seguinte redação|seguintes alterações", line, re.I):
            pending_quote = True
        if active:
            clean = active["text"]
            for m in list(_NOTA.finditer(clean))[::-1]:
                raw = m[0]
                inside = raw[1:-1].strip()
                if inside == "NR" or (_FAMILIA.match(inside) and _COMANDO_NOTA.search(inside)):
                    kind = ("vide" if inside.lower().startswith("vide") else
                            "revogado" if "revogad" in inside.lower() else
                            "veto" if "vetad" in inside.lower() else
                            "renumerado" if re.search(r"renumerad|transformad", inside, re.I) else
                            "incluido" if re.search(r"acrescid|incluíd", inside, re.I) else "redacao_dada")
                    ref = re.search(r"(?:Lei|Medida Provisória|Decreto)[^)]*", inside)
                    refs = [{"rotulo": t, "href": u} for t, u in links if t and (t in raw or raw in t)]
                    href = refs[0]["href"] if refs else None
                    dates = set()
                    for day, month, year in re.findall(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", raw):
                        try:
                            dates.add(date(int(year), int(month), int(day)).isoformat())
                        except ValueError:
                            pass  # data literal inválida não é corrigida
                    act_date = next(iter(dates)) if len(dates) == 1 else None
                    target = _alvo_nota(inside, active, records)
                    if target is None:
                        doc.issues.append(Issue("ALVO_NOTA_INCERTO", active["path"], raw, "provision"))
                    ann = Annotation(kind, raw, ref[0] if ref else None, href, act_date, target)
                    pending_annotations.append((active, ann))
                    # Toda nota removida da projeção mantém texto e âncora no texto-fonte.
                    note_start = doc.text.rfind(raw, active["start"], active["end"])
                    while note_start >= 0 and (note_start, note_start + len(raw)) in used_note_spans:
                        note_start = doc.text.rfind(raw, active["start"], note_start)
                    if note_start >= 0:
                        note_span = (note_start, note_start + len(raw))
                        used_note_spans.add(note_span)
                        doc.editorial_blocks.append(EditorialBlock(raw, note_span, "nota_camara"))
                        doc.editorial_blocks.append(EditorialBlock(json.dumps(refs, ensure_ascii=False), note_span, "nota_camara_links"))
                    if re.search(r"vigor|efeitos|vigência|condicionad", inside, re.I):
                        pending_annotations.append((active, Annotation("vigencia", raw, ann.act_ref, href,
                                                                         act_date, target)))
                    clean = clean[:m.start()] + clean[m.end():]
                elif re.search(r"redação|renumerad|transformad|acrescid|incluíd|revogad|vetad|^vide\b|produção de efeitos", inside, re.I):
                    doc.issues.append(Issue("NOTA_NAO_RECONHECIDA", active["path"], raw, "provision"))
            active["text"] = clean.strip()
    if in_quote:
        doc.issues.append(Issue("TRUNCATED", quote_host, "citacao_alteradora_sem_fim", "document"))
    # Associar depois da leitura permite que uma nota terminal pertença ao artigo/caput.
    caput_annotations = {}
    for owner, ann in pending_annotations:
        if ann.target_path and ann.target_path.endswith(".caput"):
            caput_annotations.setdefault(ann.target_path, []).append(ann)
        else:
            targets = [r for r in records if r["path"] == ann.target_path and
                       r["start"] <= owner["start"]]
            (targets[-1] if targets else owner)["annotations"].append(ann)
    seen = {}
    for i, r in enumerate(records):
        descendants = []
        for child in records[i+1:]:
            if child["level"] <= r["level"] or not child["path"].startswith(r["path"] + "."):
                break
            descendants.append(child)
        text = r["text"] + "".join("\n" + c["label"] + " " + c["text"] for c in descendants)
        anns = r["annotations"]
        if any(a.kind == "revogado" for c in descendants for a in c["annotations"]):
            doc.issues.append(Issue("REVOGACAO_PARCIAL", r["path"],
                                    "revogação restrita a descendente; agregado não revogado", "provision"))
        impediments = [a for c in [r, *descendants] for a in
                       (c["annotations"] if c is not r else []) + caput_annotations.get(c["path"] + ".caput", [])
                       if a.kind in {"vide", "vigencia", "veto", "renumerado"}]
        if impediments:
            doc.issues.append(Issue("IMPEDIMENTO_DESCENDENTE", r["path"],
                                    json.dumps([{"target_path": a.target_path, "kind": a.kind, "raw": a.raw}
                                                for a in impediments], ensure_ascii=False), "provision"))
        if veto_stub(r["text"], anns):
            doc.issues.append(Issue("VETO", r["path"], "dispositivo sem redação normativa", "provision"))
        span = (r["start"], descendants[-1]["end"] if descendants else r["end"])
        prov = Provision(r["path"], r["label"], "", redactions=[Redaction(text, False, 0, anns, span)])
        if r["path"] in seen:
            seen[r["path"]].ambiguous = prov.ambiguous = True
            doc.issues.append(Issue("DUPLICATE_CURRENT", r["path"], "rótulo concorrente", "provision"))
        seen[r["path"]] = prov
        doc.provisions.append(prov)
        if r["level"] == 1:
            cap_path = r["path"] + ".caput"
            cap = Provision(cap_path, r["label"] + " caput", "", redactions=[Redaction(
                r["text"], False, 0, caput_annotations.get(cap_path, []), (r["start"], r["end"]))])
            if cap_path in seen:
                seen[cap_path].ambiguous = cap.ambiguous = True
                doc.issues.append(Issue("DUPLICATE_CURRENT", cap_path, "caput concorrente", "provision"))
            seen[cap_path] = cap
            doc.provisions.append(cap)
    # Um agregado inclui os descendentes: impedimento do filho impede confronto do agregado.
    for issue in list(doc.issues):
        if issue.path and issue.blocking_scope == "provision":
            parts = issue.path.split(".")
            for j in range(1, len(parts)):
                doc.issues.append(Issue(issue.code, ".".join(parts[:j]), issue.detail, "provision"))
    return doc
