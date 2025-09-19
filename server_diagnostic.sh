#!/bin/bash

echo "=== DIAGNÓSTICO SERVIDOR QMS ==="
echo "Fecha: $(date)"
echo "=================================="

echo -e "\n1. ESTADO DE APACHE:"
sudo systemctl status apache2 --no-pager

echo -e "\n2. SITIOS HABILITADOS:"
ls -la /etc/apache2/sites-enabled/

echo -e "\n3. SITIOS DISPONIBLES:"
ls -la /etc/apache2/sites-available/

echo -e "\n4. CONFIGURACIÓN QMS:"
if [ -f /etc/apache2/sites-available/qms.conf ]; then
    echo "--- Contenido de qms.conf ---"
    sudo cat /etc/apache2/sites-available/qms.conf
else
    echo "qms.conf NO EXISTE"
fi

echo -e "\n5. CONFIGURACIÓN DEFAULT:"
if [ -f /etc/apache2/sites-available/000-default.conf ]; then
    echo "--- Contenido de 000-default.conf ---"
    sudo cat /etc/apache2/sites-available/000-default.conf
else
    echo "000-default.conf NO EXISTE"
fi

echo -e "\n6. LOGS DE ERROR (últimas 20 líneas):"
sudo tail -20 /var/log/apache2/error.log

echo -e "\n7. ESTADO SERVICIO QMS:"
sudo systemctl status qms --no-pager 2>/dev/null || echo "Servicio QMS no encontrado"

echo -e "\n8. PROCESOS STREAMLIT:"
ps aux | grep streamlit | grep -v grep || echo "No hay procesos Streamlit corriendo"

echo -e "\n9. PUERTOS EN USO:"
sudo netstat -tlnp | grep -E ':(80|8501|443)' || echo "No se encontraron puertos web activos"

echo -e "\n10. TEST DE CONECTIVIDAD LOCAL:"
curl -I http://localhost/fmre 2>/dev/null || echo "No responde /fmre"
curl -I http://localhost/qms 2>/dev/null || echo "No responde /qms"

echo -e "\n=== FIN DIAGNÓSTICO ==="
