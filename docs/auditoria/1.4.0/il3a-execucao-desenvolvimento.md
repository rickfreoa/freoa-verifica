# IL.3-a: execução do executor no conjunto de desenvolvimento (DIAGNÓSTICO, não apuração)

Autor: codificador (Sonnet), 06/11/2026, ramo `feat/il3a-executor`. Este documento registra a execução do executor `scripts/porta_l.py` sobre o conjunto de desenvolvimento congelado, em modo local, com home temporário vazio. **Não é apuração**: a matriz de capacidades por rota continua `nao_apurada` em todas as rotas e capacidades (`freoa_verifica/data/qualificacao_rotas.json`), e a ativação ao vivo da Câmara é a trilha IL.3-b. Nenhum estado de aprovação ou reprovação aqui vale como qualificação de capacidade; a apuração é a IL.3-c (emenda IL, seção 5, IL.3).

## Comando e insumos

```
python -I -X utf8 scripts/porta_l.py --conjunto tests/porta_l/desenvolvimento.jsonl \
    --mutantes tests/porta_l/mutantes.jsonl --home C:\dev\tmp\il3a-home --modo local \
    --saida C:\dev\tmp\il3a-desenvolvimento.json
```

| Item | Valor |
|---|---|
| Ramo / commit do executor | `feat/il3a-executor` @ `97d365f` (base `main` @ `3cbb14c`) |
| Conjunto | `tests/porta_l/desenvolvimento.jsonl`, SHA-256 `2fb75d158f197a474e753796e2d621ba67f5200413ef0121daeb5ae6873517b1` (52 casos), conferido contra `il1-congelamento.md` pelo executor |
| Mutantes | `tests/porta_l/mutantes.jsonl`, SHA-256 `1f791fc1479d1a9d308b748a022adb69b8738435e5a87d37385f56f301e6afd3` (117), conferido |
| Home | `C:\dev\tmp\il3a-home`, recém-criado e **vazio** (sem acervo, sem snapshot, sem capturas) |
| Modo | `local`: rede bloqueada no processo, `FV_OFFLINE=1`; `tentativas_de_rede: []`, `rede_bloqueada: true` |
| Relatório integral | `C:\dev\tmp\il3a-desenvolvimento.json` (fora do repositório), SHA-256 `31462c5ea15dd490a9f6d1dbfbfabfc7f986fd4eabca5e49f0653449a1e67b3b` |
| Código de saída | 1 (alguma capacidade reprovada), como esperado com home vazio |

## Resultado

Com home vazio, a fachada responde `indisponivel` (ou `unavailable`, `not_assessed` nas dimensões de `verificar_citacao`) em todos os casos. Isso é o comportamento esperado e correto: nenhum documento está capturado localmente, e a consulta de rede está bloqueada. O resultado mostra, só, que o executor roda de ponta a ponta, que a fachada falha fechado e que o executor conta `indisponivel` no denominador e nunca no numerador.

| Cap. | Casos | Denominador (unidades) | Normas | Acertos | Resultado dos casos | Confirmações indevidas | Mutantes rejeitados | p95 (s) | Situação |
|---|---|---|---|---|---|---|---|---|---|
| (a) | 9 | 8 | 8 | 0 | 9 `indisponivel` | 0 | 18/18 | 0,0033 | reprovada (acerto 0,00 < 0,95) |
| (b) | 12 | 11 | 4 | 0 | 12 `indisponivel` | 0 | 34/34 | 0,0033 | reprovada (acerto; norma grande sem truncamento 0/10 por falta de resposta) |
| (c) | 11 | 10 | 7 | 0 | 11 `indisponivel` | 0 | 25/25 | 0,0034 | reprovada (acerto; caso sem fundamento da data não devolvido como não verificado) |
| (d) | 9 | 9 | 9 | 0 | 9 `indisponivel` | 0 | 18/18 | 0,0033 | reprovada (acerto 0,00 < 0,90) |
| (e) | 11 | 10 | 4 | 0 | 11 `indisponivel` | 0 | 22/22 | 0,0036 | reprovada (acerto 0,00 < 0,90) |

Leituras que o diagnóstico permite e as que não permite:

- **Permite:** zero confirmação indevida (nenhum `verified`, nenhum `encontrada` com texto diferente, nenhum alvo resolvido fora do gabarito, nenhum mutante tratado como o original); o bloqueio de rede ficou efetivo (nenhuma tentativa registrada); os 117 mutantes foram executados pela chamada declarada em cada um; as unidades por capacidade batem com as do validador (a 8, b 11, c 10, d 9, e 10, com os representantes de menor id).
- **Não permite:** nenhuma conclusão sobre acerto das capacidades, sobre p95 (as chamadas retornam sem trabalho real: 3 ms não são medida de desempenho) ou sobre a rejeição dos mutantes (com `indisponivel`, o mutante é trivialmente rejeitado: `text.status != verified`). Casos sem captura local saem `unavailable`; é o esperado, e só a trilha IL.3-b (captura dos documentos por instrumento, snapshot local) permite a primeira medida real.

## Regressões do que o diagnóstico não exercita

Como o home vazio não exercita os caminhos de acerto, as regressões que provam cada predicado estão em `tests/test_il3a_executor.py` (oráculos sintéticos por linha das tabelas 1, 1.1, 2 e 3 da matriz, mais o teste com a fachada real sobre a Lei 6.385/1976 do fixture) e `tests/test_il3a_remissoes.py` (A2).

## Leituras da matriz que o executor fixa (para a segunda camada e para o auditor)

A matriz não fecha alguns pontos; o executor adota a leitura mais restritiva possível e aqui as registra, para que o auditor as confirme ou as recuse:

1. **(ii) literal.** `status: encontrada` com `texto` diferente do gabarito é confirmação indevida em toda chamada de obtenção, inclusive quando o texto vem truncado (`truncado: true`): a matriz não abre exceção para texto honestamente marcado como truncado.
2. **(b), "sem truncamento em 100% das normas grandes".** Vale para todos os casos (b) de tipo `texto` com `norma_grande`, não só os representantes; caso que não devolve texto não prova ausência de truncamento e reprova o item.
3. **(c), "100% dos casos sem fundamento da data devolvidos como não verificados, com motivo".** Vale para todos os casos de tipo `nao_verificado_para_D` (não só os representantes) e exige `text` e `temporal` em `unknown`, ambos com `reason_code` em `motivos_aceitos`; a conferência da cadeia só decide o acerto do caso, não essa condição.
4. **Cadeia e última versão anterior.** `ultima_versao_oficial_anterior` tem de existir, com data anterior a D; a cadeia tem de ter os mesmos atos, na mesma ordem, e cada data de publicação a até 45 dias da data do `gabarito.cadeia` (a mesma folga que o validador congelado admite entre ato e publicação).
5. **Mutante "rejeitado".** `renumerado`: nenhuma resposta `encontrada` com o texto do gabarito do caso de origem e nenhum `verified` em `text`, `temporal` ou `vigencia`; `caractere`: `text.status != verified`; `data_trocada`: `text.status` e `temporal.status` diferentes de `verified`. A dimensão `identity` pode ser `verified` num `renumerado` (o destino existe). Mutante não rejeitado ou inexecutável (função fora da fachada pública, parâmetro estranho, caso de origem ausente) conta como confirmação indevida (iv) e reprova tudo.
6. **Mínimos de composição.** O executor também reprova a capacidade com menos de 8 unidades ou 4 normas, como a matriz exige do conjunto (seção 2), além do que o validador já confere.
7. **Resultado do caso.** `acerto`, `parcial` (alvos de (e) só em parte; `verified` só numa dimensão em (c); cadeia divergente), `indisponivel` (`indisponivel`, `unavailable`) e `erro`; só `acerto` entra no numerador. O resultado vale pela primeira passada medida; a de aquecimento é descartada e as três medidas alimentam o p95 (posto mais próximo sobre todas as latências medidas da capacidade).

## Estado da matriz por rota

`freoa_verifica/data/qualificacao_rotas.json`: três rotas efetivas (`camara_atualizado`, `camara_original`, `planalto_acervo`) por sete capacidades (as cinco da Porta L mais identificação e vigência declarada), todas `nao_apurada`, sem versão e sem relatório. `listar_fontes` expõe o bloco como `qualificacao_rotas` e anexa o estado por rota a cada item de `qualificacao` da Porta L; o bloco `qualificacao` existente (seis itens da decisão 0075) não muda. O teste `tests/test_il3a_qualificacao.py` impede estado diferente de `nao_apurada` sem relatório de apuração referenciado por SHA-256 e, no checkout, confere que o arquivo existe e o hash bate.
