# 0040 - Fronteiras locais (Host/Origin) e registro minimizado

## Host e Origin (achado A7)

Sem token, REST e MCP HTTP só conferiam o IP de origem; uma página aberta no navegador do usuário podia alcançar o serviço em `127.0.0.1` por DNS rebinding ou requisição cross-origin. A validação passa a viver em `freoa_verifica/fronteira.py`, função única (`validar`) usada por `rest.py` (middleware `fronteira`) e `mcp_server.py` (`_SoLoopback`, `_BearerMCP`). Opera sobre os cabeçalhos brutos do ASGI, para enxergar duplicatas.

**Modo sem token (só loopback).** Além do IP direto e sem `X-Forwarded-For`/`Forwarded` (401, como antes):
- `Host` obrigatório e único; formato estrito `127.0.0.1 | localhost | [::1]` com porta numérica opcional (até 65535). `localhost.evil.com`, `127.0.0.1.nip.io`, `localhost.` (ponto final), `host@x`, vazio, duplicado ou com caracteres inválidos: 403 `application/problem+json`.
- `Origin` ausente é aceito (clientes que não são navegador). Presente, deve ser `http://127.0.0.1[:porta]`, `http://localhost[:porta]` ou `http://[::1][:porta]`, sem caminho; `null`, `https://...` e qualquer outro: 403. `Origin` duplicado: 403.
- `Sec-Fetch-Site: cross-site`: 403.

**Modo com token.** Token continua obrigatório (401). `Origin` presente e não local é recusado (403), salvo se estiver, por igualdade exata, em `FV_API_ORIGENS` (lista separada por vírgulas; `create_app(origens=)` para testes). `Host` não é restringido: o modo com token serve uso remoto. A checagem de Origin vem antes da de token, para que navegadores de origem estranha nunca cheguem a testar o token.

Ordem no modo local: IP (401), depois Host/Origin/Sec-Fetch-Site (403).

Cliente HTTP local que envie `Host` diferente (proxy reverso, túnel, contêiner com porta publicada e `Host` do nome do serviço) deixa de funcionar sem token; a saída é usar token. Registrado em CHANGELOG.

## Registro minimizado por padrão (achado A8)

A decisão 0030 deixou `completo` como padrão: citações e trechos de consultas confidenciais iam para o banco local. O padrão passa a ser `sem_conteudo` (`registro.PADRAO`); `completo` só por opção explícita (`FV_REGISTRO=completo`, `registro="completo"`, `--registro-completo` no `fv` e no `freoa-verifica-mcp`). `--sem-registro` continua aceita (equivale ao padrão); as duas juntas são erro.

**HMAC no lugar de hash puro.** Em `sem_conteudo`, todo hash de conteúdo de entrada gravado é `hmac1:` + HMAC-SHA256 com segredo de 32 bytes por home, em `<home>/registro.key`: `request_hash` (antes sempre SHA-256 da requisição, mesmo em `sem_conteudo`) e `citacao_sha256`, `trecho_sha256`, `data_sha256`, `modo_sha256` em `request_json` (nomes mantidos por compatibilidade de leitura). A proposição não é persistida. O HMAC inclui o nome do campo como separador de domínio. O prefixo de versão distingue estes valores dos hashes antigos (64 hex sem prefixo). Em `completo` o `request_hash` segue SHA-256 (o texto está gravado de qualquer forma).

**Chave.** Criada com `os.open(O_CREAT|O_EXCL, 0o600)`, gravada e sincronizada; processo concorrente espera o conteúdo aparecer. Arquivo com tamanho diferente de 32 bytes é erro (`RuntimeError`), nunca regenerado em silêncio, para não invalidar hashes sem aviso. No Windows o modo POSIX não se aplica: a proteção vem da ACL herdada da pasta do perfil do usuário (`%LOCALAPPDATA%`). A chave não entra em snapshot (o snapshot exporta lista fechada de tabelas/colunas, sem `run`, e não copia o arquivo; há teste que varre diretório e `.tar.gz`) nem em log. Homes em memória (sem arquivo) usam chave efêmera.

**Fora do escopo do HMAC.** Hashes da evidência pública (bytes de documento oficial, capturas, `text_sha256` de redações e extrações) continuam SHA-256 puro: são verificáveis por qualquer pessoa.

**Retenção.** Execuções antigas gravadas em `completo` permanecem no banco até `fv runs purgar --antes DATA`. A purga mantém o comportamento existente (banco original movido para `purgados/<data>/` para exclusão manual) e ganha `--apagar-original`, que apaga o original movido (e a pasta) após a troca bem-sucedida e registra `original_apagado` em `purgas.jsonl`. Backups externos continuam responsabilidade do operador.
