# 0059 — Progresso da chamada lógica, guarda única da semente e histórico de fontes também em erro

Data: 20/10/2026 · Versão: 1.3.0 · Origem: auditoria final, rodada 4 (F-06, F-08, F-09, F-10); complementa a 0058

## Problema

A 0058 deixou quatro brechas: o redirecionamento reiniciava a condição "nenhuma resposta recebida" (F-06); a proteção contra repetição na semente alcançava só as obras e os alteradores, não as consultas auxiliares de data no Senado nem a sobreposição de listas do BCB (F-08); `fontes_consultadas` desaparecia nas saídas de erro (F-09); a confirmação CNJ baixava de novo o documento já capturado e engolia o desafio da segunda requisição (F-10).

## Regras

1. **Progresso é da chamada lógica.** Se qualquer salto da cadeia de redirecionamentos recebeu status, uma falha posterior em outro salto — inclusive fechamento sem bytes — é `RespostaInvalida` (`resposta_inesperada`), sem repetição. A evidência da cadeia segue em `saltos: [{url, status}]` (`TransportError.saltos`; `Unavailable.evidencia["saltos"]`). Fechamento sem bytes no primeiro salto continua `fonte_fora`.
2. **Guarda única da semente.** `SementeSync._tentar_uma_vez(chave, fn)` executa cada chave de requisição no máximo uma vez por `run`; repetição devolve o desfecho (ou relança a exceção) da primeira, sem pedido nem incremento no breaker. Vale para obras e alteradores, datas do Senado, resolução e captura do BCB, CVM e jurisprudência. Chave marcada indisponível por `_mark_indisponivel` também entra na guarda. A repetição é da próxima execução.
3. **Histórico em erro.** Quando todas as fontes falham, `SourceUnavailable.fontes_consultadas` carrega a lista estruturada (`fonte`, `resultado`, `motivo`, `categoria`), exposta em `identity.evidence[0].fontes_consultadas` da verificação (e em `fontes_consultadas` das consultas auxiliares e de `verificar_citacao` por dispositivo). Erro de programação ou de parse numa fonte posterior preserva as falhas anteriores e entra como item `{resultado: "erro", categoria: "regressao"}`. Na confirmação CNJ, vale o mesmo para TJSP e DataJud.
4. **Confirmação CNJ.** Reutiliza a resposta já capturada (`captured_response`) em vez de baixar de novo a mesma URL. `Unavailable` do indexador (`propagar_indisponibilidade=True`) sobe ao controlador, que interrompe o TJSP (nenhum pedido adicional) e declara a falha em `fontes_consultadas` antes de seguir ao DataJud.

## Consequências

- `fontes_consultadas` continua aditivo e experimental (`docs/CONTRATO.md`).
- Com a guarda única, a mesma chave não é tentada duas vezes na semente nem quando aparece em contextos ou listas diferentes.
