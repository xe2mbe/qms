import re

def validar_call_sign(callsign: str) -> dict:
    """
    Valida un indicativo y regresa un diccionario con:
    - indicativo: True/False
    - completo: True/False
    - Zona: XE1, XE2, XE3, Definir, Extranjera o Error
    - tipo: ham, SWL o Error
    """

    callsign = callsign.strip().upper()

    # Caso especial: SWL
    if callsign == "SWL":
        return {
            "indicativo": True,
            "completo": True,
            "Zona": "Definir",
            "tipo": "SWL"
        }

    # XE1, XE2, XE3 (con o sin sufijo de 1 a 3 letras)
    regex_xe123 = re.compile(r'^(XE[123])([A-Z]{1,3})?$')

    # XE/XF/XB + dígito 4–9 + sufijo de 1–3 letras
    regex_mex_general = re.compile(r'^(?:XE|XF|XB)[4-9][A-Z]{1,3}$')

    # Prefijos especiales México: 4A–4C y 6D–6J con un dígito + sufijo
    regex_mex_especial = re.compile(r'^(?:4[ABC]|6[D-J])\d[A-Z0-9]{1,3}$')

    # Caso XE1–XE3
    match_xe = regex_xe123.match(callsign)
    if match_xe:
        zona = match_xe.group(1)
        sufijo = match_xe.group(2)
        return {
            "indicativo": True,
            "completo": bool(sufijo),
            "Zona": zona,
            "tipo": "ham"
        }

    # Caso mexicano general o especial
    if regex_mex_general.match(callsign) or regex_mex_especial.match(callsign):
        return {
            "indicativo": True,
            "completo": True,
            "Zona": "Definir",
            "tipo": "ham"
        }

    # 🚨 Si empieza con XE/XF/XB/4/6 pero no cumplió → es error, no extranjera
    if callsign.startswith(("XE", "XF", "XB", "4", "6")):
        return {
            "indicativo": False,
            "completo": False,
            "Zona": "Error",
            "tipo": "Error"
        }

    # Caso extranjero genérico: debe empezar con letra y tener al menos 3 caracteres
    regex_ext = re.compile(r'^[A-Z][A-Z0-9]{2,}$')
    if regex_ext.match(callsign):
        return {
            "indicativo": True,
            "completo": True,
            "Zona": "Extranjera",
            "tipo": "ham"
        }

    # No válido
    return {
        "indicativo": False,
        "completo": False,
        "Zona": "Error",
        "tipo": "Error"
    }


# =============================
# Ejemplos de uso
# =============================
tests = ["SWL", "XE2", "XE1ABC", "XE11", "XF4Z", "4A1MX", "6D2XYZ", "K5AB", "123"]

for t in tests:
    print(f"{t:7} -> {validar_call_sign(t)}")
