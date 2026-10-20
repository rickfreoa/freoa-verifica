# 0045 — Categorias de indisponibilidade

Data: 19/10/2026 · Versão: 1.3.0 · Origem: parecer sobre `challenge.py` no plano 1.3.0

## Contexto

`map_transport_error` transformava todo 403 em `desafio_http_403` e todo corpo vazio em
`desafio_corpo_vazio`. Recusa identificada e resposta inesperada apareciam como desafio ambiental,
e o teste live não distinguia ambiente (WAF, fonte fora) de regressão do código.

## Decisão

1. `Unavailable` ganha `categoria` e `evidencia` (`status`, `marcador`, `cabecalho`, `sha256`, `url`,
   só o que se conhece). `reason` segue sendo o código estável.
2. Categorias, sempre por prova positiva:
   - `ambiental_desafio`: assinatura da tabela em `connectors/challenge.py` (`ASSINATURAS_VERSAO`) no corpo
     ou no cabeçalho (`x-amzn-waf-action`, `cf-mitigated`);
   - `fonte_fora`: 5xx, timeout, leitura lenta, falha de conexão/TLS registrada pelo transporte;
   - `recusa_identificado`: 401/403 sem assinatura;
   - `resposta_inesperada`: corpo vazio, 202 sem prova, JSON/estrutura que o parser não reconhece
     (`resposta_invalida`, `resposta_inesperada`);
   - `regressao`: reservada a exceção não prevista do próprio código convertida em indisponibilidade.
   Sem prova, `categoria` é `None` (ex.: `sem_url`, `orcamento`, 404).
3. Códigos de `reason`: `http_403` e `http_401` (antes `desafio_http_403`) e `corpo_vazio` (antes
   `desafio_corpo_vazio`). Desafio com assinatura continua `desafio_<tipo>`. `desafio_aws_waf` por 202 sem
   corpo nem cabeçalho de borda mantém o código, com categoria `resposta_inesperada`.
4. Saída JSON (aditiva): `categoria` e `evidencia_indisponibilidade` onde `unavailable`/`indisponivel` vem de
   `Unavailable` com categoria.
5. Testes live: na fase `call`, `Unavailable` com categoria `ambiental_desafio` ou `fonte_fora` **e**
   evidência não vazia vira `xfail("<categoria>:<motivo>")`. Qualquer outra falha segue falha.
   `tests/live/conftest.py::exigir_disponivel` levanta a exceção tipada a partir de resultado.

## Limites

O transporte descarta o corpo e retém só 4 cabeçalhos em resposta não 200; por isso 403 visto como
`HTTPStatusError` não é inspecionado por assinatura e fica `recusa_identificado`. Assinaturas só valem
quando o corpo chega (200 e `detect_challenge`).

## Emenda FIX1 (auditoria do bloco 1)

- `fonte_fora` vale só para falha de conexão, TLS, timeout e 5xx com prova. Erro de protocolo com resposta
  recebida (MIME proibido, `Content-Type`/`Content-Encoding`/`Transfer-Encoding` inválidos, framing,
  `Content-Length` divergente, tamanho acima do limite) usa o tipo `transport.RespostaInvalida` (`TooLarge` é
  subclasse) e vira `resposta_inesperada`, que o hook live mantém como falha.
- `detect_challenge` não infere desafio por 202 com corpo vazio. Só cabeçalho de borda ou assinatura de corpo.

## Emenda FIX9 (auditoria final, rodada 5: F-06, F-13)

- A classificação da falha de transporte é uma só: `transport._classificar(exc, estado)` decide categoria e
  repetibilidade, e nenhum outro ponto do transporte converte exceção em categoria. O `_EstadoChamada`
  (`resposta_iniciada`, `saltos`, `bytes_recebidos`, `ultimo_status`) nasce em `fetch` e é visto por todos os
  saltos, pela validação/resolução de cada salto, pelo controlador externo de prazo e pela leitura de desafio.
- Regra: qualquer status ou byte recebido em qualquer momento da chamada torna toda falha posterior (prazo,
  fechamento, DNS, validação de outro salto) `RespostaInvalida`/`resposta_inesperada`, não repetível, com `saltos`
  preservados. Sem status nem byte na chamada, a falha é `fonte_fora` e repetível. Uma repetição decidida pelo
  transporte é um novo percurso e zera o estado.
- Falha de resolução DNS é `TransportError` (`fonte_fora`), não `BlockedHost`; endereço inseguro continua política.
- `_desafio_na_resposta` distingue "sem marcador" de "impossível examinar": erro de leitura (framing, protocolo,
  soquete) propaga como `RespostaInvalida`, sem repetição.
