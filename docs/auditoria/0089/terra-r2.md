A versão 2 fecha algumas lacunas da rodada anterior, mas ainda permite cenários que comprometem a vinculação da captura ao alvo, o sigilo de conteúdo não público e a fronteira de rede. A avaliação é **documental**: não pressupõe que exista uma implementação vulnerável nem substitui os testes de aceite.

## Reavaliação dos dez achados

| Nº | Estado | Avaliação da versão 2 |
|---|---|---|
| 1 | **Fechado** | A §2.1(4) e (7) desliga cache e service workers e só admite captura de troca pelo proxy; a §2.2(2) recusa 304. A §3(3) exige teste. O fechamento depende de demonstrar que o navegador realmente obedece à configuração. |
| 2 | **Aberto** | As §§2.3 e 2.4 validam cada troca, mas não vinculam a captura ao alvo confirmado, à ação humana, à página ou ao quadro. Uma navegação induzida pelo conteúdo pode gerar outra captura elegível. |
| 3 | **Fechado** | A §2.1(4) nega downloads; a §5(2) condiciona sua futura admissão a decisão própria. É necessário verificar também que nenhum arquivo seja salvo pelo navegador antes da negativa. |
| 4 | **Parcialmente fechado** | As §§2.3(4), 2.6(4) e 2.7(2) limitam o escopo ao público e vedam login pessoal no aviso, mas prefixo público e ausência de `Authorization` não demonstram que a resposta é pública: cookies e personalização continuam possíveis. |
| 5 | **Parcialmente fechado** | As §§2.3(3), 2.6(3) e 2.10 introduzem prefixos e padrões de valores. Falta assegurar que o **sufixo do caminho** e os valores aceitos sejam comprovadamente públicos: padrões permissivos podem admitir tokens, inclusive em parâmetros declarados. |
| 6 | **Parcialmente fechado** | As §§2.1(5) e 2.2(1) alinham `Content-Encoding` ao transporte e a §3(1) exige testes. Falta especificar o limite antes e durante o recebimento e a contenção de recursos no trecho navegador–proxy; a afirmação de equivalência depende de provar a aplicação efetiva das validações. |
| 7 | **Parcialmente fechado** | A §2.6(1) e (2) prevê ACL antes do lançamento, reconhece processos da mesma conta e trata sobras. Falta detalhar herança e verificação de **todos** os artefatos, inclusive temporários e logs produzidos fora do diretório previsto, e testar acesso por outra conta. |
| 8 | **Fechado** | As §§2.7(2) e 2.5(2) incluem o aviso, encerramento pelo humano e a limitação da prova de origem e hash. O aviso reduz o risco; não prova integridade da fonte nem impede toda indução maliciosa. |
| 9 | **Parcialmente fechado** | As §§2.1(2) e 3(7) exigem apresentação e confirmação do alvo antes do lançamento. Porém, a captura subsequente não fica vinculada a esse alvo confirmado, e a segurança da exibição depende da sanitização efetiva. |
| 10 | **Parcialmente fechado** | As §§2.1(6), 2.3 e 3(1)–(2) excluem capturas de terceiros e pedem testes de duplicados. Falta explicitar validação inequívoca da **origem efetiva de cada troca**, autoridade do CONNECT, Host/SNI e divergências entre eles, além da recusa de metadados indisponíveis ou ambíguos. |

Referências: [0089, versão 2](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md) e [achados da rodada 1](/C:/dev/_il/terra-0089.md).

## Novos ataques à superfície

1. **Crítica — CONNECT opaco alcança rede local ou o próprio proxy.**  
   **Cenário:** página hostil induz conexões a `127.0.0.1`, outras interfaces locais, endereços privados, link-local ou ao próprio listener. A §2.1(6) admite túnel para “qualquer outro host”, sem política de destino. A ausência de gravação não impede acesso a serviços internos nem envio de dados. DNS rebinding pode fazer um nome aparentemente externo resolver para IP interno.  
   **Correção mínima:** negar por padrão destinos de túnel; permitir apenas hosts e portas externos necessários, com resolução controlada, validação de **todos os IPs**, conexão ao IP validado e recusa de loopback, privado, link-local, reservado e do próprio proxy. Revalidar em cada conexão e testar rebinding e resolução divergente.

2. **Crítica — Credencial de proxy não prova que a conexão veio do navegador lançado.**  
   **Cenário:** outro processo local obtém ou reutiliza a credencial, conecta-se ao listener e envia requisições com cabeçalhos próprios. A §2.1(3) afirma que só o navegador conecta, mas uma credencial compartilhada demonstra posse, não identidade do processo; a §2.6 reconhece que a ACL não isola processos da mesma conta. O mecanismo de entrega da credencial ao navegador também não está definido.  
   **Correção mínima:** definir o adversário local e um mecanismo verificável de vinculação ao processo e à sessão, sem expor segredo em argumentos, logs ou arquivos acessíveis. Se não houver mecanismo suportado e demonstrável, não alegar exclusividade nem permitir que a credencial, isoladamente, autorize capturas. Testar processo de outra conta e da mesma conta, roubo e repetição.

3. **Alta — AC efêmera e exceção de certificado têm escopo insuficientemente demonstrado.**  
   **Cenário:** se a chave da AC for exposta ou reutilizada, um processo pode emitir certificados; se a exceção SPKI for aceita para uma cadeia fora do escopo pretendido, o navegador pode confiar em certificado de host que não pertence à fonte. A §2.1(5) declara aceitação “apenas por esse navegador”, mas não demonstra restrição por host ou ciclo de vida, nem que a opção escolhida opere como pressuposto.  
   **Correção mínima:** provar em testes, com o navegador e versão suportados, o comportamento da exceção SPKI e sua abrangência; não emitir certificados fora de autoridades expressamente autorizadas, não reutilizar chaves e destruir material ao encerrar. Recusar a sessão se o escopo e o isolamento não forem demonstráveis. A exposição a processo da mesma identidade deve ser reconhecida.

4. **Alta — Divergência entre CONNECT, Host, SNI e resolução pode trocar a origem validada.**  
   **Cenário:** o navegador solicita túnel para uma autoridade, mas a requisição interna apresenta outra autoridade, Host ou SNI. Uma classificação por apenas um desses campos pode aplicar interceptação, política de fonte ou prova de origem ao destino errado. A §2.4 valida saltos isoladamente, sem definir essa correspondência.  
   **Correção mínima:** normalizar autoridade, porta e nome internacionalizado; exigir correspondência estrita entre destino autorizado, autoridade da requisição, Host e SNI quando aplicáveis; rejeitar discrepâncias e ambiguidades. Resolver e conectar somente pelo transporte ao IP aprovado, sem confiar em resolução anterior do navegador.

5. **Alta — `Sec-Fetch-Dest` não autentica navegação humana.**  
   **Cenário:** outro cliente local forja `Sec-Fetch-Dest: document`; mesmo um navegador legítimo pode enviar esse destino para iframe ou navegação disparada por script. A §2.3(2) transforma o cabeçalho em critério de captura, mas ele não comprova identidade do processo, quadro, intenção ou alvo.  
   **Correção mínima:** tratar o cabeçalho apenas como filtro auxiliar. Vincular captura à sessão, à autoridade e URL confirmadas e a uma navegação observável; definir política para quadros, pop-ups e navegações iniciadas por conteúdo. Na ausência dessa prova, recusar a captura.

6. **Alta — Tráfego automático do navegador pode gerar captura sem ação humana sobre o documento.**  
   **Cenário:** prefetch, prerender, pré-carregamento, restauração ou navegação automática gera uma troca elegível. A §2.4 afirma que o navegador inicia por ação humana, mas a §2.7 só exige ação humana para a navegação inicial. Uma página pode também redirecionar para outro documento público elegível.  
   **Correção mínima:** desabilitar mecanismos automáticos suportados e definir um gate explícito de seleção ou confirmação humana do documento efetivamente capturado. Testar prefetch, prerender, iframe, pop-up, redirecionamento por script e navegação automática; nenhuma troca isolada deve comprovar intenção.

7. **Alta — WebSocket, HTTP/2 e QUIC podem escapar da política pretendida.**  
   **Cenário:** upgrade para WebSocket ou túneis e protocolos não tratados criam canal de saída não submetido à mesma classificação; HTTP/3/QUIC ou conexões diretas podem contornar o proxy se a configuração do navegador não as impedir. A §5(4) deixa HTTP/2 e HTTP/3 para teste manual, insuficiente como condição de segurança.  
   **Correção mínima:** definir protocolos e upgrades permitidos, negar os demais por padrão e bloquear e testar saída direta, inclusive UDP/QUIC e WebSocket. Exigir teste automatizado negativo e evidência na plataforma suportada; se não for possível garantir a rota, falhar fechado.

8. **Alta — Cookies e páginas personalizadas podem produzir evidência privada.**  
   **Cenário:** após interação humana ou configuração da fonte, um cookie de sessão faz um caminho público retornar conteúdo individualizado, embora não haja `Authorization`. A resposta satisfaz a §2.3 e pode ser persistida. Um padrão de URL não identifica a natureza do corpo.  
   **Correção mínima:** proibir captura quando houver autenticação ou indício de personalização, inclusive baseada em cookie; diante de dúvida, descartar sem persistir. Definir como a condição é verificada sem registrar segredos e testar conteúdo sintético privado em URL pública.

9. **Alta — Página local inicial pode virar canal de injeção ou de rede.**  
   **Cenário:** alvo ou identificação da fonte contendo caracteres especiais é interpolado como HTML ou JavaScript; um alvo enganoso pode executar conteúdo, carregar recurso remoto ou apresentar destino diferente do validado. A §2.7(1) diz que a página é gerada sem acesso à rede, mas não define isolamento, escape ou política de navegação.  
   **Correção mínima:** renderizar dados exclusivamente como texto escapado, sem script ou recursos externos; aplicar política restritiva de conteúdo e bloquear requisições da página inicial. Exibir exatamente o alvo público normalizado e testá-lo com entradas hostis, inclusive caracteres de controle e homógrafos.

10. **Alta — Limite de taxa apenas em candidatas permite abuso do transporte.**  
    **Cenário:** uma página cria grande volume de subrecursos ou requisições que não são candidatas a captura. Pela §2.4, elas escapam do limite de taxa e disjuntor por fonte, embora passem pelo transporte e possam consumir recursos ou pressionar a origem.  
    **Correção mínima:** aplicar limites globais por sessão e por destino a **todas** as trocas, inclusive túneis, conexões simultâneas, duração e bytes; manter limites específicos de captura quando necessários. Testar saturação e encerramento.

11. **Média — Aceite não cobre as garantias centrais da nova fronteira.**  
    **Cenário:** a §3 testa validações com cliente HTTP simulado e prevê uma sessão manual, mas não exige provas negativas para conexões locais indevidas, isolamento da AC e da credencial, rebinding, saída direta ou indução de navegação. Uma implementação pode passar no aceite sem demonstrar as premissas arquiteturais.  
    **Correção mínima:** incorporar os testes negativos acima como critérios de aceite obrigatórios, com navegador real e rede controlada, incluindo falha fechada quando uma garantia não puder ser aplicada.

**Veredito: `BLOQUEADOR`.**