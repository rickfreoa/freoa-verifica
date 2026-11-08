# 0080 — Ativação ao vivo da rota Câmara (Legislação Informatizada)

Supervisor (Opus), 08/11/2026. Trilha IL.3-b (`docs/auditoria/1.4.0/il3-especificacao.md`). Normativos: `AGENTS.md`; 0045, 0048, 0075, 0077 (rota, gramática estrita, `max_redirects=0`), 0078 e 0079; matriz IL.1 e regime D6. Esta decisão não altera matriz, pisos, reserva, mutantes, transporte nem `CONTRATO_VERSAO`.

## 1. O que se decide

O conector `camara_legin` deixa de responder `ativacao_ao_vivo_pendente` e passa a obter, ao vivo, pelo transporte comum e com o UA identificado da 0048, exatamente os endereços admitidos pela gramática da 0077 §2, nas mesmas condições (hosts exatos, HTTPS, sem query de conteúdo, cadeia de descoberta, `max_redirects=0`). Nenhuma família, sufixo, faixa de período ou host novo é admitido por esta decisão.

## 2. Fundamento e limites

1. **Termos de uso.** Lidos em 06/11/2026 os “Termos gerais” do portal da Câmara (`https://www2.camara.leg.br/termo-de-uso-e-politica-de-privacidade/termos-gerais`): as informações publicadas são de domínio público e gratuitas e podem ser reproduzidas desde que citada a fonte “Câmara dos Deputados”; trechos citados entre aspas, com fonte e autoria; não há cláusula sobre acesso automatizado nem licença formal; o termo não tem data nem versão. A ativação exige que o instrumento capture e preserve esse termo (bytes e hash) antes da primeira obtenção ao vivo, e que toda resposta que entregue texto da Câmara traga a atribuição “Câmara dos Deputados” em campo aditivo de fonte (já existente ou novo, aditivo). Esta decisão não atesta permissão jurídica além do que o termo diz.
2. **Robots.** Por host, lido e interpretado antes de cada sessão de obtenção, preservado como evidência; falha de leitura ou interpretação impede a consulta. Em `www.camara.leg.br`, o robots capturado em 04–05/11 tem um grupo nominal para bots de IA (entre eles `anthropic-ai` e `Claude-Web`), com o comentário “Evita que o conteúdo do site seja usado para treinar IAs”, e regras idênticas às do grupo `*`; nenhuma alcança `/legislacao` nem `/legislacao/busca`; ambos proíbem `/*.pdf`. O UA do produto não é nenhum desses nomes, e o uso é recuperação pontual para verificação, sem treino; ainda assim, a ativação respeita o grupo mais restritivo aplicável a qualquer leitura plausível: nenhum PDF é obtido em `www.camara.leg.br`, e se o robots vigente passar a proibir os caminhos usados a qualquer agente ou ao UA identificado, a rota vira `unavailable` com motivo próprio, sem nova tentativa. Em `www2.camara.leg.br`, nenhum `Disallow` do robots capturado alcança `/legin/fed/`; anexos PDF de www2 seguem a gramática da 0077 e continuam sem extração autorizada (pendência de C13).
3. **Ritmo.** O robots da Câmara só declara `Crawl-delay: 10` para alguns robôs de busca. O produto adota, por prudência e para todos os hosts da Câmara, intervalo mínimo de 10 s entre requisições ao mesmo host, uma requisição por vez, sem paralelismo, e teto de requisições por sessão do instrumento; o intervalo vale também para o produto em uso e é testado.
4. **Barreiras.** 403, 429, desafio, redirecionamento ou corpo fora do perfil: registrar e parar (0045), sem trocar UA, IP, host ou rota, e sem fallback para Senado, DOU, LexML ou Planalto.

## 3. Captura para os conjuntos (D6)

1. O supervisor e o codificador capturam, pelo instrumento, somente os documentos que o conjunto de **desenvolvimento** exige, com inventário prévio (lista de URLs derivada por descoberta, não fabricada) revisado pelo auditor antes da obtenção.
2. Os documentos exigidos pela **reserva** são capturados pelo guardião, em sessão própria, sem expor ao supervisor quais são; o supervisor recebe só contagens, hashes e falhas tipadas.
3. O snapshot local resultante serve ao modo local do executor; snapshot não renova `captured_at` (0077).

## 4. Questões abertas

- O termo não trata de acesso automatizado; a interpretação adotada (domínio público, citação da fonte, ritmo conservador) é do supervisor e fica sujeita a manifestação oficial em sentido diverso, que prevalece.
- O sinal de política contra treino de IA no robots do portal não alcança o uso pretendido, mas é registrado para decisão do titular sobre comunicação institucional à Câmara, se julgar conveniente.
