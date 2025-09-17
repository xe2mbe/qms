import sqlite3
import pandas as pd
from datetime import datetime
import os
import pytz

class FMREDatabase:
    def __init__(self, db_path="fmre_reports.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Inicializa la base de datos con las tablas necesarias"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabla de reportes - esquema limpio y consistente con campos HF
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_sign TEXT NOT NULL,
                operator_name TEXT NOT NULL,
                qth TEXT NOT NULL,
                ciudad TEXT NOT NULL,
                signal_report TEXT NOT NULL,
                zona TEXT NOT NULL,
                sistema TEXT NOT NULL,
                grid_locator TEXT,
                hf_frequency TEXT,
                hf_band TEXT,
                hf_mode TEXT,
                hf_power TEXT,
                observations TEXT,
                session_date TEXT NOT NULL,
                timestamp DATETIME DEFAULT (datetime('now', 'localtime')),
                region TEXT,
                signal_quality INTEGER,
                created_by TEXT
            )
        ''')
        
        # Agregar columna created_by si no existe (para bases de datos existentes)
        try:
            cursor.execute('ALTER TABLE reports ADD COLUMN created_by TEXT')
        except sqlite3.OperationalError:
            pass  # La columna ya existe
        
        # Tabla de sesiones
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_date DATE UNIQUE,
                total_participants INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de usuarios con sistema preferido
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT,
                role TEXT DEFAULT 'operator',
                preferred_system TEXT DEFAULT 'ASL',
                hf_frequency_pref TEXT,
                hf_mode_pref TEXT,
                hf_power_pref TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login DATETIME
            )
        ''')
        
        # Tabla de historial de estaciones - esquema consistente con campos HF
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS station_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_sign TEXT NOT NULL,
                operator_name TEXT NOT NULL,
                qth TEXT NOT NULL,
                ciudad TEXT NOT NULL,
                zona TEXT,
                sistema TEXT,
                grid_locator TEXT,
                hf_frequency TEXT,
                hf_band TEXT,
                hf_mode TEXT,
                hf_power TEXT,
                last_used DATETIME DEFAULT CURRENT_TIMESTAMP,
                use_count INTEGER DEFAULT 1,
                UNIQUE(call_sign, operator_name)
            )
        ''')
        
        # Ejecutar migraciones después de crear las tablas
        self._migrate_database(cursor)
        
        conn.commit()
        conn.close()
    
    def _migrate_database(self, cursor):
        """Migra la base de datos agregando columnas faltantes"""
        try:
            # Migrar datos existentes si es necesario
            cursor.execute("PRAGMA table_info(reports)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # Agregar columnas faltantes para compatibilidad
            if 'region' not in columns:
                cursor.execute('ALTER TABLE reports ADD COLUMN region TEXT')
            if 'signal_quality' not in columns:
                cursor.execute('ALTER TABLE reports ADD COLUMN signal_quality INTEGER')
            if 'grid_locator' not in columns:
                cursor.execute('ALTER TABLE reports ADD COLUMN grid_locator TEXT')
            if 'hf_frequency' not in columns:
                cursor.execute('ALTER TABLE reports ADD COLUMN hf_frequency TEXT')
            if 'hf_band' not in columns:
                cursor.execute('ALTER TABLE reports ADD COLUMN hf_band TEXT')
            if 'hf_mode' not in columns:
                cursor.execute('ALTER TABLE reports ADD COLUMN hf_mode TEXT')
            if 'hf_power' not in columns:
                cursor.execute('ALTER TABLE reports ADD COLUMN hf_power TEXT')
            
            # Migrar tabla de usuarios para agregar preferred_system y campos HF
            cursor.execute("PRAGMA table_info(users)")
            user_columns = [column[1] for column in cursor.fetchall()]
            if 'preferred_system' not in user_columns:
                cursor.execute('ALTER TABLE users ADD COLUMN preferred_system TEXT DEFAULT "ASL"')
            if 'hf_frequency_pref' not in user_columns:
                cursor.execute('ALTER TABLE users ADD COLUMN hf_frequency_pref TEXT')
            if 'hf_mode_pref' not in user_columns:
                cursor.execute('ALTER TABLE users ADD COLUMN hf_mode_pref TEXT')
            if 'hf_power_pref' not in user_columns:
                cursor.execute('ALTER TABLE users ADD COLUMN hf_power_pref TEXT')
                
            # Migrar datos de estado/ciudad si existen columnas separadas
            if 'estado' in columns and 'ciudad' in columns:
                # Migrar estado a qth si qth está vacío
                cursor.execute('''
                    UPDATE reports 
                    SET qth = COALESCE(estado, qth)
                    WHERE qth IS NULL OR qth = ''
                ''')
                # Asegurar que ciudad tenga datos
                cursor.execute('''
                    UPDATE reports 
                    SET ciudad = COALESCE(ciudad, qth, 'N/A')
                    WHERE ciudad IS NULL OR ciudad = ''
                ''')
                
        except Exception as e:
            print(f"Error durante la migración: {e}")
    
    def add_report(self, call_sign, operator_name, qth, ciudad, signal_report, zona, sistema, grid_locator="", hf_frequency="", hf_band="", hf_mode="", hf_power="", observations="", session_date=None, created_by=None):
        """Agrega un nuevo reporte a la base de datos"""
        if session_date is None:
            # Usar zona horaria de México para la fecha de sesión
            mexico_tz = pytz.timezone('America/Mexico_City')
            session_date = datetime.now(mexico_tz).date()
        
        # Extraer región del estado
        if qth == "Extranjera":
            region = "EX"
        else:
            # Buscar código del estado
            states = {v: k for k, v in self._get_mexican_states().items()}
            region = states.get(qth, "XX")
        
        # Convertir señal a calidad numérica (1=mala, 2=regular, 3=buena)
        signal_quality = self._convert_signal_to_quality(signal_report)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO reports (call_sign, operator_name, qth, ciudad, signal_report, zona, sistema,
                               grid_locator, hf_frequency, hf_band, hf_mode, hf_power, observations, session_date, region, signal_quality, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (call_sign.upper(), operator_name.title(), qth.upper(), ciudad.title(), signal_report, zona, sistema,
                  grid_locator.upper() if grid_locator else None, hf_frequency or None, hf_band or None, 
                  hf_mode or None, hf_power or None, observations, session_date, region, signal_quality, created_by))
        except sqlite3.OperationalError as e:
            if "no column named" in str(e):
                # Fallback para compatibilidad con esquemas antiguos
                cursor.execute("PRAGMA table_info(reports)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'estado' in columns and 'ciudad' in columns:
                    cursor.execute('''
                        INSERT INTO reports (call_sign, operator_name, qth, estado, ciudad, signal_report, zona, sistema,
                                           grid_locator, hf_frequency, hf_band, hf_mode, hf_power, observations, session_date, region, signal_quality)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (call_sign.upper(), operator_name.title(), qth.upper(), qth.upper(), ciudad.title(), signal_report, zona, sistema,
                          grid_locator.upper() if grid_locator else None, hf_frequency or None, hf_band or None,
                          hf_mode or None, hf_power or None, observations, session_date, region, signal_quality))
                else:
                    raise Exception(f"Estructura de base de datos incompatible: {e}")
            else:
                raise e
        
        # Actualizar historial de estaciones
        cursor.execute('''
            INSERT OR REPLACE INTO station_history 
            (call_sign, operator_name, qth, ciudad, zona, sistema, grid_locator, hf_frequency, hf_band, hf_mode, hf_power, last_used, use_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), 
                    COALESCE((SELECT use_count FROM station_history WHERE call_sign = ?) + 1, 1))
        ''', (call_sign.upper(), operator_name.title(), qth.upper(), ciudad.title(), zona, sistema, 
              grid_locator.upper() if grid_locator else None, hf_frequency or None, hf_band or None, 
              hf_mode or None, hf_power or None, call_sign.upper()))
        
        # Actualizar contador de sesión
        cursor.execute('''
            INSERT OR REPLACE INTO sessions (session_date, total_participants)
            VALUES (?, (
                SELECT COUNT(DISTINCT call_sign) 
                FROM reports 
                WHERE session_date = ?
            ))
        ''', (session_date, session_date))
        
        conn.commit()
        conn.close()
        return cursor.lastrowid
    
    def _get_mexican_states(self):
        """Retorna diccionario de estados mexicanos con códigos de 3 letras"""
        return {
            'AGS': 'Aguascalientes',
            'BCN': 'Baja California',
            'BCS': 'Baja California Sur',
            'CAM': 'Campeche',
            'CHP': 'Chiapas',
            'CHH': 'Chihuahua',
            'COA': 'Coahuila',
            'COL': 'Colima',
            'CMX': 'Ciudad de México',
            'DUR': 'Durango',
            'GTO': 'Guanajuato',
            'GRO': 'Guerrero',
            'HID': 'Hidalgo',
            'JAL': 'Jalisco',
            'MEX': 'Estado de México',
            'MIC': 'Michoacán',
            'MOR': 'Morelos',
            'NAY': 'Nayarit',
            'NLE': 'Nuevo León',
            'OAX': 'Oaxaca',
            'PUE': 'Puebla',
            'QRO': 'Querétaro',
            'ROO': 'Quintana Roo',
            'SLP': 'San Luis Potosí',
            'SIN': 'Sinaloa',
            'SON': 'Sonora',
            'TAB': 'Tabasco',
            'TAM': 'Tamaulipas',
            'TLA': 'Tlaxcala',
            'VER': 'Veracruz',
            'YUC': 'Yucatán',
            'ZAC': 'Zacatecas'
        }
    
    def _validate_grid_locator(self, grid_locator):
        """Valida formato de Grid Locator con niveles progresivos
        - Mínimo 4 caracteres requeridos
        - Niveles: DL74 (4), DL74QB (6), DL74QB44 (8), DL74QB44PG (10)
        """
        if not grid_locator:
            return True, ""  # Opcional
        
        grid_locator = grid_locator.upper().strip()
        
        # Mínimo 4 caracteres requeridos
        if len(grid_locator) < 4:
            return False, "Grid Locator debe tener mínimo 4 caracteres (ej: DL74)"
        
        # Máximo 10 caracteres
        if len(grid_locator) > 10:
            return False, "Grid Locator debe tener máximo 10 caracteres"
        
        # Validar longitudes permitidas: 4, 6, 8, 10
        if len(grid_locator) not in [4, 6, 8, 10]:
            return False, "Grid Locator debe tener 4, 6, 8 o 10 caracteres"
        
        import re
        
        # Nivel 1: DL74 (4 chars) - 2 letras A-R + 2 números
        if len(grid_locator) == 4:
            if not re.match(r'^[A-R]{2}[0-9]{2}$', grid_locator):
                return False, "Formato inválido para 4 chars. Ejemplo: DL74"
        
        # Nivel 2: DL74QB (6 chars) - + 2 letras A-X
        elif len(grid_locator) == 6:
            if not re.match(r'^[A-R]{2}[0-9]{2}[A-X]{2}$', grid_locator):
                return False, "Formato inválido para 6 chars. Ejemplo: DL74QB"
        
        # Nivel 3: DL74QB44 (8 chars) - + 2 números
        elif len(grid_locator) == 8:
            if not re.match(r'^[A-R]{2}[0-9]{2}[A-X]{2}[0-9]{2}$', grid_locator):
                return False, "Formato inválido para 8 chars. Ejemplo: DL74QB44"
        
        # Nivel 4: DL74QB44PG (10 chars) - + 2 letras A-X
        elif len(grid_locator) == 10:
            if not re.match(r'^[A-R]{2}[0-9]{2}[A-X]{2}[0-9]{2}[A-X]{2}$', grid_locator):
                return False, "Formato inválido para 10 chars. Ejemplo: DL74QB44PG"
        
        return True, ""
    
    def _convert_signal_to_quality(self, signal_report):
        """Convierte el reporte de señal a calidad numérica"""
        signal_lower = signal_report.lower()
        if any(word in signal_lower for word in ['buena', 'excelente', 'fuerte', '5']):
            return 3
        elif any(word in signal_lower for word in ['regular', 'media', '3', '4']):
            return 2
        else:
            return 1
    
    def get_all_reports(self, session_date=None):
        """Obtiene todos los reportes, opcionalmente filtrados por fecha"""
        conn = sqlite3.connect(self.db_path)
        
        if session_date:
            query = "SELECT * FROM reports WHERE session_date = ? ORDER BY timestamp DESC"
            df = pd.read_sql_query(query, conn, params=(session_date,))
        else:
            query = "SELECT * FROM reports ORDER BY timestamp DESC"
            df = pd.read_sql_query(query, conn)
        
        conn.close()
        return df
    
    def update_report(self, report_id, **kwargs):
        """Actualiza un reporte existente"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Construir query dinámicamente
        set_clause = ", ".join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values()) + [report_id]
        
        cursor.execute(f"UPDATE reports SET {set_clause} WHERE id = ?", values)
        rows_affected = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return rows_affected
    
    def delete_report(self, report_id):
        """Elimina un reporte"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        return rows_affected
    
    def get_statistics(self, session_date=None):
        """Obtiene estadísticas de los reportes"""
        conn = sqlite3.connect(self.db_path)
        
        base_query = "FROM reports"
        where_clause = ""
        params = ()
        
        if session_date:
            where_clause = " WHERE session_date = ?"
            params = (session_date,)
        
        # Estadísticas generales
        stats = {}
        
        # Total de participantes únicos
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(DISTINCT call_sign) {base_query} {where_clause}", params)
        stats['total_participants'] = cursor.fetchone()[0]
        
        # Total de reportes
        cursor.execute(f"SELECT COUNT(*) {base_query} {where_clause}", params)
        stats['total_reports'] = cursor.fetchone()[0]
        
        # Participantes por región
        query = f"SELECT region, COUNT(DISTINCT call_sign) as count {base_query} {where_clause} GROUP BY region ORDER BY count DESC"
        stats['by_region'] = pd.read_sql_query(query, conn, params=params)
        
        # Ranking de estaciones más activas
        query = f"SELECT call_sign, operator_name, COUNT(*) as reports_count {base_query} {where_clause} GROUP BY call_sign ORDER BY reports_count DESC LIMIT 10"
        stats['most_active'] = pd.read_sql_query(query, conn, params=params)
        
        # Distribución de calidad de señal
        query = f"SELECT signal_quality, COUNT(*) as count {base_query} {where_clause} GROUP BY signal_quality"
        stats['signal_quality'] = pd.read_sql_query(query, conn, params=params)
        
        # Reportes por zona (total de reportes, no participantes únicos)
        query = f"SELECT zona, COUNT(*) as count {base_query} {where_clause} GROUP BY zona ORDER BY count DESC"
        stats['by_zona'] = pd.read_sql_query(query, conn, params=params)
        
        # Reportes por sistema (total de reportes, no participantes únicos)
        query = f"SELECT sistema, COUNT(*) as count {base_query} {where_clause} GROUP BY sistema ORDER BY count DESC"
        stats['by_sistema'] = pd.read_sql_query(query, conn, params=params)
        
        # Reportes por hora
        query = f"SELECT strftime('%H', timestamp) as hour, COUNT(*) as count {base_query} {where_clause} GROUP BY hour ORDER BY hour"
        stats['by_hour'] = pd.read_sql_query(query, conn, params=params)
        
        # Rankings - Top zona (incluir empates)
        if not stats['by_zona'].empty:
            max_count = stats['by_zona']['count'].max()
            top_zonas = stats['by_zona'][stats['by_zona']['count'] == max_count]
            zona_names = ', '.join(top_zonas['zona'].tolist())
            stats['top_zona'] = {'zona': zona_names, 'count': max_count}
        
        # Rankings - Top sistema (incluir empates)
        if not stats['by_sistema'].empty:
            max_count = stats['by_sistema']['count'].max()
            top_sistemas = stats['by_sistema'][stats['by_sistema']['count'] == max_count]
            sistema_names = ', '.join(top_sistemas['sistema'].tolist())
            stats['top_sistema'] = {'sistema': sistema_names, 'count': max_count}
        
        # Rankings - Top indicativo (incluir empates)
        if not stats['most_active'].empty:
            max_count = stats['most_active']['reports_count'].max()
            top_calls = stats['most_active'][stats['most_active']['reports_count'] == max_count]
            call_names = ', '.join(top_calls['call_sign'].tolist())
            stats['top_call_sign'] = {'call_sign': call_names, 'count': max_count}
        
        conn.close()
        return stats
    
    def search_reports(self, search_term, filters=None):
        """Busca reportes por indicativo, nombre o QTH con filtros opcionales"""
        conn = sqlite3.connect(self.db_path)
        
        # Query base
        where_conditions = []
        params = []
        
        # Búsqueda por término
        if search_term:
            where_conditions.append("(call_sign LIKE ? OR operator_name LIKE ? OR ciudad LIKE ? OR qth LIKE ? OR grid_locator LIKE ? OR hf_frequency LIKE ?)")
            search_pattern = f"%{search_term}%"
            params.extend([search_pattern, search_pattern, search_pattern, search_pattern, search_pattern, search_pattern])
        
        # Aplicar filtros adicionales
        if filters:
            if filters.get('session_date'):
                where_conditions.append("session_date = ?")
                params.append(filters['session_date'])
            
            if filters.get('zona') and filters['zona'] != 'Todas':
                where_conditions.append("zona = ?")
                params.append(filters['zona'])
            
            if filters.get('sistema') and filters['sistema'] != 'Todos':
                where_conditions.append("sistema = ?")
                params.append(filters['sistema'])
        
        # Construir query final
        query = "SELECT * FROM reports"
        if where_conditions:
            query += " WHERE " + " AND ".join(where_conditions)
        query += " ORDER BY timestamp DESC"
        
        df = pd.read_sql_query(query, conn, params=params)
        
        conn.close()
        return df
    
    def get_distinct_zones(self):
        """Obtiene las zonas únicas de la base de datos"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT zona FROM reports WHERE zona IS NOT NULL ORDER BY zona")
        zones = [row[0] for row in cursor.fetchall()]
        conn.close()
        return zones
    
    def get_distinct_systems(self):
        """Obtiene los sistemas únicos de la base de datos"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT sistema FROM reports WHERE sistema IS NOT NULL ORDER BY sistema")
        systems = [row[0] for row in cursor.fetchall()]
        conn.close()
        return systems
    
    def get_motivational_stats(self):
        """Obtiene estadísticas motivacionales para competencia entre radioaficionados"""
        conn = sqlite3.connect(self.db_path)
        stats = {}
        
        # Estación más reportada del año
        current_year = datetime.now().year
        query = """
            SELECT call_sign, operator_name, COUNT(*) as total_reports
            FROM reports 
            WHERE strftime('%Y', session_date) = ?
            GROUP BY call_sign, operator_name
            ORDER BY total_reports DESC
            LIMIT 10
        """
        stats['top_stations_year'] = pd.read_sql_query(query, conn, params=(str(current_year),))
        
        # Estación más reportada del mes
        current_month = datetime.now().strftime('%Y-%m')
        query = """
            SELECT call_sign, operator_name, COUNT(*) as total_reports
            FROM reports 
            WHERE strftime('%Y-%m', session_date) = ?
            GROUP BY call_sign, operator_name
            ORDER BY total_reports DESC
            LIMIT 10
        """
        stats['top_stations_month'] = pd.read_sql_query(query, conn, params=(current_month,))
        
        # Zona más activa del año
        query = """
            SELECT zona, COUNT(DISTINCT call_sign) as unique_stations, COUNT(*) as total_reports
            FROM reports 
            WHERE strftime('%Y', session_date) = ?
            GROUP BY zona
            ORDER BY total_reports DESC
        """
        stats['top_zones_year'] = pd.read_sql_query(query, conn, params=(str(current_year),))
        
        # Zona más activa del mes
        query = """
            SELECT zona, COUNT(DISTINCT call_sign) as unique_stations, COUNT(*) as total_reports
            FROM reports 
            WHERE strftime('%Y-%m', session_date) = ?
            GROUP BY zona
            ORDER BY total_reports DESC
        """
        stats['top_zones_month'] = pd.read_sql_query(query, conn, params=(current_month,))
        
        # Sistema más usado del año
        query = """
            SELECT sistema, COUNT(DISTINCT call_sign) as unique_stations, COUNT(*) as total_reports
            FROM reports 
            WHERE strftime('%Y', session_date) = ?
            GROUP BY sistema
            ORDER BY total_reports DESC
        """
        stats['top_systems_year'] = pd.read_sql_query(query, conn, params=(str(current_year),))
        
        # Sistema más usado del mes
        query = """
            SELECT sistema, COUNT(DISTINCT call_sign) as unique_stations, COUNT(*) as total_reports
            FROM reports 
            WHERE strftime('%Y-%m', session_date) = ?
            GROUP BY sistema
            ORDER BY total_reports DESC
        """
        stats['top_systems_month'] = pd.read_sql_query(query, conn, params=(current_month,))
        
        # Estadísticas generales del año
        query = """
            SELECT 
                COUNT(*) as total_reports,
                COUNT(DISTINCT call_sign) as unique_stations,
                COUNT(DISTINCT session_date) as active_days
            FROM reports 
            WHERE strftime('%Y', session_date) = ?
        """
        stats['general_year'] = pd.read_sql_query(query, conn, params=(str(current_year),))
        
        # Estadísticas generales del mes
        query = """
            SELECT 
                COUNT(*) as total_reports,
                COUNT(DISTINCT call_sign) as unique_stations,
                COUNT(DISTINCT session_date) as active_days
            FROM reports 
            WHERE strftime('%Y-%m', session_date) = ?
        """
        stats['general_month'] = pd.read_sql_query(query, conn, params=(current_month,))
        
        conn.close()
        return stats
    
    def get_sessions(self):
        """Obtiene todas las sesiones registradas"""
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query("SELECT * FROM sessions ORDER BY session_date DESC", conn)
        conn.close()
        return df
    
    def get_station_history(self, limit=20):
        """Obtiene el historial de estaciones ordenado alfabéticamente por indicativo"""
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query('''
            SELECT * FROM station_history 
            ORDER BY call_sign ASC
            LIMIT ?
        ''', conn, params=(limit,))
        conn.close()
        return df
    
    def clear_station_history(self):
        """Limpia todo el historial de estaciones"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM station_history")
        conn.commit()
        conn.close()
        return cursor.rowcount
    
    def clean_orphaned_station_history(self):
        """Limpia registros huérfanos en station_history que no tienen reportes asociados"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM station_history 
            WHERE call_sign NOT IN (SELECT DISTINCT call_sign FROM reports)
        """)
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted_count
    
    def create_user(self, username, password_hash, full_name, email=None, role='operator'):
        """Crea un nuevo usuario"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO users (username, password_hash, full_name, email, role)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, password_hash, full_name, email, role))
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            return user_id
        except sqlite3.IntegrityError:
            conn.close()
            return None
    
    def get_user_by_username(self, username):
        """Obtiene un usuario por su nombre de usuario"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        
        conn.close()
        return user
    
    def update_user_preferred_system(self, username, preferred_system):
        """Actualiza el sistema preferido de un usuario"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET preferred_system = ? 
            WHERE username = ?
        ''', (preferred_system, username))
        
        conn.commit()
        conn.close()
        return cursor.rowcount > 0
    
    def get_user_preferred_system(self, username):
        """Obtiene el sistema preferido de un usuario"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT preferred_system FROM users WHERE username = ?', (username,))
        result = cursor.fetchone()
        
        conn.close()
        return result[0] if result else 'ASL'
    
    def update_user_hf_preferences(self, username, frequency, mode, power):
        """Actualiza las preferencias HF de un usuario"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET hf_frequency_pref = ?, hf_mode_pref = ?, hf_power_pref = ?
            WHERE username = ?
        ''', (frequency, mode, power, username))
        
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    
    def update_user_profile(self, user_id, full_name, email):
        """Actualiza información básica del perfil de usuario"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE users 
                SET full_name = ?, email = ?
                WHERE id = ?
            ''', (full_name, email, user_id))
            
            conn.commit()
            success = cursor.rowcount > 0
            conn.close()
            return success
        except Exception as e:
            conn.close()
            raise e
    
    def change_user_password(self, user_id, new_password):
        """Cambia la contraseña de un usuario"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Actualizar con nueva contraseña
            import hashlib
            password_hash = hashlib.sha256(new_password.encode()).hexdigest()
            cursor.execute('''
                UPDATE users 
                SET password_hash = ?
                WHERE id = ?
            ''', (password_hash, user_id))
            
            conn.commit()
            success = cursor.rowcount > 0
            conn.close()
            return success
        except Exception as e:
            conn.close()
            raise e
    
    def get_user(self, username):
        """Obtiene un usuario por nombre de usuario"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()
        if user:
            return dict(user)
        return None
    
    def get_all_users(self):
        """Obtiene todos los usuarios"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, full_name, role, email, created_at, last_login FROM users ORDER BY created_at DESC")
        users = cursor.fetchall()
        conn.close()
        
        # Convertir a lista de diccionarios
        if users:
            return [dict(user) for user in users]
        return []
    
    def update_user(self, user_id, full_name=None, role=None, email=None):
        """Actualiza información de un usuario"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if full_name:
            updates.append("full_name = ?")
            params.append(full_name)
        if role:
            updates.append("role = ?")
            params.append(role)
        if email:
            updates.append("email = ?")
            params.append(email)
        
        if updates:
            params.append(user_id)
            cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        
        conn.close()
        return cursor.rowcount > 0
    
    def delete_user(self, user_id):
        """Elimina un usuario"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return cursor.rowcount > 0
    
    def change_password(self, username, new_password_hash):
        """Cambia la contraseña de un usuario"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (new_password_hash, username))
        conn.commit()
        conn.close()
        return cursor.rowcount > 0
    
    def normalize_operator_names(self):
        """Normaliza todos los nombres de operadores y ciudades existentes a formato título"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Actualizar tabla reports - nombres de operadores y ciudades
        cursor.execute('SELECT id, operator_name, ciudad FROM reports WHERE operator_name IS NOT NULL OR ciudad IS NOT NULL')
        reports = cursor.fetchall()
        
        for report_id, name, ciudad in reports:
            updates = []
            params = []
            
            if name and name.strip():
                normalized_name = name.strip().title()
                updates.append('operator_name = ?')
                params.append(normalized_name)
            
            if ciudad and ciudad.strip():
                normalized_ciudad = ciudad.strip().title()
                updates.append('ciudad = ?')
                params.append(normalized_ciudad)
            
            if updates:
                params.append(report_id)
                cursor.execute(f'UPDATE reports SET {", ".join(updates)} WHERE id = ?', params)
        
        # Actualizar tabla station_history - solo actualizar ciudad (no operator_name para evitar UNIQUE constraint)
        cursor.execute('''
            UPDATE station_history 
            SET ciudad = CASE 
                WHEN ciudad IS NOT NULL AND TRIM(ciudad) != '' THEN
                    UPPER(SUBSTR(TRIM(ciudad), 1, 1)) || 
                    LOWER(SUBSTR(TRIM(ciudad), 2))
                ELSE ciudad 
            END
            WHERE ciudad IS NOT NULL
        ''')
        
        conn.commit()
        
        # Obtener conteo actualizado después de las operaciones
        cursor.execute('SELECT COUNT(*) FROM reports')
        reports_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM station_history')
        stations_count = cursor.fetchone()[0]
        
        conn.close()
        
        return reports_count + stations_count
    
    def update_last_login(self, username):
        """Actualiza la última fecha de login del usuario"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE username = ?", (username,))
        conn.commit()
        conn.close()
    
    def search_call_signs_dynamic(self, pattern, limit=10):
        """
        Busca indicativos dinámicamente usando solo la tabla reports.
        Retorna solo registros únicos por call_sign (el más reciente).
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Preparar patrón de búsqueda
        if not pattern:
            return []
            
        search_pattern = f"{pattern.upper()}%"
        
        # Buscar en reports agrupando por call_sign únicamente y tomando el más reciente
        cursor.execute('''
            SELECT call_sign, operator_name, qth, ciudad, zona, sistema, 
                   COUNT(*) as report_count,
                   MAX(timestamp) as last_report
            FROM reports 
            WHERE call_sign LIKE ? 
            GROUP BY call_sign
            ORDER BY report_count DESC, last_report DESC, call_sign ASC
            LIMIT ?
        ''', (search_pattern, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        # Formatear resultados para mantener compatibilidad con el código existente
        formatted_results = []
        for row in results:
            formatted_results.append({
                'call_sign': row[0],
                'operator_name': row[1], 
                'qth': row[2],
                'ciudad': row[3],
                'zona': row[4],
                'sistema': row[5],
                'use_count': row[6],  # report_count como use_count para compatibilidad
                'last_used': row[7]   # last_report como last_used
            })
        
        return formatted_results
    
    def diagnose_qth_data(self, pattern):
        """
        Función de diagnóstico para verificar datos QTH de estaciones específicas
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        search_pattern = f"{pattern.upper()}%"
        
        # Query detallado para diagnóstico
        cursor.execute('''
            SELECT call_sign, operator_name, qth, ciudad, zona, sistema, 
                   timestamp, session_date,
                   CASE 
                       WHEN qth IS NULL THEN 'NULL'
                       WHEN qth = '' THEN 'EMPTY'
                       WHEN TRIM(qth) = '' THEN 'WHITESPACE'
                       ELSE 'HAS_DATA'
                   END as qth_status
            FROM reports 
            WHERE call_sign LIKE ? 
            ORDER BY call_sign ASC, timestamp DESC
        ''', (search_pattern,))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
