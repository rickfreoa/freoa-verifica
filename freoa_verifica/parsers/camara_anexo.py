"""Inspeção por folha; não atribui automaticamente texto de PDF a um anexo."""
import io
import json

import pypdf

from freoa_verifica.parsers.model import ParsedDocument, EditorialBlock, Issue


def parse_camara_anexo(body):
    reader = pypdf.PdfReader(io.BytesIO(body), strict=True)
    if not 1 <= len(reader.pages) <= 100:
        raise ValueError("pdf_paginas_excedidas")
    config = {"extrator": "pypdf", "versao": pypdf.__version__, "strict": True,
              "extraction_mode": "plain", "orientations": [0, 90, 180, 270], "ocr": False}
    doc = ParsedDocument("camara_anexo", "camara-anexo-1", "Anexo: escopo pendente", None, "")
    doc.editorial_blocks.append(EditorialBlock(json.dumps(config, sort_keys=True), (0, 0), "extrator_pdf"))
    seen = {}
    for index, page in enumerate(reader.pages, 1):
        text = page.extract_text(extraction_mode="plain")
        if not text:
            raise ValueError("pdf_folha_sem_extracao")
        if len(doc.text) + len(text) > 2 * 1024**2:
            raise ValueError("pdf_texto_excedido")
        start = len(doc.text)
        doc.text += text + "\n"
        doc.editorial_blocks.append(EditorialBlock(text, (start, start + len(text)), f"folha_pdf_{index}"))
        if text in seen:
            doc.issues.append(Issue("TEXTO_EXTRAIDO_REPETIDO", None,
                                    f"folhas PDF {seen[text]} e {index}; não prova folha repetida", "document"))
        seen[text] = index
    doc.issues.append(Issue("ESCOPO_ANEXO_NAO_VALIDADO", None,
                            "rubrica, publicação, colunas e célula dependem de conferência visual independente", "document"))
    return doc
