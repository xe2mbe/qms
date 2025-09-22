import streamlit as st
import sqlite3
import time
import secrets
import string
from time_utils import format_datetime
import hashlib
from datetime import datetime, timedelta
import pytz
from database import FMREDatabase
from auth import AuthManager
from email_sender import EmailSender
import utils

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
            use_container_width=False,  # Parámetro actualizado
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
        menu_options = ["🏠 Inicio", "📊 Reportes"]
        
        # Mostrar opciones de administración solo para administradores
        if user['role'] == 'admin':
            menu_options.extend(["🔧 Gestión", "⚙️ Configuración"])
            
        selected = st.selectbox("Navegación", menu_options)
        
        # Navegación
        if selected == "🔧 Gestión":
            st.session_state.current_page = "gestion"
        elif selected == "📊 Reportes":
            st.session_state.current_page = "reports"
        elif selected == "⚙️ Configuración":
            st.session_state.current_page = "settings"
        else:
            st.session_state.current_page = "home"
        
        # Botón de cierre de sesión
        if st.button("🚪 Cerrar sesión", use_container_width=True):
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
                                st.error(f"❌ Error al crear usuario: {str(e)}")
                else:
                    st.error("❌ Por favor completa todos los campos")

def show_gestion():
    """Muestra el panel de gestión con pestañas para diferentes secciones"""
    st.title("🔧 Gestión")
    
    # Crear pestañas
    tab1, tab2, tab3, tab4 = st.tabs([
        "👥 Usuarios", 
        "📅 Eventos", 
        "📍 Zonas", 
        "📻 Radioexperimentadores"
    ])
    
    with tab1:
        show_gestion_usuarios()
    
    with tab2:
        show_gestion_eventos()
    
    with tab3:
        show_gestion_zonas()
    
    with tab4:
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
                                if st.button("✏️ Editar", key=f"edit_{evento['id']}", use_container_width=True):
                                    st.session_state[f'editing_evento_{evento["id"]}'] = True
                                    st.rerun()
                            
                            with col_btn2:
                                estado_btn = "❌ Desactivar" if evento.get('activo', 1) == 1 else "✅ Activar"
                                if st.button(estado_btn, key=f"toggle_{evento['id']}", use_container_width=True):
                                    nuevo_estado = 0 if evento.get('activo', 1) == 1 else 1
                                    db.update_evento(evento['id'], activo=nuevo_estado)
                                    st.success(f"Evento {'activado' if nuevo_estado == 1 else 'desactivado'} correctamente")
                                    time.sleep(1)
                                    st.rerun()
                            
                            # Botón de eliminar con confirmación
                            if st.button("🗑️ Eliminar", key=f"delete_{evento['id']}", 
                                       type="primary", use_container_width=True,
                                       help="Eliminar permanentemente este evento"):
                                # Mostrar diálogo de confirmación
                                if st.session_state.get(f'confirm_delete_{evento["id"]}') != True:
                                    st.session_state[f'confirm_delete_{evento["id"]}'] = True
                                    st.rerun()
                                else:
                                    if db.delete_evento(evento['id']):
                                        st.success("Evento eliminado correctamente")
                                        time.sleep(1)
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
                                           type="primary", use_container_width=True):
                                    if db.delete_evento(evento['id']):
                                        st.success("Evento eliminado correctamente")
                                        time.sleep(1)
                                        # Limpiar estado de confirmación
                                        if f'confirm_delete_{evento["id"]}' in st.session_state:
                                            del st.session_state[f'confirm_delete_{evento["id"]}']
                                        st.rerun()
                                    else:
                                        st.error("Error al eliminar el evento")
                                
                                if st.button("❌ Cancelar", key=f"cancel_del_{evento['id']}", 
                                           use_container_width=True):
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
                                if st.form_submit_button("💾 Guardar cambios", use_container_width=True):
                                    try:
                                        # Actualizar el evento
                                        if db.update_evento(
                                            evento_id=evento['id'],
                                            tipo=nombre,
                                            descripcion=descripcion,
                                            activo=1 if activo else 0
                                        ):
                                            st.success("✅ Evento actualizado correctamente")
                                            time.sleep(1)
                                            # Limpiar estado de edición
                                            del st.session_state[f'editing_evento_{evento["id"]}']
                                            st.rerun()
                                        else:
                                            st.error("❌ Error al actualizar el evento")
                                    except Exception as e:
                                        st.error(f"Error al actualizar el evento: {str(e)}")
                            
                            with col2:
                                if st.form_submit_button("❌ Cancelar", type="secondary", use_container_width=True):
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
                                time.sleep(1)
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
                                time.sleep(1)
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
                            if st.button("✏️ Editar", key=f"edit_{zona['zona']}", use_container_width=True):
                                st.session_state[f'editing_zona_{zona["zona"]}'] = True
                                st.rerun()
                        
                        with col_btn2:
                            estado_btn = "❌ Desactivar" if zona.get('activo', 1) == 1 else "✅ Activar"
                            if st.button(estado_btn, key=f"toggle_{zona['zona']}", use_container_width=True):
                                nuevo_estado = 0 if zona.get('activo', 1) == 1 else 1
                                db.update_zona(zona['zona'], activo=nuevo_estado)
                                st.success(f"Zona {'activada' if nuevo_estado == 1 else 'desactivada'} correctamente")
                                time.sleep(1)
                                st.rerun()
                        
                        # Botón de eliminar con confirmación
                        if st.button("🗑️ Eliminar", key=f"delete_{zona['zona']}", 
                                   type="primary", use_container_width=True,
                                   help="Eliminar permanentemente esta zona"):
                            # Mostrar diálogo de confirmación
                            if st.session_state.get(f'confirm_delete_{zona["zona"]}') != True:
                                st.session_state[f'confirm_delete_{zona["zona"]}'] = True
                                st.rerun()
                            else:
                                if db.delete_zona(zona['zona']):
                                    st.success("Zona eliminada correctamente")
                                    time.sleep(1)
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
                                       type="primary", use_container_width=True):
                                if db.delete_zona(zona['zona']):
                                    st.success("Zona eliminada correctamente")
                                    time.sleep(1)
                                    # Limpiar estado de confirmación
                                    if f'confirm_delete_{zona["zona"]}' in st.session_state:
                                        del st.session_state[f'confirm_delete_{zona["zona"]}']
                                    st.rerun()
                                else:
                                    st.error("Error al eliminar la zona")
                            
                            if st.button("❌ Cancelar", key=f"cancel_del_{zona['zona']}", 
                                       use_container_width=True):
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
                                            time.sleep(1)
                                            # Limpiar estado de edición
                                            del st.session_state[f'editing_zona_{zona["zona"]}']
                                            st.rerun()
                                        else:
                                            st.error("❌ Error al actualizar la zona. Verifica que la zona no esté duplicada.")
                                    except Exception as e:
                                        st.error(f"Error al actualizar la zona: {str(e)}")
                        
                        with col2:
                            if st.form_submit_button("❌ Cancelar", type="secondary", use_container_width=True):
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
            radioexperimentadores = db.get_radioexperimentadores(
                incluir_inactivos=incluir_inactivos
            )
        
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
                                        time.sleep(1)
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
                                        time.sleep(1)
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
                                        time.sleep(1)
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

def _mostrar_formulario_edicion(radio_id):
    """Muestra el formulario para editar un radioexperimentador existente"""
    st.header("✏️ Editar Radioexperimentador")
    
    try:
        # Obtener los datos actuales del radioexperimentador
        radio = db.get_radioexperimentador_por_id(radio_id)
        
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
                        # Preparar datos para actualizar
                        datos_actualizados = {
                            'nombre_completo': nombre,
                            'municipio': municipio,
                            'estado': estado,
                            'pais': pais,
                            'fecha_nacimiento': fecha_nac.strftime('%Y-%m-%d') if fecha_nac else None,
                            'nacionalidad': nacionalidad,
                            'genero': genero,
                            'tipo_licencia': tipo_licencia,
                            'fecha_expedicion': fecha_exp.strftime('%Y-%m-%d') if fecha_exp else None,
                            'estatus': estatus,
                            'observaciones': observaciones,
                            'activo': 1 if estatus == "ACTIVO" else 0
                        }
                        
                        try:
                            if db.update_radioexperimentador(radio['id'], datos_actualizados):
                                st.success("¡Los cambios se guardaron correctamente!")
                                time.sleep(1)
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
            if st.form_submit_button("💾 Guardar Zona", use_container_width=True):
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
                                time.sleep(1)
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
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("❌ Error al crear la zona. Verifica que la zona no esté duplicada.")
                    except Exception as e:
                        st.error(f"Error al procesar la solicitud: {str(e)}")
        
        with col2:
            if st.form_submit_button("❌ Cancelar", type="secondary", use_container_width=True):
                if 'editing_zona' in st.session_state:
                    del st.session_state.editing_zona
                st.rerun()

def _show_crear_radioexperimentador():
    """Muestra el formulario para crear un nuevo radioexperimentador"""
    st.header("➕ Agregar Nuevo Radioexperimentador")
    
    with st.form(key='crear_radio_form'):
        # Campos del formulario
        col1, col2 = st.columns(2)
        
        with col1:
            indicativo = st.text_input("Indicativo", "")
            nombre = st.text_input("Nombre completo", "")
            municipio = st.text_input("Municipio", "")
            
            # Obtener la lista de estados desde la base de datos
            try:
                estados = db.get_estados()
                estado_seleccionado = st.selectbox(
                    "Estado",
                    [""] + estados,
                    index=0
                )
            except Exception as e:
                st.error(f"Error al cargar los estados: {str(e)}")
                estado_seleccionado = ""
                
            pais = st.text_input("País", "México")
            
        with col2:
            fecha_nac = st.date_input("Fecha de Nacimiento", None)
            fecha_exp = st.date_input("Fecha de Expedición", None)
            nacionalidad = st.text_input("Nacionalidad", "MEXICANA")
            
            genero = st.selectbox(
                "Género", 
                ["", "MASCULINO", "FEMENINO", "OTRO"],
                index=0
            )
            
            tipo_licencia = st.selectbox(
                "Tipo de Licencia",
                ["", "NOVATO", "AVANZADO", "GENERAL", "EXTRA"],
                index=0
            )
            
            estatus = st.selectbox(
                "Estatus",
                ["ACTIVO", "INACTIVO", "SUSPENDIDO", "EN TRÁMITE"],
                index=0
            )
        
        observaciones = st.text_area("Observaciones", "")
        
        # Botones de acción
        col1, col2, _ = st.columns([1, 1, 4])
        
        with col1:
            if st.form_submit_button("💾 Guardar", type="primary"):
                # Validar campos obligatorios
                if not indicativo or not nombre:
                    st.error("Los campos de indicativo y nombre son obligatorios")
                else:
                    # Preparar datos para guardar
                    datos = {
                        'indicativo': indicativo.upper(),
                        'nombre_completo': nombre,
                        'municipio': municipio if municipio else None,
                        'estado': estado_seleccionado if estado_seleccionado else None,
                        'pais': pais if pais else None,
                        'fecha_nacimiento': fecha_nac.strftime('%Y-%m-%d') if fecha_nac else None,
                        'nacionalidad': nacionalidad if nacionalidad else None,
                        'genero': genero if genero else None,
                        'tipo_licencia': tipo_licencia if tipo_licencia else None,
                        'fecha_expedicion': fecha_exp.strftime('%Y-%m-%d') if fecha_exp else None,
                        'estatus': estatus if estatus else 'ACTIVO',
                        'observaciones': observaciones if observaciones else None,
                        'activo': 1 if estatus == 'ACTIVO' else 0
                    }
                    
                    try:
                        # Intentar crear el radioexperimentador
                        radio_id = db.create_radioexperimentador(datos)
                        if radio_id:
                            st.success("¡Radioexperimentador creado exitosamente!")
                            # Limpiar el formulario
                            st.rerun()
                        else:
                            st.error("No se pudo crear el radioexperimentador. Verifica los datos e intenta nuevamente.")
                    except Exception as e:
                        if "UNIQUE constraint failed: radioexperimentadores.indicativo" in str(e):
                            st.error("Ya existe un radioexperimentador con este indicativo.")
                        else:
                            st.error(f"Error al crear el radioexperimentador: {str(e)}")
        
        with col2:
            if st.form_submit_button("❌ Cancelar"):
                st.rerun()


if __name__ == "__main__":
    main()
