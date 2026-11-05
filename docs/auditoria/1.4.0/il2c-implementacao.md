# IL.2-c — relatório da sessão de escrita

Worktree `C:\dev\fv14-il2c`, ramo `feat/il2c-camara-legin`, base
`9f9e346ba40c962a54a19e51cc16386c915ec691`. Execução offline em 05/11/2026.
Este relatório não é parecer independente nem aceite do marco.

## Entrega e limites

Adaptador registrado, gramática por espécie e vínculo de descoberta, robots por host,
busca por identidade, inventário das páginas, perfis HTML em processo isolado,
seleção aditiva de fonte e versão, persistência de capturas coexistentes e material
histórico conservador. O transporte não foi alterado. A versão do contrato e o arquivo
do consumidor FREOA não foram alterados. Senado e o catálogo de sondas não foram alterados.

Nenhum fundamento histórico positivo foi habilitado. O lote não demonstra nenhum D.
As relações inventariadas sem publicação/texto não são cadeia completa; não há ordem
temporal demonstrada nem pertinência a D comprovada para esses recursos. Não se
reconstroem redações aplicando comandos. A original, quando capturada e documentalmente
datada, é referência anterior, não prova de aplicabilidade.

**Parada do positivo de C13:** o extrator do perfil isolado repete o texto de duas folhas que
a auditoria da especificação informa serem visualmente distintas. A inspeção guarda
as três folhas e a configuração do extrator, mas bloqueia o recorte conclusivo. Não
foi substituído esse material por texto inventado, deduplicado ou por outra rota.
Recorte por rubrica/célula e gabarito visual independente permanecem pendentes.

Conferência adicional somente de diagnóstico: o ambiente tem `pdftotext` Xpdf
4.00 (Git), executado com `-layout` sobre os mesmos bytes, com saída em
`C:\dev\tmp\il2c-anexo-poppler.txt`. Não há `pdftoppm`, `mutool`, PyMuPDF,
pdfplumber ou pypdfium2 disponíveis nos comandos/venv verificados. Essa extração
alternativa não foi integrada ao produto nem usada como gabarito do parser;
não supre a conferência visual de rubrica/célula. A habilitação do positivo
exige extrator/renderizador validado e sua configuração, sem instalação por rede
nesta sessão. A arquitetura atual permanece com pypdf isolado e recorte bloqueado.

Os gabaritos textuais dos testes foram transcritos da leitura local dos corpos,
sem derivá-los do parser. Não se leu a reserva IL.1. A conferência independente desses
gabaritos e a auditoria do código cabem à outra sessão indicada pelo supervisor.

## Critérios

`L` abaixo significa `tests/test_camara_legin.py`; `S`, `tests/test_camara_service.py`;
`I`, `tests/test_camara_importacao.py`. “Parcial” não significa aceite do critério.

| Critério | Estado | Prova e pendência |
|---|---|---|
| C1 | atendido | L `test_c1_c4_identidades_e_query`, `test_c1_texto_de_outra_obra_recusado`, `test_c1_especie_e_ano_nao_sao_confirmados_por_numero`; S `test_c1_planalto_legado_e_camara_sem_escolha_silenciosa`. Três identidades, colisão lei/LC, ano, cabeçalho, seleção explícita e ambiguidade entre origens, inclusive por work_id. Registro/UA cobertos pelas regressões comuns. |
| C2 | parcial | L `test_c2_zero_envio_negativas`, `test_c2_gramatica_direta`, `test_c2_mutante_redirect_sem_salto`; política estrita e vínculo em releitura. Captura por URL avulsa do conector é recusada, exige adaptador ou importação com origem; falta fluxo instrumental de captura nova com cadeia de descoberta. |
| C3 | parcial | L `test_c3_robots_sinteticos_em_memoria`, `test_c3_robots_inconclusivo`, `test_c3_proibicao_impede_conteudo`; robots reais nos testes de resolução. Crawl-delay respeitado; falta matriz completa de falhas/atrasos. |
| C4 | parcial | L `test_c1_c4_identidades_e_query`, `test_c4_total_desconhecido_e_sem_zero_por_silencio`; S `test_c1_c4_alternativas_sao_ambiguidade_sem_escolha`. Três queries independentes, total desconhecido e alternativas preservadas. Paginação e marcador positivo de zero continuam sem captura; não se afirma exaustividade. Matriz de truncamento da busca pendente. |
| C5 | parcial | L `test_c5_inventario_lc123`; três republicações, quatro anexos, ações múltiplas, publicação original. Inventários das demais páginas existem; falta gabarito integral independente de todas as relações. |
| C6 | atendido | L `test_c6_c8_recorte_156_e_notas`, `test_c6_gabaritos_integrais_289_e_254a`, `test_c6_tabelas_reais_e_c8_referencias_editoriais`, `test_c6_c7_hierarquia_sintetica_e_duplicidade`, `test_c6_c17_citacao_e_script_sao_dados`. Gabaritos integrais independentes de 156/289 nos dois perfis, 254-A atualizado e alíneas em tabela do art. 30 original. Hierarquia, limites, spans, citações de outra obra e truncamento exercitados. |
| C7 | parcial | L `test_c6_c7_hierarquia_sintetica_e_duplicidade`; rótulos, concorrência e impedimento do agregado preservados. Faltam provas completas de renumeração/revogação parcial/efeitos diferidos reais da LC 123. |
| C8 | parcial | L `test_c6_c8_recorte_156_e_notas`, `test_c8_nota_incerta_bloqueia_sem_apagar_parenteses`, `test_c6_tabelas_reais_e_c8_referencias_editoriais`; S `test_c8_comparacao_normalizada_preserva_caixa_e_pontuacao`, `test_c8_normalizacao_il1_ancora_sem_relaxar_comparador_legado`. Raw, links, spans e parênteses normativos preservados; comparação Câmara não normaliza caixa/pontuação/número. Formas não reconhecidas bloqueiam o recorte. Faltam gabaritos de cada família editorial real. |
| C9 | parcial | S `test_c9_selecao_coexiste_reinicio`, `test_c9_original_254a_e_invalida`, `test_c9_c12_fachadas_com_versao_e_data`; versões e parâmetro nas três fachadas. Inclusão posterior positiva não demonstrada pelo lote, sem substituição pela atualizada. |
| C10 | parcial | L `test_c10_texto_alterador_real_e_mp_apenas_pagina`, `test_c10_multiplas_acoes_limite_e_ciclo`; S `test_c10_c11_c12_material_real_persistido_sem_confirmar_d`. Aquisição limitada de página/texto publicado, ações preservadas com fetch único por URL, ciclo/orçamento explícitos. Texto e hash da Lei 13.874 obtidos; MP 881 permanece metadado. Ordenação usa publicação documental; original LSA de 17/12, não assinatura de 15/12. Faltam textos do restante da cadeia e prova específica de empate. |
| C11 | parcial | S `test_c11_c12_abstencao_final_e_recibo`, `test_c11_c12_verificar_texto_embutido`; passado/futuro, ambas as versões, cadeia incompleta explícita e fundamento nulo. Última versão anterior depende de captura original e publicação; nenhum positivo histórico demonstrado. |
| C12 | parcial | S `test_c11_c12_abstencao_final_e_recibo`, `test_c11_c12_verificar_texto_embutido`, `test_c9_c12_fachadas_com_versao_e_data`, `test_c12_recibo_obtencao_compromete_versao_e_evidencias`, `test_c12_obtencao_somente_leitura_nao_grava`. Recibos próprios de obtenção, íntegros/adulterados, completo/sem_conteudo, somente leitura e evidências auxiliares autenticadas. Sem prova positiva, todas as guardas permanecem conservadoras. Matriz integral de situação revogada/cancelada e falhas parciais da nova fonte ainda pendente. |
| C13 | parcial | L `test_c13_pdf_preservado_mas_recorte_nao_aprovado`: hash independente, três folhas, configuração e repetição textual sem deduplicação. Positivo de rubrica/célula interrompido; ver limite acima. F-01 corrigido na 0077 §6 e em C13. |
| C14 | parcial | L `test_c2_c14_evidencia_corrompida_recusada`, testes de robots/redirect; reutilização do transporte e regressões 0045 existentes. Falta matriz completa de categorias específicas do novo adaptador. |
| C15 | atendido | S `test_c9_selecao_coexiste_reinicio`, `test_c1_planalto_legado_e_camara_sem_escolha_silenciosa`, `test_c15_snapshot_preserva_instante_e_versoes`, `test_c10_c11_c12_material_real_persistido_sem_confirmar_d`; L `test_c13_pdf_preservado_mas_recorte_nao_aprovado`. Natureza/origem/corte/instante por recurso, snapshot mantém instante e marca procedência, alterador tem identidade própria; metadados/anexo não herdam natureza do HTML. |
| C16 | parcial | I: importação idempotente, recibos inválidos, corpo editado, manifesto/hash e descoberta obrigatória. 17 pares promovidos pelo instrumento; faltam revisão independente dos gabaritos e toda a matriz negativa de origem. |
| C17 | parcial | L `test_c6_c17_citacao_e_script_sao_dados`; S `test_c17_campos_em_saida_antecipada`; contrato Python/MCP/REST e consumidor FREOA. Perfis isolados e nenhuma dependência nova. Falta matriz completa de determinismo/limites do novo perfil. |
| C18 | parcial | Relatório, testes focados, mutantes e comandos finais abaixo. Sem parecer independente, sem qualificação IL.3 e sem avanço do marco. Commits locais bloqueados pelo sandbox. |

## Reprodução das fixtures

Instrumento: `scripts/capturar_fixture.py --importar-offline RECIBO --corpo CORPO
--chave CHAVE [--origem-recibo RECIBO_DA_PAGINA_QUE_PUBLICOU_O_LINK]`.
Sem rede e sem recaptura. As origens são recibos do mesmo lote local, não strings de URL
arbitrárias. O manifesto preserva o recibo original completo e seu SHA-256, UA,
método, instante, MIME, tamanho/hash do corpo e vínculo publicado. Repetição idêntica
é leitura idempotente; divergência é recusada. Os 17 pares estão em
`tests/fixtures/camara_legin/` e os 34 arquivos constam de `FIXTURES.json`.

PDF: `pypdf 6.21.4`, `PdfReader(..., strict=True)`, extração `plain`, orientações
0/90/180/270, sem OCR. O recibo dos bytes permanece separado da extração.
“Folha PDF” não é página impressa. O positivo visual de C13 é `NOT RUN` nesta sessão.

## Validação e commits

Python utilizado: `C:\dev\fv14-il\.venv\Scripts\python.exe`; não há `.venv` neste
worktree. `PYTHONPATH` aponta ao worktree; `TMP`/`TEMP` e os basetemps ficam em
`C:\dev\tmp`. Guarda de teste externa `il2c_offline_guard` impede DNS/conexões
externas reais; conexões locais dos testes de servidor continuam possíveis.

Primeira execução completa de diagnóstico: 8.365 passaram, 14 falharam, 6 skips e
34 live desmarcados, em 1.658,43 s. Registro: `C:\dev\tmp\il2c-full-final.log`.
Essa execução não valida o estado final: as correções posteriores exigem repetição.
Falhas identificadas: guarda/nomes de auxiliares e entrada binária do PDF,
interpretação de captura Planalto agora selecionada explicitamente no teste,
expectativas dos novos campos/recibos, limites MCP e ACL privada de
`TemporaryDirectory` no Python Windows. Nenhuma garantia AST foi dispensada;
os testes de wheel usam a factory herdável já existente do pytest e continuam
executando a cópia isolada sem o pacote por caminho.

Execução completa final:

```text
python -m pytest tests -q -m "not live" -p no:cacheprovider --basetemp C:\dev\tmp\pt-il2c-full
8379 passed, 6 skipped, 34 deselected in 2144.96s (0:35:44)
```

Saída 0; registro em `C:\dev\tmp\il2c-full-validado.log`. Inclui contrato do
consumidor FREOA, fachadas, garantias AST e execução real da cópia isolada da
wheel. Os 6 skips e os 34 live desmarcados não são provas positivas. A conferência
focal das últimas correções também passou (15 testes de recibos/garantias/limites,
10 de fachadas/wheel e 2 de autenticação das recusas).

Fechamento: oito mutantes rejeitados novamente (saída 1 por asserção), com os
quatro arquivos de produto restaurados byte a byte e seus SHA-256 conferidos
contra o estado da suíte aprovada (`C:\dev\tmp\il2c-antes-mutantes.json`).
`python scripts/ruff_catraca.py`: saída 0, sem saída textual, após a restauração.
`git -c core.whitespace=cr-at-eol diff --check`: saída 0. Sem diff em
`transport.py`, `contrato.py` ou `tests/contrato/consumidores/freoa.json`.

Mutantes causais executados com alteração temporária do código, restauração em
`finally` e pycache separado por execução. Todos os oito produziram falha de
asserção no teste indicado (saída 1); o teste positivo correspondente também
integra a suíte final. Registros: `C:\dev\tmp\il2c-mutantes.json` e
`C:\dev\tmp\il2c-mutante-*.log`.

| Mutação | Regressão que a rejeita |
|---|---|
| Aceitar query na rota de conteúdo | L `test_c2_gramatica_direta` |
| Dispensar identidade do texto publicado | L `test_c1_texto_de_outra_obra_recusado` |
| Trocar palavra normativa | L `test_c6_c8_recorte_156_e_notas` |
| Trocar 254-A por 254 | L `test_c6_c8_recorte_156_e_notas` |
| Alterar data de publicação | L `test_c5_inventario_lc123` |
| Aceitar hash falso | L `test_c2_c14_evidencia_corrompida_recusada` |
| Marcar cadeia incompleta como completa | S `test_c11_c12_abstencao_final_e_recibo` |
| Remover parêntese normativo como nota | L `test_c8_nota_incerta_bloqueia_sem_apagar_parenteses` |

As fixtures usadas são os 17 pares promovidos do lote: três buscas/páginas de
norma/atualizados/originais, dois robots, entrada, PDF principal e página da MP.
Recortes integrais usam constantes transcritas nos testes L; relações/publicações
e hashes esperados são constantes próprias em L/S. Bordas sintéticas são geradas
em memória nos testes, com propósito declarado; não são arquivos de captura.

Não executados: rede/sondas, positivo histórico para D, positivo visual do anexo,
reserva/equivalência/qualificação IL.3 e parecer independente. Qualificação
permanece `nao_apurada`. As pendências por critério acima não são aprovadas por
uma suíte verde.

O primeiro `git add` e o primeiro `git commit` foram recusados com:
`Unable to create 'C:/dev/fv14/.git/worktrees/fv14-il2c/index.lock': Permission denied`.
O índice fica fora das raízes graváveis (`C:\dev\fv14-il2c`, `C:\dev\tmp`), e a
política de aprovação é `never`. Nenhum commit foi criado, nenhum push foi executado
e não se tentou contornar a restrição mudando o repositório ou seu índice.

Mensagens propostas para os commits locais, quando o supervisor puder gravar o índice:

1. `Implementa importação offline das capturas Câmara e corrige F-01`.
2. `Adiciona adaptador Legin com política estrita e perfis isolados`.
3. `Integra seleção de versões e abstenção histórica no serviço`.
4. `Registra regressões, mutantes e limites da implementação IL.2-c`.

Em cada mensagem, os rodapés exigidos são:

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WYdQmwigzgE4BLZBq7EEki
```

FIM IL.2-c IMPL.
