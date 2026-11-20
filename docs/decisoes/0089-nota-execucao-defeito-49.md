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
4. Depois da resposta, cada evento exige `data` decodificável de tamanho igual
   ao próprio `dataLength`; ausência ou divergência gera `RespostaInvalida`.
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
