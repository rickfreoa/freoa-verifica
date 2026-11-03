# IL.0-R: especificação (critérios fixados antes da implementação)

Base: ramo `feat/il0r-fronteira` a partir de `d965f77`. Normativo: `docs/decisoes/0075-estado-com-data-e-fronteira-com-o-freoa.md` (r2), emenda IL (seções 5 e 8), `docs/CONTRATO.md`, `AGENTS.md`. Cada critério abaixo vem do passe final do PR #25 (`C:\dev\fv14-auditoria\parecer-pr25-final.md`, que o executor deve ler inteiro) e deve ser resolvido POR CLASSE: todos os caminhos, adaptadores (Python, MCP, REST), ferramentas e campos do mesmo padrão, não só o exemplo.

## Critérios

C1. Guarda histórica única. Para toda consulta com D diferente de hoje (passada ou futura) sem fundamento validado, nenhum estado final publicado (temporal, text, `vigencia` de `obter_dispositivo`, `status` e `verificacao` de `verificar_texto`) afirma `verified`, `divergent`, `revogado`, `OBRA_REVOGADA_NA_FONTE` ou outra negativa derivada da situação cadastral, qualquer que seja o estado intermediário (`unknown` com qualquer motivo, `not_assessed`, ausência de dispositivo, consulta sem caminho). Exceções que se mantêm: `nao_existia` nos dois casos da 0075, seção 2, item 3; `ambiguous`; entradas inválidas. Implementação: uma única guarda aplicada antes dos dois ramos de revogação da situação (`situacao.py`) e de novo na finalização da resposta (defesa em profundidade), com teste que percorre todos os dispositivos de pelo menos uma obra CVM real (fixture `cvm_resol_160_consolid_docx`) em datas passada e futura com situação `revogada` e `cancelada`, com e sem data de efeito.

C2. Fundamento temporal. No IL.0-R nenhum caminho aceita fundamento: remova o parâmetro `fundamento_temporal` de `temporal.select` e de `verify.verificar` (ou faça-o recusar qualquer valor com erro de programação) até o IL.2 trazer o resolvedor de versões oficiais. Retire os testes que exigem `verified` com fundamento fictício; acrescente mutantes que provem que `{}`, `False`, `0`, dicionário parcial e dicionário completo não liberam `verified`. `fundamento_temporal` publicado continua sempre `null`.

C3. Consulta corrente inalterada. Toda mudança temporal fica restrita ao ramo histórico. Teste diferencial contra a semântica de `430e654` para consultas sem `data` e com `data` igual a hoje, cobrindo inclusão futura com e sem anotações de juízo e `redacao_dada` futura (status e motivo idênticos à base).

C4. Campos aditivos na resposta final. `fundamento_temporal` e `correspondencia_textual` presentes (com `null` quando inaplicáveis) em todos os ramos de `verificar_citacao`, `verificar_texto` (embutida) e `obter_dispositivo`, inclusive sem caminho e após qualquer rebaixamento; `correspondencia_textual` nula sempre que a identidade FINAL não for `verified`. As condições se aplicam depois de todos os rebaixamentos (ponto único de finalização).

C5. Motivo textual. Em consulta histórica sem fundamento, `text.reason_code` é `sem_fundamento_do_periodo` também nos ramos de revogação (`RevokedProvision`, `revogacao_anotada`), antes dos tratamentos específicos.

C6. Evidência por caminho comum. Toda evidência capturada publicada (normas e decisões, `verificar_citacao` e `obter_dispositivo`) é construída por um único construtor com os seis campos da 0075, 3.2. `procedencia` é persistida por captura: `captura_direta` quando gravada por conector neste home, `snapshot` quando incorporada pela instalação de snapshot (inclusive em acervo misto), `sessao_assistida` quando rotulada; capturas anteriores sem a marca ficam `nao_identificado`. Migração e instalação de snapshot atualizadas para gravar a marca.

C7. `acervo_ate` sem cache obsoleto: calculado na emissão ou invalidado em toda alteração do acervo (indexação, `_clear_caches`, instalação e rollback de snapshot, reconstrução); teste com troca externa de banco.

C8. Registro legado autenticado. A distinção entre legado e novo não pode depender só de `registro_mac IS NULL`: a migração grava, autenticado por HMAC do home, o conjunto (ou o limite) dos `run.id` existentes antes dela; registro fora desse conjunto sem MAC dá `integridade.confere: false`. Mutantes: apagar o MAC; apagar o MAC e as colunas novas.

C9. Leitura sem escrita. Carregar a chave do home para conferir não escreve no banco (separar leitura da chave do registro da impressão digital); `obter_registro` funciona com `PRAGMA query_only=ON`.

C10. `obter_registro` nas operações contadas (`_CONTADAS`), com teste causal de concorrência com operação exclusiva.

C11. Recibo de todas as verificações. Os caminhos de verificação de decisões (`_verificar_decisao_avulsa`) e as saídas antecipadas com conclusão (indisponibilidade, divergência de identidade, ausência de captura) gravam recibo e devolvem `run_id` recuperável, com a política de minimização vigente; modo somente leitura declarado.

C12. Contrato do consumidor alinhado: `vigencia.status` de `obter_dispositivo` com os literais efetivamente publicados (`revogado`, `nao_existia` etc.); casos do harness para revogação corrente, inexistência documental, obtenção histórica e sem caminho; literais não exercitados na lista exata.

## Processo

Commits por grupo de critérios; suíte offline completa e Ruff verdes antes do último commit (`$env:TMP`/`$env:TEMP` fora do repositório); relatório em `C:\dev\_il\relatorio-sonnet-il0r.md` com, por critério, o que mudou, os testes que o provam e as classes cobertas.
