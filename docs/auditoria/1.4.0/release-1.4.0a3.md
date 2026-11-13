# Release 1.4.0a3 - geração do snapshot, bateria S4 e instalação vinculada

Executor: supervisor (Opus), notebook Windows do titular, 13/11/2026 (horário de Brasília). Procedimento: `docs/RELEASE.md`, passos 2 e 3, idêntico ao da 1.4.0a2 (`release-1.4.0a2.md`). Scripts: `C:\dev\fv14-rel\release-a3-parte1.ps1` e `-parte2.ps1`; registros em `C:\dev\fv14-rel\a3\`.

Conteúdo da pré-release: correções do IL.1 ao IL.3-c (decisões 0080 a 0083), sem a Porta L (decisão 0084). Matriz por rota `nao_apurada`; nenhum rótulo de substituição.

## Snapshot e S4

| Etapa | Comando (resumo) | Saída |
|---|---|---|
| Pacote | `pip install --require-hashes -r requirements/ci.lock` + `pip install --no-deps .` em venv limpo; parte 1 sobre `edb11c1` com a mudança de versão ainda não commitada (commitada em `43fad71`, sem diferença de código) | `freoa-verifica 1.4.0a3` |
| Candidato | cópia (`robocopy /MIR`) do candidato da 1.4.0a2; original intacto | código 1 = arquivos copiados |
| S4 no candidato | `fv acervo conferir --home <candidato> --estrito --gravar-manifesto manifesto-1.4.0a3.json` | 0 |
| Exportação | `fv --home <candidato> snapshot export --arquivo-unico --saida freoa-verifica-snapshot-20261113-1.4.0a3.tar.gz` | 0; 2.069 capturas; `blobs_completos: True` |
| Instalação experimental | `fv --home <vazio> snapshot install --arquivo ... --aceitar-nao-vinculado` | 0 |
| S4 pós-instalação | `fv acervo conferir --home <instalado> --manifesto manifesto-1.4.0a3.json --pos-instalacao --estrito` | 0 |
| Doctor | `fv --home <instalado> doctor --offline` | 0 |

Snapshot: `freoa-verifica-snapshot-20261113-1.4.0a3.tar.gz`, 665.629.516 bytes, sha256 `0c35475f52fd284c54c0083df97ef55781b24d448d8d91c239b45c641f37ea32` (igual ao `.sha256` externo e ao `asset_sha256` do export). Gravado em `freoa_verifica/data/snapshots-oficiais.json` com `versao_pacote_min` 1.4.0a3 e `derived_version` 5 (commit `111db98`). O acervo não muda em relação à 1.4.0a2 (mesmas 2.069 capturas); a rota Câmara não entra no snapshot.

Instalação vinculada (passo 3), pacote reinstalado de `111db98` (árvore limpa): `snapshot install --arquivo ...` sem `--aceitar-nao-vinculado` → 0, `vinculado: True`; S4 pós-instalação → 0; `doctor --offline` → 0.

## Publicação

Registrada abaixo, na ordem do `RELEASE.md` (passos 4 a 8).
