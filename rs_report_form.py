import streamlit as st
import pandas as pd
import json
from database import FMREDatabase
from datetime import datetime
from utils import validar_call_sign, get_zonas

def show_redes_sociales_form():
    """Muestra el formulario para reportes de redes sociales"""
    st.title("📱 Reporte de Redes Sociales")
    
    # Inicializar la base de datos
    db = FMREDatabase()
    
    # Obtener la lista de plataformas (activas e inactivas)
    plataformas = db.get_rs_entries(active_only=True)
    
    # Mostrar información de depuración
    st.sidebar.write("=== Depuración de plataformas ===")
    st.sidebar.write(f"Total de plataformas encontradas: {len(plataformas)}")
    for i, p in enumerate(plataformas, 1):
        st.sidebar.write(f"{i}. {p.get('plataforma', 'Sin plataforma')} - {p.get('nombre', 'Sin nombre')} (Activo: {bool(p.get('is_active', False))})")
    
    # Crear opciones para el selectbox
    plataforma_options = [""]  # Opción vacía por defecto
    plataforma_map = {}
    
    # Cargar las plataformas desde la base de datos
    for p in plataformas:
        # Usar solo el nombre de la plataforma como valor mostrado
        display_name = p.get('plataforma', '')
        # Agregar el nombre del grupo si existe
        if p.get('nombre'):
            display_name = f"{display_name} - {p['nombre']}"
        
        if display_name:  # Solo agregar si hay un nombre para mostrar
            plataforma_options.append(display_name)
            plataforma_map[display_name] = p.get('id')
    
    # Inicializar el estado del expander si no existe
    if 'parametros_expanded' not in st.session_state:
        st.session_state.parametros_expanded = True
    
    # Inicializar variables de sesión si no existen
    if 'plataforma_seleccionada' not in st.session_state:
        st.session_state.plataforma_seleccionada = ""
    if 'contenido' not in st.session_state:
        st.session_state.contenido = ""
    if 'fecha_reporte' not in st.session_state:
        st.session_state.fecha_reporte = datetime.now().date()
    if 'num_registros' not in st.session_state:
        st.session_state.num_registros = 1
    
    # Crear el formulario principal
    with st.form(key='reporte_form'):
        # Sección de parámetros del reporte
        with st.expander("📋 Información del Reporte", expanded=st.session_state.parametros_expanded):
            # Primera sección: Parámetros del reporte
            col1, col2 = st.columns(2)
            
            with col1:
                st.session_state.plataforma_seleccionada = st.selectbox(
                    "Plataforma de Red Social",
                    options=plataforma_options,
                    help="Selecciona la plataforma donde se realizó el reporte",
                    key='plataforma_selectbox'
                )
                
            with col2:
                st.session_state.fecha_reporte = st.date_input(
                    "Fecha del Reporte",
                    value=st.session_state.fecha_reporte,
                    format="DD/MM/YYYY",
                    key='fecha_reporte_input',
                    help="Selecciona la fecha del reporte"
                )
            
            # Detalles del reporte
            st.session_state.contenido = st.text_area(
                "Contenido del reporte", 
                value=st.session_state.contenido,
                placeholder="Ingresa el contenido del reporte...",
                height=100,
                key='contenido_textarea'
            )
            
            # Slider para seleccionar cantidad de registros
            st.session_state.num_registros = st.slider(
                "Número de registros a generar", 
                min_value=1, 
                max_value=100, 
                value=st.session_state.num_registros,
                help="Selecciona cuántos registros de estaciones deseas capturar",
                key='num_registros_slider'
            )
            
            # Botón para guardar parámetros
            if st.form_submit_button("💾 Guardar Parámetros"):
                if not st.session_state.plataforma_seleccionada:
                    st.error("Por favor selecciona una plataforma")
                else:
                    # Cerrar el expander
                    st.session_state.parametros_expanded = False
                    st.rerun()  # Actualizar la interfaz
        
        # Mostrar mensaje de éxito si los parámetros están guardados
        if not st.session_state.parametros_expanded and st.session_state.plataforma_seleccionada:
            st.success(f"✅ Parámetros guardados. Se generarán {st.session_state.num_registros} pre-registros de estaciones.")
        
        # Segunda sección: Métricas e Interacción (solo mostrar si los parámetros están guardados)
        if not st.session_state.parametros_expanded and st.session_state.plataforma_seleccionada:
            st.markdown("---")
            st.markdown("### Métricas de Interacción")
            
            # Crear columnas para las métricas
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                me_gusta = st.number_input("Me gusta", min_value=0, value=0, key='me_gusta')
            with col2:
                comentarios = st.number_input("Comentarios", min_value=0, value=0, key='comentarios')
            with col3:
                compartidos = st.number_input("Compartidos", min_value=0, value=0, key='compartidos')
            with col4:
                reproducciones = st.number_input("Reproducciones", min_value=0, value=0, key='reproducciones')
            
            # Tercera sección: Pre-Registros de Estaciones
            st.markdown("### Pre-Registros de Estaciones")
            
            # Inicializar el estado del panel de captura si no existe
            if 'mostrar_panel_captura' not in st.session_state:
                st.session_state.mostrar_panel_captura = False
            
            # Lista para almacenar los datos de los registros
            registros = []
            
            # Mostrar solo el campo de indicativo inicialmente
            if not st.session_state.mostrar_panel_captura:
                st.markdown("Ingrese los indicativos de las estaciones y haga clic en 'Buscar y Guardar' para continuar.")
                
                # Mostrar la plataforma seleccionada
                st.markdown(f"**Plataforma seleccionada:** {st.session_state.plataforma_seleccionada}")
                st.markdown("Ingrese los indicativos de las estaciones y haga clic en 'Buscar y Guardar' para continuar.")
                
                # Inicializar el estado para los resultados de búsqueda
                if 'resultados_busqueda' not in st.session_state:
                    st.session_state.resultados_busqueda = []
                
                # Mostrar cada indicativo en su propia fila
                st.markdown("#### Ingrese los indicativos de las estaciones")
                for i in range(st.session_state.num_registros):
                    # Crear una fila para cada indicativo
                    with st.container():
                        indicativo = st.text_input(
                            f"Indicativo {i+1}", 
                            key=f"indicativo_{i}",
                            help="Ingresa el indicativo de la estación",
                            placeholder=f"XE1ABC"
                        )
                
                # Botón de búsqueda
                buscar_guardar = st.form_submit_button("🔍 Buscar y Pre-Registrar")
                
                if buscar_guardar:
                    st.session_state.resultados_busqueda = []
                    indicativos = []
                    
                    for i in range(st.session_state.num_registros):
                        indicativo = st.session_state.get(f"indicativo_{i}", "").strip()
                        if indicativo:
                            # Buscar datos en la base de datos
                            db = FMREDatabase()
                            
                            # Buscar primero en reportes
                            reporte = db.get_ultimo_reporte_por_indicativo(indicativo.upper())
                            
                            # Debug: Mostrar información en la terminal
                            print("\n" + "="*50)
                            print(f"BUSCANDO INDICATIVO: {indicativo.upper()}")
                            print("-"*50)
                            
                            if reporte:
                                # Debug: Mostrar datos encontrados en reportes
                                print("ENCONTRADO EN REPORTES:")
                                print(f"- Operador: {reporte.get('nombre', 'No disponible')}")
                                print(f"- Estado: {reporte.get('estado', 'No disponible')}")
                                print(f"- Ciudad: {reporte.get('ciudad', 'No disponible')}")
                                print(f"- Zona: {reporte.get('zona', 'No disponible')}")
                                
                                # Si se encuentra en reportes, usar esos datos
                                datos = {
                                    'indicativo': indicativo.upper(),
                                    'operador': reporte.get('nombre', ''),
                                    'estado': reporte.get('estado', ''),
                                    'ciudad': reporte.get('ciudad', ''),
                                    'zona': reporte.get('zona', ''),
                                    'fuente': 'Reporte existente',
                                    'fecha_consulta': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                }
                                print(f"- Fuente: Reportes")
                                print(f"- Fecha de consulta: {datos['fecha_consulta']}")
                            else:
                                # Si no está en reportes, buscar en radioexperimentadores
                                radio = db.get_radioexperimentador_por_indicativo(indicativo.upper())
                                
                                if radio:
                                    # Determinar la zona usando validar_call_sign
                                    validacion = validar_call_sign(indicativo.upper())
                                    zona_detectada = validacion.get('Zona', 'Desconocida')
                                    
                                    # Si la zona es 'Definir' o 'Error', intentar obtener de la base de datos
                                    if zona_detectada in ['Definir', 'Error']:
                                        zonas_dict = dict(get_zonas())
                                        zona_db = radio.get('zona', '')
                                        if zona_db and zona_db in zonas_dict:
                                            zona_detectada = zonas_dict[zona_db]
                                    
                                    # Debug: Mostrar datos encontrados en radioexperimentadores
                                    print("NO ENCONTRADO EN REPORTES, BUSCANDO EN RADIOEXPERIMENTADORES...")
                                    print("ENCONTRADO EN RADIOEXPERIMENTADORES:")
                                    print(f"- Operador: {radio.get('nombre_completo', 'No disponible')}")
                                    print(f"- Estado: {radio.get('estado', 'No disponible')}")
                                    print(f"- Ciudad: {radio.get('municipio', 'No disponible')}")
                                    print(f"- Zona detectada: {zona_detectada}")
                                    print(f"- Validación completa: {validacion}")
                                    
                                    datos = {
                                        'indicativo': indicativo.upper(),
                                        'operador': radio.get('nombre_completo', ''),
                                        'estado': radio.get('estado', ''),
                                        'ciudad': radio.get('municipio', ''),
                                        'zona': zona_detectada if zona_detectada != 'Desconocida' else '',
                                        'fuente': 'Radioexperimentador',
                                        'fecha_consulta': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                    }
                                    print(f"- Fuente: Radioexperimentadores")
                                    print(f"- Zona asignada: {datos['zona']}")
                                    print(f"- Fecha de consulta: {datos['fecha_consulta']}")
                                else:
                                    # Si no se encuentra en ninguna tabla
                                    print("NO ENCONTRADO EN NINGUNA BASE DE DATOS")
                                    print("Se creará un nuevo registro vacío")
                                    
                                    datos = {
                                        'indicativo': indicativo.upper(),
                                        'operador': '',
                                        'estado': '',
                                        'ciudad': '',
                                        'zona': '',
                                        'fuente': 'Nuevo registro',
                                        'fecha_consulta': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                    }
                                    print(f"- Fuente: Nuevo registro")
                                    print(f"- Fecha de consulta: {datos['fecha_consulta']}")
                                
                                # Separador al final de cada búsqueda
                                print("="*50 + "\n")
                            
                            # Agregar a resultados
                            st.session_state.resultados_busqueda.append(datos)
                            
                            # Guardar en sesión para edición posterior
                            st.session_state[f'datos_estacion_{i}'] = {
                                'operador': datos['operador'],
                                'estado': datos['estado'],
                                'ciudad': datos['ciudad'],
                                'zona': datos['zona']
                            }
                    
                    if indicativos:
                        st.session_state.indicativos_pre_registro = indicativos
                        st.session_state.mostrar_panel_captura = True
                        st.rerun()
                    else:
                        st.warning("Por favor ingrese al menos un indicativo")
                
                # Mostrar tabla de resultados si hay búsquedas previas
                if st.session_state.resultados_busqueda:
                    st.markdown("### Pre-Registros de Estaciones")
                    
                    # Obtener listas para los dropdowns
                    db = FMREDatabase()
                    zonas = [""] + [z['zona'] for z in db.get_zonas() if z.get('zona')]
                    estados = [""] + [e['estado'] for e in db.get_estados() if e.get('estado')]
                    
                    # Inicializar lista para almacenar los datos finales
                    if 'estaciones_registradas' not in st.session_state:
                        st.session_state.estaciones_registradas = []
                    
                    # Mostrar formulario para cada estación
                    for i, resultado in enumerate(st.session_state.resultados_busqueda):
                        indicativo = resultado['indicativo']
                        datos_estacion = st.session_state.get(f'datos_estacion_{i}', {})
                        
                        with st.expander(f"Estación {i+1}: {indicativo}", expanded=True):
                            # Crear 4 columnas para los campos en una sola fila
                            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                            
                            with col1:
                                # Campo Operador
                                operador = st.text_input(
                                    "Operador",
                                    value=datos_estacion.get('operador', ''),
                                    key=f"operador_{i}",
                                    help="Nombre del operador de la estación"
                                )
                            
                            with col2:
                                # Campo Estado
                                estado = st.selectbox(
                                    "Estado",
                                    options=estados,
                                    index=estados.index(datos_estacion.get('estado', '')) 
                                            if datos_estacion.get('estado') in estados 
                                            else 0,
                                    key=f"estado_{i}",
                                    help="Seleccione el estado de la estación"
                                )
                            
                            with col3:
                                # Campo Ciudad
                                ciudad = st.text_input(
                                    "Ciudad",
                                    value=datos_estacion.get('ciudad', ''),
                                    key=f"ciudad_{i}",
                                    help="Ciudad donde se encuentra la estación"
                                )
                            
                            with col4:
                                # Campo Zona
                                zona = st.selectbox(
                                    "Zona",
                                    options=zonas,
                                    index=zonas.index(datos_estacion.get('zona', ''))
                                            if datos_estacion.get('zona') in zonas 
                                            else 0,
                                    key=f"zona_{i}",
                                    help="Zona a la que pertenece la estación"
                                )
                                
# The form fields will automatically update session state
                                # No need to manually update here
                    
                    # Los cambios se guardan automáticamente al hacer submit del formulario
                    
                    # Botón para guardar los registros (más pequeño y centrado)
                    col1, col2, col3 = st.columns([1,2,1])
                    with col2:
                        print("\n" + "="*80)
                        print("DEPURACIÓN - BOTÓN DE GUARDADO")
                        print("Se hizo clic en el botón de Guardar Registros")
                        print("="*80 + "\n")
                        
                        # Mover el botón de submit fuera del if para que el formulario funcione correctamente
                        submit_button = st.form_submit_button("💾 Guardar Registros", 
                                                          type="primary", 
                                                          use_container_width=True,
                                                          help="Guarda los registros de las estaciones")
                    
                    # Procesar el formulario cuando se envía
                    if submit_button:
                        try:
                            print("\n" + "="*80)
                            print("PROCESANDO EL ENVÍO DEL FORMULARIO")
                            print("="*80 + "\n")
                            
                            # Obtener los datos del formulario
                            plataforma_nombre = st.session_state.plataforma_seleccionada
                            me_gusta = st.session_state.get('me_gusta', 0)
                            comentarios = st.session_state.get('comentarios', 0)
                            compartidos = st.session_state.get('compartidos', 0)
                            reproducciones = st.session_state.get('reproducciones', 0)
                            fecha_reporte = st.session_state.fecha_reporte
                            created_by = st.session_state.user.get('username', 'sistema')
                            
                            # Obtener el ID de la plataforma del mapa de plataformas
                            plataforma_id = plataforma_map.get(plataforma_nombre)
                            
                            print(f"Plataforma: {plataforma_nombre} (ID: {plataforma_id})")
                            print(f"Me gusta: {me_gusta}")
                            print(f"Comentarios: {comentarios}")
                            print(f"Compartidos: {compartidos}")
                            print(f"Reproducciones: {reproducciones}")
                            print(f"Fecha: {fecha_reporte}")
                            print(f"Usuario: {created_by}")
                            
                            if not plataforma_id:
                                raise ValueError(f"No se pudo encontrar el ID para la plataforma: {plataforma_nombre}")
                            
                            # Obtener los datos de las estaciones
                            registros = []
                            for i, resultado in enumerate(st.session_state.resultados_busqueda):
                                datos = st.session_state.get(f'datos_estacion_{i}', {})
                                registros.append({
                                    'indicativo': resultado['indicativo'],
                                    'operador': datos.get('operador', ''),
                                    'estado': datos.get('estado', ''),
                                    'ciudad': datos.get('ciudad', ''),
                                    'zona': datos.get('zona', ''),
                                    'senal': 59,  # Valor por defecto
                                    'observaciones': f"Reporte de interacción en {plataforma_nombre}",
                                    'qrz_captured_by': st.session_state.user.get('username', '')
                                })
                            
                            # Preparar datos para estadísticas (solo un registro por plataforma/fecha)
                            estadistica_data = {
                                'plataforma_id': plataforma_id,
                                'plataforma_nombre': plataforma_nombre,
                                'me_gusta': int(me_gusta) if me_gusta else 0,
                                'comentarios': int(comentarios) if comentarios else 0,
                                'compartidos': int(compartidos) if compartidos else 0,
                                'reproducciones': int(reproducciones) if reproducciones else 0,
                                'fecha_reporte': fecha_reporte.strftime('%Y-%m-%d') if hasattr(fecha_reporte, 'strftime') else fecha_reporte,
                                'captured_by': created_by,
                                'observaciones': f"Reporte de {plataforma_nombre} capturado por {created_by}"
                            }
                            
                            # Insertar en la tabla reportes_rs para cada estación
                            for registro in registros:
                                reporte_data = {
                                    'plataforma_id': plataforma_id,
                                    'plataforma_nombre': plataforma_nombre,
                                    'me_gusta': int(me_gusta) if me_gusta else 0,
                                    'comentarios': int(comentarios) if comentarios else 0,
                                    'compartidos': int(compartidos) if compartidos else 0,
                                    'reproducciones': int(reproducciones) if reproducciones else 0,
                                    'fecha_reporte': fecha_reporte.strftime('%Y-%m-%d') if hasattr(fecha_reporte, 'strftime') else fecha_reporte,
                                    'created_by': created_by,
                                    'indicativo': registro['indicativo'],
                                    'operador': registro['operador'],
                                    'estado': registro['estado'],
                                    'ciudad': registro['ciudad'],
                                    'zona': registro['zona'],
                                    'senal': registro['senal'],
                                    'observaciones': registro['observaciones'],
                                    'qrz_captured_by': registro['qrz_captured_by']
                                }
                                
                                # Guardar el reporte de la estación
                                db.save_reporte_rs(reporte_data)
                            
                            # Guardar las estadísticas generales
                            db.save_estadistica_rs(estadistica_data)
                            
                            st.success("¡Los registros y estadísticas se han guardado correctamente!")
                            
                        except Exception as e:
                            st.error(f"Error al guardar los registros: {str(e)}")
                            import traceback
                            st.error("Detalles del error:")
                            st.code(traceback.format_exc())
                    
                    # Sección de depuración eliminada
                    
                    # Mostrar resumen de estaciones registradas
                    st.markdown("### Resumen de Estaciones")
                    
                    # Crear lista de estaciones con sus datos
                    estaciones = []
                    for i, resultado in enumerate(st.session_state.resultados_busqueda):
                        datos = st.session_state.get(f'datos_estacion_{i}', {})
                        estaciones.append({
                            'Indicativo': resultado['indicativo'],
                            'Operador': datos.get('operador', ''),
                            'Estado': datos.get('estado', ''),
                            'Ciudad': datos.get('ciudad', ''),
                            'Zona': datos.get('zona', '')
                        })
                    
                    # Mostrar tabla resumen
                    if estaciones:
                        df_resumen = pd.DataFrame(estaciones)
                        # Mostrar la tabla de resumen
                        st.dataframe(
                            df_resumen,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                'Indicativo': 'Indicativo',
                                'Operador': 'Operador',
                                'Estado': 'Estado',
                                'Ciudad': 'Ciudad',
                                'Zona': 'Zona'
                            }
                        )
                        
                        # El botón de guardar ahora está antes de la tabla de resumen
            
            # Mostrar panel de captura completo después de hacer clic en Pre-registrar
            if st.session_state.mostrar_panel_captura:
                st.success("Complete los datos de las estaciones pre-registradas")
                
                # Obtener lista de zonas y estados
                zonas = db.get_zonas()
                zona_options = [""] + [zona['zona'] for zona in zonas]
                estados = db.get_estados()
                estado_options = [""] + [estado['estado'] for estado in estados if estado.get('estado')]
                
                # Mostrar formulario completo para cada indicativo
                for i, indicativo in enumerate(st.session_state.indicativos_pre_registro):
                    st.markdown(f"---")
                    st.markdown(f"#### Estación {i+1}")
                    
                    # Mostrar el indicativo como texto
                    st.text_input("Indicativo", value=indicativo, disabled=True, key=f"disp_indicativo_{i}")
                    
                    # Obtener datos prellenados si existen
                    datos_estacion = st.session_state.get(f'datos_estacion_{i}', {})
                    
                    # Crear columnas para los campos
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Campo para el operador
                        operador = st.text_input(
                            f"Operador {i+1}",
                            value=datos_estacion.get('operador', ''),
                            key=f"operador_{i}",
                            help="Nombre del operador de la estación"
                        )
                        
                        # Estado
                        estado_actual = datos_estacion.get('estado', '')
                        estado_index = estado_options.index(estado_actual) if estado_actual in estado_options else 0
                        estado = st.selectbox(
                            f"Estado {i+1}",
                            options=estado_options,
                            index=estado_index,
                            key=f"estado_{i}",
                            help="Selecciona el estado de la estación"
                        )
                    
                    with col2:
                        # Ciudad
                        ciudad = st.text_input(
                            f"Ciudad {i+1}",
                            value=datos_estacion.get('ciudad', ''),
                            key=f"ciudad_{i}",
                            help="Ciudad de la estación"
                        )
                        
                        # Zona (selección de zona)
                        zona_actual = datos_estacion.get('zona', '')
                        zona_index = zona_options.index(zona_actual) if zona_actual in zona_options else 0
                        zona = st.selectbox(
                            f"Zona {i+1}", 
                            options=zona_options,
                            index=zona_index,
                            key=f"zona_{i}",
                            help="Selecciona la zona de la estación"
                        )
                    
                    # Zona de la plataforma (solo lectura)
                    plataforma_info = next((p for p in plataformas if p.get('plataforma') in st.session_state.plataforma_seleccionada), {})
                    zona_plataforma = plataforma_info.get('zona', '')
                    
                    st.text_input(
                        "Zona Plataforma", 
                        value=zona_plataforma,
                        key=f"zona_plataforma_{i}",
                        disabled=True,
                        help="Zona de la plataforma (automática)"
                    )
                    
                    # Agregar los datos del registro a la lista
                    registros.append({
                        'indicativo': indicativo,
                        'operador': operador,
                        'estado': estado,
                        'ciudad': ciudad,
                        'zona': zona,
                        'zona_plataforma': zona_plataforma
                    })
                
                # Botón para volver atrás
                col1, col2 = st.columns(2)
                with col1:
                    volver = st.form_submit_button("↩️ Volver a editar indicativos")
                    if volver:
                        st.session_state.mostrar_panel_captura = False
                        st.rerun()
                
                # Agregar los datos del registro a la lista
                registros.append({
                    'indicativo': indicativo,
                    'operador': operador,
                    'estado': estado,
                    'ciudad': ciudad,
                    'zona': zona,
                    'zona_plataforma': zona_plataforma,
                    'plataforma': st.session_state.plataforma_seleccionada
                })
            
            # Botón de pre-registrar al final del formulario
            pre_registrar = st.form_submit_button("📝 Pre-Registrar Todos")
            if pre_registrar:
                # Validaciones
                if not st.session_state.plataforma_seleccionada:
                    st.error("❌ Por favor selecciona una plataforma en la sección de Información del Reporte")
                    st.stop()
                
                if not any(registro['indicativo'] for registro in registros):
                    st.error("❌ Por favor ingresa al menos un indicativo de estación")
                    st.stop()
                
                # Validar cada indicativo
                for i, registro in enumerate(registros):
                    if registro['indicativo']:  # Solo validar si hay un indicativo
                        validacion = validar_call_sign(registro['indicativo'].upper())
                        if not validacion.get('indicativo', False):
                            st.error(f"❌ El indicativo '{registro['indicativo']}' no es válido. Por favor ingresa un indicativo válido (formato: XE1ABC o SWL).")
                            st.stop()
                
                # Si llegamos aquí, todas las validaciones pasaron
                # Mostrar tabla de resumen antes de guardar
                st.markdown("### Resumen del Pre-Registro")
                
                # Crear lista de datos para la tabla
                datos_tabla = []
                for registro in registros:
                    if registro['indicativo']:  # Solo incluir registros con indicativo
                        # Obtener datos del operador si existe en la base de datos
                        operador = db.get_radioexperimentador(registro['indicativo'].upper())
                        
                        datos_tabla.append({
                            'indicativo': registro['indicativo'].upper(),
                            'nombre_operador': operador.get('nombre', 'No encontrado') if operador else 'No encontrado',
                            'zona': registro['zona'] if registro['zona'] else 'No especificada',
                            'estado': operador.get('estado', 'No especificado') if operador else 'No especificado',
                            'ciudad': operador.get('ciudad', 'No especificada') if operador else 'No especificada',
                            'plataforma': st.session_state.plataforma_seleccionada
                        })
                
                # Mostrar la tabla de resumen
                if datos_tabla:
                    st.dataframe(
                        data=datos_tabla,
                        column_config={
                            'indicativo': 'Indicativo',
                            'nombre_operador': 'Nombre del Operador',
                            'zona': 'Zona',
                            'estado': 'Estado',
                            'ciudad': 'Ciudad',
                            'plataforma': 'Plataforma'
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Botón para confirmar el guardado
                    with st.form(key='confirmar_guardado'):
                        confirmar = st.form_submit_button("✅ Confirmar y Guardar Reporte")
                    
                    if confirmar:
                        # Preparar los datos del reporte principal
                        reporte_data = {
                            'fecha_reporte': st.session_state.fecha_reporte.strftime('%Y-%m-%d'),
                            'plataforma_id': plataforma_map[st.session_state.plataforma_seleccionada],
                            'plataforma_nombre': st.session_state.plataforma_seleccionada,
                            'me_gusta': me_gusta,
                            'comentarios': comentarios,
                            'compartidos': compartidos,
                            'reproducciones': reproducciones,
                            'contenido': st.session_state.contenido,
                            'created_by': st.session_state.user['id'],
                            'estaciones': []
                        }
                        
                        # Agregar los datos de cada estación
                        for registro in registros:
                            if registro['indicativo']:  # Solo agregar registros con indicativo
                                reporte_data['estaciones'].append({
                                    'indicativo': registro['indicativo'].upper(),
                                    'zona': registro['zona'] if registro['zona'] else None
                                })
                
                # Guardar en la base de datos
                try:
                    # Inicializar la base de datos
                    print("\n" + "="*80)
                    print("DEPURACIÓN - INICIO DEL PROCESO DE GUARDADO")
                    print("="*80 + "\n")
                    
                    db = FMREDatabase()
                    
                    # Obtener el ID de la plataforma
                    plataforma_id = plataforma_map[st.session_state.plataforma_seleccionada]
                    print(f"Plataforma ID obtenida: {plataforma_id}")
                    
                    # Preparar los datos para guardar
                    estadistica_data = {
                        'plataforma_id': plataforma_id,
                        'plataforma_nombre': st.session_state.plataforma_seleccionada,
                        'me_gusta': me_gusta,
                        'comentarios': comentarios,
                        'compartidos': compartidos,
                        'reproducciones': reproducciones,
                        'alcance': 0,  # Este campo podría calcularse o pedirse en el formulario
                        'interaccion': me_gusta + comentarios + compartidos,  # Suma de interacción
                        'fecha_reporte': st.session_state.fecha_reporte.strftime('%Y-%m-%d'),
                        'captured_by': st.session_state.user.get('username', 'Sistema'),
                        'observaciones': st.session_state.contenido,
                        'metadata_json': {
                            'tipo': 'publicacion',
                        }
                    }
                    
                    # Depuración: Mostrar los datos que se van a guardar
                    print("\n" + "="*80)
                    print("DEPURACIÓN - DATOS A GUARDAR")
                    print("="*80)
                    print(f"Tipo de estadistica_data: {type(estadistica_data)}")
                    print(f"Contenido de estadistica_data: {estadistica_data}")
                    
                    # Guardar las estadísticas
                    print("\nLlamando a save_estadistica_rs...")
                    try:
                        estadistica_id = db.save_estadistica_rs(estadistica_data)
                        print(f"Resultado de save_estadistica_rs: {estadistica_id}")
                        
                        if not estadistica_id:
                            raise Exception("Error al guardar las estadísticas de la publicación")
                            
                    except Exception as e:
                        print(f"Error en save_estadistica_rs: {str(e)}")
                        raise
                    
                    # Depuración: Mostrar los datos que se van a guardar
                    print("\n" + "="*80)
                    print("DEPURACIÓN - DATOS A GUARDAR")
                    print("="*80)
                    
                    # Mostrar datos de la estadística
                    print("\nESTADÍSTICA PRINCIPAL:")
                    print(f"- Plataforma ID: {plataforma_id}")
                    print(f"- Me gusta: {estadistica_data['me_gusta']}")
                    print(f"- Comentarios: {estadistica_data['comentarios']}")
                    print(f"- Compartidos: {estadistica_data['compartidos']}")
                    print(f"- Reproducciones: {estadistica_data['reproducciones']}")
                    print(f"- Fecha: {estadistica_data['fecha_reporte']}")
                    print(f"- Usuario: {estadistica_data['captured_by']}")
                    print(f"- Observaciones: {estadistica_data['observaciones']}")
                    print(f"- Metadata: {estadistica_data['metadata_json']}")
                    
                    print("\nREGISTROS DE ESTACIONES:")
                    for i, reg in enumerate(registros, 1):
                        print(f"\nEstación {i}:")
                        print(f"- Indicativo: {reg.get('indicativo', 'No disponible')}")
                        print(f"- Operador: {reg.get('operador', 'No disponible')}")
                        print(f"- Estado: {reg.get('estado', 'No disponible')}")
                        print(f"- Ciudad: {reg.get('ciudad', 'No disponible')}")
                        print(f"- Zona: {reg.get('zona', 'No disponible')}")
                    
                    print("\nINICIANDO GUARDADO DE REGISTROS...")
                    print("="*80 + "\n")
                    
                    # Guardar cada reporte de estación
                    for registro in registros:
                        if registro.get('indicativo'):  # Solo guardar registros con indicativo
                            reporte_data = {
                                'indicativo': registro['indicativo'].upper(),
                                'operador': registro.get('operador', ''),
                                'estado': registro.get('estado', ''),
                                'ciudad': registro.get('ciudad', ''),
                                'zona': registro.get('zona', ''),
                                'senal': 59,  # Valor fijo según la estructura
                                'observaciones': f"Reporte de interacción en {st.session_state.plataforma_seleccionada}",
                                'qrz_captured_by': st.session_state.user.get('username', ''),
                                'qrz_station': st.session_state.user.get('qrz_station', ''),
                                'plataforma_id': plataforma_id,
                                'plataforma_nombre': st.session_state.plataforma_seleccionada,
                                'created_by': st.session_state.user['id'],
                                'fecha_reporte': st.session_state.fecha_reporte.strftime('%Y-%m-%d')
                            }
                            
                            # Guardar el reporte de la estación
                            reporte_id = db.save_reporte_rs(reporte_data)
                            
                            if not reporte_id:
                                raise Exception(f"Error al guardar el reporte para la estación {registro['indicativo']}")
                    
                    st.success("✅ ¡Reporte guardado exitosamente!")
                    st.balloons()
                    
                    # Limpiar el formulario después de guardar
                    st.session_state.parametros_expanded = True
                    st.session_state.plataforma_seleccionada = ""
                    st.session_state.contenido = ""
                    st.session_state.fecha_reporte = datetime.now().date()
                    st.session_state.num_registros = 1
                    st.session_state.mostrar_panel_captura = False
                    
                    # Limpiar los campos de indicativos
                    for i in range(100):  # Asumiendo un máximo de 100 registros
                        if f'indicativo_{i}' in st.session_state:
                            del st.session_state[f'indicativo_{i}']
                    
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Error al guardar el reporte: {str(e)}")
                    st.error("Por favor intenta nuevamente o contacta al administrador.")
                    # Mostrar más detalles del error para depuración
                    import traceback
                    st.error("Detalles del error:")
                    st.code(traceback.format_exc())
                    
                    # Usar st.button en lugar de st.form para evitar anidación
                    if st.button("🔄 Intentar nuevamente", key='intento_nuevamente_btn'):
                        st.session_state.mostrar_panel_captura = False
                        st.rerun()
    #     st.dataframe(reportes_recientes)
    # else:
    #     st.info("Aún no hay reportes registrados.")
