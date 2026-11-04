PARECER: COM BLOQUEADOR

A r2 resolve parte substancial do parecer anterior, mas permanecem **quatro casos reprovados**: L-a-005, L-a-009, L-c-011 e L-d-001. Dos **124 mutantes**, **dois estão reprovados por identidade documental incorreta do destino**. Retirados os quatro casos e seus sete mutantes, restam **52 casos e 117 mutantes**, com atendimento dos pisos estruturais de todas as capacidades.

Revisão somente em leitura, com `pypdf 6.21.4` do venv indicado. Não acessei a reserva nem o código do verificador. Não executei o validador: conferi sua saída fornecida e os respectivos hashes.

**Estado documental e comparação com r1**

Os hashes dos quatro insumos conferem com `relatorio.md` e `saida_validador.txt` e permaneceram iguais ao término:

| Arquivo | SHA-256 |
|---|---|
| desenvolvimento.jsonl | `56e30b08742978983601010eda08e30bb762f11f161547448a448365577c606d` |
| mutantes.jsonl | `f6254ac70783330f0c01033365da79e208e82c9369ded59fbcef803838a28e06` |
| cobertura.json | `db0c7eaa15d5a74a2b4b0cf56c6e904512dd8faaf2cb3c55ad56b87deda488cf` |
| fontes.csv | `e18389fda7b8d8fa43fca26ef6942eba020b7bc560e54bdc66bd71fa936bd38e` |

As **39 evidências** conferem com seus nomes SHA-256 e com os tamanhos registrados em `fontes.csv`.

A comparação de linhas utilizou `_tmp/desenvolvimento_r1.jsonl`, cujo SHA-256 é `06b9a9c643245ee9775603fe24f725aeee8bb045fc47e536ca694d4d4408c38a`, coincidente com o relatório r1 preservado. Encontrados **34 casos idênticos e 22 alterados ou novos**. A autenticação dessa linha de base limita-se à cópia preservada e ao relatório que a acompanha.

Na tabela seguinte, o hash identifica os primeiros 16 caracteres do SHA-256 da linha JSON, sem terminador. “Igual” significa igualdade integral com essa linha de base. Os casos alterados receberam revisão aprofundada; os demais, comparação de hash e amostragem de mérito. Todos os mutantes foram examinados individualmente.

**Tabela de todos os casos**

| Caso | Comparação r1 / hash se igual | Resultado | Motivo |
|---|---|---|---|
| L-a-001 | Igual `4c0db6722b87c770` | aprovado | Art. 289 original integral, até § 6º; evento e limite corretos. |
| L-a-002 | Igual `d215558ddd04bd09` | aprovado | Art. 185 original completo, incluindo parágrafo único. |
| L-a-003 | Igual `f0c044ea468e95a6` | aprovado | Art. 1.031 original completo, com dois parágrafos. |
| L-a-004 | Igual `508db54dbf81a0b4` | aprovado | Art. 3º da própria LC 118; recorte e evento corretos. |
| L-a-005 | Alterado | **reprovado** | Primeira redação corrigida para a MP 881; mutante obrigatório documenta artigo de outra obra. Achado 1. |
| L-a-006 | Igual `e6d6bf69f456be6d` | aprovado | Publicação própria da reedição 2.170-36; art. 5º integral. |
| L-a-007 | Igual `eaffd1727750d2f7` | aprovado | Art. 2º original da MP 881, com três incisos. |
| L-a-008 | Igual `491ecd7e747a4b5d` | aprovado | Art. 1º da MP 449 completo; exclui a seção seguinte. |
| L-a-009 | Igual `1de0e800abce996e` | **reprovado** | Recorte original correto; novo mutante obrigatório documenta o art. 10 de outra obra. Achado 2. |
| L-a-010 | Igual `cc6926732dcfa7e7` | aprovado | Art. 156 original integral; unidade compartilhada com L-a-001. |
| L-a-011 | Novo | aprovado | Art. 2º da Lei 13.874 integral, distinto do da MP 881; evento próprio. |
| L-b-001 | Igual `45531dbfeb0c19fb` | aprovado | Art. 14 completo, com parágrafo único. |
| L-b-002 | Alterado | aprovado | Gabarito mantido; descrição corrigida para artigo composto somente de caput. |
| L-b-003 | Igual `1af21e7cde883487` | aprovado | Art. 191-A integral; inclusão pela LC 118 documentada. |
| L-b-004 | Alterado | aprovado | Art. 421 integral; data mutante agora anterior ao Código Civil. |
| L-b-005 | Igual `20fc1020e3b92858` | aprovado | Art. 1.031 consolidado completo, de redação original. |
| L-b-006 | Igual `cd95d3ab7edea185` | aprovado | Art. 489 completo, incluindo incisos e §§ 1º a 3º. |
| L-b-007 | Alterado | aprovado | Descrição corrigida; artigo termina no § 2º, II. |
| L-b-008 | Igual `ccb2626660fafe14` | aprovado | Art. 1.815-A integral; evento Lei 14.661 correto. |
| L-b-009 | Igual `e931200d7c78f698` | aprovado | Revogação do art. 254 documentada, distinta do art. 254-A. |
| L-b-010 | Igual `d6c69e98cf3c410f` | aprovado | Art. 16-A integral; inclusão pela Lei 14.195. |
| L-b-011 | Igual `d3d0daf8b39dec90` | aprovado | Art. 1.510-C completo, incluindo incisos e § 2º. |
| L-b-012 | Igual `0f71cdeaf97fa5e3` | aprovado | Art. 254-A completo, incluindo § 5º vetado; duplica unidade de L-b-002. |
| L-c-001 | Igual `1d1b0d5c5edc0d1a` | aprovado | Art. 14 original integral em D; documentação histórica preservada. |
| L-c-002 | Alterado | aprovado | Redação original em 1990; alternativa da LC 118 materializada e diferente. |
| L-c-003 | Alterado | aprovado | Redação integral da LC 118 em 2006; alternativa original materializada. |
| L-c-004 | Alterado | aprovado | Texto integral da MP em junho de 2019; nova data mutante anterior à MP. |
| L-c-005 | Alterado | aprovado | Texto integral da lei em outubro de 2019; conversão documentalmente vinculada. |
| L-c-006 | Alterado | aprovado | EC 32 e página oficial da MP suprem a ponte temporal antes ausente. |
| L-c-007 | Substituído | aprovado | Art. 29 integral publicado pela Lei 13.853; compilada e fontes anteriores sustentam texto e rasuras. |
| L-c-008 | Igual `e4eea33e55898960` | aprovado | D anterior à obra; condição documentada pela publicação original. |
| L-c-009 | Igual `ac2addee0956777e` | aprovado | D anterior à inclusão do art. 116-A; anotação de acréscimo compatível. |
| L-c-010 | Igual `fdd52b989b419501` | aprovado | D anterior à inclusão do art. 185-A; fundamento preservado. |
| L-c-011 | Alterado | **reprovado** | Persistência de seleção incorreta da última versão oficial anterior. Achado 3. |
| L-c-012 | Igual `1eded0f4b69ee8a5` | aprovado | Negativo delimita período da redação riscada e falta de versão integral demonstrada. |
| L-d-001 | Substituído | **reprovado** | Gabarito contém notas editoriais; família `original` contradiz alterações expressas no recorte. Achado 4. |
| L-d-002 | Substituído | aprovado | Anexo II integral; evento Decreto 12.669 e destino Anexo III corretos. |
| L-d-003 | Substituído | aprovado | Anexo II integral do Decreto 11.350; destino Anexo III existente e diferente. |
| L-d-004 | Substituído | aprovado | Anexo II integral; evento Decreto 12.537 documentado. |
| L-d-005 | Substituído | aprovado | Anexo II integral do Decreto 11.349; destino corretamente delimitado. |
| L-d-006 | Substituído | aprovado | Anexo II integral; evento Decreto 12.776 documentado. |
| L-d-007 | Substituído | aprovado | Anexo II integral; evento Decreto 11.998 documentado. |
| L-d-008 | Substituído | aprovado | Redação pelo Decreto 13.074; Decreto 13.087 altera a vigência, sem mudar a família textual. |
| L-d-009 | Substituído | aprovado | Anexo II integral; evento Decreto 12.859 documentado. |
| L-d-010 | Substituído | aprovado | Anexo II integral; evento Decreto 11.402 documentado. |
| L-e-001 | Igual `d61378d555b2c15c` | aprovado | Lista completa: LSA, arts. 166 e 170, § 2º. |
| L-e-003 | Igual `e6d31cfc36b682d9` | aprovado | Lista completa: CTN, art. 100, incisos I, II e IV. |
| L-e-004 | Igual `279abb90b38cc1f0` | aprovado | Lista completa: CTN, arts. 151, 205 e 206. |
| L-e-005 | Igual `f89096cd7752c276` | aprovado | Lista completa: CC, arts. 1.814 e 1.815, caput. |
| L-e-006 | Igual `62b41c874f5b6ebd` | aprovado | Lista completa: CC, arts. 862, 863, 869 e 870. |
| L-e-007 | Igual `7c035fce727252f3` | aprovado | Inclui remissão ao próprio caput e os demais caminhos expressos. |
| L-e-008 | Igual `0d790624133cfd0e` | aprovado | Lista completa: CF, art. 100; CPC, arts. 534 e 535. |
| L-e-009 | Igual `94b63c7cccfc2bfb` | aprovado | Alvo expresso completo: CPC, art. 695. |
| L-e-010 | Igual `046790a5a73b6422` | aprovado | Alvo expresso completo: LSA, art. 110-A. |
| L-e-011 | Igual `60411f00562c5145` | aprovado | Alvo determinado completo: CC, art. 249, parágrafo único. |
| L-e-012 | Igual `34361a3151bd824f` | aprovado | Alvo completo: LC 101, art. 14; evento LC 236 documentado. |

**Tabela de todos os mutantes**

A aprovação abaixo avalia o mutante individualmente. Mutante aprovado de caso reprovado também sai do conjunto quando se retira seu caso de origem.

Para `caractere`, conferi a troca única, a diferença textual e a ausência do resultado nas fontes do caso; a expectativa é `text.status != verified`. Para `data_trocada`, a expectativa de ambos os estados diferentes de `verified` confere com a data indicada. Para `renumerado`, salvo os dois reprovados, conferi dispositivo existente, identidade da obra, conteúdo diferente e expectativa prescrita pela matriz.

| Mutante | Resultado | Motivo individual |
|---|---|---|
| L-a-001#caractere | aprovado | Posição 624: o→p. |
| L-a-001#renumerado | aprovado | Art. 290 da LSA original existente e diferente. |
| L-a-002#caractere | aprovado | Posição 206: t→u. |
| L-a-002#renumerado | aprovado | Art. 186 do CTN original existente e diferente. |
| L-a-003#caractere | aprovado | Posição 288: l→m. |
| L-a-003#renumerado | aprovado | Art. 1.032 do CC original existente e diferente. |
| L-a-004#caractere | aprovado | Posição 157: i→j. |
| L-a-004#renumerado | aprovado | Art. 4º da própria LC 118 existente e diferente. |
| L-a-005#caractere | aprovado | Posição 692: s→t. |
| L-a-005#renumerado | **reprovado** | Chamada pede Lei 12.682; conteúdo registrado pertence à MP 881. |
| L-a-006#caractere | aprovado | Posição 315: f→g. |
| L-a-006#renumerado | aprovado | Art. 6º da reedição existente e diferente. |
| L-a-007#caractere | aprovado | Posição 145: a→b. |
| L-a-007#renumerado | aprovado | Art. 3º da própria MP 881 existente e diferente. |
| L-a-008#caractere | aprovado | Posição 1417: p→q. |
| L-a-008#renumerado | aprovado | Art. 2º da própria MP 449 existente e diferente. |
| L-a-009#caractere | aprovado | Posição 104: c→d. |
| L-a-009#renumerado | **reprovado** | Hash identifica art. 10 da Lei 6.385, não o da Lei 10.303 pedida. |
| L-a-010#caractere | aprovado | Posição 394: v→w. |
| L-a-010#renumerado | aprovado | Art. 157 da LSA original existente e diferente. |
| L-a-011#caractere | aprovado | Posição 272: e→f. |
| L-a-011#renumerado | aprovado | Art. 3º da própria Lei 13.874 existente e diferente. |
| L-b-001#caractere | aprovado | Posição 242: O→P. |
| L-b-001#data_trocada | aprovado | 1976-06-01 anterior à LSA. |
| L-b-001#renumerado | aprovado | Art. 15 da LSA existente e diferente. |
| L-b-002#caractere | aprovado | Posição 208: u→v. |
| L-b-002#data_trocada | aprovado | 1976-06-01 anterior à LSA. |
| L-b-002#renumerado | aprovado | Art. 166 da LSA existente e diferente. |
| L-b-003#caractere | aprovado | Posição 85: u→v. |
| L-b-003#data_trocada | aprovado | 1966-01-01 anterior ao CTN. |
| L-b-003#renumerado | aprovado | Art. 192 do CTN existente e diferente. |
| L-b-004#caractere | aprovado | Posição 116: e→f. |
| L-b-004#data_trocada | aprovado | 2001-06-01 anterior ao Código Civil. |
| L-b-004#renumerado | aprovado | Art. 422 do CC existente e diferente. |
| L-b-005#caractere | aprovado | Posição 289: l→m. |
| L-b-005#data_trocada | aprovado | 2001-06-01 anterior ao Código Civil. |
| L-b-005#renumerado | aprovado | Art. 1.032 do CC existente e diferente. |
| L-b-006#caractere | aprovado | Posição 857: r→s. |
| L-b-006#data_trocada | aprovado | 2014-06-01 anterior ao CPC. |
| L-b-006#renumerado | aprovado | Art. 490 do CPC existente e diferente. |
| L-b-007#caractere | aprovado | Posição 543: m→n. |
| L-b-007#data_trocada | aprovado | 1976-06-01 anterior à LSA. |
| L-b-007#renumerado | aprovado | Art. 137 da LSA existente e diferente. |
| L-b-008#caractere | aprovado | Posição 134: e→f. |
| L-b-008#data_trocada | aprovado | 2001-06-01 anterior ao Código Civil. |
| L-b-008#renumerado | aprovado | Art. 1.816 do CC existente e diferente. |
| L-b-009#renumerado | aprovado | Art. 255 existente, com conteúdo próprio, distinto do original revogado. |
| L-b-010#caractere | aprovado | Posição 97: r→s. |
| L-b-010#data_trocada | aprovado | 1976-06-01 anterior à LSA. |
| L-b-010#renumerado | aprovado | Art. 17 da LSA existente e diferente. |
| L-b-011#caractere | aprovado | Posição 526: s→t. |
| L-b-011#data_trocada | aprovado | 2001-06-01 anterior ao Código Civil. |
| L-b-011#renumerado | aprovado | Art. 1.511 do CC existente e diferente. |
| L-b-012#caractere | aprovado | Posição 750: s→t. |
| L-b-012#data_trocada | aprovado | 1976-06-01 anterior à LSA. |
| L-b-012#renumerado | aprovado | Art. 255 da LSA existente e diferente. |
| L-c-001#caractere | aprovado | Posição 242: O→P. |
| L-c-001#data_trocada | aprovado | 1976-06-01 anterior à LSA. |
| L-c-001#renumerado | aprovado | Art. 15 da LSA original existente; trecho do art. 14 não corresponde. |
| L-c-002#caractere | aprovado | Posição 206: t→u. |
| L-c-002#data_trocada | aprovado | 2006-01-01 alcança redação diferente da LC 118. |
| L-c-002#renumerado | aprovado | Art. 186 original existente; trecho do art. 185 não corresponde. |
| L-c-003#caractere | aprovado | Posição 192: o→p. |
| L-c-003#data_trocada | aprovado | 1990-03-01 alcança redação original diferente. |
| L-c-003#renumerado | aprovado | Art. 186 do CTN reproduzido na LC 118; conteúdo diferente. |
| L-c-004#caractere | aprovado | Posição 145: a→b. |
| L-c-004#data_trocada | aprovado | 2019-04-15 anterior à MP 881. |
| L-c-004#renumerado | aprovado | Art. 3º da MP existente; trecho do art. 2º não corresponde. |
| L-c-005#caractere | aprovado | Posição 272: e→f. |
| L-c-005#data_trocada | aprovado | 2019-06-01 anterior à Lei 13.874. |
| L-c-005#renumerado | aprovado | Art. 3º da lei existente; trecho do art. 2º não corresponde. |
| L-c-006#caractere | aprovado | Posição 315: f→g. |
| L-c-006#data_trocada | aprovado | 2001-01-01 anterior à reedição indicada. |
| L-c-006#renumerado | aprovado | Art. 6º da reedição existente; conteúdo diferente. |
| L-c-007#caractere | aprovado | Posição 180: e→f. |
| L-c-007#data_trocada | aprovado | 2018-01-15 anterior à LGPD. |
| L-c-007#renumerado | aprovado | Art. 30 da LGPD existente; trecho do art. 29 não corresponde. |
| L-c-008#renumerado | aprovado | Art. 422 existe na fonte; D permanece anterior à obra. |
| L-c-009#renumerado | aprovado | Art. 117 da própria LSA existe na fonte e difere do art. 116-A. |
| L-c-010#renumerado | aprovado | Art. 186 do próprio CTN existe na fonte e difere do art. 185-A. |
| L-c-011#renumerado | aprovado | Art. 290 existente; trecho de publicações do art. 289 não corresponde. |
| L-c-012#renumerado | aprovado | Art. 280 existente; trecho de consórcio do art. 279 não corresponde. |
| L-d-001#caractere | aprovado | Posição 4591: i→j; aprovação individual não sana o gabarito. |
| L-d-001#renumerado | aprovado | Anexo III do Decreto 11.331, PDF folha 22; existente e diferente. |
| L-d-002#caractere | aprovado | Posição 2923: O→P. |
| L-d-002#renumerado | aprovado | Anexo III do Decreto 11.346, PDF folha 17; existente e diferente. |
| L-d-003#caractere | aprovado | Posição 4801: o→p. |
| L-d-003#renumerado | aprovado | Anexo III do Decreto 11.350, PDF folha 34; existente e diferente. |
| L-d-004#caractere | aprovado | Posição 3312: r→s. |
| L-d-004#renumerado | aprovado | Anexo III do Decreto 11.335, PDF folha 24; existente e diferente. |
| L-d-005#caractere | aprovado | Posição 5119: I→J. |
| L-d-005#renumerado | aprovado | Anexo III do Decreto 11.349, PDF folha 41; existente e diferente. |
| L-d-006#caractere | aprovado | Posição 4216: E→F. |
| L-d-006#renumerado | aprovado | Anexo III do Decreto 11.330, PDF folha 37; existente e diferente. |
| L-d-007#caractere | aprovado | Posição 6595: S→T. |
| L-d-007#renumerado | aprovado | Anexo III do Decreto 11.332, PDF folha 41; existente e diferente. |
| L-d-008#caractere | aprovado | Posição 2515: C→D. |
| L-d-008#renumerado | aprovado | Anexo III do Decreto 11.351, PDF folha 17; existente e diferente. |
| L-d-009#caractere | aprovado | Posição 5545: E→F. |
| L-d-009#renumerado | aprovado | Anexo III do Decreto 11.336, PDF folha 33; existente e diferente. |
| L-d-010#caractere | aprovado | Posição 7414: L→M. |
| L-d-010#renumerado | aprovado | Anexo III do Decreto 11.342, PDF folha 42; existente e diferente. |
| L-e-001#caractere | aprovado | Posição 242: O→P. |
| L-e-001#renumerado | aprovado | Art. 15 da LSA existente e diferente. |
| L-e-003#caractere | aprovado | Posição 186: o→p. |
| L-e-003#renumerado | aprovado | Art. 104 do CTN existente e diferente. |
| L-e-004#caractere | aprovado | Posição 85: u→v. |
| L-e-004#renumerado | aprovado | Art. 192 do CTN existente e diferente. |
| L-e-005#caractere | aprovado | Posição 134: e→f. |
| L-e-005#renumerado | aprovado | Art. 1.816 do CC existente e diferente. |
| L-e-006#caractere | aprovado | Posição 97: u→v. |
| L-e-006#renumerado | aprovado | Art. 875 do CC existente e diferente. |
| L-e-007#caractere | aprovado | Posição 150: t→u. |
| L-e-007#renumerado | aprovado | Art. 10 do CPC existente e diferente. |
| L-e-008#caractere | aprovado | Posição 281: o→p. |
| L-e-008#renumerado | aprovado | Art. 911 do CPC existente e diferente. |
| L-e-009#caractere | aprovado | Posição 156: o→p. |
| L-e-009#renumerado | aprovado | Art. 700 do CPC existente e diferente. |
| L-e-010#caractere | aprovado | Posição 97: r→s. |
| L-e-010#renumerado | aprovado | Art. 17 da LSA existente e diferente. |
| L-e-011#caractere | aprovado | Posição 526: s→t. |
| L-e-011#renumerado | aprovado | Art. 1.511 do CC existente e diferente. |
| L-e-012#caractere | aprovado | Posição 117: t→u. |
| L-e-012#renumerado | aprovado | Art. 172 do CTN existente e diferente. |

Resultado individual: **50/50 `caractere` aprovados; 18/18 `data_trocada` aprovados; 54/56 `renumerado` aprovados**.

**Achados por classe**

**Classe: identidade documental dos mutantes — bloqueadora**

**1. L-a-005#renumerado confunde a obra alteradora com a obra consultada.** A chamada pede `art. 3º da Lei 12.682/2012`, com `versao="publicacao_original"`. Entretanto, a fonte `cf1d55ac8adf…` e o hash de destino `c0026aaa88bf…` documentam o art. 3º da **MP 881/2019**, relativo à declaração de direitos de liberdade econômica.

O art. 11 da MP reproduz o art. 2º-A incluído na Lei 12.682; isso sustenta o original corrigido, mas não transforma o art. 3º da própria MP em artigo da lei alterada. A ressalva do pesquisador registra o problema, sem resolvê-lo. Reprovo o mutante e, por consequência, o caso como unidade do pacote.

**Correção necessária:** documentar o destino da citação completa efetivamente chamada, regenerar e revisar o mutante, ou retirar o caso.

**2. L-a-009#renumerado seleciona artigo inserido dentro do ato, de outra obra.** A publicação da Lei 10.303, evidência `396d43186ded…`, contém dois arts. 10 com identidades diferentes:

- o art. 10 da **Lei 6.385**, reproduzido no comando alterador, sobre cooperação da CVM;
- o art. 10 da **própria Lei 10.303**, que revoga dispositivos.

O `destino_texto_sha256` registrado, `739fa3095a26d47e3de1d9ca2d18b24145628cdf6e68faca1bb766f14aabb9d0`, foi reproduzido independentemente a partir do **primeiro conteúdo**, após normalização e retirada de `(NR)`. A chamada pede o segundo.

Portanto, há destino real para a chamada, mas o comprovante materializado corresponde a outro dispositivo. A conclusão fornecida de “124 mutantes conferidos, 0 problemas” não se sustenta.

**Correção necessária:** selecionar o artigo dentro da identidade correta do ato, regenerar e revisar o mutante. O texto original de L-a-009 permanece correto.

**Classe: documentação temporal negativa — bloqueadora**

**3. L-c-011 mantém incorreta a seleção da última versão oficial anterior.** A r2 corrige as alterações de 1997 e 2001 e reconhece que a MP 892/2019 reproduz integralmente o art. 289. Contudo, continua declarando a publicação de **1976** como `ultima_versao_anterior`.

A MP 892, evidência `c6dbb8635ce8…`, é publicação oficial integral posterior a 1976 e anterior a D. Sua perda de eficácia antes de D e a condição de produção de efeitos precisam acompanhar a descrição histórica; não autorizam eliminá-la da posição de versão oficial anterior conhecida. “Última versão anterior” e “versão vigente em D” são categorias diferentes.

O resultado negativo pode subsistir, mas a documentação exigida para admitir `sem_versao_oficial_na_data` permanece inadequada. A alternativa `sem_fundamento_do_periodo` entre os motivos aceitos não corrige o campo documental contraditório já fornecido.

**Correção necessária:** registrar a publicação integral anterior conhecida com seus limites de eficácia, ajustar a cadeia e a explicação correspondente, e revisar novamente o caso e sua cobertura.

**Classe: gabarito e família normativa — bloqueadora**

**4. L-d-001 contém notas editoriais e atribuição incorreta de família.** O Anexo II do Decreto 11.331, evidência `f157fe9afe53…`, contém alterações expressamente atribuídas ao **Decreto 11.387/2023**, nas folhas 14, 15, 18, 19 e 20 do PDF.

O gabarito conserva **seis notas editoriais**, relativas a divisões, coordenações, coordenação-geral e secretaria. Isso contraria a seção 6, que exige gabarito sem notas ou anotações editoriais. Além disso, `familia_alteracao="original"` e a afirmação de ausência de anotação contradizem a própria fonte e o próprio gabarito.

O Anexo III existe e os dois mutantes são individualmente válidos; isso não sana o original.

**Correção necessária:** remover as notas do gabarito, fundamentar a família no evento efetivo da redação consolidada e regenerar os mutantes, ou retirar o caso.

**Classe: cobertura documental — bloqueadora no arquivo entregue**

| Situação obrigatória | Resultado da revisão |
|---|---|
| `lsa_156` | Atendida por L-a-010. |
| `lsa_254a` | Atendida por L-b-012. |
| `lsa_289` | Atendida por L-a-001; retirar ou corrigir o vínculo e a expectativa de L-c-011. |
| `cc_421` | Atendida por L-b-004; L-c-008 complementa a condição anterior à obra. |
| `cc_1031` | Atendida por L-a-003 e L-b-005. |
| `ctn_185` | Atendida por L-a-002, L-c-002 e L-c-003. |
| `rasura` | Atendida pelo conjunto dos vínculos: L-c-007 documenta rasuras; L-c-012 efetivamente situa D na redação anterior riscada. |
| `sem_rasura` | Atendida por L-c-002. L-c-001 é complementar e não demonstra sozinho mudança histórica. |
| `revogacao` | Atendida por L-b-009. |
| `mp_reeditada` | Atendida por L-a-006 e L-c-006, agora com ponte temporal documentada. |
| `mp_convertida` | Atendida por L-c-004, L-c-005 e L-a-007, com textos distintos e vínculo documental da conversão. |
| `anexo` | Atendida pelos nove casos aprovados; retirar ou corrigir L-d-001. |
| `remissao` | Atendida pelos onze casos aprovados de capacidade e. |
| `data_anterior_a_publicacao` | Atendida por L-c-008, L-c-009 e L-c-010. |

A cobertura obrigatória **sobrevive às exclusões**, mas `cobertura.json` ainda contém os vínculos reprovados de **L-c-011 e L-d-001**. Sua manutenção impede aprovar o arquivo como entregue.

**Classe: integridade e comprovação mecânica — sem bloqueador adicional**

A saída mecânica fornecida corresponde aos hashes atuais. As evidências e seus tamanhos conferem. Nos nove anexos aprovados, a extração por página em modo `layout`, normalizada e sem a anotação editorial externa ao conteúdo normativo, reproduziu integralmente os gabaritos e seus limites antes do Anexo III.

O resultado mecânico registrado de zero falhas não supera os achados de mérito acima.

**Tabela final de contagens por capacidade**

Aplicadas as quatro exclusões e refeita a seleção lexicográfica por evento, L-a-007 passa a representar o evento da MP 881. Permanecem como duplicatas fora do denominador L-a-010, L-b-012, L-c-010 e L-e-008.

| Capacidade | Casos entregues | Casos reprovados | Casos remanescentes | Unidades remanescentes | Normas entre representantes | Mutantes remanescentes | Piso ≥8 unidades e ≥4 normas |
|---|---:|---:|---:|---:|---:|---:|---|
| a | 11 | 2 | 9 | 8 | 8 | 18 | atende |
| b | 12 | 0 | 12 | 11 | 4 | 34 | atende |
| c | 12 | 1 | 11 | 10 | 7 | 25 | atende |
| d | 10 | 1 | 9 | 9 | 9 | 18 | atende |
| e | 11 | 0 | 11 | 10 | 4 | 22 | atende |
| **Total** | **56** | **4** | **52** | **48** | — | **117** | **atende aos pisos estruturais** |

O piso global de **40 casos** também permanece atendido. Acertos do verificador, confirmação indevida e desempenho não foram apurados nesta revisão de mérito. O pacote entregue permanece **bloqueado pelos quatro casos e pelos vínculos de cobertura indicados**, apesar da suficiência quantitativa após sua retirada.