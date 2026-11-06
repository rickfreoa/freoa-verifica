# 0079 — Recortes e impedimentos Legin (r2)

Data: 2026-11-06. Correção da implementação da 0077/0078, solicitada pelo
parecer `C:\dev\_il\parecer-pr36-r2.md`. Não amplia capacidades nem altera
o critério de `verified`. Aceite continua dependente da auditoria independente.

1. Artigo agregado e caput são dispositivos distintos. O caput conserva somente
   a projeção inicial e sua própria âncora. O mesmo vale para o caput de outro
   nível expressamente nomeado em nota. O fallback legado exige ausência de
   descendentes estruturais e de rótulos de descendentes no texto disponível.
2. A nota terminal pertence ao sujeito declarado no padrão editorial completo
   (inclusive “caput do parágrafo/inciso/alínea”), resolvido na hierarquia corrente.
   Renumeração preserva o rótulo primitivo como dado, sem confundi-lo com o caminho
   atual. Associação incerta gera impedimento explícito. Notas, links e âncoras
   editoriais permanecem recuperáveis nos bytes capturados.
3. As anotações próprias não recebem eventos dos descendentes. Impedimentos de
   descendentes são registrados separadamente como issues do agregado; notas de
   ancestral impedem conclusões sobre a aplicabilidade do filho sem prova própria.
   Essa abstenção pode tornar inconclusiva uma leitura anteriormente afirmativa.
4. Veto sem caracteres alfanuméricos normativos é stub, inclusive com pontuação
   remanescente. Identidade, pontuação, nota e captura permanecem no modelo, mas
   não se entregam nem se confrontam como redação normativa. O accessor comum
   do modelo também recusa esse stub.
5. Histórico, resolução de citação, obtenção, busca local com data e seleção de
   versão anterior documentada passam pela admissão de leitura antes de publicar
   conclusão. Histórico impedido retorna `unknown`, linha vazia, flags e
   `needs_judgment=true`, preservando os eventos disponíveis. Não escolhe uma
   ocorrência duplicada. Notas editoriais Legin não habilitam histórico conclusivo
   com a data da obra como início do dispositivo alterado.
6. A gramática de citações aceita o sufixo literal de parágrafo (`§ 1-B`), sem
   descartar a letra nem degradar o pedido para o artigo. Isso permite exercer os
   caminhos do parecer nas fachadas públicas que recebem citação.

Não se alteram transporte, UA, fontes, dependências, contrato do consumidor,
ativação viva ou prova temporal para D. Parser `camara-legin-3`: modelos anteriores
exigem reprocessamento local; não são promovidos silenciosamente.
