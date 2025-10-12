import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from database import FMREDatabase

class EmailSender:
    def __init__(self, db):
        self.db = db
    
    def get_smtp_connection(self):
        """Obtiene la configuración SMTP y devuelve una conexión"""
        settings = self.db.get_smtp_settings()
        if not settings:
            raise Exception("No se ha configurado el servidor SMTP")
        
        try:
            if settings['use_tls']:
                server = smtplib.SMTP(settings['server'], settings['port'])
                server.starttls()
            else:
                server = smtplib.SMTP(settings['server'], settings['port'])
            
            if settings['username'] and settings['password']:
                server.login(settings['username'], settings['password'])
                
            return server, settings['from_email']
            
        except Exception as e:
            raise Exception(f"Error al conectar con el servidor SMTP: {str(e)}")
    
    def send_email(self, to_email, subject, body, is_html=False):
        """Envía un correo electrónico con compatibilidad HTML/Texto (multipart/alternative)"""
        try:
            server, from_email = self.get_smtp_connection()

            # Crear mensaje multipart/alternative (primero texto, luego HTML)
            msg = MIMEMultipart('alternative')
            msg['From'] = from_email
            msg['To'] = to_email
            msg['Subject'] = subject

            # Generar partes
            if is_html:
                # Convertir HTML a texto simple básico
                text_version = body or ''
                # Reemplazar enlaces <a href="url">texto</a> por 'texto (url)'
                text_version = re.sub(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r'\2 (\1)', text_version, flags=re.IGNORECASE)
                # Quitar el resto de etiquetas HTML
                text_version = re.sub(r'<[^>]+>', '', text_version)

                part_text = MIMEText(text_version, 'plain')
                part_html = MIMEText(body or '', 'html')

                msg.attach(part_text)
                msg.attach(part_html)
            else:
                part_text = MIMEText(body or '', 'plain')
                msg.attach(part_text)

            # Enviar correo
            server.send_message(msg)
            server.quit()
            return True

        except Exception as e:
            raise Exception(f"Error al enviar el correo: {str(e)}")
    
    def send_user_credentials(self, user, password):
        """Envía las credenciales a un nuevo usuario usando plantilla configurable"""

        def render_template(template: str, context: dict) -> str:
            """Reemplaza placeholders {{key}} por valores de context de forma segura"""
            if not template:
                return ""
            pattern = re.compile(r"\{\{\s*(\w+)\s*\}\}")
            def repl(match):
                key = match.group(1)
                return str(context.get(key, ''))
            return pattern.sub(repl, template)

        # Cargar ajustes desde system_setting
        system_url = self.db.get_system_url() or "http://localhost:8501"
        subject_setting = self.db.get_system_setting('welcome_email_subject')
        body_setting = self.db.get_system_setting('welcome_email_body_html')

        # Valores por defecto
        default_subject = "Bienvenido al Sistema de Gestión de QSOs"
        default_body = (
            "<html><body>"
            "<h2>Bienvenido al Sistema de Gestión de QSOs de la FMRE A.C.</h2>"
            "<p>Hola {{full_name}},</p>"
            "<p>Se ha creado una cuenta para ti en el Sistema de Gestión de QSOs.</p>"
            "<p><strong>Tus credenciales de acceso son:</strong></p>"
            "<ul>"
            "<li><strong>Usuario:</strong> {{username}}</li>"
            "<li><strong>Contraseña temporal:</strong> {{password}}</li>"
            "</ul>"
            "<p>Te recomendamos cambiar tu contraseña después de iniciar sesión por primera vez.</p>"
            "<p>Puedes acceder al sistema en: <a href=\"{{system_url}}\" target=\"_blank\">{{system_url}}</a></p>"
            "<p>Saludos,<br>El equipo de FMRE</p>"
            "</body></html>"
        )

        subject_tmpl = (subject_setting.get('value') if subject_setting else None) or default_subject
        body_tmpl = (body_setting.get('value') if body_setting else None) or default_body

        context = {
            'full_name': user.get('full_name', ''),
            'username': user.get('username', ''),
            'password': password,
            'system_url': system_url,
        }

        subject = render_template(subject_tmpl, context)
        body = render_template(body_tmpl, context)

        # Asegurar que la URL del sistema sea clickeable aunque la plantilla no use <a>
        # Primero, envolver la system_url literal si aparece sin href
        if system_url and body and system_url in body:
            has_href_double = f'href="{system_url}"' in body
            has_href_single = f"href='{system_url}'" in body
            if not (has_href_double or has_href_single):
                body = body.replace(system_url, f'<a href="{system_url}" target="_blank">{system_url}</a>')

        # Segundo, convertir cualquier otra URL http(s) en enlace si no está ya dentro de un href
        if body:
            body = re.sub(r'(?<!href=")(https?://[^\s<>\'"]+)', r'<a href="\1" target="_blank">\1</a>', body)
            body = re.sub(r"(?<!href=')(https?://[^\s<>\'\"]+)", r'<a href="\1" target="_blank">\1</a>', body)

        return self.send_email(user['email'], subject, body, is_html=True)
