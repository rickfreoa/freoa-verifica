# 0047 — Comunica CNJ: não sondado nesta versão

Data: 20/10/2026. Origem: plano 1.3.0 (F2).

O plano previa apenas a sonda da API de comunicações processuais do CNJ, com o conector adiado para 1.4.0. A sonda não foi feita: o instrumento de captura só alcança hosts de conectores existentes (allowlist por conector), e criar um conector apenas para sondar anteciparia a decisão que a sonda deveria informar.

Ficam para a 1.4.0, nesta ordem: (1) conector mínimo de captura com allowlist `comunicaapi.pje.jus.br`, UA identificado, sem `Origin`/`Referer` de terceiros; (2) sonda do recorte temporal e da natureza do campo `texto` (íntegra, ementa ou dispositivo); (3) decisão sobre `texto_publicado` como tipo documental próprio, com nível de prova distinto de `inteiro_teor`, migração de esquema e compatibilidade de snapshot. O `hash` da API não substitui o SHA-256 local.
