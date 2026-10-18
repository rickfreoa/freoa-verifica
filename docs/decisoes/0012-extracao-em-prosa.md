# Extração de citações em prosa

A superfície de uma norma conserva os pontos de abreviações e os offsets do texto original, inclusive quando há quebra de linha. Uma letra isolada antes da norma não constitui dispositivo: artigos e preposições não podem ser promovidos a alíneas. Alíneas com rótulo, aspas ou integradas a um dispositivo composto continuam reconhecidas.

Dispositivos explícitos podem preceder ou suceder a norma; listas produzem um confronto por caminho extraído, preservando a superfície comum. Remissões sem identificação explícita da obra permanecem não resolvidas. O extrator não herda a identidade de uma norma anterior por proximidade.

O corpus de regressão contém prosa sintética com expectativas próprias de identidade, dispositivo, superfície e offsets. Não substitui a avaliação das fontes nem o benchmark.

Para consultar um acervo instalado sem persistir recibos nem executar reparos, `FV_READ_ONLY=1` abre conexões SQLite com `mode=ro` e `query_only`, dispensa migrações e desativa capturas sob demanda no fluxo de verificação de normas. O banco precisa estar previamente instalado e atualizado. Os requisitos de evidência e os critérios de `verified` permanecem os mesmos.
