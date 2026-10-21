# 0064 — Validação primeiro, recibo da interpretação, situação interrompida e garantias estruturais

Data: 21/10/2026 · Versão: 1.3.0 · Origem: auditoria final, rodada 14 (F-19, F-22, F-23); revê as regras 1 e 3 da
0063 e a 0021 (C2) na ressincronização

## Problema

1. **F-19.** A 0063 já dizia "qualquer que seja o mime", mas `texto_da_resposta` só validava os parâmetros
   proibidos ao procurar o charset: com BOM (o BOM decide antes) ou com MIME binário (`application/pdf`, lido como
   latin-1) a validação era pulada. `charset*=x` ou `charset` duplicado com BOM era aceito em 200 e repetido em 503;
   `application/pdf; charset*=x` com CAPTCHA em UTF-16 também.
2. **F-22.** `indexar_obra` fabricava um `Response` sem Content-Type para o recibo; `reprocessar_capturas` relia os
   bytes sem ele e o Planalto caía na escada de `decode_html_bytes`, que seguia o `<meta>` Latin-1: "Ação" virava
   "AÃ§Ã£o" com `reprocessados:1, falhas:[]`.
3. **F-23.** `situacao.ressincronizar` (CVM e BCB) convertia toda falha em `ilegivel` e seguia para a próxima obra
   da mesma fonte: CAPTCHA, 403 ou 503 terminavam `status:"ok"`, sem categoria; em 503, seis pedidos para duas obras.
4. Cada rodada fechava os caminhos encontrados, não a classe.

## Regra

1. **Validação primeiro.** `interpretar(corpo, content_type)` valida o media type (gramática estrita, sem
   `charset*`/continuações, sem `charset` duplicado divergente) antes de qualquer desvio por BOM, MIME binário ou
   status. O BOM decide a codificação, nunca dispensa a validação. Cabeçalho de borda de desafio continua prova
   positiva independente do corpo.
2. **Desafio sob MIME binário.** Corpo com BOM, ou com marcador HTML (`<html`, `<!doctype`) nos bytes ou na vista do
   `charset` declarado, é lido como texto mesmo sob MIME binário: um desafio HTML servido como PDF é desafio. Sem
   isso, a vista latin-1 serve só a marcadores ASCII.
3. **Recibo da interpretação.** A captura persiste (migração 014) `content_type` (cru), `codificacao` (codec usado;
   nulo se binário) e `origem_da_codificacao` (`bom`, `header`, `meta`, `declaracao_xml`, `padrao`, `binario`;
   `declaracao_xml` distingue a declaração XML do `<meta>` HTML). `indexar_obra` recebe o Content-Type da resposta
   lida pelo parser. Content-Type desconhecido fica nulo; nunca é inventado.
4. **Releitura.** `reprocessar_capturas` (e por ele `fv acervo reconstruir` e a instalação que reconstrói) monta o
   `Response` com o Content-Type do recibo; captura anterior à 014 usa o `content-type` de `headers_json`. Sem
   nenhum, a captura é `falha: interpretacao_indisponivel` e o modelo não muda; decisão persistida que a função
   atual não reproduz é `falha: interpretacao_divergente`. Nunca outra interpretação, em silêncio: o Planalto não
   tem mais a escada sem Content-Type, e `_restore_stj_ementas` lê o JSON pela mesma função. A exibição de captura
   (`obter_evidencia`) usa o recibo e, se inválido, a vista UTF-8/latin-1 declarada como exibição.
5. **Snapshot.** O export leva as três colunas; a fusão aceita snapshot anterior sem elas (as colunas ficam nulas e as
   capturas seguem a regra 4).
6. **Situação.** Na ressincronização, falha que é da fonte (categoria provada, ou orçamento) é gravada como leitura
   frustrada da obra (`ilegivel`, com motivo e categoria, sem apagar leitura autêntica anterior) e sobe ao
   controlador, que não consulta as obras seguintes daquela fonte. O retorno é `parcial` (houve leituras) ou
   `indisponivel`, com `motivo`, `categoria`, `evidencia_indisponibilidade`, `fontes.<id>` e `nao_consultadas`.
   Diferente da 0063 (regra 5), `resposta_inesperada` também interrompe: todas as obras pedem a mesma página da
   mesma fonte. Item ausente (`http_404`, sem categoria) segue sendo do item. Fora da ressincronização, a página do
   ato continua evidência acessória (`registrar_cvm` sem `propagar`). A reconstrução com situação devolve
   `parcial`; `fv acervo ressincronizar-situacao` e `fv acervo reconstruir` saem com 1 se não `ok`.
7. **Garantias estruturais.** `tests/test_garantias_estruturais.py` (marcado `repositorio`) verifica por AST, sobre
   `freoa_verifica/`: (1) toda chamada de rede (métodos derivados de `ENTRADAS_DE_REDE` e dos conectores,
   `connector_fetch`) roda sob a guarda; (2) controlador (try em laço, ou função chamada no laço de um controlador)
   não engole `Unavailable` sem `raise` ou registro com categoria; (3) `.decode(` só em `texto_resposta.py`, salvo
   linhas justificadas que não são corpo de resposta; (4) parser não recebe `.body` nem bytes de blob, nem por
   variável; bytes binários só por `corpo_binario(resp)`, que valida o Content-Type. Exceção nova exige
   justificativa escrita no próprio teste.

## Consequências

- Capturas normativas gravadas antes da 014 por `indexar_obra` não têm Content-Type em lugar nenhum (`headers_json`
  era `{}`): reconstruir um acervo assim falha com `interpretacao_indisponivel`, original intacto, até nova captura.
- A captura real da LSA no manifesto (`text/html` sem charset, cp1252 sem `<meta>`) não é interpretável pela
  função única (padrão UTF-8 da 0061). Antes desta decisão, só o caminho sem Content-Type a lia (pela escada).
- Testes: `tests/test_fix18_f19_validacao_primeiro.py`, `tests/test_fix18_f22_recibo_interpretacao.py`,
  `tests/test_fix18_f23_situacao.py`, `tests/test_garantias_estruturais.py`.
