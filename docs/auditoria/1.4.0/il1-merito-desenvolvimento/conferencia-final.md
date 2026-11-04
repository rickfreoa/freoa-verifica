CONFERE

- **117/117 mutantes preservados.** Recalculei a correspondência contra a r2 autenticada pelo parecer, excluindo somente os sete mutantes dos quatro casos reprovados. Mesmos IDs, ordem, chamadas, parâmetros, expectativas e alterações. Os 117 hashes coincidem também com o TSV e a tabela do relatório.
- **Campos D5 coerentes:** 52 destinos correspondem às chamadas e aos caminhos anteriormente aprovados; 18 referências temporais correspondem aos casos — 16 `anterior_a_obra` e duas redações alternativas, de L-c-002 e L-c-003.
- **Cobertura:** diff restrito a `lsa_289` (`evento` e `esperado`) e `anexo` (“dez” → “nove”). Nenhuma outra mudança.
- **Desenvolvimento:** mesmos 52 registros aprovados após as quatro exclusões. SHA-256 atual: `2fb75d158f197a474e753796e2d621ba67f5200413ef0121daeb5ae6873517b1`.
- **Validador:** reproduzidos **52 casos, 0 falhas, retorno 0**, com as três opções solicitadas; saída integralmente igual a `saida_validador.txt`. A execução direta encontrou `PermissionError` no `fontTools` opcional; a reprodução em memória desabilitou esse componente, como no passe anterior.

**Errata documental, sem efeito sobre a correspondência:** em `relatorio.md:511`, o hash histórico está incompleto, com 63 caracteres. O correto é `571085c272dde51f2d323ed839cbb480dbeb98d0681d16e2e093aede83b81ca9`.

Nenhum arquivo alterado; reserva não acessada.