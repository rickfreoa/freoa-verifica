# Download em fluxo e apresentação de identidade

O transporte aceita destino em arquivo, com limite de até 4 GiB, SHA-256
incremental e publicação por renomeação no mesmo diretório somente após sucesso.
Sem destino, permanece o limite de 50 MiB. Allowlist por salto, IP fixado,
MIME, prazo absoluto e taxa mínima continuam obrigatórios. A resposta em fluxo
tem corpo vazio e informa tamanho e hash. Falhas preservam o destino anterior.

A instalação procura a release estável mais recente que contenha snapshot,
consultando releases anteriores quando necessário. O arquivo baixado só é
extraído depois do confronto com o checksum publicado.

Na apresentação de `verificar_texto`, `not_found` isolado não demonstra
inexistência. Formato inválido permanece `formato_invalido`; identidade
divergente, ausência no acervo e motivos desconhecidos ficam `indisponivel`.
`inexistente` exige negativa oficial ou dispositivo ausente no documento
oficial, com evidência capturada e autenticada. Os critérios das dimensões
de verificação permanecem inalterados.
