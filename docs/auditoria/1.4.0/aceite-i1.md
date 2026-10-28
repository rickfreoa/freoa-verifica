# Fechamento do I1 (1.4.0a1): instalação, doctor e bateria ao vivo (etapas 7 e 8)

Executor: supervisor (Opus), no notebook Windows do titular, IP brasileiro. Data: 28/10/2026.
Evidências em `aceite-i1/` (logs saneados: caminhos de máquina e nome do host trocados por marcadores, escapados no XML, que continua válido; no log do
instalador, o eco "Requirement already satisfied" do pip foi omitido, com a contagem na primeira linha).

## Etapa 7: instalação pelo instalador oficial

Comando: `scripts/instalar-freoa-verifica.ps1 -Versao 1.4.0a1`, executado do checkout da tag `v1.4.0a1`
(`6ac49ee`), com a wheel da release conferida ao lado do script. Roteiro: `instalar-a1.ps1` (checkout da tag,
instalador, `fv --version`, `fv doctor`), envolto por um invólucro que impede a suspensão do Windows
durante a execução (`SetThreadExecutionState`) e faz uma limpeza pontual de recuperação (ver abaixo).

Resultado (`aceite-i1/instalacao.json`, `aceite-i1/instalar.log`): instalador com saída 0 (`instalador exit=0`); limpeza às 11:40:36, roteiro das 11:41:04 às
12:01:32 (UTC-3), incluído o `doctor` online; `concluida: true`; `commit` `6ac49ee520afcd37c26e2f9e640952dd7ea2da8a`; `sha256_wheel`
`66446a0a…4b8f`; `attestation_verificada: true` (`gh attestation verify`); `digest_snapshot`
`ad090c341b5e95c606309bff84ef9a233e144d223bcb5c6a40a9076dc3d8fafa`, igual ao snapshot anexado à release.

Tentativa anterior interrompida (`aceite-i1/instalar-tentativa-interrompida.log`, início 09:29): falhou na
etapa "instalar snapshot" com código `1073807364` (`0x40010004`, DBG_TERMINATE_PROCESS), isto é, processo
encerrado de fora. O log de eventos do Windows registra: suspensão às 09:56, retomada às 10:56,
desligamento pedido pelo usuário às 11:04 (User32 1074) e novo boot às 11:08. A interrupção é compatível com encerramento externo; não há defeito do produto demonstrado (o que não exclui, por si, problema anterior de desempenho: ver a questão aberta).
Antes de relançar, o invólucro removeu o marcador de uso `.fv-uso` cujo pid não existia após o boot (marcador de
processo vivo seria preservado) e todos os diretórios `staging/fv-snap-*`. Esta segunda limpeza não verifica
proprietário nem adquire a trava do home: é recuperação pontual, aceitável só porque nenhum `fv` rodava após o
boot; não é procedimento geral.

Questão aberta, sem defeito demonstrado: o home tinha acervo vinculado à 1.3.0, então o `snapshot install`
anexou o snapshot ao acervo existente (`_merge_attach`) em vez de instalar em home limpo. Reproduzida sobre
cópias, sem carga concorrente, a anexação levou 139 s (FTS das redações 47 s, índice de decisões 48 s, zero
divergências). Na tentativa interrompida, o processo ficou ativo cerca de 18 min (antes e depois da
suspensão) sem terminar, com o notebook ocupado por outras cargas; na instalação concluída, cerca de 6 min. Esses
dois tempos vêm dos carimbos dos arquivos de staging observados durante a execução, não dos logs anexados.
A diferença não foi isolada. Fica para medir no I2, junto do p95 do bench (defeito 3).

## Etapa 8: doctor e bateria ao vivo

`fv doctor` (online, no fim do mesmo roteiro): `status: ok`, saída 0, com quatro alertas. Só dois são
indisponibilidade classificada por prova: Planalto `recusa_identificado_planalto` (`recusa_identificado`,
decisão 0048) e TJSP `desafio_captcha` (`ambiental_desafio`). Os outros dois não têm categoria: DataJud
`http_429` (positivo e negativo; documento ok), porque `connectors/challenge.py` só prova categoria para
401/403 (`recusa_identificado`) e 5xx (`fonte_fora`); e TCU negativo `tcu_busca_incompleta_limite_de_varredura`,
levantado sem categoria nem evidência (`connectors/tcu.py`), que prova limite da própria varredura, não
indisponibilidade externa. As demais fontes (BCB, CVM colegiado e normas, Senado, STF, STJ, TJDFT e as
verificações de versão, home, banco e migrações) em `ok`.

Consequência: o critério da etapa 8 ("alertas só de indisponibilidade classificada") **não está cumprido**
nesta execução. A saída 0 não o prova, porque o `doctor` trata qualquer alerta como compatível com `ok`
(`service.py`). Defeito registrado para o I2: o `doctor` não distingue alerta classificado de não
classificado, e a busca do TCU sinaliza o limite de varredura como indisponibilidade sem categoria.

Bateria: `pytest -q -m live` no checkout da tag (`6ac49ee`, árvore limpa salvo a wheel não versionada ao
lado do instalador), Python 3.14.6, pacote importado do checkout. Evidências: `aceite-i1/live.txt`,
`aceite-i1/live.xml` e `aceite-i1/saude-fontes.json` (sha256
`c9cfd8b61ae6c68cd3fa87c30f2ef91483602799ab9bdcee109b63245894439d`).
Resultado: 25 aprovados, 5 xfail, 4 falhas, em 228,72 s. `saude-fontes.json`: `completa: true`, `commit`
igual ao da tag, `inicio` e `fim` preenchidos (o defeito do arnês registrado no I1.4 está corrigido).

| Fonte | Estado no arnês | Leitura |
|---|---|---|
| BCB, CVM colegiado, CVM normas, Senado, STF, STJ, TJDFT | `ok` | aprovados |
| DataJud | `unavailable`, `fonte_fora`, `http_504` | xfail classificado; o doctor, minutos antes, recebeu `http_429` |
| TJSP | `unavailable`, `ambiental_desafio`, `desafio_captcha` | xfail classificado, como na 1.3.0 |
| Planalto | `regressao`, `recusa_identificado` | falha fora do escopo do I1 (cascata Planalto é o I3.6), como na 1.3.0 |
| TCU (negativo) | `regressao`, `tcu_busca_incompleta_limite_de_varredura` | falha fora do escopo do I1, como na 1.3.0 |

Diferença em relação à linha de base de 27/10 (`live-1.3.0-saude-fontes.json`): o DataJud passou de `ok` a
`unavailable` (504 na bateria, 429 no doctor). Uma execução não distingue instabilidade da fonte de limite de
taxa. O conector do DataJud e `transport.py` não mudaram entre `68e743a` (1.3.0) e `6ac49ee`; `httputil.py`
ganhou um parâmetro opcional (`repeticao`) que o DataJud não usa. Não foi demonstrada regressão; a causa da
indisponibilidade não foi isolada. O arnês não foi
alargado: as quatro falhas continuam `regressao` e entram no manifesto como falhas fora do escopo.
