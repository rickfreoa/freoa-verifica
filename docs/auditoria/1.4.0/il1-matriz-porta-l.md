# IL.1: matriz da Porta L, conjuntos e regra de apuração (congelada antes da implementação)

Data: 03/11/2026. Autor: supervisor (Opus), sob a emenda IL (seções 5 e 6) e a decisão 0075. Os pisos são os da emenda, seção 6, sem alteração; são escolhas de engenharia, não exigências demonstradas. Mudança de matriz, de reserva ou de piso depois de vistos resultados exige decisão do titular (emenda, seção 7).

## 1. Capacidades e chamada medida

Cada capacidade é medida por uma chamada pública fixa. Os parâmetros e campos marcados "IL.2" são nomes publicados aqui, a implementar no IL.2 e IL.3, aditivos.

| Cap. | Escopo | Chamada | Acerto |
|---|---|---|---|
| (a) | texto publicado | `obter_dispositivo(citacao, versao="publicacao_original")` (IL.2) | `status: encontrada`; `evidencia.natureza_texto == "publicacao_original"`; `texto` igual ao gabarito |
| (b) | texto consolidado vigente | `obter_dispositivo(citacao)` | `status: encontrada`; `texto` igual ao gabarito; `truncado: false` (obrigatório em todo caso de norma grande) |
| (c) | redação em data D | `verificar_citacao(citacao, trecho, data=D)` | gabarito `verificado_para_D`: `text.status` e `temporal.status` `verified` e `fundamento_temporal` não nulo; gabarito `nao_verificado_para_D`: `text.status` e `temporal.status` fora de `verified`/`divergent` e `reason_code` de ambos em `motivos_aceitos` do caso; gabarito `nao_existia_em_D` (D anterior à publicação da obra ou do ato que incluiu o dispositivo): `temporal.status` `not_found` com `reason_code` `NAO_EXISTIA` e `text.status` fora de `verified` |
| (d) | anexos | `obter_dispositivo(citacao_do_anexo)` | `status: encontrada`; `texto` igual ao gabarito (ou ao trecho delimitado do gabarito, quando o caso o declara) |
| (e) | remissões | `obter_dispositivo(citacao)`, campo `remissoes[]` (IL.3): `{texto, alvo: {obra, caminho}, resolvida: bool}` | todo alvo do gabarito presente com `resolvida: true`, e nenhum alvo resolvido fora de `alvos_admitidos` |

"Igual ao gabarito": igualdade após normalização só de espaço em branco (sequências de espaço, tabulação, NBSP e quebra de linha viram um espaço; aparas nas pontas) e de aspas e apóstrofos tipográficos. Nada além: nem caixa, nem pontuação, nem numeração.

## 2. Contagem

- Confirmação indevida (eliminatório, todas as capacidades): resposta com `verified` em `text` ou `temporal`, ou com `status: encontrada` e texto, que não corresponda ao gabarito; ou `verified` onde o gabarito é `nao_verificado_para_D`. Piso: 0 no conjunto avaliado, incluídos os mutantes.
- Denominador de cada capacidade: casos dessa capacidade com gabarito documental, contando no máximo um caso por unidade de independência, que é o par (norma, `familia_alteracao`); casos derivados da mesma alteração da mesma norma não são independentes, e os excedentes entram só no cômputo de confirmação indevida. `familia_alteracao` é o identificador do ato alterador (`lei-10303-2001`) ou `original`; sufixos artificiais (`-b`, `-alt`) são vedados. Em cada capacidade, pelo menos 4 normas distintas.
- `unavailable`, `indisponivel` ou `parcial` nunca entram no numerador e ficam no denominador.
- Caso `nao_verificado_para_D` conta como acerto quando assim devolvido (regra da linha (c)).
- Abstenção sistemática não aprova (c): o conjunto da reserva tem pelo menos 40% de casos (c) `verificado_para_D`; abaixo de 0,80 de acerto a capacidade reprova, ainda que todos os `nao_verificado_para_D` acertem.
- (c), condição adicional: 100% dos casos sem fundamento da data devolvidos como não verificados para D, com motivo.
- Mutantes, para todo caso de (b) e (c): data trocada (D deslocada para dentro do intervalo de outra redação conhecida), um caractere alterado no trecho, dispositivo renumerado (`art. N` → `art. N+1` ou `art. N-A`, conforme exista). Mutante aprovado: nenhum `verified` e nenhum `encontrada` com o texto do original.
- Desempenho: p95 da latência por chamada sobre o mesmo n da reserva, em dois modos: local (acervo ou snapshot instalado, rede desligada) ≤ 5 s; remoto (federação ao vivo) ≤ 20 s.

| Capacidade | Piso |
|---|---|
| todas | confirmação indevida 0 (eliminatório) |
| (a) | acerto ≥ 0,95 |
| (b) | acerto ≥ 0,95; sem truncamento em 100% dos casos de norma grande |
| (c) | acerto ≥ 0,80; 100% dos casos sem fundamento da data como não verificados para D, com motivo |
| (d) | acerto ≥ 0,90 |
| (e) | acerto ≥ 0,90 |
| todas | mutantes rejeitados; p95 ≤ 5 s local e ≤ 20 s remoto |

## 3. Conjuntos

| Conjunto | Casos | Por capacidade | Guarda |
|---|---|---|---|
| Desenvolvimento | ≥ 40 | ≥ 8 | no repositório, `tests/porta_l/desenvolvimento.jsonl`, com hash no manifesto |
| Reserva | ≥ 50 | ≥ 10 | fora do repositório, no computador do titular (`Claude_Externos/freoa-verifica/porta-l/reserva/`); só o SHA-256 vai ao repositório e ao manifesto |

Regime do D6: quem guarda a reserva comunica ao supervisor só aprovado ou reprovado por capacidade e métrica; diagnósticos vêm do desenvolvimento; parcela da reserva que orientar ajuste é substituída antes do novo aceite; relatório integral ao titular.

Cobertura mínima de cada conjunto (emenda, IL.1): dispositivo alto de norma grande (LSA 156, 254-A, 289; CC 421 e 1.031; CTN 185); redação anterior em data D com e sem rasura; revogação; MP reeditada e convertida; anexo; remissão; data anterior à publicação. O acervo Planalto congelado só serve de referência para o que documenta; alteração posterior ao corte exige gabarito em evidência oficial própria.

## 4. Forma do caso (JSON Lines, UTF-8)

```json
{"id": "L-c-007", "conjunto": "desenvolvimento", "capacidade": "c", "familia_alteracao": "lei-10303-2001",
 "norma": {"especie": "lei", "numero": "6404", "ano": 1976}, "citacao": "art. 254-A da Lei 6.404/1976",
 "data": "1999-06-30", "trecho": "...",
 "gabarito": {"tipo": "texto" | "verificado_para_D" | "nao_verificado_para_D",
              "texto": "...", "motivos_aceitos": ["sem_fundamento_do_periodo", "sem_versao_oficial_na_data"],
              "alvos": [], "alvos_admitidos": [],
              "fonte_oficial": {"url": "...", "sha256": "...", "capturado_em": "AAAA-MM-DDTHH:MM:SSZ", "orgao": "..."},
              "fundamento_data": "texto curto: por que a fonte prova o texto em D, ou por que não há versão oficial em D"},
 "norma_grande": true, "mutantes": true}
```

Gabarito documental: texto esperado, fonte oficial (URL, SHA-256 dos bytes, instante) e fundamento documental da data. O texto é exatamente o dispositivo pedido: sem rubrica, título ou epígrafe do dispositivo seguinte, sem notas e sem anotação de alteração; em (c) `verificado_para_D`, o texto do dispositivo em D, não o documento inteiro. Caso `nao_verificado_para_D` também traz `fonte_oficial` (a fonte consultada que mostra a ausência de versão oficial em D, ou a compilada cuja rasura é o único registro) e `fundamento_data` que explique a ausência. Em (d), anexo é parte que o diploma publica sob a rubrica "Anexo" (tabela, quadro, regulamento aprovado como anexo), citada como tal. Em (e), `alvos` não vazio, cada alvo com `caminho` de dispositivo (`art. N`, `art. N, § M`, `Anexo X`), nunca a obra inteira. Gabarito `nao_existia_em_D`: `fonte_oficial` é a publicação original do ato que incluiu o dispositivo (ou da obra), e `fundamento_data` dá a data de publicação. Fonte oficial admitida: Câmara (publicação original), Senado (Dados Abertos/LexML, texto original), DOU/INLABS, normas.leg.br, Planalto (só o que o acervo congelado documenta). Sítio não oficial não é fonte de gabarito.

## 5. Apuração

`scripts/porta_l.py --conjunto <jsonl> --home <home> --modo local|remoto --saida <relatorio.json>` (IL.1, sem rede própria: chama o serviço público). O relatório traz, por capacidade: denominador, acertos, confirmações indevidas, mutantes rejeitados, p95, e aprovado/reprovado por piso. Para a reserva, o guardião executa e entrega ao supervisor só a tabela aprovado/reprovado; o relatório integral vai ao titular.

## 6. Congelamento

Este documento, o conjunto de desenvolvimento e o SHA-256 da reserva entram juntos no repositório, antes do primeiro commit de implementação do IL.2, e são registrados no manifesto de aceite.
