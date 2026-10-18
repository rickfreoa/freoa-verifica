# 0009 — Pesquisa no acervo de decisões instalado

A pesquisa de jurisprudência consulta primeiro o FTS comum de decisões, vinculado aos documentos e capturas persistidos. O índice auxiliar de sincronização do STJ não é requisito para pesquisar um snapshot instalado. Exportação e instalação reconstroem o índice derivado; snapshots antigos sem FTS continuam instaláveis e pesquisáveis.

O ranking usa bm25, seguido de autoridade, data de julgamento (publicação na ausência desta) decrescente e identificador para estabilidade. Tribunal, datas e autoridade mínima são predicados SQL anteriores à paginação por cursor. A autoridade segue a regra existente; resultados continuam candidatos e as capturas são autenticadas antes da resposta.

A complementação ao vivo exige busca textual ao vivo declarada pelo conector. O índice auxiliar do STJ e a varredura limitada do TCU não oferecem essa capacidade. Indisponibilidade externa e ausência de correspondência no recorte local não demonstram ausência de jurisprudência.

Capturas STJ antigas podem conter somente o dispositivo na extração rotulada como ementa. Havendo JSON original autenticado, exportação e instalação recuperam a ementa por identificador oficial e acrescentam uma extração com hash próprio, preservando a anterior. Novas capturas persistem a ementa separadamente do inteiro teor.
