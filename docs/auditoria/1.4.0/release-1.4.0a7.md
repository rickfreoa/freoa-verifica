# Release 1.4.0a7 - decisão 0092 (instaladores agendam a manutenção do acervo)

Executor: supervisor (Opus), ambiente Linux de nuvem da sessão, 26/11/2026. Procedimento: `docs/RELEASE.md`.
Autorização do titular (26/11/2026): merge depois da CI e release 1.4.0a7, sem nova rodada do Codex (três rodadas
BLOQUEADOR em endurecimento contra outro usuário local, todas corrigidas; ver decisão 0092).

## Snapshot e S4

| Etapa | Saída |
|---|---|
| Pacote 1.4.0a7 construído com `requirements/build.lock`, instalado em venv limpo com `requirements/ci.lock` | `freoa-verifica 1.4.0a7` |
| Candidato: snapshot oficial da 1.4.0a6 (sha256 `4320cac2…36ac`) instalado em home vazio (derivados 6, sem reconstrução) | 0 |
| S4 no candidato (`--estrito --gravar-manifesto manifesto-1.4.0a7.json`) | 0 |
| Exportação `--arquivo-unico` | 0 |
| Pacote com o digest (`3a70f23`): instalação vinculada em home vazio, S4 pós-instalação, `doctor --offline` | 0 (`vinculado: True`), 0, 0 |

Snapshot `freoa-verifica-snapshot-20261126-1.4.0a7.tar.gz`, 666.512.443 bytes, sha256
`9d51baf7e928586752e4846479b195e75cc6259b5aa95fdd9c32d34792fbe54e`, `derived_version` 6. Mesmo acervo da 1.4.0a6.

## Auditoria, CI e publicação

(preenchido ao longo da publicação)
