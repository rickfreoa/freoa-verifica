"""Extrai do CHANGELOG a seção de uma versão, para as notas da release (só biblioteca padrão).

Uso: python scripts/notas_da_versao.py <tag-ou-versão> [CHANGELOG.md] [saida.md]

A seção vai do cabeçalho "## <versão>" até o próximo "## " (ou o fim do arquivo). Sem a seção, ou com
seção vazia, sai com código 1: a release não publica o histórico inteiro no lugar das notas.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def notas_da_versao(changelog: str, versao: str) -> str:
    versao = versao.strip().removeprefix("v")
    cabecalho = re.compile(rf"##[ \t]+{re.escape(versao)}(?:[ \t].*)?")
    linhas = changelog.lstrip("﻿").splitlines()
    inicio = next((i for i, linha in enumerate(linhas) if cabecalho.fullmatch(linha.rstrip())), None)
    if inicio is None:
        raise LookupError(f"seção da versão {versao} ausente no CHANGELOG")
    fim = next((i for i in range(inicio + 1, len(linhas)) if linhas[i].startswith("## ")), len(linhas))
    corpo = "\n".join(linhas[inicio:fim]).strip()
    if not corpo.partition("\n")[2].strip():
        raise LookupError(f"seção da versão {versao} vazia no CHANGELOG")
    return corpo + "\n"


def main(argv: list[str]) -> int:
    if not 1 <= len(argv) <= 3:
        print(__doc__, file=sys.stderr)
        return 2
    changelog = Path(argv[1] if len(argv) > 1 else "CHANGELOG.md")
    try:
        texto = notas_da_versao(changelog.read_text(encoding="utf-8"), argv[0])
    except (LookupError, OSError) as exc:
        print(f"notas_da_versao: {exc}", file=sys.stderr)
        return 1
    if len(argv) > 2:
        Path(argv[2]).write_text(texto, encoding="utf-8")
    else:
        sys.stdout.write(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
