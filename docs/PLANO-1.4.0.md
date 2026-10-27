# Plano 1.4: de verificador a substituto do Jusratio

Estado: v2, aprovado pelo titular em 26/10/2026 (seção 9), sobre a proposta aceita por unanimidade no debate governado (Codex e Antigravity, rodada 4, 26/10/2026, `ACEITO_UNANIMIDADE`, sem dissenso). Cursor fora do debate (`SANDBOX_INDISPONIVEL_WINDOWS`).
Autorização: Ricardo Peres Freoa mantém a autorização da 1.3.0 para commit, merge, publicação, distribuição e instalação sem gate manual. Isso não dispensa o parecer do auditor sem bloqueador.
Base: `main` em `68e743a` (v1.3.0).
Registro do debate: fora do repositório, no computador do titular (`Claude_Externos/freoa-verifica/debate-20261027-arquitetura-1.4/ledger.md`).
Fato que muda o objetivo: o titular deixará de usar o Jusratio. A ferramenta passa de verificador complementar a fonte primária de pesquisa, inclusive temática, em todos os TJs e nos superiores.

## 1. Avaliação crítica do estágio atual

A ferramenta é rigorosa no que verifica e insuficiente no que cobre. As duas coisas são verdade ao mesmo tempo, e a segunda decide o objetivo novo.

O que continua válido e define o produto: proveniência por hash, abstenção declarada, zero confirmação indevida na bateria existente, cobertura declarada por consulta (bloco `cobertura`), indisponibilidade classificada por prova (decisão 0045), snapshot com attestation e instalação por digest.

O que impede a substituição:

| Problema | Fato verificado | Consequência |
|---|---|---|
| Cobertura de TJs praticamente nula | TJDFT com 112 decisões de semente; TJSP só por número; nenhum outro TJ | O uso principal do Jusratio (pesquisa temática estadual) não é atendido |
| Superiores sem inteiro teor | STJ 32.668 espelhos (ementa) de 4 órgãos; STF só súmulas; TST ausente | Resposta temática sem o voto, que é onde está a razão de decidir |
| Legislação congelada | Planalto recusa o UA identificado (decisão 0048) | Acervo de normas envelhece desde a 1.3.0 |
| Busca só lexical | FTS5, bm25 e tesauro determinístico | Precisão temática abaixo do necessário na bateria existente (resultado nos artefatos de bench) |
| Bateria atual favorável ao acervo | 42 casos do próprio projeto, 35 dentro do acervo | Mede o que já existe, não a pesquisa ampla; não autoriza desligar nada |
| Distribuição incompleta | PyPI nunca publicada; bench e testes ao vivo completos não executados na 1.3.0 | "Concluído" ainda não foi alcançado nem no ciclo anterior |
| Custo de auditoria desproporcional | 17 rodadas na 1.3.0, concentradas em gramática HTTP, charset e Content-Encoding (decisões 0059 a 0066) | O esforço foi para endurecer o transporte, não para ampliar a cobertura; correto para segurança, errado como alocação diante do objetivo novo |
| Funções do Jusratio sem equivalente | informativos, timeline, overruling por tema, ramos do direito, chunks, pedidos de autos | Paridade funcional inexistente |

Diagnóstico em uma frase: o projeto otimizou a verificabilidade do pouco que tem. A 1.4 precisa inverter a alocação, ampliando a cobertura sem abrir mão da proveniência.

## 2. Lições externas

| Fonte | Lição | Como entra |
|---|---|---|
| [juscraper](https://github.com/bdcdo/juscraper) (MIT) | `cjsg` para 17 TJs (TJSP, TJES, TJTO, TJBA, TJCE, TJDFT, TJMT, TJPA, TJPB, TJPE, TJPI, TJPR, TJRN, TJRO, TJRR, TJRS, TJSC); padrão download→parse; aviso antes de paginação ampla; TJAP com Turnstile declarado como erro, sem contorno | Contrato técnico de referência dos conectores estaduais; reimplementação pelo `transport`, com fixtures próprias |
| DJEN / Comunica PJe (CNJ) | API pública sem autenticação, filtros por tribunal, processo, OAB e data; texto da comunicação no item; sem busca textual; 403 fora do Brasil; cerca de 50 itens por página ([descrição de integradores](https://chatjuridico.com.br/api-do-djen-consulta-oficial-cnj/)) | Recência e descoberta, tipado `texto_publicado` (decisão 0047); nunca rotulado como inteiro teor |
| DataJud | Metadados e movimentos, sem texto; citação obrigatória do CNJ e do DataJud ([Portaria 374/2026](https://atos.cnj.jus.br/atos/detalhar/6972)) | Timeline processual; atribuição de fonte nas respostas |
| BNP/Pangea | Plataforma unificada de precedentes qualificados de todos os tribunais ([CNJ](https://www.cnj.jus.br/cnj-relanca-o-banco-nacional-de-precedentes-bnp/)) | Precedentes A e B, overruling por tema |
| [brlaw_mcp_server](https://github.com/pdmtt/brlaw_mcp_server) e [MCP-Jusbrasil](https://glama.ai/mcp/servers/fxbarros/mcp-jusbrasil/tree) | STF, STJ e TST por navegador automatizado; Jusbrasil atravessando Cloudflare com fetcher furtivo | Lição negativa: é o caminho que o projeto recusa (regra 3) |
| [RepoJus](https://huggingface.co/datasets/andrebadini/repojus) | 3,1 milhões de julgados de inteiro teor de 9 tribunais, com nota de LGPD | Só descoberta de candidatos, sempre recapturados na fonte oficial; nunca no snapshot |

## 3. Decisões de arquitetura (aceitas no debate)

**D1. Cobertura em três camadas.**
(a) Índice local canônico com inteiro teor e hash: STJ íntegras de todos os órgãos (meta de 5 anos, viabilidade em aberto), STF acórdãos e súmulas, TST, BNP integral, informativos de STF, STJ e TST, e o lote 1 de TJs (TJSP, TJRJ, TJMG, TJRS, TJPR, TJDFT) em janela móvel de 24 meses de acórdãos colegiados.
(b) Federação ao vivo em write-through: os 17 TJs do juscraper, TJRJ e TJMG; TJAC, TJAL, TJAM e TJMS reaproveitando o conector e-SAJ só depois de compatibilidade demonstrada por fixtures e testes por portal (premissa a validar); TJGO, TJMA e TJSE com conectores próprios; inteiro teor sob demanda em `obter_decisao`, persistido com hash; prazo por fonte e degradação parcial.
(c) Metadados e recência: DataJud e DJEN.
`search.federated` declara, por fonte, quais campos o portal pesquisa (ementa, metadados, inteiro teor). Persistir o que foi achado não torna pesquisável o que não foi.
Inteiro teor segmentado por regra em `ementa`, `relatorio`, `voto_vencedor`, `voto_vencido` e `dispositivo`, com hash por segmento; estrutura não identificável fica `nao_identificado`, nunca atribuída por inferência.
Cobertura por tribunal × coleção × órgão × período × modalidade documental; sem denominador confiável, `desconhecida`.

**D2. Busca híbrida condicionada.** `search.lexical` (FTS5, obrigatório e fallback), `search.dense` (embeddings locais em ONNX/CPU, pesos fixados por SHA-256, sqlite-vec), fusão RRF, reranker local opcional, pesos públicos para `autoridade-1` e recência. Desligada por padrão; habilita só com ganho de 5 pontos em recall@20 sobre lexical com tesauro, no mesmo corpus, documentos deduplicados, sem regressão de mais de 2 pontos em nenhum estrato. Recibo com modelo, tokenizer, segmentação, runtime, precisão numérica e desempate estável; promessa de estabilidade dentro de tolerância publicada; verificação continua exatamente determinística. A regra invariável 7 do `AGENTS.md` é reescrita por decisão formal: nenhum modelo generativo em caminho algum; modelos de ranqueamento só na descoberta, nunca em `verificar_citacao`, `verificar_texto`, `obter_dispositivo` ou `obter_evidencia`.

**D3. Barreiras.** Sem OCR de CAPTCHA, sem navegador furtivo, sem leitura do armazenamento de cookies do navegador pessoal. Sessão assistida (`fv sessao <fonte>` e retorno MCP `requer_sessao_assistida`): contexto de navegador dedicado e isolado, o humano resolve a barreira, a ferramenta captura os bytes com proveniência `sessao_assistida`, segredos fora de logs, evidências e snapshot, sem repetição automática, sem contar como cobertura automática; a limitação aparece na matriz e no retorno. Planalto: Senado/LexML, Câmara e INLABS/DOU como candidatos sujeitos a teste de equivalência por capacidade (texto, anexos, redações, remissões, vigência) contra o acervo Planalto já capturado; tipagem `texto_publicado`, `texto_consolidado`, `vigencia`; pedido formal de liberação do UA à Presidência.

**D4. Gate de substituição em duas portas.**
- Porta A, por tribunal: o Jusratio deixa de ser usado para o tribunal aprovado. Ordem: STF, STJ, TST, TJSP, TJRJ, TJMG, TJRS, TJPR, TJDFT (270 consultas).
- Porta B, rótulo: "substituição no escopo aprovado" (todos os tribunais exceto os nominalmente em `bloqueio_externo_documentado`, hoje o TJAP, e exceto funções excluídas por decisão expressa do titular) ou "substituição completa" (matriz e paridade integrais). Exceções expostas em `listar_fontes`, no bloco `cobertura` e no manifesto, com data de revisão.
- Conjunto: 30 consultas por tribunal como piso (900 ao final), nascidas de problemas jurídicos e de fontes externas ao acervo (informativos, Jurisprudência em Teses, súmulas e enunciados, temas), mais adversariais e testes por ferramenta de paridade; pooling de sistemas e avaliação humana; tarefas reais às cegas com dado de cliente substituído por hipótese pública; deduplicação por processo e família documental; reserva congelada por hash.
- Pisos fixados antes da reserva: confirmação indevida 0 (bateria declarada); recall@20 ≥ 0,90 e precisão@10 ≥ 0,80 em todos os tribunais, medidos sobre a resposta entregue dentro do prazo da tool, com parciais, vazios e `timeout_fonte_externa` no denominador; inteiro teor em ≥ 95% dos relevantes, em três denominadores (público humano, automático, assistido); p95 ≤ 5 s local e ≤ 20 s federado; atualização p95 ≤ 72 h nas coleções contínuas. Replay e avaliação sem prazo são só diagnóstico.
- Paridade: `informativo_juridico`, `timeline_decisoes`, `listar_overruling_por_tema`, `listar_tribunais`, `listar_ramos_direito`, chunks em `obter_decisao`. Pedidos de autos fora do escopo (seção 9, item 4).

**D5. Entrega e auditoria.** `transport` congelado (mudança só com auditoria própria); nenhum PR vai ao auditor sem suíte, Ruff e testes de contrato MCP verdes; bloqueiam merge os achados altos ou críticos e toda violação demonstrada de critério obrigatório fixado antes da implementação; teto de 3 rodadas por incremento mais passe final independente; após o teto sem resolução, reduz-se escopo ou adia-se, com registro no manifesto e no rótulo; o teto nunca equivale a aprovação. Decisão formal só para mudança de contrato público ou de regra.

**D6. Reserva protegida.** Durante ajustes, quem guarda a reserva comunica ao supervisor só aprovado ou reprovado por tribunal e métrica; diagnósticos vêm do conjunto de desenvolvimento; parcela da reserva que orientar qualquer ajuste é substituída antes do novo aceite. O relatório integral da reserva vai ao titular.

## 4. Ponto do supervisor não submetido ao debate: volume

O debate fixou 24 meses de acórdãos do lote 1 no índice local sem dimensionar. Estimativa a confirmar na sonda S0: só o TJSP produz, no 2º grau, da ordem de centenas de milhares a mais de um milhão de decisões por ano; 24 meses de seis TJs podem passar de dezenas de GB de texto, além do índice vetorial. O snapshot atual tem 666 MB. Consequência proposta: snapshot modular (núcleo + pacote por tribunal, cada um com digest próprio na lista embutida), recorte inicial por órgão no lote 1 (câmaras de direito privado e empresarial primeiro, demais por federação) e embeddings só sobre o recorte indexado. A sonda S0 mede volume, tamanho e tempo de indexação no notebook antes de I3; se o volume inviabilizar o recorte, a Porta A desses TJs se faz pela camada (b).

## 5. Critério de conclusão (vale para cada incremento)

Um incremento só está concluído com todas as etapas abaixo cumpridas e registradas em `release/acceptance_manifest.json`:

1. Desenvolvimento por especificação escrita, em ramo atribuído.
2. Teste: suíte offline verde na matriz (Linux e Windows, 3.11 a 3.14), Ruff, contrato MCP, testes live do escopo com indisponibilidade classificada por prova.
3. Commit com mensagem convencional do projeto.
4. Incorporação: parecer do auditor sem bloqueador sobre HEAD identificado; merge na `main` pelo supervisor.
5. Publicação: tag, release com attestation, `pypi.yml` publicando os mesmos bytes por Trusted Publishing (pré-release `1.4.0aN` nos incrementos intermediários).
6. Distribuição: snapshot (ou pacote modular) exportado, bateria S4, digest na lista embutida, anexado à release.
7. Instalação: instalador oficial no notebook Windows, attestation verificada, `instalacao.json` com `concluida: true` e commit esperado.
8. Execução: `fv doctor` ok (alertas só de indisponibilidade classificada) e bateria ao vivo do escopo executada no notebook, com relatório de saúde das fontes.

## 6. Incrementos

### I1 (1.4.0a1): pipeline e STJ íntegras

| ID | Item |
|---|---|
| I1.1 | Trusted Publisher em pypi.org e `PYPI_PUBLICAR=true` (ação do titular na conta PyPI) |
| I1.2 | PR #5 (decisão 0044): fechar I2, I3 e M1; íntegras do STJ de todos os órgãos, segmentação tipada (D1) |
| I1.3 | Ressalvas da auditoria do delta: `noqa` por linha em `stj.py` e `derivados.py`; helper `_so_desta_thread` único |
| I1.4 | Bench e bateria ao vivo completos, pela primeira vez |
| I1.5 | `release/acceptance_manifest.json` e seu gerador |
| I1.6 | Decisão 0067: reescrita da regra 7 (D2) e da regra 3 com a sessão assistida (D3) |
| S0 | Sondas de volume (seção 4), TST, STF acórdãos, BNP, DJEN e e-SAJ dos quatro TJs, só pelo instrumento `capturar_fixture.py --sonda` |

### I2 (1.4.0a2): superiores e paridade

| ID | Item |
|---|---|
| I2.1 | Tabela de requisitos por ferramenta de paridade, fixada antes da implementação |
| I2.2 | Conectores TST e STF acórdãos (STF com indisponibilidade classificada sob WAF) |
| I2.3 | BNP/Pangea integral e informativos de STF, STJ e TST |
| I2.4 | Tools `informativo_juridico`, `timeline_decisoes` (DataJud), `listar_overruling_por_tema`, `listar_tribunais`, `listar_ramos_direito`, chunks em `obter_decisao` |
| I2.5 | Conjunto de desenvolvimento e reserva da Porta A congelados por hash (Luna), revisão de método (terra) |

### I3 (1.4.0a3): tribunais estaduais, DJEN, sessão assistida, Planalto

| ID | Item |
|---|---|
| I3.1 | Federação dos 19 TJs (17 do juscraper, TJRJ, TJMG) com `search.federated`, campos declarados, prazo por fonte e degradação parcial |
| I3.2 | Índice local do lote 1 no recorte que a S0 admitir; snapshot modular |
| I3.3 | TJAC, TJAL, TJAM, TJMS (e-SAJ, condicionado) e TJGO, TJMA, TJSE (próprios); TJAP como `bloqueio_externo_documentado` |
| I3.4 | DJEN tipado `texto_publicado`, ingestão incremental dos tribunais do escopo |
| I3.5 | Sessão assistida (`fv sessao`, `requer_sessao_assistida`) |
| I3.6 | Cascata Planalto com teste de equivalência por capacidade; pedido formal à Presidência |
| I3.7 | Matriz de aceite dos 30 tribunais em `listar_fontes` |

### I4 (1.4.0): busca híbrida, avaliação reservada e Porta A

| ID | Item |
|---|---|
| I4.1 | `search.dense`, RRF, reranker e recibo (D2), atrás de chave desligada |
| I4.2 | Experimento lexical × lexical+tesauro × híbrida × híbrida+reranker no mesmo corpus; habilitação só pelo gate |
| I4.3 | Avaliação reservada da Porta A; aprovado ou reprovado por tribunal e métrica ao supervisor; relatório integral ao titular |
| I4.4 | Desligamento do Jusratio nos tribunais aprovados, por decisão do titular |

Depois da 1.4.0: 1.5.0 com os TJs restantes até a Porta B, TRFs e TNU pelo CJF, e o rótulo correspondente.

## 7. Delegação

| Agente | Papel | Permissões | Revisor | Transporte |
|---|---|---|---|---|
| Supervisor (Opus, esta sessão) | Especificação, integração, decisões, merge, tag e release sob autorização do titular | Escrita; merge e tag | Codex revisa os deltas de integração, CI e publicação | sessão |
| Codex (modelo padrão da instalação) | Auditor de todo código de produção e dos deltas do supervisor; não escreve o que audita | Somente leitura | Supervisor arbitra falso positivo | `codex exec -s read-only` via Desktop Commander, sem `-m` |
| Antigravity | Implementa `search` (lexical, dense, ranker) e o experimento I4.2 | Escrita em worktree e ramo `feat/search-*` | Codex | `agy -p` via Desktop Commander |
| Sonnet | Conectores (STJ íntegras, TST, STF, BNP, TJs, DJEN, cascata Planalto) e tools de paridade, um subagente por fonte | Escrita em ramo `feat/<fonte>` | Codex | `claude -p --model sonnet` |
| Haiku | Fixtures pelo instrumento oficial, tesauro, documentação, CHANGELOG, manifesto de fixtures | Escrita em `tests/fixtures/`, `docs/` | Sonnet | `claude -p --model haiku` |
| Cursor | Engenharia de release no host Windows: instalador, instalação limpa, `fv doctor`, bateria ao vivo com IP brasileiro e limitação de taxa | Execução local; escrita em scripts de empacotamento; sem tag nem publicação próprias | Supervisor; Codex confere hashes | `cursor-agent -p` em modo agente com allowlist via Desktop Commander |
| GPT Luna (`gpt-6-luna`) | Conjunto-ouro reservado e adjudicação preliminar | Sem acesso ao código; reserva guardada fora do repositório até o aceite | Terra (método); titular (relevância controversa) | `codex exec -s read-only -m gpt-6-luna` via Desktop Commander |
| GPT Terra (`gpt-6.1-terra`) | Red team das saídas MCP e da sessão assistida; casos adversariais; revisão do método de Luna e das fronteiras de confiança da distribuição | Somente leitura; casos entregues ao supervisor para `tests/adversarial/` | Codex | `codex exec -s read-only -m gpt-6.1-terra` via Desktop Commander |

Regras: ninguém revisa o próprio trabalho; no máximo uma trilha por vez em `service.py`, `transport.py` ou contrato; push só em ramos atribuídos; nenhum agente recebe credencial de publicação ou cookie pessoal; registro por tarefa em `docs/auditoria/1.4.0/` (ferramenta, modelo efetivo, versão, commit, comando, saída, código terminal, limitações).

## 8. Ordem

1. I1.1 (titular) ‖ I1.2 (Sonnet) ‖ I1.3 e I1.5 (Haiku) ‖ S0 (Haiku, pelo instrumento) ‖ I1.6 (supervisor).
2. Auditoria Codex de I1; Cursor instala e executa; I1 fecha pelo critério da seção 5.
3. I2.1 (supervisor) → I2.2 a I2.4 (Sonnet, um por fonte) ‖ I2.5 (Luna, Terra).
4. I3.1 a I3.7 (Sonnet por tribunal; Antigravity adapta `search.federated`); S0 decide o recorte de I3.2.
5. I4 (Antigravity) → I4.3 (Luna) → I4.4 (titular).

## 9. Decisões do titular (26/10/2026)

1. Barreiras: sessão assistida (D3). O modo com OCR de CAPTCHA, navegador que imita usuário e cookies do navegador pessoal está fora; a regra invariável 3 permanece, com a redação da decisão 0067.
2. Lua e terra são outros modelos GPT acionados pelo Codex CLI: Luna (`gpt-6-luna`) e Terra (`gpt-6.1-terra`). O Codex auditor mantém o modelo padrão.
3. Comparação com o Jusratio autorizada, só com consultas públicas e só nos testes e no bench (`tests/` e artefatos de bench); não entra no README, no `FONTES.md` nem em material de divulgação.
4. Pedidos de autos: decisão técnica delegada ao supervisor. Ficam fora do escopo. Razões: dependem de acesso processual autenticado (credencial de advogado ou certificado) e de documentos não publicados, o que colide com a premissa de fontes públicas sem credencial e criaria a maior superfície de risco do sistema (credencial no caminho MCP); o uso que justificava a função (andamento, decisões e publicações de um processo) é atendido por DataJud, DJEN e `obter_decisao`. Com a redução expressa, "substituição completa" passa a significar matriz e paridade integrais sem pedidos de autos.
5. Mantida a autorização da 1.3.0 para commit, merge, publicação, distribuição e instalação sem gate manual.
6. Adjudicação de relevância controversa: o titular.
