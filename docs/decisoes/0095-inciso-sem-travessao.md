# 0095 - Inciso sem travessão (pendente)

Status: aberta pelo titular em 27/11/2026, ao tirar a marca `ROTULO_SEM_SEPARADOR` da 1.4.0a9 (decisão 0094). Sem
implementação.

## Problema

Achados 2, 6 e 9 do colega sobre a 1.4.0a6. O Planalto escreve incisos sem o travessão que `_classify_line` exige
("II processar e julgar os Ministros", também `II)`, `II.`, `II:`), dentro de `<p>`, depois de `<br>`, em fonte órfã
ou em `<div>`/`<span>`. O bloco vira continuação do inciso anterior: o texto do inciso II é confirmado no I, a alínea
seguinte vai para o inciso errado e a consulta ao inciso II recebe negativa falsa. No acervo da 1.4.0a8: 66 casos na
CF (arts. 20, 52, 93, 95, 103-B, 111-A, 114, 115, 130-A, 215...; os incisos IX a XV do art. 93 caem no VIII-B), mais
casos em outras leis e em resoluções do BCB.

## O que não funcionou (0094, quatro rodadas do Codex)

Marca defensiva heurística, sem criar caminho: o bloco suspeito não é anexado e o dispositivo corrente fica
`unknown`, com a negativa suspensa no artigo. Cada filtro para evitar falso positivo (pontuação na linha anterior,
guardas de remissão, numeral até LXXXIX, corpo em minúscula, texto repetido) abriu um escape reproduzível; cada
fechamento ampliou a perda de cobertura (no acervo, marcas fortes em títulos espaçados, listas de numerais em
remissão e parágrafos repetidos). Código e testes dessa tentativa: commits `77cb418` a `6b9e32a` do ramo
`fix/achados-colega-a9`; pareceres em `codex-0094r1` a `codex-0094r4`.

## Caminhos a avaliar

1. **Reconhecimento estrutural** (sugestão do colega): numeral romano que é exatamente o seguinte ao do inciso
   corrente, no mesmo artigo, abre o inciso; fora disso, bloqueio amplo do artigo (confirmação e negativa). Cria
   caminhos e exige conjunto-ouro da CF.
2. **Bloqueio amplo puro**: toda linha ou segmento com numeral romano não reconhecido bloqueia o dispositivo receptor,
   seus descendentes e a negativa no artigo, salvo remissão estrutural provada. Medir a perda de cobertura no acervo
   antes de decidir.
3. Qualquer caminho: conjunto-ouro com os 66 casos da CF e os falsos positivos observados, e auditoria adversarial
   antes da implementação.
