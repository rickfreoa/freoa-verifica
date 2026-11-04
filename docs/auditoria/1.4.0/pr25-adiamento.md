# PR #25 (IL.0): teto do D5 e passe final com bloqueador; sucessor IL.0-R

Data: 03/11/2026. Autor: supervisor (Opus), sob o D5 do plano 1.4.0, a emenda IL e a autorização do titular de 03/11/2026 (decisões técnicas e de execução ao supervisor).

## Histórico

- Implementação: Antigravity, ramo `feat/il0-fronteira`, sobre a decisão 0075 r2 (PR #24, `430e654`).
- r1 (`affd742`): CI com 9 falhas; Codex COM BLOQUEADOR (2 altos: situação atual convertendo abstenção histórica; gate do consumidor sem tipos nem literais).
- r2 (`bc3cbad`): CI verde; Codex COM BLOQUEADOR (1 alto: gate sem preservação de literais pela implementação e sem validação por elemento).
- r3 (`dfd37e9`): CI verde; Codex COM BLOQUEADOR (2 altos: 23 literais retirados do arquivo do consumidor; lista vazia aprovada). Teto do D5.
- Correção conservadora do gate (`d965f77`) e passe final independente, exaustivo por classe de defeito: CI verde; Codex COM BLOQUEADOR, 2 altos e 10 médios (pareceres em `C:\dev\fv14-auditoria\parecer-pr25-*.md`).

## Fatos do passe final

1. Alto: a situação cadastral (CVM, BCB, CMN; `revogada`, `cancelada`) ainda produz negativa para D diferente de hoje quando o estado intermediário é `not_assessed` ou `unknown` com outro motivo, e em consulta futura sem data de efeito, nos três adaptadores.
2. Alto: qualquer valor não nulo de `fundamento_temporal` (inclusive `{}`, `False`, `0`) libera `verified` no motor Python; testes institucionalizam o defeito.
3. a 12. Médios: consulta corrente alterada pela restrição de inclusão; campos aditivos fora das condições da resposta final; motivo textual de revogação histórica; evidência de decisão sem os eixos e `procedencia` nunca preenchida; `acervo_ate` em cache obsoleto após snapshot; MAC apagado tido por legado; leitura de registro em home somente leitura; `obter_registro` fora das operações contadas; verificações de decisões sem recibo; literais de `vigencia.status` errados no arquivo do consumidor.

## Decisão (D5)

1. O PR #25 não é incorporado. O teto não equivale a aprovação.
2. Redução de escopo não resolve: os dois altos estão no núcleo da 0075 (seção 2), que é o objeto do IL.0. O IL.0 é adiado nesta forma.
3. Sucessor IL.0-R, ramo `feat/il0r-fronteira` a partir de `d965f77` (preserva o que o passe final confirmou), com especificação escrita própria (`il0r-especificacao.md`): a 0075 r2 mais os doze achados, cada um como critério fixado antes da implementação, com correção por classe. Novo teto de três rodadas e passe final. Se o IL.0-R também terminar com bloqueador, o IL.0 é adiado e o diagnóstico vai ao titular.
4. Executor do IL.0-R: Sonnet (`claude -p --model sonnet`), em lugar do Antigravity. Razões: os mesmos controles reincidiram em três rodadas; houve duas interrupções do processo do Antigravity no meio da rodada; o Sonnet já trabalhou no projeto e o impedimento anterior (venv negado em sessão não interativa) não se reproduz com o modo de permissão adequado. Auditor: Codex, com a instrução permanente de exaustividade por classe de defeito.
5. A numeração das pré-releases da decisão 0075, seção 6, fica mantida: 1.4.0a2 sai com o IL.0-R incorporado.
