# 0011 - Instalacao transacional de snapshots

Diretorio, arquivo local e download de release convergem para a mesma instalacao. Validacao, reconstrucao de ementas STJ, anexacao de registros, copia de todas as evidencias e reconstrucao dos indices ocorrem em staging no mesmo volume do destino. Uma falha nessa preparacao preserva o destino e nao anuncia rollback.

Apenas depois da preparacao completa, as conexoes sao fechadas e os componentes originais (banco e arvore integral de blobs) sao guardados por renomeacao. Cada componente preparado e publicado por substituicao atomica. Falhas posteriores restauram os componentes originais efetivamente movidos; os backups completos sao mantidos no sucesso. Falha na propria restauracao e reportada explicitamente, preservando os backups disponiveis.

A garantia cobre excecoes durante uma instalacao exclusiva, sem escritores concorrentes. As renomeacoes do banco e dos blobs sao operacoes separadas; nao constituem uma unica transacao de filesystem contra encerramento abrupto do processo ou queda de energia. Nao altera os criterios de verificacao.

Regressoes comparam presenca e SHA-256 de todos os arquivos locais, incluindo o banco e evidencias fora do inventario recebido, apos falhas de validacao, reconstrucao, copia, backup, substituicao, indice e reabertura, nas tres entradas suportadas.
