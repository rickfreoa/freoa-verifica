# Identidade anual, lacunas históricas e autenticação nas consultas

O ano declarado na epígrafe ou na data do ato capturado integra a identidade da
obra também quando a consulta original omite o ano. Referências no corpo não
servem para completar identidade. O reparo idempotente altera a projeção `work`,
preservando capturas e extrações. Conflito, ausência de declaração ou falha de
integridade geram pendência explícita em `work_year_issue`, incluída no snapshot.

O início da primeira redação disponível não demonstra o início do dispositivo.
Uma alteração (`redacao_dada`) sem história anterior produz `unknown` com
`HISTORICO_ANTERIOR_AUSENTE`. Somente inclusão datada ou consulta anterior à obra
permitem `nao_existia`. Ausência de redações também constitui lacuna histórica.

Consultas de dispositivos, resolução, histórico, evidência, decisões e buscas
locais autenticam a captura antes de devolver texto ou estado positivo. O mesmo
contrato é compartilhado pelas fachadas: blob ausente ou corrompido produz
`unavailable`, com `EVIDENCIA_AUSENTE` ou `EVIDENCIA_CORROMPIDA`, sem texto derivado.
Buscas externas capturam o documento para expor trechos; os resultados continuam
candidatos, sem comprovação de teor. Metadados de busca não substituem a captura.
