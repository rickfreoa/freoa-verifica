# 0065 — Captura legada sem cabeçalho e compatibilidade dos derivados

Data: 21/10/2026 · Versão: 1.3.0 · Origem: auditoria final, rodada 15 (F-24); revê a regra 4 e a primeira
consequência da 0064 para capturas sem Content-Type

## Problema

O snapshot congelado tem 843 capturas com modelo (423 BCB, 299 CVM, 121 Planalto) gravadas pela 1.2.0 com
`headers_json={}`: o Content-Type HTTP original não foi preservado. Pela 0064, a releitura delas era
`falha: interpretacao_indisponivel` (0 reprocessadas, 843 falhas), mas `derivados.compativel` continuava True (versão
4/4) e a instalação podia dispensar a reconstrução. O Planalto recusa o cliente identificado (0048): recapturar não
é possível; para BCB e CVM, recapturar trocaria a prova histórica por outra.

## Regra

1. **Captura legada.** Captura sem Content-Type (nem no recibo da 014 nem em `headers_json`) é reinterpretada só a
   partir dos próprios bytes, pela função única (`texto_resposta.interpretar_legado`, que é `interpretar` sem
   Content-Type): BOM → prescan WHATWG (HTML) → declaração XML → JSON (RFC 8259: UTF-8; corpo que começa por `{` ou
   `[` não passa pelo prescan) → UTF-8 estrito. PDF e DOCX, pela assinatura (`%PDF-`, `PK\x03\x04`), são binários,
   sem codec. Nenhum Content-Type é inventado (o MIME gravado também não faz as vezes dele). Bytes inválidos na
   codificação resultante: `falha: interpretacao_indisponivel`, modelo intacto.
2. **Recibo da decisão.** `origem_da_codificacao`/`interpretacao_origem` = `legado_sem_cabecalho` (prova degradada,
   sem cabeçalho HTTP); a codificação usada é registrada. O recibo (`capture`) é imutável: para captura cujo recibo não
   tem decisão, a releitura a grava no derivado (`parsed_document.interpretacao_codificacao`/`interpretacao_origem`,
   migração 015, exportadas no snapshot). Captura nova sem Content-Type já nasce com a decisão no recibo. A releitura
   seguinte confere a decisão registrada; divergência é `falha: interpretacao_divergente`.
3. **Resposta pública.** Texto de captura legada leva `proveniencia: {interpretacao: "legado_sem_cabecalho"}`
   (experimental) em `obter_dispositivo`, `obter_evidencia` e em cada item de `evidence[]` de `verificar_citacao`.
   `obter_evidencia` sem Content-Type exibe a mesma releitura (antes, a vista latin-1 do MIME gravado).
4. **Compatibilidade.** `DERIVED_VERSION` = 5. `derivados.compativel` só é True se os derivados são da versão atual
   e toda captura reprocessável com modelo (Planalto, CVM, BCB; obra não invalidada) tem decisão registrada, no
   recibo ou no derivado (atual ou legada). Home vazio continua compatível. Snapshot v4 é reconstruído na instalação;
   se alguma captura falhar, a instalação é recusada (fluxo existente), nunca aceita em silêncio.
5. **Relatório.** `reprocessar_capturas`, `fv acervo reconstruir` e a reconstrução na instalação relatam
   `por_fonte.<id>`: `reprocessadas_atuais`, `reprocessadas_legadas` e `falhas` (motivo → contagem); na recusa,
   `por_fonte` acompanha o erro.

## Consequências

- O snapshot da 1.2.0 deixa de ser certificado como atual e passa a ser reconstruível sem novas capturas; a releitura
  dos 1.2.0 é declarada degradada, não equiparada à captura com cabeçalho.
- Página que o servidor servia em UTF-8 com `<meta>` Latin-1 divergente (o caso F-22) é lida, sem cabeçalho, pelo
  `<meta>`: é o limite da prova sem cabeçalho, e é por isso que a origem é declarada.
- Senado e demais fontes não reprocessáveis ficam fora do critério de compatibilidade, como ficam fora da releitura.
- Testes: `tests/test_fix19_f24_legado.py`; revistos `tests/test_fix18_f22_recibo_interpretacao.py` e
  `tests/test_c6_derivados.py` (snapshot da 1.0.2 sem Content-Type agora é relido como legado).

## Emenda (FIX19b, 21/10/2026) — padrão da fonte sob conferência

**Problema.** Na cópia do banco real, 118 das 121 capturas legadas do Planalto falham na regra 1: sem BOM, sem
declaração nos bytes e inválidas em UTF-8 (cp1252 sem `<meta>`, como a fixture real da LSA). O Planalto recusa o
cliente identificado (0048): não há recaptura nem cabeçalho autêntico obtenível.

**Regra 6 (decisão do supervisor).** Para captura legada (sem Content-Type) **sem declaração de codificação nos
bytes** (BOM, `<meta>` efetivo pelo prescan, declaração XML; nem JSON nem binário pela assinatura) **e inválida em
UTF-8**, admite-se uma única codificação alternativa por fonte, declarada na tabela versionada
`texto_resposta.CODIFICACAO_LEGADA_POR_FONTE = {"planalto": "windows-1252"}` — **sob condição de conferência**:

1. a releitura só é aceita se o modelo produzido for idêntico ao modelo já persistido para aquela captura (produzido
   pela versão que a capturou), comparados por hash canônico do modelo (`service._hash_modelo`: título, ementa,
   texto e, por dispositivo, caminho, rótulo, escopo, rubrica, cabeçalhos e redações com texto e marca de riscado;
   ficam fora issues, spans, anotações e versão do parser);
2. idêntico: `interpretacao_origem = "legado_padrao_da_fonte_conferido"`, codificação registrada no derivado e, em
   `parsed_document.interpretacao_conferencia` (migração 016, exportada no snapshot), a evidência
   `{modelo_anterior_sha256, modelo_novo_sha256}`;
3. divergente, ou sem modelo anterior: `falha: interpretacao_indisponivel`, modelo e obra intactos. O padrão da fonte
   nunca é aplicado sem conferência;
4. não se aplica a capturas novas (`repo.interpretacao_do_recibo` não consulta a tabela: captura nova sem
   Content-Type continua na regra 1) nem a fontes sem entrada na tabela.

Releitura seguinte de captura conferida confere de novo, contra o modelo persistido (idêntico ao original) e contra
a decisão registrada no derivado. `obter_evidencia` só usa o padrão da fonte para captura cuja conferência está
registrada no derivado; sem ela, exibe como na regra 3.

**Relatório e resposta pública.** `por_fonte.<id>` ganha `reprocessadas_legadas_conferidas`.
`proveniencia.interpretacao` (experimental) vale `legado_sem_cabecalho` ou `legado_padrao_da_fonte_conferido`.

**Consequências.** A conferência prende a releitura ao parser: mudança futura do parser do Planalto que altere o
modelo dessas capturas fará a conferência falhar e a reconstrução ser recusada; a saída, então, é decisão nova, não
afrouxar o hash. A conferência prova que a versão atual reproduz a leitura da versão que capturou, não que
windows-1252 era a codificação servida; por isso a origem é declarada em toda resposta. Testes em
`tests/test_fix19_f24_legado.py` (padrão aceito e conferido, modelo divergente, sem modelo, fonte sem tabela,
captura nova).
