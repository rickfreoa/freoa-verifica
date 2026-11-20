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
