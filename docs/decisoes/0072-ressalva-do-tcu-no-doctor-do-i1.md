# 0072 - Ressalva do TCU no critério do doctor do I1

Estado: aceita. Decisão do titular (Ricardo Peres Freoa) em 28/10/2026, registrada pelo supervisor.

## Contexto

A etapa 8 da seção 5 do plano exige `fv doctor` ok, "alertas só de indisponibilidade classificada". No
fechamento do I1 (`docs/auditoria/1.4.0/aceite-i1.md`), o doctor da 1.4.0a1 instalada teve dois alertas sem
categoria provada (decisão 0045): DataJud `http_429` e TCU `tcu_busca_incompleta_limite_de_varredura`. O
parecer do auditor sobre a etapa 8 registrou o bloqueador. O alerta do TCU se repete em toda execução: o
conector sinaliza o limite da própria varredura como `Unavailable` sem categoria nem evidência, e o doctor
trata qualquer alerta como compatível com `ok`. O TCU já está fora do escopo do I1 (falha da bateria fora do
escopo desde o I1.4).

## Decisão

1. No I1, e só nele, o alerta do TCU com motivo `tcu_busca_incompleta_limite_de_varredura` não impede a etapa
   8. Fica registrado como ressalva no recibo `doctor` do manifesto e no rótulo do incremento.
2. Todo outro alerta continua sujeito ao critério. O DataJud não está ressalvado: o doctor é repetido e só
   vale a execução em que o DataJud sai `ok` ou com categoria provada.
3. A ressalva não altera código, a decisão 0045 nem o critério da seção 5 para os incrementos seguintes.
4. Defeitos registrados para o I2, a resolver antes do fechamento dele: (a) o doctor não distingue alerta
   classificado de alerta sem categoria; (b) a busca do TCU sinaliza o limite de varredura como
   indisponibilidade sem categoria, quando deveria declarar cobertura incompleta; (c) `http_429` não tem
   categoria no mapeamento de `connectors/challenge.py`, a decidir se merece uma, por decisão formal.

## Consequências

- O recibo `doctor` do I1 lista só os alertas classificados e leva nota com a ressalva e a remissão a esta
  decisão; o parecer do auditor sobre a etapa 8 confere a ressalva contra o log.
- O I2 não pode invocar esta decisão.
