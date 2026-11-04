"""Validador mecânico dos gabaritos da Porta L (independente do código do verificador).

Uso: python -I -X utf8 validar_gabaritos.py <conjunto.jsonl> <pasta_evidencias>
Para cada caso com `gabarito.texto`:
  1. a fonte (`evidencias/<sha256>.*`) existe e o SHA-256 dos bytes confere;
  2. o texto normalizado do gabarito é trecho contínuo do texto normalizado da fonte;
  3. termina em pontuação final (. ; : ! ? " ” ) ) e não termina com rubrica ou rótulo do dispositivo seguinte;
  4. em citação de artigo ("art. N"), começa por "Art. N" e o que vem logo depois na fonte é outro dispositivo,
     divisão (Capítulo, Seção, Título, Livro), rubrica seguida de "Art." ou fim;
  5. tamanho entre 20 e 8000 caracteres.
Casos `nao_verificado_para_D`: exige `fonte_oficial.url`, `sha256` com evidência existente e `fundamento_data`.
Unidades de independência: (norma, familia) por capacidade; exige >= 8 e >= 4 normas.
Saída: lista de falhas; código 0 só sem falha.
"""
import hashlib, html, json, re, sys, unicodedata
from collections import defaultdict
from pathlib import Path

def texto_da_fonte(b: bytes) -> str:
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            s = b.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if b[:5] == b"%PDF-":
        return ""  # PDF: só confere hash
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?is)<strike>.*?</strike>|<s>.*?</s>|<del>.*?</del>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return html.unescape(s)

def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.replace(" ", " ").replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = s.replace("º", "o").replace("°", "o")
    return re.sub(r"\s+", " ", s).strip()

_ANOTACAO = re.compile(
    r"\(\s*(?:\"?Caput\"?\s*do\s+artigo|Artigo|Par[aá]grafo|Inciso|Al[ií]nea|Item|Se[cç][aã]o|"
    r"Reda[cç][aã]o|Revogad|Revoga[cç][aã]o|Vide\s|NR\b|acrescid|inclu[ií]d|Produ[cç][aã]o de efeitos)[^)]*\)",
    re.I,
)
PROX = re.compile(r'^\s*(Art\.?\s*\d|CAP[IÍ]TULO|Cap[ií]tulo|SE[CÇ][AÃ]O|Se[cç][aã]o|T[IÍ]TULO|LIVRO|Subse[cç][aã]o|ANEXO|Anexo|\(|$)')
RUBRICA_PROX = re.compile(r'^\s*[A-ZÁÉÍÓÚÂÊÔÃÕÇ][^.;:]{0,90}?\s+Art\.?\s*\d')

def main(conj, pasta):
    pasta = Path(pasta)
    falhas = []
    casos = [json.loads(l) for l in Path(conj).read_text(encoding="utf-8").splitlines() if l.strip()]
    unidades = defaultdict(set); normas = defaultdict(set)
    for c in casos:
        cid = c["id"]; g = c["gabarito"]; fo = g.get("fonte_oficial") or {}
        fam = c.get("familia_alteracao") or ""
        if re.search(r"-(b|c|d|e|f|g|h|alt)$", fam):
            falhas.append(f"{cid}: familia com sufixo artificial: {fam}")
        nk = (c["norma"].get("especie"), str(c["norma"].get("numero")), c["norma"].get("ano"))
        unidades[c["capacidade"]].add((nk, fam)); normas[c["capacidade"]].add(nk)
        sha = fo.get("sha256")
        arqs = list(pasta.glob(f"{sha}.*")) if sha else []
        if not fo.get("url") or not arqs:
            falhas.append(f"{cid}: fonte_oficial sem url ou sem evidência gravada"); continue
        b = arqs[0].read_bytes()
        if hashlib.sha256(b).hexdigest() != sha:
            falhas.append(f"{cid}: sha256 não confere com a evidência"); continue
        if g["tipo"] in ("nao_verificado_para_D", "nao_existia_em_D"):
            if not (g.get("fundamento_data") or "").strip():
                falhas.append(f"{cid}: sem fundamento_data")
            if c["capacidade"] != "c":
                falhas.append(f"{cid}: tipo {g['tipo']} fora de (c)")
            continue
        if g["tipo"] not in ("texto", "verificado_para_D"):
            falhas.append(f"{cid}: tipo de gabarito desconhecido {g['tipo']!r}")
        t = norm(g.get("texto") or "")
        if re.search(r"(?i)reda[cç][aã]o dada|acrescid[oa] pel|inclu[ií]d[oa] pel|revogad[oa] pel|vide |WhatsApp|0800|Atendimento", t):
            falhas.append(f"{cid}: anotação de alteração ou ruído de página no gabarito")
        if len(re.findall(r'(?:^|[\s"\'])Art\.\s*\d', t)) > 1:
            falhas.append(f"{cid}: gabarito contém mais de um artigo")
        if c["capacidade"] == "d" and "anexo" not in c["citacao"].lower():
            falhas.append(f"{cid}: (d) sem 'Anexo' na citação")
        if c["capacidade"] == "e":
            for a in g.get("alvos") or []:
                if not re.match(r"(?i)(art\.\s*\d|anexo\s+[IVXLC\d])", str(a.get("caminho", ""))):
                    falhas.append(f"{cid}: alvo sem caminho de dispositivo: {a}")
        if not 20 <= len(t) <= 8000:
            falhas.append(f"{cid}: tamanho implausível ({len(t)})")
        if c["capacidade"] == "e" and not g.get("alvos"):
            falhas.append(f"{cid}: (e) sem alvos")
        if t.endswith(":"):
            falhas.append(f"{cid}: termina em dois-pontos (dispositivo truncado antes dos incisos)")
        if not re.search(r'[.;:!?")]$', t):
            falhas.append(f"{cid}: não termina em pontuação final: ...{t[-40:]!r}")
        # Só na FONTE: anotações de alteração intercaladas na compilada (o gabarito não pode contê-las; ver acima).
        fonte = re.sub(r"\s+", " ", _ANOTACAO.sub(" ", norm(texto_da_fonte(b)))).strip()
        if not fonte:
            continue
        pos = fonte.find(t)
        if pos < 0:
            falhas.append(f"{cid}: gabarito não é trecho contínuo da fonte (início {t[:50]!r})"); continue
        m = re.match(r"\s*art\.?\s*([\d.]+(?:-[A-Z])?)", c["citacao"], re.I)
        if m and c["capacidade"] != "d":
            num = m.group(1).replace(".", "")
            if re.search(r"(Art\.?\s*[\d.]+(-[A-Z])?\.?|§\s*\d+o?\.?|Par[aá]grafo [uú]nico\.?)$", t):
                falhas.append(f"{cid}: termina com rótulo de dispositivo seguinte: ...{t[-30:]!r}")
            if not re.match(rf'"?\s*Art\.?\s*{re.escape(num)}(?![\d])', re.sub(r"(?<=\d)\.(?=\d)", "", t)):
                falhas.append(f"{cid}: não começa por 'Art. {num}': {t[:30]!r}")
            depois = fonte[pos + len(t):pos + len(t) + 140]
            if not (PROX.match(depois) or RUBRICA_PROX.match(depois)):
                falhas.append(f"{cid}: corte suspeito; segue na fonte: {depois[:60]!r}")
    for cap in "abcde":
        if len(unidades[cap]) < 8 or len(normas[cap]) < 4:
            falhas.append(f"capacidade {cap}: {len(unidades[cap])} unidades independentes, {len(normas[cap])} normas")
    for f in falhas:
        print("FALHA", f)
    print(f"{len(casos)} casos, {len(falhas)} falhas")
    return 1 if falhas else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
