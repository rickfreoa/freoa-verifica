# 0087 - Reordenação: sessão assistida, STJ, Porta L

17/11/2026. Titular (Ricardo Peres Freoa), sobre avaliação do supervisor (Opus) da mesma
data. Altera a sequência da emenda IL (seção 4) e da 0084 §2.3. Não altera critério de
`verified`, matriz, pisos, reserva, mutantes nem contrato.

## 1. Fato

Da 1.4.0a1 à 1.4.0a5 (28/10 a 15/11/2026), nenhuma capacidade da Porta L atingiu o piso no
desenvolvimento (0084 §1) e as íntegras do STJ foram deslocadas a cada pré-release. As
capacidades reprovadas (consolidado vigente, redação em data D, anexos, remissões, vigência)
dependem de texto consolidado com histórico, que só o Planalto e a Câmara/normas.leg.br
oferecem, todos com barreira ao acesso automatizado: UA recusado (0048), 403 com CAPTCHA
(0085) e cobertura parcial. Novos conectores automáticos não removem essa barreira; a sessão
assistida (D3, 0067), decidida em 26/10/2026, é o instrumento previsto e segue em I3.5.

## 2. Decisão do titular

1. Nova ordem: (a) sessão assistida (ex-I3.5), como infraestrutura comum a Planalto,
   normas_leg e TJSP; (b) STJ: íntegras e Porta A; (c) reapuração da Porta L, com o acervo do
   Planalto renovado por sessão assistida.
2. A Porta L não é reapurada antes de (c): sem chance de aprovação, a apuração só consumiria
   a reserva (D6).
3. A rota `normas_leg` permanece fechada no home real até a sessão assistida. O comando de
   reabertura (pendência 24) entra na mesma versão.
4. O home virtualizado do app Claude (pendência 25) é removido.

## 3. Execução registrada

Remoção em 17/11/2026 de
`%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\freoa-verifica` (cerca de
6 GB: banco, cinco cópias `.bak`, blobs e staging). O `instalacao.json` registrava 1.4.0a3,
commit `d9bd9d7`, `concluida: true`, attestation verificada. Antes da remoção, guardaram-se
fora do repositório (`C:\dev\_il\home-virtual-a3-removido-20261117`) o `instalacao.json`, o
`acervo-manifesto.json` e o SHA-256 do `verifica.sqlite3`
(`3ae484fea4eab1392bbc1cfe32ed8f0217a19ca8333cfed2d06c4ed0b719b0a3`). O home comum, na
1.4.0a5, não foi tocado.

## 4. Atos do supervisor (sem mudança de contrato)

1. Pendências ativas até a Porta A do STJ: 18 e 26 (desenvolvimento e sondas nunca no home
   real), 19 (relançamento MSIX), 24 (reabertura de normas_leg). As demais ficam congeladas.
2. Antes da especificação do STJ, sonda do portal de íntegras pelo instrumento oficial, para
   confirmar a ausência de barreira equivalente.
3. CI em camadas, em PR próprio auditado: PR só de documentação sem a suíte completa;
   `test_continuacoes_escalam_linearmente` (defeito 12) com tolerância relativa ou fora do
   gate; matriz completa no merge de código e na release. O D5 não muda.
