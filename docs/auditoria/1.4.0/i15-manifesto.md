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

## Rodada 3 (correções do parecer r2, última pelo D5)

Parecer r2: COM BLOQUEADOR (B1, B2, mais importantes e menores). Ambiente: o mesmo da rodada 2 (venv do worktree,
sem `PYTHONPATH`, ruff 0.17.1 do `.venv` do worktree).

| Achado | Correção |
|---|---|
| B1 | `bateria_live` (etapas 2 e 8) exige `relatorio` com `sha256` (calculado pelo `registrar`, reconferido no `validar`), `commit`, `aprovados`, `xfail`, `falhas` (inteiros >= 0), `escopo` (lista não vazia), `ambiente` (`so`, `python`, `pais_ip`), `saude_fontes` com `saude_fontes_sha256` e `falhas_fora_do_escopo` (`teste`, `motivo`, `registro` existente). Regras: `aprovados + xfail >= 1`; `falhas` igual a `len(falhas_fora_do_escopo)`; nenhuma fonte do `escopo` em `falhas_fora_do_escopo`. O `validar` lê o `saude-fontes.json` (formato de `tests/live/conftest.py`: `completa` e `fontes[f].testes[]`) e exige `completa: true`, toda `regressao` listada em `falhas_fora_do_escopo` e categoria não nula em `unavailable`. `run_ci` exige `jobs` com exatamente lint, repositorio e as oito combinações `test (SO, Python)`, todas `success`. O contrato MCP (`tests/contrato`) é parte da suíte e fica coberto pelos jobs `test`; não é job à parte. |
| B2 | `CATALOGO_PLANO` (seção 6 do plano): cada incremento tem exatamente os itens do catálogo, nem menos nem mais; incremento fora do catálogo também reprova. A retirada só vale pelo procedimento de redução ou adiamento (item mantido com estado e entrada em `reducoes_de_escopo`). |
| Snapshot | `snapshot.sha256` virou `pacotes` (lista de `{nome, sha256}`, ao menos um: núcleo e um por tribunal, seção 4 do plano); `instalacao.digest_snapshot` virou `digests`, igual ao conjunto dos sha256 dos pacotes. |
| Regra 8 | `docs/decisoes/0068-manifesto-de-aceite.md`. |
| Menores | Nota do I2.6 no manifesto: "segmentação tipada e ligação das íntegras do STJ ao acervo; I1.2 adiado inteiro para cá (docs/auditoria/1.4.0/pr10-adiamento.md)". No plano, a linha do I1.2 da tabela do I1 ganhou o sufixo de adiamento para o I2.6 em 28/10/2026; nada mais foi alterado no plano. |

Decisões de implementação a ratificar:

- O plano lista I2.1 a I2.5 na tabela do I2; o catálogo inclui o I2.6 porque o manifesto (e o adiamento do I1.2) já o traz. Um teste confere que todo ID da seção 6 está no catálogo e que a diferença é só o I2.6.
- Nomes de job no formato do GitHub para matriz: `test (ubuntu-latest, 3.11)`.
- Fonte de um teste live: nome do arquivo sem `test_live_` (mesma regra do `conftest.py`), para decidir se uma falha é do escopo.
- Na CLI, listas acumulam por ocorrência (`jobs=nome=conclusao`, `pacotes=nome=sha256`, `falhas_fora_do_escopo=teste|motivo|registro`) e o ambiente vem em `ambiente.so`, `ambiente.python`, `ambiente.pais_ip`.

Verificação (rodada 3):

- Testes do módulo e das fixtures do manifesto: 352 passed. Os cenários do parecer (relatório "BATERIA NAO EXECUTADA"; itens removidos e `itens: []`; recibo só com caminho e commit; `run_ci` sem `jobs`) estão reproduzidos e falham no `validar` e no `fechar`; há um teste por regra nova.
- Ruff (`scripts/ruff_catraca.py` e `ruff check` nos dois arquivos): sem achado. `git diff --check`: limpo. `validar` no manifesto do repositório: válido.
- Suíte offline completa, `pytest tests -q -m "not live"`: 7314 passed, 9 skipped, 34 deselected, em 870 s (sem falhas).
- Pendente de CI: matriz Windows e Python 3.11 a 3.14.

## Redução de escopo (pós-r3)

Redução de escopo pelo D5 em 28/10/2026, após três rodadas COM BLOQUEADOR; registro em `docs/auditoria/1.4.0/i15-reducao-escopo.md` e decisão 0068 reescrita.

- O manifesto deixa de pretender validar o CONTEÚDO da bateria live e do ambiente. A conferência material passa ao auditor, por recibo de parecer, como na 1.3.0.
- `bateria_live` (etapas 2 e 8): `relatorio`, `saude_fontes` (sha256 calculado pelo `registrar`, reconferido no `validar`), `commit` e `parecer_bateria` (com `parecer_bateria_sha256`), parecer local terminado em `SEM BLOQUEADOR`. Removidos: `aprovados`, `xfail`, `falhas`, `escopo`, `ambiente`, `falhas_fora_do_escopo` e a leitura do `saude-fontes.json`.
- `instalacao` (etapa 7): campos anteriores mais `parecer_instalacao` (com `parecer_instalacao_sha256`). `doctor` mantém `ok` e `alertas`.
- `snapshot.pacotes`: lista com ao menos um pacote e digests; nada além disso é afirmado.
- Os bloqueadores B1 e B2 da r3 e os importantes (ambiente, redação da 0068) deixam de ser regra do validar: sem `parecer_bateria` válido (ausente, inexistente, hash errado, COM BLOQUEADOR) o fechamento é recusado, mesmo com relatório "BATERIA NAO EXECUTADA" e saúde vazia.
- Passe final independente a seguir; com bloqueador, o I1.5 é adiado e o I1 não fecha pela seção 5 até nova versão.
