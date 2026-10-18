"""Aceite da v1.0.3 sobre um acervo instalado (casos do comparativo de 18/10/2026).

Uso: python scripts/aceite_1_0_3.py <home> [--com-rede]
Conjunto montado pelo orquestrador a partir das fontes oficiais: NÃO independente.
Sai com código 1 se algum caso falhar. Sem --com-rede, roda com FV_OFFLINE=1.
"""
import json
import os
import sys

if "--com-rede" not in sys.argv:
    os.environ["FV_OFFLINE"] = "1"

from freoa_verifica.service import Verifica  # noqa: E402

svc = Verifica(home=sys.argv[1])
falhas: list[str] = []


def caso(nome, ok, detalhe):
    print(("OK   " if ok else "FALHA"), nome, "|", json.dumps(detalhe, ensure_ascii=False)[:300])
    if not ok:
        falhas.append(nome)


def dims(r):
    return {k: (r.get(k) or {}).get("status") for k in ("identity", "text", "temporal")}


CF60 = "A Constituição poderá ser emendada mediante proposta"
ADCT60 = "Até o 14º (décimo quarto) ano a partir da promulgação desta Emenda Constitucional"

r = svc.verificar_citacao("art. 60 da Constituição Federal", trecho=CF60, modo="normalizado")
caso("CF art. 60, texto permanente verified", dims(r)["text"] == "verified", dims(r))
r = svc.verificar_citacao("art. 60 da Constituição Federal", trecho=ADCT60, modo="normalizado")
caso("CF art. 60 com texto do ADCT não verified", dims(r)["text"] != "verified", dims(r))
r = svc.resolver_citacao("art. 5º do ADCT")
caso("ADCT citável", "adct/" in json.dumps(r), r)

r = svc.verificar_citacao("art. 254-A da Lei 6.404/1976")
caso("LSA art. 254-A existe (controle positivo)", dims(r)["identity"] == "verified", dims(r))
r = svc.verificar_citacao("art. 312 da Lei 6.404/1976")
caso("LSA art. 312 inexistente (negativa legítima)",
     dims(r)["identity"] == "not_found" and (r["identity"].get("reason_code") == "DISPOSITIVO_INEXISTENTE"), dims(r))
r = svc.verificar_citacao("Lei 6.404/1976: art. 117 do contrato")
caso("art. 117 do contrato nunca verified", dims(r)["identity"] != "verified", dims(r))
r = svc.obter_dispositivo(citacao="Lei 6.404/1976: art. 117 do contrato")
caso("art. 117 do contrato sem vigência em obter_dispositivo",
     "vigente_na_fonte" not in json.dumps(r), {"status": r.get("status")})

r = svc.obter_dispositivo(citacao="art. 136 da Lei 6.404/1976", data="2000-01-01")
caso("LSA art. 136 em 2000 sem texto atual como se fosse da data",
     r.get("texto") is None or r.get("redacao_selecionada"), {k: r.get(k) for k in ("status", "motivo")})

for cit in ("art. 1º da Resolução CVM 51/2021", "art. 1º da Resolução CMN 5.238/2025",
            "art. 1º da Resolução CVM 85/2022"):
    r = svc.verificar_citacao(cit)
    caso(f"{cit}: revogada não sai vigente", dims(r)["temporal"] not in ("vigente_na_fonte", "verified"), dims(r))

r = svc.verificar_texto(
    "Nos termos do art. 254-A da Lei 6.404/1976, a oferta é obrigatória. "
    "O art. 117 da mesma lei trata do abuso de poder.")
caso("anáfora declarada como referência não resolvida", "referencia" in json.dumps(r) and "117" in json.dumps(r),
     {k: r.get(k) for k in ("total_detectado", "total_processado", "truncado")})

r = svc.pesquisar_jurisprudencia("REsp 2.210.785")
caso("REsp 2.210.785 achado pelo número", "2210785" in json.dumps(r).replace(".", ""), {"status": r.get("status")})
r = svc.pesquisar_jurisprudencia("REsp 1.736.540")
caso("REsp ausente declarado", r.get("status") == "nao_confirmado_no_acervo" or "nao_confirmado" in json.dumps(r),
     {"status": r.get("status")})

if "--com-rede" in sys.argv:
    for q in ("fato relevante", "oferta pública de aquisição"):
        r = svc.buscar_normas_cvm(q)
        caso(f"CVM '{q}' com resultados", (r.get("total") or 0) > 0, {"total": r.get("total"), "status": r.get("status")})
    r = svc.buscar_normas_bcb("Resolução CMN 4.966")
    caso("BCB lookup exato 4.966", "4966" in json.dumps(r).replace(".", ""), {"total": r.get("total")})

print(f"\n{len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)
