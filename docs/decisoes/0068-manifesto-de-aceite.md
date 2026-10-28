# 0068 — Manifesto de aceite do plano 1.4.0 e sua validação offline

Data: 28/10/2026 · Versão: 1.4.0 · Origem: `docs/PLANO-1.4.0.md` (seção 5, D5 e I1.5), PR #11; revê o procedimento de aceite de incremento (regra 8 do `AGENTS.md`)

Redução de escopo pelo D5 em 28/10/2026, após três rodadas COM BLOQUEADOR (registro docs/auditoria/1.4.0/i15-reducao-escopo.md).

## Contexto

A seção 5 do plano condiciona a conclusão de cada incremento a oito etapas cumpridas e registradas em
`release/acceptance_manifest.json`, e o D5 fixa o teto de três rodadas, o passe final independente e a regra de que o
teto nunca equivale a aprovação: após ele, reduz-se escopo ou adia-se, com registro no manifesto e no rótulo. Sem um
validador, o registro era texto livre: o auditor encontrou nas três primeiras rodadas do PR #11 etapas dispensadas por
nota, parecer aceito por URL ou hash qualquer, relatório de bateria "não executada" que fechava o incremento e itens
removidos do manifesto sem deixar rastro. A mudança altera o que conta como aceite, e por isso exige registro (regra 8).

A terceira rodada ainda encontrou que o validador, ao pretender conferir o conteúdo da bateria live e do ambiente,
conferia só uma parte (saúde vazia, outra fonte ou commit diferente passavam). O D5 reduziu o escopo: o manifesto deixa
de pretender validar esse conteúdo, que passa ao auditor por recibo de parecer.

## Decisão: o que o código impõe

1. **Ferramenta.** `scripts/manifesto_aceite.py` (só stdlib) valida e escreve o manifesto; cada escrita valida o
   manifesto inteiro e grava de forma atômica. `fechar` valida sempre, inclusive com o incremento já concluído.
2. **Forma dos recibos.** A etapa concluída exige exatamente um recibo de cada tipo previsto, com os campos exatos do
   tipo e formatos conferidos (commit de 40 hex, sha256 de 64 hex, URLs do repositório, tag, versão). Recibo
   repetido, de outra etapa, com campo faltante ou extra reprova.
3. **Igualdades entre recibos.** Commit testado, commitado e auditado; `merge`, `tag`, `instalacao` e a `bateria_live`
   da etapa 8 sobre o mesmo commit; tag igual a `v` mais a versão do incremento; URL da release da tag; versão e bytes
   (wheel e sdist) da PyPI iguais aos da release; `instalacao.digests` igual ao conjunto dos sha256 de
   `snapshot.pacotes`.
4. **Etapa 2.** `run_ci` com `jobs` exatamente os do workflow `ci` (lint, repositorio e as oito combinações `test` de
   ubuntu-latest e windows-latest com Python 3.11 a 3.14), todos `success`; o contrato MCP (`tests/contrato`) é parte da
   suíte e fica coberto pelos jobs `test`.
5. **Bateria live (etapas 2 e 8).** `bateria_live` tem `relatorio` e `saude_fontes` (caminhos no repositório, sha256
   calculado pelo `registrar` e reconferido nos bytes pelo `validar`), `commit` (com as igualdades do item 3) e
   `parecer_bateria`. O validar não lê o relatório nem a saúde: confere existência e hash.
6. **Instalação (etapa 7).** `instalacao` mantém `concluida`, `commit`, `attestation_verificada` e `digests` e exige
   `parecer_instalacao`. `doctor` (etapa 8) mantém `ok` e `alertas`, com cada alerta de uma categoria de
   indisponibilidade classificada.
7. **Pareceres locais.** `parecer` (etapa 4), `parecer_bateria` e `parecer_instalacao` são arquivos existentes no
   repositório, com sha256 calculado pelo `registrar` e reconferido nos bytes, e última linha não vazia exatamente
   `SEM BLOQUEADOR` (BOM, CRLF e espaços finais normalizados). URL não vale. O teto de rodadas não aprova.
8. **Snapshot.** `snapshot.pacotes` é uma lista com ao menos um `{nome, sha256}` (nomes sem repetição); `bateria_s4` deve
   ser `aprovada`. Nada além disso é afirmado ou conferido sobre os pacotes.
9. **Catálogo fixo.** `CATALOGO_PLANO` traz os itens da seção 6 por incremento (I1.1 a I1.6 e S0; I2.1 a I2.6; I3.1 a
   I3.8; I4.1 a I4.4). Cada incremento contém exatamente esses itens: faltar ou sobrar item reprova. Item fora do
   catálogo exige decisão registrada que altere o catálogo; não há atalho.
10. **Reduções e adiamentos.** Só pelo procedimento do D5: o item permanece na lista com estado `reduzido` ou `adiado`,
    com entrada em `reducoes_de_escopo` (registro existente no repositório) e rótulo do incremento não nulo. Retirar o
    item da lista não é redução.
11. **Caminhos confinados.** Manifesto e todo caminho de recibo são relativos à raiz do repositório; absoluto, `..` que
    escape, UNC, unidade ou fluxo alternativo, nome de dispositivo do Windows e symlink para fora são recusados.

## Conferência material do auditor

O manifesto não consulta o GitHub nem a PyPI e não valida o conteúdo da bateria nem do ambiente. Cabe ao auditor, e é
atestada pelos pareceres locais acima (`parecer`, `parecer_bateria`, `parecer_instalacao`):

- a execução e a cobertura da bateria live: que foi executada de fato, sobre o escopo declarado, com as contagens e as
  falhas e indisponibilidades classificadas no relatório e no `saude-fontes.json`;
- o commit registrado no `saude-fontes.json` e a sua correspondência com o commit do recibo;
- o ambiente das etapas 7 e 8: Windows e IP brasileiro;
- a completude dos pacotes do snapshot (núcleo e tribunais da seção 4 do plano) e o conteúdo da instalação;
- a existência e o resultado do run, a release e a attestation reais, a publicação no GitHub e na PyPI e que o pacote
  publicado tem os bytes registrados.

Um parecer `SEM BLOQUEADOR` é a declaração do auditor de que fez essa conferência; o validador só prova que o parecer
existe, é o arquivo registrado e termina assim.
