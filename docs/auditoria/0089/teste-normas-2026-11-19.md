# 0089: segunda sessão de teste, normas.leg.br (19/11/2026, 17h54–17h56 UTC)

Objetivo: fixar com dados reais o vínculo entre os recursos XHR de normas.leg.br (Terra r3, achado 3) e testar a observação pura aprovada pelo titular (decisão 2 de 19/11).

## Método

Chrome 157, perfil dedicado novo. Gravador CDP com filtro de host **antes** de gravar (só `normas.leg.br`; eventos sem URL só quando associados a pedido desse host) e sem nenhum comando que altere requisição (sem `setCacheDisabled` nem `setBypassServiceWorker`). Corpos de `Document`, `XHR` e `Fetch` do host. Navegação do titular: busca e abertura da Lei 6.404/1976, busca e abertura da Lei 6.385/1976, recarga (F5) desta.

## Resultados

1. **Filtro na origem funcionou:** 614 eventos, um único host gravado (`normas.leg.br`); nada de terceiros nem do SSO corporativo.
2. **Observação pura basta para os recursos de interesse.** Sem desligar o cache, imagens e manifesto vieram do disco (`fromDiskCache: true`) na recarga; todos os `Document` e `XHR` de API vieram da rede (`fromDiskCache`, `fromServiceWorker` e `fromPrefetchCache` falsos). A recusa de resposta de cache não teria afetado nenhum recurso admissível.
3. **Vínculo JSON → texto, determinístico.** `GET /api/public/normas?urn=<URN>&&tipo_documento=maior-detalhe` devolve JSON-LD `schema.org/Legislation` com `legislationIdentifier` igual à URN pedida (conferido nas duas leis). O campo `encoding[]` traz exatamente dois `LegislationObject`:
   - `version: "Original"`, nome "Publicação Original [...] [Diário Oficial da União ...] (p., col.)", `isBasedOn` com `legislationLegalVersion: OfficialLegalValue` (o DOU), mas o próprio objeto com `legislationLegalValue: UnofficialLegalValue`; `@id` com expressão `@<data>`;
   - `version: "Current"`, nome "Compilação Monovigente na CD", `UnofficialLegalValue`; `@id` com expressão `@versao.atualizada`.
   Cada um tem `contentUrl = https://normas.leg.br/api/binario/<uuid>/texto`; a página busca o mesmo UUID em `/api/public/binario/<uuid>/texto`. A página abriu a versão `Current` nas duas leis (6.404: `f61218b3-…`; 6.385: `66e79831-…`).
4. **Texto estável.** O binário da 6.385 obtido duas vezes tem o mesmo SHA-256 (`7409fada…`): sem conteúdo variável injetado, ao contrário do Planalto.
5. **Charset.** O binário é servido como `Content-Type: text/html` sem charset; o charset UTF-8 está só no `<meta>` do próprio documento. O CDP devolveu o corpo como texto (`base64Encoded: false`), sem nenhum U+FFFD. Não foi gravada a soma de `dataReceived.dataLength`, de modo que a regra de identidade de bytes da v4 (§2.5(2)) ainda não foi exercitada com dado real.
6. **Tamanhos.** `loadingFinished.encodedDataLength` da mesma resposta variou entre 34.012 e 34.011: inclui cabeçalhos (o `Age` mudou). Confirma Codex r3, achado 8: não serve como tamanho do corpo.
7. **Cookies.** 46 dos 65 pedidos levaram `Cookie`; nenhuma resposta trouxe `Set-Cookie`. Os cookies são criados por script (provável analytics). Os nomes não foram gravados (valores e nomes redigidos).
8. **Dados pessoais em documento público.** O HTML do binário, gerado por Aspose.Words, traz nos metadados do Word o autor e o último revisor (nomes de servidores da Câmara). É conteúdo público como servido; o parser não o usa.
9. **Achado lateral.** A versão `Original` (texto da publicação, com referência a página e coluna do DOU) está disponível pela mesma API. Pode servir de árbitro `texto_publicado` não oficial na adjudicação de divergências (plano NPL, T1), com tipagem própria; não é objeto desta decisão.

## Limitações

Uma sessão, duas leis, um navegador. Nomes de cookies não registrados. Sem desafio ativo nem CAPTCHA durante a sessão. Artefatos locais em `C:\dev\tmp\cdp-sessao\normas\`.
