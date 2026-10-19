## Concordo

A direção é correta: importar disciplina de captura, contratos e monitoramento do juscraper, preservando as regras do FREOA. Concordo com as exclusões de CAPTCHA/WAF, cookies de navegador e falsificação de `Origin`/`Referer`.

Conferi `release/1.3.0` e `main` em `239bef681ddd7899dc5d213a85a0a558fabf586e`; juscraper em `9d7773149f1011c50c137b45761c2e467d7e2e9f`. Plano e comparativo estão **não rastreados**. Nenhum arquivo foi alterado.

A verificação mecânica encontrou **38 arquivos registrados, todos presentes e com hashes corretos**, e **19 arquivos não registrados**. Suítes, sondas, builds, corpus de `fv-build-1.2.1` e instalação: **NOT RUN**.

## Divirjo (com proposta)

1. **F4 parte de uma premissa não demonstrada:** o endpoint TCU consumido devolve uma lista, sem total; contar recursos CKAN não conta decisões. Retirar a promessa de coleta integral desta versão.
2. **F2 é uma alteração transversal do modelo de evidência**, não apenas um conector. Manter a pesquisa nesta versão e adiar a implementação.
3. **F3 descreve implementação que já existe.** Reescrever como qualificação/correção da busca TJSP existente.
4. **P3 e S4 devem subir para P1:** contrato público e validação do snapshot precisam preceder suas alterações e distribuição.
5. **S2 não pode confiar nos motivos atuais:** qualquer 403 já vira desafio, inclusive uma regressão de autorização ou requisição.
6. **O fluxo de release é contraditório:** a etapa 7 exige digest antes da tag, mas aparece depois dela. Corrigir o plano e `RELEASE.md` conjuntamente.

## Lacunas

**Papéis e ferramentas.** A separação proposta é adequada, com estas condições:

- Opus integra e decide arquitetura; Codex critica e audita sem editar. A auditoria arquitetural atual não substitui auditoria da implementação nem dos artefatos finais.
- Sonnet está concentrando mudanças demais em arquivos compartilhados. Worktrees isolam arquivos, mas não eliminam conflitos semânticos; limitar trilhas simultâneas sobre `service.py`, transporte e contratos.
- E1 exige decisão sobre proveniência, dados sintéticos e manifesto; Haiku pode executar o registro após essa decisão, não defini-la.
- Cursor pode implementar workflows, mas credenciais e publicação devem permanecer fora dos testes e da revisão de PR.
- Antigravity precisa receber um **instrumento público de sonda que use o transport**. Usar navegador, `requests` ou HTTP próprio para facilitar a pesquisa contrariaria a regra 4. Conjuntos-ouro devem permanecer independentes do código e das expectativas do desenvolvedor.
- Registrar ferramenta, modelo efetivo, versão, commit, comando, saída, código terminal e limitações. Disponibilidade e funcionamento dos comandos propostos não foram verificados nesta auditoria.

**Ordem.** Proponho: especificações e baseline P3 → E1/E2 e contratos E3 → classificação S2 → S1/S3 → política T2 e sondas → F1/F3 condicionais → P1/P2 → S4/D1 → auditoria final. G1 acompanha a execução. T1 pode ficar para depois; não deve alterar silenciosamente as condições das sondas.

A ordem atual omite expressamente E2, E3, S2, S4, F4, G2 e G3. Também há tensão entre começar S1 antes das sondas e deixar sua classificação ambiental para depois.

**Commit, merge e auditoria.** Aceito commits e merges locais na branch de integração como preparação reversível. Contudo, “marco aprovado” exige parecer sobre **HEAD e árvore identificados**, após integração. Correções posteriores invalidam o parecer na extensão afetada. O PR deve incluir plano, decisões e evidências rastreáveis; referências a documentos não rastreados não bastam.

**Snapshot e release.** Exijo esta sequência:

1. Congelar código funcional, versão e corpus candidato; registrar suas identidades.
2. Exportar, conferir e instalar o snapshot em home vazio; executar S4, integridade e bench.
3. Congelar os bytes exportados e registrar seu digest em **`freoa_verifica/data/snapshots-oficiais.json`**.
4. Auditar o commit final e o wheel instalado, incluindo manifesto e instalador.
5. Após autorização de publicação, merge/tag → CI do commit da tag → build/attestation → publicação dos mesmos bytes.
6. Anexar exatamente o snapshot auditado; conferir digest baixado.
7. Instalar e exigir **digest esperado**, vínculo, derivados atuais e attestation verificada.

O vínculo embutido é exigido por [snapshot.py:676](C:/dev/freoa-verifica-v2/freoa_verifica/snapshot.py:676). Já [RELEASE.md:12](C:/dev/freoa-verifica-v2/docs/RELEASE.md:12) manda gerar corpus depois da tag: precisa ser atualizado. A attestation do wheel autentica o vínculo ao digest; não atesta que a coleta foi completa ou semanticamente correta.

Há ainda um risco concreto: [snapshot.py:783](C:/dev/freoa-verifica-v2/freoa_verifica/snapshot.py:783) procura releases anteriores quando a última não contém asset elegível. Portanto, `vinculado: true` sozinho pode aceitar um snapshot antigo. O aceite da 1.3.0 precisa comparar o digest específico.

## Especificações exigidas

### E1 — Manifesto de fixtures

**Correto, com ajuste; manter P1.** O carregador valida hashes apenas quando usado, e TJDFT lê arquivos diretamente: [fixture_util.py:17](C:/dev/freoa-verifica-v2/tests/fixture_util.py:17), [test_tjdft.py:19](C:/dev/freoa-verifica-v2/tests/test_tjdft.py:19).

Exigir inventário recursivo bidirecional, hashes, caminhos confinados e origem declarada. O próprio manifesto precisa de tratamento estrutural explícito. Dos 19 arquivos não registrados, cinco são TJDFT e 14 são benchmark/prosa: registrar categorias distintas ou mover os sintéticos. **Não inventar URL/data de captura para preencher campos.** Aceite: arquivo novo, removido ou adulterado reprova; testes TJDFT passam pelo carregador validado.

### E2 — Captura reproduzível

**Viável após pequena extração; manter P2.** O payload TJDFT está embutido em `search`, não há construtor completo importável: [tjdft.py:187](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/tjdft.py:187).

Definir `build_search_payload(...)` e função pública de captura que chegue exclusivamente ao transport. Gravar bytes recebidos sem reserialização, URL, método, parâmetros públicos, instante e SHA-256; atualização consistente de arquivo/manifesto. Testar falha sem entrada publicada e ausência de HTTP alternativo. **AST de importação é complementar:** importar um construtor e não usá-lo passaria no teste proposto.

### E3 — Propagação de filtros

**Necessário, porém incompleto; elevar para P1.** O serviço envia `desde`/`ate`, mas TJDFT os ignora; TJSP espera `dt_inicio`/`dt_fim`; STJ local usa apenas limite: [service.py:2248](C:/dev/freoa-verifica-v2/freoa_verifica/service.py:2248), [tjdft.py:190](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/tjdft.py:190), [tjsp.py:111](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/tjsp.py:111), [stj.py:245](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/stj.py:245).

Especificar matriz **filtro público → filtro remoto/local → limitação declarada**. Nem todo filtro deve virar parâmetro remoto: TCU filtra texto localmente; DataJud pesquisa processos. Incluir TJSP. Testar serviço → conector → requisição/SQL e resultado final, com datas isoladas, combinadas e limites. Não computar a expectativa pelo mesmo construtor testado.

### S1 — Live TJDFT

**Correto; manter P1.** Já existe `health` com captura e tratamento de indisponibilidade: [tjdft.py:162](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/tjdft.py:162).

Exigir positivo conhecido, negativo estrutural e documento com vínculo `uuid` + identificador, hash e parse. Um acórdão sem íntegra deve continuar `parte_indisponivel`. Testar sob a política de UA definitiva; bloqueio produz indisponibilidade registrada, nunca sucesso documental nem zero.

### S2 — Xfail ambiental

**Não aprovo como escrito; fazer antes de S3.** [challenge.py:95](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/challenge.py:95) transforma todo 403 em `desafio_http_403`; corpo vazio também vira desafio.

Exigir categoria estruturada, preservação da causa e evidência do bloqueio, por exemplo `EnvironmentalUnavailable(Unavailable)`. Só teste live explicitamente marcado pode virar xfail, na fase `call`. **403 genérico não prova bloqueio ambiental.** Aceite com `pytester`: CAPTCHA comprovado recebe xfail; 403 de autorização, JSON inválido, assertion, erro de parser e exceção inesperada permanecem vermelhos. Xfail entra no relatório de fontes indisponíveis.

### S3 — Issue viva

**Correto no objetivo; classificação proposta é insuficiente.** O silenciamento existe: [fontes-saude.yml:13](C:/dev/freoa-verifica-v2/.github/workflows/fontes-saude.yml:13) e linha 21.

O código 1 do pytest significa testes falhados, incluindo regressões; **não significa “fonte fora”**. Exigir relatório estruturado por fonte com `ok`, `unavailable`, `regressao`, `not_run`, execução completa e commit. JUnit é saída auxiliar. Testar regressão com exit 1, todos xfail, XML ausente/truncado, cancelamento, falha da API da issue e concorrência. Nenhuma execução incompleta pode limpar a issue. Manter P1, dependente de S2.

### S4 — Bateria do snapshot

**Correto; elevar para P1 como dependência de D1.** O STJ limita por padrão a 12 recursos mensais por pacote; TCU tem limites explícitos de páginas: [stj.py:492](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/stj.py:492), [tcu.py:237](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/tcu.py:237).

Exigir manifesto congelado do recorte: órgãos, datas, recursos, contagens e pendências. Testar duplicatas, fronteiras temporais, páginas faltantes e decisões sem captura correspondente. Contagem local esperada valida o pacote; não prova completude histórica da fonte. Repetir após instalar os bytes exportados.

### T1 — Retry

**Viável com especificação adicional; P3, adiável.** O breaker abre após **cinco** falhas consecutivas, não após um 503: [transport.py:495](C:/dev/freoa-verifica-v2/freoa_verifica/transport.py:495). Não há `RequestPolicy` no FREOA.

Exigir política explícita em `transport.fetch`, teto de tentativas, prazo monotônico único, rate limit por tentativa e POST repetível apenas quando declarado seguro. `Retry-After` não integra os cabeçalhos preservados atualmente: [transport.py:31](C:/dev/freoa-verifica-v2/freoa_verifica/transport.py:31).

**503 pode carregar desafio:** status sozinho não autoriza repetição. Hoje o transporte rejeita não-200 antes dessa inspeção: [transport.py:677](C:/dev/freoa-verifica-v2/freoa_verifica/transport.py:677). Aceite: desafio, 403 e 429 sem retry; espera maior que orçamento encerra indisponível; temporários são descartados; uma falha lógica conta uma vez no breaker, tentativas permanecem observáveis.

### T2 — User-Agent

**Concordo com identificado por padrão; rejeito exceção decidida apenas por sucesso da sonda.** Existem três defaults e declarações explícitas a harmonizar: [transport.py:38](C:/dev/freoa-verifica-v2/freoa_verifica/transport.py:38), [base.py:98](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/base.py:98), [httputil.py:37](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/httputil.py:37).

Exigir versão derivada de fonte única e sondas documentais por endpoint, sem fallback automático. **Trocar para navegador para superar recusa ao agente identificado pode constituir contorno proibido.** Exceção exige justificativa compatível com a regra 3, não apenas “funcionou”. Manter na versão com qualificação anterior à mudança; quebra deve aparecer como indisponibilidade.

### F1 — Íntegras TJDFT

**Boa sonda P1; implementação condicionada à prova.** O parser já aceita íntegra validada independentemente da espécie: [tjdft.py:118](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/tjdft.py:118), [tjdft.py:270](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/tjdft.py:270). Juscraper fixa `retornaInteiroTeor=False`: [download.py:34](C:/dev/juscraper/src/juscraper/courts/tjdft/download.py:34); não comprova o resultado de `true`.

Distinguir `inteiroTeor` de pesquisa do campo textual de resposta. Capturar consultas controladas, bases e parâmetros separadamente. Aceite com acórdão íntegro, fragmento, placeholder, processo divergente e registro duplicado. Atualizar a 0041: [0041:21](C:/dev/freoa-verifica-v2/docs/decisoes/0041-tjdft.md:21) descreve critério mais fraco que o código atual, que também exige dispositivo e fecho.

### F2 — Comunica CNJ

**Sonda P2 sim; conector nesta versão, não.** O esquema só admite quatro partes, o serviço converte documento não integral em ementa e o MCP limita os mesmos nomes: [0001_inicial.sql:158](C:/dev/freoa-verifica-v2/freoa_verifica/store/migrations/0001_inicial.sql:158), [service.py:2424](C:/dev/freoa-verifica-v2/freoa_verifica/service.py:2424), [mcp_server.py:54](C:/dev/freoa-verifica-v2/freoa_verifica/mcp_server.py:54).

`texto_publicado` precisa ser **tipo documental**, com nível de prova e identidade de publicação próprios; não mero status. Exigir migração, captura ancorada por item, distinção publicação/julgamento, API de obtenção e compatibilidade de snapshot. O `hash` remoto não substitui SHA-256 local. Não copiar os `Origin`/`Referer` do juscraper: [download.py:21](C:/dev/juscraper/src/juscraper/aggregators/comunica_cnj/download.py:21).

### F3 — TJSP

**Reescrever; manter qualificação P1.** Busca `cjsg`, sessão efêmera e paginação já existem: [tjsp.py:96](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/tjsp.py:96). Há também três testes live.

Definir previamente N, intervalo, ambiente, consultas e critério de interrupção. Parar diante de desafio, sem trocar UA/IP ou procurar rota alternativa. Zero desafios observados prova apenas as condições da amostra. Implementação significa correção do conector existente, acompanhada de regressão de payload, sessão, paginação, zero estrutural e documento. Evitar um segundo conector concorrente.

### F4 — Coleta integral

**Inviável como escrito; adiar implementação.** TCU valida payload como lista, sem total: [tcu.py:253](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/tcu.py:253). STJ enumera recursos mensais selecionados: [stj.py:479](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/stj.py:479).

Exigir adaptadores com capacidades comprovadas: total exato, ordenação estável, identidade, paginação e fronteiras. No STJ, declarar completude dos **recursos selecionados**, distinguindo-a de decisões e cobertura histórica. Totais iguais antes/depois não detectam substituição de registros: testar mudança de IDs mantendo contagem. Sem snapshot/versão estável da fonte, declarar o limite de consistência, sem promessa de integralidade.

### P1 — Cobertura da pesquisa

**Prioridade P1 correta; especificação insuficiente.** O serviço descarta `CandidateList.total` e calcula truncamento só pelos itens locais: [service.py:2266](C:/dev/freoa-verifica-v2/freoa_verifica/service.py:2266), [service.py:2291](C:/dev/freoa-verifica-v2/freoa_verifica/service.py:2291). Além disso, [base.py:43](C:/dev/freoa-verifica-v2/freoa_verifica/connectors/base.py:43) confunde total desconhecido com tamanho lido.

Exigir por tribunal: capacidade, consulta efetivamente executada, motivo de não consulta, recorte e instante da captura, total remoto nullable/exatidão, lidos, indexados e truncamento remoto/local separados. `nao_coberto` não descreve fonte suportada que foi pulada por limite. Cobrir busca textual, CNJ, número, offline, falha e tribunal desconhecido. Total desconhecido nunca vira zero.

### P2 — Instruções MCP

**Concordo; manter P1 após P1/P3.** As instruções atuais já distinguem candidatos e verificação: [mcp_server.py:32](C:/dev/freoa-verifica-v2/freoa_verifica/mcp_server.py:32).

Exigir `listar_fontes` → pesquisar → obter parte disponível → verificar antes de citar, com recorte e abstenção explícitos. “Ponto de partida” não pode prometer cobertura geral. Testar instruções efetivamente expostas pelo servidor e descrições das ferramentas, preservando delimitadores de conteúdo. Texto instrucional não prova cumprimento pelo cliente MCP.

### P3 — Contrato JSON

**Elevar de P3 para P1 e executar primeiro.** Já há formatos distintos entre busca textual e caminhos por identificador: [service.py:2023](C:/dev/freoa-verifica-v2/freoa_verifica/service.py:2023), [service.py:2112](C:/dev/freoa-verifica-v2/freoa_verifica/service.py:2112).

Congelar respostas da 1.2.0 com proveniência e entradas públicas/sintéticas identificadas; definir campos, estados, nullabilidade e mudanças aditivas. Não perpetuar falsos estados apenas por compatibilidade: corrigir com decisão explícita. Aceite nos três adaptadores, normalizando somente valores voláteis documentados.

### G1 — CI

**Concordo parcialmente; manter P2 com recorte.** CI já testa wheel instalado, mas instala dependências abertas: [ci.yml:25](C:/dev/freoa-verifica-v2/.github/workflows/ci.yml:25).

Exigir lock compatível com oito ambientes, incluindo marcadores Windows e dependências de build; `uv pip compile` sozinho não comprova isso. Preservar teste fora do checkout. Separar testes de repositório: atualmente só o instalador é copiado com os testes, portanto novos testes AST/workflow precisam de execução própria ([ci.yml:41](C:/dev/freoa-verifica-v2/.github/workflows/ci.yml:41)). Ruff com baseline preciso é aceitável; Semgrep pode ficar posterior. Meta-teste deve permitir negativos documentados e reprovar mascaramento de gates, sem simples busca textual indiscriminada.

### G2 — Governança

**Reformular; P3.** “Amostras só reais” conflita com testes adversariais e sintéticos, como a construção de respostas em [test_tjdft.py:23](C:/dev/freoa-verifica-v2/tests/test_tjdft.py:23).

Exigir **capturas declaradas reais com proveniência; sintéticos e mutantes explicitamente rotulados**. Compartilhar construtor de payload não torna seu conjunto-ouro independente. “Família só com duas ocorrências” deve ser heurística contra abstração prematura, não veto absoluto. Papéis e comandos desta rodada pertencem ao plano; `AGENTS.md` deve conter regras duráveis.

### G3 — PyPI

**P3 correto; não bloquear a versão por cadastro externo.** Trusted Publishing condicional já existe: [release.yml:93](C:/dev/freoa-verifica-v2/.github/workflows/release.yml:93).

Especificar inspeção de conteúdo e comparação dos hashes publicados com os auditados, além da verificação da attestation e identidade do publicador. Testar wheel/sdist em instalação isolada. Ausência de cadastro deve permanecer pendência explícita; não justificar token duradouro como atalho.

### D1 — Snapshot ampliado

**Manter P1, com aceite próprio; não aprovar absorção automática.** Exportação preserva a versão dos derivados da origem: [snapshot.py:319](C:/dev/freoa-verifica-v2/freoa_verifica/snapshot.py:319). Vínculo de digest não demonstra compatibilidade nem qualidade do corpus.

Exigir identidade do produtor de `fv-build-1.2.1`, recursos e capturas usados, checkpoints, pendências, contagens por órgão/mês, duplicatas, derivados atuais e bench independente. A procedência desse build permanece **não verificada nesta auditoria**. Atualizar o instalador, hoje fixado em 1.2.0 ([instalador:17](C:/dev/freoa-verifica-v2/scripts/instalar-freoa-verifica.ps1:17)); exigir attestation efetivamente verificada, pois sua ausência hoje apenas gera aviso ([instalador:30](C:/dev/freoa-verifica-v2/scripts/instalar-freoa-verifica.ps1:30)).

**VEREDITO: SEM CONSENSO — pontos: F4, implementação F2, classificação S2/S3, contrato P1/P3, exceções de UA e sequência snapshot–digest–tag–instalação.**

