# 0048 — User-Agent identificado em todos os conectores, sem exceção

Data: 20/10/2026. Origem: plano 1.3.0 (T2), sondas em `docs/auditoria/1.3.0/sondas/`; revista após o parecer B3 (B3-05).

## Decisão

Todo conector se identifica como `freoa-verifica/<versão> (+https://github.com/rickfreoa/freoa-verifica)`, valor derivado de fonte única. Não há exceção por conector, nenhum User-Agent de navegador no código e nenhum fallback: o código nunca troca de User-Agent depois de uma recusa.

As sondas de 20/10/2026, feitas pelo instrumento de captura (transporte do pacote, UA identificado), mostraram:

| Conector | UA identificado | Prova |
|---|---|---|
| tjdft, senado, cvm_normas, cvm_colegiado, bcb, stf, stj, tcu | aceito (200, conteúdo esperado) | sha256 no relatório das sondas |
| datajud | já identificado na 1.2.0 | — |
| tjsp (`cjsg`) | desafio CAPTCHA com qualquer UA | página de desafio `782ddba1…` |
| planalto | conexão encerrada sem resposta (`TransportError`), reproduzida em 5 tentativas; o mesmo recurso responde 200 a um UA de navegador | `planalto_l6404_identificado.captura.json`; `planalto_l6404_conector.html` (sha256 `6478ff36…dc48`) |

## Planalto: sem exceção

O plano (T2) só admite manter um UA diferente do identificado se a decisão demonstrar, por conector, conteúdo público sem autenticação, ausência de desafio e **permissão positiva** de acesso automatizado ao caminho usado, com a captura dessa prova. O parecer B3 (B3-05) concluiu que a prova não existe: as sondas mostram respostas diferentes conforme o cliente, mas não identificam a causa do encerramento nem excluem controle de borda; `robots.txt` com 404 não é permissão positiva; o art. 8º, § 3º, III, da Lei 12.527/2011 impõe o dever de dados abertos ao órgão, mas não demonstra que o órgão admite o UA de navegador no caminho sondado. Sem a prova, aplica-se a alternativa do plano e da regra invariável 3: o Planalto usa o UA identificado como os demais.

Efeito: o Planalto encerra a conexão do cliente identificado sem responder. No conector Planalto, falha de transporte **anterior a qualquer resposta** (sem status registrado) vira `Unavailable(motivo="recusa_identificado_planalto", categoria="recusa_identificado", evidencia={"decisao": "0048", "causa": <motivo do transporte>, ...})`, nunca `fonte_fora`, para que a saúde das fontes não a trate como ambiental (não vira xfail; aparece vermelha). Respostas HTTP (5xx, 403 etc.) seguem a classificação geral. Não há segunda tentativa com outro UA.

Perda de cobertura declarada: a atualização ao vivo da legislação federal pelo Planalto fica indisponível. O acervo instalado continua atendendo consultas sem rede (`docs/FONTES.md`, CHANGELOG). A decisão será revista se o Planalto passar a aceitar o cliente identificado ou publicar permissão positiva de acesso automatizado com o esclarecimento técnico da recusa.

## TJSP

O `cjsg` exibe CAPTCHA independentemente do UA. O conector passa ao UA identificado e continua respondendo `unavailable(desafio)`; a afirmação do `FONTES.md` de que a busca está protegida fica confirmada por amostra (n = 2, ambas com desafio). Nenhuma mudança de comportamento além do UA.

## Implementação

- `freoa_verifica/identidade_http.py`: fonte única (`USER_AGENT_IDENTIFICADO`, tabela `UA_POR_CONECTOR`). Modo desconhecido é `ValueError`; não há fallback e o modo `navegador_1_2_0` não existe mais.
- Removidos os defaults divergentes: `DEFAULT_USER_AGENT` (`transport.py`), `IDENTIFIED_USER_AGENT` (`connectors/base.py`) e o modo `"browser"` (`connectors/httputil.py`). `transport._contact_headers`, `httputil.ua_header` e `captura.UA_IDENTIFICADO` importam do módulo novo.
- Cada conector declara `user_agent = UA_POR_CONECTOR["<id>"]`; todos resolvem para `identified`.
- `connectors/planalto.py`: `_reclassificar_recusa` aplica a regra acima na busca do documento e na sonda de saúde.
- 401/403 sem marcador de desafio seguem como `Unavailable(categoria="recusa_identificado")` (S2). O transporte passou a ler uma amostra (64 KiB) do corpo de respostas de erro e a registrar o desafio provado em `HTTPStatusError.desafio`; com marcador, a categoria é `ambiental_desafio`.
- Repetição limitada (T1) em `transport.fetch(repeticao=2, idempotente=False)`: só 502/503/504 sem marcador e falha de conexão/leitura; POST apenas com `idempotente=True`; 403, 429 e desafio nunca repetem; espera por `Retry-After` ou backoff de 1 s e 2 s com jitter de até 25%, sempre dentro do prazo total; `Retry-After` passa a constar dos cabeçalhos registrados; o circuit breaker conta uma falha por chamada lógica.
- Testes: `tests/test_user_agent_repeticao.py`.
