# 0081 — Correção r1, r2 e r3 da ativação ao vivo da Câmara (pareceres do PR #39)

Codificador (Sonnet), 08/11/2026, sobre o parecer COM BLOQUEADOR do auditor (r1: achados 1–10, contraprovas C01–C22; r2:
R2-1 a R2-8, §8; r3: R3-1 a R3-6, §9). Onde este texto foi mais forte do que o código na r1 ou na r2, a rodada seguinte o
corrigiu no código e aqui (§§8 e 9) e as afirmações abaixo valem **como estão redigidas depois da r3**, com os limites do
§9.8. Não altera
a 0080, a matriz IL.1, os pisos, a reserva, os mutantes, `transport.py`, `CONTRATO_VERSAO` nem o consumidor FREOA. Registra as
escolhas de implementação que a 0080 deixava abertas e as regras que o parecer tornou explícitas. Qualificação continua
`nao_apurada` até o IL.3-c.

## 1. Autorização de ativação (0080 §2)

1. A ativação é revalidada pelo portão antes de **cada** obtenção viva (e de novo depois da espera do ritmo), não só na criação
   do conector. Sem registro válido (ausente ou inválido): `ativacao_ao_vivo_pendente`, sem emissão e sem bloqueio persistente.
   Falha **local ao ler** a documentação (permissão, E/S, arquivo ilegível no sistema de arquivos) não é registro ausente: é
   falha local terminal (§4.1).
2. Registro válido exige estrutura completa (revisão com `auditor`, `revisado_em` ISO, `resultado`, `termo_sha256` e `sha256`
   dos bytes), os **bytes da revisão preservados** em `camara/revisao/<sha>.json` com hash conferido e coerentes com os campos,
   o termo preservado com recibo íntegro (URL exata, 200, `text/html`, tamanho, instante, hash, UA, vínculo à política de
   `www2` da ativação) e os bytes dos robots preservados e permissivos para os caminhos de conteúdo. O selo `registro_sha256`
   é checksum público de consistência e não substitui nada disso.
3. `registrar` lê a revisão uma só vez, valida o registro final antes de gravá-lo e recusa política expirada ou adulterada.
   Igualdade automática entre versões do produto continua não exigida.

## 2. Robots (0080 §4)

1. Persistem-se os **bytes originais** da resposta (`robots-<host>-<sha>.txt`); toda releitura confere o hash e interpreta pelo
   Content-Type guardado. Divergência é falha local, nunca autorização.
2. Resposta reaproveitada da guarda não é nova obtenção: vale pelo instante original (`fetched_at`) e, vencida, falha com
   `robots_expirado_sem_nova_obtencao`; o cache nunca renova `obtido_em`/`valido_ate`. O limite de 24 h é imposto no esquema.
3. `/robots.txt` pedido diretamente segue o mesmo fluxo de bloqueio, validação, persistência e backoff.
4. Decisões por caminho são registradas sem teto (o recibo renova a cada 24 h); nenhuma é descartada.
5. Comparação e especificidade (RFC 9309 §2.2.2) sobre **octetos** normalizados: `%XX` de octeto não reservado é decodificado,
   o de octeto reservado ou fora do ASCII fica codificado em maiúsculas, `*` e `$` codificados são literais.
6. **`Crawl-delay`**: o teto de 3600 s deixa de tornar o valor "inválido" (invalidez é só valor não numérico, negativo ou não
   finito). Valor válido é registrado e honrado; se a espera necessária exceder o **teto operacional de 3600 s**, a obtenção
   é uma **abstenção operacional declarada** (`crawl_delay_acima_do_teto_operacional`), sem emissão e sem bloqueio persistente.

## 3. Ritmo e tetos (0080 §5)

1. O início de cada requisição grava o instante civil e a **marca monotônica** (`time.monotonic()`, comparável entre processos
   da mesma máquina). O decorrido é o **menor** dos dois; recuo do civil ou reinício da marca contam como nada decorrido
   (conservador, no máximo uma espera de intervalo).
2. O teto da sessão (200) e o da chamada (30) somam os hosts e são **reservados atomicamente** antes da espera; a reserva é
   devolvida se a emissão é abortada. O escopo da chamada é compartilhado por todas as instâncias participantes.

## 4. Barreiras (0080 §6)

1. Falha local (persistência, leitura local do estado — inclusive da ativação —, esquema persistido inválido, valor numérico
   ou de instante fora do representável, interpretação local, falha do parser) é **terminal** para a chamada pública ou sessão
   do instrumento, nos dois hosts; não persiste; nova chamada recomeça. Os esquemas persistidos do estado da rota
   (`ritmo`, `bloqueio`, `robots`, `politicas/`, `obtencoes`, `termo`, ativação) são validados e falham como
   `persistencia_local_falhou`/`interpretacao_local_falhou`; `OverflowError` e demais `ArithmeticError` de interpretação
   também são terminais. A distinção é por origem: registro **ausente ou inválido** (documental) ≠ falha **local ao ler**.
2. Falha de perfil ou de resposta detectada depois do portão (busca, página, texto e **identidade**: o endereço é o da norma
   pedida e a página declara outra) alimenta o mesmo classificador (recurso persistente; host pelo escopo), com a evidência da
   resposta. Entrada inválida do chamador, formatos não habilitados e ausência demonstrada (nenhuma página da norma pedida entre
   os candidatos) não bloqueiam.
3. Recusa ou inconclusão de robots durante a ativação persiste o bloqueio do host. A reabertura de host descarta a política
   **antes** de remover o bloqueio, de modo que nenhum estado intermediário autoriza obtenção.

## 5. D6 e inventário (0080 §8)

1. Em `--reserva` nenhum predicado operacional (ok/falha, classe, ativação, bloqueio, conclusão) sai por stdout, stderr, logs
   ou código de saída: a execução que chega a ser despachada sai sempre com 0 e as falhas inesperadas são contidas. **Exceção
   declarada:** erro de uso detectado antes da execução (por exemplo, `--reserva` sem `--saida-privada`) sai com 2 e uma
   mensagem de uso, que não carrega predicado operacional. O resultado integral vai só ao arquivo do guardião
   (`--saida-privada`, obrigatório com `--reserva`), sob a guarda separada.
2. O inventário grava, por unidade (norma), `inventario.json` com todos os recursos (obtidos, recusados, não obtidos e motivos)
   e o material parcial, mesmo quando a unidade falha; acumuladores do conector são zerados por norma; falha de gravação é
   falha controlada que encerra a sessão.

## 6. Atribuição e snapshot (0080 §§7 e 8.4)

1. `termo_sha256` é por **captura**, identificada pela tripla que o banco usa (`sha256` do conteúdo, `url`, `fetched_at`): o
   registro de obtenção (`obtencoes.jsonl`) liga essa captura ao termo da ativação válida **na emissão**; só vale com o termo
   preservado e conferido; nunca vem do termo corrente do home; registros da mesma captura com termos diferentes tornam o
   vínculo ambíguo (nulo). `atribuicao` acompanha toda entrega de texto de origem Câmara, inclusive `buscar_legislacao` (local,
   staging e candidato ao vivo), ligada à **obra** e à ocorrência que sustentam o item, nunca por coincidência de texto e
   caminho; `obter_evidencia` extrai a `autoria`.
2. O snapshot transporta, sob o inventário de hashes, termo, recibo, revisão, política (bytes e recibos, com as decisões por
   caminho), obtenções e os registros de ativação como **evidência** (instalar não ativa). A validação confere nome-hash,
   recibo, a coerência de cada recibo de política com os seus bytes e o **fechamento dos vínculos** (§9.1: obtenção → termo
   com corpo e recibo → política com corpo, recibo, instante, validade na emissão e decisão do caminho recomposta dos
   bytes); referência quebrada ou política que não autorizava o caminho é recusada ainda que os checksums sejam refeitos. A exportação recusa home com evidência incoerente. `captured_at` e procedência originais permanecem. A
   instalação é transacional (§8, R2-7).

## 7. Limites declarados

- A marca monotônica entre processos depende de `time.monotonic()` ser comum ao sistema (vale em Windows, Linux e macOS). Não
  há identificação explícita de boot: o decorrido é o **menor** entre o civil e o monotônico, o que cobre o recuo do relógio
  civil e a marca monotônica que reinicia abaixo da persistida (nada decorrido); um reinício em que a marca nova ultrapasse a
  persistida é limitado pelo decorrido civil, mas não é detectado como reinício.
- A trava entre processos continua testada pelo teste existente com subprocessos; a reserva do teto é por processo (a sessão
  do instrumento é um processo).
- Capturas humanas futuras, revisão do inventário de desenvolvimento e captura da reserva seguem como pendências operacionais.

## 8. Correção r2 (parecer r2 do PR #39, R2-1 a R2-8)

1. **Autorização que envelhece (R2-1).** Depois de toda espera e antes do envio, sob a trava do host, o portão relê a política
   vigente (validade, integridade contra os bytes preservados), decide o caminho de novo e revalida a ativação. Se a política
   venceu na espera, o robots é lido de novo (com ritmo, tetos e ativação próprios), o caminho é decidido pela política nova
   e o ritmo é recomputado a partir dela (um `Crawl-delay` maior vale a partir da leitura). Se a política mudou, vale a vigente.
   Máximo de 4 trocas por emissão; a reserva do teto é devolvida se a emissão é abortada.
2. **Recibo de robots como evidência (R2-2).** O recibo só é aceito se coerente com os bytes: hash, status 200, tamanho, MIME,
   UA efetivo, tokens, grupos considerados, `Crawl-delay` e cada decisão por caminho são recomputados dos bytes. O atraso
   aplicado é **sempre** o recomputado dos bytes conferidos; divergência é recusa (falha local). A mesma validação vale ao
   gravar, em toda leitura da política vigente e das arquivadas, na ativação (`validar_registro`) e no snapshot.
3. **Falha local ao ler (R2-3).** `LeituraLocalFalhou` (subclasse de `EstadoIndisponivel`) distingue o que o sistema de
   arquivos não deixou ler do que não existe ou não confere; só o segundo é pendência/invalidez. A validação numérica é total
   (inteiro grande demais, instante fora do intervalo) e `ArithmeticError` de interpretação é terminal.
4. **Identidade (R2-4).** `resolve` e `fetch` com página reconhecida cujo endereço é o da norma pedida e cujo título declara
   outra levantam `identidade_nao_confirmada` com a evidência da resposta e entram no classificador (recurso persistente, host
   pelo escopo). Ausência demonstrada e erro de entrada continuam sem bloqueio.
5. **Vínculo por captura (R2-5).** A obtenção registra `capturado_em` (o `fetched_at` da resposta, componente da identidade da
   captura) e o termo da ativação **revalidada na emissão**, que pode diferir do lido na admissão. Na busca, a atribuição é
   a das capturas Câmara da obra do item; origens distintas ficam em `atribuicoes` (campo aditivo; `atribuicao` só quando há uma).
6. **Snapshot (R2-6).** Fechamento dos vínculos validado (§6.2) e decisões por caminho gravadas também no recibo arquivado
   (`politicas/<host>-<sha>-<instante>.json`), que é o que viaja; ao instalar, decisões da mesma política de homes diferentes
   são unidas e decisão contrária é conflito.
7. **Instalação transacional (R2-7).** `Publicacao` faz o preflight de **todos** os conflitos (e, desde a r3, a validação da
   união com o home, §9.2) sem escrever nele, prepara em staging e publica com diário; entra na mesma publicação do banco e dos blobs de `snapshot_install` e é
   desfeita pela mesma recuperação (falha de escrita no meio, conflito tardio e falha posterior ao banco).
8. **Cobertura (R2-8).** A regressão de contaminação entre unidades usa normas distintas e página exclusiva; o mutante sem
   zeragem a mata. As asserções tautológicas ou frouxas dos testes novos foram trocadas por exatas.

Limites que permanecem: travas entre processos reais e o fluxo com a reserva real seguem como pendências operacionais; o
vínculo ambíguo de uma mesma captura sob dois termos fica nulo em vez de escolher um.

## 9. Correção r3 (parecer r3 do PR #39, R3-1 a R3-6)

1. **Fechamento semântico da evidência (R3-1).** Para cada obtenção, o validador (`camara_evidencias._validar`, a mesma que
   serve à exportação, ao preflight da instalação e ao snapshot) recompõe dos **bytes** da política apontada a gramática e a
   decisão do caminho (mesmo motor RFC 9309 por token do portão) e exige: decisão recomposta `permitido` **e** decisão persistida
   no recibo igual; política obtida antes da emissão e válida nela (`obtido_em <= emitida_em < valido_ate`); `capturado_em`
   não anterior à obtenção da política; termo (por **conteúdo e recibo**) existente, capturado antes da emissão e sob uma
   política cuja validade o cobria e que permitia o caminho do termo; nome do recibo arquivado coerente com o instante
   declarado. A obtenção passa a registrar `emitida_em` (instante em que a política foi reconfirmada válida, imediatamente
   antes do envio): `em`, escrito depois da resposta, só precisa não preceder a emissão e segui-la em até 5 minutos
   (`JANELA_DO_REGISTRO`, acima do `timeout` de 60 s do transporte); nunca é comparado ao vencimento. `termo_sha256=null` só
   com o marcador explícito `sem_termo: "portao_sem_ativacao_exigida"` (replay e instrumento sem ativação); sem marcador, ou
   com marcador e termo, é recusado.
2. **União antes de publicar (R3-2).** `Publicacao.preparar` valida, pela mesma `_validar`, o conjunto home + pacote (decisões e
   obtenções já unidas) antes de escrever qualquer coisa. Regra explícita: **home incoerente com pacote íntegro é recusado**
   (`EvidenciaInvalida`, nada escrito); a instalação não conserta nem herda referência quebrada do destino, que precisa ser
   reparada fora dela. Restos de captura interrompida (corpo de termo sem nenhum recibo) continuam não sendo evidência.
3. **Obra da busca sem `LIMIT 1` (R3-3).** As obras que sustentam o item são as que têm o rótulo (ou número), o caminho e a
   redação do item e, com `fonte`, ocorrência capturada nela. Uma só: identificada, com os recibos **dela**. Mais de uma: o
   item **não é devolvido** (correção F-1 do passe final: `trecho: null` mudaria o tipo de campo estável sem ciclo
   `deprecated`); a resposta declara a parcialidade (`parcial`, ou `indisponivel` se nada mais restou, com
   `fontes_indisponiveis: {"acervo_local": "OBRA_AMBIGUA"}`), sem recibos, atribuição nem obra escolhida. Não há migração: a identidade da obra não viaja no índice FTS, e a ambiguidade é
   **declarada**, não resolvida.
4. **Falha ao preservar o termo (R3-4).** Falha de `guardar_termo` ou `gravar_pre_ativacao` alimenta a condição terminal do
   portão (`falha_local_de_estado`) antes de propagar: os dois hosts não emitem mais naquela sessão, mesmo com o armazenamento
   recuperado; só uma nova unidade retoma.
5. **Termo ilegível (R3-5).** Resposta do termo com interpretação inválida (charset declarado incompatível com os bytes)
   alimenta `falha_de_resposta`: recurso persistente, host pelo restante da sessão, `termo_resposta_invalida` com a evidência;
   não é falha local. `termo_hash_divergente` permanece fora do classificador.
6. **Identidade do conteúdo e da obtenção do termo (R3-6).** O corpo continua nomeado pelo hash do conteúdo
   (`termo/<sha>.html`); cada recibo é nomeado pelo hash dos seus próprios bytes (`termo/<sha>.<selo>.recibo.json`), e a
   pré-ativação, o registro de ativação e a obtenção apontam `termo_recibo_sha256`. Recapturar os mesmos bytes em outro
   instante ou sob outra política cria outro recibo e **não sobrescreve** o histórico; a ativação anterior continua válida.
   Recibo adulterado no lugar não confere com o hash do nome.
7. **Testes e F8.** `tests/test_camara_0081_r3.py` traz as variantes do auditor como negativos (política que proíbe o caminho,
   instantes deslocados, decisões removidas, sufixo temporal, termo por recibo, `sem_termo`), a união com home incoerente, a
   busca com colisões de rótulo, ano, autoridade, tipo e fonte, a sessão terminal após falha de preservação, o termo
   ilegível e as recapturas/snapshots com termo idêntico; cada correção tem mutante que o teste mata. O teste de `_perfil`
   afirma a existência do bloqueio antes dos campos. O F8 confere recibos e bytes dos robots **também depois de reabrir o
   home**, e a validação administrativa do que está em disco (não é prova global de integridade administrativa).
8. **Limites que permanecem.** (a) `emitida_em` é declarado pelo portão no instante da reconfirmação: o validador prova a
   coerência do registro, não que o envio ocorreu naquele instante. (b) `capturado_em` só é comparado à obtenção da política
   (o carimbo do transporte é de outro relógio); não se exige `capturado_em >= emitida_em`. (c) Para o termo basta que uma das
   obtenções da política que cobria o instante tenha a decisão persistida. (d) Registros anteriores à r3 (obtenção sem
   `emitida_em`, recibo de termo sem hash no nome, ativação sem `termo_recibo_sha256`) não são lidos: a rota não foi
   liberada, e um home capturado antes precisa ser recapturado. (e) Filesystem real com travas entre processos, reserva real
   e o F8 por MCP e REST seguem sem execução nesta rodada.
