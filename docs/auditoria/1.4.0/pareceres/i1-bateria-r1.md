## BLOQUEADORES

**B1 — O doctor não cumpre integralmente a etapa 8.** A afirmação de que todos os alertas são “indisponibilidade classificada por prova” em [aceite-i1.md:35](/C:/dev/fv14-aceite/docs/auditoria/1.4.0/aceite-i1.md:35) não se sustenta:

- **DataJud `http_429`:** o mapeamento devolve `Unavailable` com **categoria `None`**, embora retenha evidência HTTP; veja [challenge.py:161](/C:/dev/fv14-aceite/freoa_verifica/connectors/challenge.py:161). Não cabe atribuir-lhe retrospectivamente `fonte_fora`.
- **TCU `tcu_busca_incompleta_limite_de_varredura`:** é levantado **sem categoria e sem evidência**, em [tcu.py:147](/C:/dev/fv14-aceite/freoa_verifica/connectors/tcu.py:147). Prova limite de varredura, não indisponibilidade externa classificada.

O doctor reduz as sondas a nome/status/detalhe e considera qualquer `alerta` compatível com resultado global `ok`: [service.py:3243](/C:/dev/fv14-aceite/freoa_verifica/service.py:3243). Logo, saída 0 não prova o requisito adicional da seção 5.8. As reduções de escopo examinadas não dispensam esse requisito.

## IMPORTANTES

**I1 — XML inválido após saneamento.** A leitura direta de [live.xml](/C:/dev/fv14-aceite/docs/auditoria/1.4.0/aceite-i1/live.xml) por `ElementTree` falha: `mismatched tag: line 311, column 55`. Há 12 marcadores `<localappdata>` sem escape no conteúdo dos tracebacks. Escapando esses marcadores **somente em memória**, o XML torna-se legível e suas 34 entradas conferem individualmente com o JSON. O artefato entregue precisa preservar XML válido.

**I2 — Conclusão causal excessiva sobre DataJud.** “Nenhuma das duas é regressão do código”, em [aceite-i1.md:58](/C:/dev/fv14-aceite/docs/auditoria/1.4.0/aceite-i1.md:58), excede a prova. O conector DataJud e `transport.py` **não mudaram entre `68e743a` e `6ac49ee`**, mas isso não exclui toda regressão indireta. `httputil.py` recebeu um parâmetro opcional `repeticao`; DataJud não o fornece e preserva o comportamento padrão. A conclusão sustentada é: **não foi demonstrada regressão; a causa da indisponibilidade não foi isolada**.

## MENORES

- Não encontrei caminho absoluto de máquina remanescente nos seis artefatos de `aceite-i1/`. Entretanto, o XML conserva o hostname real no atributo `hostname`.
- Windows aparece nos registros; **IP brasileiro é declaração do executor**, sem comprovação independente nos anexos.
- O teste DataJud “documento” aprovado verifica a ausência estrutural do STF; não comprova recuperação documental online.

## VALIDAÇÃO

- **Identidade:** HEAD, tag local `v1.4.0a1`, início de `live.txt`, saúde e recibo de instalação apontam para `6ac49ee520afcd37c26e2f9e640952dd7ea2da8a`. O log registra importação do checkout, versão `1.4.0a1`, Python `3.14.6`, com somente a wheel não versionada naquela execução.
- **Completude e contagens:** 34 testes, **25 aprovados, 5 xfail e 4 falhas**, sem `not_run`. Conferem no texto, no JSON e no XML após o escape em memória. `completa: true` significa execução completa, não aprovação.
- **Tempos coerentes:** wrapper 12:07:00–12:11:01; XML 12:07:11–12:10:59; saúde 12:07:23–12:10:59, todos em UTC−3. O início posterior da saúde corresponde ao carregamento do conftest durante a coleta. SHA-256 da saúde confere com o declarado.
- **Escopo:** Planalto ×3 e TCU negativo repetem as quatro falhas da linha de base. Podem permanecer como falhas fora do escopo do I1, conforme registro anterior; isso **não sana B1 no doctor**. Não identifiquei outra falha não classificada na bateria.
- **Xfail:** nenhum marcador novo ou alargamento do arnês. Entre a linha de base e a tag, `tests/live` mudou apenas para preencher `inicio`; categorias e exigência de evidência permaneceram iguais. Os dois novos xfail são DataJud `fonte_fora:http_504`; os três restantes são TJSP `ambiental_desafio:desafio_captcha`.
- Auditoria documental e estática, sem nova execução online nem edição de arquivos. O diff dos arquivos versionados permaneceu vazio.

COM BLOQUEADOR