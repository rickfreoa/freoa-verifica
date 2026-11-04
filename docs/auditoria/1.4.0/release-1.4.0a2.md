# Release 1.4.0a2 - geração do snapshot, bateria S4 e condição (c) da decisão 0076

Executor: supervisor (Opus), notebook Windows do titular, 04/11/2026 (horário de Brasília). Procedimento: `docs/RELEASE.md`, passos 2 e 3, idêntico ao da 1.4.0a1 (`release-1.4.0a1.md`). Arquivos em `release-1.4.0a2/`: registros como `.txt` em UTF-8 (o `.gitignore` exclui `*.log`), decodificados da origem (UTF-16 ou UTF-8) e sanitizados depois da decodificação (caminhos de máquina substituídos por `<rel>`, `<repo>`, `<supervisor>` e `<home>`), mais os scripts executados (`*.ps1.txt`, `*.py.txt`). Correção da r1 da auditoria do delta de release: a primeira versão do registro omitia os `.log` e corrompia os arquivos UTF-16.

Conteúdo da pré-release: IL.0-R (fronteira com o FREOA e estado com data referido a D, decisão 0075), com a correção do C8 incorporada por exceção ao teto do D5 (decisão 0076).

## Condição (c) da decisão 0076

Migração sobre CÓPIA do home 1.4.0a1 instalado (home real intocado), com o código de `d2f3b7b`: esquema 16 → 17; 15 registros preservados; amostra de cinco registros antigos devolvida como legado (`integridade.confere: null`), sem exceção; registro novo com MAC conferido; `doctor --offline` com código 0. Registro: `release-1.4.0a2/0076-condicao-c-migracao-copia.txt` (script em `0076-condicao-c-migracao-copia.ps1.txt` e `.py.txt`). As condições (a) (CI verde nas oito combinações em `d2f3b7b`) e (b) (decisão registrada) foram cumpridas antes desta etapa.

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

## Bench (passo 2 do RELEASE)

Pacote 1.4.0a2 do venv da release, `FV_HOME` no home vinculado, `scripts/comparativo_ouro.py` com o conjunto-ouro de 44 casos (`docs/auditoria/comparativo-120/gold.jsonl`), consulta ao vivo onde o produto consulta: código 0 (`bench-etapas.txt`, `bench-freoa_raw.jsonl`). Comparação com o bench da 1.4.0a1 (`release-1.4.0a1/bench-freoa_raw.jsonl`) na projeção do I1.4 (`comparar-bench.py.txt`: status, identidade e temporal das verificações; status e top-5 das buscas, identificando o julgado por tribunal, classe e número e URL, porque o `id` interno é ULID gerado por home): **43 de 44 iguais** (`bench-comparacao.txt`). A diferença (E5, busca temática no TJDFT) está nas posições 3 a 5 do top-5 ao vivo: o mesmo conjunto de decisões recentes da fonte, com uma decisão nova e outra fora do corte; é variação da fonte consultada ao vivo, não do código de busca, que a 1.4.0a2 não alterou. Nenhum caso do conjunto-ouro usa `data` histórica, por isso a correção da decisão 0075 não aparece nesta projeção. Tempo por consulta: p50 1,1 s; p95 10,1 s; máximo 12,8 s (o p95 continua acima do piso de 5 s do D4 para consultas ao vivo, defeito já registrado).

Próximo: auditoria do delta de release (Codex), CI nas oito combinações, merge, tag `v1.4.0a2`, rascunho, auditoria dos bytes da CI, anexação do snapshot, publicação, PyPI, instalação oficial.
