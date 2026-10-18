# 0002 — Estados da dimensão temporal

**Decisão.** A dimensão `temporal` passa a distinguir duas afirmações que a versão anterior confundia:

- `vigente_na_fonte`: o texto consolidado oficial, capturado há no máximo 30 dias, apresenta a redação como não superada, sem revogação, revogação parcial, remissão (`vide`), veto ou ambiguidade pendentes. A afirmação é sobre o que a fonte oficial declara na data da captura, e a evidência traz essa data.
- `verified`: a redação vigorava numa data específica, com limites do intervalo conhecidos por data completa e regra de vigência demonstrada no texto do ato alterador capturado.

Os demais estados são `unknown`, `revogado`, `nao_existia` e `ambiguous`.

**Razão.** Exigir prova completa de vigência para toda consulta tornaria a ferramenta inútil: o texto compilado do Planalto informa apenas o ano do ato alterador, e a cláusula de vigência do ato precisa ser capturada à parte. Aceitar a redação não riscada como `verified` seria afirmar mais do que a fonte prova. O estado intermediário diz exatamente o que se sabe.

**Consequências.** Limite conhecido só pelo ano, vacatio não verificada, revogação parcial, `vide` e redação superada sem rasura impedem `verified`. Bloqueios do parser (documento quarentenado, dispositivo ambíguo ou revogado) são aplicados antes de qualquer comparação.
