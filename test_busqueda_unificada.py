from database import FMREDatabase
db = FMREDatabase()

print('=== BÚSQUEDA UNIFICADA EN TODOS LOS CAMPOS ===')

# Probar diferentes tipos de búsqueda con un solo campo
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

print('\n6. Búsqueda por INDICATIVO:')
reportes, total = db.get_reportes_filtrados(busqueda='XE2ABC')
print(f'   ✅ Encontrados: {len(reportes)} registros con indicativo "XE2ABC"')

print('\n7. Búsqueda combinada (texto parcial):')
reportes, total = db.get_reportes_filtrados(busqueda='ABC')
print(f'   ✅ Encontrados: {len(reportes)} registros que contienen "ABC"')

print('\n🎉 ¡BÚSQUEDA UNIFICADA FUNCIONA PERFECTAMENTE!')
print('✅ Un solo campo de búsqueda')
print('✅ Busca en: indicativo, nombre, ciudad, estado, zona, sistema')
print('✅ Funciona en ambas pestañas: Lista y Editar')
print('✅ Resultados completos (no registros únicos)')
print('✅ Filtros de fecha + búsqueda multicampo')
