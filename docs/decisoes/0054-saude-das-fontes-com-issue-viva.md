# 0054 — Saúde das fontes com issue viva

Data: 19/10/2026 · Versão: 1.3.0 · Origem: marco S3 do plano 1.3.0

## Contexto

O workflow semanal `saude-das-fontes` mascarava o resultado (`continue-on-error` e `|| true`) e só
entregava um XML em artefato. Ninguém era avisado de regressão, e uma execução cancelada ou truncada
era indistinguível de uma execução saudável.

## Decisão

1. `tests/live/conftest.py` grava `saude-fontes.json` ao fim da sessão: `commit`, `inicio`, `fim`,
   `completa` e, por fonte (nome do arquivo `test_live_<fonte>.py`), `estado` (`ok`, `unavailable`,
   `regressao`, `not_run`), `categoria`, `motivo` e a lista de testes. Precedência na fonte:
   `regressao` > `unavailable` > `not_run` > `ok`.
2. `completa` só é verdadeiro se a sessão terminou com `exitstatus` 0 ou 1 e nenhum teste live
   selecionado ficou `not_run` (inclui `skip` comum).
3. `scripts/saude_fontes.py` lê o JSON (e o JUnit como conferência) e, com `--issue`, mantém uma issue
   aberta com o rótulo `saude-das-fontes` por `gh api`. O corpo é reescrito a cada execução (sem
   notificação); comentário só quando o conjunto (fonte, estado, categoria) difere do guardado no corpo
   em `<!-- estado: {...} -->`. A issue é relida imediatamente antes de decidir e escrever; o comentário
   precede a escrita do corpo, para que falha da API não perca o estado anterior.
4. Saídas: 0 ok ou só indisponibilidade ambiental; 1 `regressao` ou `recusa_identificado`; 2 erro do
   script, inclusive da API; 3 execução incompleta (JSON ausente, truncado, `completa` falso ou JUnit com
   falhas que o JSON não registra), sem tocar na issue.
5. O workflow perde `continue-on-error` e `|| true`; o passo do script roda com `if: always()` e o job
   termina com o código dele. Permissões: `issues: write`, `contents: read`.

## Limites

Sem bloqueio de concorrência no GitHub, duas execuções simultâneas ainda têm janela mínima entre a
releitura e a escrita; o pior caso é um comentário duplicado, nunca estado perdido.
