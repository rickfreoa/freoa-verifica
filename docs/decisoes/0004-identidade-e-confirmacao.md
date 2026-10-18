# Identidade declarada e estados de confirmação sob demanda

Implementação da especificação R4. Captura e URL não suprem o confronto entre
identidade solicitada e identidade declarada. Tipo, número, ano e data explícita
são confrontados com epígrafe ou campos oficiais capturados; divergência resulta
em `identity=not_found`, `IDENTIDADE_DIVERGENTE`, antes de indexar. O reparo
`reparar_identidades` retira a chave pública de associações legadas divergentes
por namespace `invalidated:`, preservando recibos, hashes e referências. Modelos
derivados podem ser reprocessados dos mesmos bytes, sem inventar novas capturas.

Para decisões, `encontrada` exige julgamento identificado e captura; confirmação
de processo isolada é `processo_confirmado`. Ausência no recorte pesquisado é
`nao_confirmado_no_acervo`, com cobertura explicitada. `inexistente` exige negativa
oficial conclusiva; falha de rede, esquema ou desafio é `indisponivel`. Número
inválido é `formato_invalido`. Metadados DataJud não confirmam julgamento.

A segurança de comparação permanece: nota editorial não integra dispositivo;
continuação incerta bloqueia confronto. Cabeçalho nominal com conectivos não é
continuação normativa. Planalto tem prazo de 180 s, taxa mínima de 256 bytes/s,
limite de 30 MiB e três tentativas apenas para falhas transitórias, com espera
exponencial; desafios e controles de acesso não são retentados nem contornados.

Este registro implementa a especificação recebida; não constitui parecer
independente nem avanço de marco.

O circuito de transporte não conta HTTP 404/410 como indisponibilidade do servidor;
essas negativas não bloqueiam a descoberta de URLs posteriores. Erros 5xx e
controles de acesso continuam sujeitos ao circuito. A retomada examina os
checkpoints dos alteradores mesmo quando o contexto legado estava concluído e
mesmo quando a remissão já não aparece na edição atual; uma falha de filho não
interrompe a tentativa dos demais nem se converte em conclusão de contexto.
