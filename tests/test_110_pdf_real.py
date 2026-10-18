"""1.1.0, auditoria rodada 6: PDF real gerado em memória; descarte em fronteira limpa bloqueia o dispositivo."""
from freoa_verifica.connectors.cvm_normas import parse_pdf_direto


def _pdf(paginas: list[list[tuple[int, str]]]) -> bytes:
    """PDF mínimo (Helvetica, ASCII) com cada linha na altura dada."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for linhas in paginas:
        corpo = "".join(f"BT /F1 11 Tf 72 {y} Td ({t}) Tj ET\n" for y, t in linhas).encode("latin-1")
        objs.append(f"<< /Length {len(corpo)} >>\nstream\n" + corpo.decode("latin-1") + "endstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {len(objs)} 0 R >>")
        kids.append(len(objs))
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + "".join(f"{o:010} 00000 n \n" for o in offs).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def _codigos(doc, path):
    return {i.code for i in doc.issues if i.path == path}


def test_ressalva_em_caixa_alta_na_borda_bloqueia_o_artigo():
    pags = [[(800, "COMISSAO DE VALORES MOBILIARIOS")] + ([(600, "RESOLUCAO CVM 999/2026")] if n == 1 else [])
            + [(120, f"Art. {n}o A divulgacao e obrigatoria."), (80, "SALVO AUTORIZACAO PREVIA DA CVM.")] for n in (1, 2, 3)]
    doc = parse_pdf_direto(_pdf(pags))
    assert "MARGEM_ADJACENTE" in _codigos(doc, "art1") and "MARGEM_ADJACENTE" in _codigos(doc, "art3")


def test_inciso_na_borda_e_mantido():
    pags = [[(800, "COMISSAO DE VALORES MOBILIARIOS")] + ([(600, "RESOLUCAO CVM 999/2026")] if n == 1 else [])
            + [(120, f"Art. {n}o O emissor deve:"), (80, "I - divulgar o relatorio.")] for n in (1, 2, 3)]
    doc = parse_pdf_direto(_pdf(pags))
    assert doc.current_text("art1.inc1") == "divulgar o relatorio."


def _verificar(doc, citacao, trecho):
    from freoa_verifica.aliases import WorkKey
    from freoa_verifica.verify import MemoryResolver, ResolvedWork, verificar
    r = MemoryResolver()
    r.add(ResolvedWork("w", WorkKey("cvm", "resolucao", "999", 2026), doc, "2026-01-01", "c", "0" * 64,
                       "https://conteudo.cvm.gov.br/x.pdf", "2026-10-18T00:00:00+00:00", False))
    return verificar(citacao, trecho=trecho, resolver=r, persistir=False)


def test_margem_no_meio_do_paragrafo_tambem_bloqueia():
    # Auditor, rodada 8: ressalva repetida na borda, entre partes do mesmo parágrafo.
    linhas = {1: [(600, "RESOLUCAO CVM 999/2026"), (120, "Art. 1o O emissor deve"), (80, "SALVO DISPENSA EXPRESSA,")],
              2: [(600, "divulgar o relatorio."), (120, "Art. 2o O administrador deve"), (80, "SALVO DISPENSA EXPRESSA,")],
              3: [(600, "publicar o balanco."), (120, "Art. 3o O auditor deve"), (80, "SALVO DISPENSA EXPRESSA,")],
              4: [(600, "emitir o parecer.")]}
    doc = parse_pdf_direto(_pdf([linhas[n] for n in (1, 2, 3, 4)]))
    res = _verificar(doc, "art. 1 da Resolução CVM 999/2026", "O emissor deve divulgar o relatorio.")
    assert (res.text.status, res.text.reason_code) == ("unknown", "MARGEM_ADJACENTE")


def test_margem_adjacente_impede_verified_pelo_verificador_real():
    # Auditor, rodada 7: a issue precisa impedir o positivo no confronto, não só existir.
    pags = [[(800, "COMISSAO DE VALORES MOBILIARIOS")] + ([(600, "RESOLUCAO CVM 999/2026")] if n == 1 else [])
            + [(120, f"Art. {n}o A divulgacao e obrigatoria."), (80, "EXCETO PARA EMISSORES DISPENSADOS.")] for n in (1, 2, 3)]
    doc = parse_pdf_direto(_pdf(pags))
    for trecho in ("A divulgacao e obrigatoria.", "A divulgacao e obrigatoria. EXCETO PARA EMISSORES DISPENSADOS."):
        res = _verificar(doc, "art. 1 da Resolução CVM 999/2026", trecho)
        assert (res.text.status, res.text.reason_code) == ("unknown", "MARGEM_ADJACENTE")
