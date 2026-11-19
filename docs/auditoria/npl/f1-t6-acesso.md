# Plano de testes NPL — Fase 1, T6 (acesso automatizado): recusa

Data: 19/11/2026, 09h10–09h20 UTC. Máquina: notebook do titular (Windows, IP brasileiro, rede direta). Ramo `sonda/npl` sobre `878dcf0`.

## Procedimento
1. Fontes-sonda `npl` (portaldalegislacao.presidencia.gov.br) e `npl_classico` (portaldalegislacao-classico.presidencia.gov.br) inseridas no catálogo com rotas exatas (llms.txt, sitemap.xml, saibamais.html e 42 atos obrigatórios). Origem dos hosts: página oficial lida (`/saibamais.html`, release da SAJ de 13/11/2026); caminhos conferidos por HEAD 200 no navegador embutido.
2. `scripts/capturar_fixture.py --fonte-sonda <id> --sonda --saida C:\dev\fv14-sondas\npl\f1-teste`, UA identificado (`freoa-verifica/1.4.0a5`), transporte comum, um pedido por URL.

## Resultado
| Chave | URL | Resultado |
|---|---|---|
| r1 | npl `/robots.txt` | `unavailable(transporte_TransportError)` |
| l1 | npl `/llms.txt` | idem |
| a1 | npl `/ccivil_03/leis/l6404consol.htm` | idem |
| c1 | npl_classico `/ccivil_03/leis/l6404consol.htm` | idem |

Diagnóstico (curl.exe/Schannel, mesmo host, fora do instrumento, um pedido cada): TLS concluído, `GET` enviado, conexão reiniciada pelo servidor (`Recv failure: Connection was reset`). O mesmo ocorre com UA de navegador e com o UA padrão do curl; www.lexml.gov.br responde 200 da mesma máquina. O navegador embutido (Chromium), na mesma máquina e IP, carrega os dois portais. Conclusão: filtro na camada de aplicação que recusa clientes não navegador, independentemente do UA; não é bloqueio de IP. Cookie `TS01…` observado em 19/11 indica F5 BIG-IP (inferência, não verificada).

Achado lateral (T7): documento inexistente no NPL responde 502, não 404.

## Consequências
- Gate da Fase 1 acionado: recusa em T6. Fases 1 (T1, T4, T8) e 2 suspensas; harness não encomendado.
- `npl` e `npl_classico` registrados em `FONTES_BARRADAS`/`HOSTS_RECUSADOS` (regra do catálogo: barreira, sem nova tentativa). `tests/test_sondas.py` atualizado no conjunto esperado.
- Não foram feitas as 1.000 requisições previstas: insistir contra recusa registrada contraria a regra do catálogo.
- Acesso só por decisão do titular: documentação oficial ou liberação pela SAJ, ou sessão assistida (decisão 0067).

Bytes e `.captura.json`: `C:\dev\fv14-sondas\npl\f1-teste\` (fora do repositório).
