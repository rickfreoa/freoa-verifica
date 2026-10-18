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

<!-- registro minimizado: ver seção abaixo -->
