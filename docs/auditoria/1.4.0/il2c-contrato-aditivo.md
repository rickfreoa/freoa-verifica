# Contrato aditivo da implementação IL.2-c

`CONTRATO_VERSAO` permanece inalterado. A implementação é parcial e não qualifica
capacidades da Porta L. O relatório `il2c-implementacao.md` delimita as pendências.

`obter_dispositivo` recebe `versao`, opcional, default `vigente`, ou
`publicacao_original`. Valor inválido é `formato_invalido`/`versao_invalida`.
O campo de saída `versao` identifica a seleção. `vigente` é o atualizado declarado
pela fonte, sujeito ao modelo temporal; não é conclusão jurídica de vigência.
A original é texto publicado, com vigência desconhecida; dispositivo incluído por
outro ato só terá primeira publicação se a evidência desse alterador estiver obtida.
Sem ela, devolve `unknown`/`primeira_publicacao_do_dispositivo_nao_obtida`.

O parâmetro aditivo `fonte` permite seleção explícita quando Planalto instalado e
Câmara coexistem para a mesma obra. Omissão conserva ambiguidade entre fontes.
Fonte e versão participam da seleção das capturas persistidas; a última entrada no
cache não substitui silenciosamente outra versão. Python, MCP e REST
(`GET /v1/dispositivos`) expõem os dois parâmetros. `data` não muda a versão pedida.

Nas respostas de verificação e obtenção, os campos históricos aditivos são
`ultima_versao_oficial_anterior`, `cadeia_alteracoes`, `cadeia_completa` e
`pendencias_temporais`, com a forma de C11. Sem publicação/texto de um alterador,
o recurso permanece com data/texto/evidência nulos e pendência explícita. A posição
da fonte é preservada; não se apresenta a ordem da lista como ordem de publicação.
As verificações embutidas de `verificar_texto` preservam os mesmos campos.

`obter_dispositivo` também gera recibo autenticado pelo caminho comum: fonte,
versão, obra e caminho participam dos parâmetros comprometidos. O recibo inclui
as evidências do recorte, da versão anterior e dos textos alteradores obtidos.
`sem_conteudo` mantém compromissos sem armazenar consulta/texto em claro;
somente leitura devolve `run_id=null` e `registro.motivo=somente_leitura`.

No modo normalizado, os perfis HTML Câmara usam apenas NFC, espaços,
aspas/apóstrofos e ordinais da IL.1. Caixa, pontuação e números são preservados;
os demais perfis mantêm o comparador anterior. A âncora é mapeada para o texto
original, sem reescrever o corpo capturado.

Sem prova documental do período, o resultado para D é `unknown` com
`sem_versao_oficial_na_data`, `fundamento_temporal=null` e `cadeia_completa=false`.
Nenhum dicionário do chamador habilita fundamento. As guardas das demais fontes da
0075 continuam valendo. Não há reconstrução textual por comandos alteradores.

Para o texto atualizado de `camara_legin`, acrescenta-se o motivo
`inicio_redacao_atual_nao_documentado`: a fonte não estabelece o início da redação
atual, inclusive em recortes sem notas. Na obtenção, `vigencia.intervalo=null`,
`vigencia.limites_inferidos=true`, `vigencia.needs_judgment=true` e
`redacao_anterior_ausente_na_fonte=true` explicitam essa lacuna. O histórico
mantém `linha_do_tempo=[]`, `needs_judgment=true` e acrescenta
`limites_inferidos=true` e a indicação de redação anterior ausente. Impedimentos
específicos conservam seus motivos e o novo motivo também aparece nos flags;
para D permanece a abstenção histórica acima. `anotacoes` da obtenção e `eventos`
do histórico incluem todos os componentes do recorte, inclusive caputs, cada
qual com seu `target_path`, sem atribuir eventos ou datas ao agregado. A publicação
original continua referência documental, sem afirmar aplicabilidade.

Evidências dos perfis HTML validados usam o construtor comum:
`source_kind` da espécie efetiva, `natureza_texto` conforme atualizado/original,
`procedencia` por captura, `esfera=federal`, `captured_at=fetched_at`, `acervo_ate=null`
na Câmara. O anexo inspecionado não herda natureza do atualizado e seu recorte fica
bloqueado. Busca e página de norma continuam metadados, sem promoção a texto verificado.
