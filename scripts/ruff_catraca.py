"""Catraca do Ruff: reprova achado novo ou que volte em relação a ruff-baseline.json.

A chave do achado é (arquivo, regra, mensagem), sem número de linha, para que
edições vizinhas não invalidem a baseline. Uma chave não pode passar da contagem
registrada; achado resolvido sai da baseline com --atualizar.

Uso:
    python scripts/ruff_catraca.py              # confere
    python scripts/ruff_catraca.py --atualizar  # regrava a baseline (só para reduzi-la)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BASELINE = RAIZ / "ruff-baseline.json"


def contar(achados: list[dict]) -> Counter:
    chaves: Counter = Counter()
    for a in achados:
        arquivo = Path(a["filename"]).resolve().relative_to(RAIZ).as_posix()
        chaves[(arquivo, a["code"], a["message"])] += 1
    return chaves


def excedentes(atual: Counter, base: Counter) -> list[str]:
    """Achados novos ou repetidos além da contagem da baseline."""
    return [
        f"{arquivo}: {regra} {msg} (baseline {base.get(chave, 0)}, agora {n})"
        for chave, n in sorted(atual.items())
        if n > base.get(chave, 0)
        for arquivo, regra, msg in [chave]
    ]


def carregar_baseline() -> Counter:
    dados = json.loads(BASELINE.read_text(encoding="utf-8"))
    return Counter({(d["arquivo"], d["regra"], d["mensagem"]): d["n"] for d in dados})


def rodar_ruff() -> list[dict]:
    p = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--output-format=json", "--no-cache", str(RAIZ)],
        capture_output=True, text=True, cwd=RAIZ,
    )
    if p.returncode not in (0, 1):  # 1 = há achados; outro valor = o Ruff falhou
        sys.exit(f"ruff falhou ({p.returncode}): {p.stderr.strip()}")
    return json.loads(p.stdout or "[]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--atualizar", action="store_true")
    args = ap.parse_args()
    atual = contar(rodar_ruff())
    if args.atualizar:
        linhas = [{"arquivo": a, "regra": r, "mensagem": m, "n": n} for (a, r, m), n in sorted(atual.items())]
        BASELINE.write_text(json.dumps(linhas, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"baseline gravada: {sum(atual.values())} achados em {len(linhas)} chaves")
        return 0
    excesso = excedentes(atual, carregar_baseline())
    for linha in excesso:
        print("NOVO:", linha)
    return 1 if excesso else 0


if __name__ == "__main__":
    sys.exit(main())
