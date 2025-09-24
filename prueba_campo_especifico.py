from database import FMREDatabase

db = FMREDatabase()

print('=== PRUEBA ESPECÍFICA DEL CAMPO TIPO_REPORTE ===')

# Verificar que sí hay registros con 'Boletín'
with db.get_connection() as conn:
    cursor = conn.cursor()

    print('1. Verificando datos en tipo_reporte:')
    cursor.execute('SELECT tipo_reporte, COUNT(*) FROM reportes GROUP BY tipo_reporte')
    rows = cursor.fetchall()
    for row in rows:
        print(f'   {row[0]}: {row[1]} registros')

    print('\n2. Probando consultas específicas para tipo_reporte:')

    # Probar diferentes variaciones
    consultas = [
        ('tipo_reporte = ?', ['Boletín']),
        ('tipo_reporte LIKE ?', ['%Bolet%']),
        ('tipo_reporte LIKE ?', ['%boletin%']),
        ('tipo_reporte LIKE ?', ['%Boletin%']),
    ]

    for query_sql, params in consultas:
        cursor.execute(f'SELECT COUNT(*) FROM reportes WHERE {query_sql}', params)
        count = cursor.fetchone()[0]
        print(f'   {query_sql} {params} → {count} resultados')

print('\n3. Probando la función get_reportes_filtrados con diferentes términos:')

terminos = ['Boletin', 'boletin', 'tipo', 'reporte', 'xe2', 'durango']

for termino in terminos:
    try:
        reportes, total = db.get_reportes_filtrados(busqueda=termino)
        print(f'   "{termino}" → {len(reportes)} resultados')

        # Ver qué tipos de reporte encontró
        if reportes:
            tipos = set(r.get('tipo_reporte') for r in reportes)
            print(f'      Tipos encontrados: {tipos}')
    except Exception as e:
        print(f'   "{termino}" → Error: {e}')
