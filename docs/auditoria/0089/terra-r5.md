A v5 fecha, em texto, a maior parte dos pontos da rodada 4. **Permanece aberto o controle de instalação e remoção de extensão durante a sessão**: a conferência periódica não assegura que uma extensão que interferiu em uma candidata será detectada. A análise é documental; não executei os testes de aceite.

| Item | Situação | Motivo |
|---|---|---|
| Terra 1 — extensões | **Parcial** | O inventário deixou de depender de alvo CDP, ocorre antes de candidatas e é repetido. Contudo, a frequência de dez segundos e a conferência antes da seleção não detectam necessariamente uma extensão instalada e removida entre duas verificações. O laboratório também não exercitou a extensão declarativa sem contexto de execução. |
| Terra 2 — identidade dos bytes | **Resolvido** | A §2.5(2) substitui `getResponseBody` pelo streaming e recusa ativação tardia ou falha. O laboratório reproduziu o contraexemplo de charset e obteve os bytes esperados por streaming; a §3 exige regressões adicionais. |
| Terra 3 — vínculo e seleção | **Resolvido** | O grafo é fechado antes da seleção; conflitos posteriores invalidam os vínculos atingidos, B registra identificação e hash de A, e Bs conflitantes são recusados. A validação de `version` e `@id` e a exibição dos dependentes também foram previstas. |
| Terra 4 — gramática e publicidade | **Resolvido, na premissa adotada** | A §2.7(3) retira a afirmação de que a sintaxe prova publicidade e declara o risco residual. A publicidade por declaração do perfil é premissa do titular. |
| Terra 5 — cookies e personalização | **Parcial** | O perfil registra o fundamento público, fecha diante de nomes desconhecidos e reconhece que os nomes reais não foram registrados no teste. A suficiência do perfil concreto e os cenários de personalização continuam dependentes do aceite; a declaração de publicidade permanece premissa. |
| Terra 6 — bloco `f5_cspm` | **Resolvido** | A §2.5(3) define região variável, tamanho e hash da cauda normalizada; cauda divergente impede a afirmação de equivalência. O exemplar permanece íntegro. |
| Terra 7 — HSTS e lista CDP | **Resolvido na especificação; prova pendente** | A lista fixa métodos, parâmetros e sequência de prontidão. A §3 exige distinguir HSTS interno, redirecionamento de rede e evento incompleto, além de verificar os comandos efetivos. Esses testes ainda não foram executados. |
| Codex B1 — bytes | **Resolvido** | Mesmo fundamento do Terra 2: streaming antes dos dados, recusa em caso de falha e testes específicos exigidos. |
| Codex B2 — extensão sem alvo | **Parcial** | O inventário independe de alvo CDP, mas a lacuna temporal descrita no Terra 1 impede concluir que toda interferência posterior invalide as candidatas. |
| Codex B3 — quadro principal e prontidão | **Resolvido na especificação; prova pendente** | `Page.getFrameTree` fornece a raiz para confronto com o `frameId`; a sequência de anexação, habilitação e liberação é normativa. O laboratório demonstrou o caso básico, e a §3 exige os testes de iframe e prontidão. |

**Ataque admissível: extensão transitória entre inventários — gravidade bloqueadora.**

- **Cenário:** uma política instala uma extensão com permissão de interceptação após um inventário; ela atua sobre uma resposta candidata e é removida antes do inventário seguinte e da conferência imediatamente anterior à seleção. As verificações previstas podem encontrar um ambiente permitido nas duas pontas, preservando candidata que atravessou interferência vedada.
- **Trecho:** [§2.2(3)](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:70), que determina inventário a cada dez segundos e antes da seleção e invalidação quando uma extensão violadora é detectada.
- **Correção mínima:** exigir prova contínua e verificável de que nenhuma extensão vedada foi instalada ou ativada durante o intervalo relevante; diante de lacuna nessa prova ou mudança não verificável, invalidar as candidatas afetadas. Acrescentar ao aceite instalação, atuação e remoção entre dois inventários. Se a prova contínua não estiver disponível, recusar a sessão.

BLOQUEADOR