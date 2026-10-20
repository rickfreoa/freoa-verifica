# 0041 — Conector TJDFT (API pública de jurisprudência)

Data: 18/10/2026 · Versão: 1.2.0 · Origem: plano 1.2.0, P1 cobertura

## Contrato

`POST https://jurisdf.tjdft.jus.br/api/v1/pesquisa`, corpo `{"query", "pagina" (0-based), "tamanho", "termosAcessorios"?}`,
pelo transporte central (lista branca do host, caminho `/api/v1/pesquisa`, `application/json`, 1 req/s por host).
A resposta JSON inteira é a captura (bytes e sha256). Cada candidato guarda `uuid` + `identificador`; ao indexar, o
registro é localizado na captura por `uuid` e `identificador` (nunca por posição); ausência ou duplicidade → `Unavailable`.
Não há URL de documento por `uuid`; nenhuma é inventada (`url_oficial` fica vazio).

## Espécie e campos

`decisoes-monocraticas` e `decisoes-presidencia` → `monocratica`; base `acordaos` → `acordao`; outra espécie →
`Unavailable`. Tribunal `TJDFT`, `official_id` = `identificador`, número do processo em `metadata["processo"]`.
`segredoJustica` verdadeiro: registro descartado na busca e recusado no parse.

## Inteiro teor

Só quando `inteiroTeor` (ou `inteiroTeorHtml`, convertido para texto) (a) não contém "Inteiro Teor indisponível"
(sem acentos/caixa), (b) tem ao menos 1000 caracteres, (c) contém o número do processo do registro, (d) tem parte
dispositiva e (e) termina com fecho (auditoria 1.2.0; critério completo e extensão aos acórdãos na decisão 0046). Então perfil
`tjdft_inteiro_teor` e `metadata["documento"]="inteiro_teor"`. Caso contrário perfil `tjdft_ementa`, sem texto integral.
`possuiInteiroTeor` sozinho nunca promove (decisão 0038).

## Falhas

HTTP diferente de 200, JSON inválido, `hits` inválido ou `registros` ausente/vazio com `hits>0` → `Unavailable(motivo)`.
`hits=0` legítimo → lista vazia com `total=0`.

## Limites

Sem `retornaInteiroTeor` a API quase não traz a íntegra dos acórdãos; a decisão 0046 passou a pedi-la. `desde`/`ate`
da busca ao vivo não são repassados à API (filtro local, decisão 0053). Classe processual (`class_name`) não é
derivada. Semente temática pequena e configurável em `corpus_semente.json` (`jurisprudencia.tjdft`), com checkpoint por consulta.
