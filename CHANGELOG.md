# Histórico de versões

## 1.0.3 (em preparação)

- Data do ato alterador extraída da epígrafe já capturada quando o Senado não fornece a data; só preenche a data completa, nunca inventa, e data inválida fica sem valor (M8).
- Coluna `rubrica` no índice FTS de redações (migração 006, preserva as linhas existentes); o parser ainda não captura a rubrica de artigo, então a coluna fica vazia até essa captura existir (M11, pendente).
- Rótulos CVM com mojibake (UTF-8 lido como latin-1) são corrigidos ao gravar e ao instalar snapshot, só quando a reversão é UTF-8 válido e reduz caracteres suspeitos (M11).

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
