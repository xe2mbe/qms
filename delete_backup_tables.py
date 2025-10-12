import sqlite3
import os

def check_and_drop_tables():
    # Ruta a la base de datos
    db_path = os.path.join(os.path.dirname(__file__), 'qms.db')
    
    if not os.path.exists(db_path):
        print(f"Error: No se encontró la base de datos en {db_path}")
        return
    
    try:
        # Conectar a la base de datos
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar si las tablas existen
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('reportes_rs_backup', 'estadisticas_rs_backup')")
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        if not existing_tables:
            print("No se encontraron tablas de respaldo para eliminar.")
            return
            
        # Eliminar las tablas si existen
        for table in existing_tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"Tabla {table} eliminada exitosamente.")
        
        # Confirmar cambios
        conn.commit()
        print("Operación completada con éxito.")
        
    except sqlite3.Error as e:
        print(f"Error al acceder a la base de datos: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    check_and_drop_tables()
