# 0060 — Content-Encoding validado antes de qualquer desvio por status

Data: 20/10/2026 · Versão: 1.3.0 · Origem: auditoria final, rodada 10 (F-18); complementa a 0045 e a 0059

## Problema

A recusa de `Content-Encoding` só ocorria no ramo 200. Em 4xx/5xx o corpo era examinado em busca de desafio
sem decodificação; um corpo gzip/deflate com marcador de CAPTCHA parecia "sem marcador", e 502/503/504 eram
repetidos (3 pedidos) sem bloquear o host.

## Regra

1. Num único ponto, logo após a validação de framing e antes de qualquer desvio por status (redirecionamento,
   erro ou sucesso), `Content-Encoding` diferente de ausente ou `identity` é `RespostaInvalida`
   (`resposta_inesperada`), sem repetição, em qualquer status.
2. O transporte não decodifica gzip/deflate nem em 200; a mesma lista vale para o exame de desafio. Se vier a
   decodificar, terá de fazê-lo também no exame de 4xx/5xx (64 KiB descomprimidos, com proteção contra bomba) e
   a guarda bloqueará o host quando o desfecho for desafio identificado.
3. "Não examinei" nunca equivale a "sem marcador".

## Consequências

- Corpo comprimido com marcador de desafio deixa de ser `ambiental_desafio`: é `resposta_inesperada`, 1 pedido.
  O pedido já declara `Accept-Encoding: identity`; servidor que comprime mesmo assim é tratado como anômalo.
- Teste: `tests/test_fix14_content_encoding.py`.
