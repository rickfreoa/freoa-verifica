# 0052 — Fixtures com proveniência e heurística de família de conectores

Data: 19/10/2026 · Versão: 1.3.0 · Origem: marco G2 do plano 1.3.0

## Contexto

O diretório `tests/fixtures/` mistura capturas de fontes oficiais, respostas sintéticas e arquivos de
sondas sem registro uniforme de origem. Sem regra escrita, uma amostra real pode ser editada à mão e
passar por captura, e um conector novo pode ser generalizado antes de existir padrão repetido.

## Decisão

1. Fixture é ou captura real com proveniência em `tests/fixtures/FIXTURES.json` (categoria
   `captura_real`) ou sintética rotulada com gerador e propósito (categoria `sintetica`). Amostra real
   nunca é editada à mão; nova captura passa por `scripts/capturar_fixture.py`. Todo arquivo do
   diretório consta do manifesto (regra 9 do `AGENTS.md`).
2. Generalizar um conector para classe ou utilitário comum só depois de duas ocorrências concretas do
   mesmo padrão. Antes disso, duplicação local é preferível a abstração prematura.
3. Comandos acrescentados ao `AGENTS.md`: `python scripts/capturar_fixture.py --help` e
   `pytest -q -m repositorio` (testes que exigem o checkout).

## Consequências

- O manifesto passa a ser a fonte de verdade da proveniência; `CONTRIBUTING.md` aponta para ele.
- `scripts/capturar_fixture.py` é entregue pelo marco E2; até lá, o comando documentado não existe.
- O marcador `repositorio` ainda não está registrado em `pytest.ini`; nenhum teste o usa hoje.
