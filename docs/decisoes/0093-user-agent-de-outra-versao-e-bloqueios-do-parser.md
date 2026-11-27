# 0093 - Recibos com User-Agent de outra versão e bloqueios por recurso causados pelo parser

Status: aprovada pelo titular em 27/11/2026 ("a8 com (a) e (b), 1 rodada Codex").

## Problema

Depois da instalação da 1.4.0a7 no home real do titular, a manutenção agendada passou a falhar em todas as obras:
revalidação 113/113 `indisponivel` e renovação 67/67 `persistencia_local_falhou`, na Câmara e no normas.leg.br.

1. **User-Agent no recibo da política.** O recibo do robots.txt (decisões 0080 e 0081, R2-2) registra o User-Agent que
   fez a obtenção, e `_conferir_com_o_corpo` exigia igualdade com o User-Agent da versão em execução. O UA contém a
   versão (`freoa-verifica/1.4.0a6 (+…)`); depois da atualização, o recibo ainda vigente da a6 virou
   `estado_invalido:politica_recibo_incoerente`, falha local que encerra o escopo dos dois hosts. A conferência vem
   antes do teste de validade, de modo que o recibo não expirava: o defeito era permanente. A mesma igualdade existia
   no recibo do termo da Câmara (`validar_recibo_do_termo`). A falha não aparecia na instalação limpa (sem recibo
   anterior), por isso escapou à CI e ao teste em Debian.
2. **Bloqueios por recurso herdados do parser.** Até a 1.4.0a6 a leitura recusava `encoding` como objeto único (lei de
   versão única, como a 15.177/2025) e o portão gravava bloqueio permanente do recurso (`resposta_inesperada`,
   `corpo_ou_mime`, sem `ate`). A 1.4.0a7 corrigiu a leitura (0092), mas os nove bloqueios do home real continuam e só
   a reabertura do host existia (`fv acervo abrir-normas-leg`); recurso bloqueado não volta a ser consultado.

## Decisão

1. **UA identificado de qualquer versão.** Os recibos aceitam o User-Agent identificado do pacote de qualquer versão
   (`freoa-verifica/<versão PEP 440> (+https://github.com/rickfreoa/freoa-verifica)`, `eh_user_agent_identificado`).
   O recibo continua sendo evidência do que de fato ocorreu: registra o UA que fez a obtenção, e uma atualização não o
   torna falso. Tokens, hash, tamanho, MIME, grupos, atraso e decisões continuam conferidos contra os bytes; UA fora
   do formato continua falha local terminal. A política obtida por versão anterior vale até o fim da validade (24 h) e
   é então relida com o UA da versão corrente.
2. **Reabertura dos bloqueios do parser.** `fv acervo abrir-normas-leg --decisao "…" --liberar-recursos-do-parser`
   libera, além do host, só os bloqueios por recurso da API de normas com `motivo` `resposta_inesperada` e `classe`
   `corpo_ou_mime`. Cada liberação vai para `reaberturas` com escopo `recurso`, a URL, o bloqueio anterior e a revisão
   (texto da decisão e referência a esta). Resposta que continue inesperada é bloqueada de novo na próxima obtenção.
   Sem a opção, o comando faz o que sempre fez.

## Consequências

- Atualizar o pacote não invalida mais o estado do portão. Para quem já atualizou para a 1.4.0a7, o paliativo é
  rodar de novo `fv acervo abrir-normas-leg`, que descarta a política antiga; com a 1.4.0a8 isso deixa de ser preciso.
- Liberar os bloqueios do parser custa no máximo uma consulta por recurso liberado, dentro do teto e do ritmo do
  portão.
- Testes de regressão: `tests/test_0093_ua_e_recursos_do_parser.py` (formato do UA; política e recibo do termo de
  versão anterior aceitos; UA fora do formato terminal; liberação seletiva e registrada; decisão obrigatória; opção da
  CLI). Os dois testes de versão anterior falham sem a correção.
