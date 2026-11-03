# FREOA Verifica: emenda ao plano 1.4.0 (legislação primeiro)

Autor: Ricardo Peres Freoa | Stocche Forbes Advogados. Data: 2026-11-03. Debate: debate-20261103-verifica-freoa, ACEITO_UNANIMIDADE na rodada 3 (Codex, Antigravity, Cursor em modo ask com garantia reduzida).

Nota de execução (supervisor, 03/11/2026): a numeração das pré-releases foi ajustada pela decisão 0075, item 6 (IL.0 em pré-release própria, 1.4.0a2; IL qualificado em 1.4.0a3; STJ em 1.4.0a4). O conteúdo e os gates não mudam.

## 1. Tese

A legislação passa à frente da jurisprudência. O próximo pré-release (1.4.0a2) é o incremento de legislação (IL), aprovado por uma Porta L por capacidade; o STJ vem em seguida (1.4.0a3), em sprint separado; a 1.4.0 estável fica com IL + STJ; os demais tribunais seguem em 1.5.x, um por versão menor. A redução de escopo é recomendação técnica e depende do titular.

## 2. Base observada (leitura Git, 2026-11-03)

- `main` remoto em 9725b98 (29/10/2026), sem commit posterior; tags até v1.4.0a1; instalação local 1.4.0a1.
- Manifesto de aceite: I1 concluído com I1.2 (íntegras do STJ) adiado e I1.5 e S0 reduzidos; I2 aberto, com I2.2, I2.3 e I2.7 transferidos ao I3; I3 e I4 pendentes; a cascata do Planalto é o I3.6.
- Planalto recusa o UA identificado (decisão 0048); acervo de legislação congelado; história só pela rasura; data do ato alterador não é início de vigência (decisão 0002).
- Contrato público versão 1, com evolução aditiva e ciclo `deprecated`. Estados de verificação: verified, divergent, not_found, ambiguous, unavailable, unknown, not_assessed; buscas com falha parcial devolvem `parcial` com `fontes_indisponiveis`.
- Já existem `buscar_normas_cvm` e `buscar_normas_bcb` (normas CVM e CMN/BCB, com situação), fora do escopo do IL.

## 3. Decisões do titular (03/11/2026)

1. Redistribuição: recuperação e verificação mecânica de fonte pública no Verifica; juízo jurídico, documentos do cliente e degradação no FREOA.
2. Antecipar a legislação.
3. Substituição do Jusratio paulatina: legislação primeiro, depois cada tribunal que atingir a completude; Jusratio nas lacunas.
4. Verifica implementado no projeto próprio, sem gate humano, com commit, integração, publicação e distribuição.

## 4. Sequência

| Versão | Conteúdo | Gate |
|---|---|---|
| 1.4.0a2 | IL (seção 5); a fronteira com o FREOA (IL.0) pode sair antes, em pré-release próprio | Porta L por capacidade |
| 1.4.0a3 | STJ: íntegras (ex-I2.6), paridade mínima (ex-I2.1/I2.4), avaliação reservada do STJ | Porta A do STJ |
| 1.4.0 | IL qualificado + STJ | critério de conclusão da seção 5 do plano 1.4 |
| 1.5.x | STF acórdãos e demais tribunais, um por versão menor, na ordem da Porta A | Porta A de cada tribunal |
| condicional | busca híbrida (I4.1–I4.2) | só se a lexical reprovar por recall em algum tribunal |

O IL começa sem decisão adicional do titular: a antecipação da legislação já foi decidida. A redução da 1.4.0 estável (demais tribunais em 1.5.x) só precisa de decisão antes da tag 1.4.0. Mantêm-se D1 a D6 do plano 1.4, o critério de conclusão em 8 etapas e a tabela de delegação. Uma trilha por vez em `service.py`, `transport.py` e contrato: por isso IL e STJ não correm em paralelo.

## 5. Incremento de legislação (IL)

- **IL.0 Fronteira com o FREOA, primeiro item do IL.** As demandas da seção 8, com os nomes dos campos publicados antes de tudo; se o IL demorar, saem em pré-release próprio. O FREOA adota esses nomes e fixa a versão mínima nessa release.
- **IL.1 Conjuntos.** Desenvolvimento e reserva congelados por hash antes da implementação; reserva sob guarda no regime do D6. Mínimo de 40 casos, com pelo menos 8 por capacidade (seção 6). Cada caso traz gabarito documentado: texto esperado, fonte oficial e fundamento documental da data, ou, nos casos sem versão oficial na data, o gabarito "não verificado para D, com motivo". Casos derivados de uma mesma alteração não contam como independentes. Cobertura: dispositivo alto de norma grande (LSA 156, 254-A, 289; CC 421 e 1.031; CTN 185), redação anterior em data D com e sem rasura, revogação, MP reeditada e convertida, anexo, remissão, data anterior à publicação. O acervo Planalto congelado só serve de referência para o que documenta; alteração posterior ao corte exige gabarito em evidência oficial própria.
- **IL.2 Adaptadores.** Senado Dados Abertos/LexML (identificação, URN, atos alteradores), normas.leg.br (texto por dispositivo), Câmara e INLABS/DOU (texto publicado), atrás do `transport` congelado. Cada resultado identifica a origem efetiva; endereços distintos não são presumidos fontes independentes. O Planalto fica como acervo legado, não como fonte viva. O br-eli-mcp serve de referência de engenharia, não de dependência.
- **IL.3 Matriz de capacidades** por rota (identificação, texto publicado, consolidado vigente, redação em data D, anexos, remissões, vigência declarada), declarada só depois do teste de equivalência.
- **IL.4 Tipagem em três eixos**, campos aditivos e separados: `source_kind` (espécie: lei, lei complementar, decreto, MP, resolução CVM, resolução CMN, parecer de orientação…, ou `nao_identificado`); `natureza_texto` (publicação original, consolidação oficial, reconstrução mecânica); `procedencia` (captura direta, snapshot, cadeia de alterações, sessão assistida). Esfera do ato (federal, estadual) como metadado. Nenhum eixo afirma vigência.
- **IL.5 Defasagem.** Todo dispositivo traz `captured_at`; no acervo congelado, também `acervo_ate`.
- **Risco de calendário, não critério de merge:** pedido formal à Presidência para liberar o UA.

### Redação em data D

1. Versão oficial identificada para a data: pode dar `verified` para D.
2. Rasura na compilada: só sustenta resposta para D com fundamento documental do período. Com `data`, o estado refere-se sempre a D: sem esse fundamento, o estado é não verificado, com motivo `sem_fundamento_do_periodo`, e a coincidência textual com a redação histórica vai em campo aditivo (`correspondencia_textual`), nunca no estado. A resposta para D traz `fundamento_temporal` quando houver.
3. Sem versão oficial da data: devolver a última versão oficial anterior, com sua data, e a cadeia ordenada de atos alteradores (ato, publicação, dispositivo atingido, ação), com o texto de cada ato; estado não verificado com motivo `sem_versao_oficial_na_data`.

A versão atual nunca preenche lacuna histórica. Vigência: só a cláusula declarada no ato, tipada `vigencia_declarada`; vacatio, LINDB e transição são do FREOA. A escolha entre `ambiguous`, `unknown` e `unavailable` segue o contrato (alternativas; determinação insuficiente; falha de acesso).

**Verificar no início do IL:** se `verificar_citacao` com `data` hoje atribui a data a partir da rasura sem fundamento do período. Se atribuir, é estado falso, corrigido por decisão formal (regra 3 do contrato).

**Fora do IL:** reconstrução mecânica (admitida depois só como `reconstrucao_mecanica`, estágio `experimental`, nunca `verified` para D, inconclusiva diante de renumeração, alterações sobrepostas, veto ou comando não processável) e comparação estrutural determinística entre duas redações oficiais (depois da Porta L, rotulada "comparação textual, não conclusão jurídica").

## 6. Porta L

Aprovação independente por capacidade, medida na reserva (o conjunto de desenvolvimento só orienta ajustes). Denominador de cada capacidade: casos dessa capacidade com gabarito documental. `unavailable` nunca entra no numerador. Caso cujo gabarito é "não verificado para D, com motivo" conta como acerto quando assim devolvido. Matriz de casos, denominadores e pisos congelados antes da implementação. Os valores são escolhas de engenharia, não exigências demonstradas.

| Capacidade | Piso |
|---|---|
| todas | confirmação indevida 0 no conjunto avaliado (eliminatório) |
| (a) texto publicado | acerto ≥ 0,95 |
| (b) texto consolidado vigente | acerto ≥ 0,95; sem truncamento em 100% dos casos de norma grande |
| (c) redação em data D | acerto ≥ 0,80 (abstenção sistemática não aprova); 100% dos casos sem fundamento da data devolvidos como não verificados para D, com motivo |
| (d) anexos | acerto ≥ 0,90 |
| (e) remissões | acerto ≥ 0,90 |
| todas | mutantes rejeitados (data trocada, um caractere alterado, dispositivo renumerado); p95 ≤ 5 s local (acervo ou snapshot, sem rede) e ≤ 20 s remoto (federação ao vivo), sobre o mesmo n da reserva |

Rótulos distintos em `listar_fontes`, no manifesto e na política do FREOA: "Porta L aprovada em (capacidades)", "STJ qualificado no escopo 1.4.0" e "Porta A por tribunal". Número de versão não é rótulo de substituição.

## 7. Governança

A autorização sem gate cobre o ciclo de software (commit, merge, tag, release, PyPI, snapshot, instalação) e a apuração técnica das portas no regime do D6.

Exige decisão do titular: desligamento do Jusratio por domínio ou tribunal; mudança de reserva ou de pisos depois de vistos os resultados, ou relaxamento de piso; `CONTRATO_VERSAO` "2"; alteração da invariante sem modelo generativo; rotulagem externa de "substituição"; remoção de campo consumido pelo FREOA fora do ciclo `deprecated`. O Verifica não escreve no repositório do FREOA.

Coordenação: um integrador por repositório; parecer invalidado por mudança material posterior; demandas do FREOA chegam como requisitos públicos reproduzíveis (entrada pública, capacidade, resposta esperada, teste negativo), sem minuta, nome, tese ou fato de cliente; mudança no arquivo de contrato do consumidor exige auditoria.

Estagnação ou reprovação da Porta L: D5 (reduzir escopo às capacidades aprovadas ou adiar, com registro); diagnóstico ao titular, que decide entre manter o Jusratio no domínio, aceitar capacidade parcial rotulada ou outra rota.

Dois riscos, sem hierarquia demonstrada: entrega insuficiente por escopo excessivo; publicação de resultado incorreto apesar da esteira. Para o segundo: retirada ou correção da versão dentro da autonomia do Verifica, aviso registrado, preservação das evidências; do lado do FREOA, suspensão da rota (plano da v6.20, seção 6).

## 8. Fronteira com o FREOA (demandas aditivas)

1. `tests/contrato/consumidores/freoa.json` com os campos e estados que o FREOA consome; a suíte falha se uma mudança os remover ou alterar fora do ciclo `deprecated`. É o único controle que roda antes do merge do lado que muda.
2. Registro local confiável da operação de verificação (ferramenta, parâmetros, estado, `capture_id`, hashes, fundamento temporal), como ferramenta aditiva, e captura persistida recuperável por `capture_id` sem rede. Para fonte viva, os dois são necessários; reexecução determinística só basta para acervo local.
3. `captured_at`, `acervo_ate`, `fundamento_temporal`, `correspondencia_textual` e os três eixos de tipagem (IL.4, IL.5).
4. Bloco aditivo de qualificação em `listar_fontes` (porta, capacidade ou tribunal, estado, versão, referência ao manifesto). Informa a qualificação; não liga nem desliga rota no FREOA.
5. Aviso de incidente em ponto público nomeado: campo aditivo `avisos_incidente` em `listar_fontes` e nota na release (retirada ou correção), lidos pelo preflight do FREOA.

## 9. Decisões do titular pendentes

Nenhuma delas condiciona o início do IL. Os pisos congelam como escolha de engenharia; ajustá-los depois é a exceção da seção 7.

1. Aprovar a redução da 1.4.0 estável (IL + STJ; demais tribunais em 1.5.x), antes da tag 1.4.0.
2. Se quiser, ajustar os pisos da Porta L antes do congelamento; depois dele, só por decisão formal.
3. Desligar o Jusratio para legislação, por capacidade, depois da Porta L.
4. Questão aberta: expor o modo HTTP do Verifica a Chat e Android (hospedagem, autenticação, e nenhum texto de cliente por esse caminho).

## 10. Emendas posteriores ao debate

O Fable (família Claude, contexto isolado) fez revisão estreita de sanidade dos dois planos: "SANO COM CORREÇÕES", 12 achados, nenhum bloqueante. Incorporei, sem nova rodada com os debatedores: estado com `data` sempre referido a D, com a coincidência textual em campo aditivo (achado 1); fronteira com o FREOA como primeiro item do IL e nomes publicados antes (3); IL sem condição de início pelo titular (4); pisos medidos na reserva, `unavailable` fora do numerador, "local" e "remoto" definidos (5); registro da operação e captura persistida, sem alternativa, para fonte viva (6); estados e ferramentas CVM/BCB na base (8, 12); `procedencia` nomeado (12); aviso de incidente em ponto público (11).
