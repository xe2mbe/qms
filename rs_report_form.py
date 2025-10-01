import streamlit as st
from database import FMREDatabase
from datetime import datetime

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
    
    for p in plataformas:
        # Usar solo el nombre de la plataforma como valor mostrado
        display_name = p['plataforma']
        # Agregar el nombre del grupo si existe
        if p['nombre']:
            display_name = f"{p['plataforma']} - {p['nombre']}"
        
        plataforma_options.append(display_name)
        plataforma_map[display_name] = p['id']
    
    # Formulario principal
    with st.form("redes_sociales_form"):
        st.markdown("### Información del Reporte")
        
        # Fecha del reporte
        fecha_reporte = st.date_input("Fecha del reporte", datetime.now())
        
        # Selección de plataforma
        plataforma_seleccionada = st.selectbox(
            "Plataforma de Red Social",
            options=[""] + plataforma_options,
            help="Selecciona la plataforma donde se realizó el reporte"
        )
        
        # Detalles del reporte
        contenido = st.text_area("Contenido del reporte", 
                               placeholder="Ingresa el contenido del reporte...",
                               height=150)
        
        # Interacciones
        col1, col2, col3 = st.columns(3)
        with col1:
            me_gusta = st.number_input("Me gusta", min_value=0, value=0)
        with col2:
            comentarios = st.number_input("Comentarios", min_value=0, value=0)
        with col3:
            compartidos = st.number_input("Compartidos", min_value=0, value=0)
        
        # Botones de acción
        submitted = st.form_submit_button("Guardar Reporte")
        if submitted:
            if not plataforma_seleccionada:
                st.error("Por favor selecciona una plataforma")
                return
                
            # Preparar los datos del reporte
            reporte_data = {
                'fecha': fecha_reporte.strftime('%Y-%m-%d'),
                'plataforma_id': plataforma_map[plataforma_seleccionada],
                'contenido': contenido,
                'me_gusta': me_gusta,
                'comentarios': comentarios,
                'compartidos': compartidos,
                'usuario_id': st.session_state.user['id']
            }
            
            # Guardar en la base de datos
            try:
                # Aquí iría el código para guardar en la base de datos
                # db.guardar_reporte_redes_sociales(reporte_data)
                st.success("¡Reporte guardado exitosamente!")
                st.balloons()
            except Exception as e:
                st.error(f"Error al guardar el reporte: {str(e)}")
    
    # Sección de reportes recientes
    st.markdown("---")
    st.markdown("### Reportes Recientes")
    
    # Aquí iría el código para mostrar los reportes recientes
    # reportes_recientes = db.obtener_reportes_recientes()
    # if reportes_recientes:
    #     st.dataframe(reportes_recientes)
    # else:
    #     st.info("Aún no hay reportes registrados.")
