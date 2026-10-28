# I1.5: manifesto de aceite (release/acceptance_manifest.json)

Ferramenta: `scripts/manifesto_aceite.py` (só stdlib), subcomandos `validar`, `registrar`, `item`, `reducao`, `rotulo`, `fechar`; schema documental em `release/acceptance_manifest.schema.json`; testes em `tests/test_manifesto_aceite.py` (62 casos).
Modelo efetivo: claude-haiku-5-5 (Claude Haiku 5.5), agente implementador, sem revisão de auditor ainda.
Base: `origin/main` 6a21865. Commit de código: `0c134c7` (`release: manifesto de aceite do plano 1.4.0 (I1.5)`). Este registro está no commit seguinte, de documentação.
Ambiente: Python 3.13.18 do venv compartilhado, ruff 0.17.1, pytest 9.1.1; `PYTHONPATH=.` a partir do worktree.

Comandos e resultado:

- `PYTHONPATH=. .venv/bin/python -m pytest tests/test_manifesto_aceite.py -q`: 62 passed.
- `PYTHONPATH=. .venv/bin/python scripts/ruff_catraca.py`: sem achado novo (saída de sucesso, código 0).
- `ruff check` nos arquivos novos: All checks passed.
- `git diff --check`: sem saída (código 0).
- `PYTHONPATH=. .venv/bin/python scripts/manifesto_aceite.py validar`: manifesto válido, 4 incrementos, 2 exceções.
- Suíte offline completa, `pytest tests -q -m "not live"` (sem `-x`): 2 falhas, 7038 passed, 9 skipped, 34 deselected, em 899 s.
  - `tests/test_120_isolamento_conectores.py::test_diretorio_corrente_nao_entra_no_path_do_filho`: falha.
  - `tests/test_selecao_wheel.py::test_selecao_ancorada_em_arquivo_roda_na_copia_isolada`: falha; a execução interna reproduz a falha anterior.
  - Ambas passam sem `PYTHONPATH` (`env -u PYTHONPATH`). A causa é o `PYTHONPATH=.` herdado pelos subprocessos: o teste planta um `pypdf.py` no diretório corrente e verifica que o filho não o importa, mas o `.` do `PYTHONPATH` põe esse diretório no caminho do filho. Nenhum arquivo de `freoa_verifica/` foi alterado.

Limitações:

- A suíte não está verde no ambiente de comum.md: as duas falhas acima persistem com `PYTHONPATH=.`. Sem `PYTHONPATH`, o import resolve o checkout principal (instalação editável), não este worktree, então não há rodada limpa sem ele.
- O manifesto não confere o sha256 informado contra o arquivo local do parecer; só a última linha é verificada.
- A interpretação de "salvo nota de nao_aplicavel" para pypi é: a nota da etapa 5 declara pypi não aplicável.
- Os testes do módulo são `repositorio`, porque o script fica em `scripts/`, fora da wheel; por isso não rodam no job da wheel.
- O manifesto inicial foi gerado por um script de uma linha, não pela própria ferramenta.
- Ruff, matriz Windows e 3.11 a 3.14 não foram executados aqui; ficam para o CI após o push.
