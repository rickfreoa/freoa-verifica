# Plano 1.3.0: saúde das fontes, cobertura declarada e primeira parada de pesquisa

Estado: v3, aprovado (consenso Opus × Codex na r4, 19/10/2026), após as críticas r1 a r3 do Codex (`docs/auditoria/1.3.0/`).
Base: `main` em 239bef6 (v1.2.0). Origem: `docs/auditoria/2026-10-19-comparativo-juscraper.md`.
Exclusão expressa: nada que resolva ou contorne CAPTCHA, WAF, desafio, controle de acesso, leia cookies do navegador, falsifique `Origin`/`Referer` ou troque de User-Agent, IP ou rota para superar uma recusa (regra invariável 3). O "modo opcional" com essas capacidades não entra nesta versão nem em branch dela.
Autorização: Ricardo Peres Freoa autorizou, no pedido que origina este plano, commit, merge, publicação, distribuição e instalação sem gate manual, e delegou ao supervisor as pendências. Isso não dispensa o parecer do auditor sem bloqueador.

## Critério de conclusão

Suíte offline verde na matriz (Linux e Windows, 3.11 a 3.14), parecer do auditor sem bloqueador sobre HEAD e wheel identificados, merge na `main`, tag `v1.3.0`, release com attestation, snapshot auditado anexado com digest idêntico ao embutido em `freoa_verifica/data/snapshots-oficiais.json`, instalação no notebook pelo instalador oficial com attestation efetivamente verificada, digest esperado conferido e `doctor` ok.

## Escopo

| ID | Item | Prioridade |
|---|---|---|
| P3 | Contrato JSON, primeiro. Congelar respostas da 1.2.0 (entradas públicas ou sintéticas identificadas, com proveniência) dos três adaptadores (Python, MCP, REST); `docs/CONTRATO.md` com campos, estados, nulidade, mudanças aditivas e política de deprecação (`stable`, `deprecated` com um ciclo de aviso); teste de compatibilidade normalizando só voláteis documentados. Falsos estados não se perpetuam por compatibilidade: corrigem-se com decisão | P1 |
| E1 | Manifesto de fixtures com inventário recursivo bidirecional: todo arquivo em `tests/fixtures/` registrado, hash conferido, caminho confinado, categoria `captura_real` (URL, data, status, `content_type` quando conhecidos; nunca inventados) ou `sintetica` (gerador e propósito). Arquivo novo, removido ou adulterado reprova. Testes do TJDFT passam pelo carregador validado | P1 |
| E2 | Captura reproduzível: `build_search_payload(...)` público por conector com busca (começa pelo TJDFT); `scripts/capturar_fixture.py` chega só ao `transport`, grava bytes sem reserialização, URL, método, parâmetros públicos, instante e SHA-256, atualiza arquivo e manifesto de forma atômica. Teste de uso efetivo do construtor (não só importação) e de ausência de HTTP alternativo. O mesmo instrumento serve às sondas (`--sonda`, grava fora do repositório) | P1 |
| E3 | Matriz filtro público → filtro remoto/local → limitação declarada, por conector (TJDFT, TJSP, STJ local, TCU, DataJud, CVM). Corrigir o descarte de `desde`/`ate` no TJDFT e o mapeamento do TJSP; onde o filtro não existe, a resposta declara a limitação. Testes serviço → conector → requisição/SQL → resultado, com expectativa escrita à mão | P1 |
| S2 | Classificação ambiental estruturada: `Unavailable` ganha `categoria` (`ambiental_desafio`, `fonte_fora`, `recusa_identificado`, `resposta_inesperada`, `regressao`) e `evidencia` (status, marcador, cabeçalho, sha256 da resposta) preenchida pelo transporte. Classificação só por prova positiva: `ambiental_desafio` exige marcador de desafio identificado (CAPTCHA, página de WAF conhecida, cabeçalho de borda documentado); `fonte_fora` exige 5xx, timeout ou falha de conexão registrados; 403 sem marcador é `recusa_identificado` ou `regressao`, nunca ambiental. Hook converte em xfail apenas teste `live` marcado, na fase `call`, com `ambiental_desafio` ou `fonte_fora` e evidência presente; resto vermelho; testado com `pytester`; decisão 0045 | P1 |
| S1 | `tests/live/test_live_tjdft.py`: positivo conhecido, negativo estrutural, documento com vínculo `uuid` + identificador, hash e parse; acórdão sem íntegra continua `parte_indisponivel` | P1 |
| S3 | Saúde das fontes com issue viva: testes live gravam relatório estruturado por fonte (`ok`, `unavailable` com categoria, `regressao`, `not_run`), com commit e marcador de execução completa; `scripts/saude_fontes.py` atualiza uma issue rotulada (corpo reescrito sem notificar, comentário só quando o conjunto muda, estado anterior em comentário HTML). Execução incompleta, XML ausente ou cancelada nunca limpa a issue. Regressão derruba o job; indisponibilidade ambiental não. Testes do script (regressão com exit 1, todos xfail, XML truncado, falha da API, concorrência) | P1 |
| T2 | User-Agent identificado por padrão, de fonte única (`freoa-verifica/<__version__> (+https://github.com/rickfreoa/freoa-verifica)`), harmonizando `transport.py`, `connectors/base.py`, `httputil.py`. Nenhuma exceção nova de UA de navegador nesta versão e nenhum fallback. A sonda (E2) testa cada conector com o identificado: conector que aceita passa a usá-lo; conector que recusa só mantém o UA anterior da 1.2.0 se a decisão 0048 demonstrar, por conector, justificativa compatível com a regra 3: conteúdo oficial público sem autenticação, ausência de desafio, e **permissão positiva** de acesso automatizado ao caminho usado (robots.txt que o permite, política de dados abertos ou termo de uso que o admite), com a captura dessa prova; sem essa prova, o conector passa a responder `unavailable(recusa_identificado)` e a perda de cobertura fica declarada no `FONTES.md` e no CHANGELOG. Recusa ao identificado em produção recebe categoria `recusa_identificado`, que não é ambiental, não vira xfail e aparece vermelha na saúde das fontes | P1 política e sondas / P2 mudança |
| F1 | Sonda TJDFT (`retornaInteiroTeor`, `inteiroTeor` de pesquisa, `termosAcessorios`, separadamente); decisão 0046. Se o campo trouxer íntegra, acórdãos ganham texto integral sob o critério do código (número, dispositivo e fecho), com testes de acórdão íntegro, fragmento, placeholder, processo divergente e registro duplicado; corrigir a redação da 0041 | P1 sonda / P2 condicional |
| F3 | Qualificação do `cjsg` do TJSP existente: N, intervalo, consultas e critério de parada fixados antes; parar no primeiro desafio sem trocar UA, IP ou rota. Decisão registra a amostra e seu limite. Correções no conector existente com regressão de payload, sessão, paginação, zero estrutural e documento | P1 |
| F2 | Sonda Comunica CNJ (UA identificado, sem `Origin`/`Referer` de terceiros; recorte; natureza do `texto`); decisão 0047 com o desenho de `texto_publicado` como tipo documental. Conector adiado para 1.4.0 | P2 só sonda |
| P1 | Bloco `cobertura` em `pesquisar_jurisprudencia`, por tribunal: capacidade, consulta executada (`acervo`, `ao_vivo`, `ambos`, `nenhuma`), motivo de não consulta (`nao_suportado`, `limite`, `falha`, `offline`), recorte e instante da captura do acervo, `total_remoto` (nulo se desconhecido) e sua exatidão, `lidos`, `indexados`, `truncado_remoto` e `truncado_local`. Corrigir o descarte de `CandidateList.total` e a confusão total × lidos em `base.py`. Total desconhecido nunca vira zero | P1 |
| P2 | Instruções e descrições do servidor MCP: `listar_fontes` → pesquisar → obter a parte disponível → verificar antes de citar; recorte e abstenção explícitos; sem prometer cobertura geral; testes do texto efetivamente exposto | P1 |
| T1 | Repetição em `transport.fetch`: só 502/503/504 sem marcador de desafio, teto de tentativas, prazo monotônico único, token bucket por tentativa, `Retry-After` honrado só dentro do orçamento, POST só se declarado idempotente; 403/429/desafio nunca; uma falha lógica conta uma vez no breaker. Entra depois das sondas | P2 |
| S4 | Bateria do snapshot: manifesto congelado do recorte (órgãos, meses, recursos, contagens, pendências); duplicatas, fronteiras temporais, páginas faltantes, decisões sem captura. Roda no corpus candidato e de novo após instalar os bytes exportados | P1 |
| D1 | Snapshot 1.3.0 com STJ ampliado: identidade do produtor (`fv-build-1.2.1`, pacote 1.2.0 em 239bef6), recursos e capturas usados, checkpoints, contagens por órgão/mês, `fv acervo reconstruir` com o pacote 1.3.0 antes de exportar, S4 e bench | P1 |
| D2 | Instalação e aceite por digest: instalador atualizado para a versão corrente, attestation obrigatória (falha sem verificação, salvo `-SemAttestation` explícito que marca a instalação como não verificada); `fv snapshot install` exige o digest específico da lista embutida e não aceita snapshot de release anterior (`snapshot.py:783`); `release.yml` cria a release como rascunho; `RELEASE.md` reescrito com a sequência abaixo | P1 |
| G1 | CI: lock universal (`uv pip compile --universal --generate-hashes`) cobrindo as oito combinações e as dependências de build; job separado para testes de repositório (AST, workflows, manifesto); 3.14 na matriz; Ruff (`S`, `BLE`, `TRY`, `E9`, `F`) com baseline e catraca; meta-teste que reprova mascaramento de gate em workflow bloqueante, com negativos documentados. Semgrep adiado | P2 |
| G2 | `AGENTS.md`: capturas reais com proveniência e sintéticas rotuladas; família de conectores por heurística de duas ocorrências | P3 |
| G3 | PyPI: o job `pypi` sai do `release.yml` e vai para `pypi.yml`, disparado só por `release: published` (portanto depois da auditoria dos bytes e da publicação do rascunho); baixa os assets da própria release, confere `SHA256SUMS` e attestation, inspeciona conteúdo (uma wheel, um sdist, sem `tests/`) e publica esses bytes por Trusted Publishing; cadastro do publicador tentado; ausência fica pendência registrada, sem token duradouro | P3 |

Adiado para 1.4.0: coleta integral (F4; nenhum adaptador com total exato comprovado), conector Comunica CNJ, conectores de TJs além do TJSP, Semgrep, avisos centralizados. Fora: STF por WAF, Falcão, PDPJ/JusBR. Íntegras do STJ seguem no PR #5; quando integrado, E1 o obriga a registrar suas fixtures.

## Papéis

- Supervisor e orquestrador: **Opus**. Especifica, distribui, integra, decide arquitetura e pendências, executa release, snapshot e instalação. Não aprova o próprio trabalho.
- Auditor: **Codex** (`codex exec -s read-only`). Contraparte deste plano e auditor de implementação e artefatos. Não edita o código auditado. Parecer vale para HEAD e árvore identificados; correção posterior invalida o parecer na extensão afetada.
- Desenvolvedores. Sonnet (`claude -p --model sonnet`): trilha A (P3 → P1 → P2), trilha B (E2 → E3 → F1/F3 condicionais), trilha E (T2 → T1). Cursor (`cursor-agent -p`): trilha C (S2 → S1 → S3 → G1, G3). Haiku (`claude -p --model haiku`): E1, G2, CHANGELOG e documentação.
- Pesquisador de fontes: **Antigravity** (`agy -p`). Executa sondas F1, F2, F3 e de UA somente pelo instrumento E2 (`transport`); sem navegador, `requests` ou HTTP próprio; sem ler o verificador além da interface pública.
- Registro por tarefa em `docs/auditoria/1.3.0/`: ferramenta, modelo efetivo, versão, commit, comando, saída, código terminal, limitações.
- No máximo uma trilha simultânea editando `service.py`, `transport.py` ou o contrato.

## Ordem

1. P3 (A) ‖ E1 (Haiku) ‖ E2 (B) ‖ S2 (C) ‖ G1 preparatório.
2. E3 (B) ‖ S1, S3 (C) ‖ sondas F1, F3, F2, UA (Antigravity, depois de E2) ‖ P1 (A, depois de P3).
3. T2 (E, depois das sondas de UA) ‖ F1/F3 condicionais (B) ‖ P2 (A).
4. T1 (E) ‖ G2, G3.
5. Auditorias Codex por bloco sobre a integração; bloqueador volta ao desenvolvedor.
6. Release na sequência abaixo.

## Sequência de release, snapshot e instalação

1. Congelar código funcional e versão 1.3.0 na integração; registrar commit.
2. Instalar a wheel local em ambiente limpo; `fv acervo reconstruir` sobre cópia do corpus candidato; exportar o snapshot; instalação **experimental** em home descartável com `--aceitar-nao-vinculado`; S4, integridade, `doctor --offline` e bench.
3. Congelar os bytes exportados e gravar o digest em `freoa_verifica/data/snapshots-oficiais.json`; commit. Repetir a instalação, agora vinculada, com a wheel desse commit, em home vazio.
4. Auditoria Codex sobre esse commit (manifesto, instalador, digest, código).
5. PR para `main`, CI verde nas oito combinações, merge, tag `v1.3.0` sobre o commit auditado. `release.yml` passa a criar a release como **rascunho** (`gh release create --draft`), com wheel, sdist, lock, `SHA256SUMS` e attestation produzidos pela CI.
6. Auditoria dos bytes da CI: baixar os assets do rascunho, conferir attestation (`gh attestation verify`), conteúdo da wheel (sem `tests/`, digest do snapshot embutido igual ao auditado) e instalar a wheel baixada em ambiente limpo com o snapshot vinculado. Anexar ao rascunho exatamente o snapshot auditado e seu `.sha256`; só então publicar o rascunho (`gh release edit --draft=false`). Os bytes publicados são os auditados, por identidade, não por reconstrução.
7. Instalar pelo instalador oficial: attestation verificada, digest esperado, vínculo, derivados atuais, `doctor`, smoke de `pesquisar_jurisprudencia` com bloco de cobertura.
