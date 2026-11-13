# 0082 — Correções IL.3-c a partir do desenvolvimento

09/11/2026. Codex, sessão de escrita em `C:\dev\fv14-il3c`, base `65b98b6`.
Auditoria pendente por OUTRA sessão Codex somente leitura: independência reduzida,
declarada. Não aprova o próprio trabalho nem qualifica rota. Matriz IL.1, conjunto
de desenvolvimento, mutantes, reserva, transporte e contrato congelados intactos.

## D0 — Rótulo do dispositivo

O parser Câmara guardava o rótulo em `Provision.label`, mas retirava-o da primeira
redação de cada recorte; só descendentes conservavam o rótulo. O gabarito da IL.1
exige o dispositivo inteiro. A projeção da redação passa a incluir o rótulo literal
da fonte, também em artigo com letra, parágrafo, único, inciso, alínea, item e
caput do artigo (sem acrescentar a palavra editorial “caput”). Corpo, notas,
descendentes, spans e bytes capturados não são reescritos. Stub de veto sem
redação continua sem texto normativo: o rótulo não pode habilitar seu accessor.
O parser passa de
`camara-legin-4` a `camara-legin-5`; modelos antigos exigem reprocessamento pela
guarda existente, sem renovar a captura. Nenhuma normalização nova.

## D1 — Inventário e home

O preflight único `CamaraLeginConnector.validar_conjunto` valida a unidade inteira:
respostas íntegras, cada página acumulada com proveniência até uma busca/portal
capturada, hashes, href/rótulo publicado, igualdade do ancestral, ausência de
ciclo e `falhas_descoberta` vazia. Página acumulada sem proveniência é erro do
conjunto (fail-closed); não se descarta página para salvar o restante. Robots é
evidência administrativa independente, nunca raiz de cadeia normativa. Busca e
portal só podem ser raízes, sem antecessor. Relações válidas observadas mantêm D3.
Na pasta de corpos/recibos do instrumento, `capturas_normativas` exclui apenas
robots, mantido na área administrativa do portão, após conferir o acumulador
inteiro. Nenhuma página normativa órfã ou inválida é removida desse conjunto.

O instrumento chama o preflight antes de abrir o home (`_persistir_unidade`) e
antes de escrever corpos/recibos no destino (`_gravar_unidade`). No serviço,
`_capture_work`, `_index_candidate_legis`, `indexar_obra` e
`_material_historico_camara` chamam a mesma função antes da primeira indexação ou
gravação da unidade. No histórico, a original e as relações são primeiro
coletadas em memória: não se chama uma captura com persistência durante a coleta,
nem se zera a descoberta no meio da unidade. Falha de descoberta retida por
`capturar_relacoes`, mesmo devolvida como resultado parcial, impede as gravações.
O indexador também confere que o corpo a indexar corresponde à captura validada.

Cada modelo novo registra em `camara_inventario.conjunto_descoberta` as URLs e
hashes das páginas da unidade e suas primeiras arestas (origem/hash/href/rótulo).
A releitura reconstrói esse conjunto a partir dos corpos autenticados e executa
o mesmo preflight, incluindo a igualdade com a cadeia `descoberta` do texto.
O URL/hash da página declarada deve coincidir com a primeira aresta. O corpo e
a captura específica do texto também são autenticados e os metadados são lidos
pelo seu `capture_id`, sem substituição por outra obtenção do mesmo URL/hash.
O snapshot confere cada linha de captura, inclusive quando URL/hash se repetem:
uma obtenção 200 não mascara outra 403 dos mesmos bytes. Cada reconstrução relê
uma vez cada par URL/hash; a validação de resposta pode compartilhar seu exame
de perfil apenas dentro do mesmo preflight síncrono ou lote de registro dos
links de uma página, reconferindo hash, identidade e metadados em cada chamada.
A aprovação não atravessa fronteiras, lotes ou unidades; cada aresta é conferida.
Modelos anteriores sem esse campo usam a cadeia declarada, sem reconstruir
arestas novas a partir de busca ou metadados, e exigem cobertura de todas as
capturas Câmara do home por cadeias recuperáveis. É a recusa conservadora para
unidades antigas sem delimitação persistida: captura normativa órfã em home
legado também impede releitura. Redução de escopo após a auditoria r3 (N3,
teto do D5): `indexar_obra` da Câmara exige o conector da unidade
(`descoberta_camara`) e, sem ele, recusa com `camara_indexacao_sem_descoberta`
antes de qualquer leitura ou gravação. A versão anterior reconstruía o conjunto a
partir de uma resposta sintética (status 200, headers vazios, MIME HTML, instante
do chamador) e a persistia como captura: recibo fabricado. Todos os chamadores de
produção já passam o conector; a reconstrução offline fica restrita à releitura,
que lê o recibo real pela captura específica.

O snapshot valida os modelos e a cobertura de TODAS as capturas Câmara antes de
exportar. Na instalação repete a reconstrução e o preflight no banco e nos blobs
unidos em staging, antes da publicação de banco, blobs ou evidência administrativa.
Uma captura normativa sem cadeia recuperável recusa o snapshot inteiro; não é
omitida. Capturas íntegras preservadas após falha local de parser continuam no
home, mas, sem prova persistida de descoberta num modelo, não são exportáveis.
Busca/portal/robots independentes são conferidos como respostas, sem promover
uma captura normativa órfã a material validado. Ausência de bytes também recusa.
Um snapshot Câmara que cairia no modo texto-somente pelo limite global de blobs
é recusado antes de exportar, pois a instalação exige esses corpos.
A recusa de snapshot tem código `camara_descoberta_invalida`; a de releitura,
`camara_releitura_sem_vinculo_validado`, com causa interna, sem conteúdo livre.

Captura e indexação conservam URL/hash/instante e `captura_direta`, sem nova
obtenção ou renovação. No indexador Câmara, o recibo real é salvo antes do materializador
genérico, evitando que seu `application/octet-stream` substitua o MIME capturado.
Recibos antigos genéricos que não provem MIME admitido são recusados; não se
corrige a captura por inferência nem se renova seu instante. Passe final (N3
residual): o preflight `validar_conjunto` exige de cada página um instante de
obtenção presente e em ISO 8601 e recusa com `instante_captura_invalido` antes da
primeira escrita; sem isso, o materializador genérico preencheria o vazio com o
relógio e gravaria um segundo recibo com MIME genérico.
No instrumento os bytes íntegros são gravados após o
preflight e antes da interpretação: falha local do parser não os apaga nem cria
modelo a partir da falha. Material parcial válido e falhas continuam declarados.
As causas são acumuladas em ordem; inventário durável mantém a primeira no resumo
e todas em `causas`, saída mantém todas em `falhas`. A parada usa a união dos
impedimentos, inclusive se falham depois o inventário ou o compromisso. Não há
nova importação destino → home nem alteração dos canais públicos da reserva.

Conferências do passe final (supervisor). Uma obtenção distinta dos mesmos bytes
não encobre outra: (i) a conferência comum de resposta Câmara (`_validar_response`)
exige instante de obtenção presente e em ISO 8601, de modo que o acumulador, o
registro de arestas, o preflight, a releitura e a validação do acervo recusam
`instante_captura_invalido` antes de substituir, reduzir ou gravar; (ii)
`validar_acervo` confere cada linha de captura antes de reduzir por URL/hash; (iii)
a releitura autentica e confere todas as linhas da URL/hash de cada ancestral;
(iv) a mesclagem da instalação de snapshot recusa `conflito_recibo_captura` quando
o recibo recebido da mesma tripla (sha256, URL, instante) diverge do local, antes
do preflight e da publicação, e recusa `conflito_identidade_captura` quando um
recibo recebido colide pela identidade com outra tripla, em vez de ignorá-lo. A
comparação de `content_type` é dispensada quando um dos lados é nulo apenas para
fontes que não a Câmara (snapshot anterior à migração 014); para a Câmara, cuja rota
nasceu depois da 014, nulo de um lado só é divergência e recusa; (v) `repo.save_capture` da Câmara não reaproveita
obtenção da mesma tripla com recibo divergente (recibo legado inválido não absorve
o novo) e o materializador comum não grava recibo genérico para a Câmara: o modelo
vincula-se à captura real gravada pelo indexador após o preflight; a comparação
de recibos da Câmara em `save_capture` é estrita, inclusive no `content_type`
nulo; (vi) a reconstrução de resposta a partir do recibo não preenche
`content_type` nulo com o MIME, de modo que o Content-Type original dos headers
continua sujeito à conferência; (vii) o recibo comparado é o inteiro: na
mesclagem, para a Câmara, todas as colunas da captura exceto identidade e
procedência da cópia; em `save_capture`, também `outcome`, `codificacao` e
`origem_da_codificacao`; e a reconstrução confronta a decisão de interpretação
gravada com a reproduzida a partir do recibo (`interpretacao_divergente`).

Questões abertas registradas, não bloqueadoras segundo o passe final: a releitura
de modelos legados recusa toda a releitura Câmara se houver captura normativa
órfã no home (escolha conservadora, possivelmente mais ampla que o necessário); e
o custo de reconstruções repetidas do conjunto entre fronteiras, que alongou as
partições locais e pede medição causal.

## D2 — Isolamento local versus conteúdo

`LocalParserFailure`, subclasse aditiva de `Unavailable`, distingue ausência de
resultado do processo isolado de conteúdo incompatível. Falha de importação,
criação/saída do processo, tempo, memória e protocolo é local e terminal para o
escopo, sem gravar bloqueio de recurso. A Câmara aplica isso a HTML e PDF.
Conteúdo sem dispositivos ainda gera barreira de perfil; erros reconhecidos de
leitura HTML/PDF e limites documentais de PDF continuam conteúdo inválido.

Falha local sai do processo apenas por códigos e campos permitidos:
`fase=interpretacao`, `perfil`, `causa` (`importacao`, `criacao_processo`,
`exit_nao_zero`, `tempo`, `memoria` ou `protocolo`), `exit_code` inteiro quando
conhecido, URL oficial e SHA-256. O filho usa 77 para importação, 3 para memória,
4 para exceção inesperada; outros códigos não zero são preservados numericamente.
O pai não interpreta nem incorpora stderr. Motivo não contém mensagem nem caminho;
`Issue.detail` de falha isolada contém apenas JSON tipificado. O portão,
`_causa`/`_saida` do instrumento e os caminhos de captura/candidato do serviço
reaplicam a lista permitida, inclusive a falhas locais legadas. Tipo de falha
local desconhecido vira `protocolo`, sem repassar texto livre. Isso preserva a
acumulação de causas, a terminalidade e a distinção entre falha local e remota.
Exceções inesperadas na criação e no I/O também são tipificadas. Falhas das
threads de drenagem/escrita/fechamento não imprimem traceback em stderr; retornam
falha de protocolo, preservando a limpeza limitada do processo filho.
Exceção local inesperada no candidato Câmara também não é convertida com
`str(exc)`: a saída usa o código `falha_local_camara`.

## D3 — Proveniência da descoberta e relações observadas

Nos corpos reais do CPC e da LGPD do lote `fv-captura-dev-s2`, a página publica um
link admitido para ela mesma. `_descobrir` substituía a aresta busca → norma por
norma → norma; a interpretação detectava corretamente o ciclo que o acumulador
criara. A primeira correção (r1) toleraria só a autorreferência e trataria retorno
e descoberta concorrente como erro. A validação integral mostrou que isso inutiliza
a rota: as páginas de normas relacionadas publicam rotineiramente vínculos de
retorno e vínculos concorrentes para os mesmos atos (a página da Lei 13.874/2019
publica atos já publicados pela da Lei 6.404/1976), e o erro envenenava a unidade
inteira.

Regra (decisão do supervisor, r1b). A cadeia de descoberta registra a proveniência:
o primeiro caminho válido pelo qual a unidade alcançou uma URL. Toda aresta é
conferida antes de qualquer efeito: resposta de origem íntegra e igual à captura
acumulada, href que resolve para o destino e par href/rótulo presente nas âncoras
dos bytes. Aresta válida para URL ainda não alcançada entra na cadeia. Aresta
válida para URL já alcançada (autorreferência, duplicação na mesma página, retorno
entre páginas ou descoberta concorrente) não altera a cadeia nem é erro: fica
registrada como relação observada da unidade, com sua classe. Autorreferência sem
aresta anterior não cria raiz. Aresta inválida é erro de descoberta, retido até
zerar a unidade, e impede persistência (D1). Por construção, a cadeia é uma
floresta enraizada; a detecção de ciclo e de raiz continua como defesa em
profundidade, inclusive na releitura do banco.

Cada `resolve` inicia uma unidade de descoberta limpa, inclusive quando o serviço
reutiliza o conector entre normas; o estado de barreiras do portão não é zerado.
Relação observada não é cobertura, vigência nem prova de completude da lista de
relações. Isso não remove impedimentos de parse do CPC.

## D4 — Limites conservados com contraprovas

Identidade e epígrafe foram confirmadas nos corpos do CC (vigente/original) e do
original da Lei 13.874/2019. O problema não é sua ausência.

- CC: o reconhecedor de rótulos não admite milhares (`Art. 1.031`, com ou sem
  ponto final). Lê `Art. 1.` como artigo 1 e o restante como texto, produzindo
  duplicidades e ordens incompatíveis. Há ainda lacunas de sequência reconhecida
  que geram `TRUNCATED`. O original sem `art1031` devolve
  `primeira_publicacao_do_dispositivo_nao_obtida`; recortes reconhecidos em
  documento truncado continuam `unknown/TRUNCATED`. O atualizado também contém
  notas editoriais não reconhecidas e atribuições de caput pendentes. Não basta
  remover as quarentenas nem só admitir o milhar para declarar o documento apto.
- Original da Lei 13.874/2019: a leitura dos comandos/citações alteradoras termina
  em `citacao_alteradora_sem_fim`, associado ao art. 8. O recorte de art. 1 fica
  `unknown/TRUNCATED`, mesmo tendo identidade confirmada. Os blocos físicos do
  HTML juntam o fecho de uma citação, `(NR)` e o próximo artigo na mesma linha:
  o bloco iniciado pelo § 2º do art. 85 citado termina com o comando do art. 9º
  da alteradora, e o do § 5º seguinte termina com o comando do art. 10. O parser
  exige o fecho no fim da linha; não reconhece essas fronteiras intermediárias.
  A segmentação geral de comandos e citações intercalados permanece fora desta
  correção; não se corta arbitrariamente o texto nem se ignora a quarentena.

Adota-se a alternativa expressamente autorizada na tarefa: documentar o limite
com teste, mantendo abstenção. Não se trata D4 como capacidade corrigida nem se
afirma que captura, título ou texto aproximado habilitam `verified`.

Para conter o custo da seleção da wheel, os testes D3/D4 fazem o parse real
integral e conferem identidade, problemas e limites antes de projetar o modelo
a indexar ao artigo consultado. Conservam bytes, texto integral, spans, notas,
emendas, problemas e descoberta; preservam as saídas exatas e a releitura. Isso
evita materializar derivados quadráticos de milhares de dispositivos que esses
testes não consultam, sem alterar seleção, limite ou teste congelado da wheel.

## Fixtures e limites de entrega

Foram importados 16 pares recibo/corpo (CC, CPC, LGPD e Lei 13.874), exclusivamente
pelo `scripts/capturar_fixture.py --importar-offline`. O instrumento passou a
reconhecer o recibo de `fv camara inventariar`, preservando o objeto original e seu
hash. Os recibos antigos não registravam UA, versão nem charset HTTP: esses dados
ficam expressamente não registrados, sem valor inventado. Hash, instante, nome
por URL, MIME e vínculo são conferidos. Nos dois recibos de norma afetados por D3,
conserva-se a autorreferência como dado anômalo: o importador confere-a nos bytes e
reconfere separadamente o vínculo de raiz no corpo de busca fornecido, registrando
`raiz_reconferida_por_autorreferencia_d3`. Não conserta o recibo original.

Sem ampliação do período do CTN (D5), sem leitura da reserva (D6), sem alteração de
`C:\dev\fv-home-dev`, sem rede de produto e sem commit. O supervisor deve incluir
também `docs/auditoria/1.4.0/il3c-desenvolvimento.md` no primeiro commit. Resultados
finais da rodada R2 e limites de execução constam de `C:\dev\tmp\relatorio-il3c-impl-r2.md`.

## Adendo (13/11/2026): r4, r4b e passe final sob a 0083

**r4 (`feb65d4`).** A sanitização da r2 achatara as causas do parser isolado e dos
conectores. As causas locais voltam a ser códigos de lista fechada
(`CAUSAS_PARSER`, `freoa_verifica/connectors/base.py`); código desconhecido vira
`protocolo`. `Issue.detail` tem o formato `causa=…[;tipo=…][;exit=…]`, sem texto
livre do filho; a menção anterior a "JSON tipificado" e a enumeração de seis
causas ficam substituídas por esta. Falha local continua indisponibilidade ou
quarentena, separada de conteúdo inválido. `descendants_denied` conserva o tipo
(`erro_so:OSError`, `BlockingIOError` ou `PermissionError`) em `Issue.detail`; a
fronteira `Unavailable` preserva causa e exit, sem o campo `tipo`. O preflight
precede a identidade: conjunto inválido produz indisponibilidade e não sustenta
`not_found`. Desempenho: a releitura Câmara reaproveita a conferência de cada par
URL/hash só dentro da operação síncrona externa (`threading.local()` por
instância, criado na operação e descartado em `finally`); hash, URL, status,
redirecionamentos e instante são conferidos antes do reaproveitamento, e MIME,
Content-Type, tamanho, interpretação legada e headers compõem a assinatura.
Nenhuma aprovação persistente.

**r4b (`e771b05`).** A última linha do stderr do filho é comparada em bytes contra
os códigos admitidos para aquele exit, sem decode (garantia estrutural 3).

**Passe final sob a 0083.** O auditor demonstrou que a premissa do §3 da 0083 não
vale em todas as rotas: `--aceitar-nao-vinculado` (URL, arquivo e diretório
locais) e o instalador com `-SemAttestation` levam pacote sem vínculo até
`_merge_attach`, e a release automática não exige attestation. Com isso B2
voltava a bloquear. Correção por classe, em vez de restringir as rotas: logo
depois do `ATTACH`, `_merge_attach` executa `PRAGMA snap.foreign_key_check` sobre
o pacote recebido, isoladamente, e recusa com `snapshot_relacoes_invalidas`
qualquer referência inválida antes de remapear, reaproveitar ou ignorar linhas.
O banco local fica intacto. Regressão causal
`test_pf83_mesclagem_recusa_referencia_invalida_no_recebido` (falha sem a
correção). O snapshot oficial da 1.4.0a2 e o candidato da release não têm
violação relacional. B1 segue pendência de endurecimento (0083); a exigência de
attestation em todas as rotas e o staging antes da conferência de digest ficam
como pendências de endurecimento, sem efeito sobre B2 depois desta correção.
