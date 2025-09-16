import re
from datetime import datetime
import pytz

def is_mexican_call_sign(call_sign):
    """
    Determina si un indicativo es mexicano
    Indicativos mexicanos: XE, XF, 4A, 6D
    """
    if not call_sign:
        return False
    
    # Patrón para indicativos mexicanos
    mexican_pattern = r'^(XE|XF|4A|6D)[0-9][A-Z]{1,3}$'
    return bool(re.match(mexican_pattern, call_sign.upper()))

def validate_call_sign(call_sign):
    """
    Valida el formato del indicativo de llamada
    Acepta tanto indicativos mexicanos como extranjeros
    """
    if not call_sign:
        return False, "El indicativo no puede estar vacío"
    
    # Patrón básico para indicativos (más permisivo para extranjeros)
    # Formato general: 1-3 letras + 1 número + 1-4 letras/números
    general_pattern = r'^[A-Z]{1,3}[0-9][A-Z0-9]{1,4}$'
    
    if re.match(general_pattern, call_sign.upper()):
        return True, ""
    else:
        return False, "Formato de indicativo inválido. Ejemplo: XE1ABC, W1ABC, JA1ABC"

def validate_call_sign_zone_consistency(call_sign, zona):
    """
    Valida que el indicativo sea consistente con la zona seleccionada
    """
    if not call_sign or not zona:
        return True, ""  # Si falta información, no validar aquí
    
    is_mexican = is_mexican_call_sign(call_sign)
    mexican_zones = ['XE1', 'XE2', 'XE3']
    
    if is_mexican and zona == 'Extranjera':
        return False, "El indicativo mexicano debe usar zona XE1, XE2 o XE3, no 'Extranjera'"
    
    if not is_mexican and zona in mexican_zones:
        return False, "Las estaciones extranjeras deben usar la zona 'Extranjera'"
    
    return True, ""

def detect_inconsistent_data(call_sign, estado, zona):
    """
    Detecta inconsistencias que requieren confirmación del usuario
    Retorna: (needs_confirmation, warning_message)
    """
    if not call_sign or not estado or not zona:
        return False, ""
    
    is_mexican = is_mexican_call_sign(call_sign)
    mexican_zones = ['XE1', 'XE2', 'XE3']
    
    # Caso: Indicativo mexicano + Estado "Extranjera" + Zona mexicana
    if is_mexican and estado.upper() == 'EXTRANJERA' and zona in mexican_zones:
        return True, f"⚠️ **Inconsistencia detectada:**\n\n" \
                    f"• **Indicativo:** {call_sign} (Mexicano)\n" \
                    f"• **Estado:** {estado}\n" \
                    f"• **Zona:** {zona}\n\n" \
                    f"**Recomendación:** Si es una estación extranjera, selecciona zona 'Extranjera'. " \
                    f"Si es una estación mexicana, selecciona un estado mexicano.\n\n" \
                    f"¿Deseas continuar con estos datos?"
    
    # Caso: Indicativo extranjero + Estado mexicano + Zona extranjera
    if not is_mexican and estado.upper() != 'EXTRANJERA' and zona == 'Extranjera':
        return True, f"⚠️ **Inconsistencia detectada:**\n\n" \
                    f"• **Indicativo:** {call_sign} (Extranjero)\n" \
                    f"• **Estado:** {estado}\n" \
                    f"• **Zona:** {zona}\n\n" \
                    f"**Recomendación:** Si es una estación extranjera, selecciona estado 'Extranjera'. " \
                    f"Si es una estación mexicana, verifica el indicativo.\n\n" \
                    f"¿Deseas continuar con estos datos?"
    
    return False, ""

def validate_qth(qth):
    """Valida el formato del QTH (ubicación) - DEPRECATED, usar validate_ciudad"""
    if not qth or len(qth.strip()) < 2:
        return False, "El QTH debe tener al menos 2 caracteres"
    
    if len(qth) > 50:
        return False, "El QTH no puede exceder 50 caracteres"
    
    return True, ""

def validate_operator_name(name):
    """Valida el nombre del operador"""
    if not name or len(name.strip()) < 2:
        return False, "El nombre debe tener al menos 2 caracteres"
    
    if len(name) > 100:
        return False, "El nombre no puede exceder 100 caracteres"
    
    # Solo letras, espacios y algunos caracteres especiales
    pattern = r'^[A-Za-zÀ-ÿ\s\-\.]+$'
    if not re.match(pattern, name):
        return False, "El nombre solo puede contener letras, espacios, guiones y puntos"
    
    return True, ""

def validate_signal_report(signal):
    """Valida el reporte de señal"""
    if not signal:
        return False, "El reporte de señal es obligatorio"
    
    valid_signals = [
        'buena', 'regular', 'mala', 'excelente', 'fuerte', 'débil',
        '5', '4', '3', '2', '1', '59', '58', '57', '56', '55'
    ]
    
    if signal.lower() in valid_signals or any(vs in signal.lower() for vs in valid_signals):
        return True, ""
    else:
        return False, "Reporte de señal inválido. Use: Buena/Regular/Mala o escala RST"

def format_call_sign(call_sign):
    """Formatea el indicativo en mayúsculas"""
    return call_sign.upper().strip() if call_sign else ""

def format_qth(qth):
    """Formatea el QTH en mayúsculas"""
    return qth.upper().strip() if qth else ""

def format_name(name):
    """Formatea el nombre con capitalización apropiada"""
    return name.title().strip() if name else ""

def get_mexican_states():
    """Retorna lista de estados mexicanos con sus códigos"""
    return {
        'AG': 'Aguascalientes',
        'BC': 'Baja California',
        'BS': 'Baja California Sur',
        'CM': 'Campeche',
        'CS': 'Chiapas',
        'CH': 'Chihuahua',
        'CO': 'Coahuila',
        'CL': 'Colima',
        'DF': 'Ciudad de México',
        'DG': 'Durango',
        'GT': 'Guanajuato',
        'GR': 'Guerrero',
        'HG': 'Hidalgo',
        'JA': 'Jalisco',
        'EM': 'Estado de México',
        'MI': 'Michoacán',
        'MO': 'Morelos',
        'NA': 'Nayarit',
        'NL': 'Nuevo León',
        'OA': 'Oaxaca',
        'PU': 'Puebla',
        'QT': 'Querétaro',
        'QR': 'Quintana Roo',
        'SL': 'San Luis Potosí',
        'SI': 'Sinaloa',
        'SO': 'Sonora',
        'TB': 'Tabasco',
        'TM': 'Tamaulipas',
        'TL': 'Tlaxcala',
        'VE': 'Veracruz',
        'YU': 'Yucatán',
        'ZA': 'Zacatecas'
    }

def get_estados_list():
    """Retorna lista ordenada de estados para dropdown"""
    estados = ['Extranjera']  # Primera opción
    estados.extend(sorted(get_mexican_states().values()))
    return estados

def validate_estado(estado):
    """Valida el estado seleccionado"""
    valid_estados = get_estados_list()
    
    if not estado:
        return False, "El estado es obligatorio"
    
    if estado not in valid_estados:
        return False, f"Estado inválido. Debe ser uno de la lista"
    
    return True, ""

def validate_ciudad(ciudad):
    """Valida el campo ciudad (opcional)"""
    # Ciudad es opcional, permitir vacío
    if not ciudad or len(ciudad.strip()) == 0:
        return True, ""
    
    # Si se proporciona, debe tener al menos 2 caracteres
    if len(ciudad.strip()) < 2:
        return False, "La ciudad debe tener al menos 2 caracteres si se proporciona"
    
    if len(ciudad) > 50:
        return False, "La ciudad no puede exceder 50 caracteres"
    
    return True, ""

def extract_region_from_qth(qth):
    """Extrae la región del QTH basado en los primeros caracteres"""
    if not qth or len(qth) < 2:
        return "XX"
    
    region_code = qth[:2].upper()
    states = get_mexican_states()
    
    if region_code in states:
        return region_code
    else:
        # Intentar encontrar coincidencia parcial
        for code, state in states.items():
            if state.upper().startswith(qth[:3].upper()):
                return code
        return "XX"  # Región desconocida

def format_timestamp(timestamp):
    """Formatea timestamp para mostrar en zona horaria de México"""
    # Zona horaria de México (Centro)
    mexico_tz = pytz.timezone('America/Mexico_City')
    
    if isinstance(timestamp, str):
        try:
            # Parsear timestamp como UTC
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
        except:
            return timestamp
    else:
        dt = timestamp
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
    
    # Convertir a zona horaria de México
    dt_mexico = dt.astimezone(mexico_tz)
    return dt_mexico.strftime("%d/%m/%Y %H:%M:%S")

def get_signal_quality_text(quality_num):
    """Convierte calidad numérica a texto"""
    quality_map = {
        1: "Mala",
        2: "Regular", 
        3: "Buena"
    }
    return quality_map.get(quality_num, "Desconocida")

def validate_zona(zona):
    """Valida la zona seleccionada"""
    valid_zonas = ['XE1', 'XE2', 'XE3', 'Extranjera']
    
    if not zona:
        return False, "La zona es obligatoria"
    
    if zona not in valid_zonas:
        return False, f"Zona inválida. Debe ser: {', '.join(valid_zonas)}"
    
    return True, ""

def validate_sistema(sistema):
    """Valida el sistema seleccionado"""
    valid_sistemas = ['IRLP', 'ASL', 'DMR', 'Fusion', 'D-Star', 'HF', 'Otro']
    
    if not sistema:
        return False, "El sistema es obligatorio"
    
    if sistema not in valid_sistemas:
        return False, f"Sistema inválido. Debe ser: {', '.join(valid_sistemas)}"
    
    return True, ""

def get_zonas():
    """Retorna lista de zonas disponibles"""
    return ['XE1', 'XE2', 'XE3', 'Extranjera']

def get_sistemas():
    """Retorna lista de sistemas disponibles"""
    return ['IRLP', 'ASL', 'DMR', 'Fusion', 'D-Star', 'HF', 'Otro']

def validate_password(password):
    """Valida que la contraseña cumpla con los requisitos de seguridad"""
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres"
    
    if not any(c.isupper() for c in password):
        return False, "La contraseña debe contener al menos una letra mayúscula"
    
    if not any(c.isdigit() for c in password):
        return False, "La contraseña debe contener al menos un número"
    
    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    if not any(c in special_chars for c in password):
        return False, "La contraseña debe contener al menos un carácter especial (!@#$%^&*()_+-=[]{}|;:,.<>?)"
    
    return True, "Contraseña válida"

def validate_all_fields(call_sign, operator_name, estado, ciudad, signal_report, zona, sistema, grid_locator=""):
    """Valida todos los campos del formulario"""
    errors = []
    
    valid, msg = validate_call_sign(call_sign)
    if not valid:
        errors.append(f"Indicativo: {msg}")
    
    valid, msg = validate_operator_name(operator_name)
    if not valid:
        errors.append(f"Nombre: {msg}")
    
    valid, msg = validate_estado(estado)
    if not valid:
        errors.append(f"Estado: {msg}")
    
    valid, msg = validate_ciudad(ciudad)
    if not valid:
        errors.append(f"Ciudad: {msg}")
    
    valid, msg = validate_signal_report(signal_report)
    if not valid:
        errors.append(f"Señal: {msg}")
    
    valid, msg = validate_zona(zona)
    if not valid:
        errors.append(f"Zona: {msg}")
    
    valid, msg = validate_sistema(sistema)
    if not valid:
        errors.append(f"Sistema: {msg}")
    
    # Validar consistencia entre indicativo y zona
    valid, msg = validate_call_sign_zone_consistency(call_sign, zona)
    if not valid:
        errors.append(f"Indicativo/Zona: {msg}")
    
    # Validar Grid Locator (opcional pero si se proporciona debe ser válido)
    if grid_locator and grid_locator.strip():
        from database import FMREDatabase
        db = FMREDatabase()
        is_valid_grid, grid_error = db._validate_grid_locator(grid_locator.strip())
        if not is_valid_grid:
            errors.append(f"Grid Locator: {grid_error}")
    
    return len(errors) == 0, errors

def validate_hf_frequency(frequency):
    """Valida frecuencia HF (1.8-30 MHz)"""
    if not frequency:
        return True, ""  # Opcional para HF
    
    try:
        freq_float = float(frequency)
        if 1.8 <= freq_float <= 30.0:
            return True, ""
        return False, "Frecuencia debe estar entre 1.8-30 MHz"
    except:
        return False, "Frecuencia inválida (usar formato: 14.230)"

def validate_hf_fields(sistema, hf_frequency="", hf_band="", hf_mode="", hf_power=""):
    """Valida campos específicos de HF"""
    errors = []
    
    if sistema == "HF":
        # Validar frecuencia si se proporciona
        if hf_frequency:
            valid, msg = validate_hf_frequency(hf_frequency)
            if not valid:
                errors.append(f"Frecuencia HF: {msg}")
    
    return len(errors) == 0, errors

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import hashlib
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
from typing import Optional

def extract_prefix_from_callsign(call_sign: str) -> Optional[str]:
    """
    Extrae el prefijo de un indicativo mexicano para determinar la zona automáticamente.
    
    Args:
        call_sign: Indicativo completo (ej: XE1ABC, XE3DEF, W1ABC, JA1ABC)
        
    Returns:
        Prefijo extraído (ej: XE1, XE3) o 'FOREIGN' para indicativos extranjeros
    """
    if not call_sign:
        return None
    
    call_sign = call_sign.upper().strip()
    
    # Patrones para indicativos mexicanos
    mexican_patterns = [
        r'^(XE[1-3])[A-Z]*$',  # XE1, XE2, XE3 seguido de letras
        r'^(XF[1-3])[A-Z]*$',  # XF1, XF2, XF3 seguido de letras  
        r'^(4A[1-3])[A-Z]*$',  # 4A1, 4A2, 4A3 seguido de letras
        r'^(6D[1-3])[A-Z]*$',  # 6D1, 6D2, 6D3 seguido de letras
    ]
    
    # Verificar si es mexicano
    for pattern in mexican_patterns:
        match = re.match(pattern, call_sign)
        if match:
            return match.group(1)
    
    # Si no es mexicano pero parece un indicativo válido, es extranjero
    # Patrones básicos para indicativos internacionales
    foreign_patterns = [
        r'^[A-Z]{1,2}[0-9][A-Z]{1,4}$',  # Formato típico: W1ABC, JA1ABC, etc.
        r'^[0-9][A-Z]{1,2}[0-9][A-Z]{1,4}$',  # Formato con número inicial: 9A1ABC
        r'^[A-Z]{1,2}[0-9]{1,2}[A-Z]{1,4}$',  # Variaciones con más números
    ]
    
    for pattern in foreign_patterns:
        if re.match(pattern, call_sign):
            return 'FOREIGN'
    
    return None

def get_zone_from_prefix(prefix: str) -> Optional[str]:
    """
    Obtiene la zona correspondiente al prefijo mexicano o extranjero.
    
    Args:
        prefix: Prefijo extraído (ej: XE1, XE3, 'FOREIGN')
        
    Returns:
        Zona correspondiente o None si no se encuentra
    """
    if not prefix:
        return None
    
    # Mapeo de prefijos a zonas
    prefix_to_zone = {
        'XE1': 'XE1', 'XF1': 'XE1', '4A1': 'XE1', '6D1': 'XE1',
        'XE2': 'XE2', 'XF2': 'XE2', '4A2': 'XE2', '6D2': 'XE2', 
        'XE3': 'XE3', 'XF3': 'XE3', '4A3': 'XE3', '6D3': 'XE3',
        'FOREIGN': 'Extranjera'  # Para indicativos extranjeros
    }
    
    return prefix_to_zone.get(prefix.upper())