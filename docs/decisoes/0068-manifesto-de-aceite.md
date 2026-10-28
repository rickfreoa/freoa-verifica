# 0068 — Manifesto de aceite do plano 1.4.0 e sua validação offline

Data: 28/10/2026 · Versão: 1.4.0 · Origem: `docs/PLANO-1.4.0.md` (seção 5, D5 e I1.5), PR #11; revê o procedimento de aceite de incremento (regra 8 do `AGENTS.md`)

## Contexto

A seção 5 do plano condiciona a conclusão de cada incremento a oito etapas cumpridas e registradas em
`release/acceptance_manifest.json`, e o D5 fixa o teto de três rodadas, o passe final independente e a regra de que o
teto nunca equivale a aprovação: após ele, reduz-se escopo ou adia-se, com registro no manifesto e no rótulo. Sem um
validador, o registro era texto livre: o auditor encontrou nas três primeiras rodadas do PR #11 etapas dispensadas por
nota, parecer aceito por URL ou hash qualquer, relatório de bateria "não executada" que fechava o incremento e itens
removidos do manifesto sem deixar rastro. A mudança altera o que conta como aceite, e por isso exige registro (regra 8).

## Decisão

1. **Ferramenta.** `scripts/manifesto_aceite.py` (só stdlib) valida e escreve o manifesto; cada escrita valida o
   manifesto inteiro e grava de forma atômica. `fechar` valida sempre, inclusive com o incremento já concluído.
2. **Recibos por etapa.** A etapa concluída exige exatamente um recibo de cada tipo previsto, com campos tipados e
   igualdades entre etapas (commit testado, commitado e auditado; merge, tag, instalação e bateria da etapa 8; bytes da
   release iguais aos da PyPI):
   - etapa 2: `run_ci` com os `jobs` do workflow `ci` (lint, repositorio e as oito combinações `test` de
     ubuntu-latest e windows-latest com Python 3.11 a 3.14), todos `success`; o contrato MCP (`tests/contrato`) é parte da
     suíte e fica coberto pelos jobs `test`; `bateria_live` com relatório e `saude-fontes.json` (caminho e sha256
     reconferidos), contagens (`aprovados + xfail >= 1`, `falhas` igual às `falhas_fora_do_escopo`), escopo, ambiente
     (`so`, `python`, `pais_ip`) e a classificação lida do `saude-fontes.json` (`completa: true`; toda regressão listada
     fora do escopo, com registro; indisponibilidade com categoria);
   - etapa 6: `snapshot` em `pacotes` (núcleo e um por tribunal, seção 4 do plano), cada um com sha256; a etapa 7
     confere `digests` contra o conjunto desses sha256;
   - etapa 8: `doctor` com alertas só de indisponibilidade classificada e nova `bateria_live`.
3. **Catálogo fixo.** `CATALOGO_PLANO` traz os itens da seção 6 por incremento (I1.1 a I1.6 e S0; I2.1 a I2.6; I3.1 a
   I3.8; I4.1 a I4.4). Cada incremento contém exatamente esses itens: faltar ou sobrar item reprova. Item fora do
   catálogo exige decisão registrada que altere o catálogo; não há atalho.
4. **Reduções e adiamentos.** Só pelo procedimento do D5: o item permanece na lista com estado `reduzido` ou `adiado`,
   com entrada em `reducoes_de_escopo` (registro existente no repositório) e rótulo do incremento não nulo. Retirar o
   item da lista não é redução.
5. **Parecer.** Só local: arquivo existente no repositório, sha256 calculado pelo `registrar` e reconferido nos bytes, e
   última linha não vazia exatamente `SEM BLOQUEADOR` (BOM, CRLF e espaços finais normalizados). O teto de rodadas não
   aprova.
6. **Caminhos confinados.** Manifesto e todo caminho de recibo são relativos à raiz do repositório; absoluto, `..` que
   escape, UNC, unidade ou fluxo alternativo, nome de dispositivo do Windows e symlink para fora são recusados.

## Limites

O manifesto registra e confere a coerência entre recibos. Ele não consulta o GitHub nem a PyPI.
A conferência material é do auditor: que o run existe e passou, que a release e a attestation são reais e que o pacote
publicado tem aqueles bytes.
A lista de `jobs` e o conteúdo do `saude-fontes.json` são declarados pelo registro e conferidos quanto a
forma e coerência, não obtidos da fonte.
