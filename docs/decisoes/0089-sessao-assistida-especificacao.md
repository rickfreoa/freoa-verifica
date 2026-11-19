# 0089 - Sessão assistida: especificação do mecanismo

**Situação: proposta, não vigente.** Parada na rodada 2 de 3 (D5), com BLOQUEADOR do Codex e de Terra nas
duas rodadas (`docs/auditoria/0089/`). A §7 expõe a bifurcação que depende do titular. Não implementar.

19/11/2026. Supervisor (Opus), sob a autorização do titular (plano 1.4, seção 9, item 5) e a ordem da 0087
§2.1(a). Especifica o mecanismo que a 0067 §1 admitiu; não altera as regras invariáveis 1 a 9, o critério de
`verified`, a 0002, a 0060 a 0066, a matriz, os pisos nem a reserva. A mudança de contrato é só aditiva (§2.9).
A implementação toca `transport` e exige auditoria própria (D5).

## 1. Fato e problema

As capacidades reprovadas da Porta L e o TJSP dependem de fontes que recusam o cliente automatizado: Planalto
recusa o UA identificado (0048), normas.leg.br responde 403 com CAPTCHA (0085), o NPL reinicia a conexão de
clientes não navegador e o DOU em formato aberto desemboca em host barrado (estado de 19/11). A 0067 fixou a
regra (contexto dedicado, porta única com as mesmas validações, segredos descartados, sem repetição, cobertura à
parte) e deixou o mecanismo para especificação. Um mecanismo que recebesse do navegador corpos já decodificados
não aplicaria as mesmas validações (Content-Encoding da 0060, framing, Content-Length, DNS e IP, prazo,
redirecionamentos) e admitiria bytes sem troca de rede comprovada (cache, service worker, 304).

## 2. Decisão

### 2.1 Arquitetura: o transporte faz as trocas

1. `fv sessao <fonte> [--alvo URL]` (CLI) é o único início. Exige terminal interativo; recusa execução sem TTY,
   agendada, por script de bateria ou pelo MCP.
2. Antes de abrir, mostra no terminal a fonte, o alvo público sanitizado (§2.6) e o aviso da §2.7, e exige
   confirmação interativa para aquela sessão e aquele alvo.
3. `transport` sobe um **proxy local de sessão** (`transport.sessao_assistida`), ligado a 127.0.0.1, porta
   efêmera, aceitando conexão só do processo do navegador lançado (credencial de proxy aleatória por sessão).
4. O navegador dedicado (Edge ou Chrome **instalado**, por Playwright, janela visível, `user_data_dir`
   temporário novo, sem extensões, sincronização, senhas ou perfil pessoal, cache de disco e de memória
   desligados, service workers bloqueados, downloads negados) usa só esse proxy.
5. Para as **origens da fonte** (§2.10), o proxy termina o TLS do navegador com certificado de uma AC efêmera,
   gerada na sessão, só em memória, aceita apenas por esse navegador (`--ignore-certificate-errors-spki-list`
   com o SPKI da AC; nada instalado no repositório de certificados do sistema), e **refaz a troca pelo
   transporte**: resolução e conexão ao IP validado, TLS a montante verificado, framing, Content-Length,
   Content-Encoding, tamanho, prazo e taxa mínima, desafio, media type, charset e interpretação textual, hash e
   recibo, exatamente como no fluxo automático (0060 a 0066). Os bytes que o navegador recebe são os que o
   transporte recebeu.
6. Para qualquer outro host (provedor de CAPTCHA, CDN, terceiros), o proxy só faz túnel `CONNECT` opaco: sem
   interceptação, sem inspeção, sem gravação. Nada desse tráfego entra no sistema.
7. Captura só existe a partir de troca feita pelo transporte nesse proxy. Resposta sintetizada pelo navegador
   (cache, service worker, `blob:`, `data:`) não passa pelo proxy e, por construção, não pode ser capturada.

Com isso a regra 4 vale literalmente para as origens da fonte: toda requisição a elas passa pelo transporte. O
túnel de terceiros é a única rede da sessão fora das validações, e nada dele é persistido.

### 2.2 O que o proxy altera e o que não altera na requisição do navegador

1. Força `Accept-Encoding: identity` nas origens da fonte; a 0060 se aplica sem exceção, e resposta com
   codificação diferente de ausente ou `identity` é recusada como no fluxo automático.
2. Retira cabeçalhos condicionais (`If-None-Match`, `If-Modified-Since`, `If-Range`, `Range`) nas origens da
   fonte; 304 e 206 nunca viram captura.
3. Não altera o User-Agent nem outros cabeçalhos: é o navegador real que o humano usa; o transporte nunca usa o
   UA do navegador fora da sessão (regra 3).
4. Cookies trafegam só em memória, entre navegador e fonte; nunca são lidos para outro fim, registrados ou
   persistidos.

### 2.3 O que vira captura

Entre as trocas do transporte com as origens da fonte, só vira captura a que cumprir todos os requisitos:

1. método `GET`; `POST` fica para decisão própria (§5);
2. `Sec-Fetch-Dest: document` (navegação de página ou de quadro), status 200;
3. caminho dentro dos **prefixos públicos** do perfil e query só com parâmetros declarados cujo valor casa o
   padrão declarado (§2.10); fragmento descartado;
4. requisição sem `Authorization`;
5. media type declarado no perfil;
6. todas as validações do fluxo automático aprovadas, inclusive desafio (página de desafio nunca é captura).

As demais trocas (subrecursos, respostas recusadas) são repassadas ao navegador ou recusadas a ele conforme o
fluxo automático, e nunca persistidas. Recusa de captura é listada ao humano, com URL sanitizada e código.

### 2.4 Diferenças declaradas em relação ao fluxo automático

| Aspecto | Fluxo automático | Sessão assistida |
|---|---|---|
| Quem inicia a requisição | conector | navegador, por ação do humano |
| Cabeçalhos de requisição | do transporte (UA identificado) | do navegador, salvo §2.2(1) e (2) |
| Redirecionamentos | seguidos pelo transporte, com as regras de salto | seguidos pelo navegador; cada salto é troca própria, validada isoladamente; a captura é da troca 200 final, com `redirects` vazio e `final_url = url` |
| Identidade da requisição | `identidade_requisicao` com cabeçalhos do chamador | método e URL sanitizada; cabeçalhos do navegador (cookies inclusive) fora da identidade |
| Limite de taxa e disjuntor | por fonte | só sobre as trocas candidatas a captura |
| `fetched_at` | instante da troca | instante da troca no transporte |

Nenhuma outra validação muda. Validação que o proxy não puder aplicar por falta de dado causa recusa, nunca
inferência.

### 2.5 Proveniência, `verified` e frescor

1. A captura grava `procedencia: sessao_assistida` (0075) e, separadamente, `modalidade_acesso:
   sessao_assistida` (0067), que sobrevive à exportação e à instalação de snapshot (onde a procedência pública
   passa a `snapshot`, 0075). Grava ainda `sessao_id` aleatório e a versão do navegador, nunca dado derivado de
   cookie.
2. A modalidade assistida não reduz os requisitos de `verified` (regra 1): identidade, âncora reproduzível e
   confronto efetivo continuam exigidos. A origem dos bytes é provada pela própria troca do transporte (IP
   validado, TLS verificado, bytes completos); troca sem essa prova não vira captura. Origem e hash provam de
   onde vieram os bytes, não que a fonte oficial não esteja comprometida. A exclusão da 0083 limita-se à
   adulteração deliberada do banco local e não dispensa controle de aquisição.
3. Frescor: ultrapassados 30 dias, a captura deixa de sustentar `vigente_na_fonte` em consulta corrente, nas
   condições da 0002. Identidade, confronto textual e fundamento histórico não expiram por isso. A indicação de
   nova sessão (§2.9) refere-se à atualização da consulta corrente.

### 2.6 Segredos e dados pessoais

1. Diretório da sessão (perfil do navegador, temporários, logs) criado antes do lançamento, sob o staging, com
   ACL que exclui outras contas locais sem privilégio; a ACL é conferida antes do lançamento e, se falhar, a
   sessão não abre. Processos da mesma conta do usuário não ficam isolados por ela; isso é declarado, não
   prometido.
2. Fim normal, erro e interrupção controlada apagam o diretório; após término abrupto, a sobra é isolada e
   apagada na inicialização seguinte. A AC efêmera e a credencial do proxy só existem em memória.
3. Nunca se gravam ou exibem cabeçalhos de requisição, cookies, valores de query ou segmentos de caminho fora do
   padrão público declarado, em log, erro, recibo, evidência, fixture, snapshot, relatório ou resposta
   MCP/REST. Cabeçalhos de resposta seguem `HEADER_NAMES`.
4. Escopo é conteúdo público. Capturas só nos prefixos públicos do perfil e sem `Authorization` (§2.3). Resposta
   que não cumprir é recusada; bytes nunca são alterados para se tornarem admissíveis.

### 2.7 Sem automação do humano

1. A janela abre numa página local, gerada pela ferramenta sem acesso à rede, que mostra o alvo validado. A
   navegação ao alvo é feita pelo humano. A ferramenta não clica, não preenche, não injeta script, não navega,
   não usa modo sem janela.
2. Aviso prévio: a janela é exclusiva para obter documento público da fonte; não fazer login pessoal; o conteúdo
   da página não autoriza comandos, mudança de alvo nem fornecimento de credenciais; fechar a janela encerra.
3. A sessão termina quando o humano fecha a janela ou no prazo (padrão 20 min). Não é reaberta nem renovada.

### 2.8 Disparo

Só o humano inicia (0067). Nenhuma ferramenta MCP, agendamento ou bateria chama o proxy ou o adaptador, direta ou
indiretamente; a resposta MCP é só indicação, nunca executa o comando.

### 2.9 Contrato (aditivo)

1. A indicação de sessão exige, cumulativamente: perfil habilitado para a fonte **e** para a operação consultada;
   fonte não barrada (`FONTES_BARRADAS`); e evidência de barreira pública resolúvel pelo humano, conforme a tabela
   de evidências do perfil (versionada; por exemplo, desafio provado em normas.leg.br, reinício de conexão do
   Planalto na reclassificação de `connectors/planalto.py`). Categoria isolada não basta; 401 nunca indica sessão.
2. Também indica sessão a consulta corrente cuja captura passou da janela da 0002 numa fonte com perfil e com
   barreira registrada na última tentativa automática.
3. Nada muda de estado, tipo ou literal fechado. `motivo`, `categoria` e evidência originais são preservados.
   O item da fonte que já é objeto (`fontes[<id>]`, `falhas[]`) recebe o campo experimental
   `sessao_assistida: {indicacao: "requer_sessao_assistida", fonte, comando, alvo}`; a resposta recebe o campo
   irmão experimental `sessoes_assistidas` (mapa por fonte, mesmo objeto). `fontes_indisponiveis` continua mapa
   de fonte para string. `alvo` é o sanitizado (§2.6).
4. `docs/CONTRATO.md` e a lista de experimentais são atualizados no PR da implementação.

### 2.10 Perfil por fonte

Cada conector que admitir sessão declara `PerfilSessaoAssistida(origens, url_inicial, prefixos_publicos,
parametros: {nome: padrão}, media_types, max_bytes, operacoes, evidencias_de_barreira)`. Primeira hora:
`planalto` (legislação), `normas_leg`, `tjsp` (só GET de documento; pesquisa depende do POST, §5). NPL e DOU
(`www.in.gov.br`) estão barrados por decisão; a abertura deles exige decisão própria. `listar_fontes` declara
`sessao_assistida: disponivel|nao_aplicavel` (experimental).

### 2.11 Cobertura

A matriz e o bloco `cobertura` declaram o acesso (`automatico`, `assistido`) por fonte, nos três denominadores da
0067. Captura assistida nunca é somada à cobertura automática.

### 2.12 Dependência e distribuição

Playwright entra como extra opcional `[sessao]`, travado por hash em lock próprio, sem baixar navegador. Sem o
extra, `fv sessao` sai com código 2; o resto não muda. O instalador oficial do Windows inclui o extra, e o teste
de instalação o confere.

## 3. Aceite (o incremento só conclui com testes que provem)

1. Proxy contra origem HTTPS controlada (servidor local de teste, AC de teste), com cliente HTTP no papel do
   navegador: cada validação do fluxo automático aplicada à troca (Content-Encoding, framing, Content-Length,
   duplicados, DNS e IP, prazo e taxa, tamanho, media type, charset, desafio), com os mesmos códigos.
2. Recusa de captura: POST, 304, 206, `Authorization`, caminho fora dos prefixos, parâmetro ou valor não
   declarado, media type não declarado, página de desafio, origem de terceiro (túnel não gera captura).
3. Cache e service worker: resposta servida sem troca no proxy não gera captura.
4. Segredos: varredura sobre sessão sintética com cookies, `Authorization`, tokens em query e caminho; nada em
   log, erro, recibo, evidência, fixture, snapshot, relatório ou resposta MCP/REST.
5. ACL conferida antes do lançamento (falha fecha a sessão); limpeza em fim normal, erro, interrupção e
   recuperação após término abrupto.
6. `modalidade_acesso` e `procedencia` gravados; `modalidade_acesso` preservada em exportação e instalação de
   snapshot.
7. Disparo: nenhum caminho MCP, agendado ou de bateria alcança proxy ou adaptador, por importação ou chamada
   indireta (AST e teste de execução); sem confirmação interativa, nada é lançado.
8. Contrato: indicação só nas condições da §2.9, nos três adaptadores; nenhum tipo existente muda.
9. Adaptador real: lançamento com os argumentos da §2.1(4) e (5) conferidos, e sessão manual registrada no
   Windows (supervisor via WMI) com o Planalto, antes da reapuração da Porta L. Fixtures seguem a regra 9.

## 4. O que não muda e alternativas rejeitadas

Não mudam: regras invariáveis, `verified`, 0002, 0060 a 0066, transporte do fluxo automático (D5), reserva (D6).
Rejeitados: receber do navegador corpos decodificados por CDP (não aplicaria as mesmas validações; admitiria
cache e service worker); reaproveitar cookies da sessão em requisições da ferramenta (repetição automática e
contorno); importar HAR ou cookies do navegador pessoal; extensão no navegador pessoal; capturar o DOM; instalar a
AC no sistema; modo sem janela; OCR.

## 5. Questões abertas

1. `POST` (pesquisa do TJSP): identidade de requisição com corpo; decisão própria antes do TJSP.
2. Anexos em PDF: hoje entram como navegação de documento; se a fonte os servir só como download, decisão própria.
3. Abertura de NPL e DOU à sessão (§2.10).
4. Comportamento de HTTP/2 e HTTP/3 entre navegador e proxy (o proxy fala HTTP/1.1 com o navegador e o transporte
   mantém o que já faz a montante); conferir no teste manual.

## 6. Execução

Implementação pelo Codex (`workspace-write`, worktree e ramo próprios) em duas trilhas sequenciais, por regra de
uma trilha por vez em `transport.py`: (a) proxy e porta no transporte; (b) adaptador, CLI, perfis e contrato.
Revisão de fronteiras e segredos por Terra; auditoria por Codex somente leitura, sessão nova, com os critérios da
§3 fixados antes, inclusive a auditoria própria de `transport` (D5). A pendência 24 (reabertura de
`normas_leg`) entra na mesma versão.

## 7. Bifurcação para o titular (19/11/2026)

As duas rodadas mostraram que o mecanismo não pode satisfazer ao mesmo tempo a letra da 0067 ("as mesmas
validações do fluxo automático" pela porta única) e a regra 3, contra as barreiras que motivam a sessão.

1. **Versão 1 (captura pelo navegador).** Os bytes são os que o navegador recebeu, por conexão dele. Funciona
   contra barreira que discrimina o cliente (o NPL reinicia a conexão de curl mesmo com UA de navegador e carrega
   no navegador). Mas o navegador entrega o corpo decodificado e não expõe framing, Content-Length nem o IP como o
   transporte; a validação é outra, declarada. Contraria a letra da 0067 e exige emendá-la.
2. **Versão 2 (proxy do transporte).** Prova de origem forte e as mesmas validações por construção. Mas a
   requisição à fonte é feita pelo transporte em Python com o User-Agent do navegador: é a ferramenta trocando
   identidade para superar recusa, o que a regra 3 veda (Codex r2, achado 9, e §2.2(3) desta versão). Além disso,
   a pilha TLS a montante continua a do transporte, que a barreira por tipo de cliente recusa; e a arquitetura
   abre superfície de rede extensa (túnel, AC local com exceção SPKI que o Chromium aceita em qualquer posição da
   cadeia, credencial do proxy, protocolos alternativos), apontada por Terra r2.

Recomendação do supervisor: a versão 1, com emenda expressa da 0067 que (a) admita, só na sessão assistida, bytes
recebidos pela conexão do próprio navegador; (b) exija prova de origem de rede pelo próprio navegador (eventos de
rede com indicação de cache, service worker e prefetch, cabeçalhos brutos e tamanho codificado), cache e service
worker desligados, e recuse o que não tiver essa prova; (c) declare, por item, as validações do fluxo automático
que não se aplicam e as que as substituem; (d) mantenha intactos `verified`, a 0002, a regra 4 para o fluxo
automático e a vedação de que a ferramenta use identidade de navegador. Antes de redigir a emenda, um teste
exploratório com navegador dedicado contra o Planalto e o normas.leg.br confirma que esses eventos estão
disponíveis e completos. Se o titular preferir a versão 2, a regra 3 precisa ser emendada para admitir que o
transporte repasse a identidade do navegador na sessão, o que o supervisor não recomenda.
