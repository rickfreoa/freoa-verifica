# Recibo final

Data: 18/10/2026. Contrato C4 do plano 1.0.3 (B3, F07).

O recibo (`run`) era gravado por `verify.verificar` antes de a fachada rebaixar o resultado, e `verificar_citacao` não aplicava o bloqueio de confiança de `verificar_texto`. O recibo podia dizer `verified` enquanto a resposta dizia outra coisa.

`verify.verificar(..., persistir=False)` devolve sem gravar (a fachada sempre assim chama). `Verifica._finalizar` aplica, nesta ordem: negativa (C1), ponto de extensão da situação da obra (C2, `aplicar_situacao`), confiança de extração, exigência de `capture_id` e autenticação da evidência. Só então grava o recibo com `verify.persistir_resultado`. Respostas que não passam por verificação (fonte indisponível antes da verificação) passam pela finalização sem recibo.

Confiança de extração (decisão 0016): citação `provavel`, ou com `preferir_outro_referente`, nunca produz conclusão definitiva de pertença em `verificar_citacao` nem em `verificar_texto`. Identidade e temporal ficam `unknown` e o texto `not_assessed`, todos com `ASSOCIACAO_REQUER_CONFERENCIA`; o confronto original vai em `conferencia`. "Lei 6.404/1976: art. 117 do contrato" nunca é `verified`.

Invariante testada: status e `reason_code` de identidade, texto e temporal lidos por `run_id` coincidem com os devolvidos. O teste compara conclusões, não o JSON inteiro, porque o conteúdo gravado (citação, trecho, evidência) pode ser restringido por política de registro. O eco `proposicao` não é gravado.
