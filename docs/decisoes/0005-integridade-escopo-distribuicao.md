# Integridade da evidência, escopo e distribuição

Data: 2026-10-18.

Toda verificação pela fachada autentica existência e SHA-256 do blob da captura efetivamente usada. O cache é invalidado por mtime, tamanho e ctime. Ausência e corrupção produzem indisponibilidade. As fachadas CLI, MCP e REST usam o mesmo serviço.

Dispositivo explicitado é parte da identidade solicitada: falha de sintaxe ou de resolução não pode ser reduzida à confirmação da obra. Notas editoriais CVM são separadas do texto normativo; associação incerta bloqueia o confronto no dispositivo ou escopo afetado. Notas sem escopo identificável bloqueiam o documento.

Snapshots exigem banco com caminho seguro, inventariado e hash obrigatório, sem fallback. O asset de distribuição é tar.gz com inventário e checksums internos, acompanhado de checksum externo. Extração recusa links, caminhos externos e tamanho total excessivo. A verificação desses hashes não equivale a assinatura ou attestation externa.

A decisão 0002 permanece: data do ato não prova início de vigência; a reconstrução histórica pode permanecer desconhecida.
