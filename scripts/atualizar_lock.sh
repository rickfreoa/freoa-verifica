#!/usr/bin/env sh
# Regenera os locks com hashes usados pelo CI (instalação com --require-hashes).
# Requer uv (https://docs.astral.sh/uv/). Rodar na raiz do repositório e commitar o resultado.
set -eu
cd "$(dirname "$0")/.."
uv pip compile pyproject.toml --universal --generate-hashes --extra test --extra server \
  -o requirements/ci.lock --python-version 3.11
uv pip compile requirements/build.in --universal --generate-hashes \
  -o requirements/build.lock --python-version 3.11
uv pip compile requirements/lint.in --universal --generate-hashes \
  -o requirements/lint.lock --python-version 3.11
