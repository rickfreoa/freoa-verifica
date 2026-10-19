"""Executa o FREOA Verifica sobre um conjunto-ouro e grava a saída condensada para comparação.

Uso: python scripts/comparativo_ouro.py gold.jsonl saida.jsonl
Não julga: só registra o que o produto respondeu (top-5, status, identidade, situação). O julgamento é
feito depois, contra a resposta fixada pela fonte oficial no próprio conjunto-ouro.
"""
from __future__ import annotations

import json
import sys
import time

from freoa_verifica.service import Verifica

_TIPOS_VERIFICACAO = {"dispositivo", "norma", "sumula", "inexistente"}


def _item(i: dict) -> dict:
    return {k: i.get(k) for k in ("id", "tribunal", "classe_numero", "orgao", "relator", "datas", "url_oficial",
                                  "nivel_prova", "pertinencia", "correspondencia", "capture_id")} | {
        "autoridade": (i.get("autoridade") or {}).get("label") if isinstance(i.get("autoridade"), dict) else i.get("autoridade"),
        "ementa": (i.get("ementa") or "")[:400],
        "texto_exibido": (i.get("ementa") or i.get("trecho_inteiro_teor") or "")[:400],
    }


def _verificacao(r: dict) -> dict:
    dims = {}
    for d in ("identity", "text", "temporal", "support"):
        v = r.get(d) or {}
        ev = (v.get("evidence") or [{}])[0] if isinstance(v, dict) else {}
        dims[d] = {"status": v.get("status"), "reason_code": v.get("reason_code"),
                   "url": (ev or {}).get("url"), "trecho": str((ev or {}).get("text") or (ev or {}).get("trecho") or "")[:300]}
    return {"dimensoes": dims, "citation": r.get("citation"), "status": r.get("status")}


def main(gold: str, saida: str) -> None:
    casos = [json.loads(line) for line in open(gold, encoding="utf-8") if line.strip()]
    with Verifica() as svc, open(saida, "w", encoding="utf-8") as out:
        for c in casos:
            q = c["consulta"]
            reg = {"id": c["id"], "estrato": c.get("estrato"), "tipo": c.get("tipo"), "consulta": q}
            t0 = time.monotonic()
            try:
                if c.get("tipo") in _TIPOS_VERIFICACAO:
                    reg["verificacao"] = _verificacao(svc.verificar_citacao(q))
                if c.get("tipo") in {"decisao_numero", "decisao_tema", "sumula", "inexistente"}:
                    r = svc.pesquisar_jurisprudencia(q, limite=5)
                    reg["juris"] = {"status": r.get("status"), "motivo": r.get("motivo"),
                                    "modo_busca": r.get("modo_busca"),
                                    "top5": [_item(i) for i in (r.get("itens") or [])[:5]],
                                    "fontes": r.get("fontes")}
            except Exception as exc:  # noqa: BLE001 — registrar e seguir; o julgamento decide
                reg["erro"] = repr(exc)[:300]
            reg["segundos"] = round(time.monotonic() - t0, 2)
            out.write(json.dumps(reg, ensure_ascii=False, default=str) + "\n")
            out.flush()
            print(c["id"], reg.get("verificacao", {}).get("status"), (reg.get("juris") or {}).get("status"),
                  len((reg.get("juris") or {}).get("top5") or []), reg.get("erro", ""), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
