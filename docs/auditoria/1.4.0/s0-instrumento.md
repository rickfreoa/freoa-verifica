# S0: extensão do instrumento de sondas (plano 1.4.0)

| Campo | Valor |
|---|---|
| Ferramenta | Claude Code (Agent SDK), subagente implementador |
| Modelo | Claude Sonnet 5.5 (`claude-sonnet-5-5`) |
| Ramo / base | `feat/sondas-s0` sobre `origin/main` 6a21865 |
| Commit da implementação | `a75c0d0` |
| Escopo | `freoa_verifica/sondas.py` (novo), `freoa_verifica/captura.py`, `scripts/capturar_fixture.py`, `tests/test_sondas.py` (novo), `docs/S0-SONDAS.md` (novo). `transport.py`, `service.py`, contrato MCP e `registry()` intactos (também na rodada 2) |
| Rodada 2 | correções do parecer Codex r1 do PR #14 (bloqueador B1; B2, B3, I1, I2, I3, M1), com a arbitragem do supervisor de 28/10/2026; commit `parecer PR #14 r1: ...` (ver `git log`) |
| Rodada 3 | correções do parecer Codex r2 do PR #14 (B1, B2, I1), com a decisão do supervisor acatando o B2; commit `parecer PR #14 r2: ...` (ver `git log`) |

## O que mudou

- Catálogo imutável `FONTES_SONDA` (16 ids da especificação), `HOSTS_RECUSADOS` e `prefixos_por_host`. Acréscimo à dataclass pedida: `nota`. (Na rodada 1 havia também `hosts_sem_prefixo`, host de escopo livre; foi eliminado na rodada 2, ver abaixo.)
- `capturar(..., fonte_sonda=<id>)`: exclusivo com `conector`, só com `sonda=True` e só por `url`; recusa antes da rede com a mesma `validate_reference`; transporte comum, UA identificado (ambos os modos de `UA_MODOS`); registro com `fonte_sonda: <id>` e `conector: null` (`fonte_sonda: null` nos registros de conector). Desafio, recusa, status diferente de 200 e resposta inesperada seguem o caminho de hoje (`unavailable(motivo)`; categoria da decisão 0045 quando houver, 429 e outros status sem regra própria saem sem categoria).
- CLI: `--fonte-sonda <id>` mutuamente exclusivo com `--conector` (um dos dois obrigatório); exige `--sonda` e `--url`.
- Isolamento: só `captura.py` importa `sondas.py`; nenhum módulo importa `captura.py` (só o script). Teste estrutural por AST sobre o fecho de imports de `service`, `mcp_server` e `cli`, com mutação provada (acrescentar `from freoa_verifica import sondas` em `service.py` derruba 4 testes).

## Comandos e resultado

```
PYTHONPATH=. .venv/bin/python scripts/ruff_catraca.py                -> rc 0
.venv/bin/python -m ruff check <arquivos tocados>                    -> All checks passed
git diff --check                                                     -> limpo
PYTHONPATH=. pytest tests/test_sondas.py tests/test_captura_instrumento.py tests/test_captura.py tests/test_garantias_estruturais.py -> verdes
PYTHONPATH=<caminho absoluto do worktree> pytest tests -q -m "not live" -p no:cacheprovider -> 7241 passed, 9 skipped, 34 deselected, 1 warning em 905 s (rc 0)
```

Nota sobre o ambiente: com `PYTHONPATH=.` (relativo), `tests/test_120_isolamento_conectores.py::test_diretorio_corrente_nao_entra_no_path_do_filho` falha também na base `6a21865` sem nenhuma alteração desta entrega, porque o filho herda `PYTHONPATH=.` e passa a enxergar o diretório corrente que o teste planta. Com caminho absoluto o teste passa. A suíte completa foi rodada com caminho absoluto. O comando de `comum.md` deve usar o caminho absoluto do worktree.

## Hosts do catálogo, nível de confirmação e a URL oficial de cada um

Níveis: A = o host consta de página oficial que foi lida (ou do código/configuração publicados pelo próprio portal); B = a página do próprio sistema, no domínio do tribunal, foi indexada pela busca mas não pôde ser lida (a ferramenta de leitura foi recusada pelo `robots.txt` do site; não contornado). Só os de nível A estão confirmados. Os de nível B ficam no catálogo, com `confirmacao: "B"` e `hosts_b`, e a sonda neles está bloqueada até confirmação documental (página oficial lida ou confirmação do titular): o instrumento recusa, sem rede, qualquer URL de host B (inclusive o `robots.txt`) sem `--confirmado-por-titular`.

| Fonte | Host | Nível | URL oficial da confirmação |
|---|---|---|---|
| tst | `consultadocumento.tst.jus.br` | A | https://jurisprudencia.tst.jus.br/config.json |
| tst | `jurisprudencia-backend.tst.jus.br` | A | https://jurisprudencia.tst.jus.br/config.json |
| tst | `jurisprudencia.tst.jus.br` | A | https://jurisprudencia.tst.jus.br/ |
| stf_acordaos | `jurisprudencia.stf.jus.br` | A | https://portal.stf.jus.br/jurisprudencia/ |
| bnp | `bnp.pdpj.jus.br` | A | https://docs.pdpj.jus.br/servicos-negociais/BNP-Pangea/BNP%20-%20Manual%20de%20Utiliza%C3%A7%C3%A3o |
| bnp | `pangeabnp.pdpj.jus.br` | A | https://docs.pdpj.jus.br/servicos-negociais/BNP-Pangea/BNP%20-%20Manual%20de%20Utiliza%C3%A7%C3%A3o |
| djen | `comunica.pje.jus.br` | A | https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/comunicacoes-processuais/ |
| djen | `comunicaapi.pje.jus.br` | A | https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/comunicacoes-processuais/orientacoes-aos-tribunais/ |
| cjf_unificada | `jurisprudencia.cjf.jus.br` | A | https://www.trf1.jus.br/trf1/busca/ |
| cjf_unificada | `www.cjf.jus.br` | B | https://www.cjf.jus.br/jurisprudencia/unificada/ |
| trf1 | `arquivo.trf1.jus.br` | A | https://www.trf1.jus.br/trf1/busca/ |
| trf1 | `jurisprudencia.cjf.jus.br` | A | https://www.trf1.jus.br/trf1/busca/ |
| trf2 | `jurisprudencia.trf2.jus.br` | A | https://www.trf2.jus.br/trf2/artigo/coport/consulta-de-jurisprudencia |
| trf2 | `www10.trf2.jus.br` | A | https://www.trf2.jus.br/trf2/noticia/2024/trf2-portal-de-jurisprudencia-conta-com-novo-mecanismo-de-busca |
| trf3 | `web.trf3.jus.br` | A | https://www.trf3.jus.br/carta-servicos/acordaos |
| tjac | `esaj.tjac.jus.br` | A | https://www.tjac.jus.br/ |
| tjal | `www2.tjal.jus.br` | B | https://www2.tjal.jus.br/cjsg/consultaCompleta.do |
| tjam | `consultasaj.tjam.jus.br` | B | https://consultasaj.tjam.jus.br/cjsg/consultaCompleta.do |
| tjms | `esaj.tjms.jus.br` | B | https://esaj.tjms.jus.br/cjsg/consultaCompleta.do |
| tjrj | `www3.tjrj.jus.br` | B | https://www3.tjrj.jus.br/ejuris/ConsultarJurisprudencia.aspx |
| tjmg | `www5.tjmg.jus.br` | A | https://www.tjmg.jus.br/portal-tjmg/jurisprudencia/consulta-de-jurisprudencia/ |
| tjpr | `portal.tjpr.jus.br` | A | https://www.tjpr.jus.br/jurisprudencia |

## Hosts recusados e por quê

- `www.tjrs.jus.br` (TJRS): barreira registrada, ver a rodada 3 abaixo
- `jurisprudencia.trf1.jus.br`: não consta de página oficial lida; o TRF1 publica a pesquisa no CJF
- `jurisprudencia.trf3.jus.br`: não consta de página oficial lida; o TRF3 publica em web.trf3.jus.br
- `juris.trf2.jus.br`: apenas resultado de busca, sem página oficial lida
- `www.tst.jus.br`: página de jurisprudência não lida: respondeu 202 sem corpo (desafio) e o robots.txt do site foi recusado à ferramenta de pesquisa; sem contorno
- `consultaunificada2.tst.jus.br`: pesquisa textual legada; apenas resultado de busca, sem página oficial lida
- `www4.tjrj.jus.br`: duplicata de www3.tjrj.jus.br, apenas em resultado de busca
- `www3.tjrs.jus.br`: consulta legada, apenas em resultado de busca
- `www2.cjf.jus.br`: memória virtual e versão antiga da pesquisa unificada; fora do escopo da sonda
- `hcomunicaapi.cnj.jus.br`: ambiente de homologação do DJEN, para integração de tribunais, não é fonte pública
- `comunicaapi.cnj.jus.br`: citado na página oficial só como prefixo de ambiente, sem uso público documentado
- `docs.pdpj.jus.br`: documentação do BNP, não é fonte de decisões
- `marketplace.pdpj.jus.br`: marketplace de serviços da PDPJ, não é fonte de decisões
- `juridico.ai`: agregador privado: nunca

## Leituras feitas fora do instrumento (para a rastreabilidade)

Para confirmar hosts, o implementador leu páginas oficiais públicas com GET único e UA `FREOA-Verifica-pesquisa-hosts/1.0`. Essas leituras foram feitas pela ferramenta de pesquisa do agente, não pelo produto, não pelo instrumento e não constituem sonda de fonte: páginas do CNJ (BNP, comunicações processuais, orientações aos tribunais, Justiça em Números), `docs.pdpj.jus.br`, portal do STF, TJAC, TJMG, TJPR, TRF1, TRF2, `jurisprudencia.tst.jus.br` (página, `config.json` e o JavaScript do portal). Três leituras tocaram hosts candidatos a fonte: `robots.txt` de `comunicaapi.pje.jus.br` (403 da borda, corpo HTML de erro), de `pangeabnp.pdpj.jus.br` e de `bnp.pdpj.jus.br` (200, mas HTML da aplicação, não texto de robots). O 403 do DJEN foi, portanto, uma leitura da ferramenta de pesquisa do agente, a partir de IP de nuvem, e não um resultado do produto. Nenhuma delas foi repetida e nenhuma vale como evidência da sonda.

Para as fontes ainda no catálogo, a sonda do instrumento no notebook é o primeiro e único acesso do produto; se o BNP ou outra fonte responder 403 ou outra recusa (desafio, WAF, 429, 5xx), a fonte fica registrada como barreira e não há nova tentativa por outra rede ou rota (regra 3 do AGENTS.md). O DJEN segue a decisão 0069 (rodada 3): o 403 de 27/10/2026 foi da ferramenta de pesquisa em nuvem, fora do Brasil, e não vale como recusa ao produto. Nenhum CAPTCHA, WAF ou recusa foi contornado: `www.tst.jus.br` respondeu 202 sem corpo e não foi usado; TJRJ e TJRS tiveram a leitura recusada pelo `robots.txt` e ficaram em nível B. Vários hosts (cjf, trf3, tjrj, tjrs, tjam, tjms) fecharam a conexão da rede de nuvem e não foram insistidos.

## Pendências

1. Sem POST nem sessão para fonte-sonda: a pesquisa textual do TST (POST JSON), o resultado do TJRJ (`__VIEWSTATE`) e o resultado dos e-SAJ (POST com sessão) dependem de modo `--consulta` para fonte-sonda (S0b), fora do escopo desta entrega.
2. S0b, endpoints: o endpoint de resultado que não consta de página oficial lida está fora da S0 (STF acórdãos, BNP, DJEN, CJF, TRF1, TRF2, TRF3, TJMG, TJPR, TJRS, e-SAJ de TJAL, TJAM e TJMS). Só será descoberto por sessão assistida nos termos da decisão 0067 ou por documentação oficial lida; o roteiro não manda mais descobri-lo no navegador nem fora do instrumento.
3. Hosts em nível B (`www.cjf.jus.br`, TJAL, TJAM, TJMS, TJRJ, TJRS) estão bloqueados até leitura da página oficial ou confirmação do titular.
4. A URL de resultado do TJAC (única linha "T") tem caminho lido em página oficial e parâmetros inferidos do e-SAJ; se a sonda a refutar, vira pendência S0b.
5. `comunicaapi.pje.jus.br/api/v1` está documentado pelo CNJ como API de envio autenticada: não é sondado (só o `robots.txt` do host); a consulta pública não consta de página oficial.
6. Volume: o roteiro cita as fontes estatísticas do CNJ rotuladas como estimativa; a medição real é a do notebook.

## Rodada 2: parecer Codex r1 do PR #14 e arbitragem do supervisor

Arbitragem registrada como decisão do supervisor de 28/10/2026 (B2 e a regra de parada do B3). Cada item abaixo tem teste em `tests/test_sondas.py` (e `tests/test_captura_instrumento.py`).

| Item | Correção | Teste |
|---|---|---|
| B1 (bloqueador) | A exceção de `/robots.txt` passava `path_prefixes=None` ao percurso inteiro: um 302 de `/robots.txt` para `/admin/login` no mesmo host era seguido e aceito. Agora, em `captura._plano_get` (comum a conector e fonte-sonda), o robots roda com prefixo exato `/robots.txt` em todos os hosts da allowlist, só `text/plain` e `max_redirects=0`: o redirecionamento não é seguido (sem pedido ao destino) e vira `unavailable` (`transporte_BlockedHost`, sem categoria). Variantes (`/Robots.txt`, `/robots.txt.bak`, `/robots.txt?x=1`) não são a exceção. `transport.py` intacto. | servidor local com 302 (`/admin/login`, `/robots.txt.bak`, `/robots.txt/../admin`, outro host da allowlist) para fonte-sonda e para os conectores `tjsp` e `stf`; mutação: com o código antigo, 13 casos falham |
| B2 | (a) Retiradas do roteiro todas as instruções de descobrir endpoint no navegador ou fora do instrumento; endpoint de resultado não documentado em página oficial está fora da S0 e entra como pendência S0b (sessão assistida, decisão 0067, ou documentação oficial). (b) Registrado que o 403 do DJEN foi lido pela ferramenta de pesquisa do agente, não pelo produto; retirada a frase "refazer no notebook"; a sonda do instrumento no notebook é o primeiro e único acesso do produto, e recusa vira barreira registrada, sem nova tentativa por outra rede ou rota (regra 3), para DJEN, BNP e qualquer fonte. | `test_roteiro_sem_descoberta_de_endpoint_fora_do_instrumento_nem_rota_de_cadastro` |
| B3 | Sequência por host: o `robots.txt` do próprio host é o primeiro comando dele, com tabela de decisão (desafio, erro, redirecionamento, HTML ou conteúdo não interpretável: a sonda do host PARA; `Disallow` aplicável: não sondar o caminho). Corrigidos `bnp.pdpj.jus.br`, `www.cjf.jus.br` e os hosts de TJSP e TJDFT, que eram acessados antes do robots. | `test_primeiro_comando_de_cada_host_do_roteiro_e_o_robots_txt` (arquivo todo e por fonte; mutação provada) |
| I1 | `hosts_sem_prefixo` eliminado. O catálogo tem `rotas` host a host, prefixos estreitos de rotas documentadas; o transporte não admite `/` como prefixo, então a raiz fica fora e host sem rota documentada admite só o `robots.txt`. Retirada `/nota-tecnica/consultar` e toda rota de cadastro, login ou área institucional; `/api/` do STF e `/api/v1/` do DJEN saem. As linhas "T" cujo endpoint não é documentado saíram do roteiro. | `test_escopo_de_caminho_consistente_sem_host_livre`, `test_nenhuma_rota_de_cadastro_login_ou_area_institucional`, `test_fonte_incoerente_e_recusada_na_construcao` |
| I2 | `FonteSonda.confirmacao: Literal["A","B"]` (pior nível da fonte) e `hosts_b` (por host, necessário porque `cjf_unificada` mistura A e B). O roteiro marca as sondas de host B como bloqueadas até confirmação documental; o instrumento recusa host B sem `--confirmado-por-titular`, registrado no `.captura.json` junto de `confirmacao_host`. Corrigida a afirmação de que todos os hosts foram confirmados. | `test_host_b_*`, `test_cli_recusa_host_b_sem_flag_e_registra_com_flag`, `test_roteiro_marca_bloqueio_de_host_b_e_nao_afirma_confirmacao_geral` |
| I3 | Cada comando do roteiro leva `--chave <fonte>_<etapa>` distinta; o instrumento recusa gravar sobre `.captura.json` (ou corpo) já existente, antes da rede quando a chave é explícita, e a gravação é por criação exclusiva. | `test_nao_sobrescreve_*`, `test_roteiro_usa_chave_distinta_por_comando_e_nunca_repete_arquivo_de_saida` |
| M1 | Corrigida a promessa de categoria: 429 sai sem categoria (decisão 0045), só com motivo e evidência. | `test_roteiro_nao_promete_categoria_para_429` |

Escolhas de interpretação a confirmar pelo supervisor: (1) a regra de parada trata qualquer erro do robots, inclusive 404, como permissão indeterminada (mais conservadora que o RFC 9309); (2) `/rest/orgaos-judicantes` e `/rest/indicadores` do TST permanecem por serem GET publicados no código do próprio portal e não endpoints de resultado; (3) a linha "T" do TJAC permanece, por ter caminho lido em página oficial; (4) o redirecionamento do robots sai como `transporte_BlockedHost` sem categoria, não como categoria própria; (5) esta rodada não teve rede: nenhuma rota do catálogo foi relida em página oficial, apenas reduzida ao que o registro da rodada 1 já dava como lido.

## Comandos e resultado da rodada 2

```
PYTHONPATH=<caminho absoluto do worktree> python scripts/ruff_catraca.py -> rc 0
ruff check <arquivos tocados>                                         -> All checks passed
git diff --check                                                      -> limpo
PYTHONPATH=<caminho absoluto do worktree> pytest tests -q -m "not live" -p no:cacheprovider -x -> 7201 passed, 9 skipped, 34 deselected em 865 s (rc 0)
```

O total é menor que o da rodada 1 (7241) porque a reforma do catálogo reduziu os casos parametrizados por host (hosts de escopo livre e linhas "T" saíram); os testes novos (robots com 302 contra servidor local, B3, host B, não sobrescrita) somam-se a isso.

## Rodada 3: parecer Codex r2 do PR #14 e decisão do supervisor

Decisão do supervisor de 28/10/2026, acatando o parecer r2 (B2). `transport.py` intacto: o B1 usa o parâmetro `repeticao`, que `transport.fetch` já aceita.

| Item | Correção | Teste |
|---|---|---|
| B1 (bloqueador) | `captura._buscar` herdava as duas repetições do transporte para 502/503/504: robots 503 seguido de 200 virava sucesso e 503 em três pedidos fazia três GETs. `httputil._connector_fetch` ganhou o argumento opcional `repeticao` (repassado a `transport.fetch` só quando informado) e `_buscar` passa `repeticao=0` em todo pedido de captura, de sonda e de conector. O padrão do transporte e todos os outros consumidores ficam como estavam. | servidor local com o transporte real (DNS e conexão simulados): 503→200 e 503→503→503, 502→200 e 504→504→200 fazem exatamente um pedido e saem `unavailable(http_5xx)`, na rota, no robots e na captura de conector; `connector_fetch` sem `repeticao` continua com 2 repetições (3 pedidos no 503 contínuo); mutação: com o código anterior, os casos 503→200 passam a sucesso |
| B2 | Decisão do titular (0069, `docs/decisoes/0069-djen-restricao-geografica.md`, copiada ao repositório), que substitui a proposta do parecer r2 de tirar o DJEN do roteiro: restrição geográfica geral não é recusa para a regra 3 quando o acesso parte do ambiente normal do produto no Brasil. O DJEN fica no catálogo, com a `nota` da fonte referenciando a 0069: sondável só do notebook do titular, pelo transporte comum, UA identificado, uma requisição por comando, sem repetição (ver B1), sem proxy, VPN ou túnel; rotas só o `robots.txt` e o que consta de página oficial lida (consulta pública não documentada: pendência S0b). Registro: o 403 de 27/10/2026 foi da ferramenta de pesquisa em nuvem, fora do produto e fora do Brasil, sem valor de evidência (0069, item 5); se a sonda do notebook receber recusa, a fonte vira barreira, sem nova tentativa por outra rede (0069, item 4). O critério "host que já respondeu recusa a qualquer leitura registrada" não se aplica ao DJEN e foi revisto para os demais: `www.tst.jus.br` (202 sem corpo) já estava recusado; `www.tjrs.jus.br` teve a leitura recusada pelo `robots.txt` do próprio host e saiu (`tjrs` em `FONTES_BARRADAS`, hosts em `HOSTS_RECUSADOS`, recusado antes da rede, mesmo com `--confirmado-por-titular`); TJRJ ficou (a recusa foi no portal `www.tjrj.jus.br`, host diferente do catalogado `www3.tjrj.jus.br`, que segue nível B bloqueado); o BNP respondeu 200 com HTML da aplicação, não é recusa, fica, sujeito à regra de parada do robots. | `test_djen_referencia_a_decisao_0069_e_roteiro_sem_proxy_nem_repeticao`, `test_fontes_barradas_fora_do_catalogo_com_motivo_registrado`, `test_instrumento_recusa_fonte_barrada_antes_da_rede`, `test_registro_da_barreira_no_roteiro_e_na_auditoria` |
| I1 | As rotas eram prefixos (`startswith`): `/config.json.bak`, `/rest/indicadores/admin/login`, `/cjsg/consultaCompleta.do.evil`, `/jurisprudencia-admin/login` e `/jurisprudencia/login` passavam. Agora toda rota do catálogo é caminho exato (igualdade de string, case-sensitive, sem decodificação), validado em `captura._plano_get` antes do transporte; consulta (`?`) só nas rotas listadas em `consultas` (hoje só `/cjsg/resultadoCompleta.do` do TJAC, a única com parâmetros no roteiro). O catálogo não tem família de diretório (prefixo): `consultadocumento.tst.jus.br` (`/consultaDocumento/`, que era prefixo) ficou só com o `robots.txt`, e `/jurisprudencia/` do TJPR, `/novo/...` e as demais barras finais são caminhos exatos. A construção recusa rota com segmento que contenha login, admin, cadastro, auth, conta ou usuario, e com `?`, `#`, `%` ou `\`. O transporte continua como segunda barreira (as rotas como prefixos) e a sonda não segue redirecionamento (`max_redirects=0`): o destino de um 3xx não é pedido. | as cinco URLs do parecer e 21 variantes (`.bak`, `.old`, sufixo após `.do`, barra final, segmento extra, caixa, `//`, `%2E`, consulta em rota sem parâmetros); 302 de rota exata para `/config.json.bak`, `/admin/login` e `/config.json/../x` sem pedido ao destino; `test_fonte_recusa_rota_com_segmento_proibido_ou_consulta_fora_das_rotas`; mutação: com `startswith`, as cinco URLs do parecer passam |

Escolhas de interpretação a confirmar pelo supervisor: (1) o TJRS saiu do catálogo pelo critério "recusa a qualquer leitura registrada" (o `robots.txt` do host recusou a ferramenta de pesquisa); se o supervisor entender que o `Disallow` para a ferramenta não é recusa do host, basta devolver o id ao catálogo, ainda em nível B; (2) a repetição zero vale também para a captura dos conectores `tjsp` e `tjdft` (mesmo `_buscar`), que ficam em um pedido por etapa; (3) sem família de diretório no catálogo: `/consultaDocumento/` do TST ficou fora por ser prefixo; (4) esta rodada não teve rede.

## Comandos e resultado da rodada 3

```
PYTHONPATH=<caminho absoluto do worktree> python scripts/ruff_catraca.py -> rc 0
ruff check <arquivos tocados>                                         -> All checks passed
git diff --check                                                      -> limpo
PYTHONPATH=<caminho absoluto do worktree> pytest tests -q -m "not live" -p no:cacheprovider -> 7152 passed, 9 skipped, 34 deselected em 899 s (rc 0)
```
