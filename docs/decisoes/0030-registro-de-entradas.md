# 0030 - Registro de entradas

Politica `registro` em `{completo, sem_conteudo}` na configuracao do servico (`Verifica(registro=...)`, `FV_REGISTRO`, `fv --sem-registro`, `create_app(registro=)`, `create_mcp(registro=)`, `--sem-registro` no `freoa-verifica-mcp`). Padrao: `completo` (comportamento anterior).

Com `sem_conteudo`, `verify._persist` grava exatamente: status e `reason_code` de cada dimensao, `algo_versions`, a politica e os SHA-256 de citacao, trecho, data e modo. Nao grava citacao, trecho, `citation.raw`, evidencia textual (nem `trecho_oficial`, caminho ou URL). O resultado devolvido ao chamador nao muda; so o recibo persistido e reduzido.

Retencao: `fv runs purgar --antes AAAA-MM-DD` faz checkpoint do WAL, reconstroi o banco sem as execucoes anteriores (triggers de imutabilidade preservados), troca atomicamente e move o original, com `-wal`/`-shm`, para `purgados/<data>/` no home, imprimindo os caminhos para o operador apagar. A purga e registrada em `purgas.jsonl`. Backups externos sao responsabilidade do operador.
