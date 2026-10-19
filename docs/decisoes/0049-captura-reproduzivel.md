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

## Emenda FIX1 (auditoria do bloco 1)

1. A `chave` é validada (`^[a-z0-9_]+$`) antes de qualquer rede; cada arquivo final é resolvido e confinado
   ao destino. A API `capturar` com `sonda` recusa destino igual ou interno ao repositório.
2. Manifesto: a entrada `captura_real` usa `url_final`, `capturado_em` e
   `origem_metadados: "captura_instrumento"`; `validar_inventario` deve devolver `[]` após a captura. O
   registro completo fica ao lado da fixture como `<chave>.captura.json`, inventariado na categoria
   `metadados_captura` (o campo `descreve` aponta a fixture).
3. Publicação recuperável: bloqueio `FIXTURES.json.lock` (`O_EXCL`, espera limitada), temporários de nome
   único, diário `FIXTURES.json.pendente`, troca atômica do manifesto como confirmação e renomeio final.
   `recuperar_pendentes()` conclui ou desfaz a publicação interrompida e remove temporários órfãos.
4. Sem observação preservada, `status` e `content_type` são `null` com `origem_metadados: "desconhecida"`
   (os cinco registros TJDFT).
5. Categoria e evidência do registro vêm de `Unavailable.categoria` e `.evidencia`, sem inferência pelo
   texto do motivo.
6. Novos modos: `--conector <nome> --url <URL>` (GET simples; URL dentro da allowlist do conector, recusada
   antes da rede; `/robots.txt` do host permitido é aceito) e
   `--conector tjsp --consulta '{"termo": "...", "pagina": 1}'`, montada por `tjsp.build_cjsg_request`, a
   mesma função do conector. `--user-agent` vale para todos os modos.
