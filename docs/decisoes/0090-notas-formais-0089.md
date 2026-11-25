# 0090 - Notas formais à 0089: manifesto de componente, ordem do streaming e comparação de passividade

Estado: aprovada pelo titular em 20/11/2026 (3.1, 3.2 e 3.3, sem ressalva). Base: auditoria Codex independente r1
(`docs/auditoria/0089/parecer-codex-r1.md`), que propôs as três redações e examinou as duas primeiras sem encontrar
caminho de admissão indevida; ensaios reais de 19 e 20/11/2026 (`docs/auditoria/0089/ensaios-reais.md`).

## 1. Problema

A 0089 fixou três regras sobre fatos de navegador que o laboratório de 19/11 não mediu. Os ensaios reais no Brave 1.100
(Chromium 158) mostraram que, lidas literalmente, duas delas tornam a sessão assistida inviável e a terceira torna
inviável a prova da passividade. Nos três casos, o erro está na premissa de fato, não no propósito da regra. Até aqui, a
implementação segue leituras de execução do supervisor, que não têm autoridade para emendar a especificação. Esta
decisão as converte em texto normativo, ou as rejeita.

## 2. Premissas verificadas

1. **Componentes do navegador.** O Chromium embute as extensões de componente nos recursos do binário. No Brave 1.100,
   as duas existentes (`Chrome PDF Viewer` e `Brave`, `location` 5) apontam para caminhos absolutos dentro da
   instalação, sem `manifest.json` em disco. O próprio navegador grava o manifesto em
   `extensions.settings.<id>.manifest`, nas preferências do perfil (diagnóstico de 20/11).
2. **Ordem do streaming.** No documento principal, o navegador emite `Network.dataReceived` sem `data` antes de
   responder a `Network.streamResourceContent`; a resposta traz em `bufferedData` exatamente os bytes daquele evento;
   os eventos seguintes trazem `data`. Em `fetch` e XHR, a resposta vem primeiro e o último `dataReceived` chega sem
   `data`, com `dataLength` 0 (rastreamentos do 3º e do 4º ensaio).
3. **Variação do navegador entre sessões.** O Brave sorteia, a cada sessão, o parâmetro `q` do `Accept-Language`
   (valores de 0,5 a 0,9 observados), com ou sem depurador anexado (6º ao 9º ensaio). A comparação literal de
   cabeçalhos, exigida pelo §3 item 9, falha por causa do navegador, não do adaptador.

## 3. Decisão

### 3.1 Manifesto de componente (emenda à 0089 §2.2(3)(c))

Para extensão com `location` 5 cujo caminho, originalmente absoluto, resolva para dentro do diretório de instalação do
navegador lançado, a ausência de `manifest.json` permite usar o objeto `extensions.settings.<id>.manifest` das
preferências do perfil dedicado. Exige-se objeto JSON válido. Erro de leitura ou manifesto inválido em disco não
autoriza o recurso às preferências. A regra não alcança extensão comum, componente externo (`location` 10), caminho
relativo nem componente fora da instalação; `active_permissions` não substitui o manifesto.

### 3.2 Ordem do streaming (emenda à 0089 §2.5(2) e ao §3 item 1)

O comando `Network.streamResourceContent` continua obrigatório no `requestWillBeSent` e continua a ser a única fonte de
bytes; `Network.getResponseBody` permanece excluído. Sua resposta não precisa preceder o primeiro `dataReceived`. Antes
dela, só se admitem eventos sem `data`, com contadores e reservas imediatos, e o `bufferedData` decodificado deve ter
tamanho exatamente igual à soma dos `dataLength` anteriores. Depois dela, cada evento traz `data` cujo tamanho
decodificado é igual ao seu `dataLength`; evento sem `data` só se admite com `dataLength` 0, mantido o
`encodedDataLength` nos confrontos. Erro do comando, término anterior à resposta, divergência de tamanho ou limite
excedido recusam a candidata, sem alternativa. Permanecem os prazos e os confrontos finais da §2.4, linha 7. "Streaming
iniciado tarde", no §3 item 1, passa a significar término do carregamento ou erro antes da resposta ao comando.

### 3.3 Comparação de passividade (emenda ao §3 item 9)

A igualdade dos pedidos vistos pela origem, com e sem o adaptador, admite somente variações demonstradas em dois a quatro
controles sem adaptador, executados até que a variação apareça. Só se normalizam posições do parâmetro `q`,
sintaticamente válidas e variáveis entre os controles, no cabeçalho `Accept-Language`, no mesmo método, caminho e
ocorrência. Idiomas, ordem, demais parâmetros e todos os outros cabeçalhos permanecem comparados literalmente.
Variações de ordem ou de valor precisam reproduzir alternativas efetivamente observadas nos controles, com as mesmas
multiplicidades. Os dados originais e cada desconto integram o diagnóstico do teste.

## 4. Objeções e por que não prevalecem

1. *"As emendas afrouxam regras de segurança."* Não afrouxam. Em 3.1, a confiança no componente embutido já fora
   decidida pelo titular em 19/11 (componentes dentro da pasta do navegador são parte dele); muda só a fonte do
   manifesto, que é o próprio navegador. Em 3.2, a prova de identidade dos bytes continua integral: todo byte vem do
   streaming, e a contabilidade por evento detecta falta ou excesso. Em 3.3, nenhuma diferença produzida só com o
   adaptador é tolerada.
2. *"Em 3.2, igualdade de tamanho não prova igualdade de conteúdo."* É verdade, e a 0089 já o assume: o conteúdo depende
   do navegador, parte confiável por premissa declarada (§2.2). A regra corrigida não amplia essa dependência; só deixa
   de exigir uma ordem que o navegador não produz.
3. *"Em 3.3, uma alteração do adaptador poderia coincidir com o sorteio."* Só no `q` do `Accept-Language`, e só dentro
   do intervalo que o próprio navegador já mostrou nos controles. Uma alteração que dependa de coincidir com um sorteio
   do navegador não é meio idôneo de interferir na requisição; e o adaptador não tem método CDP capaz de alterar
   cabeçalho (§2.12, lista fechada conferida estaticamente).

## 5. Alcance

A decisão emenda só os três pontos indicados. Não altera `verified`, a lista de métodos CDP, a matriz da §2.4 nem a
nota de escopo da 1.4.0a6. Substitui, como fundamento normativo, as notas de execução do supervisor
(`0089-nota-execucao-*.md`), que permanecem como registro histórico.

## 6. Decisão do titular

Aprovadas as três notas (3.1, 3.2 e 3.3), sem ressalva, por Ricardo Peres Freoa em 20/11/2026.
