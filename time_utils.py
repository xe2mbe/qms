import pytz
from datetime import datetime
from typing import Optional, Union, Any

def get_cdmx_timezone() -> pytz.timezone:
    """
    Devuelve el objeto timezone para la Ciudad de México (CDMX).
    
    Returns:
        pytz.timezone: Zona horaria de la Ciudad de México
    """
    return pytz.timezone('America/Mexico_City')

def get_current_cdmx_time() -> datetime:
    """
    Devuelve la fecha y hora actual en la zona horaria de CDMX.
    
    Returns:
        datetime: Fecha y hora actual en CDMX con timezone configurado
    """
    return datetime.now(get_cdmx_timezone())

def convert_utc_to_cdmx(utc_dt: Optional[Union[datetime, str]]) -> Optional[datetime]:
    """
    Convierte una fecha/hora UTC a la zona horaria de CDMX.
    
    Args:
        utc_dt: Fecha/hora en UTC (puede ser datetime, string o None)
        
    Returns:
        datetime: Fecha/hora en zona horaria de CDMX o None si no se pudo convertir
    """
    if not utc_dt:
        return None
        
    try:
        cdmx_zone = get_cdmx_timezone()
        
        # Si es un string, convertirlo a datetime
        if isinstance(utc_dt, str):
            # Intentar diferentes formatos de fecha
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    utc_dt = datetime.strptime(utc_dt.split('.')[0], fmt)
                    # Asumir que la fecha está en UTC
                    utc_dt = pytz.UTC.localize(utc_dt)
                    break
                except (ValueError, AttributeError):
                    continue
            else:
                return None  # Si no coincide con ningún formato, devolver None
        
        # Si no tiene zona horaria, asumir UTC
        if utc_dt.tzinfo is None:
            utc_dt = pytz.UTC.localize(utc_dt)
        
        # Convertir a CDMX
        return utc_dt.astimezone(cdmx_zone)
        
    except Exception as e:
        print(f"Error al convertir fecha a CDMX: {e}")
        return None

def format_datetime(dt: Any, include_time: bool = True) -> str:
    """
    Formatea una fecha/hora a un string legible en CDMX.
    
    Args:
        dt: Fecha/hora a formatear (puede ser datetime, string o None)
        include_time: Si es True, incluye la hora en el formato
        
    Returns:
        str: Fecha/hora formateada o 'N/A' si no se pudo formatear
    """
    if not dt:
        return 'N/A'
        
    try:
        # Si es un string, intentar convertirlo a datetime
        if isinstance(dt, str):
            dt = convert_utc_to_cdmx(dt)
            if dt is None:
                return 'N/A'
                
        # Si ya es datetime, asegurarse de que esté en CDMX
        if dt.tzinfo is None:
            dt = convert_utc_to_cdmx(dt)
            if dt is None:
                return 'N/A'
        
        # Asegurarse de que la fecha esté en la zona horaria de CDMX
        if dt.tzinfo != get_cdmx_timezone():
            dt = dt.astimezone(get_cdmx_timezone())
            
        # Formatear según se solicite
        if include_time:
            return dt.strftime('%d/%m/%Y %H:%M:%S %Z')
        else:
            return dt.strftime('%d/%m/%Y')
            
    except Exception as e:
        print(f"Error al formatear fecha: {e}")
        return 'N/A'
