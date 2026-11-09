# IL.3-c: diagnóstico no conjunto de desenvolvimento (09/11/2026) e correções

Supervisor (Opus). Normativos: matriz IL.1 (congelada), 0077, 0080, 0081, reduções do IL.3-a; D6 (só desenvolvimento). Produto `main` `65b98b6`; home de desenvolvimento `C:\dev\fv-home-dev` (ativação registrada; ver `il3b-captura-desenvolvimento.md`).

## 1. Como o material chegou ao home

`fv camara inventariar` grava só nos diretórios de destino; o banco do home ficou vazio e a primeira execução do executor saiu toda `indisponivel` (defeito D1 abaixo). O material foi carregado pela fachada pública, pelo portão da 0080 (`obter_dispositivo`, vigente e `publicacao_original`, art. 1º de cada lei obtida). Uma primeira tentativa rodou sem `PYTHONPATH` (erro operacional do supervisor), o parser isolado não importou o pacote e o produto bloqueou persistentemente 10 páginas como barreira de perfil (defeito D2); os recursos foram reabertos por revisão registrada (`fv camara reabrir`, motivo declarado), mantido o bloqueio legítimo da busca do CTN. Resultado: 3 obras no banco (Lei 6.404/1976, Lei 10.406/2002, Lei 13.874/2019), 26 capturas; CPC e LGPD falharam com `ciclo_descoberta` (D3).

## 2. Execução do executor (modo local, qualificante quanto ao congelamento; NÃO é apuração da reserva)

Relatório `il3c-apura-dev-1.json` (SHA-256 `8f2ae09e…e932`), rede bloqueada, zero tentativas de rede.

| Cap. | Denominador | Acertos | Confirmações indevidas | Mutantes rejeitados | p95 (s) |
|---|---|---|---|---|---|
| (a) | 8 | 0 | 6 | 18/18 | 0,51 |
| (b) | 11 | 0 | 12 | 34/34 | 0,73 |
| (c) | 10 | 0 | 0 | 25/25 | 2,90 |
| (d) | 9 | 0 | 0 | 18/18 | 0,005 |
| (e) | 10 | 0 | 6 | 22/22 | 0,68 |

**24 confirmações indevidas (eliminatório).** Diagnóstico por diferença textual normalizada (seção 7 da matriz) nos casos L-b-001, L-a-001, L-b-007 e L-e-001: a ÚNICA diferença é o rótulo do artigo — o gabarito traz “Art. 14. O preço…”, a resposta da rota Câmara traz “O preço…”. A rota Câmara entrega o texto do dispositivo sem o rótulo, ao contrário da convenção do gabarito (o dispositivo inteiro). Pela matriz, `status: encontrada` com texto diferente do gabarito é confirmação indevida (ii); não há normalização que dispense o rótulo.

## 3. Defeitos para correção (trilha IL.3-c, correções só a partir do desenvolvimento)

- **D0 — rótulo do dispositivo ausente no texto da rota Câmara** (causa das 24 indevidas): o texto entregue por `obter_dispositivo` (e caminhos derivados) deve seguir a mesma convenção das demais fontes quanto ao rótulo, por classe (artigo, artigo com letra, parágrafo, inciso etc.), sem alterar o texto do confronto além disso.
- **D1 — inventário não alimenta o home**: `fv camara inventariar` deve persistir as capturas no banco do home com integridade e vínculos (0080 §8.4), ou haver importação verificada destino → home; sem isso o modo local e a captura da reserva pelo guardião não funcionam.
- **D2 — falha local do parser isolado classificada como barreira remota de perfil**: falha de importação, processo, tempo ou memória do parser isolado é falha local (terminal da chamada, sem bloqueio persistente de recurso), distinta de conteúdo não processável.
- **D3 — `ciclo_descoberta` em Lei 13.105/2015 e Lei 13.709/2018** no caminho da fachada, embora o instrumento as tenha obtido: diagnosticar e corrigir por classe, sem relaxar o vínculo de descoberta.
- **D4 — `unknown` na Lei 10.406/2002** (vigente e original) e na publicação original da Lei 13.874/2019: diagnosticar (identidade, epígrafe, recorte) e corrigir por classe ou registrar limite.
- **D5 — CTN**: faixa `1960-1969` não admitida (pendência da 0077; ampliação só por evidência).

Matriz por rota continua `nao_apurada`. Reapuração no desenvolvimento depois das correções; reserva só pelo guardião.
