# 0051 — Instalação e aceite por digest da versão

Data: 19/10/2026 · Versão: 1.3.0 · Origem: plano 1.3.0, item D2

## Contexto

`fv snapshot install` sem `--arquivo` varria releases anteriores atrás de qualquer snapshot constante da
lista embutida, e o instalador tinha a versão fixa e seguia sem verificar a attestation quando o `gh` faltava.
Isso permitia instalar, com o pacote novo, um snapshot de release anterior e uma instalação de procedência
não verificada sem registro claro.

## Decisão

1. `fv snapshot install` sem `--arquivo` consulta somente a release `v<__version__>`
   (`releases/tags/v<versão>`). Release ausente, rascunho/pré-lançamento ou sem asset da lista para esta versão
   falha com motivo explícito (`release_sem_asset_da_versao:v…`, `release_nao_publicada:v…`); não há busca anterior.
2. O digest do arquivo (baixado ou local) precisa constar de `data/snapshots-oficiais.json` em entrada cuja
   `versao_pacote_min` seja igual à versão instalada. Digest da lista, mas de outra versão: recusa
   `SNAPSHOT_OUTRA_VERSAO`; com `--aceitar-nao-vinculado` instala marcado `vinculado: false`, como antes.
   Cada release do pacote precisa, portanto, acrescentar a própria entrada à lista.
3. O instalador recebe `-Versao` (padrão = `__version__` na release, testado) e exige attestation:
   `gh` ausente ou `gh attestation verify` falho aborta com código ≠ 0. `-SemAttestation` prossegue sem
   consultar o `gh` e grava `attestation_verificada: false`. Com sucesso grava `true`, versão, commit
   (certificado da attestation, quando presente) e o digest do snapshot instalado em `instalacao.json`.
4. `fv doctor` ganha as verificações `snapshot_digest` (instalado × lista embutida da versão) e `attestation`
   (`attestation_verificada` de `instalacao.json`); divergência ou ausência é `alerta`, não falha.

## Emenda FIX1 (auditoria do bloco 1)

1. `instalacao.json` registra `versao`, `sha256_wheel` (do arquivo baixado, ao qual a attestation se refere), `digest_snapshot`, `attestation_verificada` e `concluida`. O instalador grava `concluida: true` (com o `digest_snapshot` instalado) só depois do `doctor` offline; antes disso o registro é parcial (`concluida: false`, `digest_snapshot: null`).
2. A verificação `attestation` do `doctor` só é `ok` se `concluida` for `true`, `versao` for a do pacote em execução, a attestation estiver verificada e, havendo snapshot instalado, `digest_snapshot` coincidir com o digest instalado. Qualquer outro caso é `alerta` com a lista de `motivos`; registro ausente ou ilegível também. O `doctor` não recalcula `sha256_wheel` (a wheel instalada não é retida); o valor é exibido para conferência manual.

## Emenda (1.4.0a1)

A revisão do PR #16 (rodada 1) achou que `_da_versao_instalada` comparava só os números iniciais da versão: 1.4.0a2 e 1.4.0 aceitariam o digest de 1.4.0a1, contra a igualdade exigida pelo item 2.

1. O vínculo exige igualdade da versão normalizada (PEP 440) entre `versao_pacote_min` da entrada e `__version__`. `packaging` não é dependência de execução (só chega pelo pytest), então a normalização é própria e estrita (`snapshot._versao_normalizada`): zeros finais do release não contam, `alpha`/`beta`/`c`/`pre` viram `a`/`b`/`rc`, pré, pós e dev entram na comparação. Versão não interpretável como PEP 440, de qualquer dos lados, não é igual.
2. Efeito: 1.4.0a1 aceita a entrada 1.4.0a1; 1.4.0a2 e 1.4.0 a recusam (`SNAPSHOT_OUTRA_VERSAO`); 1.3.0 continua aceitando a sua; entradas antigas seguem válidas nas suas versões.
3. `_snapshots_oficiais` (filtro por número inicial `<=`) não muda: só limita o que a lista expõe; a igualdade é aplicada por `_da_versao_instalada` em `_vincular` e na busca da release.
