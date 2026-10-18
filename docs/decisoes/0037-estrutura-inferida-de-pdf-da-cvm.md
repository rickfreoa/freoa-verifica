# 0037 — Estrutura inferida de PDF da CVM

Data: 18/10/2026. Versão: 1.1.0 (`cvm-pdf-2`). Revisada em quatro rodadas de auditoria.

## Problema

Atos da CVM disponíveis só em PDF não tinham dispositivos: toda citação de artigo respondia `DOCUMENTO_SEM_ESTRUTURA`.

## Decisão

1. Os dispositivos são inferidos pelos rótulos que o parser HTML já reconhece (Art., §, Parágrafo único, incisos, alíneas, itens), sobre parágrafos montados das linhas do pypdf. Issue informativa `ESTRUTURA_INFERIDA_PDF`.
2. Cabeçalho e rodapé saem por geometria: só o bloco contíguo a partir da borda (faixa superior acima de 75% da altura, inferior abaixo de 12%), formado por linhas que se repetem com o mesmo texto e na mesma altura em ao menos metade das páginas (mínimo três), ou pelo número da própria página. Sem coordenadas, nada sai.
3. O bloco é mantido quando separa um parágrafo aberto (sem pontuação final, nem "; e"/"; ou") de um novo dispositivo ou do fim do documento: nesse caso não se distingue de texto normativo.
4. Notas da CVM ("• Inciso VI com redação dada pela Resolução CVM nº 187, de ...", "incluído", "revogado") viram a anotação do dispositivo que as antecede, com a mesma semântica do Planalto: redação anterior superada, redação vigente anotada, dispositivo revogado.
5. O texto que outra norma "passa a vigorar com a seguinte redação:" até "(N.R.)", em até 60 parágrafos, é citação (blockquote), não dispositivo desta norma. Sem fecho, nada é tratado como citação.
6. Duplicidades remanescentes (redações antigas sem marca de rasura no PDF) ficam `DUPLICATE_CURRENT`, portanto ambíguas e sem `verified`.

## Limite residual declarado

Uma linha de corpo idêntica, na mesma altura, na borda de metade ou mais das páginas e entre duas partes do mesmo parágrafo seria descartada como cabeçalho. Não há caso real conhecido; o PDF sem rasuras continua sujeito a `PDF_SEM_RASURAS` e a conferência no original.
