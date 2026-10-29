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

Consequência: o critério da etapa 8 ("alertas só de indisponibilidade classificada") **não foi cumprido**
nesta execução de 28/10; foi cumprido na de 29/10, com a ressalva do TCU (ver adiante). A saída 0 não o prova, porque o `doctor` trata qualquer alerta como compatível com `ok`
(`service.py`). Defeito registrado para o I2: o `doctor` não distingue alerta classificado de não
classificado, e a busca do TCU sinaliza o limite de varredura como indisponibilidade sem categoria.

Bateria: `pytest -q -m live` no checkout da tag (`6ac49ee`, árvore limpa salvo a wheel não versionada ao
lado do instalador), Python 3.14.6, pacote importado do checkout. Evidências: `aceite-i1/live.txt`,
`aceite-i1/live.xml` e `aceite-i1/saude-fontes.json` (sha256 do arquivo versionado
`f2c64a5719bc1cccaf6ca05e97e8e6ef4d2bb8bc8cebf036190928f147437717`; o original gerado pelo arnês,
`c9cfd8b6…439d`, difere só por fim de linha e indentação, normalizados para o repositório).
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

## 29/10/2026: doctor que cumpre a etapa 8 e bateria da etapa 2

Por decisão do titular, as execuções foram repetidas no dia seguinte, depois do limite de taxa do DataJud
(`http_429` de cerca de 12:00 a pelo menos 14:03 de 28/10). Decisão 0072: o alerta do TCU não impede a etapa 8 no
I1; nenhum outro alerta foi ressalvado.

**Doctor** (`fv doctor --json` da instalação, 07:31 a 07:36, UTC-3; `aceite-i1/doctor-20261029.json`):
`status: ok`, saída 0. DataJud `ok`. Alertas, todos com categoria provada salvo o do TCU:

| Fonte | Alerta | Categoria |
|---|---|---|
| CVM colegiado (positivo, negativo, documento) e CVM normas (negativo) | `transporte_Timeout` | `fonte_fora` (`connectors/challenge.py`: só `Timeout` e `TransportError` produzem esse motivo) |
| Planalto | `recusa_identificado_planalto` | `recusa_identificado` (decisão 0048) |
| TJSP | `desafio_captcha` | `ambiental_desafio` |
| TCU (negativo) | `tcu_busca_incompleta_limite_de_varredura` | sem categoria; ressalvado pela decisão 0072 |

Esta execução cumpre a etapa 8 com a ressalva da 0072. A bateria da etapa 8 é a de 28/10 em `6ac49ee`
(acima), cujas indisponibilidades no escopo são todas classificadas (DataJud `fonte_fora` 504, TJSP desafio).

**Bateria da etapa 2** (exige o commit do CI e do parecer de incorporação, `5c86054`, de árvore idêntica a
`6ac49ee`). Três tentativas, todas guardadas:

| Tentativa | Hora (UTC-3) | Resultado | DataJud |
|---|---|---|---|
| 1 (`live-5c86054-tentativa1.*`) | 28/10 12:20 | 25 aprovados, 3 xfail, 6 falhas | positivo e negativo `http_429`, sem categoria (`regressao` no arnês) |
| 2 (`live-5c86054-tentativa2.*`) | 29/10 07:37 | 24 aprovados, 5 xfail, 5 falhas | positivo `http_429`, nove minutos depois do doctor |
| 3 (`live-5c86054.*`, `saude-fontes-5c86054.json`) | 29/10 08:33 | 22 aprovados, 8 xfail, 4 falhas | `ok` |

A tentativa 3 foi a única feita depois de 40 minutos sem chamada ao DataJud, por decisão do titular, para testar
a hipótese de limite por janela curta esgotado pelo próprio doctor. A decisão e seus limites foram fixados antes
do resultado, logo depois da tentativa 2 (29/10, por volta das 07:50): uma única repetição espaçada; se desse
429 de novo, a ressalva da 0072 seria estendida ao DataJud, sem nova escolha. A tentativa foi disparada às 07:52
com espera embutida de 40 minutos (início às 08:33). Que não houve outra chamada ao DataJud no intervalo é
declaração do executor: nenhum outro processo do projeto rodou nesse período, mas os anexos não o provam. O resultado é compatível com a hipótese, sem
prová-la. Ela é o recibo da etapa 2: `saude-fontes-5c86054.json` com `completa: true`, `commit` `5c86054`; as
quatro falhas são as de sempre, fora do escopo do I1 (Planalto ×3, TCU negativo); os xfail são classificados
(CVM colegiado `fonte_fora` por timeout; TJDFT `fonte_fora` `http_503` em três testes; TJSP `ambiental_desafio`).
O TJDFT, `ok` em 28/10, respondeu 503 nesta janela, como já ocorrera no doctor das 14:03 de 28/10.
