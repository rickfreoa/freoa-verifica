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

## Emenda FIX9 (auditoria final, rodada 5: F-06, F-08, F-11, F-13)

A rodada 5 achou variantes das mesmas classes; a emenda troca os remendos por mecanismos únicos.

- **Progresso (F-06, F-13).** Regra 1 vale por `_EstadoChamada` único por chamada lógica, inclusive no controlador
  externo de prazo, na validação/resolução dos saltos e na leitura de desafio (ver emenda FIX9 da 0045). Deixa de haver
  evento por salto que se limpa.
- **Identidade efetiva (F-08, F-11).** A regra 2 deixa de ser por papel (`principal`, `alterador`): em
  `connector_fetch`, sob `SementeSync`, a guarda de execução (`connectors/guarda.py`) deduplica por método + URL
  normalizada + corpo e guarda o primeiro desfecho (resposta capturada ou `Unavailable`) para todo caminho que
  chama conector. Respostas bem-sucedidas ficam num LRU de 64 MiB (uma resposta expulsa pode ser pedida de novo);
  falhas ficam todas; requisições com `session` ou `sink` não entram no cache de desfechos. `_tentar_uma_vez`
  continua como guarda por chave de checkpoint.
- **Bloqueio por fonte.** Depois de `Unavailable` com categoria `ambiental_desafio` ou `recusa_identificado`, nenhuma
  nova requisição ao host na execução; as seguintes recebem a mesma categoria, sem rede, com
  `evidencia.bloqueio_fonte`, e os itens restantes ficam pendentes com ela. `fonte_fora` e `resposta_inesperada` não
  bloqueiam. Tem efeito só dentro da guarda (a semente); consultas do usuário não são afetadas.
- **CVM Colegiado.** Todos os itens de uma ata reutilizam a mesma captura (um GET); cada um seleciona a sua decisão.
  A captura de jurisprudência da semente usa `propagar_indisponibilidade=True`, de modo que `Unavailable` do indexador
  sobe e é registrado com sua categoria em vez de virar `sem_evidencia_capturada`.

## Emenda FIX10 (auditoria final, rodada 6: F-08, F-11, F-13, F-14)

- **Identidade (F-08).** A identidade efetiva é `transport.identidade_requisicao(metodo, url, corpo)`, a mesma
  canonicalização que o transporte aplica ao validar o destino: esquema minúsculo, host IDNA minúsculo sem ponto
  final, porta padrão removida, percent-encoding canônico (`%7E` = `~`), query ordenada, fragmento descartado. A guarda
  não tem canonicalização própria; cache e bloqueio por host usam só essa função.
- **Bloqueio por host efetivo (F-11).** O bloqueio por fonte vale para o host inicial e para o host de cada salto que
  respondeu sem redirecionar (`evidencia.saltos`; `url_final` quando o desafio é visto na resposta final). O transporte
  aceita `antes_do_salto(host)`; a guarda o fornece e recusa o salto para host bloqueado com a categoria original, sem
  requisição e sem incremento no breaker. A cadeia permanece como evidência.
- **Amostra e framing (F-13).** A amostra do corpo de erro é lida em laço até 64 KiB ou o fim do corpo, e o marcador é
  procurado no buffer acumulado (atravessa fronteiras de bloco). Chunk inválido, `Content-Length` não satisfeito,
  encerramento prematuro ou leitura impossível dentro da amostra é `RespostaInvalida` (`resposta_inesperada`), nunca
  repetível. Só corpo examinado sem marcador mantém a classificação por status. Corpo além de 64 KiB: examinam-se os
  primeiros 64 KiB, sem validar o framing do restante.
- **Indexador (F-14).** `Verifica._index_candidate_juris` propaga sempre `Unavailable`; o parâmetro
  `propagar_indisponibilidade` foi removido. Só falha que não é de indisponibilidade vira candidato com metadados. A
  pesquisa textual (`pesquisar_jurisprudencia`) roda sob uma `GuardaExecucao` por pesquisa: candidatos da mesma URL
  usam uma única captura, a indisponibilidade de um candidato interrompe a fonte, aparece em `fontes` e em
  `cobertura[].indisponivel` com categoria, e o status de topo é `parcial` ou `indisponivel`, nunca `ok`.

## Emenda FIX11 (auditoria final, rodada 7: F-11, F-13, F-16)

- **Framing de toda resposta (F-13).** `transport._validar_framing(resposta)` roda sobre os cabeçalhos brutos de
  qualquer resposta, com qualquer status, antes da classificação: `Transfer-Encoding` diferente de um único `chunked`,
  `Content-Length` duplicado (mesmo com valores iguais), não numérico, com sinal ou negativo, e `Content-Length` junto
  de `Transfer-Encoding` são `RespostaInvalida` (`resposta_inesperada`, sem repetição). O 200 e as respostas de erro
  usam a mesma função. O fluxo chunked é lido por `_RespostaEstrita`, que não herda a tolerância do `http.client`:
  tamanho `HEXDIG+` com extensão opcional (sem sinal, sublinhado, espaço ou `0x`), fim de chunk exatamente CRLF, e
  corpo terminado em `0 CRLF [trailer] CRLF`. Dados além do tamanho declarado, tamanho inválido e encerramento
  prematuro são `RespostaInvalida` em 200, 503 e demais status.
- **Desfecho final na guarda (F-11).** A guarda registra o desfecho final da chamada ao conector, não o intermediário
  do transporte. `connector_fetch(..., reclassificar=f)` aplica a regra do conector (`f(Unavailable) -> Unavailable`)
  dentro do `baixar` que a guarda executa; o Planalto passa `_reclassificar_recusa` (decisão 0048), de modo que o
  fechamento sem resposta, já `recusa_identificado`, bloqueia o host para o resto da execução (a segunda lei não faz
  pedido e o breaker conta uma falha). Fora da guarda a reclassificação é a mesma.
