# I1.5: manifesto de aceite (release/acceptance_manifest.json)

Ferramenta: `scripts/manifesto_aceite.py` (só stdlib), subcomandos `validar`, `registrar`, `item`, `reducao`, `rotulo`, `fechar`; schema documental em `release/acceptance_manifest.schema.json`; testes em `tests/test_manifesto_aceite.py`.
Base: `origin/main` 6a21865. Ramo `feat/manifesto-aceite`.

## Limite do manifesto

O manifesto registra recibos tipados por etapa e confere a coerência entre eles: formatos (commit de 40 hex, sha256 de 64 hex, URLs do repositório, tag), igualdades entre etapas (commit testado, commitado e auditado; merge, tag, instalação e bateria da etapa 8; bytes da release iguais aos da PyPI; digest do snapshot), existência de arquivos dentro do repositório e o parecer lido do disco. Ele não consulta o GitHub nem a PyPI. A conferência material é do auditor: que o run existe e passou, que a release e a attestation são reais e que o pacote publicado tem aqueles bytes.

## Rodada 1 (commits `0c134c7` código, `9a4bcd6` este registro)

Modelo efetivo: claude-haiku-5-5 (Claude Haiku 5.5), agente implementador. Python 3.13.18 do venv compartilhado, ruff 0.17.1, pytest 9.1.1, com `PYTHONPATH=.`.

- Testes do módulo: 62 passed. Ruff (`scripts/ruff_catraca.py`): sem achado novo. `git diff --check`: limpo. `validar` no manifesto do repositório: válido.
- Suíte offline completa: 2 falhas, 7038 passed, 9 skipped, 34 deselected, em 899 s. As falhas (`test_diretorio_corrente_nao_entra_no_path_do_filho` e `test_selecao_ancorada_em_arquivo_roda_na_copia_isolada`) vinham do `PYTHONPATH=.` herdado pelos subprocessos; passavam sem ele. Nenhum arquivo de `freoa_verifica/` foi alterado.
- Pendente de CI, não executado na rodada: matriz Windows e Python 3.11 a 3.14.

Parecer do Codex sobre a rodada 1: COM BLOQUEADOR (B1 a B5, I1, I2, M1 a M3), tratado abaixo. Correção deste registro (M2): a versão anterior dizia que o Ruff passou e, mais abaixo, que o Ruff não foi executado; o Ruff foi executado (catraca, sem achado novo) e só a matriz Windows e 3.11 a 3.14 ficaram para o CI.

## Rodada 2 (correções do parecer r1)

Ambiente: venv próprio do worktree (`/home/claude/venv-manifesto`, instalação editável deste worktree, sem `PYTHONPATH`); ruff 0.17.1 do `.venv` do worktree (mesma versão do `requirements/lint.lock`), porque o venv novo não tinha ruff e a instalação exigiria rede.

| Achado | Correção |
|---|---|
| B1 | `nao_aplicavel` deixou de existir como estado de etapa (esquema, código, testes, documentação). O incremento só fecha com as oito etapas `concluida`. |
| B2 | Parecer só por caminho relativo, existente, dentro do repositório; `registrar` calcula o sha256 dos bytes e `validar` o reconfere; URL não vale. |
| B3 | Recibos estruturados por etapa, com campos tipados obrigatórios e igualdades entre etapas; tipos `outro` e `bench` removidos; sem dispensa da PyPI. A tag deve ainda ser `v` mais a versão do incremento (acréscimo além da especificação). |
| B4 | `fechar` valida o manifesto inteiro sempre, inclusive com o incremento já `concluido`, e sai com 1 se inválido. |
| B5 | Toda redução exige item `reduzido` ou `adiado`, registro existente no repositório e rótulo não nulo; item `reduzido` ou `adiado` exige a entrada. `reducao` passou a marcar item, registro e rótulo numa só escrita. Manifesto inicial: I1.2 `reduzido`, com a redução de 2026-10-28 e o rótulo do I1 definidos pelo supervisor; `docs/auditoria/1.4.0/pr10-reducao-escopo.md` copiado byte a byte de `origin/feat/stj-integras-1.4` (5a0bb1f). |
| I1 | Datas `AAAA-MM-DD`; instantes RFC 3339 completos, com segundos e fuso `Z` ou `±HH:MM` (HH até 23, MM até 59), validados com `datetime`; dígitos só ASCII. |
| I2 | `--manifesto` e todo caminho de recibo confinados à raiz (pai de `scripts/`): absoluto, `..` que escape, UNC, unidade ou fluxo (`:`), nome de dispositivo do Windows e componente terminado em ponto ou espaço recusados antes de qualquer acesso ao sistema de arquivos; depois, symlink que saia da raiz. Os testes apontam a raiz por parâmetro interno (`_raiz`), que a CLI não expõe. |
| M1 | BOM inicial removido, CRLF normalizado e espaços finais descartados antes de ler a última linha não vazia, que deve ser exatamente `SEM BLOQUEADOR`. |
| M2 | Este registro corrigido (Ruff). |
| M3 | TJAP mantém `revisar_em` 2027-01-31 e ganhou `nota`: "data fixada pelo supervisor em 28/10/2026; o D4 exige data de revisão e o plano não a fixa". O campo `nota` passou a existir em toda exceção e é obrigatório quando há `revisar_em`. |

Decisões de implementação a ratificar:

- Cada etapa concluída exige exatamente um recibo de cada tipo da etapa (`merge` na etapa 4 é um recibo próprio, com `commit`); recibo repetido ou de outra etapa é recusado. `registrar` de um tipo já presente na etapa substitui o anterior.
- Na etapa 2, o `commit` de `run_ci` e o de `bateria_live` devem coincidir, e o da etapa 3 deve ser o mesmo.
- Categorias aceitas num alerta do `doctor`: `ambiental_desafio`, `fonte_fora`, `recusa_identificado`, `resposta_inesperada` (as de `CATEGORIAS_INDISPONIBILIDADE` menos `regressao`), no formato `categoria: texto`.
- A estrutura (formatos) é validada antes das regras (arquivos e igualdades); o primeiro conjunto de erros mascara o segundo até ser corrigido.

Verificação (rodada 2):

- Testes do módulo: 223 passed.
- Ruff (`scripts/ruff_catraca.py`) e `ruff check` nos dois arquivos: sem achado. `git diff --check`: limpo.
- Suíte offline completa, `pytest tests -q -m "not live"`: 7201 passed, 9 skipped, 34 deselected, em 865 s (sem falhas; uma primeira execução teve 1 falha, a asserção textual deste próprio documento, corrigida antes da reexecução).
- Os testes de bloqueador reproduzem o cenário do parecer e foram executados também contra o código da rodada 1 (reescritos no formato antigo): todos passam o manifesto indevidamente lá e falham aqui (15 cenários reproduzidos no código da rodada 1, com script de cenário não versionado).
- Pendente de CI: matriz Windows e Python 3.11 a 3.14.

## Atualização do supervisor (28/10/2026)

Depois do passe final independente do PR #10 (COM BLOQUEADOR), o I1.2 passou de `reduzido` a `adiado`, com
registro `docs/auditoria/1.4.0/pr10-adiamento.md` (copiado byte a byte de `origin/feat/stj-integras-1.4`,
a9bcf88) e rótulo "1.4.0a1: sem íntegras do STJ; I1.2 adiado para 1.4.0a2 (I2.6) após passe final com
bloqueador". Feito pelos subcomandos `reducao` e `item` do próprio gerador; os dois testes do estado inicial
foram ajustados ao estado de fato.
