# 0089 — Ensaios reais da sessão assistida (19 e 20/11/2026)

Registro do supervisor. Navegador: Brave 1.100 (Chromium 158), instalado na conta do titular, sem política de
máquina; notebook do titular (Windows, sem privilégio de administrador). Execução fora do sandbox do Codex, que não
lança navegador (`SetFileSecurityW`, WinError 5). Comando: `pytest -m navegador_assistido` sobre
`tests/test_assistida_0089_navegador.py` e `tests/test_assistida_0089_navegador_cenarios.py`, harness HTTPS local
com AC e loopback exclusivos do harness. Logs integrais fora do repositório (`C:\dev\tmp\v5\impl-b\nav-*.log`,
`item9.log`), por conterem caminhos locais.

| Ensaio | Commit | Resultado | Fato observado e consequência |
|---|---|---|---|
| 1º | `a027443` | 1 de 17 | `Secure Preferences` gravado 10–30 s após abrir; inventário lido cedo demais (defeito 46). Correção `f80630b` (espera até 60 s). Extensões de componente sem `manifest.json` em disco; manifesto só nas preferências (defeito 47, leitura de execução). |
| 2º | `ee9e338` | 31 de 55 | Positivos sem captura: manutenção no caminho de cada mensagem atrasava `Network.streamResourceContent` (defeito 48). Correção `a0a7a3e`. |
| 3º | `a0a7a3e` | 23 de 55 | Negativos passaram a exigir o motivo da recusa e deixaram de passar no vazio (defeito 50). Rastreamento: no documento, o Chromium emite `dataReceived` sem `data` antes de responder ao streaming, com esses bytes no `bufferedData` (defeito 49, leitura de execução). Correção `cbce9b6`. |
| 4º | `cbce9b6` | 39 de 55 | Todos os positivos de documento passam. `fetch`/XHR: último `dataReceived` sem `data` com `dataLength` 0. Correção `e5b1012`. |
| 5º | `e5b1012` | 46 de 55, 5 pulados | Item 9 intermitente; cache comparado por URL; códigos de 304/prazo. Disco do notebook encheu (24 GB de perfis em `.tmp/pytest-*`, pendência 35). Correção `8b8eb3e` (testes). |
| 6º | `8b8eb3e` | regressão | `WinError 32`: limpeza do perfil com processos filhos do navegador vivos (defeito 51, do produto). Item 9: só o parâmetro `q` do `Accept-Language` difere, aleatorizado pelo Brave entre sessões sem CDP. Correção `deacd20`. |
| 7º | `deacd20` | 48 de 56, 5 pulados | Limpeza resolvida. 3 cenários (304, sem cabeçalhos, parcial) não produziam a condição da §3 item 1; item 9 em 3 de 4 (controles iguais por acaso). Correção `4493d5f` (testes). |
| 8º | `4493d5f` | 51 de 57, 5 pulados | Item 9 falhou no ensaio completo por exceção na coleta dos controles. Parecer Terra r1: BLOQUEADOR (charset arbitrário persistido) e ALTO (q normalizado em qualquer cabeçalho). Correção `4116e53`. |
| 9º | `4116e53` | **52 de 57, 5 pulados, 0 falhas**; item 9 em 4 de 4 | Terra r2: SEM BLOQUEADOR. |

Pulados no 9º ensaio, com motivo: instalação manual de extensão desempacotada e recarga forçada (exigem pessoa na
janela; `FV_0089_GESTO_HUMANO=1`); prerender (desativado no Brave); Early Hints (exige origem HTTP/2 e o pacote `h2`,
que não é dependência do projeto); §3 item 7, segunda conta (não existe e o titular não é administrador).

Não substitui a auditoria independente nem a sessão manual do titular (§3 item 17).
