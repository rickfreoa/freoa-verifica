# 0089: vigilância de extensões e sessão de teste no Brave (19/11/2026, ~19h35–19h45 UTC)

Objetivo: validar a correção do bloqueador B2 da rodada 5 (vigilância contínua do diretório de extensões, aprovada pelo titular) e testar o Brave, indicado pelo titular, como navegador da sessão, já que o Chrome do notebook recebe por política a extensão Fortinet. Nada do que foi gravado entra no Verifica.

## Ambiente

- Brave 1.100.58 (Chromium 158.0.8127.42), instalado na conta do usuário (`%LOCALAPPDATA%\BraveSoftware`).
- Registro: **nenhuma política** em `Software\Policies\BraveSoftware\Brave` (HKLM e HKCU). O Chrome (HKLM) tem `ExtensionInstallForcelist`, `ExtensionSettings`, `ExtensionInstallBlocklist`, `RestoreOnStartupURLs`, `NewTabPageLocation` e outras; o Edge (HKLM) tem `ExtensionInstallForcelist` e `ExtensionSettings`.

## Vigilância do diretório de extensões (B2)

`vigia.py`: observador do sistema de arquivos (watchdog, ReadDirectoryChangesW) sobre o perfil novo, ligado **antes** do lançamento; navegador aberto só em `about:blank` por 40–45 s.

- **Chrome:** a instalação da Fortinet Privileged Access Agent 8.0.1.175 apareceu como criação de `Default\Extensions\gkmiciealelfckimnoopefeplibjciih\8.0.1.175_0\…` aos 5,1 s; 740 eventos no diretório. A vigilância capta instalação por política no instante em que os arquivos são gravados, sem depender do arquivo de preferências.
- **Brave:** nenhum evento em `Default\Extensions`; o diretório nem foi criado. Inventário: só extensões de componente, `Chrome PDF Viewer` e `Brave` (`mnojpmjdmbbfmejpflffifhffcmidifd`, location 5). A extensão de componente `Brave` declara `webRequest`, `webRequestBlocking`, `cookies`, `management`, `<all_urls>`: é por ela que o navegador implementa funções próprias. Pela regra literal da v5 (§2.2(3), que inclui componentes), a sessão não abriria no Brave. Questão levada ao titular.

## Sessão de teste no Brave

Gravador `gravador3.py`: só observação (`Network.enable`, `Page.enable`, `Network.streamResourceContent`); filtro de hosts antes de gravar (`www.planalto.gov.br`, `normas.leg.br`); bytes só por streaming. Navegação do titular na aba já anexada: LSA no Planalto, recarga, Lei 6.404 e Lei 6.385 em normas.leg.br.

1. **Filtro:** 78 eventos gravados, só dos dois hosts.
2. **Planalto, primeira carga:** 200 de rede, TLS 1.2, IP 170.246.255.181, sem compressão; bytes do streaming = 757.607 = `Content-Length` = soma de `dataLength`; cauda do F5 casa o **modelo literal** da §2.5(3).
3. **Planalto, recarga (F5): 304 apresentado como 200.** `responseReceived` trouxe status 200 com `fromDiskCache: false`, mas `responseReceivedExtraInfo.statusCode` = 304; o corpo era o mesmo da primeira carga (mesmo hash, mesmo token F5). É exatamente o caso que a §2.3(1) manda recusar pelo confronto dos dois status. Prova empírica de que os sinalizadores de cache, sozinhos, não bastam.
4. **normas.leg.br:** recarga do documento veio do cache (`fromDiskCache: true`), caso que a §2.3(1) recusa. Metadados (A) das duas leis com `legislationIdentifier` igual à URN e dois UUIDs cada (`Original` e `Current`), iguais aos da sessão no Chrome. Binário da 6.385 obtido duas vezes por streaming, 147.094 bytes, **mesmo SHA-256 (`7409fada…`) da sessão no Chrome**: identidade de bytes entre navegadores e entre dias; `Content-Length` (28.963) igual à soma de `encodedDataLength` em XHR comprimido, como a §2.4, linha 7, exige.
5. **Streaming sem bytes:** numa rajada de XHR (15:41:12), o binário da 6.404 e oito pedidos de metadados terminaram com zero bytes de streaming e sem erro do comando; `responseReceivedExtraInfo` também não chegou para eles. Pela v5, essas candidatas seriam recusadas (streaming ausente, `statusCode` ausente). A causa não foi isolada (provável corrida entre a ativação do streaming e respostas rápidas, ou pedidos repetidos pela página); a recarga obteve o binário da 6.385 sem falha.
6. **Quadro principal:** o gravador só conheceu a raiz pelo `frameNavigated`, que chega depois do primeiro pedido da aba; por isso a primeira carga do Planalto saiu como "não principal". A v5 já exige `Page.getFrameTree`; a implementação deve obtê-la na anexação e mantê-la pelos eventos de quadro.
7. Nenhum desafio, CAPTCHA ou bloqueio do Shields nos recursos de interesse.

## Conclusões

O Brave serve como navegador da sessão neste notebook, condicionado à decisão sobre a extensão de componente `Brave`. A vigilância do diretório de extensões fecha o bloqueador B2 para extensões instaladas por política ou pelo usuário. O teste confirmou, com tráfego real, três regras da v5 que até aqui só tinham fundamento documental: o confronto de `statusCode` (304 escondido), a recusa de cache e o confronto de `Content-Length` com o contador codificado em XHR.
