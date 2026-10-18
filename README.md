# FREOA Verifica

**Busca verificada de fontes primárias do direito brasileiro: legislação, normas da CVM e do CMN/BCB, jurisprudência e decisões administrativas, cada resultado acompanhado da prova de onde, quando e como foi conferido.**

Modelos de linguagem citam bem e conferem mal. O problema não está em encontrar um precedente plausível, mas em saber se o dispositivo existe, se o trecho é literal, se a redação estava em vigor na data relevante e se a decisão citada é aquela mesma. O FREOA Verifica responde a essas quatro perguntas separadamente, com evidência reproduzível, e se abstém quando a fonte oficial não permite conclusão.

## O que faz

| Pergunta | Ferramenta | Prova devolvida |
|---|---|---|
| Este dispositivo existe? Qual o texto? | `obter_dispositivo` | URL oficial, data de captura, SHA-256, caminho do dispositivo |
| O trecho citado é literal? | `verificar_citacao` | confronto textual versionado, diff quando divergente |
| Qual redação vigorava em certa data? | `historico_dispositivo` | redações sucessivas, atos alteradores, regras aplicadas |
| As citações deste parecer existem? | `verificar_texto` | status por citação: encontrada, inexistente, ambígua, indisponível |
| O que decidiram STJ, STF, TJSP, TCU e o Colegiado da CVM? | `pesquisar_jurisprudencia` | ementa, metadados, nível de prova, atributos de autoridade |
| Quais normas da CVM e do CMN/BCB tratam do tema? | `buscar_normas_cvm`, `buscar_normas_bcb` | ato, situação, texto consolidado oficial |

Estados possíveis em cada dimensão: `verified`, `divergent`, `not_found`, `ambiguous`, `unavailable`, `unknown`, `not_assessed`. Falha de rede nunca vira "não encontrado"; silêncio da fonte nunca vira "vigente".

Em `verificar_texto`, associações com confiança `provavel` recebem `requer_conferencia`, com interpretação proposta, alternativas e evidência disponível; somente citações `exata` podem receber `encontrada` ou `inexistente`.

## Instalação

Requer Python 3.11 ou superior.

```bash
pip install "https://github.com/rickfreoa/freoa-verifica/releases/download/v1.0.3/freoa_verifica-1.0.3-py3-none-any.whl"
# ou a partir do código-fonte:
pip install "git+https://github.com/rickfreoa/freoa-verifica@v1.0.3"
fv doctor
fv snapshot install                   # corpus semente (opcional, recomendado)
```

### Como servidor para clientes compatíveis com MCP

```json
{
  "mcpServers": {
    "freoa-verifica": { "command": "freoa-verifica-mcp" }
  }
}
```

Alternativa sem instalação permanente:

```bash
uvx --from git+https://github.com/rickfreoa/freoa-verifica@v1.0.3 freoa-verifica-mcp
```

O snapshot é um arquivo `freoa-verifica-snapshot-AAAAMMDD.tar.gz`, acompanhado de `.sha256`. `fv snapshot install` consulta a última release que contenha o snapshot, baixa ambos e confere o hash externo e o inventário interno antes da instalação. Para um pacote local: `fv snapshot install --arquivo freoa-verifica-snapshot-AAAAMMDD.tar.gz`. Os pacotes da release têm attestation de build do GitHub, verificável com ``gh attestation verify``; o snapshot é conferido pelo ``.sha256`` publicado na mesma release.

Para uso remoto: `fv serve-mcp --http --port 8765` (streamable HTTP). API REST: `pip install "freoa-verifica[server]"` e `fv serve-api`. Os dois recusam `--host` fora de loopback sem `--token` (MCP: também `FV_MCP_TOKEN`; REST: `FV_API_TOKEN`) e exigem `Authorization: Bearer` em toda requisição. Sem token, a API só atende cliente loopback direto (nunca atrás de proxy: use token e TLS no proxy). O corpo HTTP é limitado a 512 KiB.

### O que fica armazenado

Cada verificação grava uma execução (`run`) no banco local, imutável pelas operações usuais. Com o padrão `completo`, ela contém a citação, o trecho, a data, o modo, a citação reconhecida e o trecho oficial usado como evidência. Com `fv --sem-registro` (ou `FV_REGISTRO=sem_conteudo`, `Verifica(registro="sem_conteudo")`, `--sem-registro` em `freoa-verifica-mcp`), grava apenas: status e `reason_code` de cada dimensão, `algo_versions`, a política e os SHA-256 de citação, trecho, data e modo. Hashes de entradas curtas podem ser adivinhados por força bruta. As capturas oficiais (conteúdo público) são sempre armazenadas.

Retenção: `fv runs purgar --antes AAAA-MM-DD` reconstrói o banco sem as execuções anteriores e move o original (com `-wal`/`-shm`) para `purgados/<data>/` no home, imprimindo os caminhos para você apagar. Backups e cópias externas do diretório de dados são responsabilidade do operador.

## Exemplos

```bash
fv lei "art. 254-A da Lei 6.404/76"
fv historico "art. 2º, XVI, da Resolução CVM 160"
fv verifica "art. 116, parágrafo único, da LSA" --trecho "O acionista controlador deve usar o poder com o fim de fazer a companhia realizar o seu objeto"
fv verifica-texto parecer.md
fv juris "acordo de acionistas execução específica" --tribunais stj tjsp
```

## Cobertura e limites

A apuração de 18/10/2026 está em [docs/FONTES.md](docs/FONTES.md). O acervo é um recorte, sem garantia de completude histórica ou atualização contínua.

- STJ: Corte Especial, Segunda Seção, Terceira e Quarta Turmas; julgamentos de 10/06/2024 a 26/08/2026 no recorte medido. Espelhos e ementas não substituem inteiro teor. SCON/consulta pública apresentaram barreira de acesso.
- TCU: 2.000 itens percorridos, 1.800 identificadores distintos; julgamentos de 26/08/2026 a 14/10/2026. Sumários são tratados como ementas; ausência nesse recorte não demonstra inexistência.
- CVM Colegiado: semente de 40 decisões entre 19/12/2023 e 18/09/2026; processo, ata e item decisório são identidades distintas. Normas CVM dependem do documento e da associação segura das notas editoriais.
- STF: consulta por processo; 1.399 temas como metadados. Tema ou processo identificado não prova julgamento capturado. Busca textual sob WAF permanece indisponível.
- TJSP: consultas medidas sem julgamento identificado; formulário com CAPTCHA. STF, TJSP e STJ podem ficar indisponíveis por barreiras oficiais, sem contorno.
- DataJud confirma processo público, não julgamento. Os demais tribunais e segmentos não têm cobertura jurisprudencial demonstrada.
- Legislação: redações anteriores somente quando presentes na fonte capturada. História integral não garantida; data do ato não equivale a início da vigência. Identidade, texto e tempo são apresentados separadamente; tempo pode permanecer `unknown` com texto literal conferido.
- Suporte da fonte a uma proposição jurídica não é avaliado. Não há tratamento sistemático demonstrado de precedentes superados. Busca local vazia não prova inexistência.

`fv fontes` informa a cobertura declarada e o estado de acesso dos conectores. Falha, WAF ou CAPTCHA produzem indisponibilidade com motivo.

## Versão 1.0.3: correções da auditoria de 18/10/2026

A v1.0.2 emitia `verified` e `vigente_na_fonte` em dois casos de alcance sistêmico: o ADCT gravado nos caminhos da Constituição e atos CVM/BCB/CMN revogados tratados como vigentes. A v1.0.3 corrige ambos e os demais defeitos dos relatórios em [docs/auditoria/](docs/auditoria/), sob o plano [docs/PLANO-1.0.3.md](docs/PLANO-1.0.3.md), aprovado pelo auditor independente após três rodadas, e com quatro rodadas de auditoria do código integrado.

- O ADCT tem escopo próprio (`adct/artN`) e é citável.
- A situação cadastral oficial dos atos infralegais é capturada como evidência própria; revogação ou cancelamento bloqueiam vigência; situação ilegível nunca vira vigente.
- "Inexistente" exige obra capturada, íntegra e estruturada; obra fora do acervo é lacuna de cobertura; PDF sem estrutura é `DOCUMENTO_SEM_ESTRUTURA`.
- Data sem redação histórica não confronta a redação atual.
- Associação provável nunca produz conclusão definitiva, em nenhuma entrada.
- O recibo é gravado depois de todos os rebaixamentos e coincide com a resposta.
- Respostas parciais se declaram (truncamento, fontes não consultadas, remissões não resolvidas, candidatos não indexados).
- Modo remoto exige token em REST e MCP; limites de entrada na fachada; PDF e DOCX da CVM em processo isolado.
- `fv --sem-registro` não persiste o conteúdo consultado; `fv runs purgar` descarta execuções antigas.
- `fv acervo reconstruir` atualiza homes antigos; a instalação de snapshot de versão anterior reconstrói os derivados.

Limites que permanecem: a cobertura de jurisprudência continua concentrada em 2025 e 2026 (STJ) e sem STF; artigos de normas CVM publicadas só em PDF não são estruturados; a data de efeito das revogações não é informada pelas fontes, de modo que consultas a datas passadas de atos revogados respondem `unknown`; o conjunto de aceite das 34 consultas foi montado pelo mantenedor e não é independente.

## Resultados de avaliação

Medições de 18/10/2026, com conjuntos montados por quem não escreveu o código e oráculo extraído diretamente dos documentos oficiais capturados. As auditorias adversariais foram três rodadas sucessivas, cada uma com consultas novas; os defeitos que encontraram (nota editorial aceita como texto, evidência ausente aceita, traversal no snapshot, ano de normas CVM, negativa temporal indevida) foram corrigidos e reverificados antes desta versão.

| Conjunto | Resultado |
|---|---|
| Benchmark independente (116 casos): positivos com identidade e texto verificados | 56/56 |
| Benchmark independente: mutantes com falso `verified` (dígito, negação, dispositivo vizinho, redação revogada, ano ou norma inexistente) | 0/40 |
| Auditorias adversariais com consultas novas: positivos verificados | 48/49 (uma abstenção conservadora) |
| Auditorias adversariais: mutantes com falso `verified` | 0/143 |
| Decisões reais identificadas (com consulta às fontes) | 6/15 |
| Decisões inventadas rejeitadas com prova oficial | 2/5 |

Extrator de citações em prosa (v1.0.2), oito corpora adversariais independentes com 779 frases e expectativas congeladas: falsos `encontrada`/`inexistente` 0 (eram 250 na v1.0.1); erros em citações `exata` 0/424; recall 93,7%; nenhum status definitivo nos 181 controles sem norma.

Os números de decisões mostram o limite atual: sem consulta pública universal por número no STJ e no STF, a ferramenta informa "não confirmado no acervo" em vez de afirmar inexistência. A reconstrução histórica integral de redações não está demonstrada; quando falta a história anterior, a dimensão temporal permanece `unknown`.
## Arquitetura

Transporte com proteção contra SSRF e limites rígidos; conectores por fonte; parsers por perfil editorial com sentinelas que recusam colisão de endereços; armazenamento SQLite com bytes originais endereçados por hash e evidência imutável; motor temporal por eventos; uma fachada única servida por CLI, MCP e REST. Detalhes em [docs/ARQUITETURA.md](docs/ARQUITETURA.md).

## Licença

Código sob **AGPL-3.0-or-later**, com licença comercial disponível. Dados derivados conforme o regime de cada fonte. Ver [LICENCIAMENTO.md](LICENCIAMENTO.md).

O FREOA Verifica confere fontes; não emite parecer. A interpretação jurídica permanece com quem a assina.

Autor: Ricardo Peres Freoa.
`fv busca` e `fv juris`: busca local com flexão mínima por prefixos (mínimo de quatro letras), frases entre aspas exatas e ampliação AND→OR sinalizada por `modo_busca: "ampliada"` (ver seção Busca de `docs/ARQUITETURA.md`).

Para consultar normas no acervo instalado em somente leitura, defina `FV_READ_ONLY=1` antes de executar `fv verifica` ou `fv verifica-texto`. Esse modo não grava recibos de execução, não executa migrações ou reparos e não captura documentos ausentes. O banco deve estar previamente instalado e atualizado.

verificar_texto pressupõe texto jurídico; siglas em textos de outra natureza podem ser lidas como citações. Campos técnicos explicitamente rotulados exigem conferência; a forma jurídica usual `CC, art. 114` permanece exata sem esses marcadores. Veja a decisão [0020](docs/decisoes/0020-rotulos-e-contextos-tecnicos.md).
