# Arquitetura

O FREOA Verifica responde a quatro perguntas distintas sobre uma citação jurídica: **identidade** (o ato, o dispositivo ou a decisão existem?), **texto** (o trecho é literal?), **tempo** (qual redação vigorava na data relevante?) e **suporte** (o trecho sustenta a proposição?). Cada dimensão tem estado próprio e evidência própria. A quarta permanece `not_assessed` nesta versão, porque depende de juízo que o código não deve simular.

## Camadas

```
transport ──► connectors/<fonte> ──► parsers/<perfil> ──► store (SQLite + blobs)
                                                              │
                     citation ──► verify ◄── temporal ◄───────┘
                                    │
                                 service ──► cli (fv) · mcp_server · rest
```

- **transport**: HTTPS com IP fixado por conexão e validação a cada redirecionamento (proteção contra SSRF e DNS rebinding), allowlist de hosts e prefixos por conector, MIME exato, limites de bytes, tempo e concorrência, rate limit e circuit breaker por host, sessão efêmera sem persistir cookies. Toda requisição passa por aqui.
- **connectors**: Planalto, Senado (dados abertos), CVM (normas e Colegiado), BCB/CMN, STJ (dados abertos), DataJud, TCU, TJSP e STF (portal). Cada conector declara cobertura e expõe `health` com teste positivo, negativo e documental. Desafio anti-robô, resposta vazia inesperada ou esquema inválido viram `unavailable(motivo)`, nunca "zero resultados". O projeto não contorna CAPTCHA nem WAF.
- **parsers**: perfis editoriais (HTML do Planalto, DOCX consolidado da CVM, JSON do BCB). Produzem árvore de dispositivos com caminho canônico (`art254-A.par1.inc2.ali-a`, com escopo de anexo), redações sucessivas (rasuras), anotações editoriais ("Redação dada pela…", com data quando o texto a traz), emendas citadas por leis alteradoras e blocos editoriais separados. Sentinelas recusam colisão de endereço, ordem anômala e truncamento; a quarentena é por dispositivo, salvo truncamento do documento.
- **store**: SQLite (WAL, chaves estrangeiras, migrações transacionais) e blobs endereçados por SHA-256. Capturas, extrações, redações e execuções são imutáveis por trigger. O resultado do parse é persistido integralmente, e a reconstrução usa apenas o que foi persistido; um teste garante que o veredito é idêntico antes e depois de reabrir o banco.
- **citation**: extrator determinístico de citações brasileiras (leis e atos infralegais, apelidos como "Lei das S.A.", dispositivos, classes processuais, súmulas, temas, acórdãos do TCU, PAS da CVM, número CNJ com dígito verificador).
- **temporal**: seleção de redação por data a partir de eventos. Estados: `verified`, `vigente_na_fonte`, `unknown`, `revogado`, `nao_existia`, `ambiguous` (ver `decisoes/0002`).
- **verify**: aplica bloqueios do parser antes de qualquer comparação; confronto textual versionado (`textcmp-1`) com fronteira lexical; evidência com URL, data de captura, hash, caminho e trecho.
- **service**: fachada única. CLI, MCP e REST são finos e devolvem o mesmo JSON.

## Modelo de dados

`source`, `work`, `alias`, `edition`, `capture`, `extract`, `parsed_document`, `provision`, `redaction`, `occurrence`, `event`, `relation`, `proceeding`, `decision`, `decision_document`, `theme`, `run`, `sync_state`, com índices FTS5 (`unicode61 remove_diacritics 2`) para redações e decisões. Identidade jurídica é distinta de URL e de hash; processo é distinto de julgamento.

## Autoridade

Atributos verificáveis (espécie, tribunal, órgão) e rótulo A–E derivado por regra pública e versionada (`autoridade-1`): A para súmula vinculante, controle concentrado e súmulas; B para temas de repercussão geral, repetitivos, IRDR e IAC; C para órgãos de cúpula; D para acórdãos de turma ou câmara; E para monocráticas e decisões administrativas. O rótulo é convenção de apresentação, não hierarquia jurídica universal.

## Corpus e snapshot

`fv sync --semente` popula o banco local a partir das fontes oficiais. `fv snapshot export` gera pacote novo, por inventário fechado de tabelas públicas, com `MANIFEST.json` e `SHA256SUMS`; `fv snapshot install` valida cada arquivo antes de instalar atomicamente. A confiança no pacote vem do canal autenticado (release do repositório oficial) e da attestation de build do GitHub.

## Uso de modelos de linguagem

Nenhum no caminho de execução. Coleta, parse, verificação, aritmética temporal e métricas são determinísticos. Quando a regra não decide (vacatio, remissões, efeitos), o resultado é `unknown`, com as flags e o material necessários para o juízo de quem consulta.
