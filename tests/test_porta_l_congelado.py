"""IL.1: conjunto de desenvolvimento e validador da Porta L congelados por hash (il1-congelamento.md)."""

import hashlib
import json
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DEV = RAIZ / "tests" / "porta_l" / "desenvolvimento.jsonl"
VALIDADOR = RAIZ / "scripts" / "validar_gabaritos_porta_l.py"
SHA_DEV = "002de92da820bd2e04650a64535ba1ebd9621c83f179fab901bb93266e88ece2"
SHA_VALIDADOR = "3738e0d27a34bb408ff3c8ff46e1a3a9519fa7eba70501845ddd1793bc2713ba"
SHA_RESERVA = "95641f93c97218a9e48c3efce7aedf28363dfe7b8d6508702a82adfd5e6f1358"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_desenvolvimento_congelado():
    assert _sha(DEV) == SHA_DEV


def test_validador_congelado():
    assert _sha(VALIDADOR) == SHA_VALIDADOR


def test_reserva_registrada_no_documento():
    doc = (RAIZ / "docs" / "auditoria" / "1.4.0" / "il1-congelamento.md").read_text(encoding="utf-8")
    assert SHA_RESERVA in doc and SHA_DEV in doc and SHA_VALIDADOR in doc


def test_forma_do_desenvolvimento():
    casos = [json.loads(linha) for linha in DEV.read_text(encoding="utf-8").splitlines() if linha.strip()]
    assert len(casos) == 40
    assert Counter(c["capacidade"] for c in casos) == {"a": 8, "b": 8, "c": 8, "d": 8, "e": 8}
    assert all(c["conjunto"] == "desenvolvimento" for c in casos)
    tipos_c = Counter(c["gabarito"]["tipo"] for c in casos if c["capacidade"] == "c")
    assert tipos_c["verificado_para_D"] >= 4
    assert all(c["gabarito"].get("fonte_oficial", {}).get("sha256") for c in casos)
