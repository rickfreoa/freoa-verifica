# 0035 — Data de efeito da revogação declarada pelo BCB

Data: 18/10/2026. Versão: 1.1.0.

## Problema

Atos BCB/CMN revogados respondiam `unknown` para qualquer data passada, porque a situação cadastral (`Revogado=true`) não diz desde quando. A resposta é segura, mas inútil para a pergunta mais comum: o ato estava em vigor na data do negócio?

## Decisão

O campo oficial `Atualizacoes` do JSON `exibenormativo` traz, para parte dos atos revogados, a entrada "Resolução CMN nº 5.295/2026 - Revogação total a partir de 1º/6/2026". Quando o ato está `Revogado=true` e há **uma única** entrada de revogação total:

1. o ato revogador é registrado em `ato_revogador`;
2. se a entrada declara "a partir de D/M/AAAA", essa data é a `data_efeito` (dado oficial, não inferência), e as regras já existentes de `_decidir` passam a responder `revogado` a partir dela e `vigente` com sinalização (`POSTERIOR`) antes dela.

## O que não muda

- Sem "a partir de", a data de efeito continua desconhecida: data de publicação, data do ato revogador ou epígrafe **não** substituem a data de efeito (vacatio, efeitos diferidos).
- Duas ou mais entradas de revogação, revogação parcial e entradas fora do padrão: nada é extraído.
- Planalto e CVM: sem fonte oficial estruturada de data de efeito; permanecem `unknown` para datas passadas de atos revogados.
- A leitura continua sujeita à autenticidade da captura e ao prazo de 30 dias.

## Alternativas rejeitadas

- Senado `vides`: dá a publicação da norma posterior, não o efeito.
- Publicação do ato revogador como cota inferior do efeito: correta na maioria dos casos, mas não demonstrada pela fonte; rejeitada pelo auditor (parecer 1.1.0, rodada 1).
