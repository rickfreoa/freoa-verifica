# 0089: laboratório dos bloqueadores B1 a B3 da rodada 4 (19/11/2026, ~18h40–19h UTC)

Objetivo, aprovado pelo titular (opção A da rodada 4): provar, antes da v5, (1) se há via do CDP que entregue os bytes do corpo sem interpretação de charset; (2) se o inventário de extensões independe de alvo CDP; (3) como provar o quadro principal. Só `127.0.0.1`; nenhum site externo; sem o titular. Ferramenta de laboratório (aqui o cliente navega, o que o produto nunca faz), em `C:\dev\tmp\lab0089\`.

## Montagem

- Servidor HTTP local (`servidor.py`) que envia cabeçalhos, metade do corpo, espera 1 s e envia o resto. Rotas: UTF-8 com charset no cabeçalho; UTF-8 só com `<meta>` (como normas.leg.br); gzip; **BOM UTF-16LE com cabeçalho `charset=utf-8`** (contraexemplo do Codex r4); ISO-8859-1 declarado; windows-1252 sem charset (como o Planalto); JSON; UTF-8 com sequência inválida `F0 9F 92`; página com iframe; página com três `fetch`.
- Chrome 157.0.8103.79, perfil novo, `--no-proxy-server`. Cliente CDP: `Target.setAutoAttach` (espera pelo depurador, modo plano), `Network.enable`, `Page.enable`; em cada `requestWillBeSent` do servidor local, `Network.streamResourceContent`; no fim, `Network.getResponseBody`. Comparação com os bytes originais (decodificados de Content-Encoding).
- Três execuções: a primeira criou abas com URL (`Target.createTarget`); a segunda e a terceira navegaram numa aba já anexada (`Page.navigate`); a segunda tinha erro do cliente (streaming pedido duas vezes); vale a terceira.

## Resultados

**1. Bytes (B1).** `Network.streamResourceContent` chamado no `requestWillBeSent` devolveu `bufferedData` e, em seguida, `dataReceived.data` em base64; a concatenação foi **idêntica aos bytes originais em todos os casos**: UTF-8, meta, gzip (descomprimido), BOM UTF-16 sob cabeçalho UTF-8, ISO-8859-1, windows-1252, JSON, UTF-8 inválido, e nos três `fetch`. `Network.getResponseBody`, no mesmo pedido, **errou em dois**: BOM UTF-16 (96 bytes reencodados contra 166 originais) e ISO-8859-1 (78 contra 74, documento e `fetch`). Devolveu base64 correto para windows-1252 sem charset e para o UTF-8 inválido. O campo `Response.charset` existe, mas informou `utf-8` no caso do BOM UTF-16 (o decodificador efetivo foi outro): não serve de prova. Conclusão: corpo só por streaming iniciado antes da chegada de dados; `getResponseBody` não serve de fonte de bytes.

**2. Contadores.** Em `Document`, `dataReceived.encodedDataLength` veio sempre 0 (inclusive com gzip); em `fetch`, igual ao tamanho no fio. `dataReceived.dataLength` somou o tamanho decodificado em todos os casos. `loadingFinished.encodedDataLength` inclui cabeçalhos. Consequência: para documento comprimido, o confronto do Content-Length com os bytes codificados do corpo não é observável.

**3. Prontidão (B3).** Aba criada já com URL (`Target.createTarget`): o pedido do documento principal **não foi observado** (a anexação chega depois), embora o servidor o tenha recebido. Em aba já anexada, todos os pedidos foram observados e o streaming cedo funcionou. No iframe, o streaming cedo falhou ("Request with the provided ID does not exist"), sem prejuízo, porque iframe não é candidato.

**4. Quadro principal (B3).** `Page.getFrameTree` devolveu a raiz sem `parentId`, com `id` igual ao `targetId` da aba e ao `frameId` do `requestWillBeSent` do documento principal; o iframe veio como filho, com `parentId` igual à raiz e `frameId` próprio. Prova determinada: `frameId` do pedido igual ao `id` da raiz da árvore (sem `parentId`).

**5. Extensões (B2).** O inventário pelo arquivo `Secure Preferences` do perfil da sessão (`extensions.settings`, com `location`, caminho e manifesto) listou **todas** as extensões, inclusive as que nunca apareceram como alvo CDP (visualizador de PDF, aplicativo de pagamentos). O inventário não depende de alvo. A extensão de teste só com regras declarativas não foi instalada: o Chrome 157 de marca ignora `--load-extension`, mesmo com o recurso que o reativa. O caso "regra declarativa sem contexto de execução" fica coberto pelo inventário, não por observação de efeito.

**6. Achado decisivo: política do escritório.** O perfil novo recebeu, por política de máquina (`location` 7, instalação forçada por política), a extensão **Fortinet Privileged Access Agent 8.0.1.175**, com permissões `proxy`, `declarativeNetRequest`, `webRequest`, `cookies`, `privacy`, `browsingData`, `tabs`, `webNavigation`, entre outras. Pela decisão 3 do titular, a sessão assistida **não abre neste notebook**. A mesma extensão estava presente nas duas sessões de teste anteriores; elas valem como prova de viabilidade e de observabilidade, não como captura admissível.

## Limitações

Servidor HTTP sem TLS e em loopback; um navegador; respostas pequenas. O streaming exige pedido em curso; em resposta muito rápida, a chamada pode chegar tarde (caso do iframe), o que leva à recusa da candidata, não a erro silencioso. Não foi testado navegador sem a política do escritório.
