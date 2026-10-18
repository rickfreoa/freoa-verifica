# 0021 — Situação da obra (contrato C2)

A situação cadastral de CVM, BCB e CMN vem de evidência própria capturada pelo
transporte e fica em `work_status` (migração 006): `revogada`, `cancelada`,
`vigente_declarada`, `ilegivel` ou `nao_aplicavel`, com texto oficial, ato
revogador, `data_efeito`, captura, hash e `lido_em`.

Fontes: a página do ato CVM é sempre capturada como evidência de situação, sem
substituir a captura normativa que seleciona a obra; para BCB/CMN valem os
campos `Revogado` e `Cancelado` do JSON oficial. Página ou campos ausentes,
ilegíveis ou fora do ar gravam `ilegivel`. Página lida sem marca de revogação é
`vigente_declarada`, que não prova vigência temporal e não eleva nenhum estado.
Obra CVM/BCB/CMN sem registro vale `ilegivel`. Planalto e Senado: sem efeito.

Propagação (`situacao.aplicar_situacao`, D = data consultada, hoje se omitida):

- revogada/cancelada com `data_efeito`: D >= efeito é `revogado`
  (`OBRA_REVOGADA_NA_FONTE`, texto oficial na evidência); D < efeito preserva a
  análise normal e acrescenta `REVOGACAO_POSTERIOR`.
- sem `data_efeito`: D = hoje é `revogado`; D passada é `unknown
  REVOGACAO_DATA_DESCONHECIDA` só se a análise normal daria vigente ou verified.
- `ilegivel` ou leitura com mais de 30 dias: rebaixa só vigente/verified para
  `unknown` (`SITUACAO_INDISPONIVEL`, `SITUACAO_DESATUALIZADA`). Revogado e
  `nao_existia` vindos do texto são preservados; revogação antiga continua valendo.
- A data do ato revogador nunca vira data de efeito. As fontes atuais não
  informam `data_efeito`; o campo existe para fontes que a informem.
- Vale também para citação só da obra (sem dispositivo). A identidade documental
  pode continuar `verified`.

`Verifica.ressincronizar_situacao()` relê a situação dos atos já no acervo
(insumo do snapshot). A tabela entra no snapshot.
