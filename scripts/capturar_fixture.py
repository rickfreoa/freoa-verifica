"""Captura reproduzível de uma consulta oficial como fixture (`captura_real`) ou sonda fora do repositório.

Exemplo:
    python scripts/capturar_fixture.py --conector tjdft --chave tjdft_x \\
        --consulta '{"query":"acordo de acionistas","pagina":1,"tamanho":10}'
    python scripts/capturar_fixture.py --conector tjdft --sonda --saida C:/tmp/sonda \\
        --user-agent identificado --consulta '{"query":"..."}'
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from freoa_verifica.captura import UA_MODOS, capturar, registrar_fixture

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--conector", required=True, choices=["tjdft"])
    ap.add_argument("--consulta", required=True, help='JSON: {"query","pagina","tamanho","extras"}')
    ap.add_argument("--chave", help="chave da fixture (obrigatória sem --sonda)")
    ap.add_argument("--sonda", action="store_true", help="grava fora do repositório; não toca o manifesto")
    ap.add_argument("--saida", type=Path, help="diretório da sonda (obrigatório com --sonda)")
    ap.add_argument("--user-agent", dest="user_agent", choices=UA_MODOS, default="conector")
    args = ap.parse_args(argv)
    try:
        consulta = json.loads(args.consulta)
        if not isinstance(consulta, dict):
            raise ValueError("a consulta deve ser um objeto JSON")
        if args.sonda:
            if args.saida is None:
                ap.error("--sonda exige --saida")
            if REPO in args.saida.resolve().parents:
                ap.error("--saida deve ficar fora do repositório")
            reg = capturar(args.conector, consulta, destino=args.saida, sonda=True, user_agent=args.user_agent,
                           chave=args.chave)
        else:
            if not args.chave:
                ap.error("sem --sonda, --chave é obrigatória")
            with tempfile.TemporaryDirectory() as tmp:
                reg = capturar(args.conector, consulta, destino=Path(tmp), sonda=False,
                               user_agent=args.user_agent, chave=args.chave)
                if not reg.unavailable:
                    registrar_fixture(reg, args.chave, FIXTURES)
    except ValueError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    if reg.unavailable:
        print(f"unavailable({reg.motivo})", file=sys.stderr)
        return 1
    print(f"{reg.status} {reg.bytes} bytes sha256={reg.sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
