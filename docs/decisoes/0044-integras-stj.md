# 0044 — Íntegras do STJ

Estado: aceita para o parser; ligação ao acervo pendente (1.3.0).

## Contexto

O portal de dados abertos do STJ publica o pacote
`integras-de-decisoes-terminativas-e-acordaos-do-diario-da-justica` em pares diários:
`metadadosAAAAMMDD.json` e `textosAAAAMMDD.zip`, este com `<SeqDocumento>.txt` em UTF-8 e
quebras `<br>`. Amostra de 08/10/2026: 2.004 metadados, 37 textos no ZIP, 13 deles acórdãos.
Os metadados não trazem órgão julgador.

## Decisão

1. Recorte por vínculo, não por órgão: a íntegra só é gravada quando o `numeroRegistro`
   (12 dígitos) vincula a um único espelho já presente no acervo, que carrega o órgão do
   recorte. O órgão nunca é inferido pelo ministro.
2. Vários espelhos para o mesmo registro: `ambiguous`, sem escolha.
3. Inteiro teor por declaração da coleção oficial (0038), nunca por comprimento. O hash da
   prova é do texto bruto; a limpeza de `<br>` serve só à leitura e à busca.
4. Decisões monocráticas ficam fora nesta versão e são contadas.
6. Limites do ZIP: 5.000 entradas, 200 MB descompactados, 5 MB por entrada, razão 100;
   nome fora de `[0-9]+.txt` (fullmatch) recusa o recurso inteiro (cobre zip-slip); bytes
   contados na leitura, não no cabeçalho; entrada cifrada ou ilegível recusa o recurso.
7. A cobertura textual do ZIP é parcial; `texto_ausente_no_zip` é descarte esperado e não
   pode ser lido como falha da fonte.

## Ligação pendente (1.3.0)

Capturar ZIP e metadados pelo transporte comum (recibo com sha256), gravar
`decision_document(kind='inteiro_teor', capture_id=<zip>)` na decisão do espelho, janela
padrão de 90 dias com checkpoint por recurso (0039), atualizar `coverage` do conector e
FONTES.md, e só então novo snapshot, após auditoria independente.

## Limites conhecidos

- `recurso = "EDcl"` não revela a cadeia inteira; cadeias distintas compatíveis caem em
  `ambiguous`.
- A data de publicação não entra no vínculo: o espelho a traz em texto livre ("DJEN DATA:")
  e o acórdão pode ser republicado. Avaliar como desempate na ligação ao acervo.
- O texto do `.txt` não ? conferido contra os metadados (sem cabeçalho estruturado).
- Republicação com sha256 diferente deve ser tratada como conflito pelo chamador.
