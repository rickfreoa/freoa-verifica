# 0049 — Captura reproduzível e instrumento de sonda

Data: 19/10/2026 · Versão: 1.3.0 · Origem: plano 1.3.0, trilha B (E2)

## Contexto

Fixtures eram gravadas à mão, sem garantia de que a requisição fosse a do conector. Sondas de
comportamento da fonte (por exemplo, user-agent) precisavam de instrumento próprio.

## Decisão

1. O payload da busca do TJDFT tem origem única: `tjdft.build_search_payload` (e `SEARCH_URL`).
   `extras` só aceita chaves documentadas da API pública; qualquer outra é `ValueError`.
2. `freoa_verifica.captura.capturar` monta a requisição só pelo `build_*` e a envia por
   `connector_fetch` (transporte: allowlist, limites, UA do conector). Grava os bytes sem
   reserializar e um registro JSON (url, parâmetros, status, cabeçalhos preservados, sha256,
   horário UTC, versão, UA efetivo). Falha vira registro `unavailable` com motivo e categoria,
   nunca arquivo de corpo vazio.
3. `scripts/capturar_fixture.py` grava fixtures `captura_real` com manifesto atômico; `--sonda`
   grava fora do repositório e não toca o manifesto. UA aceito: `conector` (padrão) ou
   `identificado` (`freoa-verifica/<versão> (+https://github.com/rickfreoa/freoa-verifica)`).
4. Captura e script não importam `urllib`, `http.client`, `requests`, `httpx` nem `socket`.
