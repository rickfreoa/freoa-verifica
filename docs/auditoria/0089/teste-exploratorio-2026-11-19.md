# 0089: teste exploratório da opção A (19/11/2026, 17h29–17h32 UTC)

Decisão do titular (19/11): opção A da pendência 33, isto é, emendar a 0067 para admitir, só na sessão assistida, os bytes recebidos pela conexão do próprio navegador, com validação declarada e prova de origem de rede. Este teste precede a redação da v3.

## Método

- Chrome 157.0.8103.79 no notebook do titular, perfil novo e dedicado (`--user-data-dir` em `C:\dev\tmp\cdp-sessao\perfil`), depuração remota na porta 9333, sem sincronização.
- Gravador CDP (ferramenta de teste fora de `src/`): `Target.setAutoAttach` em modo plano; em cada página, `Network.enable`, `Network.setCacheDisabled(true)` e `Network.setBypassServiceWorker(true)`; eventos de pedido, resposta (com `fromDiskCache`, `fromServiceWorker`, `fromPrefetchCache`, IP, protocolo TLS e emissor), cabeçalhos brutos, `encodedDataLength` e falhas; corpo das respostas `Document` por `Network.getResponseBody`, gravado com SHA-256. Cookie, Set-Cookie e Authorization redigidos na gravação.
- Navegação humana pelo titular: LSA (`l6404consol.htm`) no Planalto clássico, no NPL e no host `portaldalegislacao-classico`; busca por "6404" em normas.leg.br e abertura da Lei 6.404; recarga (F5) da primeira página.

## Resultados

| Recurso | Status | Rede | Content-Encoding | Bytes no fio | Corpo | Observação |
|---|---|---|---|---|---|---|
| www.planalto.gov.br LSA | 200 | 170.246.255.181, TLS 1.2, Sectigo | nenhum | 758.166 (com cabeçalhos) | 757.607 = Content-Length, base64 | corpo idêntico aos bytes do fio |
| idem, recarga F5 | 200 | idem; `fromDiskCache=false` | nenhum | 758.298 | 757.607 | hash distinto (ver achado 2) |
| portaldalegislacao (NPL) LSA | 200 | 170.246.255.72, TLS 1.2 | gzip | 144.022 | 635.025 decodificado | navegador passa; cliente identificado não (pendência 28) |
| portaldalegislacao-classico LSA | 502 (duas vezes) | 170.246.255.72 | nenhum | 552 de corpo | página nginx | falha do servidor também para o navegador; não é barreira a cliente |
| normas.leg.br | 200 | 201.54.48.132, TLS 1.3 | gzip | 14.965 | 66.002 | SPA; o texto vem por XHR (achado 3) |

Nenhuma resposta veio de cache em disco, service worker ou prefetch. Nenhum evento de prerender. Nenhum desafio, CAPTCHA ou página de bloqueio nos hosts de interesse.

## Achados

1. **Opção A viável nos três portais.** O navegador atravessa a barreira do NPL que recusa o transporte. Com cache desligado e service worker ignorado, a recarga veio da rede, e os sinalizadores do CDP permitem provar a origem resposta a resposta.
2. **Injeção do WAF F5 no Planalto.** Cada resposta do Planalto termina, depois de `</html>`, com `<script id="f5_cspm">` contendo um token por requisição; as duas capturas da LSA têm o mesmo tamanho e diferem em 115 bytes, só no token. O hash dos bytes brutos não é estável entre capturas. A injeção já existe nas fixtures capturadas pelo transporte (`planalto_lei_6385_1976.html` e outras quatro), portanto não é efeito do navegador. Consequência para a v3: a identidade da captura é o hash dos bytes brutos (exemplar), e a comparação entre capturas se faz sobre o texto extraído, com a remoção do bloco `f5_cspm` declarada em lista fechada (o mesmo tipo de regra do plano NPL, §3); o bloco é conteúdo não normativo e não confiável (T8).
3. **normas.leg.br é SPA.** O documento HTML é a casca; a lei chega por XHR: `GET /api/public/normas?urn=urn:lex:br:federal:lei:1976-12-15;6404&tipo_documento=maior-detalhe` (JSON, metadados) e `GET /api/public/binario/<uuid>/texto` (HTML gzip, 113.075 bytes no fio). A busca usa `legis.senado.leg.br/sigen/api/catalogo/basico?q=6404`. Consequência: a captura da sessão assistida não pode se limitar a `Document`; precisa de uma lista fechada, por host, dos recursos XHR/Fetch admitidos como fonte (rota e tipo), com corpo e hash. A URN LexML é o parâmetro da API, o que liga este achado à 0088.
4. **Corpo decodificado.** Com gzip, `getResponseBody` devolve o corpo descompactado (no NPL e em normas.leg.br, texto reencodado em UTF-8 pelo CDP). A validação de Content-Encoding da 0060 passa a ser declarada sobre os metadados (cabeçalho, `encodedDataLength`), não reproduzida. Sem compressão e sem charset (Planalto), o CDP entrega base64 e o corpo coincide com os bytes do fio.
5. **Política corporativa do navegador vaza para o perfil dedicado.** Cada aba nova abriu uma página do SharePoint do escritório, com redirecionamento ao login Microsoft (SSO Entra), mesmo em perfil novo; causa provável, não conferida: política de máquina do Chrome. O gravador registrou essas trocas. Foram apagadas na higienização (931 eventos → 260, cinco corpos removidos), e os cabeçalhos brutos sem URL foram descartados. Consequências para a v3: (a) a gravação filtra por lista fechada de hosts antes de gravar, nunca depois; (b) a sessão assistida não roda num navegador sob política corporativa, ou declara e isola essa política; (c) dados de terceiros e do escritório ficam fora da evidência por construção.
6. **O 502 do host clássico novo** também ocorre para o navegador; vai como dado para o plano NPL (T7), não para a 0089.

## Limitações

- Uma rodada, três portais, um ato. Não testou Câmara, TJSP, desafios ativos do WAF, nem expiração de sessão.
- O corpo XHR de normas.leg.br não foi gravado (o gravador só guardava `Document`); os tamanhos e cabeçalhos estão no registro.
- Artefatos locais, fora do repositório: `C:\dev\tmp\cdp-sessao\` (gravador, eventos higienizados, corpos).
