"""Placar FREOA × JusRatio sobre o conjunto-ouro 1.2.0.

Critérios (iguais para os dois sistemas, fixados antes da leitura do resultado temático):
- positivo (item existe): acerto = o item pedido é entregue (FREOA: identidade confirmada/`encontrada`;
  JusRatio: o item pedido entre os 5 primeiros ou no bloco de referências que o próprio resultado anuncia).
  Abstenção declarada NÃO é acerto em positivo.
- negativo (item inexistente): acerto = nenhum outro item apresentado como o pedido.
- temático: acerto = ao menos um resultado julgado "sim" pelo juiz cego entre os 5 primeiros; também se
  reporta a precisão (sim / total).
- "no acervo FREOA" = o item existe e está no acervo instalado ou numa fonte que o FREOA consulta ao vivo.
Os julgamentos caso a caso estão em JULGAMENTOS, com a evidência resumida.
"""
import json
import sys
from pathlib import Path

AQUI = Path(__file__).parent

# id: (tipo, no_acervo_freoa, acerto_freoa, acerto_jusratio, nota)
JULGAMENTOS = {
    "A1": ("positivo", True, True, True, "ambos: art. 254-A LSA (FREOA com captura e vigência)"),
    "A2": ("positivo", True, True, True, "ambos"),
    "A3": ("positivo", True, True, True, "JusRatio: CPC 1.072 em 1º, CC 1.072 em 2º"),
    "A4": ("positivo", True, True, True, "ambos (JusRatio traz também ADCT art. 5º)"),
    "A5": ("positivo", True, True, True, "ambos (JusRatio traz também ADCT art. 60)"),
    "A6": ("negativo", True, True, True, "FREOA: DISPOSITIVO_INEXISTENTE com captura; JusRatio: aviso 'LSA art. 312 não retornado', devolve art. 312 de outros diplomas"),
    "B1": ("positivo", True, True, True, "ambos"),
    "B2": ("positivo", True, True, True, "ambos"),
    "B3": ("positivo", True, True, True, "ambos"),
    "B4": ("positivo", True, True, True, "ambos (FREOA: obra sem dispositivo)"),
    "B5": ("positivo", True, True, True, "ambos marcam revogada"),
    "B6": ("negativo", True, True, True, "FREOA: indisponível (http_410), sem confirmação; JusRatio: 'norma fora da base'"),
    "C1": ("positivo", True, True, True, "JusRatio: verbete no bloco de referências anunciado; top5 são acórdãos"),
    "C2": ("positivo", True, True, True, "idem"),
    "C3": ("positivo", False, False, False, "FREOA: súmulas do STJ fora do acervo (abstenção); JusRatio: top5 sem o verbete e sem referência anunciada"),
    "C4": ("positivo", False, False, False, "idem"),
    "C5": ("positivo", True, True, True, "JusRatio: verbete no bloco de referências"),
    "C6": ("negativo", True, True, True, "FREOA: não confirmado; JusRatio: alerta verbete ausente"),
    "D1": ("positivo", True, True, True, "ambos"),
    "D2": ("positivo", True, True, True, "ambos"),
    "D3": ("positivo", False, False, True, "FREOA: fora do recorte do acervo (abstenção declarada)"),
    "D4": ("positivo", True, True, True, "ambos"),
    "E1": ("positivo", True, True, True, "FREOA: só o processo, via API oficial do TJDFT"),
    "E2": ("positivo", True, True, True, "ambos"),
    "E3": ("positivo", True, True, True, "ambos"),
    "F1": ("positivo", False, False, True, "FREOA: acórdão fora do acervo TCU instalado"),
    "F2": ("positivo", False, False, False, "nenhum localizou o processo"),
    "F3": ("positivo", False, False, False, "nenhum localizou o processo"),
    "F4": ("positivo", False, False, True, "FREOA: PAS de 2016 fora do acervo CVM (40 decisões de 2023)"),
    "G1": ("negativo", True, True, True, "FREOA: não confirmado; JusRatio: alerta identificador ausente"),
    "G2": ("negativo", True, True, True, "idem"),
    "G3": ("negativo", True, True, True, "idem"),
    "G4": ("negativo", True, True, True, "FREOA: DISPOSITIVO_INEXISTENTE com captura; JusRatio: devolve art. 300 e outros, sem afirmar 300-B"),
    "G5": ("negativo", True, True, True, "FREOA: dígito verificador inválido; JusRatio: resultados alheios com score fraco, sem afirmar identidade"),
    "G6": ("negativo", True, True, True, "ambos sem confirmação"),
}
TEMAS = ("D5", "D6", "D7", "D8", "E4", "E5", "E6")


def main() -> None:
    veredito = json.loads((AQUI / "juiz_veredito.json").read_text(encoding="utf-8"))
    chave = json.loads((AQUI / "juiz_chave.json").read_text(encoding="utf-8"))
    linhas, tot = [], {"geral": [0, 0, 0], "acervo": [0, 0, 0]}
    for cid, (tipo, acervo, fv, jr, nota) in JULGAMENTOS.items():
        linhas.append((cid, tipo, acervo, fv, jr, nota))
    prec = {"FV": [0, 0], "JR": [0, 0]}
    for cid in TEMAS:
        hit = {"FV": False, "JR": False}
        for n, v in veredito[cid].items():
            src = chave[f"{cid}-{n}"]
            prec[src][1] += 1
            if v == "sim":
                prec[src][0] += 1
                hit[src] = True
        linhas.append((cid, "tematico", True, hit["FV"], hit["JR"], "juiz cego"))
    for cid, tipo, acervo, fv, jr, _ in linhas:
        for k in ("geral",) + (("acervo",) if acervo else ()):
            tot[k][0] += 1
            tot[k][1] += fv
            tot[k][2] += jr
    out = ["| Caso | Tipo | No acervo FREOA | FREOA | JusRatio | Nota |", "|---|---|---|---|---|---|"]
    out += [f"| {c} | {t} | {'sim' if a else 'não'} | {'✔' if f else '✘'} | {'✔' if j else '✘'} | {n} |"
            for c, t, a, f, j, n in linhas]
    out.append("")
    for k, (n, f, j) in tot.items():
        out.append(f"**{k}**: {n} casos — FREOA {f}/{n}, JusRatio {j}/{n}")
    out.append(f"**precisão temática (resultados 'sim')**: FREOA {prec['FV'][0]}/{prec['FV'][1]}, "
               f"JusRatio {prec['JR'][0]}/{prec['JR'][1]}")
    out.append("**confirmações indevidas**: FREOA 0, JusRatio 0 (nenhum sistema apresentou outro item como o pedido)")
    texto = "\n".join(out)
    (AQUI / "placar.md").write_text(texto + "\n", encoding="utf-8")
    sys.stdout.write(texto + "\n")


if __name__ == "__main__":
    main()
