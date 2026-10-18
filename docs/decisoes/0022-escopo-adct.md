# 0022. Escopo próprio para o ADCT

Data: 2026-10-18. Origem: defeito B1 da auditoria comparativa (ADCT gravado nos caminhos da CF; 58 artigos transitórios verified como permanentes).

## Decisão

1. O parser de HTML do Planalto abre o escopo `adct` ao encontrar, no corpo, uma linha inteira "ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS", e somente depois do primeiro dispositivo do texto permanente. Linha de sumário ou menção em frase não abre escopo (abrir no sumário jogaria a CF inteira no ADCT). Os caminhos seguem a convenção de anexo: `adct/art5`, `adct/art5.par1`.
2. `PARSER_VERSION` sobe para 1.2.3; capturas antigas são reprocessadas pelo mecanismo de versão de parser.
3. `Redaction.scope` registra o escopo de origem. O sentinela emite `SCOPE_COLLISION` (bloqueante no dispositivo) quando redações vigentes de escopos distintos competem pelo mesmo caminho, e nunca as encadeia como substituição editorial.
4. O extrator reconhece "art. 5º do ADCT", "art. 5º do Ato das Disposições Constitucionais Transitórias" e "ADCT, art. 5º" como Constituição com caminho `adct/art5`. "art. 60 da CF" continua apontando para o permanente.

## Consequência

Trecho do ADCT confrontado com citação do texto permanente deixa de ser verified. "Art. 5º do ADCT da Constituição Federal" ainda gera, além da citação do ADCT, uma segunda citação sem dispositivo para "Constituição Federal" (confiança provável); não foi tratada nesta frente.
