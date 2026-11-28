# 0096 - Paridade da leitura de HTML entre plataformas (libxml2 2.11 e 2.14)

Status: aprovada pelo titular em 28/11/2026 ("Normalizar antes da lxml"; rito: "Atualização no Windows").

## Problema

A instalação da 1.4.0a9 pelo instalador oficial no home real do titular (Windows 11, acervo da 1.4.0a8) falhou na
etapa do snapshot: `reprocessamento falhou em 10 captura(s): interpretacao_indisponivel`, `rollback: false`. A falha
ocorreu no staging e o banco ficou intacto, mas o pacote ficou na 1.4.0a9 com derivados 6, e a guarda C6 passou a
recusar as consultas de legislação. O home voltou à 1.4.0a8 (só o pacote, wheel conferida).

Reprodução numa cópia integral do home, com instrumentação: as 10 capturas são legadas do Planalto, conferidas pelo
padrão da fonte (cp1252), de 18/10/2026 (CF, Leis 10.303 [duas], 6.385, 9.613, 14.620, 14.661, 14.690 e 14.713,
DL 2.287). O modelo gravado no snapshot (parser 1.2.5, gerado no Linux) não se reproduz no Windows com o mesmo parser
1.2.5 e a mesma decisão de interpretação, e a regra da 0065 recusa.

Causa: a lxml 6.1.3 embute libxml2 **2.11.9** nas wheels de Windows e **2.14.6** nas de Linux, e as duas leem de
modo diferente o HTML do Planalto:

1. **Referências numéricas de 128 a 159** (`&#150;`, `&#145;`, `&#146;`): a 2.14 segue o HTML5 e lê o caractere do
   cp1252 ("–", "‘", "’"); a 2.11 grava os caracteres de controle U+0096, U+0091, U+0092. Sem o travessão, o parser
   não reconhece o inciso (na CF, 37 trocas; ADCT art. 77, I, vira alínea).
2. **`</body></html>` soltos no meio da página** (L 14.661 e outras): as duas versões divergem sobre o que vem depois.

Sem a recusa da 0065, o reprocessamento no Windows grava modelos errados em silêncio: seis na cópia, entre eles a CF.
Os 965 modelos do home real estão limpos (vieram de snapshots gerados no Linux). O rito não cobria atualização sobre
home com histórico no Windows: a reconstrução era testada só a partir do snapshot, no Linux.

## Decisão

1. **Normalização léxica antes da lxml** (`parsers/html_paridade.py`; parser Planalto 1.2.6 e `cvm-html-2`, os
   parsers HTML que gravam modelo reprocessável). Só o texto entre tags é tocado; comentários, CDATA, `<script>`,
   `<style>` e o interior das tags (atributos) ficam intactos. No texto, a referência numérica de 128 a 159, decimal
   ou hexadecimal, com ou sem ponto e vírgula e com zeros à esquerda, lida por inteiro, vira o caractere que o HTML5
   lhe atribui (tabela do cp1252); os cinco códigos sem mapeamento (0x81, 0x8D, 0x8F, 0x90, 0x9D) e qualquer número
   fora da faixa ficam como estão. As tags de fechamento `</body>` e `</html>`, inteiras, saem; o parser fecha ambos no
   fim do documento, e as duas versões leem a página inteira. A remoção não junta fragmentos (`<</body>s>` vira
   `&lt;s>`, não `<s>`).
2. `DERIVED_VERSION` 8: reconstrução e snapshot novos.
3. **Rito (RELEASE.md, passo 3):** antes da tag, o candidato é instalado, com o snapshot, sobre uma cópia integral de
   um home com histórico numa máquina Windows, sem tocar o home real; instalação `ok`, S4 estrito e doctor.

## Auditoria

Codex r1 sobre `521303f`: BLOQUEADOR. A primeira versão removia fechamentos e convertia referências sem contexto
(atributo `line-</body>through` virava `line-through` e tornava texto vigente riscado; `<</body>s>` virava `<s>`),
consumia referências longas pela metade (`&#00001500;` virava `-0;`), não lia zeros à esquerda e deixava fora o
parser HTML da CVM. Todos corrigidos com teste; o teste do fechamento solto passou a reproduzir a estrutura real da
Lei 14.661 (falhava só na 2.14 sem a correção; o anterior não falhava em plataforma alguma).

## Verificação

Paridade sobre o acervo inteiro (844 capturas reprocessáveis de Planalto, CVM e BCB), com o código do ramo: hashes dos
modelos idênticos no Windows (libxml2 2.11.9) e no Linux (libxml2 2.14.6), nenhum erro, nenhum caractere de controle
no texto. Testes de regressão em `tests/test_0096_paridade_libxml2.py`; a CI roda em Ubuntu e Windows.

## Limites

- A paridade é garantida para as duas divergências encontradas e medida sobre o acervo atual. Outra divergência da
  libxml2 em HTML não visto continua possível; a 0065 continua a recusá-la em vez de gravar modelo diferente, e o
  passo novo do rito a expõe antes do release.
- Os parsers que não geram modelo reprocessável (`arvore_html` dos conectores de decisões, Câmara, TJDFT, descoberta)
  não passam pela normalização.
- A 1.4.0a9 publicada continua com o defeito: aviso nas notas da release; não atualizar no Windows home com acervo.
