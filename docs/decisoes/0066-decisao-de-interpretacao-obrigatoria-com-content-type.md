# 0066 — Decisão de interpretação obrigatória, com ou sem Content-Type

Data: 21/10/2026 · Versão: 1.3.0 · Origem: auditoria final, rodada 16 (F-26); revê a regra 4 da 0065

## Problema

`derivados.compativel` só procurava captura sem decisão de interpretação quando o recibo também não tinha
Content-Type. Pela API `indexar_obra`, um corpo cp1252 declarado `text/html; charset=utf-8`, ou um corpo com
`charset*=x`, gravava recibo com Content-Type e `codificacao`/`origem_da_codificacao` nulos, e o modelo do parser. A
releitura falhava, mas os derivados seguiam certificados: a consulta entregava o texto e `verificar_citacao` retornava
`identity=verified`, `text=verified`.

## Regra

1. **Decisão registrada.** Para toda captura com modelo de fonte reprocessável (Planalto, CVM normas, BCB), há decisão
   de interpretação no recibo ou, para recibo legado sem ela, no derivado: `origem` não nula e `codificacao` não nula,
   salvo binário (`binario`, ou `legado_sem_cabecalho` de PDF/DOCX pela assinatura), que não tem codec. A presença de
   Content-Type não dispensa a decisão (`repo.decisao_registrada`; o mesmo predicado, em SQL, em
   `derivados._SEM_DECISAO`).
2. **Compatibilidade.** Captura sem decisão torna os derivados incompatíveis (`ACERVO_DESATUALIZADO`): as operações
   dependentes (`obter_dispositivo`, `verificar_citacao` etc.) não entregam texto como atual nem retornam `verified`.
   A reconstrução relata a falha (`interpretacao_indisponivel`) e não certifica o acervo.
3. **Gravação.** Nenhum caminho grava modelo sem decisão. `populate_from_parsed` (por `indexar_obra`) recusa antes de
   gravar recibo, obra ou modelo, com `Unavailable("interpretacao_indisponivel", categoria="resposta_inesperada")` e
   evidência (sha256, url). `persist_parsed_document` recusa da mesma forma se nem o recibo nem o derivado têm
   decisão. A decisão da releitura legada é gravada no derivado no mesmo `UPDATE`/transação do modelo, não depois.
4. **Releitura.** `_resposta_da_captura` trata recibo com Content-Type e decisão nula como
   `interpretacao_indisponivel`, sem reinterpretar em silêncio.

## Consequências

- Os negativos do auditor, pela API pública, viram falha declarada sem efeito no banco; um home que já os contenha
  (candidata anterior) fica incompatível até ser reconstruído a partir de capturas interpretáveis.
- Teste de banco (`tests/test_fix20_f26_decisao.py`): após indexação, reprocessamento e reconstrução, `_SEM_DECISAO`
  não retorna linhas.
- `obter_evidencia` (exibição do recibo por `capture_id`) não é operação dependente e continua exibindo os bytes como
  evidência; não declara o texto atual.
