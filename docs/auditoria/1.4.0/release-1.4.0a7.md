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

## Teste em Debian e correções antes do merge

O colega testou o ramo em `c2e4d83` num Debian 13 limpo, como usuário comum: o timer foi criado e a manutenção
renovou obras. Os seis achados foram corrigidos em `212fbf2`; a leitura do Codex sobre esse commit trouxe cinco
achados, corrigidos em `f0b6a59` (conferência do Codex: APROVADO). Detalhes na decisão 0092. O snapshot não mudou.

## Auditoria, CI e publicação

| Etapa | Saída |
|---|---|
| CI em `f0b6a59` (run 45887396811) | 12 falhas só no Linux: fixtures agendavam um `fv` em `/opt`, gravável por terceiros nos runners, e o guarda `caminho_inseguro` recusava. Reproduzido localmente com `/opt` o+w; corrigido em `9bab510` (executável sob `tmp_path`) |
| CI do PR #56 em `9bab510` (run 45908506542) | 11/11 verdes |
| Merge do PR #56 | `5d7e1ca` (merge commit) |
| Tag anotada `v1.4.0a7` | criada e empurrada pelo notebook do titular |
| `release.yml` (run 45939648247) | verde; rascunho com wheel, sdist, `requirements-lock.txt` e `SHA256SUMS` |
| `sha256sum -c SHA256SUMS` no rascunho baixado | OK nos três arquivos |
| Wheel sem `tests/`; digest em `snapshots-oficiais.json` da wheel | 0 entradas `tests/`; `9d51baf7…be54e`, `versao_pacote_min` 1.4.0a7, derived 6 |
| `gh attestation verify` | wheel e sdist: 1 attestation cada; `requirements-lock.txt`: 8 (mesmo conteúdo em releases anteriores); todas `release.yml@refs/tags/v1.4.0a7` na primeira entrada |
| Wheel baixada em venv limpo com o lock da release (`--require-hashes`); snapshot instalado; S4 estrito; `doctor --offline` | `vinculado: True`; 0; 0 |
| Anexo do snapshot e do `.sha256` | pelo notebook do titular (`gh release upload`) |
| Asset publicado baixado de volta | sha256 `9d51baf7e928586752e4846479b195e75cc6259b5aa95fdd9c32d34792fbe54e`, 666.512.443 bytes |
| Publicação (`draft=false`, `prerelease=false`) | pelo titular, 27/11/2026 10h08 UTC |
| `pypi.yml` (run 45979537856) | verde; PyPI com wheel `f0bd7518…` e sdist `89d17a0e…`, iguais ao `SHA256SUMS` |
| Home real do titular (Windows), pelo instalador da tag (`instalar-freoa-verifica.ps1`, sha256 `b3f13c63…de4`, sem elevação) | concluído sem intervenção: etapa "instalar wheel" passou (era a que caía na 1.4.0a6); `attestation_verificada: true`; snapshot `9d51baf7…be54e` anexado ao acervo vinculado; `doctor` ok; tarefa "FREOA Verifica - manter acervo" reinstalada (05:43, a cada 2 h e ao voltar) |

## Para quem tem a 1.4.0a6

O acervo é o mesmo; basta atualizar o pacote. O instalador oficial agenda a manutenção (`-SemAgendamento` /
`--sem-agendamento` dispensam). Em Linux com systemd, sem lingering o timer de usuário só roda com sessão aberta; o
agendador avisa o comando `loginctl enable-linger` quando a política do sistema não permite ligá-lo.
