## Pendências

- **T2 / S2–S3:** `docs/PLANO-1.3.0.md:23` ainda permite exceção de UA pela ausência de controle **declarado**, insuficiente para demonstrar compatibilidade com a proibição da linha 5. Também transforma qualquer recusa ao identificado em `ambiental_bloqueio`, contrariando a exigência de evidência da linha 20 e permitindo ocultar regressões como xfail. Exigir prova positiva da classificação e de que a exceção não contorna recusa.

- **D1/D2 — instalação preliminar:** `docs/PLANO-1.3.0.md:60` manda instalar o snapshot antes de registrar seu digest na linha 61. O código recusa esses bytes sem vínculo (`freoa_verifica/snapshot.py:676–679`, chamada na linha 727). Explicitar a instalação experimental com `--aceitar-nao-vinculado` em home descartável e repetir a validação vinculada com a wheel final.

- **D1/D2 — artefato publicado:** `docs/PLANO-1.3.0.md:62–63` audita uma wheel local e depois publica outra construída pelo workflow (`.github/workflows/release.yml:34–37`). Mesmo commit não demonstra identidade dos artefatos. Falta exigir auditoria dos bytes produzidos pela CI antes da publicação ou comparação verificável com os bytes auditados.

VEREDITO: SEM CONSENSO — pontos: exceções de UA e classificação ambiental; instalação preliminar do snapshot; identidade da wheel auditada/publicada.