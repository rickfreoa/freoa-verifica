# Identidade de normas numeradas sem ano

Data: 18/10/2026. Adendo à decisão 0016 (confiança de extração).

"Resolução CMN 4.966", "Resolução BCB 428", "Resolução CVM 80" e "Instrução CVM 358" pertencem a séries de numeração única por autoridade e espécie: o número identifica o ato. Sem ano, a extração as marcava `provavel` e `verificar_citacao` e `verificar_texto` devolviam `ASSOCIACAO_REQUER_CONFERENCIA` mesmo com a obra inequívoca no acervo.

**Regra.** O extrator continua puro: citação sem ano nasce com `sem_ano`; se essa for a única razão de ser provável, recebe também `so_sem_ano`. Na finalização (`Verifica._finalizar`), uma citação com `so_sem_ano` de (cmn, resolução), (bcb, resolução BCB), (cvm, resolução) ou (cvm, instrução) é tratada como exata para a identidade quando o acervo contém exatamente uma obra daquela autoridade, espécie e número: o ano da obra é preenchido, a confiança vira `exata` e a citação recebe `numero_unico_no_acervo`. Com zero obras (a existência não é demonstrada) ou mais de uma (anos diferentes, ambiguidade real) a citação segue `provavel` e pede conferência. Os demais motivos de confiança provável (prosa, delimitação pareada, alias ambíguo, campo não jurídico) não são afetados: `so_sem_ano` só existe quando o ano ausente é a única razão.

**Lei sem ano continua provável.** Leis, decretos e demais espécies têm numeração por ano ("Lei 6.404" sem ano pode ser outra lei de outro ano); a unicidade no acervo não prova a identidade.

**Limite.** A regra depende do acervo local: o mesmo texto pode ser `exata` num home e `provavel` noutro. É a mesma contingência da resolução de obra, e o recibo grava a citação já promovida.

## Adendo (rodada 2 do auditor): premissa e condições

**Premissa declarada.** Um acervo parcial não prova, por contagem, que a numeração é global. A promoção a `exata` vale só porque a unicidade vem da série, não do acervo: Resolução CMN (numeração única desde 1964), Resolução BCB (desde 2020), Resolução CVM (nova série desde 2021) e Instrução CVM (série encerrada). Essas séries são as únicas em `_SERIES_UNICAS`; reinício de série ou ano cadastral errado invalidariam a premissa, e nesse caso a regra deve ser revista, não contornada.

**Condição adicional.** A obra única no acervo tem de ter sido capturada da fonte oficial da série (`bcb` para CMN e BCB; `cvm_normas` para CVM), com documento não quarentenado e identidade validada (obra com autoridade `invalidated:*` não conta). Sem isso a citação segue `provavel`.

**Transparência.** A resposta leva a flag `numero_unico_no_acervo` para o usuário conferir que a promoção decorreu da unicidade no acervo local, e o recibo grava a citação já promovida.
