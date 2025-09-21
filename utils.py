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

def validate_call_sign(call_sign):
    """Valida que el indicativo tenga un formato válido"""
    if not call_sign or not call_sign.strip():
        return False, "El indicativo no puede estar vacío"
    
    # Expresión regular para validar indicativos de llamada
    pattern = r'^[A-Z0-9]{3,7}(/[A-Z0-9]{1,3})?$'
    if not re.match(pattern, call_sign.upper()):
        return False, "Formato de indicativo inválido"
    
    return True, ""

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

def map_qth_to_estado(qth):
    """Mapea un QTH a un estado de México desde la base de datos"""
    if not qth:
        return ""
    
    qth_upper = qth.upper().strip()
    estados = get_mexican_states()
    
    # Buscar coincidencia exacta por abreviatura o nombre
    for abbr, estado in estados.items():
        if qth_upper == abbr or qth_upper == estado.upper():
            return estado
    
    # Búsqueda parcial
    for abbr, estado in estados.items():
        if abbr in qth_upper or estado.upper() in qth_upper:
            return estado
    
    # Si no se encuentra, verificar en la base de datos
    try:
        # Intentar obtener el estado por abreviatura
        estado = db.get_estado_by_abreviatura(qth_upper)
        if estado:
            return estado
    except:
        pass
    
    return qth  # Si no se encuentra, devolver el valor original
