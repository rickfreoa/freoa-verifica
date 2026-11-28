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
| Auditoria Codex de `d7ad8d4` (uma rodada, só leitura) | APROVADO COM RESSALVAS: liberação alcançava bloqueios posteriores à correção; regex aceitava dígitos Unicode. Corrigidos com teste (decisão 0093). O snapshot não muda; a wheel muda e é refeita pelo `release.yml` |
| CI do PR #58 em `ef602b3` | 11/11 verdes |
| Merge do PR #58 | `6edc822` (merge commit) |
| Tag anotada `v1.4.0a8` | criada e empurrada pelo notebook do titular |
| `release.yml` (run 46034451920) | verde; rascunho com wheel, sdist, `requirements-lock.txt` e `SHA256SUMS` |
| `sha256sum -c SHA256SUMS` no rascunho baixado | OK nos três arquivos |
| `gh attestation verify` | wheel e sdist: 1 attestation cada, `release.yml@refs/tags/v1.4.0a8` |
| Wheel sem `tests/`; digest em `snapshots-oficiais.json` da wheel | 0 entradas; `e8bb209f…5bef`, `versao_pacote_min` 1.4.0a8, derived 6 |
| Wheel baixada em venv limpo com o lock da release (`--require-hashes`); snapshot instalado; S4 estrito; `doctor --offline` | `vinculado: True`; 0; 0 |
| Anexo do snapshot e do `.sha256` | pelo notebook do titular (`gh release upload`); asset baixado de volta: sha256 `e8bb209f1029ff4c7715b53ad48a14d9c3c4212eb66a88230ec5a13f23395bef` |
| Publicação (`draft=false`, `prerelease=false`) | pelo titular, 28/11/2026 00h44 UTC |
| `pypi.yml` (run 46089477446) | verde; PyPI com wheel `07f7d0eb…` e sdist `43d082bc…`, iguais ao `SHA256SUMS` |
