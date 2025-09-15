# Sistema de Control de Reportes FMRE

Sistema web desarrollado en Python para llevar el control de la toma de reportes del boletín de la Federación Mexicana de Radio Experimentadores (FMRE).

## Características

- **Interfaz intuitiva**: Registro de reportes en tiempo real con formularios claros
- **Gestión completa**: Operaciones CRUD para reportes y operadores
- **Estadísticas automáticas**: Conteo por región, ranking de estaciones, gráficas de cobertura

- **Python 3.8+**
- **Sistema Operativo:** Windows, Linux, o macOS
- **RAM:** Mínimo 2GB, recomendado 4GB
- **Almacenamiento:** 1GB libre
- **Red:** Acceso a internet para envío de emails (opcional)

### 1. Preparación del Servidor

#### Opción A: Servidor Windows
```powershell
# Instalar Python desde python.org
# Verificar instalación
python --version
pip --version
```

#### Opción B: Servidor Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
├── app.py              # Aplicación principal Streamlit
├── database.py         # Gestión de base de datos
├── utils.py           # Funciones auxiliares y validaciones
├── exports.py         # Funciones de exportación
├── requirements.txt   # Dependencias
└── README.md         # Documentación
```
