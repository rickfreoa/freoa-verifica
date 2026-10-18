# 0008 — Filtro de tribunal e busca incompleta

O filtro de tribunal é normalizado antes da seleção local, do limite e da
paginação. Siglas, caixa e nomes por extenso identificam o mesmo tribunal;
CVM e cvm_colegiado identificam a mesma fonte. A ausência de filtro mantém
todo o acervo local; uma lista vazia seleciona nenhum tribunal. O MCP aceita
os mesmos nomes e inclui STF. Fonte desconhecida e modo offline são
explicitados no estado das fontes quando solicitados.

A busca textual do TCU percorre um recorte limitado da API. Atingir o teto
sem completar a quantidade solicitada não demonstra ausência: produz
indisponibilidade com motivo de busca incompleta. Uma página vazia encerra
a varredura normalmente. O formulário TJSP obedece à detecção de CAPTCHA,
sem exceção para desafios embutidos. Nenhum desses ajustes altera os
critérios de verificação ou autoriza contornar controle de acesso.

Na indexação de candidatos normativos, categorias de catálogo CVM no plural
são convertidas para o tipo canônico. A espécie declarada nos metadados de
busca BCB distingue CMN, BCB e os respectivos tipos. A identidade assim
solicitada continua sujeita ao confronto com a epígrafe do documento.

Buscas especializadas preservam os candidatos capturados quando outros
candidatos falham. A resposta é parcial e expõe as falhas por chave, URL e
motivo; nenhum trecho de candidato sem captura é exposto. Se todos falharem,
o resultado é indisponível. Modo offline também é indisponibilidade explícita,
sem simular busca bem-sucedida com zero resultados.
