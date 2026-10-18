# Cobertura efetiva das fontes

Apuração R4 em 2026-10-18T03:22:55.400947+00:00. Parecer independente de 18/10/2026 rejeitou o candidato anterior; as correções posteriores ainda exigem nova auditoria.

Corpus coletado em `.tmp/home-run`; snapshot R5 em arquivo único `.tmp/release/freoa-verifica-snapshot-20261018.tar.gz`; instalação e medição R5 em homes novos. Captura com hash não implica vigência ou juízo jurídico.

| Fonte | Capturas no snapshot |
|---|---:|
| bcb | 402 |
| cvm_colegiado | 40 |
| cvm_normas | 299 |
| planalto | 121 |
| senado | 27 |
| stj | 48 |
| tcu | 26 |

| Fonte | Prova disponível e limite |
|---|---|
| Planalto | Epígrafe confrontada; HTML oficial com hash e árvore de dispositivos sujeita às sentinelas. Prazo 180 s, mínimo 256 bytes/s, 30 MiB e três tentativas transitórias. Dos 27 timeouts legados, 26 atos foram capturados (seis ambíguos) e um respondeu 404. Negativa de health funciona. |
| Senado | 27 respostas JSON de identificação/datas; perfil sem dispositivos. Metadados não substituem o texto normativo. |
| CVM normas | DOCX, PDF e HTML conforme disponibilidade, com confronto de identidade. Declaração incompleta não autoriza verified. Negativa de health reconhece marcador oficial de zero; três mutantes do benchmark continuaram indisponíveis por HTTP 410. |
| BCB/CMN | JSON oficial, epígrafe e campos de tipo, número e data. Situação cadastral não demonstra vigência temporal. |
| STF | Processo por classe+número, incidente e abaDecisoes. Julgamento só é encontrado com identificação e documento associado na lista capturada; o vínculo pode ser PDF ou RTF. RG preserva listas de processos líderes; 25 temas antes rejeitados foram recuperados. Busca sob WAF permanece indisponível. |
| STJ | Doze recursos mensais disponíveis por órgão configurado: Corte Especial, Segunda Seção, Terceira e Quarta Turmas. Sem o limite anterior de 12 registros/recurso. A data do recurso não é a data do julgamento. Espelho comprova ementa, não inteiro teor. O snapshot contém acervo principal e capturas; índice auxiliar STJ não é distribuído. Consulta pública sondada: desafio_http_403, sem contorno. |
| TCU | 2.000 itens percorridos, 1.800 identificadores distintos. Ligação por número, ano da sessão e colegiado. Capturas usam páginas JSON originais; sumário é ementa. API documentada só publica inicio/quantidade; varredura por número é limitada. Ausência no recorte não é inexistência. |
| CVM Colegiado | Busca oficial por processo e páginas individuais; 40 decisões na semente. Diretórios anuais 404/410 têm fallback oficial por datas. Primeira página não prova completude histórica. Ata, item decisório e processo são identidades distintas. |
| TJSP | Consulta CJSG tentada por número; julgamento não foi identificado nos dois casos medidos. Formulário sondado retornou CAPTCHA; não houve contorno. |
| DataJud | Alias por segmento/tribunal CNJ e normalização de caixa. Confirma apenas processo público; dois processos confirmados no benchmark, não julgamentos. Dígito inválido impede consulta. |

| Tribunal | Decisões com captura | Datas de julgamento |
|---|---:|---|
| CVM | 40 | 2023-12-19 a 2026-09-18 |
| STJ | 32401 | 2024-06-10 a 2026-08-26 |
| TCU | 1800 | 2026-08-26 a 2026-10-14 |

STF: 1399 temas como metadados, sem inferir igual número de capturas ou julgamentos.

Pendências terminais por checkpoint:

- alterador: `http_404` — 2.
- alterador: `nao_resolvido` — 5.
- alterador_contexto: `ALTERADORES_PENDENTES` — 1.
- alterador_contexto: `IDENTIDADE_NAO_DECLARADA` — 3.
- stf: `http_404` — 1.
- stf: `stf_busca_textual_sob_waf` — 1.

| Métrica | Antes | Depois |
|---|---:|---:|
| Identidade verificada nos positivos | 54/56 | 56/56 |
| Texto verificado nos positivos | 33/56 | 56/56 |
| Falsos verified nos mutantes | 1/40 | 0/40 |
| Decisões reais identificadas | 0/15 | 6/15 |
| Negativa conclusiva nas decisões falsas | 0/5 | 2/5 |

As seis consultas STJ sem confirmação não têm correspondência de classe+número no recorte. Ausência local não é prova de inexistência. D009 permanece processo_confirmado sem documento associado ao julgamento na aba consultada; D018/D019 são processos confirmados via DataJud. Negativas conclusivas só são usadas quando a fonte as declara, com captura.

Offline final: 528 passed, 30 deselected in 77.17s (0:01:17). Live final: 30 passed, 528 deselected in 230.61s (0:03:50). Health negativos Planalto/CVM normas: respostas esperadas no doctor live preservado. O doctor da instalação final é offline.

Capturas da tabela são as exportadas; consultas sob demanda do benchmark podem acrescentar capturas apenas no home-final. O bootstrap local não integra o snapshot. Evidências por caso preservadas no pacote local de avaliação.

Contratos oficiais consultados: [Colegiado CVM](https://conteudo.cvm.gov.br/decisoes/index.html), [webservice TCU](https://sites.tcu.gov.br/dados-abertos/webservices-tcu/), [consulta STJ](https://www.stj.jus.br/sites/portalp/Processos/Consulta-Processual/), [rotas DataJud](https://datajud-wiki.cnj.jus.br/api-publica/endpoints/). Sondagens via transport e hashes estão em .tmp/r4-probes.txt, .tmp/r4-stj-public.txt, .tmp/r4-stf-negative.txt e nos recibos capturados.

## P5: precedentes qualificados do STJ e súmulas do STF

Cobertura adicionada em 18/10/2026 (decisão 0036). Contrato verificado por sondagem via transport; fixtures em `tests/fixtures` são recortes do corpo oficial.

| Fonte | O que entra no índice local | Limites |
|---|---|---|
| STJ precedentes qualificados | `fv sync stj` baixa `Temas.csv` e `Processos.csv` do pacote CKAN `precedentes-qualificados` (CSV UTF-8, vírgula, campos com quebra de linha entre aspas; chave `sequencialPrecedente`) e grava no mesmo FTS dos espelhos: classe, número, situação, questão submetida, tese firmada, súmula originada e processos paradigma (`leadingCase=S`). Chave `tema:<n>` (autoridade B, repetitivo) e `iac:<n>` (B, IAC/IRDR). O CSV integral fica capturado com hash; a tese é texto dessa captura. | `tipoPrecedente` real é `Tema`, não "Tema Repetitivo". Controvérsia, SIRDR e PUIL não são ingeridos. Temas cancelados ou revisados entram com a situação no texto e mantêm o rótulo B: o rótulo não mede vigência. Os paradigmas vêm de `Processos.csv`, outra captura (hash em `_processos_sha256`). O CSV repete algumas linhas; vale a última. O STJ publica o conjunto inteiro a cada sync; não há versão histórica. |
| STF súmulas e súmulas vinculantes | `fv sync stf` captura o sumário oficial (`sumariosumulas.asp?base=30` e `base=26`, HTML, 200 sem WAF) e depois a página de cada súmula (`&sumula=<id>`), com hash, host e prefixo `/jurisprudencia/sumariosumulas.asp` permitidos. Extrai número, enunciado e observação (`superada`, `cancelada`). Espécie `sumula` ou `sumula_vinculante`, autoridade A, chaves `sumula:<n>` e `sv:<n>`. | A página sem parâmetro é só casca: o enunciado não está no sumário, daí uma requisição por súmula (cerca de 800, retomáveis por checkpoint). Cancelada e superada mantêm A com a observação no texto; o rótulo não mede vigência. A coluna `decision.kind` grava `acordao` para súmula vinculante (a restrição do esquema não prevê o valor); a espécie correta está nos atributos de autoridade. A página do enunciado traz também jurisprudência selecionada, que não é indexada. Busca textual livre do STF segue sob WAF. |

## Reconstrução histórica e limites gerais

Revisão corretiva de 18/10/2026: no HTML capturado da LSA, art. 250, III, apenas o travessão está marcado com `<s>`. Não há redação anterior completa nesse parágrafo. O parser passa a preservar o texto do inciso sem fabricar uma redação anterior composta de pontuação. Quando a fonte contém redações anteriores reais riscadas, elas são preservadas. Captura de ato alterador e data completa melhoram a proveniência, mas não provam o início da vigência (decisão 0002).

Não há garantia de completude histórica ou atualização contínua, nem reconstrução integral demonstrada. Suporte jurídico a proposições não é avaliado; tratamento sistemático de precedentes superados não foi demonstrado. Demais tribunais e segmentos não têm cobertura jurisprudencial comprovada. STJ SCON/consulta pública, STF e TJSP podem impor barreiras oficiais; não são contornadas. Busca local vazia nunca prova inexistência. Identidade, literalidade e tempo são dimensões distintas.

Atualização R5 de 18/10/2026: 814 obras e 963 capturas. Foram capturadas a MP 449/2008 e as MPs 959/2020, 869/2018, 1.124/2022 e 1.317/2025, com vínculos a atos alteradores recalculados somente sobre capturas autenticadas. Permanecem pendentes a identidade declarada da LC 182/2021 e as respostas 404 da Lei 10.931/2004 e do Decreto-Lei 4.037/1942. A presença de outras redações em documentos não implica que todos os atos alteradores de toda a legislação tenham sido capturados.
