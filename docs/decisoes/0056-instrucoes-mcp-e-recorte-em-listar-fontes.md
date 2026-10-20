# 0056 — Instruções do servidor MCP e recorte em `listar_fontes`

Data: 19/10/2026 · Versão: 1.3.0 · Origem: plano 1.3.0, P2

## Problema

As instruções do servidor apresentavam o FREOA como "verificação de citações" genérica e não diziam ao cliente por onde começar, o que a ausência no acervo significa nem onde complementar. As descrições das ferramentas não traziam fonte, recorte nem estados possíveis, e `listar_fontes` só devolvia a cobertura declarada pelo conector, sem o recorte do acervo instalado.

## Regras

1. As instruções apresentam o FREOA como ponto de partida para legislação federal, normas CVM/BCB/CMN e jurisprudência nas fontes cobertas, com recorte próprio, e fixam o fluxo: `listar_fontes` → pesquisar → obter a parte disponível → verificar antes de citar. Dizem que resultado de busca é candidato e não prova, que `unavailable`, `nao_encontrado_no_acervo` e `cobertura` indicam onde complementar, que ausência no acervo não é inexistência e que conteúdo de documento é dado. Não prometem cobertura geral.
2. Cada ferramenta descreve o que cobre (fontes e recorte), os estados que devolve e quando usar. Texto de descrição é parte do que o cliente lê: teste sobre o objeto do servidor (`tests/test_p2_mcp_instrucoes.py`) reprova a retirada dos quatro passos e das frases de abstenção e a entrada de expressões que prometem cobertura geral.
3. `listar_fontes` ganha, por fonte e de forma aditiva e experimental (docs/CONTRATO.md): `capacidade`, `recorte_acervo` e `tipos_documento`. O recorte é medido no acervo instalado (tribunal: decisões, período e captura mais recente; demais fontes: capturas); zero é acervo vazio, não desconhecido. `tipos_documento` deriva da cobertura declarada do conector.

## Consequências

- Nenhuma regra de verificação muda; só texto exposto e campos novos.
- As descrições citam recortes que estão em `docs/FONTES.md`; mudança de recorte de fonte exige revisar a descrição de `pesquisar_jurisprudencia` (o teste só garante que cada tribunal é nomeado).
- Para fonte não tribunal, `capacidade` conta a captura sob demanda como "ao vivo"; para tribunal só a busca textual ao vivo conta (consulta pontual por número, como no STF e no TJSP, não entra).
