# IL.2-c — relatório da escrita e correção r1

Worktree `C:\dev\fv14-il2c`, ramo `feat/il2c-camara-legin`, revisão auditada
`95fddcda9689b9a89e77b74e91d87826b3535fbe`, PR #36. Correções em 05/11/2026.
Esta sessão implementa; outra sessão independente audita. Não é aceite do marco.

O parecer `C:\dev\_il\parecer-pr36-r1.md` identificou F1–F9 como bloqueadores.
As afirmações anteriores de C6 atendido, bloqueio efetivo de toda nota desconhecida
e preservação integral do contrato eram excessivas. A suíte anterior de 8.379
testes passou em `95fddcd`, mas não detectou os contraexemplos semânticos; não
valida o estado corrigido nem demonstra atendimento integral de C1–C18.

## Correções e provas delimitadas

`R` indica `tests/test_il2c_r1.py`. Os testes de R parametrizados por fachada
exercitam Python, REST e MCP. Capturas oficiais permanecem intactas e com os hashes
do manifesto. Os casos sintéticos são gerados em memória com propósito declarado.

| Achado | Implementação | Regressão pública / limite |
|---|---|---|
| F1 | Guarda comum antes de identidade/texto; recorte e agregado. Reconhecimento de LC, Primitivo §, Vide, veto e transformação de parágrafo. | R `test_f1_notas_reais_nao_sao_texto_normativo`, `test_f1_guarda_comum_causal_antes_de_identidade`, `test_f1_duplicidade_real_do_agregado_original`. Notas reais, 23 stubs do parecer e impedimentos sintéticos. Não certifica toda forma editorial possível. |
| F2 | Delimitador externo e balanço de aspas; epígrafes e artigos pontuados permanecem em QuotedAmendment. Escopo incerto bloqueia. | R `test_f2_lei_alteradora_nao_possui_inciso_do_codigo_civil`, `test_f2_escopo_incerto_bloqueia_saida`. Não certifica toda apresentação tipográfica possível. |
| F3 | Anotações com alvo; revogação de filho não migra ao pai; REVOGACAO_PARCIAL impede conclusão sobre agregado. | R `test_f3_revogacao_parcial_preserva_alvo`, caso real do art. 110 da LSA; guarda sintética de descendente. Não habilita reconstrução temporal de revogações parciais. |
| F4 | Construção comum da resposta; campos específicos aditivos; regras/intervalo preservados na abstenção histórica. | R `test_f4_contrato_consumidor_sem_alterar_esquema`, consumidor existente aplicado às duas versões, corrente e com data. Consumidor e CONTRATO_VERSAO intactos. |
| F5 | Política comum em resolução/indexação/busca, sync comum/semente, datas/textos de alteradores, diagnóstico e instrumento. Planalto só acervo; Câmara bloqueada antes de robots. | R `test_f5_pendencia_bloqueia_antes_do_transporte`, `test_f5_planalto_apenas_acervo_em_todas_as_buscas`, `test_f5_semente_e_alteradores_nao_capturam_legado`, `test_f5_diagnostico_nao_captura_legado`, `test_f5_instrumento_nao_captura_legado`. Replay permanece permitido; ativação ao vivo pendente. |
| F6 | Fontes, categoria e evidência preservadas em obtenção por citação/work_id e no recibo; sem histórico conhecido, mantém a omissão anterior. | R `test_f6_falha_tipificada_por_citacao_e_work_id`, `test_f6_sem_historico_preserva_omissao_antiga`. Recibo completo autenticado; sem_conteudo conserva dimensões/códigos de decisão e compromisso HMAC da lista, sem URL em claro. Não certifica toda falha específica de fonte. |
| F7 | Fixture intercepta transporte offline efetivamente chamado; guarda explícita de conexão. | R `test_f7_fixture_atinge_fronteira_e_nao_tenta_conexao`; hash capturado e zero tentativas do produto. Socketpair interno da stdlib permitido para asyncio no Windows. |
| F8 | Busca → página descoberta → inventário → recurso → persistência das origens; tipo Fonte do MCP aditivo. | R `test_f8_busca_ate_persistencia_e_reinicio`, nas três fachadas, com reinício offline e hash. Paginação e marcador positivo de zero continuam pendentes. |
| F9 | Este relatório substitui as afirmações excessivas e separa regressões de aceite. | Revisão documental desta sessão; parecer independente do estado corrigido ainda pendente. |
| CI recibo | A asserção por substring podia confundir 6404 dentro de HMAC com texto em claro. | `test_c12_recibo_obtencao_compromete_versao_e_evidencias[sem_conteudo]` força HMAC com esse prefixo e exige campos/compromissos exatos. Nenhuma mudança no formato para esconder dígitos. |
| CI concorrência | Aquisição do lock repete PermissionError transitório no Windows dentro do prazo, preservando erro permanente. | `test_duas_capturas_concorrentes_preservam_as_duas_entradas`, `test_publicacao_repete_lock_em_delete_pending` e `test_lock_com_permissao_negada_permanente_preserva_erro`. A janela entre exclusão do lock e nova criação não decorre do campo de importação adicionado; o lock anterior só tratava FileExistsError. CI Windows 3.11 precisa repetir. |

A decisão 0078 registra a regra corrigida. Parser `camara-legin-2`; modelos
anteriores exigem reprocessamento antes de conclusões. R
`test_modelo_anterior_nao_reutiliza_falso_positivo` cobre essa recusa.

## Estado por critério

Todos os critérios permanecem **parciais, sem aceite independente**. Em C1/C3/C18,
ativação ao vivo não foi habilitada. Em C2, captura instrumental avulsa continua
recusada e falta fluxo instrumental novo integral. Em C4 faltam paginação, zero
positivo e matriz integral de truncamento. Em C5/C16 faltam gabaritos independentes
integrais. Em C6/C7/C8 há regressões dos achados, sem certificação exaustiva de
apresentações/editoriais. Em C9/C12/C17 há prova aditiva de contrato e recibos,
sem equivaler a aceite de todo o critério. Em C10/C11 a cadeia permanece incompleta,
sem fundamento histórico positivo. Em C13 o PDF conserva três folhas e configuração
do pypdf, mas o recorte visual conclusivo continua bloqueado. Em C14 falta matriz
integral de falhas. Em C15 a prova permanece limitada aos recursos e cenários testados.

Não executados: rede/sondas, positivo histórico para D, positivo visual do anexo,
reserva/equivalência/qualificação IL.3 e parecer independente. Qualificação permanece
`nao_apurada`. Nenhum modelo generativo ou dependência nova foi introduzido.

## Validação desta revisão

Ambiente: venv existente `C:\dev\fv14-il\.venv\Scripts\python.exe`, com PATH
ajustado para `python`; PYTHONPATH aponta exclusivamente a este worktree.
TMP/TEMP e basetemps fora dos checkouts. Sem rede e sem push.
Testes focados: `tests/test_camara_*.py` (expansão PowerShell),
`tests/test_il2c_r1.py`, `tests/contrato` e `tests/test_captura_instrumento.py`,
com `-q -m "not live" -p no:cacheprovider --basetemp C:\dev\tmp\pt-il2c-r1b`:
**413 passed in 366.61s**. Execução conjunta limpa após corrigir a expectativa
de minimização de F6 e restaurar, com monkeypatch, o documento compartilhado
alterado pelo teste causal de F1. Python 3.14.6, pytest 9.2.0, Windows.

Complemento identificado na primeira execução completa: `tests/test_busca_nao_indexados.py`,
com os mesmos marcadores, cache desabilitado e basetemp focado: **4 passed in 0.95s**.
A troca da fonte simulada foi necessária porque a expectativa anterior de captura
viva no Planalto contradizia F5; nenhuma asserção sobre candidatos sem prova foi retirada.
Também foi atualizada a expectativa do motivo de não consulta em `test_fd_busca`.
A obtenção voltou a omitir fontes quando o histórico é vazio, preservando o formato
anterior; o dado conhecido permanece preservado integralmente. As três regressões
novas de omissão alcançam as três fachadas, por citação e work_id. Regressões
direcionadas dos arquivos afetados e de R: **63 passed, 18 deselected in 19.26s**;
F6 completo (histórico conhecido e ausente): **9 passed, 34 deselected in 2.97s**.
A primeira rodada completa foi interrompida após essas três falhas; uma segunda
tentativa também foi interrompida durante a conferência global de F5. Nenhuma
delas é evidência de aprovação da suíte completa.

A conferência global encontrou ainda o diagnóstico e a sincronização semente
(inclusive datas e textos de alteradores) com captura própria do Planalto. A
política foi centralizada em `politica_captura.py` e aplicada também ao instrumento
de captura e à sincronização comum. Testes antigos de falha de busca usam agora
Câmara simulada, mantendo as asserções de indisponibilidade/nao_indexado. Os testes
de capacidade exigem Planalto somente acervo e ausência de captura viva quando vazio.

Os testes antigos de mecanismos legados (repetição, breaker, fila, datas e saúde)
usam a fixture opt-in `captura_legada_simulada`, nunca autouse. Ela permite o
mecanismo legislativo legado só naquele teste e restringe DNS e conexões a loopback;
os conectores são dublês ou o transporte está ligado a servidor local. As asserções
originais de contagem, recusa, datas e repetição foram preservadas. As provas novas
de F5 usam a política real e exigem zero consultas. Validações direcionadas:
**184 passed in 79.33s**, **22 passed, 8445 deselected in 3.29s** (doctor) e
**18 passed, 177 deselected in 4.86s** (F5/F6).

Os cenários antigos de CAPTCHA dos controladores `verificar_citacao`,
`verificar_texto` e `obter_dispositivo` passaram a usar resoluções CVM, fonte
habilitada, porque a Câmara pendente já não chega ao transporte. Mantêm TCP local,
categoria/evidência de desafio e uma requisição por host; a prova de texto exige
também as três citações, e a obtenção exige a categoria na resposta pública.
Regressões: **48 passed in 24.91s** em `test_fix17_controladores.py` e
`test_fix17_variantes.py`. A rodada completa que carregou as entradas antigas
não serve como aprovação final.

Validação final, no estado materializado e com saída da suíte no terminal:

```text
python -m pytest tests -q -m "not live" -p no:cacheprovider --basetemp C:\dev\tmp\pt-il2c-r1b-full
8427 passed, 6 skipped, 34 deselected in 1954.41s (0:32:34)

python scripts/ruff_catraca.py
exit_code=0 (sem achados novos em relação à baseline)
```

Depois da suíte e da catraca, a conferência de
`C:\dev\tmp\il2c-r1b-estado-validado.json` confirmou os mesmos SHA-256 de **65
arquivos de código, testes e fixtures**, o ramo e o HEAD. O gerador/conferidor está
em `C:\dev\tmp\il2c-r1b-hashes.py`. `git diff --check` passou. Permanecem sem diff:
transporte, dependências, versão do contrato e consumidor FREOA. Não houve rede
externa, sondas ou push. O aceite independente e a repetição da CI Windows 3.11
permanecem pendentes; a suíte local foi executada no Windows com Python 3.14.6.

Estado final dos testes focados, após a extensão global de F5, a guarda do
instrumento/CLI e as novas negativas de F6: **419 passed in 465.04s** no comando
focado acima. Instrumento/CLI isolados: **67 passed, 45 deselected in 1.41s**.
Seleção da wheel sem dependência de caminhos do checkout: **1 passed in 11.09s**.
O teste que importa o script da CLI é `repositorio`.

Uma rodada completa posterior terminou com **8424 passed, 6 skipped, 34 deselected
e 3 failed in 1944.13s**. Duas falhas vinham da precedência da guarda de fonte sobre
a rejeição de URL/host: o instrumento agora valida o plano antes de aplicar a
política, sempre antes da rede. **71 passed, 432 deselected in 1.27s** nas regressões
de instrumento e DOU. A terceira foi a execução isolada da wheel: além das mesmas
duas falhas, o subprocesso registrou uma falha intermitente no teste de publicação
de fixture, cuja exceção original ficou oculta pelo corte do diagnóstico. Não a
atribuo a uma causa confirmada. O teste isolado passou na mesma cópia; a reprodução
integral da seleção da wheel passou com **4488 passed, 2 skipped, 81 deselected,
46 warnings in 398.50s**. O gate agora preserva o diagnóstico completo em arquivo
temporário quando o subprocesso falha. A rodada completa final, registrada acima,
passou inclusive nesse gate. A causa daquela falha intermitente não foi confirmada.

**Commits locais bloqueados pelo ambiente.** `git add` e `git commit` recusaram
a criação de `C:/dev/fv14/.git/worktrees/fv14-il2c/index.lock` com `Permission denied`,
mesmo estando `C:\dev\fv14\.git` nas raízes declaradas graváveis desta sessão.
A leitura da ACL do diretório revelou entradas explícitas de negação de escrita;
não existe `index.lock` residual. Não alterei ACL, índice, checkout ou configuração
para contornar a restrição. HEAD permanece `95fddcd`; nenhum commit ou push criado.
As quatro mensagens preparadas, com os dois rodapés exigidos, estão em
`C:\dev\tmp\il2c-r1b-{ci,conector,guardas,relatorio}-commit.txt`.

Prova causal adicional, sem editar arquivos do produto: em processo Python separado,
substituí `_provision_blocking_issues` por uma função que retorna lista vazia. O teste
`test_f1_guarda_comum_causal_antes_de_identidade[python]` falhou porque a resposta
pública voltou a `identity.status=verified` diante de `NOTA_NAO_RECONHECIDA` no
descendente. A mutação só existiu naquele processo; o checkout permaneceu intacto.

Mutante adicional de F5, também apenas em processo separado: permitir Planalto na
política fez `test_f5_instrumento_nao_captura_legado` falhar ao chegar a `_buscar`,
fronteira substituída por uma falha explícita. Sem a mutação, a prova passa antes
dessa fronteira e sem tentativa de conexão. Nenhum arquivo do produto foi mutado.

FIM IL.2-c R1.

## Correção da auditoria R2 — 2026-11-06

Base de escrita: `feat/il2c-camara-legin`, HEAD `0d2bb41706b719446aaf3ae27f778e0c2fc4dd41`,
PR #36. Parecer integral lido: `C:\dev\_il\parecer-pr36-r2.md`.
Esta é a sessão de implementação; o aceite pertence à sessão independente de auditoria.

| Achado | Implementação e regressão |
|---|---|
| F10 | Caput separado do agregado, com texto e span próprios, nas versões atualizada e original. Fallback legado recusa agregado com descendentes ou rótulos de descendentes. Os 282 caminhos atualizados e 236 originais do parecer são parâmetros de testes públicos. A testemunha de descendente vem de leitura independente dos elementos físicos do HTML, sem chamar o parser para gerar o esperado; a projeção agregada tem de conter a testemunha e o caput tem de excluí-la. Há positivo de caput exclusivo e negativo causal de troca por agregado. |
| F11 | Alvo resolvido pelo sujeito e predicado editoriais e sua hierarquia, incluindo caput de artigo/parágrafo/inciso/alínea e renumeração de rótulo primitivo. Alvo incerto fica nulo e gera `ALVO_NOTA_INCERTO`, sem associação inventada. As 31 associações do parecer e os 29 agregados com impedimentos são parâmetros separados. Issues do agregado preservam alvo, kind e raw dos impedimentos; não se copiam datas/eventos dos filhos às anotações próprias. Nota de ancestral também bloqueia conclusão sobre o filho. Histórico editorial se abstém, sem início inferido da data da obra. |
| F12 | A definição comum de stub de veto rejeita texto sem caracteres alfanuméricos normativos, inclusive ponto e ponto e vírgula. Os 11 caminhos atualizados e 14 originais do parecer têm regressões, além de quatro formas sintéticas. Modelo, nota, identidade, âncoras e bytes permanecem; obtenção não entrega pontuação normativa e confronto não confirma. Accessor do modelo também recusa o stub. |
| F13 | Guarda aplicada antes de construir intervalos do histórico: duplicidade, quarentena, dados incompletos, revogação parcial e notas impedem histórico conclusivo. Resposta explícita `unknown`, linha vazia, flags, eventos preservados e `needs_judgment=true`. Cobertos os oito caminhos duplicados/agregados e os 26 agregados com revogação parcial enumerados em R1. |

Revisão das rotas de leitura: `resolver_citacao`, construção comum de
`obter_dispositivo` por citação/work_id, busca local com data, histórico,
`ultima_versao_oficial_anterior`, `verificar_citacao` e verificação de texto
embutido. REST, MCP e CLI encaminham ao serviço; há regressões dinâmicas Python,
REST e MCP. A busca conserva candidatos, mas não publica vigência afirmativa de
recorte impedido. A cadeia documental continua material de referência, com
`cadeia_completa=false` e `fundamento_temporal=null`, sem transformar texto integral
do alterador em prova do dispositivo ou período solicitado.

A gramática aceita sufixos literais de parágrafo (`§ 1-B`), necessários para
exercitar os caminhos do parecer no histórico público. Nenhuma letra é descartada.
As expectativas antigas de texto positivo do art. 289 atualizado foram substituídas
por abstenção explícita; os testes do comparador preservam caixa e pontuação sobre
o caput não impedido do art. 1. O positivo de persistência/reabertura usa esse mesmo
recorte. A publicação original do art. 289 continua exercitada separadamente.

Parser `camara-legin-3`; modelos anteriores não são reutilizados como prova.
Registro da correção em `docs/decisoes/0079-correcao-dos-recortes-legin-r2.md`.
Transporte, UA, dependências, versão do contrato, consumidor, catálogo e fixtures
oficiais permanecem sem alterações. Sem rede externa, sondas, push ou ativação viva.
As limitações de capacidade e o aceite independente declarados em R1 permanecem.

Ambiente: Windows, Python 3.14.6, ambiente existente `C:\dev\fv14-il\.venv`
(MCP 2.3.0). O Python padrão tinha MCP 1.28.1 e não foi usado para a validação final.
`PYTHONPATH` aponta para este worktree e `C:\dev\tmp`; `TMP/TEMP` fora do checkout.
A guarda `il2c_offline_guard` bloqueia DNS/conexões externas nos testes. Todos os
pytest focados usam `--basetemp C:\dev\tmp\pt-il2c-r2`.

Validação focada final, após a última alteração de código:

```text
python -m pytest tests/test_camara_legin.py tests/test_camara_service.py tests/test_il2c_r1.py tests/test_il2c_r2.py -q -p no:cacheprovider --basetemp C:\dev\tmp\pt-il2c-r2 --tb=short
789 passed in 1068.68s (0:17:48)
```

Saída preservada em `C:\dev\tmp\il2c-r2-foco-final.log`. Provas causais,
apenas em processos separados, sem editar produto: devolver agregado para caput
fez a regressão pública do art. 156 falhar com `text=verified` (**1 failed**);
desabilitar a guarda do histórico fez os dois casos do art. 59 falharem com
`status=encontrada` (**2 failed**). Logs em
`C:\dev\tmp\il2c-r2-mutante-{caput,historico}.log`.

Validação completa final, com saída no terminal e preservada também em
`C:\dev\tmp\il2c-r2-full.log`:

```text
python -m pytest tests -q -m "not live" -p no:cacheprovider --basetemp C:\dev\tmp\pt-il2c-r2-full
9093 passed, 6 skipped, 34 deselected in 3129.82s (0:52:09)

python scripts/ruff_catraca.py
exit_code=0 (nenhum achado novo em relação à baseline)
```

Após a suíte e a catraca, `C:\dev\tmp\il2c-r2-hashes.py --conferir` confirmou os
mesmos SHA-256 de **44 arquivos de código, testes e fixtures**, com ramo e HEAD
preservados; fotografia em `C:\dev\tmp\il2c-r2-estado-validado.json`.
`git diff --check` passou. Não houve alteração em transporte, dependências,
versão do contrato, consumidor FREOA, catálogo de sondas ou conector Senado.
Rodadas interrompidas ou anteriores à última alteração não contam como validação
final. CI Windows 3.11 e aceite da auditoria independente permanecem pendentes.

**Commit bloqueado por permissão.** Uma única tentativa de `git add` foi recusada
ao criar `C:/dev/fv14/.git/worktrees/fv14-il2c/index.lock` (`Permission denied`).
Não repeti, não alterei ACL nem contornei a restrição. Nenhum commit foi criado;
as alterações ficam no worktree para o supervisor. Três mensagens com os dois
rodapés exigidos estão em `C:\dev\tmp\il2c-r2-{recortes,leituras,relatorio}-commit.txt`.

FIM IL.2-c R2.
