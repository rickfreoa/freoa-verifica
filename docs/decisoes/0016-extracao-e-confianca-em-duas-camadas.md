# Extração estrutural e confiança em duas camadas

Data: 18/10/2026. Substitui a decisão 0015 quanto à associação posterior e às expectativas de extração. Mantém os requisitos de captura, autenticação e confronto para `verified`.

A lista positiva de verbos perdia citações explícitas em prosa sem impedir prefixos de numeração privada, identificadores compactos e transferência de dispositivos entre normas. A extração passa a propor interpretações estruturais; a confiança limita o status que essas interpretações podem receber.

## Extração

O número de artigo ou item deve terminar em fronteira de token. Numeração decimal com uma ou duas casas depois do ponto pertence à estrutura de instrumento privado e não pode ser truncada em artigo inteiro. Três casas são separador de milhar: `1.022` e `1.142` continuam artigos. Cláusulas não são promovidas a dispositivos normativos. Siglas e números colados, ou números imediatamente seguidos de letra, não identificam norma.

A cadeia anterior exige controle de pertença e não pode reutilizar intervalo já associado à norma precedente. Sem conector explícito de pertença, uma cadeia imediatamente posterior a outra norma não é transferida para a seguinte. Isso preserva os dois artigos em enumerações de normas.

Depois da norma, a cadeia pode terminar em pontuação, fim do texto, vírgula seguida de palavra sem marcador de pertença ou continuação de prosa. Não há catálogo de verbos ou instrumentos. Uma continuação lexical sem vírgula é conservada como proposta de proximidade, pois a sintaxe isolada não demonstra sua função verbal. A construção possessiva `em seu` também produz proposta.

Parênteses e travessões imediatamente posteriores à norma exigem par e conteúdo composto somente pela cadeia. Delimitador sem par ou texto adicional dentro desse par impede a associação. Parênteses que envolvem toda a referência seguem o balanço da abertura anterior à norma.

As preposições `do/da/dos/das/de/no/na/nos/nas` e contrações demonstrativas impedem atribuir à norma um dispositivo com complemento não normativo. Os marcadores `pertencente`, `constante`, `inserid*`, `previst*` e `integrante` também impedem essa associação, inclusive em predicado posterior. Anexo, capítulo ou caput podem delimitar a divisão da mesma obra, sujeitos ao mesmo controle do complemento seguinte. Pertença explícita a outra norma prevalece sobre a proximidade com a anterior.

## Confiança e status

Toda citação tem `confidence` igual a `exata` ou `provavel`. A forma posterior canônica é norma, vírgula, `art. N`, eventualmente parágrafo e inciso, seguida de terminador. Essa estrutura pode ser `exata` se a própria identidade da norma for exata. Vínculo anterior com pertença explícita também pode ser exato. Ano ausente e alias ambíguo conservam sua confiança provável.

Associações posteriores fora dessa forma, prosa, delimitação pareada, divisões adicionais e vínculos sem pertença explícita são `provavel`. Não se promove uma proposta a exata porque o artigo proposto existe no acervo. Uma obra reconhecida cujo dispositivo foi rejeitado permanece citação da obra; a omissão do dispositivo é contabilizada no recall.

Em `verificar_texto`, toda citação provável recebe `requer_conferencia`, inclusive quando o confronto da interpretação proposta encontra o dispositivo ou produz negativa documentada. A identidade pública dessa linha permanece `unknown`, com motivo `ASSOCIACAO_REQUER_CONFERENCIA`. O objeto `conferencia` contém interpretação proposta, alternativas de norma sem dispositivo e dispositivo de outro referente, evidência disponível e confronto da proposta. Esse confronto não decide a pertença. Citações exatas mantêm os requisitos anteriores para `encontrada` e `inexistente`.

## Regressão e medição

Os oráculos originais das quatro rodadas de prosa são preservados e medidos separadamente e em conjunto. As expectativas restritivas da decisão 0015 deixam de substituir os oráculos históricos. Duas propostas historicamente divergentes, C062 e C076, são testadas como prováveis e exigem conferência no serviço.

Os testes anteriores que admitiam travessão sem par passam a exigir somente a obra. O conjunto anterior denominado canônico também contém formas não canônicas pela regra atual; seus casos continuam testados, distinguindo a rejeição de delimitadores sem par. O recall exato canônico usa denominador definido pelo texto de entrada, sem selecionar casos pela resposta do extrator. Dispositivo omitido reduz recall; obra inventada ou dispositivo atribuído indevidamente conta como erro de extração. A taxa de erro exato divide os erros nas citações exatas pelo total de citações exatas.

O aceite exige zero status definitivos falsos, erro em extrações exatas de no máximo 1%, recall explícito conjunto de exatas e prováveis de pelo menos 95% e recall exato nas formas canônicas de pelo menos 98%. A propagação é exercitada com acervos sintéticos contendo todos os caminhos esperados e propostos e, separadamente, somente um artigo alheio. Os ensaios não demonstram acesso real às fontes nem mérito jurídico. O parecer adversarial independente permanece requisito para avanço do marco.
