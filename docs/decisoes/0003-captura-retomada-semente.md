# 0003 — Captura limitada e retomada da semente

Data: 2026-10-17 (America/Sao_Paulo).

A detecção de desafio distingue conteúdo esperado de um formulário lateral. A inclusão isolada da biblioteca reCAPTCHA/hCaptcha não caracteriza desafio. Os índices CVM informam o marcador estrutural esperado; conteúdo ausente com sinal de desafio permanece indisponível. Status HTTP de falha e cabeçalhos de mitigação continuam sendo tratados conservadoramente.

O transporte usa deadline absoluto desde a entrada (inclui limitador, DNS, conexão, cabeçalhos, corpo e redirecionamentos). A leitura parcial usa read1; uma janela completa de 30 segundos com menos de 2.048 bytes/s interrompe o socket e produz TransporteLento. O limite externo de retorno não substitui o encerramento da conexão e a liberação do slot.

Falhas transitórias da semente são reagendadas ao fim da fila, por no máximo duas novas passagens, com backoff exponencial e espera até a reabertura dos circuitos. Checkpoints bem sucedidos são reaproveitados; o motivo terminal permanece registrado. As contagens finais de indisponibilidade consideram o estado terminal, sem somar cada tentativa.

O padrão STJ passa a coletar um recurso JSON mensal para cada um dos doze meses disponíveis mais recentes em cada órgão listado no corpus, em ordem decrescente. ZIPs históricos, dicionários e precedentes qualificados ficam fora dessa coleta padrão. Um --desde explícito na sincronização direta mantém a seleção temporal explícita. --max-itens limita registros por recurso, sem encerrar a coleta dos demais recursos/órgãos. package_show fica em sync_state por até 24 horas, com URL, hash e data; é cache de metadados, não prova documental. Recursos capturados têm checkpoint e hash próprio; a seleção de um julgamento é confrontada com seu identificador dentro dos bytes integrais do recurso oficial. O índice auxiliar STJ fica sob FV_HOME.

O benchmark aceita o rótulo decisao_falsa como decisão explicitamente falsa, sem reescrever o gold; indisponibilidade não constitui acerto negativo. Os resultados completos por caso e a divisão entre decisões reais e falsas ficam no relatório para diagnóstico.

Estas alterações não modificam o critério de verified. Testes internos e execução real não constituem parecer independente nem avanço automático de marco.

Espelhos STJ são classificados como ementa capturada mesmo quando o campo decisao excede 500 caracteres: comprimento não demonstra captura do inteiro teor do acórdão.
