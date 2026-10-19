# juscraper e FREOA Verifica: avaliação comparativa

19/10/2026 · Ricardo Peres Freoa

Base: [jtrecenti/juscraper](https://github.com/jtrecenti/juscraper) em `9d77731` (0.4.0, MIT) e FREOA Verifica em `239bef6` (v1.2.0). Nenhuma suíte executada e nenhuma fonte consultada ao vivo no exame; hipóteses sobre APIs oficiais estão marcadas como tais.

## Tese

O juscraper coleta dados de tribunais para análise em massa; o FREOA confere se uma citação jurídica corresponde a uma fonte oficial e prova como conferiu. O primeiro otimiza cobertura; o segundo, confiabilidade da afirmação.

1. No núcleo de evidência, o FREOA está à frente e não deve recuar (proveniência por captura com hash, transporte endurecido, abstenção tipada, recusa de contornar CAPTCHA e WAF, dígito verificador do CNJ, STJ por dados abertos).
2. Na engenharia que mantém conectores vivos ao longo do tempo, o juscraper está à frente (captura de amostras por script versionado, contratos que provam o payload enviado, monitor semanal com issue viva, separação tipada entre bloqueio ambiental e regressão, governança por meta-testes).
3. Em fontes, o juscraper aponta caminhos não explorados: parâmetros da API do TJDFT, API de busca do STF (sob WAF, fora), API de comunicações do CNJ, protocolo de coleta integral.

Regra de leitura: importar disciplina de engenharia, examinar fontes com cautela, não importar nada que enfraqueça o contrato de evidência.

## Lições de fontes

1. **TJDFT.** O FREOA envia só `query`, `pagina`, `tamanho`. A API aceita também `termosAcessorios` (datas "entre X e Y"), `sinonimos`, `espelho`, `inteiroTeor` (pesquisar no inteiro teor), `retornaInteiroTeor`, `retornaTotalizacao`. Hipótese: `retornaInteiroTeor: true` devolve o texto do acórdão. Confirmada, o critério da decisão 0041 passa a valer para acórdãos; refutada, o `FONTES.md` ganha prova negativa registrada.
2. **STF.** Busca do portal atrás de AWS WAF: proibida pela regra 3. Sobrevivem o protocolo de coleta integral (`_collection.py`: total exato `relation == "eq"`, recusa `timed_out`/shards falhos, janelas disjuntas, recontagem antes e depois) e a cadeia TLS embutida em vez de desligar verificação.
3. **Comunica CNJ** (`comunicaapi.pje.jus.br/api/v1/comunicacao`): `texto`, `tipoDocumento`, `siglaTribunal`, `nomeOrgao`, `numero_processo`, `data_disponibilizacao`, `link`, `hash`. Hipótese: para acórdão, sentença ou decisão, `texto` é a publicação oficial do ato. Confirmar UA identificado, recorte temporal, íntegra ou só ementa/dispositivo. "Texto publicado" deve ser estado próprio, distinto de inteiro teor.
4. **Falcão e PDPJ/JusBR**: fora (engenharia reversa; credencial pessoal).
5. **DataJud**: FREOA já melhor; aproveitar `search_after` se listar mais de 100.

## Lições de testes e saúde

- Captura de amostras por script versionado que importa do conector o construtor de payload e a URL base (teste AST reprova script que não importa); amostra nunca escrita à mão.
- Contrato por endpoint que envia todos os filtros e confere, por matcher, que chegaram à requisição.
- Monitor semanal com uma issue viva: corpo reescrito sem notificar; comentário só quando a lista de falhas muda; lista anterior em comentário HTML; não toca na issue se a execução não terminou; pula recesso; código 1 (fonte fora) vai para a issue, código 2+ (suíte quebrada) derruba o job; script com testes próprios.
- Bloqueio ambiental não é regressão: xfail só para a exceção tipada de bloqueio; resto vermelho; hook testado com `pytester`; lista de fontes fora do CI aparece no relatório.
- Bateria de release por janela de data: resultado não vazio, linhas dentro da janela, duas páginas ≥ uma.

## Lições de governança e CI

Lock congelado e testado; matriz até 3.14; Ruff com regras de segurança e catraca; Semgrep incremental; avisos centralizados; ciclo de vida da API pública (estabilidade do contrato JSON); exemplos do README como testes ao vivo; no `AGENTS.md`, amostras só reais e família de conectores só com duas ocorrências.

## O FREOA como primeira fonte de pesquisa

1. Cobertura onde está o direito societário: TJs (TJSP, TJRJ, TJMG, TJPR, TJRS). Medir ao vivo se o `cjsg` do TJSP responde sem desafio; conectores que exigem OCR ou navegador ficam fora.
2. Contrato de resposta para quem pesquisa: em `pesquisar_jurisprudencia`, por tribunal, o que foi consultado (acervo, ao vivo), recorte temporal, total informado pela fonte contra o lido, tribunais não cobertos.
3. Instruções e descrições do servidor MCP apresentando o FREOA como ponto de partida (pesquisar, obter, verificar antes de citar), com `listar_fontes` como primeiro passo.

## Não importar

Resolver WAF/CAPTCHA; ler cookies do navegador; imitar navegador e falsificar `Origin`/`Referer` como padrão; retry em 403; devolver vazio ou parcial com aviso; contrato por colunas; saneamento destrutivo de amostras; `FORA_DO_CI` como estado estável fora do relatório; `pandas`; meta-gates de complexidade.

## Fraquezas do FREOA reveladas

1. Fixtures do TJDFT e das íntegras do STJ fora do `FIXTURES.json`.
2. TJDFT sem teste ao vivo.
3. Monitor semanal silencioso (`continue-on-error` e `|| true`).
4. Nenhuma repetição de falhas transitórias; 503 isolado abre caminho para o circuit breaker.
5. User-Agent de navegador como padrão em oito de onze conectores.
6. CI sem lint, sem análise estática e sem lock.
7. Python 3.14 fora da matriz.
8. Ausência no PyPI.

## Aprimoramentos priorizados (do relatório)

P1: registrar fixtures e reprovar não registradas; sonda `retornaInteiroTeor`; `tests/live/test_live_tjdft.py`; issue viva. P2: script de captura; propagação de filtros; xfail ambiental; coleta integral no STJ e TCU; Comunica CNJ; CI (lock, 3.14, Ruff, Semgrep, meta-teste). P3: repetição 502/503/504 com `Retry-After`; UA identificado por padrão; estabilidade do contrato JSON; PyPI; bateria de release; `AGENTS.md`. Topo, pela frente de pesquisa: sonda do `cjsg`, bloco de cobertura por tribunal, instruções do MCP.
