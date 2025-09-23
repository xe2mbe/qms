
from validar_callsign import validar_indicativo
import utils

# Simular el comportamiento de los pre-registros
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

print()
print('Probando otros indicativos:')
test_cases = ['XE1ABC', 'XE2XYZ', 'K5AB', 'DL1ABC', '4A1MX']
for test_case in test_cases:
    result = utils.validar_call_sign(test_case)
    print(f'{test_case:8} -> Zona: {result["Zona"]:12} Extranjero: {result["Zona"] == "Extranjera"}')