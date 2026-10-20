# 0061 — Interpretação textual única do corpo (BOM, charset, meta)

Data: 20/10/2026 · Versão: 1.3.0 · Origem: auditoria final, rodada 11 (F-19); complementa a 0045 e a 0060

## Problema

A detecção de desafio decodificava o corpo sempre como UTF-8 (`errors="replace"`). HTML em UTF-16, ou em
ISO-8859-1/windows-1252 com "verificação de segurança", não casava o marcador: 502/503/504 eram repetidos (3
pedidos) sem bloquear o host, e em 200 o desafio era devolvido como sucesso.

## Regra

1. Uma só função, `freoa_verifica.texto_resposta.texto_da_resposta(corpo, content_type)`, interpreta o corpo na
   detecção de desafio (`challenge.py`, `transport._desafio_na_resposta`) e na leitura de sucesso por conectores.
2. Ordem: BOM (UTF-8, UTF-16 LE/BE, UTF-32) → `charset` do Content-Type → `<meta charset>`/`http-equiv` nos
   primeiros 1024 bytes (HTML) → UTF-8. Decodificação estrita.
3. Charset desconhecido (`codecs.lookup`), não textual ou bytes inválidos no charset escolhido é
   `RespostaInvalida` (`resposta_inesperada`), sem repetição, em qualquer status. Mime não textual (PDF etc.) não
   tem charset e é lido como latin-1 apenas para busca de marcadores ASCII.
4. Amostra truncada (64 KiB) aceita sequência multibyte cortada no fim, e só nele.
5. Marcadores e texto são comparados normalizados (NFKC, casefold, sem acentos); a tabela de assinaturas guarda
   os marcadores já normalizados (versão da tabela inalterada: o conjunto de marcadores é o mesmo).
6. `Response.content_type` guarda o Content-Type cru: `headers` só retém charsets do recibo e perdia os demais.
7. Desafio em 200 é `ambiental_desafio`, nunca sucesso (já o era; agora vale em qualquer charset).

## Consequências

- Teste: `tests/test_fix15_charset.py` (matriz codificação × status × marcador em servidor TCP real, guarda e hook).
- Parsers que reexaminam bytes já capturados (`parsers/`, `cvm_normas._html_tree`, `cvm_colegiado` RSS/reunião,
  `stf._parse_aba_decisoes`) mantêm seus fallbacks próprios: não há decisão de segurança neles, a detecção estrita
  já ocorreu no `connector_fetch`.
