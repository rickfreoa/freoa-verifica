# Relatório de avaliação — FREOA Verifica

**Data:** 18 de outubro de 2026  
**Versão examinada:** 1.0.2  
**Commit:** `5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e`

**Conclusão:** o repositório tem uma arquitetura consistente para conferência documental e boas decisões de segurança. Merece continuidade. Entretanto, encontrei falhas de implementação e lacunas operacionais que precisam ser corrigidas antes de recomendar sua exposição como serviço remoto compartilhado.

O melhor enquadramento atual é **ferramenta de apoio à conferência de fontes, com cobertura delimitada e supervisão humana**. A evidência examinada não sustenta tratá-la como certificador completo de documentos jurídicos.

## 1. Escopo e força das conclusões

Examinei código, documentação, testes selecionados, configurações de integração contínua e publicação, metadados das releases e logs da CI. Confirmei que a tag `v1.0.2` aponta para o commit acima, que também era o `main` consultado. [Versão examinada](https://github.com/rickfreoa/freoa-verifica/tree/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e).

A CI desse commit terminou com sucesso nas seis combinações de Windows/Linux e Python 3.11–3.13. Consultei os logs de duas delas: ambas registraram **4.980 testes aprovados, 30 desmarcados e 10 avisos**. Isso constitui evidência positiva de execução remota da suíte configurada. [Execução da CI](https://github.com/rickfreoa/freoa-verifica/actions/runs/39116745658).

**Limitação relevante:** não obtive execução local válida da suíte ou das reproduções propostas. O ambiente apresentou falhas de inicialização e resolução de rede. Portanto:

| Verificação | Situação |
|---|---|
| Inspeção estática do código e documentação | Executada |
| Consulta aos resultados e logs da CI | Executada |
| Reprodução local dos novos achados | **NOT RUN — sem resultado válido** |
| Testes de carga e exploração contra servidor ativo | **NOT RUN** |
| Inspeção dos bytes do wheel publicado | **NOT RUN** |
| Instalação e auditoria integral do snapshot publicado | **NOT RUN** |
| Verificação criptográfica das attestations | **NOT RUN** |
| Varredura atual de vulnerabilidades das dependências | **NOT RUN** |
| Conferência independente das métricas do README | **NOT RUN** |

Os achados abaixo distinguem comportamentos diretamente identificáveis no código de impactos que ainda dependem de reprodução. **Não apresento exploração remota, RCE ou desvio de SSRF como demonstrados.**

## 2. Aspectos positivos

Há decisões que merecem ser preservadas:

- **Separação entre identidade, texto, tempo e suporte.** O código evita transformar correspondência textual em validação da proposição jurídica. `support` permanece `not_assessed`.
- **Transporte defensivo.** Há HTTPS obrigatório, lista de hosts permitidos, bloqueio de endereços inseguros, conexão ao IP resolvido, validação de redirecionamentos e limites de transferência.
- **Conferência de integridade.** Os blobs são endereçados por SHA-256 e verificados na leitura; existem verificações adicionais antes de devolver evidência.
- **Estados conservadores.** Indisponibilidade, ambiguidade e insuficiência de evidência têm representação própria.
- **Teste do pacote instalado.** A CI constrói e instala o wheel e executa os testes fora do diretório do código-fonte.
- **Limitações documentadas.** O README reconhece recortes de cobertura, barreiras de acesso, incompletude histórica e ausência de avaliação do suporte jurídico.

Esses aspectos aparecem efetivamente no código e na configuração examinados. Sua presença, contudo, não demonstra que todos os caminhos de execução respeitem integralmente os contratos anunciados. [Arquitetura](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/docs/ARQUITETURA.md), [transporte](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/transport.py), [CI](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/.github/workflows/ci.yml).

## 3. Quadro dos principais achados

A gravidade considera o cenário de implantação. Um risco alto em servidor exposto pode ter impacto muito menor em execução local individual.

| ID | Achado | Classificação | Evidência |
|---|---|---|---|
| F01 | Proteção de autenticação depende do caminho de inicialização | Alta em implantação remota | Código |
| F02 | REST aceita entradas sem os limites definidos no MCP | Alta para disponibilidade em serviço exposto | Código; carga não medida |
| F03 | Extração de PDF sem isolamento efetivo no caminho examinado | Média, podendo aumentar conforme a exposição | Código; exploração não demonstrada |
| F04 | Corte em 200 citações sem informar truncamento | Média, de confiabilidade | Código |
| F05 | Posições de evidência incorretas após certas normalizações Unicode | Média, de fidelidade | Derivação direta do algoritmo |
| F06 | Fechamento de conexões SQLite pode falhar entre threads e silenciar o erro | Média, operacional | Código e contrato da biblioteca |
| F07 | Registro persistido precede ajustes finais do resultado | Média, de auditoria | Ordem das operações |
| F08 | Singleton MCP ignora outro diretório de dados no mesmo processo | Média em uso com múltiplas instâncias | Código |
| F09 | Persistência de entradas exige política explícita de retenção | Média, conforme os dados processados | Código |
| F10 | Publicação não exige a suíte completa e permite substituir assets | Média, de distribuição | Workflow |

## 4. Achados detalhados

### F01 — Autenticação incompleta nas diferentes formas de inicialização

Na API REST, `run_api()` recusa endereço não local sem token. Porém, `create_app()` permite autenticação desativada quando não existe token e não aplica a mesma condição de exposição.

Isso permite que uma implantação que carregue diretamente a fábrica ASGI deixe de passar pela proteção do lançador. **A proteção existe, mas não acompanha necessariamente a aplicação.**

No MCP, `run_server()` aceita `host` configurável e inicia HTTP sem configurar autenticação da aplicação. Isso não significa que todas as proteções do SDK estejam ausentes; significa que **não identifiquei nesse código uma exigência equivalente à autenticação REST para exposição remota**. [REST](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/rest.py), [MCP](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/mcp_server.py).

**Impacto:** terceiros que alcancem uma instância assim configurada podem utilizar consultas, consumir recursos e acessar o acervo disponibilizado por ela.

**Recomendação:** definir modos explícitos de operação local e remota; exigir autenticação no modo remoto em todos os pontos de entrada; documentar TLS e proxy; testar a inicialização pela CLI e diretamente pela fábrica ASGI.

**Critério de aceite:** nenhuma configuração remota suportada atende requisição anônima.

### F02 — Validação e limites inconsistentes entre REST e MCP

O MCP declara limites de comprimento e faixas numéricas. A REST recebe, por exemplo, corpos como `dict[str, Any]` e repassa os campos para o serviço.

Em `verificar_citacao()`, não encontrei limite equivalente para `citacao` e `trecho`. Assim, a restrição do MCP não protege quem acessa o mesmo serviço pela REST. Tipos inadequados também podem chegar à lógica interna em vez de serem rejeitados na entrada. [REST](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/rest.py), [serviço, linhas 1006–1088](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/service.py#L1006-L1088).

O comparador utiliza `SequenceMatcher(..., autojunk=False)`. A documentação do Python registra custo quadrático no pior caso para esse algoritmo. O custo real desta aplicação ainda precisa ser medido. [Comparador](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/textcmp.py), [documentação do Python](https://docs.python.org/3/library/difflib.html).

**Impacto:** risco de consumo excessivo de CPU, memória e armazenamento. Os limites de download não controlam o custo de processamento de entradas da API.

**Recomendação:** aplicar validação compartilhada na fachada do serviço, além dos adaptadores; limitar o corpo HTTP antes de sua leitura integral; estabelecer orçamento de processamento, concorrência e gravações.

**Critério de aceite:** entradas inválidas ou excessivas são rejeitadas de forma previsível, com testes de carga que demonstrem limites de recursos.

### F03 — Limites de download não isolam a extração de PDF

O caminho `_parse_pdf()` da CVM instancia `PdfReader` e percorre as páginas diretamente no processo que executa a operação.

Existe `parse_isolated()`, mas seus perfis são `planalto`, `cvm_docx` e `bcb_json`; o caminho PDF examinado não utiliza esse isolamento. O próprio módulo informa que a memória depende do hospedeiro. [Extração de PDF](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/connectors/cvm_normas.py#L396-L427), [isolamento](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/parsers/isolated.py).

**Impacto:** um arquivo admitido pelo limite de transferência ainda pode exigir processamento desproporcional. Não demonstrei um PDF explorável nem um mecanismo pelo qual um usuário remoto forneça PDF arbitrário; as fontes permitidas reduzem essa exposição.

**Recomendação:** executar parsers de maior risco em processos descartáveis, com limites efetivos de memória, CPU, tempo, páginas e texto extraído.

**Critério de aceite:** documentos patológicos terminam a operação com estado controlado, sem derrubar o servidor ou deixar processos órfãos.

### F04 — Verificação de texto pode omitir citações silenciosamente

`verificar_texto()` extrai as citações e, se houver mais de 200, executa:

```python
cites = cites[:200]
```

A resposta devolve o total processado, mas não informa o total detectado, a quantidade omitida ou um indicador de truncamento. [Serviço, linhas 1168–1264](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/service.py#L1168-L1264).

**Impacto:** o usuário pode interpretar uma resposta parcial como conferência integral. Uma citação problemática após o limite fica fora do resultado.

**Recomendação:** retornar `total_detectado`, `total_processado`, `truncado` e um mecanismo de continuação. Qualquer resumo deve indicar expressamente que a análise ficou incompleta.

**Teste necessário:** documento com 201 citações, colocando uma citação deliberadamente problemática na última posição.

### F05 — Âncora textual pode apontar para caracteres errados

`_map_norm_to_orig()` utiliza uma correspondência aproximada quando a normalização NFC altera o comprimento da string. Nesse caso, o código mantém índices praticamente posicionais, embora os caracteres posteriores tenham mudado de posição. [Comparador, linhas 108–138](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/textcmp.py#L108-L138).

Exemplo mínimo derivado do algoritmo:

```python
oficial = "e\u0301 abc"
resultado = compare("abc", oficial)
```

A normalização transforma os dois caracteres iniciais em `é`. O algoritmo encontra `abc` no índice 2 do texto normalizado, mas reutiliza esse índice no original. O intervalo calculado seleciona `" ab"` em vez de `"abc"`.

**Esta é uma reprodução proposta e derivada por leitura, não um teste executado nesta avaliação.**

**Impacto:** a comparação pode encontrar o texto corretamente enquanto a âncora devolvida perde fidelidade. Isso afeta diretamente a promessa de evidência reproduzível.

**Recomendação:** construir o mapa de origem durante as transformações e validar o trecho recuperado pelo intervalo antes de devolver a evidência.

**Critério de aceite:** testes com Unicode composto e decomposto, múltiplas composições e transformações que alterem comprimento.

### F06 — Fechamento de conexões SQLite pode falhar silenciosamente

O serviço cria conexões por thread, com o comportamento padrão de `sqlite3.connect()`, e guarda todas em uma lista. `_close_all_conns()` tenta fechá-las na thread que executa o encerramento e ignora qualquer exceção.

O contrato padrão do Python restringe o uso da conexão à thread que a criou. Assim, conexões abertas por trabalhadores podem falhar ao serem fechadas em outra thread. O código apaga sua lista mesmo depois dessas falhas. [Serviço, linhas 179–239](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/service.py#L179-L239), [documentação de `sqlite3`](https://docs.python.org/3/library/sqlite3.html#sqlite3.connect).

**Impacto:** encerramento não confiável, referências ou recursos remanescentes e possível interferência em operações que pressupõem o banco fechado. A instalação de snapshot chama esse fechamento antes de substituir arquivos.

**Recomendação:** definir propriedade e ciclo de vida das conexões; fechar cada conexão no contexto adequado; registrar falhas; impedir substituição de banco enquanto houver operações ativas. Alterar apenas `check_same_thread` não resolve a necessidade de coordenação.

### F07 — Resultado persistido pode divergir do resultado final devolvido

O núcleo persiste o resultado e retorna `run_id`. Depois disso, a fachada ainda:

- rebaixa `verified` quando falta captura;
- autentica evidências;
- pode trocar o estado para `unavailable`.

Esses ajustes ocorrem depois da gravação de `result_json`. [Persistência](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/verify.py#L608-L634), [ajustes posteriores](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/service.py#L1080-L1120).

**Impacto:** nos caminhos em que haja rebaixamento posterior, o recibo persistido pode representar uma conclusão diferente daquela entregue ao consumidor.

**Recomendação:** concluir as validações antes da persistência ou registrar separadamente resultado intermediário e resultado final, com vínculo explícito.

**Critério de aceite:** o resultado recuperável por `run_id` corresponde semanticamente ao devolvido, inclusive quando uma validação final falha.

### F08 — Singleton MCP não respeita múltiplos diretórios no mesmo processo

O módulo mantém `_svc` global. Depois da primeira criação, `_service(home)` retorna a instância existente sem conferir se o novo `home` é diferente. [Servidor MCP](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/mcp_server.py).

**Impacto:** duas instâncias MCP criadas no mesmo processo podem compartilhar involuntariamente o primeiro acervo. É um risco condicionado à incorporação em hospedeiros com múltiplas instâncias; não demonstra vazamento entre instalações separadas.

**Recomendação:** associar o serviço à instância criada e ao seu ciclo de vida, eliminando o singleton global ou recusando configurações conflitantes.

### F09 — Persistência de entradas exige política de privacidade e retenção

`_persist()` armazena em `request_json` a citação, o trecho, a data e o modo. O hash da requisição acompanha esses dados; ele não os anonimiza.

Existem triggers que impedem alteração e exclusão de execuções pelas operações usuais. Isso favorece rastreabilidade, mas exige política deliberada de retenção e descarte. [Persistência](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/verify.py#L608-L634), [esquema](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/store/migrations/0001_inicial.sql).

**Impacto:** trechos submetidos podem permanecer no banco, backups e cópias operacionais. Não afirmo que o parecer inteiro seja armazenado.

**Controles positivos:** há modo somente leitura, e o inventário de exportação de snapshot exclui `run`. Essas medidas devem ser preservadas.

**Recomendação:** informar claramente a persistência; permitir operação sem registro de entradas; separar evidência pública de conteúdo submetido; definir retenção, permissões locais e descarte controlado.

### F10 — Publicação pode ocorrer sem a suíte completa como pré-condição

O workflow de release faz build, teste básico e attestation. Não exige, no próprio fluxo, aprovação da suíte completa para aquele commit.

Além disso, se a criação da release falhar, o comando alternativo utiliza upload com `--clobber`, permitindo substituir assets existentes. Actions são referenciadas por tags e as dependências têm faixas abertas, sem arquivo de resolução reproduzível identificado na árvore examinada. [Workflow de release](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/.github/workflows/release.yml), [dependências](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/pyproject.toml).

**Impacto:** a publicação depende de coordenação externa ao workflow, e uma versão nominal pode receber bytes diferentes.

**Recomendação:** exigir a suíte completa sobre o mesmo commit antes de publicar; impedir substituição silenciosa; fixar Actions por commit; registrar dependências resolvidas e inventário de componentes.

Não identifiquei uma CVE específica nesta avaliação. Isso depende de uma varredura própria.

## 5. Limitações funcionais e de confiança

**Cobertura jurisprudencial parcial.** O README delimita recortes de STJ, TCU e CVM e reconhece barreiras em STF e TJSP. Esses recortes não sustentam conclusão geral de inexistência de precedente. A limitação precisa acompanhar cada resposta, especialmente resultados vazios. [Cobertura declarada](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/README.md).

**História normativa incompleta.** A ferramenta depende das redações e informações capturadas. Convém apresentar separadamente data consultada, data da captura, cobertura histórica e razão de eventual `unknown`. Não deve haver uma aparência de atualidade maior que a evidência disponível.

**Correspondência textual tem alcance limitado.** Um trecho pode ser literal e estar associado ao dispositivo correto sem sustentar a conclusão do usuário. Manter `support: not_assessed` é uma decisão adequada.

**Rótulos A–E exigem contexto.** A própria documentação os apresenta como convenção. Recomendo priorizar os atributos verificáveis — espécie, órgão, data e nível de prova — para reduzir a interpretação do rótulo como escala universal de autoridade. [Regra de classificação](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/authority.py).

**Checksum de snapshot não equivale a autenticação independente.** O instalador reconhece expressamente que a origem depende do canal da release e que eventual attestation precisa de conferência separada. Baixar pacote e checksum da mesma origem detecta corrupção, mas não resolve comprometimento dessa origem. Isso é uma limitação declarada, não uma vulnerabilidade nova demonstrada. [Modelo de confiança do snapshot](https://github.com/rickfreoa/freoa-verifica/blob/5d1936fcaf8b750ff6643c8069ea7a510bdb0f8e/freoa_verifica/snapshot.py).

A release consultada contém snapshot de aproximadamente **608 MB**. Seus metadados foram consultados; os bytes e o conteúdo interno não foram auditados nesta avaliação. [Release v1.0.2](https://github.com/rickfreoa/freoa-verifica/releases/tag/v1.0.2).

## 6. Como interpretar os testes e benchmarks

A quantidade de testes e o teste do pacote instalado são pontos fortes. Os dez avisos examinados decorrem do marcador `live` não registrado no contexto temporário de execução; recomendo levar a configuração de testes para esse contexto.

Os resultados adversariais do README são promissores, mas precisam conservar seus limites:

- zero falso positivo no conjunto não demonstra taxa universal zero;
- testes incorporados à regressão protegem contra reincidência, mas passam a ser conhecidos pela implementação;
- independência dos produtores dos conjuntos exige evidência própria;
- resultados de rodadas diferentes não devem ser somados sem verificar sobreposição;
- a CI offline não demonstra disponibilidade atual das fontes oficiais.

Recomendo reservar um conjunto novo, congelado e não utilizado durante as correções, com negativos difíceis, Unicode decomposto, documentos longos, falhas de armazenamento e concorrência.

## 7. Plano recomendado

| Prioridade | Entrega | Condição para considerar concluída |
|---|---|---|
| **P0** | Autenticação consistente em REST e MCP remoto | Todos os caminhos suportados recusam acesso anônimo |
| **P0** | Limites compartilhados de entrada e processamento | Testes demonstram rejeição previsível e recursos limitados |
| **P0** | Aviso de truncamento em `verificar_texto` | Nenhuma análise parcial aparenta ser integral |
| **P1** | Correção das âncoras Unicode | Intervalos recuperam o trecho correspondente |
| **P1** | Persistência do resultado final | Recibo e resposta permanecem consistentes nas falhas |
| **P1** | Ciclo de vida de conexões e instâncias | Concorrência e encerramento sem erros silenciados |
| **P1** | Isolamento de parsers | Arquivo patológico não compromete o servidor |
| **P2** | Retenção, distribuição e autenticidade | Política explícita e publicação reproduzível |
| **P2** | Ampliação de cobertura | Cada fonte nova recebe conjunto de referência e testes próprios |

**Decisão recomendada:** preservar a arquitetura e corrigir essas fronteiras antes de ampliar a exposição remota ou a promessa de cobertura. A intervenção de maior retorno é pequena e verificável: uniformizar validação e autenticação, explicitar análises parciais e garantir que a evidência persistida seja exatamente aquela que sustenta a resposta final.