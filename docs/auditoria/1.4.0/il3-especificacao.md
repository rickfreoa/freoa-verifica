# IL.3: especificação (executor da Porta L, remissões, matriz de capacidades por rota)

Autor: supervisor (Opus), 06/11/2026, sob a emenda IL (seções 5 a 7), a matriz IL.1 (`il1-matriz-porta-l.md`, congelada) e as decisões 0075 e 0077. Base: `main` em `3cbb14c` (merge do PR #36). Nada aqui altera matriz, pisos, denominadores, reserva ou mutantes congelados; qualquer divergência entre esta especificação e a matriz IL.1 resolve-se a favor da matriz.

## 0. Sequência e fronteira

O IL.3 corre em três trilhas, nesta ordem, uma por PR:

| Trilha | Conteúdo | Rede |
|---|---|---|
| IL.3-a | executor `scripts/porta_l.py`; campo `remissoes[]` (capacidade e); matriz de capacidades por rota como dado, com estado `nao_apurada` | nenhuma |
| IL.3-b | ativação ao vivo da rota Câmara (decisão própria, termos de uso, Crawl-delay), captura dos documentos que os conjuntos exigem e snapshot local | só pelo instrumento, depois da decisão |
| IL.3-c | apuração no desenvolvimento (teste de equivalência por rota); depois, apuração na reserva pelo guardião (D6); declaração da matriz e do bloco de qualificação | nenhuma no modo local |

A matriz por rota só é declarada (estado diferente de `nao_apurada`) depois da apuração (emenda, IL.3). Extração bem-sucedida não declara capacidade.

## IL.3-a

### A1. Executor

`scripts/porta_l.py --conjunto <jsonl> --mutantes <jsonl> --home <home> --modo local|remoto --saida <relatorio.json>`, exatamente os predicados das seções 1 a 4 da matriz IL.1, sem rede própria: chama a fachada pública Python (`obter_dispositivo`, `verificar_citacao`, `obter_evidencia`), nunca funções internas. Requisitos:

1. Comparação textual única da seção 7 da matriz, implementada uma vez e partilhada com o validador (`scripts/porta_l/validar_gabaritos_porta_l.py`) por importação, sem cópia; se o validador congelado não puder ser alterado sem mudar seu hash, o executor importa a função dele, e o teste prova a identidade.
2. Denominador por unidade de independência (seção 2): uma unidade por evento, caso de menor `id` lexicográfico; os demais só contam para confirmação indevida e mutantes. `unavailable`, `indisponivel`, `parcial` no denominador, nunca no numerador.
3. Confirmação indevida pelos quatro itens da seção 2, em todos os casos e mutantes; qualquer ocorrência reprova todas as capacidades (eliminatório).
4. (c): os três tipos da seção 1.1, com conferência do `fundamento_temporal` (tipo, `capture_id` recuperável, `sha256`, data ≤ D), da cadeia contra `gabarito.cadeia` e das duas condições adicionais (≥ 40% `verificado_para_D` na reserva; 100% dos sem fundamento devolvidos como não verificados com motivo).
5. Mutantes da seção 3, pela chamada declarada no próprio mutante.
6. p95 da seção 4: uma passada de aquecimento descartada, três medidas, posto mais próximo; modo local com rede bloqueada no processo (o executor falha fechado se detectar tentativa de rede).
7. Relatório por capacidade: denominador, acertos, confirmações indevidas, mutantes rejeitados/total, p95, aprovado/reprovado por piso, e a lista de casos com resultado e motivo. Modo `--somente-tabela` emite só a tabela aprovado/reprovado (uso do guardião na reserva, D6).
8. O executor não lê a reserva por caminho fixo; recebe arquivos por argumento e confere o hash contra `il1-congelamento.md` antes de rodar, recusando arquivo divergente.

Regressão: oráculo independente da implementação para cada predicado (casos sintéticos positivos e negativos por linha das tabelas 1, 1.1, 2 e 3); mutante do executor que aceite `parcial` no numerador, que conte duas unidades do mesmo evento, que aceite `fundamento_temporal` sem `capture_id` recuperável ou que normalize caixa deve falhar.

### A2. Remissões (capacidade e)

`obter_dispositivo` passa a devolver `remissoes[]`: `{texto, alvo: {obra, caminho}, resolvida: bool}`, campo aditivo (contrato aditivo, `tests/contrato/consumidores/freoa.json` intacto). Regras:

1. Reconhecer remissão expressa com obra explícita ou implícita na própria obra ("art. 4º desta Lei"), no caminho mais profundo que o texto der.
2. `resolvida: true` só quando a obra é identificada sem ambiguidade e o caminho existe no documento da obra alvo capturado pela rota; caso contrário `resolvida: false`, com o texto preservado. Remissão anafórica ou genérica ("na forma da lei", "do artigo anterior") nunca é resolvida; as atuais `referencias_nao_resolvidas` continuam.
3. Nenhum alvo excedente: falso positivo é confirmação indevida (seção 2, iii). Na dúvida, `resolvida: false`.
4. Notas editoriais não são remissões.

Regressão: remissão a outra lei, à própria lei, a parágrafo e inciso, lista ("arts. 5º a 8º"), remissão em nota (não conta), alvo inexistente, obra ambígua; mutante que resolva por proximidade textual deve falhar.

### A3. Matriz por rota como dado

Estrutura em `freoa_verifica/data/qualificacao.json` (ou arquivo irmão, aditivo), por rota efetiva (fonte + perfil: `camara_atualizado`, `camara_original`, acervo Planalto etc.) e por capacidade (a)–(e) e as transversais (identificação, remissões, vigência declarada), com estado `nao_apurada` | `aprovada` | `reprovada` | `nao_aplicavel`, referência ao relatório e à versão. Nesta trilha, tudo `nao_apurada`. Exposta no bloco `qualificacao` de `listar_fontes`, com os rótulos da emenda, seção 6. Teste impede estado diferente de `nao_apurada` sem relatório de apuração referenciado por hash.

## IL.3-b (depende de decisão 0078)

Ativação ao vivo da Câmara: leitura dos termos de uso e da política de dados da Câmara; robots e Crawl-delay respeitados no instrumento; mesmos limites da 0077 (padrão estrito, `max_redirects=0`, sem query de conteúdo); captura apenas dos documentos que os conjuntos de desenvolvimento e reserva exigem, pelo instrumento; snapshot local para o modo local. O guardião captura os documentos da reserva sem expor ao supervisor quais são (D6). Barreira = registrar e parar.

## IL.3-c

Apuração no desenvolvimento por rota (o teste de equivalência), relatório no repositório; correções por classe, D5; depois, apuração na reserva pelo guardião, tabela ao supervisor e relatório integral ao titular. Só então a matriz e o bloco de qualificação recebem estado. Capacidade reprovada: D5 (reduzir às aprovadas ou adiar) e diagnóstico ao titular.

## Projeção franca

- (c) depende de versão oficial datada; com a Câmara (atualizado sem rasura) e sem Senado/DOU, a maior parte dos casos `verificado_para_D` tende a não sair; risco alto de reprovação, já registrado.
- (d) depende do extrator/renderizador de PDF validado (pendência 4 do IL.2-c); sem ele, reprovação.
- (a) depende de publicação original do ato que deu a primeira redação, inclusive dos alteradores; cobertura da cadeia incompleta.
- (b) e (e) são as mais prováveis de aprovar.
