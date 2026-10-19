# 0050 — CI travado por hashes e PyPI só depois da publicação da release

Data: 19/10/2026 · Versão: 1.3.0 · Origem: plano 1.3.0 (G1, G3, D2)

## Contexto

O CI instalava dependências sem trava (`pip install wheel[test,server]`), a matriz não cobria o
Python 3.14, nada impedia mascarar um gate com `continue-on-error`/`|| true`, e o job `pypi` do
`release.yml` publicava a partir do artefato do build, antes de qualquer auditoria dos bytes da release.

## Decisão

1. Dependências do CI vêm de `requirements/ci.lock` (extras `test` e `server`, universal, com hashes) e as
   de build de `requirements/build.lock`; ambos instalados com `--require-hashes`; a wheel entra com
   `--no-deps`. O Ruff vem de `requirements/lint.lock`. `scripts/atualizar_lock.{sh,ps1}` regeram os locks.
2. Matriz: Python 3.11–3.14 em Ubuntu e Windows. Testes que leem o checkout levam
   `@pytest.mark.repositorio`: rodam no job `repositorio` e ficam fora do job da wheel instalada.
3. Ruff (`E9`, `F`, `S`, `BLE`, `TRY`) com `ruff-baseline.json` e `scripts/ruff_catraca.py`: achado novo, ou
   antigo que volte além da contagem registrada, reprova o job `lint`. O código existente não é corrigido em massa.
4. `tests/test_workflows.py` reprova `continue-on-error` diferente de `false` e `|| true`/`|| :`/`|| exit 0`.
   Exceção só com `# gate-nao-bloqueante: <motivo>` na mesma linha.
5. `release.yml` cria a release como rascunho e não publica na PyPI. `pypi.yml`, disparado por
   `release: published`, baixa os assets da própria release, confere `SHA256SUMS` e a attestation, exige uma
   wheel e um sdist (sem `tests/` na wheel) e publica esses bytes por Trusted Publishing, só com
   `vars.PYPI_PUBLICAR == 'true'`.

## Consequências

- O publicador pendente em pypi.org passa a apontar para o workflow `pypi.yml`, não `release.yml`.
- Semgrep segue adiado.
