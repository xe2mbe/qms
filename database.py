import sqlite3
import hashlib
import secrets
import string
from datetime import datetime

class FMREDatabase:
    def __init__(self, db_path="qms.db"):
        self.db_path = db_path
        self.init_database()
        
    def _check_password(self, password, hashed_password):
        """
        Verifica si la contraseña coincide con el hash almacenado
        
        Args:
            password (str): Contraseña en texto plano
            hashed_password (str): Hash de la contraseña almacenado en la base de datos
            
        Returns:
            bool: True si la contraseña coincide, False en caso contrario
        """
        # Asegurarse de que el hash se calcule de la misma manera que en change_password
        return hashlib.sha256(password.encode()).hexdigest() == hashed_password
    
    def get_connection(self):
        """Obtiene una conexión a la base de datos con manejo de timeouts y conexiones persistentes"""
        # Configuración para evitar bloqueos
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,  # Aumentar el tiempo de espera
            isolation_level=None,  # Deshabilitar el modo de transacción automática
            check_same_thread=False  # Permitir acceso desde múltiples hilos
        )
        # Habilitar WAL (Write-Ahead Logging) para mejor concurrencia
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=5000')  # 5 segundos de timeout
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Inicializa la base de datos con las tablas necesarias"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Tabla de eventos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS eventos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT NOT NULL,
                    descripcion TEXT,
                    activo BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tabla de configuración SMTP
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS smtp_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL,
                    use_tls BOOLEAN DEFAULT 1,
                    from_email TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insertar configuración por defecto si no existe
            cursor.execute('SELECT COUNT(*) FROM smtp_settings')
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                    INSERT INTO smtp_settings 
                    (server, port, username, password, use_tls, from_email)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', ('smtp.gmail.com', 587, '', '', 1, ''))
            
            # Tabla de QTH (Estados)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS qth (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    estado TEXT NOT NULL UNIQUE,
                    abreviatura TEXT NOT NULL UNIQUE
                )
            ''')
            
            # Tabla de Zonas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS zonas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zona TEXT NOT NULL UNIQUE,
                    nombre TEXT NOT NULL UNIQUE,
                    activo BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Verificar y agregar columnas faltantes si es necesario
            cursor.execute('PRAGMA table_info(zonas)')
            columns = [column[1] for column in cursor.fetchall()]
            
            # Función para agregar una columna si no existe
            def add_column_if_not_exists(column_name, column_definition):
                if column_name not in columns:
                    try:
                        cursor.execute(f'ALTER TABLE zonas ADD COLUMN {column_name} {column_definition}')
                        print(f'Columna {column_name} agregada correctamente')
                        return True
                    except sqlite3.OperationalError as e:
                        print(f'Error al agregar columna {column_name}: {str(e)}')
                        return False
                return True
            
            # Agregar columnas una por una
            add_column_if_not_exists('descripcion', 'TEXT')
            add_column_if_not_exists('activo', 'BOOLEAN DEFAULT 1')
            
            # Para columnas con valores por defecto no constantes, primero las agregamos sin valor por defecto
            if 'created_at' not in columns:
                cursor.execute('ALTER TABLE zonas ADD COLUMN created_at TIMESTAMP')
                cursor.execute("UPDATE zonas SET created_at = datetime('now') WHERE created_at IS NULL")
                
            if 'updated_at' not in columns:
                cursor.execute('ALTER TABLE zonas ADD COLUMN updated_at TIMESTAMP')
                cursor.execute("UPDATE zonas SET updated_at = datetime('now') WHERE updated_at IS NULL")
            
            # Actualizar registros existentes para establecer valores por defecto
            cursor.execute('UPDATE zonas SET activo = 1 WHERE activo IS NULL')
            
            # Tabla de Sistemas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sistemas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT NOT NULL UNIQUE,
                    nombre TEXT NOT NULL UNIQUE
                )
            ''')
            
            # Tabla de Usuarios
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    email TEXT UNIQUE,
                    phone TEXT,
                    role TEXT NOT NULL DEFAULT 'operator',
                    is_active BOOLEAN DEFAULT 1,
                    last_login DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insertar datos iniciales si no existen
            self._insert_initial_data(cursor)
            
            conn.commit()
    
    def _insert_initial_data(self, cursor):
        """Inserta los datos iniciales en las tablas"""
        # Insertar estados de México
        estados_mexico = [
            ('Aguascalientes', 'AGS'), ('Baja California', 'BC'), 
            ('Baja California Sur', 'BCS'), ('Campeche', 'CAMP'),
            ('Chiapas', 'CHIS'), ('Chihuahua', 'CHIH'),
            ('Ciudad de México', 'CDMX'), ('Coahuila', 'COAH'),
            ('Colima', 'COL'), ('Durango', 'DGO'),
            ('Estado de México', 'EDOMEX'), ('Guanajuato', 'GTO'),
            ('Guerrero', 'GRO'), ('Hidalgo', 'HGO'),
            ('Jalisco', 'JAL'), ('Michoacán', 'MICH'),
            ('Morelos', 'MOR'), ('Nayarit', 'NAY'),
            ('Nuevo León', 'NL'), ('Oaxaca', 'OAX'),
            ('Puebla', 'PUE'), ('Querétaro', 'QRO'),
            ('Quintana Roo', 'QROO'), ('San Luis Potosí', 'SLP'),
            ('Sinaloa', 'SIN'), ('Sonora', 'SON'),
            ('Tabasco', 'TAB'), ('Tamaulipas', 'TAMPS'),
            ('Tlaxcala', 'TLAX'), ('Veracruz', 'VER'),
            ('Yucatán', 'YUC'), ('Zacatecas', 'ZAC'),
            ('Extranjero', 'EXT')
        ]
        
        cursor.executemany(
            'INSERT OR IGNORE INTO qth (estado, abreviatura) VALUES (?, ?)',
            estados_mexico
        )
        
        # Insertar zonas
        zonas = [
            ('XE1', 'Zona XE1'),
            ('XE2', 'Zona XE2'),
            ('XE3', 'Zona XE3'),
            ('EXT', 'Zona Extranjera')
        ]
        
        cursor.executemany(
            'INSERT OR IGNORE INTO zonas (zona, nombre) VALUES (?, ?)',
            zonas
        )
        
        # Insertar sistemas
        sistemas = [
            ('HF', 'High Frequency'),
            ('ASL', 'All Star Link'),
            ('IRLP', 'Internet Radio Link Project'),
            ('DMR', 'DMR'),
            ('Fusion', 'Yaesu C4FM'),
            ('D-Star', 'Icom D-Star'),
            ('P25', 'P25'),
            ('M17', 'M17')
        ]
        
        cursor.executemany(
            'INSERT OR IGNORE INTO sistemas (codigo, nombre) VALUES (?, ?)',
            sistemas
        )
        
        # Insertar eventos iniciales si no existen
        eventos_iniciales = [
            ('Boletín', 'Boletín informativo semanal'),
            ('Retransmisión', 'Retransmisión del boletín en el Centro de Retransmisión'),
            ('RNE 40', 'Prácticas de la RNE en la banda de 40 metros'),
            ('RNE 80', 'Prácticas de la RNE en la banda de 80 metros'),
            ('Facebook', 'Transmisión en vivo por Facebook'),
            ('Otro', 'Otros eventos no especificados')
        ]
        
        cursor.execute('SELECT COUNT(*) as count FROM eventos')
        if cursor.fetchone()['count'] == 0:
            cursor.executemany('''
                INSERT INTO eventos (tipo, descripcion)
                VALUES (?, ?)
            ''', eventos_iniciales)
        
        # Crear usuario admin por defecto si no existe
        admin_exists = cursor.execute(
            'SELECT id FROM users WHERE username = ?', 
            ('admin',)
        ).fetchone()
        
        if not admin_exists:
            self.create_user(
                username='admin',
                password='admin123',  # Se debe cambiar en producción
                full_name='Administrador del Sistema',
                email='admin@example.com',
                role='admin'
            )
    
    def _hash_password(self, password):
        """Genera un hash seguro de la contraseña"""
        salt = secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return f"{salt}${pwd_hash}"
        
    def _check_password(self, password, hashed_password):
        """Verifica si la contraseña coincide con el hash almacenado"""
        if not hashed_password or '$' not in hashed_password:
            return False
            
        salt, stored_hash = hashed_password.split('$', 1)
        new_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return new_hash == stored_hash
        
    def create_user(self, username, password, full_name, email, phone=None, role='operator'):
        """Crea un nuevo usuario en la base de datos"""
        password_hash = self._hash_password(password)
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('BEGIN TRANSACTION')
                cursor.execute('''
                    INSERT INTO users 
                    (username, password_hash, full_name, email, phone, role)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (username, password_hash, full_name, email, phone, role))
                user_id = cursor.lastrowid
                conn.commit()
                return user_id
        except sqlite3.IntegrityError as e:
            if 'UNIQUE constraint failed: users.username' in str(e):
                raise ValueError(f"El nombre de usuario '{username}' ya existe") from e
            if 'UNIQUE constraint failed: users.email' in str(e):
                raise ValueError(f"El correo electrónico '{email}' ya está registrado") from e
            raise
        except Exception as e:
            if conn:
                conn.rollback()
            raise
    
    def user_exists(self, username):
        """Verifica si un nombre de usuario ya existe"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', (username,))
            return cursor.fetchone()[0] > 0
            
    def email_exists(self, email, exclude_user_id=None):
        """Verifica si un correo electrónico ya existe"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if exclude_user_id is not None:
                cursor.execute('SELECT COUNT(*) FROM users WHERE email = ? AND id != ?', (email, exclude_user_id))
            else:
                cursor.execute('SELECT COUNT(*) FROM users WHERE email = ?', (email,))
            return cursor.fetchone()[0] > 0
            
    def get_all_users(self):
        """Obtiene todos los usuarios registrados"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, username, full_name, email, phone, role, 
                       last_login, created_at, updated_at, is_active
                FROM users
                ORDER BY full_name
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def change_password(self, username, new_password):
        """
        Actualiza la contraseña de un usuario
        
        Args:
            username (str): Nombre de usuario
            new_password (str): Nueva contraseña en texto plano
            
        Returns:
            bool: True si la actualización fue exitosa, False en caso contrario
        """
        if not username or not new_password:
            raise ValueError("Se requiere nombre de usuario y nueva contraseña")
            
        # Usar el mismo método de hashing que en _hash_password
        password_hash = self._hash_password(new_password)
            
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    UPDATE users 
                    SET password_hash = ?, 
                        updated_at = CURRENT_TIMESTAMP
                    WHERE username = ?
                ''', (password_hash, username))
                
                if cursor.rowcount == 0:
                    return False
                    
                conn.commit()
                return True
                
            except sqlite3.Error as e:
                conn.rollback()
                raise Exception(f"Error al actualizar la contraseña: {str(e)}")
            
    def delete_user(self, user_id):
        """Elimina un usuario por su ID"""
        if not user_id:
            raise ValueError("Se requiere un ID de usuario válido")
            
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('BEGIN TRANSACTION')
                # Verificar que el usuario existe
                cursor.execute('SELECT id FROM users WHERE id = ?', (user_id,))
                if not cursor.fetchone():
                    raise ValueError("El usuario no existe")
                
                # Eliminar el usuario
                cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
                conn.commit()
                return True
                
            except sqlite3.Error as e:
                conn.rollback()
                raise Exception(f"Error al eliminar el usuario: {str(e)}")
            except Exception as e:
                conn.rollback()
                raise
    
    def update_user(self, user_id, username=None, full_name=None, email=None, phone=None, role=None, password=None, is_active=None):
        """
        Actualiza los datos de un usuario existente
        
        Args:
            user_id: ID del usuario a actualizar
            username: Nuevo nombre de usuario (opcional)
            full_name: Nuevo nombre completo (opcional)
            email: Nuevo email (opcional)
            phone: Nuevo teléfono (opcional)
            role: Nuevo rol (opcional)
            password: Nueva contraseña en texto plano (opcional)
            is_active: Estado de la cuenta (True/False) (opcional)
            
        Returns:
            bool: True si la actualización fue exitosa
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Construir la consulta dinámicamente basada en los parámetros proporcionados
                update_fields = []
                params = []
                
                if username is not None:
                    update_fields.append("username = ?")
                    params.append(username)
                    
                if full_name is not None:
                    update_fields.append("full_name = ?")
                    params.append(full_name)
                    
                if email is not None:
                    update_fields.append("email = ?")
                    params.append(email)
                    
                if phone is not None:
                    update_fields.append("phone = ?")
                    params.append(phone)
                    
                if role is not None:
                    update_fields.append("role = ?")
                    params.append(role)
                    
                if is_active is not None:
                    update_fields.append("is_active = ?")
                    params.append(1 if is_active else 0)
                    
                if password is not None:
                    password_hash = self._hash_password(password)
                    update_fields.append("password_hash = ?")
                    params.append(password_hash)
                
                # Agregar siempre la actualización de updated_at
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                
                if not update_fields:
                    return False  # No hay nada que actualizar
                
                # Construir y ejecutar la consulta
                query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = ?"
                params.append(user_id)
                
                cursor.execute(query, params)
                conn.commit()
                return cursor.rowcount > 0
                
        except sqlite3.IntegrityError as e:
            if 'UNIQUE constraint failed: users.username' in str(e):
                raise ValueError(f"El nombre de usuario ya está en uso") from e
            if 'UNIQUE constraint failed: users.email' in str(e):
                raise ValueError(f"El correo electrónico ya está registrado") from e
            raise
        except Exception as e:
            if conn:
                conn.rollback()
            raise
    
    def get_user_by_id(self, user_id):
        """Obtiene un usuario por su ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, username, full_name, email, phone, role, 
                       last_login, created_at, updated_at
                FROM users 
                WHERE id = ?
            ''', (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_user_by_username(self, username):
        """Obtiene un usuario por su nombre de usuario"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()
            return dict(user) if user else None
    
    def get_smtp_settings(self):
        """Obtiene la configuración SMTP"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM smtp_settings ORDER BY id DESC LIMIT 1')
            result = cursor.fetchone()
            return dict(result) if result else None
    
    def update_smtp_settings(self, server, port, username, password, use_tls, from_email):
        """Actualiza la configuración SMTP"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO smtp_settings 
                (server, port, username, password, use_tls, from_email)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (server, port, username, password, 1 if use_tls else 0, from_email))
            conn.commit()
            return True
    
    def verify_user(self, username, password):
        """Verifica las credenciales del usuario"""
        user = self.get_user_by_username(username)
        if not user:
            return None
            
        if self._check_password(password, user['password_hash']):
            # Actualizar último inicio de sesión
            with self.get_connection() as conn:
                conn.execute(
                    'UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?',
                    (user['id'],)
                )
                conn.commit()
            
            # No devolver el hash de la contraseña
            user.pop('password_hash', None)
            return user
        
        return None
    
# ... (rest of the code remains the same)
        """Genera un hash seguro de la contraseña"""
        salt = secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return f"{salt}${pwd_hash}"
    
    def _check_password(self, password, stored_hash):
        """Verifica si la contraseña coincide con el hash almacenado"""
        if not stored_hash or '$' not in stored_hash:
            return False
            
        salt, pwd_hash = stored_hash.split('$', 1)
        new_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        
        return pwd_hash == new_hash
        
    # Métodos para consultar datos maestros
    def get_estados(self):
        """Obtiene todos los estados de la base de datos"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT abreviatura, estado FROM qth ORDER BY estado')
            return {row['abreviatura']: row['estado'] for row in cursor.fetchall()}
    
    def get_zona(self, zona):
        """Obtiene una zona por su código"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM zonas WHERE zona = ?', (zona,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def get_zonas(self, incluir_inactivas=False):
        """
        Obtiene todas las zonas de la base de datos
        
        Args:
            incluir_inactivas (bool): Si es True, incluye las zonas inactivas.
                                    Si es False (por defecto), solo muestra las activas.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if incluir_inactivas:
                cursor.execute('''
                    SELECT * FROM zonas 
                    ORDER BY nombre
                ''')
            else:
                cursor.execute('''
                    SELECT * FROM zonas 
                    WHERE activo = 1 
                    ORDER BY nombre
                ''')
            # Asegurarse de que el resultado tenga el formato correcto
            zonas = []
            for row in cursor.fetchall():
                zona = dict(row)
                # Si la zona tiene 'codigo' en lugar de 'zona', lo mapeamos
                if 'codigo' in zona and 'zona' not in zona:
                    zona['zona'] = zona.pop('codigo')
                zonas.append(zona)
            return zonas
    
    def create_zona(self, zona=None, nombre=None, codigo=None):
        """Crea una nueva zona
        
        Args:
            zona: Código de la zona (sinónimo de 'codigo' para compatibilidad)
            nombre: Nombre de la zona
            codigo: Sinónimo de 'zona' para compatibilidad (obsoleto)
            
        Returns:
            bool: True si la zona se creó correctamente, False en caso contrario
        """
        # Manejar compatibilidad con el parámetro 'codigo'
        if codigo is not None and zona is None:
            zona = codigo
            
        if zona is None or nombre is None:
            return False
            
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO zonas (zona, nombre, activo)
                    VALUES (?, ?, 1)
                ''', (zona, nombre))
                conn.commit()
                return True
            except sqlite3.IntegrityError as e:
                print(f"Error al crear zona: {str(e)}")
                return False
    
    def update_zona(self, zona, nombre=None, activo=None):
        """Actualiza una zona existente"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Construir la consulta dinámicamente
            update_fields = []
            params = []
            
            if nombre is not None:
                update_fields.append("nombre = ?")
                params.append(nombre)
            if activo is not None:
                update_fields.append("activo = ?")
                params.append(1 if activo else 0)
            
            if not update_fields:
                return False  # No hay nada que actualizar
            
            query = f"""
                UPDATE zonas 
                SET {', '.join(update_fields)}
                WHERE zona = ?
            """
            params.append(zona)
            
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_zona(self, zona):
        """Elimina lógicamente una zona (la marca como inactiva)"""
        return self.update_zona(zona, activo=0)
    
    def get_sistemas(self):
        """Obtiene todos los sistemas de la base de datos"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT codigo, nombre FROM sistemas ORDER BY nombre')
            return {row['codigo']: row['nombre'] for row in cursor.fetchall()}
    
    def get_estado_by_abreviatura(self, abreviatura):
        """Obtiene un estado por su abreviatura"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT estado FROM qth WHERE abreviatura = ?', (abreviatura,))
            result = cursor.fetchone()
            return result['estado'] if result else None
    
    def get_nombre_zona(self, zona):
        """Obtiene el nombre de una zona por su código"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT nombre FROM zonas WHERE zona = ?', (zona,))
            result = cursor.fetchone()
            return result['nombre'] if result else None
    
    def get_sistema_by_codigo(self, codigo):
        """Obtiene un sistema por su código"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT nombre FROM sistemas WHERE codigo = ?', (codigo,))
            result = cursor.fetchone()
            return result['nombre'] if result else None

    # ========================
    # Métodos para Eventos
    # ========================
    
    def create_evento(self, tipo, descripcion=None):
        """Crea un nuevo evento"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO eventos (tipo, descripcion)
                VALUES (?, ?)
            ''', (tipo, descripcion))
            conn.commit()
            return cursor.lastrowid
    
    def get_evento(self, evento_id):
        """Obtiene un evento por su ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM eventos WHERE id = ?', (evento_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def get_all_eventos(self, incluir_inactivos=False):
        """
        Obtiene todos los eventos ordenados por tipo
        
        Args:
            incluir_inactivos (bool): Si es True, incluye los eventos inactivos.
                                     Si es False (por defecto), solo muestra los activos.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if incluir_inactivos:
                cursor.execute('''
                    SELECT * FROM eventos 
                    ORDER BY tipo ASC
                ''')
            else:
                cursor.execute('''
                    SELECT * FROM eventos 
                    WHERE activo = 1 
                    ORDER BY tipo ASC
                ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def update_evento(self, evento_id, tipo=None, descripcion=None, activo=None):
        """Actualiza un evento existente"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Construir la consulta dinámicamente basada en los parámetros proporcionados
            update_fields = []
            params = []
            
            if tipo is not None:
                update_fields.append("tipo = ?")
                params.append(tipo)
                
            if descripcion is not None:
                update_fields.append("descripcion = ?")
                params.append(descripcion)
                
            if activo is not None:
                update_fields.append("activo = ?")
                params.append(activo)
            
            # Si no hay campos para actualizar, retornar False
            if not update_fields:
                return False
                
            # Agregar el campo updated_at
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            
            # Construir la consulta final
            query = f"""
                UPDATE eventos 
                SET {', '.join(update_fields)}
                WHERE id = ?
            """
            
            # Agregar el ID del evento a los parámetros
            params.append(evento_id)
            
            # Ejecutar la consulta
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_evento(self, evento_id):
        """Elimina lógicamente un evento (lo marca como inactivo)"""
        return self.update_evento(evento_id, activo=0)

if __name__ == "__main__":
    # Crear la base de datos y tablas si no existen
    db = FMREDatabase()
    print("Base de datos inicializada correctamente.")
