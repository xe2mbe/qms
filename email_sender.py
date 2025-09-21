import smtplib
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
        """Envía un correo electrónico"""
        try:
            server, from_email = self.get_smtp_connection()
            
            # Crear mensaje
            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Adjuntar el cuerpo del mensaje
            if is_html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))
            
            # Enviar correo
            server.send_message(msg)
            server.quit()
            return True
            
        except Exception as e:
            raise Exception(f"Error al enviar el correo: {str(e)}")
    
    def send_user_credentials(self, user, password):
        """Envía las credenciales a un nuevo usuario"""
        subject = "Bienvenido al Sistema de Gestión de QSOs"
        
        # Cuerpo del mensaje en HTML
        body = f"""
        <html>
            <body>
                <h2>Bienvenido al Sistema de Gestión de QSOs de la FMRE A.C.</h2>
                <p>Hola {user['full_name']},</p>
                <p>Se ha creado una cuenta para ti en el Sistema de Gestión de QSOs.</p>
                <p><strong>Tus credenciales de acceso son:</strong></p>
                <ul>
                    <li><strong>Usuario:</strong> {user['username']}</li>
                    <li><strong>Contraseña temporal:</strong> {password}</li>
                </ul>
                <p>Te recomendamos cambiar tu contraseña después de iniciar sesión por primera vez.</p>
                <p>Puedes acceder al sistema en: http://299085.nodes.allstarlink.org/fmre</p>
                <p>Saludos,<br>El equipo de FMRE</p>
            </body>
        </html>
        """
        
        return self.send_email(user['email'], subject, body, is_html=True)
