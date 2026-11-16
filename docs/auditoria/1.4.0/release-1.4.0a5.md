# Release 1.4.0a5 - snapshot da própria versão, publicação e instalação

Executor: supervisor (Opus), notebook Windows do titular, 15 e 16/11/2026. Procedimento: `docs/RELEASE.md`. Scripts em `C:\dev\fv14-rel\` (`release-a5-parte1.ps1`, `-parte2.ps1`, `bytes-a5.ps1`, `publicar-a5.ps1`, `instalar-oficial-a5.ps1`); registros em `C:\dev\fv14-rel\a5\`.

Conteúdo funcional: o da 1.4.0a4 (decisão 0085, PR #43), mais a decisão 0086 (PR #44, só documentação).

## A 1.4.0a4, não publicada

Tag `v1.4.0a4` sobre `502943a`; `release.yml` concluído; rascunho com wheel, sdist, lock e `SHA256SUMS`. A auditoria dos bytes (`a4\bytes-etapas.txt`) aprovou checksums, attestation e conteúdo do wheel, mas a instalação do acervo foi recusada com `SNAPSHOT_OUTRA_VERSAO`: o wheel não registrava snapshot da própria versão, e `snapshot._da_versao_instalada` exige `versao_pacote_min == __version__`. A premissa do supervisor, reaproveitar o snapshot da 1.4.0a3, estava errada. Nada foi publicado. Decisão do titular (15/11): lançar como 1.4.0a5, sem apagar tag nem rascunho da a4.

## Snapshot e S4

| Etapa | Saída |
|---|---|
| Pacote 1.4.0a5 em venv limpo, árvore limpa (`c8c42a1`) | `freoa-verifica 1.4.0a5` |
| Candidato: cópia do candidato da 1.4.0a3 | robocopy 1 (arquivos copiados) |
| S4 no candidato, com manifesto `manifesto-1.4.0a5.json` | 0 |
| Exportação `--arquivo-unico` | 0; 2.069 capturas; `blobs_completos: True` |
| Instalação experimental, S4 pós-instalação, `doctor --offline` | 0, 0, 0 |
| Pacote com o digest (`7f1a4d7`): instalação vinculada em home vazio, S4, `doctor --offline` | 0 (`vinculado: True`), 0, 0 |

Snapshot `freoa-verifica-snapshot-20261115-1.4.0a5.tar.gz`, 665.629.451 bytes, sha256 `ae728d50dba100ccb20621bc5688f5f6454e930bf41a0b83d617b482713ff232`, `derived_version` 5. Acervo igual ao da 1.4.0a3.

## Auditoria, CI e publicação

- Auditoria independente (Codex, somente leitura, delta `502943a..7f1a4d7`): versão, pino, vínculo, hashes e escopo conformes; o vínculo da a3 recusado e o da a5 aceito. Bloqueador apontado: ausência dos registros da instalação vinculada, lidos antes de ela terminar; concluída às 18h00 UTC com tudo 0 (resolvido por evidência, comentário no PR #45). Menor: linha do snapshot na seção da a4 do CHANGELOG, corrigida em `20b7323`.
- PR #45 rebaseado sobre o merge do #44; CI verde nas oito combinações, `repositorio` e `lint`, inclusive jobs que atravessaram 00h UTC. Merge em `03265f4`; tag anotada `v1.4.0a5`.
- `release.yml` concluído; rascunho com wheel, sdist, lock e `SHA256SUMS`.
- Auditoria dos bytes (`a5\bytes-etapas.txt`): `SHA256SUMS` confere; `gh attestation verify` aprovado para wheel (`355fe3f0…e5bc5`), sdist (`0d3ef3ff…dd657`) e lock (`c0f8e5ae…eed3`), assinante `release.yml@refs/tags/v1.4.0a5`; wheel com 116 arquivos, nenhum em `tests/`, `Version: 1.4.0a5` e entrada do snapshot a5 com o digest auditado; instalação em venv limpo; snapshot auditado instalado em home vazio, `vinculado: True`; S4 e `doctor --offline` 0. Alerta único: `attestation` com `versao_divergente`, porque o registro do instalador na máquina ainda era o da a3 (esperado antes do instalador oficial).
- Snapshot e `.sha256` anexados; digest do GitHub para o asset igual ao auditado. Publicada em 16/11/2026, 07:07 UTC (o CHANGELOG mantém 15/11, data do corte).
- `pypi.yml` concluído; wheel e sdist na PyPI com os mesmos SHA-256 auditados.

## Instalação oficial (contexto real)

SHA-256 do instalador baixado da tag igual ao do repositório. Instalador 0, sem relançamento (processo sem identidade de pacote). `instalacao.json`: 1.4.0a5, commit `03265f4`, wheel e snapshot auditados, `attestation_verificada: true`, `concluida: true`. `doctor --offline` 0, todas `ok`. Smoke `fv verifica "art. 116 da Lei 6.404/1976"`: `verified` / `OBRA_E_CAMINHO_OK`.

`doctor` com rede: 1. BCB `ok` (a correção da 0085 confirmada na instalação real). Alertas: Câmara `ativacao_ao_vivo_pendente` (0080); Planalto `falha` `acervo_legado_sem_nova_captura` (0048); DataJud e TCU `http_429`, TJSP `desafio_captcha` (ambientais). **`normas_leg` `desafio_captcha` nas três sondas.**

## Achados desta release

1. **Rota normas.leg.br fechada no home real.** O home real guarda barreira de host persistente desde 14/11/2026, 12:05 UTC (`normas_leg\bloqueio-normas.leg.br.json`: HTTP 403 com marcador de CAPTCHA na consulta da Lei 6.404/1976), gravada durante o desenvolvimento. Pela tabela da 0080, a reabertura exige decisão registrada. O método `NormasPortao.reabrir(decisao)` existe, mas nenhum comando o expõe (`fv camara reabrir` só admite os hosts da Câmara). Lacuna de produto; reabrir é decisão do titular. A verificação ao vivo da 0085 (§7) foi feita em home de teste e não demonstra disponibilidade contínua: o portal apresenta CAPTCHA ao menos às vezes.
2. **Home virtualizado do app Claude desatualizado.** `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\freoa-verifica` continua com o registro e o snapshot da 1.4.0a3; o venv, comum aos dois contextos, agora tem a 1.4.0a5. Um `fv` executado dentro do app empacotado lê esse home e acusará versão e digest divergentes. O instalador da 0085 relança fora do pacote, o que não atualiza a cópia virtualizada. Remover ou migrar essa cópia é decisão do titular.
