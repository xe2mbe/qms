import streamlit as st
import streamlit_authenticator as stauth
from database import FMREDatabase
import time

class AuthManager:
    def __init__(self, db):
        self.db = db
    
    def show_login(self):
        """Muestra el formulario de inicio de sesión"""
        st.title("🔑 Inicio de Sesión")
        
        with st.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            
            if st.form_submit_button("Iniciar sesión"):
                user = self.db.verify_user(username, password)
                if user:
                    st.session_state.user = user
                    st.success(f"Bienvenido, {user['full_name']}!")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos")
    
    def logout(self):
        """Cierra la sesión del usuario"""
        if 'user' in st.session_state:
            del st.session_state.user
        st.session_state.current_page = "home"
        st.rerun()
    
    def is_authenticated(self):
        """Verifica si el usuario está autenticado"""
        return 'user' in st.session_state
    
    def is_admin(self):
        """Verifica si el usuario es administrador"""
        return self.is_authenticated() and st.session_state.user.get('role') == 'admin'
    
    def require_auth(self):
        """Redirige al inicio de sesión si el usuario no está autenticado"""
        if not self.is_authenticated():
            st.warning("Por favor inicia sesión para acceder a esta página.")
            self.show_login()
            st.stop()
    
    def require_admin(self):
        """Verifica que el usuario sea administrador"""
        self.require_auth()
        if not self.is_admin():
            st.error("No tienes permisos para acceder a esta sección.")
            st.stop()
