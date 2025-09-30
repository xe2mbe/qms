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
    
    with st.form(key='edit_rs_form'):
        st.session_state.rs_plataforma = st.text_input("Plataforma*", value=entry['plataforma'])
        st.session_state.rs_nombre = st.text_input("Nombre*", value=entry['nombre'])
        st.session_state.rs_descripcion = st.text_area("Descripción", value=entry['descripcion'] or '')
        st.session_state.rs_url = st.text_input("URL", value=entry['url'] or '')
        st.session_state.rs_admin = st.text_input("Administrador", value=entry['administrador'] or '')
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("💾 Guardar Cambios"):
                if not st.session_state.rs_plataforma or not st.session_state.rs_nombre:
                    st.error("Los campos con * son obligatorios")
                else:
                    if db.update_rs_entry(
                        entry_id,
                        plataforma=st.session_state.rs_plataforma,
                        nombre=st.session_state.rs_nombre,
                        descripcion=st.session_state.rs_descripcion or None,
                        url=st.session_state.rs_url or None,
                        administrador=st.session_state.rs_admin or None
                    ):
                        st.success("¡Cambios guardados exitosamente!")
                        del st.session_state.edit_rs_id
                        st.rerun()
                    else:
                        st.error("Error al actualizar la red social")
        
        with col2:
            if st.form_submit_button("❌ Cancelar"):
                if 'edit_rs_id' in st.session_state:
                    del st.session_state.edit_rs_id
                st.rerun()

def display_rs_entry(entry, db):
    """Muestra una entrada de red social en un expander con opciones de edición"""
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
            if st.button("✏️ Editar", key=f"edit_{entry['id']}"):
                st.session_state.edit_rs_id = entry['id']
                st.rerun()
                
            col1_btn, col2_btn = st.columns(2)
            with col1_btn:
                if entry.get('is_active', 1):
                    if st.button(f"❌ Desactivar", key=f"deact_{entry['id']}"):
                        if db.update_rs_entry(entry['id'], is_active=0):
                            st.success("Red social desactivada")
                            st.rerun()
                else:
                    if st.button(f"✅ Activar", key=f"act_{entry['id']}"):
                        if db.update_rs_entry(entry['id'], is_active=1):
                            st.success("Red social activada")
                            st.rerun()
            
            with col2_btn:
                if st.button("🗑️", key=f"del_{entry['id']}", help="Eliminar permanentemente"):
                    if 'confirm_delete' not in st.session_state:
                        st.session_state.confirm_delete = entry['id']
                        st.rerun()
                    elif st.session_state.confirm_delete == entry['id']:
                        if db.delete_rs_entry(entry['id']):
                            st.success("Red social eliminada correctamente")
                            if 'edit_rs_id' in st.session_state and st.session_state.edit_rs_id == entry['id']:
                                del st.session_state.edit_rs_id
                            if 'confirm_delete' in st.session_state:
                                del st.session_state.confirm_delete
                            st.rerun()
                        else:
                            st.error("Error al eliminar la red social")
            
            if 'confirm_delete' in st.session_state and st.session_state.confirm_delete == entry['id']:
                st.warning("¿Está seguro? Esta acción no se puede deshacer.")
                if st.button("✅ Confirmar eliminación", key=f"confirm_del_{entry['id']}"):
                    if db.delete_rs_entry(entry['id']):
                        st.success("Red social eliminada correctamente")
                        if 'edit_rs_id' in st.session_state and st.session_state.edit_rs_id == entry['id']:
                            del st.session_state.edit_rs_id
                        if 'confirm_delete' in st.session_state:
                            del st.session_state.confirm_delete
                        st.rerun()
                    else:
                        st.error("Error al eliminar la red social")

def show_rs_form():
    """Muestra el formulario para agregar/editar una red social"""
    db = FMREDatabase()
    
    # Obtener plataformas únicas de la base de datos
    rs_entries = db.get_rs_entries(active_only=False)
    plataformas = sorted(list(set([entry['plataforma'] for entry in rs_entries]))) if rs_entries else []
    
    # Agregar opciones comunes si no existen
    opciones_comunes = ["Facebook", "Twitter", "Instagram", "YouTube", "TikTok", "Otra"]
    for opcion in opciones_comunes:
        if opcion not in plataformas:
            plataformas.append(opcion)
    
    with st.form("rs_form"):
        plataforma = st.selectbox(
            "Plataforma*",
            plataformas,
            key="plataforma_rs",
            index=len(plataformas)-1 if "Otra" in plataformas else 0
        )
        nombre = st.text_input("Nombre de la cuenta", key="nombre_rs")
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
        tab1, tab2 = st.tabs(["Lista de Redes", "Agregar/Editar Red"])
        
        with tab1:
            st.subheader("Redes Sociales Registradas")
            rs_entries = db.get_rs_entries(active_only=False)
            
            if not rs_entries:
                st.info("No hay redes sociales registradas.")
            else:
                for entry in rs_entries:
                    display_rs_entry(entry, db)
        
        with tab2:
            st.subheader("Agregar/Editar Red Social")
            # Si se está editando, mostrar el formulario de edición
            if 'edit_rs_id' in st.session_state and st.session_state.edit_rs_id is not None:
                edit_rs_entry(st.session_state.edit_rs_id)
            else:
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
                
        st.subheader("Agregar Nueva Red Social")
        show_rs_form()

# Para probar el módulo independientemente
if __name__ == "__main__":
    show_rs_management()
