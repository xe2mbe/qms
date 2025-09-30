import re
import time
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
            "Zona": "Especial"
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

# ============================================
# Funciones para la Gestión de Estaciones
# ============================================

def get_estaciones():
    """
    Obtiene todas las estaciones de la base de datos.
    Retorna una lista de diccionarios con los datos de cada estación.
    """
    cursor = db.get_connection().cursor()
    cursor.execute('''
        SELECT id, qrz, descripcion, is_active, 
               strftime('%Y-%m-%d %H:%M', created_at) as created_at
        FROM stations
        ORDER BY qrz
    ''')
    
    # Convertir cada fila a un diccionario
    return [dict(row) for row in cursor.fetchall()]

def get_estacion_por_id(estacion_id):
    """
    Obtiene una estación por su ID.
    Retorna un diccionario con los datos de la estación o None si no se encuentra.
    """
    cursor = db.get_connection().cursor()
    cursor.execute('''
        SELECT id, qrz, descripcion, is_active, 
               strftime('%Y-%m-%d %H:%M', created_at) as created_at
        FROM stations
        WHERE id = ?
    ''', (estacion_id,))
    
    row = cursor.fetchone()
    return dict(row) if row else None

def crear_estacion(qrz, descripcion, is_active=True):
    """
    Crea una nueva estación en la base de datos.
    Lanza sqlite3.IntegrityError si ya existe una estación con el mismo QRZ.
    """
    cursor = db.get_connection().cursor()
    cursor.execute('''
        INSERT INTO stations (qrz, descripcion, is_active)
        VALUES (?, ?, ?)
    ''', (qrz.upper(), descripcion.strip(), 1 if is_active else 0))
    db.get_connection().commit()
    return cursor.lastrowid

def actualizar_estacion(estacion_id, descripcion, is_active):
    """
    Actualiza los datos de una estación existente.
    Retorna True si se actualizó correctamente, False si la estación no existe.
    La fecha de actualización se guarda en UTC-6 (hora de la Ciudad de México).
    """
    # Obtener la hora actual en UTC-6
    tz = pytz.timezone('America/Mexico_City')
    now_utc6 = datetime.now(pytz.utc).astimezone(tz)
    
    cursor = db.get_connection().cursor()
    cursor.execute('''
        UPDATE stations 
        SET descripcion = ?, is_active = ?, updated_at = ?
        WHERE id = ?
    ''', (descripcion.strip(), 1 if is_active else 0, now_utc6.strftime('%Y-%m-%d %H:%M:%S'), estacion_id))
    
    db.get_connection().commit()
    return cursor.rowcount > 0

def eliminar_estacion(estacion_id):
    """
    Elimina una estación de la base de datos.
    Retorna True si se eliminó correctamente, False si la estación no existe.
    """
    cursor = db.get_connection().cursor()
    cursor.execute('DELETE FROM stations WHERE id = ?', (estacion_id,))
    db.get_connection().commit()
    return cursor.rowcount > 0

def show_gestion_estaciones():
    """Muestra la gestión de estaciones con pestañas"""
    import streamlit as st
    
    # Determinar qué pestaña mostrar por defecto
    tab_titles = ["📋 Lista de Estaciones", "➕ Agregar Estación"]
    
    # Inicializar el estado de la pestaña activa si no existe
    if 'active_tab' not in st.session_state:
        st.session_state.active_tab = 0  # Por defecto mostrar la lista de estaciones
    
    # Si estamos editando, forzar la pestaña de lista
    if 'editar_estacion_id' in st.session_state and st.session_state['editar_estacion_id'] is not None:
        st.session_state.active_tab = 0
    
    # Crear las pestañas
    tab1, tab2 = st.tabs(tab_titles)
    
    with tab1:
        _show_lista_estaciones()
        
        # Mostrar el formulario de edición debajo de la lista si estamos editando
        if 'editar_estacion_id' in st.session_state and st.session_state['editar_estacion_id'] is not None:
            st.markdown("---")
            st.subheader("✏️ Editar Estación")
            _show_crear_estacion()
    
    with tab2:
        # Si estamos en la pestaña de agregar, limpiar el ID de edición
        if 'editar_estacion_id' in st.session_state:
            st.session_state['editar_estacion_id'] = None
        _show_crear_estacion()

def _show_crear_estacion():
    """Muestra el formulario para crear o editar una estación"""
    import streamlit as st
    import time
    import sqlite3
    
    # Inicializar variables
    estacion = None
    es_edicion = 'editar_estacion_id' in st.session_state and st.session_state['editar_estacion_id'] is not None
    
    if es_edicion:
        estacion_id = st.session_state['editar_estacion_id']
        
        # Cargar datos de la estación
        estacion = get_estacion_por_id(estacion_id)
        
        # Verificar si la estación existe
        if not estacion:
            st.error("La estación solicitada no existe.")
            time.sleep(2)
            del st.session_state['editar_estacion_id']
            st.rerun()
            return
            
        # Mostrar encabezado de edición
        st.header(f"✏️ Editar Estación: {estacion['qrz']}")
        
        # Botón para volver a la lista - con key único
        if st.button("⬅️ Volver a la lista sin guardar", 
                    key=f"btn_volver_editar_{estacion_id}",
                    use_container_width=True,
                    help="Volver a la lista sin guardar cambios"):
            del st.session_state['editar_estacion_id']
            st.rerun()
    else:
        # Modo creación de nueva estación
        estacion_id = None
        st.header("➕ Agregar Nueva Estación")
        
        # Botón para volver a la lista - con key único para creación
        if st.button("⬅️ Volver a la lista sin guardar", 
                    key="btn_volver_crear",
                    use_container_width=True,
                    help="Volver a la lista sin guardar cambios"):
            if 'editar_estacion_id' in st.session_state:
                del st.session_state['editar_estacion_id']
            st.rerun()
    
    # Configurar claves únicas para el formulario
    form_key = f"form_estacion_edit_{estacion_id}" if es_edicion else "form_estacion_new"
    
    with st.form(key=form_key, clear_on_submit=not es_edicion):
        # Configurar claves únicas para los campos
        qrz_key = f"qrz_{estacion_id}" if es_edicion else "qrz_new"
        desc_key = f"desc_{estacion_id}" if es_edicion else "desc_new"
        active_key = f"active_{estacion_id}" if es_edicion else "active_new"
        
        # Campo QRZ (solo lectura en modo edición)
        qrz = st.text_input("QRZ (Indicativo):", 
                           value=estacion['qrz'] if estacion else "",
                           max_chars=10,
                           disabled=es_edicion,
                           key=qrz_key,
                           help="Indicativo de la estación (máx. 10 caracteres)")
        
        descripcion = st.text_area("Descripción:", 
                                 value=estacion['descripcion'] if estacion else "",
                                 max_chars=200,
                                 key=desc_key,
                                 help="Descripción o notas sobre la estación (opcional)")
        
        is_active = st.checkbox("Activa", 
                              value=estacion.get('is_active', True) if estacion else True,
                              key=active_key,
                              help="¿La estación está activa y disponible para su uso?")
        
        # Botones de acción
        col1, col2 = st.columns(2)
        with col1:
            submit_button = st.form_submit_button("💾 Guardar")
        with col2:
            cancel_button = st.form_submit_button("❌ Cancelar")
        
        if submit_button:
            if not qrz.strip():
                st.error("El campo QRZ es obligatorio.")
            else:
                try:
                    if es_edicion and estacion:
                        # Actualizar estación existente
                        actualizar_estacion(estacion_id, descripcion, is_active)
                        mensaje = "✅ Estación actualizada correctamente."
                    else:
                        # Crear nueva estación
                        crear_estacion(qrz.strip().upper(), descripcion.strip(), is_active)
                        mensaje = "✅ Estación creada correctamente."
                    
                    st.success(mensaje)
                    time.sleep(1)
                    if 'editar_estacion_id' in st.session_state:
                        del st.session_state['editar_estacion_id']
                    st.rerun()
                    
                except sqlite3.IntegrityError as e:
                    st.error("❌ Error: Ya existe una estación con ese QRZ.")
                    print(f"[ERROR] Error de integridad: {e}")
                except Exception as e:
                    st.error(f"❌ Error al guardar la estación: {str(e)}")
                    print(f"[ERROR] Error inesperado: {e}")
        
        if cancel_button:
            if 'editar_estacion_id' in st.session_state:
                del st.session_state['editar_estacion_id']
            st.rerun()

def _show_lista_estaciones():
    """Muestra la lista de estaciones con opciones de búsqueda y acciones"""
    import streamlit as st
    
    st.header("📋 Lista de Estaciones")
    
    # Barra de búsqueda
    busqueda = st.text_input("🔍 Buscar estación por QRZ o descripción:", "")
    
    # Filtro de estado
    estado_filtro = st.radio("Estado:", ["Todas", "Activas", "Inactivas"], horizontal=True)
    
    # Obtener estaciones con filtros
    with st.spinner("Cargando estaciones..."):
        estaciones = get_estaciones()
        
        # Aplicar filtros
        if busqueda:
            busqueda = busqueda.lower()
            estaciones = [e for e in estaciones 
                         if busqueda in e['qrz'].lower() or 
                         (e['descripcion'] and busqueda in e['descripcion'].lower())]
            
        if estado_filtro != "Todas":
            activo = estado_filtro == "Activas"
            estaciones = [e for e in estaciones if e['is_active'] == activo]
    
    # Mostrar lista de estaciones con expanders
    if estaciones:
        for estacion in estaciones:
            # Determinar el ícono de estado
            estado_icono = "✅" if estacion['is_active'] else "❌"
            estado_texto = "Activa" if estacion['is_active'] else "Inactiva"
            
            # Mostrar cada estación en un contenedor expandible
            with st.expander(f"📻 {estacion['qrz']} - {estacion.get('descripcion', 'Sin descripción')} ({estado_icono} {estado_texto})", 
                          expanded=st.session_state.get(f"editing_estacion_{estacion['id']}", False)):
                
                # Columnas para los botones de acción
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.write(f"**QRZ:** {estacion['qrz']}")
                    st.write(f"**Descripción:** {estacion.get('descripcion', 'Sin descripción')}")
                    st.write(f"**Estado:** {estado_icono} {estado_texto}")
                    st.write(f"**Creada:** {estacion.get('created_at', 'N/A')}")
                
                with col2:
                    # Botón para editar estación
                    if st.button(f"✏️ Editar", 
                              key=f"edit_{estacion['id']}",
                              use_container_width=True):
                        # Alternar el estado de edición
                        current_state = st.session_state.get(f"editing_estacion_{estacion['id']}", False)
                        st.session_state[f"editing_estacion_{estacion['id']}"] = not current_state
                        st.rerun()
                    
                    # Botón para eliminar estación
                    if st.button(f"🗑️ Eliminar",
                              key=f"del_{estacion['id']}",
                              use_container_width=True):
                        if _eliminar_estacion(estacion['id']):
                            st.success(f"Estación {estacion['qrz']} eliminada correctamente")
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("Error al eliminar la estación")
                
                # Mostrar formulario de edición si está activo
                if st.session_state.get(f"editing_estacion_{estacion['id']}", False):
                    st.markdown("---")
                    st.subheader("✏️ Editar Estación")
                    
                    # Obtener datos actuales de la estación
                    estacion_actual = get_estacion_por_id(estacion['id'])
                    
                    with st.form(f"edit_estacion_{estacion['id']}"):
                        # Campos del formulario
                        nuevo_qrz = st.text_input("QRZ:", value=estacion_actual['qrz'])
                        nueva_descripcion = st.text_area("Descripción:", value=estacion_actual.get('descripcion', ''))
                        activa = st.toggle("Estación activa", value=bool(estacion_actual.get('is_active', True)))
                        
                        # Botones de acción
                        col_save, col_cancel = st.columns(2)
                        
                        with col_save:
                            if st.form_submit_button("💾 Guardar Cambios"):
                                if actualizar_estacion(
                                    estacion_id=estacion_actual['id'],
                                    descripcion=nueva_descripcion,
                                    is_active=activa
                                ):
                                    st.success("✅ Estación actualizada correctamente")
                                    # Cerrar el formulario después de guardar
                                    st.session_state[f"editing_estacion_{estacion['id']}"] = False
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("❌ Error al actualizar la estación")
                        
                        with col_cancel:
                            if st.form_submit_button("❌ Cancelar"):
                                st.session_state[f"editing_estacion_{estacion['id']}"] = False
                                st.rerun()
    else:
        st.info("No se encontraron estaciones con los filtros actuales.")
