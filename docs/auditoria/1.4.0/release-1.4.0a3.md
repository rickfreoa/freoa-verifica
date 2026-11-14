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

## Bench e suíte contra o pacote instalado

- Bench (`scripts/comparativo_ouro.py`, conjunto-ouro de 44 casos, home vinculado, consulta ao vivo onde o produto consulta), comparado com o da 1.4.0a2 pela mesma projeção: **44 de 44 iguais**; p50 1,13 s, p95 5,19 s, máximo 7,45 s.
- Suíte offline contra o pacote instalado no venv da release (cópia do repositório sem `freoa_verifica/`, `python -I`, import conferido em `site-packages`), sobre os testes de `73aca4d`: 14.422 passed, 31 failed, 6 errors. As 37 falhas têm duas causas, nenhuma do pacote: `test_published_pin` (pino corrigido em `5c2133e`) e testes que leem os fontes pelo caminho do repositório. Reexecutados com os fontes presentes: 37 passed. Limite: como `tests/__init__.py` faz o pytest inserir a raiz da cópia no `sys.path`, esses 37 rodaram contra os fontes locais, idênticos ao pacote (107 arquivos conferidos pelo auditor), e não contra os bytes do wheel.

## Publicação (passos 4 a 8)

- Auditoria do delta de release (Codex, `73aca4d`): SEM BLOQUEADOR; ajuste editorial (remissões à 0084 na 0075 §6 e na emenda) feito em `5c2133e`, conferido (CONFERE).
- CI de `73aca4d`: única falha `test_published_pin` em todas as combinações concluídas; corrigido. CI de `5c2133e`: verde nas oito combinações, `repositorio` e `lint`.
- Merge do PR #41 em `main` (`d9bd9d7`); tag anotada `v1.4.0a3` sobre esse commit. `release.yml` (matriz completa e build) concluído com sucesso; rascunho com wheel, sdist, lock e `SHA256SUMS`.
- Auditoria dos bytes da CI (`C:\dev\fv14-rel\bytes-a3.ps1`): `SHA256SUMS` confere para os três arquivos; `gh attestation verify` aprovado para wheel (`3875389c…0e3d7b`), sdist (`3117e68b…e93513`) e lock (`c0f8e5ae…b3eed3`, o mesmo das releases anteriores), assinante `release.yml@refs/tags/v1.4.0a3`; wheel com 113 arquivos, nenhum em `tests/`, `Version: 1.4.0a3` e entrada do snapshot a3 com o digest auditado; wheel baixada instalada em venv limpo (Python 3.14) com o lock da release; snapshot auditado instalado em home vazio, `vinculado: True`; S4 pós-instalação e `doctor --offline` com 0 (alerta único: `sem_registro_do_instalador`, esperado antes do instalador oficial).
- Snapshot e `.sha256` anexados ao rascunho; o digest que o GitHub calcula para o asset é `0c35475f…7ea32`, igual ao auditado. Release publicada em 14/11/2026, 08:21 UTC.
- `pypi.yml` concluído com sucesso; os arquivos da 1.4.0a3 na PyPI têm os mesmos SHA-256 da wheel e do sdist auditados.

## Instalação oficial (dois contextos)

Achado desta release: no notebook do titular, o home da 1.4.0a2 estava no armazenamento virtualizado do app Claude (`%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\freoa-verifica`), porque a instalação anterior rodou em processo filho do app empacotado; um `fv` aberto num terminal comum procura `%LOCALAPPDATA%\freoa-verifica` real, que não existia. O venv (`%USERPROFILE%\freoa-verifica`) não é virtualizado e é comum aos dois. A 1.4.0a3 foi instalada pelo instalador oficial nos dois contextos, depois de cópia integral do home virtualizado (8.266 arquivos, 4.968.860.472 bytes, contagem e tamanho iguais à origem).

| Contexto | Instalador | `instalacao.json` | `doctor --offline` | Smoke `fv verifica "art. 116 da Lei 6.404/1976"` |
|---|---|---|---|---|
| Real (processo comum do Windows) | 0; SHA-256 do instalador baixado da tag igual ao do repositório | 1.4.0a3, commit `d9bd9d7`, wheel e snapshot auditados, `attestation_verificada: true`, `concluida: true` | 0, todas `ok` (inclusive `attestation` e `snapshot_digest`) | `verified` / `OBRA_E_CAMINHO_OK` |
| App Claude (virtualizado; home da a2 atualizado) | 0 | idem | 0 | idem |

`doctor` com rede, nos dois contextos, saiu com 1 por alertas de fonte: DataJud `http_504`, TCU `http_429`, TJSP `desafio_captcha` e Câmara `ativacao_ao_vivo_pendente` (indisponibilidades classificadas, externas ou de ativação por home); Planalto `falha` `acervo_legado_sem_nova_captura` (decisão 0048, conhecido). BCB `resposta_invalida`: reproduzido com o pacote 1.4.0a2 no mesmo momento (`doctor-a2-rede.txt`), logo não é regressão da a3; fica como pendência de diagnóstico.

Pendências abertas por esta release: (1) instalação dentro do app empacotado grava o home no armazenamento virtualizado (o instalador e a documentação devem fixar o home real ou avisar); (2) BCB `resposta_invalida` no `doctor` com rede.
