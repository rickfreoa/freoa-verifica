# Comparativo FREOA Verifica 1.2.0 × JusRatio (19/10/2026)

## Método

- **Conjunto-ouro** (`gold.jsonl`): 44 casos em sete estratos (dispositivos de lei federal; normas CVM/CMN;
  súmulas; decisões do STJ por número e por tema; TJDFT por número CNJ e por tema; TCU e Colegiado da CVM;
  inexistentes plantados). Montado por um agente que não leu o código, com a resposta fixada pela fonte
  oficial. Os seis casos do TJDFT e o número com dígito verificador inválido foram confirmados depois na API
  oficial do tribunal. F5 e F6 foram excluídos: os documentos escolhidos não são decisões do Colegiado
  (memorando de redistribuição e voto divergente). Restam 42 casos pontuados.
- **Execução**: a mesma consulta, sem alteração, nos dois sistemas. JusRatio: `buscar_legislacao` para
  dispositivos e normas, `pesquisar_documentos` para o resto, cinco primeiros resultados (`jusratio_raw.jsonl`,
  transcrição manual pelo agente coletor, com ementas truncadas em 200 caracteres). FREOA: snapshot instalado em
  diretório novo, com consulta às fontes ao vivo onde o produto as consulta (`freoa_raw.jsonl`, gerado por
  `scripts/comparativo_ouro.py`).
- **Critérios** (em `pontuar.py`, iguais para os dois): em caso positivo, acerto é entregar o item pedido, e
  abstenção não conta; em caso negativo, acerto é não apresentar outro item como o pedido; em caso temático,
  acerto é ao menos um resultado pertinente entre os cinco primeiros, e a precisão é a fração de resultados
  pertinentes.
- **Juiz cego** (`juiz_entrada.json`, `juiz_veredito.json`, `juiz_chave.json`): agente que recebeu só a
  consulta e as ementas (200 caracteres, sem identificação e em ordem embaralhada) e julgou sim/parcial/não.
- **"No acervo FREOA"**: o item existe e está no acervo instalado ou numa fonte que o FREOA consulta ao vivo.

## Resultado

Ver `placar.md` (gerado por `python pontuar.py`). Resumo da rodada final, sobre o snapshot 1.2.0 distribuído
(sha256 `926a6eb7…`) instalado em diretório novo:

| | FREOA 1.2.0 | JusRatio |
|---|---|---|
| Casos dentro do acervo do FREOA (35) | 34 | 35 |
| Não temáticos: dispositivos, normas, súmulas, números de processo (28) | 28 | 28 |
| Todos os casos, inclusive fora do acervo do FREOA (42) | 34 | 38 |
| Resultados temáticos úteis, juiz cego (pertinente ou parcial, 35) | 33 | 33 |
| Resultados temáticos estritamente pertinentes (35) | 21 | 25 |
| Item apresentado como se fosse outro | 0 | 0 |

A rodada temática final só foi julgada depois de três ajustes de ranking motivados pelas rodadas anteriores
(IDF na complementação, ementa antes de termos espalhados no inteiro teor, consulta ao vivo do TJDFT com
locuções entre aspas). Cada rodada teve juiz cego novo; os vereditos anteriores ficam no histórico do git.
Como a busca ao vivo do TJDFT indexa candidatos no acervo local, a ordem dos casos influencia resultados
posteriores (D8 passou a incluir um acórdão do TJDFT capturado na E5): é o comportamento real do produto.

## Leitura

O comparativo serviu de teste, não de vitrine. A primeira rodada expôs defeitos de reconhecimento: REsp
presentes no acervo não eram achados quando citados com UF; súmulas não casavam por causa do acento; número
CNJ inexistente devolvia outros processos; súmula citada sozinha saía `not_found`. Esses defeitos foram
corrigidos (decisão 0043) e auditados antes da rodada final.

Limites que permanecem: o acervo do FREOA é um recorte (STJ de quatro órgãos de 06/2024 a 08/2026, TCU de
2026, 40 decisões da CVM, semente temática do TJDFT), e a busca temática é lexical. Nos casos temáticos, parte
da diferença vem de decisões pertinentes que não estão no acervo (por exemplo, REsp 2.203.772 e REsp
2.002.911). A amostra é pequena (42 casos) e não sustenta inferência estatística; "zero confirmação indevida
em 42 casos" não significa risco zero.
