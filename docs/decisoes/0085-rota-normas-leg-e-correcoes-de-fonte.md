# 0085 - Rota normas.leg.br para legislação federal sob demanda; correções de fonte (BCB, instalador)

14/11/2026. Titular (Ricardo Peres Freoa), por instrução da mesma data ao supervisor (Opus):
identificar as causas dos erros do `doctor`, corrigi-los, verificar as rotas alternativas que
funcionam para extrair os diplomas normativos, ainda que sob demanda, e adotá-las. Resolve a
decisão pendente da 0084, item 4 (rota da legislação). Não altera o critério de `verified`,
`transport.py`, a matriz da Porta L, os pisos nem a reserva (D6).

## 1. Causas dos erros do `doctor` (a2 e a3)

| Fonte | Sintoma | Causa | Tratamento |
|---|---|---|---|
| bcb | `resposta_invalida` nas três sondas | A borda do BCB passou a devolver HTML "Requisição inválida!" com status 200 para `querytext` que contém `="` (forma `Propriedade="valor"`). Sondas de 14/11 isolaram o gatilho: a forma `Propriedade:"valor"` é aceita. | Corrigido (commit `9bc6da6`): consulta sem `="`; tipo e número conferidos no cliente, porque `:` casa por frase contida. |
| planalto | `falha`, `acervo_legado_sem_nova_captura` | Desenho: o Planalto derruba a conexão do UA identificado (0048) e saiu da nova captura; o acervo do snapshot responde sem rede. | Mantido. A rota desta decisão supre a captura que o Planalto não permite. |
| camara_legin | `ativacao_ao_vivo_pendente` | O home instalado não tem `camara_ativacao.json` (0080 §2); a ativação só foi feita no home de desenvolvimento. | Mantido; a Porta L segue `nao_apurada` (0084). |
| datajud, tcu, tjsp | 504, 429, CAPTCHA | Ambientais, classificados (0045, 0048). | Sem mudança. |
| instalador | home gravado em `%LOCALAPPDATA%\Packages\Claude_…\LocalCache\Local` | Instalação executada dentro do contêiner MSIX do app Claude: a escrita em `%LOCALAPPDATA%` é redirecionada (defeitos 24 e 25). | Seção 4. |

## 2. Rotas de legislação examinadas (14/11/2026, transporte do pacote, UA identificado)

| Rota | Resultado | Situação |
|---|---|---|
| Planalto | conexão encerrada antes da resposta (robots, LSA, Decreto 3.000) | fechada (0048) |
| LexML SRU | desafio F5 (`ambiental_desafio`); `/urn/` 503 | fechada; sem contorno |
| `legis.senado.leg.br` | robots 403 ao UA identificado (`HOSTS_RECUSADOS`); a API `dadosabertos/legislacao/lista` responde, mas só metadados | não usada pela rota nova |
| Câmara (`www2`) | depende da ativação da 0080; não alcança MPs, decretos de anexos, CTN nem LC 118 (0084 §1) | inalterada |
| **normas.leg.br** | robots `User-agent: * / Allow: /`; API pública responde a MP, decreto, decreto-lei de 1940, CTN de 1966 e LC 118; texto integral (publicação original e compilação monovigente) | **adotada** |

Prova de origem da API. O IL.2 deixou `normas_leg` só com robots porque a API (`/api/public`)
era conhecida apenas por projeto de terceiros. A assinatura agora vem do cliente oficial
servido pelo próprio host: `main.9e54abd8eff4fac4.js` declara `publicApiUrl:"/api/public/"`;
`987.9451176cf8cb4e12.js` declara `apiPrefix = publicApiUrl + "normas?urn="`, a chamada
`normas?urn=<URN>&tipo_documento=maior-detalhe` e a reescrita
`/api/binario/` → `/api/public/binario/` para obter os textos. A própria resposta declara
`sdLicense` e `license` `https://creativecommons.org/licenses/by/4.0/` e o editor
(`https://www.congressonacional.leg.br/`). Robots com `Allow: /` mais licença CC BY 4.0
declarada no dado constituem permissão positiva capturada, no sentido da 0048 §2. As capturas
formais pelo instrumento (robots, os dois scripts, metadados, ausência e um binário) integram a
implementação, depois da ampliação do catálogo `sondas.normas_leg`.

Contrato observado. `GET /api/public/normas?urn=urn:lex:br:federal:<tipo>:<ano>;<número>&tipo_documento=maior-detalhe`
aceita a URN só com o ano e devolve JSON-LD (`@type: Legislation`) com `legislationIdentifier`
completo (data), `abstract`, `encoding[]` (cada texto: `version` `Original` ou `Current`,
`name`, `contentUrl`, `legislationLegalValue`, `datePublished`, `license`) e, em parte das
normas, `hasPart` (texto estruturado multivigente). URN inexistente ou com data errada devolve
200 com corpo `{"urn": "<URN consultada>"}` e nada mais. O texto `Current` é a "Compilação
Monovigente na CD" (Câmara dos Deputados); o `Original` reproduz a publicação no DOU. Ambos
trazem `legislationLegalValue: UnofficialLegalValue`; o cliente oficial exibe "Este texto não
substitui o publicado no Diário Oficial".

## 3. Decisão

1. Novo conector `normas_leg` (fonte `normas.leg.br`, editor Congresso Nacional), rota sob
   demanda para legislação federal: leis, leis complementares, decretos, decretos-leis,
   medidas provisórias (inclusive reedições `NNNN-RR`), decretos legislativos, emendas
   constitucionais e Constituição. Toda requisição pelo transporte comum, UA identificado, sem
   repetição em 403/429/desafio, robots lido e aplicado (RFC 9309, fechado em caso de dúvida),
   intervalo mínimo por host e teto por chamada pública.
2. A rota entra em `LEGIS_CONNECTORS` e `LEGIS_NOVA_CAPTURA`: busca e captura indexada sob
   demanda, com hash, URL, instante, versão do texto (`Current`/`Original`), valor legal
   declarado e licença na evidência.
3. **Sem `verified` por esta rota** até qualificação própria. A verificação que dependa só de
   texto obtido por `normas_leg` devolve `unknown` com motivo `rota_nao_qualificada`, o texto
   do dispositivo, a âncora e a evidência. `listar_fontes` e a matriz mostram a rota como
   `nao_apurada`. É a "capacidade parcial rotulada" prevista na 0084 §2, item 4.
4. A rota não substitui nem contorna o Planalto ou a Câmara: é outra editora, com permissão
   própria. Recusa, desafio ou bloqueio em `normas.leg.br` seguem a tabela de barreiras e não
   abrem rota alternativa.
5. Atribuição obrigatória em toda saída que reproduza texto: "Fonte: normas.leg.br (Congresso
   Nacional), licença CC BY 4.0; texto sem valor oficial".

## 4. Instalador em contexto empacotado

O instalador e o `doctor` detectam a execução dentro de pacote MSIX (`GetCurrentPackageFullName`
diferente de `APPMODEL_ERROR_NO_PACKAGE`). Nesse caso o instalador não grava o home no caminho
virtualizado: relança a si mesmo fora do contêiner (processo criado por WMI, que não herda a
virtualização) e espera o resultado, ou, se o relançamento falhar, aborta com mensagem que
indica o terminal comum. O `doctor` alerta `home_virtualizado` quando o home resolvido estiver
sob `%LOCALAPPDATA%\Packages\`.

## 5. Questões abertas

1. Qualificação da rota `normas_leg` (conjunto de desenvolvimento, pisos, reserva) antes de
   qualquer `verified`.
2. Uso do texto estruturado (`hasPart`, multivigente) para aritmética temporal por dispositivo.
3. Comunicação ao Senado sobre o uso da API pública pelo cliente identificado, a critério do
   titular.
4. Quarentena do perfil `normas_leg` (núcleo do parser da Câmara) em documentos antigos, apurada
   ao vivo em 14/11: CTN (`TRUNCATED` nos arts. 63, 74, 90 e 96), Decreto-Lei 2.627/1940
   (`TRUNCATED`, `ORDER` no art. 54) e Decreto 3.000/1999 (`ORDER` no art. 1º: regulamento anexo
   reinicia a numeração). A rota captura o documento, mas não devolve trecho de documento em
   quarentena. A quarentena não é afrouxada para servir extração; a correção é do parser.

## 6. Ordem das fontes e correções da auditoria (14/11/2026)

1. Obra federal: Câmara primeiro; `normas_leg` só depois, e só quando a Câmara responde
   ausência explícita ou motivo de alcance (`ativacao_ao_vivo_pendente`,
   `especie_busca_nao_demonstrada`). Falha de integridade ou barreira da Câmara não é encoberta
   (0058, com esta restrição). A primeira implementação punha `normas_leg` no lugar da Câmara:
   5.127 erros na suíte local e o CI reprovado em todas as combinações; corrigido.
2. B1: a trava `rota_nao_qualificada` reconhece a procedência por qualquer sinal (`source_id`,
   perfil, bloco `normas_leg_metadados` ou host `normas.leg.br`); trocar rótulos não promove a
   `verified`. Regressão com os bytes reais da LC 118.
3. B2 (BCB): página toda filtrada com resultados não examinados é
   `unavailable(resposta_parcial_sem_correspondencia)`, não ausência; o candidato sintético
   continua restrito a ausência explícita.
4. I3: seleção por `normas_leg` com `versao="vigente"` aceita só `Current` (ou `Original` quando a
   norma não tem compilação).
5. I4: removido `-PermitirVirtualizado` do instalador; teste de sintaxe do script no PowerShell.
6. I5: recibos formais das sondas dos dois scripts e dos metadados em
   `docs/auditoria/1.4.0/normas-leg-sondas/`, com os trechos e offsets.

## 7. Verificação ao vivo (14/11/2026, home temporário)

`doctor` da fonte: positivo `ok`, negativo `zero`, documento `ok` (LC 118, `Original`).
`verifica`: art. 1º da MP 2.158-35/2001 e art. 3º da LC 118/2005 devolvem
`unknown`/`rota_nao_qualificada` com o trecho do dispositivo, URL do binário,
`versao_texto` e `UnofficialLegalValue`; art. 116 do DL 2.627/1940 e do CTN, mesmo rótulo,
com evidência e sem trecho (item 4).
