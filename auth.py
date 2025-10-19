import streamlit as st
import streamlit_authenticator as stauth
from database import FMREDatabase
import time

class AuthManager:
    def __init__(self, db):
        self.db = db
    
    def show_login(self):
        """Muestra el formulario de inicio de sesión"""
        col_l, col_c, col_r = st.columns([1, 2, 1])
        with col_c:
            # Estilos de tarjeta para los formularios de login
            st.markdown(
                """
                <style>
                /* Tarjeta centrada para formularios de login */
                [data-testid="stForm"] {
                    max-width: 480px;
                    margin: 2rem auto 0 auto;
                    padding: 1.25rem 1.5rem;
                    background: var(--secondary-background-color);
                    border: 1px solid rgba(0,0,0,0.08);
                    border-radius: 12px;
                    box-shadow: 0 10px 24px rgba(0,0,0,0.08);
                }
                [data-testid="stForm"] .stButton > button {
                    width: 100%;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            force_user = st.session_state.get('force_change_user')
            if force_user:
                with st.form("force_change_password_form"):
                    st.markdown('<h2 style="text-align:center;margin:0 0 0.75rem 0">🔒 Cambiar contraseña</h2>', unsafe_allow_html=True)
                    st.warning("Debes cambiar tu contraseña para continuar.")
                    new_password = st.text_input("Nueva contraseña", type="password", key="force_new_pwd")
                    confirm_password = st.text_input("Confirmar nueva contraseña", type="password", key="force_confirm_pwd")
                    if st.form_submit_button("Cambiar contraseña"):
                        if not new_password or not confirm_password:
                            st.error("Por favor completa ambos campos.")
                        elif new_password != confirm_password:
                            st.error("Las contraseñas no coinciden.")
                        else:
                            try:
                                from utils import validate_password
                                is_valid, message = validate_password(new_password)
                                if not is_valid:
                                    st.error(message)
                                else:
                                    self.db.change_password(force_user, new_password)
                                    self.db.set_must_change_password(username=force_user, value=False)
                                    user = self.db.verify_user(force_user, new_password)
                                    if user:
                                        st.session_state.user = user
                                        del st.session_state['force_change_user']
                                        st.success("Contraseña actualizada. Bienvenido.")
                                        time.sleep(2)
                                        st.rerun()
                                    else:
                                        st.error("No fue posible iniciar sesión tras el cambio de contraseña.")
                            except Exception as e:
                                st.error(f"Error al actualizar la contraseña: {e}")
                return

            with st.form("login_form"):
                st.markdown('<h2 style="text-align:center;margin:0 0 0.75rem 0">🔑 Inicio de Sesión</h2>', unsafe_allow_html=True)
                username = st.text_input("Usuario")
                password = st.text_input("Contraseña", type="password")
                if st.form_submit_button("Iniciar sesión"):
                    user = self.db.verify_user(username, password)
                    if user:
                        if user.get('must_change_password'):
                            st.session_state['force_change_user'] = username
                            st.warning("Cambio de contraseña requerido. Por favor establece una nueva contraseña.")
                            st.rerun()
                        else:
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
