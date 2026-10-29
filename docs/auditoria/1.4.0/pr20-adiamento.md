# PR #20 - passe final com bloqueador; I2.7 adiado; S0b, I2.2 e I2.3 passam ao I3

Data: 29/10/2026. Autor: supervisor (Opus), sob o D5 do plano 1.4.0, a decisão 0074 (item 3) e decisão do titular
sobre a reorganização do I2.

## Histórico

A S0b parte 1 (leitura do robots.txt pelo RFC 9309, decisão 0071) foi adiada do I1 depois do PR #18
(`pr18-adiamento.md`) e retomada no I2 como I2.7, no PR #20 (ramo `feat/s0b-robots-r3`, base `701f029`): r1, r2 e
r3 COM BLOQUEADOR; a r3, por um único achado restrito a estado de versão intermediária nunca incorporada, levou à
decisão 0074 do titular (exceção ao teto com correção conservadora e conferência curta), cuja conferência resultou
"CORREÇÃO CONFERE" sobre `db3f63d`. Pareceres: `C:\dev\fv14-auditoria\parecer-pr20-r1.md`, `-r2`, `-r3`,
`-conf0074` e `-final` (fora do repositório, no computador do titular). As decisões 0071 (com emendas) e 0074 estão
no ramo e entram com a S0b refeita.

## Fato

O passe final independente sobre `db3f63d` terminou COM BLOQUEADOR: o avaliador RFC (`_permitido_rfc`) normaliza o
caminho, mas concatena a query sem normalização. Com corpo interpretável, registro coerente e SHA-256 conferido,
`Allow: /busca?x=/` e `Disallow: /busca?x=%2F` deixam `/busca?x=%2f` em `seguir` (o `robotparser` também permite), e
o orquestrador chama o instrumento para essa URL. Os requisitos do `pr18-adiamento.md` (coerência antes de qualquer
retorno permissivo, aquisição persistente exclusiva antes do pedido, sanitização estrutural com limitações
declaradas) foram dados como cumpridos pelo auditor; isso não elimina o achado novo.

## Decisão

1. Pela decisão 0074 (item 3) e pelo D5, o I2.7 é adiado, sem nova rodada nem nova exceção. O PR #20 não é
   incorporado; o ramo `feat/s0b-robots-r3` fica como base.
2. Por decisão do titular (29/10/2026), a S0b e os itens que dependem dela para sondar hosts passam ao I3, que começa
   por eles: I3.9 (S0b, ex-I2.7), I3.10 (conectores TST e STF acórdãos, ex-I2.2) e I3.11 (BNP/Pangea integral e
   informativos de STF, STJ e TST, ex-I2.3). O I2 fecha com o I2.4 (no que não depende de fonte nova), o I2.5 e o
   I2.6, com as reduções no manifesto e no rótulo.
3. Nenhuma sonda nova até o I3.9 ser incorporado.

## O que o I3.9 precisa resolver antes de código

- Normalizar a query, como o caminho, na comparação do robots (octetos não reservados decodificados, caixa
  hexadecimal uniforme), preservando a distinção entre `/` e `%2F`, com regressão na decisão composta e no
  orquestrador. A identidade de requisição do transporte não muda.
- Revisar o restante do avaliador RFC com o mesmo critério (todo componente comparado passa pela mesma normalização).
- Rodadas novas do D5; o histórico do #17, do #18 e do #20 fica nos registros de adiamento.
