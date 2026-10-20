# 0048 — User-Agent identificado em todos os conectores

Data: 20/10/2026. Origem: plano 1.3.0 (T2), sondas em `docs/auditoria/1.3.0/sondas/`, parecer `codex-audit-b3.md` (B3-05).

## Decisão

Todo conector se identifica como `freoa-verifica/<versão> (+https://github.com/rickfreoa/freoa-verifica)`, valor derivado de fonte única. Não há exceção nem fallback: o código nunca troca de User-Agent depois de uma recusa.

As sondas de 20/10/2026, feitas pelo instrumento de captura (transporte do pacote, UA identificado), mostraram:

| Conector | UA identificado | Prova |
|---|---|---|
| tjdft, senado, cvm_normas, cvm_colegiado, bcb, stf, stj, tcu | aceito (200, conteúdo esperado) | sha256 no relatório das sondas |
| datajud | já identificado na 1.2.0 | — |
| tjsp (`cjsg`) | desafio CAPTCHA com qualquer UA | página de desafio `782ddba1…` |
| planalto | conexão encerrada sem resposta, reproduzida em 5 tentativas; o mesmo recurso responde 200 ao UA de navegador da 1.2.0 | `planalto2__planalto_l6404_identificado.captura.json`; controle `planalto_l6404_conector` (sha256 `6478ff36…dc48`) |

## Planalto

O supervisor propôs manter, só no Planalto, o UA de navegador da 1.2.0, com fundamento no art. 8º, § 3º, III, da Lei 12.527/2011, que impõe aos sítios oficiais o dever de "possibilitar o acesso automatizado por sistemas externos em formatos abertos, estruturados e legíveis por máquina". O auditor recusou (B3-05), e a objeção prevalece por três razões:

1. As sondas provam que o servidor trata os clientes de modo diferente, não por que o faz. Sem identificar a causa, não se exclui um controle de borda; e contornar controle é o que a regra 3 proíbe.
2. O dever legal do órgão de permitir acesso automatizado não equivale a uma permissão para este cliente se apresentar como navegador neste caminho. A condição do plano exige permissão positiva capturada (robots, política ou termo que abranja o caminho), não a inferência de um dever genérico.
3. O critério foi fixado antes das sondas, em consenso. Afastá-lo quando o resultado incomoda transformaria a regra em preferência.

Consequência: o conector Planalto usa o UA identificado. Falha de transporte anterior a qualquer resposta é reclassificada como `recusa_identificado` (motivo `recusa_identificado_planalto`, evidência com referência a esta decisão), nunca `fonte_fora`, para que a saúde das fontes a mostre como falha e não como indisponibilidade ambiental. Respostas HTTP seguem a classificação geral.

Alcance da perda: o acervo instalado (snapshot) continua respondendo a consultas de legislação federal sem rede. Perde-se a captura ao vivo de normas e redações ausentes do acervo e a atualização incremental do Planalto até que haja permissão positiva ou mudança no servidor.

## Questões abertas

- Pedir ao órgão (Presidência da República, Portal da Legislação) manifestação sobre o acesso automatizado identificado, ou um canal de dados abertos para a legislação compilada. Uma resposta positiva e capturada reabre a decisão.
- Avaliar fontes oficiais alternativas de texto compilado (LexML, Senado) que aceitem o cliente identificado, sem perda do controle de redações.

## TJSP

O `cjsg` exibe CAPTCHA independentemente do UA. O conector usa o UA identificado e continua respondendo `unavailable(desafio)`; a afirmação do `FONTES.md` de que a busca está protegida fica confirmada por amostra (n = 2, ambas com desafio).

## Implementação

- `freoa_verifica/identidade_http.py`: fonte única (`USER_AGENT_IDENTIFICADO`, tabela `UA_POR_CONECTOR`). Modo desconhecido é `ValueError`; não há fallback.
- Removidos os defaults divergentes: `DEFAULT_USER_AGENT` (`transport.py`), `IDENTIFIED_USER_AGENT` (`connectors/base.py`) e o modo `"browser"` (`connectors/httputil.py`).
- Cada conector declara `user_agent = UA_POR_CONECTOR["<id>"]`; todos resolvem para o identificado. `connectors/planalto.py`: `_reclassificar_recusa` aplica a regra do Planalto na obtenção do documento e na sonda de saúde.
- 401/403 sem marcador de desafio são `Unavailable(categoria="recusa_identificado")` (decisão 0045). O transporte lê uma amostra (64 KiB) do corpo de respostas de erro e registra o desafio provado; com marcador, a categoria é `ambiental_desafio`.
- Repetição limitada (T1) em `transport.fetch(repeticao=2, idempotente=False)`: só 502/503/504 sem marcador e falha de conexão sem resposta; POST apenas com `idempotente=True`; 403, 429 e desafio nunca repetem; espera por `Retry-After` ou backoff de 1 s e 2 s com jitter de até 25%, sempre dentro do prazo total; o circuit breaker conta uma falha por chamada lógica.
- Testes: `tests/test_user_agent_repeticao.py`.
