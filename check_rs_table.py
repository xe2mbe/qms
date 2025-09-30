from database import FMREDatabase
import sqlite3

def check_rs_table_structure():
    db = FMREDatabase()
    
    # Get table structure
    with sqlite3.connect(db.db_path) as conn:
        cursor = conn.cursor()
        
        # Get table info
        cursor.execute("PRAGMA table_info(rs)")
        columns = cursor.fetchall()
        
        print("\n=== RS Table Structure ===")
        for col in columns:
            print(f"{col[1]} ({col[2]}) - {'PRIMARY KEY' if col[5] > 0 else ''} {'NOT NULL' if col[3] else ''}")
        
        # Get all entries with raw SQL
        cursor.execute("SELECT * FROM rs")
        rows = cursor.fetchall()
        
        print("\n=== Raw RS Entries ===")
        if not rows:
            print("No entries found in the RS table.")
        else:
            for row in rows:
                print(f"ID: {row[0]}, Plataforma: {row[1]}, Nombre: {row[2]}, Activo: {bool(row[8])}")
        
        # Check for duplicates
        cursor.execute("""
            SELECT plataforma, nombre, COUNT(*) as count 
            FROM rs 
            GROUP BY LOWER(TRIM(plataforma)), LOWER(TRIM(nombre))
            HAVING count > 1
        """)
        
        duplicates = cursor.fetchall()
        if duplicates:
            print("\n=== Duplicate Entries Found ===")
            for dup in duplicates:
                print(f"Plataforma: {dup[0]}, Nombre: {dup[1]}, Count: {dup[2]}")
                
                # Show the duplicate entries
                cursor.execute("""
                    SELECT id, plataforma, nombre, is_active, created_at 
                    FROM rs 
                    WHERE LOWER(TRIM(plataforma)) = LOWER(TRIM(?)) 
                    AND LOWER(TRIM(nombre)) = LOWER(TRIM(?))
                    ORDER BY id
                """, (dup[0], dup[1]))
                
                for entry in cursor.fetchall():
                    print(f"  - ID: {entry[0]}, Activo: {bool(entry[3])}, Creado: {entry[4]}")
        else:
            print("\nNo duplicate entries found.")

if __name__ == "__main__":
    check_rs_table_structure()
