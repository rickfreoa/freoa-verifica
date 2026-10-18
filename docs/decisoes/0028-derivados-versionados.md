# Derivados versionados e reconstrução do acervo

Data: 18/10/2026. Contrato C6 do plano 1.0.3 (F-F).

Modelo persistido, provisions, redações, ocorrências e o FTS de redações são derivados das capturas pelos parsers. Quando o parser ou o modelo muda (ADCT com escopo próprio, rubrica), um home antigo continua respondendo com derivados errados e sem aviso.

**Versão.** `derivados.DERIVED_VERSION` (2 nesta release) fica em `meta(key='derived_version')`, independente de `parser_version`. Home vazio nasce carimbado; home com obras e sem a chave (v1.0.2) é incompatível; versão diferente da do código também. Quando mudar parser ou modelo de forma que altere respostas, incrementar a constante.

**Home incompatível.** `buscar_legislacao`, `resolver_citacao`, `obter_dispositivo`, `historico_dispositivo`, `verificar_citacao` e `verificar_texto` respondem `indisponivel/ACERVO_DESATUALIZADO`. O aviso C7 (`acervo_incompleto`) ganha o motivo `derivados_desatualizados`. Capturas, recibos, `sincronizar` e `doctor` não dependem dos derivados e seguem funcionando.

**`fv acervo reconstruir [--com-situacao]`.** Com acesso exclusivo: copia o banco (backup SQLite) para uma pasta de trabalho no home; reprocessa as capturas com os parsers atuais na cópia (`reprocessar_capturas`; os blobs são lidos por ligação simbólica); `store.repo.sincronizar_derivados` remove os derivados antigos de cada captura (ocorrências, redações e dispositivos que só ela sustentava e que o modelo atual não tem) e regrava os do modelo atual, inclusive caminhos novos; o FTS é recomposto só com as redações não tachadas do modelo atual (captura mais recente de cada obra); `--com-situacao` relê a situação das obras apenas se houver rede; valida `PRAGMA integrity_check`, `foreign_key_check`, obras > 0 e contagens de obra, captura, extração, decisão, documento parseado e recibos; carimba a versão e só então troca o arquivo com `os.replace`. O original é preservado por ligação física (`verifica.sqlite3.pre-reconstruir-*`; apagar quando quiser). Qualquer falha antes da troca (inclusive captura que não reprocessa) deixa o original intacto; a reconstrução é idempotente. As triggers de imutabilidade de `redaction` são suspensas só dentro da sincronização e recriadas no `finally`.

**Snapshot.** O manifesto carrega o `derived_version` real do home de origem. Na instalação, se a versão do snapshot é maior que a local, os `parsed_document` locais das mesmas capturas são substituídos e os derivados são regravados do modelo substituído, na cópia de trabalho que depois troca o banco atomicamente. A versão do home só sobe se nenhum modelo local ficou fora do snapshot; senão o home segue incompatível e a mensagem manda reconstruir. Snapshot de versão menor rebaixa o home à versão dele. Reinstalar o mesmo snapshot é idempotente.

**Consequência.** `rubrica` e outros campos opcionais do modelo serializado não exigem migração SQL; a mudança de DERIVED_VERSION cobre a reconstrução.
