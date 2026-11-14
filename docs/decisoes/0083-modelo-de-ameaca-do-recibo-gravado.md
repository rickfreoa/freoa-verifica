# 0083 — Modelo de ameaça do recibo gravado (IL.3-c, após o teto do D5)

10/11/2026. Decisão do titular (Ricardo Peres Freoa), redigida pelo supervisor.
Aplica o D5 do plano 1.4: após o teto sem resolução, reduz-se o escopo com
registro; o teto não equivale a aprovação.

## 1. Fato

O IL.3-c (PR #41) passou por r1, r2, r3, passe final e sete conferências do
auditor (Codex, somente leitura). Cada conferência confirmou as correções
anteriores e apontou a ocorrência seguinte da mesma classe: recibo Câmara inválido
encoberto, absorvido ou reconstruído com metadado substituto. As correções estão
na 0082, itens (i) a (vii). Nenhuma rodada demonstrou `verified` indevido. Os dois
resíduos da sétima conferência exigem recibo gravado adulterado:

- B1: Content-Length declarado incompatível com os bytes, aceito na conferência
  offline de recibo gravado (o transporte de aquisição faz esse confronto);
- B2: `edition_id` inexistente em snapshot recebido, encoberto pela mesclagem
  antes da conferência relacional.

## 2. Decisão

A conferência de recibo gravado da Câmara tem este escopo:

1. Dentro: inconsistência entre obtenções distintas dos mesmos bytes; recibo que
   o transporte não produziria nos campos que afetam descoberta, interpretação,
   identidade, instante e atribuição; tudo o que a 0082 já conferir.
2. Fora: adulteração deliberada do banco do home local, cujo controle é o acesso
   ao próprio home; e adulteração de snapshot cuja integridade a instalação
   garante por digest na lista embutida e attestation antes de qualquer mesclagem.
3. B1 e B2 passam a pendências de endurecimento, não bloqueadoras do IL.3-c.

## 3. Premissa a verificar

A exclusão do snapshot vale só se a instalação recusar, antes de `_merge_attach`,
todo pacote cujo digest não conste da lista embutida ou cuja attestation falhe,
inclusive na instalação por arquivo local. Se o passe final demonstrar caminho de
instalação sem essa verificação, B2 volta a bloquear, salvo correção.

## 4. Limites

- Continua bloqueador, dentro do escopo, qualquer achado que demonstre `verified`
  indevido, ou persistência, publicação ou confirmação a partir de resposta que o
  transporte produziria.
- Não dispensa: passe final independente sobre esta decisão e sobre o objeto
  final; suíte completa e CI verdes (matriz instalada, `repositorio`, lint);
  ausência de regressão de desempenho que impeça o CI.
- Não altera a matriz IL.1, os pisos, a reserva nem o contrato. A rota Câmara
  continua `nao_apurada` até a apuração do IL.3-c.
