# Plano e execução da 1.1.0

Data: 18/10/2026. Objetivo: fechar as lacunas que impediam o uso do FREOA Verifica no lugar do JusRatio, sem afrouxar o critério de `verified`.

## Lacunas de partida (1.0.3)

(a) jurisprudência limitada a quatro órgãos do STJ desde 06/2024, sem STF nem súmulas; (b) normas da CVM em PDF sem dispositivos; (c) revogações sem data de efeito; (d) BCB recusando tráfego e falha transitória apagando leitura válida; (e) conjunto de aceite montado pelo mantenedor; (f) ausência de PyPI. Além disso, verificou-se nesta versão que o texto coletado chegava ao modelo cliente sem proteção eficaz: um documento que contivesse o delimitador de abertura saía sem envelope.

## Referências externas avaliadas

- **google-research/harness2**: aproveitadas só a separação execução/julgamento/relatório e a regra de não deixar o executor ver o gabarito. Rejeitada a auto-otimização sem verdade de referência, incompatível com um verificador determinístico.
- **r4jurimetrics (ABJ)**: curso em R centrado no TJSP; sem aproveitamento direto para CVM, BCB, STJ ou STF.
- **Fontes abertas**: CKAN do STJ (espelhos e precedentes qualificados), portal de súmulas do STF (`sumariosumulas.asp?base=30|26`), campo `Atualizacoes` do BCB, dados abertos do Senado (`vides`, rejeitado como fonte de data de efeito), DataJud (só metadados, sem STF).
- **Sanitização**: os parsers já rodavam isolados e com limites; faltava proteger a saída. Foram portados os padrões do `freoa-document-sanitizer` do FREOA, apenas para sinalizar, sem reescrever texto oficial.

## Divisão de tarefas

| Agente | Papel | Entregas |
|---|---|---|
| Opus | orquestração, especificação, integração | sanitização de saída, isolamento de PDF, estrutura de PDF da CVM (0037), data de efeito do BCB (0035), preservação de leitura, ritmo BCB, bench, CMN pré-2020 e Circular BCB, documentação |
| Codex | auditor adversarial independente | oito rodadas sobre o código, com reproduções; nenhuma edição |
| Sonnet | desenvolvedor | precedentes qualificados do STJ e súmulas do STF (0036), situação estruturada, checkpoint por versão |
| Haiku | pesquisador de fontes, sem acesso ao código | conjunto-ouro de 60 casos, selado por hash |
| Cursor, Antigravity | — | indisponíveis (cota até 30/10 e esgotada por ~5 dias); tarefas redistribuídas |

## Critério de liberação

Suíte offline verde no HEAD final; parecer do auditor sem bloqueador; gold independente executado e reportado com seus próprios erros; wheel, snapshot e instalação conferidos em diretório novo.
