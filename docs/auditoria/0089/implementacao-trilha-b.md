# 0089 — Implementação da trilha (b)

19/11/2026. Papel: Desenvolvedor. Base: cd369b6ffc1d2d3a4721e342e85fcea5b4205f26.
Worktree C:\dev\fv14-0089i; ramo feat/0089-sessao-assistida; especificação vigente v5.2.
`transport.py` permanece intocado. Sem instalação, fonte externa, troca de ramo ou push.

**Entrega parcial, sem aceite da §3.** A implementação e a prova offline não substituem
o ensaio real, o aceite manual nem o parecer independente. Este registro discrimina as
lacunas; não autoriza reapuração da Porta L ou abertura das fontes barradas.

## Implementação

* `assistida/perfis.py`: perfis Planalto e normas_leg, gramáticas públicas, grafo final
  sobre todas as capturas, UUID/URN/expressão e conflito retroativo; dependentes com hash.
* `assistida/cdp.py`: pipe delimitado por nulo; fila de bytes, reservas antes da leitura,
  cópia e JSON; lista de dez comandos; anexação, raiz, prontidão e streaming no pedido.
  Só `transport.capturar_assistida` fornece os exemplares à seleção. Sem fallback de corpo.
* `assistida/ambiente.py`: Registro HKCU/HKLM nas duas vistas, DACL protegida e conferida,
  ReadDirectoryChangesW inscrito antes do lançamento, assentamento de 10 s, sentinelas e
  barreiras de 5 s, inventário auxiliar, componentes e recusa de permissões vedadas.
  Handles de depuração herdados por lista explícita; Job Object contém descendentes antes
  da retomada do processo suspenso e os encerra na limpeza. Nenhum perfil pessoal é aberto.
* `assistida/terminal.py`, `sessao.py`: TTY e confirmação, pai shell interativo (ou o
  launcher fv.exe instalado seguido de shell), recusa remota/script, página local estática,
  fechamento sem reabertura, barreiras e seleção. Nenhum início no serviço/MCP/REST/bateria.
* `assistida/persistencia.py`: só as selecionadas e seus dependentes seguem para
  `store.repo.save_capture`; recibo inserido completo porque capture é imutável. Migração
  018 acrescenta modalidade e recibo, sem mudar critérios de verificação. Parser recebe
  apenas exemplar admitido; Planalto exige cauda literal para interpretação sem WAF;
  identidade ausente mantém só o exemplar. Modelo com identidade declarada fica candidato.
* `assistida/indicacao.py`: observa somente tentativas automáticas efetivamente executadas,
  por fonte/operação; última tentativa substitui a anterior, inclusive em sucesso ou 401.
  Guarda apenas prova fechada, instante e alvo sanitizado; não importa o adaptador.
  Contrato aditivo, cobertura separada e preservação de modalidade em snapshot.

`fv reabrir-normas-leg --decisao <registro>` é o mínimo documentado pela 0087 §2.3:
comando local confirmado, chama o `NormasPortao.reabrir` existente, descarta política
antes de remover o bloqueio e registra a decisão; não emite rede. O home real não foi
reaberto. Não foi localizado no checkout registro adicional que amplie a pendência 24.

## Mapeamento normativo → prova

Nomes abaixo pertencem a `tests/test_assistida_0089_{cdp,ambiente,grafo,integracao,indicacao}.py`.
Geradores de eventos e políticas em `tests/assistida_0089_util.py` são sintéticos em memória;
não são novas capturas nem arquivos de fixture. O harness gera chave/AC sintéticas apenas
em tmp_path; não instala confiança. A complementação abaixo acrescenta somente duas
fixtures sintéticas br/zstd, com gerador e hashes em `tests/fixtures/FIXTURES.json`.
Os dois binários novos e o modelo preexistente estão cobertos por `*.bin binary`
no `.gitattributes`; `git check-attr` confirmou binary=set, diff/merge/text=unset.

| Norma | Implementação/prova offline | Limite da prova |
|---|---|---|
| §2.2 | test_filtro_sem_retencao, test_prontidao_quadros_e_ambiente, test_registro_recusa_antes_do_lancamento, test_inventario, test_vigilancia_apos_linha_base, test_produto_recusa_parametros_harness | Windows real bloqueado pela ACL; não prova efeitos universais do navegador |
| §2.3 | test_metodos_parametros_e_sequencia, test_adaptador_real_conectado_porta_unica, test_ids_iguais_em_alvos_distintos, test_grafo_completo, test_selecao_persistencia_e_cobertura | CDP sintético; adaptador de produto conectado à porta real |
| §2.7 | test_filtro_sem_retencao, test_url_publica_gramatica_limite_declarado, test_limpeza_e_recuperacao_confinadas | Faltam inventário real de gravações e acesso por segunda conta |
| §2.8–2.9 | test_inicio_estatico_escapado, test_cli_sem_tty_sem_lancamento, test_cli_sem_confirmacao, test_fechamento_e_queda_sem_reabertura, test_ast_fronteiras | Não substitui terminal/manual no Windows instalado |
| §2.10 | test_indicacao_conjuntiva, test_401_categoria_isolada_e_sucesso_apagam_indicacao, test_contrato_indicacao_preserva_motivo_tipo | Tipos estáveis preservados; contrato congelado testado separadamente |
| §2.11 | test_grafo_completo (11 casos), test_url_publica_gramatica_limite_declarado; testes da cauda na trilha (a) | Nomes reais de cookies continuam pendentes da §3.17 |
| §2.12 | test_metodos_parametros_e_sequencia, test_ast_fronteiras | Igualdade de pedidos reais com/sem observador não demonstrada |
| §2.13 | test_selecao_persistencia_e_cobertura, test_frescor_sem_verified_por_captura | Contagem por modalidade, não apuração de capacidades da Porta L |

| §3 | Prova offline | Navegador real e pendência |
|---|---|---|
| 1 | Matriz da trilha (a); pipe/reservas/fila, integração do adaptador e IDs em (b) | Cenários novos de br/zstd, framing/chunks, confrontos Fetch/XHR e HSTS escritos; ver lista e limites abaixo. Execução real NOT RUN nesta complementação |
| 2 | test_recusas_na_integracao e matriz da trilha (a) | Cache, SW sintético, prefetch, prerender/ativação, bfcache, Early Hints/final e recarga forçada humana escritos; exigem evidência do mecanismo. NOT RUN |
| 3 | test_prontidao_quadros_e_ambiente, test_filtro_sem_retencao, test_grafo_completo; matriz (a) | Iframe/Document, XHR de iframe, blob:, data:, download, WebSocket, POST e cookie não declarado escritos. NOT RUN |
| 4 | test_selecao_persistencia_e_cobertura, test_grafo_completo | Sem marcação: sem linha e sem blob; dependente com hash |
| 5 | test_filtro_sem_retencao, test_ids_iguais_em_alvos_distintos | Não se retêm eventos órfãos; ausência ambígua recusa |
| 6 | test_url_publica_gramatica_limite_declarado; scanner detecta UTF-8/UTF-16 em WAL e recusa varredura vazia | Cenário real inventaria perfil temporário, publica seleção, limpa perfil e varre todo tmp_path (SQLite/WAL/blobs/diagnósticos/terminal/harness); segredos só no tráfego sintético em memória. NOT RUN |
| 7 | test_limpeza_e_recuperacao_confinadas; DACL implementada e conferida antes do lançamento | Segunda conta NÃO EXECUTÁVEL neste notebook: não existe e titular não é administrador; teste conserva skip expresso. Inventário universal de gravações/interrupção permanece pendente |
| 8 | Registro, inventário, vigilância e barreira; manifesto de componente interno nas preferências e negativas | Teste Chrome/Edge confere Forcelist HKLM real e exige POLITICA_ASSISTIDA_RECUSADA antes de preparar perfil/lançar; só ausência do navegador pula. Brave e instalação real de extensão continuam sem aceite |
| 9 | test_metodos_parametros_e_sequencia, test_ast_fronteiras | Cenário com/sem adaptador compara integralmente pedidos e cabeçalhos vistos pela origem, sem exclusões/normalização; NOT RUN |
| 10 | test_adaptador_real_conectado_porta_unica, test_exemplar_fora_porta_recusado, test_ast_fronteiras | Adaptador real conectado à porta com eventos sintéticos; não é navegador real |
| 11 | test_item11_0075_historico_nos_dois_caminhos (10), test_item11_trinta_dias_so_consulta_corrente_e_cobertura (3), test_item11_sem_ancora_ou_confronto_nao_verified; test_frescor_sem_verified_por_captura | Captura sintética passa pela porta, parser e persistência; dois caminhos finais da 0075, redação riscada/atual/adulterada, história, juízo pendente, idades 0/30/31, data de captura imutável e cobertura separada. Não é captura oficial real |
| 12 | test_item12_exportacao_instalacao_remapeia_vinculos e test_item12_snapshot_preserva_dependente_e_hash | Ciclo público export_snapshot → install_snapshot; colisões naturais de work/provision com IDs locais diferentes, parsed_document/redaction remapeados, FK check, hash do dependente e evidência com procedencia=snapshot/modalidade preservada |
| 13 | test_item13_ast_fecho_transitivo_sem_porta_ou_adaptador; todas as 13 ferramentas MCP e 14 rotas REST executadas; sync/semente/bateria, quatro sinais remotos e guardiões de porta/adaptador/lançamento | Fecho conservador dos imports locais, inclusive imports internos às funções; entradas exercitadas também com barreira recente que só permite indicação. Não é prova formal de Python dinâmico arbitrário nem monitoramento real de arquivos; esse último permanece pendente |
| 14 | Testes de indicação conjuntiva, preservação e contrato existente | Campo é somente indicação; nenhum disparo |
| 15 | Testes da cauda da trilha (a); integração recusa interpretar cauda não casada | Faltam exemplares reais pelo adaptador e regressão de parser assistido completa |
| 16 | CLI reconhece sessao; recusa TTY e argumentos de harness | Instalação Windows + terminal/pipe reais NOT RUN |
| 17 | Fora do escopo do desenvolvedor | Sessão manual exclusiva do titular, pendente |

## Execuções

* Execuções intermediárias: 210 aprovados (porta + 0075); 343 aprovados
  (novos, 0075, snapshot e contrato); testes novos evoluíram de 69 para 90 casos.
  Estas contagens não devem ser somadas como testes distintos.
* Execução ampliada final: **678 passed, 1 skipped, 2 deselected em 213,20 s**.
  Incluiu os cinco arquivos novos offline, porta da trilha (a), 0075, snapshot, store,
  CLI, normas_leg 0085, guardas FIX9/FIX11, Windows 0085, manifesto de fixtures e contrato.
  Filtro explícito: `-k 'not test_instrumento_passando_pelo_mesmo_portao'` (Questão 10).
  O skip é o teste preexistente de symlink do manifesto: WinError 1314, sem privilégio.
* Conferência posterior sobre a árvore final materializada: **296 passed em 5,43 s**,
  cinco arquivos novos offline + `test_transport_assistida_0089.py`, `test_store.py` e
  `test_cli.py`. Contagens sobrepostas, não somar. Os cinco arquivos novos contêm 90 casos.
* Comando-base em ambas: `C:\dev\fv14-0089i\.venv\Scripts\python.exe -X utf8 -m pytest
  -q -p no:cacheprovider <arquivos>`. Temporários em `.tmp/trilha-b-*` dentro do worktree,
  respeitando a proibição de escrever fora dele. Suíte inteira não executada.
* Ruff: `C:\dev\tmp\venv-ruff\Scripts\python.exe scripts/ruff_catraca.py`;
  código 0. Check dos arquivos novos limpo e format --check: 16 arquivos formatados.
* Navegador: `pytest -q -rs -p no:cacheprovider tests/test_assistida_0089_navegador.py`:
  **17 skipped em 0,12 s**. Todos impedidos antes do lançamento por
  `ACL_ASSISTIDA_SetFileSecurityW_WINERROR_5` (Windows: acesso negado).
  O Brave instalado foi localizado; nenhum handshake CDP nem servidor HTTPS foi alcançado.
  Não houve tentativa de contornar a recusa da ACL. Esse resultado não prova falta de pipe.

## Correção após o primeiro ensaio real

19/11/2026. Papel: Desenvolvedor. Base desta correção: `a027443`, no mesmo
worktree e ramo. Sem commit, push, troca de ramo ou alteração de `transport.py`.

**Fato observado e causa.** O supervisor executou o harness fora do sandbox com
Brave 1.100 / Chromium 158: **16 failed, 1 passed**, todas as falhas por
`INVENTARIO_ASSISTIDO_INDISPONIVEL` (log `C:\dev\tmp\v5\impl-b\nav-b.log`).
O inventário tentado ao completar 10 s de silêncio de `Default\Extensions`
tratava preferências ainda não gravadas como falha definitiva. O relato recebido
informa ausência até 10 s e presença aos 30 s; o arquivo
`C:\dev\tmp\v5\impl-b\diag_inv.txt`, lido nesta correção, registra presença já
a partir de 11 s e enumera o conteúdo aos 30 s. Isso confirma que o prazo de
assentamento do diretório não determina o instante de gravação das preferências.

**Mudança e prazo.** `PRAZO_INVENTARIO_INICIAL_S = 60`, em `ambiente.py`, fixa
o limite para concluir a primeira leitura válida, contado pelo relógio monotônico
desde a criação da vigilância, antes do lançamento. É o dobro do limite superior
de 30 s informado no diagnóstico; oferece folga sem espera indefinida. Não é
um prazo novo para o handshake CDP nem para a barreira. O limite é exclusivo:
primeira leitura concluída aos 60 s ou depois recusa com o código atual.

* Somente `FileNotFoundError` ao ler `Secure Preferences` ou `Preferences`
  produz o estado interno `InventarioPendente`. O ciclo existente relê o inventário
  durante o assentamento; não bloqueia o processamento de eventos do navegador.
  Ausência de um arquivo não oculta JSON inválido ou extensão vedada no outro.
* JSON inválido, estrutura inesperada, erro de leitura diferente de ausência e
  manifesto indisponível continuam recusando imediatamente. `Preferences` sem
  `extensions.settings` continua válido. A exceção dos componentes exige
  `location` 5 e caminho originalmente absoluto, resolvido dentro da instalação;
  não dispensa a leitura válida do manifesto.
* A linha de base exige inventário válido e 10 s sem mudança. Notificação de
  instalação durante o assentamento adia a base; não reinicia o prazo da primeira
  leitura. Se o inventário já foi lido validamente, o silêncio ainda pode completar
  depois dos 60 s. A vigilância posterior e a sentinela de 5 s foram preservadas.
* A conclusão da sequência CDP é registrada separadamente da prontidão do alvo;
  `pronto` só é declarado depois da base. Pedidos anteriores não são recuperados
  quando ela aparece. Também foi corrigida a comparação temporal do próprio pedido
  que estabelece a base: usa o instante observado antes da leitura do inventário,
  para não admitir esse pedido quando o relógio avança durante a leitura.

**Harness e demais tempos.** A navegação fixa aos 14 s assumia preferências já
gravadas, premissa desmentida pelo diagnóstico. O HTML exclusivo de teste agora
consulta um script local e só recebe a instrução de navegar quando o harness
observa inventário válido, base e alvo pronto; não há comando CDP de navegação.
O teste de pipe também exige esses três fatos. Falhas de inventário após iniciar
o protocolo não viram skip de pré-requisito, inclusive durante o handshake.
O limite adicional do harness para ambiente/alvo pronto é o limite inicial mais
10 s, sem interferir nos limites do produto.

Foram conferidos os 17 casos reais: todos usam esse mesmo harness. O handshake
de 10 s permanece separado, pois o diagnóstico não demonstra atraso do pipe;
os 48 s para observar captura/recusa só começam após o sinal de prontidão.
Os servidores dos casos `sem_cabecalhos` e `parcial` continuam esperando 31 s,
acima dos 30 s da porta, contados do pedido posterior à prontidão. Nenhuma dessas
esperas precisa absorver o tempo de criação das preferências. A execução real
dessas mudanças, inclusive do sinal por script local, permanece **NOT RUN** nesta
correção; cabe ao supervisor fora do sandbox.

**Testes.** Regressões offline acrescentadas para ausência de cada arquivo e de
ambos com aparecimento dentro do prazo; ausência ou primeira leitura no limite;
leitura que termina no limite; JSON e estruturas inválidas mesmo com o outro
arquivo ausente; instalação que adia a base; silêncio que só termina após 60 s;
ausência na barreira sem nova espera; componentes embutidos com caminhos absolutos,
permissões de rede e `Preferences` sem settings; manifestos ausentes/inválidos,
inclusive de componentes; prontidão CDP com e sem base; pedidos anteriores, na base
e posteriores; relógio que avança enquanto o próprio pedido estabelece a base.
Os arquivos gerados são sintéticos em tmp_path, sem novas fixtures ou capturas.

Validação final: **307 passed**, sem skip ou deselection, nos cinco módulos offline
`test_assistida_0089_{ambiente,cdp,grafo,indicacao,integracao}.py`,
`test_transport_assistida_0089.py` e `test_cli.py`, usando
`.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider
-m "not live and not navegador_assistido" <sete arquivos>`.
Temporários fora do checkout, em
`C:\Users\rfreoa\AppData\Local\Temp\fv14-0089i-inventario-final3-20261119`.
Uma rodada focada anterior teve 84 aprovados; contagens sobrepostas, não somar.
A primeira execução focada teve 83 aprovados e uma falha do novo teste: seu relógio
sintético não estava alinhado ao prazo monotônico real da porta; o teste foi
corrigido sem mudar o transporte nem reduzir as asserções.
Suíte inteira e navegador real não executados. Ruff check limpo e format --check
aprovado nos seis arquivos Python tocados; catraca
`C:\dev\tmp\venv-ruff\Scripts\python.exe scripts\ruff_catraca.py`: código 0,
sem alteração da baseline.

**Questão adicional comprovada na instalação.** A conferência somente de leitura
dos caminhos de componentes do diagnóstico encontrou `resources\pdf` ausente;
`resources\brave_extension` existe, mas seu `manifest.json` não. Nenhum dos dois
manifestos existe nos caminhos declarados sob `Application\158.1.100.58`.
Assim, a correção do prazo das preferências pode expor uma segunda recusa com o
mesmo código. A §2.2(3)(c) exige o manifesto de cada extensão e estabelece
"manifesto indisponível: nenhuma candidata". Não foi criada dispensa para componente,
nem presumida a extração de recursos empacotados: essa solução depende do supervisor
e, se mudar a regra, do respectivo registro de decisão. O teste positivo de
componentes usa manifestos sintéticos disponíveis; não demonstra admissão dos
componentes dessa instalação. As demais lacunas de aceite abaixo permanecem.

## Leitura de execução: manifesto de componente

19/11/2026. Complementação sobre `f80630b`, por instrução expressa do supervisor.
O fato foi verificado **pelo supervisor fora do sandbox**, em
`C:\dev\tmp\v5\impl-b\diag_inv2.txt`, e transmitido ao desenvolvedor no pedido:
Brave 1.100, componentes `Chrome PDF Viewer` e `Brave`, `location` 5, caminhos
absolutos sob `Application\158.1.100.58\resources`, sem `manifest.json` em disco.
Os recursos são embutidos no binário; o navegador registra o manifesto no dict
`extensions.settings.<id>.manifest` de `Secure Preferences`. Foi essa a fonte
das permissões do componente Brave no laboratório. `active_permissions` é campo
separado. Não se atribui ao desenvolvedor nova inspeção dessa instalação.

**Leitura de execução adotada pelo supervisor**, para ciência do auditor e do titular:
na §2.2(3)(c), para `location == 5` e caminho originalmente absoluto que, resolvido,
esteja dentro do diretório de instalação do navegador, aceita-se o manifesto
registrado pelo navegador em `extensions.settings.<id>.manifest` quando não há
`manifest.json`. Esse valor deve ser dict: ausente, lista, string ou outro tipo
significa manifesto indisponível, nenhuma candidata. O `manifest.json` em disco,
quando existe, também é aceito; JSON/tipo inválido ou erro de leitura não é ocultado
pelo fallback. O próprio diretório de recursos pode estar ausente.

Para **toda outra extensão**, inclusive `location` 10, componente fora da instalação,
caminho originalmente relativo e extensão em `Default\Extensions`, continua
obrigatório o `manifest.json` em disco. Preferências não o substituem. Nenhuma
regra de permissão muda: mantém-se a exceção do componente interno da decisão e
a recusa de extensão comum/externa com permissão vedada. `active_permissions`
não substitui `permissions`/`optional_permissions` do manifesto.

Provas offline: 20 combinações em `test_manifesto_componente_nas_preferencias`
(dict/ausente/lista/string, interno/externo/10/comum/relativo), além de
`test_manifesto_location_10_vedado_encerra` e das negativas de manifesto em disco
preexistentes. Falhas invalidam a vigilância antes da linha de base. Esta leitura
supera somente o obstáculo de manifesto de componente descrito no registro anterior;
não constitui aceite da §3 nem altera `transport.py` ou `verified`.

## Complementação de provas e harness sobre f80630b

Papel: Desenvolvedor; mesmo worktree/ramo; sem commit, tentativa de commit ou push.
Única mudança de produto: leitura restrita do manifesto em `assistida/ambiente.py`.
Não houve dependência nova nem captura de fonte real. Nenhum navegador foi executado
nesta complementação; somente coleta dos testes `navegador_assistido`.

Os cortes dos itens 11 e 12 usam HTML sintético próprio, sem alterar amostras reais.
A captura do Planalto atravessa `capturar_assistida`, a cauda preexistente com token
sintético, parser, identidade e `persistir`; o teste não injeta `ResolvedWork` nem
simula as respostas finais da fachada. O teste de snapshot verifica remapeamento
das relações SQL para work/provision preexistentes; a prova separada de dependentes
confere recibo, capture_id do metadado e hash após exportação/instalação.

O item 13 constrói o fecho transitivo dos módulos locais a partir de MCP, REST,
service, bateria e semente, e inspeciona imports/chamadas no fecho. A execução
percorre o conjunto exato de ferramentas/rotas registrado pelo produto: inclusão
de entrada nova obriga atualizar a matriz. Guardiões falham se porta, adaptador,
lançamento ou entrada de sessão forem alcançados. Sync normal/semente e bateria
são exercitados em modo offline, e terminal remoto nos quatro sinais suportados.
Isso complementa as provas preexistentes de TTY, confirmação e encerramento.

### Cenários navegador_assistido escritos nesta complementação

Todos em `tests/test_assistida_0089_navegador_cenarios.py`; **38 casos novos**,
mais 17 preexistentes com nomes agora identificando o item: **55 coletados**.
Coleção não é execução; todos os resultados reais desta complementação são NOT RUN.

| §3 | Teste novo | Casos e resultado exigido |
|---|---|---|
| 1 | `test_item1_codificacoes_e_framing_reais` (11) | br/zstd: bytes iguais ao corpo sintético; campo malformado, CL duplicado/conflitante/TE/truncado/acima do limite, chunks malformados/truncados e vazio: nenhuma candidata, recusa observada |
| 1 | `test_item1_confrontos_finais_fetch_xhr_reais` (4) | Fetch e XHR, sem codificação e gzip; confronto final, encoded_data_length presente e identidade de bytes |
| 1 | `test_item1_hsts_interno_real_e_ausencia_de_prova` (2) | HSTS real em host .test mapeado só para loopback, sem candidata http; negativo suprime a prova do salto real por injeção de falha declarada no harness |
| 1/8 | `test_item1_item8_instalacao_manual_desempacotada_recusa` (1) | operador carrega extensão sintética com webRequest pela UI brave://extensions no perfil dedicado, sem flags/política/admin; inventário confirma location 4, barreira recusa e processo fecha ao sair. Não prova instalação assinada location 1/10 nem sua regra de permissões |
| 2 | `test_item2_proveniencia_real_sem_candidata_derivada` (6) | cache, SW que sintetiza resposta, prefetch, prerender com ativação, bfcache e Early Hints; exige prova de cada mecanismo, recusa da derivada e avaliação própria do final 103 |
| 2 | `test_item2_recarga_forcada_humana_vem_da_rede` (1) | titular/supervisor pressiona Ctrl+Shift+R na janela local; origem vê Pragma e Cache-Control no-cache, nova resposta de rede candidata |
| 3 | `test_item3_escopo_e_quadros_reais` (8) | iframe Document, XHR de iframe com frame diferente da raiz, blob:, data:, download, WebSocket, POST e cookie não declarado: nenhuma candidata; origem/evento prova que o cenário aconteceu |
| 6 | `test_item6_varredura_todos_artefatos_publicados` (1) | segredos em cookie/Authorization/query/parâmetro Content-Type/corpo privado não publicados; caminho público com aparência de token e dado pessoal sintético publicado preservados no blob, sem extract; inventário temporário, limpeza e varredura de todo tmp_path em UTF-8/UTF-16 |
| 7 | `test_item7_segunda_conta_windows_sem_privilegio` (1) | skip expresso: segunda conta inexistente, titular sem privilégio de administrador; não se cria conta nem se eleva privilégio |
| 8 | `test_item8_politica_maquina_recusa_antes_de_abrir` (2) | Chrome e Edge: Forcelist de máquina real, POLITICA_ASSISTIDA_RECUSADA antes de perfil/lançamento; pula somente navegador ausente (ou SO sem Registro Windows) |
| 9 | `test_item9_pedidos_e_cabecalhos_iguais_com_sem_adaptador` (1) | perfis dedicados novos, mesmas flags/pipe/origem; um sem cliente CDP, outro com adaptador; compara todos os pedidos/cabeçalhos sem exclusão ou normalização, só ordenando intercalação concorrente |

O inventário inicial conserva até 60 s para preferências, mais até 10 s para
assentamento/prontidão. O handshake conserva seu prazo independente de 10 s.
Depois da prontidão, prazos próprios: 40 s nos cenários usuais, 45 s nos segredos,
55 s nos mecanismos de proveniência e 90 s nos gestos humanos de recarga/instalação.
A instalação manual começa após candidata de controle (prazo próprio de 40 s).
Não se usa
`location.reload(true)` como prova de recarga forçada, nem CDP para navegar,
desativar cache, contornar SW ou alterar requisições. Os drivers são páginas de teste.

O modo sem adaptador não emite nenhum comando CDP; os handles são fechados na saída.
A varredura do item 6 inclui todo o diretório após remover o perfil dedicado:
o navegador pode armazenar cookies/cache no perfil temporário durante a sessão,
por isso seus nomes de arquivos são inventariados antes da limpeza. O log da
origem com segredos fica só em memória. Não é inventário universal do disco do SO.

As fixtures `0089_wire_{br,zstd}.bin` são blocos raw deterministas, gerados sem
biblioteca extra por `tests/gerar_0089_wire.py`. A reprodutibilidade e o manifesto
são conferidos offline; zstd também é decodificado pela biblioteca padrão do
Python 3.14 (prova específica pula nas versões anteriores). O decode de br pelo
navegador permanece NOT RUN. O gerador preserva bytes/finais de linha das entradas
anteriores do manifesto.

### Validação final desta complementação

**452 passed, 1 skipped em 34,68 s**, com `.venv`, após a inclusão do cenário
manual de extensão:

```powershell
.venv\Scripts\python.exe -X utf8 -m pytest -q -rs -p no:cacheprovider `
  -m "not live and not navegador_assistido" `
  tests/test_assistida_0089_ambiente.py tests/test_assistida_0089_cdp.py `
  tests/test_assistida_0089_grafo.py tests/test_assistida_0089_indicacao.py `
  tests/test_assistida_0089_integracao.py tests/test_assistida_0089_cortes.py `
  tests/test_assistida_0089_fronteiras.py tests/test_assistida_0089_harness.py `
  tests/test_transport_assistida_0089.py tests/test_decisao_0075.py `
  tests/test_snapshot_versao_130.py tests/test_store.py tests/test_cli.py `
  tests/test_fixtures_manifesto.py `
  --basetemp "$env:TEMP\fv14-0089i-final3-20261119"
```

O único skip é preexistente: `test_link_simbolico_reprova`, WinError 1314,
sem privilégio para criar symlink. O decoder zstd da biblioteca padrão foi executado
neste Python 3.14, sem skip. A rodada anterior teve 446 passed/1 skipped; não somar
as contagens sobrepostas. Suíte inteira não executada.
A asserção REST foi depois reforçada para exigir HTTP 200 em cada uma das 14
rotas (não aceitar corte por validação/autenticação como execução da fachada).
Conferência final do módulo de fronteiras com essa asserção: **8 passed em 3,02 s**,
contagem sobreposta aos 452, sem mudança de produto.

Catraca `C:\dev\tmp\venv-ruff\Scripts\python.exe scripts\ruff_catraca.py`: código 0,
baseline intocada. `ruff check` limpo e `ruff format --check`: dez arquivos Python
tocados já formatados. `git diff --check` limpo. Gerador de fixtures idempotente;
21 drivers JavaScript tiveram sintaxe conferida por `node --check` com o Node já
instalado, sem nova dependência de runtime/teste. Essa conferência não executa JS
nem comprova os mecanismos de navegador.

Coleta somente: os dois módulos de navegador somam **55 testes**. Não se iniciou
servidor HTTPS nem navegador nesta complementação; não há novo resultado real,
inclusive para política de máquina ou recarga humana. A execução pelo supervisor
deve reservar o tempo próprio de cada cenário e observar as janelas de recarga e
de instalação manual da extensão sintética, cujas instruções aparecem na página local.
HEAD/ramo preservados; `transport.py` sem alteração; sem stage/commit/push.

## Questões

1. Esta trilha não está concluída para aceite: a prova Windows real, a cobertura integral
   do harness e as lacunas explicitadas na tabela §3 permanecem pendentes. Não declarar
   SEM_BLOQUEADOR, instalação validada, capturas reais ou Porta L reapurada.
2. O harness anterior cobre UTF-8/meta/latin1/cp1252/U+FFFD/BOM/inválido, gzip/deflate,
   codificação vedada, bomba, redirecionamento, 304, CL de 21 dígitos e prazo parcial/sem
   cabeçalhos. Os cenários antes faltantes de brotli/zstd, chunks/framing, confrontos
   Fetch/XHR, cache/SW/prerender/histórico/HSTS estão agora escritos acima, sem execução.
   Isso não cobre integralmente as 22 linhas da §2.4 com navegador: injeções completas de
   ordem/correlação/streaming, alvos pré-anexação/perda real do canal, limites globais e
   instalação assinada de extensão comum/externa location 1/10 ainda pedem prova
   específica. A instalação manual desempacotada foi escrita, mas só prova a recusa
   própria de location 4; não demonstra a regra de permissão de extensão assinada.
   Se o Brave não demonstrar um mecanismo (HSTS, Early Hints, prefetch, prerender ou
   bfcache), o cenário falha; ausência de captura não o transforma em aprovação.
3. ExtraInfo órfão antes do pedido é descartado; não se guarda dado sem associação.
   Cadeia com chave reaproveitada é recusada. Não há tentativa de adivinhar a ordem ou
   reconstruir histórico ausente. Aba anexada já com URL perde conservadoramente a
   primeira candidata Document observada; pode exigir recarga humana adicional.
4. Não foi isolada a causa da rajada sem bytes do laboratório Brave (§5.9). O adaptador
   recusa falta de streaming/ExtraInfo e não usa fallback; a causa exige execução real.
5. O modo Windows usa `--remote-debugging-io-pipes` para comunicar os dois HANDLEs herdados
   de `--remote-debugging-pipe`, nunca porta TCP. Precisa da confirmação real prevista
   na §5.4. Falha do canal não autoriza alternativa.
6. Memória conservadora pode recusar antes do limite nominal: JSON/parser reservam
   múltiplos do tamanho bruto e a seleção mantém reserva própria. Corpo não marcado não
   é gravado. Falha durante publicação pode deixar blob selecionado sem linha depois do
   rollback; falta completar ensaio causal de interrupção/publicação e recuperação desses
   blobs. Não há promessa de transação de filesystem universal nesta entrega parcial.
7. POST do TJSP, PDFs/downloads, NPL/DOU, versão Original como árbitro, instalação assinada
   comum/externa no harness e nomes reais de cookies continuam nas questões da decisão.
   Não foram resolvidos; o cenário manual desempacotado não substitui a prova de
   extensão comum/externa com permissão vedada.
   Os POST/downloads sintéticos novos só provam recusa no escopo do harness: não abrem
   essas rotas. O item 7 é não executável aqui por segunda conta inexistente e ausência
   de privilégio administrativo; mantém-se o skip, sem alegar teste de acesso cruzado.
8. Ruff global usa a catraca preexistente; não se reformata a base nem se altera sua baseline.
   `pytest.ini` tem precedência sobre pyproject.toml: marcador registrado nos dois; os jobs
   offline da CI excluem explicitamente `navegador_assistido`.
9. Exceção pontual à preservação dos testes existentes: somente duas expectativas de
   `tests/test_store.py` passam de versões 1..17 para 1..18. A exigência expressa de
   persistir modalidade/recibo (§2.6 e §3.12) introduz a migração 018; os testes mantêm
   igualdade exata das versões e preservação dos dados, sem afrouxar a asserção.
10. A execução ampliada inicial terminou com 670 passed, 1 skipped e 5 failed. Três falhas
    foram corrigidas (caminho novo da cobertura e as duas expectativas da migração).
    As outras duas, `test_instrumento_passando_pelo_mesmo_portao[False/True]`, exigem tmp_path
    fora do repositório porque o instrumento recusa gravar nele. O pedido veda mexer fora
    do worktree: não se contornou essa recusa nem se alteraram os testes. Na execução
    final esses dois cenários não afetados pela mudança são explicitamente excluídos;
    a limitação fica registrada, sem alegar que passaram.
11. Registro histórico da entrega anterior: commits bloqueados; duas tentativas de `git add`, incluindo `--git-dir` e
    `--work-tree` explícitos, falharam com
    `fatal: Unable to create 'C:/dev/fv14/.git/worktrees/fv14-0089i/index.lock': Permission denied`.
    O lock não existe. Leitura da ACL mostra entradas Deny de escrita no diretório comum.
    As raízes graváveis declaradas não removeram essa recusa efetiva. Não se alterou ACL,
    índice, ramo, HEAD ou permissões. Nenhum commit foi criado; os arquivos permanecem
    no worktree para revisão. O requisito de status limpo, portanto, não foi cumprido
    naquela entrega. Nesta complementação o supervisor expressamente reservou o commit
    para si: nenhuma tentativa de stage/commit foi feita; worktree modificado é a entrega.

## Correção de latência após o ensaio nav-d (20/11/2026)

Papel: **Desenvolvedor**. Base conferida: `ee9e338`, ramo
`feat/0089-sessao-assistida`, worktree `C:\dev\fv14-0089i`.
Sem troca de ramo, stage, tentativa de commit ou push. **`transport.py` não foi
alterado**: SHA-256 `e692e24183eed13eb767fd56e40c118b26b7c1dff1f0606bc3045f4f521ddf62`.
A exigência de streaming anterior ao primeiro `dataReceived`, inclusive quando
este não traz `data`, permanece integral. Nenhuma mudança de regra ou de método
CDP; os dez métodos e os parâmetros fechados continuam os mesmos.

### Evidência e correção

O log do supervisor `C:\dev\tmp\v5\impl-b\nav-d.log`, lido nesta correção,
registra **31 passed, 23 failed, 1 skipped em 788,44 s** sobre a base. Também foram
lidos `diag_trace.txt` e `diag_trace_plugin.py` daquele diretório. O rastreamento
mostra o primeiro `dataReceived` sem resposta anterior ao comando de streaming;
a recusa pela porta estava correta. O diagnóstico temporal do supervisor aponta
~32 ms entre pedido e resposta da origem. Não se mediu aqui a latência anterior
do adaptador, nem se apresenta aquele intervalo de rede como medida dela.

* `AdaptadorCDP.passo()` recebe e processa a mensagem **antes** da manutenção.
  A elegibilidade usa base/prontidão já estabelecidas; `_pedido` não chama mais
  `assentar()`. A retomada do alvo apenas sincroniza a prontidão com a base
  existente. O inventário/assentamento e a fiscalização de capturas têm cadência
  de 200 ms. Depois da base, o assentamento não é repetido. A espera de leitura
  é de até 50 ms, interrompida imediatamente por mensagem disponível.
* A thread de `ReadDirectoryChangesW`, a inscrição anterior ao lançamento,
  as notificações e a invalidação imediata não mudaram. `conferir()` e as
  verificações de fechamento/prazo do canal continuam no processamento; são
  leituras de estado, sem inventário ou varredura. Sentinelas, inventário nas
  barreiras, limite de 5 s e impedimento de publicação permanecem em `Vigilancia`.
* O canal conserva FIFO e registra o relógio monotônico ao receber cada mensagem
  completa, antes da cópia para a fila. Esse instante acompanha a mensagem e
  fundamenta tanto a comparação com a base como o prazo da candidata. Um pedido
  recebido antes da base e processado depois dela continua excluído.
* A escrita continua passando por `comando()` e `CanalPipe.enviar()` e suas
  reservas. Reservas de leitura/cópia/JSON continuam precedendo as alocações;
  timestamp cabe na folga de 128 bytes já contada para a entrada da fila. Novas
  estruturas fixas têm reserva de 1024 bytes, e cada diagnóstico tem reserva
  prévia de 512 bytes. A regressão do pipe confere liberação integral ao fechar.
* `latencia_stream` contém somente `n`, `total_s`, `max_s` e `ultima_s`, em
  memória, com espaço constante. Mede chegada completa à fila até retorno da
  escrita/flush do comando, incluindo espera na fila e decodificação JSON. Não
  contém URL, identificador ou dado de rede e não é persistido automaticamente.
* URL validada para um tipo é sanitizada sem repetir a gramática no caminho
  urgente. `PerfilSessaoAssistida.sanitizar()` também passa a admitir o casamento
  completo por qualquer tipo individual, mantendo rejeição de query indevida e
  origem alheia e remoção de fragmento. Corrige o `None` no perfil do harness,
  que declara o mesmo caminho para Document, XHR e Fetch.
* `recusas` mantém os pares `(URL pública, classe)`, preservando o consumidor
  CLI. `motivos_recusas`, só em memória, acrescenta o código específico.
  Texto livre de exceção não é propagado; só se admite código em maiúsculas,
  limitado a 96 caracteres, com fallback à classe. Resposta tardia do comando
  não substitui nem duplica uma recusa já decidida.

### Harness e revisão dos 31 resultados verdes anteriores

As duas origens HTTPS aceitam `atraso_primeiro_byte`, padrão **0,15 s**, aplicado
antes dos primeiros bytes de resposta. É emulação de latência de rede na origem
local, exclusivamente de teste; não representa mudança do navegador nem aparece
no produto. A pausa de 0,3 s entre partes do corpo continua sendo segmentação do
corpo e não prova início oportuno do streaming. Os laços do harness usam `passo()`.

O novo `test_atraso_zero_consumidor_tardio_recusa_streaming_tardio` usa atraso
zero na origem e atrasa deliberadamente o consumidor do teste até haver bytes
na fila. Preserva os eventos e sua ordem, exige exatamente
`STREAMING_ASSISTIDO_TARDIO` e nenhuma captura. Essa injeção explícita torna
reproduzível a condição descrita na nota final do laboratório, sem depender de
uma corrida que o adaptador corrigido pode vencer.

O antigo `redirect` era um negativo (não exigia captura); falhava por exceção de
cadeia. Foi isolado em `test_redirect_de_rede_recusa_cadeia_cdp_ambigua`, que exige
`CADEIA_CDP_AMBIGUA`. A origem deixa de redirecionar indefinidamente o destino.
Redirect de rede permanece vedado pela §2.3(2); HSTS interno com prova permanece
positivo. Não se promoveu redirecionamento de rede a captura.

| Grupo anteriormente verde | Casos | Revisão contra aprovação no vazio |
|---|---:|---|
| Pipe/ACL Brave | 1 | Positivo exige processo, fase 3, inventário/base, alvo pronto e ausência de erro; preservado |
| UTF-8 inválido, encoding vedado, bomba, 304, CL de 21 dígitos, sem cabeçalhos, parcial | 7 | Exigem código de interpretação, encoding, tamanho, status/framing ou prazo. 304 exige status observado; rejeição de CL pelo navegador exige `net::ERR_INVALID_RESPONSE`. Streaming tardio não satisfaz esses testes |
| Framing/chunks/vazio | 9 | Exigem código de cabeçalhos, tamanho ou corpo vazio; quando o navegador aborta, exigem também seu erro de rede específico. Só `ad.recusas` ou zero capturas não bastam |
| HSTS com prova suprimida | 1 | Exige salto HSTS real e `REDIRECIONAMENTO_ASSISTIDO_RECUSADO` após a supressão explicitamente injetada |
| Cache, SW, prefetch | 3 | Exigem mecanismo real e código de origem sem prova/evento recusado para a URL derivada |
| Iframe, XHR de iframe, blob, data, download, WebSocket, POST, cookie | 8 | Exigem motivo de porta para iframe/POST/cookie/download, erro de aborto no download, ou prova da exclusão por quadro/esquema/tipo e ausência de comando de streaming nos demais |
| Política de máquina Chrome/Edge | 2 | Já exigiam `POLITICA_ASSISTIDA_RECUSADA` e guardas contra preparar perfil/lançar; preservados |
| **Total** | **31** | Revisão de asserções, não nova aprovação no navegador |

Prerender, bfcache e Early Hints também conservam provas dos mecanismos;
prerender verifica o subtipo/primeira URL do alvo observado, bfcache exige uma
única troca/captura e Early Hints exige a exclusão do recurso iniciado e captura
da resposta final. Os conjuntos explícitos de motivos cobrem caminhos de
rejeição distintos do Chromium e da porta, sem aceitar streaming tardio como
substituto. Seus valores reais ainda exigem o próximo ensaio do supervisor.

### Medição e validação desta árvore

* Prova determinística offline com pipe simulado: pedido e `dataReceived` posterior
  no mesmo fluxo. A escrita/flush ocorre antes da segunda mensagem e antes da
  manutenção, sem chamada de assentamento no pedido. Relógio injetado: **8 ms de
  fila + 2 ms de escrita = 10 ms**, conferidos em última/máxima/total e contagem.
  A mensagem seguinte sem streaming é recusada pelo motivo exato; erro posterior
  do comando não muda esse motivo.
* Medição complementar local, 50 pedidos, `CanalPipe` com BytesIO, thread leitora,
  porta real e relógio monotônico real, sem navegador ou socket: **mínimo
  0,1821 ms, mediana 0,2243 ms, máximo 0,6978 ms**. Não mede transporte do Brave,
  não compara com execução anterior e não garante vencer qualquer origem rápida.
* Testes finais afetados: `.venv\Scripts\python.exe -X utf8 -m pytest -q
  -p no:cacheprovider -m "not live and not navegador_assistido"` com os oito
  arquivos `test_assistida_0089_{cdp,harness,grafo,ambiente,cortes,indicacao,
  integracao,fronteiras}.py`, `test_transport_assistida_0089.py`, `test_store.py`,
  `test_cli.py` e `test_ruff_catraca.py`: **387 passed**. TMP/TEMP e `--basetemp`
  em `%TEMP%\fv0089-latencia-final2`, fora do checkout. Suíte completa não executada.
* `C:\dev\tmp\venv-ruff\Scripts\python.exe scripts/ruff_catraca.py`: código 0,
  sem alteração de baseline. Formatação dos oito arquivos Python afetados
  conferida. `git diff --check`: código 0.
* Coleta dos dois módulos reais: **56 testes**, sem execução do navegador nesta
  correção. **Ensaio Brave atualizado: NOT RUN. Aceite da §3 e auditoria
  independente: pendentes.** Os números do supervisor sobre `ee9e338` continuam
  sendo evidência histórica, não resultado desta árvore.

## Terceiro ensaio real: ordem resposta do streaming x dataReceived

20/11/2026. Papel: **Desenvolvedor**. Base conferida: `a0a7a3e`, ramo
`feat/0089-sessao-assistida`, worktree `C:\dev\fv14-0089i`.
Nesta rodada a alteração da porta foi expressamente autorizada pelo supervisor.
Sem stage, tentativa de commit, push ou troca de ramo.

### Fatos e leitura de execução

O supervisor informou a verificação fora do sandbox com Brave 1.100 / Chromium 158,
harness HTTPS local e **150 ms até o primeiro byte**; rastreamento em
`C:\dev\tmp\v5\impl-b\diag_trace.txt` e `diag_trace_plugin.py`. No Document principal:

1. `Network.streamResourceContent` foi escrito no pipe no mono 22736.0056,
   cerca de 190 ms antes dos dados.
2. O primeiro `Network.dataReceived` veio **sem `data`**, com `dataLength=20`.
3. Só depois veio a resposta ao comando: 28 caracteres base64 em `bufferedData`,
   exatamente os mesmos 20 bytes do evento anterior.
4. Os eventos seguintes continham `data`; depois veio `loadingFinished`.

Esses fatos são do ensaio do supervisor; nenhum navegador foi executado nesta rodada.
O laboratório de 19/11 provou o início no pedido, sem provar a ordem resposta-evento.
A interpretação anterior desta documentação de que a recusa do primeiro evento
sem `data` era correta fica **superada pelo defeito 49**.

Leitura de execução adotada pelo supervisor, registrada também em
`docs/decisoes/0089-nota-execucao-defeito-49.md`:

* A chamada no `requestWillBeSent` continua obrigatória e o streaming continua a
  única fonte de bytes; sem `getResponseBody` ou método CDP novo.
* Antes da resposta do comando, só são admitidos eventos **sem a chave `data`**.
  A porta soma todos os `dataLength`/`encodedDataLength`, aplica `max_bytes` e
  reserva orçamento para os bytes declarados por `dataLength` imediatamente.
* A resposta exige `bufferedData` decodificado de tamanho exatamente igual à soma
  dos `dataLength` anteriores. Buffer vazio só sem evento anterior. A reserva
  declarada só é liberada após a cópia validada, sem intervalo sem cobertura.
* Depois da resposta, cada evento exige `data` decodificado de tamanho igual ao
  próprio `dataLength`. Os confrontos finais da §2.4 linha 7 permanecem iguais;
  divergências entre trechos não podem compensar-se no total.
* `loadingFinished` anterior à resposta: `STREAMING_ASSISTIDO_TARDIO`. `data` antes
  da resposta, ausência de `data` depois ou erro do comando na porta:
  `STREAMING_ASSISTIDO_INVALIDO`. Tamanho divergente: `STREAMING_ASSISTIDO_DIVERGENTE`.
  São recusas `RespostaInvalida`. O adaptador mantém `COMANDO_STREAMING_RECUSADO`
  para resposta CDP de erro e não substitui uma recusa já decidida. Prazo inalterado.

`freoa_verifica/assistida/cdp.py` não precisou mudar: já chama o comando no pedido e
entrega eventos/resposta em ordem, sem exigir resposta anterior ao primeiro evento.
Os parâmetros fechados e os dez métodos permanecem iguais.

### Testes e harness

O gerador sintético antigo atribuía três bytes a `bufferedData` sem evento anterior
e contava o corpo inteiro no evento com o restante dos bytes. Esse pressuposto foi
corrigido, conforme autorização expressa para ajustar os testes existentes. O padrão
agora usa buffer vazio e corpo inteiro no evento posterior; `antes_stream=20` reproduz
a sequência observada. Nenhuma captura real ou fixture foi editada.

`test_pipe_escreve_stream_antes_da_proxima_mensagem_e_da_vigia` preserva a prova de
escrita no pedido, os 10 ms do relógio injetado e a precedência sobre manutenção;
agora aceita o evento anterior sem `data`, recusa o `loadingFinished` anterior à
resposta e exige que o erro posterior do comando não mude o motivo.

Novas regressões da porta cobrem corpo/hash idênticos com prefixo de 20 bytes,
buffer vazio sem evento, corpo inteiro no buffer, soma de vários eventos anteriores,
cada violação de (b)–(e), divergências compensatórias, reserva e excesso de orçamento,
limites antes e depois da resposta. As do adaptador exercitam a porta real, exigem
aceite da sequência observada e códigos exatos das violações, inclusive erro CDP.

As duas origens do harness **mantêm 150 ms** até o primeiro byte, sem ajuste de tempo.
O cenário antigo `test_atraso_zero_consumidor_tardio_recusa_streaming_tardio` foi
revisto como `test_consumidor_tardio_fim_antes_da_resposta_streaming`: usa o atraso
padrão da origem e conserva a pausa de 0,5 s do consumidor. A asserção exige término
antes da resposta do streaming, ou resposta de erro do comando, e nenhuma captura.
Primeiro evento sem `data` já não prova streaming tardio. Esse cenário foi coletado,
mas **não executado no navegador** nesta rodada.

### Validação e questões

* `.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider
  -m "not live and not navegador_assistido"` nos nove módulos
  `test_transport_assistida_0089.py` e
  `test_assistida_0089_{cdp,harness,grafo,ambiente,cortes,indicacao,integracao,fronteiras}.py`:
  **390 passed em 9,00 s** na repetição final. `--basetemp` em
  `%TEMP%\fv0089-def49-final`, fora do checkout. Coleta dos dois módulos reais:
  **56 testes**. Suíte completa e ensaio de navegador: **NOT RUN**.
* D5: `ast.dump(include_attributes=False)` de **todas as 77 funções/classes**
  preexistentes de `transport.py`, incluindo métodos e definições internas,
  contra `87b43f7`: **zero ausentes, zero alteradas**.
* `C:\dev\tmp\venv-ruff\Scripts\python.exe scripts\ruff_catraca.py`: **exit 0**,
  baseline inalterada. Três arquivos de teste tocados com lint/formatação limpos;
  trecho assistido de `transport.py` formatado (`--range 580-1020`). O arquivo
  completo conserva seis achados de lint (comparados por regra/mensagem com o HEAD:
  idênticos, zero novos) e formatação antiga no fluxo automático;
  não foram feitas alterações fora da correção autorizada para limpar a base.
* A redação da **0089 §2.5(2)** e do **§3 item 1 ("streaming iniciado tarde")**
  precisa de **nota formal do titular**. Este registro é a leitura de execução
  autorizada, não essa nota. Aceite real e auditoria independente seguem pendentes.

## Quarto ensaio real

20/11/2026. Papel: **Desenvolvedor**. Base conferida: `cbce9b60bf96bc8bd0ac006591f926bb9ea38043`,
ramo `feat/0089-sessao-assistida`, worktree `C:\dev\fv14-0089i`, inicialmente sem
alterações de arquivos. Não houve troca de ramo, stage, tentativa de commit ou push.
A autorização para alterar a porta nesta rodada alcança exclusivamente o item 1.

### Evidência e correção da porta

Leitura integral dos blocos de falha de `C:\dev\tmp\v5\impl-b\nav-4.log`:
**39 passed, 16 failed, 1 skipped** no ensaio externo com Brave 1.100.
SHA-256 do log: `4b70ba8110be043a6e112d57fd1605d8b4a461f13973702d0c749fdc01e8cce8`.
Rastreamento `C:\dev\tmp\v5\impl-b\diag_trace.txt`, SHA-256:
`8492d7e433720cc89ca65d98ee651730bf8da43823a6fe00acbae2fd3b25823e`.

Em `fetch_identity`, o comando foi enviado no mono 26760.9069, respondido no mono
26760.9079 com buffer vazio; vieram blocos com `data` de 22 e 22 bytes, evento
sem `data` com `dataLength=0` e, por último, `loadingFinished`. A porta recusava o
evento contador. Agora, **depois da resposta**, a ausência da chave `data` só é
admitida com `dataLength == 0`; não se copia byte algum. O incremento de
`encodedDataLength` e sua validação de tipo, sinal, limite e confronto final
continuam anteriores a essa ramificação. Comprimento positivo sem `data` ainda
produz `STREAMING_ASSISTIDO_INVALIDO`. Nada muda antes da resposta ou no término.
Registro complementar em `docs/decisoes/0089-nota-execucao-defeito-49.md`.

### Classificação de cada falha

**A**: produto; **B**: expectativa do teste; **C**: cenário do harness não produziu
a condição pretendida. Os nomes abaixo são dos dois módulos
`test_assistida_0089_navegador{,_cenarios}.py`. Classificações de causa comum
indicadas como inferência não são confirmação por novo ensaio real.

| Falha | Classe | Bloco do log, fundamento e alteração |
|---|---|---|
| `test_item1_confrontos_finais_fetch_xhr_reais[fetch_identity]` | A | Linhas 313–394: zero capturas. O rastreamento demonstra o evento final sem novos bytes. Corrigida somente a porta, conforme instrução expressa e §2.4 linha 7. |
| `test_item1_confrontos_finais_fetch_xhr_reais[fetch_gzip]` | A, inferência | Linhas 395–476: mesmo ponto de falha, sem rastreamento próprio. Correção comum; confronto de comprimento codificado preservado e testado offline. Expectativa positiva mantida. |
| `test_item1_confrontos_finais_fetch_xhr_reais[xhr_identity]` | A, inferência | Linhas 477–558: zero capturas, sem motivo nem sequência CDP no bloco. Nenhuma outra causa de XHR demonstrada no material. Correção comum, expectativa positiva mantida; requer reensaio. |
| `test_item1_confrontos_finais_fetch_xhr_reais[xhr_gzip]` | A, inferência | Linhas 559–640: mesma limitação de diagnóstico. Coberto offline pelo adaptador/porta reais, com contador final codificado. Expectativa positiva mantida. |
| `test_item1_https_adaptador_real[304]` | B | Linhas 4–78: status 304 observado, nenhuma captura; lista de motivos do teste falha, mas o motivo efetivo não foi impresso. §2.3(1): “304, 206 e os demais status nunca viram captura”; §2.5(2): “Se o streaming falhar [...] a candidata é recusada”. A norma não exige alcançar a admissão nem um único motivo. Teste admite recusa anterior de streaming apenas com prova da ordem ou do erro do comando; `loadingFailed` exige `net::ERR_CACHE_MISS` do mesmo pedido. |
| `test_item1_https_adaptador_real[sem_cabecalhos]` | B | Linhas 79–168: recusa existente, motivo esperado não encontrado; motivo efetivo ausente do log. §2.4 linha 12 classifica **expiração do prazo**, não obriga esperar 30 s após falha já provada; §2.5(2) obriga recusar falha do streaming e §2.3(1) exige término bem-sucedido. Além do timeout, teste admite erro comprovado do comando ou `loadingFailed` correlacionado com erro de rede enumerado; exige ausência dos dois eventos de resposta completa. Causa efetiva desse ensaio permanece não apurada. |
| `test_item1_https_adaptador_real[parcial]` | B | Linhas 169–258: mesma ausência do motivo no log. A linha 12 declara que cabeçalho parcial não é sinal de resposta completa. Mesmas alternativas condicionadas a prova, sem mudar prazo nem porta. Causa efetiva desse ensaio permanece não apurada. |
| `test_item1_codificacoes_e_framing_reais[vazio]` | B | Linhas 259–312: motivo efetivo `STREAMING_ASSISTIDO_TARDIO`, e não `CORPO_ASSISTIDO_VAZIO`. §2.4 linha 7: “Corpo vazio, recusado”; §2.5(2) e leitura do defeito 49 também recusam término antes da resposta do streaming. Teste exige zero captura e aceita essas recusas anteriores só com prova da ordem/erro do comando. |
| `test_item2_proveniencia_real_sem_candidata_derivada[cache]` | A, inferência | Linhas 712–831: dois motivos na mesma URL, `STREAMING_ASSISTIDO_INVALIDO` e `ORIGEM_ASSISTIDA_SEM_PROVA`. O primeiro Fetch de rede é compatível com o defeito do contador; o segundo já prova recusa de cache. Mantidas as expectativas e os motivos originais: nenhuma autorização adicional para aceitar cache. Reensaio deve confirmar a causa do primeiro pedido. |
| `test_item2_proveniencia_real_sem_candidata_derivada[prerender]` | C | Linhas 832–920: nenhum alvo com subtipo prerender; a navegação comum após 4 s não demonstrava a condição. O driver agora consulta uma marca da página efetivamente pré-renderizada antes de ativá-la; sem marca não navega ao alvo. Ausência da condição vira skip explícito, sem prova positiva do produto. `FV_0089_NAVEGADOR_PRERENDER` permite escolher navegador instalado compatível; políticas continuam obrigatórias. |
| `test_item2_proveniencia_real_sem_candidata_derivada[early_hints]` | C | Linhas 921–1061: nenhum `Network.responseReceivedEarlyHints`; a origem anterior só falava HTTP/1.1, que o Chromium ignora para 103. Criada origem de teste HTTP/2/ALPN h2 com 103 real, preload de script e resposta final 200. Teste exige negociação h2, evento de 103, pedido do recurso sugerido, ausência de sua captura e captura final. Dependência opcional de teste ausente causa skip explícito, nunca aprovação. |
| `test_item3_escopo_e_quadros_reais[download]` | C | Linhas 1109–1233: origem viu pedido, mas não houve recusa de candidata. `<a download>` pode seguir o caminho interno de download sem pedido elegível em Network; esperar recusa da porta não provava o mecanismo. Driver agora navega a `attachment` sem atributo `download`; exige pedido CDP `Document`, `net::ERR_ABORTED`, recusa e nenhuma captura (§2.7(2)). |
| `test_item6_varredura_todos_artefatos_publicados` | A, inferência | Linhas 1234–1342: falhou antes da persistência/varredura, por ausência da captura pública Fetch. Correção comum do item 1; a varredura integral, os segredos sintéticos e as asserções de persistência permanecem. Acrescentado motivo das recusas ao diagnóstico da asserção. |
| `test_item9_pedidos_e_cabecalhos_iguais_com_sem_adaptador` | A, inferência | Linhas 1343–1490: a falha registrada é `assert capturas(ad)`, **não prazo próprio excedido**; duração 26,48 s. O Fetch observado é compatível com o mesmo defeito. Expectativa, comparação integral dos pedidos/cabeçalhos e prazo de 40 s mantidos; motivos impressos em eventual nova falha. O prazo excedido do log está no teste de recarga humana. |
| `test_item2_recarga_forcada_humana_vem_da_rede` | C | Linhas 1062–1108: prazo de 90 s excedido sem gesto humano. Agora skip salvo `FV_0089_GESTO_HUMANO=1`; nesse modo, após primeira captura, instrução visível ao operador e novo prazo de 90 s para Ctrl+Shift+R. Mantidas prova de dois headers `no-cache` e capturas de rede (§2.2(4)). |
| `test_item1_item8_instalacao_manual_desempacotada_recusa` | C | Linhas 641–711: instalação manual não demonstrada em 90 s. Mesmo opt-in e skip explícito; após primeira candidata, instrução fora da captura do pytest com caminho exato e 90 s para o operador. Inventário `location=4` e barreira de seleção continuam obrigatórios (§2.2(3)(b')). |

As alternativas de B não aceitam recusa arbitrária ou só zero capturas:
`exigir_recusa` continua exigindo motivo enumerado e nenhuma captura; a sonda
correlaciona respostas do comando com o pedido e prova fim anterior à resposta
ou erro efetivo do comando. As recusas de rede exigem `loadingFailed` e erro
enumerado do mesmo pedido. A porta não foi afrouxada por nenhuma dessas falhas.
O próximo ensaio ainda pode revelar motivo não contemplado; o teste deve falhar
nesse caso. Para 304 e os dois cabeçalhos incompletos, o log fornecido **não**
permite atribuir retrospectivamente qual dessas alternativas ocorreu.

Fontes técnicas dos próprios projetos, consultadas em 20/11/2026:
[Chromium, Early Hints](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/docs/early-hints.md)
declara que ignora 103 em HTTP/1.1 ou anterior;
[Brave, issue 49190](https://github.com/brave/brave-browser/issues/49190)
registra desativação de prerender. O skip do cenário depende da ausência observada
da condição, não só do nome do navegador. Nenhuma política, flag de recurso ou
CDP adicional foi usada para forçar funcionalidade.

### Arquivos e provas

* `freoa_verifica/transport.py`: única mudança de produto, na ramificação posterior
  à resposta do streaming, exclusivamente item 1.
* `tests/test_transport_assistida_0089.py`: regressão da sequência de 44 bytes em
  dois blocos, hash, contador final sem data, comprimento positivo recusado e
  confronto codificado, em Fetch/XHR e identity/gzip.
* `tests/test_assistida_0089_cdp.py`: mesma ordem pelo adaptador e porta reais,
  positivos e recusa exata, nos quatro tipos/codificações.
* `tests/harness_assistida_0089_cenarios.py`: observações correlacionadas do comando,
  guardião causal de motivos alternativos, prerender sem navegação substituta,
  download por navegação e encaminhamento do 103 para origem HTTP/2.
* `tests/harness_assistida_0089_h2.py` (novo): origem sintética exclusivamente
  loopback com ALPN h2; headers 103, final 200 e corpo segmentado na origem.
* `tests/test_assistida_0089_harness.py`: teste em memória do 103/final HTTP/2,
  guardiões de ordem/erro e opt-in humano exato (`1`, não `true`/`0`/ausência).
* `tests/test_assistida_0089_navegador.py` e
  `tests/test_assistida_0089_navegador_cenarios.py`: expectativas, pré-requisitos,
  instruções ao operador e diagnóstico descritos na tabela.
* `pyproject.toml`: extra opcional **de teste** `test-navegador = ["h2>=4,<5"]`;
  nenhuma dependência ou método CDP do produto novo. Nenhum marker novo foi necessário.
* Este registro e `docs/decisoes/0089-nota-execucao-defeito-49.md`.

### Validação e questões

* Antes do patch de produto, a regressão focada da porta produziu **8 failed,
  4 passed**: os comprimentos positivos já eram recusados. Depois: **24 passed**
  no foco incluindo violações anteriores, e **8 passed** na nova prova do adaptador.
* Validação final dos mesmos nove módulos offline da rodada anterior, com
  `.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider
  -m "not live and not navegador_assistido"`, `--tb=short -ra` e
  `--basetemp "%TEMP%\fv0089-nav4-final"`: **420 passed, 1 skipped em 8,99 s**,
  exit 0. O único skip é a prova **em memória** de HTTP/2, por ausência de `h2`;
  ela não foi validada. O temporário ficou fora do checkout.
* Sem o opt-in, execução só dos dois testes humanos: **2 skipped, 36 deselected**,
  com motivos explícitos, exit 0. Coleta dos dois módulos de navegador: **56 testes**.
  Nenhuma janela foi aberta. Ensaio real corrigido e suíte completa: **NOT RUN**.
* AST D5 por nomes qualificados, incluindo métodos e funções internas,
  `ast.dump(include_attributes=False)` contra `87b43f7`: **77 definições
  preexistentes; zero ausentes, zero alteradas**. `cdp.py` e seus dez métodos
  permitidos não foram alterados; testes da lista fechada passaram.
* `C:\dev\tmp\venv-ruff\Scripts\python.exe scripts\ruff_catraca.py`: **exit 0**.
  Os sete arquivos Python de teste/harness tocados passam `ruff check --no-cache`
  e `ruff format --no-cache --check`. Trecho assistido de `transport.py` formatado
  (`--range 804-828`); seus **seis achados históricos** são idênticos ao HEAD por
  regra/mensagem, zero novos. Fluxo automático e baseline não foram formatados
  ou alterados. `git diff --check`: limpo.
* `h2` ausente na `.venv`: tentativa de instalação offline via uv não pôde obter
  lock no cache global (acesso negado); pip sem cache não encontrou distribuição
  disponível. Nenhuma dependência foi instalada. O supervisor precisará do extra
  `.[test,test-navegador]` no ambiente do ensaio para executar o HTTP/2, ou esse
  cenário seguirá explicitamente pendente. A prova de negociação/103 em navegador
  e a prova em memória com a biblioteca **não foram executadas nesta rodada**.
* Prerender só pode ser provado num navegador instalado compatível e sem políticas
  recusadas; ausência observada da condição é skip, nunca evidência de recusa do
  produto. Não foram contornadas políticas do Chrome/Edge nem mudadas flags do Brave.
* Gesto humano, segunda conta Windows (item 7), novo ensaio real e auditoria
  independente continuam pendentes. A nota formal do titular sobre o defeito 49
  continua necessária; esta alteração só registra a leitura expressamente autorizada.

## Quinto ensaio real

20/11/2026. Desenvolvedor, no worktree `C:\dev\fv14-0089i`, ramo
`feat/0089-sessao-assistida`, HEAD `e5b1012`. Correções do harness sob a
instrução do supervisor. Nenhum arquivo do produto foi alterado, inclusive
`transport.py` e o adaptador; nenhum método CDP, dependência ou regra de
admissão foi acrescentado. Sem troca de ramo, commit ou push.

### Evidência e classificação

Logs externos lidos, sem alteração:

* `C:\dev\tmp\v5\impl-b\nav-5.log`: **46 passed, 5 failed, 5 skipped**,
  linha 599. SHA-256
  `a3d0afc6f61866d513319c80faf979ad5dacc94d2018d149623936819f35c89d`.
* `C:\dev\tmp\v5\impl-b\item9.log`: no arquivo lido há **quatro rodadas
  falhas** (linhas 174, 347, 520 e 693), todas na igualdade dos pedidos;
  a aprovação isolada informada pelo supervisor não consta desse arquivo.
  SHA-256 `ff71a75bc9014eb5ec7603337ea4fb9b009abaa933c1ca32a579381439dfc750`.

Classes: **A**, defeito do produto; **B**, defeito/insuficiência do harness;
**C**, condição ou limitação do ambiente do ensaio. Corrigir diagnóstico não
prova, por si, a causa de uma diferença do navegador.

| Item do pedido | Análise e classificação | Alteração e limite |
|---|---|---|
| 1 — §3(9), passividade | **B confirmado no diagnóstico e no controle; causa da divergência real ainda não apurada.** `nav-5.log`, linhas 498–502, e as quatro rodadas isoladas mostram diff truncado em `/case/passividade`. Não provam qual campo mudou, nem que seja ruído do navegador. A §3(9) exige igualdade inclusive dos cabeçalhos, e a §2.12 mantém a lista fechada. | Duas execuções **SEM** adaptador e uma **COM**, cada qual com perfil novo e mesmas flags/origem/driver. JSON completo com método/caminho, contagens, campos exclusivos, valores diferentes e coleções iguais em ordem diferente. Só se desconta variação demonstrada nos controles, no mesmo método/caminho; valores e multiplicidades exclusivos do adaptador falham, mesmo em cabeçalho variável. Nenhuma lista fixa de exclusão para `Priority`, GREASE, idioma ou favicon. |
| 2 — cache | **B, identificação indevida por URL.** Linhas 374–400: a asserção por chave que impede admissão das derivadas passou; também passaram a existência dos motivos e sua lista permitida. A falha é só a proibição de qualquer captura na mesma URL. O driver faz dois Fetch sequenciais, e a origem declara `public, max-age=600`. Por eliminação, a captura admitida é da primeira carga de rede, não da carga identificada como derivada. Essa conclusão decorre do fluxo e das asserções, pois o log antigo não imprime os requestIds. **Não há prova de admissão de cache pelo produto.** | O guardião exige recusa e ausência de admissão na chave `(sessão CDP, requestId)` correspondente. O teste identifica duas cargas distintas, primeira sem prova de cache e segunda com prova; exige só uma chegada à origem. A sonda registra flags de disco/memória/prefetch, evento de cache e 304 bruto. A recusa de 304 oculto continua obrigatória; seu motivo próprio é aceito somente no caso cache. Captura de rede anterior não invalida o negativo da segunda carga. |
| 3 — 304, sem cabeçalhos e parcial | **B na expectativa causal; causa exata dos três casos históricos permanece não apurada.** Ao contrário da descrição resumida, as falhas do log estão nos ramos de `EVENTO_ASSISTIDO_RECUSADO` (linhas 87–94, 197–214 e 317–334), procurando `loadingFailed` e erro de rede. O código do teste já admitia `COMANDO_STREAMING_RECUSADO`, com prova de erro do comando. O log truncado não demonstra qual evento causou `EVENTO_ASSISTIDO_RECUSADO`; não autoriza afirmar que o Brave recusou o comando nesses três pedidos. | Mantida a aceitação de streaming recusado, só com erro demonstrado do comando correspondente. A sonda associa cada recusa ao requestId e evento/comando causal. `EVENTO_ASSISTIDO_RECUSADO` exige prova de `requestServedFromCache` ou `loadingFailed` com erro enumerado, no mesmo pedido; evento inócuo ou erro de outro pedido falha. Sem cabeçalhos/parcial continuam exigindo ausência de ambos os eventos de cabeçalhos completos. |
| 4 — Early Hints | **B**, mensagem menciona extra removido. | Mensagem exata: “requer o pacote h2 no ambiente do ensaio; não é dependência do projeto”, no teste real e na prova em memória. Docstrings atualizadas; nenhuma instalação/dependência acrescentada. |
| 5 — limpeza, §3(7) | **B**, o `finally` do harness fechava recursos, mas não chamava a limpeza do perfil; só o caso de segredos a fazia manualmente. A retenção do conftest amplificava o acúmulo. O volume histórico de 24 GB foi informado pelo supervisor, não medido nesta rodada. | Todo encerramento do harness executa `limpar_diretorio` do produto e verifica inexistência do perfil. Fechamentos independentes são todos tentados, mesmo quando um falha. Sobra/erro imprime caminho, classe e motivo e faz o teste falhar. O caso de segredos conserva sua asserção após a limpeza comum. Conftest e perfis históricos não foram alterados ou apagados. |

### Leitura normativa do item 3

* §2.4 linha 4: cabeçalhos completos malformados são `RespostaInvalida`;
  não exige classificar como cabeçalho completo um prefixo parcial que o
  navegador ainda não entregou como `responseReceived`/`ExtraInfo`.
* Linha 5: chunk incompleto/malformado recusado pelo navegador exige **recusa
  da candidata**, sem código específico adicional.
* Linha 12 e §3(1): **expiração do prazo** de 30 s sem nenhum dos dois eventos
  de cabeçalhos completos exige `Timeout`; com algum deles e sem término,
  `RespostaInvalida`. Prefixo parcial permanece na primeira categoria.
* §2.3(1): 304, inclusive exposto como 200, não pode ser captura;
  §2.5(2): streaming falho ou tardio obriga recusar. Não há nessas condições
  um motivo único obrigatório nem obrigação de esperar expirar um pedido
  já recusado. `COMANDO_STREAMING_RECUSADO` só serve como alternativa com
  erro do comando provado; não substitui os códigos da linha 12 na expiração.
* As provas sintéticas da porta das linhas 4, 5 e 12 e do 304 oculto foram
  preservadas e executadas. Novo ensaio real deve distinguir recusa de cache,
  falha de rede e erro de streaming com a nova correlação; nenhum desses fatos
  foi retroativamente atribuído ao navegador sem evidência.

### Arquivos e validação

Alterados seis arquivos Python de teste/harness:
`tests/harness_assistida_0089.py`,
`tests/harness_assistida_0089_cenarios.py`,
`tests/harness_assistida_0089_h2.py`,
`tests/test_assistida_0089_harness.py`,
`tests/test_assistida_0089_navegador.py` e
`tests/test_assistida_0089_navegador_cenarios.py`, além deste registro.

* Regressões offline: campos variáveis só com controle e valores observados;
  método/caminho/quantidade/favicon/campos exclusivos não descontados;
  ordem de chegada/campos só descontada com controle; multiplicidades
  preservadas em pedidos repetidos; diagnóstico estruturado; primeira captura
  de rede seguida de disco/memória/prefetch/304 oculto, com rejeição de admissão
  indevida; evento causal de outro pedido/inócuo recusado; erro de streaming
  correlacionado mesmo sem `sessionId` na resposta do comando; limpeza em fim
  normal, erro, skip, interrupção e falha de fechamento, com registro de sobra.
  São provas sintéticas, sem navegador ou sockets, não prova real de Brave.
* A regressão de multiplicidade foi executada antes de endurecer esse ponto
  do novo comparador: **1 failed**, pois combinava duas ocorrências de uma
  variante vista só uma vez por controle. O comparador corrigido preserva
  também a coleção de valores de cada campo por método/caminho.
* Validação final dos nove módulos
  `test_transport_assistida_0089.py` e
  `test_assistida_0089_{cdp,harness,grafo,ambiente,cortes,indicacao,integracao,fronteiras}.py`:
  `.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider
  -m "not live and not navegador_assistido" ... --tb=short -ra`:
  **453 passed, 1 skipped em 9,94 s**, exit 0. `TMP`, `TEMP` e `--basetemp`
  ficaram fora do checkout, sob `%TEMP%\fv0089-nav5-final2`.
* Único skip: prova HTTP/2 em memória por ausência de `h2`, com a mensagem
  corrigida. Não é prova executada nem dependência nova do projeto.
* Coleta dos dois módulos reais com `.venv`, `-p no:cacheprovider` e
  `--collect-only`: **56 testes**, exit 0; nenhuma janela aberta.
* `C:\dev\tmp\venv-ruff\Scripts\python.exe scripts\ruff_catraca.py`:
  **exit 0**. Os seis arquivos Python passam `ruff check --no-cache` e
  `ruff format --no-cache --check`. `git diff --check`: limpo.
* `git diff --exit-code -- freoa_verifica/transport.py freoa_verifica/assistida`:
  exit 0, nenhuma mudança de produto. Ramo e HEAD reconferidos e preservados.

### Questões pendentes

Reensaio real corrigido, suíte completa e auditoria independente: **NOT RUN**.
O reensaio deverá conservar a saída completa do item 9 e a correlação causal
dos três negativos; `-rP` expõe também os diagnósticos dos testes que passam.
A variação real de cabeçalhos não foi provada nesta rodada; nenhuma exceção
fixa foi autorizada. Se os novos controles não explicarem uma diferença do
adaptador, o item 9 continuará falhando. Se o navegador produzir outro evento
ou erro de rede não enumerado, o item 3 continuará falhando com diagnóstico,
sem aprovação por mera ausência de captura. Limpeza real dos perfis do novo
ensaio e os cenários sem pré-requisito (h2/prerender/gesto humano/segunda conta)
continuam dependentes do ensaio externo. Não houve limpeza dos 24 GB históricos.

## Sexto ensaio real

### Escopo e evidência

Papel Desenvolvedor, em `C:\dev\fv14-0089i`, ramo
`feat/0089-sessao-assistida`, HEAD `8b8eb3e`, preservados. Leitura dos logs do
sexto ensaio externo com Brave 1.100; nenhum navegador foi lançado nesta rodada.
Não houve commit, push, troca de ramo ou limpeza dos perfis históricos.

Fontes locais, lidas integralmente para separar os blocos de falha:

* `C:\dev\tmp\v5\impl-b\nav-6.log`, SHA-256
  `266e024280e26c64651100cd000a17766b23cf973cbc721e694c7650127620eb`.
  Resultado original: **16 failed, 35 passed, 5 skipped**, 688,71 s.
* `C:\dev\tmp\v5\impl-b\item9.log`, SHA-256
  `72b2be8a4b3f960b326421f8b79ee3e5fed169ced88ade371f1a6561ff8a745d`.
  Quatro rodadas; `ler9.py` foi lido e executado para conferir o resumo.

Classes: **A**, produto; **B**, expectativa/insuficiência do harness;
**C**, condição ou limitação do ambiente. A leitura autorizada do controle q
e dos prazos de limpeza está registrada em
`docs/decisoes/0089-nota-execucao-sexto-ensaio.md`.

### Análise e classificação

| Evidência | Classe e conclusão | Tratamento nesta rodada |
|---|---|---|
| 13 falhas `WinError 32` em `nav-6.log`; item 9 rodadas 3 e 4 | **A**. `fechar_navegador` terminava o Job e esperava só o principal; `limpar_diretorio` removia sem esperar filhos nem repetir. O produto compartilhava o defeito que o harness tornou visível. | Espera limitada do principal e dos processos do perfil, remoção com repetição e recuperação de sobra; mesmo caminho de produto no harness. |
| zstd, iframe, blob, websocket, encoding, cl21, cl_duplicado | **A**, todos são exclusivamente `WinError 32` no bloco de falha: linhas 1111–1191, 1665–1745, 1805–1885, 2085–2165, 107–204, 450–547 e 1222–1302, respectivamente. | Não há outra exceção anterior encoberta nesses sete blocos. A rodada (h) tornou a limpeza obrigatória e expôs o defeito; não há evidência de regressão em bytes, escopo ou recusa nesses casos. O reensaio real ainda é necessário. |
| Outras seis falhas de limpeza: pipe/ACL, consumidor tardio, cl_truncado, cache, bfcache, download | **A**, mesmo mecanismo e mesma exceção. Com as sete acima, totalizam exatamente 13. | Correção comum, sem alterar os cenários ou os motivos de recusa. |
| 304, linhas 205–449 | **B**. O JSON correlaciona `responseReceivedExtraInfo` com status bruto 304 e depois `Network.loadingFailed`, `net::ERR_ABORTED`, no mesmo requestId. O produto recusa por `EVENTO_ASSISTIDO_RECUSADO`; o guardião esperava apenas `ERR_CACHE_MISS` nesse ramo. | Analisado; expectativa continua falhando até ajuste específico do harness. Não se alterou a recusa do produto nem se admitiu 304. |
| sem_cabecalhos e parcial, linhas 548–790 e 791–1033 | **B**. Cada JSON mostra `requestWillBeSent`, `requestWillBeSentExtraInfo` e `loadingFailed` com `ERR_ABORTED`; nenhum dos dois eventos de cabeçalhos completos. O teste aceita recusa por evento, mas sua lista de erros não inclui esse valor. | Analisado; expectativa preservada. Não é expiração de prazo nem prova de cabeçalhos completos: não se exige retroativamente `Timeout` para uma candidata já recusada. A causa interna do `ERR_ABORTED` não foi estabelecida. |
| JSON `cache_cargas`, linhas 1469–1488 | A primeira chave é rede/admitida; a segunda, distinta, é derivada/não admitida. A única falha desse teste é a limpeza posterior (**A**). | Preservada a prova por requestId, sem remover a captura de rede legítima nem afrouxar recusa de cache. |
| Campos `prefetch`, `cache`, `sw`, `subtipo` nos JSONs dos três negativos | São campos da sonda, em grande parte nulos nesses eventos, não falhas autônomas de prefetch/SW/prerender. Não há blocos FAILED separados de SW ou prefetch. | Não inferir regressão de produto pela simples presença desses nomes. O log sem `-rP` não contém os diagnósticos dos testes aprovados. |
| Cinco skips, linhas 2167–2171 | **C**: extensão com gesto humano, prerender não produzido pelo Brave, ausência de h2, recarga humana e inexistência de segunda conta Windows. | Permanecem sem prova real desses aceites, sem contorno nem dependência nova. |

Os 13 blocos de limpeza não contêm outra falha de asserção nem encadeamento de
exceção anterior. Descontados esses blocos, restam exatamente os três negativos
com `ERR_ABORTED`, não falhas de captura aceita. O `WinError 10054` emitido pelo
servidor HTTPS em thread é diagnóstico de conexão encerrada; não é um bloco de
falha adicional nem explica por si a origem dos três cancelamentos.

### Item 9: prova e regra limitada

| Rodada em item9.log | SEM 1 | SEM 2 | COM | Diagnóstico original |
|---|---|---|---|---|
| 1, linhas 2–3889 | `pt-BR,pt;q=0.6` | `pt-BR,pt;q=0.7` | `pt-BR,pt;q=0.8` | Só q difere nos quatro pedidos. |
| 2, linhas 3890–7777 | `pt-BR,pt;q=0.5` | `pt-BR,pt;q=0.6` | `pt-BR,pt;q=0.9` | Só q difere nos quatro pedidos. |
| 3, linhas 7778–8051 | — | — | — | `WinError 32` ao limpar COM; sem JSON completo. |
| 4, linhas 8052–8209 | — | — | — | `WinError 32` ao limpar SEM 1; sem JSON completo. |

Classificação **B com prova** para as duas rodadas com JSON: a mesma variação
surge sem adaptador em `/driver`, `/case/passividade`, `/favicon.ico` e `/done`.
Método, ordem de chegada, idiomas e demais cabeçalhos permanecem iguais.
O mecanismo de fingerprinting é informação do supervisor; a prova nos logs é
a variação entre controles. As outras duas rodadas provam apenas a falha A.

O comparador normaliza somente posições de qvalues válidos que variaram entre
controles daquele campo/ocorrência. Mantém igualdade literal de idioma, ordem,
demais parâmetros e posições q estáveis; campos estáveis não recebem exceção.
Variação mista conserva a regra anterior de valores e multiplicidades vistos.
O diagnóstico conserva os três conjuntos originais e registra controles,
adaptador, normalização e justificativa. Não há lista fixa de cabeçalhos ignorados.

Reaplicação offline aos pedidos reconstruídos dos **JSONs originais** das
rodadas 1 e 2: ambas passaram, com quatro normalizações cada. Isto não é novo
ensaio de navegador, nem inventa valores das rodadas interrompidas.

### Implementação e arquivos

* `freoa_verifica/assistida/ambiente.py`: confirmação limitada a 15 s por chamada
  para principal e processos com argumento exato do perfil; PowerShell/CIM local
  somente leitura, sem janela nem perfil pessoal; enumeração falha fecha o
  caminho. Job e kill do principal são os já existentes. Limpeza confinada,
  20 tentativas com intervalos de 100 ms; sobra marcada e informada, recuperada
  pelo mesmo caminho antes de criar outra sessão. Nome prefixado é a marca
  alternativa caso não se consiga gravar `.limpeza-pendente`.
* `freoa_verifica/assistida/sessao.py`: mesmo encerramento antes da seleção;
  finalização por `ExitStack` tenta todos os recursos e limpa por último, mesmo
  se um fechamento falhar. Encerramento e limpeza possuem esperas distintas;
  uma falha na primeira pode ser seguida de nova espera de até 15 s na segunda.
* `tests/harness_assistida_0089.py`: passa o perfil ao encerramento do produto;
  continua falhando explicitamente quando a limpeza deixa sobra.
* `tests/harness_assistida_0089_cenarios.py`: regra q limitada e diagnóstico.
* `tests/test_assistida_0089_ambiente.py`: processos/arquivos simulados, saída do
  principal antes e depois dos filhos, prazo expirado, enumeração indisponível,
  bloqueio que libera e persistente, recuperação, caminho externo intacto,
  seleção exata do argumento e finalização integral mesmo com erro.
* `tests/test_assistida_0089_harness.py`: q novo permitido, idioma/ordem/idioma
  extra/parâmetro extra/q inválido/q estável/outro campo recusados; atualiza os
  dublês do encerramento compartilhado, preservando provas anteriores.
* Este registro e `docs/decisoes/0089-nota-execucao-sexto-ensaio.md`.

Nenhuma alteração em `transport.py` ou `cdp.py`, método CDP novo, dependência,
fixture, regra de admissão de candidata ou critério de `verified`.

### Validação e questões

Validação final sobre os seis arquivos Python já formatados:

* `.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider
  -m "not live and not navegador_assistido"` nos nove módulos
  `test_transport_assistida_0089.py` e
  `test_assistida_0089_{cdp,harness,grafo,ambiente,cortes,indicacao,integracao,fronteiras}.py`,
  com `--tb=short -ra`: **484 passed, 1 skipped em 9,21 s**, exit 0.
  `TMP`, `TEMP` e `--basetemp` fora do checkout, sob
  `%TEMP%\fv0089-nav6-final2` (TEMP original do processo).
* Único skip: HTTP/2 em memória, falta de `h2` no ambiente. Não foi acrescentada
  dependência nem alegada prova desse teste.
* Coleta dos dois módulos reais com `.venv`, `-p no:cacheprovider` e
  `--collect-only`: **56 testes**, exit 0; nenhuma janela aberta.
* `C:\dev\tmp\venv-ruff\Scripts\python.exe scripts\ruff_catraca.py`:
  **exit 0**, executado separadamente para observar seu código de saída.
* Os seis arquivos Python: `ruff check --no-cache` e
  `ruff format --no-cache --check`, ambos **exit 0**; seis arquivos formatados.
  `git diff --check`: sem erro. As advertências de CRLF do Git e os diretórios
  históricos `pytest-cache-files-*` sem acesso não foram tratados como falha
  de código nem apagados.
* `git diff --exit-code -- freoa_verifica/transport.py
  freoa_verifica/assistida/cdp.py`: sem diferenças. Ramo e HEAD reconferidos.

Questões pendentes:

1. Reensaio real externo da limpeza e do item 9: **NOT RUN**. Processos e
   arquivos simulados provam o fluxo, não o prazo observado no Brave 1.100.
   Nova rodada deve guardar diagnósticos completos, inclusive aprovados (`-rP`).
2. Três expectativas B de `ERR_ABORTED` foram analisadas, sem alteração nesta
   rodada, cujo pedido para as demais falhas era de análise/classificação.
   Se corrigidas, devem continuar exigindo o evento impeditivo do mesmo
   requestId, status bruto 304 no caso 304, ausência de cabeçalhos completos
   nos outros dois e ausência de captura. Não se autoriza êxito por mero zero.
3. Cinco condições C do ensaio original continuam pendentes dos respectivos
   pré-requisitos. Não se inferem provas reais de logs que não as contêm.
4. Suíte completa do repositório e auditoria independente: **NOT RUN**.
   A implementação não declara o marco aprovado. O supervisor fará o commit;
   não houve tentativa de commit nem alteração de outro checkout.

## Sétimo ensaio real

### Escopo, evidência e classificação

Papel Desenvolvedor, `C:\dev\fv14-0089i`, ramo
`feat/0089-sessao-assistida`, HEAD `deacd20`. Correção dos testes autorizada
pelo supervisor; nenhum navegador lançado nesta rodada. Produto, transporte,
regras de admissão e decisão 0089 preservados. Sem commit, push ou troca de ramo.

* `C:\dev\tmp\v5\impl-b\nav-7.log`, SHA-256
  `d9d39f7997fb3af2729fa0fff326dbe37402e26432ba409758e7d60982018474`:
  **3 failed, 48 passed, 5 skipped**, 1124,30 s. Os três negativos do item 1
  mostram `Network.loadingFailed` e `net::ERR_ABORTED` (linhas 236, 479, 722).
* `C:\dev\tmp\v5\impl-b\item9.log`, SHA-256
  `509274c35174b5926ec31faf9e47517ac1f940640e71cde334891861143f2976`:
  rodada 1 falha, rodadas 2–4 passam. `ler9.py` foi lido e executado; só a
  rodada 1 tem JSON nesse log. Os controles dessa rodada têm o mesmo
  `Accept-Language` (`pt-BR,pt;q=0.9`), enquanto o adaptador tem q=0.7.
  Não havia variação nos controles que autorizasse normalizar q.

Classificação **B**, insuficiência do harness, nos dois itens. O antigo caso
304 enviava 304 diretamente, sem primeira carga cacheável nem condicional.
Os outros dois encerravam a conexão depois de `sleep(31)`, sem sincronizar seu
tempo com o início da candidata. Além disso, o HTML inicial relê o sinal a cada
100 ms e executava novamente `location.href`: enquanto espera cabeçalhos, o
documento antigo continua vivo, podendo abortar sua própria navegação. Esse
mecanismo foi identificado por inspeção; sua contribuição para os abortos do
log não foi isolada em navegador nesta rodada. Não há prova de defeito **A**
do produto que autorize alterá-lo.

### Item 9: controles até variação ou teto

`coletar_controles_passividade` executa no mínimo dois e no máximo quatro
controles SEM adaptador, em perfis distintos, antes da execução COM adaptador.
Só encerra antes do teto quando encontra variação de q no mesmo campo
`Accept-Language`, método, caminho e ocorrência. Variação de outro campo não
encerra a coleta. O comparador considera todos os controles efetivamente
colhidos e normaliza somente posições q que variaram entre eles; quatro
controles idênticos não autorizam normalização. Idiomas, ordem, demais
parâmetros, posições q estáveis, contagens e multiplicidades continuam sob os
guardiões anteriores. Não há cabeçalho ignorado por regra fixa.

O JSON contém todos os controles brutos, o conjunto COM adaptador, comparações
de cada controle com ele e justificativa por campo/ocorrência. As chaves antigas
de diagnóstico dos dois primeiros controles foram preservadas.

### Item 1: condições efetivas e códigos

* **304 exposto como 200:** página local faz duas cargas sequenciais da mesma
  URL. Primeira resposta 200 com ETag e cache público permitido, sujeito a
  revalidação; segunda carga usa a API web `fetch` com `cache: 'no-cache'`.
  A origem só responde 304 ao receber o ETag correto em `If-None-Match`.
  O teste exige primeira captura de rede, segundo requestId distinto, origem
  304 condicional, `responseReceived` 200 e ExtraInfo bruto 304 do segundo
  pedido, recusa `STATUS_ASSISTIDO_DIVERGENTE` / `RespostaInvalida` e nenhuma
  admissão da revalidação. A primeira captura legítima é preservada.
* **Sem cabeçalhos:** a origem aceita e lê o pedido, sem enviar resposta, e
  mantém a conexão até o teardown. Exige `PRAZO_ASSISTIDO_SEM_RESPOSTA` / `Timeout`.
* **Cabeçalho parcial:** envia apenas a linha de status e `Content-Typ`, sem
  completar o cabeçalho, mantendo a conexão até o teardown. Exige o mesmo
  `Timeout`, sem evento de cabeçalhos completos.
* **Cabeçalhos completos, sem término:** novo caso `sem_termino`; envia status,
  Content-Type, Content-Length 999, fim dos cabeçalhos e apenas `<html>`.
  A origem separa os cabeçalhos desse fragmento por 300 ms, como nos positivos,
  para permitir o início do streaming antes dos dados.
  Mantém a conexão até o teardown; exige `PRAZO_ASSISTIDO_INCOMPLETO` /
  `RespostaInvalida`, com sinal de resposta completa e sem `loadingFinished`.

As conexões pendentes usam `Event.wait()` sem prazo próprio, liberado apenas
quando o contexto do servidor termina, depois do contexto do navegador. O sinal
da página é executado uma única vez, também no controle SEM adaptador.

Se houver aborto próprio antes da conclusão normativa, o teste exige recusa
por `Network.loadingFailed` do mesmo requestId, com `errorText` não vazio, e
ausência de admissão do pedido afetado; publica o diagnóstico completo e marca
**skip `CENARIO_ITEM1_NAO_REPRODUZIVEL_NO_NAVEGADOR`**, contendo o erro observado.
Isso não aprova o código normativo. Outros motivos, ausência de recusa ou
admissão indevida continuam falhando. Os códigos são provados offline pela
porta: `test_linha_12_prazo_sem_eventos` tem os três casos nomeados e
`test_proveniencia_304_oculto` conserva o confronto 200/304.

### Provas e validação

Arquivos Python tocados: `harness_assistida_0089.py`,
`harness_assistida_0089_cenarios.py`, `test_assistida_0089_harness.py`,
`test_assistida_0089_navegador.py`, `test_assistida_0089_navegador_cenarios.py`
e `test_transport_assistida_0089.py`, todos sob `tests/`.

* Provas offline novas: 2/3/4 controles com e sem variação; parada na variação
  ou no teto; variação de outro campo não encerra coleta; posições q estáveis,
  idioma e outro campo preservados; bytes parciais/completos e espera sem
  fechamento prematuro; 200 cacheável antes do 304 condicional; códigos de
  prazo corretos; ausência de status bruto/aparente correto, código errado e
  admissão indevida recusados; aborto comprovado vira skip, nunca admissão.
* A regressão que troca apenas q de outro campo foi executada antes de fixar
  o alvo da coleta: **1 failed**, pois a coleta terminava com dois controles.
  A correção limita a parada antecipada ao campo investigado.
* `.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider
  -m "not live and not navegador_assistido"`, nos nove módulos
  `test_transport_assistida_0089.py` e
  `test_assistida_0089_{cdp,harness,grafo,ambiente,cortes,indicacao,integracao,fronteiras}.py`,
  `--tb=short -ra`: **513 passed, 1 skipped**, exit 0. O skip é o HTTP/2 em
  memória sem `h2`; nenhuma dependência instalada. `TMP`, `TEMP` e `--basetemp`
  fora do checkout, em `%LOCALAPPDATA%\Temp\fv0089-nav7-final3`.
* Prova adicional com o Node já instalado: o JavaScript gerado pelo sinal foi
  executado dez vezes no mesmo contexto: **um único disparo**, exit 0. Node
  não foi introduzido como dependência de teste ou produto.
* Coleta dos dois módulos de navegador com `.venv`, `-p no:cacheprovider` e
  `--collect-only`: **57 testes**, exit 0, sem abrir navegador.
* `C:\dev\tmp\venv-ruff\Scripts\python.exe scripts\ruff_catraca.py`:
  **exit 0**. Nos seis arquivos Python: `ruff check --no-cache` e
  `ruff format --no-cache --check`: **exit 0**, seis arquivos formatados.
* `git diff --check`: limpo. Produto e `transport.py` sem diferenças.

### Questões

Reensaio real do harness corrigido, suíte completa do repositório e auditoria
independente: **NOT RUN**. A comprovação real do 304 oculto e dos três prazos
depende da próxima rodada; recomenda-se conservar stdout dos aprovados (`-rP`)
e motivos dos skips (`-ra`). A origem não força o navegador a completar a
condição: aborto próprio demonstrado permanece não reproduzível, com cobertura
offline explícita. Os cinco pré-requisitos ausentes do ensaio original continuam
pendentes. Nenhum método CDP novo, dependência, fixture ou alteração do produto.
O marco não foi declarado aprovado; o supervisor fará o commit.
