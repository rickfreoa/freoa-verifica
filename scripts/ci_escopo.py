"""CI em camadas: decide se um PR só toca registros (`docs/decisoes/`, `docs/auditoria/`).

Escreve `so_registro=true|false` em `$GITHUB_OUTPUT`. Fora de `pull_request` (push na `main`, release por
`workflow_call`) a resposta é sempre `false`: matriz completa. Na dúvida também `false`; erro do `git` derruba o job,
e a condição do job `test` em `ci.yml` roda a matriz quando este job não responde `true`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import PurePosixPath

PREFIXOS = ("docs/decisoes/", "docs/auditoria/")
SUFIXOS = (".md", ".json", ".jsonl")


def so_registro(arquivos: list[str]) -> bool:
    arquivos = [a for a in arquivos if a]
    if not arquivos:
        return False
    for a in arquivos:
        p = PurePosixPath(a)
        if "\\" in a or p.is_absolute() or ".." in p.parts:
            return False
        if not a.startswith(PREFIXOS) or p.suffix not in SUFIXOS:
            return False
    return True


def decidir(evento: str, base: str, cabeca: str) -> bool:
    if evento != "pull_request" or not base or not cabeca:
        return False
    saida = subprocess.run(["git", "diff", "--name-only", "--no-renames", "-z", f"{base}...{cabeca}"],  # noqa: S603, S607
                           capture_output=True, check=True).stdout
    return so_registro(saida.decode("utf-8").split("\0"))


def main() -> int:
    resultado = decidir(os.environ.get("EVENTO", ""), os.environ.get("BASE", ""), os.environ.get("CABECA", ""))
    linha = f"so_registro={'true' if resultado else 'false'}"
    print(linha)
    destino = os.environ.get("GITHUB_OUTPUT")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
