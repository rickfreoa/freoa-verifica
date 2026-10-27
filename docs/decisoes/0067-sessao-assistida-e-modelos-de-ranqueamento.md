# 0067 — Sessão assistida e modelos de ranqueamento; revê as regras invariáveis 3 e 7

Data: 26/10/2026 · Versão: 1.4.0 · Origem: `docs/PLANO-1.4.0.md` (D2, D3 e seção 9), aprovado pelo titular

## Problema

A 1.4 passa a servir de fonte primária de pesquisa temática, o que exige duas coisas que as regras atuais não
admitem ou não distinguem:

1. Fontes com CAPTCHA ou WAF (TJSP em parte, STF, TJAP) ficam inacessíveis à coleta automática, e a regra 3 não diz
   se a ferramenta pode capturar o que o próprio usuário obteve, resolvendo ele mesmo a barreira.
2. A busca híbrida (D2) usa modelos neurais de embeddings e reranqueamento. A regra 7 ("nenhum modelo de linguagem
   no caminho de execução") os proíbe por inteiro; mantê-la e usá-los seria redefinição silenciosa.

## Regra

1. **Regra 3, nova redação.** A ferramenta não resolve nem contorna CAPTCHA, WAF, desafio ou controle de acesso;
   não lê o armazenamento de cookies, senhas ou perfis do navegador pessoal; não imita navegador nem troca de
   User-Agent, IP ou rota para superar recusa. Admite-se só a **sessão assistida**:
   - o usuário pede a sessão (`fv sessao <fonte>` ou a resposta MCP `requer_sessao_assistida`, que nunca a inicia
     sozinha);
   - a ferramenta abre contexto de navegador dedicado e isolado, sem o perfil pessoal;
   - o humano resolve a barreira; a ferramenta captura os bytes das respostas daquela sessão, com hash e
     `modalidade_acesso: sessao_assistida`;
   - cookies e segredos da sessão não entram em logs, evidências, fixtures nem snapshot, e são descartados ao fim;
   - não há repetição automática nem renovação silenciosa da sessão;
   - captura assistida não conta como cobertura automática: a matriz de cobertura e o bloco `cobertura` a declaram
     à parte (três denominadores de acesso: público humano, automático, assistido).
2. **Regra 7, nova redação.** Nenhum modelo generativo em caminho algum de execução. Modelos de ranqueamento
   (embeddings e reranker locais, sem geração de texto) só no plano de descoberta (`search`), e só quando habilitados
   pelo gate do plano. Nunca em `verificar_citacao`, `verificar_texto`, `obter_dispositivo`, `obter_evidencia`, na
   aritmética temporal, no parse ou na atribuição de estado; esses caminhos continuam deterministas por regra.
   Juízo pendente continua `unknown` com o material necessário.
3. **Recibo de descoberta.** Toda busca com modelo registra nome, versão e SHA-256 dos pesos, tokenizer,
   segmentação, runtime, precisão numérica, parâmetros, índice vetorial e regra de desempate. A promessa da
   descoberta é estabilidade dentro de tolerância publicada; a da verificação, igualdade exata.
4. **Escopo.** Pedidos de autos ficam fora do escopo: dependem de acesso autenticado e de documentos não publicados,
   e poriam credencial no caminho MCP. Resultados comparativos com outros serviços ficam nos testes e artefatos de
   bench, não no README nem no `FONTES.md`.

## Consequências

- `AGENTS.md` passa a trazer as redações acima das regras 3 e 7.
- A sessão assistida entra no incremento I3 com testes que provem: ausência de leitura de perfil pessoal, ausência
  de cookies em evidência, fixture e snapshot, e rotulagem da modalidade de acesso.
- A busca híbrida entra no I4 desligada por padrão; sem o gate, `modo_busca` continua `lexical`.
- A exclusão do modo opcional de contorno pedido anteriormente pelo titular é definitiva nesta linha de versões.
