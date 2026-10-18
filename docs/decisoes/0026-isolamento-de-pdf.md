# 0026 — Isolamento do PDF da CVM (F03)

`_parse_pdf` deixa de rodar no processo do serviço. Passa por
`parsers.isolated.parse_isolated` com o perfil `cvm_pdf`: filho descartável,
com timeout do pai (90 s), no máximo 600 páginas e 8 MiB de texto extraído.
Em POSIX o filho também recebe `RLIMIT_AS` (1 GiB) e `RLIMIT_CPU` (60 s); no
Windows valem timeout e limites de páginas/texto.

Excesso, timeout, memória, PDF corrompido ou saída inválida viram
`Unavailable("pdf_nao_processado: <motivo>")`, sem derrubar o serviço. O filho é
morto no timeout e coletado (sem órfãos). Biblioteca de PDF ausente também é
`unavailable`, não texto vazio. Os limites são constantes de módulo, não configuração.
