# Histórico de versões

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
