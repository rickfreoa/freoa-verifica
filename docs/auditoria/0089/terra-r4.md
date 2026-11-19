A v4 ainda contém **bloqueadores de especificação**: a conferência de extensões pode deixar de detectar uma regra de interceptação ativa, e a identidade dos bytes textuais não decorre dos critérios previstos. Os cenários abaixo avaliam a especificação; não afirmam vulnerabilidade em uma implementação existente.

A revisão tomou como premissas as seis decisões do titular e o modelo de ameaça da §2.2(7). Conferi o ramo `docs/0089-sessao-assistida`, o HEAD `9bbe2e0e709d6031c037a2c329da1d633fd2d226` e a árvore limpa. Não alterei arquivos, executei testes nem abri sessão assistida.

**Situação dos meus 12 achados da rodada 3**

| Achado r3 | Situação na v4 | Fundamento |
|---|---|---|
| 1. Extensão forçada | **Aberto** | A intenção de recusá-la foi incorporada, mas a descoberta condicionada a alvo CDP não prova que todas as extensões capazes de interceptar foram examinadas; ver achado 1 abaixo. |
| 2. Canal DevTools | **Resolvido no modelo adotado** | O pipe é obrigatório e a ameaça de processo malicioso da mesma conta foi expressamente excluída. A herança dos identificadores e a proteção contra outra conta permanecem sujeitas ao aceite. |
| 3. JSON–binário | **Parcial** | Há vínculo por URN e UUID, mas a regra temporal e a seleção de dependentes deixam ambiguidades concretas; ver achado 3. |
| 4. Origem e associação | **Parcial** | A chave composta e a recusa de eventos ambíguos foram especificadas. A prova depende dos testes de associação, origem e corridas da §3. |
| 5. Seleção humana | **Parcial** | A decisão de selecionar ao fechar foi aplicada, mas a identificação dos dependentes e a ocorrência de múltiplas capturas ainda precisam ser fechadas; ver achado 3. |
| 6. Identidade de bytes | **Aberto** | Os novos critérios não demonstram qual decodificador produziu o texto; ver achado 2. |
| 7. Bomba e completude | **Parcial** | A v4 restringe expressamente a garantia ao que a ferramenta aceita e copia. A completude e o comportamento do navegador em fluxos truncados permanecem sujeitos à prova da §3.1. |
| 8. Captura privada | **Parcial** | A v4 aplica a decisão de declaração por perfil e nomes de cookies. A prova de que os sinais e nomes previstos são suficientes para os recursos reais permanece pendente; ver achado 5. |
| 9. Segredos e artefatos | **Parcial** | Há filtro, gramáticas e inventário exigido de gravações, mas gramática não demonstra publicidade do valor; ver achado 4. A contenção dos artefatos depende do teste de sistema. |
| 10. `f5_cspm` | **Parcial** | A equivalência ficou limitada e o exemplar é preservado, mas a forma escrita não especifica fielmente o bloco observado; ver achado 6. |
| 11. Tráfego não controlado | **Resolvido quanto ao alcance declarado** | A v4 reconhece que a ferramenta não controla o tráfego do navegador e limita sua promessa à admissão de capturas. Isso não comprova isolamento de rede, que deixou de ser a garantia afirmada. |
| 12. Página inicial | **Resolvido na especificação** | HTML local estático, texto escapado, sem script ou recurso externo e CSP restritiva estão previstos. Falta demonstrar o comportamento no aceite. |

**Achados da v4**

1. **BLOQUEADOR — Conferência de extensões depende de um alvo aparecer.**

   **Cenário:** uma extensão instalada por política contém regras `declarativeNetRequest` já registradas. Essas regras podem atuar sem que seu service worker esteja em execução no momento da captura. A §2.2(3) manda ler o manifesto “a cada extensão que apareça como alvo”; se ela não aparecer como alvo durante a conferência, a sessão pode prosseguir apesar de haver interceptação. A conferência após o lançamento também precisa impedir que uma candidata anterior à descoberta sobreviva.

   **Trecho:** [§2.2(3)](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:65).

   **Correção mínima:** antes de admitir qualquer candidata, inventariar de forma completa as extensões efetivamente instaladas e habilitadas, inclusive as sem alvo ativo, e seus manifestos e regras relevantes; falhar fechado se o inventário ou o manifesto não puder ser comprovado. Revalidar mudanças durante a sessão e invalidar todas as candidatas se surgir interferência. Testar extensão com regra declarativa ativa e service worker inativo. Também é necessário demonstrar que a leitura das políticas cobre as fontes efetivas de configuração do navegador, sem presumir que as chaves enumeradas esgotem o caminho de proxy.

2. **BLOQUEADOR — Igualdade de comprimento não prova a identidade dos bytes.**

   **Cenário e contraexemplo à justificativa:** suponha que o CDP entregue texto após decodificar uma resposta como UTF-16, embora o documento declare UTF-8. Para uma sequência de dois caracteres, `A` e `中`, UTF-16 sem BOM usa quatro bytes (`41 00 2d 4e`, em little-endian), e sua reencodificação UTF-8 também usa quatro (`41 e4 b8 ad`). Não há U+FFFD e o comprimento coincide, mas os bytes diferem. Um documento maior pode conter declaração `meta` de UTF-8 e compensar as diferenças de comprimento entre caracteres, inclusive o eventual BOM.

   O exemplo demonstra que **as condições da §2.5(2), isoladamente, não provam a conclusão**. A aceitação concreta depende de qual decodificação o Chrome efetivamente aplica ao `getResponseBody` nesse caso; o teste de normas não registrou o contador necessário e não a demonstrou. A verificação apenas da declaração no corpo não comprova que ela foi o charset efetivo nem resolve conflitos entre BOM, cabeçalho e `meta`.

   **Trecho:** [§2.5(2)](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:175).

   **Correção mínima:** aceitar texto como exemplar somente se houver prova, para aquela resposta e API, de decodificação UTF-8 estrita e reversível sobre os bytes efetivos, com precedência de charset e conflitos definidos. Na ausência dessa prova, recusar e usar uma via que entregue bytes. Acrescentar ao aceite o caso de charset efetivo divergente com comprimentos compensados, além dos já previstos.

3. **BLOQUEADOR — O vínculo e a seleção não fecham a identidade de cada dependente.**

   **Cenário:** uma candidata A associa um UUID à URN 1; B é aceita; posteriormente outra A da mesma sessão associa o mesmo UUID à URN 2. A §2.11 manda recusar UUID presente em mais de uma URN, mas exige a A correspondente apenas *antes* de B e não determina invalidar B já aceita quando o conflito aparece depois. Ao fechamento, B ainda pode acompanhar o documento marcado. Outro caso: duas respostas B para o mesmo UUID, com hashes diferentes, seguem automaticamente a mesma A, sem regra que indique qual entrou ou que exponha cada uma para escolha.

   **Trechos:** [§2.3, seleção](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:126) e [§2.11, vínculo B → A](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md).

   **Correção mínima:** resolver o vínculo sobre o conjunto completo da sessão **antes da seleção e gravação**; conflito posterior invalida todas as associações afetadas. Vincular cada B ao identificador e hash de uma A específica e expor ao humano os dependentes e seus hashes. Se houver múltiplos B elegíveis para a mesma identidade e versão sem escolha inequívoca, recusar o grupo. Validar também `version` e `@id`, inclusive sua correspondência, antes de registrá-los.

4. **BLOQUEADOR — Gramática pública não torna público qualquer valor que a satisfaça.**

   **Cenário:** uma página direciona a uma URL admitida do Planalto cujo segmento contenha um token formado somente por letras e números, por exemplo `/ccivil_03/Segredo123.html`. Ele satisfaz a gramática e pode ser persistido como caminho ou exibido na lista, embora seja segredo. Um UUID também pode ser usado como identificador sensível. A afirmação de que todo valor conforme a gramática é público por construção não decorre do formato.

   **Trechos:** [§2.7(3)](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md) e [§2.11, perfil Planalto](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md).

   **Correção mínima:** separar a URL operacional da identidade exibida e persistida; admitir apenas identidades cuja publicidade tenha fundamento verificável no perfil e no recurso, recusando valores indeterminados. Testar tokens sintéticos que **satisfaçam** as gramáticas, e não apenas tokens fora delas.

5. **RESSALVA — Nomes de cookie são necessários pela decisão adotada, mas não provam ausência de personalização.**

   **Cenário:** um cookie com nome admitido pode transportar um identificador individual, e o servidor pode personalizar a resposta sem emitir `Vary: Cookie` ou `Cache-Control: private`. Os nomes reais de normas.leg.br sequer foram registrados no teste. Isso não reabre a decisão 5; delimita a prova necessária para aplicá-la ao perfil concreto.

   **Trechos:** [§2.3(2)](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:106), §2.7(4) e §2.11.

   **Correção mínima:** documentar a evidência do fundamento público e dos nomes efetivos por recurso, testar resposta personalizada sintética e recusar quando houver indício de personalização ou autenticação. Manter o perfil fechado diante de nome desconhecido.

6. **RESSALVA — A forma de `f5_cspm` não é uma gramática reproduzível do bloco observado.**

   **Cenário:** a §2.5(3) representa o início, um ponto e o fim do script, mas não define formalmente o conteúdo intermediário. Se o ponto significar qualquer conteúdo, pode abranger alteração relevante; se significar ponto literal, não corresponde ao script completo das fixtures. Por exemplo, [a fixture da Lei 6.385](/C:/dev/fv14-0089/tests/fixtures/planalto_lei_6385_1976.html:1565) contém várias funções após o token.

   **Trecho:** [§2.5(3)](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:183).

   **Correção mínima:** especificar o bloco completo como sequência literal ou gramática estrita derivada de captura real, com apenas o campo variável delimitado; qualquer desvio impede a equivalência. A preservação do exemplar e a ressalva de equivalência apenas textual já reduzem a consequência.

7. **RESSALVA — HSTS e lista CDP precisam de provas de execução específicas.**

   **Cenário:** a exceção HSTS exige um conjunto de sinais, mas ainda precisa demonstrar que o evento interno observado não pode ser confundido com resposta de rede sem metadados completos. Além disso, a lista da §2.12 restringe nomes e alguns parâmetros, mas não enumera valores obrigatórios de todos os parâmetros, inclusive a espera efetiva na autoanexação; leitura literal de “parâmetro diferente dos indicados” também deixa chamadas cujos parâmetros não estão indicados sem contrato executável completo.

   **Trechos:** [§2.4, linha 8](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:153) e §2.12.

   **Correção mínima:** fixar parâmetros e valores completos por método e alvo, incluindo `waitForDebuggerOnStart=true`, e recusar parâmetros ausentes ou adicionais. Testar redirecionamento real, interno HSTS e evento incompleto, bem como alvos criados antes e durante a autoanexação. O teste deve comprovar a distinção, não apenas registrar a presença dos campos.

Os testes exploratórios sustentam a viabilidade inicial, mas foram limitados a uma configuração e não comprovam esses ataques nem os critérios de aceite. A v4 incorpora as decisões do titular; os bloqueadores acima dizem respeito à aplicação verificável delas.

**BLOQUEADOR**