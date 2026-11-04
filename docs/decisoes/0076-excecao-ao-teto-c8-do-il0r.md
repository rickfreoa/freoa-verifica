# 0076. Exceção ao teto do D5 para o C8 do IL.0-R

Data: 04/11/2026. Decisão do titular, Ricardo Peres Freoa, sobre recomendação do supervisor (Opus). Plano 1.4.0, D5; emenda IL; registro `docs/auditoria/1.4.0/pr25-adiamento.md`.

## Fato

O IL.0-R (PR #26) cumpriu as três rodadas do D5 e o passe final independente (`bcf83e9`) terminou COM BLOQUEADOR só pelo critério C8, com onze de doze critérios cumpridos: a migração terminava sem selar o conjunto legado quando o home não tinha `registro.key`, e o selo acontecia na primeira verificação; um registro legítimo da 1.4.0a1 aparecia como não conferido logo após a atualização, e uma linha inserida entre a migração e a primeira verificação passava a contar como legado. Havia ainda um achado médio (falha de E/S da chave sem resposta controlada) e um baixo (teste sintético com argumentos posicionais trocados).

A correção (`3ae2463`, ramo `feat/il0r-c8`) fixa e autentica o legado na migração do home operacional, criando a chave quando necessário, separa staging e exportação, trata falhas de E/S da chave e corrige o teste. A conferência curta do auditor terminou "CORREÇÃO CONFERE" (`C:\dev\fv14-auditoria\parecer-pr26-conf-c8.md`).

## Decisão

1. Concede-se exceção ao teto do D5 para incorporar a correção do C8 sem nova rodada completa, sob três condições cumulativas: (a) CI verde nas oito combinações sobre o commit incorporado; (b) esta decisão registrada antes do merge; (c) na release 1.4.0a2, a migração validada sobre cópia do home 1.4.0a1 instalado no notebook do titular antes de tocar o home real, com registro do resultado.
2. Alcance estrito: um único critério residual depois do passe final; correção restrita ao defeito apontado; conferência curta favorável. A exceção não é precedente para abrir rodada nova nem para dispensar passe final em outro incremento.
3. Diferença em relação à 0074: aquela cobria só estado de versão intermediária nunca incorporada; esta cobre defeito real, corrigido de forma conservadora e conferido. A garantia sobre a correção é a da conferência curta, não a de um passe exaustivo; a condição (c) compensa em parte o risco da área (migração e chave).
