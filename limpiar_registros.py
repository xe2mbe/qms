import sqlite3
from datetime import datetime

def limpiar_tablas():
    # Conectar a la base de datos
    conn = sqlite3.connect('qms.db')
    cursor = conn.cursor()
    
    try:
        # Limpiar reportes_rs
        cursor.execute("SELECT COUNT(*) FROM reportes_rs")
        total_reportes = cursor.fetchone()[0]
        
        if total_reportes > 0:
            # Crear respaldo de reportes_rs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reportes_rs_backup AS
                SELECT * FROM reportes_rs
            """)
            cursor.execute("DELETE FROM reportes_rs")
            print(f"Se eliminaron {total_reportes} registros de reportes_rs")
        else:
            print("No hay registros en reportes_rs para eliminar")
        
        # Limpiar estadisticas_rs
        cursor.execute("SELECT COUNT(*) FROM estadisticas_rs")
        total_estadisticas = cursor.fetchone()[0]
        
        if total_estadisticas > 0:
            # Crear respaldo de estadisticas_rs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS estadisticas_rs_backup AS
                SELECT * FROM estadisticas_rs
            """)
            cursor.execute("DELETE FROM estadisticas_rs")
            print(f"Se eliminaron {total_estadisticas} registros de estadisticas_rs")
        else:
            print("No hay registros en estadisticas_rs para eliminar")
        
        conn.commit()
        
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    print("=== LIMPIEZA DE REGISTROS DE REDES SOCIALES ===")
    print("Este script eliminará los registros de las tablas:")
    print("1. reportes_rs")
    print("2. estadisticas_rs")
    print("\nSe crearán copias de seguridad de ambas tablas antes de la eliminación.")
    
    confirmacion = input("\n¿Estás seguro de que deseas continuar? (s/n): ")
    
    if confirmacion.lower() == 's':
        print("\nIniciando limpieza...")
        limpiar_tablas()
        print("\nLimpieza completada. Se crearon copias de seguridad de las tablas originales.")
    else:
        print("\nOperación cancelada.")