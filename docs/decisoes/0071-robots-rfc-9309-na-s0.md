# 0071 — A leitura do robots.txt na S0 segue o RFC 9309

Estado: aceita. Decisão do titular (Ricardo Peres Freoa) em 28/10/2026, registrada pelo supervisor. Substitui a regra
conservadora de 28/10/2026 registrada em `docs/S0-SONDAS.md` (tabela de parada do robots.txt).

## Contexto

Na rodada 1 da S0 (`docs/auditoria/1.4.0/s0-rodada1.md`, instrumento em `c24a1a4`), o `robots.txt` de cada host era o
primeiro comando dele e a tabela de parada era mais conservadora que o RFC 9309:

- seis robots foram recusados pelo instrumento com `transporte_RespostaInvalida` e status 200, sem Content-Type
  registrado (STF, BNP ×2, DJEN página, TJAC, TJDFT). O transporte aceitava só `text/plain`; o registro da recusa
  não trazia o Content-Type recebido nem o motivo, e a causa não ficou determinada;
- três robots responderam 404 (TST backend, TRF1 arquivo, TJMG) e pararam o host pela regra conservadora do
  supervisor (qualquer status diferente de 200 = permissão indeterminada). O RFC 9309 trata 4xx como ausência de
  restrições.

Nenhum desses nove hosts recusou o produto: 404 é ausência de robots, e 200 é resposta. A parada decorreu da regra
e do instrumento, não de barreira da fonte.

## Decisão

1. A leitura do `robots.txt` na S0 segue o RFC 9309, com as barreiras abaixo mantidas (regra invariável 3).
2. Regra por resposta:

| Resposta do `robots.txt` | Leitura |
|---|---|
| 200 com regras interpretáveis (ao menos um grupo `User-agent` e só diretivas conhecidas ou comentários) | obedecer; `Disallow` aplicável ao caminho impede o caminho |
| 200 sem regras interpretáveis (inclusive HTML ou outro MIME) | sem restrições; Content-Type e sha256 do corpo ficam registrados |
| 404 e 410 | sem restrições (ausência de robots) |
| 401, 403, 429, desafio, WAF, 5xx, timeout, erro de transporte, redirecionamento para outro host | barreira: a fonte para e não há nova tentativa (regra 3) |
| outros 4xx | barreira por conservadorismo, registrada como tal |
| redirecionamento para o mesmo host | continua não seguido (política atual): barreira com evidência |

3. Instrumento (sem tocar `freoa_verifica/transport.py`, congelado):
   - o `robots.txt` (forma exata `/robots.txt`, prefixo exato, um pedido, `max_redirects=0`) é pedido com uma lista
     larga de MIMEs (`robots_s0.MIMES_ROBOTS`: inclui `text/plain`, `text/html` e `application/octet-stream`), porque o
     transporte só aceita MIMEs de uma lista e recusa resposta sem Content-Type. O corpo é gravado como evidência de
     sonda, nunca como fixture nem dado do produto (o instrumento recusa o robots fora de `--sonda` e
     `registrar_fixture` o recusa);
   - a detecção de desafio por corpo do transporte comum fica desligada para o robots (o Content-Type só é
     conhecido depois do único pedido, e em `text/plain` ela confundiria `Disallow: /captcha/` com desafio); quem
     decide é `robots_s0.ler_robots`, com os marcadores do próprio projeto (`connectors.challenge`). Fora de
     `text/plain` (HTML, octet-stream, outro), corpo com marcador de desafio é barreira `desafio_no_robots`, antes de
     qualquer conclusão de "sem regras" e mesmo que haja linhas de regra; em `text/plain`, regras interpretáveis são
     obedecidas e só o texto sem regras é examinado em busca de marcador. Página de CAPTCHA/WAF servida como 200
     HTML nunca libera rotas (correção do supervisor de 28/10/2026);
   - toda recusa de transporte, em qualquer captura, passa a registrar na evidência a subclasse e a mensagem curta da
     exceção, o Content-Type recebido (quando o recibo do transporte o reteve) e os saltos de redirecionamento.
     Nunca cabeçalhos sensíveis: o recibo retém só data, Content-Type, Content-Length e Retry-After, e a mensagem é
     aparada e sem os nomes `Set-Cookie`, `Authorization` e `Cookie`.
4. A interpretação fica em módulo puro e testável (`freoa_verifica/robots_s0.py`), importado só pelo instrumento
   (`freoa_verifica/captura.py`) e pelo orquestrador oficial (`scripts/s0_orquestrar.py`). O serviço, o MCP e a CLI
   `fv` não o importam (teste estrutural). Usa `urllib.robotparser` só depois de validar que há regras
   interpretáveis.
5. Casos que a tabela não cobre, resolvidos por conservadorismo (regra invariável 2) e sujeitos à confirmação do
   titular:
   - 200 com `Allow`/`Disallow` que não é interpretável (sem grupo `User-agent`, ou misturado a linhas
     desconhecidas) e que não é HTML: barreira `regras_ambiguas`, e não "sem restrições";
   - 200 que o transporte recusa (sem Content-Type, ou MIME fora da lista): o corpo não é lido, logo não há como
     afirmar que não há regras; barreira (`content_type_ausente`, `resposta_200_recusada`) com a evidência acima;
   - 200 com corpo vazio: sem restrições, com o sha256 do corpo vazio;
   - o `urllib.robotparser` varia entre versões do Python (curingas `*` e `$`, precedência): a decisão por caminho
     soma o `robotparser` e um avaliador RFC 9309 do próprio módulo, e veda se qualquer um vedar. Diretivas não
     padronizadas comuns (`Host`, `Request-rate`, `Clean-param`, `Noindex`...) contam como conhecidas, para não
     esconder um `Disallow` ao lado delas.
   - parecer do PR #17, rodada 1 (correções do item 5):
     - corpo 200 que não pode ser examinado com segurança (charset que não fecha, NUL no texto de MIME textual, ou
       diretivas `User-agent`/`Allow`/`Disallow` em UTF-16/UTF-32 sem BOM) é barreira `corpo_nao_interpretavel`; a
       busca de marcador de desafio nos bytes só acrescenta detecção (`desafio_no_robots`), nunca libera. Isso
       revoga a leitura por vista latin-1 de arquivo em charset legado, mas só em parte: ver a decisão do titular
       abaixo, que substitui a escolha "charset legado vira barreira";
     - decisão do titular de 28/10/2026 (substitui a escolha anterior "charset legado vira barreira"): corpo 200 que
       não decodifica em UTF-8 estrito nem no charset declarado é lido como charset legado compatível com ASCII
       (byte a byte) somente se (a) não há byte nulo, (b) não há BOM nem padrão de UTF-16/UTF-32 e (c) todo byte
       >= 0x80 está em comentário, isto é, depois de `#` na mesma linha. As regras são então lidas normalmente e a
       leitura registra `charset_legado_em_comentario: true` (os bytes >= 0x80, todos em comentário, viram U+FFFD no
       texto, para que U+0085 não parta linha). Continua barreira `corpo_nao_interpretavel` com byte >= 0x80 fora de
       comentário (inclusive em linha de regra), byte nulo, padrão UTF-16/32 sem BOM ou qualquer outra impossibilidade
       de exame seguro; a busca de marcador de desafio nos bytes só acrescenta detecção, nunca libera. Charset
       declarado que decodifica continua valendo (sem a flag) e UTF-16 com BOM continua lido;
     - a comparação de caminho e regra normaliza só octetos não reservados (RFC 3986), em caixa alta uniforme para
       os demais: `%2F` continua distinto de `/` (RFC 9309, 2.2.2);
     - agrupamento pelo RFC 9309, 2.2.4: linhas `User-agent` consecutivas formam um grupo; só `Allow` e `Disallow`
       encerram a sequência de agentes; extensões (`Crawl-delay`, `Request-rate`, `Sitemap`...) não interferem. Como o
       `urllib.robotparser` também erra esse caso, a composição segue vedando se qualquer avaliador vedar.
     - parecer PR #18 r2 (28/10/2026): fim de linha é só CR, LF ou CRLF (RFC 9309, 2.2). Os demais separadores
       que `str.splitlines` reconhece (`0x0B`, `0x0C`, `0x1C` a `0x1E`, U+0085, U+2028, U+2029) nunca criam linha
       nova, nem dentro de comentário: presentes no texto, o corpo é barreira `corpo_nao_interpretavel`. Byte nulo
       é barreira em qualquer MIME, inclusive `application/octet-stream`; isso revoga a escolha anterior de ler
       binário com NUL como `sem_restricoes`, porque não há critério sintático que o separe de UTF-16/32 sem BOM
       e a ausência de marcador de desafio não pode liberar.
6. A diferença entre redirecionamento para o mesmo host e para outro host não é recuperável pelo transporte
   (`Location` não é exposto); ambos são barreira, e a evidência registra a exceção e o status 3xx dos saltos.

## Consequências

- A tabela de parada de `docs/S0-SONDAS.md` é substituída por esta regra; a seção "Rodada 2 (S0b)" lista os hosts a
  resondar. Não é nova tentativa após recusa: nenhum deles recusou o produto.
- Os hosts com barreira na rodada 1 (TRF2 servicos 503, TRF3 timeout, TRF2 portal `BlockedHost`, TJSP CAPTCHA)
  ficam fora, sem nova tentativa. O TJSP tem barreira anterior do produto; os demais, recusa registrada.
- O orquestrador da rodada 1 (`s0_runner.py`, ramo `auditoria/s0-rodada1`) é substituído por
  `scripts/s0_orquestrar.py`, que aplica esta regra, pede cada URL uma vez, lê o robots uma vez por host e recebe as
  barreiras anteriores por arquivo de entrada.
- A regra invariável 3 não muda: barreira registrada não se repete por outra rede, rota ou identidade.
- Fora do escopo: POST/sessão para fonte-sonda e endpoints de resultado (S0b, parte 2).
