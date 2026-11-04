# Validador v2 dos gabaritos da Porta L (redução D5)

Implementa as seções 1 a 7.1 da matriz IL.1 (versão 2); a rodada 2 corrigiu os 17 achados do `parecer-validador-v2-r1.md` e a
rodada 3 corrigiu os 15 do `parecer-validador-r2.md`. A rodada 3 terminou com bloqueador
(`parecer-validador-r3.md`) e o supervisor decidiu **reduzir o que o validador DECIDE** em vez de ampliá-lo (seção "Redução D5"
do `relatorio.md`; resumo abaixo). É independente do código do verificador: lê só o conjunto (`.jsonl`), as evidências gravadas (`<sha256>.*`) e, se dados,
`fontes.csv` e `cobertura.json`.

**Redução D5 (resumo).** O validador confere FORMA e coerência mecânica; o juízo de mérito é da segunda camada (matriz 7.1:
revisão de TODOS os casos e de TODOS os mutantes). (1) Os mutantes não são mais gerados pelo validador: são ESCRITOS pelo
pesquisador em `mutantes.jsonl` e conferidos por `--mutantes` (esquema, caso de origem, mutantes obrigatórios, coerência
mecânica de `renumerado`, `caractere` e `data_trocada`); TODO mutante recebe `REVISAO_HUMANA (vi)`. `--gerar-mutantes` virou ajuda
opcional que grava só um RASCUNHO (`*.rascunho.jsonl`), nunca o arquivo congelado. (2) A cobertura é conferida só na forma;
o vínculo documental de cada situação é `REVISAO_HUMANA (v)`, sem inferência por proximidade textual. (3) Cinco verificações
que reprovavam gabarito correto passaram de `FALHA` a `REVISAO_HUMANA`: remissões com anexos, `Art.` maiúsculo em remissão,
células numéricas em PDF, prioridade de estilo inline e rubrica de anexo seguida de título minúsculo. Nenhuma outra `FALHA` foi
rebaixada.

**Princípio (matriz, seção 7.1).** O validador é condição NECESSÁRIA, não suficiente. Ele confere forma, integridade dos
bytes, recorte, identidade estrutural, esquema, famílias declaradas, independência e mutantes, e **falha fechado** sempre que
não puder decidir (extração inconclusiva, limite ou ato não identificado, construção de CSS ou de remissão não reconhecida
que decida o resultado). O que depende de juízo jurídico sai como `REVISAO_HUMANA` (linha própria, que não reprova sozinha,
mas é contada e listada) e vai à segunda camada: revisão de mérito caso a caso por revisor independente de quem montou o
conjunto (desenvolvimento: o auditor; reserva: revisor independente, sob o D6).

## Uso

```
python -I -X utf8 validar_gabaritos_porta_l.py <conjunto.jsonl> <pasta_evidencias> ^
    [--fontes fontes.csv] [--mutantes mutantes.jsonl] [--cobertura cobertura.json] ^
    [--gerar-mutantes mutantes.rascunho.jsonl] [--conjunto desenvolvimento|reserva] [--exploratorio]
```

Saída: uma linha `FALHA <id>: ...` por falha; `REVISAO_HUMANA <id>: (i)|(ii)|(iii)|(iv)|(v)|(vi) ...` (segunda camada); `ALERTA
<id>: ...` (contexto, não reprova); `INFO ...` (unidades por capacidade, hash do `mutantes.jsonl` conferido, total de pendências de revisão
humana); `INCOMPLETO ...` (só no modo exploratório); linha final `N casos, M falhas`. Falhas de conjunto usam como
identificador `conjunto`, `capacidade-x`, `cobertura`, `cobertura:<situação>`, `mutantes` ou `mutantes:<id>`; registro que não é
objeto JSON, na API direta, `registro-N`.

**Código de saída:** 0 só sem falha e com resultado completo; 1 com falha; 2 sem falha mas INCOMPLETO.

**Congelamento.** Sem `--exploratorio`, são OBRIGATÓRIOS e sempre conferidos: as contagens (seção 2), a composição do
conjunto (seção 5: desenvolvimento ≥ 40 casos; reserva ≥ 50 casos e ≥ 10 por capacidade), a cobertura (`--cobertura`) e a
conferência do `mutantes.jsonl` do pesquisador (`--mutantes`; o rascunho de `--gerar-mutantes` NÃO satisfaz a obrigação); a falta de qualquer um é FALHA. Com `--conjunto reserva` (ou, se omitido,
quando os casos são `R-*`), confere também que ≥ 40% dos casos (c) são `verificado_para_D`. `--exploratorio` dispensa
cobertura e mutantes, mas declara o resultado `INCOMPLETO` (código 2).

Dependências: `pypdf` (já no venv) e, opcionalmente, `fontTools` em `vendor/`. Sem `pypdf`, todo caso em PDF reprova. O PDF é
lido em modo `layout` (o modo simples insere espaços dentro de palavras); o modo simples vale em cada página em que o texto
do layout tem **menos de 60% do comprimento do texto simples** (inclui página vazia, mas também layout não vazio e truncado).
Extração de 400 páginas leva cerca de 3 minutos (pypdf).

`pytest test_validador.py` roda as regressões causais (fixtures sintéticas geradas em temporário FORA da pasta do
validador). `mutacao_causal.py` (com `mutacao_causal_r3.py`) prova a causalidade: remove uma verificação por classe numa cópia e
exige que algum teste falhe, sinalizando se a falha veio de erro interno em vez do aceite indevido (`mutacao_causal.json`).

## O que o validador GARANTE (mecânico)

**Esquema (seção 6).** Tipos validados ANTES de qualquer processamento (entrada malformada vira falha tipada, nunca
traceback; um erro interno no caso também vira `FALHA`, não derruba o conjunto). Campos obrigatórios; enums; datas ISO
válidas; `capturado_em` com data e hora válidas; ids únicos `L|R-<cap>-NNN` coerentes com `capacidade` e `conjunto`;
`norma_grande` igual por norma; coerência norma/citação; **citação com dispositivo** (artigo ou anexo); `caminho` pela
gramática hierárquica estrita (`art. N[-A]`, depois `caput` só no início ou um `§ N`/`parágrafo único`, depois um `inciso`
com algarismo romano válido, depois uma `alínea`; sem repetição nem inversão; `Anexo [X][, art. N | , tabela]`).

**Citação x caminho x posição.** A cadeia da citação (artigo, §, inciso, alínea, caput) tem de ser igual à do caminho
(`art. 156` é o artigo inteiro; `art. 156, caput` é só o caput). O recorte tem de começar exatamente na **posição estrutural**
do dispositivo do caminho: o § 1º do art. 156 nunca é aceito como § 1º do art. 157; o artigo do corpo nunca é artigo de anexo.

**Fonte.** Arquivo presente; SHA-256 confere; host da URL na allowlist; metadados contra `fontes.csv` (url, sha256,
capturado_em, status, tamanho). Sem `--fontes`, `ALERTA`.

**Extração.** HTML: só **elemento ou estilo inline** de rasura: `strike`, `s`, `del` (com ou sem atributos) e `style` do próprio
elemento com `line-through` efetivo (vale a última declaração de `text-decoration`/`text-decoration-line`; `!important` vence).
**Folha de estilo e cascata CSS NÃO são interpretadas** (nem `<style>`, nem folha externa): o texto de elemento com classe de
rasura conhecida (a que um `<style>` associa a `line-through`, ou de nome convencional: tachado, riscado, strike...) **fica no
texto** e o recorte que o contenha recebe `REVISAO_HUMANA (i)`. PDF: página a página; cabeçalho e rodapé de página só saem por
**identificação positiva e só nas bordas** (primeiras e últimas 3 linhas): padrão de furniture do DOU, numeração de página (a
linha inteira é o número; número sozinho só na linha mais externa) ou linha com **contador de página** (`Página 2`, `pág. 2 de 9`)
que se repete, com o contador mascarado, na mesma borda de ≥ 2 páginas. **Repetição, posição e falta de pontuação, sozinhas, não
identificam cabeçalho**: continuação normativa repetida na borda é preservada; linha repetida sem identificação positiva é
mantida e listada em `ALERTA` (se atravessar o recorte, ele reprova no confronto). Dispositivo, inciso, alínea e item nunca são
removidos. Extração sem nenhuma letra, ilegível, com caracteres não decodificados ou com mais da metade das páginas sem texto é
FALHA; **não há tamanho mínimo universal** (lei curta e integral vale).

**Comparação.** Uma só normalização (seção 7). Anotação editorial sai só da FONTE e só por padrão completo: parêntese com
verbo editorial **e** referência identificável a ato (espécie e número com ano, ou espécie e data), ou `(NR)`. `(Vide Lei)`,
`(Incluído no Regulamento interno)` e `(Redação dada pela Lei nº 7.777)` (sem ano) NÃO são anotação e permanecem na fonte
(logo, o gabarito precisa contê-los).

**Identidade do ato.** O cabeçalho do ato em vigor no ponto do recorte é achado pela estrutura, não só por maiúsculas: caixa
alta; caixa mista em início de período seguida de maiúscula (título); e **cabeçalho candidato** (ementa em minúscula, data
numérica, só o ano, ou sem ponto antes: espécie, número e data de ato em início de período ou depois de palavra de título e
seguido de maiúscula ou de verbo de ementa), que **nunca é atribuído ao ato anterior**: vira cabeçalho de ato com a identidade que
o texto traz e, diferindo da esperada, reprova o recorte (`o cabeçalho de ato mais próximo antes do recorte ... não corresponde`);
nunca remissão no meio da frase (`... Lei nº 5.172, de ..., art. 2º;`, `da Lei nº ...`, `a referida Lei nº ...`). Cabeçalho
repetido do mesmo ato (título de página) não é limite. A Constituição tem cabeçalho e `ato_no_documento`
próprios (`Constituição Federal de 1988`). Em publicação de **ato alterador** (família ≠ `original`), o texto do ato antes do
dispositivo tem de mencionar a norma consultada (relação documental ato alterador, norma alterada, dispositivo). Em (a), fonte
compilada reprova (não prova a primeira publicação).

**Recorte.** Trecho contínuo; começa pelo identificador COMPLETO; termina onde a fonte passa ao próximo dispositivo, divisão,
rubrica + dispositivo, ato, anexo ou fim. **Rubrica** é título reconhecível (`Da/Do/Dos/De...`, `Disposições...`, caixa alta, ou
Title Case como `Dever de Informar`); texto qualquer com inicial maiúscula (`Continuação normativa obrigatória`) NÃO é rubrica e
dá "limite desconhecido". Continuação com § / inciso / alínea do mesmo dispositivo é "dispositivo incompleto". O **término** do
recorte também é confrontado com a região estrutural do dispositivo: recorte que avança sobre irmão (§ 2º no pedido do § 1º;
inciso II no do inciso I), rubrica ou divisão seguinte, ou que traz no interior `Art.`/`§`/inciso do mesmo nível ou superior (ainda
que sem pontuação antes), ou que termina com título de rubrica, é FALHA. **Limite inconclusivo é falha mecânica**: `caput`
terminado em dois-pontos sem os incisos que o completam; `Anexo X, tabela` só vale se o recorte for o corpo inteiro do anexo (do
fim da rubrica e do título ao fim do anexo); frase do interior do anexo reprova.

**(d).** O anexo é identificado pela rubrica `ANEXO [I|1|único]` ou `Anexo [I|1|único]` (caixa alta ou mista, em início de
período e, em caixa mista, seguida de título e não de minúscula; `conforme Anexo I` no meio da frase é remissão) e confrontado
com citação e caminho (`Anexo IX` inexistente reprova). Aceita-se: artigo do anexo, **anexo inteiro** (do `ANEXO` até o ato
seguinte ou o fim; recorte menor é "anexo incompleto") e `Anexo X, tabela` (só o corpo inteiro; a aderência semântica fica em
`REVISAO_HUMANA (v)`).

**(e).** `alvos` é comparado com a lista de remissões expressas que o parser **resolve**: listas de artigos, faixas `arts. 10 a
12` (todos os artigos), listas de §§, incisos e alíneas antes ou depois do artigo, `caput` (`art. 10, caput` ≠ `art. 10`),
`inciso IV do caput do art. 1º`, `§ 1º deste artigo` e `no § 1º` (artigo do próprio dispositivo), obra herdada em enumerações.
Lê também `art 5` (sem ponto) e faixas com `a` ou `até`. Remissão resolvida ausente de `alvos` é FALHA. Construção que o parser
não resolve (`artigo anterior/seguinte/subsequente`, `inciso precedente`, `art. 4 e seguintes`, faixa de §§ `1º a 3º`, `parágrafo
segundo`, anexo e item de anexo, faixa com sufixo `3º a 5º-A`, `incisos I e II` sem artigo, `deste artigo` solto) não reprova
nem aprova: `REVISAO_HUMANA (ii)`. **Referência parcialmente interpretada** (qualificador antes do artigo que o parser não leu,
`e seguintes`) não impõe alvo superficial e não reprova o alvo completo: só vai a (ii). `alvos_equivalentes`: só forma alternativa
do MESMO alvo (mesma obra canônica e mesmo caminho); alvo distinto reprova. **Citação** inequívoca e integralmente interpretada:
dois artigos, duas normas, `item`, faixa aberta ou qualquer palavra que sobre depois de lidos artigo, subdispositivos, anexo e obra
reprovam (falha fechado).

**(c).** `verificado_para_D`: o ato do evento (a obra, se `original`; o ato alterador, se não) tem **data demonstrada** (cabeçalho
ou anotação com data) e D ≥ essa data (data só pelo ano não sustenta D dentro do ano). `nao_verificado_para_D`: motivos só nos
permitidos; `fontes_consultadas` válidas; `trecho` localizado **dentro do dispositivo citado** (cabeçalho, outro artigo ou texto
genérico reprovam); com `sem_versao_oficial_na_data`: `cadeia` = lista de `{ato, data}` canônicos, ordenada, cada ato
**documentado em relação ao dispositivo** (nas anotações do dispositivo, ou ato de fonte que mencione a norma) e com a data
conferida (folga de publicação de 45 dias), e `ultima_versao_anterior` = `{ato|"original", data}` documentada, anterior a D e ao
primeiro ato da cadeia. `nao_existia_em_D`: `anterior_a_obra` (D < data da obra no cabeçalho) ou `anterior_a_inclusao` (D <
data do ato que incluiu; anotação registra a inclusão por esse ato; **qualquer** ressalva de vigência, produção de efeito, veto ou
revogação reprova, inclusive `(Vigência)` sem ato e `Vetado`/`Revogado` no texto).

**(b) `revogado_vigente`.** Anotação `(Revogado pela/pelo ...)` NO dispositivo citado e dispositivo **inteiro** revogado (só o
identificador e a anotação na extensão do dispositivo); revogação parcial (caput vigente, § revogado) nunca vale como revogação
do artigo inteiro (a do § vale para o § citado).

**Casos sem texto** (`revogado_vigente`, `nao_verificado_para_D`, `nao_existia_em_D`): o dispositivo é localizado
estruturalmente na fonte oficial e passa por ato, relação, página e família, como os demais.

**Famílias e independência (seção 2).** `original` ou identificador canônico; nunca o da própria norma; sem sufixos. Em
compilada: `familia_fundamento` obrigatório; só as anotações que **dão redação** (`Redação dada`, `com redação dada`,
`Incluído`, `Acrescido`, `Acrescentado`) definem o evento (e `Revogado` no caso de revogação); `Vide`, `Vigência`, `Produção de
efeitos`, `Vetado` não. Unidade = **evento**: o identificador canônico normalizado (sem zeros à esquerda) do ato; a publicação
da lei alteradora e a redação que ela deu a outra lei são o MESMO evento. Representante = menor id **entre todos os casos da
unidade, fixado antes de avaliar resultados**: se ele falha, a unidade não conta (não passa para o seguinte). ≥ 8 unidades e ≥ 4
normas por capacidade.

**Cobertura (só forma).** As situações obrigatórias `lsa_156`, `lsa_254a`, `lsa_289`, `cc_421`, `cc_1031`, `ctn_185`, `rasura`,
`sem_rasura`, `revogacao`, `mp_reeditada`, `mp_convertida`, `anexo`, `remissao`, `data_anterior_a_publicacao` têm de estar
presentes em `cobertura.json`, cada uma com `casos` não vazio, `evento` e `esperado` preenchidos; os casos citados têm de existir
e estar aprovados na triagem (sem `FALHA` de validação). Nada mais: o vínculo documental de cada situação (se os casos citados
exercitam a situação) é `REVISAO_HUMANA (v)`. Foi retirada toda inferência por proximidade textual (conversão de MP por janela de
caracteres, rasura por vizinhança).

**Mutantes (forma e coerência mecânica; o pesquisador os escreve).** Cada linha de `mutantes.jsonl` tem `id` (único), `caso`
(caso de origem, que tem de existir), `tipo` (`renumerado`, `caractere`, `data_trocada`), `chamada` (`funcao`
`obter_dispositivo|verificar_citacao` e `parametros` exatos, com `citacao`) e `esperado` (resultado esperado, não vazio). O
validador confere: todos os casos têm os mutantes obrigatórios da seção 3 (`renumerado` em todos; `caractere` nos que têm
`gabarito.texto`; `data_trocada` em (b) e (c) que declaram `data_mutante`) e no máximo um de cada tipo por caso; função coerente com
a capacidade (renumerado) e `verificar_citacao` (caractere e data_trocada); `renumerado` traz `destino {citacao, caminho}`
declarado, com citação da chamada igual à do destino, destino diferente do original (citação e dispositivo) e o dispositivo
declarado presente na fonte do caso (sem julgar se é o conteúdo pedido); `caractere` com `trecho` que difere do gabarito em
exatamente um caractere; `data_trocada` com `data_mutante` ISO válida igual à do caso, `data` da chamada igual a ela, `trecho` igual
ao gabarito e referência à redação alternativa declarada no caso (`redacao_alternativa: {ato}` igual ao `ato` do caso; sem
`redacao_alternativa` no caso, `base: "anterior_a_obra"`). Registro `rascunho: true` e arquivo `*.rascunho.jsonl` reprovam. TODO
mutante vai a `REVISAO_HUMANA (vi)`: se a expectativa de rejeição vale para o conteúdo efetivo da chamada (corpo de tabela, `trecho`,
redação integral na data) e, no `renumerado`, se o destino não é o conteúdo pedido. `gerar_mutantes` (ajuda opcional) devolve
`(rascunho, avisos, erros)` e, com `saida`, grava só `<saida>.rascunho.jsonl` (determinístico); nenhum caminho do validador grava o
`mutantes.jsonl` congelado.

## O que FICA PARA A SEGUNDA CAMADA (`REVISAO_HUMANA`, não reprova sozinha)

- **(i)** em todo caso (a) e todo `verificado_para_D`: se o documento aceito é de fato a publicação original ou a versão
  oficial válida em D (nenhuma alteração intermediária entre o ato do evento e D); em compilada com ressalva de vigência.
- **(ii)** remissões: construção que o parser não resolve; confirmar que `alvos` é a lista completa.
- **(iii)** todo `nao_verificado_para_D`: se as fontes demonstram o limite afirmado (período sem versão oficial identificada, não
  ausência de publicação num dia) e se a cadeia é suficiente.
- **(iv)** TODO caso com família, inclusive `original` (a ausência de anotação reconhecida não prova que a redação seja a
  original): se é o evento normativo certo; redação de mais de um ato; MP cuja anotação nomeia a lei de conversão.
- **(v)** vínculo documental de TODA situação da cobertura; `caput` isolado (sem dois-pontos); corpo de anexo como tabela citada;
  e as leituras alternativas da redução D5: `Art.` capitalizado lido como remissão no interior do recorte, linhas só de número ou
  contadores de página removidos de PDF (célula numérica de tabela?), estilo inline com `!important` em `text-decoration`, e
  rubrica de anexo em caixa mista seguida de título que começa por minúscula. Nesses casos o gabarito que a leitura principal
  reprovaria é aceito pela leitura alternativa, com esta revisão; a leitura principal continua sendo a que decide as demais FALHAS.
- **(vi)** TODO mutante de `mutantes.jsonl` (validade da expectativa de rejeição para o conteúdo efetivo da chamada; destino do
  `renumerado` que não seja o conteúdo pedido).
- **(ii)** também: alvo de anexo (`Anexo I`, `Anexo I, art. 1º`) em `alvos`, que o parser de remissões não resolve.
- **(i)** também: recorte com texto de elemento de classe de rasura conhecida; `data_mutante` com redação alternativa.
- Fora das categorias (continuam `ALERTA`): termos suspeitos, tamanho e `vide` no gabarito; Planalto; linhas removidas de PDF;
  `data` fora de (c); campos fora do esquema; que o texto da fonte oficial é, ele próprio, correto (o hash prova bytes).

## Escolhas de interpretação (a conferir pelo titular/revisor)

1. `www.normas.leg.br` foi aceito além da allowlist literal (mesmo órgão; aparece em `fontes.csv`).
2. Anotações editoriais usadas pela compilada da Câmara além da lista literal da seção 7: `(Parágrafo único acrescido pela …)`,
   `(Artigo com redação dada pela …)`, `("Caput" do artigo com redação dada pela …)`, `(Inciso acrescido …)`; sempre com referência
   identificável a ato (espécie, número e ano, ou espécie e data; data `d/m/aaaa`, `1º/7/2025` ou por extenso). Anotação sem ano não é
   reconhecida (e então o dispositivo não valida na compilada até o texto conter o parêntese ou o ano constar).
3. Campos que a matriz não fixa: `gabarito.condicao_inexistencia`, `fontes_consultadas`, `ultima_versao_anterior` (`{ato, data}`),
   `cadeia` (`[{ato, data}]`), `redacao_alternativa`, chave de `alvos_equivalentes` (`"<obra>, <caminho>"`), formato de
   `cobertura.json`, `numero` de MP reeditada (`2183-56`), caminho `Anexo X, tabela`.
4. Rubrica de anexo em caixa mista (`Anexo I`) só em início de período e seguida de título; `Anexo I` seguido de minúscula é
   remissão. Mutante `renumerado` de anexo só pelo número seguinte do anexo (matriz, seção 3): artigo de anexo cujo anexo seguinte
   não traz o mesmo dispositivo fica sem mutante obrigatório e o caso reprova.
5. Folga de 45 dias entre a data do ato e a da versão oficial (publicação no Diário Oficial) em `cadeia` e `ultima_versao_anterior`.
6. Em cobertura, `revogacao` por caso (c) e `mp_convertida` com vínculo documental de conversão da MP exata são as modalidades
   mecânicas admitidas. Campo novo `redacao_alternativa.texto` (rodada 3).
7. Quebra de palavra composta no fim da linha de PDF é recomposta (`higiênico-\nsanitários`); hifenização silábica não (FALHA, conservador).

## Limites conhecidos (honestos)

- A posição estrutural vale para o que o texto extraído da fonte deixa distinguir (marcadores `Art.`, `§`, `I -`, `a)`, divisões,
  cabeçalhos): fonte cujo texto perde esses marcadores reprova ("não localizado estruturalmente"), nunca é presumida.
- O parser de remissões não substitui a leitura: o que ele não resolve costuma ir a `REVISAO_HUMANA (ii)`, mas há construções
  residuais silenciosas (parecer r3, achado 11: `arts. 4º/5º desta Lei` gera só o alvo do art. 4º; `a) ... e b) ...` sem pontuação
  antes de `b)` passa como só a alínea `a`). A revisão de TODOS os casos (7.1) é quem as pega.
- A relação ato alterador x norma alterada é mecânica só até "o ato menciona a norma antes do dispositivo"; o evento certo é (iv).
- Datas de ato só por ano (`de 2001`) não sustentam afirmações que dependam do dia.
- **Limitações registradas na redução D5 (achados 9 a 12 do parecer r3, não corrigidos por não ampliarem o escopo):**
  - (9) cabeçalho de ato fora dos padrões reconhecidos (`Decreto 7/2020` sem `nº`, `Decreto nº 7, de 01-01-2020`) é atribuído ao ato
    anterior; um artigo exclusivo do outro ato passa como do primeiro (o `(i)`/`(iv)` e a revisão de mérito de cada evidência cobrem).
  - (10) listas e faixas de dispositivos com identificador compartilhado na CITAÇÃO (`art. 1 e 2`, `art. 1, 2`, `art. 1/2`, `art. 1 a 2`)
    são aceitas como dispositivo único quando caminho e gabarito são só os do art. 1º.
  - (11) construções residuais silenciosas em remissões e limites (ver acima).
  - (12) a prova causal (`mutacao_causal*.py`) mostra que ALGUM teste falha ao retirar a verificação, não que o aceite indevido
    ocorra: não distingue diagnóstico, exceção e mudança de aceitação (ex.: `a14_timestamp` continua reprovado por divergência com
    `fontes.csv`; `RuntimeError` não é contado como erro interno). Os scripts não foram regenerados na D5.
  - O achado 2 do parecer r3 (alternativa temporal truncada: `redacao_alternativa.texto` aceita fragmento) não é mais usado para
    GERAR mutante; o caso continua conferido por `checa_data_mutante` e o mutante `data_trocada` é revisado na segunda camada (vi).
- `--gerar-mutantes` (rascunho) conserva as heurísticas da r3 (destino com texto efetivo diferente, troca de letra central); a r3
  mostrou que a comparação por região documental pode mascarar igualdade de tabelas e que um fragmento pode representar outra
  redação integral. O rascunho é ponto de partida para o pesquisador, nunca prova.
