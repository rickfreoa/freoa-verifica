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

Depois da obtenção, o instrumento valida as respostas e a cadeia de descoberta,
interpreta os textos obtidos e persiste as páginas e modelos pelos mesmos caminhos
de armazenamento do serviço, no home do próprio portão. Isso conserva a tripla
URL/hash/instante e a procedência `captura_direta`, com o registro administrativo
captura → política → termo já preservado pelo portão. Não executa outra obtenção.
Os bytes são gravados depois do preflight e antes da interpretação: falha local
do parser não apaga as capturas íntegras nem cria modelo a partir de sua falha.
Material parcial e falha continuam declarados no inventário de destino. Falha
local de armazenamento ou interpretação encerra a sessão. Não há nova importação
destino → home nem alteração dos canais públicos do modo reserva.

## D2 — Isolamento local versus conteúdo

`LocalParserFailure`, subclasse aditiva de `Unavailable`, distingue a ausência de
resultado do processo isolado de uma resposta de perfil incompatível. Falha de
importação, criação/saída do processo, tempo, memória e protocolo de saída é local
terminal e não grava bloqueio de recurso. A Câmara aplica isso tanto a HTML como
a PDF. O parser que devolve conteúdo sem dispositivos continua gerando barreira
de perfil; erros reconhecidos de leitura HTML/PDF e limites documentais explícitos
de PDF são devolvidos pelo filho como conteúdo inválido, sem serem confundidos
com falha do isolamento. Exceções inesperadas continuam locais.

## D3 — Autorreferência em páginas de norma

Nos corpos reais do CPC e da LGPD do lote `fv-captura-dev-s2`, a página publica um
link admitido para ela mesma. `_descobrir` substituía a aresta busca → norma por
norma → norma; a interpretação detectava corretamente o ciclo que o acumulador
criara. Preserva-se agora a primeira aresta: relações de retorno e autorreferências
não sobrescrevem uma descoberta já registrada. A validação de href/rótulo/hash e
a exigência de raiz de busca continuam, inclusive na releitura do banco. Um ciclo
efetivo sem raiz continua recusado. Isso não remove impedimentos de parse do CPC.

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
finais de testes e limites de execução constam de `C:\dev\tmp\relatorio-il3c-impl.md`.
