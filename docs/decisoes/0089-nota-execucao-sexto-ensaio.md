# 0089 — Leitura de execução do sexto ensaio real

Registro pelo Desenvolvedor em 20/11/2026, por instrução expressa do supervisor
no pedido desta rodada, sobre `8b8eb3e`. Não constitui aprovação do marco nem
substitui a auditoria independente.

## §3(9): controle de passividade

O supervisor autorizou normalizar, em `comparar_passividade`, somente os
componentes de parâmetros `q` que variem entre as duas execuções SEM adaptador,
quando toda a diferença dos valores daquele cabeçalho se limitar a esses
parâmetros de listas de qualidade. A regex reconhece qvalues de 0 a 1, com até
três casas decimais. A normalização é local ao método/caminho e ocorrência.

Lista de idiomas, ordem, espaços, outros parâmetros, posições q estáveis,
quantidades de campos e pedidos e demais cabeçalhos conservam as comparações
anteriores. Se os controles divergirem além de q, permanece a regra anterior:
somente valores e multiplicidades vistos nos controles. Não há exclusão fixa
de `Accept-Language` ou de outro cabeçalho. Valores originais dos controles e do
adaptador continuam no diagnóstico, acompanhados dos valores normalizados.

Prova local: `item9.log`, rodadas 1 e 2, controles respectivamente q=0.6/0.7 e
q=0.5/0.6, adaptador q=0.8 e q=0.9, sempre `pt-BR,pt` nos mesmos quatro pedidos.
A atribuição dessa variação ao fingerprinting do Brave é a premissa informada
pelo supervisor; os JSONs demonstram a variação sem adaptador, não o mecanismo
interno do navegador.

## §2.7 e §3(7): encerramento e recuperação

Após encerrar o navegador pelo caminho existente, aguardar até 15 segundos por
chamada pelo processo principal e por todos os processos locais cujo argumento
`--user-data-dir` identifique exatamente o perfil da sessão. Enumerar por
PowerShell local/CIM, somente leitura, sem perfil pessoal ou janela visível;
nenhum processo é encerrado por resultado dessa enumeração. A contenção Job já
existente e o encerramento do principal continuam responsáveis por terminá-los.
Enumeração indisponível ou prazo vencido não provam saída.

A limpeza/reabertura confirma novamente a ausência desses processos antes de
remover. Faz no máximo 20 tentativas de remoção, com 100 ms entre tentativas
(até 1,9 s de espera adicional, sem incluir o tempo das operações de disco).
Falha preserva a sessão, tenta criar `.limpeza-pendente`, informa o caminho no
terminal e recusa. Se a marca não puder ser escrita, o nome `sessao-0089-*` sob
a raiz exclusiva continua identificando a sobra para recuperação na próxima
execução. A recuperação usa as mesmas verificações e não inicia outra sessão
se a sobra continuar bloqueada. Somente filhos diretos da raiz declarada com
esse prefixo podem ser removidos; links e junctions na entrada são recusados.

Esses prazos são por chamada: encerramento e limpeza são etapas distintas;
um encerramento que expire pode ser seguido de nova espera na limpeza final.
Não foi acrescentado método CDP ou dependência, nem alterado `transport.py`,
o critério de `verified` ou qualquer recusa de candidata.
