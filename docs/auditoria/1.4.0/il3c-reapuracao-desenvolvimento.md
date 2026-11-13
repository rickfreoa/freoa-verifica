# IL.3-c: reapuração no conjunto de desenvolvimento (13/11/2026)

Supervisor (Opus). Normativos: matriz IL.1 (congelada), 0077, 0080 a 0083; D6 (só desenvolvimento, nenhuma captura da reserva). Código do ramo `feat/il3c-correcoes-dev` em `e771b05` (a correção posterior `edb11c1` só altera a mesclagem de snapshot).

## 1. Por que home novo

No home de desenvolvimento original os modelos Câmara são do parser `camara-legin-4`; o código novo (`camara-legin-5`) recusa-os com `camara_modelo_requer_reprocessamento`, e a 0082 não admite reprocessá-los sem a cadeia de descoberta. A primeira tentativa, sobre cópia desse home, saiu toda `indisponivel` por esse motivo (não é resultado da rota). A reapuração usou home novo, `C:\dev\fv-home-dev2`.

## 2. Ativação e captura (ao vivo, pelo instrumento)

- `fv camara ativar --capturar` e `--registrar` com a revisão do termo já conferida pelo auditor na IL.3-b: ambos 0; termo com o mesmo SHA-256 (`7da3ee35…a507c6`).
- `fv camara inventariar` do lote executável da IL.3-b (sete normas): obtidas 5 (Leis 6.404/1976, 10.406/2002, 13.105/2015, 13.709/2018, 13.874/2019); não obtidas 2: LC 118/2005 (`versao_ausente_ou_ambigua`) e Lei 5.172/1966 (`busca_sem_marcador_zero_validado`, faixa `1960-1969` não admitida pela 0077). As 12 normas restantes do desenvolvimento (MPs e decretos de anexos) continuam fora da rota (IL.3-b, seção 2).

## 3. Executor (modo local, rede bloqueada, zero tentativas de rede)

Relatório `apura-dev.json`, SHA-256 `8b82fec3a609cfabb3bf78e532bc4d1031d7c48e9ff34dd1b5a7e670d0ed17b5` (fora do repositório, `C:\dev\_il\reapura-dev\`).

| Cap. | Denominador | Acertos | Confirmações indevidas | Mutantes rejeitados | p95 (s) |
|---|---|---|---|---|---|
| (a) | 8 | 1 | 0 | 18/18 | 1,03 |
| (b) | 11 | 4 | 0 | 34/34 | 1,43 |
| (c) | 10 | 0 | 0 | 25/25 | 4,61 |
| (d) | 9 | 0 | 0 | 18/18 | 0,006 |
| (e) | 10 | 0 | 0 | 22/22 | 1,33 |

Item eliminatório: **zero confirmações indevidas** (eram 24 na apuração de 09/11, todas pelo rótulo ausente, D0). Nenhuma capacidade atinge o piso. Causas dominantes: `unknown` (abstenção) nas normas obtidas cujo dispositivo não se identifica sem ambiguidade (D4: CC e Lei 13.874) ou cuja redação em D não tem fundamento; `indisponivel` onde a rota não tem material; (d) sem anexos (C13); (b) acusa ainda truncamento em norma grande.

## 4. Consequência

Porta L reprovada no desenvolvimento. A reserva não é apurada (decisão 0084). Matriz por rota continua `nao_apurada`.
