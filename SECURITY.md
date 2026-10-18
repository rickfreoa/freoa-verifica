# Segurança

Reporte vulnerabilidades em privado para rickfreoa@gmail.com, com descrição, passos de reprodução e impacto. Não abra issue pública antes da correção.

Escopo prioritário: SSRF ou fuga da allowlist do transporte; resultado `verified` indevido (falso positivo de identidade, texto ou tempo); vazamento de dados locais por snapshot, API ou MCP; execução de conteúdo de documento; negação de serviço por documento hostil.

A API REST recusa bind fora de `localhost` sem token. O servidor MCP não expõe URL arbitrária nem escrita administrativa.
