# Release 1.4.0a9 - decisão 0094 (achados do colega sobre a 1.4.0a6)

Executor: supervisor (Opus), ambiente Linux de nuvem da sessão, 27/11/2026. Procedimento: `docs/RELEASE.md`.
Autorização do titular (27/11/2026): corrigir os achados do colega na 1.4.0a9, depois da 1.4.0a8, a partir do
relatório; três rodadas do Codex (D5).

## Snapshot e S4

| Etapa | Saída |
|---|---|
| Pacote 1.4.0a9 construído com `requirements/build.lock`, instalado em venv limpo com `requirements/ci.lock` | `freoa-verifica 1.4.0a9` |
| Candidato: snapshot oficial da 1.4.0a8 (sha256 `e8bb209f…5bef`) instalado em home vazio, experimental | 0; 826 obras, 2.069 capturas |
| `fv acervo reconstruir` (derivados 6 para 7; parser 1.2.5 final, `900edd5`), em candidato novo a partir do snapshot da 1.4.0a8 | 0; 843 documentos reprocessados |
| Marcas novas no acervo | `NOTA_EDITORIAL_TRUNCADA`: 2 na CF; nenhuma `REDACAO_VIVA_VAZIA` (a Lei 6.404 do acervo não tem o markup da fixture). A marca de rótulo saiu (decisão 0095) |
| S4 no candidato (`--estrito --gravar-manifesto manifesto-1.4.0a9.json`) | 0; difere do da 1.4.0a8 só em `derived_version` |
| Exportação `--arquivo-unico` | 0 |
| Pacote com o digest: instalação vinculada em home vazio, S4 pós-instalação, `doctor --offline` | 0 (`vinculado: True`), 0, 0 |

Snapshot `freoa-verifica-snapshot-20261127-1.4.0a9.tar.gz`, 666.988.193 bytes, sha256
`22a0320b1196f1ef81381039e75b8012b937346e774e1f64423ce79368d158ea`, `derived_version` 7.

A reconstrução sobre o candidato já reconstruído com parsers de desenvolvimento (também rotulados 1.2.5) foi recusada
pela regra da 0065 (mesma versão de parser, modelo diferente numa captura legada conferida): a regra funcionou; o
candidato foi refeito do snapshot da 1.4.0a8. Nenhum home de usuário tem modelos dessas versões intermediárias.

## Auditoria, CI e publicação

| Etapa | Saída |
|---|---|
| Codex r1 sobre `83bea38` | BLOQUEADOR, 6 achados, corrigidos em `95d7797` (ver decisão 0094) |
| Conferência das marcas no acervo reconstruído | ruído ("X:", "D a Isenção", texto repetido) eliminado em `9cdd149`; o filtro de texto repetido derrubava 5 marcas verdadeiras da CF (texto igual em outro artigo) e foi restrito ao mesmo artigo em `6f5869d` |
| Codex r2 sobre `95d7797` | BLOQUEADOR (conclusão extraída do log; sessão encerrada por engano do supervisor), 3 escapes do rótulo, corrigidos em `91355b3` |
| Codex r3 sobre `91355b3` | BLOQUEADOR, 4 achados do rótulo; titular: correção conservadora e rodada 4 restrita (`c66d5b9`) |
| Codex r4 (restrita) sobre `c66d5b9` | BLOQUEADOR, 4 contornos do rótulo; titular: marca de rótulo sai da 1.4.0a9 (decisão 0095) |
| CI do PR #59 em `3d15c22` | 11/11 verdes |
| Merge do PR #59 | `8124e1c` (merge commit), depois da publicação da 1.4.0a8 |
| Tag anotada `v1.4.0a9` | criada e empurrada pelo notebook do titular |
| `release.yml` (run 46089755264) | verde (Windows 3.13 em cerca de 5h30, dentro do limite de 6 h do job); rascunho com wheel, sdist, `requirements-lock.txt` e `SHA256SUMS` |
| `sha256sum -c SHA256SUMS` no rascunho baixado | OK nos três arquivos |
| `gh attestation verify` | wheel e sdist: `release.yml@refs/tags/v1.4.0a9`, commit `8124e1c` |
| Wheel sem `tests/`; digest em `snapshots-oficiais.json` da wheel | 0 entradas; `22a0320b…58ea`, `versao_pacote_min` 1.4.0a9, derived 7 |
| Wheel baixada em venv limpo com o lock da release (`--require-hashes`); snapshot instalado; S4 estrito; `doctor --offline` | `vinculado: True`; 0; 0. Uma primeira execução do doctor sem `--offline` fez as verificações de saúde em rede e acusou `fonte:planalto` `acervo_legado_sem_nova_captura`; não integra o rito e foi refeita offline |
| Anexo do snapshot e do `.sha256` | pelo notebook do titular (`gh release upload`); asset baixado de volta: sha256 `22a0320b1196f1ef81381039e75b8012b937346e774e1f64423ce79368d158ea` |
| Publicação (`draft=false`, `prerelease=false`) | pelo titular, 28/11/2026 11h52 UTC |
| `pypi.yml` (run 46141899255) | verde; PyPI com wheel `ffa1a027…` e sdist `7f911dfc…`, iguais ao `SHA256SUMS` |
