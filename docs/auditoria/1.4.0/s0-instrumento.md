# S0: extensão do instrumento de sondas (plano 1.4.0)

| Campo | Valor |
|---|---|
| Ferramenta | Claude Code (Agent SDK), subagente implementador |
| Modelo | Claude Sonnet 5.5 (`claude-sonnet-5-5`) |
| Ramo / base | `feat/sondas-s0` sobre `origin/main` 6a21865 |
| Commit da implementação | `a75c0d0` |
| Escopo | `freoa_verifica/sondas.py` (novo), `freoa_verifica/captura.py`, `scripts/capturar_fixture.py`, `tests/test_sondas.py` (novo), `docs/S0-SONDAS.md` (novo). `transport.py`, `service.py`, contrato MCP e `registry()` intactos |

## O que mudou

- Catálogo imutável `FONTES_SONDA` (16 ids da especificação), `HOSTS_RECUSADOS` e `prefixos_por_host`. Acréscimos à dataclass pedida: `hosts_sem_prefixo` e `nota`.
  `hosts_sem_prefixo` existe porque `allowed_path_prefixes` do transporte recusa o prefixo `/` e vários portais são aplicações de página única cuja raiz é a página de pesquisa; neles vale o host inteiro (GET, HTTPS, MIME restrito). Só tst, bnp, cjf_unificada, trf1 e trf2 o usam; um teste fixa esse conjunto.
- `capturar(..., fonte_sonda=<id>)`: exclusivo com `conector`, só com `sonda=True` e só por `url`; recusa antes da rede com a mesma `validate_reference`; transporte comum, UA identificado (ambos os modos de `UA_MODOS`); registro com `fonte_sonda: <id>` e `conector: null` (`fonte_sonda: null` nos registros de conector). Desafio, recusa, status diferente de 200 e resposta inesperada seguem o caminho de hoje (`unavailable(motivo)` com categoria da decisão 0045).
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

## Hosts confirmados e a URL oficial de cada um

Níveis: A = o host consta de página oficial que foi lida (ou do código/configuração publicados pelo próprio portal); B = a página do próprio sistema, no domínio do tribunal, foi indexada pela busca mas não pôde ser lida (a ferramenta de leitura foi recusada pelo `robots.txt` do site; não contornado).

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
| tjrs | `www.tjrs.jus.br` | B | https://www.tjrs.jus.br/novo/buscas-solr/ |
| tjpr | `portal.tjpr.jus.br` | A | https://www.tjpr.jus.br/jurisprudencia |

## Hosts recusados e por quê

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

Para confirmar hosts, o implementador leu páginas oficiais públicas com GET único e UA `FREOA-Verifica-pesquisa-hosts/1.0` (pesquisa documental, não sonda de fonte e não pelo instrumento): páginas do CNJ (BNP, comunicações processuais, orientações aos tribunais, Justiça em Números), `docs.pdpj.jus.br`, portal do STF, TJAC, TJMG, TJPR, TRF1, TRF2, `jurisprudencia.tst.jus.br` (página, `config.json` e o JavaScript do portal). Três leituras tocaram hosts candidatos a fonte: `robots.txt` de `comunicaapi.pje.jus.br` (403 da borda, corpo HTML de erro), de `pangeabnp.pdpj.jus.br` e de `bnp.pdpj.jus.br` (200, mas HTML da aplicação, não texto de robots). Estas três não foram repetidas e a sonda S0 oficial deve refazê-las pelo instrumento; o 403 do DJEN veio de IP de nuvem. Nenhum CAPTCHA, WAF ou recusa foi contornado: `www.tst.jus.br` respondeu 202 sem corpo e não foi usado; TJRJ e TJRS tiveram a leitura recusada pelo `robots.txt` e ficaram em nível B. Vários hosts (cjf, trf3, tjrj, tjrs, tjam, tjms) fecharam a conexão da rede de nuvem e não foram insistidos.

## Pendências

1. Sem POST nem sessão para fonte-sonda: a pesquisa textual do TST (POST JSON), o resultado do TJRJ (`__VIEWSTATE`) e o resultado dos e-SAJ (POST com sessão) dependem de modo `--consulta` para fonte-sonda (S0b), fora do escopo desta entrega.
2. Endpoints de resultado de STF acórdãos, BNP, CJF, TRF1, TRF2 e TRF3 não constam de fonte oficial lida; o roteiro manda descobri-los no navegador (aba Rede, consulta neutra) e sondá-los se forem GET.
3. Hosts em nível B (TJAL, TJAM, TJMS, TJRJ, TJRS e `www.cjf.jus.br`) pedem leitura da página oficial a partir do IP brasileiro antes de a sonda ser tomada como confirmada.
4. URLs de resultado marcadas "T" no roteiro são inferências de padrão; a sonda as confirma ou refuta.
5. `comunicaapi.pje.jus.br/api/v1` está documentado pelo CNJ como API de envio autenticada; a consulta pública por GET não consta da página oficial.
6. Volume: o roteiro cita as fontes estatísticas do CNJ rotuladas como estimativa; a medição real é a do notebook.
