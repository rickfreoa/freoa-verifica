# 0058 — Nova requisição: mesma fonte só após ausência explícita; fontes distintas com declaração

Data: 20/10/2026 · Versão: 1.3.0 · Origem: auditoria final, rodada 3 (F-04, F-06, F-07); revista pelo supervisor (FIX7c)

## Problema

Três caminhos ainda produziam nova requisição, ou classificação ambiental, depois de uma falha: a semente retomava na mesma execução o alterador que acabara de falhar (F-04); resposta interrompida com linha de status ou cabeçalho incompletos virava `fonte_fora` repetível (F-06); o BCB engolia a falha da busca e consultava o endpoint de conteúdo, ocultando desafio, recusa e indisponibilidade (F-07).

A primeira redação desta decisão estendeu a regra também entre fontes distintas (Planalto → Senado; TJSP → DataJud). Isso foi além de F-05/F-07 e, com o Planalto recusando o cliente identificado (0048), eliminava a captura ao vivo de legislação federal pelo Senado, que aceita o cliente identificado.

## Regras

1. **Mesma fonte** (representações, endpoints ou rotas alternativas do mesmo órgão ou conector): só **ausência explícita** autoriza a requisição seguinte — resultado vazio estruturado, `http_404`/`http_410` ou resposta que declara não ter o ato (identidade não declarada). Desafio, recusa, `fonte_fora` esgotada e resposta inválida propagam com a categoria original.
2. **Fontes oficiais distintas** (outro órgão, outro conector): após `Unavailable` de qualquer categoria na fonte preferencial, a cadeia pode seguir para a próxima, desde que:
   - a resposta registre em `fontes_consultadas` (lista de `{fonte, resultado, motivo, categoria}`) a indisponibilidade de cada fonte anterior — nada é ocultado;
   - proveniência e rótulo do documento sejam os da fonte que efetivamente respondeu;
   - nenhuma fonte seja consultada duas vezes na mesma chamada;
   - exceção que não seja `Unavailable` (erro de programação, parse) continue interrompendo e vire indisponível, sem passar adiante.
3. Semente: `run` captura na entrada as pendências de alterador existentes e só retoma essas. Chave que falhou durante a execução (`_failed`) não é tentada de novo nela, em qualquer contexto de obra principal; a repetição é da próxima execução.
4. Transporte: o primeiro byte lido do soquete marca `resposta_iniciada` (evento compartilhado com o controlador externo de prazo). Qualquer interrupção depois disso — timeout, reset, prazo externo, mesmo com cabeçalho incompleto — é `RespostaInvalida` (`resposta_inesperada`) e não se repete. Conexão encerrada antes de qualquer byte continua `fonte_fora` repetível.
5. Aplicação: regra 1 em `BcbConnector.resolve` (só `http_404` ou busca vazia levam ao endpoint de conteúdo); regra 2 em `Verifica._capture_work` (Planalto → Senado → demais) e `Verifica._confirm_cnj` (TJSP → DataJud). No CNJ, a confirmação pelo DataJud após falha do TJSP vale como confirmação de existência do processo pelo DataJud (`processo_confirmado`, escopo "processo; não julgamento"), com a falha do TJSP em `fontes_consultadas`; nunca como texto do TJSP.

## Consequências

- Uma falha do BCB (mesma fonte) aparece como tal; deixa de ser mascarada por outra rota do mesmo órgão.
- Falha do Planalto não impede captura pelo Senado; a recusa fica declarada em `fontes_consultadas`, na evidência da verificação (`identity.evidence[].fontes_consultadas`, só quando houver fonte anterior indisponível) e em `verificar_texto`.
- `fontes_consultadas` é aditivo e experimental (`docs/CONTRATO.md`).
