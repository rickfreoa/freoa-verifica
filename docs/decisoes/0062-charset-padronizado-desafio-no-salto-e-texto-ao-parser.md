# 0062 — Charset por algoritmos padronizados, desafio em salto de redirecionamento e texto ao parser

Data: 20/10/2026 · Versão: 1.3.0 · Origem: auditoria final, rodada 12 (F-19, F-21, F-22, F-17); revê a regra 2 da 0061

## Problema

1. **F-19.** A extração de charset por expressão regular aceitava `data-charset`, `charset=` dentro de comentário ou
   de outro atributo e o parâmetro HTTP `x-charset`. Uma declaração falsa (`utf-16le`) fazia o corpo ASCII com
   "CAPTCHA" ser lido como lixo: 200 virava sucesso, 503 era repetido sem bloquear o host.
2. **F-21.** O transporte seguia `Location` em 301/302/303/307/308 sem examinar o salto; CAPTCHA no corpo ou
   `cf-mitigated: challenge` num redirecionamento eram ignorados e a cadeia terminava em 200.
3. **F-22.** A leitura de sucesso interpretava o corpo corretamente (função única) e depois entregava os BYTES ao
   parser, que os reinterpretava: título "Ação" virava mojibake, a busca por "Ação" dava `itens: []` com fonte `ok`.
4. **F-17.** O diagnóstico (`doctor`) chamava `health()` de cada fonte sem guarda: três sondas, três pedidos contra
   fonte que já desafiara.

## Regra

1. **Cabeçalho.** `Content-Type` é interpretado como media type (RFC 9110 §8.3.1) por `email.message.Message`;
   só o parâmetro chamado exatamente `charset` conta (`x-charset`, `foocharset` não), e o primeiro prevalece.
2. **HTML.** Sem `charset` no cabeçalho, vale o "prescan a byte stream to determine its encoding" do WHATWG HTML
   (§13.2.3.2) sobre os primeiros 1024 bytes: comentários são pulados, só `<meta charset>` e
   `<meta http-equiv="content-type" content="...charset=...">` são efetivos, o primeiro atributo de cada nome vale,
   atributos alheios (`data-charset`, texto em outro atributo, `content` sem `http-equiv`) são ignorados.
   UTF-16 declarado em meta vale UTF-8 e `x-user-defined` vale windows-1252 (regras do WHATWG).
3. **XML** (`*/xml`, `*+xml`) sem `charset` no cabeçalho: declaração `<?xml encoding?>` (RFC 7303 §3: o parâmetro
   `charset` do cabeçalho vence a declaração). UTF-16 declarado sem BOM vale UTF-8 (o corpo foi lido como ASCII).
   O texto resultante vai ao expat como `str`, que ignora a declaração.
4. **Rótulos** pela tabela de encodings do WHATWG (`texto_resposta._TABELA`): `latin1`/`ascii`/`iso-8859-1` são
   windows-1252, com byte indefinido mapeado ao ponto de código de mesmo valor. Rótulo fora da tabela, `replacement`
   e `x-user-defined` em cabeçalho são `RespostaInvalida`. BOM continua vencendo tudo (0061).
5. **Salto de redirecionamento.** Antes de seguir `Location`, `transport._percorrer` aplica
   `_desafio_na_resposta` (mesma função, mesma interpretação, mesmo limite de 64 KiB). Desafio levanta
   `HTTPStatusError(status, desafio=...)`: `ambiental_desafio` com `saltos`, nada é seguido. O salto leva
   `"desafio": <tipo>` e a guarda bloqueia esse host, apesar de o status ser de redirecionamento. Corpo ilegível no
   salto é `resposta_inesperada`, como em qualquer status.
6. **Texto ao parser.** Conectores obtêm o texto por `texto_do_response(resp)` (Content-Type cru do `Response`,
   não `resp.headers`, que não retém todos os charsets) e o entregam ao parser e aos filtros; o lxml só recebe
   `str` (`arvore_html`, que retira a declaração `<?xml?>`). Funções de parse aceitam `bytes | str`; `bytes` são
   interpretados por `texto_da_resposta`, nunca por `decode` próprio. Corpo ilegível é `RespostaInvalida` ou
   `Unavailable`, jamais lista vazia com fonte `ok`.
7. **Diagnóstico.** `Verifica.doctor` ativa uma `GuardaExecucao` por fonte: as sondas de uma fonte compartilham o
   bloqueio após desafio ou recusa.

## Consequências

- `cvm_normas._html_tree` deixou de aceitar cp1252 por tolerância: página sem declaração e não UTF-8 é
  `resposta_inesperada`.
- `parsers/html_devices.decode_html_bytes` (Planalto, relido de bytes capturados, sem Content-Type) usa o mesmo
  prescan; mantém sua escada de fallback (UTF-8, cp1252, latin-1) com `Issue ENCODING_FALLBACK`.
- Fora desta decisão: JSON (contrato UTF-8 próprio), CSV do STJ (UTF-8 com BOM explícito) e a exibição de captura
  armazenada (`service.obter_evidencia`), pois o armazém guarda `mime` e não o Content-Type cru.
- Testes: `tests/test_fix16_charset_redirect.py`.
