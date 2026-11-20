**Veredito: BLOQUEADOR.** Conferência sobre `16d4c7e7e3f26b0d54adca4353866d602d43dcc4`, no ramo solicitado. Nenhum arquivo foi editado; os arquivos rastreados permaneceram limpos.

1. **ALTO — a validação dos vínculos ainda admite recibos incompletos.**  
   **Local:** [snapshot.py:641](/C:/dev/fv14-0089i/freoa_verifica/snapshot.py:641) e [snapshot.py:653](/C:/dev/fv14-0089i/freoa_verifica/snapshot.py:653).

   **Cenário reproduzido:** partindo de A/B admitidos pela porta e persistidos pelos geradores existentes, executei `_merge_attach` real com bancos SQLite exclusivamente em memória:
   
   - Remover `vinculo` do recibo de B produz `MERGE_OK []`, conservando B sem vínculo.
   - Definir `A.obtencao_id=null` e `B.vinculo.metadados_obtencao_id=null` também produz `MERGE_OK []`.

   A primeira variante escapa pelo `continue`; a segunda transforma igualdade entre valores ausentes em confirmação de identidade. Referências inexistentes, IDs com tipo errado e hash divergente foram corretamente recusados.

   **Critério:** 0089 §2.6(1), §2.11, vínculo B→A, e §3 item 12. **A colisão originalmente demonstrada foi corrigida, mas a classe não está fechada.**

   **Correção:** exigir vínculo completo para capturas assistidas do recurso B e validar presença, tipo e conteúdo dos identificadores antes de compará-los. Preservar a compatibilidade das capturas legadas e dos recursos que legitimamente não possuem vínculo.

2. **ALTO — o aceite de passividade admite valores nunca observados nos controles.**  
   **Local:** [harness_assistida_0089_cenarios.py:666](/C:/dev/fv14-0089i/tests/harness_assistida_0089_cenarios.py:666).

   **Cenário reproduzido:** controles idênticos salvo `Accept-Language: pt-BR,pt;q=0.5` e `q=0.6`. Com adaptador, `q=0`, `q=0.1` e `q=1` recebem, todos, `passou=True`. A normalização substitui qualquer valor sintaticamente aceito por `<Q>`.

   **Critério:** 0090 §3.3 exige alternativas efetivamente observadas, com as mesmas multiplicidades. A implementação é mais permissiva que o texto aprovado. A reprodução demonstra falso positivo do aceite, sem demonstrar alteração de requisições pelo adaptador.

   **Correção:** conferir os valores originais e as alternativas observadas antes da normalização, preservando ocorrência, combinação e multiplicidade. Rever os testes que atualmente aprovam valores inéditos.

3. **MÉDIO — evento de zero bytes antes da resposta do streaming causa recusa indevida.**  
   **Local:** [transport.py:734](/C:/dev/fv14-0089i/freoa_verifica/transport.py:734).

   **Cenário reproduzido:** inserir, antes da resposta a `streamResourceContent`, um `dataReceived` sem `data`, com ambos os comprimentos iguais a zero; depois entregar `bufferedData=""` e o restante do fluxo válido. O controle sem esse evento admite a captura; com um ou dois eventos, recusa com `STREAMING_ASSISTIDO_DIVERGENTE`.

   **Critério:** 0090 §3.2 permite eventos anteriores sem `data` e exige tamanho do buffer igual à soma anterior. Nesse cenário, ambos são zero. A restrição adicional não consta do texto aprovado.

   **Correção:** aceitar essa igualdade, mantendo reservas, limites e confrontos posteriores. Acrescentar regressão positiva com evento zero anterior e corpo posterior não vazio.

**Fechamento dos achados da r1:**

| Achado | Resultado |
|---|---|
| 1 — projeções de metadados | Fechado nas variantes examinadas. Das 144 mutações independentes, somente valores válidos foram admitidos: listas vazias e flags `False`. |
| 2 — vínculos em snapshots | Remapeamento corrigido; classe ainda aberta pelo achado 1 acima. Colisões naturais de A, B e ambos, IDs diferentes, destino não vazio e mesclagem repetida preservaram os vínculos válidos. |
| 3 — ambiente e temporários | `TEMP/TMP/TMPDIR/TEMPDIR` confinados no lançamento. Monitoramento e segunda conta permanecem declarados pendentes, conforme o escopo aprovado. |
| 4 — provas de aceite | Prova Windows e logs adicionais presentes. Gestos humanos continuam pendentes para execução com o titular antes da sessão manual. |
| 5 — cobertura | Fechado no acervo misto examinado: modalidades conhecidas contadas separadamente, legado `NULL` explicitado e `contagem_parcial=True`. Fonte vazia publica zero sem parcialidade. |

**Confirmações adicionais:**

- Transporte contra `87b43f7`: **77 definições preexistentes, nenhuma ausente ou alterada**; nós preexistentes do módulo preservados na mesma ordem.
- `sondas` e `captura` ausentes dos fechos estáticos de service, MCP e CLI.
- Manifesto de componente, 0090 §3.1: **25 cenários em memória, nenhuma divergência**, incluindo ausência, erro de leitura, JSON inválido, caminhos relativos/externos e locations 1/5/10.
- Execução própria: **659 passed, 1 skipped, 352 deselected**, sem `conftest`, cache ou fixtures de arquivos temporários.
- Logs locais conferidos: **1612 passed** na bateria afetada e **619 passed** em `repositorio`. Wheel: **121 arquivos do produto idênticos ao checkout**; modelo literal presente na wheel e no sdist, com o hash registrado.

Os adiamentos estão declarados como pendências, sem falsa aprovação. Não os trato como bloqueadores desta versão. O manifesto de aceite ainda não contém a 1.4.0a6, e não localizei seu registro de release; o espelhamento exigido pela nota de escopo permanece por conferir.

**Não verifiquei:** suíte offline global, CI remota, nova instalação Windows, instalador público de snapshots com blobs em disco, navegador real, gestos humanos ou sessão manual. As reproduções de mesclagem usaram o código real sobre bancos em memória. Não demonstrei `verified` indevido em consulta final.