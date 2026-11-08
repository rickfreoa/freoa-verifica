# 0080 — Ativação ao vivo da rota Câmara (Legislação Informatizada)

Supervisor (Opus). Versão 3, 08/11/2026, depois dos pareceres do Codex sobre a v1 (achados 1–11) e a v2 (achados 12–15). Trilha IL.3-b (`docs/auditoria/1.4.0/il3-especificacao.md`). Normativos: `AGENTS.md`; 0045, 0048, 0075, 0077, 0078, 0079; matriz IL.1; D6. Não altera matriz, pisos, reserva, mutantes, `transport.py` nem `CONTRATO_VERSAO`. Qualificação continua `nao_apurada` até o IL.3-c.

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

1. **Grupos considerados.** Tokens avaliados: (a) o token do produto, `freoa-verifica`; (b) a lista fechada de tokens de IA desta decisão: `GPTBot`, `ChatGPT-User`, `Google-Extended`, `anthropic-ai`, `Claude-Web`, `ClaudeBot`, `Claude-User`, `Claude-SearchBot`, `Omgilibot`, `Omgili`, `FacebookBot`, `CCBot`, `PerplexityBot` (os dez nomes do grupo capturado e três tokens da Anthropic, acrescentados só por cautela). Nenhum token é inferido de comentários. Para cada token, a decisão é calculada independentemente pela RFC 9309: grupos cujo `User-agent` corresponde ao token (comparação sem distinção de caixa) são combinados; sem grupo correspondente, aplica-se `*`; dentro do conjunto, a regra de maior correspondência decide e, em empate entre `Allow` e `Disallow`, prevalece `Allow` (RFC 9309, §2.2.2). Resultado final: proibido se qualquer token resultar proibido; inconclusivo se qualquer token resultar inconclusivo; permitido só se todos permitirem. Grupos de outros agentes (SEO, regionais etc.) não entram. `Crawl-delay`: o maior valor válido entre os grupos efetivamente aplicados a qualquer token; valor inválido em grupo aplicado ⇒ inconclusivo. Testes cobrem grupos separados, repetidos, reordenados, ausentes, conflito `Allow`/`Disallow`, `$` e `*`. Na captura de 04–05/11: em `www.camara.leg.br`, o grupo de IA e o grupo `*` têm regras idênticas, nenhuma alcança `/legislacao` nem `/legislacao/busca`, e ambos contêm `Disallow: /*.pdf` (padrão sem `$`, interpretado como padrão, não como extensão terminal); em `www2.camara.leg.br`, o grupo `*` não alcança `/legin/fed/` nem o caminho do termo — o que se confere de novo na leitura viva.
2. **Leitura do sinal de IA.** O comentário do grupo nominal menciona treino de IA; as diretivas capturadas não proíbem os caminhos HTML usados; o UA do produto é diferente desses nomes. Isso não é manifestação geral da Câmara sobre acesso automatizado ou usos de IA, nem autorização. Registrado para eventual comunicação institucional, a critério do titular.
3. **PDF.** Nenhum PDF é obtido em `www.camara.leg.br`. A política do portal não se transfere a www2: anexos em www2 dependem da gramática, do vínculo de descoberta e do robots de www2, e continuam sem extração autorizada (pendência C13).
4. **Ciclo de vida.** Política por host com validade máxima de 24 h desde a obtenção (RFC 9309, §2.4), persistida com recibo, hash, instante, UA efetivo, grupos considerados e decisão por caminho; cada obtenção de conteúdo registra o hash da política que a autorizou. Expirada a validade, nova leitura obrigatória antes de qualquer obtenção; falha na releitura não reutiliza a autorização anterior. Ausência (404 ou outra), resposta inesperada, MIME incompatível, interpretação inconclusiva, `Crawl-delay` inválido ou falha de persistência ⇒ decisão fechada (`unavailable`, motivo `robots_inconclusivo` ou `robots_recusa`), sem obtenção.

## 5. Ritmo

1. Intervalo mínimo por host de `max(10 s, Crawl-delay aplicável dos grupos considerados)`, medido por relógio monotônico entre o início de requisições consecutivas efetivamente emitidas ao mesmo host, contando robots, termo, buscas, páginas de norma, textos, anexos e qualquer repetição interna.
2. Serialização por host entre chamadas, instâncias e processos do mesmo home, por trava de arquivo no home; sem paralelismo. Instrumento e produto compartilham a trava quando usam o mesmo home.
3. Teto por sessão do instrumento: 200 requisições somando os dois hosts; esgotado o teto, a sessão para com `teto_de_sessao`. Sessão do instrumento = uma execução da CLI. No produto, teto de 30 requisições por chamada pública; excedido, a chamada devolve o material obtido como parcial, com indisponibilidade explícita.
4. O controle fica fora de `transport.py` e é testado observando as requisições efetivamente emitidas (com relógio controlado).

## 6. Barreiras

1. Para esta rota e para a exceção administrativa, toda requisição é emitida com repetição interna do transporte desabilitada (`repeticao=0` ou equivalente por parâmetro existente, sem alterar `transport.py`); um único envio por URL por decisão.
2. Tabela exaustiva (produto e instrumento). "Host" = `www` ou `www2` individualmente. O bloqueio persistido no home é consultado antes de qualquer requisição, inclusive robots e termo, e vale para chamadas concorrentes, enfileiradas e após reinício; chamadas enfileiradas falham fechadas.

| Classe | Alcance | Persistência | Reabertura |
|---|---|---|---|
| 401, 403, 429, desafio (inclusive com HTTP 200), robots proibindo | host | persistente | só por decisão registrada (comando com identificador da decisão), seguida de nova leitura de robots |
| qualquer 3xx, corpo vazio, MIME ou perfil incompatível | recurso (URL) persistente; host pelo restante da chamada ou da sessão do instrumento | persistente para o recurso | revisão registrada do recurso |
| timeout, 5xx, ausência de resposta, falha de conexão | host | 1 h | automática após 1 h, com nova leitura de robots se expirada |
| robots ausente, malformado ou inconclusivo, `Crawl-delay` inválido | host | até nova leitura válida, no mínimo 1 h | nova leitura válida |
| falha local de persistência ou de interpretação | chamada (ou sessão do instrumento) | não persiste | nova chamada |
| teto de sessão/chamada atingido | sessão/chamada | não persiste | nova sessão/chamada |

3. Registrar com motivo estável e categoria só quando demonstrada (0045; 401 como recusa identificada). Testes provam nenhuma emissão posterior na unidade, inclusive em processos concorrentes, após reinício e dentro da mesma chamada do transporte.
4. Material parcial nunca vira zero resultados, inexistência de alteração ou atendimento integral; a indisponibilidade aparece na resposta (0077). Sem troca de UA, IP, host ou rota; sem fallback para Senado, DOU, LexML ou Planalto; sem sessão assistida implícita.

## 7. Atribuição

Cada evidência de origem Câmara ganha o campo aditivo `atribuicao`: `{"fonte": "Câmara dos Deputados", "autoria": <string identificada no próprio documento ou null>, "forma_de_citacao": "trecho entre aspas, com fonte e autoria quando houver", "termo_url": <URL do §3>, "termo_sha256": <hash da captura do termo>}`. Vale em toda entrega de texto ou recorte da Câmara (Python, MCP, REST, respostas embutidas, cache, snapshot e reabertura), por evidência, preservando a origem quando houver várias fontes. O Verifica não insere aspas nem altera `texto` ou os bytes usados no confronto; a delimitação da citação é instrução de apresentação ao consumidor, carregada em `forma_de_citacao`. Autoria nunca fabricada. Se a conferência do termo capturado (§2.3) revelar exigência diversa, esta seção é revista antes da ativação. Testes: autoria presente e ausente, respostas compostas com várias fontes, todas as fachadas. Campos consumidos pelo FREOA preservados.

## 8. Captura para os conjuntos e D6

1. **Inventário.** O inventário é de normas (espécie, número, ano), não de URLs. As URLs são obtidas só pela cadeia de descoberta da 0077 (busca → página de norma → links publicados), preservando `href`, URL e hash da página de origem em cada passo. Não há fase de descoberta irrestrita. O inventário do desenvolvimento é revisado pelo auditor antes da obtenção.
2. **Desenvolvimento.** Capturado pelo supervisor/codificador, com home próprio de desenvolvimento.
3. **Reserva.** Capturada pelo guardião em sessão própria, com home, inventário, recibos, corpos, logs e snapshot sob guarda separada (`Claude_Externos/freoa-verifica/porta-l/reserva-home/`), inacessíveis ao supervisor e ao codificador. Durante ajustes, ao supervisor chega apenas o que o D6 permite: `captura da reserva concluída: sim/não`, sem contagens, categorias, URLs, identificações ou hashes. Contagens, categorias e eventual compromisso ficam com o guardião e vão ao titular no relatório integral; se houver compromisso, é HMAC-SHA-256 sobre serialização canônica (JSON ordenado dos hashes individuais) com chave aleatória de 256 bits gerada e guardada pelo guardião, revelada só ao titular. Correções do produto só a partir do desenvolvimento. Contaminação segue o D6.
4. **Snapshot.** Recibos e vínculos recuperáveis, hashes conferidos na instalação, evidência adulterada recusada, `captured_at` e procedência originais preservados; instalação e reprocessamento não renovam captura nem qualificam rota; recursos fora da gramática ficam inventariados como não obtidos; modo local sem rede. O snapshot da reserva não é publicado nem misturado ao de desenvolvimento.

## 9. Regressões exigidas na implementação

Gramática (hosts, famílias, períodos, sufixos, rejeições antes do transporte); exceção administrativa (só a URL exata; vizinhos recusados; robots antes; falha impede ativação); robots reais (hashes conferidos; grupo IA = `*` no portal; PDF proibido no portal; www2 sem proibição para Legin) e sintéticos (`Allow`/`Disallow`, `*`, `$`, grupo do UA, ausente, malformado, recusado, expirado, `Crawl-delay` maior e inválido); ritmo (relógio controlado, limiares, concorrência, processos, tentativas internas, teto); barreiras (cada classe do §6; nenhuma requisição posterior; nenhum fallback); atribuição em todas as fachadas e caminhos; D6 (saídas sem URL, identificação ou hash individual da reserva); snapshot (adulteração, offline, preservação de `captured_at`); semântica (guardas 0075/0077/0078/0079 intactas; nenhum `verified` por captura, metadado ou nota; qualificação `nao_apurada`). Testes causais: liberar caminho vedado, retirar a espera, aceitar termo não preservado, seguir redirecionamento ou expor diagnóstico da reserva deve fazê-los falhar. Fixtures sintéticas rotuladas; reais intactas.

## 10. Questões abertas

- O termo não trata de acesso automatizado; a leitura adotada é do supervisor e cede a manifestação oficial em sentido diverso.
- Comunicação institucional à Câmara sobre o uso: a critério do titular.
- Política de atualização da Legislação Informatizada: não localizada (§3.3).
