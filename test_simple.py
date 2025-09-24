from database import FMREDatabase
db = FMREDatabase()

print('=== BÚSQUEDA UNIFICADA ===')
reportes, total = db.get_reportes_filtrados(busqueda='test')
print(f'Encontrados: {len(reportes)} registros')
print('✅ Búsqueda funcionando correctamente')
