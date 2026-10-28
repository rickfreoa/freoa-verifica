# S0: roteiro das sondas (plano 1.4.0)

Roteiro executável pelo supervisor, no notebook com IP brasileiro, depois da auditoria deste instrumento. Nada aqui foi executado ao vivo pelo instrumento: as URLs vêm das páginas oficiais registradas em `freoa_verifica/sondas.py` (campos `origem_hosts` e `confirmacao`) e em `docs/auditoria/1.4.0/s0-instrumento.md`. Nenhum host deve ser tomado como confirmado só por constar do catálogo: os de nível B estão bloqueados (ver abaixo).

## Regras da sonda

- Só pelo instrumento: `scripts/capturar_fixture.py --fonte-sonda <id> --sonda`. Pedido único (GET) pelo transporte comum, UA identificado do pacote, allowlist de host, caminho EXATO e MIME da fonte (a rota é igualdade de caminho: `/config.json.bak` ou um segmento extra não são a rota; consulta `?` só na rota declarada com parâmetros), sem host de escopo livre e sem seguir redirecionamento. URL fora da allowlist é recusada antes da rede. O instrumento não faz POST em fonte-sonda.
- Primeiro e único acesso: a sonda do instrumento no notebook é o primeiro e único acesso do produto a cada fonte. Se responder 403 ou outra recusa (desafio, WAF, 429, 5xx), a fonte fica registrada como barreira e não há nova tentativa por outra rede ou rota (regra 3). Vale para o BNP e qualquer outra fonte; o DJEN segue a decisão 0069. Leituras anteriores de páginas e `robots.txt` foram feitas pela ferramenta de pesquisa do agente, não pelo produto, e não substituem a sonda nem a repetem.
- Barreira (desafio, WAF, recusa, 403/5xx) vira `unavailable(motivo)` (decisão 0045). A categoria vem quando a decisão a dá (`ambiental_desafio`, `recusa_identificado`, `fonte_fora`, `resposta_inesperada`); 429 e outros status sem regra própria saem sem categoria (`categoria: null`), só com motivo e evidência. Registre e siga: não repita em laço, não troque UA, IP ou rota, não resolva CAPTCHA.
- Sequência por host: o `robots.txt` do próprio host é o primeiro comando dele. O instrumento o pede só na forma exata `/robots.txt`, aceita só `text/plain` e não segue redirecionamento. Leia o `.captura.json` do robots antes de qualquer outro comando do host:

| Resposta do robots.txt | Decisão |
|---|---|
| 200 `text/plain` interpretável, sem `Disallow` aplicável ao caminho do roteiro | seguir com os comandos daquele host |
| 200 `text/plain` interpretável, com `Disallow` aplicável a um caminho | não sondar esse caminho; registrar o fato como achado |
| desafio, erro (qualquer status diferente de 200, inclusive 404 e 429), redirecionamento, HTML ou conteúdo que não seja `text/plain` interpretável | PARAR: permissão indeterminada; nenhum outro comando daquele host; registrar como barreira |

  A regra de erro é mais conservadora que o RFC 9309 (que trata 4xx como ausência de restrições) por decisão do supervisor de 28/10/2026.
- Consulta neutra: `acordo de acionistas` (ou `sociedade anônima`). Nenhum dado de cliente, número de processo ou nome de parte.
- Nível de cada linha: "P" = `robots.txt` (RFC 9309). "A" = URL lida em página oficial (ou publicada pelo próprio portal). "B" = host indexado por busca, não lido em página oficial: bloqueado. "T" = caminho lido em página oficial com parâmetros inferidos; a sonda confirma ou refuta, e, se refutar, o resultado vira pendência S0b: não se descobre endpoint por navegador nem fora do instrumento.
- Bloqueio de host B: as sondas em host de nível B ficam bloqueadas até confirmação documental (página oficial lida ou confirmação do titular). O instrumento as recusa (saída 2, antes da rede, inclusive o `robots.txt`) sem `--confirmado-por-titular`; com a flag, o `.captura.json` registra `confirmado_por_titular: true` e `confirmacao_host: "B"`. Nenhum host de nível B foi confirmado.
- Saída: `C:/dev/fv14-sondas/<id>/` (fora do repositório; o instrumento recusa destino dentro dele). Cada comando leva `--chave <fonte>_<etapa>` distinta e gera `<chave>.<ext>` (corpo, só se 200) e `<chave>.captura.json` (registro). O instrumento recusa gravar sobre `.captura.json` (ou corpo) já existente: evidência não se sobrescreve, e refazer um comando exige chave nova e motivo registrado (nunca após barreira).

## Como ler cada registro (`.captura.json`)

| Pergunta | Onde olhar |
|---|---|
| Alcançável? | `unavailable` (false = 200 recebido), `status`, `url_final` (redirecionou para outro host?) |
| Barreira? | `unavailable: true` com `motivo`, `categoria` (quando houver) e `evidencia` (status, marcador, cabeçalho) |
| Formato? | `content_type`, extensão do corpo, primeiros bytes: HTML de página, JSON de API, casca de SPA sem lista |
| Contagem total utilizável para volume? | No corpo: campo de total (JSON) ou texto "de N" (HTML). Anote nome do campo, valor, se é exato ou cota inferior, tamanho da página (`bytes` por página) |
| Campos pesquisados? | Ementa, metadados (órgão, relator, datas, classe) e inteiro teor: o que o resultado traz e se há link estável por documento (PDF/HTML) |
| Quem serviu? | `fonte_sonda`, `user_agent`, `capturado_em`, `cabecalhos`, `confirmacao_host`, `confirmado_por_titular` |

## Fontes com barreira registrada (fora do roteiro)

Fonte que já respondeu recusa (403, desafio, robots) a uma leitura registrada sai (exceto o DJEN, decisão 0069: o 403 de nuvem fora do Brasil não é recusa ao produto) do catálogo e do roteiro, e o instrumento a recusa antes da rede (`FONTES_BARRADAS`). Não há comando, nova tentativa, outra rede nem outra rota. Acesso só por decisão do titular, por sessão assistida (decisão 0067) ou por documentação oficial de acesso.

(nenhuma fonte barrada no momento)

## Comandos por fonte

PowerShell, na raiz do repositório, com o venv ativado. As aspas duplas protegem o `&` das URLs. Blocos `powershell` são liberados; blocos `powershell-bloqueado` são de host nível B e o instrumento os recusa sem `--confirmado-por-titular`.

### tst: TST: pesquisa de jurisprudência (portal, backend REST e consulta de documento)

Hosts e rotas do catálogo: `consultadocumento.tst.jus.br`: só `robots.txt`; `jurisprudencia-backend.tst.jus.br`: `/rest/orgaos-judicantes`, `/rest/indicadores`; `jurisprudencia.tst.jus.br`: `/config.json`. Confirmação: A.

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt do portal | P | liberada |
| 2 | configuração pública do portal | A | liberada |
| 3 | robots.txt do backend | P | liberada |
| 4 | órgãos judicantes (GET publicado no código do portal) | A | liberada |
| 5 | indicadores (GET publicado no código do portal; candidato a volume) | A | liberada |

```powershell
python scripts/capturar_fixture.py --fonte-sonda tst --sonda --saida C:/dev/fv14-sondas/tst --chave tst_robots_portal --url "https://jurisprudencia.tst.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tst --sonda --saida C:/dev/fv14-sondas/tst --chave tst_config --url "https://jurisprudencia.tst.jus.br/config.json"
python scripts/capturar_fixture.py --fonte-sonda tst --sonda --saida C:/dev/fv14-sondas/tst --chave tst_robots_backend --url "https://jurisprudencia-backend.tst.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tst --sonda --saida C:/dev/fv14-sondas/tst --chave tst_orgaos --url "https://jurisprudencia-backend.tst.jus.br/rest/orgaos-judicantes"
python scripts/capturar_fixture.py --fonte-sonda tst --sonda --saida C:/dev/fv14-sondas/tst --chave tst_indicadores --url "https://jurisprudencia-backend.tst.jus.br/rest/indicadores"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: A pesquisa textual é POST JSON em `/rest/pesquisa-textual/`: o instrumento só faz GET, então a contagem do resultado por consulta não sai desta sonda (pendência S0b). A raiz do portal não é sondada: o transporte não admite `/` como prefixo. `/rest/indicadores` e `/rest/orgaos-judicantes` são GET publicados no código do próprio portal e podem trazer totais por tipo de documento.

### stf_acordaos: STF: pesquisa de jurisprudência (acórdãos)

Hosts e rotas do catálogo: `jurisprudencia.stf.jus.br`: `/pages/search`. Confirmação: A.

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt | P | liberada |
| 2 | página de pesquisa (link do portal oficial) | A | liberada |

```powershell
python scripts/capturar_fixture.py --fonte-sonda stf_acordaos --sonda --saida C:/dev/fv14-sondas/stf_acordaos --chave stf_acordaos_robots --url "https://jurisprudencia.stf.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda stf_acordaos --sonda --saida C:/dev/fv14-sondas/stf_acordaos --chave stf_acordaos_pesquisa --url "https://jurisprudencia.stf.jus.br/pages/search"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: A página é aplicação de página única: o achado esperado é desafio do WAF (já declarado no conector `stf`) ou casca vazia. O endpoint de resultado não consta de página oficial lida: fora da S0, pendência S0b.

### bnp: CNJ: Banco Nacional de Precedentes (Pangea/BNP)

Hosts e rotas do catálogo: `bnp.pdpj.jus.br`: só `robots.txt`; `pangeabnp.pdpj.jus.br`: só `robots.txt`. Confirmação: A.

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt do Pangea | P | liberada |
| 2 | robots.txt do alias do CNJ | P | liberada |

```powershell
python scripts/capturar_fixture.py --fonte-sonda bnp --sonda --saida C:/dev/fv14-sondas/bnp --chave bnp_robots_pangea --url "https://pangeabnp.pdpj.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda bnp --sonda --saida C:/dev/fv14-sondas/bnp --chave bnp_robots_cnj --url "https://bnp.pdpj.jus.br/robots.txt"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: Aplicação de página única; nenhuma rota consta de página oficial lida (a raiz não é admitida pelo transporte), então a sonda desta fonte é só o `robots.txt` de cada host. Se um deles responder 403 ou outra recusa, o BNP fica registrado como barreira, sem nova tentativa por outra rede ou rota (regra 3). Endpoint de pesquisa e de resultado: pendência S0b.

### djen: CNJ: Diário de Justiça Eletrônico Nacional (consulta pública)

Hosts e rotas do catálogo: `comunica.pje.jus.br`: `/consulta`; `comunicaapi.pje.jus.br`: só `robots.txt`. Confirmação: A.

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt da consulta | P | liberada |
| 2 | página de consulta pública | A | liberada |
| 3 | robots.txt da API | P | liberada |

```powershell
python scripts/capturar_fixture.py --fonte-sonda djen --sonda --saida C:/dev/fv14-sondas/djen --chave djen_robots_consulta --url "https://comunica.pje.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda djen --sonda --saida C:/dev/fv14-sondas/djen --chave djen_consulta --url "https://comunica.pje.jus.br/consulta"
python scripts/capturar_fixture.py --fonte-sonda djen --sonda --saida C:/dev/fv14-sondas/djen --chave djen_robots_api --url "https://comunicaapi.pje.jus.br/robots.txt"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: Fonte sujeita à decisão 0069 (`docs/decisoes/0069-djen-restricao-geografica.md`): a API responde 403 a origem fora do Brasil; só o notebook do titular, no Brasil, pelo transporte comum, UA identificado, uma requisição por comando, sem repetição, sem proxy, VPN ou túnel. O 403 de 27/10/2026 foi da ferramenta de pesquisa em nuvem, fora do produto e fora do Brasil, sem valor de evidência (0069, item 5). Se a sonda do notebook receber recusa (403, desafio, bloqueio), a fonte vira barreira, sem nova tentativa por outra rede, rota ou identidade (0069, item 4); o caminho passa a ser a sessão assistida (0067) ou o pedido formal de acesso. A página oficial do CNJ documenta `/api/v1` como API de envio dos tribunais, com autenticação: não é sondada. A consulta pública pela API não está documentada em página oficial: fora da S0, pendência S0b. Leituras anteriores desse host foram feitas pela ferramenta de pesquisa do agente, não pelo produto (ver registro da auditoria); a sonda do instrumento no notebook é o primeiro e único acesso do produto. Pergunta própria: o DJEN é publicação de comunicações, não acervo de acórdãos: verifique se o texto traz ementa/inteiro teor ou só o ato.

### cjf_unificada: CJF: pesquisa unificada de jurisprudência da Justiça Federal

Hosts e rotas do catálogo: `jurisprudencia.cjf.jus.br`: só `robots.txt`; `www.cjf.jus.br`: `/jurisprudencia/unificada/`. Confirmação: B (hosts B: `www.cjf.jus.br`).

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt de jurisprudencia.cjf.jus.br | P | liberada |
| 2 | robots.txt do portal do CJF (host B) | P | bloqueada até confirmação documental (página oficial lida ou confirmação do titular) |
| 3 | página oficial no portal do CJF (host B) | B | bloqueada até confirmação documental (página oficial lida ou confirmação do titular) |

```powershell
python scripts/capturar_fixture.py --fonte-sonda cjf_unificada --sonda --saida C:/dev/fv14-sondas/cjf_unificada --chave cjf_unificada_robots_jurisprudencia --url "https://jurisprudencia.cjf.jus.br/robots.txt"
```

```powershell-bloqueado
python scripts/capturar_fixture.py --fonte-sonda cjf_unificada --sonda --saida C:/dev/fv14-sondas/cjf_unificada --chave cjf_unificada_robots_portal --url "https://www.cjf.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda cjf_unificada --sonda --saida C:/dev/fv14-sondas/cjf_unificada --chave cjf_unificada_pagina_portal --url "https://www.cjf.jus.br/jurisprudencia/unificada/"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: `jurisprudencia.cjf.jus.br` só tem rota documentada na raiz, fora do escopo: só `robots.txt`. `www.cjf.jus.br` é nível B (indexado, não lido): bloqueado. Parâmetros e endpoint de resultado: pendência S0b.

### trf1: TRF1: pesquisa de jurisprudência (via CJF) e inteiro teor de acórdãos

Hosts e rotas do catálogo: `arquivo.trf1.jus.br`: só `robots.txt`; `jurisprudencia.cjf.jus.br`: só `robots.txt`. Confirmação: A.

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt da pesquisa (CJF) | P | liberada |
| 2 | robots.txt do inteiro teor | P | liberada |

```powershell
python scripts/capturar_fixture.py --fonte-sonda trf1 --sonda --saida C:/dev/fv14-sondas/trf1 --chave trf1_robots_cjf --url "https://jurisprudencia.cjf.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda trf1 --sonda --saida C:/dev/fv14-sondas/trf1 --chave trf1_robots_arquivo --url "https://arquivo.trf1.jus.br/robots.txt"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: O menu oficial do TRF1 leva a pesquisa ao CJF (`?tribunal=trf1`) e o inteiro teor a `arquivo.trf1.jus.br`; as rotas documentadas são raízes, fora do escopo: só `robots.txt`. Endpoint de resultado e URL estável de inteiro teor: pendência S0b.

### trf2: TRF2: portal de jurisprudência da 2ª Região

Hosts e rotas do catálogo: `jurisprudencia.trf2.jus.br`: só `robots.txt`; `www10.trf2.jus.br`: `/consultas/servicos/jurisprudencia/`. Confirmação: A.

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt do portal | P | liberada |
| 2 | robots.txt de consultas | P | liberada |
| 3 | página de serviço | A | liberada |

```powershell
python scripts/capturar_fixture.py --fonte-sonda trf2 --sonda --saida C:/dev/fv14-sondas/trf2 --chave trf2_robots_portal --url "https://jurisprudencia.trf2.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda trf2 --sonda --saida C:/dev/fv14-sondas/trf2 --chave trf2_robots_servicos --url "https://www10.trf2.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda trf2 --sonda --saida C:/dev/fv14-sondas/trf2 --chave trf2_servico --url "https://www10.trf2.jus.br/consultas/servicos/jurisprudencia/"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: A página oficial informa que o portal pesquisa ementas, inteiro teor, decisões monocráticas, súmulas e acórdãos históricos. A raiz do portal fica fora (só `robots.txt`); endpoint de resultado: pendência S0b.

### trf3: TRF3: busca de jurisprudência e acórdãos

Hosts e rotas do catálogo: `web.trf3.jus.br`: `/jurisprudencia`, `/acordaos/Acordao`. Confirmação: A.

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt | P | liberada |
| 2 | busca de jurisprudência | A | liberada |
| 3 | consulta de acórdãos | A | liberada |

```powershell
python scripts/capturar_fixture.py --fonte-sonda trf3 --sonda --saida C:/dev/fv14-sondas/trf3 --chave trf3_robots --url "https://web.trf3.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda trf3 --sonda --saida C:/dev/fv14-sondas/trf3 --chave trf3_busca --url "https://web.trf3.jus.br/jurisprudencia"
python scripts/capturar_fixture.py --fonte-sonda trf3 --sonda --saida C:/dev/fv14-sondas/trf3 --chave trf3_acordaos --url "https://web.trf3.jus.br/acordaos/Acordao"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: O serviço de acórdãos da carta de serviços é consulta por número de processo; a busca por texto está em `/jurisprudencia`. Endpoint de resultado: pendência S0b.

### tjac: e-SAJ, consulta de jurisprudência de 2º grau (cjsg) do TJAC

Hosts e rotas do catálogo: `esaj.tjac.jus.br`: `/cjsg/consultaCompleta.do`, `/cjsg/resultadoCompleta.do`. Confirmação: A.

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt | P | liberada |
| 2 | página de pesquisa | A | liberada |
| 3 | resultado (consulta neutra; caminho lido em página oficial, parâmetros inferidos) | T | liberada |

```powershell
python scripts/capturar_fixture.py --fonte-sonda tjac --sonda --saida C:/dev/fv14-sondas/tjac --chave tjac_robots --url "https://esaj.tjac.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjac --sonda --saida C:/dev/fv14-sondas/tjac --chave tjac_consulta --url "https://esaj.tjac.jus.br/cjsg/consultaCompleta.do"
python scripts/capturar_fixture.py --fonte-sonda tjac --sonda --saida C:/dev/fv14-sondas/tjac --chave tjac_resultado --url "https://esaj.tjac.jus.br/cjsg/resultadoCompleta.do?dados.buscaInteiroTeor=acordo+de+acionistas&dados.pesquisarComSinonimos=S&dados.origensSelecionadas=T&tipoDecisaoSelecionados=A&dados.ordenarPor=dtPublicacao"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: O e-SAJ do TJSP exige POST com sessão (cookie JSESSIONID) para o resultado: se o GET voltar 405, redirecionamento para a página de consulta ou página sem a lista, o achado é esse, e o modo POST com sessão vira pendência (S0b). A contagem, quando houver, aparece no cabeçalho da lista ("Resultados 1 a N de M"). Se a sonda refutar o padrão de parâmetros, não se descobre o GET real por navegador: fica como pendência S0b.

### tjal: e-SAJ, consulta de jurisprudência de 2º grau (cjsg) do TJAL

Hosts e rotas do catálogo: `www2.tjal.jus.br`: `/cjsg/consultaCompleta.do`. Confirmação: B (hosts B: `www2.tjal.jus.br`).

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt (host B) | P | bloqueada até confirmação documental (página oficial lida ou confirmação do titular) |
| 2 | página de pesquisa (host B) | B | bloqueada até confirmação documental (página oficial lida ou confirmação do titular) |

```powershell-bloqueado
python scripts/capturar_fixture.py --fonte-sonda tjal --sonda --saida C:/dev/fv14-sondas/tjal --chave tjal_robots --url "https://www2.tjal.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjal --sonda --saida C:/dev/fv14-sondas/tjal --chave tjal_consulta --url "https://www2.tjal.jus.br/cjsg/consultaCompleta.do"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: Host nível B (indexado, não lido): bloqueado. Rota de resultado não documentada em página oficial lida: pendência S0b. O e-SAJ do TJSP exige POST com sessão (cookie JSESSIONID) para o resultado: se o GET voltar 405, redirecionamento para a página de consulta ou página sem a lista, o achado é esse, e o modo POST com sessão vira pendência (S0b). A contagem, quando houver, aparece no cabeçalho da lista ("Resultados 1 a N de M").

### tjam: e-SAJ, consulta de jurisprudência de 2º grau (cjsg) do TJAM

Hosts e rotas do catálogo: `consultasaj.tjam.jus.br`: `/cjsg/consultaCompleta.do`. Confirmação: B (hosts B: `consultasaj.tjam.jus.br`).

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt (host B) | P | bloqueada até confirmação documental (página oficial lida ou confirmação do titular) |
| 2 | página de pesquisa (host B) | B | bloqueada até confirmação documental (página oficial lida ou confirmação do titular) |

```powershell-bloqueado
python scripts/capturar_fixture.py --fonte-sonda tjam --sonda --saida C:/dev/fv14-sondas/tjam --chave tjam_robots --url "https://consultasaj.tjam.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjam --sonda --saida C:/dev/fv14-sondas/tjam --chave tjam_consulta --url "https://consultasaj.tjam.jus.br/cjsg/consultaCompleta.do"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: Host nível B (indexado, não lido): bloqueado. Rota de resultado não documentada em página oficial lida: pendência S0b. O e-SAJ do TJSP exige POST com sessão (cookie JSESSIONID) para o resultado: se o GET voltar 405, redirecionamento para a página de consulta ou página sem a lista, o achado é esse, e o modo POST com sessão vira pendência (S0b). A contagem, quando houver, aparece no cabeçalho da lista ("Resultados 1 a N de M").

### tjms: e-SAJ, consulta de jurisprudência de 2º grau (cjsg) do TJMS

Hosts e rotas do catálogo: `esaj.tjms.jus.br`: `/cjsg/consultaCompleta.do`. Confirmação: B (hosts B: `esaj.tjms.jus.br`).

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt (host B) | P | bloqueada até confirmação documental (página oficial lida ou confirmação do titular) |
| 2 | página de pesquisa (host B) | B | bloqueada até confirmação documental (página oficial lida ou confirmação do titular) |

```powershell-bloqueado
python scripts/capturar_fixture.py --fonte-sonda tjms --sonda --saida C:/dev/fv14-sondas/tjms --chave tjms_robots --url "https://esaj.tjms.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjms --sonda --saida C:/dev/fv14-sondas/tjms --chave tjms_consulta --url "https://esaj.tjms.jus.br/cjsg/consultaCompleta.do"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: Host nível B (indexado, não lido): bloqueado. Rota de resultado não documentada em página oficial lida: pendência S0b. O e-SAJ do TJSP exige POST com sessão (cookie JSESSIONID) para o resultado: se o GET voltar 405, redirecionamento para a página de consulta ou página sem a lista, o achado é esse, e o modo POST com sessão vira pendência (S0b). A contagem, quando houver, aparece no cabeçalho da lista ("Resultados 1 a N de M").

### tjrj: TJRJ: eJuris, consulta de jurisprudência

Hosts e rotas do catálogo: `www3.tjrj.jus.br`: `/ejuris/ConsultarJurisprudencia.aspx`. Confirmação: B (hosts B: `www3.tjrj.jus.br`).

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt (host B) | P | bloqueada até confirmação documental (página oficial lida ou confirmação do titular) |
| 2 | página de pesquisa (host B) | B | bloqueada até confirmação documental (página oficial lida ou confirmação do titular) |

```powershell-bloqueado
python scripts/capturar_fixture.py --fonte-sonda tjrj --sonda --saida C:/dev/fv14-sondas/tjrj --chave tjrj_robots --url "https://www3.tjrj.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjrj --sonda --saida C:/dev/fv14-sondas/tjrj --chave tjrj_pesquisa --url "https://www3.tjrj.jus.br/ejuris/ConsultarJurisprudencia.aspx"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: Host nível B: bloqueado. Página `.aspx` (ASP.NET): o resultado costuma exigir POST com campos de estado (`__VIEWSTATE`), que o GET não produz; se a página confirmar isso, o modo POST com estado vira pendência S0b.

### tjmg: TJMG: consulta de jurisprudência

Hosts e rotas do catálogo: `www5.tjmg.jus.br`: `/jurisprudencia/formEspelhoAcordao.do`, `/jurisprudencia/ajuda.do`. Confirmação: A.

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt | P | liberada |
| 2 | formulário de pesquisa | A | liberada |
| 3 | ajuda | A | liberada |

```powershell
python scripts/capturar_fixture.py --fonte-sonda tjmg --sonda --saida C:/dev/fv14-sondas/tjmg --chave tjmg_robots --url "https://www5.tjmg.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjmg --sonda --saida C:/dev/fv14-sondas/tjmg --chave tjmg_formulario --url "https://www5.tjmg.jus.br/jurisprudencia/formEspelhoAcordao.do"
python scripts/capturar_fixture.py --fonte-sonda tjmg --sonda --saida C:/dev/fv14-sondas/tjmg --chave tjmg_ajuda --url "https://www5.tjmg.jus.br/jurisprudencia/ajuda.do"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: Os links oficiais usam `http://`; a sonda exige `https://`, e a resposta diz se o host o serve. O caminho do resultado não consta de página oficial lida: pendência S0b.

### tjrs: TJRS: pesquisa de jurisprudência

Hosts e rotas do catálogo: `www.tjrs.jus.br`: `/novo/buscas-solr/`. Confirmação: B (hosts B: `www.tjrs.jus.br`).

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt (host B) | P | bloqueada até confirmação documental (página oficial lida ou confirmação do titular) |
| 2 | pesquisa de jurisprudência (host B) | B | bloqueada até confirmação documental (página oficial lida ou confirmação do titular) |

```powershell-bloqueado
python scripts/capturar_fixture.py --fonte-sonda tjrs --sonda --saida C:/dev/fv14-sondas/tjrs --chave tjrs_robots --url "https://www.tjrs.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjrs --sonda --saida C:/dev/fv14-sondas/tjrs --chave tjrs_pesquisa --url "https://www.tjrs.jus.br/novo/buscas-solr/"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: Host nível B: bloqueado. A primeira sonda do host é o `robots.txt`, lido com o UA do produto; um `Disallow` aplicável impede o caminho. O `Disallow` do site à ferramenta de pesquisa do agente é política de robots para aquele User-Agent, não recusa ao produto (decisão do supervisor, rodada 3 do PR #14). A ferramenta de pesquisa teve a leitura de `/novo/` recusada pelo robots.txt do site: se, liberado o host, o robots tiver `Disallow` sobre `/novo/buscas-solr/`, NÃO sonde o caminho e registre a recusa como achado (Porta A do TJRS passa pela camada (b)). Resultado: pendência S0b.

### tjpr: TJPR: consulta de jurisprudência

Hosts e rotas do catálogo: `portal.tjpr.jus.br`: `/jurisprudencia/`. Confirmação: A.

| # | O quê | Nível | Estado |
|---|---|---|---|
| 1 | robots.txt | P | liberada |
| 2 | página de pesquisa | A | liberada |

```powershell
python scripts/capturar_fixture.py --fonte-sonda tjpr --sonda --saida C:/dev/fv14-sondas/tjpr --chave tjpr_robots --url "https://portal.tjpr.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjpr --sonda --saida C:/dev/fv14-sondas/tjpr --chave tjpr_pesquisa --url "https://portal.tjpr.jus.br/jurisprudencia/"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: Formulário e resultado da pesquisa pública não constam de página oficial lida: pendência S0b (se o resultado for POST, é a mesma pendência).

## TJSP e TJDFT (conector existente)

Têm conector no produto; a sonda de volume usa o mesmo instrumento com `--conector`, a mesma consulta neutra e o mesmo registro. O resultado do TJSP exige a sessão do conector (modo `--consulta`). O `robots.txt` do host de cada um é o primeiro comando dele, com a mesma regra de parada da seção de regras.

```powershell
python scripts/capturar_fixture.py --conector tjsp --sonda --saida C:/dev/fv14-sondas/tjsp --chave tjsp_robots --url "https://esaj.tjsp.jus.br/robots.txt"
python scripts/capturar_fixture.py --conector tjsp --sonda --saida C:/dev/fv14-sondas/tjsp --chave tjsp_volume1 --consulta '{"termo":"acordo de acionistas","pagina":1}'
python scripts/capturar_fixture.py --conector tjdft --sonda --saida C:/dev/fv14-sondas/tjdft --chave tjdft_robots --url "https://jurisdf.tjdft.jus.br/robots.txt"
python scripts/capturar_fixture.py --conector tjdft --sonda --saida C:/dev/fv14-sondas/tjdft --chave tjdft_volume1 --consulta '{"query":"acordo de acionistas","pagina":1,"tamanho":10}'
```

Contagem total do TJSP: "Resultados 1 a N de M" no HTML do resultado; do TJDFT: `hits.value` no JSON (confira no corpo se o total é exato ou cota inferior).


## Volume: estimativa pelas fontes estatísticas oficiais do CNJ

**Rótulo obrigatório: ESTIMATIVA.** Os números do CNJ medem processos e decisões, não bytes de texto nem acórdãos colegiados pesquisáveis, e são anuais e por tribunal. Citar como estimativa de ordem de grandeza, nunca como volume medido. A medição de volume, tamanho e tempo de indexação é a do notebook (plano, seção 4).

| Fonte | URL | Uso |
|---|---|---|
| Justiça em Números (página do CNJ, edições 2020 a 2026) | https://www.cnj.jus.br/pesquisas-judiciarias/justica-em-numeros/ | Ponto de entrada oficial |
| Relatório Justiça em Números 2026 (PDF, publicado em 2026/06) | https://www.cnj.jus.br/wp-content/uploads/2026/06/relatorio-justica-em-numeros2026-1.pdf | Capítulos por segmento (Justiça Estadual, Federal): casos novos, baixados e decisões por tribunal; 2º grau |
| Relatório Justiça em Números 2025 (PDF) | https://www.cnj.jus.br/wp-content/uploads/2025/11/justica-em-numeros-2025.pdf | Série anterior, para tendência |
| Painel Justiça em Números (interativo) | https://justica-em-numeros.cnj.jus.br/ | Filtro por tribunal, grau e ano |
| Painel de Estatísticas do Poder Judiciário (CNJ) | https://paineis.cnj.jus.br/QvAJAXZfc/opendoc.htm?document=qvw_l%2FPainelCNJ.qvw&host=QVS%40neodimio03&anonymous=true&sheet=shResumoDespFT | Série de casos novos, baixados e pendentes por tribunal e grau |
| Relatório interativo | https://www.cnj.jus.br/relatorio_interativo | Consulta por tribunal |

Como usar, por tribunal do lote 1 (TJSP, TJRJ, TJMG, TJPR, TJDFT) e dos TRF1, TRF2 e TRF3: no relatório ou no painel, tomar o 2º grau do tribunal, o último ano fechado, e ler casos novos e baixados no 2º grau e as decisões colegiadas/terminativas quando o capítulo as separar. Multiplicar por 2 (janela de 24 meses do plano) e por um tamanho médio de texto medido na sonda, e registrar o resultado como "estimativa CNJ x tamanho amostral". Anotar edição do relatório, página ou aba do painel e filtros, para reprodução.

Comparar a estimativa do CNJ com a contagem total de cada sonda (quando houver): divergência grande indica que a ferramenta de pesquisa cobre só parte do acervo ou que o total é cota inferior.


## Pendências conhecidas do instrumento (fora do escopo desta entrega)

- Sem POST nem sessão para fonte-sonda: TST (pesquisa textual), TJRJ (`__VIEWSTATE`), e-SAJ (resultado) e talvez TJPR, STF e BNP só entregam a contagem por POST. Se as sondas confirmarem, abrir S0b: modo `--consulta` para fonte-sonda, reaproveitando `build_cjsg_request` nos quatro e-SAJ, com o mesmo registro e a mesma recusa antes da rede.
- S0b, endpoints: o endpoint de resultado não documentado em página oficial fica fora da S0 (STF acórdãos, BNP, DJEN, CJF, TRF1, TRF2, TRF3, TJMG, TJPR e e-SAJ de TJAL, TJAM e TJMS). Só entra por sessão assistida nos termos da decisão 0067 (o humano resolve a barreira em contexto dedicado, a ferramenta captura os bytes, rótulo `sessao_assistida`) ou por documentação oficial lida. Depois de documentado, entra no roteiro e, se fora das rotas, no catálogo com nova confirmação oficial.
- Hosts de nível B (`www.cjf.jus.br`, TJAL, TJAM, TJMS, TJRJ, TJRS): bloqueados até leitura da página oficial ou confirmação do titular.
