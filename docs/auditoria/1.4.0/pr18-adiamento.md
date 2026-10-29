# PR #18 - passe final com bloqueador; S0b parte 1 adiada para I2 (I2.7)

Data: 28/10/2026. Autor: supervisor (Opus), sob o D5 do plano 1.4.0.

## Histórico

A S0b parte 1 (leitura do robots.txt pelo RFC 9309, decisão 0071) passou pelo PR #17 (r1, com bloqueador)
e pelo PR #18, que o substituiu com o mesmo conteúdo rebaseado (r2 COM BLOQUEADOR sobre `aa0cd1c`; r3 SEM
BLOQUEADOR sobre `689de1c`). O importante remanescente da r3 foi tratado em `97fb503` (CI verde nos dez jobs,
run 40716265970). Pareceres: `C:\dev\fv14-auditoria\parecer-pr17-r1.md`, `parecer-pr18-r2.md`,
`parecer-pr18-r3.md`, `parecer-pr18-final.md` (fora do repositório, no computador do titular).

## Fato

O passe final independente sobre `97fb503` terminou COM BLOQUEADOR, com achados no código do PR, não no
último delta:

- B1: `ler_do_registro` delega ao status da evidência todo motivo `http_*` sem conferir consistência.
  Registro contraditório (`motivo: http_403`, `evidencia.status: 200`) vira `sem_restricoes / 200_corpo_vazio`
  sem corpo examinado, e o orquestrador libera pedidos a partir dele. Também liberam: `http_403` com evidência
  404, e `http_404` com salto 302 (o retorno antecede a checagem dos saltos). O auditor não demonstrou que o
  transporte atual gere esses registros; demonstrou que o leitor os aceita.
- B2: a proteção contra repetição entre execuções depende só da existência do `.captura.json`, gravado depois
  do pedido. Se a gravação falhar após uma recusa (403), a reexecução repete o pedido ao mesmo robots: via de
  repetição após recusa, contrária à regra invariável 3.
- I1: `_limpo` confunde apóstrofo interno com fechamento de aspas e substitui raízes conhecidas antes do
  caminho citado; o módulo ainda afirma, em geral, que o relatório não contém caminhos de máquina.

## Decisão

1. Pelo D5, depois das três rodadas e do passe final não há nova rodada, e a decisão 0070 só cobre correção de
   registro. A S0b parte 1 é adiada inteira para o I2, item I2.7. O PR #18 não é incorporado; o ramo
   `feat/s0b-robots-r2` fica como base.
2. A S0 do I1 fica reduzida à rodada 1 (PR #15, incorporada). O adiamento entra no manifesto e no rótulo da
   1.4.0a1.
3. Nenhuma nova sonda da S0b roda até o I2.7 ser incorporado.

## O que o I2.7 precisa resolver antes de código

- Registro como fonte da decisão: toda contradição entre motivo, status da evidência e saltos resulta em
  barreira; ausência de corpo nunca é convertida em corpo vazio fora do ramo `corpo_vazio`.
- Tentativa antes do pedido: marcar a tentativa de forma persistente antes de chamar o transporte, para que
  falha de gravação depois do pedido não abra nova chamada automática.
- Sanitização do relatório por estrutura (campos de caminho do traceback), não por regex sobre texto livre,
  com a limitação remanescente declarada no módulo e no roteiro.
