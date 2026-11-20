**Veredito: BLOQUEADOR.** Encontrei um caminho de persistência de segredo no `Content-Type` e uma falha no teste de passividade. As duas reproduções usaram dados sintéticos, sem rede e sem gravar no repositório.

### 1. BLOQUEADOR — valor arbitrário de `charset` chega ao banco

**Local:** [transport.py](C:/dev/fv14-0089i/freoa_verifica/transport.py:876), [texto_resposta.py](C:/dev/fv14-0089i/freoa_verifica/texto_resposta.py:442), [repo.py](C:/dev/fv14-0089i/freoa_verifica/store/repo.py:90), [snapshot.py](C:/dev/fv14-0089i/freoa_verifica/snapshot.py:75).

**Cenário reproduzido:** uma resposta elegível contém `Content-Type: text/html; charset=TOKEN_SECRETO` e um corpo HTML iniciado por BOM UTF-8. A porta admite a captura e conserva o cabeçalho bruto em `Response.content_type`. A função usada por `save_capture` retorna esse mesmo valor para a coluna `capture.content_type`.

A reprodução pela porta real retornou:

```text
admitido: text/html; charset=TOKEN_SECRETO
coluna capture: text/html; charset=TOKEN_SECRETO
```

O cenário não gravou no banco; o caminho de gravação foi confirmado no código. Se o humano selecionar a captura, `save_capture` insere o valor na coluna, que também integra o snapshot.

**Causa e violação:** a porta verifica que o nome do parâmetro é `charset`, mas aceita seu valor arbitrário. Como o BOM determina a interpretação, `interpretar` não precisa reconhecer esse valor como codificação. Assim, o parâmetro pode transportar um segredo para um artefato persistente, contrariando a proteção de segredos da §2.7 e o teste da §3.6.

**Correção sugerida:** validar e canonizar o valor de `charset` antes de construir qualquer objeto persistível, independentemente de BOM ou de qual fonte determine a decodificação. Recusar valores não pertencentes a um conjunto fechado de codificações admitidas, ou persistir somente uma representação canônica segura. Aplicar a regra a todos os pontos de saída da captura assistida e acrescentar regressões com BOM, valores arbitrários, duplicatas, aspas e snapshots.

### 2. ALTO — teste de passividade aceita alteração de `q` em qualquer cabeçalho

**Local:** [harness_assistida_0089_cenarios.py](C:/dev/fv14-0089i/tests/harness_assistida_0089_cenarios.py:729).

**Cenário reproduzido:** para o mesmo `GET /x`, dois controles sem adaptador enviam, respectivamente, `Accept: text/html;q=0.6` e `Accept: text/html;q=0.7`; a execução com adaptador envia `Accept: text/html;q=0.1`. `comparar_passividade` retorna `passou=True`.

**Causa e violação:** embora a coleta procure variação em `Accept-Language`, a comparação chama `_normalizar_q_variavel` para **todos** os nomes de cabeçalho. A nota do sexto ensaio autorizou a normalização de posições `q` variáveis comprovadas nos controles para `Accept-Language`; a implementação também descarta diferenças em, por exemplo, `Accept`. Isso pode produzir um resultado verde para a prova de passividade da §3 item 9 sem que os pedidos satisfaçam o critério autorizado. O achado demonstra uma falha do teste, não uma alteração efetiva de requisição pelo adaptador.

**Correção sugerida:** limitar explicitamente a normalização ao nome `Accept-Language`, comparado sem distinção de caixa, e preservar literalmente os demais campos. Testar valores novos de `q` em outros cabeçalhos, além de posições estáveis e variáveis no mesmo `Accept-Language`. Revisar também os descontos existentes para ordem e valores variáveis dos controles contra o critério de igualdade aplicável.

### O que não consegui verificar

- Não executei navegador real, tráfego de rede, testes com outra conta Windows, instalação de extensão ou ensaios de limpeza: essas provas exigem efeitos externos ou gravações. Também não executei a suíte.
- Não demonstrei contorno da confirmação, acesso ao perfil pessoal, remoção fora do perfil da sessão, comando CDP fora da lista, extensão interceptadora admitida ou `verified` indevido.
- Na leitura da regra de streaming, não identifiquei uma sequência que, por si só, demonstre perda ou substituição de bytes. A conferência de comprimentos não prova independentemente o conteúdo de `bufferedData`: a identidade depende também da fidelidade dos eventos e bytes fornecidos pelo navegador confiável.
- A exceção para componentes `location 5` depende da premissa da especificação de que um caminho absoluto dentro da instalação identifica componente interno. Não demonstrei, em execução real, que uma extensão externa possa assumir essa identidade.
- Os registros de implementação apontam provas de aceite ainda pendentes, incluindo inventário real de gravações e acesso por segunda conta; esta revisão não supre essas provas.