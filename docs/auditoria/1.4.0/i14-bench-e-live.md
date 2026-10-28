# I1.4 — bench e bateria ao vivo (linha de base da 1.3.0)

Executor: supervisor (Opus), no notebook Windows do titular, IP brasileiro. Data: 27–28/10/2026.

## Bateria ao vivo (`pytest -q -m live`)

Código: `7cf2b7c` (idêntico em código a `6a21865`; o delta é só `docs/PLANO-1.4.0.md`).
Resultado: 27 aprovados, 3 xfail, 4 falhas, em 128 s.

| Fonte | Resultado | Classificação |
|---|---|---|
| BCB, CVM colegiado, CVM normas, DataJud, Senado, STF, STJ, TJDFT, TCU (positivo e documento) | aprovados | — |
| TJSP (positivo, negativo, documento) | xfail | `ambiental_desafio:desafio_captcha`, com evidência (0045) |
| Planalto (positivo, documento) | falha | `recusa_identificado_planalto` (0048) após `ConnectionResetError` transitório; recusa conhecida, fora do escopo de I1 (cascata Planalto é I3.6) |
| Planalto (negativo) | falha | o teste espera `404` no motivo e recebe `recusa_identificado_planalto`; a ausência não pode ser provada com a fonte recusando |
| TCU (negativo) | falha | `tcu_busca_incompleta_limite_de_varredura`: a varredura declara-se incompleta; sem prova de ausência |

Leitura: as quatro falhas são indisponibilidades tipadas pelo produto, não regressões de código, mas o arnês
(decisão 0045) só converte em xfail as categorias `ambiental_desafio` e `fonte_fora` com evidência. Não se
alargou o arnês para fazê-las passar: isso esconderia que a legislação está congelada desde a 1.3.0. As duas
fontes ficam fora do escopo do I1 e entram no manifesto de aceite como limitação declarada.

## Bench (conjunto-ouro de 44 casos, `docs/auditoria/comparativo-120/gold.jsonl`)

Produto: 1.3.0 instalada pelo instalador oficial (attestation verificada, snapshot `b6921f68…`), com consulta
ao vivo onde o produto consulta. Comando: `python scripts/comparativo_ouro.py gold.jsonl freoa_raw.jsonl`.
Saída: `bench-1.3.0/freoa_raw.jsonl`.

| Medida | 1.3.0 |
|---|---|
| Casos com saída idêntica à da 1.2.0 (status, identidade, situação ou top-5) | 41 de 44 |
| Casos não temáticos alterados | 0 |
| Item apresentado como se fosse outro | 0 (inalterado) |
| Temáticos com top-5 alterado | 3 (D8, E4, E5), pela busca ao vivo do TJDFT |
| Itens novos no top-5, juiz cego (Haiku, só consulta e ementa) | E4: sim; D8: parcial; E5: parcial |
| Tempo por consulta | p50 2,2 s; p95 14,8 s; máximo 31,4 s |

Leitura: a 1.3.0 preserva integralmente o resultado não temático da 1.2.0 e a confirmação indevida zero. Nos
três temáticos alterados, entrou um item estritamente pertinente (E4) e dois laterais; saiu um acórdão do
TJDFT em cada caso, o que confirma a dependência de ordem já registrada no README do comparativo. O máximo de
31 s ultrapassa o piso de 20 s do D4 para consulta federada e fica registrado para a Porta A.

Limites: o conjunto é o mesmo da 1.2.0 (sobreajuste declarado) e mede o acervo existente, não a pesquisa ampla
(plano, seção 1). Não autoriza desligar nada. O lado comparativo não foi refeito nesta rodada.
