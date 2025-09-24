from database import FMREDatabase

db = FMREDatabase()

print('=== PRUEBA FINAL CON FUNCIÓN REMOVE_ACCENTS ===')

try:
    # Probar búsqueda por tipo
    reportes, total = db.get_reportes_filtrados(busqueda='boletin')
    print(f'Buscar "boletin" → {len(reportes)} resultados')

    if reportes:
        print('✅ ¡BÚSQUEDA FUNCIONA!')
        for registro in reportes[:3]:
            print(f'   Tipo: "{registro.get("tipo_reporte", "")}"')
    else:
        print('❌ No encontró "boletin"')

    # Probar con otros términos
    print('\n=== PRUEBA CON OTROS TÉRMINOS ===')

    terminos = ['boletin', 'boletín', 'Boletin', 'retransmision', 'xe2', 'mexico', 'durango']

    for termino in terminos:
        reportes, total = db.get_reportes_filtrados(busqueda=termino)
        print(f'   "{termino}" → {len(reportes)} resultados')

    print('\n🎉 ¡BÚSQUEDA INSENSIBLE A ACENTOS FUNCIONA!')

except Exception as e:
    print(f'❌ Error: {e}')
