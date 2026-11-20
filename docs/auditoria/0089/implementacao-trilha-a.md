# 0089 — Implementação da trilha (a)

19/11/2026. Papel: Desenvolvedor. Base: 87b43f7a80da4eb88a1bf98d83e840c102033884;
worktree C:\dev\fv14-0089i, ramo feat/0089-sessao-assistida. Especificação: 0089 vigente v5.2.
Sem rede, instalação, troca de ramo ou publicação. Este registro não substitui a auditoria independente D5.

## Interface para a trilha (b)

transport.capturar_assistida(sessao, pedido) cria uma captura incremental no requestWillBeSent.
O adaptador entrega EventoAssistido a observar() e chama admitir() após o término e todos os metadados.
Só admitir() devolve CapturaAssistida. A porta não grava bytes; a trilha (b) resolve vínculos, obtém seleção
humana, confere novamente o ambiente e persiste os exemplares selecionados. Não há adaptador, perfil
concreto de fonte, CLI ou chamada MCP nesta entrega.

Tipos públicos em transport.py:

* RecursoAssistido(tipo, caminho, query, mimes, metodo="GET"): expressões regulares ancoradas, por fullmatch;
  tipos Document/XHR/Fetch. O perfil declara a classe de recurso como pública.
* PerfilPortaAssistida(origens, recursos, cookies_admitidos, fundamento_publico, max_bytes, max_capturas):
  origens são hosts de HTTPS/443, sem esquema/porta. Não substitui perfis concretos/vínculos da §2.11.
* SessaoPortaAssistida(perfil, navegador=...): gera sessao_id aleatório e mantém cotas/candidatas.
  encerrar() invalida/libera todas as pendentes, inclusive por perda de canal, fila ou prova de ambiente.
  O encerramento normal da porta ocorre depois da seleção e persistência autorizada.
* ChaveAssistida(sessao_cdp, alvo, request_id, salto): chave completa. Reutilização encerra a sessão;
  requestId coincidente entre alvos/sessões diferentes não mistura eventos.
* PedidoAssistido: URL/método/tipo observados; timestamp, wall_time; observado_em é o relógio monotônico
  LOCAL na chegada do pedido, nunca o timestamp do CDP. frame_id, raiz_id, documento_raiz e iniciador
  são os vigentes nesse instante. pronto, ambiente_conferido e posterior_linha_base precisam ser
  literalmente True; alvo_tipo precisa ser page; subtipo_desde_criacao precisa ser a string vazia,
  não None. A trilha (b) comprova esses indicadores pela sequência normativa, árvore de quadros,
  inventário, vigilância e barreiras. Não são inferências da porta.
* iniciador: {tipo, frame_id, documento, alvo} para XHR/Fetch; tipo parser/script, documento da raiz
  na mesma origem, quadro raiz e mesma aba. Document exige tipo other/parser/script; ausência,
  earlyHints ou tipo desconhecido recusam.
* redirecionamentos: tupla ordenada de {url, status, headers, remoteIPAddress?}. Só um HSTS interno
  integralmente provado é admitido. A candidata é sempre a URL HTTPS efetiva. salto é o ordinal
  observado (um HSTS anterior significa 1), mesmo que não conte como salto de rede na política.
* EventoAssistido(chave, metodo, dados): métodos sem prefixo Network. responseReceived recebe response
  com URL, status, protocol, os três indicadores de cache presentes/falsos, remoteIPAddress/remotePort,
  securityState e securityDetails (protocol, issuer). responseReceivedExtraInfo recebe statusCode
  BRUTO, headersText BRUTO obrigatório em HTTP/1.x e headers com multiplicidade original do CDP
  (duplicatas separadas por LF). mimeType inferido pelo navegador nunca decide.
* requestWillBeSentExtraInfo entrega apenas authorization_presente e associatedCookies
  [{nome, blockedReasons}]. O adaptador projeta presença de Authorization e nomes/motivos,
  descartando valores de cabeçalhos/cookies. Lista vazia de motivos significa cookie enviado.
* streamResourceContent é o RESULTADO da chamada observacional no início, com bufferedData base64.
  Seguem dataReceived (data base64, dataLength, encodedDataLength) e loadingFinished (timestamp).
  Resultado falho/tardio, loadingFailed, cache, perda de dados ou método não admitido recusam.
  Não existe entrada por getResponseBody. responseReceivedEarlyHints é apenas informativo;
  não autoriza recurso iniciado por Early Hints.
* ExtraInfo pode preceder responseReceived ou suceder loadingFinished, pela mesma chave e no prazo.
  Dados após término e repetição de eventos singulares recusam.
* CapturaAssistida contém Response íntegro (bytes, SHA-256, tamanho, MIME/Content-Type, recibo HTTP,
  fetched_at) e, separadamente, procedencia/modalidade_acesso, IDs aleatórios, navegador, protocolo,
  IP, emissor, Content-Encoding original, contador codificado quando informado e decisão de charset.
  Não atribui verified, identidade, âncora ou juízo de vigência.

Prazo: 30 s desde a observação do pedido, fiscalizado por Timer mesmo sem eventos e conferido também
antes/depois da admissão. Primeiro sinal observável de resposta: responseReceived ou ExtraInfo;
sem eles expira como Timeout; com eles, RespostaInvalida.

O adaptador reserva/libera ANTES de cada alocação própria no orçamento compartilhado: blocos de
pipe de até 1 MiB, mensagem JSON, base64, bytes e cópias. A porta cobra decodificação, blocos (inclusive
sobrecarga de objetos/referências), exemplar e temporários de interpretação. Admissão transfere a
reserva dos blocos ao exemplar; descartar() libera a candidata. Quatro streams globais separados do
fluxo automático; 32 pendentes por sessão; 64 MiB compartilhados. Fila de 10.000 mensagens/32 MiB,
leitura do pipe e fiscalização das alocações do adaptador são da trilha (b). Excesso global invalida
todas as pendentes.

## Matriz §2.4 → testes offline

Nomes em tests/test_transport_assistida_0089.py. Controles inaplicáveis têm prova de ausência de efeitos;
não recebem código inventado. Recusa de candidata sem código fechado usa RespostaInvalida.

| Linha | Testes | Resultado |
|---|---|---|
| 1 | test_linha_01_url_recusada; test_linha_01_fragmento_descartado; test_linhas_01_22_aceite | Gramática/HTTPS/host/443/caminho/query; BlockedHost; fragmento descartado |
| 2 | test_linha_02_ip_porta | _public_unicast e porta efetiva; BlockedHost; sem DNS |
| 3 | test_linha_03_tls; test_linhas_01_22_aceite | TLS seguro e emissor; RespostaInvalida |
| 4 | test_linha_04_http1_bruto; test_linha_04_http2_3 | Mesmas funções de campos/framing; CL duplicado/conflitante/21 dígitos, TE, status bruto; RespostaInvalida |
| 5 | test_linha_05_fim_obrigatorio; test_metadado_ausente_nao_inferido | Só loadingFinished; falha/truncamento relatado pelo navegador recusa |
| 6 | test_linha_06_codificacoes_admitidas; test_linha_06_todo_status | Ausente/identity/gzip/deflate/br/zstd; outra codificação/duplicata recusa em qualquer status |
| 7 | test_linha_07_confrontos; test_linha_07_limites; test_linha_07_xhr_comprimido_incompleto; test_linha_07_bomba_descarta; test_extra_info_declarado_recusa_imediata | Limites e três confrontos; TooLarge/RespostaInvalida/EmptyBody |
| 8 | test_linha_08_hsts; test_linha_08_recusa | HSTS provado aceito; rede/interno sem prova ou divergente: BlockedHost |
| 9 | test_linha_09_desafio_todo_status; test_linha_09_amostra_fronteira | Mesmo detector/64 KiB; HTTPStatusError com desafio |
| 10 | test_linha_10_content_type; test_linha_04_http2_3 | Gramática existente, MIME exato, duplicatas/parâmetros; RespostaInvalida |
| 11 | test_linha_11_bytes_charset | UTF-8/header/meta, inválido/incompleto, U+FFFD, BOM UTF-16 sob UTF-8, latin1/cp1252; bytes/hash/decodificador estrito |
| 12 | test_linha_12_prazo_sem_eventos; test_linha_12_inclui_admissao | Fiscalização independente e prazo de admissão; Timeout/RespostaInvalida |
| 13 | test_linhas_13_14_16_18_20_sem_efeitos | Sem taxa mínima automática; mantém prazo total |
| 14 | test_linhas_13_14_16_18_20_sem_efeitos | Limitador/disjuntor automáticos não chamados |
| 15 | test_linha_15_concorrencia; test_linha_15_concorrencia_global; test_linha_15_pendentes; test_linha_15_memoria_invalida_todas; test_linha_15_blocos_pequenos_contabilizados; test_linha_15_max_capturas_na_admissao; test_reserva_precede_decodificacao | 4 streams globais, 32 pendentes, reserva antes da decodificação, fragmentação, orçamento e invalidação |
| 16 | test_linhas_13_14_16_18_20_sem_efeitos | Sem repetição/requisição própria |
| 17 | test_linha_17_perfil_limites; test_linha_17_perfil_recurso; test_linhas_01_22_aceite | Limites/método/MIME; ValueError em configuração inválida; JSON só se declarado |
| 18 | test_linhas_13_14_16_18_20_sem_efeitos | Sem cabeçalhos de chamador; IDs distintos para obtenções da mesma URL |
| 19 | test_linha_19_cookies | Só nomes em memória; bloqueados não contam; autorização/nome desconhecido recusam |
| 20 | test_linhas_13_14_16_18_20_sem_efeitos | Sem reaproveitamento |
| 21 | test_linha_21_recibo_mesma_funcao; test_linha_21_descarte_duplicatas; test_linha_21_limite_recibo | Mesma observe_http_response/allowlist/limites/descarte de duplicatas |
| 22 | test_linhas_01_22_aceite; test_sem_verified_ou_renovacao_frescor | UTC = wallTime + delta do mesmo pedido; nunca renova pelo relógio atual |

Complementos: correlação, metadados ausentes, streaming falho/tardio, flags obrigatórios, iniciador,
personalização, segredos e modelo literal. Fixture nova exclusivamente sintética:
0089_streaming_sintetico.json, gerada por tests/gerar_0089_sintetica.py:gerar, com categoria,
propósito, tamanho/hash no manifesto. Eventos em memória são gerados por pedido/eventos/fluxo,
identificados como sintéticos no módulo. Nenhuma captura real foi modificada.

O artefato de produção freoa_verifica/data/planalto_cauda_0089.bin é o modelo LITERAL normativo:
1.440 bytes, com TOKEN, SHA-256 57e730d2a5f31c72f6d347d198d2e426eb7495188129242fe024c14961be4f3f.
Extraído da fixture 6.385 existente, substituindo só o valor f5_p com gramática [A-P]{128}, e conferido
contra §2.5(3); não é nova captura/fixture real. O package-data inclui o modelo. Ambas as caudas precisam
casar exatamente e o modelo precisa passar no hash. Só então se entrega ao parser o texto sem a cauda,
pela interpretação única. Não se usam hashes brutos para concluir equivalência, não se declara
equivalência normativa e não se modifica o exemplar.

## Aceite §3 → teste ou trilha (b)

| Item | Parte offline da trilha (a) | Pendente: trilha (b) |
|---|---|---|
| 1 | Matriz, bytes/charset, prazo, correlação e cotas acima | Adaptador/origem HTTPS real, AC/loopback exclusivos do harness, chunks e compressão no navegador, anexação, cabeçalho parcial, fila/pipe e alocações próprias |
| 2 | test_proveniencia_flags_obrigatorios; test_proveniencia_304_oculto; test_pedido_sem_prova; test_final_apos_103; test_eventos_nao_admitidos | Cache/SW/prefetch/prerender/bfcache/Early Hints e recarga humana efetivos |
| 3 | URL/método/MIME/iniciador/quadros, autorização/cookies, personalização/desafio | Perfis concretos, árvore real, downloads/WebSocket, grafo A/B completo de normas.leg.br |
| 4 | Porta só admite em memória | Seleção/lista/dependentes e descarte das não marcadas |
| 5 | Chave completa, URL própria e erros sanitizados | Filtro antes da retenção, tráfego SSO/terceiros, logs/diagnósticos |
| 6 | test_linha_19_cookies; test_personalizacao; test_linha_10_content_type; test_linha_21_recibo_mesma_funcao; test_segredos_erros_sanitizados; test_conteudo_publico_limite_declarado | Varredura de logs/artefatos, parser de documento público com metadados pessoais, persistência/exportação |
| 7 | — | ACL, locais de gravação, downloads, limpeza/recuperação |
| 8 | Indicadores positivos de ambiente/prontidão exigidos | Registro Windows, inventário/vigilância/assentamento/barreiras, componentes, argumentos/pipe em cada navegador |
| 9 | test_linhas_13_14_16_18_20_sem_efeitos | Métodos/parâmetros/sequência CDP e igualdade dos pedidos reais |
| 10 | test_porta_unica_ast; test_eventos_nao_admitidos | AST e tentativa de contorno com adaptador implementado; hoje não existe adaptador conectado ao produto |
| 11 | test_sem_verified_ou_renovacao_frescor; porta não atribui estados nem altera a data | Regressões finais 0075 com captura assistida persistida, histórico/juízo pendente e cobertura publicada à parte |
| 12 | test_linhas_01_22_aceite; test_linha_21_recibo_mesma_funcao: envelope procedência/modalidade | Banco/evidências e snapshot instalado preservando modalidade e alterando procedência pública |
| 13 | Nenhuma chamada do produto adicionada | CLI/TTY/confirmação, AST/execução MCP/agendamento/remoto, perfil pessoal, encerramento |
| 14 | — | Contrato/indicação/experimentais/listar_fontes |
| 15 | test_cauda_planalto_modelo_literal; test_cauda_planalto_nao_afirma | Integração com parser e capturas reais no aceite do adaptador |
| 16 | — | Instalação Windows, fv sessao e recusa sem pipe |
| 17 | — | Sessão manual do titular |

## Questões

1. Ruff global já falha na base: cópia dos arquivos rastreados do HEAD sob .tmp/ruff-baseline reproduz
   145 achados em 46 arquivos e 283 arquivos pendentes de formatação. A árvore atual tem os mesmos
   145 achados, sem lint novo. Corrigir/reformatar a base alteraria testes existentes e ampliaria
   esta trilha; não foi feito. O requisito de Ruff global limpo permanece não atendido.
   A execução final de format --check . abortou com código 101 e panic "Expected a ruff source file"
   (Ruff 0.17.1), na árvore em uso; a causa do panic não foi isolada. Isso não elimina a falha de
   formatação já reproduzida no HEAD. check . terminou com código 1 e os mesmos 145 achados,
   comparados também por arquivo/código/mensagem, não só pela contagem.
2. Content-Type com parâmetros extras: escolhida recusa, entre as alternativas da §2.7, evitando
   alterar a interpretação ou transportar parâmetros secretos no Content-Type cru.
3. Vary com asterisco: recusa por impossibilidade de excluir personalização. identity conta como
   ausência de compressão no confronto com Content-Length. O automático não muda.
4. HSTS repetido/cadeia ambígua: só um salto interno provado é admitido. Origem, subtipo histórico,
   prontidão e quadro principal ausentes nunca são inferidos.
5. Streaming (leitura de execução autorizada pelo supervisor em 20/11/2026, defeito 49):
   eventos sem `data` podem preceder a resposta do comando; o `bufferedData` deve ter exatamente
   a soma dos `dataLength` anteriores. Depois da resposta, cada evento deve trazer `data` de
   tamanho igual ao seu `dataLength`. Término anterior à resposta ou erro do comando recusa,
   sem fallback. Ver o terceiro ensaio abaixo. A redação da 0089 §2.5(2) e do §3 item 1
   ("streaming iniciado tarde") precisa de nota formal do titular.
6. Reservas conservadoras podem recusar antes do limite nominal de bytes quando as representações
   pendentes consomem o orçamento. (b) ainda deve provar reserva antes de leitura/alocação própria.
   A porta não promete medir memória do navegador.
7. A porta entrega envelope/data; banco/snapshot/serviço são (b). Modalidade ainda não está publicada
   pelo produto. Não se afirma aceite desses caminhos finais.
8. Auditoria independente D5 e revisão de fronteiras/segredos pendentes, conforme §6. Desenvolvedor
   implementa/testa, sem parecer de auditor sobre o próprio trabalho.
9. Commits impedidos pelo sandbox. O arquivo .git e git rev-parse apontam para
   C:\dev\fv14\.git\worktrees\fv14-0089i (diretório comum C:\dev\fv14\.git).
   A raiz Git gravável fornecida à sessão é C:\dev\fv14-main\.git, que não corresponde a esse
   repositório. git add recusou criar index.lock e git hash-object recusou gravar em objects;
   git commit também recusou criar index.lock. Não houve commit nem alteração de ramo/ligação
   do worktree. Sem permissão de escrita nesse Git, não é possível cumprir commits/status limpo.
10. A suíte completa encontrou falha no teste existente
    test_c13_variante_em_memoria_recibo_com_hash_correto_e_url_alheia_invalida_a_ativacao,
    de tests/test_camara_0081_ativacao_e_robots.py. Reprodução isolada: 1 failed em 0,25 s,
    PermissionError ao escrever r.json dentro de tempfile.TemporaryDirectory do Python 3.14 e
    também na limpeza desse diretório. A asserção de ativação não é alcançada; o teste não usa a
    porta assistida. Não foi alterado nem se substituiu tempfile para fabricar resultado verde.

## Validação

* Foco: 191 passaram (184 da porta/modelo + 7 garantias estruturais existentes).
* D5: comparação AST de TODAS as funções/classes preexistentes de transport.py contra HEAD:
  nenhuma mudou. O trecho automático também foi preservado na formatação.
* Nenhum teste existente alterado; sem dependência nova; git diff --check limpo.
* Suíte completa: comando solicitado executado, mas interrompido após reprodução isolada da falha
  ambiental descrita na questão 10. O progresso já gravado no log continha 1.224 casos:
  1.221 pontos de aprovação, uma falha e dois skips. Isso é contagem PARCIAL do log, não
  resultado final da suíte; não se afirma suíte verde ou validação integral.
* Após o último ajuste da porta, foco repetido: 191 passed, 1 warning em 2,85 s. O warning
  é PermissionError ao criar o cache do pytest, também imposto pelo ambiente.
* Ruff check .: exit 1, 145 achados preexistentes em 46 arquivos. Ruff format --check .:
  exit 101, panic "Expected a ruff source file". Na reprodução apenas do HEAD:
  283 arquivos a reformatar. Bloco novo da porta e ambos os arquivos Python novos:
  format --check limpo; lint sem achados novos.
* Commits: nenhum. O Git real está fora das raízes graváveis (questão 9). HEAD/ramo
  preservados. Permanecem cinco arquivos rastreados modificados e cinco novos; status não limpo.
* Ponto de parada: implementação e provas offline focadas entregues; faltam suíte integral verde,
  Ruff global verde, commits e status limpo. Não é encerramento do marco nem aprovação D5.

## Terceiro ensaio real: ordem resposta do streaming x dataReceived

20/11/2026. Papel: Desenvolvedor. Base desta correção: `a0a7a3e`, ramo
`feat/0089-sessao-assistida`, worktree `C:\dev\fv14-0089i`.

**Fatos informados pelo supervisor**, verificados por ele fora do sandbox com Brave 1.100 /
Chromium 158 e harness HTTPS local com 150 ms até o primeiro byte:
`C:\dev\tmp\v5\impl-b\diag_trace.txt` e `diag_trace_plugin.py`. No Document principal, o
comando `Network.streamResourceContent` foi escrito no pipe no mono 22736.0056, cerca de
190 ms antes dos dados. O primeiro `dataReceived` chegou sem `data`, com `dataLength=20`;
só depois veio a resposta do comando, com 28 caracteres base64 de `bufferedData`, exatamente
os mesmos 20 bytes. Os eventos seguintes trouxeram `data`, seguidos de `loadingFinished`.
Não houve novo ensaio de navegador nesta rodada. O laboratório de 19/11 provou a chamada
no pedido, sem provar a ordem entre a resposta ao comando e o primeiro evento.

O supervisor adotou a seguinte **leitura de execução**, implementada na porta:

* O comando continua obrigatório no `requestWillBeSent`, única fonte de bytes. Nenhum método
  CDP foi acrescentado; `getResponseBody` continua excluído.
* Antes da resposta, só são aceitos eventos sem a chave `data`. Seus `dataLength` e
  `encodedDataLength` entram nos contadores existentes e no limite `max_bytes`; os bytes
  declarados por `dataLength` reservam orçamento imediatamente, até a cópia do buffer.
* O tamanho decodificado de `bufferedData` deve ser igual à soma dos `dataLength` anteriores.
  Buffer vazio só é admitido sem evento anterior. Após a resposta, cada evento exige `data`
  e tamanho decodificado igual ao próprio `dataLength`, sem compensação entre eventos.
* `loadingFinished` anterior à resposta recusa com `STREAMING_ASSISTIDO_TARDIO`. Presença de
  `data` antes da resposta, falta de `data` depois ou erro do comando entregue à porta:
  `STREAMING_ASSISTIDO_INVALIDO`; divergência de tamanhos: `STREAMING_ASSISTIDO_DIVERGENTE`.
  Todos são `RespostaInvalida`. O adaptador conserva `COMANDO_STREAMING_RECUSADO` para erro
  CDP. Prazo e confrontos finais da §2.4 linha 7 permanecem iguais.

Os geradores e testes existentes foram ajustados por exigência expressa desta correção:
o gerador antigo punha três bytes em `bufferedData` sem evento que os declarasse, e contava
o corpo inteiro em um evento que só trazia o restante. Agora o padrão é buffer vazio e
evento com o corpo inteiro; a variante com prefixo reproduz a ordem observada. A regressão
antiga que recusava o primeiro evento sem `data` agora o aceita e exige recusa no término
anterior à resposta. Não se retiraram as provas de comando emitido no pedido e de latência.

Validação final desta rodada: **390 passed**, nos nove módulos offline afetados da porta e
da trilha assistida, com `.venv`, `-p no:cacheprovider`, exclusão de `live` e
`navegador_assistido` e `--basetemp` em `%TEMP%\fv0089-def49-final`, fora do checkout
(repetição final: 390 passed em 9,00 s).
Cobertura nova: sequência real com prefixo de 20 bytes, hash/corpo idênticos, soma de vários
eventos, prefixo vazio ou corpo inteiro, cada violação de ordem/tamanho, divergências que
se compensariam no total, reserva anterior ao buffer, excesso de orçamento e limites
antes/depois da resposta. Integração usa o adaptador e a porta reais, sem rede.

D5: AST de todas as **77 funções/classes preexistentes**, incluindo métodos e definições
internas, comparada com `git show 87b43f7:freoa_verifica/transport.py` por
`ast.dump(include_attributes=False)`: **zero ausentes, zero alteradas**. `cdp.py` não
precisou mudar: já entrega os eventos e a resposta na ordem recebida.

`C:\dev\tmp\venv-ruff\Scripts\python.exe scripts\ruff_catraca.py`: **exit 0**, baseline
inalterada. Os três arquivos de teste tocados estão limpos no lint e formatados; o trecho
assistido de `transport.py` passa em `ruff format --check --range 580-1020`. O arquivo
completo conserva seis achados de lint e formatação preexistentes no fluxo automático;
não se altera esse fluxo para limpar a base. Os seis achados foram comparados com o HEAD
por regra/mensagem: idênticos, zero novos. Coleta dos dois módulos reais: **56 testes**.
Suíte completa e navegador: **NOT RUN**.
Sem stage, tentativa de commit, push ou troca de ramo.

Questão remanescente: esta leitura substitui a resposta antiga da questão 5, mas não é a
nota formal do titular. A redação da 0089 §2.5(2) e do §3 item 1 ("streaming iniciado tarde")
precisa dessa nota; registro de execução em
`docs/decisoes/0089-nota-execucao-defeito-49.md`. Aceite real e auditoria independente
continuam pendentes; esta entrega não aprova o próprio marco.

## Parecer Terra r1

20/11/2026. Papel Desenvolvedor, base `4493d5f`, mesmo worktree e ramo.
Alteração da porta autorizada expressamente pelo supervisor somente para o
item 1 do parecer `C:\dev\tmp\v5\audit\parecer-terra.md`.

**Achado:** BOM permitia admitir `charset=TOKEN_SECRETO` sem reconhecer a
codificação, mantendo o Content-Type bruto no `Response`, banco e snapshot.

**Correção por classe:** `_conferir_headers` valida zero ou um charset do
conjunto fechado da interpretação única, resolve o codec por `codecs.lookup`
e publica o nome canônico WHATWG, independentemente de BOM/meta. Recusa
duplicata mesmo idêntica, parâmetro desconhecido, codec não admitido e aspas
ou escapes estranhos. Só o media type e charset canônicos chegam à
interpretação, ao recibo e a `Response.content_type`. A interpretação
preexistente em `texto_resposta.py` não foi alterada.

**Revisão de saídas:** Content-Encoding é reduzido ao valor de uma lista
fechada; Date/Last-Modified/Retry-After têm gramática de data HTTP canônica
ou inteiro limitado, e Content-Length tem gramática e limite numéricos.
`observe_http_response` só publica campos da lista `HEADER_NAMES` que passam
por essas validações. ETag, Set-Cookie, Content-Disposition, Server, campos
desconhecidos, Cache-Control e Vary não são publicados; os dois últimos só
decidem a recusa de personalização. O detector de desafio devolve tipo fixo.
As mensagens de erro da porta são códigos fixos; o adaptador e terminal não
recebem o cabeçalho recusado. Não foi necessário modificar store, evidências
ou snapshot: todos consomem o objeto já canonizado pela porta.

**Regressões:** BOM + charset arbitrário, também sem BOM e com meta; codec
transformador; duplicata idêntica/por alias; aspas simples, espaços internos
e quoted-pair; parâmetro desconhecido; caixa variada e aspas HTTP válidas;
canonização preservando o significado de latin1; recusa antes da construção
de `Response`/`CapturaAssistida`, com memória liberada. Integração passa pela
porta e persistência reais, evidencia publicamente e exporta snapshot; confere
a coluna e varre todos os arquivos, inclusive SQLite/WAL/blobs, contra o
token recusado e o Content-Type bruto válido. Há também campos arbitrários
nos demais cabeçalhos, ausentes de objeto, banco, evidência e exportação.

**D5:** comparação final de AST com `87b43f7` por nomes qualificados de funções
e classes, incluindo métodos e definições internas,
`ast.dump(include_attributes=False)`: **77 preexistentes, zero ausentes e
zero alteradas**. Só o método assistido `_conferir_headers` mudou na porta.
Validação e limitações consolidadas na seção homônima da trilha (b).
Leitura de execução: `docs/decisoes/0089-nota-execucao-parecer-terra-r1.md`.
