**BLOQUEADOR**

Auditoria documental, somente leitura, no ramo `docs/0089-sessao-assistida`, HEAD `35dd8bc1513e146ad2965d2c3e688dd88e91ebca`. A [0089 v2](C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:1) permanece não rastreada; SHA-256: `0ef14c398617741007b8dcca72a3327b1b35ec28b62f9eb6cba9702b05fe9f4c`.

Não alterei arquivos nem executei testes ou sessões assistidas. Os cenários abaixo atacam a especificação; não demonstram exploração de implementação existente. “Resolvido” nas tabelas significa resolvido **no texto**, sujeito à comprovação na implementação.

**Confronto com os pareceres anteriores.** As referências `0089:N` indicam linhas da versão auditada.

| Rodada 1 | Situação | Evidência e resíduo |
|---|---|---|
| 1. Content-Encoding | **Resolvido** | §§2.1(5), 2.2(1), linhas 31–49: aquisição pelo transporte e recusa de codificação diferente de ausente/identity. Compatível com `transport.py:1128–1136`. |
| 2. Equivalência incompleta | **Parcialmente resolvido** | §§2.1 e 3 incorporam framing, DNS/IP, tamanho e prazo. A §2.4 ainda omite diferenças e perde controles de cadeia; achados 2–5 abaixo. |
| 3. Navegação inicial automática | **Resolvido** | §2.7(1), linhas 117–119: página local sem rede; navegação pelo humano. |
| 4. Tipo de `fontes_indisponiveis` | **Resolvido** | §2.9(3), linhas 137–141: preserva mapa para string; detalhes em campos novos. Confere com `service.py:471–483`. |
| 5. Indicação por categoria | **Parcialmente resolvido** | §2.9 exige operação, perfil, barreira e ausência de bloqueio; exclui 401. Faltam a tabela concreta e a disciplina da indicação por envelhecimento; achado 9. |
| 6. Origem e alcance da 0083 | **Resolvido quanto à formulação** | §2.5(2), linhas 92–96: exige aquisição comprovada e limita corretamente a exclusão da 0083. A arquitetura ainda precisa satisfazer os bloqueadores abaixo. |
| 7. Envelhecimento genérico | **Resolvido** | §2.5(3), linhas 97–99: restringe o efeito a `vigente_na_fonte` em consulta corrente, preservando a distinção da 0002. |
| 8. Aceite insuficiente | **Parcialmente resolvido** | §3 acrescenta chamadas indiretas, modalidade, snapshot e proxy controlado. Permanecem sem prova suficiente o navegador real, isolamento, cadeia e conteúdo secreto no corpo. |

| Terra | Situação | Evidência e resíduo |
|---|---|---|
| 1. Cache/service worker/304 | **Resolvido** | §§2.1(7), 2.2(2) e 3(3): sem troca no proxy não há captura; 304 não renova evidência. |
| 2. Associação entre navegações | **Não resolvido** | §2.3 usa GET/destino/status; §2.4 esvazia a cadeia. Não exige vínculo com alvo, página, quadro ou ação humana; achado 3. |
| 3. Downloads | **Resolvido** | §2.1(4) nega downloads; §5(2) exige decisão própria para admiti-los. |
| 4. Conteúdo pessoal/autenticado | **Parcialmente resolvido** | §§2.3(4), 2.6(4), 2.7(2): vedação expressa, mas ausência de `Authorization` não exclui autenticação por cookie; achado 6. |
| 5. Segredos em URL | **Parcialmente resolvido** | §§2.3(3), 2.6(3) acrescentam padrões de valor e caminho. Falta definir sanitização, identidade e tratamento dos casos admitidos pelo padrão que ainda sejam secretos; achados 5–6. |
| 6. Compressão e limites | **Resolvido** | §§2.1(5), 2.2(1): não admite corpo comprimido decodificado pelo navegador; preserva aquisição e hash pelo transporte. |
| 7. ACL e descarte | **Parcialmente resolvido** | §2.6 especifica ACL prévia, falha fechada, interrupção e recuperação. Não comprova que cookies e demais artefatos do navegador ficam apenas em memória; achados 6 e 8. |
| 8. Página hostil | **Resolvido quanto à política** | §§2.7(2), 2.5(2): aviso explícito e ausência de promessa de integridade substantiva da fonte. |
| 9. TTY não prova autorização | **Resolvido quanto ao requisito proposto** | §2.1(2) exige apresentação e confirmação por sessão/alvo; §3(7) exige negativo sem confirmação. |
| 10. Terceiro e metadados ambíguos | **Resolvido quanto à admissão da captura** | §§2.1(5–7), 2.3, 2.4: terceiros não geram captura; validações ocorrem na troca e falta de dado causa recusa. A segurança do túnel permanece questão distinta; achado 7. |

**Achados da rodada 2**

1. **ALTA — O argumento SPKI não equivale a confiar numa AC somente para as origens da fonte.**

   **Evidência:** §2.1(5), linhas 31–37. No [verificador do Chromium](https://raw.githubusercontent.com/chromium/chromium/main/services/network/ignore_errors_cert_verifier.cc), linhas 56–85, a presença de SPKI listado em qualquer certificado apresentado faz retornar sucesso antes do verificador normal. A opção não estabelece, por si, restrição por hostname nem validação convencional da cadeia.

   **Ataque:** caso o certificado público da AC efêmera seja conhecido, testar servidor de terceiro com certificado inválido que acrescente essa AC à cadeia apresentada. O código consultado justifica esse negativo; não executei a exploração nem conferi o comportamento das versões instaladas.

   A AC efêmera **não é incompatível por natureza** com a regra 3: interceptar localmente uma sessão expressamente admitida, mantendo TLS upstream estrito, não demonstra contorno. Entretanto, a compatibilidade com o “contexto dedicado e isolado” da 0067 não está provada por esse argumento de lançamento.

   **Redação corretiva mínima:** “A exceção TLS local não autoriza certificado inválido de terceiro nem dispensa a validação upstream. O mecanismo de confiança deve ter escopo demonstrado às origens interceptadas; o aceite inclui cadeia inválida contendo o certificado público efêmero, nome incorreto, certificado expirado e AC alheia, nas versões suportadas do navegador.”

2. **ALTA — Falta separar transporte para navegação de admissão como captura; `fetch` não funciona como retransmissor transparente.**

   **Evidência:** §§2.1(5), 2.3, linhas 31–37 e 69–70. O texto manda aplicar o fluxo automático e, simultaneamente, repassar respostas conforme esse fluxo.

   Hoje:

   - redirecionamentos são consumidos internamente (`transport.py:1137–1181`);
   - status diferente de 200 gera exceção após exame do corpo (`1182–1187`);
   - `Response.headers` contém cabeçalhos filtrados, sem `Set-Cookie` e `Location` (`1268–1281`, `HEADER_NAMES:35`);
   - MIME de subrecurso como JavaScript/CSS não integra a lista padrão (`45–56`);
   - desafio e interpretação textual do sucesso são verificados também fora de `fetch`, em [httputil.py:159](C:/dev/fv14-0089/freoa_verifica/connectors/httputil.py:159) e `169–206`.

   **Consequência:** reutilizar diretamente `fetch` perde dados necessários à navegação ou impede a apresentação do desafio. Criar um caminho separado sem especificá-lo transfere a regra ao implementador. Cookies geridos por `Session` ainda substituem o cabeçalho recebido (`transport.py:1106–1111`), contrariando uma retransmissão literal.

   **Redação corretiva mínima:** “O proxy distingue entrega ao navegador e admissão no acervo. A especificação define, por classe de resposta, quais bytes e cabeçalhos são retransmitidos, quais falhas encerram a troca e quais apenas impedem captura. Cabeçalhos operacionais completos permanecem transitórios; recibos continuam filtrados. O navegador é o único gestor de cookies.”

   Essa disciplina deve abranger desafio 200/403, redirecionamento, `Set-Cookie`, subrecursos e POST necessário à interação humana, sem admitir esses POSTs como captura.

3. **ALTA — Validar cada salto isoladamente não preserva as regras de redirecionamento nem a associação com o alvo.**

   **Evidência:** §2.4, linha 78, manda gravar `redirects` vazio. O transporte atual mantém estado compartilhado entre saltos (`906–938`), verifica desafio antes de seguir `Location` (`1137–1142`), valida o destino, recusa 307/308 entre origens, trata credenciais e chama a guarda antes do salto (`1143–1179`). Há limite de saltos e prazo do percurso (`1061–1077`, `1293`).

   **Ataques admitidos pela omissão:**

   - quatro saltos tratados como quatro trocas independentes;
   - 307/308 entre duas origens permitidas;
   - origem permitida → terceiro opaco → origem permitida, com captura final aparentemente direta;
   - navegação por script ou *meta refresh* atribuída ao alvo confirmado;
   - falha no salto final classificada sem o progresso já recebido no anterior.

   **Redação corretiva mínima:** “Cada navegação possui identificador e vínculo com alvo, página/quadro e início autorizado. Os saltos HTTP preservam cadeia, limite, prazo total, exame de desafio e política de destino/credenciais antes de serem liberados ao navegador. Navegação induzida por conteúdo não herda autorização ou cadeia anterior. Cadeia não demonstrável impede captura.”

   Se a intenção for aceitar uma captura direta independente do percurso, isso precisa ser decidido expressamente, sem declarar equivalência integral com o fluxo atual.

4. **ALTA — Repetição, `Retry-After`, concorrência e guardas não estão integralmente especificados.**

   **Evidência:** §2.4, linha 80, restringe taxa/disjuntor às candidatas. No código:

   - `fetch` tem duas repetições por padrão (`882–883`, `1311`);
   - repete falhas elegíveis e usa `Retry-After` ou espera exponencial (`986–992`, `1399–1410`);
   - limita concorrência global e DNS (`1344–1348`, `691–693`);
   - taxa/disjuntor são indexados por **host**, não por fonte (`852–864`);
   - a guarda de execução do fluxo automático é adicional ao disjuntor (`httputil.py:54–68`; `guarda.py:102–156`).

   **Consequência:** chamar `fetch` com os padrões viola a proibição de repetição automática da 0067. Excluir subrecursos dos limites permite carga sem esses controles. “Candidata” tampouco esclarece se a decisão antecede a rede ou depende do status recebido.

   **Redação corretiva mínima:** “Toda troca upstream assistida tem uma tentativa, sem replay pelo transporte. `Retry-After` não agenda requisição. Limites de concorrência e taxa incidem antes da rede, inclusive em subrecursos. A decisão declara separadamente a política de disjuntor e guarda após desafio, permitindo apenas a continuidade humana necessária à resolução.”

   A tabela deve registrar essas diferenças e corrigir “por fonte” para “por host” ao descrever o código atual.

5. **ALTA — Método e URL sanitizada não identificam necessariamente a representação obtida.**

   **Evidência:** §2.4, linha 79. [identidade_requisicao](C:/dev/fv14-0089/freoa_verifica/transport.py:474) inclui query exata, corpo e cabeçalhos do chamador porque eles podem alterar a representação. Essa identidade alimenta cache e guarda.

   **Ataque:** dois GETs para a mesma URL pública, um antes e outro depois de alteração de cookie ou de `Accept-Language`, tornam-se a mesma identidade assistida. Sanitização também pode colapsar URLs operacionais distintas. Gravar `sessao_id` separadamente não define como impedir reutilização ou atribuição cruzada.

   **Redação corretiva mínima:** “URL pública de proveniência e identidade operacional são distintas. Cada troca assistida recebe identificador opaco único, sem reutilização de resposta por método/URL sanitizada. Sanitização não reúne destinos distintos; destino cuja identidade pública suficiente não possa ser preservada é recusado.”

   Não é necessário persistir cookies ou derivados deles para estabelecer essa separação.

6. **ALTA — Prefixo público e ausência de `Authorization` não garantem corpo público nem ausência de segredos.**

   **Evidência:** §§2.3(3–4), 2.6(3–4), linhas 63–65 e 109–113. A §3(4) testa cookies, autorização e tokens em URL, mas não exige negativos com segredo no corpo. O armazenamento atual grava o corpo integral e o Content-Type cru ([repo.py:82](C:/dev/fv14-0089/freoa_verifica/store/repo.py:82), linhas 82–110).

   **Ataque:** cookie autentica ou personaliza um GET no prefixo permitido; a resposta contém identificação pessoal ou token CSRF. Outro caso: parâmetro adicional do Content-Type contém segredo e segue pelo campo cru, embora o recibo filtrado o descarte.

   **Redação corretiva mínima:** “Não são admitidas respostas autenticadas ou personalizadas por cookie, nem corpos ou metadados persistidos contendo segredos incompatíveis com o acervo. O perfil declara como comprova a natureza pública; dúvida causa recusa, sem redação dos bytes. O aceite inclui segredo no corpo e em Content-Type cru.”

   Também é necessário comprovar a promessa “cookies só em memória”: perfil temporário e limpeza posterior não provam ausência de gravação durante a sessão.

7. **ALTA — `CONNECT` irrestrito deixa uma saída de rede fora da política e pode alcançar fontes barradas.**

   **Evidência:** §2.1(6), linhas 38–44, permite túnel para “qualquer outro host”. Não fixa portas, destinos IP, resolução segura, duração ou limites. `validate_reference` exige HTTPS/443 e `validate_url` recusa qualquer endereço resolvido inseguro (`transport.py:620–629`, `716–719`). `HOSTS_RECUSADOS` inclui `legis.senado.leg.br` e `www.in.gov.br` (`sondas.py:266–273`).

   **Ataque:** página induz acesso a destino privado ou a host barrado, classificado como terceiro. Não persistir os bytes não impede a requisição.

   **Regra 4:** um túnel implementado dentro de `transport` pode satisfazer o encaminhamento literal. Isso **não prova** as validações nem autoriza restringir a regra às origens da fonte. A 0067 admite a navegação humana e exige porta única de captura; ela não torna captura de terceiro admissível.

   **Redação corretiva mínima:** “Túneis passam pelo transporte e obedecem à política explícita de destinos, portas, DNS/IP, bloqueios e recursos, sem inspeção de conteúdo. Hosts barrados não são liberados como terceiros. O navegador não dispõe de fallback direto; falha do proxy encerra sua rede.”

   A correspondência entre autoridade CONNECT, origem interceptada e destino upstream também precisa ser definida.

8. **ALTA — O aceite pode passar sem provar as fronteiras introduzidas pela arquitetura nova.**

   **Evidência:** §3(1) usa cliente HTTP no lugar do navegador; §3(9) confere argumentos e prevê sessão manual no Planalto. Isso não prova o comportamento efetivo do navegador.

   Faltam negativos obrigatórios para confiança TLS, saída direta/loopback/protocolos alternativos, cadeia de redirecionamento, ausência de repetição, persistência de cookies e vínculo entre navegação e captura. A credencial aleatória de proxy (§2.1(3)) autentica seu portador; não demonstra, sozinha, identidade de processo.

   **Redação corretiva mínima:** “Além dos testes do proxy, o aceite executa o navegador real contra origens controladas e prova os negativos dos achados 1–7. Confere tráfego efetivo e artefatos durante e após a sessão. Autenticação por credencial não é descrita como isolamento por processo sem mecanismo e teste próprios.”

   HTTP/2/3 pode permanecer questão de compatibilidade, mas a ausência de saída alternativa é condição de segurança anterior à aceitação.

9. **MÉDIA — Permanecem ambiguidades concretas de captura e indicação.**

   **Evidência:** §2.3(2), linha 62, trata `Sec-Fetch-Dest: document` como navegação de página ou quadro. A [especificação Fetch Metadata](https://www.w3.org/TR/fetch-metadata/#sec-fetch-dest-header) distingue `document` para navegação superior e `iframe` para iframe. O cabeçalho também não comprova que o humano iniciou a navegação.

   Na §2.9(2), “também indica” não afirma expressamente que herda operação habilitada, fonte não barrada e demais requisitos do item 1. O perfil apenas nomeia `evidencias_de_barreira`; não fornece a tabela, sua validade ou o vínculo entre evidência, alvo e operação.

   Por fim, refazer upstream com `PinnedHTTPSConnection` preserva o TLS verificado, mas não o comportamento de rede do navegador real. Não está demonstrado que resolverá barreira que discrimine essa conexão; isso deve permanecer limitação, sem ajuste furtivo de identidade.

   **Redação corretiva mínima:** “Neste incremento, captura limita-se à navegação superior `document`” — ou enumerar quadros e seus vínculos. “O item 2 herda cumulativamente todos os requisitos do item 1. Os perfis iniciais incluem tabela versionada de barreiras, escopo e critérios de validade. Indicação não afirma resolubilidade ainda não comprovada.”

**Reaplicação dos seis critérios obrigatórios da rodada 1**

| Critério | Resultado |
|---|---|
| 1. Sem contradição com invariáveis, 0067, 0001 e 0002 | **Não atende.** Equivalência, repetição e segurança das requisições permanecem abertas. A separação temporal foi corrigida. |
| 2. Aditividade real do contrato | **Atende no desenho declarado.** Preserva estados, categorias e mapa para string; campos novos são experimentais. `procedencia: sessao_assistida` já existe em `repo.py:62` e `verify.py:248–266`. |
| 3. Afirmações conferem com o código atual | **Não atende integralmente.** Limites são por host; validação de sucesso inclui `httputil`; `fetch` não oferece a retransmissão descrita sem adaptação especificada. |
| 4. Todas as diferenças enumeradas | **Não atende.** Faltam repetição/Retry-After, concorrência, guarda, cookies, cabeçalhos operacionais, estado/prazo da cadeia e política de subrecursos/túneis. |
| 5. Aceite testável e suficiente | **Não atende.** Os testes previstos são úteis, mas insuficientes para as novas fronteiras; achado 8. |
| 6. Elegibilidade a `verified` coerente | **Atende quanto à regra escrita da §2.5.** Não comprova que o mecanismo a satisfaz. Origem oficial, hash e captura assistida continuam insuficientes sem identidade, âncora e confronto efetivo. |

Não identifiquei conflito específico adicional com a 0088, alteração da reserva D6 ou dispensa da auditoria própria de `transport` exigida por D5. A versão 2 corrige pontos substanciais dos pareceres anteriores, mas ainda deixa decisões de segurança e de admissão ao implementador.