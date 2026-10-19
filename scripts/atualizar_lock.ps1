# Regenera os locks com hashes usados pelo CI (instalação com --require-hashes).
# Requer uv (https://docs.astral.sh/uv/). Rodar de qualquer pasta e commitar o resultado.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
uv pip compile pyproject.toml --universal --generate-hashes --extra test --extra server `
  -o requirements/ci.lock --python-version 3.11
if ($LASTEXITCODE) { exit $LASTEXITCODE }
uv pip compile requirements/build.in --universal --generate-hashes `
  -o requirements/build.lock --python-version 3.11
if ($LASTEXITCODE) { exit $LASTEXITCODE }
uv pip compile requirements/lint.in --universal --generate-hashes `
  -o requirements/lint.lock --python-version 3.11
exit $LASTEXITCODE
