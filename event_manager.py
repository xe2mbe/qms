import streamlit as st
import pandas as pd
from database import FMREDatabase

def show_event_management():
    """Muestra la interfaz de gestión de tipos de eventos"""
    st.title("📅 Gestión de Eventos")
    
    # Inicializar base de datos
    db = FMREDatabase()
    
    # Pestañas principales
    tab1, tab2 = st.tabs(["📋 Lista de Eventos", "➕ Crear Evento"])
    
    with tab1:
        st.header("📋 Lista de Eventos")
        show_event_list(db)
    
    with tab2:
        st.header("➕ Crear Nuevo Evento")
        show_create_event_form(db)

def show_event_list(db):
    """Muestra la lista de eventos con opciones de edición y eliminación"""
    # Obtener tipos de evento existentes
    event_types = db.get_event_types(active_only=False)
    
    if not event_types.empty:
        # Mostrar tabla de eventos
        for _, event in event_types.iterrows():
            with st.expander(f"📌 {event['name']} - {event['description']}"):
                col1, col2 = st.columns([4, 1])
                
                with col1:
                    st.markdown(f"**ID:** {event['id']}")
                    st.markdown(f"**Nombre:** {event['name']}")
                    st.markdown(f"**Descripción:** {event['description']}")
                    
                    weekdays = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
                    default_weekday = int(event['default_weekday']) if pd.notna(event['default_weekday']) and not pd.isna(event['default_weekday']) else None
                    weekday = weekdays[default_weekday] if default_weekday is not None and 0 <= default_weekday < len(weekdays) else "Diario"
                    time = event['default_time'] if event['default_time'] else "No especificada"
                    
                    st.markdown(f"**Día:** {weekday}")
                    st.markdown(f"**Hora:** {time}")
                    st.markdown(f"**Estado:** {'🟢 Activo' if event['is_active'] else '🔴 Inactivo'}")
                
                with col2:
                    # Botón para editar
                    edit_clicked = st.button("✏️ Editar", key=f"edit_{event['id']}")
                    # Botón para eliminar/desactivar
                    status_btn_text = "❌ Desactivar" if event['is_active'] else "✅ Activar"
                    status_clicked = st.button(status_btn_text, key=f"status_{event['id']}")
                    
                    if edit_clicked:
                        st.session_state['editing_event'] = event.to_dict()
                        st.session_state['show_edit_form'] = True
                    
                    if status_clicked:
                        try:
                            db.update_event_type(
                                event_type_id=event['id'],
                                is_active=not event['is_active']
                            )
                            st.success(f"Evento {'activado' if not event['is_active'] else 'desactivado'} correctamente")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al actualizar el estado del evento: {str(e)}")
                
                # Mostrar formulario de edición si corresponde
                if st.session_state.get('show_edit_form', False) and st.session_state.get('editing_event', {}).get('id') == event['id']:
                    show_edit_event_form(db, event)
    else:
        st.info("No hay eventos registrados. Crea tu primer evento en la pestaña 'Crear Evento'.")

def show_create_event_form(db):
    """Muestra el formulario para crear un nuevo evento"""
    with st.form("create_event_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("Nombre del evento*")
            description = st.text_area("Descripción")
        
        with col2:
            weekdays = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
            
            # Opciones para el selector de día
            day_options = ["Diario", "Fecha única"] + weekdays
            
            selected_day = st.selectbox(
                "Tipo de evento", 
                options=day_options,
                index=0  # Diario por defecto
            )
            
            # Mostrar selector de fecha si se selecciona Fecha única
            specific_date = None
            if selected_day == "Fecha única":
                specific_date = st.date_input("Seleccione la fecha del evento")
                default_weekday = None
            elif selected_day == "Diario":
                default_weekday = None
            else:
                default_weekday = weekdays.index(selected_day)
            
            default_time = st.time_input("Hora por defecto")
            is_active = st.checkbox("Activo", value=True)
        
        submitted = st.form_submit_button("💾 Guardar Evento", type="primary")
        
        if submitted:
            if not name:
                st.error("El nombre del evento es obligatorio")
            else:
                try:
                    # Convertir el día de la semana a número (0-6)
                    weekday_num = weekdays.index(default_weekday) if default_weekday else None
                    
                    # Crear el evento
                    success = db.create_event_type(
                        name=name,
                        description=description,
                        default_weekday=weekday_num,
                        default_time=default_time.strftime("%H:%M") if default_time else None,
                        is_active=is_active
                    )
                    
                    if success:
                        st.success("✅ Evento creado exitosamente")
                        st.rerun()
                    else:
                        st.error("❌ Error al crear el evento")
                except Exception as e:
                    st.error(f"❌ Error al crear el evento: {str(e)}")

def show_edit_event_form(db, event):
    """Muestra el formulario para editar un evento existente"""
    with st.form(key=f"edit_form_{event['id']}"):
        st.subheader(f"✏️ Editando: {event['name']}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            new_name = st.text_input("Nombre*", value=event['name'])
            new_desc = st.text_area("Descripción", value=event['description'])
        
        with col2:
            weekdays = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
            default_weekday = int(event['default_weekday']) if pd.notna(event['default_weekday']) else None
            
            # Opciones para el selector de día
            day_options = ["Diario", "Fecha única"] + weekdays
            
            # Determinar el índice seleccionado
            if pd.notna(event.get('specific_date')):
                select_index = 1  # Fecha única
            elif default_weekday is not None and 0 <= default_weekday < len(weekdays):
                select_index = default_weekday + 2  # +2 porque los primeros son Diario y Fecha única
            else:
                select_index = 0  # Diario por defecto
            
            selected_day = st.selectbox(
                "Tipo de evento", 
                options=day_options,
                index=int(select_index)
            )
            
            # Mostrar selector de fecha si se selecciona Fecha única
            if selected_day == "Fecha única":
                specific_date = st.date_input("Seleccione la fecha del evento")
                new_weekday = None
            elif selected_day == "Diario":
                new_weekday = None
            else:
                new_weekday = weekdays.index(selected_day)
            
            default_time = pd.to_datetime(event['default_time']).time() if event['default_time'] else None
            new_time = st.time_input("Hora por defecto", value=default_time)
            
            is_active = st.checkbox("Activo", value=bool(event['is_active']))
        
        col1, col2 = st.columns([1, 3])
        with col1:
            save_clicked = st.form_submit_button("💾 Guardar Cambios", type="primary")
        with col2:
            cancel_clicked = st.form_submit_button("❌ Cancelar")
        
        if save_clicked:
            if not new_name:
                st.error("El nombre del evento es obligatorio")
            else:
                try:
                    # Convertir el día de la semana a número (0-6)
                    weekday_num = weekdays.index(new_weekday) if new_weekday else None
                    
                    # Actualizar el evento
                    success = db.update_event_type(
                        event_type_id=event['id'],
                        name=new_name,
                        description=new_desc,
                        default_weekday=weekday_num,
                        default_time=new_time.strftime("%H:%M") if new_time else None,
                        is_active=is_active
                    )
                    
                    if success:
                        st.success("✅ Evento actualizado exitosamente")
                        # Limpiar estado de edición
                        if 'editing_event' in st.session_state:
                            del st.session_state['editing_event']
                        st.session_state['show_edit_form'] = False
                        st.rerun()
                    else:
                        st.error("❌ Error al actualizar el evento")
                except Exception as e:
                    st.error(f"❌ Error al actualizar el evento: {str(e)}")
        
        if cancel_clicked:
            # Limpiar estado de edición
            if 'editing_event' in st.session_state:
                del st.session_state['editing_event']
            st.session_state['show_edit_form'] = False
            st.rerun()

def show_event_selection_modal():
    """Muestra el modal de selección de evento"""
    db = FMREDatabase()
    events = db.get_event_types(active_only=True)
    
    if events.empty:
        st.warning("No hay eventos configurados")
        return None
    
    # Crear lista de opciones para el selectbox
    options = ["Seleccione un evento..."] + [f"{row['name']} - {row['description']}" for _, row in events.iterrows()]
    
    # Mostrar selectbox para seleccionar evento
    selected = st.selectbox("Seleccione un evento:", options)
    
    if selected != "Seleccione un evento...":
        # Obtener el ID del evento seleccionado
        selected_name = selected.split(" - ")[0]
        selected_event = events[events['name'] == selected_name].iloc[0]
    
    # Obtener el evento sugerido basado en la fecha/hora actual
    suggested_event = db.get_suggested_event_type()
    
    # Crear modal
    with st.sidebar.expander("🎯 Seleccionar Evento", expanded=True):
        st.markdown("### 🎯 Seleccionar Evento")
        
        # Obtener lista de eventos activos
        event_types = db.get_event_types(active_only=True)
        
        if event_types.empty:
            st.warning("No hay tipos de evento configurados. Contacta al administrador.")
            return None, None
        
        # Crear opciones para el selectbox
        event_options = {}
        for _, event in event_types.iterrows():
            time_info = f" ({event['default_time']})" if event['default_time'] else ""
            day_info = f" - {['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'][event['default_weekday']]}" if pd.notna(event['default_weekday']) else ""
            event_options[event['id']] = f"{event['name']}{day_info}{time_info}"
        
        # Encontrar el índice del evento sugerido
        default_idx = 0
        if suggested_event and suggested_event['id'] in event_options:
            default_idx = list(event_options.keys()).index(suggested_event['id'])
        
        # Mostrar selector de evento
        selected_event_id = st.selectbox(
            "Tipo de evento",
            options=list(event_options.keys()),
            format_func=lambda x: event_options[x],
            index=default_idx
        )
        
        # Mostrar fecha del evento
        import datetime
        today = datetime.date.today()
        
        # Si es un evento semanal, ajustar al próximo día correspondiente
        selected_event = event_types[event_types['id'] == selected_event_id].iloc[0]
        if pd.notna(selected_event['default_weekday']):
            days_ahead = (selected_event['default_weekday'] - today.weekday()) % 7
            event_date = today + datetime.timedelta(days=days_ahead)
        else:
            event_date = today
        
        # Permitir editar la fecha
        event_date = st.date_input(
            "Fecha del evento",
            value=event_date,
            min_value=today - datetime.timedelta(days=30),  # Permitir fechas pasadas cercanas
            max_value=today + datetime.timedelta(days=365)  # Un año hacia adelante
        )
        
        return selected_event_id, event_date
    
    return None, None
