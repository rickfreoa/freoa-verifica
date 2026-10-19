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
