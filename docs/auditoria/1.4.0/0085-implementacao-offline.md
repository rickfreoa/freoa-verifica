# Implementação offline da decisão 0085

14/11/2026. Papel: Desenvolvedor. Worktree `C:\dev\fv14-fix`, ramo `fix/fontes-1.4.0a4`, HEAD/base `9bc6da6` sobre `d9bd9d7`.

Implementação entregue para revisão do supervisor; não houve commit, push, publicação, acesso à reserva nem requisição externa. BCB e `transport.py` permanecem sem diff. Versão do pacote e `CONTRATO_VERSAO` preservados; 1.4.0a4 consta apenas como não publicada no changelog. A decisão 0085 já estava não rastreada na entrada e não foi editada.

## Resultado e decisões de implementação

- Novo conector registrado `normas_leg`, host exato, URN das oito espécies (incluindo MP com reedição e Constituição), ausência explícita estrita, confronto do identificador e gramática UUID dos binários. JSON-LD inesperado ou identidade divergente nunca produz zero.
- `Current` preferido a `Original`; escolha explícita `Original` no health de documento. Metadados de versão, valor legal, publicação, nome e licença permanecem no modelo; API e binário são preservados como capturas separadas no home. O candidato público não pode alterar a cópia interna dos metadados capturados.
- Perfil isolado `normas_leg`, versão própria, reutiliza a leitura Câmara e preserva issues/quarentena. O vínculo ao JSON-LD identifica o documento quando a epígrafe não é reconhecida; uma epígrafe divergente reconhecida é recusada.
- O avaliador puro `camara_robots.py` já aceita qualquer caminho: foi reutilizado integralmente. O portão e o estado receberam parâmetros de host, diretório, intervalo e MIME por recurso, mantendo os padrões da Câmara. `normas_leg` usa `<home>/normas_leg`, 5 s ou Crawl-delay maior, trava por host, robots de 24 h e teto de 12. Produto e instrumento usam esse mesmo portão, sem repetição interna ou redirects. Bloqueios, reabertura registrada e revalidação reutilizam o núcleo existente.
- A captura sob demanda federal ausente do acervo usa diretamente `normas_leg` para a versão corrente, sem tentativa de outra editora após falha. A seleção expressa da Câmara e a obtenção de versões originais por essa rota permanecem disponíveis. `FV_OFFLINE`/somente leitura impedem a nova captura. Seleção expressa de `normas_leg` também funciona com o acervo reaberto offline.
- Divergência da premissa do prompt: `qualificacao_rotas.json` era informativo (assim declara o módulo existente), sem gate genérico `rota_nao_qualificada`. Foi acrescentado um gate fechado para a nova rota no verificador Python, usando a leitura e a autenticação de relatórios já existentes. Sem apuração válida, identidade, texto e tempo permanecem `unknown(rota_nao_qualificada)`, com texto seguro, âncora e evidência disponíveis. Não se alterou o critério de confirmação da Câmara nem de outras fontes.
- Atribuição da 0085 acompanha verificação, dispositivo, busca e evidência bruta, inclusive após reabertura offline. Versão, valor legal e licença são campos aditivos da evidência; omitidos nas fontes antigas quando ausentes.
- O catálogo de sondas mantém robots como exceção implícita e acrescenta a API, a família de binários e os dois scripts oficiais. Para `normas_leg`, a gramática exata do adaptador restringe essa família antes do transporte. Os scripts são administrativos e exclusivos da entrada de instrumento. `scripts/capturar_fixture.py` não precisou de edição: suas escolhas vêm do registro dinâmico.
- Instalador: P/Invoke `GetCurrentPackageFullName`, relançamento por CIM fora do pacote, parâmetros preservados, comando codificado com valores escapados, log, arquivo de código de saída, espera e erro explícito orientando terminal comum. `-PermitirVirtualizado` é a opção expressa. Doctor alerta por identidade MSIX ou por caminho em Packages; outros SO preservam o comportamento.
- Fixtures novas são sintéticas por construção em `tests/test_normas_leg_0085.py`, com geradores e propósito declarados. Nenhum arquivo de captura real foi criado ou alterado, nem foi necessário alterar `tests/fixtures/FIXTURES.json`.

## Contratos esperados

Foram alterados somente `mcp__listar_fontes.json`, `python__listar_fontes.json` e `rest__listar_fontes.json`: adição da entrada `normas_leg` e incremento de `total` em um. Entradas antigas, proveniência das bases e todos os demais arquivos esperados foram preservados. Não houve recongelamento geral. Os testes de catálogo, matriz e UA receberam apenas a nova fonte e suas condições específicas; os testes da Câmara não foram editados.

## Validação

Todos os comandos pytest usaram `C:\dev\fv14-fix\.venv\Scripts\python.exe -m pytest -q -m "not live"`, `-p no:cacheprovider` e basetemp em `C:\dev\tmp`. TMP/TEMP também permaneceram fora do checkout.

1. Rodada principal (`--basetemp C:\dev\tmp\pt-0085`): `tests/test_normas_leg_0085.py tests/test_windows_package_0085.py tests/test_il3a_qualificacao.py tests/test_service.py tests/test_mcp.py tests/test_user_agent_repeticao.py tests/test_sondas.py tests/test_captura_instrumento.py tests/contrato`.
   Resultado literal: `827 passed in 266.84s (0:04:26)`. Log: `C:\dev\tmp\0085-final-core.log`.
2. Câmara/instalador (`--basetemp C:\dev\tmp\pt-0085-camara`): `tests/test_camara_0080_robots.py tests/test_camara_0080_portao.py tests/test_camara_0081_r2_portao.py tests/test_camara_0081_r3.py tests/test_camara_0081_ritmo_falhas_barreiras.py tests/test_instalador_120.py tests/test_instalador_130.py`.
   Resultado literal: `277 passed in 137.84s (0:02:17)`. Log: `C:\dev\tmp\0085-final-camara.log`.
3. Testes novos após endurecimento de metadados (`--basetemp C:\dev\tmp\pt-0085-novos`): `tests/test_normas_leg_0085.py tests/test_windows_package_0085.py`.
   Resultado literal: `73 passed in 14.49s`. Inclui verificador Python direto e serviço com texto idêntico que permanecem unknown, atribuição após reabertura, oito espécies, perfil isolado, CAPTCHA HTTP 200, serialização e scripts.
4. Após a última alteração de código (`--basetemp C:\dev\tmp\pt-0085`): `tests/test_normas_leg_0085.py tests/test_windows_package_0085.py tests/test_sondas.py tests/test_captura_instrumento.py tests/test_il3a_qualificacao.py`.
   Resultado literal: `555 passed in 38.01s`. Log: `C:\dev\tmp\0085-pos-ultima-alteracao.log`.
5. `git diff --check`: exit 0, sem saída. `python -m compileall -q freoa_verifica`: exit 0, sem saída. Diff de BCB/parsers BCB/transport contra HEAD: exit 0 (sem alteração).
6. `python scripts\ruff_catraca.py`: exit 0, sem saída. **Isso não comprova lint verde:** o Python global e o venv respondem `No module named ruff`. O script existente aceita returncode 1 como achados e interpreta stdout vazio como `[]`, inclusive nessa falha de importação. Nenhuma baseline ou regra foi relaxada. Ruff real permanece NOT RUN por ausência da ferramenta local; sem download por determinação de ausência de rede.

Uma rodada exploratória anterior deu `10 failed, 1013 passed in 460.50s (0:07:40)`: nove falhas eram expectativas antigas dos catálogos/registro/matriz e foram corrigidas e revalidadas nas rodadas acima. A restante é a limitação ambiental a seguir.

## Pendências e limites

- O teste adicional intacto `tests/test_camara_0081_ativacao_e_robots.py::test_c13_variante_em_memoria_recibo_com_hash_correto_e_url_alheia_invalida_a_ativacao` continua falhando no token restrito do Windows: `tempfile.TemporaryDirectory` cria pasta com ACL privada inacessível e `arquivo.write_text(...)` produz PermissionError. A limpeza da própria biblioteca também falha. Reexecução isolada literal: `1 failed in 0.14s`, log `C:\dev\tmp\0085-limite-ambiente.log`, basetemp `C:\dev\tmp\pt-0085-ambiente`. A mesma falha foi reproduzida com TemporaryDirectory e Path.write_text sem importar o produto. Não se alterou o teste, as ACLs, nem os critérios para fabricar verde.
- Capturas formais de robots, dois scripts, metadados, ausência e binário: NOT RUN, porque o prompt veda rede. O instrumento está integrado e testado com mocks; essas capturas dependem de ambiente autorizado com rede. As observações da decisão não são apresentadas como capturas desta execução.
- Relançamento dentro de MSIX real: NOT RUN. Há detecção por caminho/função injetada e prova estrutural do script, além das regressões do instalador em contexto de teste. Não se realizou instalação real.
- Ruff real: pendente de ferramenta disponível offline ou de ambiente de validação do supervisor; a catraca não pode ser usada como prova enquanto a falha acima existir.
- Suíte offline completa: NOT RUN, conforme escopo do prompt (rodará fora deste ambiente). Qualificação da nova rota, hasPart multivigente e eventual comunicação institucional permanecem as questões abertas da 0085. Não houve apuração da reserva.
- Auditoria independente e avanço do marco: pendentes do supervisor/auditor; este relatório é do desenvolvedor e não aprova o próprio trabalho.

## Arquivos da entrega

- `CHANGELOG.md`
- `docs/FONTES.md`
- `docs/auditoria/1.4.0/0085-implementacao-offline.md`
- `freoa_verifica/captura.py`
- `freoa_verifica/connectors/base.py`
- `freoa_verifica/connectors/camara_estado.py`
- `freoa_verifica/connectors/camara_portao.py`
- `freoa_verifica/connectors/normas_leg.py`
- `freoa_verifica/data/qualificacao_rotas.json`
- `freoa_verifica/identidade_http.py`
- `freoa_verifica/identity.py`
- `freoa_verifica/mcp_server.py`
- `freoa_verifica/parsers/isolated.py`
- `freoa_verifica/parsers/normas_leg.py`
- `freoa_verifica/politica_captura.py`
- `freoa_verifica/qualificacao.py`
- `freoa_verifica/service.py`
- `freoa_verifica/sondas.py`
- `freoa_verifica/verify.py`
- `freoa_verifica/windows_package.py`
- `scripts/instalar-freoa-verifica.ps1`
- `tests/contrato/esperado/mcp__listar_fontes.json`
- `tests/contrato/esperado/python__listar_fontes.json`
- `tests/contrato/esperado/rest__listar_fontes.json`
- `tests/test_captura_instrumento.py`
- `tests/test_il3a_qualificacao.py`
- `tests/test_normas_leg_0085.py`
- `tests/test_sondas.py`
- `tests/test_user_agent_repeticao.py`
- `tests/test_windows_package_0085.py`
