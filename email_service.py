import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import secrets
import hashlib
import os
from typing import Optional, Dict, Any

class EmailService:
    """Servicio de correo electrónico para el sistema FMRE"""
    
    def __init__(self):
        # Configuración SMTP (se puede configurar via variables de entorno)
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_username)
        self.from_name = os.getenv('FROM_NAME', 'Sistema FMRE')
        
        # Tokens de recuperación (en producción usar Redis o base de datos)
        self.reset_tokens = {}
    
    def configure_smtp(self, server: str, port: int, username: str, password: str, from_email: str = None, from_name: str = None):
        """Configura los parámetros SMTP"""
        self.smtp_server = server
        self.smtp_port = port
        self.smtp_username = username
        if password:  # Solo actualizar si se proporciona nueva contraseña
            self.smtp_password = password
        self.from_email = from_email or username
        self.from_name = from_name or 'Sistema FMRE'
    
    def test_smtp_connection(self) -> bool:
        """Prueba la conexión SMTP"""
        if not self.is_configured():
            return False
        
        try:
            import ssl
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.smtp_username, self.smtp_password)
            return True
        except Exception as e:
            print(f"Error en conexión SMTP: {str(e)}")
            return False
    
    def is_configured(self) -> bool:
        """Verifica si el servicio de email está configurado"""
        return bool(self.smtp_username and self.smtp_password and self.smtp_server)
    
    def send_email(self, to_email: str, subject: str, body_html: str, body_text: str = None) -> bool:
        """Envía un correo electrónico"""
        if not self.is_configured():
            print("⚠️ Servicio de email no configurado")
            return False
        
        try:
            # Crear mensaje
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.from_name} <{self.from_email}>"
            message["To"] = to_email
            
            # Agregar contenido
            if body_text:
                text_part = MIMEText(body_text, "plain", "utf-8")
                message.attach(text_part)
            
            html_part = MIMEText(body_html, "html", "utf-8")
            message.attach(html_part)
            
            # Enviar email
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.smtp_username, self.smtp_password)
                server.sendmail(self.from_email, to_email, message.as_string())
            
            print(f"✅ Email enviado a {to_email}")
            return True
            
        except Exception as e:
            print(f"❌ Error enviando email: {str(e)}")
            return False
    
    def send_welcome_email(self, user_data: Dict[str, Any], password: str) -> bool:
        """Envía email de bienvenida con credenciales"""
        subject = "🎉 Bienvenido al Sistema FMRE - Credenciales de Acceso"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .credentials {{ background: white; padding: 20px; border-radius: 8px; border-left: 4px solid #667eea; margin: 20px 0; }}
                .button {{ display: inline-block; background: #667eea; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
                .warning {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📻 Sistema FMRE</h1>
                    <p>Control de Reportes de Boletín</p>
                </div>
                <div class="content">
                    <h2>¡Bienvenido, {user_data['full_name']}!</h2>
                    <p>Tu cuenta ha sido creada exitosamente en el Sistema FMRE. A continuación encontrarás tus credenciales de acceso:</p>
                    
                    <div class="credentials">
                        <h3>🔐 Credenciales de Acceso</h3>
                        <p><strong>Usuario:</strong> {user_data['username']}</p>
                        <p><strong>Contraseña:</strong> {password}</p>
                        <p><strong>Rol:</strong> {user_data['role'].title()}</p>
                    </div>
                    
                    <div class="warning">
                        <strong>⚠️ Importante:</strong> Por seguridad, te recomendamos cambiar tu contraseña después del primer inicio de sesión.
                    </div>
                    
                    <p>Puedes acceder al sistema usando el enlace de abajo:</p>
                    <a href="http://299085.nodes.allstarlink.org/fmre" class="button">🚀 Acceder al Sistema</a>
                    
                    <h3>📋 Funcionalidades Disponibles:</h3>
                    <ul>
                        <li>✅ Registro de reportes en tiempo real</li>
                        <li>📊 Dashboard con estadísticas</li>
                        <li>📁 Exportación a PDF, Excel y CSV</li>
                        <li>⚡ Registro rápido desde historial</li>
                        <li>🔍 Búsqueda y filtrado avanzado</li>
                    </ul>
                    
                    <p>Si tienes alguna pregunta o necesitas ayuda, no dudes en contactar al administrador del sistema.</p>
                </div>
                <div class="footer">
                    <p>Sistema FMRE - QSO Manager System - QMS<br>
                    Generado automáticamente el {datetime.now().strftime('%d/%m/%Y a las %H:%M')}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
        Sistema FMRE - Bienvenido
        
        Hola {user_data['full_name']},
        
        Tu cuenta ha sido creada exitosamente en el Sistema FMRE.
        
        Credenciales de Acceso:
        - Usuario: {user_data['username']}
        - Contraseña: {password}
        - Rol: {user_data['role'].title()}
        
        IMPORTANTE: Por seguridad, te recomendamos cambiar tu contraseña después del primer inicio de sesión.
        
        Accede al sistema en: http://http://299085.nodes.allstarlink.org/fmre
        
        Sistema FMRE - {datetime.now().strftime('%d/%m/%Y %H:%M')}
        """
        
        return self.send_email(user_data['email'], subject, html_body, text_body)
    
    def generate_reset_token(self, username: str) -> str:
        """Genera un token de recuperación de contraseña"""
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=1)  # Token válido por 1 hora
        
        self.reset_tokens[token] = {
            'username': username,
            'expires_at': expires_at,
            'used': False
        }
        
        return token
    
    def validate_reset_token(self, token: str) -> Optional[str]:
        """Valida un token de recuperación y retorna el username si es válido"""
        if token not in self.reset_tokens:
            return None
        
        token_data = self.reset_tokens[token]
        
        if token_data['used'] or datetime.now() > token_data['expires_at']:
            return None
        
        return token_data['username']
    
    def use_reset_token(self, token: str) -> bool:
        """Marca un token como usado"""
        if token in self.reset_tokens:
            self.reset_tokens[token]['used'] = True
            return True
        return False
    
    def send_password_reset_email(self, user_data: Dict[str, Any]) -> Optional[str]:
        """Envía email de recuperación de contraseña"""
        token = self.generate_reset_token(user_data['username'])
        reset_url = f"http://localhost:8501?reset_token={token}"
        
        subject = "🔐 Recuperación de Contraseña - Sistema FMRE"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .button {{ display: inline-block; background: #e74c3c; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                .warning {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
                .token {{ background: white; padding: 15px; border-radius: 5px; font-family: monospace; word-break: break-all; margin: 15px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔐 Recuperación de Contraseña</h1>
                    <p>Sistema FMRE</p>
                </div>
                <div class="content">
                    <h2>Hola, {user_data['full_name']}</h2>
                    <p>Hemos recibido una solicitud para restablecer la contraseña de tu cuenta <strong>{user_data['username']}</strong>.</p>
                    
                    <p>Haz clic en el siguiente enlace para crear una nueva contraseña:</p>
                    <a href="{reset_url}" class="button">🔄 Restablecer Contraseña</a>
                    
                    <p>O copia y pega este enlace en tu navegador:</p>
                    <div class="token">{reset_url}</div>
                    
                    <div class="warning">
                        <strong>⚠️ Importante:</strong>
                        <ul>
                            <li>Este enlace es válido por <strong>1 hora</strong></li>
                            <li>Solo puede ser usado <strong>una vez</strong></li>
                            <li>Si no solicitaste este cambio, ignora este email</li>
                        </ul>
                    </div>
                    
                    <p>Si tienes problemas con el enlace, contacta al administrador del sistema.</p>
                </div>
                <div class="footer">
                    <p>Sistema FMRE - Control de Reportes de Boletín<br>
                    Solicitud generada el {datetime.now().strftime('%d/%m/%Y a las %H:%M')}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
        Sistema FMRE - Recuperación de Contraseña
        
        Hola {user_data['full_name']},
        
        Hemos recibido una solicitud para restablecer la contraseña de tu cuenta {user_data['username']}.
        
        Para crear una nueva contraseña, visita el siguiente enlace:
        {reset_url}
        
        IMPORTANTE:
        - Este enlace es válido por 1 hora
        - Solo puede ser usado una vez
        - Si no solicitaste este cambio, ignora este email
        
        Sistema FMRE - {datetime.now().strftime('%d/%m/%Y %H:%M')}
        """
        
        success = self.send_email(user_data['email'], subject, html_body, text_body)
        return token if success else None
