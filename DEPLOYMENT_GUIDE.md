# 🚀 Guía de Instalación en Producción - Sistema FMRE

## 📋 Requisitos del Sistema

- **Python 3.8+**
- **Sistema Operativo:** Windows, Linux, o macOS
- **RAM:** Mínimo 2GB, recomendado 4GB
- **Almacenamiento:** 1GB libre
- **Red:** Acceso a internet para envío de emails (opcional)

## 🔧 Instalación Paso a Paso

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
```

### 2. Instalación del Sistema

```bash
# 1. Crear directorio del proyecto
mkdir fmre-system
cd fmre-system

# 2. Copiar todos los archivos del sistema:
# - app.py
# - database.py
# - auth.py
# - utils.py
# - exports.py
# - email_service.py
# - requirements.txt

# 3. Crear entorno virtual
python -m venv venv

# 4. Activar entorno virtual
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 5. Instalar dependencias
pip install -r requirements.txt
```

### 3. Configuración Inicial

#### A. Primera Ejecución
```bash
# Ejecutar por primera vez para crear la base de datos
streamlit run app.py
```

#### B. Cambiar Credenciales por Defecto
- **Usuario:** admin
- **Contraseña:** admin123
- ⚠️ **IMPORTANTE:** Cambiar inmediatamente en producción

### 4. Configuración de Producción

#### A. Configuración de Email SMTP (Opcional)
1. Ir a "Gestión de Usuarios" → "Configuración Email"
2. Configurar servidor SMTP:
   - **Gmail:** smtp.gmail.com:587
   - **Outlook:** smtp-mail.outlook.com:587
   - **Yahoo:** smtp.mail.yahoo.com:587

#### B. Configuración de Red
```bash
# Abrir puerto 8501 en firewall
# Windows:
netsh advfirewall firewall add rule name="FMRE System" dir=in action=allow protocol=TCP localport=8501

# Linux (UFW):
sudo ufw allow 8501
```

### 5. Ejecución en Producción

#### Opción A: Ejecución Simple
```bash
streamlit run app.py --server.port=8501 --server.address=0.0.0.0
```

#### Opción B: Como Servicio Windows
```powershell
# 1. Crear archivo run_fmre.bat
@echo off
cd /d "C:\ruta\a\tu\proyecto"
call venv\Scripts\activate
streamlit run app.py --server.port=8501 --server.address=0.0.0.0

# 2. Usar NSSM para crear servicio (descargar de nssm.cc)
nssm install "FMRE-System" "C:\ruta\a\tu\proyecto\run_fmre.bat"
nssm start "FMRE-System"
```

#### Opción C: Con PM2 en Linux (Recomendado)
```bash
# Instalar PM2
npm install -g pm2

# Crear archivo de configuración
cat > ecosystem.config.js << EOF
module.exports = {
  apps: [{
    name: 'fmre-system',
    script: 'streamlit',
    args: 'run app.py --server.port=8501 --server.address=0.0.0.0',
    cwd: '/ruta/a/tu/proyecto',
    interpreter: '/ruta/a/tu/venv/bin/python'
  }]
}
EOF

# Iniciar aplicación
pm2 start ecosystem.config.js
pm2 save
pm2 startup
```

## 🔐 Configuración de Seguridad

### 1. Credenciales
- Cambiar usuario/contraseña por defecto
- Crear usuarios operadores con permisos limitados
- Usar contraseñas seguras (8+ caracteres, mayúsculas, números, símbolos)

### 2. Red
- Configurar firewall para puerto 8501
- Considerar VPN para acceso remoto
- Usar HTTPS en producción (con reverse proxy)

### 3. Base de Datos
```bash
# Configurar permisos de archivo
chmod 664 fmre_reports.db
chown usuario:grupo fmre_reports.db
```

## 💾 Respaldos

### Respaldo Manual
```bash
# Copiar base de datos
cp fmre_reports.db backup_$(date +%Y%m%d_%H%M%S).db
```

### Respaldo Automático (Linux)
```bash
# Crear script backup.sh
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p backups
cp fmre_reports.db "backups/fmre_reports_$DATE.db"
find backups/ -name "*.db" -mtime +30 -delete

# Programar en crontab
0 2 * * * /ruta/a/backup.sh
```

## 🌐 Acceso al Sistema

- **URL Local:** http://localhost:8501
- **URL Red:** http://IP_SERVIDOR:8501
- **Panel Admin:** Menú "Gestión de Usuarios"

## 📊 Funcionalidades Principales

1. **Registro de Reportes:** Formulario principal para captura
2. **Dashboard:** Estadísticas y gráficas en tiempo real
3. **Ranking:** Competencia motivacional entre estaciones
4. **Búsqueda/Edición:** Gestión de reportes existentes
5. **Exportación:** CSV y Excel para análisis
6. **Gestión de Usuarios:** Control de acceso y roles

## 🔧 Mantenimiento

### Verificar Estado
```bash
# Con PM2
pm2 status
pm2 logs fmre-system

# Verificar puerto
netstat -tulpn | grep 8501
```

### Actualización
```bash
# 1. Detener servicio
pm2 stop fmre-system

# 2. Respaldar base de datos
cp fmre_reports.db fmre_reports_backup.db

# 3. Actualizar archivos de código
# 4. Actualizar dependencias
pip install -r requirements.txt --upgrade

# 5. Reiniciar servicio
pm2 start fmre-system
```

## ❗ Solución de Problemas

### Puerto Ocupado
```bash
# Encontrar proceso
netstat -tulpn | grep 8501
# Terminar proceso
kill -9 PID_DEL_PROCESO
```

### Permisos de Base de Datos
```bash
chmod 664 fmre_reports.db
chown $USER:$USER fmre_reports.db
```

### Logs de Debug
```bash
streamlit run app.py --logger.level=debug
```

## ✅ Checklist de Producción

- [ ] Python 3.8+ instalado
- [ ] Entorno virtual creado
- [ ] Dependencias instaladas
- [ ] Base de datos creada
- [ ] Credenciales cambiadas
- [ ] Firewall configurado
- [ ] Servicio configurado
- [ ] Respaldos programados
- [ ] Acceso verificado
- [ ] SMTP configurado (opcional)
- [ ] Usuarios de prueba creados
- [ ] Documentación entregada

## 📞 Soporte

Para problemas técnicos, proporcionar:
- Descripción del error
- Logs del sistema
- Pasos para reproducir
- Configuración del servidor

---

**¡Sistema FMRE listo para operación! 📻✨**
