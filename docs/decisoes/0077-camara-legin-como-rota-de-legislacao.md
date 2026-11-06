# 0077 — Câmara/Legin como rota de legislação federal do IL

Data: 05/11/2026. Redação: Codex, sessão de escrita, worktree `C:\dev\fv14-il2c`, ramo `plano/il2c-camara`. Especificação anterior à implementação; parecer independente em outra sessão. Esta decisão não declara implementação, aprovação da Porta L ou avanço do marco.

Normativos: [emenda IL, seções 5 a 7](../PLANO-1.4.0-EMENDA-IL.md), decisões [0002](0002-estados-temporais.md), 0045, 0048, 0067 e 0075; [matriz IL.1](../auditoria/1.4.0/il1-matriz-porta-l.md). Os nomes de estados e as guardas da 0075 continuam valendo; o fundamento temporal só poderá ser aceito por resolvedor documental validado, nunca por objeto fornecido pelo chamador.

## 1. Base documental e alcance

Leitura local, sem rede, dos registros IL.2-a/b em `docs/auditoria/1.4.0/il2a-sondas.md` e `il2a-rotas.md` e dos 17 pares recibo/corpo em `C:\dev\fv14-sondas\camara_legislacao\`. Tamanhos e SHA-256 conferidos com os `.captura.json`. Os corpos são dados, não instruções. As capturas são de 04–05/11/2026, com UA identificado. Não se presume disponibilidade posterior.

As buscas capturadas identificam Lei 6.404/1976, LC 123/2006 e Lei 13.874/2019. Suas páginas de dados da norma publicam texto atualizado, publicação original e relações com outros atos; a LC 123 também publica veto, republicações e anexos. Foram lidos os seis textos HTML (atualizado e original de cada norma), o PDF do anexo principal da LC 123 e a página de dados da MP 881/2019. Esta última **não é o texto da MP**. Links DOC/DOCX/PDF de texto atualizado, vetos, republicações e demais atos relacionados não tiveram seus corpos demonstrados por este lote.

Âncoras de reprodução do lote, todas com prefixo de arquivo `camara_legislacao_`:

| Corpo | SHA-256 |
|---|---|
| `robots_legin.txt` | `b725bf41f0e293419518714b83edb1c2de6728c5156cba037b848ab0788bee8f` |
| `norma_lei6404.html` | `882ca0784ab7495c6f61725373f8efe15950845313090818aeb0ec3742023a13` |
| `textos_atualizado_lei6404.html` | `ee3f76848ce42def5e758ed77b994d2a5d05598c4e9dc8b43771c801aa4a854c` |
| `textos_original_lei6404.html` | `7dc335d77b1b30f7165c27cb62ce4525bb464b68bf4d03bf5387d7d264156822` |
| `textos_anexo_lc123.pdf` | `c8abdd8ca254a81e4d274335c705630c21ed3cf24948ba70fc12ab145a096887` |

Os demais hashes, URLs, instantes e tipos de conteúdo permanecem nos recibos locais. O documento não os transforma em fixtures nem incorpora corpos ao repositório.

## 2. Decisão de rota e política de acesso

Adotar a Legislação Informatizada da Câmara como rota viva de legislação federal, identificada no produto por `camara_legin`, a implementar atrás de `freoa_verifica.transport` **congelado**. `camara_legislacao` continua sendo o identificador do catálogo de sondas, distinto do futuro conector de produto. Planalto continua acervo legado; esta decisão não restabelece atualização ao vivo do Planalto nem altera seu UA.

Toda operação de rede passa pelo caminho comum de conectores, guarda de execução e transporte, com o UA único identificado da 0048. Robots deve ser obtido por host, interpretado antes do conteúdo e preservado como evidência da política aplicada. Falha de leitura/interpretação ou recusa impede a consulta; não é permissão implícita. O robots www2 capturado tem um grupo `User-Agent: *` com muitos `Disallow`; nenhum alcança os caminhos Legin examinados. Isso não libera o host inteiro nem dispensa nova avaliação da política no acesso futuro. Termos de uso/licença continuam não demonstrados e pendentes conforme IL.2-a; esta decisão não atesta permissão jurídica geral.

### Padrão estrutural admitido

Admissão exige simultaneamente URL segura, estrutura abaixo e vínculo de descoberta preservado (`href`, URL e hash da página oficial que o publicou). A estrutura não é um gerador de endereços. Slugs, IDs, variantes de formato e páginas seguintes nunca são adivinhados.

1. Hosts exatos `www.camara.leg.br` e `www2.camara.leg.br`, HTTPS, porta padrão, sem credenciais. Robots apenas `/robots.txt`, sem query. No portal: `/legislacao` e GET `/legislacao/busca`, com campos publicados `abrangencia`, `tipo`, `numero`, `ano`, `geral`; escopo `Legislação Federal`, valores de tipo documentados no formulário, número sem pontuação, ano completo. A consulta inicial não autoriza pesquisa avançada ou coleções. Paginação só se publicada, dentro da mesma política e demonstrada por captura; até lá não se afirma exaustividade.
2. Em www2, conteúdo exclusivamente em `/legin/fed/<familia>/<periodo>/<arquivo>`. Pares observados de família/radical: `lei/lei`, `leicom/leicomplementar`, `medpro/medidaprovisoria`, `declei/decreto-lei`, `decret/decreto`. Os dois últimos aparecem como links relacionados, não como corpos parseados. `<periodo>` é ano de quatro dígitos ou uma das faixas efetivamente publicadas nos links preservados (por exemplo, `1970-1979` e `1980-1987`), contendo o ano do ato; não se presume que toda faixa seja uma década. A implementação deve congelar a lista das faixas observadas como expectativa independente. Novas famílias/faixas ficam fora até evidência e ampliação explícita da especificação.
3. `<arquivo>` tem radical da espécie, número decimal positivo, dia de um ou dois dígitos, mês do vocabulário de slugs (`janeiro`, `fevereiro`, `marco`, `abril`, `maio`, `junho`, `julho`, `agosto`, `setembro`, `outubro`, `novembro`, `dezembro`), ano de quatro dígitos e ID decimal positivo da norma, separados por hífen. Exemplo efetivamente capturado: `lei-6404-15-dezembro-1976-368447-norma-pl.html`. Conferir data válida e coerência com período/identidade. Sufixos admitidos para obtenção nesta etapa: `-norma-pl.html` (leis/LC), `-norma-pe.html` (MP e atos executivos), `-normaatualizada-pl.html`, `-publicacaooriginal-<id_publicacao>-pl.html` e `-anexo-pl.pdf`, nos pares de espécie/formato sustentados pelo lote. A extensão é terminal; não há query de conteúdo. Não generalizar `pl|pe` a todas as combinações por conveniência. Texto de MP/executivo e suas variantes ainda sem captura ficam como lacuna, não se fabricam trocando sufixo.
4. O link de conteúdo deve partir da seção correspondente da página de norma, ou de referência editorial identificada no texto oficial. Texto atualizado, original e anexo da mesma obra devem conservar o identificador da norma; outro ato exige vínculo de relação e validação de identidade própria. Número de publicação é outro ID, nunca derivado do da norma. Fragmentos de navegação não abrem nova rota; eventual fragmento de âncora fica como metadado, fora da requisição. Links HTTP antigos são preservados como referências não obtidas: não se troca esquema automaticamente; caminho equivalente em HTTPS exige publicação oficial demonstrada.
5. Fora: `/legin/` genérico, legislação estadual/municipal, outros hosts ou subdomínios, APIs não documentadas, proposições, login/admin, travessia, codificação ambígua de separadores, arquivos com sufixo extra, queries inesperadas e qualquer endereço sem cadeia de descoberta. Vetos, republicações, anexos de republicação, DOC/DOCX e PDF de texto atualizado são inventariados quando publicados, mas sua obtenção/parse fica fora da admissão inicial de conteúdo acima, até captura e perfil próprios.

Os prefixos atuais do transporte não implementam essa gramática. O adaptador deve aplicar a validação estrita **antes** do transporte, inclusive na releitura de capturas. Para não seguir destino de caminho não validado, as requisições desta etapa usam `max_redirects=0`; o callback atual de salto recebe apenas host e não pode provar a gramática do destino. Redirecionamento vira indisponibilidade, sem seguir `Location` ou procurar rota alternativa para superar recusa. Não se modifica o transporte para satisfazer esta decisão. A especificação C2 fixa provas negativas da política.

## 3. Tipagem IL.4/IL.5, sem inferência de vigência

| Recurso efetivamente interpretado | `natureza_texto` | Justificação |
|---|---|---|
| Publicação original HTML, com identidade e referência de publicação conferidas | `publicacao_original` | Reprodução oficial identificada da publicação, não a versão atual da obra |
| Texto atualizado HTML publicado pela página da norma, com identidade vinculada e perfil validado | `consolidacao_oficial` | A Câmara publica uma redação integrada com notas das alterações. Como a compilada do Planalto, é consolidação oficial editorial; não precisa conter rasura para pertencer a essa classe |
| Página de dados, busca ou recurso de natureza ainda não validada | `nao_identificado` | Autoridade do host e nome do arquivo não provam natureza textual |
| Anexo | conforme documento e vínculo comprovados, senão `nao_identificado` | O PDF deve ser atribuído à publicação/versão correta, sem herdar a natureza do HTML atualizado |

A diferença material para o Planalto é que os atualizados capturados não exibem a sequência histórica riscada: apresentam a redação atual declarada pela fonte e notas editoriais. Não se criam redações anteriores a partir dessas notas. `consolidacao_oficial` não significa texto autenticado do DOU nem versão válida em qualquer D, e não implica `verified`.

Nota R3 (F14): para `camara_legin`, o início da redação do texto atualizado é sempre indeterminado, inclusive sem notas e nos agregados. Nenhuma leitura pública pode inferi-lo da data da obra ou do ato citado na nota. A obtenção sinaliza a lacuna e a ausência de redação anterior; o histórico se abstém de linha do tempo conclusiva. Metadados do recorte incluem as notas de todos os componentes, inclusive caputs, preservando cada alvo, sem transferir eventos ou datas ao pai. A publicação original conserva sua data documental como referência, sem provar aplicabilidade. Esta nota explicita também a execução conservadora da seção 4.

`source_kind` é a espécie do ato cujo texto se entrega: `lei`, `lei_complementar`, `medida_provisoria` etc., conforme identidade declarada e validada, senão `nao_identificado`; não é `camara_legin` nem a espécie da obra alterada quando a evidência pertence ao alterador. `esfera=federal` exige identidade federal conferida. `procedencia` é persistida **por captura**: `captura_direta`, `snapshot` ou `sessao_assistida` conforme obtenção efetiva; ausência de marca é `nao_identificado`. Listar relações não transforma as capturas dos atos em `cadeia_de_alteracoes`; esse valor só descreve resultado derivado de cadeia explicitamente rotulado, nunca encobre o modo de obtenção dos documentos. Não há reconstrução mecânica nesta etapa.

Cada evidência mantém `capture_id`, URL, SHA-256 e `captured_at=fetched_at` do recibo, nunca a data do ato, do parser ou da instalação. `acervo_ate` continua o corte do Planalto congelado, nulo para a Câmara viva. Snapshot não renova a captura. Nenhum desses eixos afirma vigência; cláusula literal do ato é somente `vigencia_declarada`, sem cálculo de vacatio, LINDB, eficácia ou transição.

## 4. Redação em D: execução conservadora da regra 3

D diferente de hoje em America/Sao_Paulo inclui passado e futuro. A redação atual capturada depois de D não é retrodatada. Nem data de assinatura, data em slug, data da captura, nota editorial, ordem da página ou existência de link são fundamento do período.

Sem versão oficial identificada para D, devolver **a última versão oficial documentalmente datada anterior a D**, com sua data e evidência, e a cadeia ordenada de atos alteradores publicados desde essa versão até D, com texto de cada ato. Não se exige publicação exatamente no dia D: a questão é a cobertura documental do período. Uma consolidação sem data de referência comprovada não concorre como versão anterior. Se a original for a única versão anterior documentada, ela é material de referência, não automaticamente a redação aplicável em D.

Para cada relação, preservar ato, publicação (veículo, data e página quando disponíveis), dispositivo atingido, ação literal e link da página de norma; obter desta o texto publicado do ato, com captura/hash/âncora próprios. Ordenar por data documental de publicação crescente, preservando também a posição e o rótulo da lista da Câmara. Empate fica explícito, com desempate apenas de apresentação por identificador e posição; nunca se inventa precedência normativa. Data faltante impede afirmar ordenação completa. Várias ações do mesmo ato não são descartadas; capturas podem ser deduplicadas, relações não. Regulamentação, veto, revogação parcial e ação condicionada não se convertem em substituição textual automática. MP reeditada, MP convertida e lei de conversão são atos distintos.

Estado final para essa entrega: `unknown`, motivo `sem_versao_oficial_na_data`, `fundamento_temporal=null`; mesmo texto coincidente continua não verificado para D. Cadeia ou versão anterior não obtida deve vir explicitamente ausente/incompleta, com pendência e motivo por recurso. Não se apresenta cadeia vazia como prova de inexistência de alterações. Falha de acesso/parse é `unavailable` (na fachada, `indisponivel`) na operação afetada, com categoria da 0045 quando provada; não se mascara falha como simples lacuna histórica. Se o serviço puder entregar material parcial com estado histórico `unknown`, deve também expor a indisponibilidade, sem alegar atendimento integral da regra 3. Ausência de versão anterior identificada, publicação incerta ou pertinência indecidível mantém `unknown` com motivo específico e material disponível.

### Quando a publicação original pode sustentar D

Somente com prova positiva, cumulativa e recuperável:

1. Identidade, dispositivo integral e publicação original identificados; data documental não posterior a D, não inferida do slug.
2. Intervalo até D documentado: ou cadeia comprovadamente completa sem ato alterador publicado até D, ou prova documental por dispositivo de que nenhum evento no período alterou o recorte pedido. Lista vazia, silêncio da busca e ausência de nota não são essa prova. Havendo alterações em outros dispositivos, exige-se prova de escopo, inclusive de comandos gerais e renumeração.
3. Nenhuma questão pendente de veto, republicação/retificação, reedição/conversão, revogação parcial, comando sobreposto, produção de efeitos, vacatio ou transição que impeça identificar a versão para D. Não se resolve juízo jurídico por aritmética ou modelo.
4. Resolvedor interno valida as capturas, hashes, âncoras, intervalo coberto e vínculo ao dispositivo; produz `fundamento_temporal` na forma da 0075 (`tipo=versao_oficial_na_data`, `capture_id`, `url`, `sha256`, `data`), com evidências complementares recuperáveis da prova do período. Só então as guardas podem reconhecer o fundamento e o confronto integral pode dar `verified` para D. Origem oficial e fundamento não substituem o confronto textual.

O lote atual **não demonstra esses requisitos para nenhum D concreto**. A capacidade positiva histórica permanece por provar. Fundamento parcial, fornecido pelo chamador ou apenas sintaticamente completo continua rejeitado. D futuro sem versão identificada é `unknown`; as duas exceções de inexistência da 0075 permanecem estritas. A situação cadastral atual não rebaixa abstenção histórica a negativa. Em todo caminho público, o estado final refere-se a D, inclusive `verificar_texto` e `vigencia` de `obter_dispositivo`.

## 5. Senado e outras rotas

O instrumento barrou `legis.senado.leg.br` após 403 no **robots.txt**, categoria `recusa_identificado`, e não consultou a API. O conector `senado` do produto não é alterado por esta decisão: a recusa do robots não prova recusa da API; a 0048 registra aceitação com UA identificado em 20/10/2026. Esse registro anterior tampouco prova disponibilidade atual. Mantêm-se as barreiras do instrumento, inclusive alias, destinos de redirecionamento e robots, sem nova tentativa nesta tarefa.

Questão aberta: compatibilidade entre política de acesso atual e conector existente. Reabertura exige manifestação oficial capturada que esclareça/libere o acesso identificado e revisão explícita do bloqueio do instrumento pelo supervisor; ou evidência oficial nova, obtida por via autorizada, sobre mudança da política/API que justifique reavaliar o produto. Falha observada pelo produto em uso autorizado deve ser registrada como tal, sem induzir repetição pelo instrumento. Não se tenta API para contornar a recusa do robots nem se muda UA, IP ou rota.

DOU segue barrado no instrumento pelo 403 do robots; LexML não admite `/busca/`; normas.leg.br continua sem rota documentada de texto. Nenhuma delas é fallback oculto para lacuna da Câmara.

## 6. Questões abertas e consequências

- Termos de uso/licença e política de atualização da Câmara, ainda não demonstrados; permanecem pendências antes da ativação ao vivo.
- Completude/paginação da busca e das relações, frequência e data de referência da consolidação; não demonstradas pelas três normas.
- Texto publicado dos alteradores (a MP 881 capturada só documenta sua página), publicações de MPs/executivos e famílias ainda sem perfil; sem esses corpos não há cadeia completa prometida.
- Vetos, republicações, retificações, anexos de republicação e DOC/DOCX/PDF alternativos: links observados não validam conteúdo nem equivalência. No anexo PDF capturado há três folhas. O exame textual reproduzido usa `pypdf 6.21.4`, `PdfReader(BytesIO(corpo))`, `page.extract_text()` com configuração padrão (`extraction_mode="plain"`, sem visitantes, sem OCR): o extrator repete o texto das folhas 2 e 3. Isso não prova folha repetida: a conferência por renderização informada na auditoria da especificação mostra conteúdos distintos. A repetição é defeito/limitação da extração; não deduplicar, reordenar ou colar folhas silenciosamente. Ordem, colunas, escopo e recorte exigem conferência visual e gabarito próprio.
- Tratamento dos links HTTP antigos, novos padrões de slug, redirecionamentos e formatos fora da admissão inicial exige evidência e decisão explícita; não autoriza relaxar o transporte.
- Nenhuma captura demonstra versão oficial por data, completude temporal ou remissões resolvidas. A habilitação de fundamento exige prova de período, regressões por classe e auditoria; a qualificação por capacidade e `porta_l.py` pertencem ao IL.3.

Implementação futura deve satisfazer [IL.2-c, C1–C18](../auditoria/1.4.0/il2c-especificacao.md), com contrato aditivo e `CONTRATO_VERSAO` inalterado. Não há mudança de piso, reserva ou critério de `verified`, nem reconstrução mecânica, conclusão jurídica de vigência ou autorização de substituição do Jusratio.

## Nota D5 — redução de escopo (F15/F16)

Por correção conceitual do titular, caput designa somente a cabeça do artigo;
a premissa de F15 e a pendência do prompt anterior nesse ponto são retiradas.
Para `camara_legin`, `.parX.caput` produz abstenção com
`caput_refere_se_ao_artigo`, com as leituras `artN.caput` e `artN.parX` como
alternativas sem confirmação. Não se materializam caputs fora do artigo;
notas impróprias são preservadas com alvo incerto. Parser Câmara versão 4
invalida a releitura de modelos anteriores até reprocessamento.

A referência a inciso do caput é correta. Sem recorte exato representado,
`.caput.incX` produz `inciso_do_caput_nao_resolvido`. Fica pendente a
normalização `artN.caput.incX → artN.incX` em `citation.py`, ressalvada a
colisão com incisos de parágrafos. Não se implementa essa equivalência.
As guardas precedem a negativa e a construção do histórico, em identidade,
texto, verificação embutida, resolução e obtenção, por Python/MCP/REST.
Caput de artigo representado e outras fontes preservam seu comportamento.
Esta nota não declara novo aceite do auditor nem avanço de marco.
