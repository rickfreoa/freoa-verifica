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

Instalação vinculada (passo 3 do RELEASE), 06:26–06:29, pacote reinstalado de `62c0df7` (com o digest):
`fv --home <vazio> snapshot install --arquivo ...` sem `--aceitar-nao-vinculado` → 0, `vinculado: true`,
`snapshot_derived_version: 5`; S4 pós-instalação contra o mesmo manifesto → 0; `doctor --offline` → 0.

Bench sobre a instalação vinculada (passo 2 do RELEASE; faltava na rodada 1 do PR #16), 06:58–06:59, pacote de
`62c0df7`, `FV_HOME` no home vinculado, `scripts/comparativo_ouro.py` com o conjunto-ouro de 44 casos
(`release-1.4.0a1/bench-freoa_raw.jsonl`): 44 de 44 iguais à linha de base da 1.3.0
(`bench-1.3.0/freoa_raw.jsonl`) na projeção do I1.4 (status, identidade e situação; status e top-5). Tempo por
consulta: p50 0,7 s; p95 8,8 s; máximo 11,9 s. O código de consulta não mudou entre as versões; a queda dos
tempos frente à medição de 27/10 (p95 21,1 s) é atribuída à rede e às fontes no momento, não a melhoria do
produto, e não altera o risco registrado para o piso do D4.

Registros da instalação vinculada: `install-vinc.log`, `conferir-vinc.log`, `doctor-vinc.log`, `vinculado.txt`.

Próximo: auditoria independente do commit (manifesto, instalador, digest, código), CI nas oito combinações, merge,
tag `v1.4.0a1` e auditoria dos bytes da CI (passos 4 a 6).
