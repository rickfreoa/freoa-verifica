# Sondas formais de normas.leg.br (0085 §2)

Capturadas em 14/11/2026 por `scripts/capturar_fixture.py --fonte-sonda normas_leg --sonda`,
UA identificado. Corpos fora do repositório (`C:\dev\fv14-sondas\normas_leg`); aqui os recibos
e os trechos que fundamentam o contrato da API, com offset em bytes no corpo capturado.

## `s_main_js` — https://normas.leg.br/main.9e54abd8eff4fac4.js
- sha256 `29b7f4d3cd4250f61c625b503f1bf58441e7322661b069a8662cecabc517a4f2`, 744680 bytes, status 200
- offset 42334: `publicApiUrl:"/api/public/"`

## `s_987_js` — https://normas.leg.br/987.9451176cf8cb4e12.js
- sha256 `b04f0e8b48bce6635e570de4f52bb3a8af58bf70c4162ed6b237f92324039324`, 879862 bytes, status 200
- offset 114893: `publicApiUrl+"normas?urn="`
- offset 121391: `&&tipo_documento=${t}`
- offset 121568: `"maior-detalhe"`
- offset 266250: `replace("/api/binario/","/api/public/binario/")`

## `s_meta_l6404` — https://normas.leg.br/api/public/normas?urn=urn:lex:br:federal:lei:1976;6404&tipo_documento=maior-detalhe
- sha256 `94b3e19a5f1590f6bbaf0a79400b29db00e9943ac513b1df429cc764d9fa86f6`, 4537 bytes, status 200
- offset 498: `"sdLicense":"https://creativecommons.org/licenses/by/4.0/"`
- offset 167: `"legislationIdentifier"`

