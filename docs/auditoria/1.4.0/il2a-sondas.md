# IL.2-a: registro das sondas de legislação

Sondas executadas pelo supervisor em 04/11/2026, pelo instrumento `scripts/capturar_fixture.py`, versão `1.4.0a2`. Consolidação local por Codex (sessão de escrita), ramo `feat/il2a-sondas-registro`, base `785c72e`. Nenhuma sonda ou acesso de rede nesta consolidação. Auditoria independente e suíte completa ficam com o supervisor.

UA em todos os registros: `freoa-verifica/1.4.0a2 (+https://github.com/rickfreoa/freoa-verifica)`. Horários UTC das capturas: de `2026-11-04T22:13:04.641662+00:00` a `2026-11-04T22:14:12.681472+00:00` (19:13–19:14 em America/Sao_Paulo).

## Resultados observados

| Fonte | Comando / alvo | Resultado |
|---|---|---|
| `senado_legislacao` | robots.txt de `legis.senado.leg.br` | 403 em `evidencia.status`, `unavailable(http_403)`, categoria `recusa_identificado`: barreira; nenhum outro comando do host |
| `dou` | robots.txt de `www.in.gov.br` | 403 em `evidencia.status`, `unavailable(http_403)`, categoria `recusa_identificado`: barreira |
| `lexml` | robots.txt | 200 `text/plain`; `User-Agent: *` com `Disallow: /busca/`, `Allow: /urn`, `Allow: /sru` (minúsculo), `Crawl-delay: 5`; `/busca/SRU` proibida e não sondada |
| `normas_leg` | robots.txt | 200 `text/plain`; `User-agent: *`, `Allow: /`; nenhuma rota catalogada além do robots |
| `camara_legislacao` | robots do portal e de `www2` | 200 `text/plain`, sem `Disallow` aplicável a `/legislacao` |
| `camara_legislacao` | `/legislacao` | 200 HTML (59.842 bytes); publica formulário `/legislacao/busca`, `/legislacao/pesquisa-avancada` e links para coleções em `www2.camara.leg.br/atividade-legislativa/legislacao/...` |

Nos registros de recusa, `status`, `sha256`, `bytes` e `arquivo` são nulos; o 403 consta de `evidencia.status`. Nenhum corpo foi gravado para Senado e DOU; não há robots dessas fontes a copiar. Não se infere qual controle causou a recusa além da categoria registrada.

## Evidências preservadas

Sete `.captura.json` e quatro corpos de robots estão em [il2a-sondas/](il2a-sondas/), separados por fonte. Os JSON já usam apenas nomes relativos em `arquivo` e não contêm caminhos absolutos de máquina: a conferência de sanitização não exigiu alterar bytes. Corpos e registros foram copiados sem edição; `.gitattributes` fixa `-text` nesse diretório. Tamanhos e SHA-256 dos corpos disponíveis foram conferidos contra os registros, inclusive o HTML original antes de omiti-lo da cópia.

| Registro (relativo ao diretório de evidências) | Corpo versionado |
|---|---|
| `senado_legislacao/senado_legislacao_robots.captura.json` | nenhum (recusa) |
| `dou/dou_robots.captura.json` | nenhum (recusa) |
| `lexml/lexml_robots.captura.json` | `lexml_robots.txt` |
| `normas_leg/normas_leg_robots.captura.json` | `normas_leg_robots.txt` |
| `camara_legislacao/camara_legislacao_robots_portal.captura.json` | `camara_legislacao_robots_portal.txt` |
| `camara_legislacao/camara_legislacao_robots_legin.captura.json` | `camara_legislacao_robots_legin.txt` |
| `camara_legislacao/camara_legislacao_pesquisa.captura.json` | HTML omitido |

SHA-256 do HTML da Câmara conforme captura: `2735440e8cc2c54f71b610af8b0dd38fcb0a46110ef1b9b667b20cc90bda49f1`.

## Aplicação do roteiro e pendências IL.2-b

- Senado e DOU saem de `FONTES_SONDA`, entram em `FONTES_BARRADAS` com motivo e data, e seus hosts entram em `HOSTS_RECUSADOS`. Suas seções do roteiro não têm comandos executáveis. A recusa por host vale antes do transporte em toda entrada da CLI e da API: fonte-sonda, alias de conector (inclusive `senado`), com ou sem sonda e ambos os modos de UA; inclui robots.txt, todas as etapas de consulta e destinos de redirecionamento. Nenhum conector atual admite o host do DOU. A confirmação do titular para host B não remove essas barreiras. O filtro pertence ao instrumento de captura; conectores do serviço e transporte permanecem inalterados.
- LexML permanece só com robots no catálogo. `/busca/SRU` sai de `rotas` e `consultas`; não foi pedida. `/urn` e `/sru` aparecem no robots, mas não têm página oficial lida que documente endpoints. Não foram promovidas ao catálogo e não houve descoberta fora do instrumento.
- O instrumento não interpreta `Crawl-delay`. O intervalo de 5 segundos é pendência IL.2-b para futuras sondas; não se afirma enforcement automático. Nenhuma nova requisição foi feita nesta entrega.
- `Allow: /` no normas.leg.br não documenta rota de texto nem API: continua só robots.
- A Câmara publica pontos de entrada da pesquisa e coleções; não houve consulta ao formulário, pesquisa avançada, coleção ou norma. Essas rotas continuam fora do catálogo até tratamento IL.2-b.

São aplicações das regras existentes de `docs/S0-SONDAS.md`, sem mudança de critério de `verified` ou dos pisos da Porta L.

## Consequências para a Porta L

No lote IL.2 de hoje, nenhuma rota viva capturada entrega texto de dispositivo, versão em data D, anexo ou remissão resolvida. O único caminho de conteúdo mantido no catálogo é `/legislacao` da Câmara, uma página de entrada da pesquisa. Robots 200 não comprova capacidade normativa.

| Capacidade da matriz IL.1 | Situação neste lote |
|---|---|
| (a) texto publicado | Sem rota viva de texto demonstrada: DOU barrado; Câmara só pesquisa, sem captura de publicação de norma |
| (b) consolidado vigente | Sem rota viva demonstrada de texto consolidado; normas.leg.br só robots; Senado barrado |
| (c) redação em data D | Sem rota viva demonstrada de versão ou cadeia temporal; consultas Senado e LexML não executadas |
| (d) anexos | Sem rota viva demonstrada de anexo; os casos previstos não foram consultados |
| (e) remissões | Sem rota viva demonstrada de remissões resolvidas; nenhum corpo de norma ou resposta de API capturado |

Isso descreve apenas este lote, sem concluir indisponibilidade geral dos acervos, incapacidade das fontes ou resultado da Porta L. Planalto e acervo instalado ficam fora desta consolidação. IL.3 e a apuração da matriz continuam necessários.


## IL.2-b.1: buscas da Câmara

Buscas executadas pelo supervisor em 05/11/2026, pelo instrumento, UA identificado `freoa-verifica/1.4.0a2 (+https://github.com/rickfreoa/freoa-verifica)`. Conferência local por Codex na sessão de escrita IL.2-b.2, worktree `C:\dev\fv14-il2`, ramo `feat/il2b2-camara-normas`, base informada `1077b1d`. Sem rede, sondas ou novas capturas nesta consolidação. HTMLs tratados como dados: cada URL abaixo consta como `href` de um link da respectiva resposta. Tamanhos e SHA-256 recalculados, iguais aos registros e ao log do supervisor `C:\dev\fv14-sondas\il2b1-buscas.txt`.

| Chave da busca | Resultado | Bytes HTML | SHA-256 HTML | URL publicada (nível A) |
|---|---|---|---|---|
| `camara_legislacao_busca_lei6404` | 200 `text/html` | 62219 | `4026cacd902d161f50df1dcd976f6845cf7a867c5fff1301c845f19f13642878` | `https://www2.camara.leg.br/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-368447-norma-pl.html` |
| `camara_legislacao_busca_lc123` | 200 `text/html` | 59778 | `9bd90cfad8c6c0fed23f589a24e90e1cb1ee415c824c76034d9e36cb470aedb8` | `https://www2.camara.leg.br/legin/fed/leicom/2006/leicomplementar-123-14-dezembro-2006-548099-norma-pl.html` |
| `camara_legislacao_busca_lei13874` | 200 `text/html` | 62896 | `c0377cd867d3a3b1b29c6713a6629b41055daa3726053512473893070174744d` | `https://www2.camara.leg.br/legin/fed/lei/2019/lei-13874-20-setembro-2019-789149-norma-pl.html` |

Os três `.captura.json` estão em [il2a-sondas/camara_legislacao/](il2a-sondas/camara_legislacao/), copiados byte a byte dos registros locais, sem edição; igualdade de bytes e hashes conferida após a cópia. Os HTMLs permanecem fora do repositório, em `C:\dev\fv14-sondas\camara_legislacao\`; hashes acima. Esta seção acrescenta três registros aos sete do lote IL.2-a, totalizando dez; os quatro corpos de robots permanecem iguais.

Robots de `www2.camara.leg.br`: `camara_legislacao_robots_legin.txt`, 5.809 bytes, SHA-256 `b725bf41f0e293419518714b83edb1c2de6728c5156cba037b848ab0788bee8f`, conferido com seu registro e a cópia preservada. Grupo único `User-Agent: *`; nenhum dos 230 `Disallow` alcança os três caminhos exatos, inclusive considerando `*` e âncora final `$`.

IL.2-b.2 cataloga somente esses três caminhos de `www2`, nível A, sem consulta e sem prefixo; `origem_hosts` associa cada caminho à chave e ao hash da resposta que o publica. Roteiro com chaves novas `camara_legislacao_norma_lei6404`, `camara_legislacao_norma_lc123` e `camara_legislacao_norma_lei13874`. Nenhum comando foi executado nesta sessão. Links publicados nessas páginas (publicação original, texto atualizado, anexos) só entram no IL.2-b.3, depois de capturados. Nenhuma capacidade normativa ou `verified` demonstrado; sem mudança de regra. Auditoria independente fica com a outra sessão.

Valida??o IL.2-b.2: `python -m pytest tests/test_sondas.py tests/test_captura_instrumento.py -q -p no:cacheprovider --basetemp C:\dev\tmp\pt-il2b2` ? **389 passed**. Testes com constantes independentes, transporte substitu?do e mutantes de remo??o/expans?o/altera??o de rotas, libera??o de consulta, destino e chave do roteiro, proveni?ncia e `Disallow` aplic?vel. Su?te completa n?o executada nesta sess?o; auditoria independente pendente.

## IL.2-b.2: páginas de norma da Câmara

Sondas do supervisor em 05/11/2026, pelo instrumento com UA identificado `freoa-verifica/1.4.0a2 (+https://github.com/rickfreoa/freoa-verifica)`, log `C:\dev\fv14-sondas\il2b2-normas.txt`. Consolidação local por Codex, sessão de escrita IL.2-b.3, no worktree `C:\dev\fv14-il2`, ramo informado `feat/il2b3-camara-textos`, base informada `6c9e39d` (main com PR #32). Sem rede, sondas ou novas capturas nesta sessão. HTMLs tratados como dados; tamanhos e SHA-256 recalculados e conferidos com os registros e os valores informados pelo supervisor.

| Chave da página | Resultado | Bytes HTML | SHA-256 HTML |
|---|---|---|---|
| `camara_legislacao_norma_lei6404` | 200 `text/html` | 85675 | `882ca0784ab7495c6f61725373f8efe15950845313090818aeb0ec3742023a13` |
| `camara_legislacao_norma_lc123` | 200 `text/html` | 74769 | `04aee462753d1eaa1caae30fe5be953a4160c343b20565135cf024cab1a842c0` |
| `camara_legislacao_norma_lei13874` | 200 `text/html` | 53481 | `01399e663bc3c108d0eb1a58ebdda1a56a89ef549db537215bd9c4642133b3c3` |

O que cada página efetivamente publica como links e rótulos (sem captura dos destinos):

- Lei 6.404/1976: texto atualizado em HTML/DOC/PDF e publicação original em HTML; não foram observados links de veto, republicação ou anexo nessa página. A seção de normas relacionadas publica atos com tipo de ação e dispositivos, incluindo Alteração, Revogação Parcial, Acréscimo de Artigo/Parágrafo e ações sem eficácia. A MP 881/2019 aparece com ação Alteração e referência ao art. 85, caput, §§ 1º e 2º, e art. 294-A; seu link relativo resolve para `-norma-pe.html`.
- LC 123/2006: texto atualizado em HTML/DOCX/PDF, publicação original, veto e três republicações em HTML; anexo principal e três links de anexos de republicação em PDF. Normas relacionadas com rótulos como Alteração, Alteração Condicionada, Revogação, Revogação Parcial e Acréscimo (inclusive de Anexo), além de regulamentações. Esses rótulos não são conclusão própria sobre eficácia ou vigência.
- Lei 13.874/2019: texto atualizado em HTML/DOC/PDF, publicação original e veto em HTML; não foram observados links de republicação ou anexo nessa página. Normas relacionadas com Alteração, Revogação Parcial, Regulamentação e Mantém Veto. Não se presume que a lista seja uma cadeia temporal completa.

Os oito destinos selecionados foram extraídos de `href` e resolvidos contra a URL da página capturada, sem fabricar slug ou identificador. Host comum: `https://www2.camara.leg.br`. A coluna origem identifica `camara_legislacao_norma_<origem>.html`, com hash na tabela acima; essa associação consta também de `origem_hosts` no catálogo, nível A.

| Destino | Origem | Caminho exato resolvido |
|---|---|---|
| texto atualizado HTML | lei6404 | `/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-368447-normaatualizada-pl.html` |
| publicação original HTML | lei6404 | `/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-368447-publicacaooriginal-1-pl.html` |
| página da MP 881/2019 | lei6404 | `/legin/fed/medpro/2019/medidaprovisoria-881-30-abril-2019-788037-norma-pe.html` |
| texto atualizado HTML | lc123 | `/legin/fed/leicom/2006/leicomplementar-123-14-dezembro-2006-548099-normaatualizada-pl.html` |
| publicação original HTML | lc123 | `/legin/fed/leicom/2006/leicomplementar-123-14-dezembro-2006-548099-publicacaooriginal-156405-pl.html` |
| anexo principal PDF | lc123 | `/legin/fed/leicom/2006/leicomplementar-123-14-dezembro-2006-548099-anexo-pl.pdf` |
| texto atualizado HTML | lei13874 | `/legin/fed/lei/2019/lei-13874-20-setembro-2019-789149-normaatualizada-pl.html` |
| publicação original HTML | lei13874 | `/legin/fed/lei/2019/lei-13874-20-setembro-2019-789149-publicacaooriginal-159080-pl.html` |

Os três `.captura.json` foram copiados byte a byte para [il2a-sondas/camara_legislacao/](il2a-sondas/camara_legislacao/), sem edição; igualdade de bytes conferida após a cópia. São treze registros no diretório de evidências, mantendo os quatro corpos de robots. HTMLs não versionados, preservados apenas fora do repositório em `C:\dev\fv14-sondas\camara_legislacao\`; hashes acima.

Robots www2 preservado: 5.809 bytes, SHA-256 `b725bf41f0e293419518714b83edb1c2de6728c5156cba037b848ab0788bee8f`, grupo único `User-Agent: *`. Nenhum dos 230 `Disallow` alcança os oito caminhos, considerando curingas `*` e âncora final `$`; conferência offline, sem afirmar interpretação automática de robots pelo instrumento.

IL.2-b.3 cataloga somente esses oito destinos adicionais, sem consulta ou prefixo, com chaves novas `camara_legislacao_textos_*` no roteiro. Limitação: `FonteSonda.mimes` é por fonte, sem restrição por rota. `application/pdf` foi acrescentado para o anexo principal da LC 123, mas também fica aceito nas demais rotas de conteúdo dessa fonte; robots continua exclusivamente `text/plain`. Não foram liberados os demais links observados. Nenhum destino foi capturado nesta sessão, nenhuma capacidade da Porta L ou `verified` demonstrado; sem mudança de regra. Auditoria independente fica com a outra sessão.

Validação IL.2-b.3: `python -m pytest tests/test_sondas.py tests/test_captura_instrumento.py -q -p no:cacheprovider --basetemp C:\dev\tmp\pt-il2b3` — **454 passed**. Constantes independentes para os oito destinos, MIME, proveniência e metadados das três capturas; transporte substituído; rejeição de variantes antes do transporte; mutantes de remoção/expansão/alteração de rotas, consulta indevida, MIME, proveniência, roteiro (host, identificador, query, prefixo, chave, destino e remoção) e `Disallow` aplicável. Suíte completa não executada; auditoria independente pendente. Sem commit ou push.

## IL.2-b.3: textos da Câmara

Registro das oito sondas do supervisor em 05/11/2026, log `C:\dev\fv14-sondas\il2b3-textos.txt`, instrumento `1.4.0a2`, UA identificado. Conferência local por Codex, sessão de escrita, worktree `C:\dev\fv14-il2`, ramo `feat/il2b3-registro`, base `5aa2ff2` (main com PR #33). Sem rede, sondas ou novas capturas nesta sessão. Esta seção atualiza as hipóteses dos lotes anteriores; não apura a Porta L.

Os oito corpos foram lidos como dados, com tamanho e SHA-256 recalculados e iguais aos respectivos `.captura.json` e ao log. MIME conforme `content_type` dos registros (HTML com `charset=UTF-8` no cabeçalho). Capturas entre `2026-11-05T10:11:00.992588+00:00` e `2026-11-05T10:11:46.238434+00:00`.

| Chave | HTTP | Bytes | SHA-256 do corpo | MIME |
|---|---|---|---|---|
| `camara_legislacao_textos_atualizado_lei6404` | 200 | 686299 | `ee3f76848ce42def5e758ed77b994d2a5d05598c4e9dc8b43771c801aa4a854c` | `text/html` |
| `camara_legislacao_textos_original_lei6404` | 200 | 365194 | `7dc335d77b1b30f7165c27cb62ce4525bb464b68bf4d03bf5387d7d264156822` | `text/html` |
| `camara_legislacao_textos_mp881_lei6404` | 200 | 47221 | `677752f6feaea991ca461933384b451d46d1a2f9c9d0cc7a6b6708de1b73b9e1` | `text/html` |
| `camara_legislacao_textos_atualizado_lc123` | 200 | 796759 | `ad9b586fdf7864ba47dcdeabb20af2cdc9882c8a7511e75461b4321c2e59e459` | `text/html` |
| `camara_legislacao_textos_original_lc123` | 200 | 166709 | `65775c1f3e09819229f05c0a10adbeeb6d0bfd8eb0a481c01faaba3bb16e5a99` | `text/html` |
| `camara_legislacao_textos_anexo_lc123` | 200 | 120702 | `c8abdd8ca254a81e4d274335c705630c21ed3cf24948ba70fc12ab145a096887` | `application/pdf` |
| `camara_legislacao_textos_atualizado_lei13874` | 200 | 117838 | `a231acb388e65b023db0536b60d134e146890f1f642413d1d4e8616317a3c6b0` | `text/html` |
| `camara_legislacao_textos_original_lei13874` | 200 | 103071 | `4fd5ddbc75e7dc56ab3c2d53c7abdcbb3eee46c894e18b5a3d07041e7cd244c3` | `text/html` |

Características estruturais confirmadas nos corpos locais:

- **Textos atualizados:** HTML de editor, com dispositivos em parágrafos e rótulos textuais no início, sem estrutura semântica própria que identifique cada dispositivo. Lei 6.404 e LC 123 usam `<p class="western">` e `<font>`; a Lei 13.874 usa `<p class="MsoHeader">`, sem `<font>`. A extração exige segmentação por rótulo e normalização das quebras de linha internas: por exemplo, `Art. 116.` na Lei 6.404, `a)`, `Parágrafo único.` e `§ 1º` no conjunto. As classes e estilos são de apresentação, não identificadores normativos.
- **Redações e notas:** nenhum dos três textos atualizados contém `<strike>`, `<s>`, `<del>` ou `line-through`. Não oferecem redações anteriores riscadas nem versão histórica em D: apresentam a redação atualizada, com notas textuais de alteração e marcadores de revogação. Foram confirmadas notas de redação dada, de acréscimo (`Parágrafo acrescido pela Lei...`) e de revogação (`Revogado pela...`), identificando o ato responsável; não se presume o literal `Incluído pela` sugerido na observação inicial. Isso não comprova vigência, produção de efeitos ou correção da consolidação por dispositivo.
- **Publicações originais:** outra família de HTML, com `<P>`, `<CENTER>` e `<TABLE>` contendo alíneas; texto apresentado como publicação original no DOU. As páginas indicam DOU de 17/12/1976 (Lei 6.404, suplemento), 15/12/2006 (LC 123) e 20/9/2019 (Lei 13.874, edição extra B). Essas indicações são dados das páginas, sem confronto com os exemplares do DOU nesta sessão.
- **MP 881/2019:** página `-norma-pe.html` de dados da norma, não o texto da MP. Publica origem, situação rotulada `Convertida em Lei`, relação com a Lei 13.874/2019 e links de publicação original e retificação. O texto dos destinos não foi capturado neste lote; os rótulos não substituem análise temporal.
- **Anexo LC 123:** corpo com assinatura `%PDF-1.6`, MIME `application/pdf`. Conteúdo interno e equivalência do anexo não examinados.

Os oito `.captura.json` foram copiados para [il2a-sondas/camara_legislacao/](il2a-sondas/camara_legislacao/), sem edição, com igualdade de bytes conferida após a cópia. Os sete HTMLs e o PDF permanecem somente em `C:\dev\fv14-sondas\camara_legislacao\`, fora do repositório. Nenhuma fixture criada, nenhum código de produto ou regra alterado. Auditoria independente fica com a outra sessão; nenhuma conclusão de `verified` ou aprovação da Porta L.

Validação IL.2-b.3 REG: `python -m pytest tests/test_sondas.py -q -p no:cacheprovider --basetemp C:\dev\tmp\pt-il2b3reg` — **391 passed in 19.96s**. A primeira execução teve 390 aprovados e uma falha na expectativa antiga de 13 registros. O teste de integridade foi atualizado para os 21 registros, com constantes independentes de tamanho/hash e conferência dos oito novos nomes, MIME, URLs e ausência dos corpos. `TMP`/`TEMP` em `C:\dev\tmp`; sem commit ou push. Suíte completa não executada; auditoria independente pendente.
