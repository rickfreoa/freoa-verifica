# Respostas parciais e histórico ausente

Data: 18/10/2026. Contrato C3 do plano 1.0.3 (A3, M1, A5, A8, M11 parte F-C).

**Histórico ausente.** Quando nenhuma redação é selecionada para a data pedida, a redação atual não é confrontada nem devolvida como se fosse a da data. `verificar` responde `text=unknown HISTORICO_ANTERIOR_AUSENTE` (ou o motivo temporal, se houver). `obter_dispositivo` devolve `texto=null` e, separado, `texto_atual` com `rotulo` que o distingue. Sem data pedida, a redação vigente continua sendo o texto.

**Redações anteriores.** `redacoes_anteriores` não inclui a redação vigente. Quando a primeira redação conhecida traz "Redação dada", `redacao_anterior_ausente_na_fonte` é `true` em `obter_dispositivo` e `historico_dispositivo`: a fonte não preserva o texto anterior.

**Remissão anafórica.** "art. 117 da mesma lei" não herda obra (decisão 0012 continua), mas deixa de sumir: `verificar_texto` a lista em `referencias_nao_resolvidas` com `status=referencia_nao_resolvida` e `motivo=REMISSAO_ANAFORICA`, para que o leitor não presuma conferência.

**Truncamento.** `verificar_texto` processa até 200 citações e informa `total_detectado`, `total_processado` e `truncado`. Acima do limite, `truncado=true`: as demais não foram verificadas.
