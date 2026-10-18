# Plano v1.0.3 — versão 3 (incorpora O1–O8 e a rodada 2 do auditor)

Fontes: (R1) comparativo FREOA × JusRatio, 24 defeitos; (R2) avaliação de segurança e operação, F01–F10; (A1) parecer do auditor sobre a versão 1 (SEM CONSENSO, objeções O1–O8).
Base: 5d1936f (v1.0.2). AGENTS.md sem exceção.

O orquestrador aceita O1–O8 e as lacunas. Diverge em um ponto: ranking e tesauro (M5, M6, tesauro-1) entram nesta versão porque o mandato é corrigir todos os itens de R1, mas **fora do portão de release** e na forma mínima (pesos bm25, corte de pertinência, OR completando AND escasso, tabela de sinônimos versionada com menos de 30 pares).

## Contratos transversais (fixados pelo orquestrador antes da implementação; dono único)

**C1 — Negativa (dono F-C).** Uma função única `pode_negar(rw, path) -> motivo | None` decide se ausência do caminho autoriza `not_found/DISPOSITIVO_INEXISTENTE`. Autoriza somente quando: obra capturada e autenticada; documento não quarentenado; sem issue de truncamento, extração incompleta ou `DOCUMENTO_SEM_ESTRUTURA` no escopo do caminho (anexo, ADCT ou corpo); a obra tem ao menos um dispositivo estruturado no mesmo escopo. Caso contrário: `unknown` com o motivo (`DOCUMENTO_QUARENTENADO`, `ESTRUTURA_INCOMPLETA`, `DOCUMENTO_SEM_ESTRUTURA`) ou `indisponivel/COBERTURA` quando não há captura. Consumidores obrigatórios: verify.verificar (todos os ramos, inclusive quarentena em verify.py:334), service.lei/obter_dispositivo (812, 885), historico (956), verificar_texto. Teste por consumidor.

**C2 — Situação da obra (dono F-B).** Novo registro `work_status(work_id, situacao ∈ {revogada, cancelada, vigente_declarada, ilegivel}, texto_oficial, ato_revogador, data_efeito|NULL, captura_id, sha256, lido_em)`, alimentado por evidência própria (página do ato CVM; campos `Revogado`/`Cancelado` do BCB/CMN), capturada pelo transporte, sem substituir a captura normativa na seleção da obra (service.py:332–339 continua escolhendo a íntegra). Ausência ou falha de leitura → `ilegivel`, nunca `vigente` (corrige cvm_normas.py:367). Fontes sem situação cadastral (Planalto, Senado) → `nao_aplicavel`, sem efeito algum. Propagação: uma função `aplicar_situacao(temporal_dim, status, data, hoje)` chamada por **todo** consumidor temporal (verify, lei, obter_dispositivo, historico/build_intervals). Regras, sendo D a data consultada (hoje quando omitida):
- revogada/cancelada com `data_efeito` conhecida: D ≥ data_efeito → `revogado OBRA_REVOGADA_NA_FONTE` com texto oficial; D < data_efeito → análise temporal normal preservada, com flag `REVOGACAO_POSTERIOR` (inclui revogação futura: consulta atual antes do efeito não é revogada).
- revogada/cancelada sem `data_efeito`: D = hoje → `revogado OBRA_REVOGADA_NA_FONTE`; D passada → `unknown REVOGACAO_DATA_DESCONHECIDA` quando a análise normal daria vigente/verified; `nao_existia` e `revogado` vindos do próprio texto são preservados.
- `ilegivel` ou `SITUACAO_DESATUALIZADA` (mais de 30 dias sem releitura): rebaixa apenas `vigente_na_fonte`/`verified` temporal para `unknown SITUACAO_INDISPONIVEL`; não altera conclusões sustentadas pelo próprio texto (revogado, nao_existia).
- `vigente_declarada` e `nao_aplicavel`: nada muda (FONTES.md: situação não afirma vigência).
A data do ato revogador nunca vira data de efeito. Identidade documental pode continuar `verified`.

**C3 — Histórico ausente (dono F-C).** Sem redação selecionada para a data pedida, o núcleo não confronta a redação atual: `text=unknown HISTORICO_ANTERIOR_AUSENTE`, e `lei`/`obter_dispositivo` devolvem `texto=null` com `texto_atual` separado e rotulado. Corrige verify.py:474–504 e service.py:889. `redacoes_anteriores` exclui a vigente (M1); primeira redação "Redação dada" marca `redacao_anterior_ausente_na_fonte` (M11 parte F-C).

**C4 — Finalização única antes do recibo (dono F-C).** `verify.verificar` deixa de persistir; devolve resultado. `service._finalizar(result, ctx)` aplica, nesta ordem: C1, C2, confiança de extração (decisão 0016: provável ou referente alternativo nunca produz conclusão definitiva de pertença, em `verificar_citacao` e `verificar_texto`), autenticação de evidência e rebaixamento por captura ausente; só então `_persist`. Teste: as conclusões (status e reason_code de cada dimensão) lidas por `run_id` são iguais às devolvidas em todos os rebaixamentos; com C5 `sem_conteudo`, a projeção persistida é definida (dimensões e hashes) e o teste compara só ela.

**C5 — Registro de entradas (dono F-E, com F-C).** Política `registro ∈ {completo, sem_conteudo}` em configuração do serviço, exposta igualmente em CLI (`--sem-registro`), REST, MCP e biblioteca. `sem_conteudo` grava apenas hashes, política e dimensões: sem `citacao`, `trecho`, `citation.raw` nem evidência textual. Teste com marcador sintético procurado em todo o banco. README declara o que fica armazenado; retenção: `fv runs purgar --antes DATA` faz checkpoint do WAL, reconstrói o banco sem as execuções antigas num arquivo novo, troca atomicamente e move o original (com -wal/-shm) para `purgados/<data>/`, imprimindo os caminhos que restam para o usuário apagar; backups externos são declarados no README como responsabilidade do operador. Os triggers continuam.

**C6 — Versão dos derivados e recuperação (dono F-F, com F-A/F-B).** `DERIVED_VERSION` em `meta`, independente de `parser_version` e incrementada nesta release; versão ausente = incompatível. Home incompatível: o serviço recusa consultas que dependem de derivados com `indisponivel/ACERVO_DESATUALIZADO`. `fv acervo reconstruir` (idempotente e atômico): copia o banco, reprocessa as capturas com os parsers atuais na cópia, substitui provisions/redações/ocorrências dos documentos reprocessados (corrige repo.py:530–536), recompõe o FTS só com as redações do modelo atual (snapshot.py:595–598), valida contagens e integridade e só então troca o arquivo; interrupção deixa o original intacto. Capturas e recibos preservados. Instalação de snapshot: substitui `parsed_document` quando o `DERIVED_VERSION` recebido é maior e reconstrói os derivados na mesma transação de instalação. Aceite: home novo, home v1.0.2 reconstruído e home com snapshot instalado **e reinstalado** dão as mesmas respostas em B1–B3; reconstrução interrompida (falha injetada) não altera o original.

**C7 — Acervo efetivo (dono F-E).** O snapshot publica manifesto (`obras`, `decisoes`, `derived_version`, sha256). `doctor`, `create_mcp` e `fv serve-api` comparam o home com o manifesto do snapshot instalado (identificadores das obras, por hash do conjunto, além dos totais) ou, sem ele, com o mínimo embutido na versão; abaixo dele, aviso em toda resposta (`acervo_incompleto`) e no início do servidor.

## Frentes, itens e critérios

| Frente | Exec. | Itens | Aceite mínimo |
|---|---|---|---|
| F-A Constituição | sonnet | B1, ADCT citável | testes nomeados em R1; caminhos ambíguos da CF ≤ 10 no acervo real |
| F-B Infralegais | sonnet | C2 (B2), A4, A9 conector, M2, M3, M4, F03 (PDF no `parse_isolated` com limites de tempo/memória/páginas/texto) | R1 testes B2; PDF patológico termina `unavailable` sem derrubar o processo; A1 resposta `DOCUMENTO_SEM_ESTRUTURA` (via C1) |
| F-C Verificação | sonnet | C1, C3, C4, B3, A2, A3, A5, A8/F04, M1, M9, M11 (histórico) | um teste por consumidor de C1; regressão A3 em núcleo, fachada e obter_dispositivo; 201 citações com erro na última |
| F-D Busca | sonnet | A6, A7 (staging fora do FTS), A9 serviço, M5, M6, M7, M10, tesauro-1 | REsp no acervo achado por número; ausente → `nao_confirmado_no_acervo`; busca não altera contagem do FTS |
| F-E Fronteiras | sonnet | F01, F02, F05, F06, F08, F10, C5, C7 (A10) | F01: anônimo recusado pela fábrica ASGI e pelo HTTP MCP; F02: corpo limitado antes da leitura, tipos validados na fachada, semáforo de concorrência; F05: intervalo recupera o trecho ou a âncora é recusada; F06: fechamento coordenado, falhas registradas, troca de banco bloqueada com operação ativa; F08: um serviço por home; F10: release só após suíte no mesmo commit, sem `--clobber`, Actions por SHA |
| F-F Dados | haiku | C6, M8 (epígrafe), M11 (rubricas, mojibake) | home v1.0.2 sintético reconstruído; rubrica pesquisável |

Ordem de integração (contratos primeiro): F-C (C1, C3, C4) → F-B (C2) → F-A → F-F (C6) → F-E → F-D. Cada merge roda a suíte inteira.

## Decisões a registrar

0021 situação da obra (C2) · 0022 ADCT · 0023 negativa (C1) · 0024 respostas parciais e histórico ausente (C3, A5, A8, A9, M7) · 0025 busca (revisa 0010) · 0026 fronteiras remotas (F01, F02, F03) · 0027 recibo final e registro (C4, C5) · 0028 derivados versionados (C6).

## Portão de release

1. Suíte offline verde no commit publicado.
2. Testes de O1–O7 executados com o resultado esperado, **e controles positivos**: os casos verdadeiros de R1 (art. 254-A, art. 60 com o texto correto, Res. CVM vigente com artigo) continuam `verified`/`vigente_na_fonte`; a negativa legítima (art. 312 da LSA, obra íntegra) continua `not_found/DISPOSITIVO_INEXISTENTE`; uma implementação que devolva sempre `unknown` reprova.
3. Isolamento entre homes, ausência de registro com `sem_conteudo`, atualização de home antigo.
4. Auditor sem bloqueador sobre o commit integrado.
5. Snapshot reprocessado instalado e reinstalado em home novo e em home v1.0.2 atualizado, auditado nas consultas de B1–B3 e nos controles positivos antes da publicação.

## Fora do escopo (com franqueza)

Ampliação de cobertura da Fase 4 (STJ pré-2024, súmulas STF) e estruturação de artigos em PDF da CVM: dependem de captura ou parser novo; a resposta passa a declarar `DOCUMENTO_SEM_ESTRUTURA` ou lacuna de cobertura. Conjunto-ouro das 34 consultas: montado pelo orquestrador, marcado **não independente**.
