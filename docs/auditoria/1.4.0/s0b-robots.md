# S0b, parte 1: leitura do robots.txt pelo RFC 9309

Implementador: Sonnet, worktree `wt-s0b`, ramo `feat/s0b-robots`, base `origin/main` em `8447cf8` (merge do PR #14).
Decisão do titular de 28/10/2026, registrada em `docs/decisoes/0071-robots-rfc-9309-na-s0.md`. Nada foi sondado ao
vivo: todos os testes são offline (servidor local sobre o transporte real, ou instrumento falso).

## O que mudou

| Arquivo | Mudança |
|---|---|
| `docs/decisoes/0071-robots-rfc-9309-na-s0.md` | contexto (rodada 1), regra, instrumento, lacunas resolvidas por conservadorismo e consequências; substitui a regra conservadora de 28/10/2026 |
| `freoa_verifica/robots_s0.py` | módulo puro: `ler_robots(status, content_type, corpo)`, `ler_do_registro(registro, corpo)`, `LeituraRobots.decidir(url)` com ação `seguir`, `vedado`, `sem_restricoes` ou `barreira` e motivo; `MIMES_ROBOTS` |
| `freoa_verifica/captura.py` | robots: MIMEs largos, um pedido, `max_redirects=0`, detecção de desafio do transporte desligada (quem decide é `robots_s0`); robots só como sonda e nunca fixture; toda recusa de transporte registra subclasse, mensagem curta, Content-Type recebido e saltos |
| `scripts/s0_orquestrar.py` | orquestrador oficial (substitui `s0_runner.py` da rodada 1): saída por argumento, um pedido por URL, robots uma vez por host, barreira anterior por arquivo, reaproveita evidência já gravada, nenhuma repetição |
| `docs/S0-SONDAS.md` | tabela de parada substituída pela regra da 0071; seção "Rodada 2 (S0b)" |
| `docs/auditoria/1.4.0/s0b-rodada2/{hosts,barreiras}.json` | entradas do orquestrador para a rodada 2 (nove hosts a resondar; quatro hosts com barreira, fora) |
| `tests/test_robots_s0.py`, `tests/test_s0_orquestrar.py` | testes novos (abaixo) |
| `tests/test_sondas.py`, `tests/test_captura_instrumento.py` | quatro asserções de "robots só `text/plain`" trocadas por `MIMES_ROBOTS` |

`freoa_verifica/transport.py` não foi tocado (D5).

## Regra implementada

| Resposta | Leitura |
|---|---|
| 200 com grupo `User-agent` e só diretivas conhecidas | `regras`: `Disallow` aplicável veda o caminho (`vedado`); senão `seguir` |
| 200 sem regras interpretáveis (HTML, outro MIME, vazio, só comentários) | `sem_restricoes`, com Content-Type e sha256 |
| 404, 410 | `sem_restricoes` |
| 401, 403, 429, desafio, 5xx, timeout, erro de transporte, redirecionamento | `barreira` |
| outros 4xx | `barreira` (conservadorismo) |

## Pontos que a especificação não cobria (resolvidos por conservadorismo; a confirmar pelo titular)

1. **200 recusado pelo transporte** (sem Content-Type, ou MIME fora de `MIMES_ROBOTS`): o transporte congelado não lê o
   corpo, então não há como afirmar "sem regras". Vira barreira (`content_type_ausente`, `resposta_200_recusada`), com a
   evidência nova. Se a causa das seis recusas da rodada 1 foi Content-Type ausente, a rodada 2 as repete como barreira;
   a evidência nova diz qual foi a causa. Resolver isso exige mudar o transporte (fora do escopo) ou decisão do titular.
2. **200 com `Allow`/`Disallow` não interpretável** (sem `User-agent`, ou com linhas desconhecidas, e não HTML): barreira
   `regras_ambiguas`, em vez de "sem restrições".
3. **200 vazio**: o transporte o recusa (`EmptyBody`, `corpo_vazio`); tratado como "sem restrições" com o sha256 do vazio.
4. **Redirecionamento**: o transporte não expõe o `Location`; mesmo host e outro host não se distinguem. Ambos são
   barreira (como a regra manda); a evidência traz a exceção (`BlockedHost`) e o status 3xx dos saltos.
5. **`urllib.robotparser`** muda entre versões (no 3.13.18 trata curingas e precedência; no 3.11.18 não). A decisão por
   caminho veda se o `robotparser` ou o avaliador RFC 9309 do módulo vedar (soma de restrições; nunca libera mais).
6. Diretivas não padronizadas comuns (`Host`, `Request-rate`, `Clean-param`, `Noindex`...) contam como conhecidas.

## Correção do supervisor (28/10/2026): desafio no robots

Fora de `text/plain`, corpo 200 com marcador de desafio do projeto é barreira `desafio_no_robots` (antes de concluir
"sem regras", e mesmo com linhas de regra); em `text/plain`, regras interpretáveis são obedecidas
(`Disallow: /captcha/` veda `/captcha/`). A detecção do transporte continua desligada para o robots em todos os MIMEs:
ligá-la só fora de `text/plain` não é possível, porque o Content-Type só se conhece depois do único pedido e o
transporte decide a detecção antes dele. O efeito pedido é obtido por `robots_s0`, com a lista de marcadores de
`connectors.challenge`, sem duplicá-la. Testes: HTML e outros MIMEs com página de CAPTCHA, `text/plain` com
`Disallow: /captcha/`, HTML sem marcador.

## Testes

- `tests/test_robots_s0.py` (103): tabela completa por status e MIME (404, 410, 401, 403, 429, 5xx, outros 4xx, 3xx,
  200 com regras, 200 HTML, octet-stream, JSON, vazio, só comentário), robots arbitrário, desafio no corpo e `Disallow:
  /captcha/` que não é desafio, BOM e charset, registro `.captura.json` mapeado pela regra; ponta a ponta com o
  transporte real sobre servidor local (um único pedido, inclusive em 503; 302 para mesmo host e para outro host;
  200 sem Content-Type e com MIME fora da lista; evidência com Content-Type e subclasse; `Set-Cookie`,
  `Authorization` e `Cookie` ausentes do registro); timeout e erro de transporte; robots só como sonda e nunca
  fixture; estrutural: serviço, MCP e CLI `fv` não importam `robots_s0` nem `captura` (fecho de importações por AST
  e em execução), e só `captura.py` e `scripts/s0_orquestrar.py` o importam.
- `tests/test_s0_orquestrar.py` (14): instrumento falso; um pedido por URL; robots uma vez por host; regra por host
  (404 e HTML 200 seguem, 403 para); barreira anterior vinda de arquivo e sem pedido; nenhuma repetição após barreira
  ou erro; segunda execução reaproveita a evidência; `--somente-robots` e filtro de hosts; relatório sem caminho de
  máquina; roteiro oficial; rodada 2 pede exatamente os nove robots.

## Verificação

| Verificação | Resultado |
|---|---|
| Suíte completa `pytest -m "not live"`, Python 3.13.18, Linux | 7273 passed, 9 skipped, 34 deselected (990 s) antes da correção do supervisor e do rebase; depois: ver abaixo. A primeira execução teve 2 falhas em `test_selecao_wheel` (o módulo de teste do orquestrador abria `scripts/` na coleta); corrigido por carga sob demanda e a suíte repetida inteira |
| Arquivos tocados e vizinhos, Python 3.11.18, Linux (`test_robots_s0`, `test_s0_orquestrar`, `test_sondas`, `test_captura_instrumento`, `test_captura`, `test_garantias_estruturais`, `test_challenge`, `test_categorias_indisponibilidade`) | 412 passed |
| `test_selecao_wheel` + testes novos, 3.13 e 3.11 | 122 passed em cada |
| Ruff (`scripts/ruff_catraca.py`), `git diff --check` | sem achado novo; sem erro de espaço |
| Testes novos | 117 (103 em `test_robots_s0`, 14 em `test_s0_orquestrar`); 4 asserções antigas ajustadas |

Não verificado: Python 3.12 e 3.14 e Windows (o CI roda 3.11 a 3.14 em Linux e Windows). O código não usa nada
específico de plataforma além de `PureWindowsPath` para o nome da pasta de saída do roteiro.

Depois da correção do supervisor e do rebase sobre `origin/main` (`624f8a9`): suíte completa em Python 3.13.18,
7602 passed, 9 skipped, 34 deselected (983 s); arquivos tocados e vizinhos em 3.11.18, 417 passed; Ruff
(`scripts/ruff_catraca.py`) e `git diff --check` sem achado.
