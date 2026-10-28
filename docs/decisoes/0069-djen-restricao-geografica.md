# 0069 — DJEN: restrição geográfica geral não é recusa para a regra 3

Estado: aceita. Decisão do titular (Ricardo Peres Freoa) em 27/10/2026, registrada pelo supervisor.

## Contexto

A API pública de comunicações processuais do CNJ (DJEN, `comunicaapi.pje.jus.br`) responde 403 a origens
fora do Brasil. Em 27/10/2026, a ferramenta de pesquisa de um agente, executada em nuvem fora do Brasil e
fora do produto, leu o `robots.txt` desse host e recebeu 403 da borda. Na rodada 2 do PR #14, o auditor
entendeu que um acesso posterior do produto a partir do notebook do titular, no Brasil, seria troca de IP
ou rota depois de recusa conhecida, vedada pela regra invariável 3 e pela decisão 0067.

## Decisão

1. Restrição geográfica geral, aplicada pela fonte a toda origem fora do Brasil e não dirigida ao produto,
   ao seu User-Agent ou ao seu titular, não é recusa para os fins da regra 3 quando o acesso parte do
   ambiente normal de operação do produto no Brasil.
2. Ambiente normal de operação é o computador do titular ou outro ambiente fisicamente no Brasil que o
   titular designe por escrito. Proxy, VPN, túnel ou qualquer rota que faça origem estrangeira parecer
   brasileira continua vedado.
3. O acesso sai pelo transporte comum, com o User-Agent identificado, sem repetição automática e sem
   alteração de cabeçalhos.
4. Se o acesso a partir do Brasil receber recusa (403, desafio, bloqueio), a fonte fica registrada como
   barreira; não há nova tentativa por outra rede, rota ou identidade, e o caminho passa a ser a sessão
   assistida (0067) ou o pedido formal de acesso.
5. O 403 recebido em nuvem em 27/10/2026 fica registrado como o que é: leitura de ferramenta de pesquisa,
   fora do produto e fora do Brasil, sem valor de evidência para o produto.
6. A decisão vale para o DJEN. Estendê-la a outra fonte exige nova decisão, com prova de que a restrição
   é geográfica e geral.

## Consequências

- O DJEN volta ao roteiro da S0 e ao escopo do I3.4, sondado só a partir do notebook do titular.
- A regra invariável 3 não muda de redação; esta decisão fixa sua interpretação para restrição geográfica
  geral.
- Agentes em nuvem não acessam o DJEN, nem por ferramenta de pesquisa.
