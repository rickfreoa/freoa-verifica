# 0089 — Registro de execução do defeito 49

20/11/2026. Registro do Desenvolvedor por instrução expressa do supervisor, na base
`a0a7a3e` de `feat/0089-sessao-assistida`. Não substitui a nota formal do titular.

O terceiro ensaio real informado pelo supervisor (Brave 1.100 / Chromium 158,
harness HTTPS local com 150 ms até o primeiro byte) mostrou comando de streaming
escrito no pedido, cerca de 190 ms antes dos dados, primeiro `dataReceived` sem
`data` com comprimento 20, resposta com os mesmos 20 bytes em `bufferedData` e
eventos seguintes com `data`. Evidência informada: `C:\dev\tmp\v5\impl-b\diag_trace.txt`
e `diag_trace_plugin.py`; não se executou novo navegador nesta rodada.

Leitura de execução adotada pelo supervisor e implementada:

1. `Network.streamResourceContent` continua chamado no `requestWillBeSent`, única
   fonte de bytes; nenhum método CDP novo, sem `getResponseBody`.
2. Antes da resposta, eventos sem `data` são admitidos; com `data`, recusados.
3. O buffer decodificado deve medir a soma dos `dataLength` anteriores. Buffer
   vazio só se não houve evento anterior. Divergência gera `RespostaInvalida`.
4. Depois da resposta, evento com `data` exige base64 decodificável de tamanho
   igual ao próprio `dataLength`. Evento **sem a chave `data` só é admitido se
   `dataLength == 0`**: não acrescenta bytes, e seu `encodedDataLength` continua
   incluído nos contadores, limites e confrontos finais. Ausência de `data` com
   `dataLength > 0` ou divergência de tamanho gera `RespostaInvalida`.
5. `loadingFinished` anterior à resposta é streaming tardio e gera
   `RespostaInvalida`; erro do comando também recusa. Prazo inalterado.
6. Confrontos finais da §2.4 linha 7 e contadores/limites incluem todos os eventos.
   Os bytes declarados antes da resposta também reservam orçamento imediatamente.

O laboratório de 19/11 provou a chamada no pedido, sem provar a ordem da resposta
em relação ao evento. A exigência anterior de resposta antes do primeiro evento
era o defeito 49. A redação da 0089 §2.5(2) e do §3 item 1 ("streaming iniciado tarde")
**precisa de nota formal do titular**. Esta implementação registra a leitura
autorizada, sem emitir essa nota ou alterar por conta própria a especificação.

Provas, ajustes exigidos dos testes antigos, comparação AST D5, resultados e
limitações estão nas seções "Terceiro ensaio real: ordem resposta do streaming x
dataReceived" dos registros `docs/auditoria/0089/implementacao-trilha-a.md` e
`implementacao-trilha-b.md`.

## Quarto ensaio real: contador sem novos bytes

20/11/2026. Complementação por instrução expressa do supervisor, base `cbce9b6`,
mesmo ramo e worktree. No rastreamento `diag_trace.txt`, caso `fetch_identity`,
a resposta a `streamResourceContent` trouxe `bufferedData` vazio; seguiram dois
`dataReceived` **com `data`**, de 22 bytes cada, um `dataReceived` **sem `data`**,
com `dataLength=0`, e `loadingFinished`. A recusa anterior do item 4 abrangia
indevidamente esse último evento, que só informa contador codificado. A redação
do item 4 acima registra a exceção autorizada nesta rodada; os demais itens
permanecem iguais. Nenhum método CDP foi acrescentado.

Regressões sintéticas da porta e do adaptador reproduzem essa ordem para Fetch
e XHR, identity/gzip, preservam corpo/hash e contador codificado, recusam
comprimento positivo sem `data` e divergência no confronto codificado da §2.4,
linha 7. O rastreamento fornecido só demonstra Fetch identity; o log `nav-4.log`
não traz outra causa demonstrável para XHR. Não se afirma que o ensaio real
corrigido passou: novo navegador não foi executado nesta rodada.

A necessidade da nota formal do titular sobre a §2.5(2) e o §3 item 1 permanece.
Classificações A/B/C, validação e pendências estão na seção **Quarto ensaio real**
de `docs/auditoria/0089/implementacao-trilha-b.md`.
