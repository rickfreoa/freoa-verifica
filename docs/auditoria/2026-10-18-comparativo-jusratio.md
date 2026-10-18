# FREOA Verifica × JusRatio: erros, causas e plano de correção

Oct 18, 2026 · @Ricardo Peres Freoa

## Síntese

O FREOA Verifica v1.0.2 não está pronto para substituir o JusRatio. Não por perder em ranking, mas porque emite "verified" e "vigente\_na\_fonte" em casos nos quais a resposta correta é a oposta. A promessa central do produto (não certificar o que a fonte oficial não sustenta) é violada em dois pontos de alcance sistêmico.

O primeiro: a Constituição. O parser não separa o ADCT do texto permanente, e o art. 5º do ADCT cai no mesmo caminho do art. 5º da CF. Em 58 artigos o texto transitório substitui o permanente sem aviso. `fv verifica "art. 60 da CF"` com o texto do ADCT sai identity, text e temporal verificados; o texto verdadeiro ("A Constituição poderá ser emendada…") sai divergente.

O segundo: normas revogadas. Res. CVM 51/2021 e Res. CMN 5.238/2025, ambas revogadas, saem verified com temporal `vigente_na_fonte` quando se cita um artigo. A revogação é capturada (página do ato na CVM, campo `Revogado` no BCB), mas nenhuma linha de `verify.py` ou `temporal.py` a lê.

O restante se ordena em três camadas. Omissões silenciosas: busca CVM que zera consultas acentuadas, anáfora ("art. 117 da mesma lei") que desaparece do relatório, artigo de PDF da CVM declarado inexistente, ausência local tratada como inexistência. Erros de apresentação: texto vigente rotulado como redação anterior, texto de 2021 devolvido para data de 2000. Fragilidade de busca: ranking lexical, ausência de lookup por número de processo e de norma BCB, acervo de jurisprudência concentrado em 2025 e 2026.

Há um achado lateral que muda a urgência: o FREOA instalado no notebook usado no dia a dia tem 16 a 20 obras e nenhuma decisão no acervo padrão. O acervo completo (814 obras, 34.242 decisões) está em `.tmp/home-final`, fora do caminho que a CLI e o servidor MCP leem.

O que fazer primeiro: congelar o uso do FREOA como verificador em produção, corrigir os dois bloqueadores (ADCT e revogação) com teste de regressão e novo snapshot, e só então tratar busca e cobertura. O JusRatio também erra (devolve o art. 312 do RIR, da CLT e do CPC quando se pede o art. 312 da LSA, que não existe), e nisso o FREOA acerta.

## Método e limites

Foram rodadas 34 consultas no FREOA (12 dispositivos, 2 históricos, 3 buscas de legislação, 4 buscas CVM, 1 BCB, 6 de jurisprudência, 6 verificações e um texto de 9 frases com citações certas e erradas plantadas) e as equivalentes no JusRatio. A comparação usou o repositório público no commit 5d1936f (v1.0.2) com o snapshot de 18/10/2026 instalado, em ambiente isolado, e foi repetida em parte no notebook (C:\\dev\\freoa-verifica-v2), com rede para as fontes oficiais. E2 e E8 se reproduzem com rede; não são artefato de ambiente.

A investigação de causas foi feita por três auditores Claude em contexto isolado (normas CVM/BCB e revogação; extração e vigência; busca e jurisprudência) e por uma passada independente do Codex no notebook, em modo somente leitura. Cursor e Antigravity não rodaram: as duas contas atingiram o limite de uso (Cursor renova em 30/10; Antigravity em cerca de cinco dias). Os achados que sustentam a síntese (ADCT, revogação, N1, N2, N5) foram reproduzidos por mim depois dos relatórios.

Três limites pesam na leitura. O JusRatio não foi tratado como conjunto-ouro: onde ele diverge do FREOA, a fonte oficial decide. A suíte pytest não foi executada e nenhum teste proposto foi escrito. E a própria auditoria alterou o acervo usado: buscas de legislação indexaram normas do BCB no FTS durante as rodadas (de 963 para 1.079 capturas), o que é por si um defeito e obriga a reinstalar o snapshot antes de qualquer nova medição.

## Comparação lado a lado

O FREOA vence onde a pergunta é de identidade e evidência de lei federal; o JusRatio vence em normas infralegais, jurisprudência e em toda pergunta que dependa de vigência do ato inteiro.

| Consulta | FREOA | JusRatio | Quem acerta |
| --- | --- | --- | --- |
| art. 254-A LSA | caput exato, URL, sha256, vigente | artigo inteiro com §§, vigente | ambos |
| art. 312 LSA (não existe) | inexistente | devolve art. 312 do RIR, CLT e CPC sem aviso | FREOA |
| CF art. 5º, XXXVI | inciso exato, mas marcado ambíguo | art. 5º inteiro + ADCT art. 5º | nenhum por inteiro |
| art. 60 CF | texto do ADCT como se fosse da CF, verified | não testado | FREOA erra |
| art. 136 LSA em 01/01/2000 | devolve o texto de 2021 como encontrado | sem consulta por data; tem íntegra histórica | FREOA erra |
| "OPA" (CVM, frase longa) | ok, zero resultados | Res. CVM 215/2024, vigente desde 01/10/2025 | JusRatio |
| "fato relevante" (CVM) | ok, zero resultados | Res. CVM 44/2021 | JusRatio |
| Instrução CVM 358/2002 | busca: http 410 na pasta errada; verifica: verified | REVOGADO, com texto | JusRatio |
| Res. CVM 85/2022 e 51/2021 | verified; com artigo, vigente\_na\_fonte | REVOGADO | JusRatio |
| Res. CMN 4.966 | 15 normas recentes sem relação | norma exata, vigente desde 01/01/2025 | JusRatio |
| REsp 1.736.540 | outros REsps, sem aviso | alerta de identificador ausente | JusRatio |
| REsp 2.210.785 (está no acervo) | não acha pelo número | acha | JusRatio |
| tag along / 254-A | PAS CVM, TCU sem relação, REsp de falência | REsp 1.837.538, EREsp 710.648, consulta CVM AMBEV | JusRatio |
| recesso e apuração de haveres | 1 resultado | 8 acórdãos + Súmula 265/STF | JusRatio |
| Tema 69/STF | zero (STF indisponível por decisão) | RE 574.706 e embargos | JusRatio |
| Súmula 999/STJ (não existe) | nao\_confirmado\_no\_acervo | alerta de verbete ausente | ambos |
| texto com 9 citações plantadas | detecta art. 312 inexistente e Súmula 999; omite "art. 117 da mesma lei" | sem verificação de texto | FREOA, com lacuna |

A vantagem estrutural do FREOA (hash, captura, âncora reproduzível, granularidade de inciso) é real e não existe no JusRatio. Ela só se converte em vantagem jurídica quando o veredito é confiável; hoje, nos dois bloqueadores, a evidência criptográfica acompanha uma resposta errada.

## Erros confirmados, causas e severidade

São 24 defeitos confirmados: 3 bloqueadores, 10 de severidade alta, 11 média ou baixa. A severidade mede o risco para quem confia na saída: falso "verified" pesa mais que omissão silenciosa, e omissão pesa mais que ranking ruim. Caminhos relativos a `freoa_verifica/`.

| # | Defeito | Causa (arquivo:linha) | Classe | Severidade |
| --- | --- | --- | --- | --- |
| B1 | ADCT gravado nos caminhos da CF; 58 artigos com texto transitório verified como permanente | `parsers/html_devices.py:905-914` só abre escopo para anexo e suplemento; `sentinel.py` aceita a substituição | código | bloqueador |
| B2 | Ato revogado (Res. CVM 51, 85; IN 358; Res. CMN 5.238; Res. BCB 428) sai verified e, com artigo, vigente\_na\_fonte | revogação lida em `connectors/cvm_normas.py:367` e `parsers/bcb_json.py:52`, mas só vai para o texto; `verify.py` e `temporal.py` não a consultam; página do ato CVM só é capturada se não houver PDF/DOCX (`cvm_normas.py:184-191`) | código + dados | bloqueador |
| B3 | "Lei 6.404/1976: art. 117 do contrato" vira verified, embora a extração seja provável e aponte outro referente | `service.py:1080` e `verify.py:445` não aplicam o bloqueio de confiança que `verifica-texto` aplica | código | bloqueador |
| A1 | Artigo existente de norma CVM em PDF declarado inexistente (241 documentos) | `cvm_normas.py:419-427` devolve `provisions=[]`; `verify.py:439-443` trata ausência de estrutura como inexistência | código | alta |
| A2 | Ausência no acervo local vira "inexistente" sem negativa oficial | `service.py:866` e `:952` | código | alta |
| A3 | `fv lei --data 2000-01-01` devolve o texto de 2021 como encontrado | `service.py:889-891` não inclui HISTORICO\_ANTERIOR\_AUSENTE nos motivos que suprimem o texto | código | alta |
| A4 | Busca CVM zera consultas longas ou acentuadas (portal informa 30 e 175 resultados) | `cvm_normas.py:297` decodifica UTF-8 como latin-1; `:336` exige a frase literal; `:356` devolve zero mesmo com total > 0 | código | alta |
| A5 | "art. 117 da mesma lei" some do relatório de `verifica-texto` | não resolver anáfora é decisão 0012; o defeito é a omissão calada em `service.py:1180-1260` | código sobre decisão documentada | alta |
| A6 | Juris por número devolve outros processos sem aviso; nem REsp presente no acervo é achado | `service.py:1474-1491` não usa `parse_one` nem `_decision_evidence`; número fora do índice FTS (`migrations/0004`) | código | alta |
| A7 | Busca de legislação indexa candidatos ao vivo no acervo e contamina buscas seguintes | `service.py:744` (`indexar_obra`) sobre o mesmo FTS, sem marca | código | alta |
| A8 | `verifica-texto` corta em 200 citações sem avisar | `service.py:1181` | código | alta |
| A9 | Busca CVM e BCB devolvem `truncado=false` com 175 e 55 resultados na fonte | `service.py:1847` fixo; `cvm_normas.py:242` lê 20 | código | alta |
| A10 | Instalação do notebook com 16 a 20 obras e nenhuma decisão; acervo completo fora do caminho padrão | snapshot não instalado no home padrão; `fv doctor` não alerta | ambiente | alta |
| M1 | Texto vigente rotulado como "redação 1" em `redacoes_anteriores` | `service.py:894-903` inclui todas as redações | código | média |
| M2 | "Instrução CVM 358" buscada na pasta de resoluções (HTTP 410) | `cvm_normas.py:140-149` descarta a espécie | código | média |
| M3 | Itens duplicados por anexo (Res. 232 quatro vezes; anexo não normativo capturado) | `cvm_normas.py:339-351` sem deduplicação por ato | código | média |
| M4 | "Resolução CMN 4.966" não aciona o lookup exato que já existe | `connectors/bcb.py:104-124` só lê número de filtros; ordena por data | código | média |
| M5 | Ranking lexical premia textos curtos (TCU) e termos isolados | `store/repo.py:422` bm25 sem pesos; sem corte de pertinência | código + decisão 0010 | média |
| M6 | Recall baixo: OR só entra se o AND der zero | `service.py:1484` | decisão documentada | média |
| M7 | Fontes marcadas "ok" sem terem sido consultadas; Planalto chamado para busca textual que não suporta | `service.py:692-700`; `connectors/planalto.py:214-221` | código | média |
| M8 | 4.896 de 10.289 anotações sem data do ato alterador (CC, Lei 11.101, LGPD, CPC) | `semente.py:322-383` depende do Senado e ignora a epígrafe já capturada | código | média |
| M9 | "caput" produz falso inexistente em `fv lei` | `service.py:884` sem a resolução canônica do verificador | código | média |
| M10 | Filtro `fonte` ignorado na busca local | `service.py:590` | código | média |
| M11 | Redações anteriores ausentes na fonte sem sinalização; rubricas ("Dever de Lealdade") não indexadas; ADCT não citável; rótulos CVM com mojibake no acervo | `service.py:944-1000`; `snapshot.py:595`; `citation.py`; `cvm_normas.py:297` | dados + código | baixa |

Cobertura do acervo de jurisprudência, para separar lacuna de defeito: STJ 32.401 decisões, quase todas de 2025 e 2026, de quatro órgãos (3ª e 4ª Turmas, 2ª Seção, Corte Especial); TCU 1.800, todas de 2026; CVM 40; STF nenhuma. Precedentes de mérito anteriores a junho de 2024 e súmulas do STF são lacuna de dados, não erro de ranking.

## Divergências entre os auditores

Os auditores concordaram em quase tudo; nas quatro divergências, a reprodução decidiu.

**Revogação (B2).** O Codex classificou o caso da IN 358 como decisão de projeto: identidade confirma existência, não vigência, e o temporal fica `not_assessed` sem dispositivo. A leitura é correta para a citação sem artigo. Não prevalece porque o auditor Claude mostrou o caso com artigo: "art. 1º da Resolução CVM 51/2021" sai `vigente_na_fonte`, e a página oficial diz "REVOGADA pela Resolução 234/25". Reproduzi. `docs/FONTES.md` proíbe usar a situação cadastral para afirmar vigência; não autoriza ignorá-la quando ela afirma revogação.

**Anáfora (A5).** Ambos reconhecem que não herdar a obra é decisão 0012 e deve continuar assim. O defeito não está na regra, está no silêncio: um rótulo explícito ("art. 117") some do relatório, e quem lê presume que o texto foi conferido por inteiro.

**BCB (M4).** O relatório preliminar dizia que a consulta era ignorada. Os dois auditores refutaram: a consulta chega à API (55 resultados, a Res. CMN 4.966 em 42º), mas a ordenação por data e o corte em 15 escondem a norma.

**Datas de alteradores (M8) e ruído BCB na busca (A7).** O Codex não reproduziu nem a data nula do art. 421 nem o ruído BCB e atribuiu a diferença ao acervo. A explicação é a contaminação: a busca indexou normas BCB durante a rodada, e homes distintos têm projeções distintas. A contagem do auditor Claude (4.896 anotações sem data) mostra que a falha é sistêmica fora da LSA.

## Plano de correção

Cinco fases, cada uma fechada por um portão: suíte verde, parecer do auditor adversarial sem bloqueador (AGENTS.md) e repetição das 34 consultas deste comparativo sobre snapshot reinstalado. Nenhuma correção usa modelo de linguagem no caminho de execução; toda mudança de regra ganha registro em `docs/decisoes/`. Papéis sugeridos: Claude ou Codex como desenvolvedor, o outro como auditor adversarial, e um pesquisador de fontes que monta o conjunto-ouro sem ler o código.

### Fase 0: contenção (imediata)

- [x] Suspender o uso do FREOA como verificador em qualquer uso real até a conclusão dos ajustes, e manter o JusRatio como ferramenta de pesquisa e verificação (decidido em 18/10/2026).
- [ ] Reinstalar o snapshot de 18/10 no home padrão do notebook e conferir com `fv snapshot info` (814 obras, 34.241 decisões).
- [ ] `fv doctor` e o servidor MCP passam a alertar quando o acervo tem menos obras que o snapshot publicado.
- [ ] Nota pública de limitação no README e na release v1.0.2: CF/ADCT e revogação de atos infralegais.

### Fase 1: bloqueadores (v1.0.3 e novo snapshot)

1. **B1 ADCT.** Em `html_devices.py:905`, abrir o escopo `adct/` no cabeçalho do ADCT, só depois do primeiro dispositivo (o link do sumário não pode abrir escopo; testado: abrir no sumário joga a CF inteira no ADCT). Subir `parser_version`, reprocessar com `reprocessar_capturas`, aceitar "art. 5º do ADCT" no extrator. No protótipo, os caminhos ambíguos da CF caíram de 971 para 8.
   - Testes: `test_cf_adct_escopo_separado`, `test_cf_sumario_adct_nao_abre_escopo`, `test_verifica_cf_art60_trecho_adct_nao_verified`.
2. **B2 revogação.** Issue de documento `OBRA_REVOGADA_NA_FONTE` com o texto oficial ("REVOGADA pela Resolução 44/21"); capturar sempre a página do ato CVM como evidência própria; em `verify.py`, temporal `divergent REVOGADO` para a data atual e `unknown` para datas passadas sem data de revogação, também no ramo sem dispositivo. Falha ao obter a situação vira `unknown SITUACAO_INDISPONIVEL`, nunca vigente. Ressincronizar os atos CVM, BCB e CMN.
   - Testes: `test_bcb_revogado_bloqueia_vigente`, `test_cvm_pagina_revogada_marca_obra`, `test_cvm_situacao_indisponivel_nao_vigente`.
3. **B3 associação privada.** Aplicar em `verificar_citacao` o mesmo bloqueio de confiança de `verifica-texto`: extração provável com outro referente preferido nunca chega a verified.
   - Teste: `test_verifica_bloqueia_pertenca_privada`.

Portão: zero verified indevido nos casos de B1 a B3 e nos 8 corpora adversariais existentes.

### Fase 2: omissões silenciosas e falsas negativas

- [ ] A1: documento sem estrutura (PDF da CVM) responde `unknown DOCUMENTO_SEM_ESTRUTURA`, nunca inexistente; extrair artigos do DOCX consolidado quando houver.
- [ ] A2: ausência local vira indisponibilidade com motivo de cobertura; "inexistente" só com a obra capturada e o caminho ausente nela.
- [ ] A3: data anterior sem histórico devolve texto nulo; marcar `redacao_anterior_ausente_na_fonte` quando a primeira redação for "Redação dada".
- [ ] A4 e A9: decodificar UTF-8, remover o filtro literal, levantar `Unavailable` quando a fonte informa resultados e o parser não lê nenhum, propagar total e `truncado`.
- [ ] A5: listar remissões anafóricas como `referencia_nao_resolvida`, sem herdar obra; expor `support` em cada linha com rótulo legível.
- [ ] A6: lookup por classe e número antes do FTS; ausente = `nao_confirmado_no_acervo` com a cobertura; incidentes do mesmo processo como relacionados; resultados textuais em bloco separado.
- [ ] A7: candidatos ao vivo em staging, fora do FTS do acervo, até confirmação.
- [ ] A8: informar truncamento acima de 200 citações.

### Fase 3: busca e normas

- [ ] M2 a M4: espécie extraída junto do número na CVM; deduplicação por ato; lookup nominal no BCB via `parse_one`.
- [ ] M5 e M6: MATCH restrito a ementa e inteiro teor, bm25 com pesos, ordenação por cobertura de termos com corte mínimo de dois terços e `pertinencia` exposta; completar o AND escasso com o OR ordenado (revisar a decisão 0010).
- [ ] M7, M9, M10: fontes não consultadas como `nao_consultada`; respeitar `busca_textual: False`; resolução canônica de "caput"; filtro de fonte antes do limite.
- [ ] Tesauro jurídico versionado (`tesauro-1`), determinístico, para pares como tag along e art. 254-A, recesso e retirada, apuração de haveres e dissolução parcial.

### Fase 4: cobertura e dados

- [ ] Ampliar o STJ para precedentes de mérito anteriores a junho de 2024 por seleção curada (societário e mercado de capitais primeiro), súmulas do STJ e do STF e temas com tese.
- [ ] M8: usar a epígrafe do ato alterador já capturado quando o Senado não der a data.
- [ ] M11: indexar rubricas como coluna própria, corrigir rótulos CVM corrompidos.
- [ ] Normas CVM vigentes de maior uso (Res. 44, 80, 81, 160, 175, 215) com artigos estruturados.

### Fase 5: medição contínua

- [ ] Conjunto-ouro independente com os 34 casos deste comparativo, mais casos de revogação, ADCT e anáfora, montado sem leitura do código.
- [ ] Critério de release: zero verified indevido e zero vigente indevido; recall e ranking medidos e publicados, sem portão.

## Questões abertas

- O efeito da correção do ADCT sobre os outros cerca de 140 atos compilados não foi medido; outras leis podem ter disposições transitórias com o mesmo padrão.
- Não se sabe se o Planalto, ao vivo, mostra hoje as redações riscadas do art. 136 da LSA; a captura do snapshot não as tem.
- O motivo da falha do Senado na data dos alteradores não é auditável: o estado de sincronização fica fora do snapshot.
- Para atos CVM com DOCX, só 45 foram conferidos contra a página oficial; pode haver outros revogados além das Res. 51 e 124.
- Cursor e Antigravity não deram segunda leitura; vale rodá-los na fase 1 como auditores adversariais quando os limites renovarem.
- A decisão de vetar embeddings locais (regra 7) merece revisão explícita só se o ranking determinístico da fase 3 não bastar; o plano não depende dela.
