"""
Script para reiniciar la tabla reportes_rs

Este script elimina la tabla reportes_rs si existe, para que sea recreada
con la estructura actualizada al reiniciar la aplicación.
"""
import sqlite3
import os

def reset_reportes_rs():
    db_path = "qms.db"
    backup_db_path = "qms_backup_before_reset.db"
    
    # Verificar si la base de datos existe
    if not os.path.exists(db_path):
        print("No se encontró la base de datos. No hay nada que hacer.")
        return
    
    try:
        # Crear una copia de seguridad de la base de datos actual
        import shutil
        shutil.copy2(db_path, backup_db_path)
        print(f"Se creó una copia de seguridad en: {backup_db_path}")
        
        # Conectar a la base de datos
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar si la tabla existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reportes_rs'")
        if cursor.fetchone():
            # Eliminar la tabla si existe
            cursor.execute("DROP TABLE reportes_rs")
            print("Tabla 'reportes_rs' eliminada exitosamente.")
        else:
            print("La tabla 'reportes_rs' no existe. No hay nada que eliminar.")
        
        # Cerrar la conexión
        conn.close()
        
        print("\n¡Listo! La próxima vez que inicies la aplicación, "
              "la tabla 'reportes_rs' se creará con la estructura actualizada.")
        
    except Exception as e:
        print(f"\n¡Error!: {str(e)}")
        print("\nSi ocurrió un error, la base de datos original no ha sido modificada.")
        print(f"Puedes restaurar manualmente desde la copia de seguridad: {backup_db_path}")

if __name__ == "__main__":
    print("=== Reinicio de la tabla reportes_rs ===\n")
    print("Este script realizará lo siguiente:")
    print("1. Creará una copia de seguridad de la base de datos actual")
    print("2. Eliminará la tabla 'reportes_rs' si existe")
    print("3. La aplicación la recreará con la estructura actualizada al iniciar\n")
    
    confirmacion = input("¿Deseas continuar? (s/n): ")
    if confirmacion.lower() == 's':
        reset_reportes_rs()
    else:
        print("\nOperación cancelada. No se realizaron cambios.")
    
    input("\nPresiona Enter para salir...")
