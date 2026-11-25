# Release 1.4.0a6 - decisão 0091 (Constituição, parser de fontes órfãs, renovação do acervo)

Executor: supervisor (Opus), ambiente Linux de nuvem da sessão, 25/11/2026. Procedimento: `docs/RELEASE.md`.
Autorização do titular: "pode incorporar. pode publicar." (25/11/2026), depois de CI verde no `def6bc7`.

Conteúdo funcional: decisão 0091 e emenda A (PR #54), com as rodadas de auditoria r1 a r7 e as decisões do titular
registradas na própria 0091. A r7 terminou BLOQUEADOR por resíduos de classes já decididas; o titular encerrou as
rodadas com guarda territorial no texto inteiro e resíduos 25 e 28 do parser declarados.

## Snapshot e S4

| Etapa | Saída |
|---|---|
| Pacote 1.4.0a6 construído com `requirements/build.lock`, instalado em venv limpo com `requirements/ci.lock` | `freoa-verifica 1.4.0a6` |
| Candidato: snapshot oficial da 1.4.0a5 (sha256 `ae728d50…f232`) instalado em home vazio, derivados reconstruídos para 6 | 0; 826 obras, 2.069 capturas |
| Modelos do Planalto no candidato | 544 com parser 1.2.4 |
| S4 no candidato (`--estrito --gravar-manifesto manifesto-1.4.0a6.json`), 2.069 blobs conferidos | 0 |
| Exportação `--arquivo-unico` | 0; 2.069 capturas; `blobs_completos: True` |
| Instalação experimental, S4 pós-instalação, `doctor --offline` | 0, 0, 0 |
| Pacote com o digest (`6071d83`): instalação vinculada em home vazio, S4, `doctor --offline` | 0 (`vinculado: True`), 0, 0 |
| Smoke `fv verifica "art. 116 da Lei 6.404/1976"` no home vinculado | `verified` / `OBRA_E_CAMINHO_OK` |

Snapshot `freoa-verifica-snapshot-20261125-1.4.0a6.tar.gz`, 666.512.068 bytes, sha256
`4320cac27d311dc984debe441e7bf0371e348acb5e0a349621c09a608eb836ac`, `derived_version` 6. Acervo igual ao da
1.4.0a5 (mesmas capturas), com derivados e modelos reprocessados pela 1.4.0a6.

## Auditoria, CI e publicação

(preenchido ao longo da publicação)
