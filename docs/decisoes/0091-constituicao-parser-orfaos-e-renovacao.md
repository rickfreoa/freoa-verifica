# 0091 - Constituição pelo MCP: dispositivo fora de `<p>`, citação por ano, artigo integral e renovação do acervo

24/11/2026. Proposta do supervisor (Opus) para o titular, a partir de relato de uso externo (MCP instalado de
`main`/1.4.0a5 em servidor de terceiro, consultado pelo Claude Desktop). **Aprovada pelo titular em 24/11/2026, inclusive a emenda A (§5); pendente de auditoria
Codex.** Altera parser (1.2.4), derivados (versão 6), a conferência legada da 0065 e o contrato de
`obter_dispositivo` (campos aditivos). Não altera o critério de `verified`.

## 1. Fatos

1. **Confirmação indevida no snapshot publicado (1.4.0a5).** Na CF compilada do Planalto, parte dos parágrafos
   abre com `</font>` órfão (`<p ...></font><font ...>LXXVIII - ...`). Dentro do `<font>` externo da página, o lxml
   fecha o externo, esvazia o `<p>` e põe a fonte sob o `<body>`. O parser só lia `//p` e, sob o body, apenas o
   rótulo "Art N" sem corpo. Resultado, sem rede, sobre o snapshot oficial:
   - `obter_dispositivo("art. 5º, LXXVIII, da CF")` → `inexistente`; `verificar_citacao` → `not_found`.
   - Os arts. 57, 62, 126 e 222 da CF e o art. 52 do ADCT não entram no modelo; seus parágrafos e incisos ficam
     sob o artigo anterior. `verificar_citacao("art. 61, § 3º, da CF", trecho=<texto do art. 62, § 3º>)` →
     identidade e texto `verified`. O art. 61 não tem § 3º.
   - Mesma causa no art. 6º, § 1º, do DL 4.657/1942 (LINDB), no art. 21 da Lei 6.385/1976 e no DL 1.978/1982.
   - Total nas 121 obras do Planalto no snapshot: 101 caminhos ausentes, 36 atribuídos ao artigo errado, 12
     redações espúrias somadas a dispositivos corretos (todos restituídos pela correção; nenhuma perda indevida).
2. **Captura recente ignorada (ponto 1 do relato).** A 0034 rebaixa a captura nova que "perde" caminhos do modelo
   canônico. Com o modelo antigo da CF inflado por caminhos espúrios (`art56.par5`, `art61.par3` etc.), qualquer
   captura nova corretamente lida "perde" esses caminhos e é rebaixada em silêncio. A resposta serve a captura de
   18/10, que passa de 30 dias e sai `unknown/CAPTURA_DESATUALIZADA`; o cliente desconfia e vai ao site. CC e Lei
   8.666 não têm o defeito de origem e por isso não reproduzem.
3. **Artigo inteiro (ponto 2).** `obter_dispositivo` devolve só a cabeça do dispositivo; o cliente pedia inciso por
   inciso.
4. **Citação (ponto 3).** "Constituição Federal de 1988, art. 5º" não ligava o dispositivo (o "de 1988" não era
   consumido); "CF/88, art. 5º" não era reconhecida.
5. **Constituições anteriores (ponto 4).** A gramática fixava número e ano 1988 para toda "Constituição"; a semente
   e `planalto.work_key` registravam qualquer `CF` como `CF:1988`. "art. 5º da Constituição de 1967" era lido como
   art. 5º da de 1988 (identidade errada). Constituição estadual também caía na Federal.
6. **Envelhecimento (ponto 5).** Não há renovação programada; o Planalto não admite nova captura pelo UA
   identificado (0048). Sem renovação, todo o acervo legislativo passa da janela de 30 dias.

## 2. Decisões propostas

1. **Parser 1.2.4.** Fonte sob o `<body>`, sem `<p>` descendente, que abre um único dispositivo (rótulo com corpo
   de pelo menos três letras fora de parênteses; artigo só com "Art" maiúsculo seguido de maiúscula) entra como
   bloco na ordem do documento. Remissão ("art. 45 da Lei ...") e rótulo só com nota ("h) (Revogado ...)") não
   entram. Fonte com mais de um dispositivo não é decomposta: gera `DISPOSITIVO_FORA_DA_ARVORE`, que integra os
   códigos de estrutura incompleta e impede negativa (`pode_negar` → `ESTRUTURA_INCOMPLETA`).
2. **Derivados 6.** Homes com derivados 5 recebem `indisponivel/ACERVO_DESATUALIZADO` até
   `fv acervo reconstruir` (ou snapshot reprocessado). É a resposta correta: os modelos 5 da CF contêm atribuição
   errada. A reconstrução atualiza `derived_version` no manifesto local (guarda a do snapshot em
   `derived_version_do_snapshot`).
3. **Emenda à 0065.** Captura legada com decisão `legado_padrao_da_fonte_conferido` já registrada no derivado, com o
   mesmo codec, é relida sem exigir modelo idêntico quando a versão do parser mudou. A conferência por igualdade de
   modelo provava o codec; feita uma vez e registrada, não deve impedir correção do parser. O registro guarda
   `parser_anterior`, `parser_novo` e `decisao_ja_conferida`.
4. **Declaração de capturas recentes não canônicas (reconfirmação retirada na auditoria r2).** Em
   `obter_dispositivo`, a vigência continua a usar o `fetched_at` da captura canônica servida; a resposta pode declarar
   `capturas_recentes_nao_canonicas` (`capture_id`, `fetched_at`, `source_id`, `motivo` e, quando houver, `perdidos`),
   sem efeito em vigência, texto ou status. Fonte distinta não entra nessa declaração (0085).
5. **`abrangencia="integral"`** em `obter_dispositivo` (serviço, MCP, REST, CLI `fv lei --integral`): `texto`
   continua a cabeça; acrescem `subdispositivos` (caminho, rótulo, status, texto e vigência próprios, na ordem do
   documento, cada um pela mesma construção do dispositivo), `subdispositivos_total`, `subdispositivos_truncado`
   (teto de 60.000 caracteres e 400 itens) e `texto_integral`. No MCP, todo texto vai entre delimitadores de
   documento oficial. Rota Câmara: `aviso_abrangencia=integral_indisponivel_na_rota_camara`.
6. **Citação.** Constituição se identifica pelo ano (número = ano): 1824, 1891, 1934, 1937, 1946, 1967, 1969
   (EC 1/1969, no uso forense) e 1988; sem ano, a vigente. Formas: "Constituição [Federal | da República
   (Federativa) do Brasil | dos Estados Unidos do Brasil | Política do Império do Brasil | Brasileira]
   [, de <data> | (de ...)] <ano>", "CF/88", "CF/1988", "CRFB/88", "CR/88". Ano que não é de Constituição federal:
   citação `provavel` com `constituicao_nao_federal`, nunca 1988. Constituição estadual ("do Estado", "Estadual",
   gentílicos): sem citação federal. A identidade declarada da página usa o ano (número = ano). Constituições
   anteriores não têm rota: a nova captura passa por `normas_leg`, que as recusa (`tipo_nao_suportado`), e a
   resposta é `indisponivel`, nunca `inexistente`.
7. **Renovação.** `fv acervo renovar [--dias 21] [--limite N]` recaptura, pelas rotas de nova captura admitidas
   (Câmara, `normas_leg`; nunca Planalto, 0048), as obras legislativas federais com captura canônica mais antiga
   que `--dias`; resultado por obra; código de saída 1 em falha ou parcial. Aviso `acervo_envelhecendo` no `doctor`
   e no início do servidor MCP. Agendamento documentado em `docs/operacao/renovacao-do-acervo.md`.

## 3. Limites e questões abertas

1. A renovação não renova a captura do Planalto (0048). A CF renovada vem de `normas_leg`, cuja verificação segue
   `unknown(rota_nao_qualificada)` (0085). Frescor da CF com `verified` depende de rota qualificada (sessão
   assistida, 0089) ou de qualificação de `normas_leg`. Decisão do titular.
2. A reconfirmação entre fontes distintas (Planalto × `normas_leg` ou NPL) não foi admitida. Seria o caminho para a
   CF não sair `CAPTURA_DESATUALIZADA`; exige decisão sobre equivalência entre fontes (plano NPL, T1 a T3).
3. Varredura limitada às 121 obras do Planalto do snapshot. Outras marcações quebradas (texto entre `<p>` dentro de
   `<font>` com `<p>`) não foram medidas; a sentinela só cobre fontes órfãs sem `<p>`.
4. O relato menciona captura do "Portal da Legislação" em 20/11. O código publicado não tem conector do NPL; a
   captura veio de modificação local de terceiro, fora deste repositório.

## 4. Verificação

`tests/test_0091_cf_entrega.py` (25 testes; os de parser falham sobre a 1.2.3). Reconstrução de cópia do home do
snapshot 1.4.0a5 (843 capturas, 0 falhas, 0 divergentes): CF art. 5º, LXXVIII, arts. 57, 62 e 222 `encontrada`;
art. 61, § 3º `inexistente`.


## 5. Emenda A (24/11/2026): revalidação por metadados, escopo do `normas_leg` e manutenção agendada

Aprovada pelo titular em 24/11/2026, em duas respostas afirmativas à proposta do supervisor: (a) reabrir a rota
`normas_leg` no home real só para metadados e renovação; (b) admitir os metadados do normas.leg.br como gatilho de
recaptura, nunca como prova. Implementação pendente de auditoria Codex.

### 5.1 Fatos (sonda de 24/11, `claude/sonda-2026-11-24-npl-push-normasleg.md`)

1. NPL e Planalto clássico: conexão reiniciada para o cliente identificado, como em 19/11. Barreira mantida.
2. Push da Legislação: página de sistema indisponível (acesso suspenso por recomendação do CISC GOV.BR). Mesmo ativo,
   avisa atos novos por e-mail, não recompilações.
3. normas.leg.br, metadados da CF (`tipo_documento=maior-detalhe`): 200, 4,79 MB; `dateModified` 2026-10-16;
   encoding `Current` (`CompilacaoMonoVigente`) com versão `@2026-10-16` no `@id`; sem ETag nem Last-Modified.
4. Home real: barreira persistente do host desde 14/11/2026 12:05 (`desafio_captcha`, 403) na URL de metadados da
   Lei 6.404 montada por `urlencode` (`urn%3Alex%3A...`). Na mesma sessão, a URL com `:` e `;` literais foi obtida
   às 11:33; a sonda de 24/11, também literal, obteve 200. Hipótese não demonstrada: o desafio responde à forma
   codificada. Não se provoca o desafio para testá-la.

### 5.2 Decisões

1. **Gatilho, não prova.** O sinal de mudança é o par (`dateModified`, data da versão `Current` no `@id`). Fica em
   `sync_state` e só decide o que recapturar. Nenhum caminho de verificação, temporal, situação, busca ou resposta
   lê esse estado. Não há inferência de vigência a partir de "a compilação da Câmara não mudou".
2. **Revalidação.** `fv acervo revalidar` lê os metadados das obras federais do acervo pela rota `normas_leg` (mesmo
   portão: robots, ritmo de 5 s, teto, barreiras, registro de obtenção). Sinal diferente do último lido marca a obra
   como `renovacao_pendente`. Primeira leitura só registra. Falha é declarada por obra; não marca nem desmarca.
3. **Renovação.** `fv acervo renovar` passa a incluir as obras pendentes, qualquer que seja a idade da captura, e
   desmarca só depois de recaptura bem-sucedida.
4. **URN literal.** A URL de metadados usa `:`, `;` e `@` literais, na forma do `@id` publicado pela própria fonte.
5. **Escopo do `normas_leg` por home.** Arquivo `normas_leg/escopo.json` (`{"escopo": "metadados_e_renovacao",
   "decisao": ..., "em": ...}`). Com ele, a consulta (resolução e obtenção sob demanda) não usa `normas_leg` e
   declara `{"fonte": "normas_leg", "resultado": "fora_do_escopo_do_home"}` em `fontes_consultadas`; revalidação e
   renovação usam. Sem o arquivo, o comportamento é o de antes (outras instalações não mudam).
6. **Reabertura registrada.** `fv acervo abrir-normas-leg --decisao TEXTO` grava o escopo e reabre a barreira do
   host pelo `NormasPortao.reabrir` (registro em `reaberturas`). Novo desafio fecha o host de novo, pelas regras
   do portão, sem nova tentativa.
7. **Manutenção agendada.** `fv acervo manter` executa revalidar e depois renovar, e grava `manutencao.json` no home
   (início, fim, contagens, falhas). `fv acervo agendar --instalar | --remover | --mostrar [--hora HH:MM]` registra
   a execução diária no agendador do usuário, sem privilégio de administrador: Agendador de Tarefas no Windows
   (`schtasks`, tarefa do usuário corrente), unidade e timer de usuário do systemd no Linux. `doctor` alerta se a
   última manutenção concluída tem mais de 48 horas ou falhou.

### 5.3 Correções da auditoria r1

1. **Parser:** fronteira documental separada da admissão como bloco; `DISPOSITIVO_FORA_DA_ARVORE` na ordem do documento com `blocking_scope=provision`; compostas detectadas por quebra de linha.
2. **Citação:** anos curtos, qualificadores encadeados, territorial e ADCT com ano divergente; identidade e Planalto por ano.
3. **Reconfirmação:** redação vigente estrita e bloqueadores de leitura na candidata.
4. **Escopo:** `_rota_admitida` em captura, busca e indexação.
5. **Manutenção:** cursor `manutencao_cursor`, revalidar e renovar com orçamentos separados, agendamento a cada 2 horas.
6. **Metadados:** estrutura validada; sinal ausente após leitura válida não substitui nem desmarca.
7. **MCP:** envelopamento integral de textos documentais em `obter_dispositivo`.
8. **Evidência:** conferência de `interpretacao_codificacao` em `obter_evidencia`.
9. **Derivados:** `snapshot_derived_version` preservada no manifesto local.
10. **Isolamento:** regex corrigida; bateria exclui fontes de manutenção das pendências.

### 5.4 Correções da auditoria r2

1. **Parser:** fronteira documental sem conteúdo mínimo; itens numéricos em fontes compostas; paridade órfã e `<p>`.
2. **Citação:** qualificadores constitucionais completos antes do ano; complemento territorial limitado à ocorrência.
3. **Escopo reduzido:** reconfirmação removida; mantida só `capturas_recentes_nao_canonicas`.
4. **Escopo `normas_leg`:** admissão central em `_get`, `sincronizar` e `doctor`.
5. **Manutenção:** `manter_acervo` com duas fachadas `da_chamada`; renovação com `renovacao_cursor`.
6. **Metadados:** identidade recebida e unicidade do sinal `Current`/`pt`.
7. **MCP:** `situacao_obra.texto_oficial` e `anotacoes[].act_ref` envolvidos.
8. **Evidência legada:** codec registrado ausente não é conferido.
9. **Bateria:** contagem de `sync_state` exclui fontes de manutenção.
10. **Concorrência:** `abrangencia` em `ContextVar` por requisição.


**Ajustes do supervisor sobre as correções da r2 (antes da r3).** (a) Artigo ou rótulo só com nota em fonte órfã
(`Art. 2 (Revogado).`, `h) (Revogado ...)`) é admitido como bloco, igual ao `<p>` equivalente; só a fonte composta
vira fronteira, e a fronteira não zera mais o contexto (zerar apagava o resto do artigo: na CF, 19 caminhos do art.
102 sumiam). (b) Alínea só com rótulo (`h)`, depois de extraída a nota) passa a ser dispositivo próprio; antes o
rótulo se somava ao texto do dispositivo anterior, também no `<p>` (CF art. 102, I, g; Lei 11.101 art. 35, II; LC
214/2025 arts. 201 e 542). (c) `manter_acervo` deixa de abrir guarda: revalidar e renovar abrem cada uma a sua, com
teto próprio (teste com a guarda ativa real). Medição nas 121 obras do Planalto do snapshot 1.4.0a5, contra a
1.2.3: 120 caminhos ganhos, 52 caminhos de atribuição errada ou de texto de emenda citada eliminados, 21 redações
corrigidas (rótulos soltos e textos de outros artigos), nenhuma fronteira `DISPOSITIVO_FORA_DA_ARVORE`.

### 5.5 Rodada 4 (autorizada pelo titular em 24/11, após o BLOQUEADOR da r3)

A r3 fechou os achados 3, 4, 5, 6, 8, 9, 10, 11 e 12 e apontou dois bloqueadores novos (14 e 15) e o resíduo do 2,
todos com resposta errada servida como `verified`. Pela D5, voltaram ao titular, que autorizou uma rodada restrita a
eles e aos resíduos 7, 13 e 16. Regra adotada para fonte órfã: na dúvida, bloqueia a região.

- **Achado 14 (remissão promovida a artigo).** Artigo em fonte órfã só é admitido se o caput começa por maiúscula ou
  por nota entre parênteses. `Art. 45 da Lei ...`, `Art. 45 desta Lei` e qualquer "Art. N" seguido de minúscula viram
  fronteira `DISPOSITIVO_FORA_DA_ARVORE` no artigo corrente, sem artigo próprio.
- **Achado 15 (abertura citada órfã descartada).** A abertura citada (`“Art. 2 ...`) entra como bloco, para a máquina
  de citação controlar o contexto como no `<p>`, só quando o texto imediatamente anterior a introduz (termina em
  dois-pontos); fora disso, fronteira.
- **Achado 2 (itens numéricos).** `1. julgar; 2. processar.` e variantes com ponto ou parêntese são fonte composta
  (fronteira); "Art. 57. O ..." não é item.
- Medição nas 121 obras do Planalto (snapshot 1.4.0a5, contra 1.2.3): 122 caminhos ganhos, 52 eliminados, 21
  redações corrigidas, 60 fontes órfãs admitidas (todas dispositivos genuínos, em CF, DL 1.978/1982, LINDB e Lei
  6.385/1976) e nenhuma fronteira. Os dois caminhos ganhos a mais são os incisos II e III do art. 1º do DL 1.978/1982,
  antes `UNPARSED_LABEL`.
- **Achado 7 (metadados).** Todo identificador presente (`urn`, `legislationIdentifier`, `@id` quando é URN) confere
  com a obra pedida; qualquer contradição recusa o sinal (`identidade_divergente`), sem gravar nem marcar renovação.
- **Achado 13 (filtro territorial).** O qualificador não federal só é procurado no complemento sintático da
  ocorrência, que termina em pontuação ou em "e" que coordena outra oração; o limite de oito palavras saiu.
- **Achado 16 (rótulo sem corpo).** Dispositivo com texto vazio sai `status=unknown`,
  `reason_code=dispositivo_sem_redacao_normativa` e vigência `unknown` com o mesmo motivo (revogação e inexistência
  seguem como estão); em `texto_integral`, todo subdispositivo sem texto aparece com o motivo, nunca some.
- **Delegação.** 2, 14 e 15: supervisor. 7, 13 e 16: rascunho do Cursor, revisado (o rascunho lia a vigência de
  variável reaproveitada no laço das redações anteriores e marcava como "sem redação" também item bloqueado por
  outro motivo; o `urn` deixara de ser conferido por igualdade). Teste de injeção MCP ajustado: desde a r2 cada campo
  documental tem envelope próprio.

**Ajustes após a auditoria r4 (BLOQUEADOR, levado ao titular pela D5).** A r4 fechou 2, 7 e 16 e apontou quatro
resíduos com `verified` errado, corrigidos antes de nova auditoria: (14) remissão com maiúscula (`Art. 45 Da Lei`,
`DESTA LEI`) vira fronteira, reconhecida por preposição seguida de nome de ato, para não bloquear caput como "Art. 62.
Em caso de ..."; (17) abertura citada órfã só é admitida depois do gatilho de emenda que a máquina de citação reconhece
(`_AMEND_TRIGGER`), não depois de dois-pontos genéricos; (18) aposto territorial depois de vírgula ("Constituição, do
Estado de São Paulo") volta a qualificar a ocorrência; (13) "e" que coordena oração passou a ser reconhecido também no
início do complemento. Risco declarado (achado 19 da r4): números no corpo de fonte órfã ("1. 2. 2000") podem bloquear
o artigo; não ocorre no corpus medido. Medição repetida: 122 ganhos, 52 eliminados, 21 redações, 60 órfãs admitidas,
nenhuma fronteira.

**Regra conservadora (titular, 24/11, após a conferência r5).** A r5 fechou 13 e 17 e mostrou que as regras pontuais
não convergiam: resíduos em 14 (`Da referida Lei`), 18 (`Constituição, a do Estado de São Paulo`) e regressão 20
(`Constituição e Emendas Constitucionais do Estado de São Paulo`), todos com `verified` errado. O titular escolheu
regra de classe:
- **Parser.** Artigo em fonte órfã cujo corpo começa por preposição seguida de determinante referencial (referido,
  citado, mencionado, presente, mesmo, respectivo...), de palavra com inicial maiúscula ou de nome de ato ou
  dispositivo vira fronteira. Preposição seguida de substantivo comum ("Em caso de", "Da decisão", "No prazo") é
  caput e continua admitida; sem essa distinção, a CF perderia os arts. 61 e 62.
- **Citação.** Constituição com qualificador territorial em qualquer ponto da mesma frase (aposto, coordenação,
  oração invertida) sai `provavel`, com a marca `constituicao_qualificador_territorial_na_frase`; a verificação vira
  `requer_conferencia` e nunca conclui `verified`. O complemento imediato não federal continua recusado.
- Risco declarado: "art. 5 da Constituição de 1988, do Estado de São Paulo exige-se..." (achado 21 da r5) não é
  reconhecida; não há `verified` errado. Medição repetida sem alteração: 122 ganhos, 52 eliminados, 21 redações,
  60 órfãs admitidas, nenhuma fronteira.

**Após a conferência r6 (BLOQUEADOR, levado ao titular).** A r6 mostrou resíduos lexicais nas duas classes
(`Da supramencionada Lei`, `Art. 45 I, da Lei`; Constituição qualificada em outra frase, antes da citação ou por
apelido). Medidas de classe, sem lista de palavras:
- **Sequência de artigos.** Artigo inteiro em fonte órfã só é admitido se continua a numeração do ato (N+1 do artigo
  anterior, ou N-A); fora disso, fronteira. Texto citado não conta na numeração. No corpus, as órfãs da CF, LINDB e Lei
  6.385 seguem a sequência; a captura mutilada do DL 1.978/1982 (artigos fora de ordem, caput do art. 1º trocado por
  texto citado) passou a ter fronteira, o que a bloqueia (120 ganhos, 52 eliminados, 21 redações).
- **Guarda territorial.** Vale também para Constituição por apelido (`CF, a do Estado de São Paulo`); a frase não
  termina no ponto de abreviatura (`art. 5`); "do Estado" só qualifica seguido de nome próprio ("do Estado de São
  Paulo"), não "do Estado Democrático de Direito".
- **Constituição sem qualificação federal (titular, 24/11).** "Constituição" sem "Federal", "da República", "do
  Brasil", ano ou sigla (CF, CRFB, CR) sai `provavel`, com a marca `constituicao_sem_qualificacao_federal`, e a
  verificação pede conferência. Fecha a classe da Constituição estadual referida fora da frase; custa a confirmação
  direta de "art. 5º da Constituição", que passa a exigir conferência.

**Encerramento (titular, 24/11, após a conferência r7).** A r7 não demonstrou classe nova; restavam resíduos de
classes já decididas. O titular escolheu:
- **Citação, guarda no texto inteiro.** Marca de ente determinado em qualquer ponto do texto analisado ("do Estado
  de São Paulo", "Constituição Estadual" ou gentílica, CE/SP, Lei Orgânica, "a Estadual") impede Constituição exata;
  sai `provavel`. Referências à federação em geral ("dos Estados", "do Distrito Federal", "Justiça Estadual", "do
  Estado Democrático de Direito") não rebaixam. Custo: em peça que cite também uma Constituição estadual, toda
  citação da Federal pede conferência.
- **Parser, risco declarado.** Remissão em fonte órfã que comece por preposição seguida de determinante não listado e
  cite exatamente o artigo seguinte ao anterior (r7, achado 25) pode ser admitida como artigo. Exige markup partido
  numa remissão ao artigo N+1; não ocorre nas 121 obras medidas. Também declarado (r7, achado 28): texto de emenda
  citado sem aspas pode deslocar a contagem e bloquear o artigo órfão seguinte, sem `verified` errado. A
  numeração passa a reiniciar no art. 1º (ADCT).
- Os testes estruturais que leem o código-fonte foram marcados `repositorio`, fora da seleção da wheel.
