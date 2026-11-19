# 0088 - Padrões de representação: FRBR pelo ELI, URN:LEX e ids LexML; Akoma Ntoso não

19/11/2026. Titular (Ricardo Peres Freoa), sobre avaliação do supervisor (Opus) da mesma
data. Não altera critério de `verified`, matriz, pisos, reserva, mutantes, contrato, código nem
a 0001. Fixa o modelo de referência que a normalização de caminhos, a pendência `hasPart`
multivigente (0085) e os próximos conectores devem seguir.

## 1. Fato

1. Nenhum padrão da OASIS LegalXML é usado. Não há Akoma Ntoso (LegalDocML), LegalRuleML nem
   LegalCiteM no código ou na documentação; FRBR não é nomeado.
2. URN:LEX (LexML Brasil, Parte 2) já é usada: `connectors/normas_leg.py` e
   `connectors/senado.py` montam e leem `urn:lex:br:federal:<tipo>:<data>;<número>`. Pela
   0001 §2, URN derivada não é identidade confirmada: a obra tem chave interna opaca e aliases
   com origem e estado (`store/repo.py`).
3. O vocabulário schema.org/Legislation já é consumido: o conector `connectors/normas_leg.py`
   lê `legislationIdentifier`, `encoding`, `version` (`Current`/`Original`),
   `legislationLegalValue` e `datePublished`. Esse vocabulário é a extensão do ELI ao
   schema.org; o ELI segue os princípios do FRBR (Publications Office da UE, ontologia ELI 1.4
   e seu alinhamento ao schema.org).
4. O modelo atual é parcialmente compatível com o FRBR, sem nomeá-lo. A 0001 §1 já separa
   texto consolidado de versão jurídica (dispositivo, redação e evento temporal; publicação,
   vigência e efeitos distintos). Há campos que correspondem a níveis do FRBR (chave da obra,
   redações por dispositivo, captura com URL, instante e `sha256`), mas não entidades
   separadas para cada nível: `ResolvedWork` reúne identidade, documento parseado e captura.
5. O caminho canônico interno de dispositivo (`ARQUITETURA.md`, `parsers/paths.py`) tem
   caput implícito sob artigo (`art5.inc3`), aceita caput explícito (`art5.caput`,
   `art5.caput.inc3`), usa `parunico` para parágrafo único, conserva literal a letra de
   inclusão (`art254-A`, `par1-A`, `inc2-A`) e a letra de alínea (`ali-a`), e tem escopos de
   anexo, ADCT e suplemento, inclusive aninhados (`tests/test_paths.py`). O caminho com caput
   explícito nasce do extrator de citações quando a referência menciona caput
   (`citation.py`); o parser da Câmara monta incisos sem esse segmento, mas distingue artigo
   agregado de caput (0079 §1). A normalização `artN.caput.incX → artN.incX` está pendente,
   com a ressalva de colisão com incisos de parágrafo (0077; `il2c-implementacao.md`).
6. LexML Brasil, Parte 3 (XML Schema 1.0 RC1, dez./2008), lido na fonte oficial: ids de
   dispositivo concatenam os níveis com `_`; o caput é segmento explícito sem número (`cpt`);
   romanos e letras viram arábicos, inclusive a letra de inclusão (`art8-1` para art. 8-A);
   exemplos `art8_cpt_inc3`, `art20_par2_inc2`, `art39_cpt_inc1_ali2_ite1`. O exemplo de
   parágrafo único é `par1`. Não há regra de id para anexos.
7. O LegalCiteM, comitê da OASIS para marcação de citações, foi encerrado em 09/02/2021.

## 2. Decisão do titular

1. **FRBR, pelo vocabulário ELI, é o modelo conceitual declarado.** Correspondência conceitual,
   que orienta especificações futuras e não afirma que cada nível já seja entidade própria:

   | FRBR / ELI | FREOA Verifica |
   |---|---|
   | obra (`eli:LegalResource`) | chave opaca da obra (`work_id`), `WorkKey`, dimensão de identidade |
   | expressão (`eli:LegalExpression`) | redação ou versão textual representada, com vigência possivelmente desconhecida |
   | manifestação (`eli:Format`) | documento da fonte num formato (HTML, PDF, DOCX, JSON) |
   | exemplar | a captura: URL, `fetched_at`, `sha256`, procedência |
   | parte (`eli:LegalResourceSubdivision`, `has_part`) | dispositivo pelo caminho canônico |

   A vigência em data D é conclusão da dimensão temporal sobre expressões, não a expressão.
   `encoding.version` (`Current`/`Original`) é metadado editorial da fonte, sem equivalência
   automática com expressão vigente (0002, 0085). Termo novo em código, campo de recibo ou
   documentação usa esses níveis: "redação" ou "versão textual" designa expressão; "captura",
   exemplar; nunca um pelo outro.
2. **URN:LEX é o identificador externo preferencial da obra**, registrado como alias com
   origem e estado (0001 §2), sempre que a gramática LexML a define. A chave interna continua
   opaca. URN montada pelo conector não comprova existência nem identidade, que continuam
   exigindo documento oficial capturado (regra invariável 1). Substituir a chave opaca pela URN
   exigiria alteração expressa da 0001 e plano de migração; não é decidido aqui.
3. **O caminho canônico interno não muda.** Recibos, capturas, fixtures e caminhos conhecidos
   (0034) dependem dele. Especifica-se, para implementação futura, uma conversão **parcial**
   para o id LexML (Parte 3), com estes requisitos:
   1. Domínio declarado: artigo, caput, parágrafo, inciso, alínea e item do corpo da norma.
      Anexo, ADCT e suplemento ficam fora até haver regra oficial ou decisão própria; caminho
      fora do domínio faz a conversão falhar de modo explícito, nunca descartar o escopo.
   2. A conversão opera sobre classes de equivalência com representante canônico declarado:
      `artN.incX` e `artN.caput.incX` exportam para `artN_cpt_incX`, que importa para o
      representante canônico da pendência de normalização. `cpt` só é suprimido na importação
      quando seguido de descendente (inciso e abaixo). `artN.caput` ↔ `artN_cpt` e `artN` ↔
      `artN` permanecem distintos (0079 §1).
   3. Letra de inclusão converte-se em número (A=1), com retorno literal.
   4. Parágrafo único fica **sem correspondência** até a conferência do item 5.1: com a regra
      do exemplo oficial, `parunico` e `par1` convergiriam para `par1` e a importação isolada
      não os distinguiria. Não se promete reversibilidade pelo id isolado onde ela não existe.
   5. A distinção LexML entre `artN_cpt_incX` e `artN_parY_incX` é requisito da implementação,
      não prova de que a normalização interna evita colisões. A ressalva da 0077 permanece até
      haver regressões que preservem artigo, caput, parágrafo e escopo na ida e na volta.
4. **Akoma Ntoso não é formato interno.** Nenhuma fonte consultada publica nesse formato;
   converter para ele interporia uma camada de interpretação entre a fonte e o confronto.
   Exportação em Akoma Ntoso só por demanda concreta e em decisão própria.
5. **LegalCiteM e LegalRuleML não são adotados.** O primeiro teve o comitê encerrado em 2021;
   o segundo modela regras como lógica, fora do escopo de verificação de fonte.

## 3. Execução e limites

1. Registro apenas. Nenhuma mudança de código nesta decisão.
2. A implementação (conversão de ids, termos FRBR, alias URN:LEX) entra com a normalização de
   caminhos ou com o primeiro conector que precisar dela. Pela 0087 §4, a normalização e o
   `hasPart` multivigente seguem congelados até a Porta A do STJ; ao serem retomados,
   especificam-se contra esta decisão. `ARQUITETURA.md` é atualizada no mesmo PR da
   implementação, para não rodar a matriz completa só por documentação.
3. A especificação do conector do STJ usa desde já a correspondência do item 2.1 e verifica se
   a gramática LexML define URN para acórdãos do tribunal antes de registrá-la como alias.
4. Hipótese a especificar com o `hasPart` multivigente: tratá-lo como relação entre
   subdivisões (dispositivos) e sucessão de redações, nos termos do item 2.1. A 0085 registra o
   uso de `hasPart` para aritmética temporal por dispositivo; não demonstra ainda essa
   classificação.

## 4. Objeções consideradas

1. *Formalizar agora gera trabalho sem ganho imediato.* O custo desta decisão é documental; o
   ganho é que o conector do STJ, próximo a ser especificado, nasça no modelo em vez de migrar.
2. *Adotar Akoma Ntoso daria interoperabilidade internacional.* A interoperabilidade útil ao
   Verifica é com as fontes brasileiras, que usam URN:LEX e schema.org/ELI. Exportação continua
   possível sem que o formato governe a verificação.
3. *Adotar os ids LexML como caminho interno eliminaria a conversão.* Trocaria uma conversão
   localizada e testável por uma migração de recibos, capturas e fixtures, perderia a letra
   literal, legível para o usuário, e herdaria a ambiguidade do parágrafo único.
4. *URN:LEX deveria ser a chave da obra.* A 0001 §2 recusou URN derivada como identidade; o
   alias com origem e estado dá o ganho de interoperabilidade sem esse risco.

## 5. Questões abertas

1. Parágrafo único: o exemplo oficial (RC1) usa `par1`; há uso secundário de `par1u`. Conferir
   as expressões regulares de `idArtigo` no `lexml-br-rigido.xsd` (Anexo 2 da Parte 3) antes de
   fixar a correspondência.
2. Anexos, ADCT e suplementos: a Parte 3 não define id para anexos. Manter os escopos do
   caminho interno sem correspondente LexML até haver regra oficial.
3. Versão vigente do esquema LexML posterior à 1.0 RC1, se houver.

## 6. Fontes lidas

- LexML Brasil, Parte 3 - LexML XML Schema, versão 1.0 (RC1), dez./2008
  (`projeto.lexml.gov.br/documentacao/Parte-3-XML-Schema.pdf`), regras de id de dispositivo.
- Publications Office da UE, ELI: ontologia 1.4, princípios FRBR e alinhamento ao
  schema.org legal extension (`op.europa.eu/web/eu-vocabularies/eli`; `eli-sdo.ttl`).
- schema.org, `legislationIdentifier` (aceita ELI ou URN-Lex).
- OASIS, arquivo da lista `legalcitem`: encerramento do comitê em 09/02/2021.
- Repositório em `9d97ab4`: decisões 0001, 0002, 0034, 0077, 0079, 0085 e 0087;
  `connectors/normas_leg.py`, `connectors/senado.py`, `verify.py`, `store/repo.py`,
  `parsers/paths.py`, `citation.py`, `connectors/camara_legin.py`, `tests/test_paths.py`;
  `docs/auditoria/1.4.0/il2c-implementacao.md`.
- Parecer do auditor (Codex, somente leitura), rodada 1: BLOQUEADOR, dez achados, todos
  incorporados nesta redação.
