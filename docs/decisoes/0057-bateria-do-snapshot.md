# 0057 — Bateria do snapshot (`fv acervo conferir`)

Data: 19/10/2026 · Versão: 1.3.0 · Origem: plano 1.3.0, S4

## Problema

Nada conferia o acervo candidato antes de exportar nem os bytes depois de instalados: duplicatas, decisões sem captura, datas fora do recorte e derivados antigos só apareciam por acaso, e o conteúdo (órgãos, meses, recursos CKAN) não tinha referência congelada.

## Regras

1. `fv acervo conferir [--home DIR] [--manifesto ARQ] [--gravar-manifesto ARQ] [--recorte-desde D] [--recorte-ate D] [--estrito] [--json]`. Código de saída 0 só com `status: ok`; falha ou erro (banco ausente, manifesto ilegível) sai com 1.
2. Somente leitura: o banco abre com `mode=ro` e o comando não passa por `Verifica` (que migra e grava registro). Home sem banco é erro, não é criado.
3. Contagens (comparáveis): obras, decisões, por fonte (`capturas`, `documentos`, `parseados`), STJ por órgão e por mês de publicação e de julgamento, recursos CKAN (`id`, `nome`, `last_modified`, `sha256`, `n`, lidos do `sync_state` `stj_resource` capturado) e `derived_version`.
4. Defeitos (sempre falham, com ou sem manifesto): duplicata (`court` + `official_id` com mais de um id interno), decisão sem `decision_document` com captura, data de julgamento ou publicação fora do recorte (ou não ISO, quando há recorte) e `derived_version` diferente de `DERIVED_VERSION` (home sem obras é compatível). Sem recorte declarado, não há verificação de datas.
5. Pendências do `sync_state` (status fora de capturado, parseado, ambíguo, metadados, concluído) só falham com `--estrito`; aparecem sempre no resultado.
6. Manifesto congelado = `manifesto_versao`, `recorte` e `contagens`, JSON de chaves ordenadas. Com `--manifesto`, qualquer contagem diferente (inclusive chave presente só de um lado) é `contagem_divergente`; o recorte do manifesto vale se não houver flags. `--gravar-manifesto` não grava (e sai com 1) se houver defeito.

## Consequências

- Roda no corpus candidato (passo 2 de `docs/RELEASE.md`) e de novo sobre o home instalado, contra o mesmo manifesto (passo 6).
- Decisão gravada só com metadados (falha de download na captura) é "sem captura" e reprova a bateria: o acervo a publicar não deve tê-la.
- `official_id` nulo não é detectado como duplicata (o esquema não identifica por ele).
