import pytz
from datetime import datetime

def get_cdmx_timezone():
    """Devuelve el objeto timezone para la Ciudad de México"""
    return pytz.timezone('America/Mexico_City')

def convert_utc_to_cdmx(utc_dt):
    """Convierte una fecha/hora UTC a la zona horaria de CDMX"""
    if not utc_dt:
        return None
        
    try:
        cdmx_zone = get_cdmx_timezone()
        
        # Si es un string, convertirlo a datetime
        if isinstance(utc_dt, str):
            # Intentar diferentes formatos de fecha
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    utc_dt = datetime.strptime(utc_dt, fmt)
                    # Asumir que la fecha está en UTC
                    utc_dt = pytz.UTC.localize(utc_dt)
                    break
                except ValueError:
                    continue
            else:
                return utc_dt  # Si no coincide con ningún formato, devolver el original
        
        # Si no tiene zona horaria, asumir UTC
        if utc_dt.tzinfo is None:
            utc_dt = pytz.UTC.localize(utc_dt)
        
        # Convertir a CDMX
        return utc_dt.astimezone(cdmx_zone)
    except Exception as e:
        print(f"Error al convertir fecha a CDMX: {e}")
        return utc_dt

def format_datetime(dt, include_time=True):
    """Formatea una fecha/hora a un string legible en CDMX"""
    if not dt:
        return 'N/A'
        
    try:
        # Si es un string, intentar convertirlo a datetime
        if isinstance(dt, str):
            dt = convert_utc_to_cdmx(dt)
            if dt is None:
                return 'N/A'
        
        # Formatear la fecha y hora de manera legible
        if include_time:
            return dt.strftime("%d/%m/%Y %I:%M %p")
        return dt.strftime("%d/%m/%Y")
    except Exception as e:
        print(f"Error al formatear fecha: {e}")
        return str(dt)
