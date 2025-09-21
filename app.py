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
            menu_options.extend(["👥 Usuarios", "⚙️ Configuración"])
            
        selected = st.selectbox("Navegación", menu_options)
        
        # Navegación
        if selected == "👥 Usuarios":
            st.session_state.current_page = "users"
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

def show_users():
    """Muestra la gestión de usuarios con expanders para cada usuario"""
    st.title("👥 Gestión de Usuarios")
    
    # Verificar si el usuario es admin
    if st.session_state.user['role'] != 'admin':
        st.error("❌ Acceso denegado. Solo los administradores pueden acceder a esta sección.")
        st.stop()
    
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
        
        # Mostrar la página correspondiente
        if st.session_state.current_page == "home":
            show_home()
        elif st.session_state.current_page == "users":
            show_users()
        elif st.session_state.current_page == "reports":
            show_reports()
        elif st.session_state.current_page == "settings":
            show_settings()

if __name__ == "__main__":
    main()
