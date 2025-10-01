import streamlit as st
from database import FMREDatabase

def edit_rs_entry(entry_id):
    """Muestra el formulario de edición para una entrada de red social"""
    db = FMREDatabase()
    entry = db.get_rs_entry(entry_id)
    
    if not entry:
        st.error("Entrada no encontrada")
        return
    
    st.subheader(f"Editando: {entry['plataforma']} - {entry['nombre']}")
    
    # Usar el formulario de Streamlit
    with st.form(key=f'edit_rs_form_{entry_id}'):
        # Campos del formulario
        plataforma = st.text_input("Plataforma*", value=entry['plataforma'])
        nombre = st.text_input("Nombre*", value=entry['nombre'])
        descripcion = st.text_area("Descripción", value=entry['descripcion'] or '')
        url = st.text_input("URL", value=entry['url'] or '')
        admin = st.text_input("Administrador", value=entry['administrador'] or '')
        
        # Botones de acción
        col1, col2 = st.columns(2)
        
        with col1:
            if st.form_submit_button("💾 Guardar Cambios"):
                if not plataforma or not nombre:
                    st.error("Los campos con * son obligatorios")
                else:
                    if db.update_rs_entry(
                        entry_id,
                        plataforma=plataforma,
                        nombre=nombre,
                        descripcion=descripcion or None,
                        url=url or None,
                        administrador=admin or None
                    ):
                        st.success("¡Cambios guardados exitosamente!")
                        if 'edit_rs_id' in st.session_state:
                            del st.session_state['edit_rs_id']
                        st.rerun()
                    else:
                        st.error("Error al actualizar la red social")
        
        with col2:
            if st.form_submit_button("❌ Cancelar"):
                if 'edit_rs_id' in st.session_state:
                    del st.session_state['edit_rs_id']
                st.rerun()

def display_rs_entry(entry, db):
    """Muestra una entrada de red social en un expander con opciones de edición"""
    entry_id = entry['id']
    
    # Verificar si estamos editando esta entrada
    is_editing = st.session_state.get(f'editing_rs_{entry_id}', False)
    
    if is_editing:
        # Mostrar formulario de edición
        with st.form(key=f'edit_rs_form_{entry_id}'):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                plataforma = st.text_input("Plataforma*", value=entry['plataforma'], key=f'plataforma_{entry_id}')
                nombre = st.text_input("Nombre*", value=entry['nombre'], key=f'nombre_{entry_id}')
                descripcion = st.text_area("Descripción", value=entry['descripcion'] or '', key=f'descripcion_{entry_id}')
                url = st.text_input("URL", value=entry['url'] or '', key=f'url_{entry_id}')
                admin = st.text_input("Administrador", value=entry['administrador'] or '', key=f'admin_{entry_id}')
            
            with col2:
                st.write("")
                st.write("")
                if st.form_submit_button("💾 Guardar"):
                    if not plataforma or not nombre:
                        st.error("Los campos con * son obligatorios")
                    else:
                        if db.update_rs_entry(
                            entry_id,
                            plataforma=plataforma,
                            nombre=nombre,
                            descripcion=descripcion or None,
                            url=url or None,
                            administrador=admin or None
                        ):
                            st.success("¡Cambios guardados!")
                            st.session_state[f'editing_rs_{entry_id}'] = False
                            st.rerun()
                        else:
                            st.error("Error al actualizar la red social")
                
                if st.form_submit_button("❌ Cancelar"):
                    st.session_state[f'editing_rs_{entry_id}'] = False
                    st.rerun()
    else:
        # Mostrar información de la red social
        with st.expander(f"{entry['plataforma']} - {entry['nombre']}"):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write(f"**Plataforma:** {entry['plataforma']}")
                st.write(f"**Nombre:** {entry['nombre']}")
                if entry['descripcion']:
                    st.write(f"**Descripción:** {entry['descripcion']}")
                if entry['url']:
                    st.write(f"**URL:** [{entry['url']}]({entry['url']})")
                if entry['administrador']:
                    st.write(f"**Administrador:** {entry['administrador']}")
                st.write(f"**Estado:** {'✅ Activo' if entry.get('is_active', 1) else '❌ Inactivo'}")
            
            with col2:
                # Botón de editar
                if st.button("✏️ Editar", key=f"edit_{entry_id}"):
                    st.session_state[f'editing_rs_{entry_id}'] = True
                    st.rerun()
                
                # Botones de activar/desactivar
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if entry.get('is_active', 1):
                        if st.button("❌ Desactivar", key=f"deact_{entry_id}"):
                            if db.update_rs_entry(entry_id, is_active=0):
                                st.success("Red social desactivada")
                                st.rerun()
                    else:
                        if st.button("✅ Activar", key=f"act_{entry_id}"):
                            if db.update_rs_entry(entry_id, is_active=1):
                                st.success("Red social activada")
                                st.rerun()
                
                # Botón de eliminar
                with col_btn2:
                    if st.button("🗑️", key=f"del_{entry_id}", help="Eliminar"):
                        if 'confirm_delete' not in st.session_state:
                            st.session_state.confirm_delete = entry_id
                            st.rerun()
                
                # Confirmación de eliminación
                if 'confirm_delete' in st.session_state and st.session_state.confirm_delete == entry_id:
                    st.warning("¿Está seguro?")
                    if st.button("✅ Confirmar", key=f"confirm_del_{entry_id}"):
                        if db.delete_rs_entry(entry_id):
                            st.success("Red social eliminada")
                            if 'confirm_delete' in st.session_state:
                                del st.session_state.confirm_delete
                            st.rerun()
                        else:
                            st.error("Error al eliminar")
                        if 'confirm_delete' in st.session_state:
                            del st.session_state.confirm_delete
def show_rs_form():
    """Muestra el formulario para agregar/editar una red social"""
    db = FMREDatabase()
    
    # Debug: Verificar conexión a la base de datos
    st.sidebar.write("Probando conexión a la base de datos...")
    
    # Obtener todas las entradas de redes sociales
    try:
        rs_entries = db.get_rs_entries(active_only=False)
        st.sidebar.write(f"✅ Conexión exitosa. Entradas encontradas: {len(rs_entries) if rs_entries else 0}")
    except Exception as e:
        st.sidebar.error(f"❌ Error al conectar con la base de datos: {str(e)}")
        rs_entries = []
    
    # Extraer plataformas únicas de la base de datos
    plataformas = set()
    if rs_entries:
        st.sidebar.write("Analizando entradas...")
        for i, entry in enumerate(rs_entries, 1):
            if not entry:
                st.sidebar.write(f"  - Entrada {i}: None")
                continue
                
            st.sidebar.write(f"  - Entrada {i}: {entry}")
            
            if 'plataforma' not in entry:
                st.sidebar.write(f"    ❌ No tiene campo 'plataforma'. Campos disponibles: {list(entry.keys())}")
            elif not entry['plataforma']:
                st.sidebar.write(f"    ⚠️  Plataforma vacía en entrada {i}")
            else:
                st.sidebar.write(f"    ✅ Plataforma encontrada: {entry['plataforma']}")
                plataformas.add(entry['plataforma'])
    
    # Convertir a lista y ordenar alfabéticamente
    plataformas = sorted(list(plataformas)) if plataformas else []
    
    # Mostrar resumen
    st.sidebar.write("\n=== RESUMEN ===")
    st.sidebar.write(f"Total de plataformas únicas: {len(plataformas)}")
    if plataformas:
        st.sidebar.write("Plataformas encontradas:", plataformas)
    
    with st.form("rs_form"):
        if not plataformas:
            st.warning("No hay plataformas registradas. Por favor, ingrese una nueva plataforma.")
            plataforma = st.text_input("Plataforma*", key="plataforma_rs")
        else:
            # Mostrar selectbox con las plataformas existentes
            plataforma = st.selectbox(
                "Plataforma*",
                options=plataformas,
                key="plataforma_rs"
            )
            
        nombre = st.text_input("Nombre de la cuenta*", key="nombre_rs")
        url = st.text_input("URL", key="url_rs")
        descripcion = st.text_area("Descripción", key="descripcion_rs")
        administrador = st.text_input("Administrador/Responsable", key="admin_rs")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("💾 Guardar"):
                rs_data = {
                    'plataforma': plataforma,
                    'nombre': nombre,
                    'url': url,
                    'descripcion': descripcion,
                    'administrador': administrador
                }
                
                if 'edit_rs_id' in st.session_state:
                    # Actualizar existente
                    if db.update_rs_entry(st.session_state.edit_rs_id, rs_data):
                        st.success("¡Cambios guardados exitosamente!")
                        del st.session_state.edit_rs_id
                        st.rerun()
                    else:
                        st.error("Error al actualizar la red social")
                else:
                    # Crear nuevo
                    if db.create_rs_entry(rs_data):
                        st.success("¡Red social creada exitosamente!")
                        st.rerun()
                    else:
                        st.error("Error al crear la red social")
        
        with col2:
            if st.form_submit_button("❌ Cancelar"):
                if 'edit_rs_id' in st.session_state:
                    del st.session_state.edit_rs_id
                st.rerun()

def show_rs_management(show_tabs=True):
    """Muestra la interfaz de gestión de redes sociales
    
    Args:
        show_tabs (bool): Si es False, no muestra las pestañas (útil cuando ya se muestran en el contenedor padre)
    """
    db = FMREDatabase()
    
    if show_tabs:
        # Pestañas para diferentes operaciones
        tab1, tab2 = st.tabs(["Lista de Redes", "Agregar Nueva"])
        
        with tab1:
            st.subheader("Redes Sociales Registradas")
            
            # Mostrar formulario de edición si hay un ID de edición activo
            if 'edit_rs_id' in st.session_state and st.session_state.edit_rs_id is not None:
                if st.button("⬅️ Volver a la lista"):
                    del st.session_state.edit_rs_id
                    st.rerun()
                st.subheader("Editar Red Social")
                edit_rs_entry(st.session_state.edit_rs_id)
            else:
                rs_entries = db.get_rs_entries(active_only=False)
                
                if not rs_entries:
                    st.info("No hay redes sociales registradas.")
                else:
                    for entry in rs_entries:
                        display_rs_entry(entry, db)
        
        with tab2:
            st.subheader("Agregar Nueva Red Social")
            show_rs_form()
    else:
        # Vista sin pestañas (para cuando ya están en el contenedor padre)
        st.subheader("Redes Sociales Registradas")
        rs_entries = db.get_rs_entries(active_only=False)
        
        if not rs_entries:
            st.info("No hay redes sociales registradas.")
        else:
            for entry in rs_entries:
                display_rs_entry(entry, db)

# Para probar el módulo independientemente
if __name__ == "__main__":
    show_rs_management()
