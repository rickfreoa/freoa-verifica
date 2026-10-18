# Busca rebaixa por item, não por resposta

Data: 18/10/2026. Ensaio real da v1.0.3 com rede: `buscar_normas_cvm("fato relevante")` respondia `unavailable/EVIDENCIA_AUSENTE` inteira porque alguns candidatos não tinham captura.

Busca e metadados produzem candidatos (AGENTS.md, regra 1). Em respostas de busca:

- candidato sem captura é devolvido como metadado, com `nao_indexado: true`, sem `work_id`, identidade, texto ou vigência;
- item indexado cuja evidência falha na autenticação (recibo ausente ou corrompido) é rebaixado individualmente para `nao_indexado`, com `motivo` igual ao código `EVIDENCIA_*`;
- havendo qualquer item não indexado ou truncamento, a resposta tem `status: parcial` (decisão 0024).

A regra não se estende a consultas que afirmam algo sobre uma obra ou dispositivo (`resolver_citacao`, `obter_dispositivo`, `historico_dispositivo`, `obter_evidencia`, verificações): nelas, evidência ausente continua tornando a resposta `unavailable`. Revoga, para buscas, o comportamento anterior em que um único recibo inválido derrubava a busca inteira (testes de `test_r6` ajustados).
