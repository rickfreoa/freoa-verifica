# Como contribuir

1. Leia `AGENTS.md` (regras invariáveis) e `docs/ARQUITETURA.md`.
2. Abra uma issue descrevendo o problema ou a fonte nova antes de um pull request grande.
3. Todo pull request traz teste de regressão e mantém `pytest -q -m "not live"` verde.
4. Conector novo: declare cobertura, implemente `health` com positivo, negativo e documento, grave fixtures reais com SHA-256 e trate desafio como `unavailable`.
5. Inclua no pull request a frase `Li e concordo com o CLA.md`. O CLA permite manter a licença comercial alternativa descrita em `LICENCIAMENTO.md`.
