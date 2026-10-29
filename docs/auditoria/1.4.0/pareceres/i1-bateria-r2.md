## BLOQUEADORES

Nenhum bloqueador na execução examinada. **B1 do r1 está sanado sob a ressalva expressa da decisão 0072.** Isso não declara o I1 encerrado: o manifesto ainda mantém as etapas 2 e 8 pendentes.

## IMPORTANTES

- **Registro da tentativa 3:** repetir uma vez com espaçamento definido para testar uma hipótese, preservando e descrevendo os resultados anteriores, é justificativa suficiente para aceitar essa execução. Não encontrei descarte ou reclassificação dos 429. Contudo, [o registro](/C:/dev/fv14-aceite/docs/auditoria/1.4.0/aceite-i1.md:103) não explicita que a decisão e o limite de uma repetição foram fixados **antes** do resultado. Convém registrar isso, com referência datada à instrução existente. Os horários são compatíveis com o intervalo declarado, mas não provam ausência de outras chamadas.
- **Preservação das evidências:** `live.xml`, `saude-fontes.json` e os dois logs de instalação estão **ignorados pelo Git**, não apenas sem commit. O parecer abrange os arquivos locais lidos; sua preservação precisa ser resolvida na incorporação. O manifesto também ainda precisa receber os recibos e a ressalva exigida pela 0072.

## MENORES

- O XML não contém campo de commit. Sua associação ao commit decorre da concordância com texto e JSON, horários e resultados individuais.
- Não encontrei caminho absoluto de máquina remanescente nos anexos examinados. Todos os quatro XMLs usam `hostname="<host>"`, corretamente escapado.
- A ausência de chamadas durante o intervalo e a decisão prévia são declarações do executor, sem comprovação independente nos anexos.

## VALIDAÇÃO

1. **Doctor de 29/10:** atende ao requisito material da etapa 8 com a 0072. DataJud está `ok`; os demais alertas têm classificação sustentada pelo código:
   - CVM: `fonte_fora`, por `transporte_Timeout`;
   - Planalto: `recusa_identificado`, pela regra da 0048;
   - TJSP: `ambiental_desafio`;
   - TCU: permanece sem categoria, expressamente ressalvado.

   Conferi o percurso CVM → `connector_fetch` → mapeamento do transporte. Não encontrei produtor alternativo desse motivo nos conectores CVM. Há um fallback genérico por nome de exceção em `httputil.py:104`; portanto, a conclusão depende do percurso examinado, não apenas da string. `TransportError` puro produz `transporte_TransportError`, não `transporte_Timeout`.

2. **Decisão 0072:** coerente como redução formal e explícita do aceite do I1, registrada no rótulo. Não transforma o limite do TCU em indisponibilidade classificada, não ressalva DataJud e impede expressamente sua aplicação ao I2. A etapa 8 original continua exigível nos incrementos seguintes.

3. **I1 e I2 do r1:** corrigidos. Os quatro XMLs passam diretamente pelo parser. A redação sobre DataJud agora limita a conclusão a “não foi demonstrada regressão” e reconhece a causa não isolada.

4. **Baterias:** conferi os 34 resultados individuais de cada XML contra seu JSON, sem divergência:

   | Execução | Aprovados | Xfail | Falhas |
   |---|---:|---:|---:|
   | 28/10, `6ac49ee` | 25 | 5 | 4 |
   | Tentativa 1, `5c86054` | 25 | 3 | 6 |
   | Tentativa 2, `5c86054` | 24 | 5 | 5 |
   | Tentativa 3, `5c86054` | 22 | 8 | 4 |

   A tentativa 3 tem `completa: true`, commit integral concordante entre texto e JSON e contagens iguais nos três formatos. Serve como bateria live da etapa 2. As quatro falhas são Planalto ×3 e TCU negativo, já fora do escopo. Os oito xfail são CVM ×2 por timeout, TJDFT ×3 por 503 e TJSP ×3 por desafio; o hook exige categoria admitida **e evidência não vazia**.

5. **Etapa 8 em datas diferentes:** a bateria de 28/10 continua servindo. A seção 5 não exige mesma sessão ou dia. As árvores de `5c86054` e `6ac49ee` são idênticas; não houve mudança posterior em produção ou `tests/live` até o HEAD auditado. As janelas distintas permanecem identificadas.

6. **Normalização:** o JSON atual tem SHA-256 `f2c64a5719bc1cccaf6ca05e97e8e6ef4d2bb8bc8cebf036190928f147437717`. Resserializando seu conteúdo em memória com indentação 2 e CRLF, reconstruí `c9cfd8b61ae6c68cd3fa87c30f2ef91483602799ab9bdcee109b63245894439d`, compatível com o hash original registrado. Confirma-se a mudança exclusivamente de formatação.

Auditoria documental e estática no HEAD `4bd057e` com os arquivos locais apresentados. `git diff --check` passou. Sem edição, nova execução online ou reexecução da suíte offline/Ruff.

SEM BLOQUEADOR