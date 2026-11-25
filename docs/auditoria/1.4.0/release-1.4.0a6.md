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

| Etapa | Resultado |
|---|---|
| Auditoria Codex do delta de release (`def6bc7..dcd0a2e`, só leitura) | APROVADO COM RESSALVAS: bytes do snapshot dependem da evidência do supervisor (registrada acima e conferida de novo no asset publicado, abaixo) |
| CI do PR #54 em `dcd0a2e` (run 45577248309) | 11/11 verdes |
| Merge do PR #54 | `a94728f` (merge commit) |
| Tag anotada `v1.4.0a6` | criada e empurrada pelo notebook do titular; o proxy da sessão de nuvem recusa criar tag |
| `release.yml` (run 45626179687) | verde; rascunho com wheel, sdist, `requirements-lock.txt` e `SHA256SUMS` |
| `sha256sum -c SHA256SUMS` no rascunho baixado | OK nos três arquivos |
| Wheel sem `tests/`; digest `4320cac2…36ac` em `snapshots-oficiais.json` da wheel | 0 entradas `tests/`; digest presente |
| `gh attestation verify` da wheel | 1 attestation; `release.yml`, `refs/tags/v1.4.0a6` |
| Wheel baixada em venv limpo com o lock da release; snapshot instalado; S4 pós-instalação; `doctor --offline` | `vinculado: True`; 0; 0 |
| Anexo do snapshot e do `.sha256` | pelo notebook do titular (`gh release upload`): a sessão de nuvem não envia binários ao GitHub; 27 partes de 24 MB remontadas e conferidas antes do envio |
| Asset publicado baixado de volta | sha256 `4320cac27d311dc984debe441e7bf0371e348acb5e0a349621c09a608eb836ac`, 666.512.068 bytes |
| Publicação (`draft=false`, `prerelease=false`) | pelo titular, 25/11/2026 20h50 UTC; a sessão de nuvem recebe 403 para editar releases; `releases/latest` = `v1.4.0a6` |
| Instalação de usuário no Windows (notebook do titular, home descartável): `pip install freoa-verifica==1.4.0a6` em venv Python 3.14; `fv snapshot install` sem argumentos; `doctor --offline` | `status: ok`, `vinculado: True`, derived 6; doctor 0; `CF/88, art. 5o --integral` encontrado. Argumentos com acento passados pelo PowerShell 5 ao executável chegam corrompidos (página de código do console); questão de ambiente, não do pacote |
| `pypi.yml` (run 45698738904) | verde; PyPI com wheel `f10b8865…6deb` e sdist `2190e6a4…ea32`, iguais ao `SHA256SUMS` |

## Para quem tem a 1.4.0a5

Home da a5 responde `ACERVO_DESATUALIZADO` até `fv acervo reconstruir` (derivados 5 para 6) ou reinstalação pelo
instalador oficial. A abertura do normas.leg.br para metadados (emenda A) exige `fv acervo abrir-normas-leg --decisao
"0091-A, titular, 24/11/2026"`; a manutenção periódica, `fv acervo agendar --instalar`.
