# 0089 — Leitura de execução do Parecer Terra r1

20/11/2026. Registro do Desenvolvedor, por instrução expressa do supervisor
nesta rodada, sobre `4493d5f`. Esclarece a aplicação da especificação; não
constitui decisão arquitetural autônoma nem aprovação do marco.

## §2.7 e §3(6): cabeçalhos da captura assistida

Antes de construir `Response` ou `CapturaAssistida`, a porta valida o
Content-Type independentemente do BOM, do meta e da interpretação do corpo.
Só admite zero ou um parâmetro, de nome `charset`. Duplicata, mesmo idêntica,
parâmetro desconhecido, rótulo desconhecido, codec sem implementação, espaços
no rótulo, aspas simples ou curvas e quoted-pair são recusados. Aspas duplas
HTTP simples em torno de rótulo admitido são aceitas e removidas.

O conjunto fechado é o da tabela WHATWG já usada pela interpretação única,
excluídas as entradas sem codec. A resolução usa `codecs.lookup(codec).name`
e a comparação com o mapa fechado desses nomes canônicos. Publica-se somente
o media type minúsculo admitido pelo perfil e o nome canônico WHATWG associado
ao codec: assim `LaTiN1` continua significando `windows-1252`, sem mudar a
interpretação anterior. Não se publica o nome de entrada nem a forma bruta.

O mesmo Content-Type canônico alimenta a interpretação e o recibo HTTP,
além de `Response.content_type`. O store, as evidências públicas e o snapshot
herdam essa representação. Recusas usam códigos fixos, sem o valor recusado.
O caminho automático e a interpretação textual preexistente não mudam.

## §3(9): descontos remanescentes de passividade

1. **q de Accept-Language:** somente o nome do campo é reconhecido sem
   distinção de caixa. Só posições de q que variem em dois a quatro controles
   SEM adaptador podem ser normalizadas. O qvalue deve ter sintaxe de 0 a 1,
   com até três casas decimais. Idiomas, ordem, espaços, demais parâmetros,
   posições q estáveis e número de campos permanecem literais. Justificativa:
   variação independente demonstrada nos controles e autorizada na nota do
   sexto ensaio. Nenhum outro campo recebe essa normalização, inclusive Accept.
2. **Ordem de chegada:** havendo variação nos controles, a sequência de
   método/caminho com adaptador deve ser exatamente uma sequência observada
   neles. Não se admite permutação nova. Justificativa: a variação observada
   estabelece alternativas concretas, sem autorizar ordem arbitrária.
3. **Demais valores e ordem dos cabeçalhos:** para cada método/caminho,
   a sequência completa de tuplas normalizadas deve reproduzir um controle.
   Valores diferentes são alternativas literais já observadas; não são
   excluídos da condição de aceite. Preservam-se nomes, presença, ordem dos
   campos, campos repetidos, multiplicidades e ordem das ocorrências do mesmo
   pedido. Não se combinam campos de controles diferentes nem se ordenam
   silenciosamente ocorrências para esconder nova permutação. Justificativa:
   permitir exclusivamente a variante concreta que ocorreu SEM adaptador.

Não há exclusão fixa de favicon, campo, valor ou pedido. Os dados originais,
as diferenças e a justificativa de cada desconto observado ficam no
diagnóstico. A ordenação de multiconjuntos usada para apresentar diferenças
nunca governa o resultado de `comparar_passividade`.

## §2.7 e §3(7): encerramento e enumeração CIM

O traceback de `C:\dev\tmp\v5\impl-b\nav-8.log`, linhas 42–124, localiza
a falha na saída do contexto do primeiro controle `sem1`, em
`fechar_navegador -> aguardar_saida_navegador -> _processos_do_perfil`.
A chamada recusada recebeu somente 3,793946700003289 s do prazo de 15 s.
A execução do controle chegou ao teardown; o traceback não aponta falha de
bind da porta nem lançamento. Os resets de conexões em stderr são posteriores
e não são a exceção que fez o teste falhar.

O código consultava o estado do principal ANTES de executar CIM. Uma consulta
lenta podia tornar esse estado obsoleto e obrigar outra consulta com o prazo
residual, mesmo com a enumeração vazia e o principal já encerrado. Esse defeito
foi reproduzido com relógio e processos sintéticos. Agora o estado é conferido
após CIM; além disso, a espera do principal antecede a primeira enumeração,
evitando gastar o prazo com consultas precoces. Só depois se comprova a
ausência dos processos do perfil. O limite de 15 s e a recusa em qualquer
ausência de prova permanecem; não há aumento de prazo, retry após falha,
skip de limpeza nem tratamento de erro como ausência de processos.

O log antigo suprime a exceção original de subprocesso/JSON. Não permite
concluir retrospectivamente qual ocorreu, nem atribuir o problema a vazamento
de processo, perfil ou interferência de outro caso. Timeout e falha do
PowerShell passam a emitir respectivamente os sufixos fixos `_PRAZO` e
`_PROCESSO`; cmd, stdout/stderr e linhas de comando nunca são exibidos.
Não se isola caso com base numa interferência não demonstrada.

O reensaio completo em navegador continua necessário para validar a causa
operacional do oitavo ensaio. As regressões offline demonstram a eliminação
da consulta prematura e da repetição causada por estado obsoleto; não
substituem essa prova real.
