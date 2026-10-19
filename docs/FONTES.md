# Cobertura efetiva das fontes (1.2.0)

Estado do pacote e do snapshot 1.2.0 de 19/10/2026. Este documento descreve só o estado atual; o que mudou
em cada versão está no [CHANGELOG](../CHANGELOG.md) e as apurações anteriores em [docs/auditoria/](auditoria/).
Captura com hash prova a origem dos bytes; não implica vigência nem juízo jurídico.

## Acervo distribuído

Snapshot `freoa-verifica-snapshot-20261019-1.2.0.tar.gz` (617 MB; sha256
`926a6eb7fcf25ca4b7c8ec37f2804b1b9a32232fc67b3770ca05c2e4d2acc4e7`; `derived_version` 4), montado a partir do
snapshot 1.1.0 reprocessado com o código 1.2.0 e da semente TJDFT. Instalado em diretório novo: 826 obras,
35.419 decisões, 2.034 capturas no pacote, `vinculado: true`.

| Tribunal | Decisões | Recorte |
|---|---:|---|
| STJ | 32.668 | espelhos de 06/2024 a 08/2026 (Corte Especial, Segunda Seção, Terceira e Quarta Turmas) |
| TCU | 1.800 | acórdãos de 08/2026 a 10/2026 |
| STF | 799 | súmulas e súmulas vinculantes (temas de repercussão geral como metadados) |
| TJDFT | 112 | semente temática societária (API oficial) |
| CVM | 40 | Colegiado, 12/2023 a 09/2026 |

## Fonte a fonte

| Fonte | O que entra e qual prova | Limite |
|---|---|---|
| Planalto | HTML oficial com hash; árvore de dispositivos sob sentinelas (ADCT com escopo próprio); redações e atos alteradores presentes na página; parse em processo isolado com limites. | História anterior só quando riscada na própria página; data do ato não é início de vigência (decisão 0002). |
| Senado | JSON de identificação e datas de atos alteradores. | Metadados não substituem o texto normativo. |
| CVM normas | DOCX, PDF ou HTML oficial; página do ato capturada sempre (situação: revogação bloqueia vigência); PDF com estrutura inferida (decisão 0037). | Dispositivo junto a margem descartada fica `unknown`; redações antigas sem rasura ficam `ambiguous`. |
| BCB/CMN | JSON oficial; situação e data de efeito declarada da revogação (decisão 0035); parse em processo isolado. | Circulares cujo JSON só remete a outro endereço respondem `DOCUMENTO_SEM_ESTRUTURA`. |
| STJ espelhos | Recursos mensais do portal de dados abertos (Corte Especial, Segunda Seção, Terceira e Quarta Turmas); ementa com hash do recurso. Recursos recentes e capturas com mais de 30 dias são revalidados sem limpar checkpoint (decisão 0039). | Espelho comprova ementa, não inteiro teor. A coleção oficial de íntegras existe, mas a aquisição não está implementada. Fora do recorte: `nao_confirmado_no_acervo`. O portal não respondeu durante a montagem dos snapshots 1.1.0 e 1.2.0. |
| STJ precedentes qualificados | Código pronto (decisão 0036). | Não entraram no snapshot: o portal estava fora do ar. |
| STF | Súmulas e súmulas vinculantes com situação estruturada; temas de repercussão geral como metadados; decisões por processo quando há documento associado. | Busca textual livre sob WAF; tema identificado não prova julgamento capturado. |
| TJDFT | API pública oficial de jurisprudência (decisão 0041): busca ao vivo, número CNJ exato (decisão 0043) e semente temática societária. A resposta JSON inteira é a captura; cada decisão é vinculada ao registro por `uuid` e identificador. | Acórdãos só com ementa: a API não traz a íntegra. Texto de decisão individual só é inteiro teor com o número do processo, parte dispositiva e fecho. Processos em segredo de justiça não aparecem. |
| TCU | Acórdãos do recorte instalado (sumário tratado como ementa). | Sem busca ao vivo; números fora do recorte não são achados. |
| CVM Colegiado | Decisões da semente, com processo, ata e item como identidades distintas. | Sem cobertura histórica. |
| TJSP | Consultas pontuais por número. | Formulário com CAPTCHA; não há contorno. |
| DataJud | Confirma processo público por número CNJ. | Não confirma julgamento nem traz texto. |

## Limites gerais

- O acervo é um recorte; não há garantia de completude histórica nem de atualização contínua.
- Ausência no acervo local nunca prova inexistência. Negativas usam a fonte oficial e declaram o escopo
  (`nao_encontrado_no_acervo` com `escopo: acervo_local`; `nao_encontrado_na_fonte` com a fonte consultada).
- Suporte de uma fonte a uma tese não é avaliado; não há acompanhamento sistemático de superação de precedentes.
- A classificação A–E descreve a espécie e o órgão; não garante aplicabilidade atual.
- Busca temática é lexical (FTS5 com bm25 ponderado, tesauro determinístico e ordenação por raridade do termo);
  não é busca semântica. A pertinência temática medida está no [comparativo](auditoria/comparativo-120/).
- STJ (SCON e consulta pública), STF e TJSP podem impor barreiras oficiais; não são contornadas.
