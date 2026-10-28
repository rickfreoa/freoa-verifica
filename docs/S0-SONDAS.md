# S0: roteiro das sondas (plano 1.4.0)

Roteiro executável pelo supervisor, no notebook com IP brasileiro, depois da auditoria deste instrumento. Nada aqui foi executado ao vivo pelo instrumento: as URLs vêm das páginas oficiais registradas em `freoa_verifica/sondas.py` (campo `origem_hosts`) e em `docs/auditoria/1.4.0/s0-instrumento.md`.

## Regras da sonda

- Só pelo instrumento: `scripts/capturar_fixture.py --fonte-sonda <id> --sonda`. Pedido único (GET) pelo transporte comum, UA identificado do pacote, allowlist de host, caminho e MIME da fonte. URL fora da allowlist é recusada antes da rede. O instrumento não faz POST em fonte-sonda.
- Barreira (desafio, WAF, recusa, 403/429/5xx) vira `unavailable(motivo)` com categoria (decisão 0045). Registre e siga: não repita em laço, não troque UA, IP ou rota, não resolva CAPTCHA (regra 3).
- Leia o `robots.txt` do host antes de qualquer outra URL dele. Se um `Disallow` cobrir o caminho que viria a seguir, não o sonde e registre o fato como achado.
- Consulta neutra: `acordo de acionistas` (ou `sociedade anônima`). Nenhum dado de cliente, número de processo ou nome de parte.
- Nível: "P" = `robots.txt` (padrão RFC 9309, existe ou não em cada host). "A" = URL lida em página oficial. "B" = URL da página do próprio sistema, indexada por busca, não lida. "T" (tentativa): padrão de URL inferido; a sonda confirma ou refuta. Se refutar, descubra o GET real no navegador (aba Rede, consulta neutra), confira que cai nos prefixos do catálogo e sonde-o; se o resultado for POST, é pendência S0b, não contorno.
- Saída: `C:/dev/fv14-sondas/<id>/` (fora do repositório; o instrumento recusa destino dentro dele). Cada URL gera `<id>_<sha12>.<ext>` (corpo, só se 200) e `<id>_<sha12>.captura.json` (registro).

## Como ler cada registro (`.captura.json`)

| Pergunta | Onde olhar |
|---|---|
| Alcançável? | `unavailable` (false = 200 recebido), `status`, `url_final` (redirecionou para outro host?) |
| Barreira? | `unavailable: true` com `categoria` (`ambiental_desafio`, `recusa_identificado`, `fonte_fora`, `resposta_inesperada`) e `evidencia` (status, marcador, cabeçalho) |
| Formato? | `content_type`, extensão do corpo, primeiros bytes: HTML de página, JSON de API, casca de SPA sem lista |
| Contagem total utilizável para volume? | No corpo: campo de total (JSON) ou texto "de N" (HTML). Anote nome do campo, valor, se é exato ou cota inferior, tamanho da página (`bytes` por página) |
| Campos pesquisados? | Ementa, metadados (órgão, relator, datas, classe) e inteiro teor: o que o resultado traz e se há link estável por documento (PDF/HTML) |
| Quem serviu? | `fonte_sonda`, `user_agent`, `capturado_em`, `cabecalhos` |

## Comandos por fonte

PowerShell, na raiz do repositório, com o venv ativado. As aspas duplas protegem o `&` das URLs.

### tst: TST

Hosts do catálogo: `consultadocumento.tst.jus.br`, `jurisprudencia-backend.tst.jus.br`, `jurisprudencia.tst.jus.br`. Prefixos: `/rest/`, `/consultaDocumento/` (host inteiro em `jurisprudencia.tst.jus.br`).

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt do portal | P |
| 2 | página de pesquisa | A |
| 3 | configuração pública do portal | A |
| 4 | robots.txt do backend | P |
| 5 | órgãos judicantes (GET do portal) | A |
| 6 | indicadores (GET do portal; candidato a volume) | A |

```powershell
python scripts/capturar_fixture.py --fonte-sonda tst --sonda --saida C:/dev/fv14-sondas/tst --url "https://jurisprudencia.tst.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tst --sonda --saida C:/dev/fv14-sondas/tst --url "https://jurisprudencia.tst.jus.br/"
python scripts/capturar_fixture.py --fonte-sonda tst --sonda --saida C:/dev/fv14-sondas/tst --url "https://jurisprudencia.tst.jus.br/config.json"
python scripts/capturar_fixture.py --fonte-sonda tst --sonda --saida C:/dev/fv14-sondas/tst --url "https://jurisprudencia-backend.tst.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tst --sonda --saida C:/dev/fv14-sondas/tst --url "https://jurisprudencia-backend.tst.jus.br/rest/orgaos-judicantes"
python scripts/capturar_fixture.py --fonte-sonda tst --sonda --saida C:/dev/fv14-sondas/tst --url "https://jurisprudencia-backend.tst.jus.br/rest/indicadores"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: A pesquisa textual é POST JSON em `/rest/pesquisa-textual/<início>/<tamanho>` (lido no código do próprio portal): o instrumento só faz GET, então a contagem do resultado por consulta não sai desta sonda. `/rest/indicadores` e `/rest/orgaos-judicantes` são GET no código do portal e podem trazer totais por tipo de documento. Modo POST para fonte-sonda = pendência (S0b).

### stf_acordaos: STF, acórdãos

Hosts do catálogo: `jurisprudencia.stf.jus.br`. Prefixos: `/pages/search`, `/api/`.

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt | P |
| 2 | página de pesquisa | A |
| 3 | resultado (consulta neutra, base de acórdãos) | T |

```powershell
python scripts/capturar_fixture.py --fonte-sonda stf_acordaos --sonda --saida C:/dev/fv14-sondas/stf_acordaos --url "https://jurisprudencia.stf.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda stf_acordaos --sonda --saida C:/dev/fv14-sondas/stf_acordaos --url "https://jurisprudencia.stf.jus.br/pages/search"
python scripts/capturar_fixture.py --fonte-sonda stf_acordaos --sonda --saida C:/dev/fv14-sondas/stf_acordaos --url "https://jurisprudencia.stf.jus.br/pages/search?base=acordaos&pesquisa_inteiro_teor=false&sinonimo=true&plural=true&radicais=false&buscaExata=true&page=1&pageSize=10&queryString=acordo%20de%20acionistas&sort=_score&sortBy=desc"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: A página é aplicação de página única; o padrão de parâmetros vem dos links oficiais de súmulas e informativos (`base=sumulas`, `base=informativos`), e `base=acordaos` é inferência. O HTML da SPA não traz a lista nem a contagem: o achado esperado é desafio do WAF (já declarado no conector `stf`) ou casca vazia. O endpoint da API (`/api/`) deve ser descoberto no navegador (aba Rede, consulta pública neutra) antes de nova sonda.

### bnp: BNP (Pangea)

Hosts do catálogo: `bnp.pdpj.jus.br`, `pangeabnp.pdpj.jus.br`. Prefixos: host inteiro.

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt | P |
| 2 | página de pesquisa | A |
| 3 | nota técnica (rota documentada) | A |
| 4 | alias do CNJ | A |

```powershell
python scripts/capturar_fixture.py --fonte-sonda bnp --sonda --saida C:/dev/fv14-sondas/bnp --url "https://pangeabnp.pdpj.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda bnp --sonda --saida C:/dev/fv14-sondas/bnp --url "https://pangeabnp.pdpj.jus.br/"
python scripts/capturar_fixture.py --fonte-sonda bnp --sonda --saida C:/dev/fv14-sondas/bnp --url "https://pangeabnp.pdpj.jus.br/nota-tecnica/consultar"
python scripts/capturar_fixture.py --fonte-sonda bnp --sonda --saida C:/dev/fv14-sondas/bnp --url "https://bnp.pdpj.jus.br/"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: Aplicação de página única; o caminho da API de pesquisa não consta de fonte oficial lida. O catálogo admite o host inteiro justamente para a sonda poder seguir o que a página carrega, mas só por GET: descubra o endpoint no navegador (aba Rede, consulta neutra) e, se for GET, sonde-o aqui. Se for POST, pendência S0b.

### djen: DJEN

Hosts do catálogo: `comunica.pje.jus.br`, `comunicaapi.pje.jus.br`. Prefixos: `/consulta`, `/api/v1/`.

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt da consulta | P |
| 2 | página de consulta pública | A |
| 3 | robots.txt da API | P |
| 4 | resultado da API (consulta neutra, 5 itens) | T |

```powershell
python scripts/capturar_fixture.py --fonte-sonda djen --sonda --saida C:/dev/fv14-sondas/djen --url "https://comunica.pje.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda djen --sonda --saida C:/dev/fv14-sondas/djen --url "https://comunica.pje.jus.br/consulta?siglaTribunal=TJSP"
python scripts/capturar_fixture.py --fonte-sonda djen --sonda --saida C:/dev/fv14-sondas/djen --url "https://comunicaapi.pje.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda djen --sonda --saida C:/dev/fv14-sondas/djen --url "https://comunicaapi.pje.jus.br/api/v1/comunicacao?texto=acordo%20de%20acionistas&siglaTribunal=TJSP&pagina=1&itensPorPagina=5"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: A página oficial do CNJ documenta `/api/v1` como API de envio dos tribunais, com autenticação; a consulta pública por GET e seus parâmetros (`texto`, `siglaTribunal`, `pagina`, `itensPorPagina`) são inferência. Pergunta própria: o DJEN é publicação de comunicações (intimações, ementas?), não acervo de acórdãos: verifique se o texto da comunicação traz ementa/inteiro teor ou só o ato. Em teste prévio de leitura feito sem o instrumento, a borda do host de API respondeu 403 à rede de nuvem (ver registro da auditoria); esperado diferente a partir do IP brasileiro.

### cjf_unificada: CJF, pesquisa unificada

Hosts do catálogo: `jurisprudencia.cjf.jus.br`, `www.cjf.jus.br`. Prefixos: `/jurisprudencia/` (host inteiro em `jurisprudencia.cjf.jus.br`).

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt | P |
| 2 | página de pesquisa | A |
| 3 | página de pesquisa com tribunal | A |
| 4 | página oficial no portal do CJF | A |

```powershell
python scripts/capturar_fixture.py --fonte-sonda cjf_unificada --sonda --saida C:/dev/fv14-sondas/cjf_unificada --url "https://jurisprudencia.cjf.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda cjf_unificada --sonda --saida C:/dev/fv14-sondas/cjf_unificada --url "https://jurisprudencia.cjf.jus.br/"
python scripts/capturar_fixture.py --fonte-sonda cjf_unificada --sonda --saida C:/dev/fv14-sondas/cjf_unificada --url "https://jurisprudencia.cjf.jus.br/?tribunal=trf1"
python scripts/capturar_fixture.py --fonte-sonda cjf_unificada --sonda --saida C:/dev/fv14-sondas/cjf_unificada --url "https://www.cjf.jus.br/jurisprudencia/unificada/"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: Parâmetros do resultado desconhecidos: descubra no navegador (aba Rede, consulta neutra) e sonde se for GET. Pergunte a quais tribunais e bases (acórdãos, decisões monocráticas, turmas recursais) a pesquisa se estende, e se a contagem total vem por tribunal.

### trf1: TRF1

Hosts do catálogo: `arquivo.trf1.jus.br`, `jurisprudencia.cjf.jus.br`. Prefixos: host inteiro.

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt da pesquisa (CJF) | P |
| 2 | pesquisa do TRF1 no CJF | A |
| 3 | robots.txt do inteiro teor | P |
| 4 | inteiro teor de acórdãos | A |

```powershell
python scripts/capturar_fixture.py --fonte-sonda trf1 --sonda --saida C:/dev/fv14-sondas/trf1 --url "https://jurisprudencia.cjf.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda trf1 --sonda --saida C:/dev/fv14-sondas/trf1 --url "https://jurisprudencia.cjf.jus.br/?tribunal=trf1"
python scripts/capturar_fixture.py --fonte-sonda trf1 --sonda --saida C:/dev/fv14-sondas/trf1 --url "https://arquivo.trf1.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda trf1 --sonda --saida C:/dev/fv14-sondas/trf1 --url "https://arquivo.trf1.jus.br/"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: O menu oficial do TRF1 leva a pesquisa ao CJF (`?tribunal=trf1`) e o inteiro teor a `arquivo.trf1.jus.br`. Descubra o endpoint de resultado no navegador. Pergunte se o inteiro teor tem URL estável por acórdão.

### trf2: TRF2

Hosts do catálogo: `jurisprudencia.trf2.jus.br`, `www10.trf2.jus.br`. Prefixos: `/consultas/` (host inteiro em `jurisprudencia.trf2.jus.br`).

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt do portal | P |
| 2 | portal de jurisprudência | A |
| 3 | robots.txt de consultas | P |
| 4 | página de serviço | A |

```powershell
python scripts/capturar_fixture.py --fonte-sonda trf2 --sonda --saida C:/dev/fv14-sondas/trf2 --url "https://jurisprudencia.trf2.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda trf2 --sonda --saida C:/dev/fv14-sondas/trf2 --url "https://jurisprudencia.trf2.jus.br/"
python scripts/capturar_fixture.py --fonte-sonda trf2 --sonda --saida C:/dev/fv14-sondas/trf2 --url "https://www10.trf2.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda trf2 --sonda --saida C:/dev/fv14-sondas/trf2 --url "https://www10.trf2.jus.br/consultas/servicos/jurisprudencia/"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: A página oficial informa que o portal pesquisa ementas, inteiro teor, decisões monocráticas, súmulas e acórdãos históricos. O endpoint de resultado deve ser descoberto no navegador.

### trf3: TRF3

Hosts do catálogo: `web.trf3.jus.br`. Prefixos: `/jurisprudencia`, `/acordaos/`.

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt | P |
| 2 | busca de jurisprudência | A |
| 3 | consulta de acórdãos | A |

```powershell
python scripts/capturar_fixture.py --fonte-sonda trf3 --sonda --saida C:/dev/fv14-sondas/trf3 --url "https://web.trf3.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda trf3 --sonda --saida C:/dev/fv14-sondas/trf3 --url "https://web.trf3.jus.br/jurisprudencia"
python scripts/capturar_fixture.py --fonte-sonda trf3 --sonda --saida C:/dev/fv14-sondas/trf3 --url "https://web.trf3.jus.br/acordaos/Acordao"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: O serviço de acórdãos do carta de serviços é consulta por número de processo; a busca por texto está em `/jurisprudencia`. Descubra o endpoint de resultado no navegador. Pergunte se a busca cobre inteiro teor.

### tjac: TJAC (e-SAJ)

Hosts do catálogo: `esaj.tjac.jus.br`. Prefixos: `/cjsg/`.

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt | P |
| 2 | página de pesquisa | A |
| 3 | resultado (consulta neutra) | T |

```powershell
python scripts/capturar_fixture.py --fonte-sonda tjac --sonda --saida C:/dev/fv14-sondas/tjac --url "https://esaj.tjac.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjac --sonda --saida C:/dev/fv14-sondas/tjac --url "https://esaj.tjac.jus.br/cjsg/consultaCompleta.do"
python scripts/capturar_fixture.py --fonte-sonda tjac --sonda --saida C:/dev/fv14-sondas/tjac --url "https://esaj.tjac.jus.br/cjsg/resultadoCompleta.do?dados.buscaInteiroTeor=acordo+de+acionistas&dados.pesquisarComSinonimos=S&dados.origensSelecionadas=T&tipoDecisaoSelecionados=A&dados.ordenarPor=dtPublicacao"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: O e-SAJ do TJSP exige POST com sessão (cookie JSESSIONID) para o resultado: se o GET voltar 405, redirecionamento para a página de consulta ou página sem a lista, o achado é esse, e o modo POST com sessão vira pendência (S0b). A contagem, quando houver, aparece no cabeçalho da lista ("Resultados 1 a N de M").

### tjal: TJAL (e-SAJ)

Hosts do catálogo: `www2.tjal.jus.br`. Prefixos: `/cjsg/`.

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt | P |
| 2 | página de pesquisa | B |
| 3 | resultado (consulta neutra) | T |

```powershell
python scripts/capturar_fixture.py --fonte-sonda tjal --sonda --saida C:/dev/fv14-sondas/tjal --url "https://www2.tjal.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjal --sonda --saida C:/dev/fv14-sondas/tjal --url "https://www2.tjal.jus.br/cjsg/consultaCompleta.do"
python scripts/capturar_fixture.py --fonte-sonda tjal --sonda --saida C:/dev/fv14-sondas/tjal --url "https://www2.tjal.jus.br/cjsg/resultadoCompleta.do?dados.buscaInteiroTeor=acordo+de+acionistas&dados.pesquisarComSinonimos=S&dados.origensSelecionadas=T&tipoDecisaoSelecionados=A&dados.ordenarPor=dtPublicacao"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: O e-SAJ do TJSP exige POST com sessão (cookie JSESSIONID) para o resultado: se o GET voltar 405, redirecionamento para a página de consulta ou página sem a lista, o achado é esse, e o modo POST com sessão vira pendência (S0b). A contagem, quando houver, aparece no cabeçalho da lista ("Resultados 1 a N de M").

### tjam: TJAM (e-SAJ)

Hosts do catálogo: `consultasaj.tjam.jus.br`. Prefixos: `/cjsg/`.

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt | P |
| 2 | página de pesquisa | B |
| 3 | resultado (consulta neutra) | T |

```powershell
python scripts/capturar_fixture.py --fonte-sonda tjam --sonda --saida C:/dev/fv14-sondas/tjam --url "https://consultasaj.tjam.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjam --sonda --saida C:/dev/fv14-sondas/tjam --url "https://consultasaj.tjam.jus.br/cjsg/consultaCompleta.do"
python scripts/capturar_fixture.py --fonte-sonda tjam --sonda --saida C:/dev/fv14-sondas/tjam --url "https://consultasaj.tjam.jus.br/cjsg/resultadoCompleta.do?dados.buscaInteiroTeor=acordo+de+acionistas&dados.pesquisarComSinonimos=S&dados.origensSelecionadas=T&tipoDecisaoSelecionados=A&dados.ordenarPor=dtPublicacao"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: O e-SAJ do TJSP exige POST com sessão (cookie JSESSIONID) para o resultado: se o GET voltar 405, redirecionamento para a página de consulta ou página sem a lista, o achado é esse, e o modo POST com sessão vira pendência (S0b). A contagem, quando houver, aparece no cabeçalho da lista ("Resultados 1 a N de M").

### tjms: TJMS (e-SAJ)

Hosts do catálogo: `esaj.tjms.jus.br`. Prefixos: `/cjsg/`.

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt | P |
| 2 | página de pesquisa | B |
| 3 | resultado (consulta neutra) | T |

```powershell
python scripts/capturar_fixture.py --fonte-sonda tjms --sonda --saida C:/dev/fv14-sondas/tjms --url "https://esaj.tjms.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjms --sonda --saida C:/dev/fv14-sondas/tjms --url "https://esaj.tjms.jus.br/cjsg/consultaCompleta.do"
python scripts/capturar_fixture.py --fonte-sonda tjms --sonda --saida C:/dev/fv14-sondas/tjms --url "https://esaj.tjms.jus.br/cjsg/resultadoCompleta.do?dados.buscaInteiroTeor=acordo+de+acionistas&dados.pesquisarComSinonimos=S&dados.origensSelecionadas=T&tipoDecisaoSelecionados=A&dados.ordenarPor=dtPublicacao"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: O e-SAJ do TJSP exige POST com sessão (cookie JSESSIONID) para o resultado: se o GET voltar 405, redirecionamento para a página de consulta ou página sem a lista, o achado é esse, e o modo POST com sessão vira pendência (S0b). A contagem, quando houver, aparece no cabeçalho da lista ("Resultados 1 a N de M").

### tjrj: TJRJ (eJuris)

Hosts do catálogo: `www3.tjrj.jus.br`. Prefixos: `/ejuris/`.

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt | P |
| 2 | página de pesquisa | B |

```powershell
python scripts/capturar_fixture.py --fonte-sonda tjrj --sonda --saida C:/dev/fv14-sondas/tjrj --url "https://www3.tjrj.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjrj --sonda --saida C:/dev/fv14-sondas/tjrj --url "https://www3.tjrj.jus.br/ejuris/ConsultarJurisprudencia.aspx"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: Página `.aspx` (ASP.NET): o resultado costuma exigir POST com campos de estado (`__VIEWSTATE`), que o GET não produz. Se a página confirmar isso, o achado fecha a pergunta e o modo POST com estado vira pendência S0b. Confirmação do host é nível B (ver registro).

### tjmg: TJMG

Hosts do catálogo: `www5.tjmg.jus.br`. Prefixos: `/jurisprudencia/`.

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt | P |
| 2 | formulário de pesquisa | A |
| 3 | ajuda | A |
| 4 | resultado (consulta neutra) | T |

```powershell
python scripts/capturar_fixture.py --fonte-sonda tjmg --sonda --saida C:/dev/fv14-sondas/tjmg --url "https://www5.tjmg.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjmg --sonda --saida C:/dev/fv14-sondas/tjmg --url "https://www5.tjmg.jus.br/jurisprudencia/formEspelhoAcordao.do"
python scripts/capturar_fixture.py --fonte-sonda tjmg --sonda --saida C:/dev/fv14-sondas/tjmg --url "https://www5.tjmg.jus.br/jurisprudencia/ajuda.do"
python scripts/capturar_fixture.py --fonte-sonda tjmg --sonda --saida C:/dev/fv14-sondas/tjmg --url "https://www5.tjmg.jus.br/jurisprudencia/pesquisaPalavrasEspelhoAcordao.do?palavras=acordo+de+acionistas&pesquisarPor=ementa&linhasPorPagina=10&pesquisaPalavras=Pesquisar"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: O caminho do resultado é inferência a partir do nome do formulário; se recusar, copie o GET real do navegador. Os links oficiais usam `http://`; a sonda exige `https://`, e a resposta diz se o host o serve.

### tjrs: TJRS

Hosts do catálogo: `www.tjrs.jus.br`. Prefixos: `/novo/buscas-solr/`, `/novo/busca/`.

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt | P |
| 2 | pesquisa de jurisprudência | B |
| 3 | resultado (consulta neutra) | T |

```powershell
python scripts/capturar_fixture.py --fonte-sonda tjrs --sonda --saida C:/dev/fv14-sondas/tjrs --url "https://www.tjrs.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjrs --sonda --saida C:/dev/fv14-sondas/tjrs --url "https://www.tjrs.jus.br/novo/buscas-solr/"
python scripts/capturar_fixture.py --fonte-sonda tjrs --sonda --saida C:/dev/fv14-sondas/tjrs --url "https://www.tjrs.jus.br/novo/buscas-solr/?aba=jurisprudencia&q=acordo+de+acionistas&conteudo_busca=ementa_completa"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: A ferramenta de pesquisa do projeto teve a leitura de `/novo/` recusada pelo robots.txt do site: LEIA o robots.txt antes e, se `Disallow` cobrir `/novo/buscas-solr/`, NÃO sonde o caminho (registre a recusa como achado: Porta A do TJRS passa pela camada (b)). Parâmetros do resultado são inferência.

### tjpr: TJPR

Hosts do catálogo: `portal.tjpr.jus.br`. Prefixos: `/jurisprudencia/`.

| # | O quê | Nível |
|---|---|---|
| 1 | robots.txt | P |
| 2 | página de pesquisa | A |
| 3 | formulário de pesquisa pública | B |
| 4 | resultado (consulta neutra) | T |

```powershell
python scripts/capturar_fixture.py --fonte-sonda tjpr --sonda --saida C:/dev/fv14-sondas/tjpr --url "https://portal.tjpr.jus.br/robots.txt"
python scripts/capturar_fixture.py --fonte-sonda tjpr --sonda --saida C:/dev/fv14-sondas/tjpr --url "https://portal.tjpr.jus.br/jurisprudencia/"
python scripts/capturar_fixture.py --fonte-sonda tjpr --sonda --saida C:/dev/fv14-sondas/tjpr --url "https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do?actionType=pesquisar"
python scripts/capturar_fixture.py --fonte-sonda tjpr --sonda --saida C:/dev/fv14-sondas/tjpr --url "https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do?actionType=pesquisar&criterioPesquisa=acordo+de+acionistas"
```

Perguntas: (1) alcançável a partir do IP brasileiro? (2) barreira, e de que categoria? (3) formato da página e do resultado? (4) contagem total utilizável para volume, exata ou cota inferior? (5) campos pesquisados: ementa, metadados, inteiro teor?

Notas: O parâmetro do termo (`criterioPesquisa`) é inferência; se o GET devolver só o formulário, o resultado é POST: pendência S0b.

## TJSP e TJDFT (conector existente)

Têm conector no produto; a sonda de volume usa o mesmo instrumento com `--conector`, a mesma consulta neutra e o mesmo registro. O resultado do TJSP exige a sessão do conector (modo `--consulta`).

```powershell
python scripts/capturar_fixture.py --conector tjsp --sonda --saida C:/dev/fv14-sondas/tjsp --chave volume1 --consulta '{"termo":"acordo de acionistas","pagina":1}'
python scripts/capturar_fixture.py --conector tjdft --sonda --saida C:/dev/fv14-sondas/tjdft --chave volume1 --consulta '{"query":"acordo de acionistas","pagina":1,"tamanho":10}'
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

Como usar, por tribunal do lote 1 (TJSP, TJRJ, TJMG, TJRS, TJPR, TJDFT) e dos TRF1, TRF2 e TRF3: no relatório ou no painel, tomar o 2º grau do tribunal, o último ano fechado, e ler casos novos e baixados no 2º grau e as decisões colegiadas/terminativas quando o capítulo as separar. Multiplicar por 2 (janela de 24 meses do plano) e por um tamanho médio de texto medido na sonda, e registrar o resultado como "estimativa CNJ x tamanho amostral". Anotar edição do relatório, página ou aba do painel e filtros, para reprodução.

Comparar a estimativa do CNJ com a contagem total de cada sonda (quando houver): divergência grande indica que a ferramenta de pesquisa cobre só parte do acervo ou que o total é cota inferior.

## Pendências conhecidas do instrumento (fora do escopo desta entrega)

- Sem POST nem sessão para fonte-sonda: TST (pesquisa textual), TJRJ (`__VIEWSTATE`), e-SAJ (resultado) e talvez TJPR, STF e BNP só entregam a contagem por POST. Se as sondas confirmarem, abrir S0b: modo `--consulta` para fonte-sonda, reaproveitando `build_cjsg_request` nos quatro e-SAJ, com o mesmo registro e a mesma recusa antes da rede.
- Endpoints de resultado marcados "T" ou "descubra no navegador": depois de descobertos, entram no roteiro (e, se fora dos prefixos, no catálogo, com nova confirmação oficial).
