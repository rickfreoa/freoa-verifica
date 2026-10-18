"""Atributos verificáveis de autoridade e rótulo A–E (regra pública)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

RULES_VERSION = "autoridade-1"

# Espécies reconhecidas (forma canônica).
SPECIES = frozenset(
    {
        "sumula_vinculante",
        "controle_concentrado",
        "repercussao_geral",
        "repetitivo",
        "irdr_iac",
        "sumula",
        "orgao_cupula",
        "acordao",
        "monocratica",
        "administrativa",
        "informativo",
    }
)

# Órgãos de cúpula / colegiados superiores (rótulo C) — só judiciais.
CUPULA_ORGANS = frozenset(
    {
        "pleno",
        "plenario",
        "tribunal pleno",
        "corte especial",
        "secao",
        "primeira secao",
        "segunda secao",
        "terceira secao",
        "orgao especial",
    }
)

CONTROLE_CLASSES = frozenset({"adi", "adc", "adpf", "ado"})

# Cortes administrativas: nunca promovidas por órgão de cúpula.
_ADMIN_COURTS = frozenset({"CVM", "TCU", "BCB", "CMN"})

_SPECIES_ALIASES: dict[str, str] = {
    "acordao": "acordao",
    "acordaos": "acordao",
    "monocratica": "monocratica",
    "decisao monocratica": "monocratica",
    "decisoes monocraticas": "monocratica",
    "administrativa": "administrativa",
    "controle concentrado": "controle_concentrado",
    "controle_concentrado": "controle_concentrado",
    "repercussao geral": "repercussao_geral",
    "repercussao_geral": "repercussao_geral",
    "repetitivo": "repetitivo",
    "tema repetitivo": "repetitivo",
    "irdr": "irdr_iac",
    "iac": "irdr_iac",
    "irdr_iac": "irdr_iac",
    "irdr/iac": "irdr_iac",
    "sumula": "sumula",
    "sumula vinculante": "sumula_vinculante",
    "sumula_vinculante": "sumula_vinculante",
    "orgao_cupula": "orgao_cupula",
    "informativo": "informativo",
}


@dataclass(frozen=True)
class AuthorityAttributes:
    species: str
    court: str
    organ: str | None = None
    class_name: str | None = None

    def __post_init__(self) -> None:
        if self.species not in SPECIES:
            raise ValueError(f"espécie desconhecida: {self.species}")


@dataclass(frozen=True)
class AuthorityLabel:
    label: str  # A..E
    rule: str
    attributes: AuthorityAttributes
    rules_version: str = RULES_VERSION


def normalize_species(species: str) -> str:
    """Normaliza espécie (acórdão/ACÓRDÃO/Acordao → acordao)."""
    key = _norm(species)
    if key in _SPECIES_ALIASES:
        return _SPECIES_ALIASES[key]
    # remove underscores duplicados / espaços já tratados por _norm
    compact = key.replace(" ", "_")
    if compact in SPECIES:
        return compact
    if compact in _SPECIES_ALIASES:
        return _SPECIES_ALIASES[compact]
    raise ValueError(f"espécie desconhecida: {species}")


def classify_authority(
    *,
    species: str,
    court: str,
    organ: str | None = None,
    class_name: str | None = None,
) -> AuthorityLabel:
    """Deriva rótulo A–E e devolve sempre atributos + regra aplicada."""
    species_n = normalize_species(species)
    # Preserva grafia comprovada do órgão (ex.: Plenário), só normaliza internamente.
    attrs = AuthorityAttributes(
        species=species_n,
        court=(court or "").strip().upper(),
        organ=organ,
        class_name=class_name,
    )
    label, rule = _derive(attrs)
    return AuthorityLabel(label=label, rule=rule, attributes=attrs)


def _derive(attrs: AuthorityAttributes) -> tuple[str, str]:
    species = attrs.species
    court = attrs.court
    organ_norm = _norm(attrs.organ)
    class_norm = _norm(attrs.class_name)

    # Exclusões antes de qualquer promoção (monocrática / administrativa).
    if species == "monocratica":
        return "E", "especie=monocratica"
    if species == "administrativa" or court in _ADMIN_COURTS:
        return "E", "administrativa_ou_corte_administrativa"

    # A — súmula vinculante; ADI/ADC/ADPF colegiados; súmulas STF/STJ
    if species == "sumula_vinculante":
        return "A", "especie=sumula_vinculante"
    if species == "controle_concentrado" or class_norm in CONTROLE_CLASSES:
        return "A", "controle_concentrado_ou_classe_adi_adc_adpf"
    if species == "sumula" and court in {"STF", "STJ"}:
        return "A", f"sumula_{court.lower()}"

    # B — tema RG, repetitivo, IRDR/IAC
    if species == "repercussao_geral":
        return "B", "especie=repercussao_geral"
    if species == "repetitivo":
        return "B", "especie=repetitivo"
    if species == "irdr_iac":
        return "B", "especie=irdr_iac"

    # C — Pleno / Corte Especial / Seções / Órgão Especial (judiciais)
    if species == "orgao_cupula" or _is_cupula(organ_norm):
        return "C", "orgao_cupula_ou_colegiado_superior"

    # D — acórdão de turma/câmara (padrão residual de julgamento colegiado)
    if species in {"acordao", "informativo"}:
        return "D", "acordao_turma_camara_ou_equivalente"

    return "E", "residual_especie_" + species


def _norm(value: str | None) -> str:
    if not value:
        return ""
    return (
        value.strip()
        .lower()
        .replace("á", "a")
        .replace("ã", "a")
        .replace("à", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )


def _is_cupula(organ_norm: str) -> bool:
    if not organ_norm:
        return False
    if organ_norm in CUPULA_ORGANS:
        return True
    return any(
        token in organ_norm
        for token in (
            "pleno",
            "plenario",
            "corte especial",
            "orgao especial",
            "secao",
        )
    )


def as_dict(label: AuthorityLabel) -> dict[str, Any]:
    return {
        "label": label.label,
        "rule": label.rule,
        "rules_version": label.rules_version,
        "attributes": {
            "species": label.attributes.species,
            "court": label.attributes.court,
            "organ": label.attributes.organ,
            "class_name": label.attributes.class_name,
        },
    }
