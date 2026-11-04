"""IL.1: matriz, validador e conjunto de desenvolvimento da Porta L congelados por hash (il1-congelamento.md).

O validador e seus testes ficam em scripts/porta_l (dependem de pypdf, fora do lock da CI); aqui se confere só
que os bytes congelados não mudaram e a forma mínima do conjunto de desenvolvimento.
"""

import hashlib
import json
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PL = RAIZ / "tests" / "porta_l"
DOC = RAIZ / "docs" / "auditoria" / "1.4.0" / "il1-congelamento.md"

CONGELADOS = {
    RAIZ / "docs" / "auditoria" / "1.4.0" / "il1-matriz-porta-l.md": "7455870927a3d530f2aa224399eba5b9b71530eb4026f044aca4814af11539dd",
    RAIZ / "scripts" / "porta_l" / "validar_gabaritos_porta_l.py": "3d73de90df476c699e158e812bb381f7a38ecbfe52e328fe3fb021451ffbfcda",
    RAIZ / "scripts" / "porta_l" / "test_validador.py": "8e377a2ec29cbf6ed1f4f4f251978bf5c2643a1d22b9250b3be9f6ed24e12517",
    PL / "desenvolvimento.jsonl": "2fb75d158f197a474e753796e2d621ba67f5200413ef0121daeb5ae6873517b1",
    PL / "mutantes.jsonl": "1f791fc1479d1a9d308b748a022adb69b8738435e5a87d37385f56f301e6afd3",
    PL / "cobertura.json": "7ae9e8d5b9507c44ac43eee9666adfa610cdc2916720bb467025fcaf42b1e7bb",
    PL / "desenvolvimento-fontes.csv": "e18389fda7b8d8fa43fca26ef6942eba020b7bc560e54bdc66bd71fa936bd38e",
}

RESERVA = {
    "reserva.jsonl": "b16fe24e81ff5d5756d048d1e654db67bc23aa90ae4a7456bc9f6ead55ac8774",
    "mutantes.jsonl": "8ddbbdaf0874a05d718869019ecff03bb359af6d2e73765efbbf556bd974f6e0",
    "cobertura.json": "f6cdbc919bad06c726d8259b6ffef61ed6f262b4e757a0fe7688b54cf0c1d939",
}


def _sha(p: Path) -> str:
    # Bytes exatos: .gitattributes marca tests/porta_l e scripts/porta_l como -text.
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_bytes_congelados():
    divergentes = {str(p.relative_to(RAIZ)): _sha(p) for p, h in CONGELADOS.items() if _sha(p) != h}
    assert divergentes == {}


def test_hashes_registrados_no_documento():
    doc = DOC.read_text(encoding="utf-8")
    faltam = [h for h in list(CONGELADOS.values()) + list(RESERVA.values()) if h not in doc]
    assert faltam == []


def test_forma_do_desenvolvimento():
    casos = [json.loads(l) for l in (PL / "desenvolvimento.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(casos) >= 40
    assert all(c["conjunto"] == "desenvolvimento" for c in casos)
    assert len({c["id"] for c in casos}) == len(casos)
    por_cap = Counter(c["capacidade"] for c in casos)
    assert set(por_cap) == {"a", "b", "c", "d", "e"} and min(por_cap.values()) >= 8
    assert all(c["gabarito"].get("fonte_oficial", {}).get("sha256") for c in casos)
    mutantes = [json.loads(l) for l in (PL / "mutantes.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert mutantes
