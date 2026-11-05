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

- Senado e DOU saem de `FONTES_SONDA`, entram em `FONTES_BARRADAS` com motivo e data, e seus hosts entram em `HOSTS_RECUSADOS`. Suas seções do roteiro não têm comandos executáveis. A confirmação do titular para host B não remove essas barreiras.
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
