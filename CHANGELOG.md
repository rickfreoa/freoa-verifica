# Histórico de versões

## 1.0.3 (em preparação)

- Busca (frente F-D, decisão 0025): consulta que é só classe e número (`REsp 2.210.785`, `Recurso Especial nº ...`) faz lookup exato no acervo; achado traz evidência, incidentes do mesmo processo vão em `relacionados` e ausência devolve `nao_confirmado_no_acervo` com a cobertura (tribunais, órgãos, período), sem outros processos.
- Candidatos de legislação indexados ao vivo ficam em `fts_staging` (migração 0040), fora do FTS canônico; só a busca que consulta fontes ao vivo os vê, marcados `candidato_ao_vivo`.
- Fontes não consultadas (offline, limite atingido, sem busca textual como o Planalto) aparecem como `nao_consultada`; `truncado` e `total` por fonte são propagados quando o conector os informa.
- Filtro `fonte` da busca local de legislação é aplicado antes do limite.
- Ranking: MATCH de decisões restrito a ementa e inteiro teor, bm25 ponderado (ementa 5, inteiro teor 1), `pertinencia` e `correspondencia` em cada item, corte de dois terços dos termos e OR completando AND escasso (substitui "OR só com AND vazio" da 0010).
- Tesauro jurídico `tesauro-1` (20 pares determinísticos, `freoa_verifica/data/tesauro-1.json`) expande a consulta por OR; a versão e as expansões saem na resposta.

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
