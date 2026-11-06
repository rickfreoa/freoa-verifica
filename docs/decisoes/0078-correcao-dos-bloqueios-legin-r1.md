# 0078 — Aplicação dos bloqueios Legin e preservação do contrato

Data: 05/11/2026. Correção da implementação da 0077 após o parecer PR #36 r1.
Não habilita captura ao vivo, vigência histórica positiva, qualificação IL.3 ou aceite do marco.

1. Todo impedimento de recorte é examinado antes de concluir identidade e texto,
   inclusive se pertence a descendente incluído no agregado. Nota editorial não
   reconhecida, duplicidade, continuação incerta, margem, veto e colisão de escopo
   impedem conclusão. Parênteses normativos não são removidos como notas.
2. Citação alteradora mantém o delimitador externo e o balanço de aspas, abrangendo
   epígrafes e artigos com numeração pontuada. Material estrangeiro é
   `QuotedAmendment`; escopo não fechado ou comando sem escopo reconhecido bloqueia.
3. A anotação pertence ao dispositivo de origem (`target_path`). A redação do
   agregado não recebe anotações temporais dos filhos. Revogação de descendente
   produz `REVOGACAO_PARCIAL`, sem afirmar revogação total do agregado.
4. A obtenção Legin usa o construtor comum da resposta de dispositivo, preservando
   campos, semântica e nulidade do contrato. Os campos específicos são aditivos.
5. Planalto permanece consultável no acervo, sem novas capturas em busca federada,
   resolução, indexação de candidato, sincronização comum/semente, obtenção de
   datas/textos de alteradores, diagnóstico ou instrumento de captura. A política
   compartilhada antecede a obtenção do conector nesses caminhos. Câmara permanece com
   `ativacao_ao_vivo_pendente`: o bloqueio antecede qualquer requisição, inclusive
   robots. O conector admite injeção explícita de transporte offline para replay;
   isso não é opção de ativação ao vivo das fachadas.
6. A falha de obtenção mantém fontes consultadas, categoria e evidência conhecidas.
   O recibo completo as autentica e expõe; `sem_conteudo` mantém compromisso HMAC,
   sem gravar os dados em claro. Substring numérica dentro de HMAC não prova vazamento.
7. O replay offline intercepta a fronteira chamada e proíbe conexões reais. A única
   exceção de infraestrutura é a criação do socketpair local da stdlib no Windows,
   necessária ao self-pipe do asyncio; conexões do produto continuam proibidas.
8. Busca Legin pode obter a página de norma descoberta, validar identidade, montar
   inventário, obter o recurso e persistir as origens. Não se fabrica URL de recurso.
9. Modelos persistidos do parser anterior exigem reprocessamento antes de voltarem
   a fundamentar conclusões; a atualização não confere validade retroativa ao modelo.

O parecer independente continua necessário. As regressões desta correção não
certificam exaustividade da gramática editorial, de citações ou do inventário.
