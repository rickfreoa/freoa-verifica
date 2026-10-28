# S0 — rodada 1 das sondas (instrumento auditado em `c24a1a4`)

Execução: supervisor (Opus), notebook Windows do titular, IP brasileiro, 28/10/2026 03:36–03:37 UTC.
Instrumento: `scripts/capturar_fixture.py --fonte-sonda ... --sonda`, HEAD `c24a1a4` (parecer Codex r3 SEM
BLOQUEADOR), UA `freoa-verifica/1.3.0 (+https://github.com/rickfreoa/freoa-verifica)`, um pedido por comando,
sem repetição nem redirecionamento. Orquestração: `s0-rodada1/s0_runner.py`, que só chama o instrumento com
os comandos dos blocos liberados de `docs/S0-SONDAS.md` e aplica a tabela de parada por host (robots primeiro,
interpretado localmente com o token `freoa-verifica`; qualquer indisponibilidade encerra o host; blocos de host
B não rodam). Registros e corpos em `s0-rodada1/<fonte>/`; consolidação em `s0-rodada1/relatorio-s0.json`.

## Resultado por host

| Host | robots.txt | Decisão | Demais comandos |
|---|---|---|---|
| jurisprudencia.tst.jus.br | 200 text/plain: `User-agent: *` / `Disallow: /` | caminho vedado | `/config.json` não sondado (Disallow) |
| jurisprudencia-backend.tst.jus.br | 404 | parada (regra conservadora: 4xx = indeterminado) | 2 não sondados |
| jurisprudencia.stf.jus.br | 200, recusado pelo instrumento (`transporte_RespostaInvalida`, `resposta_inesperada`) | parada | 1 não sondado |
| pangeabnp.pdpj.jus.br | 200, `transporte_RespostaInvalida` | parada | — |
| bnp.pdpj.jus.br | 200, `transporte_RespostaInvalida` | parada | — |
| comunica.pje.jus.br (DJEN, página) | 200, `transporte_RespostaInvalida` | parada | `/consulta` não sondada |
| comunicaapi.pje.jus.br (DJEN, API) | 200 text/plain: `User-agent: *` / `Disallow:` (vazio) | permitido | sem rota de resultado no catálogo (pendência S0b) |
| jurisprudencia.cjf.jus.br | 200 text/plain: `Allow: /`, `Disallow: /api/`, sitemap | permitido, salvo `/api/` | robots do TRF1 no mesmo host não repetido |
| arquivo.trf1.jus.br | 404 | parada | — |
| jurisprudencia.trf2.jus.br | `transporte_BlockedHost` (redirecionamento barrado) | parada | — |
| www10.trf2.jus.br | 503 (`fonte_fora`) | parada; barreira | 1 não sondado |
| web.trf3.jus.br | timeout (`fonte_fora`) | parada; barreira | 2 não sondados |
| esaj.tjac.jus.br | 200, `transporte_RespostaInvalida` | parada | 2 não sondados |
| www5.tjmg.jus.br | 404 | parada | 2 não sondados |
| portal.tjpr.jus.br | 200 text/plain: só `Disallow: /tjpr-assinador/` | permitido | `/jurisprudencia/`: 200, HTML, 80.587 bytes |
| esaj.tjsp.jus.br | não sondado | barreira anterior (27/10/2026, `ambiental_desafio:desafio_captcha`, mesmo instrumento) | sem nova tentativa |
| jurisdf.tjdft.jus.br | 200, `transporte_RespostaInvalida` | parada | volume não sondado |

Hosts de nível B (CJF www, TJAL, TJAM, TJMS, TJRJ, TJRS) não foram sondados: bloqueados até confirmação.

## Achados

1. **TST veda rastreamento do portal** (`Disallow: /` para todos). O conector TST do I2.2 não pode raspar o
   portal de jurisprudência; restam o backend (robots 404) e fontes alternativas (dados abertos, BNP), a decidir.
2. **CJF veda `/api/`.** A pesquisa unificada do CJF só pode ser usada pelas páginas HTML permitidas; o
   teste de equivalência do I3.8 tem de considerar isso.
3. **DJEN API alcançável do Brasil, com robots aberto.** Confirma a premissa da decisão 0069. Falta rota
   documentada de consulta (S0b).
4. **`transporte_RespostaInvalida` com status 200 em seis robots** (STF, BNP ×2, DJEN página, TJAC, TJDFT).
   O instrumento exige `text/plain` no robots e recusou o corpo; o registro não traz o Content-Type recebido,
   então não se sabe se é HTML de aplicação (SPA), `application/octet-stream` ou `text/plain` com parâmetro
   inesperado. Defeito menor do instrumento: a evidência da recusa deve registrar o Content-Type.
5. **Robots 404 em três hosts** (TST backend, TRF1 arquivo, TJMG). Pela regra conservadora fixada pelo
   supervisor (4xx = permissão indeterminada), pararam. O RFC 9309 trata 4xx como ausência de restrições.
6. **Volume não medido.** Nenhuma rota de resultado com contagem foi alcançada: as rotas GET documentadas são
   páginas de pesquisa; os resultados exigem POST ou sessão (S0b) e o TJSP está sob CAPTCHA. A estimativa de
   volume da seção 4 do plano continua dependente das estatísticas oficiais do CNJ, rotuladas como estimativa.

## Consequências e propostas (a decidir)

- **Regra de robots.** Proposta do supervisor: alinhar ao RFC 9309 — 404/410 = sem restrições; 200 sem regras
  interpretáveis (inclusive HTML) = sem restrições, registrado o Content-Type; 401, 403, 429, desafio, 5xx e
  timeout = barreira. Exige mudança do instrumento (aceitar e registrar o corpo do robots em qualquer MIME) e
  nova auditoria (S0b).
- **S0b**: modo POST/sessão no instrumento para resultados (TST textual, e-SAJ, TJRJ), rota de consulta do DJEN
  e reabertura dos hosts parados por robots indeterminado, sob a regra que o titular fixar.
- **Recorte de I3.2**: sem medição de volume, a decisão pela camada (b) federada para o lote 1 (seção 4 do plano)
  ganha peso.
