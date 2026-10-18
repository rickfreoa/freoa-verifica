# 0039 - Atualização STJ/STF sem limpar checkpoint

Achado A4: o checkpoint `resource:{id}:{max_itens}` do STJ pulava o recurso quando o arquivo local conferia com o hash salvo, e um segundo cache (`prior`) reaproveitava bytes de capturas anteriores do mesmo recurso. Recursos mensais que o STJ corrige ficavam congelados até alguém limpar o checkpoint.

**Checkpoint com metadados.** O checkpoint registra `meta` (`last_modified`, `metadata_modified`, `size`, `hash` do CKAN, quando existirem) e só vale se todos forem iguais aos atuais. O mesmo filtro vale para o caminho `prior`. Checkpoints anteriores a esta decisão não têm `meta` e são rebaixados uma vez.

**Revalidação obrigatória.** Os dois meses mais recentes do pacote (por nome AAAAMM) e todo recurso cuja última captura bem-sucedida tenha mais de 30 dias são sempre baixados de novo, ignorando checkpoint e `prior`. Sha256 igual ao do checkpoint: só se atualiza o carimbo (`revalidado_em`, `ultima_captura_ok`), sem reprocessar registros. Sha256 diferente: os registros passam pelo caminho de indexação existente (`_put`), que substitui o documento da decisão pela chave documental; os bytes antigos continuam em `resource_dir` por sha256. O cache de 24 h do `package_show` continua (é TTL, não congelamento).

**Estado por recurso.** O payload do `sync_state` traz `ultima_tentativa`, `ultima_captura_ok`, `sha256`, `revalidado_em` e `meta`. Falha na revalidação grava `indisponivel` preservando `ultima_captura_ok` e `sha256`; nunca apaga a captura boa nem vira "sem mudança". `fv doctor` expõe `stj_atualizacao: {ultima_captura_ok, atraso_dias, ultima_tentativa}` no nível superior (chave nova; ausente quando nunca houve captura), com a captura bem-sucedida mais recente entre os recursos.

**STF súmulas e SV.** `state.done()` deixa de bastar: checkpoint com mais de 30 dias (`updated_at`) é recapturado e reingerido pelo mesmo caminho de indexação (que substitui o documento do mesmo tipo). O sha256 da captura fica no payload do checkpoint.

Limite conhecido: a seleção "dois meses mais recentes" usa o nome do recurso; pacote sem recursos mensais continua `indisponivel`.
