1. **B2 — Bloqueador.** A vigilância cobre a alteração transitória **após a linha de base**, mas a redação não exclui expressamente uma resposta obtida durante o assentamento, quando uma extensão pode ter atuado e sido removida. Também falta sincronizar o processamento das notificações pendentes com a gravação. O [teste do Brave](C:/dev/fv14-0089/docs/auditoria/0089/teste-brave-2026-11-19.md:10) demonstrou a detecção da instalação observada, não esses dois limites.

   **Redação mínima:** “Somente pedidos iniciados após a linha de base são elegíveis. Antes da gravação, processar as notificações pendentes até uma barreira sincronizada; alteração, perda de eventos ou impossibilidade de estabelecer a barreira invalida as candidatas.”

2. **R4 — Resolvido.** A [linha 15](C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:196) inclui as representações simultâneas, mantém a mensagem em processamento na contabilidade e exige reserva antes da leitura e das alocações. O aceite depende da implementação desses limites.

3. **Extensões de componente — Resolvido.** A exceção exige cumulativamente `location` 5 e caminho dentro da instalação do navegador; extensão comum ou componente externo não satisfaz a regra. A política de instalação forçada também impede a abertura da sessão.

4. **Brave — Ressalva.** O teste não encontrou bloqueio do Shields nos recursos examinados e confirmou igualdade de bytes em um binário, mas não demonstra, para todos os casos, a afirmação de que o componente `Brave` nunca altera o corpo. Streaming e conferências de tamanho provam o corpo entregue pelo navegador; isoladamente, não demonstram ausência de transformação anterior.

   **Redação mínima:** “A não alteração do corpo pelo componente embutido é premissa do navegador confiável; o teste realizado não a demonstra universalmente.”

**BLOQUEADOR**