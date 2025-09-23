import database
db = database.FMREDatabase()

# Verificar si XE2MBE existe específicamente
print("=== CONSULTA ESPECÍFICA PARA XE2MBE ===")
result = db.get_radioexperimentador_por_indicativo('XE2MBE')
print(f'Resultado de búsqueda para XE2MBE: {result}')

if result:
    print('\nCampos encontrados para XE2MBE:')
    for key, value in result.items():
        print(f'  {key}: {value}')
else:
    print('\n❌ XE2MBE NO existe en la base de datos')

# Ver todos los radioexperimentadores activos
print("\n=== TODOS LOS RADIOEXPERIMENTADORES ACTIVOS ===")
radios = db.get_radioexperimentadores(incluir_inactivos=False)
print(f'Total de radioexperimentadores activos: {len(radios)}')

if radios:
    print('\nPrimeros 10 radioexperimentadores:')
    for radio in radios[:10]:
        estado = radio.get("estado") or "Sin estado"
        municipio = radio.get("municipio") or "Sin municipio"
        print(f'  - {radio["indicativo"]}: {radio["nombre_completo"]} ({estado} - {municipio})')

    # Buscar indicativos que empiecen con XE2
    xe2_radios = [r for r in radios if r['indicativo'].startswith('XE2')]
    print(f'\nIndicativos que empiecen con XE2: {len(xe2_radios)}')
    for radio in xe2_radios:
        estado = radio.get("estado") or "Sin estado"
        municipio = radio.get("municipio") or "Sin municipio"
        print(f'  - {radio["indicativo"]}: {radio["nombre_completo"]} ({estado} - {municipio})')

    # Buscar específicamente XE2MBE en la lista
    xe2mbe_in_list = [r for r in radios if r['indicativo'] == 'XE2MBE']
    if xe2mbe_in_list:
        print(f'\n✅ XE2MBE SÍ existe en la lista de radioexperimentadores:')
        for radio in xe2mbe_in_list:
            estado = radio.get("estado") or "Sin estado"
            municipio = radio.get("municipio") or "Sin municipio"
            print(f'  - {radio["indicativo"]}: {radio["nombre_completo"]} ({estado} - {municipio})')
    else:
        print('\n❌ XE2MBE NO aparece en la lista de radioexperimentadores')
else:
    print('No hay radioexperimentadores en la base de datos')

# También probar variaciones de búsqueda
print("\n=== PRUEBA DE VARIACIONES ===")
variations = ['xe2mbe', 'XE2mbe', 'Xe2Mbe', 'xe2MBE', 'XE2MBE']
for var in variations:
    result = db.get_radioexperimentador_por_indicativo(var)
    if result:
        print(f'✅ Encontrado con variación "{var}": {result["nombre_completo"]} ({result["estado"]} - {result["ciudad"]})')
        break
else:
    print('❌ No se encontró XE2MBE con ninguna variación')
