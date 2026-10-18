# Plano v1.0.3 — proposta do orquestrador para debate com o auditor

Fontes: (R1) comparativo FREOA × JusRatio, 24 defeitos; (R2) avaliação de segurança e operação, F01–F10.
Base: commit 5d1936f (v1.0.2). Regras invariáveis de AGENTS.md mantidas sem exceção.

## Princípio de arquitetura (uma regra nova, três consequências)

**Ausência de evidência nunca é evidência de ausência, e evidência de revogação nunca é ignorada.**

1. `inexistente` só quando a obra foi capturada, tem estrutura de dispositivos e o caminho falta nela. Sem captura → `indisponivel/COBERTURA`; captura sem estrutura → `unknown DOCUMENTO_SEM_ESTRUTURA` (A1, A2, M9).
2. Situação cadastral oficial que afirma revogação vira issue de obra `OBRA_REVOGADA_NA_FONTE` e bloqueia `vigente_na_fonte` e `verified` temporal; situação ilegível vira `unknown SITUACAO_INDISPONIVEL`. Situação "vigente" continua sem poder afirmar vigência (FONTES.md) (B2).
3. Toda resposta parcial declara-se parcial: `truncado`, `total_detectado`, `nao_consultada`, `referencia_nao_resolvida` (A5, A8/F04, A9, M7).

Escopos estruturais: o ADCT passa a ser escopo próprio `adct/` aberto no cabeçalho do corpo (não no sumário); "art. N do ADCT" passa a ser citável (B1, M11).

## Frentes (delegação; arquivos disjuntos sempre que possível)

| Frente | Executor | Itens | Arquivos principais |
|---|---|---|---|
| F-A Constituição | sonnet | B1, ADCT citável (M11) | parsers/html_devices.py, citation.py, sentinel.py |
| F-B Normas infralegais | sonnet | B2, A1, A4, A9 (conector), M2, M3, M4 | connectors/cvm_normas.py, connectors/bcb.py, parsers/bcb_json.py, verify.py, temporal.py |
| F-C Verificação | sonnet | B3, A2, A3, A5, A8/F04, M1, M9, F07 | service.py (verificar_*, lei), verify.py:_persist |
| F-D Busca | sonnet | A6, A7, A9 (serviço), M5, M6, M7, M10, tesauro-1 | service.py (buscar_*, juris), store/repo.py, migração FTS |
| F-E Fronteiras | sonnet | F01, F02, F03, F05, F06, F08, F09, F10, A10 | rest.py, mcp_server.py, textcmp.py, parsers/isolated.py, service.py (conexões), cli doctor, .github/workflows |
| F-F Dados | haiku | M8 (epígrafe), M11 (rubricas, mojibake) | semente.py, snapshot.py |

Conflitos esperados: F-C × F-D em service.py (funções distintas); F-B × F-C em verify.py (B2 no ramo temporal; F07 em _persist). Worktrees isolados; integração pelo orquestrador, suíte inteira a cada merge.

## Decisões a registrar em docs/decisoes/

- 0021 Revogação na fonte bloqueia vigência (B2).
- 0022 Escopo ADCT (B1).
- 0023 Inexistência exige estrutura capturada (A1, A2, M9).
- 0024 Respostas parciais se declaram (A5, A8, A9, M7) — complementa 0012 sem alterá-la.
- 0025 Busca: AND completado por OR ordenado, pertinência exposta, tesauro determinístico (revisa 0010; M5, M6).
- 0026 Modo remoto exige autenticação em todas as entradas; limites de entrada na fachada (F01, F02).
- 0027 Recibo persistido = resultado final (F07); `--sem-registro` (F09).

## Fora do escopo desta versão (dito com franqueza)

- Fase 4 de cobertura (STJ pré-2024 curado, súmulas STF, CVM estruturada) depende de captura ao vivo nas fontes oficiais; entra como sincronização no notebook, não como código. Nada aqui contorna WAF do STF.
- Conjunto-ouro independente (Fase 5) exige pesquisador que não leia o código; o orquestrador monta o conjunto das 34 consultas a partir das fontes oficiais, marcado como não independente.

## Portão de release

Suíte offline verde; testes de regressão nomeados em R1 presentes; auditor sem bloqueador; zero `verified` e zero `vigente_na_fonte` indevidos nos casos B1–B3 e nos 8 corpora adversariais.
