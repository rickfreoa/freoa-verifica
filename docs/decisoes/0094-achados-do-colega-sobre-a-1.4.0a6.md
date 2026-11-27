# 0094 - Achados do colega sobre a 1.4.0a6: parser, citação e renovação

Status: implementação autorizada pelo titular em 27/11/2026 ("seria bom já corrigirmos também"; sequência: a 1.4.0a8
sai antes, estes achados na 1.4.0a9; implementar a partir do relatório, sem código do fork do colega). As regras
abaixo seguem a linha conservadora já fixada pelo titular na 0091 (r5 e r6): na dúvida, a ferramenta não confirma.

## Problema

O colega mediu o parser 1.2.4 e o `citation.py` da 1.4.0a6 contra as fixtures do repositório e relatou nove achados,
mais seis do instalador (os do instalador entraram na 0092). Reproduzidos no código da 1.4.0a8 antes de corrigir:

- **Confirmação indevida (`verified`).** Inciso escrito sem travessão ("II processar e julgar ...", também `II)` e
  `II.`) não é reconhecido como rótulo e vira continuação do inciso anterior; o texto do inciso II é confirmado no I,
  e a alínea seguinte vai para o inciso errado (achados 2, 6 e 9; 66 blocos assim na CF do Planalto, segundo o
  colega). Artigo de outro ato, inteiro dentro de um link em fonte órfã, vira artigo da obra (achado 7).
  "art. 5º da CF/88, § 2º", ", inciso II", ", II", "ou do ADCT?" confirmam o caput do art. 5º (achado 4), defeito que
  vale também para leis ("art. 5º da Lei 6.404/1976, § 2º").
- **Redação vigente errada.** Quando um `</font>` órfão fecha a fonte da página no meio do `<p>`, o lxml leva o fim do
  parágrafo para fora dele e a redação nova se perde: o dispositivo fica com a riscada e uma viva vazia (achado 1;
  18 provisões na Lei 6.404, entre elas arts. 39, 50, 78, 230, 283, 72 § 2º c, g, j e 256 II a). Nota editorial
  cortada pelo markup ("(Redação dada pela Emenda Constitucional no 40, de 2") fica dentro da redação (achado 8).
- **Data da Constituição.** "Constituição Federal de 31 de outubro de 1988" resolve a CF como exata: o dia e o mês
  eram descartados (achado 3).
- **Renovação.** `renovar_acervo` contava como renovada, e apagava `renovacao_pendente`, qualquer `ResolvedWork`
  devolvido por `_capture_work`, inclusive a mesma captura de antes (mesmos bytes), a captura anterior que a
  monotonia (0034) mantém e uma captura intermediária anterior ao sinal que abriu a pendência (achado 5).

## Decisão

1. **Marcas defensivas no parser (1.2.5).** Nenhuma cria caminho nem move texto; o dispositivo marcado passa a
   `unknown` em identidade, texto e tempo (issue de escopo `provision`, que alcança ancestrais e descendentes):
   - `ROTULO_SEM_SEPARADOR`: bloco sem rótulo reconhecido que começa por numeral romano válido seguido de espaço,
     `)` ou `.` e de texto, em `<p>` ou em fonte órfã. O bloco não é anexado ao dispositivo anterior; a marca vai
     para o dispositivo corrente. A negativa (`DISPOSITIVO_INEXISTENTE`) fica bloqueada em todo o artigo, porque o
     inciso existe na fonte. A regra é deliberadamente larga ("V. Exa.", "III Congresso" também marcam): o custo é
     não confirmar, nunca confirmar errado.
   - Fonte órfã cujo texto inteiro está em links para outro ato (arquivo do `href` diferente do da obra, ou qualquer
     arquivo quando a URL da obra não é conhecida) é fronteira (`DISPOSITIVO_FORA_DA_ARVORE`), não dispositivo.
     Âncora da própria obra (`#art2`, `l9999.htm#art2`) continua abrindo o artigo.
   - `REDACAO_VIVA_VAZIA`: redação vigente vazia depois de redação riscada, sem nota de revogação ou veto.
   - `NOTA_EDITORIAL_TRUNCADA`: redação vigente que termina em nota editorial aberta, não fechada e cortada no meio
     ("..., de 2", "(Vigência"). Nota completa a que só falta o `)` final (termina em ano de quatro dígitos) não marca:
     na Lei 11.076 seriam 29 provisões perdidas sem que nenhum texto normativo estivesse escondido.

   No acervo da 1.4.0a8 reconstruído: 66 `ROTULO_SEM_SEPARADOR` na CF (a contagem do colega) e 2 na Lei 13.043; na CF,
   os incisos IX a XV do art. 93 estavam sendo anexados ao inciso VIII-B.
2. **Citação.** Logo depois da norma citada (com o dispositivo antes dela), vocabulário de dispositivo (§,
   parágrafo, inc./inciso, al./alínea, item, numeral romano, número, `a)`) ou de alternativa (`ou`, `(ou`, também
   depois de vírgula) rebaixa a citação a `provavel` (`complemento_de_dispositivo_apos_a_norma`), para qualquer
   norma. `, caput` e prosa comum seguem `exata`. Constituição com dia e mês diferentes da promulgação (1988: 5 de
   outubro; tabela para 1824 a 1969) é `provavel` (`constituicao_data_divergente`).
3. **Renovação.** Só renova a captura canônica cuja data é instante válido (ISO com fuso) posterior à captura que a
   obra tinha e, havendo pendência, ao sinal que a abriu (`payload.em`; pendência antiga sem ela: a data do
   registro). Caso contrário a obra vai para `sem_renovacao` (`captura_canonica_nao_renovada` ou
   `captura_anterior_ao_sinal_da_pendencia`), a pendência fica e a obra vai para o fim da fila. Datas nunca são
   comparadas como texto. `sem_renovacao` não é falha da fonte: a execução fica `parcial`, sem falha real.
4. **Derivados.** Parser 1.2.5 e `DERIVED_VERSION` 7: o acervo é reconstruído e há snapshot novo.

## Auditoria Codex, rodada 1 (BLOQUEADOR) e correções

1. **Inciso fora de `<p>` ou depois de `<br>`.** `<div>`/`<span>` com rótulo de dispositivo (com ou sem separador)
   fora de qualquer `<p>`, e linha depois de `<br>` que abre dispositivo no mesmo bloco, também marcam o dispositivo
   corrente. Para não marcar diagramação: a linha anterior ao `<br>` tem de fechar dispositivo (`;`, `:` ou `.`),
   rótulo sozinho sem corpo não conta e redação riscada fora de `<p>` é ignorada. Nas seis fixtures do Planalto do
   repositório, nenhuma marca nova além das 18 de redação vazia da Lei 6.404.
2. **`II:`** (também `II;` e `II,`) entra no padrão do rótulo sem separador; a negativa no artigo fica bloqueada.
3. **Link de outro ato com arquivo de mesmo nome.** A comparação é do documento inteiro (host e caminho, resolvido
   contra a URL da obra, sem esquema, consulta nem fragmento). Sem URL da obra, só o fragmento puro (`#art2`) é a
   própria obra.
4. **Complemento com conector.** "e (seu/o/...)", ponto e vírgula e travessão antes do complemento; `item` no
   singular; vocabulário sem distinção de caixa (numeral romano continua só em maiúsculas).
5. **Sinal gravado durante a captura.** A pendência só é removida se ainda é o registro avaliado (remoção
   condicional por payload e data); se mudou, a captura é reavaliada contra o sinal novo.
6. **Pendência sem instante legível** (sem `em`, data do registro sem fuso) não é tratada como livre: nenhuma captura
   a supera (`sinal_da_pendencia_sem_data`).

## O que fica de fora

- **Causa do achado 1.** Recuperar o texto que o `</font>` órfão tira do `<p>` (o colega sugere) devolveria as 18
  provisões da Lei 6.404 à verificação; hoje elas saem `unknown`. Fica para decisão própria, com teste nas fixtures.
- **Reconhecer o inciso sem travessão** quando o numeral é o seguinte ao corrente (sugestão do colega) criaria
  caminhos; a marca defensiva vem antes.
- A fixture da CF do Planalto usada pelo colega não está no repositório; as medições da CF são dele.

## Testes

`tests/test_0094_parser.py`, `tests/test_0094_citacao.py`, `tests/test_0094_renovacao.py`. O teste antigo
`test_pendente_renovado_apaga_marca` afirmava o defeito (a mesma captura de T0 contava como renovada) e passou a usar
captura posterior ao sinal.
