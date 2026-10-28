# Release 1.4.0a1 — geração do snapshot e bateria S4

Executor: supervisor (Opus), notebook Windows do titular, 28/10/2026 06:09–06:14 (horário de Brasília).
Procedimento: `docs/RELEASE.md`, passos 2 e 3, idêntico ao da 1.3.0 (`fv-130/snapshot2`), com o pacote 1.4.0a1.
Arquivos em `release-1.4.0a1/` (caminhos de máquina substituídos por `<rel>`).

| Etapa | Comando (resumo) | Saída |
|---|---|---|
| Pacote | `pip install --require-hashes -r requirements/ci.lock` + `pip install --no-deps .` em venv limpo, sobre `c2cf3e2` | `freoa-verifica 1.4.0a1` |
| Candidato | cópia (`robocopy /MIR`) do corpus produtor da 1.3.0 (`fv-build-130`); original intacto | código 1 = arquivos copiados |
| S4 no candidato | `fv acervo conferir --home <candidato> --estrito --gravar-manifesto manifesto-1.4.0a1.json` (sem recorte, como na 1.3.0) | 0 |
| Exportação | `fv --home <candidato> snapshot export --arquivo-unico --saida freoa-verifica-snapshot-20261028-1.4.0a1.tar.gz` | 0; 2.069 capturas; `blobs_completos: True` |
| Instalação experimental | `fv --home <vazio> snapshot install --arquivo ... --aceitar-nao-vinculado` | 0 |
| S4 pós-instalação | `fv acervo conferir --home <instalado> --manifesto manifesto-1.4.0a1.json --pos-instalacao --estrito` | 0 (`sync_state` vazio) |
| Doctor | `fv --home <instalado> doctor --offline` | 0 |

Snapshot: `freoa-verifica-snapshot-20261028-1.4.0a1.tar.gz`, 665.622.520 bytes,
sha256 `ad090c341b5e95c606309bff84ef9a233e144d223bcb5c6a40a9076dc3d8fafa` (igual ao `.sha256` externo e ao
`asset_sha256` do export). Gravado em `freoa_verifica/data/snapshots-oficiais.json` com
`versao_pacote_min` 1.4.0a1 e `derived_version` 5.

Conteúdo: o `conteudo` e a `origem` do manifesto congelado são idênticos aos do manifesto S4 da 1.3.0
(`recorte-1.3.0.json`): 826 obras, 44.780 decisões, `derived_version` 5. A 1.4.0a1 não muda o acervo; muda o
pacote (os bytes do snapshot diferem pelo manifesto de exportação, que registra a versão).

Pendente nesta fase (passo 3 do RELEASE): repetir a instalação, agora vinculada, em home vazio, com o pacote que
contém o digest; depois, auditoria independente do commit.
