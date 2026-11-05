# IL.2-a: rotas de legislação, o que a documentação oficial promete

| Campo | Valor |
|---|---|
| Ferramenta / modelo | Claude Code (Agent SDK), Claude Sonnet 5.5 (`claude-sonnet-5-5`) |
| Ramo / base | `feat/il2-sondas` sobre `main` 3686cdb |
| Escopo | catálogo `freoa_verifica/sondas.py` (5 fontes), roteiro em `docs/S0-SONDAS.md`, testes em `tests/test_sondas.py`. Sem adaptador, sem conector, sem `registry()`, sem acesso ao vivo pelo produto |
| Leituras | 04/11/2026, pela ferramenta de pesquisa do agente (WebFetch/WebSearch), não pelo produto nem pelo instrumento; não valem como sonda. Nenhuma sonda havia sido executada nesta etapa de documentação; resultados posteriores na seção "Resultado das sondas" |

Este documento diz o que a documentação oficial lida **promete**. O que só a resposta de cada rota mostra (campos, texto por dispositivo, anexos, vigência) fica em aberto até a sonda do supervisor. Capacidades da matriz da Porta L (`il1-matriz-porta-l.md`, seção 1): (a) texto publicado; (b) consolidado vigente; (c) redação em data D; (d) anexos; (e) remissões.

## O que cada rota promete

| Fonte (id) | Página oficial lida | Promessa documentada | (a) | (b) | (c) | (d) | (e) |
|---|---|---|---|---|---|---|---|
| Senado, Dados Abertos (`senado_legislacao`) | especificação OpenAPI `legis.senado.leg.br/dadosabertos/v3/api-docs`; catálogo `www12.senado.leg.br/dados-abertos/conjuntos?portal=Legislativo&grupo=legislacao` | detalhe de norma por URN (`/legislacao/urn`), por código, por tipo/número/ano; pesquisa de normas federais; tabelas de tipos, inclusive "Vide" (normas e dispositivos relacionados); xml, json, csv por extensão ou `Accept`; sem autenticação | não documentado | não documentado | não documentado | não documentado | "Vide" é a única relação descrita; sem campos de resposta na documentação lida |
| LexML (`lexml`) | `www12.senado.leg.br/dados-abertos/legislativo/legislacao/acervo-do-portal-lexml` | API por URL, padrão SRU, resposta XML; acervo do portal LexML. O link de exemplo oficial aponta `www.lexml.gov.br/busca/SRU?operation=searchRetrieve&query=urn = "..."` | não documentado | não documentado | não documentado | não documentado | não documentado |
| normas.leg.br (`normas_leg`) | notícia oficial do Senado de 13/11/2025 | portal conjunto Câmara e Senado (Ato Conjunto 2/2021), fontes Sigen e Legin, "consultas detalhadas por versão", visões hierárquica e cronológica de alterações | a página sugere versões; sem rota nem formato | a página sugere versões; sem rota | a página sugere consulta por versão; sem rota | não documentado | não documentado |
| Câmara (`camara_legislacao`) | `www.camara.leg.br/legislacao` e páginas da Legislação Informatizada | por norma, "Publicação Original" (com a edição do Diário ou Boletim) e "Dados da Norma" (origem, situação, vide, indexação); pesquisa por tipo, número, ano e assunto | página de publicação original existe por norma | não vista na página lida | não documentado | não documentado | "Vide" apenas |
| DOU / Imprensa Nacional (`dou`) | `github.com/Imprensa-Nacional` e README do INLABS | edições completas em PDF e XML, livre e gratuito desde 01/01/2020, só os últimos 4 meses no INLABS; períodos anteriores nas coleções de Dados Abertos | publicação do ato (o DOU é o veículo) | não aplicável (não consolida) | não aplicável | não documentado | não documentado |

Leitura das células: "não documentado" significa que a página oficial lida não o diz, não que a rota não o faça. As células de (a) a (e) que dependem de campo, texto por dispositivo ou anexo são perguntas da sonda; nenhuma é afirmada aqui. A Porta L não depende da promessa: depende do teste de equivalência (IL.3) e da apuração da matriz.

## Rotas catalogadas e níveis

| Fonte | Host | Rotas (caminho exato) | Nível |
|---|---|---|---|
| `senado_legislacao` | `legis.senado.leg.br` | `/dadosabertos/legislacao/urn.json` (consulta), `/dadosabertos/legislacao/lista.json` (consulta), `/dadosabertos/legislacao/LEI/6404/1976.json` | A no caminho (especificação oficial), T nos valores (URN LEX, sigla) |
| `lexml` | `www.lexml.gov.br` | `/busca/SRU` (consulta) | A no host e caminho; T no índice `urn` e no valor |
| `normas_leg` | `normas.leg.br` | só `robots.txt` | A no host; texto por dispositivo: B |
| `camara_legislacao` | `www.camara.leg.br`, `www2.camara.leg.br` | `/legislacao`; só `robots.txt` em www2 | A; página de norma: B |
| `dou` | `www.in.gov.br` | só `robots.txt` | A no host; texto publicado: B |

Nível B (caminho só de busca ou de projeto de terceiros) não entra no catálogo e aparece no roteiro como linha bloqueada, sem comando:

- `normas.leg.br`, API pública de texto por dispositivo: a base e o formato da URN com sufixo de dispositivo vêm só do br-eli-mcp. O br-eli-mcp é referência de engenharia, não fonte de URL oficial.
- Câmara, página de norma: o identificador numérico do slug (`.../legin/...-norma-...html`, `...-publicacaooriginal-...html`) só sai da busca do portal; o da Lei 6.404/1976 não foi obtido.
- Senado, `legis.senado.leg.br/norma/{id}/publicacao/{id}`: apareceu só em resultado de busca.
- DOU, texto publicado: nenhuma rota lida (a página de dados abertos do portal não pôde ser lida: a conexão caiu).
- LexML, resolvedor de URN e documentação do webservice: a página oficial de documentação do Senado redireciona ao padrão SRU da Library of Congress, sem endereço nem índices do LexML.

## O que fica fora

- **INLABS** (`inlabs.in.gov.br`): exige cadastro e login. É sessão assistida (decisão 0067), nunca automatizada; não tem comando no roteiro e está em `HOSTS_RECUSADOS`. A página inicial estava em manutenção e indicava a "Base de Dados de Publicações do DOU" do portal da Imprensa Nacional, sem rota lida.
- **API de Dados Abertos da Câmara** (`dadosabertos.camara.leg.br`): a página lida descreve proposições, legislaturas e arquivos em massa, nenhum endpoint de legislação; em `HOSTS_RECUSADOS`.
- Planalto: acervo legado, já no produto (`planalto`); fora desta entrega.
- `projeto.lexml.gov.br` e `www12.senado.leg.br`: documentação, não fonte de normas.

## Termos de uso e licença

- Senado: a página de dados abertos diz que os dados são "disponibilizados sob licença que permita sua livre utilização"; a Política de uso do portal foi citada e não lida. A especificação avisa que mais de 10 requisições por segundo recebem 429 e que o serviço pode dar 503 em alta demanda.
- Câmara: link "Termos de uso e política de privacidade" no rodapé, não lido; nenhuma licença explícita no conteúdo lido.
- DOU: README do INLABS, "livre e gratuito desde 01/01/2020".
- LexML e normas.leg.br: nenhuma página oficial de termos lida.

Termos não lidos não são afirmados: ficam como pendência do titular antes de qualquer adaptador.

## Para o supervisor

- Uma requisição por comando, `robots.txt` primeiro por host, regra de parada do roteiro. Linhas T (URN LEX, sigla, índice SRU) são inferência: se a sonda as refutar, o resultado vira pendência IL.2-b, sem descoberta fora do instrumento.
- Casos da sonda: Lei 6.404/1976 (consulta neutra), Lei Complementar 123/2006 (lei com anexos, capacidade d) e MP 881/2019 convertida na Lei 13.874/2019 (capacidade c). A escolha das duas últimas e as datas das URN são de conhecimento do autor, não conferidas em página oficial lida.
- Pendência IL.2-b: texto por dispositivo no normas.leg.br, página de norma da Câmara e texto publicado no DOU, que só entram por documentação oficial lida ou sessão assistida.
- Novo no catálogo: sufixo `.leg.br` na checagem de domínio oficial dos testes e `_MIMES_XML` para o SRU.


## Resultado das sondas

Em 04/11/2026, o supervisor executou pelo instrumento as sondas descritas no [registro IL.2-a](il2a-sondas.md), com UA `freoa-verifica/1.4.0a2 (+https://github.com/rickfreoa/freoa-verifica)`. A tabela de rotas acima registra o estado anterior às sondas; o estado atual é:

| Fonte | Evidência | Consequência no catálogo / roteiro |
|---|---|---|
| `senado_legislacao` | robots 403, `http_403`, `recusa_identificado` | Fonte barrada e host recusado, sem comandos executáveis nem nova tentativa |
| `dou` | robots 403, `http_403`, `recusa_identificado` | Fonte barrada e host recusado, sem comandos executáveis nem nova tentativa |
| `lexml` | robots 200; `Disallow: /busca/` | `/busca/SRU` retirada e não sondada; só robots. `Allow: /urn` e `/sru` não documenta endpoint; página oficial lida e `Crawl-delay: 5` pendentes IL.2-b (instrumento sem interpretação do intervalo) |
| `normas_leg` | robots 200, `Allow: /` | Continua só robots, sem rota documentada de conteúdo |
| `camara_legislacao` | robots 200 nos dois hosts; `/legislacao` 200 HTML, 59.842 bytes | Mantida só página de entrada e robots; formulário `/legislacao/busca`, `/legislacao/pesquisa-avancada` e coleções www2 observados, sem sondar ou catalogar novas rotas |

Os sete registros e quatro corpos de robots estão em [il2a-sondas/](il2a-sondas/), sem caminhos de máquina. HTML da Câmara não versionado; SHA-256: `2735440e8cc2c54f71b610af8b0dd38fcb0a46110ef1b9b667b20cc90bda49f1`. Nenhuma captura deste lote demonstra rota viva para (a) texto publicado, (b) consolidado vigente, (c) redação em data D, (d) anexos ou (e) remissões resolvidas. Isso não é apuração da Porta L nem conclusão sobre outras fontes ou acervo instalado. Nenhum acesso de rede foi executado na consolidação dos registros.
