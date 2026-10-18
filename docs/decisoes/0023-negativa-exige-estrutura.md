# Negativa de dispositivo exige estrutura

Data: 18/10/2026. Contrato C1 do plano 1.0.3.

`not_found/DISPOSITIVO_INEXISTENTE` afirma que a fonte oficial não tem o dispositivo. Ausência no acervo local, documento cortado ou documento sem dispositivos estruturados não sustentam essa afirmação.

Uma função única, `verify.pode_negar(rw, caminho)`, decide. Devolve `None` (a negativa é autorizada) ou o motivo que a impede:

- sem obra capturada: `COBERTURA` (`unavailable`, nunca `inexistente`);
- issue de truncamento ou extração incompleta no escopo do caminho: `ESTRUTURA_INCOMPLETA`;
- documento em quarentena: `DOCUMENTO_QUARENTENADO`;
- nenhum dispositivo estruturado no mesmo escopo (anexo, ADCT ou corpo), como o PDF da CVM com `provisions=[]`: `DOCUMENTO_SEM_ESTRUTURA`.

Os motivos de documento resultam em `unknown`. Consumidores: `verify.verificar` (inclusive o ramo de quarentena e o ramo de dispositivo ausente), `resolver_citacao`, `obter_dispositivo`, `historico_dispositivo`, `verificar_citacao` (reaplicada em `_finalizar`) e, por ela, `verificar_texto`. Obra ausente do acervo com a rede desligada (`FV_OFFLINE`, `FV_READ_ONLY`) é `COBERTURA`; negativa online do conector continua valendo.

"caput" usa a resolução canônica do verificador (`_find_provision`) em todos os consumidores.

Controles positivos obrigatórios: dispositivo existente com trecho correto continua `verified`; dispositivo ausente de obra íntegra e capturada continua `not_found/DISPOSITIVO_INEXISTENTE`.
