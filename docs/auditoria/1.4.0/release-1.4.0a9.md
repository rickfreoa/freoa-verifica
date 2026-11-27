# Release 1.4.0a9 - decisão 0094 (achados do colega sobre a 1.4.0a6)

Executor: supervisor (Opus), ambiente Linux de nuvem da sessão, 27/11/2026. Procedimento: `docs/RELEASE.md`.
Autorização do titular (27/11/2026): corrigir os achados do colega na 1.4.0a9, depois da 1.4.0a8, a partir do
relatório; três rodadas do Codex (D5).

## Snapshot e S4

| Etapa | Saída |
|---|---|
| Pacote 1.4.0a9 construído com `requirements/build.lock`, instalado em venv limpo com `requirements/ci.lock` | `freoa-verifica 1.4.0a9` |
| Candidato: snapshot oficial da 1.4.0a8 (sha256 `e8bb209f…5bef`) instalado em home vazio, experimental | 0; 826 obras, 2.069 capturas |
| `fv acervo reconstruir` (derivados 6 para 7; parser 1.2.5) | 0; 843 documentos reprocessados |
| Marcas novas no acervo | `ROTULO_SEM_SEPARADOR`: 66 na CF (a contagem do colega), 3 no DL 1.978, 3 na Lei 4.728, 1 na IN BCB 733, 1 na Lei 6.404, 1 na Lei 8.668; `NOTA_EDITORIAL_TRUNCADA`: 2 na CF |
| S4 no candidato (`--estrito --gravar-manifesto manifesto-1.4.0a9.json`) | 0; difere do da 1.4.0a8 só em `derived_version` |
| Exportação `--arquivo-unico` | 0 |
| Pacote com o digest: instalação vinculada em home vazio, S4 pós-instalação, `doctor --offline` | 0 (`vinculado: True`), 0, 0 |

Snapshot `freoa-verifica-snapshot-20261127-1.4.0a9.tar.gz`, 668.023.455 bytes, sha256
`9f041f37d0b3cb5a0aa25f6d8fa1d68bf52a93cd13c245cd963c3f67ad31f745`, `derived_version` 7.

## Auditoria, CI e publicação

| Etapa | Saída |
|---|---|
| Codex r1 sobre `83bea38` | BLOQUEADOR, 6 achados, corrigidos em `95d7797` (ver decisão 0094) |
| Conferência das marcas no acervo reconstruído | ruído ("X:", "D a Isenção", texto repetido) eliminado em `9cdd149`; o filtro de texto repetido derrubava 5 marcas verdadeiras da CF (texto igual em outro artigo) e foi restrito ao mesmo artigo em `6f5869d` |
