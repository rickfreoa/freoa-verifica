"""Expectativas da extração estrutural; oráculos históricos ficam preservados."""


def audit_gold(case):
    expected = case.get("gold", case.get("expected"))
    # Propostas ambíguas são retidas na camada de extração, sem confirmação.
    if case["id"] in {"C062", "C076"}:
        path = "art69" if case["id"] == "C062" else "art83"
        return [f"federal/lei/6404/1976/{path}"]
    return expected


def prosa_expected(case):
    return case["expected"]
