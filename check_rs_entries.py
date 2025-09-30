from database import FMREDatabase

def check_duplicate_rs_entries():
    db = FMREDatabase()
    entries = db.get_rs_entries(active_only=False)
    
    print("\n=== All RS Entries ===")
    for entry in entries:
        print(f"ID: {entry['id']}, Plataforma: {entry['plataforma']}, Nombre: {entry['nombre']}, Activo: {bool(entry['is_active'])}")
    
    # Check for duplicates
    from collections import defaultdict
    
    # Create a key based on platform and name (case-insensitive)
    entries_by_key = defaultdict(list)
    for entry in entries:
        key = (entry['plataforma'].lower().strip(), entry['nombre'].lower().strip())
        entries_by_key[key].append(entry)
    
    print("\n=== Potential Duplicates ===")
    has_duplicates = False
    for key, entries in entries_by_key.items():
        if len(entries) > 1:
            has_duplicates = True
            print(f"\nFound {len(entries)} entries for {key[0]} - {key[1]}:")
            for entry in entries:
                print(f"  - ID: {entry['id']}, Activo: {bool(entry['is_active'])}, Creado: {entry['created_at']}")
    
    if not has_duplicates:
        print("No duplicate entries found.")

if __name__ == "__main__":
    check_duplicate_rs_entries()
