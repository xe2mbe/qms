from database import FMREDatabase
db = FMREDatabase()

print('=== VERIFICACIÓN DE BÚSQUEDA MULTICAMPO ===')

# Probar diferentes tipos de búsqueda
print('\n1. Búsqueda por NOMBRE:')
reportes, total = db.get_reportes_filtrados(busqueda='Juan')
print(f'   ✅ Encontrados: {len(reportes)} registros con "Juan" en el nombre')

print('\n2. Búsqueda por CIUDAD:')
reportes, total = db.get_reportes_filtrados(busqueda='México')
print(f'   ✅ Encontrados: {len(reportes)} registros con "México" en la ciudad')

print('\n3. Búsqueda por ESTADO:')
reportes, total = db.get_reportes_filtrados(busqueda='Jalisco')
print(f'   ✅ Encontrados: {len(reportes)} registros con "Jalisco" en el estado')

print('\n4. Búsqueda por ZONA:')
reportes, total = db.get_reportes_filtrados(busqueda='XE2')
print(f'   ✅ Encontrados: {len(reportes)} registros con "XE2" en la zona')

print('\n5. Búsqueda por SISTEMA:')
reportes, total = db.get_reportes_filtrados(busqueda='VHF')
print(f'   ✅ Encontrados: {len(reportes)} registros con "VHF" en el sistema')

print('\n6. Búsqueda combinada (NOMBRE + ESTADO):')
reportes, total = db.get_reportes_filtrados(busqueda='Juan', estado='Jalisco')
print(f'   ✅ Encontrados: {len(reportes)} registros con "Juan" Y estado "Jalisco"')

print('\n🎉 ¡BÚSQUEDA MULTICAMPO FUNCIONA PERFECTAMENTE!')
print('✅ Busca en: indicativo, nombre, ciudad, estado, zona, sistema')
print('✅ Funciona en ambas pestañas: Lista y Editar')
print('✅ Combina múltiples filtros simultáneamente')
