import streamlit as st
import sqlite3
import time
import secrets
import string
from time_utils import format_datetime
import hashlib
from datetime import datetime
import pytz
from database import FMREDatabase
from auth import AuthManager
from email_sender import EmailSender
import utils
import re

# Inicializar la base de datos y autenticación
db = FMREDatabase()
auth = AuthManager(db)

def show_sidebar():
    """Muestra la barra lateral solo cuando el usuario está autenticado"""
    if 'user' not in st.session_state:
        # Si no está autenticado, no mostrar barra lateral
        st.sidebar.empty()
        return
    
    with st.sidebar:
        # Usar una versión más grande del logo con un ancho máximo
        st.image(
            "assets/LogoFMRE_medium.png",
            width='content',  # Ancho fijo en lugar de usar el contenedor
            output_format='PNG',
            #width=200  # Ancho máximo en píxeles
        )
        
        # Mostrar información del usuario
        user = st.session_state.user
        st.markdown(f"### {user['full_name']}")
        st.caption(f"👤 {user['role'].capitalize()}")
        
        # Mostrar fecha actual
        mexico_tz = pytz.timezone('America/Mexico_City')
        current_date = datetime.now(mexico_tz).strftime("%d/%m/%Y %H:%M")
        st.markdown(f"---")
        st.caption(f"📅 Sesión: {current_date}")
        
        # Menú de navegación
        st.markdown("### Menú")
        menu_options = ["🏠 Inicio", "📝 Toma de Reportes", "📊 Reportes"]
        
        # Mostrar opciones de administración solo para administradores
        if user['role'] == 'admin':
            menu_options.extend(["🔧 Gestión", "⚙️ Configuración"])
            
        selected = st.selectbox("Navegación", menu_options)
        
        # Navegación
        if selected == "🔧 Gestión":
            st.session_state.current_page = "gestion"
        elif selected == "📝 Toma de Reportes":
            st.session_state.current_page = "toma_reportes"
        elif selected == "📊 Reportes":
            st.session_state.current_page = "reports"
        elif selected == "⚙️ Configuración":
            st.session_state.current_page = "settings"
        else:
            st.session_state.current_page = "home"
        
        # Botón de cierre de sesión
        if st.button("🚪 Cerrar sesión", width='stretch'):
            auth.logout()
            st.rerun()

def show_home():
    """Muestra la página de inicio"""
    st.title("Bienvenido al Sistema de Gestión de QSOs")
    st.markdown("""
    ### 📊 Panel de Control
    
    Utilice el menú lateral para navegar por las diferentes secciones del sistema.
    """)

def show_gestion_usuarios():
    """Muestra la gestión de usuarios dentro de la sección de Gestión"""
    # El título ya no es necesario aquí ya que está en la pestaña
    
    # Inicializar servicio de email
    if 'email_service' not in st.session_state:
        st.session_state.email_service = EmailSender(db)
    
    email_service = st.session_state.email_service
    
    # Tabs para organizar funcionalidades
    tab1, tab2 = st.tabs(["📋 Lista de Usuarios", "➕ Crear Usuario"])
    
    with tab1:
        st.subheader("Lista de Usuarios")
        
        # Obtener usuarios
        users = db.get_all_users()
        
        if users is not None and len(users) > 0:
            for user in users:
                with st.expander(f"👤 {user.get('username', 'N/A')} ({user.get('role', 'operator')})", 
                              expanded=st.session_state.get(f"editing_user_{user['id']}", False)):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Nombre completo:** {user.get('full_name', 'N/A')}")
                        st.write(f"**Email:** {user.get('email', 'N/A')}")
                        st.write(f"**Rol:** {user.get('role', 'operator')}")
                        status_emoji = "✔️" if user.get('is_active', 0) else "❌"
                        status_text = "Activo" if user.get('is_active', 0) else "Inactivo"
                        st.write(f"**Estado:** {status_emoji} {status_text}")
                        st.write(f"**Creado:** {format_datetime(user.get('created_at'))}")
                        st.write(f"**Último inicio de sesión:** {format_datetime(user.get('last_login'))}")
                    
                    with col2:
                        # Botón para editar usuario
                        if st.button(f"✏️ Editar", key=f"edit_user_{user['id']}"):
                            st.session_state[f"editing_user_{user['id']}"] = True
                            st.rerun()
                        
                        # Botón para reenviar correo de bienvenida
                        if st.button(f"📧 Reenviar correo", key=f"resend_email_{user['id']}"):
                            try:
                                # Generar una contraseña temporal segura
                                import secrets
                                import string
                                
                                alphabet = string.ascii_letters + string.digits + string.punctuation
                                temp_password = ''.join(secrets.choice(alphabet) for i in range(12))
                                
                                # Actualizar la contraseña usando el método de la base de datos
                                # (ahora espera la contraseña en texto plano y se encarga del hashing)
                                db.change_password(user['username'], temp_password)
                                
                                # Enviar el correo de bienvenida
                                if email_service.send_user_credentials(user, temp_password):
                                    st.success(f"✅ Correo de bienvenida reenviado a {user.get('email', '')}")
                                    st.warning("⚠️ Se generó una nueva contraseña temporal. El usuario deberá cambiarla al iniciar sesión.")

                                else:
                                    st.error("❌ Error al enviar el correo. Verifica la configuración SMTP.")
                                    
                            except Exception as e:
                                st.error(f"❌ Error al procesar la solicitud: {str(e)}")
                        
                        # Botón para eliminar usuario (solo si no es admin)
                        if user.get('username') != 'admin':
                            if st.button(f"🗑️ Eliminar", key=f"delete_user_{user['id']}"):
                                try:
                                    db.delete_user(user['id'])
                                    st.success(f"Usuario {user.get('username', '')} eliminado")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al eliminar usuario: {str(e)}")
                        else:
                            st.info("👑 Usuario administrador protegido")
                    
                    # Formulario de edición si está activado
                    if st.session_state.get(f"editing_user_{user['id']}", False):
                        st.markdown("---")
                        st.subheader("✏️ Editar Usuario")
                        
                        with st.form(f"edit_user_form_{user['id']}"):
                            edit_full_name = st.text_input("Nombre completo:", value=user.get('full_name', ''))
                            edit_email = st.text_input("Email:", value=user.get('email', ''))
                            edit_role = st.selectbox("Rol:", ["operator", "admin"], 
                                                   index=0 if user.get('role') == 'operator' else 1)
                            edit_is_active = st.toggle("Cuenta activa", 
                                                     value=bool(user.get('is_active', 1)),
                                                     help="Desactiva para bloquear el acceso de este usuario")
                            
                            # Opción para cambiar contraseña
                            change_password = st.checkbox("Cambiar contraseña")
                            new_password = ""
                            confirm_new_password = ""
                            
                            if change_password:
                                new_password = st.text_input("Nueva contraseña:", type="password", 
                                                           help="Mínimo 8 caracteres, 1 mayúscula, 1 número, 1 carácter especial")
                                confirm_new_password = st.text_input("Confirmar nueva contraseña:", type="password")
                            
                            col_save, col_cancel = st.columns(2)
                            
                            with col_save:
                                save_changes = st.form_submit_button("💾 Guardar Cambios")
                            
                            with col_cancel:
                                cancel_edit = st.form_submit_button("❌ Cancelar")
                            
                            if save_changes:
                                # Validar campos obligatorios
                                if not edit_full_name or not edit_email:
                                    st.error("❌ Nombre completo y email son obligatorios")
                                else:
                                    # Validar contraseña si se va a cambiar
                                    password_valid = True
                                    if change_password:
                                        if new_password != confirm_new_password:
                                            st.error("❌ Las contraseñas no coinciden")
                                            password_valid = False
                                        else:
                                            from utils import validate_password
                                            is_valid, message = validate_password(new_password)
                                            if not is_valid:
                                                st.error(f"❌ {message}")
                                                password_valid = False
                                    
                                    if password_valid:
                                        try:
                                            # Actualizar información del usuario
                                            db.update_user(
                                                user_id=user['id'],
                                                full_name=edit_full_name,
                                                email=edit_email,
                                                role=edit_role,
                                                is_active=edit_is_active
                                            )
                                            
                                            # Cambiar contraseña si se solicitó
                                            if change_password:
                                                import hashlib
                                                password_hash = hashlib.sha256(new_password.encode()).hexdigest()
                                                db.change_password(user['username'], password_hash)
                                            
                                            st.success("✅ Usuario actualizado exitosamente")
                                            import time
                                            time.sleep(2)
                                            
                                            # Limpiar estado de edición
                                            del st.session_state[f"editing_user_{user['id']}"]
                                            st.rerun()
                                            
                                        except Exception as e:
                                            st.error(f"❌ Error al actualizar usuario: {str(e)}")
                            elif cancel_edit:
                                # Cancelar edición
                                del st.session_state[f"editing_user_{user['id']}"]
                                st.rerun()
        else:
            st.info("No hay usuarios registrados")
    
    with tab2:
        st.subheader("Crear Nuevo Usuario")
        
        with st.form("create_user_form"):
            new_username = st.text_input("Nombre de usuario:")
            new_full_name = st.text_input("Nombre completo:")
            new_email = st.text_input("Email:")
            new_password = st.text_input("Contraseña:", type="password", 
                                      help="Mínimo 8 caracteres, 1 mayúscula, 1 número, 1 carácter especial")
            confirm_password = st.text_input("Confirmar contraseña:", type="password")
            new_role = st.selectbox("Rol:", ["operator", "admin"])
            
            submit_create = st.form_submit_button("✅ Crear Usuario")
            
            if submit_create:
                if new_username and new_full_name and new_email and new_password and confirm_password:
                    # Validar que el nombre de usuario no exista
                    if db.user_exists(new_username):
                        st.error("❌ El nombre de usuario ya está en uso")
                    # Validar que el correo no exista
                    elif db.email_exists(new_email):
                        st.error("❌ El correo electrónico ya está registrado")
                    # Validar que las contraseñas coincidan
                    elif new_password != confirm_password:
                        st.error("❌ Las contraseñas no coinciden")
                    else:
                        # Validar fortaleza de la contraseña
                        from utils import validate_password
                        is_valid, message = validate_password(new_password)
                        
                        if not is_valid:
                            st.error(f"❌ {message}")
                        else:
                            try:
                                # Crear usuario usando el método de autenticación
                                user_id = auth.db.create_user(
                                    username=new_username,
                                    password=new_password,
                                    full_name=new_full_name,
                                    email=new_email,
                                    role=new_role
                                )
                                
                                if user_id:
                                    st.success("✅ Usuario creado exitosamente")
                                    
                                    # Mostrar información del usuario creado
                                    st.info(f"""
                                    **Usuario creado:**
                                    - **Nombre de usuario:** {new_username}
                                    - **Nombre completo:** {new_full_name}
                                    - **Email:** {new_email}
                                    - **Rol:** {new_role}
                                    """)
                                    
                                    # Enviar email de bienvenida
                                    user_data = {
                                        'username': new_username,
                                        'full_name': new_full_name,
                                        'email': new_email,
                                        'role': new_role
                                    }
                                    
                                    if email_service.send_user_credentials(user_data, new_password):
                                        st.success("📧 Email de bienvenida enviado")
                                    else:
                                        st.warning("⚠️ Usuario creado pero no se pudo enviar el email de bienvenida")
                                    
                                    # Esperar un momento antes de recargar para mostrar mensajes
                                    import time
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    st.error("❌ Error al crear usuario (posiblemente el usuario ya existe)")
                            except Exception as e:
                                st.error(f"❌ Error al enviar el correo de bienvenida al usuario {new_username} al correo {new_email}: {str(e)}")
                else:
                    st.error("❌ Por favor completa todos los campos")

# Variable para almacenar la pestaña activa
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = "👥 Usuarios"

# Función para cambiar de pestaña
def set_active_tab(tab_name):
    st.session_state.active_tab = tab_name

def show_gestion():
    """Muestra el panel de gestión con pestañas para diferentes secciones"""
    st.title("🔧 Gestión")
    
    # Crear pestañas
    tabs = ["👥 Usuarios", "📅 Eventos", "📍 Zonas", "📻 Radioexperimentadores"]
    
    # Crear botones de pestaña personalizados
    cols = st.columns(len(tabs))
    for i, tab in enumerate(tabs):
        with cols[i]:
            if st.button(tab, key=f"tab_{i}", width='stretch'):
                set_active_tab(tab)
    
    st.markdown("---")  # Línea separadora
    
    # Mostrar el contenido de la pestaña activa
    if st.session_state.active_tab == "👥 Usuarios":
        show_gestion_usuarios()
    elif st.session_state.active_tab == "📅 Eventos":
        show_gestion_eventos()
    elif st.session_state.active_tab == "📍 Zonas":
        show_gestion_zonas()
    elif st.session_state.active_tab == "📻 Radioexperimentadores":
        show_gestion_radioexperimentadores()

def show_gestion_eventos():
    """Muestra la gestión de eventos con pestañas para listar y crear eventos"""
    # Mostrar pestañas
    tab_lista, tab_crear = st.tabs(["📋 Lista de Eventos", "➕ Crear Evento"])
    
    with tab_lista:
        st.subheader("📅 Lista de Eventos")
        
        # Barra de búsqueda y filtros
        col1, col2 = st.columns([3, 1])
        with col1:
            busqueda = st.text_input("Buscar evento", "", placeholder="Buscar por nombre o ubicación...")
        with col2:
            mostrar_inactivos = st.checkbox("Mostrar inactivos", value=False)
        
        # Obtener eventos con filtros
        eventos = db.get_all_eventos(incluir_inactivos=mostrar_inactivos)
            
        if busqueda:
            busqueda = busqueda.lower()
            eventos = [e for e in eventos if 
                      busqueda in e['tipo'].lower() or 
                      busqueda in e.get('descripcion', '').lower()]
        
        if eventos:
            # Mostrar estadísticas rápidas
            activos = sum(1 for e in eventos if e.get('activo', 1) == 1)
            inactivos = len(eventos) - activos
            st.caption(f"Mostrando {len(eventos)} eventos ({activos} activos, {inactivos} inactivos)")
            
            # Mostrar eventos en una tabla
            for evento in eventos:
                # Determinar si estamos editando este evento
                is_editing = st.session_state.get(f'editing_evento_{evento["id"]}', False)
                
                with st.expander(
                    f"{'✅' if evento.get('activo', 1) == 1 else '⏸️'} {evento['tipo']}",
                    expanded=is_editing  # Expandir si está en modo edición
                ):
                    if not is_editing:
                        # Vista normal del evento
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            # Mostrar estado
                            estado = "Activo" if evento.get('activo', 1) == 1 else "Inactivo"
                            st.markdown(f"**Estado:** {estado}")
                            
                            # Mostrar descripción si existe
                            if evento.get('descripcion'):
                                st.markdown("**Descripción:**")
                                st.markdown(evento['descripcion'])
                        
                        with col2:
                            # Botones de acción
                            col_btn1, col_btn2 = st.columns(2)
                            
                            with col_btn1:
                                if st.button("✏️ Editar", key=f"edit_{evento['id']}", width='stretch'):
                                    st.session_state[f'editing_evento_{evento["id"]}'] = True
                                    st.rerun()
                            
                            with col_btn2:
                                estado_btn = "❌ Desactivar" if evento.get('activo', 1) == 1 else "✅ Activar"
                                if st.button(estado_btn, key=f"toggle_{evento['id']}", width='stretch'):
                                    nuevo_estado = 0 if evento.get('activo', 1) == 1 else 1
                                    db.update_evento(evento['id'], activo=nuevo_estado)
                                    st.success(f"Evento {'activado' if nuevo_estado == 1 else 'desactivado'} correctamente")
                                    time.sleep(2)
                                    st.rerun()
                            
                            # Botón de eliminar con confirmación
                            if st.button("🗑️ Eliminar", key=f"delete_{evento['id']}", 
                                       type="primary", width='stretch',
                                       help="Eliminar permanentemente este evento"):
                                # Mostrar diálogo de confirmación
                                if st.session_state.get(f'confirm_delete_{evento["id"]}') != True:
                                    st.session_state[f'confirm_delete_{evento["id"]}'] = True
                                    st.rerun()
                                else:
                                    if db.delete_evento(evento['id']):
                                        st.success("Evento eliminado correctamente")
                                        time.sleep(2)
                                        # Limpiar estado de confirmación
                                        if f'confirm_delete_{evento["id"]}' in st.session_state:
                                            del st.session_state[f'confirm_delete_{evento["id"]}']
                                        st.rerun()
                                    else:
                                        st.error("Error al eliminar el evento")
                                        if f'confirm_delete_{evento["id"]}' in st.session_state:
                                            del st.session_state[f'confirm_delete_{evento["id"]}']
                                        
                            # Mostrar mensaje de confirmación si es necesario
                            if st.session_state.get(f'confirm_delete_{evento["id"]}') == True:
                                st.warning("¿Estás seguro de que quieres eliminar este evento? Esta acción no se puede deshacer.")
                                if st.button("✅ Confirmar eliminación", key=f"confirm_del_{evento['id']}", 
                                           type="primary", width='stretch'):
                                    if db.delete_evento(evento['id']):
                                        st.success("Evento eliminado correctamente")
                                        time.sleep(2)
                                        # Limpiar estado de confirmación
                                        if f'confirm_delete_{evento["id"]}' in st.session_state:
                                            del st.session_state[f'confirm_delete_{evento["id"]}']
                                        st.rerun()
                                    else:
                                        st.error("Error al eliminar el evento")
                                
                                if st.button("❌ Cancelar", key=f"cancel_del_{evento['id']}", 
                                           width='stretch'):
                                    del st.session_state[f'confirm_delete_{evento["id"]}']
                                    st.rerun()
                    else:
                        # Mostrar formulario de edición
                        with st.form(f"edit_evento_{evento['id']}"):
                            # Obtener datos actuales del evento
                            evento_data = db.get_evento(evento['id'])
                            
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                nombre = st.text_input("Nombre del evento", value=evento_data['tipo'])
                                descripcion = st.text_area("Descripción", value=evento_data.get('descripcion', ''))
                                #ubicacion = st.text_input("Ubicación", value=evento_data.get('ubicacion', ''))
                            
                            with col2:
                                activo = st.checkbox("Activo", value=bool(evento_data.get('activo', 1)))
                            
                            # Botones del formulario
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                if st.form_submit_button("💾 Guardar cambios", width='stretch'):
                                    try:
                                        # Actualizar el evento
                                        if db.update_evento(
                                            evento_id=evento['id'],
                                            tipo=nombre,
                                            descripcion=descripcion,
                                            activo=1 if activo else 0
                                        ):
                                            st.success("✅ Evento actualizado correctamente")
                                            time.sleep(2)
                                            # Limpiar estado de edición
                                            del st.session_state[f'editing_evento_{evento["id"]}']
                                            st.rerun()
                                        else:
                                            st.error("❌ Error al actualizar el evento")
                                    except Exception as e:
                                        st.error(f"Error al actualizar el evento: {str(e)}")
                            
                            with col2:
                                if st.form_submit_button("❌ Cancelar", type="secondary", width='stretch'):
                                    # Cancelar edición
                                    del st.session_state[f'editing_evento_{evento["id"]}']
                                    st.rerun()
            
            if not eventos:
                st.info("No se encontraron eventos que coincidan con los criterios de búsqueda")
        else:
            st.info("No hay eventos registrados")
    
    with tab_crear:
        show_crear_evento()

def show_crear_evento():
    """Muestra el formulario para crear o editar un tipo de evento"""
    # Verificar si estamos en modo edición
    is_editing = 'editing_evento' in st.session_state
    evento = None
    
    if is_editing:
        st.subheader("✏️ Editar Tipo de Evento")
        # Obtener datos del evento a editar
        evento = db.get_evento(st.session_state['editing_evento'])
        if not evento:
            st.error("Tipo de evento no encontrado")
            del st.session_state['editing_evento']
            return
    else:
        st.subheader("➕ Crear Nuevo Tipo de Evento")
    
    with st.form("evento_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            tipo = st.text_input("Tipo de evento", 
                               value=evento['tipo'] if evento else "",
                               placeholder="Ej: Retransmisión, Facebook, etc.")
            
            descripcion = st.text_area("Descripción",
                                    value=evento.get('descripcion', '') if evento else "",
                                    placeholder="Descripción opcional del tipo de evento")
        
        with col2:
            st.write("")
            st.write("")
            activo = st.checkbox("Activo", value=bool(evento.get('activo', 1)) if evento else True)
        
        # Botones del formulario
        col1, col2 = st.columns(2)
        
        with col1:
            if st.form_submit_button("💾 Guardar"):
                if not tipo:
                    st.error("El tipo de evento es obligatorio")
                else:
                    try:
                        if is_editing:
                            # Actualizar evento existente
                            if db.update_evento(
                                evento_id=evento['id'],
                                tipo=tipo,
                                descripcion=descripcion,
                                activo=1 if activo else 0
                            ):
                                st.success("✅ Tipo de evento actualizado correctamente")
                                time.sleep(2)
                                del st.session_state['editing_evento']
                                st.rerun()
                            else:
                                st.error("❌ Error al actualizar el tipo de evento")
                        else:
                            # Crear nuevo tipo de evento
                            evento_id = db.create_evento(
                                tipo=tipo,
                                descripcion=descripcion if descripcion else None
                            )
                            
                            if evento_id:
                                st.success("✅ Tipo de evento creado exitosamente")
                                time.sleep(2)
                                st.rerun()
                    except Exception as e:
                        st.error(f"Error al {'guardar' if is_editing else 'crear'} el tipo de evento: {str(e)}")
        
        with col2:
            if st.form_submit_button("❌ Cancelar"):
                if is_editing:
                    del st.session_state['editing_evento']
                st.rerun()

def show_reports():
    """Muestra la sección de reportes"""
    st.title("📊 Reportes")
    st.write("Aquí se mostrarán los reportes de QSOs")

def show_settings():
    """Muestra la configuración del sistema"""
    st.title("⚙️ Configuración del Sistema")
    
    # Pestañas para las diferentes configuraciones
    tab1, tab2 = st.tabs(["Correo Electrónico", "Opciones del Sistema"])
    
    with tab1:
        st.header("Configuración SMTP")
        st.markdown("Configura los parámetros del servidor de correo para el envío de notificaciones.")
        
        # Obtener configuración actual
        current_config = db.get_smtp_settings()
        
        with st.form("smtp_settings_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                server = st.text_input("Servidor SMTP*", 
                                     value=current_config.get('server', 'smtp.gmail.com') if current_config else 'smtp.gmail.com')
                port = st.number_input("Puerto*", 
                                     min_value=1, 
                                     max_value=65535, 
                                     value=current_config.get('port', 587) if current_config else 587)
                from_email = st.text_input("Correo remitente*", 
                                         value=current_config.get('from_email', '') if current_config else '')
            
            with col2:
                username = st.text_input("Usuario*", 
                                       value=current_config.get('username', '') if current_config else '')
                password = st.text_input("Contraseña*", 
                                       type="password",
                                       value="")
                use_tls = st.checkbox("Usar TLS/SSL", 
                                    value=bool(current_config.get('use_tls', True)) if current_config else True)
            
            # Botón para probar la configuración
            test_col1, test_col2, _ = st.columns([1, 1, 3])
            
            if test_col1.form_submit_button("Probar configuración"):
                try:
                    # Actualizar temporalmente la configuración para la prueba
                    test_config = {
                        'server': server,
                        'port': port,
                        'username': username,
                        'password': password if password else current_config.get('password', ''),
                        'use_tls': use_tls,
                        'from_email': from_email
                    }
                    
                    # Probar conexión
                    with st.spinner("Probando conexión con el servidor SMTP..."):
                        email_sender = EmailSender(db)
                        server_conn, _ = email_sender.get_smtp_connection()
                        server_conn.quit()
                        st.success("Conexión exitosa con el servidor SMTP")
                        
                except Exception as e:
                    st.error(f"Error al conectar con el servidor SMTP: {str(e)}")
            
            # Botón para guardar la configuración
            if test_col2.form_submit_button("Guardar configuración"):
                try:
                    # Usar la contraseña existente si no se proporcionó una nueva
                    password_to_save = password if password else current_config.get('password', '')
                    
                    db.update_smtp_settings(
                        server=server,
                        port=port,
                        username=username,
                        password=password_to_save,
                        use_tls=use_tls,
                        from_email=from_email
                    )
                    st.success("✅ Configuración guardada correctamente")
                    time.sleep(2)  # Pequeña pausa para mostrar el mensaje
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Error al guardar la configuración: {str(e)}")
    
    with tab2:
        st.header("Opciones del Sistema")
        st.write("Configuración general del sistema.")
        # Aquí puedes agregar más opciones de configuración en el futuro

def show_toma_reportes():
    """Muestra la sección de Toma de Reportes"""
    st.title("📝 Toma de Reportes")
    st.markdown("### Registro de Reportes")
    
    st.markdown("""
    <div style="background-color: #f0f8ff; padding: 15px; border-radius: 10px; border-left: 4px solid #1f77b4; margin-bottom: 20px;">
        <h4 style="color: #1f77b4; margin-top: 0;">📋 Configuración de Parámetros</h4>
        <p style="margin-bottom: 10px;">
            <strong>Selecciona los parámetros iniciales</strong> para la generación de reportes. 
            Estos valores se utilizarán como <strong>configuración predeterminada</strong> en todos tus registros.
        </p>
        <p style="margin-bottom: 5px;">
            <strong>📅 Fecha del Reporte:</strong> Establece la fecha para el reporte actual. 
            Por defecto se muestra la fecha del sistema.
        </p>
        <p style="margin-bottom: 0;">
            <strong>📋 Tipo de Boletín:</strong> Selecciona el tipo de boletín para clasificar 
            tu reporte. Las opciones disponibles se cargan automáticamente 
            desde la configuración del sistema.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Inicializar el estado del expander y parámetros si no existen
    if 'expander_abierto' not in st.session_state:
        st.session_state.expander_abierto = True  # Siempre inicia expandido
    if 'parametros_reporte' not in st.session_state:
        st.session_state.parametros_reporte = {}
    
    # Resetear el estado del expander si se recarga la página
    if 'just_saved' in st.session_state and st.session_state.just_saved:
        st.session_state.expander_abierto = False
        st.session_state.just_saved = False
    
    # Mostrar parámetros guardados si existen
    if st.session_state.parametros_reporte:
        st.info(f"📅 **Fecha de Reporte:** {st.session_state.parametros_reporte['fecha_reporte']} | "
                f"📋 **Tipo de Reporte:** {st.session_state.parametros_reporte['tipo_reporte']} | "
                f"🖥️ **Sistema Preferido:** {st.session_state.parametros_reporte['sistema_preferido'] or 'Ninguno'} | "
                f"📝 **Pre-Registros:** {st.session_state.parametros_reporte['pre_registro']}")
    
    # Formulario de parámetros de captura - Siempre expandido al inicio
    with st.expander("📋 Parámetros de Captura", expanded=st.session_state.expander_abierto):
        with st.form("reporte_form"):
            # Campos del formulario en el orden solicitado
            fecha_actual = datetime.now().date()
            fecha = st.date_input("Fecha de Reporte", fecha_actual)
            
            # Mostrar advertencia si la fecha no es la actual
            if fecha != fecha_actual:
                st.warning("⚠️ Los reportes se están capturando con fecha distinta a la actual y así serán guardados.")
            
            # Obtener la lista de eventos activos
            try:
                eventos = db.get_all_eventos()
                opciones_eventos = [e['tipo'] for e in eventos]
                if not opciones_eventos:
                    opciones_eventos = ["Actividad de Radio"]  # Valor por defecto si no hay eventos
                    st.warning("No se encontraron tipos de eventos configurados")
            except Exception as e:
                st.error(f"Error al cargar los tipos de eventos: {str(e)}")
                opciones_eventos = ["Actividad de Radio"]  # Valor por defecto en caso de error
                
            tipo_reporte = st.selectbox(
                "Tipo de Reporte",
                opciones_eventos,
                index=0
            )
            
            # Obtener la lista de sistemas para el selectbox
            try:
                sistemas_dict = db.get_sistemas()
                opciones_sistemas = sorted(list(sistemas_dict.keys()))  # Ordenar alfabéticamente
                if not opciones_sistemas:
                    st.error("No se encontraron sistemas configurados en la base de datos")
                    opciones_sistemas = ["ASL"]
            except Exception as e:
                st.error(f"Error al cargar los sistemas: {str(e)}")
                opciones_sistemas = ["ASL"]
            
            # Obtener el sistema actual del usuario si existe
            sistema_actual = None
            if 'user' in st.session_state and 'sistema_preferido' in st.session_state.user:
                sistema_actual = st.session_state.user['sistema_preferido']
            
            # Si no hay sistema actual, usar 'ASL' como predeterminado
            sistema_default = sistema_actual if sistema_actual in opciones_sistemas else (opciones_sistemas[0] if opciones_sistemas else "ASL")
                
            sistema_preferido = st.selectbox(
                "Sistema Preferido *",
                opciones_sistemas,
                index=opciones_sistemas.index(sistema_default) if sistema_default in opciones_sistemas else 0,
                help="Selecciona un sistema de la lista"
            )
            
            # Campo Pre-registro con slider
            # Obtener el valor guardado del usuario o usar 1 como predeterminado
            pre_registro_guardado = 1
            if 'user' in st.session_state and st.session_state.user and 'id' in st.session_state.user:
                usuario = db.get_user_by_id(st.session_state.user['id'])
                if usuario and 'pre_registro' in usuario and usuario['pre_registro'] is not None:
                    pre_registro_guardado = usuario['pre_registro']
            
            pre_registro = st.slider(
                "Pre-Registros",
                min_value=1,
                max_value=10,
                value=pre_registro_guardado,
                help=f"Valor actual: {pre_registro_guardado}. Selecciona un valor entre 1 y 10 para el pre-registro"
            )
            
            # Botones del formulario centrados
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    guardar = st.form_submit_button("💾 Guardar Parámetros", type="primary", use_container_width=True)
                with col_btn2:
                    cancelar = st.form_submit_button("❌ Cancelar", type="secondary", use_container_width=True)
            
            if guardar:
                try:
                    # Validar que se haya seleccionado un sistema
                    if not sistema_preferido:
                        st.error("Por favor selecciona un Sistema Preferido")
                        st.session_state.expander_abierto = True  # Mantener expandido si hay error
                        st.stop()
                    
                    # Marcar que se acaba de guardar para cerrar el expander
                    st.session_state.just_saved = True
                        
                    # Obtener el ID del usuario actual
                    user_id = st.session_state.user['id']
                    
                    # Actualizar los datos del usuario
                    db.update_user(
                        user_id=user_id,
                        sistema_preferido=sistema_preferido,
                        pre_registro=pre_registro
                    )
                    
                    # Guardar parámetros en la sesión
                    st.session_state.parametros_reporte = {
                        'fecha_reporte': fecha.strftime('%d/%m/%Y'),
                        'tipo_reporte': tipo_reporte,
                        'sistema_preferido': sistema_preferido,
                        'pre_registro': pre_registro
                    }
                    
                    st.success("✅ Parámetros guardados correctamente")
                    # Cerrar el expander después de guardar
                    st.session_state.expander_abierto = False
                    time.sleep(2)
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Error al guardar los parámetros: {str(e)}")
                    st.stop()
            
            if cancelar:
                st.session_state.expander_abierto = False
                st.rerun()
    
    # Mostrar tabla de pre-registros si los parámetros están guardados
    if st.session_state.parametros_reporte and not st.session_state.expander_abierto:
        st.markdown("### Pre-Registros")
        
        # Inicializar la variable de sesión para los registros si no existe
        if 'registros' not in st.session_state:
            st.session_state.registros = []
        if 'registros_editados' not in st.session_state:
            st.session_state.registros_editados = False
        
        # Crear un formulario para los pre-registros
        form_submitted = False
        with st.form("pre_registros_form"):
            # Crear una tabla con los campos de entrada
            for i in range(st.session_state.parametros_reporte['pre_registro']):
                # Usar CSS personalizado para alinear perfectamente los campos
                st.markdown(f"""
                <style>
                .row-{i} {{
                    display: flex;
                    gap: 20px;
                    margin-bottom: 20px;
                    align-items: flex-start;
                }}
                .field-indicativo-{i} {{
                    flex: 3;
                    display: flex;
                    flex-direction: column;
                }}
                .field-sistema-{i} {{
                    flex: 1;
                    display: flex;
                    flex-direction: column;
                }}
                .field-indicativo-{i} label {{
                    font-weight: bold;
                    margin-bottom: 5px;
                    color: #1f77b4;
                }}
                .field-sistema-{i} label {{
                    font-weight: bold;
                    margin-bottom: 5px;
                    color: #1f77b4;
                }}
                </style>
                <div class="row-{i}">
                    <div class="field-indicativo-{i}"></div>
                    <div class="field-sistema-{i}"></div>
                </div>
                """, unsafe_allow_html=True)

                col1, col2 = st.columns([3, 1])

                with col1:
                    # Usar el valor guardado o vacío si no existe
                    valor_guardado = st.session_state.get(f'indicativo_{i}', '')
                    st.markdown(f"**Indicativo {i+1}**")
                    indicativo = st.text_input(
                        f"Indicativo {i+1}",
                        key=f"indicativo_{i}",
                        value=valor_guardado,
                        placeholder="Ej: XE1ABC",
                        label_visibility="collapsed"
                    )

                with col2:
                    # Obtener la lista de sistemas desde la base de datos
                    try:
                        sistemas_dict = db.get_sistemas()
                        opciones_sistemas = sorted(list(sistemas_dict.keys()))  # Usar campo 'codigo'
                        if not opciones_sistemas:
                            st.error("No se encontraron sistemas configurados en la base de datos")
                            opciones_sistemas = ["ASL"]
                    except Exception as e:
                        st.error(f"Error al cargar los sistemas: {str(e)}")
                        opciones_sistemas = ["ASL"]

                    sistema_guardado = st.session_state.get(f'sistema_{i}', st.session_state.parametros_reporte['sistema_preferido'])
                    # Asegurarse de que el sistema guardado esté en la lista de opciones
                    try:
                        indice = opciones_sistemas.index(sistema_guardado)
                    except ValueError:
                        indice = 0

                    st.markdown("**Sistema**")
                    sistema = st.selectbox(
                        f"Sistema {i+1}",
                        opciones_sistemas,
                        key=f"sistema_{i}",
                        index=indice,
                        label_visibility="collapsed"
                    )

            # Botón para pre-registrar todos
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                form_submitted = st.form_submit_button(
                    "📋 Pre-Registrar Todos",
                    type="primary",
                    use_container_width=True
                )
        
        # Procesar el formulario cuando se envía
        if form_submitted:
            # Recopilar todos los registros
            registros_guardar = []
            indicativos_invalidos = []
            indicativos_incompletos = []

            # Procesar cada indicativo
            for i in range(st.session_state.parametros_reporte['pre_registro']):
                indicativo = st.session_state.get(f'indicativo_{i}', '').strip().upper()
                if not indicativo:  # Saltar si está vacío
                    continue

                # Validar el indicativo
                result = utils.validar_call_sign(indicativo)

                # Verificar que sea válido Y completo
                if not result["indicativo"]:
                    indicativos_invalidos.append(indicativo)
                    continue

                if not result["completo"]:
                    indicativos_incompletos.append(indicativo)
                    continue

                # Crear registro base con datos mínimos
                registro = {
                    'indicativo': indicativo,
                    'sistema': st.session_state.get(f'sistema_{i}', st.session_state.parametros_reporte['sistema_preferido']),
                    'fecha': st.session_state.parametros_reporte['fecha_reporte'],
                    'tipo_reporte': st.session_state.parametros_reporte['tipo_reporte'],
                    'senal': '59'  # Valor por defecto para la señal
                }

                # Obtener datos del radioexperimentador si existe
                radioexperimentador = db.get_radioexperimentador_por_indicativo(indicativo)

                if radioexperimentador:
                    # Guardar los datos completos del radioexperimentador para depuración
                    registro['radioexperimentador_data'] = dict(radioexperimentador)

                    # Si existe en la base de datos, actualizar el registro con los datos
                    registro.update({
                        'nombre_operador': radioexperimentador.get('nombre_completo', ''),  # ← CORREGIDO: usar 'nombre_completo'
                        'apellido_paterno': radioexperimentador.get('apellido_paterno', ''),
                        'apellido_materno': radioexperimentador.get('apellido_materno', ''),
                        'estado': radioexperimentador.get('estado', ''),           # ← Correcto
                        'ciudad': radioexperimentador.get('municipio', ''),        # ← CORREGIDO: usar 'municipio' en lugar de 'ciudad'
                        'colonia': radioexperimentador.get('colonia', ''),
                        'codigo_postal': radioexperimentador.get('codigo_postal', ''),
                        'telefono': radioexperimentador.get('telefono', ''),
                        'email': radioexperimentador.get('email', ''),
                        'zona': radioexperimentador.get('zona', '')               # ← CORREGIDO: usar zona de BD o calcular
                    })

                    # Si no hay zona en BD, calcularla automáticamente
                    if not registro['zona']:
                        prefijo = indicativo[:3]
                        if prefijo.startswith('XE') and len(indicativo) >= 3 and indicativo[2] in ['1', '2', '3']:
                            registro['zona'] = f"XE{indicativo[2]}"
                else:
                    # Si no existe, crear un registro básico
                    registro = {
                        'indicativo': indicativo,
                        'nombre_operador': '',
                        'estado': '',
                        'ciudad': '',
                        'zona': '',
                        'sistema': st.session_state.get(f'sistema_{i}', st.session_state.parametros_reporte['sistema_preferido']),
                        'fecha': st.session_state.parametros_reporte['fecha_reporte'],
                        'tipo_reporte': st.session_state.parametros_reporte['tipo_reporte'],
                        'senal': '59'  # Valor por defecto para la señal
                    }

                    # Intentar determinar la zona basada en el prefijo
                    prefijo = indicativo[:3]  # Tomar los primeros 3 caracteres como prefijo
                    if prefijo.startswith('XE') and len(indicativo) >= 3 and indicativo[2] in ['1', '2', '3']:
                        registro['zona'] = f"XE{indicativo[2]}"

                registros_guardar.append(registro)

            # Mostrar errores de validación si los hay
            if indicativos_invalidos:
                st.error(f"❌ Los siguientes indicativos no son válidos: {', '.join(indicativos_invalidos)}")
                return

            if indicativos_incompletos:
                st.error(f"⚠️ Los siguientes indicativos están incompletos (necesitan sufijo): {', '.join(indicativos_incompletos)}")
                return

            # Solo proceder si hay registros válidos
            if not registros_guardar:
                st.warning("⚠️ No hay registros válidos para procesar. Complete todos los indicativos correctamente.")
                return

            # Actualizar la variable de sesión con los nuevos registros
            st.session_state.registros = registros_guardar
            st.session_state.expander_abierto = False  # Minimizar el formulario

            # Limpiar los campos del formulario
            for i in range(st.session_state.parametros_reporte['pre_registro']):
                if f'indicativo_{i}' in st.session_state:
                    del st.session_state[f'indicativo_{i}']
                if f'sistema_{i}' in st.session_state:
                    del st.session_state[f'sistema_{i}']

            st.rerun()
        
        # Mostrar la tabla de registros si hay registros guardados
        if 'registros' in st.session_state and st.session_state.registros:
            st.markdown("---")
            st.subheader("📋 Indicativos Registrados")
            
            # Crear una tabla con los registros
            import pandas as pd
            
            # Verificar si hay registros para mostrar
            if not st.session_state.registros:
                st.info("No hay registros para mostrar. Agrega indicativos usando el formulario superior.")
                return
                
            # Crear DataFrame con los datos de los registros
            df = pd.DataFrame(st.session_state.registros)

            # Seleccionar y ordenar columnas para mostrar
            columnas_a_mostrar = ['indicativo', 'nombre_operador', 'estado', 'ciudad', 'zona', 'sistema', 'senal']
            columnas_disponibles = [col for col in columnas_a_mostrar if col in df.columns]

            # Mostrar la tabla editable con estilos
            st.markdown("### ✏️ Tabla Editable - Corrige los datos antes de guardar")

            # Crear configuración para la tabla editable
            column_config = {
                'indicativo': st.column_config.TextColumn(
                    'Indicativo',
                    help="Indicativo del radioexperimentador (solo lectura)",
                    disabled=True  # No editable
                ),
                'nombre_operador': st.column_config.TextColumn(
                    'Operador',
                    help="Nombre completo del operador"
                ),
                'estado': st.column_config.TextColumn(
                    'Estado',
                    help="Estado donde reside"
                ),
                'ciudad': st.column_config.TextColumn(
                    'Ciudad',
                    help="Ciudad o municipio"
                ),
                'zona': st.column_config.TextColumn(
                    'Zona',
                    help="Zona geográfica (XE1, XE2, XE3, etc.)"
                ),
                'sistema': st.column_config.SelectboxColumn(
                    'Sistema',
                    help="Sistema de comunicación utilizado",
                    options=['HF', 'ASL', 'IRLP', 'DMR', 'Fusion', 'D-Star', 'P25', 'M17'],
                    required=True
                ),
                'senal': st.column_config.NumberColumn(
                    'Señal',
                    help="Calidad de señal reportada",
                    min_value=1,
                    max_value=99,
                    step=1,
                    format="%d"
                )
            }

            # Mostrar tabla editable
            edited_df = st.data_editor(
                df[columnas_disponibles],
                column_config=column_config,
                hide_index=True,
                use_container_width=True,
                height=min(400, 35 * len(df) + 40),  # Ajustar altura automáticamente
                key="editable_table"
            )

            # Detectar cambios en la tabla
            if not edited_df.equals(df):
                # Actualizar los registros en la sesión con los cambios
                st.session_state.registros_editados = True
                st.success("✅ Tabla editada. Haz clic en '💾 Guardar en Base de Datos' para aplicar los cambios.")

                # Actualizar los registros con los datos editados
                for i, registro_editado in enumerate(edited_df.to_dict('records')):
                    if i < len(st.session_state.registros):
                        # Actualizar el registro existente
                        st.session_state.registros[i].update(registro_editado)

            # Mostrar resumen y botones de acción
            st.caption(f"Total de registros: {len(df)}")

            # Mostrar información sobre edición
            if st.session_state.get('registros_editados', False):
                st.info("💡 **Nota:** Los cambios se aplicarán cuando guardes en la base de datos.")

            # Sección de depuración
            with st.expander("🔍 Datos de depuración (solo desarrollo)", expanded=False):
                st.write("### Datos completos de los indicativos consultados en la base de datos")
                for idx, registro in enumerate(st.session_state.registros, 1):
                    st.write(f"#### Indicativo {idx}: {registro.get('indicativo', 'N/A')}")

                    # Mostrar datos básicos del registro
                    st.write("**Datos del registro:**")
                    st.json({
                        'indicativo': registro.get('indicativo', ''),
                        'sistema': registro.get('sistema', ''),
                        'fecha': registro.get('fecha', ''),
                        'tipo_reporte': registro.get('tipo_reporte', ''),
                        'senal': registro.get('senal', '')
                    })

                    # Mostrar datos del radioexperimentador si se consultaron
                    if 'radioexperimentador_data' in registro:
                        st.write("**Datos completos del radioexperimentador desde la base de datos:**")
                        st.json(registro['radioexperimentador_data'])

                    st.markdown("---")
            
            # Botones de acción
            col1, col2 = st.columns(2)

            with col1:
                # Botón para guardar en la base de datos
                if st.button("💾 Guardar en Base de Datos", type="primary", use_container_width=True):
                    try:
                        # Verificar que haya registros para guardar
                        if not st.session_state.registros:
                            st.error("❌ No hay registros para guardar")
                            return

                        # Guardar cada registro en la base de datos
                        registros_guardados = 0
                        for registro in st.session_state.registros:
                            # Validar que el registro tenga los campos obligatorios
                            if not registro.get('indicativo') or not registro.get('tipo_reporte'):
                                st.error(f"❌ El registro de {registro.get('indicativo', 'desconocido')} no tiene los campos obligatorios")
                                continue

                            db.save_reporte({
                                'indicativo': registro['indicativo'],
                                'nombre_operador': registro.get('nombre_operador', ''),
                                'estado': registro.get('estado', ''),
                                'ciudad': registro.get('ciudad', ''),
                                'zona': registro.get('zona', ''),
                                'sistema': registro.get('sistema', ''),
                                'senal': registro.get('senal', '59'),
                                'fecha_reporte': registro.get('fecha', ''),
                                'tipo_reporte': registro.get('tipo_reporte', '')
                            })
                            registros_guardados += 1

                        if registros_guardados > 0:
                            st.success(f"✅ {registros_guardados} registro(s) guardado(s) correctamente en la base de datos")
                            # Limpiar los registros y el estado de edición
                            st.session_state.registros = []
                            st.session_state.registros_editados = False
                            st.rerun()
                        else:
                            st.error("❌ No se pudo guardar ningún registro. Verifica que tengan los campos obligatorios.")

                    except Exception as e:
                        st.error(f"❌ Error al guardar en la base de datos: {str(e)}")

            with col2:
                # Botón para deshacer cambios
                if st.session_state.get('registros_editados', False):
                    if st.button("↩️ Deshacer Cambios", type="secondary", use_container_width=True):
                        # Recargar los registros originales desde la sesión
                        st.session_state.registros_editados = False
                        st.success("✅ Cambios deshechos. Los datos originales han sido restaurados.")
                        st.rerun()

                # Botón para limpiar los registros
                if st.button("🗑️ Limpiar todos los registros", type="secondary", use_container_width=True):
                    st.session_state.registros = []
                    st.session_state.registros_editados = False
                    st.session_state.expander_abierto = True  # Mostrar el formulario de nuevo
                    st.rerun()


def obtener_datos_para_reporte(indicativo, sistema):
    """
    Obtiene los datos necesarios para un reporte basado en el indicativo y sistema proporcionados.
    
    Args:
        indicativo (str): El indicativo del radioexperimentador
        sistema (str): El sistema de comunicación utilizado
        
    Returns:
        dict: Un diccionario con los datos del reporte
    """
    # Obtener datos del radioexperimentador si existe
    radioexperimentador = db.get_radioexperimentador_por_indicativo(indicativo)
    
    if radioexperimentador:
        # Si existe en la base de datos, copiar todos los campos relevantes
        datos = {
            'indicativo': radioexperimentador.get('indicativo', indicativo),
            'nombre_operador': radioexperimentador.get('nombre_completo', ''),  # ← CORREGIDO: usar 'nombre_completo'
            'apellido_paterno': radioexperimentador.get('apellido_paterno', ''),
            'apellido_materno': radioexperimentador.get('apellido_materno', ''),
            'estado': radioexperimentador.get('estado', ''),           # ← Correcto
            'ciudad': radioexperimentador.get('municipio', ''),        # ← CORREGIDO: usar 'municipio'
            'colonia': radioexperimentador.get('colonia', ''),
            'codigo_postal': radioexperimentador.get('codigo_postal', ''),
            'telefono': radioexperimentador.get('telefono', ''),
            'email': radioexperimentador.get('email', ''),
            'zona': radioexperimentador.get('zona', ''),               # ← Usar zona de BD o calcular
            'sistema': sistema,  # Usar el sistema proporcionado
            'senal': '59',  # Valor por defecto para la señal
            'activo': radioexperimentador.get('activo', 1)  # Mantener el estado activo/inactivo
        }

        # Si no hay zona en BD, calcularla automáticamente
        if not datos['zona']:
            if len(indicativo) >= 3:
                prefijo = indicativo[:3]
                if prefijo.startswith('XE') and indicativo[2] in ['1', '2', '3']:
                    datos['zona'] = f"XE{indicativo[2]}"
    else:
        # Si no existe, crear un registro básico
        datos = {
            'indicativo': indicativo,
            'nombre_operador': '',
            'estado': '',
            'ciudad': '',
            'zona': '',
            'sistema': sistema,
            'senal': '59'  # Valor por defecto para la señal
        }
        
        # Intentar determinar la zona basada en el prefijo
        if len(indicativo) >= 3:
            prefijo = indicativo[:3]
            if prefijo.startswith('XE') and indicativo[2] in ['1', '2', '3']:
                datos['zona'] = f"XE{indicativo[2]}"
    
    return datos

def main():
    # Inicializar variables de sesión si no existen
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "home"
    
    # Verificar autenticación
    if 'user' not in st.session_state:
        # No mostrar barra lateral en el login
        st.set_page_config(
            page_title="Inicio de Sesión - QMS",
            page_icon="🔒",
            layout="centered"
        )
        auth.show_login()
    else:
        # Configurar página con barra lateral solo cuando está autenticado
        st.set_page_config(
            page_title="Sistema de Gestión de QSOs",
            page_icon="📻",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        # Mostrar la barra lateral solo cuando está autenticado
        show_sidebar()
        
        # Navegación
        current_page = st.session_state.get('current_page', 'home')
        
        if current_page == 'home':
            show_home()
        elif current_page == 'gestion':
            show_gestion()
        elif current_page == 'toma_reportes':
            show_toma_reportes()
        elif current_page == 'reports':
            show_reports()
        elif current_page == 'settings':
            show_settings()
        # Mantener compatibilidad con la navegación antigua
        elif current_page == 'users':
            st.session_state.current_page = 'gestion'
            st.rerun()

def show_gestion_zonas():
    """Muestra la gestión de zonas con pestañas para listar y crear zonas"""
    # Mostrar pestañas
    tab_lista, tab_crear = st.tabs(["📋 Lista de Zonas", "➕ Crear Zona"])
    
    with tab_lista:
        _show_lista_zonas()
    
    with tab_crear:
        _show_crear_zona()

def _show_lista_zonas():
    """Muestra la lista de zonas con opciones de búsqueda y filtrado"""
    st.subheader("📍 Lista de Zonas")
    
    # Barra de búsqueda y filtros
    col1, col2 = st.columns([3, 1])
    with col1:
        busqueda = st.text_input("Buscar zona", "", placeholder="Buscar por código o nombre...")
    with col2:
        mostrar_inactivas = st.checkbox("Mostrar inactivas", value=False)
    
    # Obtener zonas con filtros
    zonas = db.get_zonas(incluir_inactivas=mostrar_inactivas)
        
    if busqueda:
        busqueda = busqueda.lower()
        zonas = [z for z in zonas if 
                busqueda in z['zona'].lower() or 
                busqueda in z['nombre'].lower()]
    
    if zonas:
        # Mostrar estadísticas rápidas
        activas = sum(1 for z in zonas if z.get('activo', 1) == 1)
        inactivas = len(zonas) - activas
        st.caption(f"Mostrando {len(zonas)} zonas ({activas} activas, {inactivas} inactivas)")
        
        # Mostrar zonas en una tabla
        for zona in zonas:
            # Determinar si estamos editando esta zona
            is_editing = st.session_state.get(f'editing_zona_{zona["zona"]}', False)
            
            with st.expander(
                f"{'✅' if zona.get('activo', 1) == 1 else '⏸️'} {zona['zona']} - {zona['nombre']}",
                expanded=is_editing  # Expandir si está en modo edición
            ):
                if not is_editing:
                    # Vista normal de la zona
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        # Mostrar estado
                        estado = "Activa" if zona.get('activo', 1) == 1 else "Inactiva"
                        st.markdown(f"**Zona:** {zona['zona']}")
                        st.markdown(f"**Estado:** {estado}")
                    
                    with col2:
                        # Botones de acción
                        col_btn1, col_btn2 = st.columns(2)
                        
                        with col_btn1:
                            if st.button("✏️ Editar", key=f"edit_{zona['zona']}", width='stretch'):
                                st.session_state[f'editing_zona_{zona["zona"]}'] = True
                                st.rerun()
                        
                        with col_btn2:
                            estado_btn = "❌ Desactivar" if zona.get('activo', 1) == 1 else "✅ Activar"
                            if st.button(estado_btn, key=f"toggle_{zona['zona']}", width='stretch'):
                                nuevo_estado = 0 if zona.get('activo', 1) == 1 else 1
                                db.update_zona(zona['zona'], activo=nuevo_estado)
                                st.success(f"Zona {'activada' if nuevo_estado == 1 else 'desactivada'} correctamente")
                                time.sleep(2)
                                st.rerun()
                        
                        # Botón de eliminar con confirmación
                        if st.button("🗑️ Eliminar", key=f"delete_{zona['zona']}", 
                                   type="primary", width='stretch',
                                   help="Eliminar permanentemente esta zona"):
                            # Mostrar diálogo de confirmación
                            if st.session_state.get(f'confirm_delete_{zona["zona"]}') != True:
                                st.session_state[f'confirm_delete_{zona["zona"]}'] = True
                                st.rerun()
                            else:
                                if db.delete_zona(zona['zona']):
                                    st.success("Zona eliminada correctamente")
                                    time.sleep(2)
                                    # Limpiar estado de confirmación
                                    if f'confirm_delete_{zona["zona"]}' in st.session_state:
                                        del st.session_state[f'confirm_delete_{zona["zona"]}']
                                    st.rerun()
                                else:
                                    st.error("Error al eliminar la zona")
                                    if f'confirm_delete_{zona["zona"]}' in st.session_state:
                                        del st.session_state[f'confirm_delete_{zona["zona"]}']
                        
                        # Mostrar mensaje de confirmación si es necesario
                        if st.session_state.get(f'confirm_delete_{zona["zona"]}') == True:
                            st.warning("¿Estás seguro de que quieres eliminar esta zona? Esta acción no se puede deshacer.")
                            if st.button("✅ Confirmar eliminación", key=f"confirm_del_{zona['zona']}", 
                                       type="primary", width='stretch'):
                                if db.delete_zona(zona['zona']):
                                    st.success("Zona eliminada correctamente")
                                    time.sleep(2)
                                    # Limpiar estado de confirmación
                                    if f'confirm_delete_{zona["zona"]}' in st.session_state:
                                        del st.session_state[f'confirm_delete_{zona["zona"]}']
                                    st.rerun()
                                else:
                                    st.error("Error al eliminar la zona")
                            
                            if st.button("❌ Cancelar", key=f"cancel_del_{zona['zona']}", 
                                       width='stretch'):
                                del st.session_state[f'confirm_delete_{zona["zona"]}']
                                st.rerun()
                else:
                    # Mostrar formulario de edición
                    with st.form(f"edit_zona_{zona['zona']}"):
                        # Obtener datos actuales de la zona
                        zona_data = db.get_zona(zona['zona'])
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            zona_valor = st.text_input("Zona", value=zona_data['zona'])
                            nombre = st.text_input("Nombre de la zona", value=zona_data['nombre'])
                        
                        with col2:
                            st.write("")
                            st.write("")
                            activo = st.checkbox("Activa", value=bool(zona_data.get('activo', 1)))
                        
                        # Botones del formulario
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            if st.form_submit_button("💾 Guardar cambios", use_container_width=True):
                                if not zona_valor or not nombre:
                                    st.error("La zona y el nombre son campos obligatorios")
                                else:
                                    try:
                                        # Actualizar la zona
                                        if db.update_zona(
                                            zona_original=zona['zona'],
                                            zona=zona_valor,
                                            nombre=nombre,
                                            activo=1 if activo else 0
                                        ):
                                            st.success("✅ Zona actualizada correctamente")
                                            time.sleep(2)
                                            # Limpiar estado de edición
                                            del st.session_state[f'editing_zona_{zona["zona"]}']
                                            st.rerun()
                                        else:
                                            st.error("❌ Error al actualizar la zona. Verifica que la zona no esté duplicada.")
                                    except Exception as e:
                                        st.error(f"Error al actualizar la zona: {str(e)}")
                        
                        with col2:
                            if st.form_submit_button("❌ Cancelar", type="secondary", width='stretch'):
                                # Cancelar edición
                                del st.session_state[f'editing_zona_{zona["zona"]}']
                                st.rerun()
        
        if not zonas:
            st.info("No se encontraron zonas que coincidan con los criterios de búsqueda")
    else:
        st.info("No hay zonas registradas")

def show_gestion_radioexperimentadores():
    """Muestra la gestión de radioexperimentadores con pestañas"""
    tab1, tab2, tab3 = st.tabs([
        "📋 Lista de Radioexperimentadores",
        "➕ Agregar Radioexperimentador",
        "📤 Importar desde Excel"
    ])
    
    with tab1:
        _show_lista_radioexperimentadores()
    
    with tab2:
        _show_crear_radioexperimentador()
    
    with tab3:
        _show_importar_radioexperimentadores()

@st.cache_data(ttl=300)  # Cache por 5 minutos
def _get_radioexperimentadores(incluir_inactivos=False):
    """Obtiene la lista de radioexperimentadores con caché"""
    try:
        return db.get_radioexperimentadores(incluir_inactivos=incluir_inactivos)
    except Exception as e:
        st.error(f"Error al cargar los radioexperimentadores: {str(e)}")
        return []

def _show_lista_radioexperimentadores():
    """Muestra la lista de radioexperimentadores con opciones de búsqueda y acciones"""
    st.header("📋 Lista de Radioexperimentadores")
    
    # Inicializar variables de sesión si no existen
    if 'editando_radio_id' not in st.session_state:
        st.session_state.editando_radio_id = None
    if 'eliminando_radio_id' not in st.session_state:
        st.session_state.eliminando_radio_id = None
    
    # Si estamos en modo edición, mostrar el formulario de edición
    if st.session_state.editando_radio_id:
        _mostrar_formulario_edicion(st.session_state.editando_radio_id)
        return
    
    # Barra de búsqueda y filtros
    col1, col2 = st.columns([3, 1])
    
    with col1:
        busqueda = st.text_input("Buscar por indicativo, nombre o municipio:", "")
    
    with col2:
        incluir_inactivos = st.checkbox("Mostrar inactivos", False, key="mostrar_inactivos_radio")
    
    # Obtener y mostrar la lista de radioexperimentadores
    try:
        radioexperimentadores = []
        
        if busqueda:
            # Primero intentar buscar por indicativo exacto
            busqueda_upper = busqueda.upper()
            radio = db.get_radioexperimentador_por_indicativo(busqueda_upper)
            
            if radio:
                # Si encontramos por indicativo exacto, mostramos solo ese
                radioexperimentadores = [radio]
            else:
                radioexperimentadores = db.get_radioexperimentadores(
                    incluir_inactivos=incluir_inactivos
                )
                
                # Filtrar localmente para mejor control de la búsqueda
                busqueda_terms = busqueda_upper.split()
                radioexperimentadores = [
                    r for r in radioexperimentadores
                    if (busqueda_upper in r['indicativo'].upper() or
                        all(term in r['nombre_completo'].upper() for term in busqueda_terms) or
                        busqueda_upper in (r['municipio'] or '').upper() or
                        busqueda_upper in (r['estado'] or '').upper())
                ]
        else:
            # Si no hay búsqueda, obtener todos los activos (o inactivos si está marcado)
            radioexperimentadores = _get_radioexperimentadores(
                incluir_inactivos=incluir_inactivos
            )
        
        # Mostrar contador de resultados
        total_aficionados = len(radioexperimentadores)
        st.subheader(f"📊 {total_aficionados} aficionado{'s' if total_aficionados != 1 else ''} encontrado{'s' if total_aficionados != 1 else ''}")
        
        if radioexperimentadores:
            # Mostrar la lista en un formato de tabla mejorado
            for radio in radioexperimentadores:
                with st.expander(f"{radio['indicativo']} - {radio['nombre_completo']}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Municipio:** {radio['municipio'] or 'No especificado'}")
                        st.write(f"**Estado:** {radio['estado'] or 'No especificado'}")
                        st.write(f"**País:** {radio['pais'] or 'No especificado'}")
                        
                    with col2:
                        st.write(f"**Tipo de licencia:** {radio['tipo_licencia'] or 'No especificado'}")
                        st.write(f"**Estatus:** {radio['estatus'] or 'No especificado'}")
                        st.write(f"**Activo:** {'Sí' if radio.get('activo', 1) == 1 else 'No'}")
                    
                    # Mostrar botones de acción
                    col_btn1, col_btn2, col_btn3 = st.columns(3)
                    
                    with col_btn1:
                        if st.button(f"✏️ Editar", key=f"editar_{radio['id']}"):
                            st.session_state.editando_radio_id = radio['id']
                            st.rerun()
                    
                    with col_btn2:
                        if radio.get('activo', 1) == 1:
                            if st.button(f"⏸️ Desactivar", key=f"desactivar_{radio['id']}"):
                                try:
                                    if db.delete_radioexperimentador(radio['id']):
                                        st.success(f"Radioexperimentador {radio['indicativo']} desactivado correctamente")
                                        time.sleep(2)
                                        st.rerun()
                                    else:
                                        st.error("No se pudo desactivar el radioexperimentador")
                                except Exception as e:
                                    st.error(f"Error al desactivar: {str(e)}")
                        else:
                            if st.button(f"▶️ Activar", key=f"activar_{radio['id']}"):
                                try:
                                    if db.activar_radioexperimentador(radio['id']):
                                        st.success(f"Radioexperimentador {radio['indicativo']} activado correctamente")
                                        time.sleep(2)
                                        st.rerun()
                                    else:
                                        st.error("No se pudo activar el radioexperimentador")
                                except Exception as e:
                                    st.error(f"Error al activar: {str(e)}")
                    
                    with col_btn3:
                        if st.button(f"🗑️ Eliminar", key=f"eliminar_{radio['id']}"):
                            st.session_state.eliminando_radio_id = radio['id']
                            st.rerun()
                    
                    # Mostrar confirmación de eliminación si corresponde
                    if st.session_state.get('eliminando_radio_id') == radio['id']:
                        st.warning("¿Estás seguro de que deseas eliminar permanentemente este registro? Esta acción no se puede deshacer.")
                        
                        col_conf1, col_conf2 = st.columns(2)
                        
                        with col_conf1:
                            if st.button("✅ Confirmar eliminación", type="primary", key=f"confirmar_eliminar_{radio['id']}"):
                                try:
                                    if db.delete_radioexperimentador(radio['id'], force_delete=True):
                                        st.success(f"Radioexperimentador {radio['indicativo']} eliminado permanentemente")
                                        del st.session_state.eliminando_radio_id
                                        time.sleep(2)
                                        st.rerun()
                                    else:
                                        st.error("No se pudo eliminar el radioexperimentador")
                                except Exception as e:
                                    st.error(f"Error al eliminar: {str(e)}")
                        
                        with col_conf2:
                            if st.button("❌ Cancelar", key=f"cancelar_eliminar_{radio['id']}"):
                                if 'eliminando_radio_id' in st.session_state:
                                    del st.session_state.eliminando_radio_id
                                st.rerun()
        else:
            st.info("No se encontraron radioexperimentadores que coincidan con los criterios de búsqueda")
    
    except Exception as e:
        st.error(f"Error al cargar la lista de radioexperimentadores: {str(e)}")

@st.cache_data(ttl=300)  # Cache por 5 minutos
def _get_radioexperimentador_por_id(radio_id):
    """Obtiene un radioexperimentador por su ID con caché"""
    try:
        return db.get_radioexperimentador_por_id(radio_id)
    except Exception as e:
        st.error(f"Error al cargar el radioexperimentador: {str(e)}")
        return None

def _mostrar_formulario_edicion(radio_id):
    """Muestra el formulario para editar un radioexperimentador existente"""
    st.header("✏️ Editar Radioexperimentador")
    
    try:
        # Obtener los datos actuales del radioexperimentador
        radio = _get_radioexperimentador_por_id(radio_id)
        
        if not radio:
            st.error("No se encontró el radioexperimentador especificado")
            if st.button("Volver a la lista"):
                del st.session_state.editando_radio_id
                st.rerun()
            return
        
        # Mostrar el indicativo como texto (no editable)
        st.write(f"**Indicativo:** {radio['indicativo']}")
        
        # Campos editables
        with st.form(key='editar_radio_form'):
            nombre = st.text_input("Nombre completo", value=radio['nombre_completo'])
            
            col1, col2 = st.columns(2)
            with col1:
                municipio = st.text_input("Municipio", value=radio['municipio'] or '')
            with col2:
                estado = st.text_input("Estado", value=radio['estado'] or '')
            
            pais = st.text_input("País", value=radio['pais'] or 'México')
            
            # Convertir fechas de string a date si existen
            fecha_nacimiento = None
            if radio['fecha_nacimiento']:
                try:
                    fecha_nacimiento = datetime.strptime(radio['fecha_nacimiento'], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass
            
            fecha_expedicion = None
            if radio['fecha_expedicion']:
                try:
                    fecha_expedicion = datetime.strptime(radio['fecha_expedicion'], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass
            
            col1, col2 = st.columns(2)
            with col1:
                fecha_nac = st.date_input("Fecha de Nacimiento", value=fecha_nacimiento)
            with col2:
                fecha_exp = st.date_input("Fecha de Expedición", value=fecha_expedicion)
            
            nacionalidad = st.text_input("Nacionalidad", value=radio['nacionalidad'] or 'MEXICANA')
            
            genero = st.selectbox("Género", ["MASCULINO", "FEMENINO", "OTRO"], 
                                index=0 if not radio['genero'] else ["MASCULINO", "FEMENINO", "OTRO"].index(radio['genero'])
                                if radio['genero'] in ["MASCULINO", "FEMENINO", "OTRO"] else 0)
            
            tipo_licencia = st.selectbox("Tipo de Licencia", 
                                       ["NOVATO", "AVANZADO", "GENERAL", "EXTRA"],
                                       index=0 if not radio['tipo_licencia'] else 
                                       ["NOVATO", "AVANZADO", "GENERAL", "EXTRA"].index(radio['tipo_licencia'])
                                       if radio['tipo_licencia'] in ["NOVATO", "AVANZADO", "GENERAL", "EXTRA"] else 0)
            
            estatus = st.selectbox("Estatus", 
                                 ["ACTIVO", "INACTIVO", "SUSPENDIDO", "EN TRÁMITE"],
                                 index=0 if not radio['estatus'] else 
                                 ["ACTIVO", "INACTIVO", "SUSPENDIDO", "EN TRÁMITE"].index(radio['estatus'])
                                 if radio['estatus'] in ["ACTIVO", "INACTIVO", "SUSPENDIDO", "EN TRÁMITE"] else 0)
            
            observaciones = st.text_area("Observaciones", value=radio['observaciones'] or '')
            
            # Botones de acción
            col1, col2, col3 = st.columns([1, 1, 2])
            
            with col1:
                if st.form_submit_button("💾 Guardar Cambios", type="primary"):
                    # Validar campos obligatorios
                    if not nombre or not radio['indicativo']:
                        st.error("Los campos de nombre e indicativo son obligatorios")
                    else:
                        # Función para formatear texto en formato oración
                        def formatear_oracion(texto):
                            if not texto or not isinstance(texto, str):
                                return texto
                            return ' '.join(word.capitalize() for word in texto.split())
                        
                        # Preparar datos para actualizar
                        datos_actualizados = {
                            'nombre_completo': formatear_oracion(nombre),
                            'municipio': formatear_oracion(municipio) if municipio else None,
                            'estado': formatear_oracion(estado) if estado else None,
                            'pais': formatear_oracion(pais) if pais else None,
                            'fecha_nacimiento': fecha_nac.strftime('%Y-%m-%d') if fecha_nac else None,
                            'nacionalidad': nacionalidad.upper() if nacionalidad else None,  # Se mantiene en mayúsculas
                            'genero': genero.upper() if genero else None,  # Se mantiene en mayúsculas
                            'tipo_licencia': tipo_licencia.upper() if tipo_licencia else None,  # Se mantiene en mayúsculas
                            'fecha_expedicion': fecha_exp.strftime('%Y-%m-%d') if fecha_exp else None,
                            'estatus': estatus.upper() if estatus else 'ACTIVO',  # Se mantiene en mayúsculas
                            'observaciones': observaciones,  # No se formatea para mantener el formato original
                            'activo': 1 if estatus == "ACTIVO" else 0
                        }
                        
                        try:
                            if db.update_radioexperimentador(radio['id'], datos_actualizados):
                                st.success("¡Los cambios se guardaron correctamente!")
                                time.sleep(2)
                                del st.session_state.editando_radio_id
                                st.rerun()
                            else:
                                st.error("No se pudieron guardar los cambios. Intente nuevamente.")
                        except Exception as e:
                            st.error(f"Error al guardar los cambios: {str(e)}")
            
            with col2:
                if st.form_submit_button("❌ Cancelar"):
                    del st.session_state.editando_radio_id
                    st.rerun()
            
            with col3:
                if st.form_submit_button("🗑️ Eliminar Radioexperimentador", type="secondary"):
                    st.session_state.eliminando_radio_id = radio['id']
                    st.session_state.volver_a_editar = True
                    st.rerun()
    
    except Exception as e:
        st.error(f"Error al cargar el formulario de edición: {str(e)}")
        if st.button("Volver a la lista"):
            if 'editando_radio_id' in st.session_state:
                del st.session_state.editando_radio_id
            st.rerun()

def _show_importar_radioexperimentadores():
    """Muestra el formulario para importar radioexperimentadores desde Excel"""
    st.header("📤 Importar Radioexperimentadores desde Excel")
    
    # Sección de descarga de plantilla
    st.subheader("📥 Descargar plantilla")
    st.write("Descarga esta plantilla para asegurar el formato correcto:")
    
    # Crear un DataFrame de ejemplo
    import pandas as pd
    from io import BytesIO
    
    # Datos de ejemplo
    data = {
        'INDICATIVO': ['XE1ABC', 'XE2DEF'],
        'NOMBRE': ['JUAN PEREZ LOPEZ', 'MARIA GONZALEZ'],
        'MUNICIPIO': ['TOLUCA', 'GUADALAJARA'],
        'ESTADO': ['MEXICO', 'JALISCO'],
        'PAIS': ['MEXICO', 'MEXICO'],
        'FECHA_NACIMIENTO': ['1980-01-15', '1985-05-20'],
        'NACIONALIDAD': ['MEXICANA', 'MEXICANA'],
        'GENERO': ['MASCULINO', 'FEMENINO'],
        'TIPO_LICENCIA': ['NOVATO', 'AVANZADO'],
        'FECHA_EXPEDICION': ['2023-01-01', '2023-01-01'],
        'ESTATUS': ['ACTIVO', 'ACTIVO'],
        'OBSERVACIONES': ['', '']
    }
    
    df_template = pd.DataFrame(data)
    
    # Crear un buffer para el archivo Excel
    output = BytesIO()
    
    try:
        # Intentar usar xlsxwriter si está disponible
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_template.to_excel(writer, index=False, sheet_name='Plantilla')
            
            # Formato de la hoja solo disponible con xlsxwriter
            workbook = writer.book
            worksheet = writer.sheets['Plantilla']
            
            # Ajustar el ancho de las columnas
            for i, col in enumerate(df_template.columns):
                max_length = max(df_template[col].astype(str).apply(len).max(), len(col)) + 2
                worksheet.set_column(i, i, max_length)
    except ImportError:
        # Si xlsxwriter no está instalado, usar openpyxl (menos opciones de formato)
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_template.to_excel(writer, index=False, sheet_name='Plantilla')
    
    # Crear botón de descarga
    st.download_button(
        label="📥 Descargar Plantilla de Ejemplo",
        data=output.getvalue(),
        file_name="plantilla_radioexperimentadores.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    st.markdown("---")
    st.subheader("Subir archivo")
    st.info("""
    **Instrucciones para la importación:**
    1. Usa la plantilla de arriba o asegúrate que tu archivo Excel tenga al menos estas columnas:
       - `INDICATIVO` (obligatorio)
       - `NOMBRE` o `NOMBRE COMPLETO` (obligatorio)
    2. La primera fila debe contener los nombres de las columnas.
    3. Los demás campos son opcionales.
    """)
    
    # Usar una clave de sesión para controlar la importación
    if 'import_in_progress' not in st.session_state:
        st.session_state.import_in_progress = False
        st.session_state.import_complete = False
        st.session_state.import_errors = []
    
    uploaded_file = st.file_uploader("Selecciona un archivo Excel", type=["xlsx", "xls"])
    
    # Mostrar vista previa del archivo
    if uploaded_file is not None and not st.session_state.import_in_progress and not st.session_state.import_complete:
        st.subheader("Vista previa del archivo")
        try:
            import pandas as pd
            df_preview = pd.read_excel(uploaded_file)
            st.dataframe(df_preview.head(5))  # Mostrar solo las primeras 5 filas
            st.caption(f"Total de filas en el archivo: {len(df_preview)}")
            
            # Mostrar botón de confirmación
            if st.button("✅ Confirmar e importar", type="primary"):
                st.session_state.import_in_progress = True
                
                # Guardar el archivo temporalmente
                import tempfile
                import os
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_file_path = tmp_file.name
                
                try:
                    # Importar el archivo
                    with st.spinner('Procesando archivo...'):
                        total, creados, actualizados, errores = db.import_radioexperimentadores_from_excel(tmp_file_path)
                    
                    # Mostrar resultados
                    st.success(f"✅ Importación completada con éxito!")
                    st.info(f"• Total de registros: {total}")
                    st.info(f"• Nuevos registros: {creados}")
                    st.info(f"• Registros actualizados: {actualizados}")
                    
                    if errores:
                        st.session_state.import_errors = errores
                        with st.expander(f"⚠️ {len(errores)} errores encontrados (haz clic para ver)", expanded=False):
                            for error in errores[:10]:  # Mostrar solo los primeros 10 errores
                                st.error(f"• {error}")
                            if len(errores) > 10:
                                st.warning(f"... y {len(errores) - 10} errores más.")
                    
                    st.balloons()  # Efecto de animación al completar
                    st.session_state.import_complete = True
                    
                except Exception as e:
                    st.error(f"❌ Error al importar el archivo: {str(e)}")
                    st.session_state.import_in_progress = False
                finally:
                    # Limpiar archivo temporal
                    try:
                        os.unlink(tmp_file_path)
                    except:
                        pass
                    
        except Exception as e:
            st.error(f"❌ No se pudo leer el archivo: {str(e)}")
    
    # Mostrar botón para reiniciar la importación
    if st.session_state.import_complete:
        if st.button("🔄 Realizar nueva importación"):
            st.session_state.import_in_progress = False
            st.session_state.import_complete = False
            st.session_state.import_errors = []
            st.rerun()
            
        # Botón para descargar reporte de errores si hay errores
        if st.session_state.import_errors:
            import pandas as pd
            df_errores = pd.DataFrame({"Errores": st.session_state.import_errors})
            st.download_button(
                label="📥 Descargar reporte de errores",
                data=df_errores.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'),
                file_name="errores_importacion_radioexperimentadores.csv",
                mime="text/csv"
            )

def _show_crear_zona():
    """Muestra el formulario para crear o editar una zona"""
    # Verificar si estamos en modo edición
    if 'editing_zona' in st.session_state:
        st.subheader("✏️ Editar Zona")
        zona_data = db.get_zona(st.session_state.editing_zona)
        
        if not zona_data:
            st.error("No se encontró la zona a editar")
            del st.session_state.editing_zona
            return
            
        # Inicializar valores por defecto
        zona_valor = zona_data.get('zona', '')
        nombre = zona_data.get('nombre', '')
        activo = zona_data.get('activo', 1) == 1
    else:
        st.subheader("➕ Crear Nueva Zona")
        # Valores por defecto para nueva zona
        zona_valor = ""
        nombre = ""
        activo = True
    
    # Formulario para crear/editar zona
    with st.form("zona_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            zona_valor = st.text_input("Zona*", value=zona_valor, 
                                     disabled='editing_zona' in st.session_state)
            nombre = st.text_input("Nombre de la zona*", value=nombre)
        
        with col2:
            st.write("")
            st.write("")
            activo = st.checkbox("Activa", value=activo)
        
        # Botones del formulario
        col1, col2 = st.columns(2)
        
        with col1:
            if st.form_submit_button("💾 Guardar Zona", width='stretch'):
                if not zona_valor or not nombre:
                    st.error("Los campos marcados con * son obligatorios")
                else:
                    try:
                        if 'editing_zona' in st.session_state:
                            # Actualizar zona existente
                            if db.update_zona(
                                zona_original=st.session_state.editing_zona,
                                zona=zona_valor,
                                nombre=nombre,
                                activo=1 if activo else 0
                            ):
                                st.success("✅ Zona actualizada correctamente")
                                time.sleep(2)
                                # Limpiar estado de edición
                                del st.session_state.editing_zona
                                st.rerun()
                            else:
                                st.error("❌ Error al actualizar la zona. Verifica que la zona no esté duplicada.")
                        else:
                            # Crear nueva zona
                            if db.create_zona(
                                zona=zona_valor,
                                nombre=nombre
                            ):
                                st.success("✅ Zona creada correctamente")
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error("❌ Error al crear la zona. Verifica que la zona no esté duplicada.")
                    except Exception as e:
                        st.error(f"Error al procesar la solicitud: {str(e)}")
        
        with col2:
            if st.form_submit_button("❌ Cancelar", type="secondary", width='stretch'):
                if 'editing_zona' in st.session_state:
                    del st.session_state.editing_zona
                st.rerun()

@st.cache_data(ttl=86400)  # Cache por 24 horas
def _get_estados_cached():
    """Obtiene la lista de estados con caché mejorada"""
    try:
        # Usar una variable de sesión para cachear los estados
        if 'estados_cache' not in st.session_state:
            estados = db.get_estados()
            estados_list = [""] + [e['nombre'] for e in estados]
            st.session_state.estados_cache = estados_list
        return st.session_state.estados_cache
    except Exception as e:
        st.error(f"Error al cargar los estados: {str(e)}")
        return [""]

@st.cache_data(ttl=86400)  # Cache por 24 horas
def _get_opciones_estaticas():
    """Obtiene opciones estáticas con caché"""
    # Usar una variable de sesión para cachear las opciones
    if 'opciones_estaticas' not in st.session_state:
        st.session_state.opciones_estaticas = {
            'paises': ['México', 'Estados Unidos', 'España', 'Colombia', 'Argentina', 'Otro'],
            'genero': ['', 'MASCULINO', 'FEMENINO', 'OTRO'],
            'licencia': ['', 'NOVATO', 'AVANZADO', 'GENERAL', 'EXTRA'],
            'estatus': ['ACTIVO', 'INACTIVO', 'SUSPENDIDO', 'EN TRÁMITE']
        }
    return st.session_state.opciones_estaticas

def _formatear_oracion(texto):
    """Formatea el texto en formato oración"""
    if not texto or not isinstance(texto, str):
        return texto
    return ' '.join(word.capitalize() for word in texto.split())

@st.cache_data(ttl=3600, show_spinner=False)
def _get_estados_list():
    """Obtiene la lista de estados con caché"""
    try:
        estados = db.get_estados()
        return [""] + list(estados.values())
    except Exception as e:
        st.error(f"Error al cargar los estados: {str(e)}")
        return [""]

@st.cache_data(ttl=3600, show_spinner=False)
def _get_estados_cached():
    """Obtiene la lista de estados con caché mejorada"""
    try:
        estados = db.get_estados()
        # get_estados() returns a list of state names, not a dictionary
        return [""] + [estado for estado in estados if estado]  # Filter out any None or empty values
    except Exception as e:
        st.error(f"Error al cargar los estados: {str(e)}")
        return [""]

def _show_crear_radioexperimentador():
    """Muestra el formulario para crear un nuevo radioexperimentador con mejoras de rendimiento"""
    st.header("🆕 Agregar Nuevo Radioexperimentador")
    
    # Obtener opciones estáticas y estados con caché
    opciones = _get_opciones_estaticas()
    estados_list = _get_estados_cached()
    
    # Inicializar el estado del formulario si no existe
    if 'form_data' not in st.session_state:
        st.session_state.form_data = {
            'indicativo': '',
            'nombre': '',
            'municipio': '',
            'estado': '',
            'pais': 'México',
            'fecha_nac': None,
            'fecha_exp': None,
            'nacionalidad': 'MEXICANA',
            'genero': '',
            'tipo_licencia': '',
            'estatus': 'ACTIVO',
            'observaciones': ''
        }
    
    # Obtener referencias directas a los datos del formulario
    form_data = st.session_state.form_data
    
# Cargar opciones estáticas una sola vez
    opciones = _get_opciones_estaticas()
    estados_list = _get_estados_cached()
    
    # Usar st.form para agrupar los campos
    with st.form(key='crear_radio_form'):
        col1, col2 = st.columns(2)
        
        with col1:
            # Usar st.text_input con key única para cada campo
            form_data['indicativo'] = st.text_input(
                "Indicativo*", 
                value=form_data['indicativo'],
                key='form_indicativo'
            )
            
            form_data['nombre'] = st.text_input(
                "Nombre completo*", 
                value=form_data['nombre'],
                key='form_nombre'
            )
            
            form_data['municipio'] = st.text_input(
                "Municipio", 
                value=form_data['municipio'],
                key='form_municipio'
            )
            
            # Estado con datos en caché
            estado_index = estados_list.index(form_data['estado']) if form_data['estado'] in estados_list else 0
            form_data['estado'] = st.selectbox(
                "Estado",
                estados_list,
                index=estado_index,
                key='form_estado'
            )
            
            pais_index = opciones['paises'].index(form_data['pais']) if form_data['pais'] in opciones['paises'] else 0
            form_data['pais'] = st.selectbox(
                "País",
                opciones['paises'],
                index=pais_index,
                key='form_pais'
            )
            
        with col2:
            form_data['fecha_nac'] = st.date_input(
                "Fecha de Nacimiento", 
                value=form_data['fecha_nac'],
                key='form_fecha_nac'
            )
            
            form_data['fecha_exp'] = st.date_input(
                "Fecha de Expedición", 
                value=form_data['fecha_exp'],
                key='form_fecha_exp'
            )
            
            form_data['nacionalidad'] = st.text_input(
                "Nacionalidad", 
                value=form_data['nacionalidad'],
                key='form_nacionalidad'
            )
            
            genero_index = opciones['genero'].index(form_data['genero']) if form_data['genero'] in opciones['genero'] else 0
            form_data['genero'] = st.selectbox(
                "Género", 
                opciones['genero'],
                index=genero_index,
                key='form_genero'
            )
            
            licencia_index = opciones['licencia'].index(form_data['tipo_licencia']) if form_data['tipo_licencia'] in opciones['licencia'] else 0
            form_data['tipo_licencia'] = st.selectbox(
                "Tipo de Licencia",
                opciones['licencia'],
                index=licencia_index,
                key='form_licencia'
            )
            
            estatus_index = opciones['estatus'].index(form_data['estatus']) if form_data['estatus'] in opciones['estatus'] else 0
            form_data['estatus'] = st.selectbox(
                "Estatus",
                opciones['estatus'],
                index=estatus_index,
                key='form_estatus'
            )
        
        form_data['observaciones'] = st.text_area(
            "Observaciones", 
            value=form_data['observaciones'],
            key='form_observaciones'
        )
        
        # Botones del formulario
        col_btn1, col_btn2, _ = st.columns([1, 1, 4])
        
        with col_btn1:
            guardar = st.form_submit_button("💾 Guardar", type="primary", width='stretch')
        
        with col_btn2:
            cancelar = st.form_submit_button("❌ Cancelar", type="secondary", width='stretch')
        
        # Procesar guardado o cancelación
        if guardar:
            # Validar campos obligatorios
            if not form_data['indicativo'] or not form_data['nombre']:
                st.error("Los campos marcados con * son obligatorios")
            else:
                # Validar formato del indicativo
                es_valido, mensaje_error = utils.validate_call_sign(form_data['indicativo'])
                if not es_valido:
                    st.error(f"Error en el indicativo: {mensaje_error}")
                    st.stop()  # Detener la ejecución para evitar procesamiento adicional
                try:
                    # Preparar datos para guardar
                    datos = {
                        'indicativo': form_data['indicativo'].upper(),
                        'nombre_completo': _formatear_oracion(form_data['nombre']),
                        'municipio': _formatear_oracion(form_data['municipio']) if form_data['municipio'] else None,
                        'estado': _formatear_oracion(form_data['estado']) if form_data['estado'] else None,
                        'pais': _formatear_oracion(form_data['pais']) if form_data['pais'] else None,
                        'fecha_nacimiento': form_data['fecha_nac'].strftime('%Y-%m-%d') if form_data['fecha_nac'] else None,
                        'nacionalidad': form_data['nacionalidad'].upper(),
                        'genero': form_data['genero'].upper() if form_data['genero'] else None,
                        'tipo_licencia': form_data['tipo_licencia'].upper() if form_data['tipo_licencia'] else None,
                        'fecha_expedicion': form_data['fecha_exp'].strftime('%Y-%m-%d') if form_data['fecha_exp'] else None,
                        'estatus': form_data['estatus'].upper(),
                        'observaciones': form_data['observaciones'],
                        'activo': 1 if form_data['estatus'] == 'ACTIVO' else 0
                    }
                    
                    # Intentar crear el radioexperimentador
                    with st.spinner('Guardando radioexperimentador...'):
                        radio_id = db.create_radioexperimentador(datos)
                    
                    if radio_id:
                        st.success("¡Radioexperimentador creado exitosamente!")
                        time.sleep(2)
                        # Limpiar el formulario después de guardar exitosamente
                        for key in st.session_state.form_data:
                            if key == 'pais':
                                st.session_state.form_data[key] = 'México'
                            elif key == 'estatus':
                                st.session_state.form_data[key] = 'ACTIVO'
                            elif key == 'nacionalidad':
                                st.session_state.form_data[key] = 'MEXICANA'
                            elif key in ['fecha_nac', 'fecha_exp']:
                                st.session_state.form_data[key] = None
                            else:
                                st.session_state.form_data[key] = ''
                        st.rerun()
                    else:
                        st.error("No se pudo crear el radioexperimentador. Verifica los datos e intenta nuevamente.")
                except Exception as e:
                    if "UNIQUE constraint failed: radioexperimentadores.indicativo" in str(e):
                        st.error("Ya existe un radioexperimentador con este indicativo.")
                    else:
                        st.error(f"Error al crear el radioexperimentador: {str(e)}")
        
        # Manejar cancelación
        if cancelar:
            # Restablecer el formulario a los valores por defecto sin recargar la página
            for key in st.session_state.form_data:
                if key in ['pais', 'estatus']:
                    st.session_state.form_data[key] = 'México' if key == 'pais' else 'ACTIVO'
                elif key in ['fecha_nac', 'fecha_exp']:
                    st.session_state.form_data[key] = None
                elif key == 'nacionalidad':
                    st.session_state.form_data[key] = 'MEXICANA'
                else:
                    st.session_state.form_data[key] = ''
            
            # Usar st.rerun() para forzar la actualización
            st.rerun()
        

if __name__ == "__main__":
    main()
