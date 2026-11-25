**Veredito: BLOQUEADOR.** Auditei `87b43f7..c32b4f1b03c2815ad930aec0715171a95b495a3e`, no ramo e worktree indicados. Não editei arquivos; o estado dos arquivos rastreados permaneceu limpo.

Reproduzi dois defeitos: admissão sem os metadados necessários para excluir credenciais e quebra do vínculo A/B na mesclagem de snapshots. Há também lacunas obrigatórias de aceite.

As execuções focadas desta auditoria tiveram **451 aprovações e um skip**, sem navegador, usando testes que dispensam arquivos temporários. Não equivalem à suíte completa. Conferi o log externo do **nono ensaio**, posterior aos oito mencionados: **52 passed, 5 skipped**, sobre `4116e53`; entre esse commit e o HEAD só mudaram documentos.

**Achados**

1. **ALTO — ausência de metadados vira prova de ausência de credenciais.**  
   Local: [cdp.py:646](/C:/dev/fv14-0089i/freoa_verifica/assistida/cdp.py:646).

   `_evento` transforma `headers` ausente em `{}` e `associatedCookies` ausente em `[]`. Assim, informa à porta `authorization_presente=False` e nenhum cookie, embora não tenha recebido a prova necessária.

   **Prova:** executei três variantes de `requestWillBeSentExtraInfo`: sem ambos os campos, só com `headers` e só com `associatedCookies`. Todas terminaram com:

   ```text
   ADMITTED: True
   REFUSALS: []
   ```

   Reprodução mínima, em memória:

   ```python
   from freoa_verifica import transport as t
   from freoa_verifica.assistida.perfis import PERFIS
   from tests.assistida_0089_util import adapter, request, entregar

   s = t.SessaoPortaAssistida(PERFIS["planalto"].porta, navegador="Brave 1")
   try:
       ad = adapter(s)
       original = ad._evento

       def truncar(sid, rid, metodo, dados):
           if metodo == "requestWillBeSentExtraInfo":
               dados = {"requestId": rid}
           return original(sid, rid, metodo, dados)

       ad._evento = truncar
       request(ad)
       entregar(ad)
       print(ad.pedidos["cdp", "pedido"].admitida is not None)
       print(ad.motivos_recusas)
   finally:
       s.encerrar()
   ```

   Executar com `.venv\Scripts\python.exe -B -X utf8 -`, passando o trecho pela entrada padrão.

   **Critério violado:** §2.1(2), §2.3(2) e §2.4: dado necessário ausente ou ambíguo exige recusa, nunca inferência.

   **Correção por classe:** validar presença, tipo e estrutura dos campos necessários **antes** da projeção sanitizada. Diferenciar lista comprovadamente vazia de campo ausente. Acrescentar regressões no adaptador para ausência, `null`, tipo incorreto e elementos incompletos; repetir essa revisão em todas as projeções de metadados de segurança.

   A reprodução demonstra admissão sintética indevida; não afirma que o Brave observado tenha omitido esses campos.

2. **ALTO — snapshot pode instalar B com referência inexistente ao metadado A.**  
   Locais: [persistencia.py:111](/C:/dev/fv14-0089i/freoa_verifica/assistida/persistencia.py:111), [snapshot.py:660](/C:/dev/fv14-0089i/freoa_verifica/snapshot.py:660).

   O vínculo `metadados_capture_id` fica dentro de `assistida_json`. A mesclagem remapeia IDs por chave natural e pelas FKs SQL, mas não essa referência embutida.

   **Prova:** usei capturas A/B efetivamente admitidas pela porta, obtidas pelos geradores sintéticos existentes, em dois bancos SQLite exclusivamente em memória:

   - destino: A com ID `a-local`;
   - snapshot: a mesma obtenção A com ID `a-snapshot`;
   - B aponta para `a-snapshot`.

   `_merge_attach` reconheceu a duplicata A e terminou normalmente:

   ```text
   MERGE []
   PORT-ADMITTED A/B; LINK TARGET a-snapshot EXISTS False
   FK CHECK 0
   ```

   Restaram `a-local` e `b-snapshot`; B conservou a referência inexistente. `foreign_key_check` não detecta referências dentro de JSON.

   **Critério violado:** §2.11, vínculo B→A; §2.6(1); §3 item 12.

   **Correção por classe:** representar e validar os vínculos locais de forma remapeável, preservando separadamente a identidade original da obtenção. Conferir existência e hash do dependente depois da mesclagem. Cobrir colisões naturais de A e B, IDs diferentes e instalações repetidas. O teste atual de dependentes instala em destino vazio; o teste de colisões cobre work/provision, sem alcançar esse caso.

3. **ALTO — faltam as provas obrigatórias sobre gravações externas e acesso ao perfil pessoal.**  
   Locais: [test_assistida_0089_navegador_cenarios.py:569](/C:/dev/fv14-0089i/tests/test_assistida_0089_navegador_cenarios.py:569), [harness_assistida_0089_cenarios.py:816](/C:/dev/fv14-0089i/tests/harness_assistida_0089_cenarios.py:816), [ambiente.py:604](/C:/dev/fv14-0089i/freoa_verifica/assistida/ambiente.py:604).

   O inventário enumera arquivos dentro do perfil; a varredura posterior percorre `tmp_path`. Isso não observa gravações fora dessa árvore nem acessos ao perfil pessoal. O lançamento de produção também herda o ambiente; não fixa `TEMP`/`TMP` no perfil da sessão.

   **Prova:** o próprio registro reconhece que a varredura não é inventário do disco/SO e que o monitoramento real do perfil pessoal permanece pendente. O nono ensaio executa o mesmo teste restrito.

   **Critério não demonstrado:** §2.7(2), §3 itens 7 e 13. Não demonstrei gravação externa efetiva ou acesso indevido; demonstrei que o aceite disponível não pode detectá-los.

   **Correção por classe:** executar monitoramento de arquivos por processo e descendentes, incluindo leituras do perfil pessoal e gravações fora do perfil dedicado, durante execução e encerramento. Comparar o ambiente do harness com o lançamento de produção. Gravação externa inevitável e não eliminável deve impedir a sessão, conforme a especificação.

4. **ALTO — o conjunto obrigatório de aceite ainda não está concluído.**  
   Locais: [test_assistida_0089_navegador_cenarios.py:185](/C:/dev/fv14-0089i/tests/test_assistida_0089_navegador_cenarios.py:185), [test_assistida_0089_navegador_cenarios.py:592](/C:/dev/fv14-0089i/tests/test_assistida_0089_navegador_cenarios.py:592), [implementacao-trilha-b.md:1259](/C:/dev/fv14-0089i/docs/auditoria/0089/implementacao-trilha-b.md:1259).

   Permanecem sem prova real: extensão por gesto humano, recarga forçada, prerender, Early Hints e acesso por segunda conta. Além disso:

   - a extensão desempacotada `location 4` não prova a regra de permissões para extensão comum/externa `location 1/10`;
   - Chrome/Edge foram provados recusados por política nesse notebook, sem executar neles o restante do aceite exigido para cada navegador admitido;
   - não localizei teste de **instalação Windows** que confira `fv sessao` instalado e recusa por pipe indisponível;
   - não há evidência apresentada de suíte offline completa verde no código final. A bateria de 987 casos é focada.

   **Critério:** §3 itens 2, 7, 8 e 16; D5.

   **Correção:** completar as provas nos ambientes apropriados e registrar resultados vinculados ao commit auditado. Impedimento local justifica `NOT RUN`/skip; não dispensa critério obrigatório. Qualquer redução de escopo depende de decisão formal.

5. **MÉDIO — a migração permite publicar zero onde existe acervo sem modalidade preenchida.**  
   Locais: [018_sessao_assistida.sql:2](/C:/dev/fv14-0089i/freoa_verifica/store/migrations/018_sessao_assistida.sql:2), [indicacao.py:129](/C:/dev/fv14-0089i/freoa_verifica/assistida/indicacao.py:129).

   **Prova:** inseri uma captura anterior à 018, com `procedencia='captura_direta'`, e apliquei o SQL real da migração em memória. A linha permaneceu com `modalidade_acesso=NULL`; `cobertura` publicou:

   ```text
   automatico: {capturas: 0}
   assistido:  {habilitado: True, capturas: 0}
   ```

   Antes da migração, a função usa `None` para contagem não mensurável; depois dela, a mera existência da coluna passa a permitir esse zero incompleto.

   **Critério:** §2.13 e §3 item 11: declaração correta dos denominadores, preservando a distinção entre desconhecido e zero.

   **Correção por classe:** contabilizar registros sem modalidade explicitamente e declarar contagens parciais/desconhecidas. Recuperar a modalidade somente quando a proveniência existente a provar; não inferir modalidade de snapshots antigos.

**Auditoria própria do transporte — D5**

Comparei AST por nome qualificado e `ast.dump(include_attributes=False)`: **77 definições preexistentes, zero ausentes e zero alteradas**, incluindo métodos e definições internas. Os demais nós preexistentes do módulo também foram preservados. Nenhuma definição antiga referencia as novas definições assistidas; os semáforos automático e assistido são separados.

O fecho estático das entradas não interativas e os testes estruturais examinados não mostraram caminho automático para `capturar_assistida` ou para o adaptador. Isso não equivale a uma prova formal de todo comportamento dinâmico possível em Python.

| Linha §2.4 | Resultado da inspeção |
|---|---|
| 1 | URL efetiva usa `validate_reference` e gramática do recurso; fragmento descartado. |
| 2 | `_public_unicast` e porta 443; DNS permanece responsabilidade declarada do navegador. |
| 3 | Estado seguro, TLS 1.2/1.3 e emissor exigidos. |
| 4 | HTTP/1 usa funções preexistentes sobre `headersText`; h2/h3 preservam multiplicidade e recusam TE. |
| 5 | Exige `loadingFinished`; falha de rede recusa. |
| 6 | Lista fechada de codificações; original registrado. |
| 7 | Limites e confrontos decodificado/CL/codificado presentes; vazio recusado. |
| 8 | Nenhum salto de rede admitido; HSTS exige prova e identidade estrutural. |
| 9 | Detector preexistente sobre amostra de 64 KiB. |
| 10 | MIME e charset validados; correção Terra r1 confirmada. |
| 11 | Interpretação estrita preexistente; bytes não substituídos por texto. |
| 12 | Timer independente; 30 s incluem admissão; classificação conforme sinais de resposta. |
| 13 | Taxa mínima declarada inaplicável; prazo continua. |
| 14 | Rate limiter/breaker automáticos não usados pela porta. |
| 15 | Cotas e reservas presentes; excesso global encerra. Não medi consumo real de memória. |
| 16 | Sem emissão ou repetição de requisição pela porta. |
| 17 | Perfil validado; JSON permitido apenas no caminho assistido e quando declarado. |
| 18 | Não recebe cabeçalhos de chamador; obtenções têm IDs distintos. |
| 19 | Porta exige nomes/motivos; **adaptador perde a exigência de presença — achado 1**. |
| 20 | Sem reaproveitamento. |
| 21 | Recibo construído por `observe_http_response`, com allowlist e descarte de duplicatas. |
| 22 | `wallTime + delta` do mesmo pedido, em UTC. |

Em §2.5–§2.7, confirmei o hash dos bytes decodificados, o modelo literal da cauda, a separação entre procedência/modalidade e a ausência de atribuição de `verified` pela porta. Permanecem os achados sobre metadados de credenciais, vínculo em snapshot e prova de artefatos.

**Expectativas alteradas — classe B**

| Caso | Avaliação do HEAD |
|---|---|
| 304 | **Sustentado.** Agora exige primeira captura, revalidação condicional, 200 aparente/304 bruto e recusa do segundo requestId. Aborto anterior vira skip, não aprovação do código normativo. |
| Sem cabeçalhos | **Sustentado.** Conexão mantida aberta; exige `Timeout` sem sinal de cabeçalhos completos. |
| Cabeçalho parcial | **Sustentado.** Prefixo incompleto não equivale aos eventos completos definidos pela linha 12; exige `Timeout`. |
| Sem término | Positivo de controle necessário: cabeçalhos completos e corpo incompleto exigem `RespostaInvalida`. Está presente. |
| Vazio | **Sustentado.** Recusa anterior de streaming só é aceita com prova de ordem/erro. A prova específica de `EmptyBody` permanece offline. |
| Cache por requestId | **Correção necessária.** Proibir qualquer captura da URL confundia a primeira carga legítima com a segunda derivada. O teste atual exige mecanismo e recusa da chave afetada. |
| Controles do item 9 | Dois a quatro controles são aceitáveis para demonstrar variação independente. Sem variação, não há autorização para normalizar. |
| `q` de Accept-Language | A correção Terra r2 restringe nome, posição variável e sintaxe; idiomas, ordem, espaços, demais parâmetros e outros campos continuam comparados. **Precisa da formalização proposta abaixo**, pois o §3(9) exige igualdade inclusive de cabeçalhos. |

Os negativos examinados agora exigem mecanismo/motivo, e os positivos relevantes exigem captura. Não encontrei permanência do falso verde amplo descrito no segundo ensaio. Isso não cobre as lacunas dos achados 1–4.

**Suficiência do §3, itens 1–16**

“Real” abaixo significa execução registrada no nono ensaio, conferida no log; não nova execução minha.

| Item | Prova disponível e conclusão |
|---|---|
| 1 | Porta/adaptador offline e ampla bateria HTTPS real. **Parcial**, diante do achado 1 e da abrangência real incompleta. |
| 2 | Cache, SW, prefetch e bfcache reais. Prerender, Early Hints e recarga humana pendentes. **Insuficiente para encerrar.** |
| 3 | Escopo/quadros reais; grafo normas_leg offline com conflitos. Prova útil, sujeita ao achado 1. |
| 4 | Seleção/persistência offline, incluindo ausência de marcação e dependentes. **Suficiente para o comportamento examinado.** |
| 5 | Filtro/correlação sintéticos e provas estruturais. **Suficiente no escopo desses testes.** |
| 6 | Varredura sintética publicada e cenário real; charset corrigido. Não supre inventário externo do item 7. |
| 7 | ACL e limpeza parciais; segunda conta e inventário externo ausentes. **Insuficiente.** |
| 8 | Registro/inventário/vigilância offline; Brave real; Chrome/Edge recusados por política. Extensões e matriz entre navegadores incompletas. **Insuficiente.** |
| 9 | Lista/parâmetros/sequência estáticos e comparação real; quatro repetições isoladas aprovadas. **Condicionado à nota de passividade.** |
| 10 | Porta única por inspeção, AST e integração. Não encontrei contorno pelos conectores/parsers. |
| 11 | Cortes finais offline de identidade, texto, história, juízo pendente e 30 dias. **Cobertura prejudicada pelo achado 5.** |
| 12 | Exportação/instalação offline. **Reprovado pelo achado 2.** |
| 13 | Fronteiras AST e execução registradas; terminal conservador. Falta monitoramento real do perfil pessoal. **Insuficiente.** |
| 14 | Indicação conjuntiva e preservação de tipos/motivos examinadas. Não encontrei disparo decorrente da indicação. |
| 15 | Modelo literal e variantes negativas offline. **Suficiente para a regra textual examinada.** |
| 16 | Parser CLI não equivale a instalação Windows. **Não demonstrado.** |

A inexistência de segunda conta é motivo aceitável para não executar **nesse notebook**, sem criar conta ou elevar privilégio. Ausência de gesto humano também justifica o skip da execução desassistida. Prerender desativado e ausência de `h2` explicam os outros skips. Nenhum desses motivos transforma requisito obrigatório em cumprido. O pacote `h2` pode pertencer somente ao ambiente de ensaio, sem virar dependência do produto.

A exclusão de `navegador_assistido` da CI deixa risco relevante de regressão do protocolo e da limpeza. **A especificação exige a prova, mas não determina que ela seja necessariamente um job de CI.** Um job Windows controlado é recomendável para os cenários automatizáveis; uma bateria externa rastreável ao commit também pode fornecer essa prova. Os gestos humanos continuam exigindo acompanhamento.

**Demais fronteiras e regressões**

- Não encontrei método CDP de navegação, injeção, alteração de cache/SW ou requisição. A lista fechada e os parâmetros são conferidos antes do envio.
- `aguardar_saida_navegador` compara exatamente o argumento do perfil; a enumeração não mata processos. `limpar_diretorio` exige filho direto com prefixo próprio e recusa link/junction na entrada. Não demonstrei remoção fora do perfil.
- A correção de charset fecha o caminho da Terra r1 nas variantes examinadas. Não demonstrei novo vazamento de valores de cabeçalhos/cookies para os recibos.
- Em `httputil.py`, `observar_tentativa` fica depois da tentativa e dentro do callback da guarda; não encontrei repetição de rede causada pela adição. Os testes focados do desfecho reclassificado passaram.
- `service.py` acrescenta indicação/proveniência; `contrato.py` mantém `CONTRATO_VERSAO`. Não encontrei alteração dos tipos fechados examinados.
- As regressões demonstradas fora da porta são a referência em `snapshot.py` e a contagem após a migração 018.
- A pendência 24 recebeu comando local confirmado que chama `NormasPortao.reabrir`, sem emitir rede. **Não reabri o home real.** O teste existente verifica o método; falta fortalecer a prova do comando completo.

**Limites da auditoria**

Não executei suíte completa, Ruff ou contrato MCP integral no HEAD; navegador real; instalação Windows; segunda conta; gestos humanos; monitoramento de arquivos do SO/perfil pessoal; nem sessão manual do titular, expressamente excluída. A reprodução do snapshot exercitou a mesclagem real em memória, sem executar o instalador público completo com blobs em disco. Não demonstrei `verified` indevido em consulta final.

**Propostas de notas formais para deliberação do titular**

1. **Manifesto de componente — §2.2(3)(c).**

   > Para componente com `location` 5 e caminho originalmente absoluto que, resolvido, esteja dentro da instalação do navegador lançado, a ausência de `manifest.json` permite usar o objeto `extensions.settings.<id>.manifest` das preferências do perfil dedicado. Exige-se objeto JSON válido. Erro de leitura ou manifesto inválido em disco não autoriza fallback. A alternativa não alcança extensão comum, componente externo, caminho relativo ou componente fora da instalação; `active_permissions` não substitui o manifesto.

   **Avaliação:** preserva o propósito e a premissa expressa de confiança no componente embutido. Não identifiquei ampliação para extensão externa pelo fallback implementado.

2. **Ordem do streaming — §2.5(2) e §3(1).**

   > O comando continua obrigatório no `requestWillBeSent`. Sua resposta não precisa preceder o primeiro `dataReceived`. Antes dela, só se admitem eventos sem `data`, com contadores e reservas imediatos; `bufferedData` deve corresponder exatamente à soma anterior de `dataLength`. Depois da resposta, cada bloco deve corresponder ao comprimento do próprio evento. Evento sem `data` só é admitido com `dataLength=0`, mantendo `encodedDataLength` nos controles. Erro do comando, término anterior à resposta, divergência ou limite excedido recusam, sem fallback. Permanecem os prazos e confrontos finais.

   **Avaliação:** preserva a obtenção exclusiva por streaming e evita a recusa indevida da ordem observada. Não encontrei caminho de admissão indevida causado por essa leitura. A identidade dos bytes continua dependente do navegador confiável; igualdade de comprimentos não prova o conteúdo independentemente dele.

3. **Passividade — §3(9).**

   > A comparação admite somente variações demonstradas em dois a quatro controles sem adaptador. Apenas posições de `q` sintaticamente válidas e variáveis em `Accept-Language`, no mesmo método, caminho e ocorrência, podem ser normalizadas. Todo o restante permanece literal. Variações de ordem e valores devem reproduzir alternativas efetivamente observadas nos controles, preservando multiplicidades. Os dados originais e cada desconto integram o diagnóstico.

   Essa terceira nota explicita a flexibilização do aceite de igualdade; não deve ficar sustentada apenas pelo registro do desenvolvedor.

**Veredito final: BLOQUEADOR**, pelos achados reproduzidos 1 e 2 e pelas provas obrigatórias ainda incompletas.