# IL.3-b: ativação ao vivo e captura do conjunto de desenvolvimento (09/11/2026)

Supervisor (Opus). Normativos: decisões 0077, 0080 e 0081; D6. Produto em `main` `65b98b6` (1.4.0a2 + IL.3-a/IL.3-b). Home de desenvolvimento `C:\dev\fv-home-dev`, exclusivo; nenhuma captura da reserva.

## 1. Ativação (0080 §2)

| Etapa | Resultado |
|---|---|
| 1ª tentativa de captura (03:44 UTC) | `transporte_Timeout` no robots de `www2` → bloqueio transitório de 1 h; parada sem nova tentativa |
| 2ª tentativa (04:53 UTC) | robots de `www.camara.leg.br` (`80d159e6…ce4a`) e `www2.camara.leg.br` (`b725bf41…bee8f`) idênticos às capturas de 04–05/11; termo `7da3ee35…7c6` (54.834 bytes, 200, `text/html`, UA identificado) |
| Revisão do termo pelo auditor (Codex, somente leitura) | `REVISAO: CONFORME` — seis afirmações da síntese do §3.2 confirmadas com trecho literal; sem exigência fora do §7; registros: item 17 (alteração a qualquer momento), item 15, item 14 (fora do escopo) |
| Registro (05:20 UTC) | `camara_ativacao.json`, `registro_sha256` `4fdd2beb…b77e`; estado: ativação válida, sem bloqueios |

## 2. Inventário (0080 §8.1)

Inventário mestre de 19 normas extraídas de `tests/porta_l/desenvolvimento.jsonl` (SHA-256 `44f6a723…ed8`); correspondência exata confirmada pelo auditor. O instrumento só aceita `lei` e `lei_complementar`; o lote inteiro seria recusado. Plano revisado, aprovado pelo auditor: lote executável de 7 normas; 12 não suportadas registradas como não obtidas, sem contorno e sem uso de URLs dos gabaritos:

- MPs 2170-36/2001, 449/2008, 881/2019 — sem busca/perfil de texto (0077).
- Decretos 11330, 11332, 11335, 11336, 11342, 11346, 11349, 11350, 11351 de 2023 — sem busca/perfil; anexos PDF sem extração validada (C13).

## 3. Captura

| Norma | Sessão | Resultado | Motivo |
|---|---|---|---|
| Lei 6.404/1976 | 1 | obtida (atualizado e original) | — |
| Lei 10.406/2002 | 1 | obtida (atualizado e original) | — |
| Lei 5.172/1966 | 1 | não obtida | `busca_sem_marcador_zero_validado` (resposta de busca fora do perfil; links da faixa `1960-1969`, não admitida pela 0077); recurso bloqueado persistentemente e host `www` bloqueado pelo restante da sessão (0080 §6) |
| Leis 13.105/2015, 13.709/2018, 13.874/2019 e LC 118/2005 | 1 | não tentadas | host bloqueado pelo restante da sessão 1, sem requisição |
| Lei 13.105/2015 | 2 | obtida (atualizado, original e página da norma) | — |
| Lei 13.709/2018 | 2 | obtida (atualizado, original e página da norma) | — |
| Lei 13.874/2019 | 2 | obtida (atualizado e original) | — |
| LC 118/2005 | 2 | não obtida | `versao_ausente_ou_ambigua` |

A sessão 2 abrangeu só as quatro normas não tentadas; o recurso bloqueado da sessão 1 não foi repetido (o bloqueio de host por perfil é de sessão; o do recurso, persistente — tabela do §6). Nenhuma barreira 401/403/429/desafio. Inventários duráveis por norma em `C:\dev\fv-captura-dev` e `C:\dev\fv-captura-dev-s2`.

## 4. Efeito sobre o desenvolvimento

Obtidas 5 de 19 normas. Ficam sem material de rota viva: CTN (inclusive o art. 185, de cobertura obrigatória), LC 118, as três MPs e os nove decretos de anexos. Os casos correspondentes saem `indisponivel` na apuração do desenvolvimento, que não poderá aprovar (a), (c) nem (d); (e) segue não apurável (redução de escopo do IL.3-a).

## 5. Pendências abertas por esta captura

1. Faixas de período além das observadas (`1960-1969` e anteriores) na gramática da 0077, por evidência e ampliação explícita.
2. Busca/perfil de texto de MPs e decretos; extração validada de anexos PDF (C13).
3. Diagnóstico do `versao_ausente_ou_ambigua` da LC 118/2005.
