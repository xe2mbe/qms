import re
from datetime import datetime
import pytz
from database import FMREDatabase

# Inicializar la base de datos
db = FMREDatabase()

def format_call_sign(call_sign):
    """Formatea un indicativo de llamada a mayúsculas"""
    return call_sign.upper().strip() if call_sign else ""

def format_name(name):
    """Formatea un nombre con mayúsculas iniciales"""
    return name.title().strip() if name else ""

def format_qth(qth):
    """Formatea una ubicación (QTH)"""
    return qth.upper().strip() if qth else ""

def get_mexican_states():
    """Retorna un diccionario con los estados de México desde la base de datos"""
    return db.get_estados()

def get_estados_list():
    """Retorna una lista de tuplas (abreviatura, nombre) de los estados de México"""
    states = get_mexican_states()
    return [(abbr, name) for abbr, name in states.items()]

def get_zonas():
    """Retorna las zonas disponibles desde la base de datos"""
    zonas = db.get_zonas()
    return [(codigo, nombre) for codigo, nombre in zonas.items()]

def get_sistemas():
    """Retorna los sistemas disponibles desde la base de datos"""
    sistemas = db.get_sistemas()
    return [(codigo, nombre) for codigo, nombre in sistemas.items()]

def validar_call_sign(callsign: str) -> dict:
    """
    Valida un indicativo de radioaficionado y regresa un diccionario con:
    - indicativo: True/False (si es válido)
    - completo: True/False (si incluye sufijo)
    - Zona: XE1, XE2, XE3, Especial, Extranjera o Error
    """

    callsign = callsign.strip().upper()

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
            "Zona": zona
        }

    # Caso mexicano general o especial
    if regex_mex_general.match(callsign) or regex_mex_especial.match(callsign):
        return {
            "indicativo": True,
            "completo": True,
            "Zona": "Especial"
        }

    # 🚨 Si empieza con XE/XF/XB/4/6 pero no cumplió → es error, no extranjera
    if callsign.startswith(("XE", "XF", "XB", "4", "6")):
        return {
            "indicativo": False,
            "completo": False,
            "Zona": "Error"
        }

    # Caso extranjero genérico (mínimo 3 caracteres alfanuméricos)
    regex_ext = re.compile(r'^[A-Z0-9]{3,}$')
    if regex_ext.match(callsign):
        return {
            "indicativo": True,
            "completo": True,
            "Zona": "Extranjera"
        }

    # No válido
    return {
        "indicativo": False,
        "completo": False,
        "Zona": "Error"
    }

def validate_operator_name(name):
    """Valida el nombre del operador"""
    if not name or not name.strip():
        return False, "El nombre del operador no puede estar vacío"
    
    if len(name) < 3:
        return False, "El nombre es demasiado corto"
    
    return True, ""

def validate_ciudad(ciudad):
    """Valida el nombre de la ciudad"""
    if not ciudad or not ciudad.strip():
        return False, "La ciudad no puede estar vacía"
    
    return True, ""

def validate_estado(estado):
    """Valida que el estado exista en la base de datos"""
    if not estado:
        return False, "El estado no puede estar vacío"
        
    # Verificar si el estado existe en la base de datos
    estados = get_mexican_states()
    if estado not in estados.values() and estado != 'Extranjero':
        return False, "Seleccione un estado válido"
    
    return True, ""

def validate_signal_report(report):
    """Valida el reporte de señal"""
    if not report or not report.strip():
        return False, "El reporte de señal no puede estar vacío"
    
    # Validar formato común de reportes (ej: 59, 5x9, 5x9+10, etc.)
    pattern = r'^[0-9]{1,2}(x[0-9+]+)?$'
    if not re.match(pattern, report.lower()):
        return False, "Formato de reporte inválido"
    
    return True, ""

def validate_password(password):
    """
    Valida que una contraseña cumpla con los requisitos de seguridad:
    - Mínimo 8 caracteres
    - Al menos una letra mayúscula
    - Al menos un número
    - Al menos un carácter especial
    """
    if not password or len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres"
    
    if not any(char.isupper() for char in password):
        return False, "La contraseña debe contener al menos una letra mayúscula"
    
    if not any(char.isdigit() for char in password):
        return False, "La contraseña debe contener al menos un número"
    
    special_chars = "!@#$%^&*()-_=+[]{}|;:,.<>?/`~"
    if not any(char in special_chars for char in password):
        return False, "La contraseña debe contener al menos un carácter especial"
    
    return True, ""

def validate_call_sign_zone_consistency(call_sign, zona):
    """Valida que el prefijo del indicativo coincida con la zona"""
    if not call_sign or not zona:
        return True  # La validación de campos vacíos se hace en otras funciones
    
    call_sign = call_sign.upper()
    
    # Si es extranjero, no hay validación de prefijo
    if zona == 'EXT' or zona == 'Zona Extranjera':
        return True, ""
    
    # Extraer el prefijo del indicativo (primeros 3 caracteres)
    prefix = call_sign[:3].upper()
    
    # Verificar si el prefijo coincide con la zona
    if zona.startswith('XE') and prefix.startswith('XE'):
        # Verificar el número de zona
        zone_number = zona[2]  # Obtener el número de zona (1, 2 o 3)
        if len(prefix) > 2 and prefix[2] == zone_number:
            return True, ""
    
    return False, f"El prefijo del indicativo no coincide con la zona {zona}"

def detect_inconsistent_data(report):
    """Detecta datos inconsistentes en un reporte"""
    warnings = []
    
    # Verificar consistencia entre indicativo y zona
    if 'call_sign' in report and 'zona' in report:
        is_valid, message = validate_call_sign_zone_consistency(report['call_sign'], report['zona'])
        if not is_valid:
            warnings.append(message)
    
    return warnings

def get_radioaficionado_info(indicativo):
    """
    Busca la información de un radioaficionado por su indicativo.
    Devuelve un diccionario con los datos o None si no se encuentra.
    """
    if not indicativo:
        return None
        
    # Buscar en la tabla de radioexperimentadores
    return db.get_radioexperimentador(indicativo.upper())

def calcular_zona_indicativo(indicativo):
    """
    Calcula la zona a partir de un indicativo usando la función validar_call_sign.
    """
    if not indicativo:
        return "Dato no encontrado, ingresar manualmente"
        
    # Usar la función validar_call_sign para determinar el tipo de indicativo
    result = validar_call_sign(indicativo)
    
    if not result["indicativo"]:
        return "Indicativo inválido"
        
    if result["Zona"] in ["XE1", "XE2", "XE3"]:
        return result["Zona"]  # Retorna XE1, XE2 o XE3
    elif result["Zona"] == "Especial":
        # Para indicativos especiales, intentamos extraer la zona
        indicativo = indicativo.upper()
        # Buscar un número de zona (1-3) en el indicativo
        match = re.search(r'[1-3]', indicativo)
        if match:
            zona_num = match.group(0)
            return f"XE{zona_num}"
        return "Especial"
    else:  # Extranjera
        return "Extranjera"

def obtener_datos_para_reporte(indicativo, sistema_preferido):
    """
    Obtiene todos los datos necesarios para un reporte a partir de un indicativo.
    """
    # Buscar información del radioaficionado
    radioaficionado = get_radioaficionado_info(indicativo)
    
    # Calcular la zona
    zona = calcular_zona_indicativo(indicativo)
    
    # Obtener información del sistema
    sistema_info = db.get_sistema_info(sistema_preferido) if sistema_preferido else {}
    
    # Construir el diccionario de datos
    datos = {
        'indicativo': indicativo.upper(),
        'nombre_operador': radioaficionado.get('nombre_completo', 'Dato no encontrado, ingresar manualmente') if radioaficionado else 'Dato no encontrado, ingresar manualmente',
        'estado': radioaficionado.get('estado', 'Dato no encontrado, ingresar manualmente') if radioaficionado else 'Dato no encontrado, ingresar manualmente',
        'ciudad': radioaficionado.get('municipio', 'Dato no encontrado, ingresar manualmente') if radioaficionado else 'Dato no encontrado, ingresar manualmente',
        'zona': zona,
        'sistema': sistema_preferido,
        'senal': '59',  # Valor por defecto para RST
        'frecuencia': sistema_info.get('frecuencia', '') if sistema_info else '',
        'modo': sistema_info.get('modo', '') if sistema_info else '',
        'potencia': sistema_info.get('potencia', '') if sistema_info else ''
    }
    
    return datos

def map_qth_to_estado(qth):
    """Mapea un QTH a un estado de México desde la base de datos"""
    if not qth:
        return None
        
    # Limpiar y estandarizar el QTH
    qth_clean = qth.upper().strip()
    
    # Buscar coincidencias exactas primero
    estados = db.get_estados()
    for abbr, nombre in estados.items():
        if qth_clean == abbr or qth_clean == nombre.upper():
            return abbr
    
    # Búsqueda por similitud (puedes ajustar según sea necesario)
    for abbr, nombre in estados.items():
        if qth_clean in nombre.upper() or nombre.upper() in qth_clean:
            return abbr
    
        pass
    
    return qth  # Si no se encuentra, devolver el valor original
