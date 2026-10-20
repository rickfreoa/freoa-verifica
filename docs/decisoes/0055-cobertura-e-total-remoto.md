# 0055 — Bloco `cobertura` e total remoto desconhecido

Data: 19/10/2026 · Versão: 1.3.0 · Origem: plano 1.3.0, P1

## Problema

`CandidateList.total` valia `max(total or 0, len(self))`: fonte que não informava total passava a "ter" exatamente o que foi lido, e o serviço (`pesquisar_jurisprudencia`) descartava o total e calculava `truncado` só pelos itens locais. A resposta não dizia quanto da fonte foi lido, nem se a fonte foi sequer consultada (limite, offline, falha) nem qual o recorte do acervo instalado.

## Regras

1. `CandidateList.total` é `int | None`: `None` = a fonte não informou (desconhecido, nunca o tamanho lido). `total_exato` é `bool | None` (exato, cota inferior, não dito). `truncado` só é verdadeiro com total conhecido maior que o lido.
2. Os conectores informam o total só quando a fonte o dá: TJDFT (`hits.value`; exatidão por `hits.relation == "eq"` quando existir, senão `None`), DataJud (`hits.total`, idem), TJSP (contador da página; exatidão `None`), STJ local (`COUNT` do índice: exato). TCU e CVM Colegiado devolvem lista simples: total desconhecido. Zero só quando a fonte informa zero (TJSP, DataJud, STJ local).
3. `pesquisar_jurisprudencia` ganha `cobertura` (experimental, docs/CONTRATO.md): um item por tribunal pedido ou implicado, com capacidade, consulta executada, motivo de não consulta, recorte e instante de captura do acervo, `total_remoto`/`total_exato`, `lidos`, `indexados`, `truncado_remoto`, `truncado_local` e `indisponivel` (com a categoria preservada).
4. Na busca textual, `truncado` passa a ser verdadeiro também quando a fonte informou mais do que foi lido (`status: "parcial"`). O `cursor` continua só paginando o acervo local e fica nulo nesse caso.
5. Em classe e número com `nao_confirmado_no_acervo`, `cobertura` já é, no contrato 1, um objeto estável; a lista por tribunal vai em `cobertura_por_tribunal` (experimental) até uma versão que a unifique, com o ciclo `deprecated`.

## Consequências

- Nenhum caminho produz `total_remoto: 0` sem a fonte ter informado zero; lista vazia sem total informado é `total_remoto: null`.
- `lidos` mede o que a fonte devolveu; no TJDFT o filtro de data local pode reduzir os candidatos mantidos, de modo que `total_remoto` (da consulta sem esse filtro) é um limite da fonte, não do recorte.
- Busca ao vivo pelo número CNJ só existe para o TJDFT; busca por classe e número não consulta fonte ao vivo (`motivo_nao_consulta: nao_suportado`).
