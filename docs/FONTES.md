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
| STJ precedentes qualificados | `fv sync stj` baixa `Temas.csv` e `Processos.csv` do pacote CKAN `precedentes-qualificados` (CSV UTF-8, vírgula, campos com quebra de linha entre aspas; chave `sequencialPrecedente`) e grava no mesmo FTS dos espelhos: classe, número, situação, questão submetida, tese firmada e súmula originada. A situação também é campo estruturado (`situacao_precedente`) com alerta `PRECEDENTE_NAO_VIGENTE_NA_FONTE` (decisão 0036). Chave `tema:<n>` (autoridade B, repetitivo) e `iac:<n>` (B, IAC/IRDR). O CSV integral fica capturado com hash; a tese é texto dessa captura. | `tipoPrecedente` real é `Tema`, não "Tema Repetitivo". Controvérsia, SIRDR e PUIL não são ingeridos. Temas cancelados ou revisados mantêm o rótulo B (espécie), com situação estruturada e alerta. Os processos paradigma (`Processos.csv`, outra captura) ficam só como metadado não autenticado, fora do texto probatório. O CSV repete algumas linhas: vale a última, e divergência entre elas é declarada. O STJ publica o conjunto inteiro a cada sync; não há versão histórica. |
| STF súmulas e súmulas vinculantes | `fv sync stf` captura o sumário oficial (`sumariosumulas.asp?base=30` e `base=26`, HTML, 200 sem WAF) e depois a página de cada súmula (`&sumula=<id>`), com hash, host e prefixo `/jurisprudencia/sumariosumulas.asp` permitidos. Extrai número, enunciado e observação (`superada`, `cancelada`). Espécie `sumula` ou `sumula_vinculante`, autoridade A, chaves `sumula:<n>` e `sv:<n>`. | A página sem parâmetro é só casca: o enunciado não está no sumário, daí uma requisição por súmula (cerca de 800, retomáveis por checkpoint). Cancelada e superada mantêm A, com `situacao_precedente` estruturada e alerta; súmula sem observação fica `desconhecida`, não vigente. A coluna `decision.kind` grava `acordao` para súmula vinculante (a restrição do esquema não prevê o valor); a espécie correta está nos atributos de autoridade. A página do enunciado traz também jurisprudência selecionada, que não é indexada. Busca textual livre do STF segue sob WAF. |

## 1.1.0: o que mudou na cobertura e na prova

| Fonte | Mudança | Limite que permanece |
|---|---|---|
| CVM normas em PDF | Dispositivos endereçáveis por estrutura inferida (`cvm-pdf-2`, decisão 0037): notas "• ... com redação dada / incluído / revogado" viram histórico do dispositivo; texto citado de outra norma até "(N.R.)" não vira dispositivo; cabeçalho e rodapé saem por geometria, repetição e forma de rótulo (issue `MARGEM_DESCARTADA`); imagem no corpo marca os dispositivos vizinhos. Na Resolução CVM 175 (parte geral): 143 artigos, 801 dispositivos. | Dispositivo que termina junto a uma margem descartada recebe `MARGEM_ADJACENTE` e não obtém conclusão textual (67 de 801 na Res. 175); redações antigas sem rasura que persistem no PDF ficam ambíguas (6 na Res. 175); `PDF_SEM_RASURAS` continua valendo. |
| BCB/CMN | Resoluções do CMN anteriores a 2020 (tipo "Resolução" no BCB) são localizadas e identificadas como CMN pelo preâmbulo; "Circular BCB nº N" reconhecida; data de efeito declarada em `Atualizacoes` ("Revogação total a partir de D/M/AAAA") vira `data_efeito` (decisão 0035); ritmo de 0,2 req/s; falha de transporte não apaga leitura autêntica. | Circulares cujo JSON oficial traz só aviso de "inteiro teor em outro endereço" respondem `DOCUMENTO_SEM_ESTRUTURA`. Sem "a partir de", a data de efeito da revogação continua desconhecida. |
| STJ precedentes qualificados e STF súmulas | Ver seção P5 (decisão 0036): situação estruturada (`situacao_precedente`) e alerta `PRECEDENTE_NAO_VIGENTE_NA_FONTE`; A/B classificam a espécie, não garantem aplicabilidade atual. | Atualização do STF depende de limpar o checkpoint das súmulas; paradigmas do STJ são metadado não autenticado. |
| STJ espelhos | Semente configurada para sete órgãos não criminais (Corte Especial, 1ª e 2ª Seções, 1ª a 4ª Turmas) e 24 meses. | O portal de dados abertos do STJ não respondeu (timeout de 40 s) durante a montagem do snapshot 1.1.0; a cobertura distribuída é a medida abaixo, e `fv sync --semente --fontes stj` amplia quando o portal responder. STJ anterior a 2022 não existe em dados abertos. |
| Saída para modelos de linguagem | Envelope `DOCUMENTO OFICIAL` sempre aplicado e não fechável por dentro; `alertas_conteudo` para padrões de instrução e caracteres invisíveis; PDFs de decisão do STF/TJSP lidos em processo isolado. | A triagem sinaliza; não comprova resistência do modelo cliente a injeção. |

### Avaliação independente (gold 1.1.0)

Conjunto de 60 casos montado por agente sem acesso ao código, a partir das páginas oficiais, selado antes da execução (sha256 `a7e0e8314183a524c71bac68965e730cdae80537793cf49ce0f07c253015aab7`). Resultado medido antes das correções que ele motivou: 0 de 20 mutantes com `verified` falso; 18 de 30 positivos com texto verificado (dos 12 restantes, 4 eram erros do próprio gabarito — trecho abrangendo caput e inciso ou redação antiga —, 5 eram resoluções do CMN anteriores a 2020, corrigidas, e 3 eram Circular sem texto no JSON oficial); 10 de 10 decisões responderam `nao_confirmado_no_acervo` (julgados fora da janela do acervo; as 4 falsas nunca foram confirmadas, e a ferramenta não afirma inexistência por ausência local). Repetido no HEAD final, em diretório novo com o snapshot 1.1.0 instalado: 0 de 20 mutantes com `verified` falso (18 recusados corretamente; 2 com o Planalto respondendo 300/404 para número ou ano inexistente, contados como erro); 23 de 30 positivos com texto verificado (os 7 restantes: 4 erros do gabarito e 3 Circulares sem texto no JSON oficial, `DOCUMENTO_SEM_ESTRUTURA`); 0 de 10 decisões confirmadas, porque os julgados escolhidos estão fora do recorte do acervo distribuído. O conjunto não é exaustivo nem estatisticamente representativo.

Snapshot 1.1.0 instalado em diretório novo: 826 obras e 2.028 capturas; decisões por tribunal: STJ 32.668, TCU 1.800, STF 799 (súmulas e súmulas vinculantes, além dos temas de repercussão geral como metadados), CVM 40.

## Reconstrução histórica e limites gerais

Revisão corretiva de 18/10/2026: no HTML capturado da LSA, art. 250, III, apenas o travessão está marcado com `<s>`. Não há redação anterior completa nesse parágrafo. O parser passa a preservar o texto do inciso sem fabricar uma redação anterior composta de pontuação. Quando a fonte contém redações anteriores reais riscadas, elas são preservadas. Captura de ato alterador e data completa melhoram a proveniência, mas não provam o início da vigência (decisão 0002).

Não há garantia de completude histórica ou atualização contínua, nem reconstrução integral demonstrada. Suporte jurídico a proposições não é avaliado; tratamento sistemático de precedentes superados não foi demonstrado. Demais tribunais e segmentos não têm cobertura jurisprudencial comprovada. STJ SCON/consulta pública, STF e TJSP podem impor barreiras oficiais; não são contornadas. Busca local vazia nunca prova inexistência. Identidade, literalidade e tempo são dimensões distintas.

Atualização R5 de 18/10/2026: 814 obras e 963 capturas. Foram capturadas a MP 449/2008 e as MPs 959/2020, 869/2018, 1.124/2022 e 1.317/2025, com vínculos a atos alteradores recalculados somente sobre capturas autenticadas. Permanecem pendentes a identidade declarada da LC 182/2021 e as respostas 404 da Lei 10.931/2004 e do Decreto-Lei 4.037/1942. A presença de outras redações em documentos não implica que todos os atos alteradores de toda a legislação tenham sido capturados.
