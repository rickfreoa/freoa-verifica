# Histórico de versões

## 1.0.3 (18/10/2026)

- Monotonia estrutural (decisão 0034): captura de texto compilado que perde dispositivos do modelo canônico não é promovida (`PERDA_ESTRUTURAL` em `divergentes` de reprocessar, reconstruir e instalar snapshot); `pode_negar` não nega caminho de captura canônica anterior (`ESTRUTURA_DIVERGENTE_ENTRE_CAPTURAS`).
- ADCT com escopo próprio (`adct/artN`) no parser do Planalto (`parser_version` 1.2.3), sentinela `SCOPE_COLLISION` contra substituição entre escopos e extração de "art. N do ADCT" (decisão 0022).
- Negativa de dispositivo exige estrutura (decisão 0023): `pode_negar` único em todos os consumidores; obra não capturada é `COBERTURA`, documento cortado, em quarentena ou sem dispositivos estruturados (PDF da CVM) é `unknown` com motivo, nunca `inexistente`. "caput" usa a resolução canônica.
- Histórico ausente (decisão 0024): data sem redação selecionada não confronta nem devolve a redação atual como se fosse da data (`HISTORICO_ANTERIOR_AUSENTE`; `texto=null` e `texto_atual` rotulado); `redacoes_anteriores` exclui a vigente; `redacao_anterior_ausente_na_fonte`.
- `verificar_texto` lista remissões anafóricas como `referencia_nao_resolvida` e informa `total_detectado`, `total_processado` e `truncado` acima de 200 citações.
- Recibo final (decisão 0027): o recibo é gravado depois de todos os rebaixamentos e coincide com a resposta; `verificar_citacao` aplica o bloqueio de confiança de extração (corrige "Lei 6.404/1976: art. 117 do contrato" verified).
- Data do ato alterador extraída da epígrafe já capturada quando o Senado não fornece a data; só preenche a data completa, nunca inventa, e data inválida fica sem valor (M8).
- Coluna `rubrica` no índice FTS de redações (migração 006, preserva as linhas existentes); o parser do Planalto captura a rubrica (linha centrada antes do "Art.") em `Provision.rubrica` e ela alimenta a coluna: "dever de lealdade" acha o art. 155 da LSA. Modelos persistidos sem o campo continuam carregando (M11).
- Rótulos CVM com mojibake (UTF-8 lido como latin-1) são corrigidos ao gravar e ao instalar snapshot, só quando a reversão é UTF-8 válido e reduz caracteres suspeitos (M11).
- Situação da obra (C2, decisão 0021): tabela `work_status` alimentada pela página do ato CVM (sempre capturada) e pelos campos `Revogado`/`Cancelado` do BCB/CMN. Ato revogado ou cancelado deixa de sair `vigente_na_fonte` (`OBRA_REVOGADA_NA_FONTE`, inclusive em citação só da obra); data passada sem `data_efeito` é `unknown REVOGACAO_DATA_DESCONHECIDA`; revogação futura preserva a análise e marca `REVOGACAO_POSTERIOR`; situação ilegível ou com mais de 30 dias nunca é vigente. A página do ato CVM deixou de presumir vigência. `Verifica.ressincronizar_situacao()` relê o acervo.
- Busca CVM: decodificação UTF-8 correta (consultas acentuadas), sem exigir a frase literal, `unavailable` quando a fonte informa total > 0 e nada é lido, um item por ato (anexos duplicados descartados) e espécie acompanhando o número ("Instrução CVM 358"). Busca CVM/BCB informa `truncado` pelo total da fonte.
- BCB/CMN: "Resolução CMN 4.966" na consulta aciona o lookup exato por número.
- `fv acervo ressincronizar-situacao` relê a situação dos atos CVM/BCB/CMN. Conectores devolvem `CandidateList` com `total` e `truncado` reais (A9); `buscar_normas_*` e `buscar_legislacao` os repassam. Migrações em sequência: 006 rubrica, 007 `work_status`, 008 `fts_staging`.
- PDF da CVM roda em processo isolado com limites de tempo, memória, páginas e texto (decisão 0029).
- Busca (frente F-D, decisão 0025): consulta que é só classe e número (`REsp 2.210.785`, `Recurso Especial nº ...`) faz lookup exato no acervo; achado traz evidência, incidentes do mesmo processo vão em `relacionados` e ausência devolve `nao_confirmado_no_acervo` com a cobertura (tribunais, órgãos, período), sem outros processos.
- Candidatos de legislação indexados ao vivo ficam em `fts_staging` (migração 008), fora do FTS canônico; só a busca que consulta fontes ao vivo os vê, marcados `candidato_ao_vivo`.
- Fontes não consultadas (offline, limite atingido, sem busca textual como o Planalto) aparecem como `nao_consultada`; `truncado` e `total` por fonte são propagados quando o conector os informa.
- Filtro `fonte` da busca local de legislação é aplicado antes do limite.
- Ranking: MATCH de decisões restrito a ementa e inteiro teor, bm25 ponderado (ementa 5, inteiro teor 1), `pertinencia` e `correspondencia` em cada item, corte de dois terços dos termos e OR completando AND escasso (substitui "OR só com AND vazio" da 0010).
- Tesauro jurídico `tesauro-1` (20 pares determinísticos, `freoa_verifica/data/tesauro-1.json`) expande a consulta por OR; a versão e as expansões saem na resposta.
- Fronteiras remotas (decisão 0026): modo local/remoto explícito na API REST e no MCP HTTP; token obrigatório fora de loopback, verificado em toda requisição, inclusive ao carregar a fábrica ASGI diretamente.
- Validação de entrada compartilhada na fachada (tipos e tetos), corpo HTTP limitado antes da leitura integral, semáforo para operações caras; entrada inválida devolve 422, excesso de corpo 413, sobrecarga 503.
- Âncora textual: o intervalo devolvido é validado contra o trecho casado; sem prova, a âncora é recusada em vez de apontar caracteres errados (NFC, múltiplas composições).
- Conexões SQLite com dono registrado, fechamento coordenado e falhas registradas em log; a instalação de snapshot e a purga esperam as operações ativas.
- MCP: um serviço por home no mesmo processo.
- Política de registro `sem_conteudo` (`--sem-registro`) e `fv runs purgar --antes DATA` (decisão 0030).
- Snapshot publica identificadores das obras e das decisões e `derived_version`; `fv doctor`, o MCP e a API avisam `acervo_incompleto` quando o home está abaixo do manifesto instalado ou do mínimo embutido.
- Release só publica após a suíte completa no mesmo commit, sem substituição de assets, com `requirements-lock.txt` anexado. Actions fixadas por SHA de commit (tag em comentário).

- Derivados versionados (C6, decisão 0028): `DERIVED_VERSION` em `meta` (migração 009); home de versão anterior responde `indisponivel/ACERVO_DESATUALIZADO`; `fv acervo reconstruir [--com-situacao]` refaz modelo, dispositivos, redações e FTS numa cópia e troca o banco atomicamente; a instalação de snapshot com derivados mais novos substitui os modelos locais; o manifesto leva a `derived_version` real. Dispositivos novos de um modelo reprocessado passam a ser gravados e os antigos removidos.

- Purga de execuções em ordem segura (banco novo gravado em disco, original movido, novo instalado) com recuperação automática de troca interrompida (decisão 0030).

- Normas de série única citadas sem ano ("Resolução CMN 4.966", "Resolução BCB 428", "Resolução CVM 80", "Instrução CVM 358") são tratadas como exatas quando o acervo tem exatamente uma obra com o número; com zero ou mais de uma, ou para lei sem ano, seguem exigindo conferência (decisão 0031).

## 1.0.2

- Extração de citações em duas camadas: regras estruturais (numeração decimal de cláusulas, siglas coladas a números, pertença a instrumentos particulares, fronteiras de arquivo e de campo técnico) e confiança explícita `exata`/`provavel`. Em `verificar_texto`, citações `provavel` recebem `requer_conferencia`; só `exata` recebe `encontrada` ou `inexistente`. Nos oito corpora adversariais independentes (779 frases), falsos definitivos caíram de 250 para 0 e o recall subiu de 70,9% para 93,7%.
- Associação de dispositivo posterior exige vírgula ou travessão na mesma oração e rejeita dispositivos de instrumentos particulares; reconhece `Instr. CVM`, `Inst. CVM` e `IN CVM`.
- Corpus literal de 80 frases e controles de fronteira sintática cobrem as regressões de identidade.
- Staging de snapshots fica no diretório de dados, configurável por `FV_STAGING_DIR`, com testes isolados em `tmp_path`.
- Extração em prosa preserva o ponto de aliases como `Lei das S.A.`, aceita quebras de linha e dispositivos abreviados com `inc.` e `al.`.
- Artigos e preposições anteriores à norma não são tratados como alíneas isoladas; dispositivos após a norma, separados por vírgula, são associados corretamente.
- Trechos entre aspas após abreviações são confrontados, e listas de artigos verificam cada dispositivo extraído.
- Corpus independente de 118 frases sintéticas cobre pontuação, abreviações, listas, remissões não resolvidas e controles negativos.
- Instalação de snapshot mantém a seleção da última release que contenha esse asset, mesmo quando releases posteriores só distribuam o pacote.

- `FV_READ_ONLY=1` permite verificar normas no acervo instalado sem gravações no banco ou captura sob demanda.

## 1.0.1

- Pesquisa primeiro no acervo instalado de decisões de todos os tribunais, com FTS reconstruído na exportação/instalação, ranking bm25, desempate por autoridade/data e filtros SQL antes da paginação.

- Instalação de snapshots com download em fluxo, publicação atômica do arquivo e conferência de SHA-256 antes da extração; seleção da release mais recente com snapshot.
- `verificar_texto` preserva `formato_invalido` e exige evidência de negativa oficial para informar `inexistente`.

## 1.0.0

Primeira versão pública.

- Verificação de citações em quatro dimensões (identidade, texto, tempo, suporte), com evidência reproduzível: URL oficial, data de captura, SHA-256, caminho do dispositivo e trecho.
- Legislação federal (Planalto, com datas dos atos alteradores via Senado), normas da CVM (consolidados oficiais com redações anteriores e notas datadas) e do CMN/BCB.
- Jurisprudência e decisões administrativas: STJ (dados abertos), STF (portal de processos, decisões e Repercussão Geral), TJSP, TCU, Colegiado da CVM; metadados processuais pelo DataJud.
- `verificar_texto`: extrai todas as citações de um texto e informa, uma a uma, se existem.
- Motor temporal por eventos, com estados `verified`, `vigente_na_fonte`, `unknown`, `revogado`, `nao_existia` e `ambiguous`.
- Servidor MCP (stdio e streamable HTTP), CLI `fv` e API REST.
- Corpus semente distribuído como snapshot verificável.
