import sqlite3

def check_rs_table():
    try:
        conn = sqlite3.connect('qms.db')
        cursor = conn.cursor()
        
        # Verificar la estructura de la tabla
        cursor.execute('PRAGMA table_info(rs)')
        columns = cursor.fetchall()
        print("\n=== Estructura de la tabla rs ===")
        for col in columns:
            print(f"{col[1]} ({col[2]}) - {'PRIMARY KEY' if col[5] > 0 else ''} {'NOT NULL' if col[3] else ''}")
        
        # Verificar el contenido de la tabla
        cursor.execute('SELECT * FROM rs')
        rows = cursor.fetchall()
        
        print("\n=== Contenido de la tabla rs ===")
        if not rows:
            print("No hay registros en la tabla rs")
        else:
            for row in rows:
                print(dict(zip([col[0] for col in cursor.description], row)))
        
        # Verificar si hay plataformas activas
        cursor.execute('SELECT COUNT(*) FROM rs WHERE is_active = 1')
        active_count = cursor.fetchone()[0]
        print(f"\nPlataformas activas: {active_count}")
        
    except sqlite3.Error as e:
        print(f"Error al acceder a la base de datos: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    check_rs_table()
