"""Benchmark de verificação contra gold.jsonl."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CasoResultado:
    id: str
    tipo: str  # positivo|mutante|decisao
    ok: bool
    identity: str | None = None
    text: str | None = None
    gold_suspeito: dict[str, Any] | None = None
    detalhe: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    fonte: str = "desconhecida"
    com_trecho: bool = False
    decisao_real: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "tipo": self.tipo,
            "ok": self.ok,
            "identity": self.identity,
            "text": self.text,
            "detalhe": self.detalhe,
            "fonte": self.fonte,
            "resultado": self.raw,
        }
        if self.decisao_real is not None:
            d["decisao_real"] = self.decisao_real
        if self.gold_suspeito:
            d["gold_suspeito"] = self.gold_suspeito
        return d


def _load_gold(path: Path) -> list[dict[str, Any]]:
    casos: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"gold linha {i}: JSON inválido: {exc}") from exc
        if "id" not in obj:
            obj["id"] = f"caso-{i}"
        if "tipo" not in obj:
            raise ValueError(f"gold linha {i}: falta 'tipo'")
        casos.append(obj)
    return casos


def _dim(res: dict[str, Any], nome: str) -> str | None:
    bloco = res.get(nome)
    if isinstance(bloco, dict):
        return bloco.get("status")
    return None


def run_bench(svc: Any, gold_path: str | Path) -> dict[str, Any]:
    """Executa benchmark e devolve relatório estruturado."""
    path = Path(gold_path)
    if not path.is_file():
        return {"status": "erro", "motivo": "gold_ausente", "caminho": str(path)}

    casos = _load_gold(path)
    for caso in casos:
        if caso["tipo"] not in {"positivo", "mutante", "decisao", "decisao_falsa"}:
            raise ValueError("tipo de caso desconhecido")
    resultados: list[CasoResultado] = []

    for caso in casos:
        cid = str(caso["id"])
        tipo = str(caso["tipo"]).lower()
        citacao = caso.get("citacao") or caso.get("citation") or ""
        trecho = caso.get("trecho") or caso.get("texto_citado")
        expectativa = caso.get("expectativa") or {}

        if tipo in {"decisao", "decisao_falsa"}:
            texto = caso.get("texto") or citacao
            res = svc.verificar_texto(texto)
            # decisão real vs falsa: olhar status das citações de decisão
            real = tipo != "decisao_falsa" and bool(caso.get("decisao_real", True))
            statuses = [c.get("status") for c in res.get("citacoes") or [] if (c.get("parseada") or {}).get("decision")]
            encontrada = any(s == "encontrada" for s in statuses)
            if real:
                ok = encontrada
            else:
                ok = bool(statuses) and all(s == "inexistente" for s in statuses)
            resultados.append(
                CasoResultado(
                    id=cid,
                    tipo="decisao",
                    ok=ok,
                    detalhe=f"real={real} statuses={statuses}",
                    raw=res,
                    fonte=caso.get("fonte") or caso.get("tribunal") or "desconhecida",
                    decisao_real=real,
                )
            )
            continue

        # positivo / mutante
        res = svc.verificar_citacao(citacao, trecho=trecho)
        identity = _dim(res, "identity")
        text = _dim(res, "text")
        gold_suspeito = None

        if tipo == "positivo":
            # esperado: identity verified; text verified se trecho presente
            id_ok = identity == "verified"
            text_ok = True if trecho is None else text == "verified"
            ok = id_ok and text_ok
            # gold suspeito: se falhou mas há evidência oficial divergente do trecho do gold
            if not ok and identity == "verified" and text in {"divergent", "not_found"}:
                ev = (res.get("text") or {}).get("evidence") or (res.get("text") or {}).get(
                    "evidencia"
                )
                oficial = None
                if isinstance(ev, list):
                    oficial = next((e.get("trecho_oficial") for e in ev if e.get("trecho_oficial")), None)
                elif isinstance(ev, dict):
                    oficial = ev.get("trecho") or ev.get("oficial") or ev.get("excerpt")
                if oficial and trecho and oficial.strip() != str(trecho).strip():
                    gold_suspeito = {
                        "motivo": "trecho_gold_diverge_do_oficial",
                        "trecho_oficial": str(oficial)[:500],
                        "trecho_gold": str(trecho)[:500],
                    }
            # expectativa explícita no gold (não altera exclusão das métricas)
            if expectativa.get("identity"):
                ok = identity == expectativa["identity"] and (
                    trecho is None or text == expectativa.get("text", text)
                )
        else:  # mutante
            # nunca deve ser text=verified (nem identity+text verified com trecho mutante)
            falso_verified = text == "verified"
            if trecho is None:
                # mutante só de identidade: identity não pode ser verified se number/path errado
                exp_id = expectativa.get("identity")
                if exp_id:
                    ok = identity == exp_id
                else:
                    ok = identity != "verified"
            else:
                ok = not falso_verified
                if expectativa.get("text"):
                    ok = text == expectativa["text"]

        resultados.append(
            CasoResultado(
                id=cid,
                tipo=tipo,
                ok=ok,
                identity=identity,
                text=text,
                gold_suspeito=gold_suspeito,
                raw=res,
                fonte=caso.get("fonte") or ((res.get("citation") or {}).get("work") or {}).get("authority", "desconhecida"),
                com_trecho=trecho is not None,
            )
        )

    return _agregar(resultados, caminho=str(path))


def _agregar(resultados: list[CasoResultado], *, caminho: str) -> dict[str, Any]:
    positivos = [r for r in resultados if r.tipo == "positivo"]
    mutantes = [r for r in resultados if r.tipo == "mutante"]
    decisoes = [r for r in resultados if r.tipo == "decisao"]

    def taxa(ok_n: int, total: int) -> float | None:
        if total == 0:
            return None
        return round(ok_n / total, 4)

    pos_id = sum(1 for r in positivos if r.identity == "verified")
    pos_text = sum(1 for r in positivos if r.text == "verified")
    # positivos com trecho
    pos_com_trecho = [r for r in positivos if r.com_trecho]
    pos_text_ok = sum(1 for r in pos_com_trecho if r.text == "verified")

    mut_falso = sum(1 for r in mutantes if r.text == "verified" or (not r.com_trecho and r.identity == "verified"))
    mut_ok = sum(1 for r in mutantes if r.ok)

    dec_ok = sum(1 for r in decisoes if r.ok)

    # indisponibilidade por fonte (quando identity/text unavailable)
    indisponivel: dict[str, int] = {}
    for r in resultados:
        unavailable = r.identity == "unavailable" or r.text == "unavailable"
        if r.tipo == "decisao":
            unavailable = any(c.get("status") == "indisponivel" for c in r.raw.get("citacoes", []))
        if unavailable:
            indisponivel[r.fonte] = indisponivel.get(r.fonte, 0) + 1

    gold_suspeitos = [r.as_dict() for r in resultados if r.gold_suspeito]

    relatorio = {
        "status": "ok",
        "gold": caminho,
        "total": len(resultados),
        "metricas": {
            "positivos": {
                "total": len(positivos),
                "identity_verified": pos_id,
                "taxa_identity_verified": taxa(pos_id, len(positivos)),
                "text_verified": pos_text_ok,
                "com_trecho": len(pos_com_trecho),
                "taxa_text_verified": taxa(pos_text_ok, len(pos_com_trecho)),
            },
            "mutantes": {
                "total": len(mutantes),
                "falsos_verified": mut_falso,
                "taxa_falsos_verified": taxa(mut_falso, len(mutantes)),
                "casos_ok": mut_ok,
            },
            "decisoes": {
                "total": len(decisoes),
                "acertos": dec_ok,
                "acuracia": taxa(dec_ok, len(decisoes)),
                "reais": {"total": sum(r.decisao_real is True for r in decisoes),
                          "acertos": sum(r.ok and r.decisao_real is True for r in decisoes)},
                "falsas": {"total": sum(r.decisao_real is False for r in decisoes),
                           "acertos": sum(r.ok and r.decisao_real is False for r in decisoes)},
            },
            "indisponibilidade_por_fonte": indisponivel,
        },
        "gold_suspeitos": gold_suspeitos,
        "casos": [r.as_dict() for r in resultados],
    }
    return relatorio


def markdown_table(relatorio: dict[str, Any]) -> str:
    m = relatorio.get("metricas") or {}
    pos = m.get("positivos") or {}
    mut = m.get("mutantes") or {}
    dec = m.get("decisoes") or {}
    lines = [
        "# Benchmark FREOA Verifica",
        "",
        f"Gold: `{relatorio.get('gold')}` — {relatorio.get('total')} casos",
        "",
        "| Métrica | Valor |",
        "|---------|-------|",
        f"| Positivos (n) | {pos.get('total')} |",
        f"| Taxa identity=verified | {pos.get('taxa_identity_verified')} |",
        f"| Taxa text=verified (com trecho) | {pos.get('taxa_text_verified')} |",
        f"| Mutantes (n) | {mut.get('total')} |",
        f"| Falsos text=verified | {mut.get('falsos_verified')} |",
        f"| Decisões acurácia | {dec.get('acuracia')} |",
        f"| Gold suspeitos | {len(relatorio.get('gold_suspeitos') or [])} |",
        "",
    ]
    if relatorio.get("casos"):
        lines += [
            "## Casos",
            "",
            "| id | tipo | ok | identity | text |",
            "|----|------|----|----------|------|",
        ]
        for c in relatorio["casos"]:
            lines.append(
                f"| {c.get('id')} | {c.get('tipo')} | {c.get('ok')} | "
                f"{c.get('identity')} | {c.get('text')} |"
            )
        lines.append("")
    return "\n".join(lines)
