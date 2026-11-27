# Release 1.4.0a8 - decisão 0093 (User-Agent de outra versão nos recibos; bloqueios do parser)

Executor: supervisor (Opus), ambiente Linux de nuvem da sessão, 27/11/2026. Procedimento: `docs/RELEASE.md`.
Autorização do titular (27/11/2026): "a8 com (a) e (b), 1 rodada Codex".

## Origem

Depois da instalação da 1.4.0a7 no home real, a manutenção agendada falhou em todas as obras
(`persistencia_local_falhou`). Diagnóstico local, sem rede: `estado_invalido:politica_recibo_incoerente`, porque o
recibo vigente do robots.txt do normas.leg.br registrava `freoa-verifica/1.4.0a6 (+…)`. Paliativo no home real,
autorizado pelo titular: `fv acervo abrir-normas-leg --decisao "0091-A, titular, 24/11/2026"` (descarte da política),
seguido de revalidação de duas obras com `status: ok` e nova política com o User-Agent da 1.4.0a7. Ver decisão 0093.

## Snapshot e S4

| Etapa | Saída |
|---|---|
| Pacote 1.4.0a8 construído com `requirements/build.lock`, instalado em venv limpo com `requirements/ci.lock` | `freoa-verifica 1.4.0a8` |
| Candidato: snapshot oficial da 1.4.0a7 (sha256 `9d51baf7…be54e`) instalado em home vazio, experimental | 0; 826 obras, 2.069 capturas, derivados 6 |
| S4 no candidato (`--estrito --gravar-manifesto manifesto-1.4.0a8.json`) | 0; manifesto igual ao da 1.4.0a7, salvo data e versão |
| Exportação `--arquivo-unico` | 0 |

Snapshot `freoa-verifica-snapshot-20261127-1.4.0a8.tar.gz`, 666.511.458 bytes, sha256
`e8bb209f1029ff4c7715b53ad48a14d9c3c4212eb66a88230ec5a13f23395bef`, `derived_version` 6. Mesmo acervo da 1.4.0a7.

## Auditoria, CI e publicação

| Etapa | Saída |
|---|---|
| Pacote com o digest: instalação vinculada em home vazio, S4 pós-instalação, `doctor --offline` | 0 (`vinculado: True`), 0, 0 |
