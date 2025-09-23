
from validar_callsign import validar_indicativo
import utils
from database import FMREDatabase

# Simular el comportamiento de los pre-registros con HF
indicativo = 'n5jmd'
result = utils.validar_call_sign(indicativo)

print(f'Validando indicativo: {indicativo}')
print(f'Resultado: {result}')

# Simular la lógica de pre-llenado
if result['Zona'] == 'Extranjera':
    estado = 'Extranjero'
    zona = 'EXT'
    print(f'✅ Indicativo extranjero detectado')
    print(f'   Estado pre-llenado: {estado}')
    print(f'   Zona pre-llenada: {zona}')
else:
    print('❌ No es un indicativo extranjero')

# Simular configuración HF
sistema_preferido = 'HF'
frecuencia = '7.100'
modo = 'SSB'
potencia = 'Media (≤200W)'

print(f'\n📻 Configuración HF:')
print(f'   Sistema: {sistema_preferido}')
print(f'   Frecuencia: {frecuencia} MHz')
print(f'   Modo: {modo}')
print(f'   Potencia: {potencia}')

# Simular creación de registro
registro = {
    'indicativo': indicativo,
    'sistema': sistema_preferido,
    'fecha': '23/09/2025',
    'tipo_reporte': 'Boletín',
    'senal': '59'
}

# Agregar campos HF si el sistema es HF
if sistema_preferido == 'HF':
    registro.update({
        'frecuencia': frecuencia,
        'modo': modo,
        'potencia': potencia
    })

print(f'\n📋 Registro creado:')
for key, value in registro.items():
    print(f'   {key}: {value}')

print()
print('Probando otros indicativos:')
test_cases = ['XE1ABC', 'XE2XYZ', 'K5AB', 'DL1ABC', '4A1MX']
for test_case in test_cases:
    result = utils.validar_call_sign(test_case)
    print(f'{test_case:8} -> Zona: {result["Zona"]:12} Extranjero: {result["Zona"] == "Extranjera"}')

# Verificar que la base de datos tenga los campos HF
print('\n🔍 Verificando estructura de la base de datos:')
db = FMREDatabase()
try:
    # Obtener información de un usuario para verificar campos
    users = db.get_all_users()
    if users:
        user = users[0]
        print('✅ Campos disponibles en tabla users:')
        hf_fields = ['frecuencia', 'modo', 'potencia']
        for field in hf_fields:
            if field in user:
                print(f'   ✅ {field}: {user[field]}')
            else:
                print(f'   ❌ {field}: Campo no encontrado')
    else:
        print('⚠️ No hay usuarios en la base de datos para verificar')
except Exception as e:
    print(f'❌ Error al verificar base de datos: {e}')