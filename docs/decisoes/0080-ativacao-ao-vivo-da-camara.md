# 0080 — Ativação ao vivo da rota Câmara (Legislação Informatizada)

Supervisor (Opus). Versão 2, 08/11/2026, depois do parecer do Codex sobre a versão 1 (COM BLOQUEADOR, achados 1–11). Trilha IL.3-b (`docs/auditoria/1.4.0/il3-especificacao.md`). Normativos: `AGENTS.md`; 0045, 0048, 0075, 0077, 0078, 0079; matriz IL.1; D6. Não altera matriz, pisos, reserva, mutantes, `transport.py` nem `CONTRATO_VERSAO`. Qualificação continua `nao_apurada` até o IL.3-c.

## 1. Objeto

O conector `camara_legin` deixa de responder `ativacao_ao_vivo_pendente` e passa a obter ao vivo, pelo transporte comum e com o UA identificado da 0048, exclusivamente: (a) os endereços de conteúdo da gramática da 0077 §2, nas mesmas condições (hosts exatos, HTTPS, porta padrão, sem query de conteúdo, vínculo de descoberta, `max_redirects=0`); (b) `/robots.txt` de cada host; (c) a exceção administrativa do §3. Nada mais. Nenhum destino de redirecionamento é obtido, ainda que no mesmo host.

## 2. Pré-condições de ativação (ordem obrigatória; falha em qualquer uma impede a ativação)

1. Robots do host `www2.camara.leg.br` lido e decidido conforme §4.
2. Captura do termo pela exceção do §3, persistida íntegra (recibo, URL, instante UTC, status, MIME, tamanho, SHA-256, eventual data/versão exibida).
3. Revisão documental do termo capturado pelo auditor contra a síntese do §3.2; divergência material impede a ativação e exige revisão desta decisão.
4. Só então a ativação é registrada em arquivo de estado do home (`camara_ativacao.json`: hash do termo, hash dos robots, versão do produto, instante). Sem esse registro válido, o conector continua `ativacao_ao_vivo_pendente`.

## 3. Exceção administrativa do termo

1. Uma única URL exata: `https://www2.camara.leg.br/termo-de-uso-e-politica-de-privacidade/termos-gerais`. GET, HTTPS, sem query, sem fragmento, sem redirecionamento, pelo transporte comum, sujeita a robots (§4), ritmo (§5) e barreiras (§6). Caminhos vizinhos (inclusive o índice `/termo-de-uso-e-politica-de-privacidade`) são recusados antes do transporte. A exceção não habilita outro caminho nem faz do termo documento normativo; seu corpo não é parseado como legislação.
2. Síntese provisória do supervisor (leitura de 06/11/2026, a conferir contra a captura): informações publicadas de domínio público e gratuitas; reprodução condicionada à citação da fonte “Câmara dos Deputados”; trechos citados entre aspas, com fonte e autoria quando houver; a página lida não trata de acesso automatizado nem indica licença formal; não exibe data nem versão. O universo dessa leitura é só essa página; políticas vinculadas não foram examinadas.
3. Política de dados e de atualização: não localizei documento oficial que fixe frequência de atualização ou data de consolidação da Legislação Informatizada. Efeito: a ativação prossegue com essa lacuna declarada; o produto nunca infere tempestividade da disponibilidade de uma página; `captured_at` e a ausência de data de consolidação aparecem na evidência; a lacuna permanece pendência aberta (0077 §6) até evidência oficial.

## 4. Robots

1. **Grupos considerados.** Para cada host, o grupo selecionado pelo UA do produto segundo a RFC 9309 (correspondência do token do produto; na falta, `*`), mais, como sobreposição conservadora, o grupo nominal de bots de IA quando existir; a decisão é a mais restritiva entre os dois. Grupos nominais de outros agentes (SEO, regionais etc.) não se aplicam ao produto e não são somados. Na captura de 04–05/11: em `www.camara.leg.br`, o grupo de IA e o grupo `*` têm regras idênticas, nenhuma alcança `/legislacao` nem `/legislacao/busca`, e ambos contêm `Disallow: /*.pdf` (padrão sem `$`, interpretado como padrão, não como extensão terminal); em `www2.camara.leg.br`, o grupo `*` não alcança `/legin/fed/` nem o caminho do termo — o que se confere de novo na leitura viva.
2. **Leitura do sinal de IA.** O comentário do grupo nominal menciona treino de IA; as diretivas capturadas não proíbem os caminhos HTML usados; o UA do produto é diferente desses nomes. Isso não é manifestação geral da Câmara sobre acesso automatizado ou usos de IA, nem autorização. Registrado para eventual comunicação institucional, a critério do titular.
3. **PDF.** Nenhum PDF é obtido em `www.camara.leg.br`. A política do portal não se transfere a www2: anexos em www2 dependem da gramática, do vínculo de descoberta e do robots de www2, e continuam sem extração autorizada (pendência C13).
4. **Ciclo de vida.** Política por host com validade máxima de 24 h desde a obtenção (RFC 9309, §2.4), persistida com recibo, hash, instante, UA efetivo, grupos considerados e decisão por caminho; cada obtenção de conteúdo registra o hash da política que a autorizou. Expirada a validade, nova leitura obrigatória antes de qualquer obtenção; falha na releitura não reutiliza a autorização anterior. Ausência (404 ou outra), resposta inesperada, MIME incompatível, interpretação inconclusiva, `Crawl-delay` inválido ou falha de persistência ⇒ decisão fechada (`unavailable`, motivo `robots_inconclusivo` ou `robots_recusa`), sem obtenção.

## 5. Ritmo

1. Intervalo mínimo por host de `max(10 s, Crawl-delay aplicável dos grupos considerados)`, medido por relógio monotônico entre o início de requisições consecutivas efetivamente emitidas ao mesmo host, contando robots, termo, buscas, páginas de norma, textos, anexos e qualquer repetição interna.
2. Serialização por host entre chamadas, instâncias e processos do mesmo home, por trava de arquivo no home; sem paralelismo. Instrumento e produto compartilham a trava quando usam o mesmo home.
3. Teto por sessão do instrumento: 200 requisições somando os dois hosts; esgotado o teto, a sessão para com `teto_de_sessao`. Sessão do instrumento = uma execução da CLI. No produto, teto de 30 requisições por chamada pública; excedido, a chamada devolve o material obtido como parcial, com indisponibilidade explícita.
4. O controle fica fora de `transport.py` e é testado observando as requisições efetivamente emitidas (com relógio controlado).

## 6. Barreiras

1. 403, 429, desafio (inclusive com HTTP 200), qualquer 3xx, corpo vazio, MIME ou perfil incompatível, timeout, 5xx, ausência de resposta, falha de persistência ou de interpretação: registrar com motivo estável e categoria só quando demonstrada (0045), e parar.
2. Unidade interrompida: o host, pelo restante da sessão do instrumento; no produto, a barreira de 403, 429 ou desafio é persistida no home e bloqueia novas obtenções ao host até reabertura expressa por decisão registrada; timeout, 5xx e ausência de resposta bloqueiam o host por 1 h. Testes provam ausência de novas requisições após a barreira na unidade.
3. Material parcial nunca vira zero resultados, inexistência de alteração ou atendimento integral; a indisponibilidade aparece na resposta (0077). Sem troca de UA, IP, host ou rota; sem fallback para Senado, DOU, LexML ou Planalto; sem sessão assistida implícita.

## 7. Atribuição

Cada evidência de origem Câmara ganha o campo aditivo `atribuicao`: `{"fonte": "Câmara dos Deputados", "termo_url": <URL do §3>, "termo_sha256": <hash da captura do termo>}`. Vale em toda entrega de texto ou recorte da Câmara (Python, MCP, REST, respostas embutidas, cache, snapshot e reabertura), por evidência, preservando a origem quando houver várias fontes. Autoria só quando identificada no próprio documento, nunca fabricada; o texto usado no confronto não é alterado. Campos consumidos pelo FREOA preservados.

## 8. Captura para os conjuntos e D6

1. **Inventário.** O inventário é de normas (espécie, número, ano), não de URLs. As URLs são obtidas só pela cadeia de descoberta da 0077 (busca → página de norma → links publicados), preservando `href`, URL e hash da página de origem em cada passo. Não há fase de descoberta irrestrita. O inventário do desenvolvimento é revisado pelo auditor antes da obtenção.
2. **Desenvolvimento.** Capturado pelo supervisor/codificador, com home próprio de desenvolvimento.
3. **Reserva.** Capturada pelo guardião em sessão própria, com home, inventário, recibos, corpos, logs e snapshot sob guarda separada (`Claude_Externos/freoa-verifica/porta-l/reserva-home/`), inacessíveis ao supervisor e ao codificador. Ao supervisor chegam só: contagem de normas do inventário, contagem de obtenções por resultado (`ok`, `unavailable` por categoria, sem URL nem identificação) e um hash agregado de compromisso (SHA-256 da lista ordenada dos hashes individuais), sem lista individual. Relatório integral ao titular. Correções do produto só a partir do desenvolvimento. Contaminação segue o D6.
4. **Snapshot.** Recibos e vínculos recuperáveis, hashes conferidos na instalação, evidência adulterada recusada, `captured_at` e procedência originais preservados; instalação e reprocessamento não renovam captura nem qualificam rota; recursos fora da gramática ficam inventariados como não obtidos; modo local sem rede. O snapshot da reserva não é publicado nem misturado ao de desenvolvimento.

## 9. Regressões exigidas na implementação

Gramática (hosts, famílias, períodos, sufixos, rejeições antes do transporte); exceção administrativa (só a URL exata; vizinhos recusados; robots antes; falha impede ativação); robots reais (hashes conferidos; grupo IA = `*` no portal; PDF proibido no portal; www2 sem proibição para Legin) e sintéticos (`Allow`/`Disallow`, `*`, `$`, grupo do UA, ausente, malformado, recusado, expirado, `Crawl-delay` maior e inválido); ritmo (relógio controlado, limiares, concorrência, processos, tentativas internas, teto); barreiras (cada classe do §6; nenhuma requisição posterior; nenhum fallback); atribuição em todas as fachadas e caminhos; D6 (saídas sem URL, identificação ou hash individual da reserva); snapshot (adulteração, offline, preservação de `captured_at`); semântica (guardas 0075/0077/0078/0079 intactas; nenhum `verified` por captura, metadado ou nota; qualificação `nao_apurada`). Testes causais: liberar caminho vedado, retirar a espera, aceitar termo não preservado, seguir redirecionamento ou expor diagnóstico da reserva deve fazê-los falhar. Fixtures sintéticas rotuladas; reais intactas.

## 10. Questões abertas

- O termo não trata de acesso automatizado; a leitura adotada é do supervisor e cede a manifestação oficial em sentido diverso.
- Comunicação institucional à Câmara sobre o uso: a critério do titular.
- Política de atualização da Legislação Informatizada: não localizada (§3.3).
