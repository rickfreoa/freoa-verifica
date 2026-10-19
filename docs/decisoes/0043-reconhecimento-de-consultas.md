# 0043 — Reconhecimento de consultas por identificador

Data: 19/10/2026 · Versão: 1.2.0 · Origem: comparativo FREOA × JusRatio sobre conjunto-ouro independente

## Contexto

Na primeira medição da 1.2.0, decisões presentes no acervo não foram achadas pelo número, e
números inexistentes trouxeram outros processos. Eram defeitos de reconhecimento, não lacunas de dados:

- "REsp 2.257.277/PR" falhava porque a UF citada excluía registros sem UF (espelhos do STJ não a trazem);
- "Súmula 265 do STF" falhava porque a classe gravada ("Súmula", "Súmula Vinculante") era comparada com a
  da chave ("Sumula", "SumulaVinculante") com acento e espaço;
- número CNJ isolado caía na busca textual e devolvia processos alheios como resultado;
- "Resolução CVM 44/2021 art. 2º", consulta isolada sem vírgula, ficava `provavel`.

## Decisão

1. Classe comparada sem acento, caixa nem espaços. UF divergente exclui; UF ausente no registro não
   exclui e sai em `evidencia.uf_citada_nao_conferida`.
2. Número CNJ isolado tem caminho próprio (`modo_busca: numero_cnj`): dígito verificador inválido é
   `formato_invalido`; com conector de busca oficial pelo número (TJDFT, segmento 8.07), a fonte é
   consultada e só registros do mesmo processo entram; sem registro na fonte, `nao_encontrado_na_fonte`
   com escopo; sem fonte consultável, `nao_confirmado_no_acervo`. Nunca outro processo.
3. Na verificação de citação avulsa, "<norma> art. N" seguido só de dispositivo recebe a vírgula que a
   extração exige em prosa. Texto corrido e qualquer complemento ("do contrato") seguem as decisões 0016/0018.
