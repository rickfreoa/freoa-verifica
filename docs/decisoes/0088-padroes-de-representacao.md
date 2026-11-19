# 0088 - Padrões de representação: FRBR pelo ELI, URN:LEX e ids LexML; Akoma Ntoso não

19/11/2026. Titular (Ricardo Peres Freoa), sobre avaliação do supervisor (Opus) da mesma
data. Não altera critério de `verified`, matriz, pisos, reserva, mutantes, contrato nem código.
Fixa o modelo de referência que as pendências 1 e 12 e os próximos conectores devem seguir.

## 1. Fato

1. Nenhum padrão da OASIS LegalXML é usado. Não há Akoma Ntoso (LegalDocML), LegalRuleML nem
   LegalCiteM no código ou na documentação; FRBR não é nomeado.
2. URN:LEX (LexML Brasil, Parte 2) já é usada: `connectors/normas_leg.py` e
   `connectors/senado.py` montam e leem `urn:lex:br:federal:<tipo>:<data>;<número>`.
3. O vocabulário schema.org/Legislation já é consumido: o parser de normas.leg.br lê
   `legislationIdentifier`, `encoding`, `version` (`Current`/`Original`),
   `legislationLegalValue` e `datePublished`. Esse vocabulário é a extensão do ELI ao
   schema.org; o ELI segue os princípios do FRBR (Publications Office da UE, ontologia ELI 1.4
   e seu alinhamento ao schema.org).
4. O modelo interno já separa, sem nomeá-los, os níveis do FRBR: `WorkKey`/`ResolvedWork`
   (obra), a dimensão temporal (redação vigente em data D), a captura com URL, data e
   `sha256` (manifestação e exemplar). A pendência 12 (`hasPart` multivigente) é um problema
   de relação parte-todo entre expressões.
5. O caminho canônico interno de dispositivo (`ARQUITETURA.md`, `parsers/paths.py`) tem caput
   implícito sob artigo (`art5.inc3`), `parunico` para parágrafo único e letra de inclusão
   literal (`art254-A`, `ali-a`). A Câmara emite caput explícito (`art16.caput.inc1`), daí a
   pendência 1.
6. LexML Brasil, Parte 3 (XML Schema 1.0 RC1, dez./2008), lido na fonte oficial: ids de
   dispositivo concatenam os níveis com `_`; o caput é segmento explícito sem número (`cpt`);
   romanos e letras viram arábicos, inclusive a letra de inclusão (`art8-1` para art. 8-A);
   exemplos `art8_cpt_inc3`, `art20_par2_inc2`, `art39_cpt_inc1_ali2_ite1`. O exemplo de
   parágrafo único é `par1`. Não há regra de id para anexos.
7. O LegalCiteM, comitê da OASIS para marcação de citações, foi encerrado em 09/02/2021.

## 2. Decisão do titular

1. **FRBR, pelo vocabulário ELI, é o modelo conceitual declarado.** Correspondência:

   | FRBR / ELI | FREOA Verifica |
   |---|---|
   | obra (`eli:LegalResource`) | `WorkKey`, `ResolvedWork.work_id`, dimensão de identidade |
   | expressão (`eli:LegalExpression`) | redação vigente em data D, dimensão temporal, `encoding.version` |
   | manifestação (`eli:Format`) | documento capturado num formato (HTML, PDF, DOCX, JSON) |
   | exemplar | a captura: URL, `fetched_at`, `sha256`, procedência |
   | parte (`eli:LegalResourceSubdivision`, `has_part`) | dispositivo pelo caminho canônico |

   Termo novo em código, campo de recibo ou documentação usa esses níveis. "Versão" designa
   expressão; "captura", exemplar; nunca um pelo outro.
2. **URN:LEX é o identificador canônico de obra** sempre que a gramática LexML a define. É
   identificador, não evidência: URN montada pelo conector não comprova existência nem
   identidade, que continuam exigindo documento oficial capturado (regra invariável 1). Ato
   sem URN:LEX definida mantém a `WorkKey`, sem URN improvisada.
3. **O caminho canônico interno não muda.** Recibos, capturas, fixtures e caminhos conhecidos
   (0034) dependem dele. Especifica-se uma conversão bidirecional e testada entre o caminho
   interno e o id LexML (Parte 3), com estas regras de partida: caput implícito sob artigo
   recebe `cpt` na exportação e o perde na importação; letra de inclusão converte-se em número
   (A=1); `parunico` corresponde ao `par1` do exemplo oficial, sujeito à conferência do item
   5.1. A equivalência da pendência 1 (`artN.caput.incX ≡ artN.incX`) passa a ter fundamento
   externo: ambos designam o único id LexML `artN_cpt_incX`. A direção indicada como pendente
   em `il2c-implementacao.md` (para `artN.incX`) permanece; a colisão ali ressalvada com
   incisos de parágrafo de mesma numeração não existe no id LexML (`artN_cpt_incX` e
   `artN_parY_incX` são distintos), o que serve de teste de regressão da normalização.
4. **Akoma Ntoso não é formato interno.** Nenhuma fonte consultada publica nesse formato;
   converter para ele interporia uma camada de interpretação entre a fonte e o confronto.
   Exportação em Akoma Ntoso só por demanda concreta e em decisão própria.
5. **LegalCiteM e LegalRuleML não são adotados.** O primeiro teve o comitê encerrado em 2021; o segundo
   modela regras como lógica, fora do escopo de verificação de fonte.

## 3. Execução e limites

1. Registro apenas. Nenhuma mudança de código nesta decisão.
2. A implementação (conversão de ids, uso dos termos FRBR, URN:LEX como chave) entra com a
   pendência 1 ou com o primeiro conector que precisar dela. Pela 0087 §4, as pendências 1 e
   12 seguem congeladas até a Porta A do STJ; ao serem retomadas, especificam-se contra esta
   decisão. `ARQUITETURA.md` é atualizada no mesmo PR da implementação, para não rodar a
   matriz completa por documentação (0087 §4.3).
3. A especificação do conector do STJ usa desde já a correspondência do item 2.1 e verifica se
   a gramática LexML define URN para acórdãos do tribunal antes de adotá-la como chave.

## 4. Objeções consideradas

1. *Formalizar agora gera trabalho sem ganho imediato.* O custo desta decisão é documental; o
   ganho é que o conector do STJ, próximo a ser especificado, nasça no modelo em vez de migrar.
2. *Adotar Akoma Ntoso daria interoperabilidade internacional.* A interoperabilidade útil ao
   Verifica é com as fontes brasileiras, que usam URN:LEX e schema.org/ELI. Exportação continua
   possível sem que o formato governe a verificação.
3. *Adotar os ids LexML como caminho interno eliminaria a conversão.* Trocaria uma conversão
   localizada e testável por uma migração de recibos, capturas e fixtures, e perderia a letra
   de inclusão literal, legível para o usuário.

## 5. Questões abertas

1. Parágrafo único: o exemplo oficial (RC1) usa `par1`; há uso secundário de `par1u`. Conferir
   as expressões regulares de `idArtigo` no `lexml-br-rigido.xsd` (Anexo 2 da Parte 3) antes de
   fixar a regra.
2. Anexos: a Parte 3 não define id. Manter o escopo de anexo do caminho interno sem
   correspondente LexML até haver regra oficial.
3. Versão vigente do esquema LexML posterior à 1.0 RC1, se houver.

## 6. Fontes lidas

- LexML Brasil, Parte 3 - LexML XML Schema, versão 1.0 (RC1), dez./2008
  (`projeto.lexml.gov.br/documentacao/Parte-3-XML-Schema.pdf`), regras de id de dispositivo.
- Publications Office da UE, ELI: ontologia 1.4, princípios FRBR e alinhamento ao
  schema.org legal extension (`op.europa.eu/web/eu-vocabularies/eli`; `eli-sdo.ttl`).
- schema.org, `legislationIdentifier` (aceita ELI ou URN-Lex).
- OASIS, arquivo da lista `legalcitem`: encerramento do comitê em 09/02/2021.
- Código em `origin/main` `9d97ab4`: `connectors/normas_leg.py`, `connectors/senado.py`,
  `verify.py` (`ResolvedWork`), `parsers/paths.py`; `docs/auditoria/1.4.0/il2c-implementacao.md`.
