# 0058 — Só ausência explícita autoriza nova requisição

Data: 20/10/2026 · Versão: 1.3.0 · Origem: auditoria final, rodada 3 (F-04, F-06, F-07)

## Problema

Três caminhos ainda produziam nova requisição, ou classificação ambiental, depois de uma falha: a semente retomava na mesma execução o alterador que acabara de falhar (F-04); resposta interrompida com linha de status ou cabeçalho incompletos virava `fonte_fora` repetível (F-06); o BCB engolia a falha da busca e consultava o endpoint de conteúdo, ocultando desafio, recusa e indisponibilidade (F-07).

## Regras

1. Depois de uma falha, só a **ausência explícita** autoriza nova requisição: resultado vazio estruturado, `http_404`/`http_410` ou resposta que declara não ter o ato (identidade não declarada). Desafio, recusa, `fonte_fora` esgotada e resposta inválida propagam com a categoria original.
2. Semente: `run` captura na entrada as pendências de alterador existentes e só retoma essas. Chave que falhou durante a execução (`_failed`) não é tentada de novo nela, em qualquer contexto de obra principal; a repetição é da próxima execução.
3. Transporte: o primeiro byte lido do soquete marca `resposta_iniciada` (evento compartilhado com o controlador externo de prazo). Qualquer interrupção depois disso — timeout, reset, prazo externo, mesmo com cabeçalho incompleto — é `RespostaInvalida` (`resposta_inesperada`) e não se repete. Conexão encerrada antes de qualquer byte continua `fonte_fora` repetível.
4. Aplicação da regra 1: `BcbConnector.resolve` (só `http_404` ou busca vazia levam ao endpoint de conteúdo), `Verifica._capture_work` (Planalto → Senado) e `Verifica._confirm_cnj` (TJSP → DataJud).

## Consequências

- Uma falha do BCB, do Planalto ou do TJSP aparece como tal; deixa de ser mascarada por resposta de outra rota.
- Fontes alternativas continuam permitidas após `cand is None`, 404/410 ou identidade não declarada.
