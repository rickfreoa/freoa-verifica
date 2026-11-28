# Release 1.4.0a10 - decisão 0096 (paridade da leitura de HTML entre plataformas)

Executor: supervisor (Opus), ambiente Linux de nuvem da sessão e notebook Windows do titular (cópias do home, nunca o
home real), 28/11/2026. Procedimento: `docs/RELEASE.md`. Autorização do titular (28/11/2026): voltar o home à
1.4.0a8; aviso na release da 1.4.0a9; correção na a10 por normalização antes da lxml; rito com atualização no
Windows; depois da rodada 3 do Codex, HTML5 como referência e rodada 4 restrita.

## Diagnóstico

| Etapa | Saída |
|---|---|
| Instalação da 1.4.0a9 no home real (Windows 11, acervo da 1.4.0a8) | falha no staging: `reprocessamento falhou em 10 captura(s): interpretacao_indisponivel`; banco intacto; home de volta à 1.4.0a8 |
| Cópia do home reprocessada sozinha com a 1.4.0a9 (Windows) | 843 reprocessadas, 0 falhas, mas 6 modelos com caracteres C1 (CF com 37) |
| Snapshot da 1.4.0a9 reprocessado sozinho (Linux) | 843 reprocessadas, 0 falhas |
| Instalação instrumentada sobre cópia integral do home (Windows) | as mesmas 10 capturas do Planalto, legadas conferidas, de 18/10; modelo do snapshot (1.2.5, Linux) difere da releitura (1.2.5, Windows) |
| Versões | lxml 6.1.3 nas duas; libxml2 2.11.9 (Windows) e 2.14.6 (Linux) |
| Causas | `&#128;`–`&#159;` lidas como C1 na 2.11; `</body></html>` soltos lidos de modo diferente |
| Modelos do home real | 965, nenhum com C1 |

## Correção e auditoria

| Etapa | Saída |
|---|---|
| `521303f` (normalização inicial) | Codex r1: BLOQUEADOR (remoção sem contexto, referência consumida pela metade, zeros à esquerda, CVM fora) |
| `40dfead` (normalização léxica, `cvm-html-2`) | Codex r2: BLOQUEADOR (referência fabricada pela remoção, limites léxicos, custo quadrático) |
| `7c2fd74` (comentário vazio, limites da libxml2, varredura linear) | Codex r3: BLOQUEADOR (fechamento no meio do parágrafo continua o texto; `</script x>`) |
| Titular | HTML5 como referência (conferido com html5lib nos quatro casos); rodada 4 restrita |
| `29675c8`/`8c17d58` (fechamento de `script`/`style`; registro da regra) | Codex r4 restrita: APROVADO, sem achados |
| Testes da 0096 | 15, verdes no Linux (libxml2 2.14.6) e no Windows (2.11.9) |
| Paridade sobre o acervo inteiro, código final | 844 modelos idênticos nas duas plataformas; nenhum erro; nenhum caractere C1 |

## Snapshot e S4

| Etapa | Saída |
|---|---|
| Pacote 1.4.0a10 construído com `requirements/build.lock`, instalado em venv limpo com `requirements/ci.lock` | `freoa-verifica 1.4.0a10` |
| Candidato: snapshot oficial da 1.4.0a9 (`22a0320b…58ea`) instalado em home vazio, experimental, com reconstrução para derivados 8 | 0; 826 obras, 2.069 capturas |
| S4 no candidato (`--estrito --gravar-manifesto manifesto-1.4.0a10.json`) | 0; difere do da 1.4.0a9 só em `derived_version` |
| Exportação `--arquivo-unico` | 0 |
| Pacote com o digest (`a0c2643`): instalação vinculada em home vazio, S4 pós-instalação, `doctor --offline` | 0 (`vinculado: True`), 0, 0 |

Snapshot `freoa-verifica-snapshot-20261128-1.4.0a10.tar.gz`, 667.256.587 bytes, sha256
`bd99184f5f862858b5272408fce761652bbcbb82baef827e581ae26e5b517f57`, `derived_version` 8.

## Atualização no Windows sobre home com histórico (passo novo do rito)

| Etapa | Saída |
|---|---|
| Wheel com o digest e snapshot remontado no notebook (hash conferido); cópia integral nova do home real (1.4.0a8, derivados 6) | — |
| `fv snapshot install` sobre a cópia (Windows 11, libxml2 2.11.9) | `status: ok`, `vinculado: True`, derivados reconstruídos para 8 no staging (o caminho que falhou na 1.4.0a9); 826 obras, 2.069 capturas |
| S4 estrito; `doctor --offline` | 0; `ok` |
| Caracteres C1 nos modelos da cópia atualizada | 0 em 971 |

Uma primeira tentativa (`home3`) foi descartada: o script embutido que copiava o banco falhou e a instalação seguiu
sobre cópia sem banco, o que não testava a atualização; foi interrompida e refeita com script próprio (`home4`).

## CI

| Etapa | Saída |
|---|---|
| CI em `f9226b0` | `repositorio` falhou: `test_3_decode_so_na_interpretacao_unica` (a normalização chamava `.decode("cp1252")` fora da interpretação única) |
| `.decode` trocado por tabela fixa do HTML5 (27 códigos, conferida igual ao cp1252) | comportamento idêntico; snapshot, paridade e passo do Windows seguem válidos; garantias estruturais 7/7 |
