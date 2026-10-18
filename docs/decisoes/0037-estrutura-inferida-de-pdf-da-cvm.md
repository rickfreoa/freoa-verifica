# 0037 — Estrutura inferida de PDF da CVM

Data: 18/10/2026. Versão: 1.1.0 (`cvm-pdf-2`). Revisada em onze rodadas de auditoria.

## Problema

Atos da CVM disponíveis só em PDF não tinham dispositivos: toda citação de artigo respondia `DOCUMENTO_SEM_ESTRUTURA`.

## Decisão

1. Os dispositivos são inferidos pelos rótulos que o parser HTML já reconhece (Art., §, Parágrafo único, incisos, alíneas, itens), sobre parágrafos montados das linhas do pypdf. Issue informativa `ESTRUTURA_INFERIDA_PDF`.
2. Cabeçalho e rodapé saem por geometria: só o bloco contíguo a partir da borda (faixa superior acima de 75% da altura, inferior abaixo de 12%), formado por linhas que se repetem com o mesmo texto e na mesma altura em ao menos metade das páginas (mínimo três) e têm forma de rótulo (não são dispositivo, título ou nota; estão em caixa alta ou não terminam em ponto ou ponto e vírgula), ou pelo número da própria página. Sem coordenadas, nada sai. O que saiu fica registrado na issue informativa `MARGEM_DESCARTADA`.
3. O bloco é mantido quando separa um parágrafo aberto (sem pontuação final, nem "; e"/"; ou") de um novo dispositivo ou do fim do documento: nesse caso não se distingue de texto normativo.
4. Notas da CVM ("• Inciso VI com redação dada pela Resolução CVM nº 187, de ...", "incluído", "revogado") viram a anotação do dispositivo que as antecede, com a mesma semântica do Planalto: redação anterior superada, redação vigente anotada, dispositivo revogado.
5. O texto que outra norma "passa a vigorar com a seguinte redação:" até "(N.R.)", em até 60 parágrafos, é citação (blockquote), não dispositivo desta norma. Sem fecho, nada é tratado como citação.
6. Todo bloco descartado que contenha texto (e não só o número da própria página) marca o dispositivo que o antecede com `MARGEM_ADJACENTE` (bloqueio por dispositivo, que alcança seus filhos): o verificador responde `unknown/MARGEM_ADJACENTE` para qualquer confronto textual, nem `verified` nem `divergent`. Vale na fronteira limpa e no meio do parágrafo. Na Resolução CVM 175: 67 de 801 dispositivos.
7. Imagem desenhada em qualquer posição da página pode conter texto que o pypdf não extrai: as linhas mantidas imediatamente acima e abaixo dela (ou, no alto da página, a última linha da página anterior) recebem a mesma marca `MARGEM_ADJACENTE`. Linha na mesma altura da imagem também é marcada. Não há exceção para logotipo: nenhuma posição prova que a imagem não contém texto.
8. Duplicidades remanescentes (redações antigas sem marca de rasura no PDF) ficam `DUPLICATE_CURRENT`, portanto ambíguas e sem `verified`.

## Limite residual declarado

Bloco formado apenas pelo número da própria página (na faixa da margem, sozinho na linha, igual ao índice da página) sai sem marcar o dispositivo anterior. Um número normativo idêntico ao da página, isolado nessa posição, seria perdido; não há caso real conhecido.
