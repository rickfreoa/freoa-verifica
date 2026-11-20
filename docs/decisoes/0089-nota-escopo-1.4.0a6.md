# 0089 — Nota de escopo da 1.4.0a6 (decisão do titular, 20/11/2026)

## Fato

A auditoria Codex independente r1 (`docs/auditoria/0089/parecer-codex-r1.md`) apontou, além de defeitos de código,
provas obrigatórias do §3 que não podem ser produzidas no notebook do titular: o usuário não é administrador e o
Chrome e o Edge recebem extensão forçada por política de máquina (Fortinet), o que os exclui da sessão pela §2.2(3).
O auditor registrou que só decisão formal do titular reduz escopo.

## Decisão

Opção (b), aprovada pelo titular em 20/11/2026: a 1.4.0a6 é publicada com a sessão assistida **restrita ao Brave no
notebook do titular**, desde que os demais critérios da 0089 estejam cumpridos e a auditoria não aponte bloqueador
nos itens dentro do escopo. Ficam **não executados por impedimento do ambiente**, declarados no manifesto de aceite e
no registro da release, e **adiados para antes da 1.4.0 final**:

1. §3 item 7, acesso por segunda conta do Windows; §2.7(2) e §3 itens 7 e 13, monitoramento de gravações fora do
   perfil dedicado e de leituras do perfil pessoal por ferramenta do sistema (exigem privilégio de administrador).
2. §3 item 8, execução do aceite completo no Chrome e no Edge (recusados por política neste notebook; a recusa está
   provada).
3. §3 item 2, prerender (desativado no Brave) e Early Hints (exige origem HTTP/2 de teste).

Os cenários de gesto humano (recarga forçada; extensão desempacotada) **não** são adiados: executam-se com o titular,
antes da sessão manual da §3 item 17.

## Alcance

A decisão não altera regra da 0089 nem o critério de `verified`. Não dispensa as provas dentro do escopo, a matriz da
CI nem o parecer do auditor sem bloqueador. As leituras de execução do supervisor (manifesto de componente, §2.2(3)(c);
ordem da resposta do streaming, §2.5(2); comparação de passividade, §3 item 9) foram convertidas em texto normativo pela
decisão 0090, aprovada pelo titular em 20/11/2026.
