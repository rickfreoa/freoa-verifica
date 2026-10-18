"""1.1.0: bench confronta toda dimensão declarada; indisponibilidade não é acerto (auditoria, rodada 2)."""
import json

import pytest

from freoa_verifica.bench import run_bench


class _Svc:
    def __init__(self, identity, text, temporal=None):
        self.r = {"identity": {"status": identity}, "text": {"status": text}, "temporal": {"status": temporal}}

    def verificar_citacao(self, citacao, trecho=None, data=None):
        return self.r

    def verificar_texto(self, texto):
        return {"citacoes": []}


@pytest.mark.parametrize("resp,caso,ok", [
    (("verified", "unavailable"), {"tipo": "mutante", "trecho": "x"}, False),
    (("verified", "unavailable"), {"tipo": "mutante", "trecho": "x", "expectativa": {"identity": "verified"}}, False),
    (("verified", "unavailable"), {"tipo": "mutante", "trecho": "x", "expectativa": {"identity": "not_found"}}, False),
    (("verified", "unavailable"), {"tipo": "mutante", "trecho": "x", "expectativa": {"text": "unavailable"}}, True),
    (("verified", "divergent"), {"tipo": "mutante", "trecho": "x", "expectativa": {"motivo": "troca"}}, True),
    (("unavailable", None), {"tipo": "mutante"}, False),
    (("verified", "verified", "unknown"), {"tipo": "positivo", "trecho": "x", "expectativa": {"temporal": "divergent"}}, False),
])
def test_avaliacao(tmp_path, resp, caso, ok):
    caso = {"id": "c", "citacao": "Lei 1/2000, art. 1", **caso}
    p = tmp_path / "gold.jsonl"
    p.write_text(json.dumps(caso), encoding="utf-8")
    rel = run_bench(_Svc(*resp), p)
    assert json.dumps(rel).count('"ok": true') == (1 if ok else 0), rel
