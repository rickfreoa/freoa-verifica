# Relatório de sondas SONDAS: pesquisa de fontes

Data das capturas: 2026-10-20 (UTC). Instrumento: `scripts/capturar_fixture.py --sonda` (passa por `freoa_verifica.transport`). Espaçamento mínimo de 5 s entre requisições; 30 s entre consultas TJSP. Nenhum outro meio de rede. Sidecars `*.captura.json` e corpos ficam em `C:\dev\fv-130\sondas\`, fora do repositório.

## Grupo 1: TJDFT (F1)

Consulta: `dissolução parcial de sociedade`, página 1, tamanho 5. UA identificado (modo próprio do conector).

| Variante | Status | Desafio | Achado | sha256 |
|---|---|---|---|---|
| (a) base | 200, 104 853 bytes | não | Campo `inteiroTeor` com texto em 1 de 5 registros; `possuiInteiroTeor` true em 4 de 5. Datas 2026-09-30 e 2026-10-08. | `8e2b71b8f589917aff51c314d3e0cdd66080b122ed16c2ba44c81aeeef8784d0` |
| (b) `extras.retornaInteiroTeor=true` | 200, 241 544 bytes | não | `inteiroTeor` com texto em 5 de 5 registros. Arquivo maior que (a). Datas 2026 (não há recorte 2024). | `47dbaf4a21daf49eb53570ce7b14363a8c15081c0d5f447650b0003ff2275b15` |
| (c) `extras.inteiroTeor=true` | 200, 104 853 bytes | não | Idêntica a (a) byte a byte. Chave sem efeito observável. | `8e2b71b8f589917aff51c314d3e0cdd66080b122ed16c2ba44c81aeeef8784d0` |
| (d) `termosAcessorios` lista `[{"campo":"dataJulgamento","valor":"entre 01/01/2024 e 31/12/2024"}]` | HTTP 500 → `unavailable(http_500)` | não | Recusada. | sem arquivo |
| (d2) `termosAcessorios` string `"entre 01/01/2024 e 31/12/2024"` (uma tentativa) | HTTP 400 → `unavailable(http_400)` | não | Recusada. | sem arquivo |

Observações sobre (b): os marcadores "RELATÓRIO", "VOTO", "DISPOSITIVO" (com "DEU PROVIMENTO" / "NÃO CONHECIDO") e "Ante o exposto" / "É como voto" aparecem no arquivo. O fecho com local e data (`Brasília (DF), dd de … de 2026`) aparece em 4 de 5 textos. Os números CNJ dos processos aparecem dentro do texto. Tamanho por campo não foi medido; só o tamanho do arquivo inteiro.

## Grupo 2: TJSP (F3)

| Consulta (`cjsg`, termo) | Status | Desafio | Resultados informados | sha256 |
|---|---|---|---|---|
| `dissolução parcial de sociedade` (1ª) | 200 na etapa prévia `resultadoCompleta.do` | sim: marcador `captcha` | não obtidos | página de desafio `782ddba1332cdfd22cef418fe71400bd39cc1451e12109cb51014dd4e1941b95` (evidência, não fixture) |

Grupo parado no primeiro desafio, conforme a especificação. As 5 consultas restantes não foram feitas. Amostra: 1 de 1 requisição com desafio (taxa 100%, mas com n = 1). O limite de desafio não foi medido.

## Grupo 3: UA identificado (T2)

| Conector | Recurso | Status | Desafio | Conteúdo esperado | Resultado | sha256 |
|---|---|---|---|---|---|---|
| tjdft | consulta da variante (a) | 200 JSON | não | sim (acórdãos) | aceita | `8e2b71b8…8784d0` |
| tjsp | `cjsg` termo `acordo de acionistas` | 200 com marcador `captcha` | sim | não | **recusa** (desafio) | não gravado como fixture |
| planalto | `ccivil_03/leis/l6404.htm` (2 tentativas) e `leis_2001/l10303.htm` (1) | sem resposta: `TransportError` nas 3 | — | não | **sem resposta** com UA identificado | nenhum |
| planalto | `robots.txt` | sem resposta: `TransportError` | — | não | sem resposta | nenhum |
| senado | `dadosabertos/legislacao/lista?tipo=LEI&numero=10303&ano=2001` | 200 XML, 1 140 bytes | não | sim (token 10303) | aceita | `62eeb65badc65f45e2af5ba847b5a8d80ec7dfbe87542ec1577a61f9cf1f0709` |
| cvm_normas | `legislacao/resolucoes.html` | 200 HTML, 77 882 bytes | não | sim | aceita | `764665ae86fc0d25fb2abc6a5c2e793bb2c5c8d3309bb3f4642b9dba79f39146` |
| cvm_colegiado | `feed/decisoes.xml` | 200 XML, 16 528 bytes | não | sim (`<item>`) | aceita | `73f8a19cc4e0f512e024d6709e69d19a9e1a7155326545f3906ab0f1cef6d187` |
| bcb | `api/conteudo/…/exibenormativo?p1=Resolução CMN&p2=4966` | 200 JSON, 306 588 bytes | não | sim (token 4966) | aceita | `8d2ac4d5dde4b1277564739854138c8154ea838e84396832c8fad7669b09358c` |
| stf | `jurisprudencia/sumariosumulas.asp` | 200 HTML, 54 470 bytes | não | sim (Súmula) | aceita | `cf28f572189dc6d3249d027d398f49a1f13c709e43ffe4f23749164a7072269c` |
| stj | `package_show?id=espelhos-de-acordaos-primeira-turma` | 200 JSON, 42 159 bytes | não | sim | aceita | `9db5f0bc2b19ce3352427065678395b6ddae619e048702cfcc53d744e2d88450` |
| tcu | `recupera-acordaos?inicio=0&quantidade=2` | 200 JSON, 2 621 bytes | não | sim | aceita | `ab46c0ab5a8f7b69864b5fdd447be51ca4ff5ec73bad2cef1e8f59626b08f2c5` |
| datajud | — | não sondado | — | — | o instrumento só faz GET por URL para este conector; a API é POST `_search` | — |
| comunica_cnj | — | não sondado | — | — | instrumento sem conector `comunica_cnj` | — |

Controle (UA do conector, mesma URL): planalto `l6404.htm` → HTTP 404; planalto `robots.txt` → HTTP 404; tjsp `robots.txt` (UA identificado) → HTTP 404 (o host não publica `robots.txt` neste caminho). Ou seja: com o UA do conector o planalto responde 404; com o UA identificado não responde (TransportError). A causa não se separa pelos bytes. Não é possível dizer se é o UA, a rota ou a URL.

## Conclusões por questão

**F1 (TJDFT).** Sim, há íntegra: com `retornaInteiroTeor=true`, os 5 registros trazem o campo `inteiroTeor` com texto. Com o `extras` padrão, só 1 de 5 traz o texto. Cada texto contém número de processo, dispositivo e fecho na maioria dos casos (fecho em 4 de 5 pelo padrão observado). Verificação registro a registro completa não foi feita. O recorte de data **não** é satisfeito: as duas formas de `termosAcessorios` foram recusadas (500 e 400), e os resultados da base são de 2026. A aplicação do filtro de data, se houver, é local, segundo o comentário do próprio conector em `freoa_verifica/connectors/tjdft.py` (linha 172).

**F3 (TJSP).** A primeira consulta já caiu em desafio CAPTCHA (`marcador: captcha`) com UA do conector. O teste com UA identificado também caiu em CAPTCHA. Em 2 de 2 requisições houve desafio. Não há amostra suficiente para estimar um limite. O grupo parou conforme a regra.

**T2 (UA identificado).** Aceitam o UA identificado (200 com conteúdo esperado): tjdft, senado, cvm_normas, cvm_colegiado, bcb, stf, stj, tcu. Recusam ou não respondem: tjsp (desafio CAPTCHA) e planalto (TransportError nas 4 tentativas, incluindo `robots.txt`). Não sondados: datajud e comunica_cnj. Provas: os sidecars listados na tabela acima.

## Limites desta sonda

- Uma única consulta TJSP antes do desafio. Sem resultados informados.
- Planalto: falha de transporte reproduzível com UA identificado, sem causa separada.
- `robots.txt` do TJSP não existe (404); não há URL pública de termos do TJSP capturada.
- Não há captura de termos de dados abertos além dos recursos listados.
