from database import FMREDatabase
import sqlite3

def fix_duplicate_rs_entries():
    """
    Fixes duplicate RS entries by keeping the most recent one and removing duplicates.
    Also adds a unique constraint to prevent future duplicates.
    """
    db = FMREDatabase()
    
    with sqlite3.connect(db.db_path) as conn:
        cursor = conn.cursor()
        
        print("\n=== Checking for duplicate RS entries ===")
        
        # Find all duplicate platform+name combinations
        cursor.execute("""
            SELECT plataforma, nombre, COUNT(*) as count, GROUP_CONCAT(id) as ids
            FROM rs 
            WHERE is_active = 1
            GROUP BY LOWER(TRIM(plataforma)), LOWER(TRIM(nombre))
            HAVING count > 1
        """)
        
        duplicates = cursor.fetchall()
        
        if not duplicates:
            print("No duplicate active entries found.")
            return
            
        print(f"Found {len(duplicates)} sets of duplicates to process...")
        
        for plataforma, nombre, count, ids_str in duplicates:
            ids = list(map(int, ids_str.split(',')))
            print(f"\nProcessing duplicates for: {plataforma} - {nombre}")
            print(f"Found {count} duplicates with IDs: {ids}")
            
            # Keep the most recent entry (highest ID)
            keep_id = max(ids)
            ids.remove(keep_id)
            
            print(f"Keeping ID {keep_id}, marking others as inactive")
            
            # Mark all but the most recent as inactive
            placeholders = ','.join(['?'] * len(ids))
            cursor.execute(
                f"UPDATE rs SET is_active = 0 WHERE id IN ({placeholders})",
                ids
            )
            
            print(f"Marked {len(ids)} entries as inactive")
        
        # Add a unique constraint if it doesn't exist
        print("\n=== Adding unique constraint if needed ===")
        try:
            # SQLite doesn't support adding UNIQUE constraint with ALTER TABLE directly
            # So we need to create a new table and copy the data
            
            # 1. Create a new table with the constraint
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rs_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plataforma TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    descripcion TEXT,
                    url TEXT,
                    administrador TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    UNIQUE(plataforma, nombre)
                )
            """)
            
            # 2. Copy only active, non-duplicate entries to the new table
            cursor.execute("""
                INSERT OR IGNORE INTO rs_new 
                (id, plataforma, nombre, descripcion, url, administrador, created_at, updated_at, is_active)
                SELECT id, plataforma, nombre, descripcion, url, administrador, created_at, updated_at, is_active
                FROM rs
                WHERE is_active = 1
                GROUP BY LOWER(TRIM(plataforma)), LOWER(TRIM(nombre))
            """)
            
            # 3. Drop the old table and rename the new one
            cursor.execute("DROP TABLE IF EXISTS rs_old")
            cursor.execute("ALTER TABLE rs RENAME TO rs_old")
            cursor.execute("ALTER TABLE rs_new RENAME TO rs")
            
            print("Successfully added unique constraint on (plataforma, nombre)")
            
        except sqlite3.Error as e:
            print(f"Error adding unique constraint: {e}")
            conn.rollback()
            print("Rolling back changes...")
            return
        
        conn.commit()
        print("\nCleanup completed successfully!")

if __name__ == "__main__":
    fix_duplicate_rs_entries()
