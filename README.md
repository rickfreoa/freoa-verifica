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
| O que decidiram STJ, STF, TJDFT, TJSP, TCU e o Colegiado da CVM? | `pesquisar_jurisprudencia` | ementa, metadados, nível de prova, atributos de autoridade |
| Qual o texto desta decisão? | `obter_decisao` | parte pedida e parte entregue declaradas; parte ausente é `parte_indisponivel`, nunca outro documento |
| Quais normas da CVM e do CMN/BCB tratam do tema? | `buscar_normas_cvm`, `buscar_normas_bcb` | ato, situação, texto consolidado oficial |

Estados possíveis em cada dimensão: `verified`, `divergent`, `not_found`, `ambiguous`, `unavailable`, `unknown`, `not_assessed`. Falha de rede nunca vira "não encontrado"; silêncio da fonte nunca vira "vigente".

Em `verificar_texto`, associações com confiança `provavel` recebem `requer_conferencia`, com interpretação proposta, alternativas e evidência disponível; somente citações `exata` podem receber `encontrada` ou `inexistente`.

## Instalação

Requer Python 3.11 ou superior.

```bash
pip install "https://github.com/rickfreoa/freoa-verifica/releases/download/v1.3.0/freoa_verifica-1.3.0-py3-none-any.whl"
# ou a partir do código-fonte:
pip install "git+https://github.com/rickfreoa/freoa-verifica@v1.3.0"
fv doctor
fv snapshot install                   # corpus semente (opcional, recomendado)
```

No Windows, [`scripts/instalar-freoa-verifica.ps1`](scripts/instalar-freoa-verifica.ps1) faz tudo de uma vez: cria o ambiente em `%USERPROFILE%\freoa-verifica`, exige e confere a attestation do wheel e do lock com o GitHub CLI (`gh`): sem `gh`, ou com a attestation inválida, a instalação é interrompida. A única exceção é o parâmetro explícito `-SemAttestation`, que prossegue com aviso e grava `attestation_verificada: false` ("PROVENIENCIA NAO VERIFICADA") na instalação; instala o pacote e o acervo vinculado; e só declara sucesso depois de conferir versão, acervo e `fv doctor`. Qualquer etapa que falhe interrompe a instalação com o nome da etapa. Um acervo anterior sem vínculo comprovado é preservado ao lado (`<home>.pre-<versão>-<data>`), e o snapshot vai para um diretório limpo. Execute com `powershell -ExecutionPolicy Bypass -File .\instalar-freoa-verifica.ps1`.

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
uvx --from git+https://github.com/rickfreoa/freoa-verifica@v1.3.0 freoa-verifica-mcp
```

O snapshot é um arquivo `freoa-verifica-snapshot-AAAAMMDD-<versão>.tar.gz`, acompanhado de `.sha256`. O pacote traz a lista dos snapshots oficiais (`freoa_verifica/data/snapshots-oficiais.json`, coberta pela attestation do wheel); `fv snapshot install` escolhe a release mais recente cujo snapshot conste dessa lista e recusa qualquer outro (`SNAPSHOT_NAO_VINCULADO`), salvo com `--aceitar-nao-vinculado`. Nesse caso, o acervo fica marcado `vinculado: false` de forma permanente, visível em `fv snapshot info` e `fv doctor`. Para um pacote local: `fv snapshot install --arquivo <arquivo>.tar.gz`.

Para uso remoto: `fv serve-mcp --http --port 8765` (streamable HTTP). API REST: `pip install "freoa-verifica[server]"` e `fv serve-api`. Os dois recusam `--host` fora de loopback sem `--token` (MCP: também `FV_MCP_TOKEN`; REST: `FV_API_TOKEN`) e exigem `Authorization: Bearer` em toda requisição. Sem token, a API só atende cliente loopback direto (nunca atrás de proxy: use token e TLS no proxy). Sem token, `Host` deve ser `127.0.0.1`, `localhost` ou `[::1]` (porta opcional) e `Origin`, quando presente, também local (defesa contra DNS rebinding); com token, `Origin` externo é recusado salvo se listado em `FV_API_ORIGENS` (`esquema://host[:porta]`, separadas por vírgula; formato inválido impede a inicialização). Não é CORS: a lista serve a clientes não-navegador que enviam `Origin`; não há resposta a preflight. Purga, instalação de snapshot e reconstrução recusam (`HOME_EM_USO_POR_OUTRO_PROCESSO`) se outro processo (servidor MCP/REST) estiver com o home aberto. O corpo HTTP é limitado a 512 KiB.

### O que fica armazenado

Cada verificação grava uma execução (`run`) no banco local, imutável pelas operações usuais. O padrão desde a 1.2.0 é `sem_conteudo`: grava apenas status e `reason_code` de cada dimensão, `algo_versions`, a política e, no lugar das entradas, HMAC-SHA256 (`hmac1:<hex>`) de citação, trecho, data, modo e requisição, com um segredo aleatório de 32 bytes por home em `<home>/registro.key` (modo 0600; no Windows a proteção vem da ACL herdada do perfil em `%LOCALAPPDATA%`). Quem não tem a chave não consegue confirmar uma entrada adivinhada por força bruta; a chave nunca entra em snapshot exportado nem em log, e apagá-la impede correlacionar execuções antigas. O registro `completo` (citação, trecho, data, modo, citação reconhecida e trecho oficial usado como evidência) só vale por opção explícita: `fv --registro-completo` (ou `FV_REGISTRO=completo`, `Verifica(registro="completo")`, `--registro-completo` em `freoa-verifica-mcp`). `--sem-registro` continua aceita e equivale ao padrão. As capturas oficiais (conteúdo público) são sempre armazenadas e seus hashes seguem SHA-256 puro. Execuções gravadas em `completo` por versões anteriores permanecem no banco até `fv runs purgar`.

Retenção: `fv runs purgar --antes AAAA-MM-DD` reconstrói o banco sem as execuções anteriores e move o original (com `-wal`/`-shm`) para `purgados/<data>/` no home, imprimindo os caminhos para você apagar (ou, com `--apagar-original`, apaga o original após a troca bem-sucedida). Backups e cópias externas do diretório de dados são responsabilidade do operador.

## Exemplos

```bash
fv lei "art. 254-A da Lei 6.404/76"
fv historico "art. 2º, XVI, da Resolução CVM 160"
fv verifica "art. 116, parágrafo único, da LSA" --trecho "O acionista controlador deve usar o poder com o fim de fazer a companhia realizar o seu objeto"
fv verifica-texto parecer.md
fv juris "acordo de acionistas execução específica" --tribunais stj tjsp
fv juris "0713166-62.2018.8.07.0000"          # número CNJ: só o próprio processo
fv decisao <id> --parte inteiro_teor --tribunal tjdft
```

`fv busca` e `fv juris`: busca local com flexão mínima por prefixos (mínimo de quatro letras), frases entre aspas exatas e ampliação AND→OR sinalizada por `modo_busca: "ampliada"` (ver seção Busca de `docs/ARQUITETURA.md`).

Para consultar normas no acervo instalado em somente leitura, defina `FV_READ_ONLY=1` antes de executar `fv verifica` ou `fv verifica-texto`. Esse modo não grava recibos de execução, não executa migrações ou reparos e não captura documentos ausentes. O banco deve estar previamente instalado e atualizado.

verificar_texto pressupõe texto jurídico; siglas em textos de outra natureza podem ser lidas como citações. Campos técnicos explicitamente rotulados exigem conferência; a forma jurídica usual `CC, art. 114` permanece exata sem esses marcadores. Veja a decisão [0020](docs/decisoes/0020-rotulos-e-contextos-tecnicos.md).

## Estado atual (1.3.0)

Cobertura medida e limites, fonte a fonte, em [docs/FONTES.md](docs/FONTES.md). Histórico de mudanças no [CHANGELOG](CHANGELOG.md).

| Fonte | O que o acervo e as consultas ao vivo entregam | Limite principal |
|---|---|---|
| Legislação federal (Planalto) | dispositivo com texto, redações e vigência na fonte | história anterior só quando presente na página capturada |
| CVM e CMN/BCB | normas com dispositivos e situação (revogação bloqueia vigência) | PDF da CVM com estrutura inferida; Circulares antigas sem texto no JSON oficial |
| STJ | espelhos de acórdãos (ementa) de quatro órgãos, 06/2024 a 08/2026 | sem íntegras; fora do recorte = `nao_confirmado_no_acervo` |
| STF | súmulas e súmulas vinculantes com situação; temas como metadados | busca textual livre sob WAF |
| TJDFT | API oficial: busca ao vivo, número CNJ exato, semente temática societária; decisões individuais com texto integral validado | acórdãos só com ementa (a API não traz a íntegra) |
| TCU | acórdãos de 2026 no recorte instalado | sem busca ao vivo; números fora do recorte não são achados |
| CVM Colegiado | 40 decisões (12/2023 a 09/2026) | sem cobertura histórica |
| TJSP, demais tribunais | consultas pontuais; DataJud confirma processo, não julgamento | barreiras oficiais (CAPTCHA) não são contornadas |

Suporte de uma fonte a uma tese não é avaliado; a classificação A–E é do produto e não garante aplicabilidade; ausência no acervo nunca prova inexistência. A triagem de conteúdo (`alertas_conteudo`, envelope `DOCUMENTO OFICIAL`) sinaliza padrões de instrução e caracteres invisíveis no texto coletado; é delimitação e triagem, não garantia de que o modelo cliente resista a injeção.

## Comparativo com o JusRatio (19/10/2026)

Conjunto-ouro de 44 casos montado sem leitura do código, com a resposta fixada pela fonte oficial (dois casos excluídos por não serem decisões), executado nos dois sistemas com as mesmas consultas. Metodologia, saídas brutas, juiz cego da pertinência temática e placar em [docs/auditoria/comparativo-120/](docs/auditoria/comparativo-120/).

| | FREOA 1.2.0 | JusRatio |
|---|---|---|
| Casos dentro do acervo do FREOA (35) | 34 | 35 |
| Não temáticos: dispositivos, normas, súmulas, números de processo (28) | 28 | 28 |
| Todos os casos, inclusive fora do acervo do FREOA (42) | 34 | 38 |
| Resultados temáticos úteis, juiz cego (pertinente ou parcial, 35) | 33 | 33 |
| Resultados temáticos estritamente pertinentes (35) | 21 | 25 |
| Item apresentado como se fosse outro | 0 | 0 |

Dentro do acervo, a única perda do FREOA é temática (legitimidade do sócio excluído): a decisão que a fonte
oficial indica como pertinente não está no acervo. Fora dele (súmulas do STJ, REsp e acórdão do TCU fora do
recorte, PAS de 2016 da CVM), o FREOA se abstém e declara a cobertura; o JusRatio localiza. Nas buscas temáticas,
o JusRatio ainda traz mais resultados estritamente pertinentes. Nas verificações, o FREOA entrega o que o JusRatio
não entrega: captura oficial com hash, dispositivo exato, vigência, negativa provada (art. 312 e 300-B da LSA) e
recusa de número CNJ com dígito inválido. Amostra pequena: o resultado não sustenta inferência estatística.

## Arquitetura

Transporte com proteção contra SSRF e limites rígidos; conectores por fonte; parsers por perfil editorial com sentinelas que recusam colisão de endereços; armazenamento SQLite com bytes originais endereçados por hash e evidência imutável; motor temporal por eventos; uma fachada única servida por CLI, MCP e REST. Detalhes em [docs/ARQUITETURA.md](docs/ARQUITETURA.md).

## Licença

Código sob **AGPL-3.0-or-later**, com licença comercial disponível. Dados derivados conforme o regime de cada fonte. Ver [LICENCIAMENTO.md](LICENCIAMENTO.md).

O FREOA Verifica confere fontes; não emite parecer. A interpretação jurídica permanece com quem a assina.

Autor: Ricardo Peres Freoa.
