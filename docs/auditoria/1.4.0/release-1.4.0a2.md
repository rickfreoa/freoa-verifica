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

Pacote 1.4.0a2 do venv da release, `FV_HOME` no home vinculado, `scripts/comparativo_ouro.py` com o conjunto-ouro de 44 casos (`docs/auditoria/comparativo-120/gold.jsonl`), consulta ao vivo onde o produto consulta: código 0 (`bench-etapas.txt`, `bench-freoa_raw.jsonl`). Comparação com o bench da 1.4.0a1 (`release-1.4.0a1/bench-freoa_raw.jsonl`) na projeção do I1.4 (`comparar-bench.py.txt`: status, identidade e temporal das verificações; status e top-5 das buscas, identificando o julgado por tribunal, classe e número e URL, porque o `id` interno é ULID gerado por home): **43 de 44 iguais** (`bench-comparacao.txt`). A diferença (E5, busca temática no TJDFT) está nas posições 3 a 5 do top-5: sai `0703329-25.2024.8.07.0015`, entra `0703541-46.2024.8.07.0015` (publicada em 30/06/2026; nova apenas naquele top-5) e dois itens se deslocam. A variação é compatível com a consulta ao vivo, e o delta da 1.4.0a2 não altera o código de busca; a causa, porém, não foi isolada (isso exigiria execução controlada sobre as mesmas respostas). Limitação do comparador: a chave tribunal, classe e número e URL não individualiza decisões distintas do mesmo processo (E1 e E3 têm itens assim). A auditoria r2 conferiu também órgão, relator, datas, ementa e texto exibido: só E5 difere. Para a próxima release, o comparador deve usar identificador oficial estável ou chave discriminante. Nenhum caso do conjunto-ouro usa `data` histórica, por isso a correção da decisão 0075 não aparece nesta projeção. Tempo por consulta: p50 1,1 s; p95 10,1 s; máximo 12,8 s (o D4 fixa 5 s para consulta local e 20 s para federada; esta medição agregada mistura as duas e não certifica, nem infirma, o D4).

## Ressalvas da auditoria r2 (não bloqueadoras)

- Codificação: os registros são UTF-8 válido, sem NUL, mas reproduzem fielmente mojibake já presente nos originais de console (ex.: `Diagn├│stico`). Números, hashes, estados e códigos de saída estão íntegros. Nas próximas releases, a captura fixa a codificação (`$OutputEncoding`/`PYTHONIOENCODING=utf-8`).
- Condição (c) da 0076: o script aceitava sucesso sem registro novo e não exigia contagem e esquema no predicado final. O log desta execução comprova esquema 16→17, 15 registros preservados, cinco legados com `confere: null` e registro novo com `confere: true`. O script deve ser endurecido antes de reúso.
- Não versionados por serem auxiliares: `pip.log`, `pip2.log` (instalação de dependências do venv a partir de `requirements/ci.lock`), `bench-console.txt` (eco de console do bench, cujo conteúdo útil está em `bench-freoa_raw.jsonl` e `bench-etapas.txt`) e `registro-release-a2.py` (script de supervisão que converteu e sanitizou os registros; não toca o produto).
- Proveniência: o `doctor` vinculado sai com 0, mas ainda lê a attestation da 1.4.0a1 (`versao_divergente`, `digest_snapshot_divergente`), porque a da 1.4.0a2 só existe depois do `release.yml`. A proveniência dos bytes a2 é conferida na etapa de auditoria dos bytes da CI.

## Publicação (passos 5 a 8)

- Auditoria r2 do delta de release (Codex): SEM BLOQUEADOR; ressalvas incorporadas acima (`53dcf38`). CI verde nas oito combinações, `repositorio` e `lint` em `5dae93b` e `53dcf38`.
- Merge do PR #26 em `main` (`5600f58`); tag anotada `v1.4.0a2` sobre esse commit. `release.yml` concluído com sucesso e rascunho criado com wheel, sdist, lock e `SHA256SUMS`.
- Auditoria dos bytes da CI (`bytes-etapas.txt`): `SHA256SUMS` confere para os três arquivos; `gh attestation verify` aprovado para wheel (`b3623076…cfeede`) e sdist (`871bc8a6…7192ab`), assinante `release.yml@refs/tags/v1.4.0a2`; wheel com 97 arquivos, nenhum em `tests/`, `Version: 1.4.0a2` e entrada do snapshot a2 com o digest auditado; wheel baixada instalada em venv limpo (Python 3.14) com `requirements/ci.lock`; snapshot auditado instalado em home vazio, `vinculado: True`; S4 pós-instalação e `doctor --offline` com 0. O `doctor` desse home ainda acusava a attestation da 1.4.0a1, porque o registro de instalação é do sistema e só o instalador oficial o atualiza (ver abaixo).
- Snapshot e `.sha256` anexados ao rascunho; o digest que o GitHub calcula para o asset é `8e2ad821…bfff9e`, igual ao auditado. Release publicada.
- `pypi.yml` concluído com sucesso; os arquivos da 1.4.0a2 na PyPI têm os mesmos SHA-256 da wheel e do sdist auditados.
- Instalação oficial no notebook (`instalacao-oficial.txt`), depois de cópia integral do home 1.4.0a1 (6.191 arquivos, 3.638.365.975 bytes, contagem e tamanho iguais à origem): instalador baixado da tag com SHA-256 igual ao do repositório; saída 0; `instalacao.json` com versão 1.4.0a2, commit `5600f58`, wheel e snapshot auditados, `attestation_verificada: true`, `concluida: true`; `doctor --offline` com todas as verificações `ok`, inclusive `attestation` (agora 1.4.0a2, sem motivos) e `snapshot_digest`. Migração do home real: esquema 16→17, as 15 execuções registradas preservadas (16 depois do smoke). Smoke: `fv verifica "art. 116 da Lei 6.404/1976"` → `verified`/`OBRA_E_CAMINHO_OK` com os eixos novos da decisão 0075 na evidência.

Próximo: IL.1 (congelamento da Porta L) e IL.2.
