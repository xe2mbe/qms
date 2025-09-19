import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
import io
import sqlite3
import numpy as np

from database import FMREDatabase
from utils import (
    validate_all_fields, format_call_sign, format_name, format_qth,
    get_mexican_states, format_timestamp, get_signal_quality_text,
    get_zonas, get_sistemas, validate_call_sign, validate_operator_name, 
    validate_ciudad, validate_estado, validate_signal_report, get_estados_list,
    validate_call_sign_zone_consistency, detect_inconsistent_data, map_qth_to_estado
)
from exports import FMREExporter
from auth import AuthManager
from email_service import EmailService
import secrets
import string

def get_bulletin_number(target_date):
    """
    Calcula el número de boletín basado en la fecha.
    El primer domingo del año es el boletín 1, el segundo el 2, etc.
    """
    # Obtener el primer día del año
    first_day = date(target_date.year, 1, 1)
    
    # Encontrar el primer domingo del año
    first_sunday = first_day + timedelta(days=(6 - first_day.weekday() + 1) % 7)
    
    # Si el primer día del año es domingo, es el boletín 1
    if first_day.weekday() == 6:  # 6 es domingo
        first_sunday = first_day
    
    # Calcular la diferencia en semanas y sumar 1 para el número de boletín
    week_diff = (target_date - first_sunday).days // 7 + 1
    
    # Asegurarnos de que el boletín no sea negativo o cero
    return max(1, week_diff)

# Definir funciones antes de usarlas
def show_db_admin():
    """Muestra la página de administración de base de datos (solo para admins)"""
    st.header("🔧 Administrador de Base de Datos")
    st.markdown("### Panel de Administración Avanzado")
    
    # Verificar que el usuario sea admin
    if current_user['role'] != 'admin':
        st.error("❌ Acceso denegado. Solo los administradores pueden acceder a esta sección.")
        return
    
    # Advertencia de seguridad
    st.warning("⚠️ **ZONA DE ADMINISTRADOR**: Las operaciones en esta sección pueden afectar permanentemente la base de datos. Usa con precaución.")
    
    # Crear pestañas para organizar las funciones
    tab1, tab2, tab3, tab4 = st.tabs(["🔍 Consultas SQL", "🗑️ Eliminar Registros", "📊 Estadísticas DB", "🔧 Mantenimiento"])
    
    with tab1:
        st.subheader("🔍 Ejecutar Consultas SQL Directas")
        st.info("💡 Ejecuta consultas SQL personalizadas en la base de datos. Solo consultas SELECT son seguras para exploración.")
        
        # Consultas predefinidas útiles
        st.markdown("**Consultas Predefinidas:**")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📋 Ver todos los reportes"):
                st.session_state.sql_query = "SELECT * FROM reports ORDER BY timestamp DESC LIMIT 100"
        
        with col2:
            if st.button("👥 Ver todos los usuarios"):
                st.session_state.sql_query = "SELECT id, username, full_name, email, role, created_at FROM users"
        
        with col3:
            if st.button("📊 Estadísticas generales"):
                st.session_state.sql_query = "SELECT COUNT(*) as total_reportes, COUNT(DISTINCT call_sign) as estaciones_unicas, COUNT(DISTINCT zona) as zonas_activas FROM reports"
        
        # Editor de consultas SQL
        sql_query = st.text_area(
            "Consulta SQL:",
            value=st.session_state.get('sql_query', ''),
            height=150,
            help="Ingresa tu consulta SQL. Recomendado: usar LIMIT para consultas grandes."
        )
        
        col_execute, col_clear = st.columns(2)
        
        with col_execute:
            if st.button("▶️ Ejecutar Consulta", type="primary"):
                if sql_query.strip():
                    try:
                        # Ejecutar la consulta
                        import sqlite3
                        conn = sqlite3.connect(db.db_path)
                        
                        # Verificar si es una consulta de solo lectura (SELECT)
                        query_upper = sql_query.upper().strip()
                        if query_upper.startswith('SELECT') or query_upper.startswith('WITH'):
                            # Consulta de solo lectura
                            result_df = pd.read_sql_query(sql_query, conn)
                            conn.close()
                            
                            st.success(f"✅ Consulta ejecutada exitosamente. {len(result_df)} filas devueltas.")
                            
                            if not result_df.empty:
                                st.dataframe(result_df, width='stretch')
                                
                                # Opción para descargar resultados
                                csv = result_df.to_csv(index=False)
                                from datetime import datetime as dt
                                st.download_button(
                                    label="📥 Descargar resultados como CSV",
                                    data=csv,
                                    file_name=f"query_results_{dt.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                    mime="text/csv"
                                )
                            else:
                                st.info("La consulta no devolvió resultados.")
                        
                        else:
                            # Consulta de modificación - requiere confirmación adicional
                            st.warning("⚠️ Esta consulta puede modificar datos. ¿Estás seguro?")
                            
                            if st.button("⚠️ SÍ, EJECUTAR CONSULTA DE MODIFICACIÓN", type="secondary"):
                                cursor = conn.cursor()
                                cursor.execute(sql_query)
                                rows_affected = cursor.rowcount
                                conn.commit()
                                conn.close()
                                
                                st.success(f"✅ Consulta ejecutada. {rows_affected} filas afectadas.")
                            else:
                                conn.close()
                    
                    except Exception as e:
                        st.error(f"❌ Error al ejecutar consulta: {str(e)}")
                else:
                    st.warning("⚠️ Ingresa una consulta SQL válida.")
        
        with col_clear:
            if st.button("🗑️ Limpiar"):
                st.session_state.sql_query = ""
                st.rerun()
    
    with tab2:
        st.subheader("🗑️ Eliminar Registros por Criterios")
        st.warning("⚠️ **PELIGRO**: Esta operación eliminará registros permanentemente de la base de datos.")
        
        # Opciones de eliminación
        delete_option = st.selectbox(
            "Selecciona el tipo de eliminación:",
            ["Por ID específico", "Por rango de fechas", "Por indicativo", "Por zona"]
        )
        
        if delete_option == "Por ID específico":
            report_ids = st.text_input("ID(s) del reporte a eliminar (separados por comas):", help="Ejemplo: 1,2,3 o solo 1")
            
            if report_ids and st.button("🔍 Buscar reportes"):
                try:
                    ids_list = [int(id.strip()) for id in report_ids.split(',')]
                    reports_found = []
                    
                    for report_id in ids_list:
                        # Buscar reporte en la base de datos
                        conn = sqlite3.connect(db.db_path)
                        cursor = conn.cursor()
                        cursor.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
                        report = cursor.fetchone()
                        conn.close()
                        
                        if report:
                            reports_found.append({
                                'id': report[0],
                                'call_sign': report[1],
                                'operator_name': report[2],
                                'timestamp': report[12]
                            })
                    
                    if reports_found:
                        st.info(f"📋 **{len(reports_found)} reporte(s) encontrado(s):**")
                        for report in reports_found:
                            st.write(f"- **ID:** {report['id']} | **Indicativo:** {report['call_sign']} | **Operador:** {report['operator_name']} | **Fecha:** {report['timestamp']}")
                        
                        if st.button("🗑️ ELIMINAR ESTOS REPORTES", type="secondary"):
                            try:
                                conn = sqlite3.connect(db.db_path)
                                cursor = conn.cursor()
                                deleted_count = 0
                                
                                for report_id in ids_list:
                                    cursor.execute("DELETE FROM reports WHERE id = ?", (report_id,))
                                    if cursor.rowcount > 0:
                                        deleted_count += 1
                                
                                conn.commit()
                                conn.close()
                                st.success(f"✅ {deleted_count} reporte(s) eliminado(s) exitosamente.")
                            except Exception as e:
                                st.error(f"❌ Error al eliminar: {str(e)}")
                    else:
                        st.warning(f"⚠️ No se encontraron reportes con los IDs especificados")
                except ValueError:
                    st.error("❌ Por favor ingresa solo números separados por comas")
                except Exception as e:
                    st.error(f"❌ Error al buscar reportes: {str(e)}")
        
        elif delete_option == "Por rango de fechas":
            col_start, col_end = st.columns(2)
            
            with col_start:
                start_date = st.date_input("Fecha inicio:")
            
            with col_end:
                end_date = st.date_input("Fecha fin:")
            
            if st.button("🔍 Contar registros en rango"):
                try:
                    conn = sqlite3.connect(db.db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM reports WHERE DATE(timestamp) BETWEEN ? AND ?", (start_date, end_date))
                    count = cursor.fetchone()[0]
                    conn.close()
                    
                    st.info(f"📊 Se encontraron **{count}** registros en el rango seleccionado.")
                    
                    if count > 0 and st.button("🗑️ ELIMINAR REGISTROS EN RANGO", type="secondary"):
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM reports WHERE DATE(timestamp) BETWEEN ? AND ?", (start_date, end_date))
                        deleted = cursor.rowcount
                        conn.commit()
                        conn.close()
                        st.success(f"✅ {deleted} registros eliminados exitosamente.")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
        
        elif delete_option == "Por indicativo":
            call_sign = st.text_input("Indicativo a eliminar:").upper()
            
            if call_sign and st.button("🔍 Buscar reportes"):
                try:
                    conn = sqlite3.connect(db.db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, call_sign, operator_name, timestamp FROM reports WHERE call_sign = ?", (call_sign,))
                    reports = cursor.fetchall()
                    conn.close()
                    
                    if reports:
                        st.info(f"📊 Se encontraron **{len(reports)}** reportes para {call_sign}")
                        for report in reports:
                            st.write(f"- **ID:** {report[0]} | **Operador:** {report[2]} | **Fecha:** {report[3]}")
                        
                        if st.button(f"🗑️ ELIMINAR TODOS LOS REPORTES DE {call_sign}", type="secondary"):
                            conn = sqlite3.connect(db.db_path)
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM reports WHERE call_sign = ?", (call_sign,))
                            deleted = cursor.rowcount
                            conn.commit()
                            conn.close()
                            st.success(f"✅ {deleted} reportes eliminados exitosamente.")
                    else:
                        st.warning(f"⚠️ No se encontraron reportes para {call_sign}")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
        
        elif delete_option == "Por zona":
            zona = st.selectbox("Zona a eliminar:", ["XE1", "XE2", "XE3", "Extranjera"])
            
            if st.button("🔍 Contar reportes por zona"):
                try:
                    conn = sqlite3.connect(db.db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM reports WHERE zona = ?", (zona,))
                    count = cursor.fetchone()[0]
                    conn.close()
                    
                    st.info(f"📊 Se encontraron **{count}** reportes en la zona {zona}")
                    
                    if count > 0 and st.button(f"🗑️ ELIMINAR TODOS LOS REPORTES DE ZONA {zona}", type="secondary"):
                        conn = sqlite3.connect(db.db_path)
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM reports WHERE zona = ?", (zona,))
                        deleted = cursor.rowcount
                        conn.commit()
                        conn.close()
                        st.success(f"✅ {deleted} reportes eliminados exitosamente.")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
    
    with tab3:
        st.subheader("📊 Estadísticas de Base de Datos")
        
        try:
            # Estadísticas generales usando consultas SQL directas
            import sqlite3
            conn = sqlite3.connect(db.db_path)
            cursor = conn.cursor()
            
            # Total de reportes
            cursor.execute("SELECT COUNT(*) FROM reports")
            total_reports = cursor.fetchone()[0]
            
            # Total de usuarios
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            # Indicativos únicos
            cursor.execute("SELECT COUNT(DISTINCT call_sign) FROM reports")
            unique_calls = cursor.fetchone()[0]
            
            conn.close()
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("📋 Total Reportes", total_reports)
            
            with col2:
                st.metric("👥 Total Usuarios", total_users)
            
            with col3:
                st.metric("📻 Indicativos Únicos", unique_calls)
            
            # Calcular tamaño de base de datos
            import os
            if os.path.exists(db.db_path):
                db_size = os.path.getsize(db.db_path) / (1024 * 1024)  # MB
                st.metric("💾 Tamaño DB", f"{db_size:.2f} MB")
            
            # Estadísticas detalladas
            st.markdown("---")
            st.subheader("📈 Estadísticas Detalladas")
            
            # Top indicativos
            conn = sqlite3.connect(db.db_path)
            top_calls_df = pd.read_sql_query("""
                SELECT call_sign, operator_name, COUNT(*) as total_reportes 
                FROM reports 
                GROUP BY call_sign, operator_name 
                ORDER BY total_reportes DESC 
                LIMIT 10
            """, conn)
            
            if not top_calls_df.empty:
                st.markdown("**🏆 Top 10 Indicativos:**")
                st.dataframe(top_calls_df, width='stretch')
            
            # Actividad por zona
            zone_stats_df = pd.read_sql_query("""
                SELECT zona, COUNT(*) as total_reportes 
                FROM reports 
                GROUP BY zona 
                ORDER BY total_reportes DESC
            """, conn)
            
            if not zone_stats_df.empty:
                st.markdown("**🌍 Actividad por Zona:**")
                st.dataframe(zone_stats_df, width='stretch')
            
            conn.close()
        
        except Exception as e:
            st.error(f"❌ Error al obtener estadísticas: {str(e)}")
    
    with tab4:
        st.subheader("🔧 Mantenimiento de Base de Datos")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**🧹 Limpieza:**")
            
            if st.button("🗑️ Limpiar registros duplicados"):
                try:
                    conn = sqlite3.connect(db.db_path)
                    cursor = conn.cursor()
                    
                    # Encontrar y eliminar duplicados basados en call_sign, timestamp y operator_name
                    cursor.execute("""
                        DELETE FROM reports 
                        WHERE id NOT IN (
                            SELECT MIN(id) 
                            FROM reports 
                            GROUP BY call_sign, operator_name, DATE(timestamp)
                        )
                    """)
                    
                    removed = cursor.rowcount
                    conn.commit()
                    conn.close()
                    
                    st.success(f"✅ {removed} registros duplicados eliminados.")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            
            if st.button("🧹 Limpiar registros huérfanos"):
                try:
                    deleted_count = db.clean_orphaned_station_history()
                    st.success(f"✅ {deleted_count} registros huérfanos eliminados del historial.")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            
            if st.button("📝 Normalizar nombres y ciudades"):
                try:
                    normalized_count = db.normalize_operator_names()
                    st.success(f"✅ {normalized_count} registros normalizados (nombres de operadores y ciudades) a formato título.")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            
            if st.button("🌍 Normalizar QTH"):
                try:
                    conn = sqlite3.connect(db.db_path)
                    cursor = conn.cursor()
                    
                    # Obtener registros con QTH
                    cursor.execute("SELECT id, qth FROM reports WHERE qth IS NOT NULL AND qth != ''")
                    records = cursor.fetchall()
                    
                    updated_count = 0
                    
                    # Actualizar cada registro
                    for record_id, qth in records:
                        if qth and qth.strip():
                            new_qth = qth.title()
                            if new_qth != qth:
                                cursor.execute(
                                    "UPDATE reports SET qth = ? WHERE id = ?",
                                    (new_qth, record_id)
                                )
                                updated_count += 1
                    
                    conn.commit()
                    conn.close()
                    
                    st.success(f"✅ {updated_count} registros de QTH normalizados a formato título.")
                    
                except Exception as e:
                    st.error(f"❌ Error al normalizar QTH: {str(e)}")
                    if 'conn' in locals():
                        conn.rollback()
                        conn.close()
            
            if st.button("🔄 Optimizar base de datos (VACUUM)"):
                try:
                    conn = sqlite3.connect(db.db_path)
                    conn.execute("VACUUM")
                    conn.close()
                    st.success("✅ Base de datos optimizada.")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
        
        with col2:
            st.markdown("**💾 Respaldo:**")
            
            if st.button("📥 Crear respaldo completo"):
                try:
                    import shutil
                    from datetime import datetime
                    
                    backup_filename = f"backup_sigq_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                    backup_path = f"backups/{backup_filename}"
                    
                    # Crear directorio de backups si no existe
                    os.makedirs("backups", exist_ok=True)
                    
                    # Copiar base de datos
                    shutil.copy2(db.db_path, backup_path)
                    
                    st.success(f"✅ Respaldo creado: {backup_path}")
                    
                    # Ofrecer descarga del respaldo
                    with open(backup_path, "rb") as f:
                        st.download_button(
                            label="📥 Descargar respaldo",
                            data=f.read(),
                            file_name=backup_filename,
                            mime="application/octet-stream"
                        )
                        
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
        
        # Test de conexión
        if st.button("🧪 Probar Conexión SMTP"):
            if email_service.test_smtp_connection():
                st.success("✅ Conexión SMTP exitosa")
            else:
                st.error("❌ Error en la conexión SMTP")

def show_motivational_dashboard():
    """Muestra el dashboard de rankings y reconocimientos"""
    st.header("🏆 Ranking")
    st.markdown("### ¡Competencia Sana entre Radioaficionados!")
    
    # Obtener estadísticas motivacionales
    motivational_stats = db.get_motivational_stats()
    
    # Pestañas para organizar las estadísticas
    tab1, tab2, tab3, tab4 = st.tabs(["🥇 Estaciones Top", "🌍 Zonas Activas", "📡 Sistemas Populares", "📊 Resumen General"])
    
    with tab1:
        st.subheader("🎯 Estaciones Más Reportadas")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📅 **Este Año**")
            if not motivational_stats['top_stations_year'].empty:
                for idx, row in motivational_stats['top_stations_year'].head(5).iterrows():
                    if idx == 0:
                        st.markdown(f"🥇 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
                    elif idx == 1:
                        st.markdown(f"🥈 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
                    elif idx == 2:
                        st.markdown(f"🥉 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
                    else:
                        st.markdown(f"🏅 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
            else:
                st.info("No hay datos suficientes para mostrar el ranking anual")
        
        with col2:
            st.markdown("#### 📆 **Este Mes**")
            if not motivational_stats['top_stations_month'].empty:
                for idx, row in motivational_stats['top_stations_month'].head(5).iterrows():
                    if idx == 0:
                        st.markdown(f"🥇 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
                    elif idx == 1:
                        st.markdown(f"🥈 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
                    elif idx == 2:
                        st.markdown(f"🥉 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
                    else:
                        st.markdown(f"🏅 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
            else:
                st.info("No hay datos suficientes para mostrar el ranking mensual")
    
    with tab2:
        st.subheader("🌍 Zonas Más Activas")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📅 **Este Año**")
            if not motivational_stats['top_zones_year'].empty:
                for idx, row in motivational_stats['top_zones_year'].iterrows():
                    st.markdown(f"🏆 **Zona {row['zona']}**")
                    st.markdown(f"   👥 {row['unique_stations']} estaciones únicas")
                    st.markdown(f"   📊 {row['total_reports']} reportes totales")
                    st.markdown("---")
            else:
                st.info("No hay datos de zonas para este año")
        
        with col2:
            st.markdown("#### 📆 **Este Mes**")
            if not motivational_stats['top_zones_month'].empty:
                for idx, row in motivational_stats['top_zones_month'].iterrows():
                    st.markdown(f"🏆 **Zona {row['zona']}**")
                    st.markdown(f"   👥 {row['unique_stations']} estaciones únicas")
                    st.markdown(f"   📊 {row['total_reports']} reportes totales")
                    st.markdown("---")
            else:
                st.info("No hay datos de zonas para este mes")
    
    with tab3:
        st.subheader("📡 Sistemas Más Utilizados")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📅 **Este Año**")
            if not motivational_stats['top_systems_year'].empty:
                for idx, row in motivational_stats['top_systems_year'].iterrows():
                    st.markdown(f"🔧 **{row['sistema']}**")
                    st.markdown(f"   👥 {row['unique_stations']} estaciones únicas")
                    st.markdown(f"   📊 {row['total_reports']} reportes totales")
                    st.markdown("---")
            else:
                st.info("No hay datos de sistemas para este año")
        
        with col2:
            st.markdown("#### 📆 **Este Mes**")
            if not motivational_stats['top_systems_month'].empty:
                for idx, row in motivational_stats['top_systems_month'].iterrows():
                    st.markdown(f"🔧 **{row['sistema']}**")
                    st.markdown(f"   👥 {row['unique_stations']} estaciones únicas")
                    st.markdown(f"   📊 {row['total_reports']} reportes totales")
                    st.markdown("---")
            else:
                st.info("No hay datos de sistemas para este mes")
    
    with tab4:
        st.subheader("📊 Resumen General de Actividad")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📅 **Estadísticas del Año**")
            if not motivational_stats['general_year'].empty:
                year_stats = motivational_stats['general_year'].iloc[0]
                st.metric("📊 Total Reportes", year_stats['total_reports'])
                st.metric("👥 Estaciones Únicas", year_stats['unique_stations'])
                st.metric("📅 Días Activos", year_stats['active_days'])
            else:
                st.info("No hay estadísticas generales del año")
        
        with col2:
            st.markdown("#### 📆 **Estadísticas del Mes**")
            if not motivational_stats['general_month'].empty:
                month_stats = motivational_stats['general_month'].iloc[0]
                st.metric("📊 Total Reportes", month_stats['total_reports'])
                st.metric("👥 Estaciones Únicas", month_stats['unique_stations'])
                st.metric("📅 Días Activos", month_stats['active_days'])
            else:
                st.info("No hay estadísticas generales del mes")
    
    # Mensaje motivacional
    st.markdown("---")
    st.markdown("### 🎉 ¡Sigue Participando!")
    st.info("💪 **¡Cada reporte cuenta!** Mantente activo en las redes y ayuda a tu zona y sistema favorito a liderar las estadísticas. ¡La competencia sana nos hace crecer como comunidad radioaficionada! 📻✨")

def show_user_management():
    # Verificar si el usuario es admin
    if current_user['role'] != 'admin':
        st.error("❌ Acceso denegado. Solo los administradores pueden acceder a esta sección.")
        st.stop()
        
    st.header("👥 Gestión de Usuarios")
    
    # Inicializar servicio de email
    if 'email_service' not in st.session_state:
        st.session_state.email_service = EmailService()
    
    email_service = st.session_state.email_service
    
    # Tabs para organizar funcionalidades
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Lista de Usuarios", "➕ Crear Usuario", "🔄 Recuperar Contraseña", "⚙️ Configuración Email"])
    
    with tab1:
        st.subheader("Lista de Usuarios")
        
        # Obtener usuarios
        users = db.get_all_users()
        
        if users is not None and len(users) > 0:
            for user in users:
                with st.expander(f"👤 {user['username']} ({user['role']})", expanded=st.session_state.get(f"editing_user_{user['id']}", False)):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Nombre completo:** {user.get('full_name', 'N/A')}")
                        st.write(f"**Email:** {user.get('email', 'N/A')}")
                        st.write(f"**Rol:** {user['role']}")
                        st.write(f"**Creado:** {user.get('created_at', 'N/A')}")
                    
                    with col2:
                        # Botón para editar usuario
                        if st.button(f"✏️ Editar", key=f"edit_user_{user['id']}"):
                            st.session_state[f"editing_user_{user['id']}"] = True
                        
                        # Botón para eliminar usuario (solo si no es admin)
                        if user['username'] != 'admin':
                            if st.button(f"🗑️ Eliminar", key=f"delete_user_{user['id']}"):
                                try:
                                    db.delete_user(user['id'])
                                    st.success(f"Usuario {user['username']} eliminado")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al eliminar usuario: {str(e)}")
                        else:
                            st.info("👑 Usuario administrador protegido")
                    
                    # Formulario de edición si está activado
                    if st.session_state.get(f"editing_user_{user['id']}", False):
                        st.markdown("---")
                        st.subheader("✏️ Editar Usuario")
                        
                        with st.form(f"edit_user_form_{user['id']}"):
                            edit_full_name = st.text_input("Nombre completo:", value=user.get('full_name', ''))
                            edit_email = st.text_input("Email:", value=user.get('email', ''))
                            edit_role = st.selectbox("Rol:", ["operator", "admin"], 
                                                   index=0 if user['role'] == 'operator' else 1)
                            
                            # Opción para cambiar contraseña
                            change_password = st.checkbox("Cambiar contraseña")
                            new_password = ""
                            confirm_new_password = ""
                            
                            if change_password:
                                new_password = st.text_input("Nueva contraseña:", type="password", 
                                                           help="Mínimo 8 caracteres, 1 mayúscula, 1 número, 1 carácter especial")
                                confirm_new_password = st.text_input("Confirmar nueva contraseña:", type="password")
                            
                            col_save, col_cancel = st.columns(2)
                            
                            with col_save:
                                save_changes = st.form_submit_button("💾 Guardar Cambios")
                            
                            with col_cancel:
                                cancel_edit = st.form_submit_button("❌ Cancelar")
                            
                            if save_changes:
                                # Validar campos obligatorios
                                if not edit_full_name or not edit_email:
                                    st.error("❌ Nombre completo y email son obligatorios")
                                else:
                                    # Validar contraseña si se va a cambiar
                                    password_valid = True
                                    if change_password:
                                        if new_password != confirm_new_password:
                                            st.error("❌ Las contraseñas no coinciden")
                                            password_valid = False
                                        else:
                                            from utils import validate_password
                                            is_valid, message = validate_password(new_password)
                                            if not is_valid:
                                                st.error(f"❌ {message}")
                                                password_valid = False
                                    
                                    if password_valid:
                                        try:
                                            # Actualizar información del usuario
                                            db.update_user(user['id'], edit_full_name, edit_role, edit_email)
                                            
                                            # Cambiar contraseña si se solicitó
                                            if change_password:
                                                import hashlib
                                                password_hash = hashlib.sha256(new_password.encode()).hexdigest()
                                                db.change_password(user['username'], password_hash)
                                            
                                            st.success("✅ Usuario actualizado exitosamente")
                                            
                                            # Limpiar estado de edición
                                            del st.session_state[f"editing_user_{user['id']}"]
                                            st.rerun()
                                            
                                        except Exception as e:
                                            st.error(f"❌ Error al actualizar usuario: {str(e)}")
                            elif cancel_edit:
                                # Cancelar edición
                                del st.session_state[f"editing_user_{user['id']}"]
                                st.rerun()
        else:
            st.info("No hay usuarios registrados")
    
    with tab2:
        st.subheader("➕ Crear Nuevo Usuario")
        
        with st.form("create_user_form"):
            new_username = st.text_input("Nombre de usuario:")
            new_full_name = st.text_input("Nombre completo:")
            new_email = st.text_input("Email:")
            new_password = st.text_input("Contraseña:", type="password", help="Mínimo 8 caracteres, 1 mayúscula, 1 número, 1 carácter especial")
            confirm_password = st.text_input("Confirmar contraseña:", type="password")
            new_role = st.selectbox("Rol:", ["operator", "admin"])
            
            submit_create = st.form_submit_button("✅ Crear Usuario")
            
            if submit_create:
                if new_username and new_full_name and new_email and new_password and confirm_password:
                    # Validar que las contraseñas coincidan
                    if new_password != confirm_password:
                        st.error("❌ Las contraseñas no coinciden")
                    else:
                        # Validar fortaleza de la contraseña
                        from utils import validate_password
                        is_valid, message = validate_password(new_password)
                        
                        if not is_valid:
                            st.error(f"❌ {message}")
                        else:
                            try:
                                # Crear usuario
                                user_id = auth.create_user(new_username, new_password, role=new_role, full_name=new_full_name, email=new_email)
                                
                                if user_id:
                                    st.success("✅ Usuario creado exitosamente")
                                    
                                    # Mostrar información del usuario creado
                                    st.info(f"""
                                    **Usuario creado:**
                                    - **Nombre de usuario:** {new_username}
                                    - **Nombre completo:** {new_full_name}
                                    - **Email:** {new_email}
                                    - **Rol:** {new_role}
                                    """)
                                    
                                    # Enviar email de bienvenida si está configurado
                                    if email_service.is_configured():
                                        user_data = {
                                            'username': new_username,
                                            'full_name': new_full_name,
                                            'email': new_email,
                                            'role': new_role
                                        }
                                        
                                        if email_service.send_welcome_email(user_data, new_password):
                                            st.success("📧 Email de bienvenida enviado")
                                        else:
                                            st.warning("⚠️ Usuario creado pero no se pudo enviar el email de bienvenida")
                                    else:
                                        st.warning("⚠️ Usuario creado. Configura SMTP para enviar credenciales por email")
                                    
                                    # Esperar un momento antes de recargar para mostrar mensajes
                                    import time
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    st.error("❌ Error al crear usuario (posiblemente el usuario ya existe)")
                            except Exception as e:
                                st.error(f"❌ Error al crear usuario: {str(e)}")
                else:
                    st.error("❌ Por favor completa todos los campos")
    
    with tab3:
        st.subheader("🔄 Recuperar Contraseña")
        
        with st.form("password_recovery_form"):
            recovery_email = st.text_input("Email del usuario:")
            submit_recovery = st.form_submit_button("📧 Enviar Email de Recuperación")
            
            if submit_recovery:
                if recovery_email:
                    if email_service.is_configured():
                        try:
                            # Buscar usuario por email
                            user = db.get_user_by_email(recovery_email)
                            
                            if user:
                                # Generar token y enviar email
                                if email_service.send_password_reset_email(user):
                                    st.success("📧 Email de recuperación enviado")
                                else:
                                    st.error("❌ Error al enviar email de recuperación")
                            else:
                                st.error("❌ No se encontró usuario con ese email")
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
                    else:
                        st.error("❌ Servicio de email no configurado")
                else:
                    st.error("❌ Por favor ingresa un email")
    
    with tab4:
        st.subheader("⚙️ Configuración del Servicio de Email")
        
        # Estado actual del servicio
        if email_service.is_configured():
            st.success("✅ Servicio de email configurado")
            st.info(f"Servidor: {email_service.smtp_server}:{email_service.smtp_port}")
            st.info(f"Usuario: {email_service.smtp_username}")
        else:
            st.warning("⚠️ Servicio de email no configurado")
        
        with st.form("smtp_config_form"):
            st.write("**Configuración SMTP:**")
            
            smtp_server = st.text_input("Servidor SMTP:", value=email_service.smtp_server or "smtp.gmail.com")
            smtp_port = st.number_input("Puerto SMTP:", value=email_service.smtp_port or 587, min_value=1, max_value=65535)
            smtp_username = st.text_input("Usuario SMTP:", value=email_service.smtp_username or "")
            smtp_password = st.text_input("Contraseña SMTP:", type="password")
            sender_email = st.text_input("Email remitente:", value=getattr(email_service, 'from_email', '') or "")
            sender_name = st.text_input("Nombre remitente:", value=getattr(email_service, 'from_name', '') or "Sistema FMRE")
            
            submit_smtp = st.form_submit_button("💾 Guardar Configuración SMTP")
            
            if submit_smtp:
                if smtp_server and smtp_username and smtp_password:
                    email_service.configure_smtp(
                        smtp_server, smtp_port, smtp_username, 
                        smtp_password if smtp_password else email_service.smtp_password,
                        sender_email, sender_name
                    )
                    st.success("✅ Configuración SMTP guardada")
                    st.rerun()
                else:
                    st.error("❌ Por favor completa los campos obligatorios")

# Configuración de la página
st.set_page_config(
    page_title="Sistema Integral de Gestión de QSOs (SIGQ)",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado para mejorar la apariencia
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 20px;
    }
    .logo-container {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 15px;
        margin-bottom: 1rem;
        flex-wrap: wrap;
    }
    @media (max-width: 768px) {
        .logo-container {
            flex-direction: column;
            gap: 10px;
        }
        .logo-container img {
            width: 80px !important;
        }
        .logo-container h1 {
            font-size: 1.8rem !important;
            text-align: center;
        }
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .success-message {
        padding: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 0.25rem;
        color: #155724;
    }
    .login-header {
        text-align: center;
        margin-bottom: 2rem;
    }
    .login-logo {
        display: block;
        margin: 0 auto 20px auto;
        max-width: 150px;
        height: auto;
    }
    .error-message {
        padding: 0.5rem;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 0.25rem;
        color: #721c24;
    }
</style>
""", unsafe_allow_html=True)

# Inicializar base de datos y autenticación
@st.cache_resource
def init_database():
    return FMREDatabase()

@st.cache_resource
def init_exporter():
    return FMREExporter()

def init_auth():
    if 'auth_manager' not in st.session_state:
        db = init_database()
        auth = AuthManager(db)
        auth.create_default_admin()  # Crear admin por defecto
        st.session_state.auth_manager = auth
    return st.session_state.auth_manager

db = init_database()
exporter = init_exporter()
auth = init_auth()

# Verificar autenticación
if not auth.is_logged_in():
    auth.show_login_form()
    st.stop()

# Usuario actual
current_user = auth.get_current_user()

# Título principal
st.markdown('<h1 style="color: #1f77b4; margin: 20px 0; font-size: 2.2rem; text-align: center;">Sistema Integral de Gestión de QSOs (SIGQ)</h1>', unsafe_allow_html=True)

# Sidebar para navegación
st.sidebar.title("Navegación")

# Información del usuario
st.sidebar.markdown("---")
st.sidebar.markdown(f"👤 **Usuario:** {current_user['full_name']}")
st.sidebar.markdown(f"🎭 **Rol:** {current_user['role'].title()}")

# Sistema corregido - debug removido

if st.sidebar.button("🚪 Cerrar Sesión"):
    auth.logout()

st.sidebar.markdown("---")

# Crear menú dinámico basado en el rol del usuario
menu_options = ["🏠 Registro de Reportes", "📊 Dashboard", "📈 Reportes Avanzados", "📋 Reportes Básicos/Exportar", "🔍 Buscar/Editar", "🏆 Ranking", "👤 Mi Perfil"]

# Solo mostrar opciones de admin si es admin
if current_user['role'] == 'admin':
    menu_options.append("👥 Gestión de Usuarios")
    menu_options.append("🔧 Administrador DB")

page = st.sidebar.selectbox(
    "Navegación:",
    menu_options
)

# Selector de fecha de sesión
st.sidebar.markdown("---")
st.sidebar.subheader("Sesión Actual")
session_date = st.sidebar.date_input(
    "Fecha de sesión:",
    value=date.today(),
    help="Selecciona la fecha de la sesión de boletín"
)

# Validar si la fecha de sesión es diferente a la actual
date_difference = session_date != date.today()
if date_difference:
    st.sidebar.warning(f"⚠️ **Capturando con fecha:** {session_date.strftime('%d/%m/%Y')}")
    st.sidebar.info("Los reportes se guardarán con la fecha seleccionada")

def show_profile_management():
    """Muestra la página de gestión de perfil del usuario"""
    st.header("👤 Mi Perfil")
    st.markdown("### Gestiona tu información personal")
    # Mostrar mensaje persistente tras actualización
    if st.session_state.get('profile_updated'):
        st.success("✅ Información actualizada correctamente")
        del st.session_state['profile_updated']
    
    # Obtener información actual del usuario
    user_info = db.get_user_by_username(current_user['username'])
    
    if not user_info:
        st.error("❌ Error al cargar información del usuario")
        return
    
    # Convertir tupla a diccionario usando índices conocidos
    # Estructura real: (id, username, password_hash, full_name, email, role, preferred_system, hf_frequency_pref, hf_mode_pref, hf_power_pref, created_at, last_login)
    user_dict = {
        'id': user_info[0],
        'username': user_info[1],
        'password_hash': user_info[2],
        'full_name': user_info[3] if len(user_info) > 3 else '',
        'email': user_info[4] if len(user_info) > 4 else '',
        'role': user_info[5] if len(user_info) > 5 else '',
        'preferred_system': user_info[6] if len(user_info) > 6 else 'ASL',
        'created_at': user_info[10] if len(user_info) > 10 else '',
        'last_login': user_info[11] if len(user_info) > 11 else ''
    }
    
    # Crear tabs para organizar la información
    tab1, tab2 = st.tabs(["📝 Información Personal", "🔐 Cambiar Contraseña"])
    
    with tab1:
        st.subheader("Actualizar Información Personal")
        
        with st.form("update_profile_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                new_full_name = st.text_input(
                    "Nombre Completo:",
                    value=user_dict['full_name'],
                    help="Tu nombre completo como aparecerá en los reportes"
                )
                
                new_email = st.text_input(
                    "Correo Electrónico:",
                    value=user_dict['email'],
                    help="Tu dirección de correo electrónico"
                )
            
            with col2:
                st.text_input(
                    "Nombre de Usuario:",
                    value=user_dict['username'],
                    disabled=True,
                    help="El nombre de usuario no se puede cambiar"
                )
                
                st.text_input(
                    "Rol:",
                    value=user_dict['role'].title(),
                    disabled=True,
                    help="Tu rol en el sistema"
                )
            
            # Información adicional
            st.markdown("---")
            col3, col4 = st.columns(2)
            
            with col3:
                if user_dict['created_at']:
                    formatted_created = format_timestamp(user_dict['created_at'])
                    st.info(f"📅 **Miembro desde:** {formatted_created}")
            
            with col4:
                if user_dict['last_login']:
                    formatted_login = format_timestamp(user_dict['last_login'])
                    st.info(f"🕒 **Último acceso:** {formatted_login}")
            
            submitted = st.form_submit_button("💾 Actualizar Información", type="primary")
            
            if submitted:
                # Validar datos
                if not new_full_name or not new_full_name.strip():
                    st.error("❌ El nombre completo es obligatorio")
                elif not new_email or not new_email.strip():
                    st.error("❌ El correo electrónico es obligatorio")
                elif '@' not in new_email:
                    st.error("❌ Ingresa un correo electrónico válido")
                else:
                    # Actualizar información
                    success = db.update_user_profile(
                        user_dict['id'],
                        new_full_name.strip(),
                        new_email.strip()
                    )
                    
                    if success:
                        # Guardar bandera de éxito y recargar
                        st.session_state['profile_updated'] = True
                        st.rerun()
                    else:
                        st.error("❌ Error al actualizar la información")
    
    with tab2:
        st.subheader("Cambiar Contraseña")
        
        with st.form("change_password_form"):
            current_password = st.text_input(
                "Contraseña Actual:",
                type="password",
                help="Ingresa tu contraseña actual para confirmar el cambio"
            )
            
            new_password = st.text_input(
                "Nueva Contraseña:",
                type="password",
                help="Mínimo 6 caracteres"
            )
            
            confirm_password = st.text_input(
                "Confirmar Nueva Contraseña:",
                type="password",
                help="Repite la nueva contraseña"
            )
            
            submitted_password = st.form_submit_button("🔐 Cambiar Contraseña", type="primary")
            
            if submitted_password:
                # Validar contraseña actual
                if not auth.verify_password(current_password, user_dict['password_hash']):
                    st.error("❌ La contraseña actual es incorrecta")
                elif len(new_password) < 6:
                    st.error("❌ La nueva contraseña debe tener al menos 6 caracteres")
                elif new_password != confirm_password:
                    st.error("❌ Las contraseñas no coinciden")
                elif current_password == new_password:
                    st.error("❌ La nueva contraseña debe ser diferente a la actual")
                else:
                    # Cambiar contraseña
                    success = db.change_user_password(
                        user_dict['id'],
                        new_password
                    )
                    
                    if success:
                        st.success("✅ Contraseña cambiada correctamente")
                        st.info("🔄 Por seguridad, deberás iniciar sesión nuevamente")
                        # Marcar para mostrar botón de logout fuera del form
                        st.session_state.show_logout_button = True
                    else:
                        st.error("❌ Error al cambiar la contraseña")
    
    # Botón de logout fuera del formulario
    if st.session_state.get('show_logout_button', False):
        if st.button("🚪 Cerrar Sesión"):
            del st.session_state.show_logout_button
            auth.logout()

def registro_reportes():
    """Página de registro de reportes con autocompletado inteligente"""
    import pandas as pd
    
    st.title("📋 Registro de Reportes")
    
    # Obtener sistema preferido del usuario y configuración HF
    user_preferred_system = "ASL"  # Default
    user_hf_frequency = ""
    user_hf_mode = ""
    user_hf_power = ""
    
    if current_user:
        user_preferred_system = db.get_user_preferred_system(current_user['username']) or "ASL"
        # Obtener configuración HF preferida del usuario
        user_data = db.get_user_by_username(current_user['username'])
        if user_data and len(user_data) > 6:  # Verificar que existan los campos HF
            user_hf_frequency = user_data[7] or ""  # hf_frequency_pref
            user_hf_mode = user_data[8] or ""       # hf_mode_pref  
            user_hf_power = user_data[9] or ""      # hf_power_pref
        
    # Configuración de Sistema Preferido
    st.subheader("⚙️ Configuración de Sistema Preferido")
    
    st.markdown("""
    <div style="background-color: #f0f8ff; padding: 15px; border-radius: 10px; border-left: 4px solid #1f77b4; margin-bottom: 20px;">
        <h4 style="color: #1f77b4; margin-top: 0;">📡 ¿Qué es el Sistema Preferido?</h4>
        <p style="margin-bottom: 10px;">
            <strong>Configura tu sistema de radio favorito</strong> para que aparezca <strong>pre-seleccionado automáticamente</strong> 
            en todos tus reportes, ahorrándote tiempo en cada registro.
        </p>
        <p style="margin-bottom: 0;">
            <strong>🎯 Ventaja especial HF:</strong> Si seleccionas HF, también puedes configurar tu 
            <strong>frecuencia, modo y potencia por defecto</strong> para que aparezcan automáticamente.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    st.info(f"💡 **Tu sistema preferido actual:** {user_preferred_system}")
    
    if user_preferred_system == "HF" and (user_hf_frequency or user_hf_mode or user_hf_power):
        st.write("**Configuración HF preferida:**")
        if user_hf_frequency:
            st.write(f"📻 Frecuencia: {user_hf_frequency} MHz")
        if user_hf_mode:
            st.write(f"📡 Modo: {user_hf_mode}")
        if user_hf_power:
            st.write(f"⚡ Potencia: {user_hf_power} W")
    
    # Selector para cambiar sistema preferido
    new_preferred = st.selectbox(
        "Cambiar sistema preferido:",
        get_sistemas(),
        index=get_sistemas().index(user_preferred_system) if user_preferred_system in get_sistemas() else 0,
        key="change_preferred_system"
    )
    
    # Campos HF adicionales si se selecciona HF
    new_hf_frequency = ""
    new_hf_mode = ""
    new_hf_power = ""
    
    if new_preferred == "HF":
        st.markdown("**📻 Configuración HF Preferida:**")
        col_hf1, col_hf2, col_hf3 = st.columns(3)
        
        with col_hf1:
            new_hf_frequency = st.text_input(
                "Frecuencia (MHz)", 
                value=user_hf_frequency,
                placeholder="14.230", 
                help="1.8-30 MHz"
            )
        
        with col_hf2:
            new_hf_mode = st.selectbox(
                "Modo", 
                ["", "USB", "LSB", "CW", "DIGITAL"],
                index=["", "USB", "LSB", "CW", "DIGITAL"].index(user_hf_mode) if user_hf_mode in ["", "USB", "LSB", "CW", "DIGITAL"] else 0
            )
        
        with col_hf3:
            new_hf_power = st.text_input(
                "Potencia (W)", 
                value=user_hf_power,
                placeholder="100"
            )
        
        # Botón después de los campos HF
        update_button = st.button("💾 Actualizar Preferido", help="Guardar configuración preferida")
    else:
        # Botón inmediatamente después del selector si no es HF
        update_button = st.button("💾 Actualizar Preferido", help="Guardar configuración preferida")
    
    if update_button:
        if current_user:
            # Actualizar sistema preferido
            result = db.update_user_preferred_system(current_user['username'], new_preferred)
            
            # Si es HF, actualizar también la configuración HF preferida
            if new_preferred == "HF":
                hf_result = db.update_user_hf_preferences(
                    current_user['username'], 
                    new_hf_frequency, 
                    new_hf_mode, 
                    new_hf_power
                )
            
            if result:
                st.success(f"✅ **Sistema preferido actualizado a: {new_preferred}**")
                if new_preferred == "HF":
                    st.success("✅ **Configuración HF preferida guardada**")
                st.info("ℹ️ Los cambios se aplicarán inmediatamente en el próximo reporte.")
                st.rerun()
            else:
                st.error("❌ Error al actualizar sistema preferido")
        else:
            st.error("❌ No hay usuario autenticado")
    
    st.markdown("---")
    
    # Inicializar valores por defecto desde session_state si existen
    default_call = st.session_state.get('prefill_call', "")
    default_name = st.session_state.get('prefill_name', "")
    default_estado = st.session_state.get('prefill_estado', "")
    default_ciudad = st.session_state.get('prefill_ciudad', "")
    
    # Encontrar índices para los selectbox
    zonas = get_zonas()
    sistemas = get_sistemas()
    estados = get_estados_list()
    
    default_zona = 0
    default_sistema = 0
    default_estado_idx = 0
    
    if 'prefill_zona' in st.session_state:
        try:
            default_zona = zonas.index(st.session_state['prefill_zona'])
        except ValueError:
            default_zona = 0
    
    if 'prefill_sistema' in st.session_state:
        try:
            default_sistema = sistemas.index(st.session_state['prefill_sistema'])
        except ValueError:
            default_sistema = 0
    
    if 'prefill_estado' in st.session_state:
        try:
            # Convertir a formato título para que coincida con la lista
            estado_formatted = st.session_state['prefill_estado'].title()
            default_estado_idx = estados.index(estado_formatted)
        except ValueError:
            default_estado_idx = 0
    
    # Campo Indicativo con autocompletado mejorado (fuera del formulario)
    # Aplicar limpieza de búsqueda si está marcado el flag
    input_value = "" if st.session_state.get('clear_search', False) else default_call
    
    # Usar key dinámico para forzar recreación del widget cuando se limpia
    widget_key = f"call_sign_input_{st.session_state.get('input_counter', 0)}"
    
    call_sign_input = st.text_input(
        "📻 Indicativo", 
        placeholder="(Obligatorio) | Ejemplo: XE1ABC",
        value=input_value, 
        help="Escribe al menos 2 caracteres para ver sugerencias automáticas",
        key=widget_key

    )
    
    # Limpiar el flag después de aplicar para evitar bucles
    if st.session_state.get('clear_search', False):
        st.session_state.clear_search = False

    # Autocompletado dinámico mejorado - TABLA INLINE PARA CAPTURA MASIVA
    # Inicializar suggestions como lista vacía por defecto
    suggestions = []
    
    # Solo mostrar tabla si no estamos editando registros de sesión
    if (call_sign_input and len(call_sign_input.strip()) >= 2 and 
        not st.session_state.get('show_bulk_edit', False) and
        not st.session_state.get('show_selected_details', False) and
        not st.session_state.get('confirm_bulk_delete', False) and
        not st.session_state.get('editing_individual_report', False) and
        not st.session_state.get('selected_reports', [])):
        with st.spinner("🔍 Buscando estaciones..."):
            suggestions = db.search_call_signs_dynamic(call_sign_input.strip(), limit=20)
        
        if suggestions:
            # Mostrar información de resultados encontrados
            st.info(f"🔍 **{len(suggestions)}** estaciones únicas encontradas para **{call_sign_input.upper()}**")
            st.info("💡 **Tip:** Selecciona solo las estaciones que se reportaron y guarda todas juntas.")
            
            # Preparar datos para la tabla editable
            bulk_data = []
            for i, suggestion in enumerate(suggestions):
                bulk_data.append({
                    'Seleccionar': True,
                    'Indicativo': suggestion['call_sign'],
                    'Operador': suggestion['operator_name'],
                    'Estado': suggestion['qth'],
                    'Ciudad': suggestion.get('ciudad', ''),
                    'Zona': suggestion['zona'],
                    'Sistema': suggestion['sistema'],
                    'Señal': '59',
                    'Observaciones': ''
                })
            
            # Inicializar o recuperar el estado de selección
            if 'bulk_df_state' not in st.session_state:
                st.session_state.bulk_df_state = None
            
            # Crear DataFrame solo si no existe o si cambió el indicativo
            current_call_sign = call_sign_input.upper() if call_sign_input else ""
            if (st.session_state.bulk_df_state is None or 
                st.session_state.get('last_call_sign', '') != current_call_sign):
                
                # Crear DataFrame nuevo
                bulk_data = []
                for i, suggestion in enumerate(suggestions):
                    bulk_data.append({
                        'Seleccionar': True,
                        'Indicativo': suggestion['call_sign'],
                        'Operador': suggestion['operator_name'],
                        'Estado': suggestion['qth'],
                        'Ciudad': suggestion.get('ciudad', ''),
                        'Zona': suggestion['zona'],
                        'Sistema': suggestion['sistema'],
                        'Señal': '59',
                        'Observaciones': ''
                    })
                
                st.session_state.bulk_df_state = pd.DataFrame(bulk_data)
                st.session_state.last_call_sign = current_call_sign
            
            df_bulk = st.session_state.bulk_df_state.copy()
            
            # Configuración de columnas
            column_config = {
                'Seleccionar': st.column_config.CheckboxColumn("✓", help="Seleccionar para guardar", default=True, width="small"),
                'Indicativo': st.column_config.TextColumn("Indicativo", disabled=True, width="medium"),
                'Operador': st.column_config.TextColumn("Operador", width="medium"),
                'Estado': st.column_config.TextColumn("Estado", width="medium"),
                'Ciudad': st.column_config.TextColumn("Ciudad", width="medium"),
                'Zona': st.column_config.SelectboxColumn("Zona", options=get_zonas(), width="small"),
                'Sistema': st.column_config.SelectboxColumn("Sistema", options=get_sistemas(), width="medium"),
                'Señal': st.column_config.TextColumn("Señal", width="small"),
                'Observaciones': st.column_config.TextColumn("Observaciones", width="large")
            }
            
            # Mostrar tabla editable dentro del formulario
            with st.form("bulk_capture_form_inline"):
                # Botones superiores
                col1_top, col2_top, col3_top, col4_top = st.columns([2, 1.5, 1.5, 1])
                
                with col1_top:
                    save_clicked_top = st.form_submit_button("💾 Agregar Seleccionadas", type="primary", use_container_width=True)
                
                with col2_top:
                    select_all_clicked_top = st.form_submit_button("✅ Seleccionar Todas", use_container_width=True)
                
                with col3_top:
                    deselect_all_clicked_top = st.form_submit_button("❌ Deseleccionar Todas", use_container_width=True)
                
                with col4_top:
                    cancel_clicked_top = st.form_submit_button("❌ Cancelar", type="secondary", use_container_width=True)
                
                st.markdown("---")  # Línea divisoria
                
                # Tabla editable
                edited_df = st.data_editor(
                    df_bulk,
                    column_config=column_config,
                    width="stretch",
                    hide_index=True,
                    height=400,
                    key="bulk_table_editor"
                )
                
                # Actualizar el estado con los cambios del usuario
                if edited_df is not None:
                    st.session_state.bulk_df_state = edited_df.copy()
                
                # Contador de estaciones seleccionadas
                if edited_df is not None:
                    selected_count = edited_df['Seleccionar'].sum()
                    st.info(f"📊 {selected_count} estaciones seleccionadas")
                
                # Botones inferiores
                st.markdown("---")  # Línea divisoria
                
                col1_bottom, col2_bottom, col3_bottom, col4_bottom = st.columns([2, 1.5, 1.5, 1])
                
                with col1_bottom:
                    save_clicked_bottom = st.form_submit_button("💾 Agregar Seleccionadas", key="save_bottom_btn", type="primary", use_container_width=True)
                
                with col2_bottom:
                    select_all_clicked_bottom = st.form_submit_button("✅ Seleccionar Todas", key="select_all_bottom_btn", use_container_width=True)
                
                with col3_bottom:
                    deselect_all_clicked_bottom = st.form_submit_button("❌ Deseleccionar Todas", key="deselect_all_bottom_btn", use_container_width=True)
                
                with col4_bottom:
                    cancel_clicked_bottom = st.form_submit_button("❌ Cancelar", key="cancel_bottom_btn", type="secondary", use_container_width=True)
                
                # Procesar clics en los botones
                save_clicked = save_clicked_top or save_clicked_bottom
                select_all_clicked = select_all_clicked_top or select_all_clicked_bottom
                deselect_all_clicked = deselect_all_clicked_top or deselect_all_clicked_bottom
                cancel_clicked = cancel_clicked_top or cancel_clicked_bottom
                
                # Procesar acciones de los botones
                if select_all_clicked:
                    st.session_state.bulk_df_state['Seleccionar'] = True
                    st.rerun()
                
                if deselect_all_clicked:
                    st.session_state.bulk_df_state['Seleccionar'] = False
                    st.rerun()
                
                # El botón de cancelación se procesa fuera del formulario
                if cancel_clicked:
                    st.session_state.clear_search = True
                    st.session_state.input_counter = st.session_state.get('input_counter', 0) + 1
                    st.rerun()
                
                # Información sobre deselección
                st.info("💡 **Tip:** Para deseleccionar estaciones individuales, desmarca los checkboxes en la columna '✓'.")
                                
            # Procesar guardado
            if save_clicked:
                if edited_df is not None:
                    selected_stations = edited_df[edited_df['Seleccionar'] == True]
                    
                    if len(selected_stations) == 0:
                        st.error("❌ No has seleccionado ninguna estación para guardar")
                    else:
                        success_count = 0
                        error_count = 0
                        saved_items = []
                        
                        for _, row in selected_stations.iterrows():
                            try:
                                if not row['Indicativo'] or not row['Operador']:
                                    st.error(f"❌ {row['Indicativo']}: Faltan campos obligatorios")
                                    error_count += 1
                                    continue
                                
                                created_by = current_user['username'] if current_user else 'guest'
                                report_id = db.add_report(
                                    row['Indicativo'], row['Operador'], row['Estado'],
                                    row['Ciudad'], row['Señal'], row['Zona'],
                                    row['Sistema'], grid_locator="", hf_frequency="",
                                    hf_band="", hf_mode="", hf_power="",
                                    observations=row['Observaciones'], created_by=created_by
                                )
                                success_count += 1
                                saved_items.append({
                                    'Indicativo': row['Indicativo'],
                                    'Operador': row['Operador'],
                                    'Estado': row['Estado'],
                                    'Ciudad': row['Ciudad'],
                                    'Zona': row['Zona'],
                                    'Sistema': row['Sistema']
                                })
                                
                            except Exception as e:
                                st.error(f"❌ Error guardando {row['Indicativo']}: {str(e)}")
                                error_count += 1
                        
                        # Preparar resumen de la operación para mostrar en un modal
                        if success_count > 0:
                            st.session_state.save_summary = {
                                'count': success_count,
                                'errors': error_count,
                                'items': saved_items
                            }
                            st.session_state.show_save_summary = True
                        
                        # Limpiar búsqueda después de guardar
                        st.session_state.clear_search = True
                        st.rerun()
            
            # Procesar cancelación/limpiar
            if cancel_clicked:
                st.session_state.clear_search = True
                st.session_state.input_counter = st.session_state.get('input_counter', 0) + 1
                st.rerun()
            
            st.markdown("---")

    # Usar el valor seleccionado
    call_sign = call_sign_input if call_sign_input else default_call
    
    # Auto-llenar zona y sistema cuando no hay resultados de captura masiva
    auto_zona_idx = default_zona
    auto_sistema_idx = default_sistema
    
    # Solo auto-llenar si hay un indicativo y NO hay resultados de captura masiva
    if call_sign and call_sign.strip() and not suggestions:
        from utils import extract_prefix_from_callsign, get_zone_from_prefix
        
        # Extraer zona automáticamente del indicativo
        prefix = extract_prefix_from_callsign(call_sign.strip())
        if prefix:
            auto_zone = get_zone_from_prefix(prefix)
            if auto_zone:
                try:
                    auto_zona_idx = get_zonas().index(auto_zone)
                except ValueError:
                    auto_zona_idx = default_zona
        
        # Usar sistema preferido del usuario
        if 'prefill_sistema' not in st.session_state:
            try:
                auto_sistema_idx = get_sistemas().index(user_preferred_system)
            except ValueError:
                auto_sistema_idx = 0
    
    # Formulario de registro
    with st.form("report_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            operator_name = st.text_input("👤 Nombre del Operador",placeholder="(Obligatorio) | Ejemplo: Juan Pérez", value=default_name)
            estado = st.selectbox("🏛️ Estado", get_estados_list(), index=default_estado_idx, help="Selecciona el estado")
            ciudad = st.text_input("🏙️ Ciudad",placeholder="(Opcional) | Ejemplo: Durangotitlan de los Baches", value=default_ciudad, help="Ejemplo: Monterrey, Guadalajara")
        
        with col2:
            signal_report = st.text_input("📶 Reporte de Señal",value="59", help="Ejemplo: Buena, Regular, Mala")
            zona = st.selectbox("🌍 Zona", get_zonas(), index=auto_zona_idx)
            # Usar sistema preferido como default si no hay prefill
            if 'prefill_sistema' not in st.session_state:
                try:
                    default_sistema = get_sistemas().index(user_preferred_system)
                except ValueError:
                    default_sistema = 0
            sistema = st.selectbox("📡 Sistema", get_sistemas(), index=auto_sistema_idx)
        
        # Campos HF dinámicos con valores preferidos como default
        hf_frequency = ""
        hf_mode = ""
        hf_power = ""
        
        if sistema == "HF":
            st.subheader("📻 Configuración HF")
            col_hf1, col_hf2, col_hf3 = st.columns(3)
            
            with col_hf1:
                hf_frequency = st.text_input(
                    "Frecuencia (MHz)", 
                    value=user_hf_frequency,
                    placeholder="14.230", 
                    help="1.8-30 MHz"
                )
            
            with col_hf2:
                hf_mode = st.selectbox(
                    "Modo", 
                    ["", "USB", "LSB", "CW", "DIGITAL"],
                    index=["", "USB", "LSB", "CW", "DIGITAL"].index(user_hf_mode) if user_hf_mode in ["", "USB", "LSB", "CW", "DIGITAL"] else 0
                )
            
            with col_hf3:
                hf_power = st.text_input(
                    "Potencia (W)", 
                    value=user_hf_power,
                    placeholder="100"
                )
        
        observations = st.text_area(
            "Observaciones",
            placeholder="Comentarios adicionales (opcional)",
            height=100
        )
        
        submitted = st.form_submit_button("📝 Agregar Reporte", width='stretch')
        
        if submitted:
            # Validar campos
            is_valid, errors = validate_all_fields(call_sign, operator_name, estado, ciudad, signal_report, zona, sistema)
            
            if is_valid:
                # Verificar si hay inconsistencias que requieren confirmación
                needs_confirmation, warning_msg = detect_inconsistent_data(call_sign, estado, zona)
                
                if needs_confirmation:
                    # Guardar datos en session_state para confirmación
                    st.session_state.pending_report = {
                        'call_sign': call_sign,
                        'operator_name': operator_name,
                        'estado': estado,
                        'ciudad': ciudad,
                        'signal_report': signal_report,
                        'zona': zona,
                        'sistema': sistema,
                        'observations': observations,
                        'warning_msg': warning_msg
                    }
                    st.rerun()
                else:
                    # No hay inconsistencias, guardar directamente
                    try:
                        created_by = current_user['username'] if current_user else 'guest'
                        # Agregar a la base de datos
                        report_id = db.add_report(
                            call_sign, operator_name, estado, ciudad, 
                            signal_report, zona, sistema, 
                            grid_locator="", hf_frequency="", hf_band="", hf_mode="", hf_power="", 
                            observations=observations, session_date=session_date, created_by=created_by
                        )
                        
                        # Limpiar datos precargados después de agregar reporte
                        for key in ['prefill_call', 'prefill_name', 'prefill_estado', 'prefill_ciudad', 'prefill_zona', 'prefill_sistema']:
                            if key in st.session_state:
                                del st.session_state[key]
                        
                        # Guardar resumen en sesión para mostrar modal
                        st.session_state.save_summary = {
                            'count': 1,
                            'errors': 0,
                            'items': [{
                                'Indicativo': call_sign,
                                'Operador': operator_name,
                                'Estado': estado,
                                'Ciudad': ciudad,
                                'Zona': zona,
                                'Sistema': sistema
                            }]
                        }
                        st.session_state.show_save_summary = True
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Error al agregar reporte: {str(e)}")
            else:
                for error in errors:
                    st.error(f"❌ {error}")
    
    # Mostrar ventana emergente modal para confirmación
    if 'pending_report' in st.session_state:
        @st.dialog("⚠️ Confirmación de Datos Inconsistentes")
        def show_confirmation_dialog():
            pending = st.session_state.pending_report
            
            st.markdown(pending['warning_msg'])
            
            col_confirm, col_cancel = st.columns(2)
            
            with col_confirm:
                if st.button("✅ Continuar y Guardar", key="confirm_save_modal", type="primary", width='stretch'):
                    try:
                        created_by = current_user['username'] if current_user else 'guest'
                        # Agregar a la base de datos
                        report_id = db.add_report(
                            pending['call_sign'], pending['operator_name'], pending['estado'], 
                            pending['ciudad'], pending['signal_report'], pending['zona'], 
                            pending['sistema'], 
                            grid_locator="", hf_frequency="", hf_band="", hf_mode="", hf_power="", 
                            observations=pending['observations'], session_date=session_date, created_by=created_by
                        )
                        
                        # Limpiar datos precargados después de agregar reporte
                        for key in ['prefill_call', 'prefill_name', 'prefill_estado', 'prefill_ciudad', 'prefill_zona', 'prefill_sistema']:
                            if key in st.session_state:
                                del st.session_state[key]
                        
                        # Preparar resumen en sesión
                        st.session_state.save_summary = {
                            'count': 1,
                            'errors': 0,
                            'items': [{
                                'Indicativo': pending['call_sign'],
                                'Operador': pending['operator_name'],
                                'Estado': pending['estado'],
                                'Ciudad': pending['ciudad'],
                                'Zona': pending['zona'],
                                'Sistema': pending['sistema']
                            }]
                        }
                        st.session_state.show_save_summary = True
                        
                        # Limpiar pending_report
                        del st.session_state.pending_report
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Error al agregar reporte: {str(e)}")
            
            with col_cancel:
                if st.button("❌ Cancelar y Editar", key="cancel_save_modal", width='stretch'):
                    # Limpiar pending_report
                    del st.session_state.pending_report
                    st.rerun()
        
        show_confirmation_dialog()
        
    # Mostrar modal con resumen de registros guardados
    if st.session_state.get('show_save_summary', False) and 'save_summary' in st.session_state:
        summary = st.session_state.save_summary
        @st.dialog("✅ Registros Agregados Exitosamente")
        def show_save_summary_dialog():
            st.success(f"👤 {(current_user['full_name'] if current_user else 'Usuario')} — se guardaron {summary['count']} registro(s) exitosamente.")
            if summary.get('errors', 0):
                st.warning(f"{summary['errors']} registro(s) presentaron errores y no se guardaron.")
            
            # Botón de cierre enfocado dentro de formulario
            with st.form('close_summary_form'):
                close_clicked = st.form_submit_button('Cerrar', type='primary', width='stretch')
            
            if close_clicked:
                del st.session_state['show_save_summary']
                del st.session_state['save_summary']
                st.rerun()
        show_save_summary_dialog()

    # Mostrar reportes recientes de la sesión actual
    st.subheader(f"Reportes de la Sesión - {session_date.strftime('%d/%m/%Y')}")
    
    recent_reports = db.get_all_reports(session_date)
    
    if not recent_reports.empty:
        # Métricas del historial
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            unique_participants = recent_reports['call_sign'].nunique()
            st.metric("Participantes Únicos", unique_participants)
        
        with col2:
            total_reports = len(recent_reports)
            st.metric("Total Reportes", total_reports)

        with col3:
            if not recent_reports.empty:
                # Encontrar el sistema que más aparece
                sistema_counts = recent_reports['sistema'].value_counts()
                most_used_system = sistema_counts.index[0] if len(sistema_counts) > 0 else "N/A"
                system_count = sistema_counts.iloc[0] if len(sistema_counts) > 0 else 0
                st.metric("Sistema Más Utilizado", most_used_system, f"{system_count} reportes")
            else:
                st.metric("Sistema Más Utilizado", "N/A")
        
        #with col4:
        #    if not recent_reports.empty:
        #        # Encontrar el indicativo que más aparece
        #        call_sign_counts = recent_reports['call_sign'].value_counts()
        #        most_used_call = call_sign_counts.index[0] if len(call_sign_counts) > 0 else "N/A"
        #        usage_count = call_sign_counts.iloc[0] if len(call_sign_counts) > 0 else 0
        #        st.metric("Más Utilizada", most_used_call, f"{usage_count} reportes")
        #    else:
        #        st.metric("Más Utilizada", "N/A")
        with col4:
            if not recent_reports.empty:
                # Encontrar el estado que más aparece
                estado_counts = recent_reports['qth'].value_counts()
                most_active_state = estado_counts.index[0] if len(estado_counts) > 0 else "N/A"
                state_count = estado_counts.iloc[0] if len(estado_counts) > 0 else 0
                st.metric("Estado Más Activo", most_active_state, f"{state_count} reportes")
            else:
                st.metric("Estado Más Activo", "N/A")

        with col5:
            # Zona con más actividad
            if not recent_reports.empty:
                zona_counts = recent_reports['zona'].value_counts()
                most_active_zone = zona_counts.index[0] if len(zona_counts) > 0 else "N/A"
                zone_count = zona_counts.iloc[0] if len(zona_counts) > 0 else 0
                st.metric("Zona Más Activa", most_active_zone, f"{zone_count} reportes")
            else:
                st.metric("Zona Más Activa", "N/A")
        
        # Mostrar reportes con checkboxes para selección
        st.write("**Reportes de esta sesión:**")
        
        # Inicializar lista de reportes seleccionados
        if 'selected_reports' not in st.session_state:
            st.session_state.selected_reports = []
        
        # Checkbox para seleccionar todos
        col_select_all, col_actions = st.columns([2, 6])
        
        with col_select_all:
            select_all = st.checkbox("Seleccionar todos", key="select_all_reports")
            if select_all:
                st.session_state.selected_reports = list(recent_reports['id'].values)
            elif not select_all and len(st.session_state.selected_reports) == len(recent_reports):
                st.session_state.selected_reports = []
        
        with col_actions:
            if st.session_state.selected_reports:
                col_edit, col_delete, col_export = st.columns(3)
                
                with col_edit:
                    if st.button(f"✏️ Editar Seleccionados ({len(st.session_state.selected_reports)})", key="edit_selected"):
                        st.session_state.show_bulk_edit = True
                        st.rerun()
                
                with col_delete:
                    if st.button(f"🗑️ Eliminar Seleccionados ({len(st.session_state.selected_reports)})", key="delete_selected"):
                        st.session_state.confirm_bulk_delete = True
                        st.rerun()
                
                with col_export:
                    if st.button(f"📄 Ver Seleccionados ({len(st.session_state.selected_reports)})", key="view_selected"):
                        st.session_state.show_selected_details = True
                        st.rerun()
        
        st.divider()
        
        
        # Preparar datos para la tabla con checkboxes
        display_data = recent_reports.copy()
        
        # Agregar columna de selección
        display_data['Seleccionar'] = display_data['id'].apply(lambda x: x in st.session_state.selected_reports)
        
        # Formatear timestamp
        display_data['Hora'] = pd.to_datetime(display_data['timestamp']).dt.strftime('%H:%M:%S')
        
        # Agregar columna de usuario
        display_data['Capturado por'] = display_data['created_by'].fillna('N/A')
        
        # Configurar columnas principales a mostrar
        columns_to_show = ['Seleccionar', 'call_sign', 'operator_name', 'qth', 'zona', 'sistema', 'signal_report', 'Hora', 'Capturado por']
        column_config = {
            "Seleccionar": st.column_config.CheckboxColumn("✓", help="Seleccionar para acciones masivas", default=False, width="small"),
            'call_sign': st.column_config.TextColumn("Indicativo", width="medium"),
            'operator_name': st.column_config.TextColumn("Operador", width="medium"),
            'qth': st.column_config.TextColumn("QTH", width="medium"),
            'zona': st.column_config.TextColumn("Zona", width="small"),
            'sistema': st.column_config.TextColumn("Sistema", width="medium"),
            'signal_report': st.column_config.TextColumn("Señal", width="small"),
            'Hora': st.column_config.TextColumn("Hora", width="small"),
            'Capturado por': st.column_config.TextColumn("Usuario", width="medium")
        }
        
        # Mostrar tabla de solo lectura con selección para editar
        st.markdown("### 📋 Reportes de la Sesión")
        
        # Preparar datos para mostrar en tabla
        display_data = recent_reports.copy()
        display_data['Hora'] = pd.to_datetime(display_data['timestamp']).dt.strftime('%H:%M:%S')
        display_data['Seleccionar'] = display_data['id'].isin(st.session_state.selected_reports)
        display_data['Capturado por'] = display_data['created_by'].fillna('N/A')
        
        # Configuración de columnas para tabla de solo lectura
        column_config = {
            'Seleccionar': st.column_config.CheckboxColumn(
                "Sel",
                help="Seleccionar para editar o acciones masivas",
                default=False,
                width="small"
            ),
            'call_sign': st.column_config.TextColumn("Indicativo", width="medium"),
            'operator_name': st.column_config.TextColumn("Operador", width="medium"),
            'qth': st.column_config.TextColumn("QTH", width="medium"),
            'zona': st.column_config.TextColumn("Zona", width="small"),
            'sistema': st.column_config.TextColumn("Sistema", width="medium"),
            'signal_report': st.column_config.TextColumn("Señal", width="small"),
            'Hora': st.column_config.TextColumn("Hora", width="small"),
            'Capturado por': st.column_config.TextColumn("Usuario", width="medium")
        }
        
        # Mostrar tabla de solo lectura (solo para selección)
        columns_to_show = ['Seleccionar', 'call_sign', 'operator_name', 'qth', 'zona', 'sistema', 'signal_report', 'Hora', 'Capturado por']
        
        selected_df = st.data_editor(
            display_data[columns_to_show],
            column_config=column_config,
            width='stretch',
            hide_index=True,
            disabled=['call_sign', 'operator_name', 'qth', 'zona', 'sistema', 'signal_report', 'Hora', 'Capturado por'],  # Solo permitir editar checkboxes
            key="session_reports_selection_table"
        )
        
        # Actualizar selecciones basadas en la tabla
        if selected_df is not None:
            new_selections = []
            for idx, row in selected_df.iterrows():
                if row['Seleccionar']:
                    report_id = display_data.iloc[idx]['id']
                    new_selections.append(report_id)
            
            # Actualizar session_state solo si hay cambios en selecciones
            if set(new_selections) != set(st.session_state.selected_reports):
                st.session_state.selected_reports = new_selections
                st.rerun()
        
        
        # Mostrar mensajes de éxito o error
        if 'delete_success_msg' in st.session_state:
            st.success(st.session_state.delete_success_msg)
            del st.session_state.delete_success_msg
        
        if 'delete_error_msg' in st.session_state:
            st.error(st.session_state.delete_error_msg)
            del st.session_state.delete_error_msg
        
        # Fin de la sección de reportes
        
        # Modales para acciones masivas
        
        # Modal para eliminar seleccionados
        if st.session_state.get('confirm_bulk_delete', False):
            @st.dialog(f"🗑️ Eliminar {len(st.session_state.selected_reports)} Reportes")
            def show_bulk_delete_confirmation():
                selected_reports_data = recent_reports[recent_reports['id'].isin(st.session_state.selected_reports)]
                
                st.warning(f"¿Estás seguro de que deseas eliminar {len(st.session_state.selected_reports)} reportes?")
                st.write("**Reportes a eliminar:**")
                for _, report in selected_reports_data.iterrows():
                    st.write(f"• {report['call_sign']} - {report['operator_name']}")
                st.write("Esta acción no se puede deshacer.")
                
                col_confirm, col_cancel = st.columns(2)
                
                with col_confirm:
                    if st.button("🗑️ Sí, Eliminar Todos", key="confirm_bulk_delete_modal", type="primary", width='stretch'):
                        try:
                            deleted_count = 0
                            
                            for report_id in st.session_state.selected_reports:
                                # Convertir np.int64 a int nativo de Python
                                report_id_int = int(report_id)
                                result = db.delete_report(report_id_int)
                                if result > 0:
                                    deleted_count += 1
                            
                            st.session_state.delete_success_msg = f"✅ {deleted_count} reportes eliminados exitosamente"
                            
                            st.session_state.selected_reports = []
                            del st.session_state.confirm_bulk_delete
                            st.rerun()
                        except Exception as e:
                            st.session_state.delete_error_msg = f"❌ Error al eliminar reportes: {str(e)}"
                            del st.session_state.confirm_bulk_delete
                            st.rerun()
                
                with col_cancel:
                    if st.button("❌ Cancelar", key="cancel_bulk_delete_modal", width='stretch'):
                        del st.session_state.confirm_bulk_delete
                        st.rerun()
            
            show_bulk_delete_confirmation()
        
        # Modal para ver detalles de seleccionados
        if st.session_state.get('show_selected_details', False):
            @st.dialog(f"📄 Detalles de {len(st.session_state.selected_reports)} Reportes Seleccionados")
            def show_selected_details():
                selected_reports_data = recent_reports[recent_reports['id'].isin(st.session_state.selected_reports)]
                
                for _, report in selected_reports_data.iterrows():
                    with st.expander(f"{report['call_sign']} - {report['operator_name']}", expanded=False):
                        col_det1, col_det2 = st.columns(2)
                        with col_det1:
                            st.write(f"**ID:** {report['id']}")
                            st.write(f"**Indicativo:** {report['call_sign']}")
                            st.write(f"**Operador:** {report['operator_name']}")
                            st.write(f"**QTH:** {report['qth']}")
                        with col_det2:
                            st.write(f"**Zona:** {report['zona']}")
                            st.write(f"**Sistema:** {report['sistema']}")
                            st.write(f"**Señal:** {report['signal_report']}")
                            timestamp = pd.to_datetime(report['timestamp']).strftime('%H:%M:%S')
                            st.write(f"**Hora:** {timestamp}")
                            if 'hf_frequency' in report and pd.notna(report['hf_frequency']):
                                st.write(f"**Frecuencia:** {report['hf_frequency']}")
                                st.write(f"**Modo:** {report.get('hf_mode', 'N/A')}")
                        if 'observations' in report and pd.notna(report['observations']) and report['observations']:
                            st.write(f"**Observaciones:** {report['observations']}")
                
                if st.button("❌ Cerrar", key="close_selected_details", width='stretch'):
                    del st.session_state.show_selected_details
                    st.rerun()
        
        if st.session_state.get('show_bulk_edit', False):
            @st.dialog(f"✏️ Editar {len(st.session_state.selected_reports)} Reporte{'s' if len(st.session_state.selected_reports) > 1 else ''}")
            def show_individual_edit():
                selected_reports_data = recent_reports[recent_reports['id'].isin(st.session_state.selected_reports)]
                
                # Si es solo un reporte, mostrar edición completa
                if len(st.session_state.selected_reports) == 1:
                    report = selected_reports_data.iloc[0]
                    
                    with st.form(f"individual_edit_form_{report['id']}"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            edit_call_sign = st.text_input(
                                "Indicativo",
                                value=report['call_sign'],
                                key=f"bulk_call_{report['id']}",
                                disabled=True
                            )
                            operator_name = st.text_input(
                                "Nombre del Operador",
                                value=report['operator_name'],
                                key=f"bulk_operator_{report['id']}"
                            )
                        
                        with col2:
                            # Obtener índice del estado actual
                            estados_list = get_estados_list()
                            current_qth = report.get('qth', '')
                            if current_qth in estados_list:
                                qth_index = estados_list.index(current_qth)
                            else:
                                qth_index = 0
                            
                            edit_qth = st.selectbox(
                                "Estado/QTH:",
                                estados_list,
                                index=qth_index,
                                key=f"bulk_estado_{report['id']}"
                            )
                            
                            edit_ciudad = st.text_input(
                                "Ciudad",
                                value=report.get('ciudad', ''),
                                key=f"bulk_ciudad_{report['id']}"
                            )
                        
                        # Zona
                        zonas_list = get_zonas()
                        current_zona = report.get('zona', '')
                        zona_index = zonas_list.index(current_zona) if current_zona in zonas_list else 0
                        edit_zona = st.selectbox(
                            "Zona:",
                            zonas_list,
                            index=zona_index,
                            key=f"bulk_zona_{report['id']}"
                        )
                        
                        # Sistema
                        sistemas_list = get_sistemas()
                        current_sistema = report.get('sistema', '')
                        sistema_index = sistemas_list.index(current_sistema) if current_sistema in sistemas_list else 0
                        edit_sistema = st.selectbox(
                            "Sistema:",
                            sistemas_list,
                            index=sistema_index,
                            key=f"bulk_sistema_{report['id']}"
                        )
                        
                        edit_signal_report = st.text_input(
                            "Reporte de Señal",
                            value=report.get('signal_report', ''),
                            key=f"bulk_signal_{report['id']}"
                        )
                        
                        edit_grid_locator = st.text_input(
                            "Grid Locator (opcional):",
                            value=report.get('grid_locator', '') or '',
                            key=f"bulk_grid_locator_{report['id']}",
                            help="Ejemplo: DL74QB"
                        )
                        
                        edit_observations = st.text_area(
                            "Observaciones:",
                            value=report.get('observations', '') or '',
                            key=f"bulk_obs_{report['id']}",
                            height=100
                        )
                        
                        col_save, col_cancel = st.columns(2)
                        
                        with col_save:
                            save_individual = st.form_submit_button(
                                f"💾 Guardar Cambios",
                                type="primary",
                                width='stretch'
                            )
                        
                        with col_cancel:
                            cancel_individual = st.form_submit_button(
                                "❌ Cancelar",
                                width='stretch'
                            )
                        
                        if save_individual:
                            # Validar datos
                            is_valid, errors = validate_all_fields(edit_call_sign, operator_name, edit_qth, edit_ciudad, edit_signal_report, edit_zona, edit_sistema)
                            
                            if is_valid:
                                # Verificar inconsistencias
                                needs_confirmation, warning_msg = detect_inconsistent_data(edit_call_sign, edit_qth, edit_zona)
                                
                                if needs_confirmation:
                                    # Guardar datos en session_state para confirmación
                                    pending_key = f"pending_individual_edit_{report['id']}"
                                    st.session_state[pending_key] = {
                                        'report_id': report['id'],
                                        'call_sign': edit_call_sign,
                                        'operator_name': operator_name,
                                        'qth': edit_qth,
                                        'ciudad': edit_ciudad,
                                        'zona': edit_zona,
                                        'sistema': edit_sistema,
                                        'signal_report': edit_signal_report,
                                        'grid_locator': edit_grid_locator,
                                        'observations': edit_observations,
                                        'warning_msg': warning_msg
                                    }
                                    del st.session_state.show_bulk_edit
                                    st.rerun()
                                else:
                                    # Actualizar directamente
                                    try:
                                        db.update_report(
                                            int(report['id']),
                                            call_sign=edit_call_sign.upper(),
                                            operator_name=operator_name,
                                            qth=edit_qth,
                                            ciudad=edit_ciudad.title(),
                                            zona=edit_zona,
                                            sistema=edit_sistema,
                                            signal_report=edit_signal_report,
                                            grid_locator=edit_grid_locator.upper() if edit_grid_locator else None,
                                            observations=edit_observations
                                        )
                                        
                                        st.session_state.selected_reports = []
                                        del st.session_state.show_bulk_edit
                                        st.success("✅ Reporte actualizado exitosamente")
                                        st.rerun()
                                        
                                    except Exception as e:
                                        st.error(f"❌ Error al actualizar: {str(e)}")
                            else:
                                for error in errors:
                                    st.error(f"❌ {error}")
                        
                        if cancel_individual:
                            del st.session_state.show_bulk_edit
                            st.rerun()
                
                else:
                    # Edición masiva para múltiples reportes
                    st.write("**Campos a actualizar (deja vacío para mantener valor original):**")
                    
                    with st.form("bulk_edit_form"):
                        col_edit1, col_edit2 = st.columns(2)
                        
                        with col_edit1:
                            bulk_qth = st.selectbox("QTH (Estado)", options=["-- No cambiar --"] + get_estados_list())
                            bulk_ciudad = st.text_input("Ciudad", placeholder="Dejar vacío para no cambiar")
                            bulk_zona = st.selectbox("Zona", options=["-- No cambiar --"] + get_zonas())
                            
                        with col_edit2:
                            bulk_sistema = st.selectbox("Sistema", options=["-- No cambiar --"] + get_sistemas())
                            bulk_signal = st.selectbox("Reporte de Señal", options=["-- No cambiar --"] + ["59", "58", "57", "56", "55", "54", "53", "52", "51", "Buena", "Regular", "Mala"])
                            bulk_observations = st.text_area("Observaciones", placeholder="Dejar vacío para no cambiar")
                        
                        st.write("**Reportes que serán actualizados:**")
                        for _, report in selected_reports_data.iterrows():
                            st.write(f"• {report['call_sign']} - {report['operator_name']}")
                        
                        col_save, col_cancel, col_info = st.columns([1, 1, 2])
                        
                        with col_save:
                            save_bulk = st.form_submit_button(
                                f"💾 Actualizar Todos",
                                type="primary",
                                width='stretch'
                            )
                        
                        with col_cancel:
                            cancel_bulk = st.form_submit_button(
                                "❌ Cancelar",
                                width='stretch'
                            )
                        
                        with col_info:
                            selected_count = len(selected_reports_data)
                            st.info(f"📊 **{selected_count}** registros seleccionados")
                        
                        # Procesar guardado masivo
                        if save_bulk:
                            try:
                                updated_count = 0
                                for report_id in st.session_state.selected_reports:
                                    # Obtener datos actuales del reporte
                                    current_report = recent_reports[recent_reports['id'] == report_id].iloc[0]
                                    
                                    # Preparar datos para actualizar (solo los que no están vacíos)
                                    update_data = {}
                                    
                                    if bulk_qth.strip():
                                        update_data['qth'] = bulk_qth.strip()
                                    if bulk_ciudad.strip():
                                        update_data['ciudad'] = bulk_ciudad.strip().title()
                                    if bulk_zona != "-- No cambiar --":
                                        update_data['zona'] = bulk_zona
                                    if bulk_sistema != "-- No cambiar --":
                                        update_data['sistema'] = bulk_sistema
                                    if bulk_signal != "-- No cambiar --":
                                        update_data['signal_report'] = bulk_signal
                                    if bulk_observations.strip():
                                        update_data['observations'] = bulk_observations.strip()
                                    
                                    # Solo actualizar si hay cambios
                                    if update_data:
                                        db.update_report(report_id, **update_data)
                                        updated_count += 1
                                
                                st.session_state.selected_reports = []
                                del st.session_state.show_bulk_edit
                                st.success(f"✅ {updated_count} reportes actualizados exitosamente")
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"❌ Error al actualizar reportes: {str(e)}")
                        else:
                            # Limpiar estado de edición masiva
                            del st.session_state.show_bulk_edit
                            st.rerun()
            
            show_individual_edit()
        
        # Modal de confirmación para edición individual con inconsistencias
        for report_id in st.session_state.selected_reports:
            pending_key = f"pending_individual_edit_{report_id}"
            if pending_key in st.session_state:
                @st.dialog("⚠️ Confirmación de Edición - Datos Inconsistentes")
                def show_individual_edit_confirmation():
                    pending_edit = st.session_state[pending_key]
                    
                    st.markdown(pending_edit['warning_msg'])
                    
                    col_conf, col_canc = st.columns(2)
                    
                    with col_conf:
                        if st.button("✅ Continuar y Actualizar", key=f"confirm_individual_edit_{report_id}", type="primary", width='stretch'):
                            try:
                                # Actualizar reporte
                                db.update_report(
                                    pending_edit['report_id'],
                                    call_sign=pending_edit['call_sign'].upper(),
                                    operator_name=pending_edit['operator_name'],
                                    qth=pending_edit['qth'],
                                    ciudad=pending_edit['ciudad'].title(),
                                    zona=pending_edit['zona'],
                                    sistema=pending_edit['sistema'],
                                    signal_report=pending_edit['signal_report'],
                                    grid_locator=pending_edit['grid_locator'].upper() if pending_edit['grid_locator'] else None,
                                    observations=pending_edit['observations']
                                )
                                
                                st.success("✅ Reporte actualizado exitosamente")
                                st.session_state.selected_reports = []
                                del st.session_state[pending_key]
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"❌ Error al actualizar reporte: {str(e)}")
                    
                    with col_canc:
                        if st.button("❌ Revisar Datos", key=f"cancel_individual_edit_{report_id}", width='stretch'):
                            del st.session_state[pending_key]
                            st.rerun()
                
                show_individual_edit_confirmation()
                break
    else:
        st.info("📝 **Primero agrega algunos reportes para que aparezcan en el historial**")
        st.info("Una vez que tengas reportes, podrás usar la función de registro rápido desde el historial.")

# ==================== FUNCIONES DE REPORTES AVANZADOS ====================

def show_advanced_reports():
    """Muestra reportes estadísticos avanzados comparativos"""
    st.header("📊 Reportes Avanzados")
    st.markdown("### Análisis Comparativo de Sesiones")
    
    try:
        # Obtener todas las fechas con reportes
        conn = sqlite3.connect(db.db_path)
        
        # Consulta para obtener fechas únicas con reportes
        dates_query = """
        SELECT DISTINCT DATE(session_date) as report_date
        FROM reports
        ORDER BY report_date DESC
        """
        
        dates_df = pd.read_sql_query(dates_query, conn)
        
        if len(dates_df) < 2:
            st.warning("⚠️ Se necesitan al menos 2 fechas con reportes para generar comparativas.")
            st.info("💡 Los reportes comparativos estarán disponibles después de tener más datos.")
            conn.close()
            return
            
        # Convertir a lista de fechas
        available_dates = pd.to_datetime(dates_df['report_date']).dt.date.tolist()
        
        # Encontrar automáticamente los dos últimos domingos con reportes
        last_sundays = []
        for date in available_dates:
            if date.weekday() == 6:  # 6 es domingo
                if len(last_sundays) < 2 and date not in last_sundays:
                    last_sundays.append(date)
                    if len(last_sundays) == 2:
                        break
        
        # Si no hay suficientes domingos, usar las dos fechas más recientes
        if len(last_sundays) < 2:
            last_sundays = available_dates[:2]
        
        # Ordenar las fechas (más antigua primero)
        last_sundays = sorted(last_sundays)
        
        # Selector de fechas
        st.markdown("### Seleccione las fechas a comparar")
        
        # Crear dos columnas para los selectores de fecha
        col1, col2 = st.columns(2)
        
        with col1:
            fecha1 = st.selectbox(
                "Primera fecha:",
                options=available_dates,
                index=available_dates.index(last_sundays[0]) if last_sundays[0] in available_dates else 0,
                format_func=lambda d: d.strftime('%d/%m/%Y')
            )
        
        with col2:
            # Filtrar fechas posteriores a la primera seleccionada
            available_dates_second = [d for d in available_dates if d != fecha1]
            
            # Encontrar la segunda fecha más cercana a la primera
            second_date_index = 0
            if len(available_dates_second) > 0:
                if last_sundays[1] in available_dates_second and last_sundays[1] != fecha1:
                    second_date_index = available_dates_second.index(last_sundays[1])
                elif len(available_dates_second) > 0:
                    # Encontrar la fecha más cercana a la primera seleccionada
                    date_diffs = [abs((d - fecha1).days) for d in available_dates_second]
                    second_date_index = date_diffs.index(min(d for d in date_diffs if d > 0))
            
            fecha2 = st.selectbox(
                "Segunda fecha:",
                options=available_dates_second,
                index=second_date_index,
                format_func=lambda d: d.strftime('%d/%m/%Y')
            )
        
        # Asegurarse de que fecha1 sea la más reciente
        if fecha1 < fecha2:
            fecha1, fecha2 = fecha2, fecha1
        
        # Obtener datos de ambas fechas para mostrar en la comparación
        current_data = pd.read_sql_query(
            "SELECT * FROM reports WHERE DATE(session_date) = ?", 
            conn, 
            params=[fecha1.strftime('%Y-%m-%d')]
        )
        
        previous_data = pd.read_sql_query(
            "SELECT * FROM reports WHERE DATE(session_date) = ?", 
            conn, 
            params=[fecha2.strftime('%Y-%m-%d')]
        )
        
        # Obtener números de boletín para ambas fechas
        bulletin1 = get_bulletin_number(fecha1)
        bulletin2 = get_bulletin_number(fecha2)
        
        # Mostrar información de comparación con formato mejorado
        st.markdown(f"""
        <div style='background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin: 10px 0;'>
            <h3 style='margin: 0 0 10px 0; color: #1f77b4;'>📅 Comparación de Boletines</h3>
            <div style='display: flex; justify-content: space-between;'>
                <div style='text-align: center; padding: 10px; background: white; border-radius: 8px; flex: 1; margin: 0 5px;'>
                    <div style='font-weight: bold; font-size: 1.2em;'>Boletín #{bulletin1}</div>
                    <div style='color: #666;'>{fecha1.strftime('%d/%m/%Y')}</div>
                    <div style='color: #888; font-size: 0.9em;'>{fecha1.strftime('%A').capitalize()}</div>
                </div>
                <div style='display: flex; align-items: center; justify-content: center; font-size: 1.5em; color: #666;'>vs</div>
                <div style='text-align: center; padding: 10px; background: white; border-radius: 8px; flex: 1; margin: 0 5px;'>
                    <div style='font-weight: bold; font-size: 1.2em;'>Boletín #{bulletin2}</div>
                    <div style='color: #666;'>{fecha2.strftime('%d/%m/%Y')}</div>
                    <div style='color: #888; font-size: 0.9em;'>{fecha2.strftime('%A').capitalize()}</div>
                </div>
            </div>
            <div style='margin-top: 10px; font-size: 0.9em; color: #666;'>
                <span style='display: inline-block; margin-right: 15px;'>📅 Diferencia: {abs((fecha1 - fecha2).days)} días</span>
                <span>📊 Total de reportes: {len(current_data)} vs {len(previous_data)}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Crear pestañas para diferentes tipos de reportes
        tab1, tab2, tab3, tab4 = st.tabs([
            "📈 Participación", 
            "🌍 Geográfico", 
            "🔧 Técnico", 
            "📊 Tendencias"
        ])
        
        # Convertir fechas a string en formato YYYY-MM-DD para las consultas
        current_date_str = fecha1.strftime('%Y-%m-%d')
        previous_date_str = fecha2.strftime('%Y-%m-%d')
        
        # Cerrar la conexión a la base de datos
        conn.close()
        
        # Mostrar pestañas con los diferentes reportes
        with tab1:
            show_participation_report(current_date_str, previous_date_str, bulletin1, bulletin2, fecha1, fecha2)
        
        with tab2:
            show_geographic_report(current_date_str, previous_date_str, bulletin1, bulletin2, fecha1, fecha2)
        
        with tab3:
            show_technical_report(current_date_str, previous_date_str, bulletin1, bulletin2, fecha1, fecha2)
        
        with tab4:
            show_trends_report(current_date_str, previous_date_str, bulletin1, bulletin2, fecha1, fecha2)
            
        conn.close()
            
    except Exception as e:
        st.error(f"❌ Error al generar reportes: {str(e)}")
        if 'conn' in locals():
            conn.close()

def show_participation_report(current_date, previous_date, bulletin1, bulletin2, fecha1, fecha2):
    """
    Muestra el reporte de participación comparativo entre dos boletines
    
    Args:
        current_date (str): Fecha del boletín actual en formato YYYY-MM-DD
        previous_date (str): Fecha del boletín anterior en formato YYYY-MM-DD
        bulletin1 (int): Número del boletín actual
        bulletin2 (int): Número del boletín anterior
        fecha1 (datetime.date): Fecha del boletín actual
        fecha2 (datetime.date): Fecha del boletín anterior
    """
    st.subheader("📈 Análisis de Participación")
    
    try:
        conn = sqlite3.connect(db.db_path)
        
        # Obtener datos de ambas sesiones
        current_data = pd.read_sql_query("""
            SELECT call_sign, operator_name, COUNT(*) as reports_count
            FROM reports 
            WHERE DATE(session_date) = ?
            GROUP BY call_sign, operator_name
        """, conn, params=[current_date])
        
        previous_data = pd.read_sql_query("""
            SELECT call_sign, operator_name, COUNT(*) as reports_count
            FROM reports 
            WHERE DATE(session_date) = ?
            GROUP BY call_sign, operator_name
        """, conn, params=[previous_date])
        
        conn.close()
        
        # Métricas principales
        col1, col2, col3 = st.columns(3)
        
        # Calcular total de reportes (no solo estaciones únicas)
        current_total_reports = current_data['reports_count'].sum() if not current_data.empty else 0
        previous_total_reports = previous_data['reports_count'].sum() if not previous_data.empty else 0
        
        # Contar estaciones únicas
        current_unique = len(current_data)
        previous_unique = len(previous_data)
        
        # Calcular tasa de crecimiento
        growth_rate = ((current_unique - previous_unique) / previous_unique * 100) if previous_unique > 0 else 0
        
        with col1:
            # Calcular diferencia en reportes
            reports_diff = current_total_reports - previous_total_reports
            reports_diff_str = f"+{reports_diff}" if reports_diff > 0 else str(reports_diff)
            
            # Mostrar métrica principal con el delta
            st.metric(f"📊 Boletín #{bulletin1} - {fecha1.strftime('%d/%m')}", 
                    f"{current_total_reports:,} reportes",
                    delta=f"{reports_diff_str} reportes vs boletín anterior",
                    delta_color="normal",
                    help=f"Total de reportes en el boletín actual ({fecha1.strftime('%d/%m/%Y')})")
            
            # Mostrar comparación de estaciones únicas
            #unique_diff = current_unique - previous_unique
            #unique_diff_str = f"+{unique_diff}" if unique_diff > 0 else str(unique_diff)
            #st.caption(f"""
            #    {current_unique:,} estaciones únicas  
            #    <span style='color: green; font-weight: bold;'>{unique_diff_str} vs boletín anterior</span>
            #""", unsafe_allow_html=True)
        
        with col2:
            st.metric(f"📊 Boletín #{bulletin2} - {fecha2.strftime('%d/%m')}", 
                     f"{previous_total_reports:,} reportes",
                     help=f"Total de reportes en el boletín anterior ({fecha2.strftime('%d/%m/%Y')})")
            st.caption(f"{previous_unique:,} estaciones únicas")
        
        with col3:
            st.metric("📈 Crecimiento de Estaciones", 
                     f"{current_unique:,} vs {previous_unique:,}",
                     delta=f"{current_unique - previous_unique:+d} ({growth_rate:+.1f}%)",
                     help=f"Comparación de estaciones únicas entre boletines")
            # Mostrar comparación de estaciones únicas
            unique_diff = current_unique - previous_unique
            unique_diff_str = f"+{unique_diff}" if unique_diff > 0 else str(unique_diff)
            st.caption(f"""
                {current_unique:,} estaciones únicas  
                <span style='color: green; font-weight: bold;'>{unique_diff_str} vs boletín anterior</span>
                """, unsafe_allow_html=True)
        
        # Análisis de estaciones
        current_stations = set(current_data['call_sign'])
        previous_stations = set(previous_data['call_sign'])
        new_stations = current_stations - previous_stations
        regular_stations = current_stations & previous_stations
        
        st.markdown("---")
        
        # Mostrar métricas principales
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("📊 Total Estaciones", f"{len(current_stations):,}", 
                     delta=f"{len(current_stations) - len(previous_stations):+d} vs anterior")
        
        with col2:
            st.metric("🆕 Nuevas Estaciones", len(new_stations), 
                     delta=f"{len(new_stations) - (len(current_stations) - len(previous_stations)):+.0f}")
        
        with col3:
            retention_rate = (len(regular_stations) / len(previous_stations) * 100) if previous_stations else 0
            st.metric("🔄 Tasa de Retención", f"{retention_rate:.1f}%")
        
        # Crear dos columnas para las tablas
        col_tabla1, col_tabla2 = st.columns(2)
        
        with col_tabla1:
            st.markdown("### 🆕 Detalle de Nuevas Estaciones")
            if new_stations:
                # Crear DataFrame para la tabla
                new_stations_data = []
                for station in sorted(new_stations):
                    operator = current_data[current_data['call_sign'] == station]['operator_name'].iloc[0]
                    reports = current_data[current_data['call_sign'] == station]['reports_count'].iloc[0]
                    new_stations_data.append({
                        'Indicativo': station,
                        'Operador': operator,
                        'Reportes': reports
                    })
                
                # Mostrar tabla estilizada
                st.dataframe(
                    pd.DataFrame(new_stations_data),
                    column_config={
                        "Indicativo": "Indicativo",
                        "Operador": "Operador",
                        "Reportes": st.column_config.NumberColumn(
                            "Reportes",
                            help="Número de reportes en este boletín",
                            format="%d"
                        )
                    },
                    hide_index=True,
                    use_container_width=True,
                    height=min(300, 35 * len(new_stations_data) + 40)
                )
            else:
                st.info("🌟 ¡Excelente noticia! No hay estaciones nuevas en este boletín.")
        
        with col_tabla2:
            st.markdown("### 🔄 Estaciones que no Repitieron")
            missing_stations = previous_stations - current_stations
            missing_count = len(missing_stations)
            
            if missing_stations:
                # Crear DataFrame para la tabla
                missing_stations_data = []
                for station in sorted(missing_stations):
                    operator = previous_data[previous_data['call_sign'] == station]['operator_name'].iloc[0] if not previous_data[previous_data['call_sign'] == station].empty else 'N/A'
                    reports = previous_data[previous_data['call_sign'] == station]['reports_count'].iloc[0] if not previous_data[previous_data['call_sign'] == station].empty else 0
                    missing_stations_data.append({
                        'Indicativo': station,
                        'Operador': operator,
                        'Reportes': reports
                    })
                
                # Mostrar tabla estilizada
                st.dataframe(
                    pd.DataFrame(missing_stations_data),
                    column_config={
                        "Indicativo": "Indicativo",
                        "Operador": "Operador",
                        "Reportes": st.column_config.NumberColumn(
                            "Reportes en Anterior",
                            help="Número de reportes en el boletín anterior",
                            format="%d"
                        )
                    },
                    hide_index=True,
                    use_container_width=True,
                    height=min(300, 35 * len(missing_stations_data) + 40)
                )
            else:
                st.info("🌟 ¡Excelente! Todas las estaciones del boletín anterior reportaron en este boletín.")
        
        # Mostrar métricas de retención
        st.markdown("### 🔄 Métricas de Retención")
        retention_col1, retention_col2 = st.columns(2)
        
        with retention_col1:
            st.metric("Estaciones Regulares", len(regular_stations), 
                     delta=f"{len(regular_stations) - len(previous_stations):+d} vs total anterior")
        
        with retention_col2:
            missing_percentage = (missing_count / len(previous_stations) * 100) if previous_stations else 0
            st.metric("Estaciones que no repitieron", 
                     f"{missing_count:,}",
                     delta=f"{missing_percentage:.1f}% del total anterior" if previous_stations else None)
        
    except Exception as e:
        st.error(f"❌ Error en reporte de participación: {str(e)}")

def show_geographic_report(current_date, previous_date, bulletin1, bulletin2, fecha1, fecha2):
    """
    Muestra el reporte geográfico comparativo entre dos boletines
    
    Args:
        current_date (str): Fecha del boletín actual en formato YYYY-MM-DD
        previous_date (str): Fecha del boletín anterior en formato YYYY-MM-DD
        bulletin1 (int): Número del boletín actual
        bulletin2 (int): Número del boletín anterior
        fecha1 (datetime.date): Fecha del boletín actual
        fecha2 (datetime.date): Fecha del boletín anterior
    """
    st.subheader("🌍 Análisis Geográfico")
    
    try:
        conn = sqlite3.connect(db.db_path)
        
        # Datos por zona
        current_zones = pd.read_sql_query("""
            SELECT zona, COUNT(DISTINCT call_sign) as estaciones_unicas, COUNT(*) as total_reportes
            FROM reports 
            WHERE DATE(session_date) = ?
            GROUP BY zona
            ORDER BY total_reportes DESC
        """, conn, params=[current_date])
        
        previous_zones = pd.read_sql_query("""
            SELECT zona, COUNT(DISTINCT call_sign) as estaciones_unicas, COUNT(*) as total_reportes
            FROM reports 
            WHERE DATE(session_date) = ?
            GROUP BY zona
            ORDER BY total_reportes DESC
        """, conn, params=[previous_date])
        
        # Datos por estado
        current_states = pd.read_sql_query("""
            SELECT qth as estado, COUNT(DISTINCT call_sign) as estaciones_unicas, COUNT(*) as total_reportes
            FROM reports 
            WHERE DATE(session_date) = ?
            GROUP BY qth
            ORDER BY total_reportes DESC
            LIMIT 10
        """, conn, params=[current_date])
        
        # Obtener totales para mostrar en los títulos
        total_current_reports = current_zones['total_reportes'].sum() if not current_zones.empty else 0
        total_previous_reports = previous_zones['total_reportes'].sum() if not previous_zones.empty else 0
        
        conn.close()
        
        # Métricas principales
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric(f"📊 Boletín #{bulletin1} - {fecha1.strftime('%d/%m')}", 
                     f"{total_current_reports:,} reportes",
                     delta=f"{total_current_reports - total_previous_reports:+,} reportes")

        with col2:
            st.metric(f"📊 Boletín #{bulletin2} - {fecha2.strftime('%d/%m')}",
                     f"{total_previous_reports:,} reportes")
        #             delta=f"{total_current_reports - total_previous_reports:+,} reportes")
        
        st.markdown("---")
        
        # Gráfico de barras agrupadas para comparación entre boletines
        st.subheader("📊 Comparación de Sistemas entre Boletines")
        
        if not current_zones.empty or not previous_zones.empty:
            # Preparar datos para el gráfico combinado
            df_comparison = pd.concat([
                current_zones.assign(Boletín=f'#{bulletin1} - {fecha1.strftime("%d/%m")}'),
                previous_zones.assign(Boletín=f'#{bulletin2} - {fecha2.strftime("%d/%m")}')
            ])
            
            # Crear gráfico de barras agrupadas
            fig = px.bar(
                df_comparison,
                x='zona',
                y='total_reportes',
                color='Boletín',
                barmode='group',
                title=f'Comparación de Reportes por Zona',
                labels={
                    'zona': 'Zona',
                    'total_reportes': 'Total de Reportes',
                    'Boletín': 'Boletín'
                },
                hover_data=['estaciones_unicas'],
                text='total_reportes',
                color_discrete_sequence=px.colors.qualitative.Plotly
            )
            
            # Mejorar el diseño del gráfico
            fig.update_traces(
                textposition='outside',
                hovertemplate='<b>%{x}</b><br>' +
                            'Boletín: %{customdata[1]}<br>' +
                            'Reportes: %{y}<br>' +
                            'Estaciones Únicas: %{customdata[0]}<br>' +
                            '<extra></extra>'
            )
            
            fig.update_layout(
                xaxis_tickangle=-45,
                yaxis_title='Número de Reportes',
                legend_title='Boletín',
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                margin=dict(t=60, b=100, l=50, r=50),
                height=500
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No hay datos suficientes para mostrar la comparación")
        
        st.markdown("---")
        
        # Tablas de zonas
        st.subheader("📊 Detalle por Zona")
        col1, col2 = st.columns(2)
        
        with col1:
            # Métrica para el boletín actual
            total_current = current_zones['total_reportes'].sum() if not current_zones.empty else 0
            st.metric(
                f"📊 Boletín #{bulletin1} - {fecha1.strftime('%d/%m')}",
                f"{total_current:,} reportes",
                help=f"Total de reportes: {total_current:,}"
            )
            if not current_zones.empty:
                st.dataframe(current_zones, width='stretch')
            else:
                st.info(f"No hay datos de zonas para el boletín #{bulletin1}")
        
        with col2:
            # Métrica para el boletín anterior
            total_previous = previous_zones['total_reportes'].sum() if not previous_zones.empty else 0
            delta = (total_current - total_previous) if (not current_zones.empty and not previous_zones.empty) else None
            
            st.metric(
                f"📊 Boletín #{bulletin2} - {fecha2.strftime('%d/%m')}",
                f"{total_previous:,} reportes",
                #delta=f"{delta:+,} reportes" if delta is not None else None,
                help=f"Total de reportes: {total_previous:,}"
            )
            if not previous_zones.empty:
                st.dataframe(previous_zones, width='stretch')
            else:
                st.info(f"No hay datos de zonas para el boletín #{bulletin2}")
        
        st.markdown("---")
        
        st.subheader(f"🏛️ Top 10 Estados - Boletín #{bulletin1}")
        if not current_states.empty:
            st.dataframe(current_states, width='stretch')
        else:
            st.info("No hay datos de estados disponibles")
            
    except Exception as e:
        st.error(f"❌ Error en reporte geográfico: {str(e)}")

def show_technical_report(current_date, previous_date, bulletin1, bulletin2, fecha1, fecha2):
    """
    Muestra el reporte técnico comparativo entre dos boletines con visualizaciones mejoradas
    
    Args:
        current_date (str): Fecha del boletín actual en formato YYYY-MM-DD
        previous_date (str): Fecha del boletín anterior en formato YYYY-MM-DD
        bulletin1 (int): Número del boletín actual
        bulletin2 (int): Número del boletín anterior
        fecha1 (datetime.date): Fecha del boletín actual
        fecha2 (datetime.date): Fecha del boletín anterior
    """
    st.subheader("🔧 Análisis Técnico")
    
    try:
        conn = sqlite3.connect(db.db_path)
        
        # Sistemas utilizados - Datos actuales
        current_systems = pd.read_sql_query("""
            SELECT 
                COALESCE(sistema, 'No especificado') as sistema, 
                COUNT(DISTINCT call_sign) as estaciones_unicas, 
                COUNT(*) as total_reportes,
                ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM reports WHERE DATE(session_date) = ?), 1) as porcentaje
            FROM reports 
            WHERE DATE(session_date) = ?
            GROUP BY sistema
            ORDER BY total_reportes DESC
        """, conn, params=[current_date, current_date])
        
        # Sistemas utilizados - Datos anteriores
        previous_systems = pd.read_sql_query("""
            SELECT 
                COALESCE(sistema, 'No especificado') as sistema, 
                COUNT(DISTINCT call_sign) as estaciones_unicas, 
                COUNT(*) as total_reportes,
                ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM reports WHERE DATE(session_date) = ?), 1) as porcentaje
            FROM reports 
            WHERE DATE(session_date) = ?
            GROUP BY sistema
            ORDER BY total_reportes DESC
        """, conn, params=[previous_date, previous_date])
        
        # Calidad de señales - Datos actuales
        current_signals = pd.read_sql_query("""
            SELECT 
                COALESCE(signal_report, 'No especificado') as reporte_señal, 
                COUNT(*) as total,
                ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM reports WHERE DATE(session_date) = ?), 1) as porcentaje
            FROM reports 
            WHERE DATE(session_date) = ?
            GROUP BY signal_report
            ORDER BY total DESC
        """, conn, params=[current_date, current_date])
        
        # Obtener totales para mostrar en los títulos
        total_current_reports = current_systems['total_reportes'].sum() if not current_systems.empty else 0
        total_previous_reports = previous_systems['total_reportes'].sum() if not previous_systems.empty else 0
        
        conn.close()
        
        # Métricas principales
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric(f"📡 Boletín #{bulletin1} - {fecha1.strftime('%d/%m')}", 
                     f"{total_current_reports:,} reportes",
                     delta=f"{total_current_reports - total_previous_reports:+,} reportes")
        
        with col2:
            st.metric(f"📡 Boletín #{bulletin2} - {fecha2.strftime('%d/%m')}",
                     f"{total_previous_reports:,} reportes")
        #             delta=f"{total_current_reports - total_previous_reports:+,} reportes")
        
        st.markdown("---")
        
        # Sección de Sistemas
        st.subheader("📡 Distribución de Sistemas")
        
        if not current_systems.empty or not previous_systems.empty:
            # Preparar datos para el gráfico comparativo
            if not current_systems.empty:
                current_systems['boletin'] = f'Boletín #{bulletin1}'
            if not previous_systems.empty:
                previous_systems['boletin'] = f'Boletín #{bulletin2}'
            
            # Combinar datos para el gráfico
            combined_systems = pd.concat([current_systems, previous_systems])
            
            # Crear gráfico de barras agrupadas
            fig_sistemas = px.bar(
                combined_systems,
                x='sistema',
                y='porcentaje',
                color='boletin',
                barmode='group',
                title=f'Comparación de Sistemas - Boletín #{bulletin1} vs #{bulletin2}',
                labels={'sistema': 'Sistema', 'porcentaje': 'Porcentaje (%)', 'boletin': 'Boletín'},
                text='porcentaje',
                color_discrete_sequence=px.colors.qualitative.Plotly
            )
            
            # Mejorar formato del gráfico
            fig_sistemas.update_traces(
                texttemplate='%{text:.1f}%',
                textposition='outside',
                marker_line_color='rgba(0,0,0,0.5)',
                marker_line_width=0.5
            )
            
            fig_sistemas.update_layout(
                xaxis_tickangle=-45,
                yaxis_title='Porcentaje de Reportes (%)',
                legend_title='Boletín',
                height=500
            )
            
            st.plotly_chart(fig_sistemas, use_container_width=True)
        
        # Mostrar tablas de sistemas
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader(f"📋 Detalle - Boletín #{bulletin1}")
            if not current_systems.empty:
                st.dataframe(
                    current_systems[['sistema', 'estaciones_unicas', 'total_reportes', 'porcentaje']]
                    .rename(columns={
                        'sistema': 'Sistema',
                        'estaciones_unicas': 'Estaciones Únicas',
                        'total_reportes': 'Total Reportes',
                        'porcentaje': '% del Total'
                    }),
                    width='stretch',
                    hide_index=True
                )
            else:
                st.info(f"No hay datos de sistemas para el boletín #{bulletin1}")
        
        with col2:
            st.subheader(f"📋 Detalle - Boletín #{bulletin2}")
            if not previous_systems.empty:
                st.dataframe(
                    previous_systems[['sistema', 'estaciones_unicas', 'total_reportes', 'porcentaje']]
                    .rename(columns={
                        'sistema': 'Sistema',
                        'estaciones_unicas': 'Estaciones Únicas',
                        'total_reportes': 'Total Reportes',
                        'porcentaje': '% del Total'
                    }),
                    width='stretch',
                    hide_index=True
                )
            else:
                st.info(f"No hay datos de sistemas para el boletín #{bulletin2}")
        
        st.markdown("---")
        
        # Sección de Calidad de Señales
        st.subheader(f"📶 Calidad de Señales - Boletín #{bulletin1}")
        
        if not current_signals.empty:
            # Crear gráfico de dona para la calidad de señales
            fig_señales = px.pie(
                current_signals,
                values='total',
                names='reporte_señal',
                hole=0.4,
                title=f'Distribución de Calidad de Señales - Boletín #{bulletin1}',
                labels={'reporte_señal': 'Calidad de Señal', 'total': 'Cantidad'}
            )
            
            # Mejorar formato del gráfico
            fig_señales.update_traces(
                textposition='inside',
                textinfo='percent+label',
                marker=dict(line=dict(color='#FFFFFF', width=1))
            )
            
            fig_señales.update_layout(
                showlegend=False,
                height=500
            )
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.plotly_chart(fig_señales, use_container_width=True)
            
            with col2:
                st.write("### Detalle de Calidad")
                st.dataframe(
                    current_signals.rename(columns={
                        'reporte_señal': 'Calidad',
                        'total': 'Cantidad',
                        'porcentaje': '% del Total'
                    }),
                    width='stretch',
                    hide_index=True
                )
        else:
            st.info("No hay datos de calidad de señales disponibles")
        
        # Agregar análisis de tendencia en la calidad de señales si hay datos históricos
        try:
            conn = sqlite3.connect(db.db_path)
            
            # Obtener datos históricos de calidad de señales
            historical_signals = pd.read_sql_query("""
                SELECT 
                    DATE(session_date) as fecha,
                    signal_report as calidad,
                    COUNT(*) as total
                FROM reports 
                WHERE DATE(session_date) BETWEEN date(?, '-30 days') AND ?
                GROUP BY DATE(session_date), signal_report
                ORDER BY DATE(session_date)
            """, conn, params=[current_date, current_date])
            
            if not historical_signals.empty:
                st.markdown("---")
                st.subheader("📈 Tendencia de Calidad de Señales (Últimos 30 días)")
                
                # Crear gráfico de líneas para la tendencia
                fig_tendencia = px.line(
                    historical_signals,
                    x='fecha',
                    y='total',
                    color='calidad',
                    title='Evolución de la Calidad de Señales',
                    labels={'fecha': 'Fecha', 'total': 'Número de Reportes', 'calidad': 'Calidad'},
                    markers=True
                )
                
                fig_tendencia.update_layout(
                    xaxis_title='Fecha',
                    yaxis_title='Número de Reportes',
                    legend_title='Calidad de Señal',
                    hovermode='x unified'
                )
                
                st.plotly_chart(fig_tendencia, use_container_width=True)
                
        except Exception as e:
            st.warning(f"No se pudo cargar el análisis de tendencia: {str(e)}")
        finally:
            if 'conn' in locals():
                conn.close()
            
    except Exception as e:
        st.error(f"❌ Error en reporte técnico: {str(e)}")
        if 'conn' in locals():
            conn.close()

def show_trends_report(current_date, previous_date, bulletin1, bulletin2, fecha1, fecha2):
    """
    Muestra el reporte de tendencias comparativo entre dos boletines con visualizaciones avanzadas
    
    Args:
        current_date (str): Fecha del boletín actual en formato YYYY-MM-DD
        previous_date (str): Fecha del boletín anterior en formato YYYY-MM-DD
        bulletin1 (int): Número del boletín actual
        bulletin2 (int): Número del boletín anterior
        fecha1 (datetime.date): Fecha del boletín actual
        fecha2 (datetime.date): Fecha del boletín anterior
    """
    st.subheader("📊 Análisis de Tendencias")
    
    try:
        conn = sqlite3.connect(db.db_path)
        
        # ===== 1. OBTENER DATOS HISTÓRICOS =====
        # Primero, obtener la lista de sistemas únicos en los datos
        sistemas_unicos = pd.read_sql_query(
            "SELECT DISTINCT sistema FROM reports WHERE sistema IS NOT NULL AND sistema != ''", 
            conn
        )['sistema'].tolist()
        
        # Si no hay sistemas, usar una lista por defecto
        if not sistemas_unicos:
            sistemas_unicos = ['FM', 'DMR', 'YSF', 'HF', 'ASL']
        
        # Crear la parte dinámica de la consulta para contar por sistema
        subconsultas_sistemas = []
        for sistema in sistemas_unicos:
            subconsultas_sistemas.append(
                f"(SELECT COUNT(*) FROM reports r2 WHERE DATE(r2.session_date) = DATE(r.session_date) AND r2.sistema = '{sistema}') as reportes_{sistema.lower()}"
            )
        
        subconsultas_sql = ',\n                    '.join(subconsultas_sistemas)
        
        # Crear subconsultas para contar por zona
        zonas = ['XE1', 'XE2', 'XE3', 'Extranjera']
        subconsultas_zonas = []
        for zona in zonas:
            subconsultas_zonas.append(
                f"SUM(CASE WHEN r.zona = '{zona}' THEN 1 ELSE 0 END) as reportes_{zona.lower()}"
            )
        
        subconsultas_zonas_sql = ',\n                '.join(subconsultas_zonas)
        
        # Consulta principal con sistemas y zonas dinámicas
        query = f"""
            WITH fechas_boletines AS (
                SELECT DISTINCT DATE(session_date) as fecha
                FROM reports
                WHERE DATE(session_date) <= ?
                ORDER BY DATE(session_date) DESC
                LIMIT 12
            )
            SELECT 
                DATE(r.session_date) as fecha,
                COUNT(DISTINCT r.call_sign) as estaciones_unicas,
                COUNT(*) as total_reportes,
                COUNT(DISTINCT r.zona) as zonas_unicas,
                COUNT(DISTINCT r.qth) as estados_unicos,
                ROUND(AVG(CASE WHEN r.signal_report = 3 THEN 1 ELSE 0 END) * 100, 1) as porcentaje_buenas_señales,
                {subconsultas_sql},
                {subconsultas_zonas_sql}
            FROM reports r
            WHERE DATE(r.session_date) IN (SELECT fecha FROM fechas_boletines)
            GROUP BY DATE(r.session_date)
            ORDER BY DATE(r.session_date)
        """
        
        # Ejecutar la consulta
        historical_data = pd.read_sql_query(query, conn, params=[current_date])
        
        # Obtener datos del boletín actual y anterior para comparación
        current_data = pd.read_sql_query("""
            SELECT 
                call_sign as 'Indicativo', 
                operator_name as 'Operador',
                zona as 'Zona',
                qth as 'Estado',
                sistema as 'Sistema',
                signal_report as 'Señal',
                strftime('%H:00', timestamp) as 'Hora'
            FROM reports 
            WHERE DATE(session_date) = ?
        """, conn, params=[current_date])
        
        previous_data = pd.read_sql_query("""
            SELECT 
                call_sign as 'Indicativo', 
                operator_name as 'Operador',
                zona as 'Zona',
                qth as 'Estado',
                sistema as 'Sistema',
                signal_report as 'Señal',
                strftime('%H:00', timestamp) as 'Hora'
            FROM reports 
            WHERE DATE(session_date) = ?
        """, conn, params=[previous_date])
        
        # Cerrar conexión a la base de datos
        conn.close()
        
        # ===== 2. CALCULAR MÉTRICAS PRINCIPALES =====
        # Calcular totales
        total_current_reports = len(current_data) if not current_data.empty else 0
        total_previous_reports = len(previous_data) if not previous_data.empty else 0
        
        # Calcular crecimiento
        if total_previous_reports > 0:
            crecimiento = ((total_current_reports - total_previous_reports) / total_previous_reports) * 100
        else:
            crecimiento = 0
        
        # ===== 3. MOSTRAR MÉTRICAS PRINCIPALES =====
        st.subheader("📈 Indicadores Clave")
        
        # Primera fila de métricas
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                f"📊 Total Reportes - B#{bulletin1}",
                f"{total_current_reports:,}",
                delta=f"{total_current_reports - total_previous_reports:+,} vs B#{bulletin2}"
            )
        
        with col2:
            st.metric(
                f"👥 Estaciones Únicas - B#{bulletin1}",
                f"{current_data['Indicativo'].nunique() if not current_data.empty else 0:,}",
                delta=f"{current_data['Indicativo'].nunique() - previous_data['Indicativo'].nunique():+,} vs B#{bulletin2}"
            )
        
        with col3:
            st.metric(
                f"🌍 Estados - B#{bulletin1}",
                f"{current_data['Estado'].nunique() if not current_data.empty else 0:,}",
                delta=f"{current_data['Estado'].nunique() - previous_data['Estado'].nunique():+,} vs B#{bulletin2}"
            )
        
        with col4:
            # Calcular la mejor participación histórica
            if not historical_data.empty:
                mejor_participacion = historical_data.loc[historical_data['total_reportes'].idxmax()]
                st.metric(
                    "🏆 Mejor Participación",
                    f"Boletín {mejor_participacion['fecha']}",
                    delta=f"{mejor_participacion['total_reportes']:,} reportes"
                )
            else:
                st.metric("🏆 Mejor Participación", "Sin datos históricos")
        
        st.markdown("---")
        
        # ===== 4. GRÁFICOS DE EVOLUCIÓN =====
        if not historical_data.empty:
            # 4.1 Evolución de Participación
            st.subheader("📈 Evolución de la Participación (Últimos 12 Boletines)")
            
            # Crear figura manualmente para más control
            fig_tendencia = go.Figure()
            
            # Añadir línea de total de reportes
            fig_tendencia.add_trace(
                go.Scatter(
                    x=historical_data['fecha'],
                    y=historical_data['total_reportes'],
                    name='Total Reportes',
                    mode='lines+markers+text',
                    text=historical_data['total_reportes'].astype(str),
                    textposition='top center',
                    textfont=dict(size=10),
                    line=dict(width=2.5, color=px.colors.qualitative.Plotly[0]),
                    marker=dict(size=8, color=px.colors.qualitative.Plotly[0]),
                    hovertemplate='<b>Total Reportes</b><br>%{y} reportes<br>%{x|%d/%m/%Y}<extra></extra>',
                    showlegend=True
                )
            )
            
            # Añadir línea de estaciones únicas
            fig_tendencia.add_trace(
                go.Scatter(
                    x=historical_data['fecha'],
                    y=historical_data['estaciones_unicas'],
                    name='Estaciones Únicas',
                    mode='lines+markers+text',
                    text=historical_data['estaciones_unicas'].astype(str),
                    textposition='top center',
                    textfont=dict(size=10),
                    line=dict(width=2.5, color=px.colors.qualitative.Plotly[1]),
                    marker=dict(size=8, color=px.colors.qualitative.Plotly[1]),
                    hovertemplate='<b>Estaciones Únicas</b><br>%{y} estaciones<br>%{x|%d/%m/%Y}<extra></extra>',
                    showlegend=True
                )
            )
            
            # Mejorar formato del gráfico
            fig_tendencia.update_layout(
                title='Evolución de la Participación',
                xaxis_title='Fecha del Boletín',
                yaxis_title='Cantidad',
                legend_title='Métricas',
                hovermode='x unified',
                height=550,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                    bgcolor='rgba(255, 255, 255, 0.8)'
                ),
                margin=dict(l=50, r=50, t=80, b=80)
            )
            
            # Añadir etiquetas al final de cada línea
            for trace in fig_tendencia.data:
                if len(trace.x) > 0:  # Asegurarse de que hay datos
                    last_x = trace.x[-1]
                    last_y = trace.y[-1]
                    
                    fig_tendencia.add_annotation(
                        x=last_x,
                        y=last_y,
                        text=f"{trace.name}: {last_y}",
                        showarrow=False,
                        xshift=15,
                        yshift=5,
                        font=dict(
                            size=11,
                            color=trace.line.color,
                            family='Arial, bold'
                        ),
                        align='left',
                        bgcolor='rgba(255, 255, 255, 0.8)',
                        borderpad=3,
                        bordercolor=trace.line.color,
                        borderwidth=1
                    )
            
            # Calcular y añadir tendencia para total de reportes
            if len(historical_data) > 1:
                x = range(len(historical_data))
                y = historical_data['total_reportes'].values
                z = np.polyfit(x, y, 1)
                p = np.poly1d(z)
                
                fig_tendencia.add_trace(
                    go.Scatter(
                        x=historical_data['fecha'],
                        y=p(x),
                        name='Tendencia Reportes',
                        mode='lines',
                        line=dict(
                            color=px.colors.qualitative.Plotly[0],
                            width=2,
                            dash='dot'
                        ),
                        showlegend=True,
                        hoverinfo='skip'
                    )
                )
            
            st.plotly_chart(fig_tendencia, use_container_width=True)
            
            # 4.2 Evolución de Sistemas
            st.subheader("📡 Evolución de Sistemas (Últimos 12 Boletines)")
            
            # Obtener las columnas de sistemas dinámicamente
            system_columns = [f'reportes_{sistema.lower()}' for sistema in sistemas_unicos]
            
            # Asegurarse de que todas las columnas de sistemas existan en el DataFrame
            for col in system_columns:
                if col not in historical_data.columns:
                    historical_data[col] = 0
            
            # Crear un mapa de colores para los sistemas
            colors = px.colors.qualitative.Plotly
            color_map = {col: colors[i % len(colors)] for i, col in enumerate(system_columns)}
            
            # Crear figura manualmente para más control
            fig_sistemas_evol = go.Figure()
            
            # Añadir una línea para cada sistema
            for i, col in enumerate(system_columns):
                sistema_nombre = col.replace('reportes_', '').upper()
                
                fig_sistemas_evol.add_trace(
                    go.Scatter(
                        x=historical_data['fecha'],
                        y=historical_data[col],
                        name=sistema_nombre,
                        mode='lines+markers+text',
                        text=historical_data[col].astype(str),
                        textposition='top center',
                        textfont=dict(size=9),
                        line=dict(width=2.5, color=colors[i % len(colors)]),
                        marker=dict(size=8, color=colors[i % len(colors)]),
                        hovertemplate=f'<b>{sistema_nombre}</b><br>%{{y}} reportes<br>%{{x|%d/%m/%Y}}<extra></extra>',
                        showlegend=True
                    )
                )
                
                # Calcular y añadir tendencia para este sistema
                if len(historical_data) > 1 and historical_data[col].sum() > 0:
                    x = range(len(historical_data))
                    y = historical_data[col].values
                    z = np.polyfit(x, y, 1)
                    p = np.poly1d(z)
                    
                    fig_sistemas_evol.add_trace(
                        go.Scatter(
                            x=historical_data['fecha'],
                            y=p(x),
                            name=f'Tendencia {sistema_nombre}',
                            mode='lines',
                            line=dict(
                                color=colors[i % len(colors)],
                                width=1.5,
                                dash='dot'
                            ),
                            showlegend=False,
                            hoverinfo='skip'
                        )
                    )
            
            # Mejorar formato del gráfico
            fig_sistemas_evol.update_layout(
                title='Evolución de Sistemas por Tipo',
                xaxis_title='Fecha del Boletín',
                yaxis_title='Número de Reportes',
                legend_title='Sistema',
                hovermode='x unified',
                height=600,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                    bgcolor='rgba(255, 255, 255, 0.8)'
                ),
                margin=dict(l=50, r=50, t=80, b=80)
            )
            
            # Añadir etiquetas al final de cada línea
            for trace in fig_sistemas_evol.data:
                if 'Tendencia' not in trace.name and len(trace.x) > 0:  # Solo para líneas principales, no tendencias
                    last_x = trace.x[-1]
                    last_y = trace.y[-1]
                    
                    # Solo mostrar etiqueta si hay un valor
                    if last_y > 0:
                        fig_sistemas_evol.add_annotation(
                            x=last_x,
                            y=last_y,
                            text=f"{trace.name}: {int(last_y) if last_y == int(last_y) else last_y}",
                            showarrow=False,
                            xshift=15,
                            yshift=5,
                            font=dict(
                                size=10,
                                color=trace.line.color,
                                family='Arial, bold'
                            ),
                            align='left',
                            bgcolor='rgba(255, 255, 255, 0.8)',
                            borderpad=2,
                            bordercolor=trace.line.color,
                            borderwidth=1
                        )
            
            st.plotly_chart(fig_sistemas_evol, use_container_width=True)
            
            # 4.3 Evolución de Cobertura Geográfica por Zona
            st.subheader("🌍 Evolución de la Participación por Zona (Últimos 12 Boletines)")
            
            try:
                # Obtener los datos de zonas directamente de la base de datos
                conn = sqlite3.connect('fmre_reports.db')
                
                # Primero, obtener las zonas únicas
                zonas_query = """
                SELECT DISTINCT zona 
                FROM reports 
                WHERE zona IS NOT NULL 
                ORDER BY zona
                """
                zonas_unicas = pd.read_sql_query(zonas_query, conn)['zona'].tolist()
                
                if not zonas_unicas:
                    st.warning("No se encontraron datos de zonas en la base de datos.")
                    conn.close()
                    return
                
                # Crear subconsultas para contar por zona
                subconsultas = []
                for zona in zonas_unicas:
                    subconsultas.append(
                        f"SUM(CASE WHEN zona = '{zona}' THEN 1 ELSE 0 END) as reportes_{zona.lower()}"
                    )
                
                subconsultas_sql = ',\n                '.join(subconsultas)
                
                # Consulta principal para obtener la evolución por zona
                query = f"""
                WITH fechas_boletines AS (
                    SELECT DISTINCT DATE(session_date) as fecha
                    FROM reports
                    WHERE DATE(session_date) >= date('now', '-12 months')
                    ORDER BY DATE(session_date) DESC
                    LIMIT 12
                )
                SELECT 
                    DATE(r.session_date) as fecha,
                    {subconsultas_sql}
                FROM reports r
                WHERE DATE(r.session_date) IN (SELECT fecha FROM fechas_boletines)
                GROUP BY DATE(r.session_date)
                ORDER BY DATE(r.session_date)
                """
                
                # Ejecutar la consulta
                zonas_data = pd.read_sql_query(query, conn)
                conn.close()

                if not zonas_data.empty:
                    # Obtener las columnas de zonas (excluyendo 'fecha')
                    zona_columns = [col for col in zonas_data.columns if col != 'fecha']
                    
                    # Crear un mapa de colores para las zonas
                    colors = px.colors.qualitative.Plotly
                    color_map = {col: colors[i % len(colors)] for i, col in enumerate(zona_columns)}
                    
                    # Crear el gráfico de líneas para la evolución de zonas
                    fig_zonas_evol = go.Figure()
                    
                    # Añadir cada zona como una traza separada
                    for col in zona_columns:
                        zone_name = col.replace('reportes_', '').upper()
                        fig_zonas_evol.add_trace(
                            go.Scatter(
                                x=zonas_data['fecha'],
                                y=zonas_data[col],
                                name=zone_name,
                                mode='lines+markers+text',
                                text=zonas_data[col].astype(str),
                                textposition='top center',
                                textfont=dict(size=10),
                                line=dict(width=2.5),
                                marker=dict(size=8),
                                hovertemplate='<b>' + zone_name + '</b><br>%{y} reportes<br>%{x|%d/%m/%Y}<extra></extra>'
                            )
                        )
                    
                    # Configurar el diseño del gráfico
                    fig_zonas_evol.update_layout(
                        title='Evolución de la Participación por Zona',
                        xaxis_title='Fecha del Boletín',
                        yaxis_title='Número de Reportes',
                        legend_title='Zona',
                        hovermode='x unified',
                        height=600,  # Aumentar altura para mejor visualización
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="right",
                            x=1,
                            title_font=dict(size=12),
                            font=dict(size=10)
                        ),
                        margin=dict(l=50, r=50, t=80, b=80)  # Ajustar márgenes
                    )
                    
                    
                    # Renombrar las etiquetas de la leyenda y añadir anotaciones
                    for trace in fig_zonas_evol.data:
                        # Obtener el nombre de la zona (sin el prefijo 'reportes_')
                        zone_name = trace.name.replace('reportes_', '').upper()
                        trace.name = zone_name
                        
                        # Añadir etiquetas al final de cada línea
                        if len(trace.x) > 0:  # Asegurarse de que hay datos
                            last_x = trace.x[-1]
                            last_y = trace.y[-1]
                            
                            # Solo mostrar la etiqueta si hay un valor
                            if last_y > 0:
                                fig_zonas_evol.add_annotation(
                                    x=last_x,
                                    y=last_y,
                                    text=zone_name,
                                    showarrow=False,
                                    xshift=10,  # Desplazar un poco a la derecha
                                    font=dict(
                                        size=11,
                                        color=trace.line.color
                                    ),
                                    yshift=5
                                )
                    
                    st.plotly_chart(fig_zonas_evol, use_container_width=True)
                    
                    # Agregar tabla resumen debajo del gráfico
                    st.subheader("📊 Resumen de Participación por Zona")
                    
                    # Calcular totales por zona
                    resumen = zonas_data[zona_columns].sum().reset_index()
                    resumen.columns = ['Zona', 'Total Reportes']
                    resumen['Zona'] = resumen['Zona'].str.replace('reportes_', '').str.upper()
                    resumen = resumen.sort_values('Total Reportes', ascending=False)
                    
                    # Mostrar métricas principales
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.metric("🌍 Zonas Activas", len(zona_columns))
                    
                    with col2:
                        total_reportes = resumen['Total Reportes'].sum()
                        st.metric("📊 Total de Reportes", total_reportes)
                    
                    # Mostrar tabla con los totales
                    st.dataframe(
                        resumen,
                        column_config={
                            'Zona': 'Zona',
                            'Total Reportes': st.column_config.NumberColumn(
                                'Total Reportes',
                                help='Número total de reportes en los últimos 12 boletines',
                                format='%d'
                            )
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                else:
                    st.warning("No se encontraron datos de zonas para mostrar.")
                    return

            except Exception as e:
                st.error(f"Error al cargar los datos de zonas: {str(e)}")
                if 'conn' in locals():
                    conn.close()
                return
                
        # Sección de resumen eliminada según solicitud del usuario
    except Exception as e:
        st.error(f"❌ Error en reporte de tendencias: {str(e)}")
        if 'conn' in locals():
            conn.close()

# ==================== NAVEGACIÓN PRINCIPAL ====================

# Página: Registro de Reportes
if page == "🏠 Registro de Reportes":
    registro_reportes()

# Página: Dashboard
elif page == "📊 Dashboard":
    st.header("Dashboard de Estadísticas")
    
    # Obtener estadísticas
    stats = db.get_statistics(session_date.strftime('%Y-%m-%d'))

    # Métricas principales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Total Participantes",
            stats['total_participants'],
            help="Número de indicativos únicos"
        )
    
    with col2:
        st.metric(
            "Total Reportes",
            stats['total_reports'],
            help="Número total de reportes registrados"
        )
    
    with col3:
        avg_per_participant = stats['total_reports'] / max(stats['total_participants'], 1)
        st.metric(
            "Promedio por Participante",
            f"{avg_per_participant:.1f}",
            help="Reportes promedio por participante"
        )
    
    with col4:
        if not stats['signal_quality'].empty:
            good_signals = stats['signal_quality'][stats['signal_quality']['signal_quality'] == 3]['count'].sum()
            total_signals = stats['signal_quality']['count'].sum()
            good_percentage = (good_signals / max(total_signals, 1)) * 100
            st.metric(
                "% Señales Buenas",
                f"{good_percentage:.1f}%",
                help="Porcentaje de señales reportadas como buenas"
            )
        else:
            st.metric("% Señales Buenas", "0%")
    
    # Gráficas - Primera fila
    col1, col2 = st.columns(2)
    
    with col1:
        # Participantes por zona
        if not stats['by_zona'].empty:
            st.subheader("Participantes por Zona")
            
            fig_zona = px.bar(
                stats['by_zona'],
                x='zona',
                y='count',
                title="Distribución por Zonas",
                labels={'zona': 'Zona', 'count': 'Participantes'},
                color='count',
                color_continuous_scale='Blues'
            )
            fig_zona.update_layout(showlegend=False)
            st.plotly_chart(fig_zona, width='stretch')
        else:
            st.info("No hay datos de zonas disponibles")
    
    with col2:
        # Participantes por sistema
        if not stats['by_sistema'].empty:
            st.subheader("Participantes por Sistema")
            
            fig_sistema = px.pie(
                stats['by_sistema'],
                values='count',
                names='sistema',
                title="Distribución por Sistemas"
            )
            st.plotly_chart(fig_sistema, width='stretch')
        else:
            st.info("No hay datos de sistemas disponibles")
    
    # Gráficas - Segunda fila
    col1, col2 = st.columns(2)
    
    with col1:
        # Participantes por región
        if not stats['by_region'].empty:
            st.subheader("Participantes por Región")
            
            fig_region = px.bar(
                stats['by_region'],
                x='region',
                y='count',
                title="Distribución por Estados",
                labels={'region': 'Estado', 'count': 'Participantes'}
            )
            fig_region.update_layout(showlegend=False)
            st.plotly_chart(fig_region, width='stretch')
        else:
            st.info("No hay datos de regiones disponibles")
    
    with col2:
        # Calidad de señal
        if not stats['signal_quality'].empty:
            st.subheader("Distribución de Calidad de Señal")
            
            quality_df = stats['signal_quality'].copy()
            quality_df['quality_text'] = quality_df['signal_quality'].map(get_signal_quality_text)
            
            fig_quality = px.pie(
                quality_df,
                values='count',
                names='quality_text',
                title="Calidad de Señales Reportadas"
            )
            st.plotly_chart(fig_quality, width='stretch')
        else:
            st.info("No hay datos de calidad de señal disponibles")
    
    # Estaciones más activas
    if not stats['most_active'].empty:
        st.subheader("Estaciones Más Activas")
        
        active_df = stats['most_active'].head(10)
        fig_active = px.bar(
            active_df,
            x='call_sign',
            y='reports_count',
            title="Top 10 Estaciones por Número de Reportes",
            labels={'call_sign': 'Indicativo', 'reports_count': 'Reportes'}
        )
        fig_active.update_layout(showlegend=False)
        st.plotly_chart(fig_active, width='stretch')
    
    # Actividad por hora
    if not stats['by_hour'].empty:
        st.subheader("Actividad por Hora")
        
        fig_hour = px.line(
            stats['by_hour'],
            x='hour',
            y='count',
            title="Reportes por Hora del Día",
            labels={'hour': 'Hora', 'count': 'Número de Reportes'}
        )
        fig_hour.update_traces(mode='lines+markers')
        st.plotly_chart(fig_hour, width='stretch')

# Página: Gestión de Reportes
elif page == "📋 Gestión de Reportes":
    st.header("Gestión de Reportes")
    
    # Búsqueda
    search_term = st.text_input(
        "🔍 Buscar reportes:",
        placeholder="Buscar por indicativo, nombre o QTH",
        help="Ingresa cualquier término para buscar en los reportes"
    )
    
    # Obtener reportes
    if search_term:
        reports_df = db.search_reports(search_term)
        st.subheader(f"Resultados de búsqueda: '{search_term}'")
    else:
        reports_df = db.get_all_reports(session_date)
        st.subheader(f"Todos los reportes - {session_date.strftime('%d/%m/%Y')}")
    
    if not reports_df.empty:
        # Mostrar reportes con opciones de edición
        for idx, report in reports_df.iterrows():
            with st.expander(f"{report['call_sign']} - {report['operator_name']} ({format_timestamp(report['timestamp'])})"):
                col1, col2, col3 = st.columns([2, 2, 1])
                
                with col1:
                    st.write(f"**Indicativo:** {report['call_sign']}")
                    st.write(f"**Operador:** {report['operator_name']}")
                    st.write(f"**QTH:** {report['qth']}")
                
                with col2:
                    st.write(f"**Señal:** {report['signal_report']}")
                    st.write(f"**Zona:** {report.get('zona', 'N/A')}")
                    st.write(f"**Sistema:** {report.get('sistema', 'N/A')}")
                    st.write(f"**Región:** {report.get('region', 'N/A')}")
                    if report.get('observations'):
                        st.write(f"**Observaciones:** {report['observations']}")
                
                with col3:
                    if st.button(f"🗑️ Eliminar", key=f"delete_{report['id']}"):
                        try:
                            db.delete_report(report['id'])
                            st.success("Reporte eliminado")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al eliminar reporte: {str(e)}")
    else:
        st.info("No se encontraron reportes.")

# Página: Historial de Estaciones
elif page == "📻 Historial de Estaciones":
    st.header("Historial de Estaciones")
    
    # Obtener historial
    station_history = db.get_station_history(100)
    
    if not station_history.empty:
        # Métricas del historial
        col1, col2, col3 = st.columns(3)
        
        with col1:
            total_stations = len(station_history)
            st.metric("Total de Estaciones", total_stations)
        
        with col2:
            most_used = station_history.iloc[0] if len(station_history) > 0 else None
            if most_used is not None:
                st.metric("Más Utilizada", most_used['call_sign'], f"{most_used['use_count']} usos")
        
        with col3:
            avg_uses = station_history['use_count'].mean()
            st.metric("Promedio de Usos", f"{avg_uses:.1f}")
        
        # Búsqueda en historial
        search_history = st.text_input(
            "🔍 Buscar en historial:",
            placeholder="Buscar por indicativo, operador o QTH"
        )
        
        # Filtrar historial si hay búsqueda
        if search_history:
            filtered_history = station_history[
                station_history['call_sign'].str.contains(search_history, case=False, na=False) |
                station_history['operator_name'].str.contains(search_history, case=False, na=False) |
                station_history['qth'].str.contains(search_history, case=False, na=False)
            ]
        else:
            filtered_history = station_history
        
        # Mostrar tabla de historial
        if not filtered_history.empty:
            st.subheader("Estaciones en el Historial")
            
            # Preparar datos para mostrar
            display_history = filtered_history.copy()
            display_history['last_used'] = pd.to_datetime(display_history['last_used']).dt.strftime('%d/%m/%Y %H:%M')
            display_history = display_history[['call_sign', 'operator_name', 'qth', 'zona', 'sistema', 'use_count', 'last_used']]
            display_history.columns = ['Indicativo', 'Operador', 'QTH', 'Zona', 'Sistema', 'Usos', 'Último Uso']
            
            st.dataframe(
                display_history,
                width='stretch',
                hide_index=True
            )
            
            # Gráfica de estaciones más utilizadas
            if len(filtered_history) > 0:
                st.subheader("Estaciones Más Utilizadas")
                
                top_stations = filtered_history.head(10)
                fig_stations = px.bar(
                    top_stations,
                    x='call_sign',
                    y='use_count',
                    title="Top 10 Estaciones por Número de Usos",
                    labels={'call_sign': 'Indicativo', 'use_count': 'Número de Usos'}
                )
                fig_stations.update_layout(showlegend=False)
                st.plotly_chart(fig_stations, width='stretch')
        else:
            st.info("No se encontraron estaciones en el historial con ese criterio de búsqueda.")
    else:
        st.info("No hay estaciones en el historial aún.")

# Página: Reportes Avanzados
elif page == "📈 Reportes Avanzados":
    show_advanced_reports()

# Página: Reportes Básicos/Exportar
elif page == "📋 Reportes Básicos/Exportar":
    st.header("📋 Reportes Básicos y Exportación")
    
    # Opciones de exportación
    col1, col2 = st.columns(2)
    
    with col1:
        export_date = st.date_input(
            "Fecha de sesión a exportar:",
            value=session_date
        )
        
        export_format = st.selectbox(
            "Formato de exportación:",
            ["CSV", "Excel", "PDF"]
        )
    
    with col2:
        include_stats = st.checkbox(
            "Incluir estadísticas",
            value=True,
            help="Incluir resumen estadístico en la exportación"
        )
        
        all_sessions = st.checkbox(
            "Exportar todas las sesiones",
            value=False,
            help="Exportar datos de todas las fechas"
        )
    
    if st.button("📥 Generar Exportación", width='stretch'):
        try:
            # Obtener datos
            if all_sessions:
                export_df = db.get_all_reports()
                stats = db.get_statistics() if include_stats else None
            else:
                export_df = db.get_all_reports(export_date)
                stats = db.get_statistics(export_date) if include_stats else None
            
            if export_df.empty:
                st.warning("No hay datos para exportar en el período seleccionado.")
            else:
                # Generar exportación según formato
                if export_format == "CSV":
                    data, filename = exporter.export_to_csv(export_df)
                    st.download_button(
                        label="📄 Descargar CSV",
                        data=data,
                        file_name=filename,
                        mime="text/csv"
                    )
                
                elif export_format == "Excel":
                    data, filename = exporter.export_to_excel(export_df)
                    st.download_button(
                        label="📊 Descargar Excel",
                        data=data,
                        file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                
                elif export_format == "PDF":
                    try:
                        data, filename = exporter.export_to_pdf(export_df, stats, session_date=export_date, current_user=current_user)
                        st.download_button(
                            label="📑 Descargar PDF",
                            data=data,
                            file_name=filename,
                            mime="application/pdf"
                        )
                    except Exception as e:
                        st.error(f"❌ Error al generar PDF: {str(e)}")
                        import traceback
                        st.code(traceback.format_exc())
                
                # Mostrar resumen
                st.success(f"✅ Exportación generada: {len(export_df)} reportes")
                
                if include_stats and stats:
                    summary = exporter.create_session_summary(stats, export_date)
                    
                    st.subheader("Resumen de la Exportación")
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Participantes", summary['total_participantes'])
                    with col2:
                        st.metric("Reportes", summary['total_reportes'])
                    with col3:
                        if summary['calidad_señal']:
                            buenas = summary['calidad_señal'].get('Buena', {}).get('porcentaje', 0)
                            st.metric("% Señales Buenas", f"{buenas}%")
        
        except Exception as e:
            st.error(f"❌ Error al generar exportación: {str(e)}")

# Página: Buscar/Editar
elif page == "🔍 Buscar/Editar":
    st.header("Buscar y Editar Reportes")
    
    # Búsqueda de reportes
    search_term = st.text_input(
        "🔍 Buscar reportes:",
        placeholder="Buscar por indicativo, operador, QTH, zona o sistema"
    )
    
    # Filtros adicionales
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_date = st.date_input(
            "Filtrar por fecha:",
            value=None,
            help="Dejar vacío para buscar en todas las fechas"
        )
    
    with col2:
        # Obtener zonas únicas de la base de datos
        available_zones = db.get_distinct_zones()
        search_zona = st.selectbox(
            "Filtrar por zona:",
            ["Todas"] + available_zones
        )
    
    with col3:
        # Obtener sistemas únicos de la base de datos
        available_systems = db.get_distinct_systems()
        search_sistema = st.selectbox(
            "Filtrar por sistema:",
            ["Todos"] + available_systems
        )
    
    # Obtener reportes filtrados
    if search_term or search_date or search_zona != "Todas" or search_sistema != "Todos":
        # Construir filtros
        filters = {}
        if search_date:
            filters['session_date'] = search_date.strftime('%Y-%m-%d')
        if search_zona != "Todas":
            filters['zona'] = search_zona
        if search_sistema != "Todos":
            filters['sistema'] = search_sistema
        
        # Buscar reportes
        reports_df = db.search_reports(search_term, filters)
        
        if not reports_df.empty:
            st.subheader(f"Resultados de búsqueda: '{search_term}'")
            
            # Agregar información de debug para el usuario
            st.info(f"🔍 **Debug Info:** Encontrados {len(reports_df)} reportes. Filtros aplicados: {filters}")
            
            # Configurar paginación
            items_per_page = st.selectbox("Reportes por página:", [10, 25, 50, 100], index=1)
            
            # Calcular páginas
            total_pages = (len(reports_df) - 1) // items_per_page + 1
            
            if total_pages > 1:
                page_num = st.selectbox(f"Página (de {total_pages}):", range(1, total_pages + 1))
                start_idx = (page_num - 1) * items_per_page
                end_idx = start_idx + items_per_page
                page_df = reports_df.iloc[start_idx:end_idx]
            else:
                page_df = reports_df
            
            # Mostrar reportes de la página actual
            for idx, report in page_df.iterrows():
                with st.expander(f"📻 {report['call_sign']} - {report['operator_name']} ({report['session_date']}) - ID: {report['id']}"):
                    # Verificar si está en modo edición
                    edit_key = f"edit_mode_{report['id']}"
                    is_editing = st.session_state.get(edit_key, False)
                    
                    if not is_editing:
                        # Modo visualización
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**Indicativo:** {report['call_sign']}")
                            st.write(f"**Operador:** {report['operator_name']}")
                            if 'estado' in report and report['estado']:
                                st.write(f"**Estado:** {report['estado']}")
                            if 'ciudad' in report and report['ciudad']:
                                st.write(f"**Ciudad:** {report['ciudad']}")
                            elif 'qth' in report and report['qth']:
                                st.write(f"**QTH:** {report['qth']}")
                            st.write(f"**Zona:** {report['zona']}")
                            st.write(f"**Sistema:** {report['sistema']}")
                        
                        with col2:
                            st.write(f"**Reporte de Señal:** {report['signal_report']}")
                            st.write(f"**Fecha:** {report['session_date']}")
                            st.write(f"**Timestamp:** {report['timestamp']}")
                            if report['observations']:
                                st.write(f"**Observaciones:** {report['observations']}")
                            if report.get('grid_locator'):
                                st.write(f"**Grid Locator:** {report['grid_locator']}")
                        
                        # Botones de acción
                        col_edit, col_delete = st.columns(2)
                        
                        with col_edit:
                            if st.button(f"✏️ Editar", key=f"edit_{report['id']}"):
                                st.session_state[edit_key] = True
                                st.rerun()
                        
                        with col_delete:
                            if st.button(f"🗑️ Eliminar", key=f"delete_{report['id']}"):
                                try:
                                    db.delete_report(report['id'])
                                    st.success("Reporte eliminado")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al eliminar reporte: {str(e)}")
                    
                    else:
                        # Modo edición
                        st.markdown("### ✏️ Editando Reporte")
                        
                        with st.form(f"edit_form_{report['id']}"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                edit_call_sign = st.text_input(
                                    "Indicativo:",
                                    value=report['call_sign'],
                                    help="Ejemplo: XE1ABC"
                                )
                                
                                edit_operator_name = st.text_input(
                                    "Nombre del Operador:",
                                    value=report['operator_name']
                                )
                                
                                # Obtener estados mexicanos
                                estados_list = get_estados_list()
                                current_qth = report.get('qth', '')
                                if current_qth in estados_list:
                                    qth_index = estados_list.index(current_qth)
                                else:
                                    qth_index = 0
                                
                                edit_qth = st.selectbox(
                                    "Estado/QTH:",
                                    estados_list,
                                    index=qth_index
                                )
                                
                                edit_ciudad = st.text_input(
                                    "Ciudad:",
                                    value=report.get('ciudad', '')
                                )
                                
                                # Obtener zonas disponibles
                                zonas_list = get_zonas()
                                current_zona = report.get('zona', '')
                                zona_index = zonas_list.index(current_zona) if current_zona in zonas_list else 0
                                edit_zona = st.selectbox(
                                    "Zona:",
                                    zonas_list,
                                    index=zona_index
                                )
                            
                            with col2:
                                # Obtener sistemas disponibles
                                sistemas_list = get_sistemas()
                                current_sistema = report.get('sistema', '')
                                sistema_index = sistemas_list.index(current_sistema) if current_sistema in sistemas_list else 0
                                edit_sistema = st.selectbox(
                                    "Sistema:",
                                    sistemas_list,
                                    index=sistema_index
                                )
                                
                                edit_signal_report = st.text_input(
                                    "Reporte de Señal:",
                                    value=report.get('signal_report', ''),
                                    help="Ejemplo: Buena, Regular, Mala"
                                )
                                
                                edit_grid_locator = st.text_input(
                                    "Grid Locator (opcional):",
                                    value=report.get('grid_locator', '') or '',
                                    help="Ejemplo: DL74QB"
                                )
                                
                                edit_observations = st.text_area(
                                    "Observaciones:",
                                    value=report.get('observations', '') or '',
                                    height=100
                                )
                            
                            col_save, col_cancel = st.columns(2)
                            
                            with col_save:
                                save_changes = st.form_submit_button("💾 Guardar Cambios")
                            
                            with col_cancel:
                                cancel_edit = st.form_submit_button("❌ Cancelar")
                            
                            if save_changes:
                                # Validar datos
                                is_valid, errors = validate_all_fields(edit_call_sign, edit_operator_name, edit_qth, edit_ciudad, edit_signal_report, edit_zona, edit_sistema)
                                
                                if is_valid:
                                    # Verificar inconsistencias
                                    needs_confirmation, warning_msg = detect_inconsistent_data(edit_call_sign, edit_qth, edit_zona)
                                    
                                    if needs_confirmation:
                                        # Guardar datos en session_state para confirmación de edición
                                        pending_edit_key = f"pending_edit_{report['id']}"
                                        st.session_state[pending_edit_key] = {
                                            'report_id': report['id'],
                                            'call_sign': edit_call_sign,
                                            'operator_name': edit_operator_name,
                                            'qth': edit_qth,
                                            'ciudad': edit_ciudad,
                                            'zona': edit_zona,
                                            'sistema': edit_sistema,
                                            'signal_report': edit_signal_report,
                                            'grid_locator': edit_grid_locator,
                                            'observations': edit_observations,
                                            'warning_msg': warning_msg,
                                            'edit_key': edit_key
                                        }
                                        del st.session_state[edit_key]
                                        st.rerun()
                                    else:
                                        # Actualizar directamente
                                        try:
                                            db.update_report(
                                                int(report['id']),
                                                call_sign=edit_call_sign.upper(),
                                                operator_name=edit_operator_name,
                                                qth=edit_qth,
                                                ciudad=edit_ciudad.title(),
                                                zona=edit_zona,
                                                sistema=edit_sistema,
                                                signal_report=edit_signal_report,
                                                grid_locator=edit_grid_locator.upper() if edit_grid_locator else None,
                                                observations=edit_observations
                                            )
                                            
                                            st.session_state.selected_reports = []
                                            # Solo eliminar pending_edit_key si existe
                                            if f"pending_edit_{report['id']}" in st.session_state:
                                                del st.session_state[f"pending_edit_{report['id']}"]
                                            st.success("✅ Reporte actualizado exitosamente")
                                            st.rerun()
                                            
                                        except Exception as e:
                                            st.error(f"❌ Error al actualizar reporte: {str(e)}")
                                else:
                                    for error in errors:
                                        st.error(f"❌ {error}")
                        
                        if cancel_edit:
                            del st.session_state[edit_key]
                            st.rerun()
                    
                    # Mostrar ventana emergente modal para confirmación de edición
                    pending_edit_key = f"pending_edit_{report['id']}"
                    if pending_edit_key in st.session_state:
                        @st.dialog("⚠️ Confirmación de Edición - Datos Inconsistentes")
                        def show_edit_confirmation_dialog():
                            pending_edit = st.session_state[pending_edit_key]
                            
                            st.markdown(pending_edit['warning_msg'])
                            
                            col_conf, col_canc = st.columns(2)
                            
                            with col_conf:
                                if st.button("✅ Continuar y Actualizar", key=f"confirm_edit_modal_{report['id']}", type="primary", width='stretch'):
                                    try:
                                        # Actualizar reporte
                                        db.update_report(
                                            pending_edit['report_id'],
                                            call_sign=pending_edit['call_sign'].upper(),
                                            operator_name=pending_edit['operator_name'],
                                            qth=pending_edit['qth'],
                                            ciudad=pending_edit['ciudad'].title(),
                                            zona=pending_edit['zona'],
                                            sistema=pending_edit['sistema'],
                                            signal_report=pending_edit['signal_report'],
                                            grid_locator=pending_edit['grid_locator'].upper() if pending_edit['grid_locator'] else None,
                                            observations=pending_edit['observations']
                                        )
                                        
                                        st.success("✅ Reporte actualizado exitosamente")
                                        st.session_state.selected_reports = []
                                        del st.session_state[pending_edit_key]
                                        st.rerun()
                                        
                                    except Exception as e:
                                        st.error(f"❌ Error al actualizar reporte: {str(e)}")
                            
                            with col_canc:
                                if st.button("❌ Revisar Datos", key=f"cancel_edit_modal_{report['id']}", width='stretch'):
                                    del st.session_state[pending_edit_key]
                                    st.rerun()
                        
                        show_edit_confirmation_dialog()
            
            # Mostrar resumen de la página actual
            if total_pages > 1:
                showing_start = start_idx + 1
                showing_end = min(end_idx, len(reports_df))
                st.caption(f"Mostrando reportes {showing_start}-{showing_end} de {len(reports_df)} total")
        else:
            st.info("No se encontraron reportes con los criterios de búsqueda especificados.")
    else:
        st.info("Ingresa un término de búsqueda o selecciona filtros para buscar reportes.")

# Página: Ranking y Reconocimientos
elif page == "🏆 Ranking":
    show_motivational_dashboard()

# Página: Mi Perfil
elif page == "👤 Mi Perfil":
    show_profile_management()

# Página: Gestión de Usuarios
elif page == "👥 Gestión de Usuarios":
    show_user_management()

# Página: Administrador DB (solo para admins)
elif page == "🔧 Administrador DB":
    show_db_admin()

def show_profile_management():
    """Muestra la página de gestión de perfil del usuario"""
    st.header("👤 Mi Perfil")
    st.markdown("### Gestiona tu información personal")
    # Mostrar mensaje persistente tras actualización
    if st.session_state.get('profile_updated'):
        st.success("✅ Información actualizada correctamente")
        del st.session_state['profile_updated']
    
    # Obtener información actual del usuario
    user_info = db.get_user_by_username(current_user['username'])
    
    if not user_info:
        st.error("❌ Error al cargar información del usuario")
        return
    
    # Convertir tupla a diccionario usando índices conocidos
    # Estructura real: (id, username, password_hash, full_name, email, role, preferred_system, hf_frequency_pref, hf_mode_pref, hf_power_pref, created_at, last_login)
    user_dict = {
        'id': user_info[0],
        'username': user_info[1],
        'password_hash': user_info[2],
        'full_name': user_info[3] if len(user_info) > 3 else '',
        'email': user_info[4] if len(user_info) > 4 else '',
        'role': user_info[5] if len(user_info) > 5 else '',
        'preferred_system': user_info[6] if len(user_info) > 6 else 'ASL',
        'created_at': user_info[10] if len(user_info) > 10 else '',
        'last_login': user_info[11] if len(user_info) > 11 else ''
    }
    
    # Crear tabs para organizar la información
    tab1, tab2 = st.tabs(["📝 Información Personal", "🔐 Cambiar Contraseña"])
    
    with tab1:
        st.subheader("Actualizar Información Personal")
        
        with st.form("update_profile_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                new_full_name = st.text_input(
                    "Nombre Completo:",
                    value=user_dict['full_name'],
                    help="Tu nombre completo como aparecerá en los reportes"
                )
                
                new_email = st.text_input(
                    "Correo Electrónico:",
                    value=user_dict['email'],
                    help="Tu dirección de correo electrónico"
                )
            
            with col2:
                st.text_input(
                    "Nombre de Usuario:",
                    value=user_dict['username'],
                    disabled=True,
                    help="El nombre de usuario no se puede cambiar"
                )
                
                st.text_input(
                    "Rol:",
                    value=user_dict['role'].title(),
                    disabled=True,
                    help="Tu rol en el sistema"
                )
            
            # Información adicional
            st.markdown("---")
            col3, col4 = st.columns(2)
            
            with col3:
                if user_dict['created_at']:
                    formatted_created = format_timestamp(user_dict['created_at'])
                    st.info(f"📅 **Miembro desde:** {formatted_created}")
            
            with col4:
                if user_dict['last_login']:
                    formatted_login = format_timestamp(user_dict['last_login'])
                    st.info(f"🕒 **Último acceso:** {formatted_login}")
            
            submitted = st.form_submit_button("💾 Actualizar Información", type="primary")
            
            if submitted:
                # Validar datos
                if not new_full_name or not new_full_name.strip():
                    st.error("❌ El nombre completo es obligatorio")
                elif not new_email or not new_email.strip():
                    st.error("❌ El correo electrónico es obligatorio")
                elif '@' not in new_email:
                    st.error("❌ Ingresa un correo electrónico válido")
                else:
                    # Actualizar información
                    success = db.update_user_profile(
                        user_dict['id'],
                        new_full_name.strip(),
                        new_email.strip()
                    )
                    
                    if success:
                        # Guardar bandera de éxito y recargar
                        st.session_state['profile_updated'] = True
                        st.rerun()
                    else:
                        st.error("❌ Error al actualizar la información")
    
    with tab2:
        st.subheader("Cambiar Contraseña")
        
        with st.form("change_password_form"):
            current_password = st.text_input(
                "Contraseña Actual:",
                type="password",
                help="Ingresa tu contraseña actual para confirmar el cambio"
            )
            
            new_password = st.text_input(
                "Nueva Contraseña:",
                type="password",
                help="Mínimo 6 caracteres"
            )
            
            confirm_password = st.text_input(
                "Confirmar Nueva Contraseña:",
                type="password",
                help="Repite la nueva contraseña"
            )
            
            submitted_password = st.form_submit_button("🔐 Cambiar Contraseña", type="primary")
            
            if submitted_password:
                # Validar contraseña actual
                if not auth.verify_password(current_password, user_dict['password_hash']):
                    st.error("❌ La contraseña actual es incorrecta")
                elif len(new_password) < 6:
                    st.error("❌ La nueva contraseña debe tener al menos 6 caracteres")
                elif new_password != confirm_password:
                    st.error("❌ Las contraseñas no coinciden")
                elif current_password == new_password:
                    st.error("❌ La nueva contraseña debe ser diferente a la actual")
                else:
                    # Cambiar contraseña
                    success = db.change_user_password(
                        user_dict['id'],
                        new_password
                    )
                    
                    if success:
                        st.success("✅ Contraseña cambiada correctamente")
                        st.info("🔄 Por seguridad, deberás iniciar sesión nuevamente")
                        # Marcar para mostrar botón de logout fuera del form
                        st.session_state.show_logout_button = True
                    else:
                        st.error("❌ Error al cambiar la contraseña")
    
    # Botón de logout fuera del formulario
    if st.session_state.get('show_logout_button', False):
        if st.button("🚪 Cerrar Sesión"):
            del st.session_state.show_logout_button
            auth.logout()

def show_motivational_dashboard():
    """Muestra el dashboard de rankings y reconocimientos"""
    st.header("🏆 Ranking")
    st.markdown("### ¡Competencia Sana entre Radioaficionados!")
    
    # Obtener estadísticas motivacionales
    motivational_stats = db.get_motivational_stats()
    
    # Pestañas para organizar las estadísticas
    tab1, tab2, tab3, tab4 = st.tabs(["🥇 Estaciones Top", "🌍 Zonas Activas", "📡 Sistemas Populares", "📊 Resumen General"])
    
    with tab1:
        st.subheader("🎯 Estaciones Más Reportadas")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📅 **Este Año**")
            if not motivational_stats['top_stations_year'].empty:
                for idx, row in motivational_stats['top_stations_year'].head(5).iterrows():
                    if idx == 0:
                        st.markdown(f"🥇 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
                    elif idx == 1:
                        st.markdown(f"🥈 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
                    elif idx == 2:
                        st.markdown(f"🥉 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
                    else:
                        st.markdown(f"🏅 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
            else:
                st.info("No hay datos suficientes para mostrar el ranking anual")
        
        with col2:
            st.markdown("#### 📆 **Este Mes**")
            if not motivational_stats['top_stations_month'].empty:
                for idx, row in motivational_stats['top_stations_month'].head(5).iterrows():
                    if idx == 0:
                        st.markdown(f"🥇 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
                    elif idx == 1:
                        st.markdown(f"🥈 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
                    elif idx == 2:
                        st.markdown(f"🥉 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
                    else:
                        st.markdown(f"🏅 **{row['call_sign']}** - {row['operator_name']}")
                        st.markdown(f"   📊 {row['total_reports']} reportes")
            else:
                st.info("No hay datos suficientes para mostrar el ranking mensual")
    
    with tab2:
        st.subheader("🌍 Zonas Más Activas")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📅 **Este Año**")
            if not motivational_stats['top_zones_year'].empty:
                for idx, row in motivational_stats['top_zones_year'].iterrows():
                    st.markdown(f"🏆 **Zona {row['zona']}**")
                    st.markdown(f"   👥 {row['unique_stations']} estaciones únicas")
                    st.markdown(f"   📊 {row['total_reports']} reportes totales")
                    st.markdown("---")
            else:
                st.info("No hay datos de zonas para este año")
        
        with col2:
            st.markdown("#### 📆 **Este Mes**")
            if not motivational_stats['top_zones_month'].empty:
                for idx, row in motivational_stats['top_zones_month'].iterrows():
                    st.markdown(f"🏆 **Zona {row['zona']}**")
                    st.markdown(f"   👥 {row['unique_stations']} estaciones únicas")
                    st.markdown(f"   📊 {row['total_reports']} reportes totales")
                    st.markdown("---")
            else:
                st.info("No hay datos de zonas para este mes")
    
    with tab3:
        st.subheader("📡 Sistemas Más Utilizados")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📅 **Este Año**")
            if not motivational_stats['top_systems_year'].empty:
                for idx, row in motivational_stats['top_systems_year'].iterrows():
                    st.markdown(f"🔧 **{row['sistema']}**")
                    st.markdown(f"   👥 {row['unique_stations']} estaciones únicas")
                    st.markdown(f"   📊 {row['total_reports']} reportes totales")
                    st.markdown("---")
            else:
                st.info("No hay datos de sistemas para este año")
        
        with col2:
            st.markdown("#### 📆 **Este Mes**")
            if not motivational_stats['top_systems_month'].empty:
                for idx, row in motivational_stats['top_systems_month'].iterrows():
                    st.markdown(f"🔧 **{row['sistema']}**")
                    st.markdown(f"   👥 {row['unique_stations']} estaciones únicas")
                    st.markdown(f"   📊 {row['total_reports']} reportes totales")
                    st.markdown("---")
            else:
                st.info("No hay datos de sistemas para este mes")
    
    with tab4:
        st.subheader("📊 Resumen General de Actividad")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📅 **Estadísticas del Año**")
            if not motivational_stats['general_year'].empty:
                year_stats = motivational_stats['general_year'].iloc[0]
                st.metric("📊 Total Reportes", year_stats['total_reports'])
                st.metric("👥 Estaciones Únicas", year_stats['unique_stations'])
                st.metric("📅 Días Activos", year_stats['active_days'])
            else:
                st.info("No hay estadísticas generales del año")
        
        with col2:
            st.markdown("#### 📆 **Estadísticas del Mes**")
            if not motivational_stats['general_month'].empty:
                month_stats = motivational_stats['general_month'].iloc[0]
                st.metric("📊 Total Reportes", month_stats['total_reports'])
                st.metric("👥 Estaciones Únicas", month_stats['unique_stations'])
                st.metric("📅 Días Activos", month_stats['active_days'])
            else:
                st.info("No hay estadísticas generales del mes")
    
    # Mensaje motivacional
    st.markdown("---")
    st.markdown("### 🎉 ¡Sigue Participando!")
    st.info("💪 **¡Cada reporte cuenta!** Mantente activo en las redes y ayuda a tu zona y sistema favorito a liderar las estadísticas. ¡La competencia sana nos hace crecer como comunidad radioaficionada! 📻✨")

def show_user_management():
    # Verificar si el usuario es admin
    if current_user['role'] != 'admin':
        st.error("❌ Acceso denegado. Solo los administradores pueden acceder a esta sección.")
        st.stop()
        
    st.header("👥 Gestión de Usuarios")
    
    # Inicializar servicio de email
    if 'email_service' not in st.session_state:
        st.session_state.email_service = EmailService()
    
    email_service = st.session_state.email_service
    
    # Tabs para organizar funcionalidades
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Lista de Usuarios", "➕ Crear Usuario", "🔄 Recuperar Contraseña", "⚙️ Configuración Email"])
    
    with tab1:
        st.subheader("Lista de Usuarios")
        
        # Obtener usuarios
        users = db.get_all_users()
        
        if users is not None and len(users) > 0:
            for user in users:
                with st.expander(f"👤 {user['username']} ({user['role']})", expanded=st.session_state.get(f"editing_user_{user['id']}", False)):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Nombre completo:** {user.get('full_name', 'N/A')}")
                        st.write(f"**Email:** {user.get('email', 'N/A')}")
                        st.write(f"**Rol:** {user['role']}")
                        st.write(f"**Creado:** {user.get('created_at', 'N/A')}")
                    
                    with col2:
                        # Botón para editar usuario
                        if st.button(f"✏️ Editar", key=f"edit_user_{user['id']}"):
                            st.session_state[f"editing_user_{user['id']}"] = True
                        
                        # Botón para eliminar usuario (solo si no es admin)
                        if user['username'] != 'admin':
                            if st.button(f"🗑️ Eliminar", key=f"delete_user_{user['id']}"):
                                try:
                                    db.delete_user(user['id'])
                                    st.success(f"Usuario {user['username']} eliminado")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al eliminar usuario: {str(e)}")
                        else:
                            st.info("👑 Usuario administrador protegido")
                    
                    # Formulario de edición si está activado
                    if st.session_state.get(f"editing_user_{user['id']}", False):
                        st.markdown("---")
                        st.subheader("✏️ Editar Usuario")
                        
                        with st.form(f"edit_user_form_{user['id']}"):
                            edit_full_name = st.text_input("Nombre completo:", value=user.get('full_name', ''))
                            edit_email = st.text_input("Email:", value=user.get('email', ''))
                            edit_role = st.selectbox("Rol:", ["operator", "admin"], 
                                                   index=0 if user['role'] == 'operator' else 1)
                            
                            # Opción para cambiar contraseña
                            change_password = st.checkbox("Cambiar contraseña")
                            new_password = ""
                            confirm_new_password = ""
                            
                            if change_password:
                                new_password = st.text_input("Nueva contraseña:", type="password", 
                                                           help="Mínimo 8 caracteres, 1 mayúscula, 1 número, 1 carácter especial")
                                confirm_new_password = st.text_input("Confirmar nueva contraseña:", type="password")
                            
                            col_save, col_cancel = st.columns(2)
                            
                            with col_save:
                                save_changes = st.form_submit_button("💾 Guardar Cambios")
                            
                            with col_cancel:
                                cancel_edit = st.form_submit_button("❌ Cancelar")
                            
                            if save_changes:
                                # Validar campos obligatorios
                                if not edit_full_name or not edit_email:
                                    st.error("❌ Nombre completo y email son obligatorios")
                                else:
                                    # Validar contraseña si se va a cambiar
                                    password_valid = True
                                    if change_password:
                                        if new_password != confirm_new_password:
                                            st.error("❌ Las contraseñas no coinciden")
                                            password_valid = False
                                        else:
                                            from utils import validate_password
                                            is_valid, message = validate_password(new_password)
                                            if not is_valid:
                                                st.error(f"❌ {message}")
                                                password_valid = False
                                    
                                    if password_valid:
                                        try:
                                            # Actualizar información del usuario
                                            db.update_user(user['id'], edit_full_name, edit_role, edit_email)
                                            
                                            # Cambiar contraseña si se solicitó
                                            if change_password:
                                                import hashlib
                                                password_hash = hashlib.sha256(new_password.encode()).hexdigest()
                                                db.change_password(user['username'], password_hash)
                                            
                                            st.success("✅ Usuario actualizado exitosamente")
                                            
                                            # Limpiar estado de edición
                                            del st.session_state[f"editing_user_{user['id']}"]
                                            st.rerun()
                                            
                                        except Exception as e:
                                            st.error(f"❌ Error al actualizar usuario: {str(e)}")
                            elif cancel_edit:
                                # Cancelar edición
                                del st.session_state[f"editing_user_{user['id']}"]
                                st.rerun()
        else:
            st.info("No hay usuarios registrados")
    
    with tab2:
        st.subheader("➕ Crear Nuevo Usuario")
        
        with st.form("create_user_form"):
            new_username = st.text_input("Nombre de usuario:")
            new_full_name = st.text_input("Nombre completo:")
            new_email = st.text_input("Email:")
            new_password = st.text_input("Contraseña:", type="password", help="Mínimo 8 caracteres, 1 mayúscula, 1 número, 1 carácter especial")
            confirm_password = st.text_input("Confirmar contraseña:", type="password")
            new_role = st.selectbox("Rol:", ["operator", "admin"])
            
            submit_create = st.form_submit_button("✅ Crear Usuario")
            
            if submit_create:
                if new_username and new_full_name and new_email and new_password and confirm_password:
                    # Validar que las contraseñas coincidan
                    if new_password != confirm_password:
                        st.error("❌ Las contraseñas no coinciden")
                    else:
                        # Validar fortaleza de la contraseña
                        from utils import validate_password
                        is_valid, message = validate_password(new_password)
                        
                        if not is_valid:
                            st.error(f"❌ {message}")
                        else:
                            try:
                                # Crear usuario
                                user_id = auth.create_user(new_username, new_password, role=new_role, full_name=new_full_name, email=new_email)
                                
                                if user_id:
                                    st.success("✅ Usuario creado exitosamente")
                                    
                                    # Mostrar información del usuario creado
                                    st.info(f"""
                                    **Usuario creado:**
                                    - **Nombre de usuario:** {new_username}
                                    - **Nombre completo:** {new_full_name}
                                    - **Email:** {new_email}
                                    - **Rol:** {new_role}
                                    """)
                                    
                                    # Enviar email de bienvenida si está configurado
                                    if email_service.is_configured():
                                        user_data = {
                                            'username': new_username,
                                            'full_name': new_full_name,
                                            'email': new_email,
                                            'role': new_role
                                        }
                                        
                                        if email_service.send_welcome_email(user_data, new_password):
                                            st.success("📧 Email de bienvenida enviado")
                                        else:
                                            st.warning("⚠️ Usuario creado pero no se pudo enviar el email de bienvenida")
                                    else:
                                        st.warning("⚠️ Usuario creado. Configura SMTP para enviar credenciales por email")
                                    
                                    # Esperar un momento antes de recargar para mostrar mensajes
                                    import time
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    st.error("❌ Error al crear usuario (posiblemente el usuario ya existe)")
                            except Exception as e:
                                st.error(f"❌ Error al crear usuario: {str(e)}")
                else:
                    st.error("❌ Por favor completa todos los campos")
    
    with tab3:
        st.subheader("🔄 Recuperar Contraseña")
        
        with st.form("password_recovery_form"):
            recovery_email = st.text_input("Email del usuario:")
            submit_recovery = st.form_submit_button("📧 Enviar Email de Recuperación")
            
            if submit_recovery:
                if recovery_email:
                    if email_service.is_configured():
                        try:
                            # Buscar usuario por email
                            user = db.get_user_by_email(recovery_email)
                            
                            if user:
                                # Generar token y enviar email
                                if email_service.send_password_reset_email(user):
                                    st.success("📧 Email de recuperación enviado")
                                else:
                                    st.error("❌ Error al enviar email de recuperación")
                            else:
                                st.error("❌ No se encontró usuario con ese email")
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
                    else:
                        st.error("❌ Servicio de email no configurado")
                else:
                    st.error("❌ Por favor ingresa un email")
    
    with tab4:
        st.subheader("⚙️ Configuración del Servicio de Email")
        
        # Estado actual del servicio
        if email_service.is_configured():
            st.success("✅ Servicio de email configurado")
            st.info(f"Servidor: {email_service.smtp_server}:{email_service.smtp_port}")
            st.info(f"Usuario: {email_service.smtp_username}")
        else:
            st.warning("⚠️ Servicio de email no configurado")
        
        with st.form("smtp_config_form"):
            st.write("**Configuración SMTP:**")
            
            smtp_server = st.text_input("Servidor SMTP:", value=email_service.smtp_server or "smtp.gmail.com")
            smtp_port = st.number_input("Puerto SMTP:", value=email_service.smtp_port or 587, min_value=1, max_value=65535)
            smtp_username = st.text_input("Usuario SMTP:", value=email_service.smtp_username or "")
            smtp_password = st.text_input("Contraseña SMTP:", type="password")
            sender_email = st.text_input("Email remitente:", value=getattr(email_service, 'from_email', '') or "")
            sender_name = st.text_input("Nombre remitente:", value=getattr(email_service, 'from_name', '') or "Sistema FMRE")
            
            submit_smtp = st.form_submit_button("💾 Guardar Configuración SMTP")
            
            if submit_smtp:
                if smtp_server and smtp_username and smtp_password:
                    email_service.configure_smtp(
                        smtp_server, smtp_port, smtp_username, 
                        smtp_password if smtp_password else email_service.smtp_password,
                        sender_email, sender_name
                    )
                    
                    st.success("✅ Configuración SMTP guardada")
                    st.rerun()
                else:
                    st.error("❌ Por favor completa los campos obligatorios")

# Footer
st.markdown("---")
# Footer con logo usando base64
import base64
try:
    with open("assets/LogoFMRE_small.png", "rb") as f:
        logo_data = base64.b64encode(f.read()).decode()
    st.markdown(f"""
    <div style='text-align: center; color: #666;'>
        <div style='display: flex; align-items: center; justify-content: center; gap: 8px; margin-bottom: 5px;'>
            <img src="data:image/png;base64,{logo_data}" alt="FMRE Logo" style="max-height:40px; width:auto;">
            <span style="font-weight: bold;">SIGQ v1.3</span>
        </div>
        <div>
            Federación Mexicana de Radioexperimentadores<br>
            Desarrollado con ❤️ por los miembros del Radio Club Guadiana A.C.
        </div>
    </div>
    """, unsafe_allow_html=True)
except:
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        📻 FMRE SIR v1.0 | Federación Mexicana de Radioexperimentadores<br>
        Desarrollado con ❤️ por los miembros del Radio Club Guadiana A.C.
    </div>
    """, unsafe_allow_html=True)

# Endpoint API para búsqueda de indicativos
def get_call_signs_suggestions():
    """API endpoint para obtener sugerencias de indicativos"""
    query_params = st.query_params
    query = query_params.get('q', '')
    
    if len(query) >= 2:
        suggestions = db.search_call_signs_dynamic(query, limit=10)
        return suggestions
    return []

# Función para servir el endpoint API
if st.query_params.get('api') == 'call_signs':
    suggestions = get_call_signs_suggestions()
    st.json(suggestions)
    st.stop()

