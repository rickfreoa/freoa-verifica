## Pendências

O arquivo disponível declara **v2**, não v1 ([plano:3](C:/dev/freoa-verifica-v2/docs/PLANO-1.3.0.md:3)). Sobre esses bytes:

- **T2:** manter o UA anterior justamente nos conectores que recusarem o identificado continua condicionando a exceção à recusa. O anterior simula Chrome ([transport.py:38](C:/dev/freoa-verifica-v2/freoa_verifica/transport.py:38)); registrar a tensão e adiá-la não demonstra compatibilidade com a regra 3. Exigir justificativa compatível antes de manter a exceção; sem ela, declarar indisponibilidade ([plano:23](C:/dev/freoa-verifica-v2/docs/PLANO-1.3.0.md:23)).
- **D2/G3:** o rascunho protege a publicação GitHub, mas deixa aberta a publicação antecipada no PyPI. Quando habilitado, o workflow publica após o build ([release.yml:84](C:/dev/freoa-verifica-v2/.github/workflows/release.yml:84)), antes da auditoria dos bytes prevista no [plano:64](C:/dev/freoa-verifica-v2/docs/PLANO-1.3.0.md:64). Condicionar também o PyPI à conclusão dessa auditoria.

VEREDITO: SEM CONSENSO — pontos: T2, D2/G3.