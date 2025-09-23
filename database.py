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
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    sistema_preferido TEXT,
                    frecuencia TEXT,
                    modo TEXT,
                    potencia TEXT,
                    pre_registro INTEGER DEFAULT 0
                )
            ''')
            
            # Verificar y agregar columnas faltantes en la tabla users
            cursor.execute("PRAGMA table_info(users)")
            columns = {column[1] for column in cursor.fetchall()}
            
            # Agregar columnas si no existen
            if 'sistema_preferido' not in columns:
                cursor.execute('ALTER TABLE users ADD COLUMN sistema_preferido TEXT')
            if 'frecuencia' not in columns:
                cursor.execute('ALTER TABLE users ADD COLUMN frecuencia TEXT')
            if 'modo' not in columns:
                cursor.execute('ALTER TABLE users ADD COLUMN modo TEXT')
            if 'potencia' not in columns:
                cursor.execute('ALTER TABLE users ADD COLUMN potencia TEXT')
            if 'pre_registro' not in columns:
                cursor.execute('ALTER TABLE users ADD COLUMN pre_registro INTEGER DEFAULT 0')
                        
            # Tabla de Radioexperimentadores
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS radioexperimentadores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    indicativo TEXT NOT NULL UNIQUE,
                    nombre_completo TEXT NOT NULL,
                    municipio TEXT,
                    estado TEXT,
                    pais TEXT,
                    fecha_nacimiento TEXT,
                    nacionalidad TEXT,
                    genero TEXT,
                    tipo_licencia TEXT,
                    fecha_expedicion TEXT,
                    estatus TEXT,
                    observaciones TEXT,
                    origen TEXT,
                    activo BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Verificar y agregar la columna 'origen' si no existe
            cursor.execute("PRAGMA table_info(radioexperimentadores)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'origen' not in columns:
                cursor.execute('ALTER TABLE radioexperimentadores ADD COLUMN origen TEXT')
            
            # Crear índices para búsquedas frecuentes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_radioexperimentadores_indicativo ON radioexperimentadores(indicativo)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_radioexperimentadores_estado ON radioexperimentadores(estado)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_radioexperimentadores_municipio ON radioexperimentadores(municipio)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_radioexperimentadores_estatus ON radioexperimentadores(estatus)')
            
            # Tabla de Reportes - Primero creamos la tabla si no existe
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reportes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    indicativo TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    zona TEXT,
                    sistema TEXT,
                    ciudad TEXT,
                    estado TEXT,
                    senal INTEGER,
                    observaciones TEXT,
                    reportado BOOLEAN DEFAULT 0,
                    origen TEXT,
                    tipo_reporte TEXT,
                    fecha_reporte DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (indicativo) REFERENCES radioexperimentadores(indicativo) ON DELETE CASCADE
                )
            ''')
            
            # Verificar y agregar la columna 'tipo_reporte' si no existe
            cursor.execute("PRAGMA table_info(reportes)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # Si la tabla ya existía, verificar y agregar columnas faltantes
            if 'tipo_reporte' not in columns:
                cursor.execute('ALTER TABLE reportes ADD COLUMN tipo_reporte TEXT')
            
            # Crear índices para búsquedas frecuentes en reportes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reportes_indicativo ON reportes(indicativo)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reportes_fecha ON reportes(fecha_reporte)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reportes_estado ON reportes(estado)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reportes_sistema ON reportes(sistema)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reportes_tipo_reporte ON reportes(tipo_reporte)')
            
            # Insertar datos iniciales
            self._insert_initial_data(cursor)
            
            conn.commit()
    
    def _normalizar_datos_existentes(self, cursor):
        """Normaliza los datos existentes en la base de datos para mantener consistencia"""
        try:
            # Normalizar radioexperimentadores
            cursor.execute("SELECT id, nombre_completo, municipio, estado, pais, nacionalidad, genero, tipo_licencia, estatus FROM radioexperimentadores")
            radios = cursor.fetchall()
            
            for radio in radios:
                datos_actualizados = {}
                
                # Función para formatear texto en formato oración
                def formatear_oracion(texto):
                    if not texto or not isinstance(texto, str):
                        return texto
                    return ' '.join(word.capitalize() for word in texto.split())
                
                # Aplicar formato a los campos que deben estar en formato oración
                for campo in ['nombre_completo', 'municipio', 'estado', 'pais']:
                    if radio[campo]:
                        datos_actualizados[campo] = formatear_oracion(radio[campo])
                
                # Asegurar que los campos de códigos estén en mayúsculas
                for campo in ['nacionalidad', 'genero', 'tipo_licencia', 'estatus']:
                    if radio[campo]:
                        datos_actualizados[campo] = radio[campo].upper()
                
                # Actualizar solo si hay cambios
                if datos_actualizados:
                    set_clause = ", ".join(f"{campo} = ?" for campo in datos_actualizados.keys())
                    valores = list(datos_actualizados.values())
                    valores.append(radio['id'])
                    
                    sql = f"UPDATE radioexperimentadores SET {set_clause} WHERE id = ?"
                    cursor.execute(sql, valores)
            
            return True
            
        except Exception as e:
            print(f"Error al normalizar datos existentes: {str(e)}")
            return False

    def _insert_initial_data(self, cursor):
        """Inserta los datos iniciales en las tablas"""
        # Normalizar datos existentes primero
        self._normalizar_datos_existentes(cursor)
        
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
    
    def update_user(self, user_id, username=None, full_name=None, email=None, phone=None, role=None, password=None, is_active=None, sistema_preferido=None, pre_registro=None):
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
            sistema_preferido: Código del sistema preferido (opcional)
            pre_registro: Valor de pre-registro (opcional)
            
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
                    
                if sistema_preferido is not None:
                    update_fields.append("sistema_preferido = ?")
                    params.append(sistema_preferido)
                    
                if pre_registro is not None:
                    update_fields.append("pre_registro = ?")
                    params.append(pre_registro)
                
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
                       last_login, created_at, updated_at, sistema_preferido, pre_registro
                FROM users 
                WHERE id = ?
            ''', (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_user_by_username(self, username):
        """Obtiene un usuario por su nombre de usuario"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, username, password_hash, full_name, email, phone, role, 
                       last_login, created_at, updated_at, sistema_preferido, pre_registro
                FROM users 
                WHERE username = ?
            ''', (username,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
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
    
    # =============================================
    # MÉTODOS PARA GESTIÓN DE RADIOEXPERIMENTADORES
    # =============================================
    
    def get_radioexperimentadores(self, incluir_inactivos=False, filtro=None):
        """Obtiene todos los radioexperimentadores
        
        Args:
            incluir_inactivos: Si es True, incluye los registros inactivos
            filtro: Diccionario con filtros opcionales (ej: {'indicativo': 'XE1ABC'})
            
        Returns:
            list: Lista de diccionarios con los datos de los radioexperimentadores
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM radioexperimentadores'
            params = []
            conditions = []
            
            if not incluir_inactivos:
                conditions.append('activo = 1')
                
            if filtro:
                for key, value in filtro.items():
                    if value:
                        conditions.append(f"{key} LIKE ?")
                        params.append(f"%{value}%")
            
            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)
            # Ordenar por indicativo
            query += " ORDER BY indicativo"
            cursor.execute(query, params)
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_radioexperimentador(self, id_or_indicativo):
        """Obtiene un radioexperimentador por su ID o indicativo"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if str(id_or_indicativo).isdigit():
                cursor.execute('SELECT * FROM radioexperimentadores WHERE id = ?', (int(id_or_indicativo),))
            else:
                cursor.execute('SELECT * FROM radioexperimentadores WHERE indicativo = ?', (str(id_or_indicativo).upper(),))
            
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_radioexperimentador_por_indicativo(self, indicativo):
        """Obtiene un radioexperimentador por su indicativo
        
        Args:
            indicativo: El indicativo del radioexperimentador
            
        Returns:
            dict: Los datos del radioexperimentador o None si no se encuentra
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM radioexperimentadores WHERE indicativo = ?',
                (indicativo.upper(),)
            )
            result = cursor.fetchone()
            return dict(result) if result else None
            
    def get_radioexperimentador_por_id(self, id_radio):
        """Obtiene un radioexperimentador por su ID
        
        Args:
            id_radio: El ID del radioexperimentador
            
        Returns:
            dict: Los datos del radioexperimentador o None si no se encuentra
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM radioexperimentadores WHERE id = ?',
                (id_radio,)
            )
            result = cursor.fetchone()
            return dict(result) if result else None
            
    def get_estados(self):
        """Obtiene la lista de estados únicos de la tabla QTH
        
        Returns:
            list: Lista de diccionarios con los estados disponibles
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT estado FROM qth WHERE estado IS NOT NULL ORDER BY estado')
            estados = [dict(row)['estado'] for row in cursor.fetchall()]
            return estados
            
    def activar_radioexperimentador(self, id_radio):
        """Activa un radioexperimentador previamente desactivado
        
        Args:
            id_radio: ID del radioexperimentador a activar
            
        Returns:
            bool: True si la operación fue exitosa, False en caso contrario
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    'UPDATE radioexperimentadores SET activo = 1, updated_at = ? WHERE id = ?',
                    (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), id_radio)
                )
                conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                conn.rollback()
                raise e
    
    def create_radioexperimentador(self, data):
        """Crea un nuevo registro de radioexperimentador
        
        Args:
            data: Diccionario con los datos del radioexperimentador
            
        Returns:
            int: ID del registro creado, o None en caso de error
        """
        required_fields = ['indicativo', 'nombre_completo']
        for field in required_fields:
            if field not in data or not data[field]:
                raise ValueError(f"El campo {field} es requerido")
        
        # Asegurar que el indicativo esté en mayúsculas
        data['indicativo'] = data['indicativo'].upper()
        
        # Filtrar solo los campos que existen en la tabla
        campos_permitidos = [
            'indicativo', 'nombre_completo', 'municipio', 'estado', 'pais',
            'fecha_nacimiento', 'nacionalidad', 'genero', 'tipo_licencia',
            'fecha_expedicion', 'estatus', 'observaciones', 'activo'
        ]
        
        data_filtrado = {k: v for k, v in data.items() if k in campos_permitidos}
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Construir la consulta dinámicamente
                columns = ', '.join(data_filtrado.keys())
                placeholders = ', '.join(['?'] * len(data_filtrado))
                values = list(data_filtrado.values())
                
                cursor.execute(
                    f'INSERT INTO radioexperimentadores ({columns}) VALUES ({placeholders})',
                    values
                )
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError as e:
                if 'UNIQUE constraint failed: radioexperimentadores.indicativo' in str(e):
                    raise ValueError("Ya existe un radioexperimentador con este indicativo")
                else:
                    raise
    
    def update_radioexperimentador(self, id_or_indicativo, data):
        """Actualiza los datos de un radioexperimentador
        
        Args:
            id_or_indicativo: ID o indicativo del radioexperimentador a actualizar
            data: Diccionario con los campos a actualizar
            
        Returns:
            bool: True si la actualización fue exitosa, False en caso contrario
        """
        if not data:
            return False
            
        # Filtrar solo los campos que existen en la tabla
        campos_permitidos = [
            'indicativo', 'nombre_completo', 'municipio', 'estado', 'pais',
            'fecha_nacimiento', 'nacionalidad', 'genero', 'tipo_licencia',
            'fecha_expedicion', 'estatus', 'observaciones', 'activo', 'updated_at'
        ]
        
        data_filtrado = {k: v for k, v in data.items() if k in campos_permitidos}
        
        if not data_filtrado:
            return False
            
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Asegurar que el indicativo esté en mayúsculas si se está actualizando
                if 'indicativo' in data_filtrado:
                    data_filtrado['indicativo'] = data_filtrado['indicativo'].upper()
                
                # Agregar la fecha de actualización
                data_filtrado['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Construir la consulta dinámicamente
                set_clause = ', '.join([f"{key} = ?" for key in data_filtrado.keys()])
                values = list(data_filtrado.values())
                
                # Agregar el ID o indicativo a los valores
                if str(id_or_indicativo).isdigit():
                    where_clause = 'id = ?'
                else:
                    where_clause = 'indicativo = ?'
                    
                values.append(id_or_indicativo)
                
                cursor.execute(
                    f'UPDATE radioexperimentadores SET {set_clause} WHERE {where_clause}',
                    values
                )
                conn.commit()
                return cursor.rowcount > 0
            except sqlite3.IntegrityError as e:
                if 'UNIQUE constraint failed: radioexperimentadores.indicativo' in str(e):
                    raise ValueError("Ya existe otro radioexperimentador con este indicativo")
                else:
                    raise
    
    def delete_radioexperimentador(self, id_or_indicativo, force_delete=False):
        """Elimina un radioexperimentador
        
        Args:
            id_or_indicativo: ID o indicativo del radioexperimentador a eliminar
            force_delete: Si es True, elimina físicamente el registro. Si es False, lo marca como inactivo
            
        Returns:
            bool: True si la operación fue exitosa, False en caso contrario
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Primero obtenemos el ID si se pasó un indicativo
                if isinstance(id_or_indicativo, str) and not id_or_indicativo.isdigit():
                    cursor.execute('SELECT id FROM radioexperimentadores WHERE indicativo = ?', 
                                 (id_or_indicativo.upper(),))
                    result = cursor.fetchone()
                    if not result:
                        return False
                    id_or_indicativo = result[0]
                
                if force_delete:
                    # Eliminación física del registro
                    cursor.execute('DELETE FROM radioexperimentadores WHERE id = ?', (id_or_indicativo,))
                else:
                    # Eliminación lógica (marcar como inactivo)
                    cursor.execute(
                        'UPDATE radioexperimentadores SET activo = 0, updated_at = ? WHERE id = ?',
                        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), id_or_indicativo)
                    )
                
                conn.commit()
                return cursor.rowcount > 0
                
            except sqlite3.IntegrityError as e:
                conn.rollback()
                if 'FOREIGN KEY constraint failed' in str(e):
                    raise ValueError("No se puede eliminar este registro porque tiene datos relacionados.")
                raise
            except Exception as e:
                conn.rollback()
                raise e
    
    def import_radioexperimentadores_from_excel(self, file_path):
        """Importa radioexperimentadores desde un archivo Excel
        
        Args:
            file_path: Ruta al archivo Excel
            
        Returns:
            tuple: (total, creados, actualizados, errores) con el resumen de la importación
        """
        try:
            import pandas as pd
            
            # Mapeo de columnas del Excel a los campos de la base de datos
            # Clave: nombre de columna en Excel (en mayúsculas)
            # Valor: tupla (nombre_campo_bd, es_requerido)
            column_mapping = {
                # Columna obligatoria
                'INDICATIVO': ('indicativo', True),
                
                # Columnas con múltiples nombres posibles (solo el primero es requerido si lo es)
                'NOMBRE COMPLETO': ('nombre_completo', True),  # Nombre preferido
                'NOMBRE': ('nombre_completo', False),  # Alternativa
                
                # Columnas opcionales
                'MUNICIPIO': ('municipio', False),
                'ESTADO': ('estado', False),
                'PAIS': ('pais', False),
                
                # Fechas con múltiples formatos
                'FECHA DE NACIMIENTO': ('fecha_nacimiento', False),
                'FECHA_NACIMIENTO': ('fecha_nacimiento', False),
                'FECHA_NAC': ('fecha_nacimiento', False),
                
                'NACIONALIDAD': ('nacionalidad', False),
                'GENERO': ('genero', False),
                
                # Tipo de licencia con múltiples formatos
                'TIPO DE LICENCIA': ('tipo_licencia', False),
                'TIPO_LICENCIA': ('tipo_licencia', False),
                'TIPO': ('tipo_licencia', False),
                'LICENCIA': ('tipo_licencia', False),
                
                # Fecha de expedición con múltiples formatos
                'FECHA DE EXPEDICION': ('fecha_expedicion', False),
                'FECHA_EXPEDICION': ('fecha_expedicion', False),
                'FECHA_EXP': ('fecha_expedicion', False),
                
                'ESTATUS': ('estatus', False),
                'OBSERVACIONES': ('observaciones', False)
            }
            
            # Leer el archivo Excel
            df = pd.read_excel(file_path)
            
            # Normalizar los nombres de las columnas (mayúsculas y sin espacios extra)
            df.columns = [col.strip().upper() for col in df.columns]
            
            # Verificar columnas requeridas
            required_columns = [col for col, (_, required) in column_mapping.items() if required]
            missing_required = [col for col in required_columns if col not in df.columns]
            
            if missing_required:
                raise ValueError(f"Faltan columnas requeridas en el archivo: {', '.join(missing_required)}")
                
            # Mapeo inverso para encontrar el nombre de columna preferido
            field_to_col = {}
            for col, (field, _) in column_mapping.items():
                if col in df.columns and field not in field_to_col:
                    field_to_col[field] = col
            
            # Crear un diccionario de mapeo de columnas para renombrar
            rename_columns = {}
            for col in df.columns:
                for map_col, (field, _) in column_mapping.items():
                    if col == map_col:
                        rename_columns[col] = field
                        break
            
            # Renombrar las columnas
            df = df.rename(columns=rename_columns)
            
            # Convertir a lista de diccionarios
            records = df.to_dict('records')
            
            # Procesar cada registro
            total = len(records)
            creados = 0
            actualizados = 0
            errores = []
            
            for i, record in enumerate(records, 1):
                try:
                    # Verificar si el registro ya existe (por indicativo)
                    existente = self.get_radioexperimentador(record['indicativo'])
                    
                    if existente:
                        # Actualizar registro existente
                        self.update_radioexperimentador(existente['id'], record)
                        actualizados += 1
                    else:
                        # Crear nuevo registro
                        self.create_radioexperimentador(record)
                        creados += 1
                        
                except Exception as e:
                    errores.append({
                        'fila': i + 1,  # +1 porque los DataFrames empiezan en 0
                        'indicativo': record.get('indicativo', 'Desconocido'),
                        'error': str(e)
                    })
            
            return total, creados, actualizados, errores
            
        except Exception as e:
            raise Exception(f"Error al procesar el archivo: {str(e)}")
    
    # =============================================
    # MÉTODOS PARA GESTIÓN DE ZONAS
    # =============================================
    
    def get_zonas(self, incluir_inactivas=False):
        """Obtiene todas las zonas"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM zonas'
            params = []

            if not incluir_inactivas:
                query += ' WHERE activo = 1'

            query += ' ORDER BY zona'
            cursor.execute(query, params)

            # Asegurarse de que el resultado tenga el formato correcto
            zonas = []
            for row in cursor.fetchall():
                zona = dict(row)
                # Si la zona tiene 'codigo' en lugar de 'zona', lo mapeamos
                if 'codigo' in zona and 'zona' not in zona:
                    zona['zona'] = zona.pop('codigo')
                zonas.append(zona)
            return zonas

    def get_estados(self, incluir_extranjero=True):
        """Obtiene todos los estados de la tabla qth"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT estado, abreviatura FROM qth'
            params = []

            if not incluir_extranjero:
                query += ' WHERE estado != "Extranjero"'

            query += ' ORDER BY estado'
            cursor.execute(query, params)

            return [dict(row) for row in cursor.fetchall()]
    
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
        
    def save_reporte(self, reporte_data):
        """
        Guarda un nuevo reporte en la base de datos
        
        Args:
            reporte_data (dict): Diccionario con los datos del reporte que debe contener:
                - indicativo (str): Indicativo del radioexperimentador
                - sistema (str): Sistema de comunicación utilizado
                - fecha_reporte (str): Fecha del reporte en formato 'dd/mm/yyyy'
                - tipo_reporte (str): Tipo de reporte (ej. 'Boletín')
                - senal (int, optional): Señal reportada (por defecto: 59)
                - nombre (str, optional): Nombre del operador
                - ciudad (str, optional): Ciudad del operador
                - estado (str, optional): Estado del operador
                - origen (str, optional): Origen del reporte
                - observaciones (str, optional): Observaciones adicionales
                
        Returns:
            int: ID del reporte guardado o None si hubo un error
        """
        try:
            # Validar campos obligatorios
            required_fields = ['indicativo', 'sistema', 'fecha_reporte', 'tipo_reporte']
            for field in required_fields:
                if field not in reporte_data or not reporte_data[field]:
                    raise ValueError(f"El campo '{field}' es obligatorio")
            
            # Asegurar que el indicativo esté en mayúsculas
            reporte_data['indicativo'] = reporte_data['indicativo'].upper()
            
            # Establecer valores por defecto
            if 'senal' not in reporte_data or not reporte_data['senal']:
                reporte_data['senal'] = 59
            
            # Convertir la fecha al formato YYYY-MM-DD para SQLite
            try:
                fecha_obj = datetime.strptime(reporte_data['fecha_reporte'], '%d/%m/%Y')
                fecha_sql = fecha_obj.strftime('%Y-%m-%d')
            except ValueError as e:
                raise ValueError("Formato de fecha inválido. Use el formato dd/mm/yyyy") from e
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Insertar el reporte en la base de datos
                cursor.execute('''
                    INSERT INTO reportes (
                        indicativo, nombre, zona, sistema, ciudad, estado, 
                        senal, observaciones, origen, tipo_reporte, fecha_reporte
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    reporte_data['indicativo'],
                    reporte_data.get('nombre', ''),
                    reporte_data.get('zona', ''),
                    reporte_data['sistema'],
                    reporte_data.get('ciudad', ''),
                    reporte_data.get('estado', ''),
                    reporte_data['senal'],
                    reporte_data.get('observaciones', ''),
                    reporte_data.get('origen', ''),
                    reporte_data['tipo_reporte'],
                    fecha_sql
                ))
                
                reporte_id = cursor.lastrowid
                conn.commit()
                return reporte_id
                
        except sqlite3.IntegrityError as e:
            if 'FOREIGN KEY constraint failed' in str(e):
                raise ValueError("El indicativo no existe en la base de datos") from e
            raise
        except Exception as e:
            if 'conn' in locals():
                conn.rollback()
            print(f"Error al guardar el reporte: {str(e)}")
            raise

if __name__ == "__main__":
    # Crear la base de datos y tablas si no existen
    db = FMREDatabase()
    print("Base de datos inicializada correctamente.")
