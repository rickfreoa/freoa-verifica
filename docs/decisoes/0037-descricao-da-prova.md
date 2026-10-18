# 0037 — A descrição da prova corresponde ao documento entregue

Data: 18/10/2026 · Versão: 1.2.0 · Origem: avaliação externa (A1, A2, A3, A5, A12)

## Contexto

Autenticar os bytes da captura não basta: o documento selecionado e o rótulo devolvido também
precisam corresponder a ela. Até a 1.1.0, `obter_decisao` trocava a parte ausente por outro
documento sob o rótulo pedido, resolvia identificador oficial sem tribunal com `fetchone()`, chamava
de `inexistente` a ausência no banco local, perdia a espécie monocrática (o conector STJ a normaliza
para `monocratica`, valor que a ingestão não reconhecia) e classificava como inteiro teor qualquer
texto acima de 500 caracteres (duas súmulas do STF estavam assim no snapshot 1.1.0).

## Decisão

1. `obter_decisao(id, parte, tribunal=None)`. Identidade é tribunal + identificador. Mais de um
   registro → `ambiguous` com candidatos, sem texto. Tribunal informado é conferido também quando o
   id interno resolve.
2. Ausência no banco → `nao_encontrado_no_acervo` com `escopo: acervo_local`. `inexistente` fica
   reservado à negativa oficial delimitada (decisão 0023).
3. Parte não capturada → `parte_indisponivel`, `parte_entregue: null`, `partes_disponiveis`. Toda
   resposta traz `parte_solicitada`; o sucesso traz `parte_entregue` igual a ela. Parte fora do
   vocabulário é entrada inválida.
4. Espécie declarada pela fonte prevalece (`monocratica`, `repercussao_geral`); a inferência por
   classe e órgão é o residual. Vale para ingestão, rótulo exibido e filtro SQL (`fv_authority` recebe
   `d.kind`). `tema` genérico não prova repetitivo nem repercussão geral.
5. `inteiro_teor` só quando o perfil declara texto integral (`_PERFIS_INTEIRO_TEOR`) ou a fonte o
   marca em `metadata["documento"]`. Comprimento não decide.
6. `DERIVED_VERSION` 4. `fv acervo reconstruir` reclassifica monocráticas e corrige súmulas gravadas
   como inteiro teor (documento, nível de prova e FTS).

## Consequências

Consumidores que liam `status == "inexistente"` em `obter_decisao` passam a ver
`nao_encontrado_no_acervo`. Homes 1.1.0 respondem `ACERVO_DESATUALIZADO` até reconstruir ou instalar
o snapshot 1.2.0.
