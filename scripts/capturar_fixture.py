"""Captura reproduzível de uma consulta oficial como fixture (`captura_real`) ou sonda fora do repositório.

Exemplo:
    python scripts/capturar_fixture.py --conector tjdft --chave tjdft_x \\
        --consulta '{"query":"acordo de acionistas","pagina":1,"tamanho":10}'
    python scripts/capturar_fixture.py --conector tjsp --sonda --saida C:/tmp/sonda --chave s1 \\
        --consulta '{"termo":"acordo de acionistas","pagina":1}'
    python scripts/capturar_fixture.py --conector stf --sonda --saida C:/tmp/sonda --chave s2 \\
        --url https://portal.stf.jus.br/robots.txt --user-agent identificado
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from freoa_verifica.captura import UA_MODOS, capturar, registrar_fixture
from freoa_verifica.connectors.base import registry

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--conector", required=True, choices=sorted(registry()))
    alvo = ap.add_mutually_exclusive_group(required=True)
    alvo.add_argument("--consulta", help='JSON da consulta: tjdft {"query","pagina","tamanho","extras"}; tjsp {"termo","pagina"}')
    alvo.add_argument("--url", help="GET simples; a URL deve estar na allowlist do conector")
    ap.add_argument("--chave", help="chave da fixture (obrigatória sem --sonda)")
    ap.add_argument("--sonda", action="store_true", help="grava fora do repositório; não toca o manifesto")
    ap.add_argument("--saida", type=Path, help="diretório da sonda (obrigatório com --sonda)")
    ap.add_argument("--user-agent", dest="user_agent", choices=UA_MODOS, default="conector")
    args = ap.parse_args(argv)
    try:
        consulta = None
        if args.consulta is not None:
            consulta = json.loads(args.consulta)
            if not isinstance(consulta, dict):
                raise ValueError("a consulta deve ser um objeto JSON")
        comum = {"url": args.url, "user_agent": args.user_agent, "chave": args.chave}
        if args.sonda:
            if args.saida is None:
                ap.error("--sonda exige --saida")
            saida = args.saida.resolve()
            if saida == REPO or REPO in saida.parents:
                ap.error("--saida deve ficar fora do repositório")
            reg = capturar(args.conector, consulta, destino=saida, sonda=True, **comum)
        else:
            if not args.chave:
                ap.error("sem --sonda, --chave é obrigatória")
            with tempfile.TemporaryDirectory() as tmp:
                reg = capturar(args.conector, consulta, destino=Path(tmp), sonda=False, **comum)
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
