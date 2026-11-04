# Release 1.4.0a2 - geração do snapshot, bateria S4 e condição (c) da decisão 0076

Executor: supervisor (Opus), notebook Windows do titular, 04/11/2026 (horário de Brasília). Procedimento: `docs/RELEASE.md`, passos 2 e 3, idêntico ao da 1.4.0a1 (`release-1.4.0a1.md`). Arquivos em `release-1.4.0a2/` (caminhos de máquina substituídos por `<rel>` e `<home>`).

Conteúdo da pré-release: IL.0-R (fronteira com o FREOA e estado com data referido a D, decisão 0075), com a correção do C8 incorporada por exceção ao teto do D5 (decisão 0076).

## Condição (c) da decisão 0076

Migração sobre CÓPIA do home 1.4.0a1 instalado (home real intocado), com o código de `d2f3b7b`: esquema 16 → 17; 15 registros preservados; amostra de cinco registros antigos devolvida como legado (`integridade.confere: null`), sem exceção; registro novo com MAC conferido; `doctor --offline` com código 0. Registro: `release-1.4.0a2/0076-condicao-c-migracao-copia.log`. As condições (a) (CI verde nas oito combinações em `d2f3b7b`) e (b) (decisão registrada) foram cumpridas antes desta etapa.

## Snapshot e S4

| Etapa | Comando (resumo) | Saída |
|---|---|---|
| Pacote | `pip install --require-hashes -r requirements/ci.lock` + `pip install --no-deps .` em venv limpo, sobre `23c0c0a` | `freoa-verifica 1.4.0a2` |
| Candidato | cópia (`robocopy /MIR`) do candidato da 1.4.0a1; original intacto | código 1 = arquivos copiados |
| S4 no candidato | `fv acervo conferir --home <candidato> --estrito --gravar-manifesto manifesto-1.4.0a2.json` | 0 |
| Exportação | `fv --home <candidato> snapshot export --arquivo-unico --saida freoa-verifica-snapshot-20261104-1.4.0a2.tar.gz` | 0; 2.069 capturas; `blobs_completos: True` |
| Instalação experimental | `fv --home <vazio> snapshot install --arquivo ... --aceitar-nao-vinculado` | 0 |
| S4 pós-instalação | `fv acervo conferir --home <instalado> --manifesto manifesto-1.4.0a2.json --pos-instalacao --estrito` | 0 |
| Doctor | `fv --home <instalado> doctor --offline` | 0 |

Snapshot: `freoa-verifica-snapshot-20261104-1.4.0a2.tar.gz`, 665.630.616 bytes, sha256 `8e2ad821ae78ace4b61a4a0957ac73ffb4ce4ba48408d7bd05efbec5f0bfff9e` (igual ao `.sha256` externo e ao `asset_sha256` do export). Gravado em `freoa_verifica/data/snapshots-oficiais.json` com `versao_pacote_min` 1.4.0a2 e `derived_version` 5 (commit `4ae0b34`). O acervo não muda em relação à 1.4.0a1 (mesmas 2.069 capturas); muda o pacote e o esquema (migração 017).

Instalação vinculada (passo 3), pacote reinstalado de `4ae0b34`: `fv --home <vazio> snapshot install --arquivo ...` sem `--aceitar-nao-vinculado` → 0, `vinculado: True`; S4 pós-instalação contra o mesmo manifesto → 0; `doctor --offline` → 0.

Próximo: auditoria do delta de release (Codex), CI nas oito combinações, merge, tag `v1.4.0a2`, rascunho, auditoria dos bytes da CI, anexação do snapshot, publicação, PyPI, instalação oficial.
