# 0063 — Media type estrito, texto a todo parser e guarda em toda chamada

Data: 20/10/2026 · Versão: 1.3.0 · Origem: auditoria final, rodada 13 (F-19, F-22, F-23; F-17 e F-15 residuais);
revê as regras 1, 6 e 7 da 0062

## Problema

1. **F-19.** `email.message.Message` aplica a RFC 2231: `charset*=us-ascii''utf-16le`, `charset*0=utf-16;
   charset*1=le` e continuações codificadas viravam `charset`. A declaração falsa escondia `<p>CAPTCHA</p>`: 200
   virava sucesso; 503 era repetido e terminava `fonte_fora`, sem bloquear o host.
2. **F-22.** O Planalto entregava ao parser isolado os bytes; o filho relia `<meta charset>` e "Ação" virava
   "AÃ§Ã£o", sem issue. Conectores JSON decodificavam os bytes como UTF-8 por conta própria.
3. **F-23.** `buscar_legislacao` e `buscar_normas_*` não tinham guarda por chamada e `_index_candidate_legis`
   engolia `Unavailable`: após CAPTCHA, novos pedidos ao mesmo host e `fontes.<id>.status = "ok"`.
   `StjConnector.sync` com estado seguia para outro pacote. `health()` chamado diretamente repetia sondas (F-17);
   a guarda da semente atravessava execuções (F-15).

## Regra

1. **Media type.** `Content-Type` é lido por gramática própria e estrita (RFC 9110 §5.6.6, §8.3.1):
   `type "/" subtype *( OWS ";" OWS [ token "=" ( token / quoted-string ) ] )`, nomes sem diferenciar
   maiúsculas, sem RFC 2231. Só o parâmetro de nome exatamente `charset` conta. `charset*`, `charset*N`,
   `charset` repetido com valores diferentes, parâmetro sem valor e media type malformado são `RespostaInvalida`
   (`resposta_inesperada`, nunca sucesso, nunca repetição), qualquer que seja o mime. `charset` repetido com o
   mesmo valor é aceito. Várias linhas de Content-Type são ambíguas também na resposta de erro.
2. **Marcador nos bytes.** Além do texto da interpretação única, a detecção de desafio procura os marcadores na
   vista latin-1 dos bytes: um rótulo ou BOM UTF-16/32 não esconde "CAPTCHA" escrito em ASCII. Só acrescenta
   detecção; corpo ilegível no charset declarado continua `resposta_inesperada`.
3. **Texto a todo parser.** Todo parser de resposta recebe `texto_do_response(resp)`; os bytes ficam para captura
   e hash. O parser isolado recebe o texto (`--texto`, UTF-8 só como transporte) e o filho não redetecta charset.
   JSON segue a mesma interpretação (cabeçalho, BOM, UTF-8 por omissão). Binários (DOCX, PDF) seguem em bytes:
   não têm charset. `parse_html_devices` retira a declaração `<?xml?>` antes do lxml, como `arvore_html`.
4. **Guarda por chamada.** `guarda.da_chamada()` abre uma `GuardaExecucao` na chamada externa e a compartilha com
   as aninhadas; ela morre com a chamada. Abrem-na: todo método da fachada `Verifica` (`_guardar`, e
   `ressincronizar_situacao`, `reconstruir_acervo`, `snapshot_install`), os métodos de entrada de todo conector
   (`health`, `search`, `resolve`, `fetch`, `fetch_situacao`, `sync`, `package_show`, por `Connector.__init_subclass__`)
   e cada método da semente. CLI, MCP e REST passam pela fachada.
5. **Falha da fonte não é falha do item.** Desafio, recusa e fonte fora (`ambiental_desafio`,
   `recusa_identificado`, `fonte_fora`) interrompem a fonte no controlador: `_index_candidate_legis` propaga,
   `buscar_legislacao` declara `fontes.<id>.status = "unavailable"` com categoria e evidência, `buscar_normas_*`
   declara `fonte` e marca os candidatos restantes como não indexados, `StjConnector.sync` registra o estado e
   propaga, `sincronizar` declara `parcial` quando o conector registrou falhas por recurso. Outra
   indisponibilidade do item (ex.: `resposta_inesperada` de um documento) fica no item, com categoria e evidência.

## Consequências

- Servidor que mande `Content-Type` fora da gramática (por exemplo, `text/html charset=utf-8` ou parâmetro sem
  valor) passa a ser `resposta_inesperada`, também para mime não textual.
- Duas chamadas externas sucessivas não herdam bloqueio: a segunda consulta a fonte de novo (F-15).
- Testes: `tests/test_fix17_charset_estrito.py`, `tests/test_fix17_texto_ao_parser.py`,
  `tests/test_fix17_controladores.py`, `tests/test_fix17_variantes.py`.
