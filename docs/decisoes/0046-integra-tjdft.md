# 0046 — Íntegra dos acórdãos do TJDFT

Data: 19/10/2026 · Versão: 1.3.0 · Origem: plano 1.3.0, F1; evidência em `docs/auditoria/1.3.0/sondas/RELATORIO.md` (grupo 1)

## Problema

A decisão 0041 tratava a íntegra como ausente dos acórdãos. A sonda mostrou que a API pública devolve o campo `inteiroTeor` com texto em 5 de 5 registros quando a busca envia `retornaInteiroTeor: true`, e em 1 de 5 sem ele. `inteiroTeor: true` (pesquisa) não teve efeito observável; `termosAcessorios` com data foi recusado (HTTP 500 e 400).

## Regras

1. `search` e a obtenção de documento (que refaz a busca pelo processo) enviam `retornaInteiroTeor: true` por `build_search_payload(..., extras=...)`. Não se envia `inteiroTeor` nem `termosAcessorios` de data; o filtro de data segue local (0053).
2. O critério de aceitação da íntegra vale para acórdãos e decisões individuais: texto de ao menos 1000 caracteres, **número do processo do registro** presente, **parte dispositiva** e **fecho** no fim do texto. Sem esses requisitos a parte `inteiro_teor` fica indisponível; ementa nunca ocupa o lugar da íntegra.
3. Fecho. Decisão individual: fórmula de cumprimento ou assinatura (`publique-se`, `intimem-se`, `assinado eletronicamente`, …). Acórdão: além dessas, a proclamação do resultado na seção `DECISÃO` que encerra o documento (`UNÂNIME`, `MAIORIA`, `vencido`). As capturas reais encerram o acórdão assim, sem fórmula de cumprimento; sem essa extensão nenhum acórdão real seria aceito. Rever se a fonte mudar o formato.
4. Falhas ficam em `metadata["integra_motivo"]` do candidato, gravado nos atributos da decisão, e `obter_decisao(parte="inteiro_teor")` devolve `parte_indisponivel` com `motivo: PARTE_NAO_CAPTURADA` (contrato estável) e `motivo_integra`:
   `integra_placeholder` (mensagem de indisponibilidade), `integra_curta` (menos de 1000 caracteres), `integra_processo_divergente` (texto sem o número do registro), `integra_sem_dispositivo`, `integra_sem_fecho`. Registro sem texto algum não tem `motivo_integra`.
5. Registro repetido na resposta (mesmo `uuid`): um só candidato; o parse continua ambíguo (`tjdft_registro_ausente_ou_ambiguo`) e nada é gravado como íntegra.

## Evidência

Captura `tjdft_busca_integra` (sha256 `47dbaf4a…5b15`, igual à da sonda (b)): 4 acórdãos aceitos; a decisão monocrática do conjunto tem texto íntegro, mas sem o próprio número do processo no corpo, e é recusada com `integra_processo_divergente`. Variantes sintéticas (fragmento, placeholder, processo divergente, curta, sem dispositivo) são derivadas em memória nos testes a partir dessa captura.

## Limites

O tamanho dos textos (16–47 mil caracteres por registro) aumenta o JSON capturado (cerca de 2,3 vezes na sonda). O critério é textual: não prova que o texto é o de todo o julgado, só que é o do próprio processo, com dispositivo e fecho.
