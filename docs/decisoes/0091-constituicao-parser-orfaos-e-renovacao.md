# 0091 - Constituição pelo MCP: dispositivo fora de `<p>`, citação por ano, artigo integral e renovação do acervo

24/11/2026. Proposta do supervisor (Opus) para o titular, a partir de relato de uso externo (MCP instalado de
`main`/1.4.0a5 em servidor de terceiro, consultado pelo Claude Desktop). **Pendente de aprovação do titular e de
auditoria Codex.** Altera parser (1.2.4), derivados (versão 6), a conferência legada da 0065 e o contrato de
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
4. **Reconfirmação (emenda à 0034, sem alterar a monotonia).** Em `obter_dispositivo`, captura mais nova da mesma
   obra e da mesma fonte, rebaixada ou candidata, reconfirma o dispositivo pedido se tiver o mesmo caminho, a mesma
   redação vigente (espaços normalizados), sem ambiguidade e com recibo autenticado. A data de frescor passa a ser a
   dela (`reconfirmacao`); o texto continua o da captura canônica. Sem reconfirmação, a resposta declara
   `capturas_recentes_nao_canonicas` (motivo e caminhos perdidos). Fonte distinta não reconfirma (0085: rota
   `normas_leg` não qualificada; NPL derivado). `verificar_citacao` fica inalterado nesta proposta.
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
