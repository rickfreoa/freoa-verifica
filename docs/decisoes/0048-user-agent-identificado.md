# 0048 — User-Agent identificado por padrão e exceção do Planalto

Data: 20/10/2026. Origem: plano 1.3.0 (T2), sondas em `docs/auditoria/1.3.0/sondas/`.

## Decisão

Todo conector passa a se identificar como `freoa-verifica/<versão> (+https://github.com/rickfreoa/freoa-verifica)`, valor derivado de fonte única. Não há fallback: o código nunca troca de User-Agent depois de uma recusa.

As sondas de 20/10/2026, feitas pelo instrumento de captura (transporte do pacote, UA identificado), mostraram:

| Conector | UA identificado | Prova |
|---|---|---|
| tjdft, senado, cvm_normas, cvm_colegiado, bcb, stf, stj, tcu | aceito (200, conteúdo esperado) | sha256 no relatório das sondas |
| datajud | já identificado na 1.2.0 | — |
| tjsp (`cjsg`) | desafio CAPTCHA com qualquer UA | página de desafio `782ddba1…` |
| planalto | conexão encerrada sem resposta (`TransportError`), reproduzida em 5 tentativas; o mesmo recurso responde 200 ao UA da 1.2.0 | `planalto_l6404_identificado.captura.json`; `planalto_l6404_conector.html` (sha256 `6478ff36…dc48`) |

## Exceção: Planalto

O Planalto mantém o UA usado na 1.2.0, e somente ele. A exceção satisfaz as três condições do plano:

1. **Conteúdo oficial público sem autenticação.** Texto de leis federais, publicado para consulta irrestrita.
2. **Ausência de desafio.** Não há CAPTCHA, página de WAF, cabeçalho de borda nem `robots.txt` (404). A recusa é o encerramento da conexão diante de um cliente que se identifica; nada é resolvido, nenhum token é obtido, nenhum controle declarado é contornado.
3. **Permissão positiva de acesso automatizado.** A Lei 12.527/2011, art. 8º, § 3º, III, impõe aos sítios oficiais o dever de "possibilitar o acesso automatizado por sistemas externos em formatos abertos, estruturados e legíveis por máquina". O acesso automatizado à legislação federal é, portanto, o comportamento que a lei exige do próprio órgão, não uma exceção tolerada.

A exceção é de User-Agent apenas. Não autoriza `Origin`, `Referer`, cookies de navegador, troca de IP, repetição após recusa nem qualquer mudança diante de desafio. Se o Planalto passar a exibir desafio ou publicar restrição, o conector responde `unavailable` e a exceção cai.

## Questão aberta

A leitura de que o encerramento seletivo de conexão não é "controle de acesso" no sentido da regra 3 é razoavelmente controvertida. A alternativa (Planalto indisponível) suprimiria o núcleo de legislação federal do produto. A exceção fica sob revisão a cada versão, com nova sonda.

## TJSP

O `cjsg` exibe CAPTCHA independentemente do UA. O conector passa ao UA identificado e continua respondendo `unavailable(desafio)`; a afirmação do `FONTES.md` de que a busca está protegida fica confirmada por amostra (n = 2, ambas com desafio). Nenhuma mudança de comportamento além do UA.
