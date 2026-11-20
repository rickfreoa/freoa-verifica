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
em tmp_path; não instala confiança. Não foi acrescentado binário nem alterado manifesto
de fixtures. O modelo binário preexistente continua coberto por `*.bin binary`.

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
| 1 | Matriz da trilha (a); pipe/reservas/fila, integração do adaptador e IDs em (b) | Harness HTTPS implementa subconjunto; nenhum cenário executado por recusa da ACL. Faltam cenários discriminados em Questões |
| 2 | test_recusas_na_integracao e matriz da trilha (a) | Cache/SW/prefetch/prerender/bfcache/Early Hints reais pendentes |
| 3 | test_prontidao_quadros_e_ambiente, test_filtro_sem_retencao, test_grafo_completo; matriz (a) | Falta a prova de escopo por navegador real |
| 4 | test_selecao_persistencia_e_cobertura, test_grafo_completo | Sem marcação: sem linha e sem blob; dependente com hash |
| 5 | test_filtro_sem_retencao, test_ids_iguais_em_alvos_distintos | Não se retêm eventos órfãos; ausência ambígua recusa |
| 6 | test_url_publica_gramatica_limite_declarado e testes de segredos da trilha (a) | Falta varredura completa de todos os artefatos reais |
| 7 | test_limpeza_e_recuperacao_confinadas; DACL implementada e conferida antes do lançamento | SetFileSecurityW recusado (5); segunda conta e inventário real de disco NOT RUN |
| 8 | Registro, inventário, vigilância e barreira nos testes de ambiente | Brave impedido pela ACL; Chrome/Edge e extensão instalada no harness NOT RUN |
| 9 | test_metodos_parametros_e_sequencia, test_ast_fronteiras | Igualdade de pedidos com/sem CDP NOT RUN |
| 10 | test_adaptador_real_conectado_porta_unica, test_exemplar_fora_porta_recusado, test_ast_fronteiras | Adaptador real conectado à porta com eventos sintéticos; não é navegador real |
| 11 | test_frescor_sem_verified_por_captura e regressões existentes da 0075 | Teste novo cobre exemplar sem identidade; falta completar todos os cortes com modelo assistido/história/juízo |
| 12 | test_snapshot_preserva_modalidade; store, evidência pública e merge instalado | Falta conferir o ciclo completo de exportação/instalação com vínculos remapeados |
| 13 | CLI/TTY/confirmação, AST, fechamento e consulta sem adaptador | Falta prova transitiva por execução de todos os caminhos MCP/agendado/bateria/remoto e monitoramento real de arquivos |
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

## Questões

1. Esta trilha não está concluída para aceite: a prova Windows real, a cobertura integral
   do harness e as lacunas explicitadas na tabela §3 permanecem pendentes. Não declarar
   SEM_BLOQUEADOR, instalação validada, capturas reais ou Porta L reapurada.
2. O harness atual cobre UTF-8/meta/latin1/cp1252/U+FFFD/BOM/inválido, gzip/deflate,
   codificação vedada, bomba, redirecionamento, 304, CL de 21 dígitos e prazo parcial/sem
   cabeçalhos. Ainda faltam brotli/zstd, chunks/framing malformados, confrontos XHR reais,
   cenários reais de cache/SW/prerender/histórico/HSTS e instalação de extensão. As provas
   sintéticas da porta não substituem esses cenários do §3.1.
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
7. POST do TJSP, PDFs/downloads, NPL/DOU, versão Original como árbitro, mecanismo de extensão
   no harness e nomes reais de cookies continuam nas questões da decisão. Não foram resolvidos.
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
11. Commits bloqueados: duas tentativas de `git add`, incluindo `--git-dir` e
    `--work-tree` explícitos, falharam com
    `fatal: Unable to create 'C:/dev/fv14/.git/worktrees/fv14-0089i/index.lock': Permission denied`.
    O lock não existe. Leitura da ACL mostra entradas Deny de escrita no diretório comum.
    As raízes graváveis declaradas não removeram essa recusa efetiva. Não se alterou ACL,
    índice, ramo, HEAD ou permissões. Nenhum commit foi criado; os arquivos permanecem
    no worktree para revisão. O requisito de status limpo, portanto, não foi cumprido.
