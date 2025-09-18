import hashlib
import streamlit as st
from database import FMREDatabase

class AuthManager:
    def __init__(self, db: FMREDatabase):
        self.db = db
        
    def hash_password(self, password):
        """Genera hash de la contraseña"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_password(self, password, password_hash):
        """Verifica si una contraseña coincide con su hash"""
        return self.hash_password(password) == password_hash
    
    def create_default_admin(self):
        """Crea usuario administrador por defecto si no existe"""
        if not self.db.get_user('admin'):
            admin_hash = self.hash_password('admin123')
            self.db.create_user('admin', admin_hash, 'Administrador FMRE', None, 'admin')
            return True
        return False
    
    def authenticate_user(self, username, password):
        """Autentica un usuario"""
        user = self.db.get_user(username)
        if user and self.verify_password(password, user['password_hash']):
            self.db.update_last_login(username)
            return {
                'id': user['id'],
                'username': user['username'],
                'full_name': user['full_name'],
                'email': user['email'],
                'role': user['role']
            }
        return None
    
    def create_user(self, username, password, role='operator', full_name=None, email=None):
        """Crea un nuevo usuario"""
        password_hash = self.hash_password(password)
        return self.db.create_user(username, password_hash, full_name, email, role)
    
    def is_logged_in(self):
        """Verifica si hay un usuario logueado"""
        return 'user' in st.session_state and st.session_state.user is not None
    
    def get_current_user(self):
        """Obtiene el usuario actual"""
        return st.session_state.get('user', None)
    
    def logout(self):
        """Cierra sesión del usuario"""
        if 'user' in st.session_state:
            del st.session_state.user
        st.rerun()
    
    def require_login(self):
        """Requiere que el usuario esté logueado"""
        if not self.is_logged_in():
            self.show_login_form()
            st.stop()
    
    def show_login_form(self):
        """Muestra el formulario de login"""
        # Logo y título de login centrados
        st.markdown("""
        <div style="display: flex; justify-content: center; align-items: center; flex-direction: column; width: 100%; margin: 30px 0;">
            <div style="text-align: center;">
        """, unsafe_allow_html=True)
        
        # Logo centrado con CSS directo
        import base64
        try:
            with open("assets/LogoFMRE_medium.png", "rb") as f:
                logo_data = base64.b64encode(f.read()).decode()
            st.markdown(f"""
            <img src="data:image/png;base64,{logo_data}" 
                 style="display: block; margin: 0 auto 15px auto; max-width: 100%; height: auto;" 
                 alt="FMRE Logo">
            """, unsafe_allow_html=True)
        except:
            st.markdown('<div style="font-size: 60px; text-align: center;">📻</div>', unsafe_allow_html=True)
        
        # Título y subtítulo
        st.markdown("""
                <h3 style="color: #1f77b4; margin: 0 0 5px 0; text-align: center;">🔐 Federación Mexicana de Radioexperimentadores A.C.</h3>
                <h3 style="color: #666; margin: 0; text-align: center;">Sistema Integral de Gestión de QSOs (SIGQ)</h3>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            with st.form("login_form"):
                username = st.text_input("Usuario", placeholder="Ingresa tu usuario")
                password = st.text_input("Contraseña", type="password", placeholder="Ingresa tu contraseña")
                
                login_submitted = st.form_submit_button("🚪 Iniciar Sesión", width='stretch')
                
                if login_submitted:
                    if username and password:
                        user = self.authenticate_user(username, password)
                        if user:
                            st.session_state.user = user
                            st.success(f"¡Bienvenido, {user['full_name']}!")
                            st.rerun()
                        else:
                            st.error("❌ Usuario o contraseña incorrectos")
                    else:
                        st.error("❌ Por favor completa todos los campos")
        
        # Mostrar información de usuario por defecto
        #st.info("👤 **Usuario por defecto:** admin | **Contraseña:** admin123")
        
    
    def show_register_form(self):
        """Muestra el formulario de registro"""
        st.markdown("---")
        st.markdown('<h3 style="text-align: center;">📝 Registro de Nuevo Usuario</h3>', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            with st.form("register_form"):
                new_username = st.text_input("Nuevo Usuario", placeholder="Elige un nombre de usuario")
                new_password = st.text_input("Nueva Contraseña", type="password", placeholder="Crea una contraseña")
                confirm_password = st.text_input("Confirmar Contraseña", type="password", placeholder="Confirma tu contraseña")
                full_name = st.text_input("Nombre Completo", placeholder="Tu nombre completo")
                
                col_reg, col_cancel = st.columns(2)
                
                with col_reg:
                    register_submitted = st.form_submit_button("✅ Registrar", width='stretch')
                
                with col_cancel:
                    cancel_submitted = st.form_submit_button("❌ Cancelar", width='stretch')
                
                if register_submitted:
                    if all([new_username, new_password, confirm_password, full_name]):
                        if new_password == confirm_password:
                            if len(new_password) >= 6:
                                user_id = self.create_user(new_username, new_password, full_name)
                                if user_id:
                                    st.success("✅ Usuario registrado exitosamente. Ahora puedes iniciar sesión.")
                                    st.session_state.show_register = False
                                    st.rerun()
                                else:
                                    st.error("❌ El nombre de usuario ya existe")
                            else:
                                st.error("❌ La contraseña debe tener al menos 6 caracteres")
                        else:
                            st.error("❌ Las contraseñas no coinciden")
                    else:
                        st.error("❌ Por favor completa todos los campos")
                
                if cancel_submitted:
                    st.session_state.show_register = False
                    st.rerun()
