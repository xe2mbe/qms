import streamlit as st
import sqlite3
import time
import secrets
import string
from time_utils import format_datetime, get_current_cdmx_time
import hashlib
from datetime import datetime, timedelta
import pytz
from database import FMREDatabase
from auth import AuthManager
from email_sender import EmailSender
import utils
import re
import io
import unicodedata
import json
import base64
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from utils import show_gestion_estaciones
from rs_management import show_rs_management

db = FMREDatabase()
auth = AuthManager(db)

MEXICO_STATE_COORDS = {
    "aguascalientes": (21.8853, -102.2916),
    "baja california": (30.8406, -115.2838),
    "baja california sur": (24.1426, -110.3128),
    "campeche": (19.8301, -90.5349),
    "chiapas": (16.7520, -93.1167),
    "chihuahua": (28.6320, -106.0691),
    "ciudad de mexico": (19.4326, -99.1332),
    "coahuila": (27.0587, -101.7068),
    "colima": (19.1223, -104.0072),
    "durango": (24.0277, -104.6532),
    "guanajuato": (21.0190, -101.2574),
    "guerrero": (17.4392, -99.5451),
    "hidalgo": (20.1011, -98.7624),
    "jalisco": (20.6597, -103.3496),
    "mexico": (19.2832, -99.6557),
    "estado de mexico": (19.2832, -99.6557),
    "michoacan": (19.5665, -101.7068),
    "morelos": (18.6813, -99.1013),
    "nayarit": (21.7514, -104.8455),
    "nuevo leon": (25.5922, -99.9962),
    "oaxaca": (17.0732, -96.7266),
    "puebla": (19.0413, -98.2062),
    "queretaro": (20.5888, -100.3899),
    "quintana roo": (19.1817, -88.4791),
    "san luis potosi": (22.1565, -100.9855),
    "sinaloa": (24.8091, -107.3940),
    "sonora": (29.0729, -110.9559),
    "tabasco": (17.8409, -92.6189),
    "tamaulipas": (24.2669, -98.8363),
    "tlaxcala": (19.3182, -98.2374),
    "veracruz": (19.1738, -96.1342),
    "yucatan": (20.7099, -89.0943),
    "zacatecas": (22.7709, -102.5833),
    "extranjero": (21.0, -89.0),
}

GEOJSON_STATE_ALIASES = {
    "cdmx": "ciudad de mexico",
    "ciudad de mexico": "ciudad de mexico",
    "distrito federal": "ciudad de mexico",
    "coahuila": "coahuila de zaragoza",
    "coahuila de zaragoza": "coahuila de zaragoza",
    "estado de mexico": "mexico",
    "mexico": "mexico",
    "michoacan": "michoacan",
    "michoacan de ocampo": "michoacan",
    "veracruz": "veracruz de ignacio de la llave",
    "veracruz de ignacio de la llave": "veracruz de ignacio de la llave",
}

def _normalizar_estado_nombre(nombre_estado: str) -> str:
    if not nombre_estado:
        return ""

    texto = unicodedata.normalize('NFKD', str(nombre_estado))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.strip().lower()

@st.cache_resource
def _load_mexico_states_geojson() -> dict | None:
    geojson_path = Path("data/mexico_states.geojson")
    if not geojson_path.exists():
        return None

    try:
        return json.loads(geojson_path.read_text(encoding="utf-8"))
    except Exception as exc:
        st.warning(f"No se pudo cargar el archivo GeoJSON de estados: {exc}")
        return None

def _infer_featureidkey(geojson: dict) -> tuple[str, str]:
    """Infere la propiedad a usar como featureidkey para el GeoJSON (compatibilidad amplia)."""
    try:
        props = geojson.get('features', [{}])[0].get('properties', {})
        for key in (
            "state_name", "STATE_NAME",  # GeoJSON común (este repo)
            "name", "NOMGEO", "NOM_ENT", "estado", "nombre"
        ):
            if key in props:
                return f"properties.{key}", key
    except Exception:
        pass
    # Fallback razonable
    return "properties.state_name", "state_name"

def show_public_home():
    """Página pública con mapa y filtros para usuarios no autenticados"""
    h_menu, h_logo, h_txt = st.columns([1, 1, 6])
    with h_menu:
        popover = getattr(st, "popover", None)
        if callable(popover):
            with st.popover("☰"):
                if st.button("Login", type="primary", width='stretch'):
                    st.session_state.force_login = True
                    st.rerun()
        else:
            with st.expander("☰", expanded=False):
                if st.button("Login", type="primary", width='stretch'):
                    st.session_state.force_login = True
                    st.rerun()
    with h_logo:
        try:
            st.image("assets/LogoFMRE_medium.png")
        except Exception:
            pass
    with h_txt:
        st.subheader("Estadísticas de la toma de reportes del boletín FMRE")
        st.caption("Mapa interactivo de México con actividad por estado y resúmenes por estado y sistema.")

    rango = st.selectbox("Rango", ["Últimos 7 días", "Últimos 30 días", "Últimos 12 meses", "Todo", "Personalizado"], index=1)

    # Rango personalizado (opcional)
    fecha_ini_input = None
    fecha_fin_input = None
    if rango == "Personalizado":
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            fecha_ini_input = st.date_input("Fecha inicio", value=datetime.now() - timedelta(days=30), key="pub_fecha_inicio")
        with col_f2:
            fecha_fin_input = st.date_input("Fecha fin", value=datetime.now(), key="pub_fecha_fin")
        if fecha_ini_input > fecha_fin_input:
            st.error("❌ La fecha de inicio debe ser anterior o igual a la fecha de fin")
            return

    # Construir consulta agregada por estado
    where = []
    params: list = []
    today = datetime.now().date()
    # Normalizar fecha a formato ISO YYYY-MM-DD para comparar
    fecha_expr = (
        "(CASE "
        " WHEN fecha_reporte LIKE '__/__/____%' THEN substr(fecha_reporte,7,4)||'-'||substr(fecha_reporte,4,2)||'-'||substr(fecha_reporte,1,2)"
        " WHEN fecha_reporte LIKE '____-__-__%' THEN substr(fecha_reporte,1,10)"
        " ELSE substr(fecha_reporte,1,10) END)"
    )
    if rango == "Últimos 7 días":
        start = (today - timedelta(days=7)).strftime('%Y-%m-%d')
        where.append(f"{fecha_expr} >= ?")
        params.append(start)
    elif rango == "Últimos 30 días":
        start = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        where.append(f"{fecha_expr} >= ?")
        params.append(start)
    elif rango == "Últimos 12 meses":
        start = (today - timedelta(days=365)).strftime('%Y-%m-%d')
        where.append(f"{fecha_expr} >= ?")
        params.append(start)
    elif rango == "Personalizado" and fecha_ini_input and fecha_fin_input:
        start = fecha_ini_input.strftime('%Y-%m-%d')
        end = fecha_fin_input.strftime('%Y-%m-%d')
        where.append(f"{fecha_expr} >= ?")
        params.append(start)
        where.append(f"{fecha_expr} <= ?")
        params.append(end)

    where_clause = " WHERE " + " AND ".join(where) if where else ""
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            total = cur.execute(f"SELECT COUNT(*) FROM reportes{where_clause}", params).fetchone()[0]
            estaciones = cur.execute(f"SELECT COUNT(DISTINCT indicativo) FROM reportes{where_clause}", params).fetchone()[0]
            estados_cnt = cur.execute(f"SELECT COUNT(DISTINCT CASE WHEN estado IS NOT NULL AND estado<>'' THEN estado END) FROM reportes{where_clause}", params).fetchone()[0]
            zonas_cnt = cur.execute(f"SELECT COUNT(DISTINCT CASE WHEN zona IS NOT NULL AND zona<>'' THEN zona END) FROM reportes{where_clause}", params).fetchone()[0]
            sistemas_cnt = cur.execute(f"SELECT COUNT(DISTINCT CASE WHEN sistema IS NOT NULL AND sistema<>'' THEN sistema END) FROM reportes{where_clause}", params).fetchone()[0]
    except Exception:
        total = estaciones = estados_cnt = zonas_cnt = sistemas_cnt = 0
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Reportes", int(total))
    m2.metric("Estaciones", int(estaciones))
    m3.metric("Estados", int(estados_cnt))
    m4.metric("Zonas", int(zonas_cnt))
    m5.metric("Sistemas", int(sistemas_cnt))

    sql = "SELECT estado, COUNT(*) as c FROM reportes"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY estado"

    rows = []
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            rows = cur.execute(sql, params).fetchall() or []
    except Exception:
        rows = []

    # Cargar GeoJSON y preparar índice por estado
    geo = _load_mexico_states_geojson()
    if not geo:
        st.info("No se encontró el mapa de estados. Contacte al administrador.")
        return
    featureidkey, prop_key = _infer_featureidkey(geo)

    # Mapa de normalización a propiedad original del GeoJSON
    geo_index: dict[str, str] = {}
    try:
        for feat in geo.get('features', []):
            props = feat.get('properties', {})
            val = str(props.get(prop_key, '')).strip()
            if not val:
                continue
            norm = _normalizar_estado_nombre(val)
            geo_index[norm] = val
    except Exception:
        pass

    def _match_geo_key(e: str) -> str | None:
        if not e:
            return None
        e_norm = _normalizar_estado_nombre(e)
        # Coincidencia directa con propiedades del GeoJSON
        if e_norm in geo_index:
            return e_norm
        # Intentar alias conocidos
        alias = GEOJSON_STATE_ALIASES.get(e_norm)
        if alias:
            alias_norm = _normalizar_estado_nombre(alias)
            if alias_norm in geo_index:
                return alias_norm
            # Caso especial: Estado de México
            if alias_norm == "mexico" and "estado de mexico" in geo_index:
                return "estado de mexico"
        # Caso especial: DB dice "mexico", GeoJSON usa "estado de mexico"
        if e_norm == "mexico" and "estado de mexico" in geo_index:
            return "estado de mexico"
        return None

    data_map = []
    total_extranjero = 0
    for r in rows:
        estado_db = r[0]
        conteo = int(r[1] or 0)
        match_key = _match_geo_key(estado_db)
        if not match_key:
            # Contabilizar extranjero si aplica
            if _normalizar_estado_nombre(estado_db) in ("extranjero", "ext"):
                total_extranjero += conteo
            continue
        target = geo_index.get(match_key)
        if target:
            data_map.append({"estado": target, "conteo": conteo})

    if not data_map:
        st.caption("Sin datos para el rango/filtros seleccionados")

    # Construir mapa para TODOS los estados de México (los sin datos en 0)
    counts_by_estado = {d['estado']: d['conteo'] for d in data_map}
    full_map = [
        {"estado": estado_full, "conteo": counts_by_estado.get(estado_full, 0)}
        for estado_full in geo_index.values()
    ]
    df_map = pd.DataFrame(full_map)
    fig = px.choropleth(
        df_map,
        geojson=geo,
        locations="estado",
        color="conteo",
        featureidkey=featureidkey,
        color_continuous_scale="Greens",
        projection="mercator",
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=700)
    st.plotly_chart(fig, use_container_width=True)

    if total_extranjero:
        st.caption(f"Incluye {total_extranjero} reporte(s) de 'Extranjero' no mapeados en el coroplético")
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            add_cond = " AND " if where_clause else " WHERE "
            rows_est = cur.execute(
                f"SELECT estado, COUNT(*) as c FROM reportes{where_clause}{add_cond}estado IS NOT NULL AND estado<>'' GROUP BY estado ORDER BY c DESC",
                params,
            ).fetchall() or []
            rows_sys = cur.execute(
                f"SELECT sistema, COUNT(*) as c FROM reportes{where_clause}{add_cond}sistema IS NOT NULL AND sistema<>'' GROUP BY sistema ORDER BY c DESC",
                params,
            ).fetchall() or []
    except Exception:
        rows_est, rows_sys = [], []
    if rows_est:
        df_est = pd.DataFrame(rows_est, columns=["estado", "reportes"])
        df_est.insert(0, "Numero", range(1, len(df_est) + 1))
        st.subheader("Por estado")
        fig_est = px.bar(
            df_est, x="estado", y="reportes", color="estado",
            color_discrete_sequence=px.colors.qualitative.Plotly
        )
        fig_est.update_layout(showlegend=False)
        st.plotly_chart(fig_est, use_container_width=True)
        df_est_display = df_est.rename(columns={
            "Numero": "Número",
            "estado": "Estado",
            "reportes": "Reportes"
        })
        st.dataframe(df_est_display, width=720, hide_index=True)
    if rows_sys:
        df_sys = pd.DataFrame(rows_sys, columns=["sistema", "reportes"])
        df_sys.insert(0, "Numero", range(1, len(df_sys) + 1))
        st.subheader("Por sistema")
        fig_sys = px.bar(
            df_sys, x="sistema", y="reportes", color="sistema",
            color_discrete_sequence=px.colors.qualitative.Dark24
        )
        fig_sys.update_layout(showlegend=False)
        st.plotly_chart(fig_sys, use_container_width=True)
        df_sys_display = df_sys.rename(columns={
            "Numero": "Número",
            "sistema": "Sistema",
            "reportes": "Reportes"
        })
        st.dataframe(df_sys_display, width=720, hide_index=True)

def show_sidebar():
    """Muestra la barra lateral solo cuando el usuario está autenticado"""
    if 'user' not in st.session_state:
        # Si no está autenticado, no mostrar barra lateral
        st.sidebar.empty()
        return

    with st.sidebar:
        # Centrar cualquier imagen en la barra lateral (incluye el logo FMRE)
        st.markdown(
            """
            <style>
            [data-testid="stSidebar"] > div:first-child { min-height:100vh; display:flex; flex-direction:column; }
            [data-testid="stSidebar"] [data-testid="stImage"] { display:flex; justify-content:center; }
            [data-testid="stSidebar"] [data-testid="stImage"] img { display:block; margin-left:auto; margin-right:auto; }
            .qms-sb-spacer { flex: 1 1 auto; }
            .qms-sb-session { margin-top:auto; }
            </style>
            """,
            unsafe_allow_html=True,
        )
        # Logo FMRE centrado sin modificar tamaño (contenedor flex con base64)
        try:
            _logo_b64_mid = base64.b64encode(Path("assets/LogoFMRE_medium.png").read_bytes()).decode()
            st.markdown(
                f'<div style="width:100%;display:flex;justify-content:center;">\n'
                f'  <img src="data:image/png;base64,{_logo_b64_mid}" alt="FMRE" style="display:block;height:auto;"/>\n'
                f'</div>',
                unsafe_allow_html=True,
            )
        except Exception:
            st.image("assets/LogoFMRE_medium.png", output_format='PNG')
        
        # Datos de usuario (para menú y para mostrar al final)
        user = st.session_state.user
        
        # Menú de navegación
        st.markdown("### Menú")
        menu_options = ["🏠 Inicio", "📝 Toma de Reportes", "📋 Registros", "🧾 Reportes", "📊 Estadísticas"]
        
        # Mostrar opciones de administración solo para administradores
        if user['role'] == 'admin':
            menu_options.extend(["🔧 Gestión", "⚙️ Configuración"])
            
        selected = st.selectbox("Navegación", menu_options)
        
        # Navegación
        if selected == "🔧 Gestión":
            st.session_state.current_page = "gestion"
        elif selected == "📝 Toma de Reportes":
            st.session_state.current_page = "toma_reportes"
        elif selected == "📋 Registros":
            st.session_state.current_page = "registros"
        elif selected == "🧾 Reportes":
            st.session_state.current_page = "reportes"
        elif selected == "📊 Estadísticas":
            st.session_state.current_page = "reports"
        elif selected == "📧 Enviar Reportes":
            st.session_state.current_page = "send_reports"
        elif selected == "⚙️ Configuración":
            st.session_state.current_page = "settings"
        else:
            st.session_state.current_page = "home"
        
        # Botón de cierre de sesión
        if st.button("🚪 Cerrar sesión", width='stretch'):
            auth.logout()
            st.rerun()

        # Espaciador flexible para empujar la info de sesión al fondo
        st.markdown('<div class="qms-sb-spacer"></div>', unsafe_allow_html=True)

        # Información de sesión en la parte inferior
        current_date = get_current_cdmx_time().strftime("%d/%m/%Y %H:%M %Z")
        st.markdown(
            f"""
<div class="qms-sb-session">
  <hr/>
  <div>👤 {user['role'].capitalize()} — {user['full_name']}</div>
  <div>📅 Sesión: {current_date} (Hora CDMX)</div>
</div>
""",
            unsafe_allow_html=True,
        )

def show_home():
    """Muestra la página de inicio"""
    st.title("Bienvenido al Sistema de Gestión de QSOs")
    user = st.session_state.get('user')
    now_cdmx = get_current_cdmx_time()
    if user:
        st.markdown(f"### {user['full_name']}")
        st.caption(f"{user['role'].capitalize()} · {now_cdmx.strftime('%d/%m/%Y %H:%M %Z')}")
    else:
        st.caption(now_cdmx.strftime("%d/%m/%Y %H:%M %Z"))

    total_reportes = 0
    total_radios = 0
    zonas_activas = 0
    last_fecha = None
    last_tipo = None
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            total_reportes = cur.execute("SELECT COUNT(*) FROM reportes").fetchone()[0] or 0
            total_radios = cur.execute("SELECT COUNT(*) FROM radioexperimentadores WHERE activo=1").fetchone()[0] or 0
            try:
                zonas_activas = cur.execute("SELECT COUNT(*) FROM zonas WHERE activo=1").fetchone()[0] or 0
            except Exception:
                zonas_activas = cur.execute("SELECT COUNT(*) FROM zonas").fetchone()[0] or 0
            r = cur.execute("SELECT tipo_reporte, fecha_reporte FROM reportes ORDER BY fecha_reporte DESC, id DESC LIMIT 1").fetchone()
            if r:
                last_tipo = r[0] or "N/D"
                last_fecha = str(r[1])
    except Exception:
        pass

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Reportes", f"{total_reportes}")
    with c2:
        st.metric("Estaciones registradas", f"{total_radios}")
    with c3:
        st.metric("Zonas activas", f"{zonas_activas}")
    with c4:
        if last_fecha or last_tipo:
            st.metric("Último reporte", f"{last_fecha or 'N/D'}", last_tipo)
        else:
            st.metric("Último reporte", "N/D")

    st.subheader("Actividad reciente")
    lines = []
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            rows = cur.execute("SELECT fecha_reporte, indicativo, estado, zona, sistema FROM reportes ORDER BY fecha_reporte DESC, id DESC LIMIT 8").fetchall()
            for row in rows or []:
                fr = row[0]
                ind = row[1]
                est = row[2] or 'N/D'
                zon = row[3] or 'N/D'
                sis = row[4] or 'N/D'
                lines.append(f"- {fr}: {ind} · {zon} · {sis} · {est}")
    except Exception:
        pass
    if lines:
        st.markdown("\n".join(lines))
    else:
        st.caption("Sin actividad reciente")

    st.subheader("Próximas sesiones")
    def _next_weekday(base_dt, target_wd):
        d = (target_wd - base_dt.weekday()) % 7
        if d == 0:
            d = 7
        return (base_dt + timedelta(days=d)).date()
    prox_dom = _next_weekday(now_cdmx, 6)
    prox_mie = _next_weekday(now_cdmx, 2)
    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown(f"**Domingo (Boletín en Vivo):** {prox_dom.strftime('%d/%m/%Y')}")
    with cc2:
        st.markdown(f"**Miércoles (Retransmisión CREBC):** {prox_mie.strftime('%d/%m/%Y')}")

def show_gestion_usuarios():
    """Muestra la gestión de usuarios dentro de la sección de Gestión"""
    # El título ya no es necesario aquí ya que está en la pestaña
    
    # Inicializar servicio de email
    if 'email_service' not in st.session_state:
        st.session_state.email_service = EmailSender(db)
    
    email_service = st.session_state.email_service
    
    # Tabs para organizar funcionalidades
    tab1, tab2 = st.tabs(["📋 Lista de Usuarios", "➕ Crear Usuario"])
    
    with tab1:
        st.subheader("Lista de Usuarios")
        
        # Obtener usuarios
        users = db.get_all_users()
        
        if users is not None and len(users) > 0:
            for user in users:
                with st.expander(f"👤 {user.get('username', 'N/A')} ({user.get('role', 'operator')})", 
                              expanded=st.session_state.get(f"editing_user_{user['id']}", False)):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Nombre completo:** {user.get('full_name', 'N/A')}")
                        st.write(f"**Email:** {user.get('email', 'N/A')}")
                        st.write(f"**Rol:** {user.get('role', 'operator')}")
                        status_emoji = "✔️" if user.get('is_active', 0) else "❌"
                        status_text = "Activo" if user.get('is_active', 0) else "Inactivo"
                        st.write(f"**Estado:** {status_emoji} {status_text}")
                        st.write(f"**Creado:** {format_datetime(user.get('created_at'))}")
                        st.write(f"**Último inicio de sesión:** {format_datetime(user.get('last_login'))}")
                    
                    with col2:
                        # Botón para editar usuario
                        if st.button(f"✏️ Editar", key=f"edit_user_{user['id']}"):
                            st.session_state[f"editing_user_{user['id']}"] = True
                            st.rerun()
                        
                        # Botón para reenviar correo de bienvenida
                        if st.button(f"📧 Reenviar correo", key=f"resend_email_{user['id']}"):
                            try:
                                # Generar una contraseña temporal segura
                                import secrets
                                import string
                                
                                alphabet = string.ascii_letters + string.digits + string.punctuation
                                temp_password = ''.join(secrets.choice(alphabet) for i in range(12))
                                
                                # Actualizar la contraseña (hashing interno) y forzar cambio al siguiente inicio
                                db.change_password(user['username'], temp_password)
                                db.set_must_change_password(username=user['username'], value=True)
                                
                                # Enviar el correo de bienvenida
                                if email_service.send_user_credentials(user, temp_password):
                                    st.success(f"✅ Correo de bienvenida reenviado a {user.get('email', '')}")
                                    st.warning("⚠️ Se generó una nueva contraseña temporal y se forzará su cambio al próximo inicio de sesión.")

                                else:
                                    st.error("❌ Error al enviar el correo. Verifica la configuración SMTP.")
                                    
                            except Exception as e:
                                st.error(f"❌ Error al procesar la solicitud: {str(e)}")
                        
                        # Botón para eliminar usuario (solo si no es admin)
                        if user.get('username') != 'admin':
                            if st.button(f"🗑️ Eliminar", key=f"delete_user_{user['id']}"):
                                try:
                                    db.delete_user(user['id'])
                                    st.success(f"Usuario {user.get('username', '')} eliminado")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al eliminar usuario: {str(e)}")
                        else:
                            st.info("👑 Usuario administrador protegido")
                    
                    # Formulario de edición si está activado
                    if st.session_state.get(f"editing_user_{user['id']}", False):
                        st.markdown("---")
                        st.subheader("✏️ Editar Usuario")
                        # Selector de cuenta activa fuera del formulario para refresco inmediato
                        active_key = f"active_{user['id']}"
                        st.toggle(
                            "Cuenta activa",
                            value=bool(user.get('is_active', 1)),
                            help="Desactiva para bloquear el acceso de este usuario",
                            key=active_key
                        )
                        # Control de cambio de contraseña fuera del formulario para refresco inmediato (debajo del selector)
                        change_password_key = f"change_pwd_{user['id']}"
                        st.checkbox("Cambiar contraseña", key=change_password_key, help="Marca para mostrar campos de nueva contraseña")
                        
                        with st.form(f"edit_user_form_{user['id']}"):
                            edit_full_name = st.text_input("Nombre completo:", value=user.get('full_name', ''))
                            edit_email = st.text_input("Email:", value=user.get('email', ''))
                            edit_role = st.selectbox("Rol:", ["operator", "admin"], 
                                                   index=0 if user.get('role') == 'operator' else 1)
                            # Leer el valor del toggle externo
                            edit_is_active = st.session_state.get(active_key, bool(user.get('is_active', 1)))
                            
                            # Opción para cambiar contraseña (controlada desde fuera del formulario para refresco inmediato)
                            change_password = st.session_state.get(f"change_pwd_{user['id']}", False)
                            if change_password:
                                new_password = st.text_input("Nueva contraseña:", type="password", 
                                                           help="Mínimo 8 caracteres, 1 mayúscula, 1 número, 1 carácter especial",
                                                           key=f"new_password_{user['id']}")
                                confirm_new_password = st.text_input("Confirmar nueva contraseña:", type="password",
                                                                     key=f"confirm_new_password_{user['id']}")
                            else:
                                new_password = ""
                                confirm_new_password = ""
                            
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
                                            db.update_user(
                                                user_id=user['id'],
                                                full_name=edit_full_name,
                                                email=edit_email,
                                                role=edit_role,
                                                is_active=edit_is_active,
                                                password=(new_password if change_password else None)
                                            )
                                            
                                            st.success("✅ Usuario actualizado exitosamente")
                                            import time
                                            time.sleep(2)
                                            
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
        st.subheader("Crear Nuevo Usuario")
        
        with st.form("create_user_form"):
            new_username = st.text_input("Nombre de usuario:")
            new_full_name = st.text_input("Nombre completo:")
            new_email = st.text_input("Email:")
            new_password = st.text_input("Contraseña:", type="password", 
                                      help="Mínimo 8 caracteres, 1 mayúscula, 1 número, 1 carácter especial")
            confirm_password = st.text_input("Confirmar contraseña:", type="password")
            new_role = st.selectbox("Rol:", ["operator", "admin"])
            
            submit_create = st.form_submit_button("✅ Crear Usuario")
            
            if submit_create:
                if new_username and new_full_name and new_email and new_password and confirm_password:
                    # Validar que el nombre de usuario no exista
                    if db.user_exists(new_username):
                        st.error("❌ El nombre de usuario ya está en uso")
                    # Validar que el correo no exista
                    elif db.email_exists(new_email):
                        st.error("❌ El correo electrónico ya está registrado")
                    # Validar que las contraseñas coincidan
                    elif new_password != confirm_password:
                        st.error("❌ Las contraseñas no coinciden")
                    else:
                        # Validar fortaleza de la contraseña
                        from utils import validate_password
                        is_valid, message = validate_password(new_password)
                        
                        if not is_valid:
                            st.error(f"❌ {message}")
                        else:
                            try:
                                # Crear usuario usando el método de autenticación
                                user_id = auth.db.create_user(
                                    username=new_username,
                                    password=new_password,
                                    full_name=new_full_name,
                                    email=new_email,
                                    role=new_role
                                )
                                
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
                                    
                                    # Enviar email de bienvenida
                                    user_data = {
                                        'username': new_username,
                                        'full_name': new_full_name,
                                        'email': new_email,
                                        'role': new_role
                                    }
                                    
                                    if email_service.send_user_credentials(user_data, new_password):
                                        st.success("📧 Email de bienvenida enviado")
                                    else:
                                        st.warning("⚠️ Usuario creado pero no se pudo enviar el email de bienvenida")
                                    
                                    # Esperar un momento antes de recargar para mostrar mensajes
                                    import time
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    st.error("❌ Error al crear usuario (posiblemente el usuario ya existe)")
                            except Exception as e:
                                st.error(f"❌ Error al enviar el correo de bienvenida al usuario {new_username} al correo {new_email}: {str(e)}")
                else:
                    st.error("❌ Por favor completa todos los campos")

# Variable para almacenar la pestaña activa
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = "👥 Usuarios"

# Función para cambiar de pestaña
def set_active_tab(tab_name):
    st.session_state.active_tab = tab_name

def show_gestion():
    """Muestra el panel de gestión con pestañas para diferentes secciones"""
    st.title("🔧 Gestión")
    
    # Crear pestañas
    tabs = ["👥 Usuarios", "📅 Eventos", "📍 Zonas", "📻 HAMs", "🏢 Estaciones", "📱 Redes Sociales"]
    
    # Crear botones de pestaña personalizados
    cols = st.columns(len(tabs))
    for i, tab in enumerate(tabs):
        with cols[i]:
            if st.button(tab, key=f"tab_{i}", width='stretch'):
                set_active_tab(tab)
    
    st.markdown("---")  # Línea separadora
    
    # Mostrar el contenido de la pestaña activa
    if st.session_state.active_tab == "👥 Usuarios":
        show_gestion_usuarios()
    elif st.session_state.active_tab == "📅 Eventos":
        show_gestion_eventos()
    elif st.session_state.active_tab == "📍 Zonas":
        show_gestion_zonas()
    elif st.session_state.active_tab in ("📻 HAMs", "📻 Radioexperimentadores"):
        show_gestion_radioexperimentadores()
    elif st.session_state.active_tab == "🏢 Estaciones":
        show_gestion_estaciones()
    elif st.session_state.active_tab == "📱 Redes Sociales":
        show_gestion_redes_sociales()

def show_gestion_redes_sociales():
    """Muestra la gestión de redes sociales con pestañas"""
    from rs_management import show_rs_management, show_rs_form
    
    # Mostrar pestañas
    tab_lista, tab_crear = st.tabs(["📋 Lista de Redes Sociales", "➕ Agregar Red Social"])
    
    with tab_lista:
        st.subheader("📱 Lista de Redes Sociales")
        show_rs_management(show_tabs=False)
    
    with tab_crear:
        st.subheader("➕ Agregar Nueva Red Social")
        # Mostrar el formulario para agregar una nueva red social
        show_rs_form()

def show_gestion_eventos():
    """Muestra la gestión de eventos con pestañas para listar y crear eventos"""
    # Mostrar pestañas
    tab_lista, tab_crear = st.tabs(["📋 Lista de Eventos", "➕ Crear Evento"])
    
    with tab_lista:
        st.subheader("📅 Lista de Eventos")
        
        # Barra de búsqueda y filtros
        col1, col2 = st.columns([3, 1])
        with col1:
            busqueda = st.text_input("Buscar evento", "", placeholder="Buscar por nombre o ubicación...")
        with col2:
            mostrar_inactivos = st.checkbox("Mostrar inactivos", value=False)
        
        # Obtener eventos con filtros
        eventos = db.get_all_eventos(incluir_inactivos=mostrar_inactivos)
            
        if busqueda:
            busqueda = busqueda.lower()
            eventos = [e for e in eventos if 
                      busqueda in e['tipo'].lower() or 
                      busqueda in e.get('descripcion', '').lower()]
        
        if eventos:
            # Mostrar estadísticas rápidas
            activos = sum(1 for e in eventos if e.get('activo', 1) == 1)
            inactivos = len(eventos) - activos
            st.caption(f"Mostrando {len(eventos)} eventos ({activos} activos, {inactivos} inactivos)")
            
            # Mostrar eventos en una tabla
            for evento in eventos:
                # Determinar si estamos editando este evento
                is_editing = st.session_state.get(f'editing_evento_{evento["id"]}', False)
                
                with st.expander(
                    f"{'✅' if evento.get('activo', 1) == 1 else '⏸️'} {evento['tipo']}",
                    expanded=is_editing  # Expandir si está en modo edición
                ):
                    if not is_editing:
                        # Vista normal del evento
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            # Mostrar estado
                            estado = "Activo" if evento.get('activo', 1) == 1 else "Inactivo"
                            st.markdown(f"**Estado:** {estado}")
                            
                            # Mostrar descripción si existe
                            if evento.get('descripcion'):
                                st.markdown("**Descripción:**")
                                st.markdown(evento['descripcion'])
                        
                        with col2:
                            # Botones de acción
                            col_btn1, col_btn2 = st.columns(2)
                            
                            with col_btn1:
                                if st.button("✏️ Editar", key=f"edit_{evento['id']}", width='stretch'):
                                    st.session_state[f'editing_evento_{evento["id"]}'] = True
                                    st.rerun()
                            
                            with col_btn2:
                                estado_btn = "❌ Desactivar" if evento.get('activo', 1) == 1 else "✅ Activar"
                                if st.button(estado_btn, key=f"toggle_{evento['id']}", width='stretch'):
                                    nuevo_estado = 0 if evento.get('activo', 1) == 1 else 1
                                    db.update_evento(evento['id'], activo=nuevo_estado)
                                    st.success(f"Evento {'activado' if nuevo_estado == 1 else 'desactivado'} correctamente")
                                    time.sleep(2)
                                    st.rerun()
                            
                            # Botón de eliminar con confirmación
                            if st.button("🗑️ Eliminar", key=f"delete_{evento['id']}", 
                                       type="primary", width='stretch',
                                       help="Eliminar permanentemente este evento"):
                                # Mostrar diálogo de confirmación
                                if st.session_state.get(f'confirm_delete_{evento["id"]}') != True:
                                    st.session_state[f'confirm_delete_{evento["id"]}'] = True
                                    st.rerun()
                                else:
                                    if db.delete_evento(evento['id']):
                                        st.success("Evento eliminado correctamente")
                                        time.sleep(2)
                                        # Limpiar estado de confirmación
                                        if f'confirm_delete_{evento["id"]}' in st.session_state:
                                            del st.session_state[f'confirm_delete_{evento["id"]}']
                                        st.rerun()
                                    else:
                                        st.error("Error al eliminar el evento")
                                        if f'confirm_delete_{evento["id"]}' in st.session_state:
                                            del st.session_state[f'confirm_delete_{evento["id"]}']
                                        
                            # Mostrar mensaje de confirmación si es necesario
                            if st.session_state.get(f'confirm_delete_{evento["id"]}') == True:
                                st.warning("¿Estás seguro de que quieres eliminar este evento? Esta acción no se puede deshacer.")
                                if st.button("✅ Confirmar eliminación", key=f"confirm_del_{evento['id']}", 
                                           type="primary", width='stretch'):
                                    if db.delete_evento(evento['id']):
                                        st.success("Evento eliminado correctamente")
                                        time.sleep(2)
                                        # Limpiar estado de confirmación
                                        if f'confirm_delete_{evento["id"]}' in st.session_state:
                                            del st.session_state[f'confirm_delete_{evento["id"]}']
                                        st.rerun()
                                    else:
                                        st.error("Error al eliminar el evento")
                                
                                if st.button("❌ Cancelar", key=f"cancel_del_{evento['id']}", 
                                           width='stretch'):
                                    del st.session_state[f'confirm_delete_{evento["id"]}']
                                    st.rerun()
                    else:
                        # Mostrar formulario de edición
                        with st.form(f"edit_evento_{evento['id']}"):
                            # Obtener datos actuales del evento
                            evento_data = db.get_evento(evento['id'])
                            
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                nombre = st.text_input("Nombre del evento", value=evento_data['tipo'])
                                descripcion = st.text_area("Descripción", value=evento_data.get('descripcion', ''))
                                #ubicacion = st.text_input("Ubicación", value=evento_data.get('ubicacion', ''))
                            
                            with col2:
                                activo = st.checkbox("Activo", value=bool(evento_data.get('activo', 1)))
                            
                            # Botones del formulario
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                save_changes = st.form_submit_button("💾 Guardar cambios", width='stretch')

                            with col2:
                                cancel_edit = st.form_submit_button("❌ Cancelar", width='stretch')

                            if save_changes:
                                try:
                                    # Actualizar el evento
                                    if db.update_evento(
                                        evento_id=evento['id'],
                                        tipo=nombre,
                                        descripcion=descripcion,
                                        activo=1 if activo else 0
                                    ):
                                        st.success("✅ Evento actualizado correctamente")
                                        time.sleep(2)
                                        # Limpiar estado de edición
                                        del st.session_state[f'editing_evento_{evento["id"]}']
                                        st.rerun()
                                    else:
                                        st.error("❌ Error al actualizar el evento")
                                except Exception as e:
                                    st.error(f"Error al actualizar el evento: {str(e)}")
                            elif cancel_edit:
                                # Cancelar edición
                                del st.session_state[f'editing_evento_{evento["id"]}']
                                st.rerun()
            
            if not eventos:
                st.info("No se encontraron eventos que coincidan con los criterios de búsqueda")
        else:
            st.info("No hay eventos registrados")
    
    with tab_crear:
        show_crear_evento()

def show_crear_evento():
    """Muestra el formulario para crear o editar un tipo de evento"""
    # Verificar si estamos en modo edición
    is_editing = 'editing_evento' in st.session_state
    evento = None
    
    if is_editing:
        st.subheader("✏️ Editar Tipo de Evento")
        # Obtener datos del evento a editar
        evento = db.get_evento(st.session_state['editing_evento'])
        if not evento:
            st.error("Tipo de evento no encontrado")
            del st.session_state['editing_evento']
            return
    else:
        st.subheader("➕ Crear Nuevo Tipo de Evento")
    
    with st.form("evento_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            tipo = st.text_input("Tipo de evento", 
                               value=evento['tipo'] if evento else "",
                               placeholder="Ej: Retransmisión, Facebook, etc.")
            
            descripcion = st.text_area("Descripción",
                                    value=evento.get('descripcion', '') if evento else "",
                                    placeholder="Descripción opcional del tipo de evento")
        
        with col2:
            st.write("")
            st.write("")
            activo = st.checkbox("Activo", value=bool(evento.get('activo', 1)) if evento else True)
        
        # Botones del formulario
        col1, col2 = st.columns(2)
        
        with col1:
            if st.form_submit_button("💾 Guardar"):
                if not tipo:
                    st.error("El tipo de evento es obligatorio")
                else:
                    try:
                        if is_editing:
                            # Actualizar evento existente
                            if db.update_evento(
                                evento_id=evento['id'],
                                tipo=tipo,
                                descripcion=descripcion,
                                activo=1 if activo else 0
                            ):
                                st.success("✅ Tipo de evento actualizado correctamente")
                                time.sleep(2)
                                del st.session_state['editing_evento']
                                st.rerun()
                            else:
                                st.error("❌ Error al actualizar el tipo de evento")
                        else:
                            # Crear nuevo tipo de evento
                            evento_id = db.create_evento(
                                tipo=tipo,
                                descripcion=descripcion if descripcion else None
                            )
                            
                            if evento_id:
                                st.success("✅ Tipo de evento creado exitosamente")
                                time.sleep(2)
                                st.rerun()
                    except Exception as e:
                        st.error(f"Error al {'guardar' if is_editing else 'crear'} el tipo de evento: {str(e)}")
        
        with col2:
            if st.form_submit_button("❌ Cancelar"):
                if is_editing:
                    del st.session_state['editing_evento']
                st.rerun()

def show_reports():
    """Muestra la sección de reportes con análisis completo"""
    st.title("📊 Reportes y Análisis")
    tipo_reportes = st.selectbox("Tipo de reportes", ["Tradicional", "Redes Sociales"], index=0, key="reports_tipo")
    if tipo_reportes == "Tradicional":
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📈 Actividad General",
            "🌍 Análisis Geográfico",
            "📡 Sistemas de Radio",
            "📊 Tendencias",
            "⚖️ Comparativos"
        ])

        with tab1:
            show_actividad_general_report()

        with tab2:
            show_geografico_report()

        with tab3:
            show_sistemas_report()

        with tab4:
            show_tendencias_report()

        with tab5:
            show_comparativos_report()
    else:
        show_rs_reports()
 
def show_reportes():
    """Muestra la sección de Reportes con pestañas para Tradicional y Redes Sociales"""
    st.title("🧾 Reportes")
    tab1, tab2 = st.tabs(["📻 Tradicional", "📱 Redes Sociales"])

    with tab1:
        show_evento_report()

    with tab2:
        show_rs_reports()

def show_rs_reports():
    st.subheader("📱 Reportes de Redes Sociales")
    col1, col2 = st.columns(2)
    from datetime import datetime
    with col1:
        fecha_inicio = st.date_input("Fecha inicio", value=datetime.now().replace(day=1), key="rs_fecha_inicio")
    with col2:
        fecha_fin = st.date_input("Fecha fin", value=datetime.now(), key="rs_fecha_fin")
    if fecha_inicio > fecha_fin:
        st.error("❌ La fecha de inicio debe ser anterior a la fecha de fin")
        return
    fecha_inicio_str = fecha_inicio.strftime('%Y-%m-%d')
    fecha_fin_str = fecha_fin.strftime('%Y-%m-%d')
    fecha_rango_lbl = f"{fecha_inicio_str} a {fecha_fin_str}" if fecha_inicio_str != fecha_fin_str else fecha_inicio_str

    # Obtener datos RS de la BD
    try:
        reportes_rs = db.get_reportes_rs_por_fecha(fecha_inicio_str, fecha_fin_str)
        est = db.get_estadisticas_rs_por_fecha(fecha_inicio_str, fecha_fin_str)
    except Exception as e:
        st.error(f"Error al cargar reportes RS: {e}")
        return

    if not reportes_rs:
        st.info("No hay reportes de redes sociales para el período seleccionado.")
        return

    # Armar DataFrame principal
    df_rs = pd.DataFrame([
        {
            'Estación': (r.get('qrz_station') or ''),
            'Indicativo': r.get('indicativo', ''),
            'Nombre': r.get('operador', ''),
            'Estado': r.get('estado', ''),
            'Ciudad': r.get('ciudad', ''),
            'Zona': r.get('zona', ''),
            'Plataforma': r.get('plataforma_nombre', ''),
            'Fecha': (r.get('fecha_reporte') or '')
        }
        for r in reportes_rs
    ])

    # Métricas básicas
    estaciones_unicas = df_rs['Indicativo'].nunique()
    zona_mas_reportada = (df_rs['Zona'].mode().iloc[0] if not df_rs['Zona'].mode().empty else "N/A")
    plataforma_mas_usada = (df_rs['Plataforma'].mode().iloc[0] if not df_rs['Plataforma'].mode().empty else "N/A")
    cobertura_estados = df_rs['Estado'].nunique() if 'Estado' in df_rs.columns else 0

    # Distribuciones
    zonas_count = df_rs['Zona'].value_counts()
    df_zonas = pd.DataFrame({
        'Zona': zonas_count.index,
        'Cantidad': zonas_count.values,
        'Porcentaje': (zonas_count.values / max(len(df_rs), 1) * 100).round(1)
    })
    plataformas_count = df_rs['Plataforma'].value_counts()
    df_plataformas = pd.DataFrame({
        'Plataforma': plataformas_count.index,
        'Cantidad': plataformas_count.values,
        'Porcentaje': (plataformas_count.values / max(len(df_rs), 1) * 100).round(1)
    })

    # Mostrar resumen simple
    colm1, colm2, colm3, colm4 = st.columns(4)
    colm1.metric("Total de Reportes", f"{len(df_rs)}")
    colm2.metric("Estaciones Únicas", f"{estaciones_unicas}")
    colm3.metric("Zona Más Reportada", zona_mas_reportada)
    colm4.metric("Plataforma Más Usada", plataforma_mas_usada)

    st.subheader("📍 Distribución por Zona")
    st.dataframe(df_zonas, hide_index=True, width='stretch')

    st.subheader("📱 Distribución por Plataforma")
    st.dataframe(df_plataformas, hide_index=True, width='stretch')

    # Métricas por Plataforma (como en el PDF)
    st.subheader("📊 Métricas por Plataforma")
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                '''
                SELECT plataforma_nombre,
                       SUM(me_gusta) as me_gusta,
                       SUM(comentarios) as comentarios,
                       SUM(compartidos) as compartidos,
                       SUM(reproducciones) as reproducciones
                FROM estadisticas_rs
                WHERE fecha_reporte BETWEEN ? AND ?
                GROUP BY plataforma_nombre
                ORDER BY plataforma_nombre
                ''',
                (fecha_inicio_str, fecha_fin_str)
            )
            rows_metrics_ui = cur.fetchall() or []
    except Exception:
        rows_metrics_ui = []

    plat_metrics_records_ui = []
    total_me_gusta_ui = total_comentarios_ui = total_compartidos_ui = total_reproducciones_ui = 0
    for r in rows_metrics_ui:
        mg = int(r['me_gusta'] or 0)
        cm = int(r['comentarios'] or 0)
        cp = int(r['compartidos'] or 0)
        rp = int(r['reproducciones'] or 0)
        plat_metrics_records_ui.append({
            'Plataforma': str(r['plataforma_nombre'] or ''),
            'Me gusta': mg,
            'Comentarios': cm,
            'Compartidos': cp,
            'Reproducciones': rp
        })
        total_me_gusta_ui += mg
        total_comentarios_ui += cm
        total_compartidos_ui += cp
        total_reproducciones_ui += rp

    if plat_metrics_records_ui:
        plat_metrics_records_ui.append({
            'Plataforma': 'Total',
            'Me gusta': total_me_gusta_ui,
            'Comentarios': total_comentarios_ui,
            'Compartidos': total_compartidos_ui,
            'Reproducciones': total_reproducciones_ui
        })
        df_plat_metrics_ui = pd.DataFrame(plat_metrics_records_ui)
        st.dataframe(df_plat_metrics_ui, hide_index=True, width='stretch')
    else:
        st.info("No hay métricas por plataforma en el período seleccionado.")

    # Detalle de reportes (similar a tradicional)
    st.subheader("📄 Detalle de Reportes")
    st.dataframe(df_rs, hide_index=True, width='stretch')

    # Información del usuario para leyendas
    usuario = st.session_state.user if 'user' in st.session_state and st.session_state.user else {}
    indicativo_usuario = usuario.get('username', 'Sistema')
    nombre_usuario = usuario.get('full_name', 'Sistema')

    # Exportación
    st.subheader("📤 Exportar Reporte")
    with st.expander("Filtros de exportación", expanded=True):
        export_plataformas = ['Todas'] + sorted([p for p in df_rs['Plataforma'].dropna().unique().tolist() if str(p).strip()])
        export_plat_sel = st.selectbox("Plataforma a exportar", export_plataformas, key="rs_export_plat_sel")
        if export_plat_sel != 'Todas':
            df_export = df_rs[df_rs['Plataforma'] == export_plat_sel]
        else:
            df_export = df_rs
        st.caption(f"Registros a exportar: {len(df_export)}")

    colx, coly, colz = st.columns(3)
    # Excel
    with colx:
        if st.button("📊 Excel", key="rs_btn_excel", width='stretch'):
            buffer = io.BytesIO()
            # Recalcular distribuciones sobre export
            zonas_count_exp = df_export['Zona'].value_counts()
            df_zonas_exp = pd.DataFrame({
                'Zona': zonas_count_exp.index,
                'Cantidad': zonas_count_exp.values,
                'Porcentaje': (zonas_count_exp.values / max(len(df_export), 1) * 100).round(1)
            })
            plataformas_count_exp = df_export['Plataforma'].value_counts()
            df_plataformas_exp = pd.DataFrame({
                'Plataforma': plataformas_count_exp.index,
                'Cantidad': plataformas_count_exp.values,
                'Porcentaje': (plataformas_count_exp.values / max(len(df_export), 1) * 100).round(1)
            })

            # Métricas por plataforma (Me gusta, Comentarios, Compartidos, Reproducciones)
            try:
                with db.get_connection() as conn:
                    cur = conn.cursor()
                    if export_plat_sel != 'Todas':
                        cur.execute(
                            '''
                            SELECT plataforma_nombre,
                                   SUM(me_gusta) as me_gusta,
                                   SUM(comentarios) as comentarios,
                                   SUM(compartidos) as compartidos,
                                   SUM(reproducciones) as reproducciones
                            FROM estadisticas_rs
                            WHERE plataforma_nombre = ? AND fecha_reporte BETWEEN ? AND ?
                            GROUP BY plataforma_nombre
                            ORDER BY plataforma_nombre
                            ''',
                            (export_plat_sel, fecha_inicio_str, fecha_fin_str)
                        )
                    else:
                        cur.execute(
                            '''
                            SELECT plataforma_nombre,
                                   SUM(me_gusta) as me_gusta,
                                   SUM(comentarios) as comentarios,
                                   SUM(compartidos) as compartidos,
                                   SUM(reproducciones) as reproducciones
                            FROM estadisticas_rs
                            WHERE fecha_reporte BETWEEN ? AND ?
                            GROUP BY plataforma_nombre
                            ORDER BY plataforma_nombre
                            ''',
                            (fecha_inicio_str, fecha_fin_str)
                        )
                    rows_metrics = cur.fetchall() or []
            except Exception:
                rows_metrics = []

            total_me_gusta = total_comentarios = total_compartidos = total_reproducciones = 0
            plat_metrics_records = []
            for r in rows_metrics:
                mg = int(r['me_gusta'] or 0)
                cm = int(r['comentarios'] or 0)
                cp = int(r['compartidos'] or 0)
                rp = int(r['reproducciones'] or 0)
                plat_metrics_records.append({
                    'Plataforma': str(r['plataforma_nombre'] or ''),
                    'Me gusta': mg,
                    'Comentarios': cm,
                    'Compartidos': cp,
                    'Reproducciones': rp
                })
                total_me_gusta += mg
                total_comentarios += cm
                total_compartidos += cp
                total_reproducciones += rp

            # Totales
            plat_metrics_records.append({
                'Plataforma': 'Total',
                'Me gusta': total_me_gusta,
                'Comentarios': total_comentarios,
                'Compartidos': total_compartidos,
                'Reproducciones': total_reproducciones
            })
            df_plat_metrics = pd.DataFrame(plat_metrics_records)

            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                stats_df = pd.DataFrame({
                    'Métrica': ['Reporte', 'Período', 'Total Reportes', 'Estaciones Únicas', 'Zona Más Reportada', 'Plataforma Más Usada', 'Generado por'],
                    'Valor': ['Redes Sociales', fecha_rango_lbl, len(df_export), df_export['Indicativo'].nunique(),
                              (df_export['Zona'].mode().iloc[0] if not df_export['Zona'].mode().empty else 'N/A'),
                              (df_export['Plataforma'].mode().iloc[0] if not df_export['Plataforma'].mode().empty else 'N/A'),
                              f"{indicativo_usuario} - {nombre_usuario}"]
                })
                stats_df.to_excel(writer, sheet_name='Estadísticas', index=False)
                # Métricas por Plataforma
                try:
                    df_plat_metrics.to_excel(writer, sheet_name='Métricas por Plataforma', index=False)
                except Exception:
                    pass
                df_export.to_excel(writer, sheet_name='Datos Detallados', index=False)
                df_zonas_exp.to_excel(writer, sheet_name='Por Zona', index=False)
                df_plataformas_exp.to_excel(writer, sheet_name='Por Plataforma', index=False)

            buffer.seek(0)
            est_suffix = "" if export_plat_sel == 'Todas' else f"_{str(export_plat_sel).replace(' ', '_')}"
            st.download_button(
                label="⬇️ Descargar Excel",
                data=buffer,
                file_name=f"reporte_rs_{fecha_inicio_str}_a_{fecha_fin_str}{est_suffix}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width='stretch'
            )

    # CSV
    with coly:
        if st.button("📄 CSV", key="rs_btn_csv", width='stretch'):
            csv_bytes = df_export.to_csv(index=False).encode('utf-8-sig')
            est_suffix = "" if export_plat_sel == 'Todas' else f"_{str(export_plat_sel).replace(' ', '_')}"
            st.download_button(
                label="⬇️ Descargar CSV",
                data=csv_bytes,
                file_name=f"reporte_rs_{fecha_inicio_str}_a_{fecha_fin_str}{est_suffix}.csv",
                mime="text/csv",
                width='stretch'
            )

        # CSV de métricas por plataforma
        if st.button("📄 CSV Métricas", key="rs_btn_csv_metrics", width='stretch'):
            try:
                with db.get_connection() as conn:
                    cur = conn.cursor()
                    if export_plat_sel != 'Todas':
                        cur.execute(
                            '''
                            SELECT plataforma_nombre,
                                   SUM(me_gusta) as me_gusta,
                                   SUM(comentarios) as comentarios,
                                   SUM(compartidos) as compartidos,
                                   SUM(reproducciones) as reproducciones
                            FROM estadisticas_rs
                            WHERE plataforma_nombre = ? AND fecha_reporte BETWEEN ? AND ?
                            GROUP BY plataforma_nombre
                            ORDER BY plataforma_nombre
                            ''',
                            (export_plat_sel, fecha_inicio_str, fecha_fin_str)
                        )
                    else:
                        cur.execute(
                            '''
                            SELECT plataforma_nombre,
                                   SUM(me_gusta) as me_gusta,
                                   SUM(comentarios) as comentarios,
                                   SUM(compartidos) as compartidos,
                                   SUM(reproducciones) as reproducciones
                            FROM estadisticas_rs
                            WHERE fecha_reporte BETWEEN ? AND ?
                            GROUP BY plataforma_nombre
                            ORDER BY plataforma_nombre
                            ''',
                            (fecha_inicio_str, fecha_fin_str)
                        )
                    rows_metrics_csv = cur.fetchall() or []
            except Exception:
                rows_metrics_csv = []

            total_me_gusta = total_comentarios = total_compartidos = total_reproducciones = 0
            plat_metrics_records_csv = []
            for r in rows_metrics_csv:
                mg = int(r['me_gusta'] or 0)
                cm = int(r['comentarios'] or 0)
                cp = int(r['compartidos'] or 0)
                rp = int(r['reproducciones'] or 0)
                plat_metrics_records_csv.append({
                    'Plataforma': str(r['plataforma_nombre'] or ''),
                    'Me gusta': mg,
                    'Comentarios': cm,
                    'Compartidos': cp,
                    'Reproducciones': rp
                })
                total_me_gusta += mg
                total_comentarios += cm
                total_compartidos += cp
                total_reproducciones += rp

            plat_metrics_records_csv.append({
                'Plataforma': 'Total',
                'Me gusta': total_me_gusta,
                'Comentarios': total_comentarios,
                'Compartidos': total_compartidos,
                'Reproducciones': total_reproducciones
            })
            df_plat_metrics_csv = pd.DataFrame(plat_metrics_records_csv)
            csv_bytes_metrics = df_plat_metrics_csv.to_csv(index=False).encode('utf-8-sig')
            est_suffix = "" if export_plat_sel == 'Todas' else f"_{str(export_plat_sel).replace(' ', '_')}"
            st.download_button(
                label="⬇️ Descargar CSV (Métricas por Plataforma)",
                data=csv_bytes_metrics,
                file_name=f"reporte_rs_metricas_{fecha_inicio_str}_a_{fecha_fin_str}{est_suffix}.csv",
                mime="text/csv",
                width='stretch'
            )

    # PDF
    with colz:
        if st.button("📋 PDF", key="rs_btn_pdf", width='stretch'):
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image, HRFlowable
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.lib.enums import TA_CENTER
            import os

            buffer = io.BytesIO()

            # Etiqueta dinámica de encabezado por sección
            header_current_platform = {
                'label': (export_plat_sel if export_plat_sel != 'Todas' else 'Todas las Plataformas')
            }

            # Preparar variables de fecha y título como en Tradicional
            fi_fmt = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').strftime('%d/%m/%y')
            ff_fmt = datetime.strptime(fecha_fin_str, '%Y-%m-%d').strftime('%d/%m/%y')
            fecha_formateada = fi_fmt if fecha_inicio_str == fecha_fin_str else f"{fi_fmt} - {ff_fmt}"
            evento_nombre = "Redes Sociales"

            # Encabezado y pie de página (adaptado a Plataforma)
            def add_header_footer(canvas, doc):
                canvas.saveState()
                canvas.setFont('Helvetica', 4)
                canvas.setFillColor(colors.HexColor('#333333'))
                evento = (evento_nombre[:12] + '...') if len(evento_nombre) > 15 else evento_nombre
                header_text = f"{evento} | {fecha_formateada} | Plataforma: {header_current_platform['label']} | Página {canvas.getPageNumber()}"
                # Encabezado: parte superior del área de contenido
                canvas.drawString(doc.leftMargin, doc.height + doc.bottomMargin + 5, header_text)
                # Pie: línea divisoria inferior
                canvas.setStrokeColor(colors.HexColor('#CCCCCC'))
                canvas.setLineWidth(0.1)
                canvas.line(doc.leftMargin, doc.bottomMargin + 2, doc.width + doc.leftMargin, doc.bottomMargin + 2)
                canvas.restoreState()

            # Estilos
            styles = getSampleStyleSheet()
            # Copiado del tradicional
            info_style = ParagraphStyle(
                'InfoStyle',
                parent=styles['Normal'],
                fontSize=10,
                spaceAfter=4,
                textColor=colors.HexColor('#333333'),
                alignment=1,
                leading=12
            )
            section_style = ParagraphStyle('SectionStyle', parent=styles['Normal'], fontSize=12, fontName='Helvetica-Bold', textColor=colors.HexColor('#1f4e79'), spaceBefore=0, spaceAfter=0, leading=12)

            # Dataset export a usar en PDF
            df_pdf = df_export.copy()

            # Recalcular métricas para PDF
            estaciones_unicas_pdf = df_pdf['Indicativo'].nunique()
            zona_mas_pdf = (df_pdf['Zona'].mode().iloc[0] if not df_pdf['Zona'].mode().empty else "N/A")
            plataforma_mas_pdf = (df_pdf['Plataforma'].mode().iloc[0] if not df_pdf['Plataforma'].mode().empty else "N/A")
            cobertura_estados_pdf = df_pdf['Estado'].nunique() if 'Estado' in df_pdf.columns else 0

            zonas_count_pdf = df_pdf['Zona'].value_counts()
            df_zonas_pdf = pd.DataFrame({'Zona': zonas_count_pdf.index, 'Cantidad': zonas_count_pdf.values, 'Porcentaje': (zonas_count_pdf.values / max(len(df_pdf), 1) * 100).round(1)})
            plataformas_count_pdf = df_pdf['Plataforma'].value_counts()
            df_plataformas_pdf = pd.DataFrame({'Plataforma': plataformas_count_pdf.index, 'Cantidad': plataformas_count_pdf.values, 'Porcentaje': (plataformas_count_pdf.values / max(len(df_pdf), 1) * 100).round(1)})

            # Documento
            doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=54, bottomMargin=36)
            story = []

            # Encabezado con logo y título (idéntico al tradicional)
            logo_path = os.path.join(os.path.dirname(__file__), 'assets', 'LogoFMRE_medium.png')
            header_style = ParagraphStyle(
                'HeaderStyle',
                fontName='Helvetica-Bold',
                fontSize=11,
                leading=13,
                spaceBefore=0,
                spaceAfter=0,
                alignment=TA_CENTER,
                textColor=colors.HexColor('#006400'),
                leftIndent=0,
                rightIndent=0
            )

            if os.path.exists(logo_path):
                header_data = [[
                    Image(logo_path, width=0.8*inch, height=0.8*inch, kind='proportional'),
                    Paragraph("FEDERACIÓN MEXICANA DE RADIOEXPERIMENTADORES", header_style)
                ]]
                header_table = Table(header_data, colWidths=[1.0*inch, 5*inch], rowHeights=[0.7*inch])
                header_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                    ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('LEFTPADDING', (0, 0), (-1, -1), 4),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                    ('TEXTCOLOR', (1, 0), (1, 0), colors.HexColor('#2c3e50')),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
                    ('LINEAFTER', (0, 0), (0, 0), 0.5, colors.HexColor('#DDDDDD')),
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8F9FA'))
                ]))
                story.append(Spacer(1, 6))
                story.append(header_table)
                story.append(Spacer(1, 6))
            else:
                story.append(Paragraph("FEDERACIÓN MEXICANA DE RADIOEXPERIMENTADORES", ParagraphStyle('HeaderNoLogo', fontName='Helvetica-Bold', fontSize=8, alignment=TA_CENTER, spaceAfter=2)))
                story.append(Spacer(1, 2))

            # Información general
            story.append(Paragraph(f"<b>Evento:</b> Redes Sociales", info_style))
            story.append(Paragraph(f"<b>Fecha del Evento:</b> {fecha_formateada}", info_style))
            story.append(Paragraph(f"<b>Fecha de Generación:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", info_style))
            story.append(Paragraph(f"<b>Generado por:</b> {indicativo_usuario} - {nombre_usuario}", info_style))
            story.append(Spacer(1, 2))

            # Línea divisoria
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#CCCCCC')))
            story.append(Paragraph("Estadísticas del evento", section_style))
            story.append(Spacer(1, 8))

            # Estadísticas (generales, sin interacciones)
            stats = [
                ['Métrica', 'Valor', 'Detalles'],
                ['Total de Reportes', str(len(df_pdf)), f"Participantes activos: {len(df_pdf)}"],
                ['Estaciones Únicas', str(estaciones_unicas_pdf), "Diferentes estaciones que reportaron"],
                ['Zona Más Reportada', zona_mas_pdf, "Concentración geográfica principal"],
                ['Plataforma Más Usada', plataforma_mas_pdf, "Plataforma predominante"],
                ['Cobertura Geográfica', f"{cobertura_estados_pdf} estados", "Alcance territorial del período"]
            ]
            stats_table = Table(stats)
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#333333')),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6'))
            ]))
            story.append(stats_table)
            story.append(Spacer(1, 8))

            # Métricas por plataforma (Me gusta, Comentarios, Compartidos, Reproducciones)
            story.append(Paragraph("Métricas por plataforma", section_style))
            story.append(Spacer(1, 8))
            plat_metrics_data = [['Plataforma', 'Me gusta', 'Comentarios', 'Compartidos', 'Reproducciones']]
            try:
                with db.get_connection() as conn:
                    cur = conn.cursor()
                    if export_plat_sel != 'Todas':
                        cur.execute(
                            '''
                            SELECT plataforma_nombre,
                                   SUM(me_gusta) as me_gusta,
                                   SUM(comentarios) as comentarios,
                                   SUM(compartidos) as compartidos,
                                   SUM(reproducciones) as reproducciones
                            FROM estadisticas_rs
                            WHERE plataforma_nombre = ? AND fecha_reporte BETWEEN ? AND ?
                            GROUP BY plataforma_nombre
                            ORDER BY plataforma_nombre
                            ''',
                            (export_plat_sel, fecha_inicio_str, fecha_fin_str)
                        )
                    else:
                        cur.execute(
                            '''
                            SELECT plataforma_nombre,
                                   SUM(me_gusta) as me_gusta,
                                   SUM(comentarios) as comentarios,
                                   SUM(compartidos) as compartidos,
                                   SUM(reproducciones) as reproducciones
                            FROM estadisticas_rs
                            WHERE fecha_reporte BETWEEN ? AND ?
                            GROUP BY plataforma_nombre
                            ORDER BY plataforma_nombre
                            ''',
                            (fecha_inicio_str, fecha_fin_str)
                        )
                    rows = cur.fetchall() or []
            except Exception:
                rows = []

            total_me_gusta = total_comentarios = total_compartidos = total_reproducciones = 0
            for r in rows:
                mg = int(r['me_gusta'] or 0)
                cm = int(r['comentarios'] or 0)
                cp = int(r['compartidos'] or 0)
                rp = int(r['reproducciones'] or 0)
                plat_metrics_data.append([
                    str(r['plataforma_nombre'] or ''), str(mg), str(cm), str(cp), str(rp)
                ])
                total_me_gusta += mg
                total_comentarios += cm
                total_compartidos += cp
                total_reproducciones += rp

            # Fila de totales
            plat_metrics_data.append([
                'Total', str(total_me_gusta), str(total_comentarios), str(total_compartidos), str(total_reproducciones)
            ])

            plat_metrics_table = Table(plat_metrics_data)
            plat_metrics_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor('#f8f9fa')),
                ('TEXTCOLOR', (0, 1), (-1, -2), colors.HexColor('#333333')),
                ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -2), 8),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e9ecef')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6'))
            ]))
            story.append(plat_metrics_table)
            story.append(Spacer(1, 10))

            # Distribución por zona
            story.append(Paragraph("Distribución por zona geográfica", section_style))
            story.append(Spacer(1, 10))
            zonas_data = [['Zona', 'Cantidad', 'Porcentaje']]
            for _, row in df_zonas_pdf.iterrows():
                zonas_data.append([str(row['Zona']), str(int(row['Cantidad'])), f"{row['Porcentaje']:.1f}%"])
            zonas_table = Table(zonas_data)
            zonas_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5f2d')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#90EE90'))
            ]))
            story.append(zonas_table)
            story.append(Spacer(1, 8))

            # Distribución por plataforma
            story.append(Paragraph("Distribución por plataforma", section_style))
            story.append(Spacer(1, 10))
            plat_data = [['Plataforma', 'Cantidad', 'Porcentaje']]
            for _, row in df_plataformas_pdf.iterrows():
                plat_data.append([str(row['Plataforma']), str(int(row['Cantidad'])), f"{row['Porcentaje']:.1f}%"])
            plat_table = Table(plat_data)
            plat_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8B4513')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#DEB887'))
            ]))
            story.append(plat_table)

            # Página de detalle (Total)
            story.append(PageBreak())
            story.append(Paragraph("Reporte de Actividad (Total)", section_style))
            story.append(Spacer(1, 10))
            reportes_data = [['Indicativo', 'Nombre', 'Estado', 'Ciudad', 'Zona', 'Plataforma']]
            for _, row in df_pdf.iterrows():
                reportes_data.append([
                    row.get('Indicativo', ''), row.get('Nombre', ''),
                    row.get('Estado', ''), row.get('Ciudad', ''), row.get('Zona', ''), row.get('Plataforma', '')
                ])
            # Dar más espacio a 'Plataforma' y ajustar anchos totales a 6.5"
            reportes_table = Table(reportes_data, colWidths=[1.0*inch, 1.5*inch, 0.9*inch, 1.0*inch, 0.5*inch, 1.6*inch])
            reportes_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#333333')),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6'))
            ]))
            story.append(reportes_table)

            # Desglose por plataforma
            plataformas_list = [p for p in df_pdf['Plataforma'].dropna().unique().tolist() if str(p).strip()]
            for plat in sorted(plataformas_list):
                df_p = df_pdf[df_pdf['Plataforma'] == plat]
                if df_p.empty:
                    continue
                story.append(PageBreak())
                story.append(Paragraph(f"Plataforma: {plat}", section_style))
                story.append(Spacer(1, 8))
                # Métricas individuales por plataforma
                try:
                    with db.get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute(
                            '''
                            SELECT 
                                SUM(me_gusta) as me_gusta,
                                SUM(comentarios) as comentarios,
                                SUM(compartidos) as compartidos,
                                SUM(reproducciones) as reproducciones
                            FROM estadisticas_rs
                            WHERE plataforma_nombre = ? AND fecha_reporte BETWEEN ? AND ?
                            ''',
                            (plat, fecha_inicio_str, fecha_fin_str)
                        )
                        row = cur.fetchone()
                        me_gusta_p = int((row['me_gusta'] if row and row['me_gusta'] is not None else 0))
                        comentarios_p = int((row['comentarios'] if row and row['comentarios'] is not None else 0))
                        compartidos_p = int((row['compartidos'] if row and row['compartidos'] is not None else 0))
                        reproducciones_p = int((row['reproducciones'] if row and row['reproducciones'] is not None else 0))
                except Exception:
                    me_gusta_p = comentarios_p = compartidos_p = reproducciones_p = 0

                estaciones_unicas_p = df_p['Indicativo'].nunique()
                zona_mas_p = (df_p['Zona'].mode().iloc[0] if not df_p['Zona'].mode().empty else "N/A")
                cobertura_estados_p = df_p['Estado'].nunique() if 'Estado' in df_p.columns else 0

                stats_p = [
                    ['Métrica', 'Valor', 'Detalles'],
                    ['Total de Reportes', str(len(df_p)), f"Participantes activos: {len(df_p)}"],
                    ['Estaciones Únicas', str(estaciones_unicas_p), "Diferentes estaciones que reportaron"],
                    ['Zona Más Reportada', zona_mas_p, "Concentración geográfica principal"],
                    ['Cobertura Geográfica', f"{cobertura_estados_p} estados", "Alcance territorial del período"],
                    ['Me gusta', str(me_gusta_p), "Interacciones de 'me gusta'"],
                    ['Comentarios', str(comentarios_p), "Comentarios recibidos"],
                    ['Compartidos', str(compartidos_p), "Veces compartido"],
                    ['Reproducciones', str(reproducciones_p), "Reproducciones totales"]
                ]
                stats_table_p = Table(stats_p)
                stats_table_p.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#333333')),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6'))
                ]))
                story.append(stats_table_p)
                story.append(Spacer(1, 8))
                # Distribución por zona (plataforma)
                zonas_count_p = df_p['Zona'].value_counts()
                df_zonas_p = pd.DataFrame({'Zona': zonas_count_p.index, 'Cantidad': zonas_count_p.values, 'Porcentaje': (zonas_count_p.values / max(len(df_p), 1) * 100).round(1)})
                zonas_data_p = [['Zona', 'Cantidad', 'Porcentaje']]
                for _, row in df_zonas_p.iterrows():
                    zonas_data_p.append([str(row['Zona']), str(int(row['Cantidad'])), f"{row['Porcentaje']:.1f}%"])
                zonas_table_p = Table(zonas_data_p)
                zonas_table_p.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5f2d')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#90EE90'))
                ]))
                story.append(zonas_table_p)
                story.append(Spacer(1, 8))
                # Detalle por plataforma
                story.append(Paragraph("Detalle de Reportes", section_style))
                story.append(Spacer(1, 6))
                reportes_p = [['Indicativo', 'Nombre', 'Estado', 'Ciudad', 'Zona']]
                for _, row in df_p.iterrows():
                    reportes_p.append([
                        row.get('Indicativo', ''), row.get('Nombre', ''),
                        row.get('Estado', ''), row.get('Ciudad', ''), row.get('Zona', '')
                    ])
                # Ajustar anchos para 5 columnas a 6.5"
                reportes_table_p = Table(reportes_p, colWidths=[1.0*inch, 2.0*inch, 1.2*inch, 1.8*inch, 0.5*inch])
                reportes_table_p.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#333333')),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 7),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6'))
                ]))
                story.append(reportes_table_p)

            doc.build(story, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
            buffer.seek(0)
            est_suffix = "" if export_plat_sel == 'Todas' else f"_{str(export_plat_sel).replace(' ', '_')}"
            st.download_button(
                label="⬇️ Descargar PDF",
                data=buffer,
                file_name=f"reporte_rs_{fecha_inicio_str}_a_{fecha_fin_str}{est_suffix}.pdf",
                mime="application/pdf",
                width='stretch'
            )

def show_actividad_general_report():
    """Muestra reporte de actividad general con filtros"""
    st.subheader("📈 Reporte de Actividad General")

    # Filtros de fecha
    col1, col2 = st.columns(2)

    with col1:
        fecha_inicio = st.date_input(
            "Fecha inicio",
            value=datetime.now().replace(day=1),  # Primer día del mes actual
            key="actividad_fecha_inicio"
        )

    with col2:
        fecha_fin = st.date_input(
            "Fecha fin",
            value=datetime.now(),  # Fecha actual
            key="actividad_fecha_fin"
        )

    if fecha_inicio > fecha_fin:
        st.error("❌ La fecha de inicio debe ser anterior a la fecha de fin")
        return

    try:
        # Convertir fechas para consulta
        fecha_inicio_str = fecha_inicio.strftime('%Y-%m-%d')
        fecha_fin_str = fecha_fin.strftime('%Y-%m-%d')

        # Obtener estadísticas generales
        reportes, estadisticas = db.get_reportes_por_fecha_rango(fecha_inicio_str, fecha_fin_str)

        actividad_por_fecha = None
        df_actividad = None
        dia_mas_activo_label = "Sin datos"
        dia_mas_activo_delta = None
        dia_menos_activo_label = "Sin datos"
        dia_menos_activo_delta = None

        # Preparar datos de actividad diaria
        if reportes:
            import pandas as pd
            df_actividad = pd.DataFrame([{
                'Fecha': r.get('fecha_reporte', ''),
                'Indicativo': r.get('indicativo', ''),
                'Sistema': r.get('sistema', ''),
                'Zona': r.get('zona', ''),
                'Estado': r.get('estado', '')
            } for r in reportes])

            def _parse_fecha(valor: str | None) -> pd.Timestamp | None:
                if not valor:
                    return None

                valor = str(valor).strip()

                formatos = [
                    '%d/%m/%Y %H:%M:%S',
                    '%d/%m/%Y',
                    '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%d',
                ]

                for fmt in formatos:
                    try:
                        return datetime.strptime(valor, fmt)
                    except ValueError:
                        continue

                return None

            df_actividad['Fecha'] = df_actividad['Fecha'].apply(_parse_fecha)
            df_actividad = df_actividad.dropna(subset=['Fecha'])
            df_actividad['Dia'] = df_actividad['Fecha'].dt.strftime('%Y-%m-%d')

            # Agrupar por día usando fecha_reporte
            actividad_por_fecha = (
                df_actividad
                .groupby('Dia')
                .size()
                .reset_index(name='Reportes')
                .sort_values('Dia')
            )

            if not actividad_por_fecha.empty:
                dia_mas_activo = actividad_por_fecha.loc[actividad_por_fecha['Reportes'].idxmax()]
                dia_mas_activo_label = dia_mas_activo['Dia']
                dia_mas_activo_delta = f"{int(dia_mas_activo['Reportes'])} reportes"

                dia_menos_activo = actividad_por_fecha.loc[actividad_por_fecha['Reportes'].idxmin()]
                dia_menos_activo_label = dia_menos_activo['Dia']
                dia_menos_activo_delta = f"{int(dia_menos_activo['Reportes'])} reportes"

        # Mostrar métricas principales
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            st.metric("Total de Reportes", estadisticas.get('total_reportes', 0))

        with col2:
            st.metric("Estaciones Únicas", estadisticas.get('estaciones_unicas', 0))

        with col3:
            dias_con_actividad = (fecha_fin - fecha_inicio).days + 1
            st.metric("Días de Período", dias_con_actividad)

        with col4:
            st.metric("Día con más reportes", dia_mas_activo_label, dia_mas_activo_delta)

        with col5:
            st.metric("Día con menos reportes", dia_menos_activo_label, dia_menos_activo_delta)

        # Gráfico de actividad por día
        if reportes:
            st.subheader("📅 Actividad por Día")

            # Gráfico de barras
            st.bar_chart(actividad_por_fecha.set_index('Dia'))

            # Tabla detallada por día
            st.dataframe(actividad_por_fecha.rename(columns={'Dia': 'Día'}))

            # Tabla de resumen
            st.subheader("📋 Resumen por Sistema")
            resumen_sistemas = df_actividad['Sistema'].value_counts()
            st.dataframe(resumen_sistemas)

    except Exception as e:
        st.error(f"Error al cargar el reporte: {str(e)}")

def show_geografico_report():
    """Muestra análisis geográfico por zonas y estados"""
    st.subheader("🌍 Análisis Geográfico")

    # Filtros de fecha
    col1, col2 = st.columns(2)

    with col1:
        fecha_inicio = st.date_input(
            "Fecha inicio",
            value=datetime.now().replace(day=1),
            key="geo_fecha_inicio"
        )

    with col2:
        fecha_fin = st.date_input(
            "Fecha fin",
            value=datetime.now(),
            key="geo_fecha_fin"
        )

    if fecha_inicio > fecha_fin:
        st.error("❌ La fecha de inicio debe ser anterior a la fecha de fin")
        return

    try:
        # Convertir fechas para consulta
        fecha_inicio_str = fecha_inicio.strftime('%Y-%m-%d')
        fecha_fin_str = fecha_fin.strftime('%Y-%m-%d')

        # Obtener datos geográficos
        reportes, estadisticas = db.get_reportes_por_fecha_rango(fecha_inicio_str, fecha_fin_str)

        if reportes:
            import pandas as pd
            
            # Mapeo de nombres alternativos de estados
            MAPEO_ESTADOS = {
                'México': 'Estado de México',
                'MEXICO': 'Estado de México',
                'MEX': 'Estado de México',
                'mexico': 'Estado de México',
                'mex': 'Estado de México'
            }
            
            df_geografico = pd.DataFrame([{
                'Indicativo': r.get('indicativo', ''),
                'Estado': r.get('estado', ''),
                'Ciudad': r.get('ciudad', ''),
                'Zona': r.get('zona', ''),
                'Sistema': r.get('sistema', '')
            } for r in reportes])
            
            # Estandarizar los nombres de los estados antes de cualquier procesamiento
            df_geografico['Estado'] = df_geografico['Estado'].fillna('Desconocido').str.strip()
            df_geografico['Estado'] = df_geografico['Estado'].apply(
                lambda x: MAPEO_ESTADOS.get(x, x) if x in MAPEO_ESTADOS else x
            )
            
            # Normalizar los nombres de los estados para comparación
            df_geografico['estado_norm'] = df_geografico['Estado'].apply(_normalizar_estado_nombre)

            st.subheader("🗺️ Mapa de Reportes por Estado")

            if px is None:
                st.info("Instala la librería `plotly` para visualizar el mapa interactivo (pip install plotly).")
            else:
                estado_label_map = {}
                for norm, original in zip(df_geografico['estado_norm'], df_geografico['Estado']):
                    if norm and norm not in estado_label_map:
                        estado_label_map[norm] = original

                df_estados_validos = df_geografico[df_geografico['estado_norm'] != '']

                conteo_por_estado = (
                    df_estados_validos
                    .groupby('estado_norm')
                    .size()
                    .reset_index(name='reportes')
                )

                if conteo_por_estado.empty:
                    st.info("No hay estados válidos para graficar en el mapa.")
                else:
                    conteo_por_estado['Estado'] = conteo_por_estado['estado_norm'].apply(
                        lambda s: estado_label_map.get(s, 'Desconocido')
                    )
                    conteo_por_estado['lat'] = conteo_por_estado['estado_norm'].map(
                        lambda s: MEXICO_STATE_COORDS.get(s, (None, None))[0]
                    )
                    conteo_por_estado['lon'] = conteo_por_estado['estado_norm'].map(
                        lambda s: MEXICO_STATE_COORDS.get(s, (None, None))[1]
                    )

                    conteo_valido = conteo_por_estado.dropna(subset=['lat', 'lon'])

                    geojson_data = _load_mexico_states_geojson() if go is not None else None
                    render_fallback_scatter = True

                    if geojson_data and go is not None:
                        geojson_name_map = {}
                        for feature in geojson_data.get('features', []):
                            nombre_estado = feature.get('properties', {}).get('state_name')
                            if not nombre_estado:
                                continue
                            geo_norm = _normalizar_estado_nombre(nombre_estado)
                            geojson_name_map[geo_norm] = nombre_estado

                        if not geojson_name_map:
                            st.warning("El archivo GeoJSON no contiene estados válidos para graficar.")
                        else:
                            conteo_por_estado = conteo_por_estado.copy()
                            conteo_por_estado['geo_norm'] = conteo_por_estado['estado_norm'].map(
                                lambda s: GEOJSON_STATE_ALIASES.get(s, s)
                            )

                            conteo_por_estado['geo_norm'] = conteo_por_estado['geo_norm'].where(
                                conteo_por_estado['geo_norm'].isin(geojson_name_map.keys())
                            )

                            unmatched_states = (
                                conteo_por_estado[conteo_por_estado['geo_norm'].isna()][['Estado']]
                                .drop_duplicates()
                            )

                            geo_df = (
                                pd.DataFrame(
                                    [
                                        {
                                            'geo_norm': norm,
                                            'feature_name': original,
                                        }
                                        for norm, original in geojson_name_map.items()
                                    ]
                                )
                                .drop_duplicates(subset='geo_norm')
                            )

                            choropleth_df = geo_df.merge(
                                conteo_por_estado[['geo_norm', 'Estado', 'reportes']],
                                on='geo_norm',
                                how='left'
                            )
                            choropleth_df['reportes'] = choropleth_df['reportes'].fillna(0)
                            choropleth_df['Estado'] = choropleth_df['Estado'].fillna(choropleth_df['feature_name'])

                            render_fallback_scatter = False
                            fig = go.Figure()

                            fig.add_trace(go.Choropleth(
                                geojson=geojson_data,
                                featureidkey="properties.state_name",
                                locations=choropleth_df['feature_name'],
                                z=choropleth_df['reportes'],
                                zmin=0,
                                colorscale=[
                                    [0.0, "#f2f2f2"],   # very low -> light gray
                                    [0.15, "#e0e0e0"],
                                    [0.35, "#c8e6c9"],  # light green tint
                                    [0.6, "#81c784"],   # medium green
                                    [0.8, "#43a047"],   # darker green
                                    [1.0, "#1b5e20"]    # highest -> deep green
                                ],
                                colorbar_title="Reportes",
                                marker_line_color="rgb(120, 120, 120)",
                                marker_line_width=0.8,
                                hovertext=[
                                    f"{row.Estado}<br>Reportes: {int(row.reportes)}"
                                    for row in choropleth_df.itertuples()
                                ],
                                hoverinfo="text"
                            ))

                            if not conteo_valido.empty:
                                tamaño_base = 12
                                fig.add_trace(go.Scattergeo(
                                    lat=conteo_valido['lat'],
                                    lon=conteo_valido['lon'],
                                    text=[
                                        f"{row.Estado}<br>Reportes: {row.reportes}"
                                        for row in conteo_valido.itertuples()
                                    ],
                                    hoverinfo="text",
                                    mode="markers",
                                    marker=dict(
                                        size=conteo_valido['reportes'].clip(lower=1) * 2 + tamaño_base,
                                        color="rgba(33, 76, 229, 0.65)",
                                        line=dict(color="rgba(15, 40, 160, 0.8)", width=1.5)
                                    ),
                                    name="Reportes"
                                ))

                            fig.update_geos(
                                fitbounds="locations",
                                visible=False,
                                showcountries=True,
                                countrycolor="rgb(90, 90, 90)",
                                showland=True,
                                landcolor="rgb(235, 235, 235)",
                                showsubunits=True,
                                subunitcolor="rgb(150, 150, 150)",
                                subunitwidth=0.8,
                                showcoastlines=True,
                                coastlinecolor="rgb(120, 120, 120)"
                            )
                            fig.update_layout(
                                margin=dict(l=0, r=0, t=0, b=0),
                                height=600
                            )

                            st.plotly_chart(fig, use_container_width=True)

                            if not unmatched_states.empty:
                                st.caption(
                                    "⚠️ Estados sin coincidencia en el GeoJSON: "
                                    + ", ".join(sorted(unmatched_states['Estado'].unique()))
                                )

                    if render_fallback_scatter:
                        if conteo_valido.empty:
                            st.warning("No se pudieron ubicar coordenadas para los estados reportados.")
                        else:
                            fig = px.scatter_geo(
                                conteo_valido,
                                lat='lat',
                                lon='lon',
                                size='reportes',
                                size_max=40,
                                color='reportes',
                                hover_name='Estado',
                                hover_data={'reportes': True, 'lat': False, 'lon': False},
                                projection='natural earth'
                            )

                            fig.update_geos(
                                scope='north america',
                                center=dict(lat=23.0, lon=-102.0),
                                projection_scale=5.0,
                                showland=True,
                                landcolor='rgb(235, 235, 235)',
                                showcountries=True,
                                countrycolor='rgb(204, 204, 204)',
                                showsubunits=True,
                                subunitcolor='rgb(160, 160, 160)',
                                subunitwidth=1,
                                showcoastlines=True,
                                coastlinecolor='rgb(150, 150, 150)'
                            )
                            fig.update_layout(
                                coloraxis_colorbar=dict(title='Reportes'),
                                margin=dict(l=0, r=0, t=0, b=0)
                            )

                            st.plotly_chart(fig, use_container_width=True)

                estados_sin_coordenadas = conteo_por_estado[conteo_por_estado[['lat', 'lon']].isna().any(axis=1)]
                if not estados_sin_coordenadas.empty:
                    st.caption(
                        "⚠️ Estados sin coordenadas mapeadas: "
                        + ", ".join(sorted(estados_sin_coordenadas['Estado'].unique()))
                    )

            # Estandarizar los nombres de los estados antes de buscar la zona
            df_geografico['Estado'] = df_geografico['Estado'].apply(
                lambda x: MAPEO_ESTADOS.get(x, x) if pd.notna(x) and x != 'Desconocido' else x
            )
            
            # Obtener el mapeo de estados a zonas desde la base de datos
            estados_zonas = db.get_estados_zonas()
            
            # Mostrar estados que no tienen zona asignada (solo para depuración)
            estados_unicos = df_geografico['Estado'].unique()
            estados_sin_zona = [e for e in estados_unicos if e not in estados_zonas and pd.notna(e) and e != '']
            
            if estados_sin_zona:
                st.warning(f"⚠️ Los siguientes estados no tienen zona asignada y aparecerán como 'DESCONOCIDA': {', '.join(estados_sin_zona)}")
                
                # Mostrar registros problemáticos para depuración
                registros_problematicos = df_geografico[df_geografico['Estado'].isin(estados_sin_zona)]
                with st.expander("Ver registros problemáticos"):
                    st.write("Registros con estados sin zona asignada (se mostrarán como 'DESCONOCIDA'):")
                    st.dataframe(registros_problematicos[['Indicativo', 'Estado', 'Ciudad']])
            
            # Agregar la zona a cada reporte basado en el estado
            df_geografico['Zona'] = df_geografico['Estado'].map(
                lambda x: estados_zonas.get(x, 'DESCONOCIDA') if pd.notna(x) and x != '' else 'DESCONOCIDA'
            )
            
            # Calcular conteo de zonas para la sección de zonas más activas
            zonas_count = df_geografico['Zona'].value_counts()
            
            # Sección de Distribución Detallada
            st.subheader("📋 Distribución Detallada", divider='rainbow')
            
            # Mostrar tablas en 4 columnas
            cols = st.columns(4)
            
            # Definir las zonas en el orden deseado
            zonas_orden = ['XE1', 'XE2', 'XE3', 'EXT']
            
            # Mostrar cada zona en su propia columna
            for idx, zona in enumerate(zonas_orden):
                with cols[idx % 4]:
                    # Filtrar reportes de esta zona
                    if zona == 'EXT':
                        # Para EXT, incluir también 'Extranjero' si existe
                        df_zona = df_geografico[df_geografico['Zona'].isin(['EXT', 'Extranjero'])]
                        titulo = 'Zona Extranjera'
                    else:
                        df_zona = df_geografico[df_geografico['Zona'] == zona]
                        titulo = f'Zona {zona}'
                    
                    if not df_zona.empty:
                        # Contar reportes totales para esta zona
                        total_reportes = len(df_zona)
                        
                        # Mostrar encabezado de zona con el total
                        st.markdown(f"**{titulo}**  \n*{total_reportes} reportes*")
                        
                        # Contar reportes por estado en esta zona
                        if zona != 'EXT':  # Para zonas que no son EXT, mostrar el desglose
                            # Filtrar solo los estados que pertenecen a esta zona según la tabla qth
                            estados_en_zona = [estado for estado, z in estados_zonas.items() if z == zona]
                            df_zona_filtrado = df_geografico[df_geografico['Estado'].isin(estados_en_zona)]
                            
                            if not df_zona_filtrado.empty:
                                conteo_estados = df_zona_filtrado['Estado'].value_counts()
                                st.dataframe(
                                    conteo_estados.rename('Reportes'),
                                    width='stretch',
                                    height=min(300, 50 + len(conteo_estados) * 35)
                                )
                    else:
                        st.markdown(f"**{titulo}**  \n*0 reportes*")
                        st.write("Sin reportes")

            # Sección de Zonas Más Activas
            st.subheader("🏆 Zonas Más Activas", divider='rainbow')
            top_zonas = zonas_count.head(5)
            
            # Crear un DataFrame para mostrar la tabla
            df_top_zonas = pd.DataFrame({
                'Zona': top_zonas.index,
                'Reportes': top_zonas.values,
                'Porcentaje': (top_zonas.values / len(df_geografico) * 100).round(1).astype(str) + '%'
            })
            
            # Mostrar la tabla con estilos
            st.dataframe(
                df_top_zonas,
                column_config={
                    'Zona': 'Zona',
                    'Reportes': st.column_config.NumberColumn('Reportes'),
                    'Porcentaje': 'Porcentaje'
                },
                hide_index=True,
                width='stretch'
            )
            
            # Sección de Gráficos de Barras
            st.subheader("📊 Reportes por Zona y Estado", divider='rainbow')
            
            # Gráficos en columnas
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### 📍 Reportes por Zona")
                if not zonas_count.empty:
                    # Crear un DataFrame con los datos
                    df_zonas = zonas_count.reset_index()
                    df_zonas.columns = ['Zona', 'Cantidad']
                    
                    # Generar colores únicos para cada barra
                    n_colors = len(df_zonas)
                    colors = px.colors.qualitative.Plotly[:n_colors]
                    
                    # Crear el gráfico con colores personalizados
                    fig = px.bar(
                        df_zonas, 
                        x='Zona', 
                        y='Cantidad',
                        color='Zona',
                        color_discrete_sequence=colors,
                        title='Reportes por Zona'
                    )
                    
                    # Mejorar el diseño
                    fig.update_layout(
                        showlegend=False,
                        xaxis_title='Zona',
                        yaxis_title='Cantidad de Reportes',
                        xaxis_tickangle=-45
                    )
                    
                    # Mostrar el gráfico
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No hay datos de zonas para mostrar")
            
            with col2:
                st.markdown("#### 🏙️ Reportes por Estado")
                estados_count = df_geografico['Estado'].value_counts().head(10)  # Tomar solo los 10 primeros
                if not estados_count.empty:
                    # Crear un DataFrame con los datos
                    df_estados = estados_count.reset_index()
                    df_estados.columns = ['Estado', 'Cantidad']
                    
                    # Generar colores únicos para cada barra
                    n_colors = len(df_estados)
                    colors = px.colors.qualitative.Dark24[:n_colors]  # Usar una paleta diferente
                    
                    # Crear el gráfico con colores personalizados
                    fig = px.bar(
                        df_estados, 
                        x='Estado', 
                        y='Cantidad',
                        color='Estado',
                        color_discrete_sequence=colors,
                        title='Top 10 Estados con más Reportes',
                        text='Cantidad'
                    )
                    
                    # Mejorar el diseño
                    fig.update_layout(
                        showlegend=False,
                        xaxis_title='Estado',
                        yaxis_title='Cantidad de Reportes',
                        xaxis_tickangle=-45,
                        height=500  # Altura fija para mejor visualización
                    )
                    
                    # Mostrar los valores en las barras
                    fig.update_traces(
                        textposition='outside',
                        textfont_size=12
                    )
                    
                    # Mostrar el gráfico
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No hay datos de estados para mostrar")

        else:
            st.info("No hay datos para el período seleccionado")

    except Exception as e:
        st.error(f"Error al cargar el análisis geográfico: {str(e)}")

def show_sistemas_report():
    """Muestra análisis por sistemas de radio"""
    st.subheader("📡 Análisis por Sistemas de Radio")

    # Filtros de fecha
    col1, col2 = st.columns(2)

    with col1:
        fecha_inicio = st.date_input(
            "Fecha inicio",
            value=datetime.now().replace(day=1),
            key="sistemas_fecha_inicio"
        )

    with col2:
        fecha_fin = st.date_input(
            "Fecha fin",
            value=datetime.now(),
            key="sistemas_fecha_fin"
        )

    if fecha_inicio > fecha_fin:
        st.error("❌ La fecha de inicio debe ser anterior a la fecha de fin")
        return

    try:
        # Convertir fechas para consulta
        fecha_inicio_str = fecha_inicio.strftime('%Y-%m-%d')
        fecha_fin_str = fecha_fin.strftime('%Y-%m-%d')

        # Obtener datos de sistemas
        reportes, estadisticas = db.get_reportes_por_fecha_rango(fecha_inicio_str, fecha_fin_str)

        if reportes:
            import pandas as pd
            df_sistemas = pd.DataFrame([{
                'Indicativo': r.get('indicativo', ''),
                'Sistema': r.get('sistema', ''),
                'Zona': r.get('zona', ''),
                'Estado': r.get('estado', ''),
                'Señal': r.get('senal', 0)
            } for r in reportes])

            # Análisis por sistema
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("📊 Uso de Sistemas")
                sistemas_count = df_sistemas['Sistema'].value_counts()
                st.bar_chart(sistemas_count)

                # Porcentaje de uso
                total = len(df_sistemas)
                st.subheader("📈 Porcentaje de Uso")
                for sistema, count in sistemas_count.items():
                    porcentaje = (count / total) * 100
                    st.write(f"**{sistema}:** {count} ({porcentaje:.1f}%)")

            with col2:
                st.subheader("📡 Calidad de Señal por Sistema")
                # Calcular promedio de señal por sistema
                senal_por_sistema = df_sistemas.groupby('Sistema')['Señal'].mean().sort_values(ascending=False)
                st.bar_chart(senal_por_sistema)

                # Mostrar promedios
                st.subheader("📊 Promedio de Señal")
                for sistema, promedio in senal_por_sistema.items():
                    st.write(f"**{sistema}:** {promedio:.1f}")

            # Análisis HF específico
            if 'HF' in df_sistemas['Sistema'].values:
                st.subheader("📻 Análisis HF Detallado")
                df_hf = df_sistemas[df_sistemas['Sistema'] == 'HF']

                if not df_hf.empty:
                    col_hf1, col_hf2 = st.columns(2)

                    with col_hf1:
                        st.write("**Modos HF más usados:**")
                        modos_hf = df_hf['Modo'].value_counts() if 'Modo' in df_hf.columns else {}
                        if not modos_hf.empty:
                            st.bar_chart(modos_hf)
                        else:
                            st.info("No hay datos de modos HF")

                    with col_hf2:
                        st.write("**Potencias HF más usadas:**")
                        potencias_hf = df_hf['Potencia'].value_counts() if 'Potencia' in df_hf.columns else {}
                        if not potencias_hf.empty:
                            st.bar_chart(potencias_hf)
                        else:
                            st.info("No hay datos de potencias HF")

        else:
            st.info("No hay datos para el período seleccionado")

    except Exception as e:
        st.error(f"Error al cargar el análisis de sistemas: {str(e)}")

def show_tendencias_report():
    """Muestra análisis de tendencias a lo largo del tiempo"""
    st.subheader("📊 Análisis de Tendencias")

    # Opciones de período
    col1, col2 = st.columns(2)

    with col1:
        periodo = st.selectbox(
            "Período de análisis",
            ["Últimos 30 días", "Últimos 90 días", "Último año", "Personalizado"],
            key="tendencias_periodo"
        )

    with col2:
        if periodo == "Personalizado":
            fecha_inicio = st.date_input("Fecha inicio", key="tendencias_fecha_inicio")
            fecha_fin = st.date_input("Fecha fin", key="tendencias_fecha_fin")
        else:
            # Calcular fechas automáticamente
            fecha_fin = datetime.now()
            if periodo == "Últimos 30 días":
                fecha_inicio = fecha_fin - timedelta(days=30)
            elif periodo == "Últimos 90 días":
                fecha_inicio = fecha_fin - timedelta(days=90)
            else:  # Último año
                fecha_inicio = fecha_fin - timedelta(days=365)

    if periodo == "Personalizado" and fecha_inicio > fecha_fin:
        st.error("❌ La fecha de inicio debe ser anterior a la fecha de fin")
        return

    try:
        # Convertir fechas para consulta
        fecha_inicio_str = fecha_inicio.strftime('%Y-%m-%d')
        fecha_fin_str = fecha_fin.strftime('%Y-%m-%d')

        # Obtener datos para tendencias
        reportes, estadisticas = db.get_reportes_por_fecha_rango(fecha_inicio_str, fecha_fin_str)

        if reportes:
            import pandas as pd
            df_tendencias = pd.DataFrame([{
                'Fecha': r.get('fecha_reporte', ''),
                'Indicativo': r.get('indicativo', ''),
                'Sistema': r.get('sistema', ''),
                'Zona': r.get('zona', '')
            } for r in reportes])

            # Convertir fecha a datetime correctamente
            # Las fechas vienen de la BD en formato datetime completo, no dd/mm/yyyy
            df_tendencias['Fecha'] = pd.to_datetime(df_tendencias['Fecha'], format='mixed', dayfirst=True)

            # Agrupar por semana
            df_tendencias['Semana'] = df_tendencias['Fecha'].dt.to_period('W').astype(str)
            tendencia_semanal = df_tendencias.groupby('Semana').size().reset_index(name='Reportes')

            # Gráfico de tendencia
            st.subheader("📈 Tendencia de Actividad (por semana)")
            st.line_chart(tendencia_semanal.set_index('Semana'))

            # Análisis de crecimiento
            st.subheader("📊 Análisis de Crecimiento")

            # Calcular crecimiento semanal
            if len(tendencia_semanal) > 1:
                crecimiento = tendencia_semanal['Reportes'].pct_change() * 100
                crecimiento_promedio = crecimiento.mean()

                col1, col2 = st.columns(2)

                with col1:
                    st.metric("Crecimiento Promedio Semanal", f"{crecimiento_promedio:.1f}%")

                with col2:
                    total_crecimiento = (tendencia_semanal['Reportes'].iloc[-1] / tendencia_semanal['Reportes'].iloc[0] - 1) * 100
                    st.metric("Crecimiento Total del Período", f"{total_crecimiento:.1f}%")

            # Top estaciones más activas
            st.subheader("🏆 Estaciones Más Activas")
            top_estaciones = df_tendencias['Indicativo'].value_counts().head(10)

            # Crear columnas para mostrar
            cols = st.columns(min(2, len(top_estaciones)))

            for i, (estacion, count) in enumerate(top_estaciones.items()):
                col_idx = i % 2
                with cols[col_idx]:
                    st.write(f"**{estacion}:** {count} reportes")

        else:
            st.info("No hay datos para el período seleccionado")

    except Exception as e:
        st.error(f"Error al cargar el análisis de tendencias: {str(e)}")

def show_comparativos_report():
    """Muestra análisis comparativos entre diferentes períodos"""
    st.subheader("⚖️ Análisis Comparativos")

    # Selección de períodos para comparar
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Período 1")
        p1_tipo = st.selectbox(
            "Tipo de período",
            ["Mes actual", "Mes anterior", "Últimos 30 días", "Personalizado"],
            key="p1_tipo"
        )

        if p1_tipo == "Personalizado":
            p1_fecha_inicio = st.date_input("Fecha inicio P1", key="p1_fecha_inicio")
            p1_fecha_fin = st.date_input("Fecha fin P1", key="p1_fecha_fin")
        else:
            # Calcular automáticamente
            hoy = datetime.now()
            if p1_tipo == "Mes actual":
                p1_fecha_inicio = hoy.replace(day=1)
                p1_fecha_fin = hoy
            elif p1_tipo == "Mes anterior":
                mes_anterior = hoy.replace(day=1) - timedelta(days=1)
                p1_fecha_inicio = mes_anterior.replace(day=1)
                p1_fecha_fin = mes_anterior
            else:  # Últimos 30 días
                p1_fecha_inicio = hoy - timedelta(days=30)
                p1_fecha_fin = hoy

    with col2:
        st.subheader("Período 2")
        p2_tipo = st.selectbox(
            "Tipo de período",
            ["Mes anterior", "Últimos 30 días", "Personalizado"],
            key="p2_tipo"
        )

        if p2_tipo == "Personalizado":
            p2_fecha_inicio = st.date_input("Fecha inicio P2", key="p2_fecha_inicio")
            p2_fecha_fin = st.date_input("Fecha fin P2", key="p2_fecha_fin")
        else:
            # Calcular automáticamente
            hoy = datetime.now()
            if p2_tipo == "Mes anterior":
                mes_anterior = hoy.replace(day=1) - timedelta(days=1)
                p2_fecha_inicio = mes_anterior.replace(day=1)
                p2_fecha_fin = mes_anterior
            else:  # Últimos 30 días
                p2_fecha_inicio = hoy - timedelta(days=30)
                p2_fecha_fin = hoy

    # Validar fechas
    if p1_tipo == "Personalizado" and p1_fecha_inicio > p1_fecha_fin:
        st.error("❌ Período 1: La fecha de inicio debe ser anterior a la fecha de fin")
        return

    if p2_tipo == "Personalizado" and p2_fecha_inicio > p2_fecha_fin:
        st.error("❌ Período 2: La fecha de inicio debe ser anterior a la fecha de fin")
        return

    try:
        # Obtener datos para ambos períodos
        p1_inicio_str = p1_fecha_inicio.strftime('%Y-%m-%d')
        p1_fin_str = p1_fecha_fin.strftime('%Y-%m-%d')
        p1_reportes, p1_estadisticas = db.get_reportes_por_fecha_rango(p1_inicio_str, p1_fin_str)

        p2_inicio_str = p2_fecha_inicio.strftime('%Y-%m-%d')
        p2_fin_str = p2_fecha_fin.strftime('%Y-%m-%d')
        p2_reportes, p2_estadisticas = db.get_reportes_por_fecha_rango(p2_inicio_str, p2_fin_str)

        # Crear dataframes para comparación
        import pandas as pd

        if p1_reportes and p2_reportes:
            df_p1 = pd.DataFrame([{
                'Indicativo': r.get('indicativo', ''),
                'Sistema': r.get('sistema', ''),
                'Zona': r.get('zona', ''),
                'Estado': r.get('estado', '')
            } for r in p1_reportes])

            df_p2 = pd.DataFrame([{
                'Indicativo': r.get('indicativo', ''),
                'Sistema': r.get('sistema', ''),
                'Zona': r.get('zona', ''),
                'Estado': r.get('estado', '')
            } for r in p2_reportes])

            # Comparación de métricas
            st.subheader("📊 Comparación de Métricas")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                p1_total = p1_estadisticas.get('total_reportes', 0)
                p2_total = p2_estadisticas.get('total_reportes', 0)
                st.metric("Total Reportes", f"{p1_total} vs {p2_total}")

            with col2:
                p1_estaciones = p1_estadisticas.get('estaciones_unicas', 0)
                p2_estaciones = p2_estadisticas.get('estaciones_unicas', 0)
                st.metric("Estaciones Únicas", f"{p1_estaciones} vs {p2_estaciones}")

            with col3:
                variacion_reportes = ((p2_total - p1_total) / max(p1_total, 1)) * 100
                st.metric("Variación Reportes", f"{variacion_reportes:.1f}%")

            with col4:
                variacion_estaciones = ((p2_estaciones - p1_estaciones) / max(p1_estaciones, 1)) * 100
                st.metric("Variación Estaciones", f"{variacion_estaciones:.1f}%")

            # Comparación por sistemas
            st.subheader("📡 Comparación por Sistemas")

            p1_sistemas = df_p1['Sistema'].value_counts()
            p2_sistemas = df_p2['Sistema'].value_counts()

            # Crear dataframe comparativo
            df_comparativo = pd.DataFrame({
                'Período 1': p1_sistemas,
                'Período 2': p2_sistemas
            }).fillna(0)

            st.bar_chart(df_comparativo)

            # Nuevas estaciones
            st.subheader("🆕 Nuevas Estaciones")
            estaciones_p1 = set(df_p1['Indicativo'])
            estaciones_p2 = set(df_p2['Indicativo'])

            nuevas = estaciones_p2 - estaciones_p1
            perdidas = estaciones_p1 - estaciones_p2

            col1, col2 = st.columns(2)

            with col1:
                st.write(f"**Nuevas estaciones:** {len(nuevas)}")
                if nuevas:
                    for estacion in sorted(nuevas)[:10]:  # Mostrar primeras 10
                        st.write(f"• {estacion}")

            with col2:
                st.write(f"**Estaciones no activas:** {len(perdidas)}")
                if perdidas:
                    for estacion in sorted(perdidas)[:10]:  # Mostrar primeras 10
                        st.write(f"• {estacion}")

        else:
            st.info("No hay datos suficientes para la comparación")

    except Exception as e:
        st.error(f"Error al cargar el análisis comparativo: {str(e)}")

def show_evento_report():
    """Muestra reportes por evento específico con estadísticas y exportación"""
    st.subheader("📅 Reportes por Evento")

    # Filtros de selección
    col1, col2 = st.columns(2)

    with col1:
        # Obtener eventos activos
        try:
            eventos = db.get_eventos_activos()
            opciones_eventos = [e['tipo'] for e in eventos]
            if not opciones_eventos:
                st.error("❌ No hay eventos configurados en el sistema")
                return
        except Exception as e:
            st.error(f"Error al cargar eventos: {str(e)}")
            return

        evento_seleccionado = st.selectbox(
            "Tipo de Evento",
            opciones_eventos,
            key="evento_seleccionado"
        )

    with col2:
        fecha_evento = st.date_input(
            "Fecha del Evento",
            value=datetime.now(),
            key="fecha_evento"
        )

    # Botón para generar reporte
    if st.button("🔍 Generar Reporte", type="primary"):
        try:
            # Convertir fecha para consulta
            fecha_str = fecha_evento.strftime('%Y-%m-%d')

            # Obtener reportes para el evento y fecha específicos
            reportes, estadisticas = db.get_reportes_por_fecha_rango(fecha_str, fecha_str)

            # Filtrar solo los reportes del evento seleccionado
            reportes_evento = [r for r in reportes if r.get('tipo_reporte') == evento_seleccionado]

            if reportes_evento:
                # Crear dataframe para análisis (incluye Estación QRZ)
                import pandas as pd
                df_evento = pd.DataFrame([{
                    'Indicativo': r.get('indicativo', ''),
                    'Nombre': r.get('nombre', ''),
                    'Zona': r.get('zona', ''),
                    'Sistema': r.get('sistema', ''),
                    'Estado': r.get('estado', ''),
                    'Ciudad': r.get('ciudad', ''),
                    'Señal': r.get('senal', 0),
                    'Observaciones': r.get('observaciones', ''),
                    'Estación': (r.get('qrz_station') or '').strip() or 'Sin estación'
                } for r in reportes_evento])

                # Guardar datos en session_state para mantener el estado
                st.session_state.reporte_generado = True
                st.session_state.datos_evento = {
                    'evento': evento_seleccionado,
                    'fecha': fecha_str,
                    'reportes': reportes_evento,
                    'df_evento': df_evento,
                    'usuario': st.session_state.get('user', {})
                }

                # Forzar rerun para actualizar la interfaz
                st.rerun()

        except Exception as e:
            st.error(f"Error al generar el reporte: {str(e)}")

    # Si hay un reporte generado, mostrar los datos y opciones de exportación
    if st.session_state.get('reporte_generado', False):
        import pandas as pd
        datos = st.session_state.datos_evento

        # Estadísticas principales
        st.subheader("📊 Estadísticas del Evento")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total de Reportes", len(datos['reportes']))

        with col2:
            estaciones_unicas = datos['df_evento']['Indicativo'].nunique()
            st.metric("Estaciones Únicas", estaciones_unicas)

        with col3:
            zona_mas_reportada = datos['df_evento']['Zona'].mode().iloc[0] if not datos['df_evento']['Zona'].mode().empty else "N/A"
            st.metric("Zona Más Reportada", zona_mas_reportada)

        with col4:
            sistema_mas_usado = datos['df_evento']['Sistema'].mode().iloc[0] if not datos['df_evento']['Sistema'].mode().empty else "N/A"
            st.metric("Sistema Más Usado", sistema_mas_usado)

        # Tabla de distribución por zona
        st.subheader("📍 Distribución por Zona")
        zonas_count = datos['df_evento']['Zona'].value_counts()
        df_zonas = pd.DataFrame({
            'Zona': zonas_count.index,
            'Cantidad': zonas_count.values,
            'Porcentaje': (zonas_count.values / len(datos['df_evento']) * 100).round(1)
        })

        st.dataframe(
            df_zonas,
            width='stretch',
            hide_index=True
        )

        # Tabla de distribución por sistema
        st.subheader("📡 Distribución por Sistema")
        sistemas_count = datos['df_evento']['Sistema'].value_counts()
        df_sistemas = pd.DataFrame({
            'Sistema': sistemas_count.index,
            'Cantidad': sistemas_count.values,
            'Porcentaje': (sistemas_count.values / len(datos['df_evento']) * 100).round(1)
        })

        st.dataframe(
            df_sistemas,
            width='stretch',
            hide_index=True
        )

        # Desglose por Estación (QRZ Station)
        st.subheader("🏷️ Desglose por Estación (QRZ Station)")
        estaciones_count = datos['df_evento']['Estación'].value_counts(dropna=False)
        df_estaciones = pd.DataFrame({
            'Estación': estaciones_count.index,
            'Cantidad': estaciones_count.values,
            'Porcentaje': (estaciones_count.values / len(datos['df_evento']) * 100).round(1)
        })
        st.dataframe(
            df_estaciones,
            width='stretch',
            hide_index=True
        )
        # Validar suma de desglose por estación
        total_suma_estaciones = int(df_estaciones['Cantidad'].sum())
        if total_suma_estaciones != len(datos['df_evento']):
            st.warning(f"La suma por estación ({total_suma_estaciones}) no coincide con el total del evento ({len(datos['df_evento'])}).")

        # Filtro por estación
        estaciones_opciones = ['Todas'] + sorted([e for e in df_estaciones['Estación'].tolist() if e and e != ''])
        estacion_sel = st.selectbox("Filtrar por Estación (QRZ Station)", estaciones_opciones, key="filtro_estacion_evento")

        if estacion_sel != 'Todas':
            df_evento_filtrado = datos['df_evento'][datos['df_evento']['Estación'] == estacion_sel]
        else:
            df_evento_filtrado = datos['df_evento']

        # Si se filtró por estación, repetir las estadísticas y distribuciones para esa estación
        if estacion_sel != 'Todas':
            st.subheader("📊 Estadísticas de la Estación")
            colf1, colf2, colf3, colf4 = st.columns(4)

            with colf1:
                st.metric("Total de Reportes", len(df_evento_filtrado))

            with colf2:
                st.metric("Estaciones Únicas", df_evento_filtrado['Indicativo'].nunique())

            with colf3:
                zona_mas_reportada_est = (
                    df_evento_filtrado['Zona'].mode().iloc[0]
                    if not df_evento_filtrado['Zona'].mode().empty else "N/A"
                )
                st.metric("Zona Más Reportada", zona_mas_reportada_est)

            with colf4:
                sistema_mas_usado_est = (
                    df_evento_filtrado['Sistema'].mode().iloc[0]
                    if not df_evento_filtrado['Sistema'].mode().empty else "N/A"
                )
                st.metric("Sistema Más Usado", sistema_mas_usado_est)

            # Distribución por zona (estación)
            st.subheader("📍 Distribución por Zona (Estación)")
            zonas_count_est = df_evento_filtrado['Zona'].value_counts()
            df_zonas_est = pd.DataFrame({
                'Zona': zonas_count_est.index,
                'Cantidad': zonas_count_est.values,
                'Porcentaje': (zonas_count_est.values / len(df_evento_filtrado) * 100).round(1)
            })
            st.dataframe(
                df_zonas_est,
                width='stretch',
                hide_index=True
            )

            # Distribución por sistema (estación)
            st.subheader("📡 Distribución por Sistema (Estación)")
            sistemas_count_est = df_evento_filtrado['Sistema'].value_counts()
            df_sistemas_est = pd.DataFrame({
                'Sistema': sistemas_count_est.index,
                'Cantidad': sistemas_count_est.values,
                'Porcentaje': (sistemas_count_est.values / len(df_evento_filtrado) * 100).round(1)
            })
            st.dataframe(
                df_sistemas_est,
                width='stretch',
                hide_index=True
            )

        st.subheader("📄 Detalle de Reportes" + (" - Estación: " + estacion_sel if estacion_sel != 'Todas' else ""))
        st.dataframe(df_evento_filtrado, width='stretch', hide_index=True)

        # Información del usuario que generó el reporte
        usuario_actual = datos['usuario']
        indicativo_usuario = usuario_actual.get('username', 'Sistema')
        nombre_usuario = usuario_actual.get('full_name', 'Sistema')

        # Botones de exportación con filtros
        st.subheader("📤 Exportar Reporte")

        with st.expander("Filtros de exportación", expanded=True):
            export_estaciones_opciones = ['Todas'] + sorted([e for e in df_estaciones['Estación'].tolist() if e and e != ''])
            # Opción para usar el mismo filtro de la vista (por defecto activado)
            export_use_view_station = st.checkbox(
                "Usar misma estación filtrada en la vista",
                value=True,
                key="export_use_view_station"
            )

            if export_use_view_station:
                selected_export_station = estacion_sel
                st.caption(f"Estación para exportar: {selected_export_station}")
            else:
                # Preseleccionar la estación actualmente filtrada en la vista cuando no se usa el checkbox
                try:
                    export_index = export_estaciones_opciones.index(estacion_sel)
                except Exception:
                    export_index = 0
                export_estacion_sel = st.selectbox(
                    "Estación a exportar (QRZ Station)",
                    export_estaciones_opciones,
                    index=export_index,
                    key="export_estacion_evento"
                )
                selected_export_station = export_estacion_sel

            # Precomputar dataset a exportar y mostrar conteo
            if selected_export_station != 'Todas':
                df_export = datos['df_evento'][datos['df_evento']['Estación'] == selected_export_station]
            else:
                df_export = datos['df_evento']
            st.caption(f"Registros a exportar: {len(df_export)}")

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("📊 Excel", width='stretch'):
                # Determinar dataset a exportar según filtro
                if selected_export_station != 'Todas':
                    df_export = datos['df_evento'][datos['df_evento']['Estación'] == selected_export_station]
                else:
                    df_export = datos['df_evento']

                # Recalcular métricas para exportación
                estaciones_unicas_exp = df_export['Indicativo'].nunique()
                zona_mas_reportada_exp = (df_export['Zona'].mode().iloc[0] if not df_export['Zona'].mode().empty else "N/A")
                sistema_mas_usado_exp = (df_export['Sistema'].mode().iloc[0] if not df_export['Sistema'].mode().empty else "N/A")
                zonas_count_exp = df_export['Zona'].value_counts()
                df_zonas_exp = pd.DataFrame({
                    'Zona': zonas_count_exp.index,
                    'Cantidad': zonas_count_exp.values,
                    'Porcentaje': (zonas_count_exp.values / max(len(df_export), 1) * 100).round(1)
                })
                sistemas_count_exp = df_export['Sistema'].value_counts()
                df_sistemas_exp = pd.DataFrame({
                    'Sistema': sistemas_count_exp.index,
                    'Cantidad': sistemas_count_exp.values,
                    'Porcentaje': (sistemas_count_exp.values / max(len(df_export), 1) * 100).round(1)
                })

                # Crear Excel con información detallada
                buffer = io.BytesIO()

                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    # Hoja principal con estadísticas
                    stats_df = pd.DataFrame({
                        'Métrica': ['Evento', 'Fecha', 'Total Reportes', 'Estaciones Únicas',
                                  'Zona Más Reportada', 'Sistema Más Usado', 'Generado por'],
                        'Valor': [datos['evento'], datos['fecha'], len(df_export),
                                estaciones_unicas_exp, zona_mas_reportada_exp, sistema_mas_usado_exp,
                                f"{indicativo_usuario} - {nombre_usuario}"]
                    })
                    stats_df.to_excel(writer, sheet_name='Estadísticas', index=False)

                    # Hoja con datos detallados
                    df_export.to_excel(writer, sheet_name='Datos Detallados', index=False)

                    # Hoja con distribución por zona
                    df_zonas_exp.to_excel(writer, sheet_name='Por Zona', index=False)

                    # Hoja con distribución por sistema
                    df_sistemas_exp.to_excel(writer, sheet_name='Por Sistema', index=False)

                buffer.seek(0)

                est_suffix = "" if selected_export_station == 'Todas' else f"_{selected_export_station.replace(' ', '_')}"
                excel_bytes = buffer.getvalue()
                st.session_state['trad_excel'] = {
                    'bytes': excel_bytes,
                    'file_name': f"reporte_{datos['evento']}_{datos['fecha']}{est_suffix}.xlsx",
                    'mime': "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                }
                st.session_state['trad_excel_df_preview'] = df_export.copy()

            if st.session_state.get('trad_excel'):
                ex = st.session_state['trad_excel']
                st.download_button(
                    label="⬇️ Descargar Excel",
                    data=ex['bytes'],
                    file_name=ex['file_name'],
                    mime=ex['mime'],
                    key="trad_excel_download_persist",
                    width='stretch'
                )
                open_excel_modal = st.button("📧 Enviar por Correo", key="open_trad_excel_dialog", use_container_width=True)
                if open_excel_modal:
                    if hasattr(st, "dialog"):
                        @st.dialog("Enviar reporte (Excel)")
                        def _trad_excel_dialog():
                            st.markdown(
                                """
                                <style>
                                div[role='dialog'] { width: min(95vw, 1200px) !important; }
                                div[role='dialog'] > div { width: 100% !important; }
                                @media (max-width: 900px) {
                                  div[role='dialog'] [data-testid='column'] { flex: 0 0 100% !important; width: 100% !important; min-width: 100% !important; }
                                }
                                </style>
                                """,
                                unsafe_allow_html=True
                            )
                            ex_loc = st.session_state.get('trad_excel')
                            df_loc = st.session_state.get('trad_excel_df_preview')
                            if df_loc is None:
                                df_loc = df_export
                            total = int(len(df_loc)) if isinstance(df_loc, pd.DataFrame) else 0
                            ests = int(df_loc['Indicativo'].nunique()) if isinstance(df_loc, pd.DataFrame) and 'Indicativo' in df_loc.columns else 0
                            zona_m = (df_loc['Zona'].mode().iloc[0] if isinstance(df_loc, pd.DataFrame) and 'Zona' in df_loc.columns and not df_loc['Zona'].mode().empty else "N/A")
                            sist_m = (df_loc['Sistema'].mode().iloc[0] if isinstance(df_loc, pd.DataFrame) and 'Sistema' in df_loc.columns and not df_loc['Sistema'].mode().empty else "N/A")
                            ests_geo = int(df_loc['Estado'].nunique()) if isinstance(df_loc, pd.DataFrame) and 'Estado' in df_loc.columns else 0
                            zonas_html = ""
                            if isinstance(df_loc, pd.DataFrame) and 'Zona' in df_loc.columns and total > 0:
                                vc_z = df_loc['Zona'].fillna('N/D').astype(str).value_counts()
                                zonas_html = "<p><strong>Distribución por Zona:</strong></p><ul>" + "".join([f"<li>{z}: {int(c)} ({(c/total)*100:.1f}%)</li>" for z, c in vc_z.items()]) + "</ul>"
                            sistemas_html = ""
                            if isinstance(df_loc, pd.DataFrame) and 'Sistema' in df_loc.columns and total > 0:
                                vc_s = df_loc['Sistema'].fillna('N/D').astype(str).value_counts()
                                sistemas_html = "<p><strong>Distribución por Sistema:</strong></p><ul>" + "".join([f"<li>{s}: {int(c)} ({(c/total)*100:.1f}%)</li>" for s, c in vc_s.items()]) + "</ul>"
                            estaciones_html = ""
                            if isinstance(df_loc, pd.DataFrame) and 'Estación' in df_loc.columns and total > 0:
                                vc_e = df_loc['Estación'].fillna('Sin estación').astype(str).value_counts()
                                estaciones_html = "<p><strong>Desglose por Estación (top 10):</strong></p><ul>" + "".join([f"<li>{e}: {int(c)} ({(c/total)*100:.1f}%)</li>" for e, c in vc_e.head(10).items()]) + "</ul>"
                            per_station_html = ""
                            if isinstance(df_loc, pd.DataFrame) and 'Estación' in df_loc.columns and total > 0:
                                top_e = vc_e.head(5) if 'vc_e' in locals() else df_loc['Estación'].fillna('Sin estación').astype(str).value_counts().head(5)
                                items = []
                                for est_name, _cnt in top_e.items():
                                    df_s = df_loc[df_loc['Estación'].fillna('Sin estación').astype(str) == est_name]
                                    sz = len(df_s)
                                    z_block = ""
                                    if 'Zona' in df_s.columns and sz > 0:
                                        vc_zs = df_s['Zona'].fillna('N/D').astype(str).value_counts()
                                        z_block = "<ul>" + "".join([f"<li>{z}: {int(c)} ({(c/sz)*100:.1f}%)</li>" for z, c in vc_zs.items()]) + "</ul>"
                                    s_block = ""
                                    if 'Sistema' in df_s.columns and sz > 0:
                                        vc_ss = df_s['Sistema'].fillna('N/D').astype(str).value_counts()
                                        s_block = "<ul>" + "".join([f"<li>{s}: {int(c)} ({(c/sz)*100:.1f}%)</li>" for s, c in vc_ss.items()]) + "</ul>"
                                    items.append(f"<li><strong>{est_name}</strong><ul><li>Distribución por Zona:{z_block}</li><li>Distribución por Sistema:{s_block}</li></ul></li>")
                                per_station_html = "<p><strong>Detalle por Estación (top 5):</strong></p><ul>" + "".join(items) + "</ul>"
                            # Cuerpo narrativo (Excel)
                            try:
                                meses_es = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
                                fecha_larga = datos['fecha']
                                try:
                                    fdt = datetime.strptime(datos['fecha'], '%Y-%m-%d')
                                    fecha_larga = f"{fdt.day} de {meses_es[fdt.month-1]} de {fdt.year}"
                                except Exception:
                                    pass
                                vc_z_loc = df_loc['Zona'].fillna('N/D').astype(str).value_counts() if isinstance(df_loc, pd.DataFrame) and 'Zona' in df_loc.columns and total > 0 else pd.Series(dtype=int)
                                vc_s_loc = df_loc['Sistema'].fillna('N/D').astype(str).value_counts() if isinstance(df_loc, pd.DataFrame) and 'Sistema' in df_loc.columns and total > 0 else pd.Series(dtype=int)
                                vc_e_loc = df_loc['Estación'].fillna('Sin estación').astype(str).value_counts() if isinstance(df_loc, pd.DataFrame) and 'Estación' in df_loc.columns and total > 0 else pd.Series(dtype=int)
                                def fmt_pct(n, d):
                                    return f"{(n/d*100):.1f}%" if d else "0.0%"
                                zonas_presentes = [z for z in vc_z_loc.index if z in ['XE1','XE2','XE3']]
                                ext_count = int(vc_z_loc.get('EXT', 0)) if hasattr(vc_z_loc, 'get') else 0
                                zona_frase = ""
                                if len(vc_z_loc) > 0:
                                    z_pairs = list(vc_z_loc.items())
                                    topz = z_pairs[0]
                                    zona_frase = f"La zona {topz[0]} fue la más activa con {int(topz[1])} reportes ({fmt_pct(topz[1], total)})."
                                    if len(z_pairs) > 1:
                                        z2 = z_pairs[1]
                                        zona_frase = zona_frase[:-1] + f", seguida por {z2[0]} ({fmt_pct(z2[1], total)})."
                                    if len(z_pairs) > 2:
                                        z3 = z_pairs[2]
                                        zona_frase = zona_frase[:-1] + f" y {z3[0]} ({fmt_pct(z3[1], total)})."
                                    if ext_count > 0:
                                        zona_frase = zona_frase[:-1] + f" Además, {ext_count} estaciones extranjeras ({fmt_pct(ext_count, total)})."
                                sistemas_frase = ""
                                if len(vc_s_loc) > 0:
                                    s_pairs = list(vc_s_loc.items())
                                    stp = s_pairs[0]
                                    sistemas_frase = f"En sistemas, {stp[0]} lideró con {fmt_pct(stp[1], total)}"
                                    if len(s_pairs) > 1:
                                        s2 = s_pairs[1]
                                        sistemas_frase += f", seguido por {s2[0]} ({fmt_pct(s2[1], total)})."
                                    else:
                                        sistemas_frase += "."
                                dist_zona_html = "<ul>" + "".join([f"<li>{z}: {int(c)} ({fmt_pct(c, total)})</li>" for z, c in vc_z_loc.items()]) + "</ul>" if len(vc_z_loc) > 0 else ""
                                dist_sist_html = "<ul>" + "".join([f"<li>{s}: {int(c)} ({fmt_pct(c, total)})</li>" for s, c in vc_s_loc.items()]) + "</ul>" if len(vc_s_loc) > 0 else ""
                                top10 = list(vc_e_loc.items())[:10]
                                top10_html = "<ul>" + "".join([f"<li>{e}: {int(c)} ({fmt_pct(c, total)})</li>" for e, c in top10]) + "</ul>" if top10 else ""
                                # Desglose narrativo para estaciones específicas (XE1LM y XE2BC)
                                det_xe_html = ""
                                if isinstance(df_loc, pd.DataFrame) and ('Estación' in df_loc.columns) and total > 0:
                                    for _st_code in ['XE1LM','XE2BC']:
                                        _df_s = df_loc[df_loc['Estación'].fillna('Sin estación').astype(str) == _st_code]
                                        _sz = len(_df_s)
                                        if _sz > 0:
                                            _pct_tot = fmt_pct(_sz, total)
                                            _z_s = _df_s['Zona'].fillna('N/D').astype(str).value_counts() if 'Zona' in _df_s.columns else pd.Series(dtype=int)
                                            _s_s = _df_s['Sistema'].fillna('N/D').astype(str).value_counts() if 'Sistema' in _df_s.columns else pd.Series(dtype=int)
                                            _zona_frase_st = ""
                                            if len(_z_s) > 0:
                                                _z_pairs = list(_z_s.items())
                                                _topz = _z_pairs[0]
                                                _zona_frase_st = f"La zona {_topz[0]} fue la más activa con {int(_topz[1])} reportes ({fmt_pct(_topz[1], _sz)})"
                                                if len(_z_pairs) > 1:
                                                    _zona_frase_st += f", seguida por {_z_pairs[1][0]} ({fmt_pct(_z_pairs[1][1], _sz)})"
                                                if len(_z_pairs) > 2:
                                                    _zona_frase_st += f" y {_z_pairs[2][0]} ({fmt_pct(_z_pairs[2][1], _sz)})"
                                                _ext_st = int(_z_s.get('EXT', 0)) if hasattr(_z_s, 'get') else 0
                                                if _ext_st > 0:
                                                    _zona_frase_st += f", además de {_ext_st} estaciones extranjeras ({fmt_pct(_ext_st, _sz)})."
                                                else:
                                                    _zona_frase_st += "."
                                            _sistemas_frase_st = ""
                                            if len(_s_s) > 0:
                                                _s_pairs = list(_s_s.items())
                                                _stp = _s_pairs[0]
                                                _sistemas_frase_st = f"En cuanto a los sistemas, {_stp[0]} encabezó la actividad con el {fmt_pct(_stp[1], _sz)}"
                                                if len(_s_pairs) > 1:
                                                    _sistemas_frase_st += f", seguido por {_s_pairs[1][0]} ({fmt_pct(_s_pairs[1][1], _sz)})"
                                                if len(_s_pairs) > 2:
                                                    _sistemas_frase_st += f", {_s_pairs[2][0]} ({fmt_pct(_s_pairs[2][1], _sz)})"
                                                _otros_pct = 100.0 - sum([(v/_sz*100) for _, v in _s_pairs[:3]]) if _sz else 0.0
                                                if len(_s_pairs) > 3 and _otros_pct > 0:
                                                    _sistemas_frase_st += f" y el {_otros_pct:.1f}% restante en otros sistemas."
                                                else:
                                                    _sistemas_frase_st += "."
                                            det_xe_html += f"<p>La Estación <strong>{_st_code}</strong> informa que se reportaron <strong>{_sz}</strong> colegas, que representan el <strong>{_pct_tot}</strong> del total de reportes del boletín.</p><p>{_zona_frase_st}</p><p>{_sistemas_frase_st}</p>"
                                # Desglose narrativo para estaciones específicas (XE1LM y XE2BC)
                                det_xe_html = ""
                                if isinstance(df_loc, pd.DataFrame) and ('Estación' in df_loc.columns) and total > 0:
                                    for _st_code in ['XE1LM','XE2BC']:
                                        _df_s = df_loc[df_loc['Estación'].fillna('Sin estación').astype(str) == _st_code]
                                        _sz = len(_df_s)
                                        if _sz > 0:
                                            _pct_tot = fmt_pct(_sz, total)
                                            _z_s = _df_s['Zona'].fillna('N/D').astype(str).value_counts() if 'Zona' in _df_s.columns else pd.Series(dtype=int)
                                            _s_s = _df_s['Sistema'].fillna('N/D').astype(str).value_counts() if 'Sistema' in _df_s.columns else pd.Series(dtype=int)
                                            _zona_frase_st = ""
                                            if len(_z_s) > 0:
                                                _z_pairs = list(_z_s.items())
                                                _topz = _z_pairs[0]
                                                _zona_frase_st = f"La zona {_topz[0]} fue la más activa con {int(_topz[1])} reportes ({fmt_pct(_topz[1], _sz)})"
                                                if len(_z_pairs) > 1:
                                                    _zona_frase_st += f", seguida por {_z_pairs[1][0]} ({fmt_pct(_z_pairs[1][1], _sz)})"
                                                if len(_z_pairs) > 2:
                                                    _zona_frase_st += f" y {_z_pairs[2][0]} ({fmt_pct(_z_pairs[2][1], _sz)})"
                                                _ext_st = int(_z_s.get('EXT', 0)) if hasattr(_z_s, 'get') else 0
                                                if _ext_st > 0:
                                                    _zona_frase_st += f", además de {_ext_st} estaciones extranjeras ({fmt_pct(_ext_st, _sz)})."
                                                else:
                                                    _zona_frase_st += "."
                                            _sistemas_frase_st = ""
                                            if len(_s_s) > 0:
                                                _s_pairs = list(_s_s.items())
                                                _stp = _s_pairs[0]
                                                _sistemas_frase_st = f"En cuanto a los sistemas, {_stp[0]} encabezó la actividad con el {fmt_pct(_stp[1], _sz)}"
                                                if len(_s_pairs) > 1:
                                                    _sistemas_frase_st += f", seguido por {_s_pairs[1][0]} ({fmt_pct(_s_pairs[1][1], _sz)})"
                                                if len(_s_pairs) > 2:
                                                    _sistemas_frase_st += f", {_s_pairs[2][0]} ({fmt_pct(_s_pairs[2][1], _sz)})"
                                                _otros_pct = 100.0 - sum([(v/_sz*100) for _, v in _s_pairs[:3]]) if _sz else 0.0
                                                if len(_s_pairs) > 3 and _otros_pct > 0:
                                                    _sistemas_frase_st += f" y el {_otros_pct:.1f}% restante en otros sistemas."
                                                else:
                                                    _sistemas_frase_st += "."
                                            det_xe_html += f"<p>La Estación <strong>{_st_code}</strong> informa que se reportaron <strong>{_sz}</strong> colegas, que representan el <strong>{_pct_tot}</strong> del total de reportes del boletín.</p><p>{_zona_frase_st}</p><p>{_sistemas_frase_st}</p>"
                                # Desglose narrativo para estaciones específicas (XE1LM y XE2BC)
                                det_xe_html = ""
                                if isinstance(df_loc, pd.DataFrame) and ('Estación' in df_loc.columns) and total > 0:
                                    for _st_code in ['XE1LM','XE2BC']:
                                        _df_s = df_loc[df_loc['Estación'].fillna('Sin estación').astype(str) == _st_code]
                                        _sz = len(_df_s)
                                        if _sz > 0:
                                            _pct_tot = fmt_pct(_sz, total)
                                            _z_s = _df_s['Zona'].fillna('N/D').astype(str).value_counts() if 'Zona' in _df_s.columns else pd.Series(dtype=int)
                                            _s_s = _df_s['Sistema'].fillna('N/D').astype(str).value_counts() if 'Sistema' in _df_s.columns else pd.Series(dtype=int)
                                            _zona_frase_st = ""
                                            if len(_z_s) > 0:
                                                _z_pairs = list(_z_s.items())
                                                _topz = _z_pairs[0]
                                                _zona_frase_st = f"La zona {_topz[0]} fue la más activa con {int(_topz[1])} reportes ({fmt_pct(_topz[1], _sz)})"
                                                if len(_z_pairs) > 1:
                                                    _zona_frase_st += f", seguida por {_z_pairs[1][0]} ({fmt_pct(_z_pairs[1][1], _sz)})"
                                                if len(_z_pairs) > 2:
                                                    _zona_frase_st += f" y {_z_pairs[2][0]} ({fmt_pct(_z_pairs[2][1], _sz)})"
                                                _ext_st = int(_z_s.get('EXT', 0)) if hasattr(_z_s, 'get') else 0
                                                if _ext_st > 0:
                                                    _zona_frase_st += f", además de {_ext_st} estaciones extranjeras ({fmt_pct(_ext_st, _sz)})."
                                                else:
                                                    _zona_frase_st += "."
                                            _sistemas_frase_st = ""
                                            if len(_s_s) > 0:
                                                _s_pairs = list(_s_s.items())
                                                _stp = _s_pairs[0]
                                                _sistemas_frase_st = f"En cuanto a los sistemas, {_stp[0]} encabezó la actividad con el {fmt_pct(_stp[1], _sz)}"
                                                if len(_s_pairs) > 1:
                                                    _sistemas_frase_st += f", seguido por {_s_pairs[1][0]} ({fmt_pct(_s_pairs[1][1], _sz)})"
                                                if len(_s_pairs) > 2:
                                                    _sistemas_frase_st += f", {_s_pairs[2][0]} ({fmt_pct(_s_pairs[2][1], _sz)})"
                                                _otros_pct = 100.0 - sum([(v/_sz*100) for _, v in _s_pairs[:3]]) if _sz else 0.0
                                                if len(_s_pairs) > 3 and _otros_pct > 0:
                                                    _sistemas_frase_st += f" y el {_otros_pct:.1f}% restante en otros sistemas."
                                                else:
                                                    _sistemas_frase_st += "."
                                            det_xe_html += f"<p>La Estación <strong>{_st_code}</strong> informa que se reportaron <strong>{_sz}</strong> colegas, que representan el <strong>{_pct_tot}</strong> del total de reportes del boletín.</p><p>{_zona_frase_st}</p><p>{_sistemas_frase_st}</p>"
                                zonas_txt = ", ".join(zonas_presentes) + (" y EXT" if ext_count > 0 else "") if zonas_presentes or ext_count > 0 else "N/D"
                                sistema_mas_usado = (vc_s_loc.index[0] if len(vc_s_loc) > 0 else 'N/D')
                                general_stats_html = (
                                    "<ul>"
                                    f"<li>📡 Total de reportes: {total}</li>"
                                    f"<li>👥 Estaciones únicas: {ests}</li>"
                                    f"<li>🗺️ Zonas participantes: {zonas_txt}</li>"
                                    f"<li>🔗 Sistema más usado: {sistema_mas_usado}</li>"
                                    f"<li>🌎 Cobertura geográfica: {ests_geo} estados</li>"
                                    "</ul>"
                                )
                                body_html = (
                                    f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:8px;'><img src='cid:logo_fmre_small' alt='FMRE' style='height:40px'/><div style='font-family:Arial, sans-serif; font-size:16px; font-weight:700; color:#1f4e79;'>Federación Mexicana de Radioexperimentadores A.C.</div></div><hr/>"
                                    f"<p>Nos da gusto compartirles el resumen de estadísticas correspondiente a <strong>{datos['evento']}</strong> del <strong>{fecha_larga}</strong>, generado automáticamente por el Sistema de Gestión de QSO (QMS).</p>"
                                    f"<p>En esta ocasión se registraron <strong>{total}</strong> reportes, con la participación de <strong>{ests}</strong> estaciones únicas provenientes de <strong>{ests_geo}</strong> estados.</p>"
                                    f"<p>{zona_frase}</p>"
                                    f"<p>{sistemas_frase}</p>"
                                    f"<h4>Estadísticas Generales</h4>"
                                    f"{general_stats_html}"
                                    f"<h4>Distribución por Zona</h4>"
                                    f"{dist_zona_html}"
                                    f"<h4>Distribución por Sistema</h4>"
                                    f"{dist_sist_html}"
                                    f"<h4>Estaciones Control participantes</h4>"
                                    f"{top10_html}"
                                    f"<h4>Desglose por Estaciones Control</h4>"
                                    f"{det_xe_html}"
                                    f"<p>El archivo adjunto incluye el detalle completo de registros y las distribuciones por zona, sistema y estación.</p>"
                                    f"<p>¡Nos escuchamos en el próximo boletín!<br/>73 de parte del equipo de la FMRE</p>"
                                    f"<hr/><p><strong>Enviado por:</strong> {indicativo_usuario} - {nombre_usuario}</p>"
                                )
                            except Exception:
                                body_html = (
                                    f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:8px;'><img src='cid:logo_fmre_small' alt='FMRE' style='height:40px'/><div style='font-family:Arial, sans-serif; font-size:16px; font-weight:700; color:#1f4e79;'>Federación Mexicana de Radioexperimentadores A.C.</div></div><hr/>"
                                    f"<p>Se adjunta el reporte <strong>{datos['evento']}</strong> correspondiente al <strong>{datos['fecha']}</strong>.</p>"
                                )
                            default_body = body_html
                            # Actualizar el cuerpo del PDF en sesión si está vacío o contiene el fallback
                            try:
                                _curr_pdf = st.session_state.get('dlg_trad_pdf_body')
                                if (not _curr_pdf) or (isinstance(_curr_pdf, str) and 'Se adjunta el reporte' in _curr_pdf):
                                    st.session_state['dlg_trad_pdf_body'] = default_body
                            except Exception:
                                st.session_state['dlg_trad_pdf_body'] = default_body
                            # Sincronizar vista previa/textarea con el machote narrativo si hay fallback previo
                            try:
                                _curr_pdf = st.session_state.get('dlg_trad_pdf_body')
                                if (not _curr_pdf) or (isinstance(_curr_pdf, str) and 'Se adjunta el reporte' in _curr_pdf):
                                    st.session_state['dlg_trad_pdf_body'] = default_body
                            except Exception:
                                st.session_state['dlg_trad_pdf_body'] = default_body
                            try:
                                _curr_pdf = st.session_state.get('dlg_trad_pdf_body')
                                if (not _curr_pdf) or (isinstance(_curr_pdf, str) and 'Se adjunta el reporte' in _curr_pdf):
                                    st.session_state['dlg_trad_pdf_body'] = default_body
                            except Exception:
                                st.session_state['dlg_trad_pdf_body'] = default_body
                            # Sincronizar el cuerpo del PDF con el machote narrativo si la sesión está vacía o con el fallback
                            try:
                                _curr_pdf = st.session_state.get('dlg_trad_pdf_body')
                                if (not _curr_pdf) or (isinstance(_curr_pdf, str) and 'Se adjunta el reporte' in _curr_pdf):
                                    st.session_state['dlg_trad_pdf_body'] = default_body
                            except Exception:
                                st.session_state['dlg_trad_pdf_body'] = default_body
                            # Asegurar que la vista previa y el textarea no queden con el fallback minimalista
                            try:
                                _curr_pdf = st.session_state.get('dlg_trad_pdf_body')
                                if (not _curr_pdf) or (isinstance(_curr_pdf, str) and 'Se adjunta el reporte' in _curr_pdf):
                                    st.session_state['dlg_trad_pdf_body'] = default_body
                            except Exception:
                                st.session_state['dlg_trad_pdf_body'] = default_body
                            # Refrescar el cuerpo del correo (PDF) si está vacío o contiene el texto minimalista
                            try:
                                _curr_pdf = st.session_state.get('dlg_trad_pdf_body')
                                if (not _curr_pdf) or (isinstance(_curr_pdf, str) and 'Se adjunta el reporte' in _curr_pdf):
                                    st.session_state['dlg_trad_pdf_body'] = default_body
                            except Exception:
                                st.session_state['dlg_trad_pdf_body'] = default_body
                            # Refrescar el cuerpo del correo en sesión si está vacío o contiene el texto minimalista
                            try:
                                _curr = st.session_state.get('dlg_trad_pdf_body')
                                if (not _curr) or (isinstance(_curr, str) and 'Se adjunta el reporte' in _curr):
                                    st.session_state['dlg_trad_pdf_body'] = default_body
                            except Exception:
                                st.session_state['dlg_trad_pdf_body'] = default_body
                            col_l, col_r = st.columns([2, 1])
                            with col_r:
                                users_list = db.get_all_users() or []
                                user_emails = sorted({u.get('email') for u in users_list if (u.get('email') and (u.get('is_active', 1) == 1))})
                                selected_users = st.multiselect("Destinatarios (usuarios)", options=user_emails, key="dlg_trad_excel_users")
                                to_d = st.text_input("Correos (separados por coma)", key="dlg_trad_excel_to")
                                body_d = st.text_area("Cuerpo del correo (HTML permitido)", value=default_body, key="dlg_trad_excel_body", height=240)
                                send_d = st.button("📨 Enviar", type="primary", use_container_width=True, key="dlg_trad_excel_send")
                            with col_l:
                                st.subheader("Vista previa")
                                st.markdown(st.session_state.get('dlg_trad_excel_body') or default_body, unsafe_allow_html=True)
                            if send_d:
                                typed = [p.strip() for p in (to_d or "").replace(";", ",").split(",") if p.strip()]
                                from_users = [e for e in (selected_users or []) if e]
                                emails = sorted(set(typed + from_users))
                                if not emails:
                                    st.error("Ingrese al menos un destinatario")
                                elif not ex_loc:
                                    st.error("Genere el adjunto antes de enviar")
                                else:
                                    mailer = EmailSender(db)
                                    ok = mailer.send_email_with_attachments(
                                        to_emails=emails,
                                        subject=f"Reporte Tradicional {datos['evento']} - {datos['fecha']}",
                                        body=(st.session_state.get('dlg_trad_excel_body') or default_body),
                                        attachments=[(ex_loc['file_name'], ex_loc['bytes'], ex_loc['mime'])],
                                        is_html=True
                                    )
                                    if ok:
                                        st.success("✅ Correo enviado")
                                        st.balloons()
                                    else:
                                        st.error("No se pudo enviar el correo")
                        _trad_excel_dialog()
                    if not hasattr(st, "dialog"):
                        st.info("Tu versión de Streamlit no soporta ventanas modales (st.dialog). Actualiza Streamlit para usar 'Enviar por Correo'.")

        with col2:
            if st.button("📄 CSV", width='stretch'):
                # Crear CSV con datos principales
                csv_bytes = df_export.to_csv(index=False).encode('utf-8-sig')  # UTF-8 con BOM para Excel
                est_suffix = "" if selected_export_station == 'Todas' else f"_{selected_export_station.replace(' ', '_')}"
                st.session_state['trad_csv'] = {
                    'bytes': csv_bytes,
                    'file_name': f"reporte_{datos['evento']}_{datos['fecha']}{est_suffix}.csv",
                    'mime': "text/csv"
                }
                st.session_state['trad_csv_df_preview'] = df_export.copy()

            if st.session_state.get('trad_csv'):
                cv = st.session_state['trad_csv']
                st.download_button(
                    label="⬇️ Descargar CSV",
                    data=cv['bytes'],
                    file_name=cv['file_name'],
                    mime=cv['mime'],
                    key="trad_csv_download_persist",
                    width='stretch'
                )
                open_csv_modal = st.button("📧 Enviar por Correo", key="open_trad_csv_dialog", use_container_width=True)
                if open_csv_modal:
                    if hasattr(st, "dialog"):
                        @st.dialog("Enviar reporte (CSV)")
                        def _trad_csv_dialog():
                            st.markdown(
                                """
                                <style>
                                div[role='dialog'] { width: min(95vw, 1200px) !important; }
                                div[role='dialog'] > div { width: 100% !important; }
                                @media (max-width: 900px) {
                                  div[role='dialog'] [data-testid='column'] { flex: 0 0 100% !important; width: 100% !important; min-width: 100% !important; }
                                }
                                </style>
                                """,
                                unsafe_allow_html=True
                            )
                            cv_loc = st.session_state.get('trad_csv')
                            df_loc = st.session_state.get('trad_csv_df_preview')
                            if df_loc is None:
                                df_loc = df_export
                            total = int(len(df_loc)) if isinstance(df_loc, pd.DataFrame) else 0
                            ests = int(df_loc['Indicativo'].nunique()) if isinstance(df_loc, pd.DataFrame) and 'Indicativo' in df_loc.columns else 0
                            zona_m = (df_loc['Zona'].mode().iloc[0] if isinstance(df_loc, pd.DataFrame) and 'Zona' in df_loc.columns and not df_loc['Zona'].mode().empty else "N/A")
                            sist_m = (df_loc['Sistema'].mode().iloc[0] if isinstance(df_loc, pd.DataFrame) and 'Sistema' in df_loc.columns and not df_loc['Sistema'].mode().empty else "N/A")
                            ests_geo = int(df_loc['Estado'].nunique()) if isinstance(df_loc, pd.DataFrame) and 'Estado' in df_loc.columns else 0
                            zonas_html = ""
                            if isinstance(df_loc, pd.DataFrame) and 'Zona' in df_loc.columns and total > 0:
                                vc_z = df_loc['Zona'].fillna('N/D').astype(str).value_counts()
                                zonas_html = "<p><strong>Distribución por Zona:</strong></p><ul>" + "".join([f"<li>{z}: {int(c)} ({(c/total)*100:.1f}%)</li>" for z, c in vc_z.items()]) + "</ul>"
                            sistemas_html = ""
                            if isinstance(df_loc, pd.DataFrame) and 'Sistema' in df_loc.columns and total > 0:
                                vc_s = df_loc['Sistema'].fillna('N/D').astype(str).value_counts()
                                sistemas_html = "<p><strong>Distribución por Sistema:</strong></p><ul>" + "".join([f"<li>{s}: {int(c)} ({(c/total)*100:.1f}%)</li>" for s, c in vc_s.items()]) + "</ul>"
                            estaciones_html = ""
                            if isinstance(df_loc, pd.DataFrame) and 'Estación' in df_loc.columns and total > 0:
                                vc_e = df_loc['Estación'].fillna('Sin estación').astype(str).value_counts()
                                estaciones_html = "<p><strong>Desglose por Estación (top 10):</strong></p><ul>" + "".join([f"<li>{e}: {int(c)} ({(c/total)*100:.1f}%)</li>" for e, c in vc_e.head(10).items()]) + "</ul>"
                            per_station_html = ""
                            if isinstance(df_loc, pd.DataFrame) and 'Estación' in df_loc.columns and total > 0:
                                top_e = vc_e.head(5) if 'vc_e' in locals() else df_loc['Estación'].fillna('Sin estación').astype(str).value_counts().head(5)
                                items = []
                                for est_name, _cnt in top_e.items():
                                    df_s = df_loc[df_loc['Estación'].fillna('Sin estación').astype(str) == est_name]
                                    sz = len(df_s)
                                    z_block = ""
                                    if 'Zona' in df_s.columns and sz > 0:
                                        vc_zs = df_s['Zona'].fillna('N/D').astype(str).value_counts()
                                        z_block = "<ul>" + "".join([f"<li>{z}: {int(c)} ({(c/sz)*100:.1f}%)</li>" for z, c in vc_zs.items()]) + "</ul>"
                                    s_block = "" 
                                    if 'Sistema' in df_s.columns and sz > 0:
                                        vc_ss = df_s['Sistema'].fillna('N/D').astype(str).value_counts()
                                        s_block = "<ul>" + "".join([f"<li>{s}: {int(c)} ({(c/sz)*100:.1f}%)</li>" for s, c in vc_ss.items()]) + "</ul>"
                                    items.append(f"<li><strong>{est_name}</strong><ul><li>Distribución por Zona:{z_block}</li><li>Distribución por Sistema:{s_block}</li></ul></li>")
                                per_station_html = "<p><strong>Detalle por Estación (top 5):</strong></p><ul>" + "".join(items) + "</ul>"
                            # Cuerpo narrativo (CSV)
                            try:
                                meses_es = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
                                fecha_larga = datos['fecha']
                                try:
                                    fdt = datetime.strptime(datos['fecha'], '%Y-%m-%d')
                                    fecha_larga = f"{fdt.day} de {meses_es[fdt.month-1]} de {fdt.year}"
                                except Exception:
                                    pass
                                vc_z_loc = df_loc['Zona'].fillna('N/D').astype(str).value_counts() if isinstance(df_loc, pd.DataFrame) and 'Zona' in df_loc.columns and total > 0 else pd.Series(dtype=int)
                                vc_s_loc = df_loc['Sistema'].fillna('N/D').astype(str).value_counts() if isinstance(df_loc, pd.DataFrame) and 'Sistema' in df_loc.columns and total > 0 else pd.Series(dtype=int)
                                vc_e_loc = df_loc['Estación'].fillna('Sin estación').astype(str).value_counts() if isinstance(df_loc, pd.DataFrame) and 'Estación' in df_loc.columns and total > 0 else pd.Series(dtype=int)
                                def fmt_pct(n, d):
                                    return f"{(n/d*100):.1f}%" if d else "0.0%"
                                zonas_presentes = [z for z in vc_z_loc.index if z in ['XE1','XE2','XE3']]
                                ext_count = int(vc_z_loc.get('EXT', 0)) if hasattr(vc_z_loc, 'get') else 0
                                zona_frase = ""
                                if len(vc_z_loc) > 0:
                                    z_pairs = list(vc_z_loc.items())
                                    topz = z_pairs[0]
                                    zona_frase = f"La zona {topz[0]} fue la más activa con {int(topz[1])} reportes ({fmt_pct(topz[1], total)})."
                                    if len(z_pairs) > 1:
                                        z2 = z_pairs[1]
                                        zona_frase = zona_frase[:-1] + f", seguida por {z2[0]} ({fmt_pct(z2[1], total)})."
                                    if len(z_pairs) > 2:
                                        z3 = z_pairs[2]
                                        zona_frase = zona_frase[:-1] + f" y {z3[0]} ({fmt_pct(z3[1], total)})."
                                    if ext_count > 0:
                                        zona_frase = zona_frase[:-1] + f" Además, {ext_count} estaciones extranjeras ({fmt_pct(ext_count, total)})."
                                sistemas_frase = ""
                                if len(vc_s_loc) > 0:
                                    s_pairs = list(vc_s_loc.items())
                                    stp = s_pairs[0]
                                    sistemas_frase = f"En sistemas, {stp[0]} lideró con {fmt_pct(stp[1], total)}"
                                    if len(s_pairs) > 1:
                                        s2 = s_pairs[1]
                                        sistemas_frase += f", seguido por {s2[0]} ({fmt_pct(s2[1], total)})."
                                    else:
                                        sistemas_frase += "."
                                dist_zona_html = "<ul>" + "".join([f"<li>{z}: {int(c)} ({fmt_pct(c, total)})</li>" for z, c in vc_z_loc.items()]) + "</ul>" if len(vc_z_loc) > 0 else ""
                                dist_sist_html = "<ul>" + "".join([f"<li>{s}: {int(c)} ({fmt_pct(c, total)})</li>" for s, c in vc_s_loc.items()]) + "</ul>" if len(vc_s_loc) > 0 else ""
                                top10 = list(vc_e_loc.items())[:10]
                                top10_html = "<ul>" + "".join([f"<li>{e}: {int(c)} ({fmt_pct(c, total)})</li>" for e, c in top10]) + "</ul>" if top10 else ""
                                # Desglose narrativo para estaciones específicas (XE1LM y XE2BC)
                                det_xe_html = ""
                                for _st_code in ['XE1LM','XE2BC']:
                                    _df_s = df_loc[df_loc['Estación'].fillna('Sin estación').astype(str) == _st_code]
                                    _sz = len(_df_s)
                                    if _sz > 0:
                                        _pct_tot = fmt_pct(_sz, total)
                                        _z_s = _df_s['Zona'].fillna('N/D').astype(str).value_counts() if 'Zona' in _df_s.columns else pd.Series(dtype=int)
                                        _s_s = _df_s['Sistema'].fillna('N/D').astype(str).value_counts() if 'Sistema' in _df_s.columns else pd.Series(dtype=int)
                                        _zona_frase_st = ""
                                        if len(_z_s) > 0:
                                            _z_pairs = list(_z_s.items())
                                            _topz = _z_pairs[0]
                                            _zona_frase_st = f"La zona {_topz[0]} fue la más activa con {int(_topz[1])} reportes ({fmt_pct(_topz[1], _sz)})"
                                            if len(_z_pairs) > 1:
                                                _zona_frase_st += f", seguida por {_z_pairs[1][0]} ({fmt_pct(_z_pairs[1][1], _sz)})"
                                            if len(_z_pairs) > 2:
                                                _zona_frase_st += f" y {_z_pairs[2][0]} ({fmt_pct(_z_pairs[2][1], _sz)})"
                                            _ext_st = int(_z_s.get('EXT', 0)) if hasattr(_z_s, 'get') else 0
                                            if _ext_st > 0:
                                                _zona_frase_st += f", además de {_ext_st} estaciones extranjeras ({fmt_pct(_ext_st, _sz)})."
                                            else:
                                                _zona_frase_st += "."
                                        _sistemas_frase_st = ""
                                        if len(_s_s) > 0:
                                            _s_pairs = list(_s_s.items())
                                            _stp = _s_pairs[0]
                                            _sistemas_frase_st = f"En cuanto a los sistemas, {_stp[0]} encabezó la actividad con el {fmt_pct(_stp[1], _sz)}"
                                            if len(_s_pairs) > 1:
                                                _sistemas_frase_st += f", seguido por {_s_pairs[1][0]} ({fmt_pct(_s_pairs[1][1], _sz)})"
                                            if len(_s_pairs) > 2:
                                                _sistemas_frase_st += f", {_s_pairs[2][0]} ({fmt_pct(_s_pairs[2][1], _sz)})"
                                            _otros_pct = 100.0 - sum([(v/_sz*100) for _, v in _s_pairs[:3]]) if _sz else 0.0
                                            if len(_s_pairs) > 3 and _otros_pct > 0:
                                                _sistemas_frase_st += f" y el {_otros_pct:.1f}% restante en otros sistemas."
                                            else:
                                                _sistemas_frase_st += "."
                                        det_xe_html += f"<p>La Estación <strong>{_st_code}</strong> informa que se reportaron <strong>{_sz}</strong> colegas, que representan el <strong>{_pct_tot}</strong> del total de reportes del boletín.</p><p>{_zona_frase_st}</p><p>{_sistemas_frase_st}</p>"
                                zonas_txt = ", ".join(zonas_presentes) + (" y EXT" if ext_count > 0 else "") if zonas_presentes or ext_count > 0 else "N/D"
                                sistema_mas_usado = (vc_s_loc.index[0] if len(vc_s_loc) > 0 else 'N/D')
                                general_stats_html = (
                                    "<ul>"
                                    f"<li>📡 Total de reportes: {total}</li>"
                                    f"<li>👥 Estaciones únicas: {ests}</li>"
                                    f"<li>🗺️ Zonas participantes: {zonas_txt}</li>"
                                    f"<li>🔗 Sistema más usado: {sistema_mas_usado}</li>"
                                    f"<li>🌎 Cobertura geográfica: {ests_geo} estados</li>"
                                    "</ul>"
                                )
                                body_html = (
                                    f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:8px;'><img src='cid:logo_fmre_small' alt='FMRE' style='height:40px'/><div style='font-family:Arial, sans-serif; font-size:16px; font-weight:700; color:#1f4e79;'>Federación Mexicana de Radioexperimentadores A.C.</div></div><hr/>"
                                    f"<p>Nos da gusto compartirles el resumen de estadísticas correspondiente a <strong>{datos['evento']}</strong> del <strong>{fecha_larga}</strong>, generado automáticamente por el Sistema de Gestión de QSO (QMS).</p>"
                                    f"<p>En esta ocasión se registraron <strong>{total}</strong> reportes, con la participación de <strong>{ests}</strong> estaciones únicas provenientes de <strong>{ests_geo}</strong> estados.</p>"
                                    f"<p>{zona_frase}</p>"
                                    f"<p>{sistemas_frase}</p>"
                                    f"<h4>Estadísticas Generales</h4>"
                                    f"{general_stats_html}"
                                    f"<h4>Distribución por Zona</h4>"
                                    f"{dist_zona_html}"
                                    f"<h4>Distribución por Sistema</h4>"
                                    f"{dist_sist_html}"
                                    f"<h4>Estaciones Control participantes</h4>"
                                    f"{top10_html}"
                                    f"<h4>Desglose por Estaciones Control</h4>"
                                    f"{det_xe_html}"
                                    f"<p>El archivo adjunto incluye el detalle completo de registros y las distribuciones por zona, sistema y estación.</p>"
                                    f"<p>¡Nos escuchamos en el próximo boletín!<br/>73 de parte del equipo de la FMRE</p>"
                                    f"<hr/><p><strong>Enviado por:</strong> {indicativo_usuario} - {nombre_usuario}</p>"
                                )
                            except Exception:
                                body_html = (
                                    f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:8px;'><img src='cid:logo_fmre_small' alt='FMRE' style='height:40px'/><div style='font-family:Arial, sans-serif; font-size:16px; font-weight:700; color:#1f4e79;'>Federación Mexicana de Radioexperimentadores A.C.</div></div><hr/>"
                                    f"<p>Se adjunta el reporte <strong>{datos['evento']}</strong> correspondiente al <strong>{datos['fecha']}</strong>.</p>"
                                )
                            default_body = body_html
                            try:
                                _curr_pdf = st.session_state.get('dlg_trad_pdf_body')
                                if (not _curr_pdf) or (isinstance(_curr_pdf, str) and 'Se adjunta el reporte' in _curr_pdf):
                                    st.session_state['dlg_trad_pdf_body'] = default_body
                            except Exception:
                                st.session_state['dlg_trad_pdf_body'] = default_body
                            col_l, col_r = st.columns([2, 1])
                            with col_r:
                                users_list = db.get_all_users() or []
                                user_emails = sorted({u.get('email') for u in users_list if (u.get('email') and (u.get('is_active', 1) == 1))})
                                selected_users = st.multiselect("Destinatarios (usuarios)", options=user_emails, key="dlg_trad_csv_users")
                                to_d = st.text_input("Correos (separados por coma)", key="dlg_trad_csv_to")
                                body_d = st.text_area("Cuerpo del correo (HTML permitido)", value=default_body, key="dlg_trad_csv_body", height=240)
                                send_d = st.button("📨 Enviar", type="primary", use_container_width=True, key="dlg_trad_csv_send")
                            with col_l:
                                st.subheader("Vista previa")
                                st.markdown(st.session_state.get('dlg_trad_csv_body') or default_body, unsafe_allow_html=True)
                            if send_d:
                                typed = [p.strip() for p in (to_d or "").replace(";", ",").split(",") if p.strip()]
                                from_users = [e for e in (selected_users or []) if e]
                                emails = sorted(set(typed + from_users))
                                if not emails:
                                    st.error("Ingrese al menos un destinatario")
                                elif not cv_loc:
                                    st.error("Genere el adjunto antes de enviar")
                                else:
                                    mailer = EmailSender(db)
                                    ok = mailer.send_email_with_attachments(
                                        to_emails=emails,
                                        subject=f"Reporte Tradicional {datos['evento']} - {datos['fecha']}",
                                        body=(st.session_state.get('dlg_trad_csv_body') or default_body),
                                        attachments=[(cv_loc['file_name'], cv_loc['bytes'], cv_loc['mime'])],
                                        is_html=True
                                    )
                                    if ok:
                                        st.success("✅ Correo enviado")
                                        st.balloons()
                                    else:
                                        st.error("No se pudo enviar el correo")
                        _trad_csv_dialog()
                    if not hasattr(st, "dialog"):
                        st.info("Tu versión de Streamlit no soporta ventanas modales (st.dialog). Actualiza Streamlit para usar 'Enviar por Correo'.")

        with col3:
            if st.button("📋 PDF", width='stretch'):
                # Generar PDF con información detallada
                from reportlab.lib import colors
                from reportlab.lib.pagesizes import letter, A4, landscape
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image, Frame, PageTemplate, HRFlowable, NextPageTemplate, BaseDocTemplate
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.units import inch
                from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
                from reportlab.pdfgen.canvas import Canvas
                import textwrap
                import os

                # Crear buffer para el PDF
                buffer = io.BytesIO()

                # Etiqueta dinámica de encabezado por sección
                header_current_station = {
                    'label': (selected_export_station if selected_export_station != 'Todas' else 'General')
                }

                # Función para crear el encabezado ultra compacto
                def create_header(canvas, doc, **kwargs):
                    canvas.saveState()
                    
                    # Configuración de márgenes y tamaños
                    logo_size = 0.2 * inch  # Logo muy pequeño
                    top_margin = 0  # Sin margen superior
                    
                    # Texto del encabezado - todo en una sola línea compacta
                    canvas.setFont('Helvetica', 4)  # Fuente más pequeña y normal (no negrita)
                    canvas.setFillColor(colors.HexColor('#333333'))  # Gris oscuro para mejor legibilidad
                    
                    # Texto en una sola línea: Evento | Fecha | Página
                    fecha_formateada = datetime.strptime(datos['fecha'], '%Y-%m-%d').strftime('%d/%m/%y')
                    # Acortar el nombre del evento a 15 caracteres máximo
                    evento = (datos['evento'][:12] + '...') if len(datos['evento']) > 15 else datos['evento']
                    header_text = f"{evento} | {fecha_formateada} | Estación: {header_current_station['label']} | Página {canvas.getPageNumber()}"
                    
                    # Posición del texto (arriba a la izquierda)
                    text_x = doc.leftMargin
                    text_y = A4[1] - 0.15 * inch  # Muy pegado al borde superior
                    
                    # Logo pequeño en la esquina superior derecha
                    logo_path = os.path.join(os.path.dirname(__file__), 'assets', 'LogoFMRE_small.png')
                    if os.path.exists(logo_path):
                        logo = Image(logo_path, width=logo_size, height=logo_size)
                        logo.drawOn(canvas, A4[0] - doc.rightMargin - logo_size, A4[1] - logo_size - top_margin)
                    
                    # Dibujar el texto
                    canvas.drawString(text_x, text_y, header_text)
                    
                    # Línea divisoria muy fina
                    line_y = text_y - 0.1 * inch
                    canvas.setStrokeColor(colors.HexColor('#CCCCCC'))  # Línea gris claro
                    canvas.setLineWidth(0.1)
                    canvas.line(doc.leftMargin, line_y, A4[0] - doc.rightMargin, line_y)
                    
                    # Ajustar el margen superior del contenido
                    doc.topMargin = 0.15 * inch  # Mínimo espacio necesario
                    
                    canvas.restoreState()
                    
                    # Llamar al método onPage de la plantilla si existe
                    if hasattr(doc, 'onPage'):
                        doc.onPage(canvas, doc)

                # Función para agregar el encabezado a cada página
                def add_header_footer(canvas, doc):
                    # Guardar el estado del canvas
                    canvas.saveState()
                    
                    # Configuración de márgenes y tamaños
                    logo_size = 0.2 * inch
                    
                    # Texto del encabezado
                    canvas.setFont('Helvetica', 4)
                    canvas.setFillColor(colors.HexColor('#333333'))
                    
                    # Texto en una sola línea: Evento | Fecha | Página
                    fecha_formateada = datetime.strptime(datos['fecha'], '%Y-%m-%d').strftime('%d/%m/%y')
                    evento = (datos['evento'][:12] + '...') if len(datos['evento']) > 15 else datos['evento']
                    
                    # Texto del encabezado (sin logo)
                    header_text = f"{evento} | {fecha_formateada} | Estación: {header_current_station['label']} | Página {canvas.getPageNumber()}"
                    canvas.drawString(doc.leftMargin, doc.height + doc.bottomMargin + 5, header_text)
                    
                    # Línea divisoria
                    canvas.setStrokeColor(colors.HexColor('#CCCCCC'))
                    canvas.setLineWidth(0.1)
                    canvas.line(doc.leftMargin, doc.bottomMargin + 2, 
                              doc.width + doc.leftMargin, doc.bottomMargin + 2)
                    
                    # Restaurar el estado del canvas
                    canvas.restoreState()
                
                # Crear una clase de documento personalizada que ignora los cambios de plantilla
                class SimpleDocTemplateNoTemplates(SimpleDocTemplate):
                    def handle_nextPageTemplate(self, *args, **kwargs):
                        # Ignorar cualquier intento de cambiar la plantilla
                        pass
                
                # Crear el documento PDF con nuestra clase personalizada
                doc = SimpleDocTemplateNoTemplates(
                    buffer,
                    pagesize=letter,
                    rightMargin=72,
                    leftMargin=72,
                    topMargin=36,  # Espacio para el encabezado
                    bottomMargin=36
                )
                
                # Inicializar la historia como una lista normal
                story = []

                # Estilos compactos
                styles = getSampleStyleSheet()

                # Estilo para el título principal (más compacto)
                title_style = ParagraphStyle(
                    'CustomTitle',
                    parent=styles['Heading1'],
                    fontSize=16,
                    spaceAfter=8,
                    textColor=colors.HexColor('#1f4e79'),
                    alignment=1
                )

                # Estilo para el subtítulo (más compacto)
                subtitle_style = ParagraphStyle(
                    'CustomSubtitle',
                    parent=styles['Heading2'],
                    fontSize=12,
                    spaceAfter=5,
                    textColor=colors.HexColor('#2c5f2d'),
                    alignment=1
                )

                # Estilo para información general (más compacto)
                info_style = ParagraphStyle(
                    'InfoStyle',
                    parent=styles['Normal'],
                    fontSize=10,
                    spaceAfter=3,
                    textColor=colors.HexColor('#333333'),
                    alignment=0
                )

                # Estilo para secciones con formato de oración
                section_style = ParagraphStyle(
                    'SectionStyle',
                    parent=styles['Normal'],
                    fontSize=12,
                    fontName='Helvetica-Bold',
                    spaceBefore=0,
                    spaceAfter=0,   # Controlamos el espacio con Spacer
                    leading=12,     # Mismo que el tamaño de fuente
                    textColor=colors.HexColor('#1f4e79'),
                    leftIndent=0,
                    rightIndent=0,
                    textTransform='none'  # Asegura que no se aplique mayúsculas
                )

                normal_style = styles['Normal']

                # Contenido del PDF
                story = []
                
                # Primera página en retrato
                story.append(NextPageTemplate('Portrait'))

                # Información del evento (más compacta)
                event_info = [
                    f"<b>Evento:</b> {datos['evento']} | <b>Fecha:</b> {datos['fecha']}",
                    f"<b>Generado por:</b> {indicativo_usuario} - {nombre_usuario} | <b>Fecha de generación:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                ]

                for info in event_info:
                    story.append(Paragraph(info, info_style))

                story.append(Spacer(1, 10))

                # Estadísticas principales con mejor formato
                story.append(Paragraph("Estadísticas del evento", section_style))
                story.append(Spacer(1, 8))  # Espacio después del título

                estaciones_unicas_pdf = df_export['Indicativo'].nunique()
                zona_mas_reportada_pdf = (df_export['Zona'].mode().iloc[0] if not df_export['Zona'].mode().empty else "N/A")
                sistema_mas_usado_pdf = (df_export['Sistema'].mode().iloc[0] if not df_export['Sistema'].mode().empty else "N/A")
                cobertura_estados_pdf = df_export['Estado'].nunique() if 'Estado' in df_export.columns else 0

                stats_data = [
                    ['Métrica', 'Valor', 'Detalles'],
                    ['Total de Reportes', str(len(df_export)), f"Participantes activos: {len(df_export)}"],
                    ['Estaciones Únicas', str(estaciones_unicas_pdf), f"Diferentes estaciones que reportaron"],
                    ['Zona Más Reportada', zona_mas_reportada_pdf, f"Concentración geográfica principal"],
                    ['Sistema Más Usado', sistema_mas_usado_pdf, f"Tecnología de radio predominante"],
                    ['Cobertura Geográfica', f"{cobertura_estados_pdf} estados", f"Alcance territorial del evento"]
                ]

                # Crear la tabla directamente con los datos
                stats_table = Table(stats_data)
                stats_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),  # Tamaño de fuente 10pt
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 6),  # Espaciado reducido
                    ('TOPPADDING', (0, 0), (-1, 0), 4),  # Espaciado superior añadido
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#333333')),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),  # Tamaño de fuente reducido
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 3)  # Espaciado reducido
                ]))
                story.append(stats_table)

                # Distribuciones filtradas para PDF
                zonas_count_pdf = df_export['Zona'].value_counts()
                df_zonas_pdf = pd.DataFrame({
                    'Zona': zonas_count_pdf.index,
                    'Cantidad': zonas_count_pdf.values,
                    'Porcentaje': (zonas_count_pdf.values / max(len(df_export), 1) * 100).round(1)
                })
                sistemas_count_pdf = df_export['Sistema'].value_counts()
                df_sistemas_pdf = pd.DataFrame({
                    'Sistema': sistemas_count_pdf.index,
                    'Cantidad': sistemas_count_pdf.values,
                    'Porcentaje': (sistemas_count_pdf.values / max(len(df_export), 1) * 100).round(1)
                })

                # Título con formato de oración
                story.append(Paragraph("Distribución por zona geográfica", section_style))
                story.append(Spacer(1, 8))  # Espacio después del título

                zonas_data = [['Zona', 'Cantidad', 'Porcentaje', 'Participación']]
                for _, row in df_zonas_pdf.iterrows():
                    zonas_data.append([
                        str(row['Zona']),
                        str(int(row['Cantidad'])),
                        f"{row['Porcentaje']:.1f}%",
                        "●" * min(int(row['Cantidad']), 10)
                    ])

                zonas_table = Table(zonas_data)
                zonas_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5f2d')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),  # Tamaño de fuente 10pt
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 6),  # Espaciado reducido
                    ('TOPPADDING', (0, 0), (-1, 0), 4),  # Espaciado superior añadido
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0f8f0')),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#2c5f2d')),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),  # Tamaño de fuente reducido
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#90EE90')),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 3)  # Espaciado reducido
                ]))
                story.append(zonas_table)
# Título con formato de oración
                story.append(Paragraph("Principales estados participantes", section_style))
                story.append(Spacer(1, 8))  # Espacio después del título

                # Calcular los 3 estados con más reportes (filtrado)
                estados_count = df_export['Estado'].value_counts()
                top_estados = estados_count.head(3)

                estados_data = [['Estado', 'Reportes', 'Porcentaje', 'Participación']]
                for estado, cantidad in top_estados.items():
                    if estado and estado.strip():
                        porcentaje = (cantidad / max(len(df_export), 1) * 100)
                        estados_data.append([
                            str(estado),
                            str(int(cantidad)),
                            f"{porcentaje:.1f}%",
                            "●" * min(int(cantidad), 12)
                        ])

                if len(estados_data) > 1:
                    estados_table = Table(estados_data)
                    estados_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DC143C')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 10),  # Tamaño de fuente reducido
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),  # Reducido de 10 a 6
                        ('TOPPADDING', (0, 0), (-1, 0), 4),  # Añadido padding superior
                        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FFF0F0')),
                        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#DC143C')),
                        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 1), (-1, -1), 9),  # Mantenido en 9
                        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#FFB6C1')),
                        ('BOTTOMPADDING', (0, 1), (-1, -1), 4)  # Reducido de 6 a 4
                    ]))
                    story.append(estados_table)
                    story.append(Spacer(1, 20))

                # Distribución por sistema de radio
                story.append(Paragraph("Distribución por sistema de radio", section_style))
                story.append(Spacer(1, 8))  # Espacio después del título

                sistemas_data = [['Sistema', 'Cantidad', 'Porcentaje', 'Uso']]
                for _, row in df_sistemas_pdf.iterrows():
                    sistemas_data.append([
                        str(row['Sistema']),
                        str(int(row['Cantidad'])),
                        f"{row['Porcentaje']:.1f}%",
                        "●" * min(int(row['Cantidad']), 8)
                    ])

                sistemas_table = Table(sistemas_data)
                sistemas_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8B4513')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),  # Reducido de 12 a 10
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 6),  # Reducido de 10 a 6
                    ('TOPPADDING', (0, 0), (-1, 0), 4),  # Añadido padding superior
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FFF8DC')),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#8B4513')),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),  # Mantenido en 9
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#DEB887')),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 4)  # Reducido de 6 a 4
                ]))
                story.append(sistemas_table)

                # Si se exportan todas las estaciones, añadir secciones por estación
                if selected_export_station == 'Todas':
                    # Ordenar estaciones alfabéticamente, ignorando vacíos
                    estaciones_lista = sorted([e for e in datos['df_evento']['Estación'].dropna().unique().tolist() if str(e).strip()])

                    for est in estaciones_lista:
                        # Nueva página por estación y actualizar encabezado
                        story.append(PageBreak())
                        header_current_station['label'] = est

                        # Sección de estación
                        story.append(Paragraph(f"Estación: {est}", section_style))
                        story.append(Spacer(1, 8))

                        df_est = datos['df_evento'][datos['df_evento']['Estación'] == est]

                        # Métricas de estación
                        est_estaciones_unicas = df_est['Indicativo'].nunique()
                        est_zona_mas = (df_est['Zona'].mode().iloc[0] if not df_est['Zona'].mode().empty else "N/A")
                        est_sistema_mas = (df_est['Sistema'].mode().iloc[0] if not df_est['Sistema'].mode().empty else "N/A")
                        est_cobertura = df_est['Estado'].nunique() if 'Estado' in df_est.columns else 0

                        stats_est = [
                            ['Métrica', 'Valor', 'Detalles'],
                            ['Total de Reportes', str(len(df_est)), f"Participantes activos: {len(df_est)}"],
                            ['Estaciones Únicas', str(est_estaciones_unicas), f"Diferentes estaciones que reportaron"],
                            ['Zona Más Reportada', est_zona_mas, f"Concentración geográfica principal"],
                            ['Sistema Más Usado', est_sistema_mas, f"Tecnología de radio predominante"],
                            ['Cobertura Geográfica', f"{est_cobertura} estados", f"Alcance territorial del evento"]
                        ]

                        table_est = Table(stats_est)
                        table_est.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 10),
                            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                            ('TOPPADDING', (0, 0), (-1, 0), 4),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#333333')),
                            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                            ('FONTSIZE', (0, 1), (-1, -1), 8),
                            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
                            ('BOTTOMPADDING', (0, 1), (-1, -1), 3)
                        ]))
                        story.append(table_est)
                        story.append(Spacer(1, 10))

                        # Distribución por zona (estación)
                        zonas_est = df_est['Zona'].value_counts()
                        df_zonas_est = pd.DataFrame({
                            'Zona': zonas_est.index,
                            'Cantidad': zonas_est.values,
                            'Porcentaje': (zonas_est.values / max(len(df_est), 1) * 100).round(1)
                        })

                        story.append(Paragraph("Distribución por zona geográfica", section_style))
                        story.append(Spacer(1, 6))
                        zonas_data_est = [['Zona', 'Cantidad', 'Porcentaje', 'Participación']]
                        for _, row in df_zonas_est.iterrows():
                            zonas_data_est.append([
                                str(row['Zona']), str(int(row['Cantidad'])), f"{row['Porcentaje']:.1f}%", "●" * min(int(row['Cantidad']), 10)
                            ])
                        zonas_table_est = Table(zonas_data_est)
                        zonas_table_est.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5f2d')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 10),
                            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                            ('TOPPADDING', (0, 0), (-1, 0), 4),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0f8f0')),
                            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#2c5f2d')),
                            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                            ('FONTSIZE', (0, 1), (-1, -1), 8),
                            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#90EE90')),
                            ('BOTTOMPADDING', (0, 1), (-1, -1), 3)
                        ]))
                        story.append(zonas_table_est)
                        story.append(Spacer(1, 10))

                        # Principales estados (estación)
                        story.append(Paragraph("Principales estados participantes", section_style))
                        story.append(Spacer(1, 6))
                        estados_est = df_est['Estado'].value_counts()
                        top_est = estados_est.head(3)
                        estados_data_est = [['Estado', 'Reportes', 'Porcentaje', 'Participación']]
                        for estado, cantidad in top_est.items():
                            if estado and str(estado).strip():
                                pct = (cantidad / max(len(df_est), 1) * 100)
                                estados_data_est.append([str(estado), str(int(cantidad)), f"{pct:.1f}%", "●" * min(int(cantidad), 12)])
                        if len(estados_data_est) > 1:
                            estados_table_est = Table(estados_data_est)
                            estados_table_est.setStyle(TableStyle([
                                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DC143C')),
                                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                ('FONTSIZE', (0, 0), (-1, 0), 10),
                                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                                ('TOPPADDING', (0, 0), (-1, 0), 4),
                                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FFF0F0')),
                                ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#DC143C')),
                                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                                ('FONTSIZE', (0, 1), (-1, -1), 8),
                                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#FFB6C1')),
                                ('BOTTOMPADDING', (0, 1), (-1, -1), 3)
                            ]))
                            story.append(estados_table_est)
                            story.append(Spacer(1, 10))

                        # Distribución por sistema (estación)
                        story.append(Paragraph("Distribución por sistema de radio", section_style))
                        story.append(Spacer(1, 6))
                        sistemas_est = df_est['Sistema'].value_counts()
                        df_sist_est = pd.DataFrame({
                            'Sistema': sistemas_est.index,
                            'Cantidad': sistemas_est.values,
                            'Porcentaje': (sistemas_est.values / max(len(df_est), 1) * 100).round(1)
                        })
                        sist_data_est = [['Sistema', 'Cantidad', 'Porcentaje', 'Uso']]
                        for _, row in df_sist_est.iterrows():
                            sist_data_est.append([str(row['Sistema']), str(int(row['Cantidad'])), f"{row['Porcentaje']:.1f}%", "●" * min(int(row['Cantidad']), 8)])
                        sist_table_est = Table(sist_data_est)
                        sist_table_est.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8B4513')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 9),
                            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                            ('TOPPADDING', (0, 0), (-1, 0), 4),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FFF8DC')),
                            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#8B4513')),
                            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                            ('FONTSIZE', (0, 1), (-1, -1), 8),
                            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#DEB887')),
                            ('BOTTOMPADDING', (0, 1), (-1, -1), 3)
                        ]))
                        story.append(sist_table_est)

                # Generar el PDF con la historia
                try:
                    doc.build(story, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
                except Exception as e:
                    st.error(f"Error al generar el PDF: {str(e)}")

                # Estilos personalizados
                styles = getSampleStyleSheet()

                # Estilo para el título principal
                title_style = ParagraphStyle(
                    'CustomTitle',
                    parent=styles['Heading1'],
                    fontSize=20,  # Reducido de 28
                    spaceAfter=15,  # Reducido de 20
                    textColor=colors.HexColor('#1f4e79'),  # Azul FMRE
                    alignment=1  # Centrado
                )

                # Estilo para el subtítulo
                subtitle_style = ParagraphStyle(
                    'CustomSubtitle',
                    parent=styles['Heading2'],
                    fontSize=14,  # Reducido de 18
                    spaceAfter=10,  # Reducido de 15
                    textColor=colors.HexColor('#2c5f2d'),  # Verde FMRE
                    alignment=1  # Centrado
                )

                # Estilo para información general (más compacto)
                info_style = ParagraphStyle(
                    'InfoStyle',
                    parent=styles['Normal'],
                    fontSize=10,
                    spaceAfter=4,  # Reducido de 10 a 4 puntos
                    textColor=colors.HexColor('#333333'),
                    alignment=1,  # Centrado
                    leading=12    # Interlineado reducido
                )

                # Estilo para secciones con formato de oración
                section_style = ParagraphStyle(
                    'SectionStyle',
                    parent=styles['Normal'],
                    fontSize=12,
                    fontName='Helvetica-Bold',
                    spaceBefore=0,
                    spaceAfter=0,   # Controlamos el espacio con Spacer
                    leading=12,     # Mismo que el tamaño de fuente
                    textColor=colors.HexColor('#1f4e79'),
                    leftIndent=0,
                    rightIndent=0,
                    textTransform='none'  # Asegura que no se aplique mayúsculas
                )

                normal_style = styles['Normal']

                # Inicializar la historia
                story = []

                # Encabezado compacto con logo y título
                logo_path = os.path.join(os.path.dirname(__file__), 'assets', 'LogoFMRE_medium.png')
                
                # Estilo de párrafo para el encabezado
                header_style = ParagraphStyle(
                    'HeaderStyle',
                    fontName='Helvetica-Bold',
                    fontSize=11,  # Aumentado a 11 puntos
                    leading=13,   # Interlineado ajustado
                    spaceBefore=0,
                    spaceAfter=0,
                    alignment=TA_CENTER,
                    textColor=colors.HexColor('#006400'),
                    leftIndent=0,
                    rightIndent=0
                )

                # Verificar si el logo existe
                if os.path.exists(logo_path):
                    # Crear tabla para el encabezado con tamaño reducido
                    # Tabla con logo y texto, manteniendo proporciones
                    header_data = [
                        [
                            Image(logo_path, width=0.8*inch, height=0.8*inch, kind='proportional'),
                            Paragraph("FEDERACIÓN MEXICANA DE RADIOEXPERIMENTADORES", header_style)
                        ]
                    ]

                    # Crear tabla con borde para el encabezado
                    header_table = Table(header_data, 
                                     colWidths=[1.0*inch, 5*inch],  # Anchos de columna fijos
                                     rowHeights=[0.7*inch])  # Altura reducida para el encabezado
                    header_table.setStyle(TableStyle([
                        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),  # Reducido de 8 a 6
                        ('TOPPADDING', (0, 0), (-1, -1), 6),     # Reducido de 8 a 6
                        ('LEFTPADDING', (0, 0), (-1, -1), 4),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                        ('TEXTCOLOR', (1, 0), (1, 0), colors.HexColor('#2c3e50')),
                        ('FONTSIZE', (0, 0), (-1, -1), 10),  # Tamaño de fuente reducido
                        # Borde sutil alrededor del encabezado
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
                        # Línea vertical entre el logo y el texto
                        ('LINEAFTER', (0, 0), (0, 0), 0.5, colors.HexColor('#DDDDDD')),
                        # Fondo ligeramente coloreado
                        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8F9FA'))
                    ]))
                    # Añadir espacio antes del encabezado con borde
                    story.append(Spacer(1, 6))
                    # Añadir el encabezado con borde
                    story.append(header_table)
                    # Espacio después del encabezado
                    story.append(Spacer(1, 6))
                else:
                    # Si no hay logo, solo el título centrado
                    story.append(Paragraph("FEDERACIÓN MEXICANA DE RADIOEXPERIMENTADORES", 
                                        style=ParagraphStyle(
                                            'HeaderNoLogo',
                                            fontName='Helvetica-Bold',
                                            fontSize=8,
                                            alignment=TA_CENTER,
                                            spaceAfter=2
                                        )))
                    story.append(Spacer(1, 2))  # Espacio mínimo después del encabezado sin logo

                # Información del evento
                story.append(Paragraph(f"<b>Evento:</b> {datos['evento']}", info_style))
                story.append(Paragraph(f"<b>Fecha del Evento:</b> {datos['fecha']}", info_style))
                story.append(Paragraph(f"<b>Fecha de Generación:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", info_style))
                story.append(Paragraph(f"<b>Generado por:</b> {indicativo_usuario} - {nombre_usuario}", info_style))
                story.append(Spacer(1, 2))  # Espacio reducido después de la información

                # Línea divisoria más delgada
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#CCCCCC')))
                # Título con formato de oración
                story.append(Paragraph("Estadísticas del evento", section_style))
                story.append(Spacer(1, 8))  # Espacio después del título

                stats_data = [
                    ['Métrica', 'Valor', 'Detalles'],
                    ['Total de Reportes', str(len(df_export)), f"Participantes activos: {len(df_export)}"],
                    ['Estaciones Únicas', str(estaciones_unicas_pdf), f"Diferentes estaciones que reportaron"],
                    ['Zona Más Reportada', zona_mas_reportada_pdf, f"Concentración geográfica principal"],
                    ['Sistema Más Usado', sistema_mas_usado_pdf, f"Tecnología de radio predominante"],
                    ['Cobertura Geográfica', f"{(df_export['Estado'].nunique() if 'Estado' in df_export.columns else 0)} estados", f"Alcance territorial del evento"]
                ]

                stats_table = Table(stats_data)
                stats_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),  # Reducido de 14 a 10
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 6),  # Reducido de 12 a 6
                    ('TOPPADDING', (0, 0), (-1, 0), 4),  # Añadido padding superior
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#333333')),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),  # Reducido de 10 a 8
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 3)  # Reducido de 8 a 3
                ]))
                story.append(stats_table)
                story.append(Spacer(1, 25))

                # Distribución por Zona con mejor formato
                story.append(Paragraph("Distribución por zona geográfica", section_style))
                story.append(Spacer(1, 8))  # Espacio después del título

                zonas_data = [['Zona', 'Cantidad', 'Porcentaje', 'Participación']]
                for _, row in df_zonas_pdf.iterrows():
                    zonas_data.append([
                        str(row['Zona']),
                        str(int(row['Cantidad'])),
                        f"{row['Porcentaje']:.1f}%",
                        "●" * min(int(row['Cantidad']), 10)  # Indicador visual
                    ])

                zonas_table = Table(zonas_data)
                zonas_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5f2d')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),  # Tamaño de fuente 10pt
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 6),  # Espaciado reducido
                    ('TOPPADDING', (0, 0), (-1, 0), 4),  # Espaciado superior añadido
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0f8f0')),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#2c5f2d')),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),  # Tamaño de fuente reducido
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#90EE90')),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 3)  # Espaciado reducido
                ]))
                story.append(zonas_table)
                story.append(Spacer(1, 20))

                # Principales Estados de México
                story.append(Paragraph("Principales estados participantes", section_style))
                story.append(Spacer(1, 8))  # Espacio después del título

                # Calcular los 3 estados con más reportes (filtrado)
                estados_count = df_export['Estado'].value_counts()
                top_estados = estados_count.head(3)

                estados_data = [['Estado', 'Reportes', 'Porcentaje', 'Participación']]
                for estado, cantidad in top_estados.items():
                    if estado and estado.strip():  # Solo incluir estados no vacíos
                        porcentaje = (cantidad / max(len(df_export), 1) * 100)
                        estados_data.append([
                            str(estado),
                            str(int(cantidad)),
                            f"{porcentaje:.1f}%",
                            "●" * min(int(cantidad), 12)  # Indicador visual
                        ])

                # Solo agregar la tabla si hay estados
                if len(estados_data) > 1:
                    estados_table = Table(estados_data)
                    estados_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DC143C')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 10),  # Tamaño de fuente 10pt
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),  # Reducido de 10 a 6
                        ('TOPPADDING', (0, 0), (-1, 0), 4),  # Añadido padding superior
                        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FFF0F0')),
                        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#DC143C')),
                        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 1), (-1, -1), 9),  # Mantenido en 9
                        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#FFB6C1')),
                        ('BOTTOMPADDING', (0, 1), (-1, -1), 4)  # Reducido de 6 a 4
                    ]))
                    story.append(estados_table)
                    story.append(Spacer(1, 20))

                # Distribución por Sistema con mejor formato
                story.append(Paragraph("Distribución por sistema de radio", section_style))
                story.append(Spacer(1, 8))  # Espacio después del título

                sistemas_data = [['Sistema', 'Cantidad', 'Porcentaje', 'Uso']]
                for _, row in df_sistemas_pdf.iterrows():
                    sistemas_data.append([
                        str(row['Sistema']),
                        str(int(row['Cantidad'])),
                        f"{row['Porcentaje']:.1f}%",
                        "●" * min(int(row['Cantidad']), 8)  # Indicador visual
                    ])

                sistemas_table = Table(sistemas_data)
                sistemas_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8B4513')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),  # Reducido de 12 a 10
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 6),  # Reducido de 10 a 6
                    ('TOPPADDING', (0, 0), (-1, 0), 4),  # Añadido padding superior
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FFF8DC')),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#8B4513')),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),  # Mantenido en 9
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#DEB887')),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 4)  # Reducido de 6 a 4
                ]))
                story.append(sistemas_table)

                # Si se exportan todas las estaciones, añadir secciones por estación (también en este bloque)
                if selected_export_station == 'Todas':
                    estaciones_lista = sorted([e for e in datos['df_evento']['Estación'].dropna().unique().tolist() if str(e).strip()])

                    for est in estaciones_lista:
                        story.append(PageBreak())
                        header_current_station['label'] = est

                        story.append(Paragraph(f"Estación: {est}", section_style))
                        story.append(Spacer(1, 8))

                        df_est = datos['df_evento'][datos['df_evento']['Estación'] == est]

                        est_estaciones_unicas = df_est['Indicativo'].nunique()
                        est_zona_mas = (df_est['Zona'].mode().iloc[0] if not df_est['Zona'].mode().empty else "N/A")
                        est_sistema_mas = (df_est['Sistema'].mode().iloc[0] if not df_est['Sistema'].mode().empty else "N/A")
                        est_cobertura = df_est['Estado'].nunique() if 'Estado' in df_est.columns else 0

                        stats_est = [
                            ['Métrica', 'Valor', 'Detalles'],
                            ['Total de Reportes', str(len(df_est)), f"Participantes activos: {len(df_est)}"],
                            ['Estaciones Únicas', str(est_estaciones_unicas), f"Diferentes estaciones que reportaron"],
                            ['Zona Más Reportada', est_zona_mas, f"Concentración geográfica principal"],
                            ['Sistema Más Usado', est_sistema_mas, f"Tecnología de radio predominante"],
                            ['Cobertura Geográfica', f"{est_cobertura} estados", f"Alcance territorial del evento"]
                        ]

                        table_est = Table(stats_est)
                        table_est.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 10),
                            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                            ('TOPPADDING', (0, 0), (-1, 0), 4),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#333333')),
                            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                            ('FONTSIZE', (0, 1), (-1, -1), 8),
                            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
                            ('BOTTOMPADDING', (0, 1), (-1, -1), 3)
                        ]))
                        story.append(table_est)
                        story.append(Spacer(1, 10))

                        # Distribución por zona (estación)
                        zonas_est = df_est['Zona'].value_counts()
                        df_zonas_est = pd.DataFrame({
                            'Zona': zonas_est.index,
                            'Cantidad': zonas_est.values,
                            'Porcentaje': (zonas_est.values / max(len(df_est), 1) * 100).round(1)
                        })
                        story.append(Paragraph("Distribución por zona geográfica", section_style))
                        story.append(Spacer(1, 6))
                        zonas_data_est = [['Zona', 'Cantidad', 'Porcentaje', 'Participación']]
                        for _, row in df_zonas_est.iterrows():
                            zonas_data_est.append([str(row['Zona']), str(int(row['Cantidad'])), f"{row['Porcentaje']:.1f}%", "●" * min(int(row['Cantidad']), 10)])
                        zonas_table_est = Table(zonas_data_est)
                        zonas_table_est.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5f2d')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 10),
                            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                            ('TOPPADDING', (0, 0), (-1, 0), 4),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0f8f0')),
                            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#2c5f2d')),
                            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                            ('FONTSIZE', (0, 1), (-1, -1), 8),
                            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#90EE90')),
                            ('BOTTOMPADDING', (0, 1), (-1, -1), 3)
                        ]))
                        story.append(zonas_table_est)
                        story.append(Spacer(1, 10))

                        # Principales estados (estación)
                        story.append(Paragraph("Principales estados participantes", section_style))
                        story.append(Spacer(1, 6))
                        estados_est = df_est['Estado'].value_counts()
                        top_est = estados_est.head(3)
                        estados_data_est = [['Estado', 'Reportes', 'Porcentaje', 'Participación']]
                        for estado, cantidad in top_est.items():
                            if estado and str(estado).strip():
                                pct = (cantidad / max(len(df_est), 1) * 100)
                                estados_data_est.append([str(estado), str(int(cantidad)), f"{pct:.1f}%", "●" * min(int(cantidad), 12)])
                        if len(estados_data_est) > 1:
                            estados_table_est = Table(estados_data_est)
                            estados_table_est.setStyle(TableStyle([
                                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DC143C')),
                                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                ('FONTSIZE', (0, 0), (-1, 0), 10),
                                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                                ('TOPPADDING', (0, 0), (-1, 0), 4),
                                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FFF0F0')),
                                ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#DC143C')),
                                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                                ('FONTSIZE', (0, 1), (-1, -1), 8),
                                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#FFB6C1')),
                                ('BOTTOMPADDING', (0, 1), (-1, -1), 3)
                            ]))
                            story.append(estados_table_est)
                            story.append(Spacer(1, 10))

                        # Distribución por sistema (estación)
                        story.append(Paragraph("Distribución por sistema de radio", section_style))
                        story.append(Spacer(1, 6))
                        sistemas_est = df_est['Sistema'].value_counts()
                        df_sist_est = pd.DataFrame({
                            'Sistema': sistemas_est.index,
                            'Cantidad': sistemas_est.values,
                            'Porcentaje': (sistemas_est.values / max(len(df_est), 1) * 100).round(1)
                        })
                        sist_data_est = [['Sistema', 'Cantidad', 'Porcentaje', 'Uso']]
                        for _, row in df_sist_est.iterrows():
                            sist_data_est.append([str(row['Sistema']), str(int(row['Cantidad'])), f"{row['Porcentaje']:.1f}%", "●" * min(int(row['Cantidad']), 8)])
                        sist_table_est = Table(sist_data_est)
                        sist_table_est.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8B4513')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 9),
                            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                            ('TOPPADDING', (0, 0), (-1, 0), 4),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FFF8DC')),
                            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#8B4513')),
                            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                            ('FONTSIZE', (0, 1), (-1, -1), 8),
                            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#DEB887')),
                            ('BOTTOMPADDING', (0, 1), (-1, -1), 3)
                        ]))
                        story.append(sist_table_est)

                # Pie de página más elegante
                story.append(Spacer(1, 30))
                
                # Crear una tabla de una celda para la línea divisoria que ocupe todo el ancho
                from reportlab.platypus import Table
                
                # Calcular el ancho disponible (ancho de página - márgenes)
                page_width = A4[0]  # Ancho de la hoja A4 en puntos (595.2755905511812)
                available_width = page_width - doc.leftMargin - doc.rightMargin
                
                # Crear una tabla de una celda con borde inferior
                line_table = Table([[None]], colWidths=[available_width])
                line_table.setStyle(TableStyle([
                    ('LINEBELOW', (0, 0), (0, 0), 0.5, colors.HexColor('#CCCCCC')),
                    ('BOTTOMPADDING', (0, 0), (0, 0), 10)
                ]))
                
                story.append(line_table)
                story.append(Spacer(1, 5))
                
                # Texto del pie de página centrado
                footer_style = ParagraphStyle(
                    'FooterStyle',
                    parent=info_style,
                    alignment=TA_CENTER,
                    spaceAfter=0,
                    spaceBefore=0
                )
                
                story.append(Paragraph("Federación Mexicana de Radioexperimentadores, A.C.", footer_style))
                story.append(Paragraph("Reporte generado automáticamente por el Sistema QMS", footer_style))
                story.append(Paragraph(f"© {datetime.now().year} FMRE - Todos los derechos reservados", footer_style))

                # Agregar página de reporte de actividad en horizontal
                # Restablecer etiqueta del encabezado a General o a la estación seleccionada
                if selected_export_station == 'Todas':
                    header_current_station['label'] = 'General'
                else:
                    header_current_station['label'] = selected_export_station

                story.append(PageBreak())
                story.append(NextPageTemplate('Landscape'))
                
                # Título de la segunda página
                story.append(Paragraph("Reporte de Actividad", section_style))
                story.append(Spacer(1, 12))
                
                # Aquí puedes agregar el contenido de la segunda página (filtrado por estación)
                if selected_export_station != 'Todas':
                    reportes_export = [r for r in datos['reportes'] if (r.get('qrz_station') or '').strip() == selected_export_station]
                else:
                    reportes_export = datos['reportes']

                if len(reportes_export) > 0:
                    # Crear tabla con los reportes (incluye Estación y Nombre; quita Frecuencia y Modo)
                    reportes_data = [['Estación', 'Indicativo', 'Nombre', 'Estado', 'Ciudad', 'Zona', 'Sistema']]
                    for reporte in reportes_export:
                        reportes_data.append([
                            (reporte.get('qrz_station') or ''),
                            reporte.get('indicativo', ''),
                            reporte.get('nombre', ''),
                            reporte.get('estado', ''),
                            reporte.get('ciudad', ''),
                            reporte.get('zona', ''),
                            reporte.get('sistema', '')
                        ])
                    
                    # Crear tabla con anchos que caben en Letter con márgenes (6.5")
                    reportes_table = Table(
                        reportes_data,
                        colWidths=[1.0*inch, 1.0*inch, 1.6*inch, 0.9*inch, 1.0*inch, 0.5*inch, 0.5*inch]
                    )
                    reportes_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 8),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#333333')),
                        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 1), (-1, -1), 7),
                        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
                        ('BOTTOMPADDING', (0, 1), (-1, -1), 3)
                    ]))
                    story.append(reportes_table)
                
                # Pie de página para la segunda página
                story.append(Spacer(1, 10))
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#CCCCCC')))
                story.append(Spacer(1, 5))
                story.append(Paragraph("Federación Mexicana de Radioexperimentadores, A.C. - Reporte de Actividad", footer_style))

                # Generar el PDF
                try:
                    doc.build(story, onFirstPage=create_header, onLaterPages=create_header)
                except Exception as e:
                    st.error(f"Error al generar el PDF: {str(e)}")
                    return None

                # Posicionar el buffer al inicio
                buffer.seek(0)

                # Botón de descarga
                est_suffix = "" if selected_export_station == 'Todas' else f"_{selected_export_station.replace(' ', '_')}"
                pdf_bytes = buffer.getvalue()
                st.session_state['trad_pdf'] = {
                    'bytes': pdf_bytes,
                    'file_name': f"reporte_{datos['evento']}_{datos['fecha']}{est_suffix}.pdf",
                    'mime': "application/pdf"
                }

            if st.session_state.get('trad_pdf'):
                pv = st.session_state['trad_pdf']
                st.download_button(
                    label="⬇️ Descargar PDF",
                    data=pv['bytes'],
                    file_name=pv['file_name'],
                    mime=pv['mime'],
                    key="trad_pdf_download_persist",
                    width='stretch'
                )
                open_pdf_modal = st.button("📧 Enviar por Correo", key="open_trad_pdf_dialog", use_container_width=True)
                if open_pdf_modal:
                    if hasattr(st, "dialog"):
                        @st.dialog("Enviar reporte (PDF)")
                        def _trad_pdf_dialog():
                            st.markdown(
                                """
                                <style>
                                div[role='dialog'] { width: min(95vw, 1200px) !important; }
                                div[role='dialog'] > div { width: 100% !important; }
                                @media (max-width: 900px) {
                                  div[role='dialog'] [data-testid='column'] { flex: 0 0 100% !important; width: 100% !important; min-width: 100% !important; }
                                }
                                </style>
                                """,
                                unsafe_allow_html=True
                            )
                            pv_loc = st.session_state.get('trad_pdf')
                            # Dataset para construir el cuerpo del correo (PDF)
                            try:
                                df_loc = df_export
                            except Exception:
                                df_loc = datos['df_evento']
                            if df_loc is None:
                                df_loc = datos['df_evento']
                            total = int(len(df_loc)) if isinstance(df_loc, pd.DataFrame) else 0
                            ests = int(df_loc['Indicativo'].nunique()) if isinstance(df_loc, pd.DataFrame) and 'Indicativo' in df_loc.columns else 0
                            zona_m = (df_loc['Zona'].mode().iloc[0] if isinstance(df_loc, pd.DataFrame) and 'Zona' in df_loc.columns and not df_loc['Zona'].mode().empty else "N/A")
                            sist_m = (df_loc['Sistema'].mode().iloc[0] if isinstance(df_loc, pd.DataFrame) and 'Sistema' in df_loc.columns and not df_loc['Sistema'].mode().empty else "N/A")
                            ests_geo = int(df_loc['Estado'].nunique()) if isinstance(df_loc, pd.DataFrame) and 'Estado' in df_loc.columns else 0
                            zonas_html = ""
                            if isinstance(df_loc, pd.DataFrame) and 'Zona' in df_loc.columns and total > 0:
                                vc_z = df_loc['Zona'].fillna('N/D').astype(str).value_counts()
                                zonas_html = "<p><strong>Distribución por Zona:</strong></p><ul>" + "".join([f"<li>{z}: {int(c)} ({(c/total)*100:.1f}%)</li>" for z, c in vc_z.items()]) + "</ul>"
                            sistemas_html = ""
                            if isinstance(df_loc, pd.DataFrame) and 'Sistema' in df_loc.columns and total > 0:
                                vc_s = df_loc['Sistema'].fillna('N/D').astype(str).value_counts()
                                sistemas_html = "<p><strong>Distribución por Sistema:</strong></p><ul>" + "".join([f"<li>{s}: {int(c)} ({(c/total)*100:.1f}%)</li>" for s, c in vc_s.items()]) + "</ul>"
                            estaciones_html = ""
                            if isinstance(df_loc, pd.DataFrame) and 'Estación' in df_loc.columns and total > 0:
                                vc_e = df_loc['Estación'].fillna('Sin estación').astype(str).value_counts()
                                estaciones_html = "<p><strong>Desglose por Estación (top 10):</strong></p><ul>" + "".join([f"<li>{e}: {int(c)} ({(c/total)*100:.1f}%)</li>" for e, c in vc_e.head(10).items()]) + "</ul>"
                            per_station_html = ""
                            if isinstance(df_loc, pd.DataFrame) and 'Estación' in df_loc.columns and total > 0:
                                top_e = vc_e.head(5) if 'vc_e' in locals() else df_loc['Estación'].fillna('Sin estación').astype(str).value_counts().head(5)
                                items = []
                                for est_name, _cnt in top_e.items():
                                    df_s = df_loc[df_loc['Estación'].fillna('Sin estación').astype(str) == est_name]
                                    sz = len(df_s)
                                    z_block = ""
                                    if 'Zona' in df_s.columns and sz > 0:
                                        vc_zs = df_s['Zona'].fillna('N/D').astype(str).value_counts()
                                        z_block = "<ul>" + "".join([f"<li>{z}: {int(c)} ({(c/sz)*100:.1f}%)</li>" for z, c in vc_zs.items()]) + "</ul>"
                                    s_block = ""
                                    if 'Sistema' in df_s.columns and sz > 0:
                                        vc_ss = df_s['Sistema'].fillna('N/D').astype(str).value_counts()
                                        s_block = "<ul>" + "".join([f"<li>{s}: {int(c)} ({(c/sz)*100:.1f}%)</li>" for s, c in vc_ss.items()]) + "</ul>"
                                    items.append(f"<li><strong>{est_name}</strong><ul><li>Distribución por Zona:{z_block}</li><li>Distribución por Sistema:{s_block}</li></ul></li>")
                                per_station_html = "<p><strong>Detalle por Estación (top 5):</strong></p><ul>" + "".join(items) + "</ul>"
                            try:
                                meses_es = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
                                fecha_larga = datos['fecha']
                                try:
                                    fdt = datetime.strptime(datos['fecha'], '%Y-%m-%d')
                                    fecha_larga = f"{fdt.day} de {meses_es[fdt.month-1]} de {fdt.year}"
                                except Exception:
                                    pass
                                vc_z_loc = df_loc['Zona'].fillna('N/D').astype(str).value_counts() if isinstance(df_loc, pd.DataFrame) and 'Zona' in df_loc.columns and total > 0 else pd.Series(dtype=int)
                                vc_s_loc = df_loc['Sistema'].fillna('N/D').astype(str).value_counts() if isinstance(df_loc, pd.DataFrame) and 'Sistema' in df_loc.columns and total > 0 else pd.Series(dtype=int)
                                vc_e_loc = df_loc['Estación'].fillna('Sin estación').astype(str).value_counts() if isinstance(df_loc, pd.DataFrame) and 'Estación' in df_loc.columns and total > 0 else pd.Series(dtype=int)
                                def fmt_pct(n, d):
                                    return f"{(n/d*100):.1f}%" if d else "0.0%"
                                zonas_presentes = [z for z in vc_z_loc.index if z in ['XE1','XE2','XE3']]
                                ext_count = int(vc_z_loc.get('EXT', 0)) if hasattr(vc_z_loc, 'get') else 0
                                zona_frase = ""
                                if len(vc_z_loc) > 0:
                                    z_pairs = list(vc_z_loc.items())
                                    topz = z_pairs[0]
                                    zona_frase = f"La zona {topz[0]} fue la más activa con {int(topz[1])} reportes ({fmt_pct(topz[1], total)})."
                                    if len(z_pairs) > 1:
                                        z2 = z_pairs[1]
                                        zona_frase = zona_frase[:-1] + f", seguida por {z2[0]} ({fmt_pct(z2[1], total)})."
                                    if len(z_pairs) > 2:
                                        z3 = z_pairs[2]
                                        zona_frase = zona_frase[:-1] + f" y {z3[0]} ({fmt_pct(z3[1], total)})."
                                    if ext_count > 0:
                                        zona_frase = zona_frase[:-1] + f" Además, {ext_count} estaciones extranjeras ({fmt_pct(ext_count, total)})."
                                sistemas_frase = ""
                                if len(vc_s_loc) > 0:
                                    s_pairs = list(vc_s_loc.items())
                                    stp = s_pairs[0]
                                    sistemas_frase = f"En sistemas, {stp[0]} lideró con {fmt_pct(stp[1], total)}"
                                    if len(s_pairs) > 1:
                                        s2 = s_pairs[1]
                                        sistemas_frase += f", seguido por {s2[0]} ({fmt_pct(s2[1], total)})."
                                    else:
                                        sistemas_frase += "."
                                dist_zona_html = "<ul>" + "".join([f"<li>{z}: {int(c)} ({fmt_pct(c, total)})</li>" for z, c in vc_z_loc.items()]) + "</ul>" if len(vc_z_loc) > 0 else ""
                                dist_sist_html = "<ul>" + "".join([f"<li>{s}: {int(c)} ({fmt_pct(c, total)})</li>" for s, c in vc_s_loc.items()]) + "</ul>" if len(vc_s_loc) > 0 else ""
                                top10 = list(vc_e_loc.items())[:10]
                                top10_html = "<ul>" + "".join([f"<li>{e}: {int(c)} ({fmt_pct(c, total)})</li>" for e, c in top10]) + "</ul>" if top10 else ""
                                # Desglose narrativo para estaciones específicas (XE1LM y XE2BC)
                                det_xe_html = ""
                                for _st_code in ['XE1LM','XE2BC']:
                                    _df_s = df_loc[df_loc['Estación'].fillna('Sin estación').astype(str) == _st_code]
                                    _sz = len(_df_s)
                                    if _sz > 0:
                                        _pct_tot = fmt_pct(_sz, total)
                                        _z_s = _df_s['Zona'].fillna('N/D').astype(str).value_counts() if 'Zona' in _df_s.columns else pd.Series(dtype=int)
                                        _s_s = _df_s['Sistema'].fillna('N/D').astype(str).value_counts() if 'Sistema' in _df_s.columns else pd.Series(dtype=int)
                                        _zona_frase_st = ""
                                        if len(_z_s) > 0:
                                            _z_pairs = list(_z_s.items())
                                            _topz = _z_pairs[0]
                                            _zona_frase_st = f"La zona {_topz[0]} fue la más activa con {int(_topz[1])} reportes ({fmt_pct(_topz[1], _sz)})"
                                            if len(_z_pairs) > 1:
                                                _zona_frase_st += f", seguida por {_z_pairs[1][0]} ({fmt_pct(_z_pairs[1][1], _sz)})"
                                            if len(_z_pairs) > 2:
                                                _zona_frase_st += f" y {_z_pairs[2][0]} ({fmt_pct(_z_pairs[2][1], _sz)})"
                                            _ext_st = int(_z_s.get('EXT', 0)) if hasattr(_z_s, 'get') else 0
                                            if _ext_st > 0:
                                                _zona_frase_st += f", además de {_ext_st} estaciones extranjeras ({fmt_pct(_ext_st, _sz)})."
                                            else:
                                                _zona_frase_st += "."
                                        _sistemas_frase_st = ""
                                        if len(_s_s) > 0:
                                            _s_pairs = list(_s_s.items())
                                            _stp = _s_pairs[0]
                                            _sistemas_frase_st = f"En cuanto a los sistemas, {_stp[0]} encabezó la actividad con el {fmt_pct(_stp[1], _sz)}"
                                            if len(_s_pairs) > 1:
                                                _sistemas_frase_st += f", seguido por {_s_pairs[1][0]} ({fmt_pct(_s_pairs[1][1], _sz)})"
                                            if len(_s_pairs) > 2:
                                                _sistemas_frase_st += f", {_s_pairs[2][0]} ({fmt_pct(_s_pairs[2][1], _sz)})"
                                            _otros_pct = 100.0 - sum([(v/_sz*100) for _, v in _s_pairs[:3]]) if _sz else 0.0
                                            if len(_s_pairs) > 3 and _otros_pct > 0:
                                                _sistemas_frase_st += f" y el {_otros_pct:.1f}% restante en otros sistemas."
                                            else:
                                                _sistemas_frase_st += "."
                                        det_xe_html += f"<p>La Estación <strong>{_st_code}</strong> informa que se reportaron <strong>{_sz}</strong> colegas, que representan el <strong>{_pct_tot}</strong> del total de reportes del boletín.</p><p>{_zona_frase_st}</p><p>{_sistemas_frase_st}</p>"
                                zonas_txt = ", ".join(zonas_presentes) + (" y EXT" if ext_count > 0 else "") if zonas_presentes or ext_count > 0 else "N/D"
                                sistema_mas_usado = (vc_s_loc.index[0] if len(vc_s_loc) > 0 else 'N/D')
                                general_stats_html = (
                                    "<ul>"
                                    f"<li>📡 Total de reportes: {total}</li>"
                                    f"<li>👥 Estaciones únicas: {ests}</li>"
                                    f"<li>🗺️ Zonas participantes: {zonas_txt}</li>"
                                    f"<li>🔗 Sistema más usado: {sistema_mas_usado}</li>"
                                    f"<li>🌎 Cobertura geográfica: {ests_geo} estados</li>"
                                    "</ul>"
                                )
                                body_html = (
                                    f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:8px;'><img src='cid:logo_fmre_small' alt='FMRE' style='height:40px'/><div style='font-family:Arial, sans-serif; font-size:16px; font-weight:700; color:#1f4e79;'>Federación Mexicana de Radioexperimentadores A.C.</div></div><hr/>"
                                    f"<p>Nos da gusto compartirles el resumen de estadísticas correspondiente a <strong>{datos['evento']}</strong> del <strong>{fecha_larga}</strong>, generado automáticamente por el Sistema de Gestión de QSO (QMS).</p>"
                                    f"<p>En esta ocasión se registraron <strong>{total}</strong> reportes, con la participación de <strong>{ests}</strong> estaciones únicas provenientes de <strong>{ests_geo}</strong> estados.</p>"
                                    f"<p>{zona_frase}</p>"
                                    f"<p>{sistemas_frase}</p>"
                                    f"<h4>Estadísticas Generales</h4>"
                                    f"{general_stats_html}"
                                    f"<h4>Distribución por Zona</h4>"
                                    f"{dist_zona_html}"
                                    f"<h4>Distribución por Sistema</h4>"
                                    f"{dist_sist_html}"
                                    f"<h4>Estaciones Control participacipantes</h4>"
                                    f"{top10_html}"
                                    f"<h4>Desglose por Estaciones Control</h4>"
                                    f"{det_xe_html}"
                                    f"<p>El archivo adjunto incluye el detalle completo de registros y las distribuciones por zona, sistema y estación.</p>"
                                    f"<p>¡Nos escuchamos en el próximo boletín!<br/>73 de parte del equipo de la FMRE</p>"
                                    f"<hr/><p><strong>Enviado por:</strong> {indicativo_usuario} - {nombre_usuario}</p>"
                                )
                            except Exception:
                                body_html = (
                                    f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:8px;'><img src='cid:logo_fmre_small' alt='FMRE' style='height:40px'/><div style='font-family:Arial, sans-serif; font-size:16px; font-weight:700; color:#1f4e79;'>Federación Mexicana de Radioexperimentadores A.C.</div></div><hr/>"
                                    f"<p>Se adjunta el reporte <strong>{datos['evento']}</strong> correspondiente al <strong>{datos['fecha']}</strong>.</p>"
                                )
                            default_body = body_html
                            col_l, col_r = st.columns([2, 1])
                            with col_r:
                                users_list = db.get_all_users() or []
                                user_emails = sorted({u.get('email') for u in users_list if (u.get('email') and (u.get('is_active', 1) == 1))})
                                selected_users = st.multiselect("Destinatarios (usuarios)", options=user_emails, key="dlg_trad_pdf_users")
                                to_d = st.text_input("Correos (separados por coma)", key="dlg_trad_pdf_to")
                                body_d = st.text_area("Cuerpo del correo (HTML permitido)", value=default_body, key="dlg_trad_pdf_body", height=240)
                                send_d = st.button("📨 Enviar", type="primary", use_container_width=True, key="dlg_trad_pdf_send")
                            with col_l:
                                st.subheader("Vista previa")
                                st.markdown(st.session_state.get('dlg_trad_pdf_body') or default_body, unsafe_allow_html=True)
                            if send_d:
                                typed = [p.strip() for p in (to_d or "").replace(";", ",").split(",") if p.strip()]
                                from_users = [e for e in (selected_users or []) if e]
                                emails = sorted(set(typed + from_users))
                                if not emails:
                                    st.error("Ingrese al menos un destinatario")
                                elif not pv_loc:
                                    st.error("Genere el adjunto antes de enviar")
                                else:
                                    mailer = EmailSender(db)
                                    ok = mailer.send_email_with_attachments(
                                        to_emails=emails,
                                        subject=f"Reporte Tradicional {datos['evento']} - {datos['fecha']}",
                                        body=(st.session_state.get('dlg_trad_pdf_body') or default_body),
                                        attachments=[(pv_loc['file_name'], pv_loc['bytes'], pv_loc['mime'])],
                                        is_html=True
                                    )
                                    if ok:
                                        st.success("✅ Correo enviado")
                                        st.balloons()
                                    else:
                                        st.error("No se pudo enviar el correo")
                        _trad_pdf_dialog()
                    if not hasattr(st, "dialog"):
                        st.info("Tu versión de Streamlit no soporta ventanas modales (st.dialog). Actualiza Streamlit para usar 'Enviar por Correo'.")

        # Información adicional
        st.subheader("ℹ️ Información del Reporte")
        col1, col2 = st.columns(2)

        with col1:
            st.write("**Evento:**", datos['evento'])
            st.write("**Fecha del Evento:**", datos['fecha'])
            st.write("**Fecha de Generación:**", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        with col2:
            st.write("**Generado por:**", f"{indicativo_usuario} - {nombre_usuario}")
            st.write("**Total de Participantes:**", len(datos['reportes']))
            st.write("**Cobertura Geográfica:**", f"{datos['df_evento']['Estado'].nunique()} estados")

        # Botón para generar nuevo reporte
        if st.button("🔄 Generar Nuevo Reporte"):
            # Limpiar el estado
            if 'reporte_generado' in st.session_state:
                del st.session_state['reporte_generado']
            if 'datos_evento' in st.session_state:
                del st.session_state['datos_evento']
            st.rerun()

    else:
        st.info(f"No hay reportes para el evento '{evento_seleccionado}' en la fecha {fecha_evento.strftime('%Y-%m-%d')}")

def show_settings():
    """Muestra la configuración del sistema"""
    st.title("⚙️ Configuración del Sistema")
    
    # Pestañas para las diferentes configuraciones
    tab1, tab2, tab3, tab4 = st.tabs([
        "Correo Electrónico", 
        "Opciones del Sistema", 
        "Consulta SQL",
        "Redes Sociales"
    ])
    
    with tab1:
        st.header("Configuración SMTP")
        st.markdown("Configura los parámetros del servidor de correo para el envío de notificaciones.")
        
        # Obtener configuración actual
        current_config = db.get_smtp_settings()
        
        with st.form("smtp_settings_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                server = st.text_input("Servidor SMTP*", 
                                     value=current_config.get('server', 'smtp.gmail.com') if current_config else 'smtp.gmail.com')
                port = st.number_input("Puerto*", 
                                     min_value=1, 
                                     max_value=65535, 
                                     value=current_config.get('port', 587) if current_config else 587)
                from_email = st.text_input("Correo remitente*", 
                                         value=current_config.get('from_email', '') if current_config else '')
            
            with col2:
                username = st.text_input("Usuario*", 
                                       value=current_config.get('username', '') if current_config else '')
                password = st.text_input("Contraseña*", 
                                       type="password",
                                       value="")
                use_tls = st.checkbox("Usar TLS/SSL", 
                                    value=bool(current_config.get('use_tls', True)) if current_config else True)
            
            # Botón para probar la configuración
            test_col1, test_col2, _ = st.columns([1, 1, 3])
            
            if test_col1.form_submit_button("Probar configuración"):
                try:
                    # Actualizar temporalmente la configuración para la prueba
                    test_config = {
                        'server': server,
                        'port': port,
                        'username': username,
                        'password': password if password else current_config.get('password', ''),
                        'use_tls': use_tls,
                        'from_email': from_email
                    }
                    
                    # Probar conexión
                    with st.spinner("Probando conexión con el servidor SMTP..."):
                        email_sender = EmailSender(db)
                        server_conn, _ = email_sender.get_smtp_connection()
                        server_conn.quit()
                        st.success("Conexión exitosa con el servidor SMTP")
                        
                except Exception as e:
                    st.error(f"Error al conectar con el servidor SMTP: {str(e)}")
            
            # Botón para guardar la configuración
            if test_col2.form_submit_button("Guardar configuración"):
                try:
                    # Usar la contraseña existente si no se proporcionó una nueva
                    password_to_save = password if password else current_config.get('password', '')
                    
                    db.update_smtp_settings(
                        server=server,
                        port=port,
                        username=username,
                        password=password_to_save,
                        use_tls=use_tls,
                        from_email=from_email
                    )
                    st.success("✅ Configuración guardada correctamente")
                    time.sleep(2)  # Pequeña pausa para mostrar el mensaje
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Error al guardar la configuración: {str(e)}")
    
    with tab2:
        st.header("Opciones del Sistema")
        st.write("Configuración general del sistema.")

        # URL del sistema (base)
        current_setting = db.get_system_setting('system_url')
        current_url = (current_setting.get('value') if current_setting else '') or ''

        # Mostrar metadatos si existen
        if current_setting:
            meta_cols = st.columns([2, 2])
            meta_cols[0].info(f"Última actualización: {current_setting.get('updated_at', '')}")
            meta_cols[1].info(f"Por: {current_setting.get('updated_by_username', 'N/D')}")

        with st.form("system_options_form"):
            st.subheader("URL del Sistema")
            system_url = st.text_input(
                "URL base (incluye http/https)",
                value=current_url,
                help="Ejemplos: https://tudominio.com/qms o http://localhost:8501"
            )

            # Campo opcional para comentarios/descripcion
            description = st.text_area(
                "Descripción (opcional)",
                value=current_setting.get('description', '') if current_setting else '',
                help="Notas sobre el uso de esta URL."
            )

            save_settings = st.form_submit_button("Guardar opciones")

            if save_settings:
                try:
                    # Validar URL simple (http/https)
                    import re as _re
                    pattern = r'^https?://[^\s]+$'
                    if system_url and not _re.match(pattern, system_url.strip()):
                        st.error("La URL debe iniciar con http:// o https:// y no contener espacios.")
                    else:
                        updated_by = st.session_state.user["id"] if "user" in st.session_state and st.session_state.user else None
                        db.set_system_setting(
                            key='system_url',
                            value=system_url.strip() if system_url else '',
                            updated_by=updated_by,
                            description=description.strip() if description else None
                        )
                        st.success("✅ Opciones del sistema guardadas correctamente")
                        time.sleep(1.5)
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al guardar las opciones: {e}")

        st.markdown("---")
        st.subheader("Plantilla de correo de bienvenida")
        st.caption("Usa placeholders: {{full_name}}, {{username}}, {{password}}, {{system_url}}")

        # Cargar configuraciones actuales
        subj_setting = db.get_system_setting('welcome_email_subject')
        body_setting = db.get_system_setting('welcome_email_body_html')

        default_subject = "Bienvenido al Sistema de Gestión de QSOs"
        default_body = (
            "<html><body>"
            "<h2>Bienvenido al Sistema de Gestión de QSOs de la FMRE A.C.</h2>"
            "<p>Hola {{full_name}},</p>"
            "<p>Se ha creado una cuenta para ti en el Sistema de Gestión de QSOs.</p>"
            "<p><strong>Tus credenciales de acceso son:</strong></p>"
            "<ul>"
            "<li><strong>Usuario:</strong> {{username}}</li>"
            "<li><strong>Contraseña temporal:</strong> {{password}}</li>"
            "</ul>"
            "<p>Te recomendamos cambiar tu contraseña después de iniciar sesión por primera vez.</p>"
            "<p>Puedes acceder al sistema en: {{system_url}}</p>"
            "<p>Saludos,<br>El equipo de FMRE</p>"
            "</body></html>"
        )

        with st.form("welcome_email_template_form"):
            email_subject = st.text_input(
                "Asunto",
                value=(subj_setting.get('value') if subj_setting else default_subject)
            )
            email_body = st.text_area(
                "Cuerpo (HTML)",
                value=(body_setting.get('value') if body_setting else default_body),
                height=300
            )
            save_tpl = st.form_submit_button("Guardar plantilla")

            if save_tpl:
                try:
                    updated_by = st.session_state.user["id"] if "user" in st.session_state and st.session_state.user else None
                    db.set_system_setting('welcome_email_subject', email_subject or default_subject, updated_by=updated_by)
                    db.set_system_setting('welcome_email_body_html', email_body or default_body, updated_by=updated_by)
                    st.success("✅ Plantilla guardada correctamente")
                    time.sleep(1.2)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al guardar la plantilla: {e}")
    
    with tab3:
        st.header("Consulta SQL Directa")
        st.warning("⚠️ ADVERTENCIA: Esta herramienta permite ejecutar consultas SQL directamente en la base de datos. "
                  "Úsala con precaución, ya que las consultas pueden modificar o eliminar datos.")
        
        # Área para escribir la consulta SQL
        query = st.text_area("Escribe tu consulta SQL aquí", height=150,
                           placeholder="Ejemplo: SELECT * FROM radioexperimentadores LIMIT 10;")
        
        # Opciones de ejecución
        col1, col2 = st.columns(2)
        
        # Botón para ejecutar consulta
        if col1.button("Ejecutar Consulta"):
            if not query.strip():
                st.warning("Por favor, ingresa una consulta SQL válida.")
            else:
                try:
                    # Ejecutar la consulta
                    with db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(query)
                        
                        # Obtener los resultados
                        results = cursor.fetchall()
                        
                        # Mostrar resultados si es una consulta SELECT
                        if query.strip().upper().startswith('SELECT'):
                            if results:
                                # Obtener nombres de columnas
                                column_names = [description[0] for description in cursor.description]
                                
                                # Mostrar resultados en una tabla
                                st.dataframe(results, width='stretch', 
                                           column_config={col: st.column_config.TextColumn(col) for col in column_names})
                                
                                # Mostrar conteo de resultados
                                st.success(f"Consulta ejecutada correctamente. Se encontraron {len(results)} registros.")
                            else:
                                st.info("La consulta no devolvió resultados.")
                        else:
                            # Para consultas que no son SELECT (INSERT, UPDATE, DELETE, etc.)
                            conn.commit()
                            st.success(f"Operación completada exitosamente. Filas afectadas: {cursor.rowcount}")
                            
                except Exception as e:
                    st.error(f"Error al ejecutar la consulta: {str(e)}")
        
        # Botón para obtener información de las tablas
        if col2.button("Mostrar Tablas"):
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    # Obtener lista de tablas
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = cursor.fetchall()
                    
                    if tables:
                        st.subheader("Tablas en la base de datos:")
                        for table in tables:
                            table_name = table[0]
                            with st.expander(f"📋 {table_name}"):
                                try:
                                    # Obtener estructura de la tabla
                                    cursor.execute(f"PRAGMA table_info({table_name})")
                                    columns = cursor.fetchall()
                                    
                                    # Mostrar columnas
                                    st.write("**Columnas:**")
                                    for col in columns:
                                        st.write(f"- {col[1]} ({col[2]})")
                                    
                                    # Mostrar conteo de registros
                                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                                    count = cursor.fetchone()[0]
                                    st.write(f"**Total de registros:** {count:,}")
                                    
                                except Exception as e:
                                    st.error(f"Error al obtener información de la tabla {table_name}: {str(e)}")
                    else:
                        st.info("No se encontraron tablas en la base de datos.")
                        
            except Exception as e:
                st.error(f"Error al obtener información de la base de datos: {str(e)}")

def show_toma_reportes():
    """Muestra la sección de Toma de Reportes con pestañas para Tradicional y Redes Sociales."""
    st.title("📝 Toma de Reportes")
    
    # Crear pestañas
    tab1, tab2 = st.tabs(["📻 Tradicional", "📱 Redes Sociales"])
    
    with tab1:
        _show_toma_reportes_tradicional()
    
    with tab2:
        from rs_report_form import show_redes_sociales_form
        show_redes_sociales_form()

def _show_toma_reportes_tradicional():
    """Muestra el formulario tradicional de toma de reportes."""
    import pandas as pd
    from datetime import datetime
    from time import sleep
    from time_utils import get_current_cdmx_time

    # ==========================
    # Helpers internos
    # ==========================
    def _safe_str(x):
        return "" if x is None else str(x)

    def _pre_form_key(name: str) -> str:
        """Genera keys únicas para widgets del Pre-Registro usando un nonce."""
        nonce = st.session_state.get("pre_form_nonce", 0)
        return f"{name}_{nonce}"

    def _clear_current_pre_form_inputs():
        """Elimina del session_state los widgets de pre-registro del nonce actual."""
        nonce = st.session_state.get("pre_form_nonce", 0)
        n = st.session_state.get("parametros_reporte", {}).get("pre_registro", 0)
        for i in range(n):
            k_ind = f"indicativo_{i}_{nonce}"
            k_sis = f"sistema_{i}_{nonce}"
            if k_ind in st.session_state:
                del st.session_state[k_ind]
            if k_sis in st.session_state:
                del st.session_state[k_sis]

    def _bump_pre_form_nonce_and_clear():
        """Aumenta el nonce para que los inputs del Pre-Registro salgan vacíos."""
        st.session_state["pre_form_nonce"] = st.session_state.get("pre_form_nonce", 0) + 1

    def _estimar_zona(indicativo: str, zona_bd: str = "", result_validacion=None) -> str:
        """Regresa zona estimada."""
        if indicativo == "SWR":
            return ""  # SWR no lleva zona
        if zona_bd:
            return zona_bd
        try:
            if result_validacion is None:
                result_validacion = utils.validar_call_sign(indicativo)
        except Exception:
            result_validacion = None

        if result_validacion and result_validacion.get("Zona") == "Extranjera":
            return "EXT"

        # Regla por prefijo XE1/XE2/XE3
        if indicativo.startswith("XE") and len(indicativo) >= 3 and indicativo[2] in ("1", "2", "3"):
            return f"XE{indicativo[2]}"

        # Fallback extranjero
        return "EXT"

    def _get_fecha_consulta_from_parametros() -> str:
        """Convierte dd/mm/yyyy a yyyy-mm-dd para la consulta SQL."""
        fecha_txt = st.session_state["parametros_reporte"].get("fecha_reporte")
        fecha_dt = datetime.strptime(fecha_txt, "%d/%m/%Y")
        return fecha_dt.strftime("%Y-%m-%d")

    # ==========================
    # UI: Encabezado
    # ==========================
    st.title("📝 Toma de Reportes")
    st.markdown("### Registro de Reportes")
    st.markdown("""
    <div style="background-color: #f0f8ff; padding: 15px; border-radius: 10px; border-left: 4px solid #1f77b4; margin-bottom: 20px;">
        <h4 style="color: #1f77b4; margin-top: 0;">📋 Configuración de Parámetros</h4>
        <p>Selecciona los parámetros iniciales para la generación de reportes.
        Estos valores se utilizarán como <strong>configuración predeterminada</strong> en todos tus registros.</p>
    </div>
    """, unsafe_allow_html=True)

    # ==========================
    # Session state base
    # ==========================
    if "expander_abierto" not in st.session_state:
        st.session_state.expander_abierto = True  # primera vez abierto
    if "parametros_reporte" not in st.session_state:
        st.session_state.parametros_reporte = {}
    if "registros" not in st.session_state:
        st.session_state.registros = []
    if "registros_editados" not in st.session_state:
        st.session_state.registros_editados = False
    if "pre_form_nonce" not in st.session_state:
        st.session_state.pre_form_nonce = 0  # para vaciar los campos de pre-registro cuando se requiera

    # Si justo se guardaron parámetros en esta corrida, mantener expander cerrado
    if st.session_state.get("just_saved_params", False):
        st.session_state.expander_abierto = False
        st.session_state["just_saved_params"] = False

    # ==========================
    # Resumen de parámetros arriba
    # ==========================
    if st.session_state.parametros_reporte:
        pr = st.session_state.parametros_reporte
        hf_info = ""
        if pr.get("sistema_preferido") == "HF":
            hf_info = f" | 📻 HF: {pr.get('frecuencia','')} {pr.get('modo','')} {pr.get('potencia','')}"
        st.info(
            f"📅 **Fecha de Reporte:** {pr.get('fecha_reporte','')} | "
            f"📋 **Tipo de Reporte:** {pr.get('tipo_reporte','')} | "
            f"🖥️ **Sistema Preferido:** {pr.get('sistema_preferido','')} | "
            f"📝 **Pre-Registros:** {pr.get('pre_registro','')}{hf_info} | "
            f"📍 **SWL Estado:** {pr.get('swl_estado','')} | "
            f"🏙️ **SWL Ciudad:** {pr.get('swl_ciudad','')}"
        )

    # ==========================
    # Formulario Parámetros
    # ==========================
    with st.expander("📋 Parámetros de Captura", expanded=st.session_state.expander_abierto):
        with st.form("form_parametros_reporte"):
            # Fecha
            fecha_actual = get_current_cdmx_time().date()
            fecha = st.date_input("Fecha de Reporte", fecha_actual)
            if fecha != fecha_actual:
                st.warning("⚠️ Reporte con fecha distinta a la actual.")
                
            # Operando Estación
            # Obtener la estación QRZ del usuario actual
            qrz_estacion = ""
            if 'user' in st.session_state and st.session_state.user and 'id' in st.session_state.user:
                usuario = db.get_user_by_id(st.session_state.user['id'])
                if usuario and 'qrz_station' in usuario:
                    qrz_estacion = usuario['qrz_station']
            
            # Mostrar el campo de estación con el valor actual del usuario
            try:
                cursor = db.get_connection().cursor()
                cursor.execute("SELECT qrz FROM stations ORDER BY qrz")
                estaciones = [""] + [row[0] for row in cursor.fetchall()]
                
                # Si el usuario ya tiene una estación asignada, mostrarla como valor por defecto
                indice_estacion = estaciones.index(qrz_estacion) if qrz_estacion in estaciones else 0
                qrz_estacion = st.selectbox(
                    "Operando Estación", 
                    estaciones, 
                    index=indice_estacion,
                    help="Selecciona la estación desde la que estás operando"
                )
            except Exception as e:
                st.error(f"Error al cargar las estaciones: {str(e)}")
                qrz_estacion = qrz_estacion or ""  # Mantener el valor actual si hay un error

            # Tipo reporte
            try:
                eventos = db.get_all_eventos()
                opciones_eventos = [e["tipo"] for e in eventos] or ["Boletín"]
            except Exception:
                opciones_eventos = ["Boletín"]
            tipo_reporte = st.selectbox("Tipo de Reporte", opciones_eventos)

            # Sistemas
            try:
                sistemas_dict = db.get_sistemas()
                opciones_sistemas = sorted(list(sistemas_dict.keys())) or ["ASL"]
            except Exception:
                opciones_sistemas = ["ASL"]

            # Sugerir por usuario
            sistema_default = None
            if "user" in st.session_state and st.session_state.user and "sistema_preferido" in st.session_state.user:
                sistema_default = st.session_state.user["sistema_preferido"]
            if sistema_default not in opciones_sistemas:
                sistema_default = opciones_sistemas[0] if opciones_sistemas else "ASL"

            sistema_preferido = st.selectbox(
                "Sistema Preferido *",
                opciones_sistemas,
                index=(opciones_sistemas.index(sistema_default) if sistema_default in opciones_sistemas else 0),
            )

            # Estados SWL
            try:
                estados = db.get_estados()
                opciones_estados = [""] + [str(e["estado"]) for e in estados if e]
            except Exception:
                opciones_estados = [""]

            # Cargar valores guardados del usuario para SWL
            swl_estado_guardado = ""
            swl_ciudad_guardada = ""
            try:
                if "user" in st.session_state and st.session_state.user and "id" in st.session_state.user:
                    u = db.get_user_by_id(st.session_state.user["id"])
                    if u:
                        if u.get("swl_estado"):
                            swl_estado_guardado = str(u["swl_estado"])
                        if u.get("swl_ciudad"):
                            swl_ciudad_guardada = str(u["swl_ciudad"])
            except Exception:
                pass

            col_swl1, col_swl2 = st.columns(2)
            with col_swl1:
                # Encontrar el índice del estado guardado
                estado_index = 0
                if swl_estado_guardado and swl_estado_guardado in opciones_estados:
                    estado_index = opciones_estados.index(swl_estado_guardado)
                swl_estado = st.selectbox("SWL Estado", options=opciones_estados, index=estado_index)
            with col_swl2:
                swl_ciudad = st.text_input("SWL Ciudad", value=swl_ciudad_guardada)

            # Pre-registros
            # Si el usuario ya tiene uno guardado, proponlo
            pre_registro_guardado = 3
            try:
                if "user" in st.session_state and st.session_state.user and "id" in st.session_state.user:
                    u = db.get_user_by_id(st.session_state.user["id"])
                    if u and u.get("pre_registro") is not None:
                        pre_registro_guardado = int(u.get("pre_registro") or 3)
            except Exception:
                pass

            pre_registro = st.slider("Pre-Registros", min_value=1, max_value=10, value=pre_registro_guardado)

            # HF si aplica
            # Cargar valores guardados del usuario para HF
            frecuencia = modo = potencia = ""
            try:
                if "user" in st.session_state and st.session_state.user and "id" in st.session_state.user:
                    u = db.get_user_by_id(st.session_state.user["id"])
                    if u:
                        if u.get("frecuencia"):
                            frecuencia = str(u["frecuencia"])
                        if u.get("modo"):
                            modo = str(u["modo"])
                        if u.get("potencia"):
                            potencia = str(u["potencia"])
            except Exception:
                pass

            if sistema_preferido == "HF":
                st.markdown("**📻 Configuración HF**")
                c1, c2, c3 = st.columns(3)
                with c1:
                    frecuencia = st.text_input("Frecuencia (MHz)", value=frecuencia)
                with c2:
                    modo = st.selectbox("Modo", ["SSB", "CW", "FT8", "RTTY", "PSK31", "Otro"],
                                      index=["SSB", "CW", "FT8", "RTTY", "PSK31", "Otro"].index(modo) if modo in ["SSB", "CW", "FT8", "RTTY", "PSK31", "Otro"] else 0)
                with c3:
                    potencia = st.selectbox("Potencia", ["QRP (≤5W)", "Baja (≤50W)", "Media (≤200W)", "Alta (≤1kW)", "Máxima (>1kW)"],
                                          index=["QRP (≤5W)", "Baja (≤50W)", "Media (≤200W)", "Alta (≤1kW)", "Máxima (>1kW)"].index(potencia) if potencia in ["QRP (≤5W)", "Baja (≤50W)", "Media (≤200W)", "Alta (≤1kW)", "Máxima (>1kW)"] else 1)

            # Botones
            cb1, cb2 = st.columns(2)
            with cb1:
                guardar = st.form_submit_button("💾 Guardar Parámetros", type="primary", width='stretch')
            with cb2:
                cancelar = st.form_submit_button("❌ Cancelar", type="secondary", width='stretch')

        # Acciones del form de parámetros
        if guardar:
            try:
                # Persistir preferencias de usuario
                if "user" in st.session_state and st.session_state.user and "id" in st.session_state.user:
                    # Actualizar la base de datos
                    db.update_user(
                        user_id=st.session_state.user["id"],
                        sistema_preferido=sistema_preferido,
                        frecuencia=(frecuencia if sistema_preferido == "HF" else None),
                        modo=(modo if sistema_preferido == "HF" else None),
                        potencia=(potencia if sistema_preferido == "HF" else None),
                        pre_registro=pre_registro,
                        swl_estado=swl_estado,
                        swl_ciudad=swl_ciudad,
                        qrz_station=qrz_estacion,
                    )
                    # Actualizar la sesión del usuario con los datos actualizados de la base de datos
                    updated_user = db.get_user_by_id(st.session_state.user["id"])
                    if updated_user:
                        st.session_state.user.update(updated_user)
                        print(f"[DEBUG] Sesión actualizada: {st.session_state.user}")
            except Exception as e:
                st.warning(f"⚠️ No se pudieron guardar preferencias de usuario: {e}")

            # Guardar parámetros en sesión
            st.session_state.parametros_reporte = {
                "fecha_reporte": fecha.strftime("%d/%m/%Y"),
                "qrz_estacion": qrz_estacion,
                "tipo_reporte": tipo_reporte,
                "sistema_preferido": sistema_preferido,
                "pre_registro": pre_registro,
                "swl_estado": swl_estado,
                "swl_ciudad": swl_ciudad,
            }
            if sistema_preferido == "HF":
                st.session_state.parametros_reporte.update({
                    "frecuencia": frecuencia, "modo": modo, "potencia": potencia
                })

            # Cerrar expander y mostrar resto del flujo
            st.session_state.expander_abierto = False
            st.session_state.just_saved_params = True  # bandera para este ciclo
            st.success("✅ Parámetros guardados.")
            sleep(0.3)
            st.rerun()

        if cancelar:
            st.session_state.expander_abierto = False
            st.rerun()

    # ==========================
    # Pre-Registros (form)
    # ==========================
    if st.session_state.parametros_reporte and not st.session_state.expander_abierto:
        st.markdown("### Pre-Registros")

        # Clave única del form basada en nonce para evitar duplicados
        pre_form_key = f"pre_registros_form_{st.session_state.get('pre_form_nonce',0)}"
        with st.form(pre_form_key):
            n = st.session_state.parametros_reporte["pre_registro"]
            for i in range(n):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.text_input(
                        f"Indicativo {i+1}",
                        key=_pre_form_key(f"indicativo_{i}"),
                        placeholder="Ej: XE1ABC"
                    )
                with col2:
                    # Opciones de sistemas desde BD
                    try:
                        sist_dict = db.get_sistemas()
                        sist_opc = sorted(list(sist_dict.keys())) or ["ASL"]
                    except Exception:
                        sist_opc = ["ASL"]

                    # Usar el sistema preferido como selección por defecto
                    sistema_default = pr.get("sistema_preferido")
                    if sistema_default not in sist_opc:
                        sistema_default = sist_opc[0] if sist_opc else "ASL"

                    st.selectbox(
                        f"Sistema {i+1}",
                        sist_opc,
                        index=(sist_opc.index(sistema_default) if sistema_default in sist_opc else 0),
                        key=_pre_form_key(f"sistema_{i}"),
                    )

            pre_guardar = st.form_submit_button("📋 Pre-Registrar Todos", type="primary", width='stretch')

        # Procesar el pre-registro
        if pre_guardar:
            pr = st.session_state.parametros_reporte
            registros_guardar = []
            indicativos_invalidos, indicativos_incompletos = [], []

            for i in range(pr["pre_registro"]):
                indicativo = _safe_str(st.session_state.get(_pre_form_key(f"indicativo_{i}"))).strip().upper()
                if not indicativo:
                    continue

                # Validar indicativo
                try:
                    result_val = utils.validar_call_sign(indicativo)
                except Exception:
                    result_val = {"indicativo": True, "completo": True, "Zona": ""}

                if not result_val.get("indicativo"):
                    indicativos_invalidos.append(indicativo)
                    continue
                if not result_val.get("completo"):
                    indicativos_incompletos.append(indicativo)
                    continue

                # Base del registro
                registro = {
                    "indicativo": indicativo,
                    "sistema": st.session_state.get(_pre_form_key(f"sistema_{i}"), pr["sistema_preferido"]),
                    "fecha": pr["fecha_reporte"],
                    "tipo_reporte": pr["tipo_reporte"],
                    "senal": "59",
                }

                # SWR: copiar SWL estado/ciudad y zona vacía
                if indicativo == "SWR":
                    registro["estado"] = _safe_str(pr.get("swl_estado"))
                    registro["ciudad"] = _safe_str(pr.get("swl_ciudad"))
                    registro["zona"] = ""
                    registro["_es_swr"] = True
                else:
                    rep = db.get_ultimo_reporte_por_indicativo(indicativo)
                    if rep:
                        registro.update({
                            "nombre_operador": _safe_str(rep.get("nombre", "")),
                            "estado": _safe_str(rep.get("estado", "")),
                            "ciudad": _safe_str(rep.get("ciudad", "")),
                        })
                        zona_rep = _safe_str(rep.get("zona", ""))
                        registro["zona"] = zona_rep if zona_rep else _estimar_zona(indicativo, zona_bd="", result_validacion=result_val)
                        registro["origen"] = "Reportes"
                        if not registro.get("estado"):
                            registro["estado"] = _safe_str(pr.get("swl_estado"))
                        if not registro.get("ciudad"):
                            registro["ciudad"] = _safe_str(pr.get("swl_ciudad"))
                    else:
                        # Buscar en radioexperimentadores
                        rx = db.get_radioexperimentador_por_indicativo(indicativo)
                        if rx:
                            registro.update({
                                "nombre_operador": _safe_str(rx.get("nombre_completo","")),
                                "apellido_paterno": _safe_str(rx.get("apellido_paterno","")),
                                "apellido_materno": _safe_str(rx.get("apellido_materno","")),
                                "estado": _safe_str(rx.get("estado","")),
                                "ciudad": _safe_str(rx.get("municipio","")),
                                "colonia": _safe_str(rx.get("colonia","")),
                                "codigo_postal": _safe_str(rx.get("codigo_postal","")),
                                "telefono": _safe_str(rx.get("telefono","")),
                                "email": _safe_str(rx.get("email","")),
                            })
                            zona_bd = _safe_str(rx.get("zona",""))
                            registro["zona"] = _estimar_zona(indicativo, zona_bd=zona_bd, result_validacion=result_val)
                            registro["origen"] = "Radioexperimentadores"

                            # Si sigue sin estado/ciudad, usa SWL como respaldo
                            if not registro.get("estado"):
                                registro["estado"] = _safe_str(pr.get("swl_estado"))
                            if not registro.get("ciudad"):
                                registro["ciudad"] = _safe_str(pr.get("swl_ciudad"))
                        else:
                            # No existe en BD → usar SWL + estimar zona y dejar nombre vacío
                            registro.update({
                                "nombre_operador": "",
                                "estado": _safe_str(pr.get("swl_estado")),
                                "ciudad": _safe_str(pr.get("swl_ciudad")),
                            })
                            # Extranjero directo si la validación lo marcó así
                            if result_val.get("Zona") == "Extranjera":
                                registro["zona"] = "EXT"
                                registro["estado"] = "Extranjero"
                            else:
                                registro["zona"] = _estimar_zona(indicativo, zona_bd="", result_validacion=result_val)

                # HF extras
                if pr.get("sistema_preferido") == "HF":
                    registro.update({
                        "frecuencia": _safe_str(pr.get("frecuencia","")),
                        "modo": _safe_str(pr.get("modo","")),
                        "potencia": _safe_str(pr.get("potencia","")),
                    })

                registros_guardar.append(registro)

            if indicativos_invalidos:
                st.error(f"❌ Indicativos inválidos: {', '.join(indicativos_invalidos)}")
                return
            if indicativos_incompletos:
                st.error(f"⚠️ Indicativos incompletos (falta sufijo): {', '.join(indicativos_incompletos)}")
                return
            if not registros_guardar:
                st.warning("⚠️ No hay registros válidos para procesar.")
                return

            st.session_state.registros = registros_guardar
            st.session_state.registros_editados = False
            st.success("✅ Pre-registros cargados.")
            st.rerun()

    # ==========================
    # Tabla editable de "Estaciones a Reportar"
    # ==========================
    if st.session_state.get("registros"):
        st.markdown("---")
        st.subheader("📋 Estaciones a Reportar")

        # Ajustar SWR y normalizar strings antes del DataFrame
        pr = st.session_state.parametros_reporte
        registros_para_df = []
        for reg in st.session_state.registros:
            r = dict(reg)
            if r.get("_es_swr"):
                r["estado"] = _safe_str(pr.get("swl_estado"))
                r["ciudad"] = _safe_str(pr.get("swl_ciudad"))
                r["zona"] = ""
            # Convertir None->"" en campos de texto
            for k in ("indicativo", "nombre_operador", "estado", "ciudad", "zona", "sistema", "frecuencia", "modo", "potencia"):
                if k in r:
                    r[k] = _safe_str(r[k])
            # Señal a entero seguro
            try:
                r["senal"] = int(r.get("senal", 59) or 59)
            except Exception:
                r["senal"] = 59
            registros_para_df.append(r)

        df = pd.DataFrame(registros_para_df).fillna("")
        columnas_a_mostrar = ['indicativo', 'nombre_operador', 'estado', 'ciudad', 'zona', 'sistema', 'senal']
        if pr.get('sistema_preferido') == 'HF':
            columnas_a_mostrar += ['frecuencia', 'modo', 'potencia']
        columnas_disponibles = [c for c in columnas_a_mostrar if c in df.columns]

        # Opciones dropdown
        try:
            estados_db = _get_estados_options()
            estados_options = [e['estado'] for e in estados_db]
        except Exception:
            estados_options = []
        try:
            zonas_db = _get_zonas_options()
            zonas_options = [z['zona'] for z in zonas_db]
        except Exception:
            zonas_options = ["XE1", "XE2", "XE3", "EXT", ""]

        # Asegurar estados presentes
        for r in registros_para_df:
            if r.get("estado") and r["estado"] not in estados_options:
                estados_options.append(r["estado"])

        # Column config sin NaN
        column_config = {
            'indicativo': st.column_config.TextColumn('Indicativo', disabled=True),
            'nombre_operador': st.column_config.TextColumn('Operador'),
            'estado': st.column_config.SelectboxColumn('Estado', options=estados_options or [""], required=False),
            'ciudad': st.column_config.TextColumn('Ciudad'),
            'zona': st.column_config.SelectboxColumn('Zona', options=zonas_options or [""], required=False),
            'sistema': st.column_config.SelectboxColumn('Sistema', options=['HF','ASL','IRLP','DMR','Fusion','D-Star','P25','M17'], required=True),
            'senal': st.column_config.NumberColumn('Señal', min_value=1, max_value=99, step=1, format="%d"),
        }
        if pr.get('sistema_preferido') == 'HF':
            column_config.update({
                'frecuencia': st.column_config.TextColumn('Frecuencia (MHz)'),
                'modo': st.column_config.SelectboxColumn('Modo', options=["SSB","CW","FT8","RTTY","PSK31","Otro"], required=False),
                'potencia': st.column_config.SelectboxColumn('Potencia', options=["QRP (≤5W)","Baja (≤50W)","Media (≤200W)","Alta (≤1kW)","Máxima (>1kW)"], required=False),
            })

        # Crear dataframe para mostrar en la tabla usando los valores actuales de session_state
        df_para_tabla = []
        for reg in st.session_state.registros:
            fila = {}
            for col in columnas_disponibles:
                fila[col] = reg.get(col, "")
            df_para_tabla.append(fila)

        df_para_tabla = pd.DataFrame(df_para_tabla).fillna("")

        # Usar st.data_editor con configuración optimizada
        edited_df = st.data_editor(
            df_para_tabla,
            column_config=column_config,
            hide_index=True,
            width='stretch',
            key="editable_table"
        )

        # Detectar cambios de manera más robusta
        cambios_detectados = False
        campos_actualizados = {}

        # Comparar cada celda individualmente
        try:
            for i, (_, row_edit) in enumerate(edited_df.iterrows()):
                if i < len(st.session_state.registros):
                    registro_actual = st.session_state.registros[i]

                    for col in columnas_disponibles:
                        if col in row_edit.index:
                            valor_editado = row_edit[col]
                            valor_actual = registro_actual.get(col, "")

                            # Convertir a string para comparación confiable
                            valor_editado_str = str(valor_editado) if pd.notna(valor_editado) else ""
                            valor_actual_str = str(valor_actual) if valor_actual is not None else ""

                            if valor_editado_str != valor_actual_str:
                                print(f"[DEBUG] Diferencia detectada en fila {i}, columna {col}")
                                print(f"[DEBUG] Valor editado: '{valor_editado_str}', valor actual: '{valor_actual_str}'")

                                # Actualizar inmediatamente el session_state
                                if pd.notna(valor_editado) and valor_editado_str.strip():
                                    st.session_state.registros[i][col] = valor_editado_str
                                    campos_actualizados[f"{i}_{col}"] = valor_editado_str
                                    print(f"[DEBUG] ✅ session_state actualizado para {col}")
                                    cambios_detectados = True
                                break
                    if cambios_detectados:
                        break
        except Exception as e:
            print(f"[DEBUG] Error en detección de cambios: {e}")
            cambios_detectados = True

        # Marcar que la tabla ha sido editada
        if cambios_detectados or campos_actualizados:
            st.session_state.tabla_editada = True
            st.session_state.registros_editados = True

            # Mostrar resumen de cambios
            if campos_actualizados:
                print(f"[DEBUG] 📝 Campos actualizados: {len(campos_actualizados)}")
                for campo, valor in campos_actualizados.items():
                    print(f"[DEBUG]   {campo}: '{valor}'")

            # Verificación detallada después de la actualización
            print("[DEBUG] === VERIFICACIÓN POST-ACTUALIZACIÓN ===")
            for i, reg in enumerate(st.session_state.registros[:3]):  # Solo primeros 3 para no saturar logs
                print(f"[DEBUG] Registro {i}:")
                for col in columnas_disponibles:
                    valor = reg.get(col, 'N/A')
                    print(f"[DEBUG]   {col}: '{valor}'")
                print("[DEBUG] -------------------")

            # Forzar rerun para actualizar la interfaz visual
            st.rerun()

        print(f"[DEBUG] Estado final - tabla_editada: {st.session_state.get('tabla_editada', False)}, registros_editados: {st.session_state.get('registros_editados', False)}")

        # Mostrar información de debug
        st.caption(f"Total de registros: {len(df)} | Tabla editada: {st.session_state.get('tabla_editada', False)}")
        if st.session_state.get("registros_editados", False):
            st.info("💡 Los cambios se aplicarán cuando guardes en la base de datos.")

        # Botones Guardar / Deshacer / Limpiar
        c1, c2, c3 = st.columns([2,1,1])
        with c1:
            if st.button("💾 Guardar en Base de Datos", type="primary", width='stretch'):
                # Guardar en BD
                guardados = 0
                pr = st.session_state.parametros_reporte
                for registro in st.session_state.registros:
                    if not registro.get("indicativo") or not pr.get("tipo_reporte"):
                        continue

                    # Debug: mostrar qué se va a guardar
                    print(f"[DEBUG] Guardando registro: {registro.get('indicativo', 'N/A')}")
                    print(f"[DEBUG] Valores: nombre_operador='{registro.get('nombre_operador', 'N/A')}', estado='{registro.get('estado', 'N/A')}', ciudad='{registro.get('ciudad', 'N/A')}'")

                    # Ensamble payload
                    # Obtener el indicativo del usuario logueado
                    usuario_logueado = st.session_state.user.get('username', '') if 'user' in st.session_state else ''
                    
                    # Obtener la estación QRZ del usuario logueado
                    qrz_station = ''
                    if 'user' in st.session_state and st.session_state.user:
                        # Verificar la estructura del objeto user
                        print(f"[DEBUG] Estructura del usuario: {st.session_state.user}")
                        # Intentar obtener qrz_station de diferentes formas
                        qrz_station = st.session_state.user.get('qrz_station', '')
                        if not qrz_station:
                            # Si no está en el primer nivel, verificar en data
                            if 'data' in st.session_state.user and st.session_state.user['data']:
                                qrz_station = st.session_state.user['data'].get('qrz_station', '')
                    
                    print(f"[DEBUG] qrz_station del usuario: {qrz_station}")
                    print(f"[DEBUG] usuario_logueado: {usuario_logueado}")
                    print(f"[DEBUG] Estructura completa del usuario: {st.session_state.user if 'user' in st.session_state else 'No hay usuario en la sesión'}")
                    
                    payload = {
                        'indicativo': _safe_str(registro.get('indicativo')).upper(),
                        'nombre': _formatear_oracion(_safe_str(registro.get('nombre_operador'))),
                        'estado': _safe_str(registro.get('estado')),
                        'ciudad': _formatear_oracion(_safe_str(registro.get('ciudad'))),
                        'zona': _safe_str(registro.get('zona')),
                        'sistema': _safe_str(registro.get('sistema') or pr.get('sistema_preferido') or 'ASL'),
                        'senal': int(registro.get('senal') or 59),
                        'fecha_reporte': pr.get('fecha_reporte', get_current_cdmx_time().strftime('%d/%m/%Y')),
                        'tipo_reporte': pr.get('tipo_reporte','Boletín'),
                        'origen': _safe_str(registro.get('origen') or 'Manual'),
                        'qrz_captured_by': usuario_logueado,  # Indicativo del usuario que capturó el reporte
                        'qrz_station': qrz_station  # Estación QRZ del usuario
                    }

                    print(f"[DEBUG] Payload: nombre='{payload['nombre']}', estado='{payload['estado']}', ciudad='{payload['ciudad']}'")
                    if payload['sistema'] == 'HF':
                        payload['observaciones'] = f"Frecuencia: {_safe_str(registro.get('frecuencia',''))}, Modo: {_safe_str(registro.get('modo',''))}, Potencia: {_safe_str(registro.get('potencia',''))}"
                    try:
                        db.save_reporte(payload)
                        guardados += 1
                    except Exception as e:
                        st.error(f"❌ Error al guardar {payload['indicativo']}: {e}")

                if guardados > 0:
                    st.success(f"✅ {guardados} registro(s) guardado(s) correctamente.")
                    # LIMPIEZA post-guardado:
                    st.session_state.registros = []                 # limpiar tabla editable
                    st.session_state.registros_editados = False
                    st.session_state.tabla_editada = False
                    st.session_state.expander_abierto = False        # mantener expander cerrado
                    # Limpiar también el estado original
                    if hasattr(st.session_state, 'registros_estado_original'):
                        delattr(st.session_state, 'registros_estado_original')
                    _clear_current_pre_form_inputs()                 # limpiar inputs actuales
                    _bump_pre_form_nonce_and_clear()                 # forzar que los inputs aparezcan vacíos
                    sleep(0.4)
                    st.rerun()
                else:
                    st.warning("⚠️ No se guardó ningún registro.")

        with c2:
            if st.session_state.get("registros_editados", False):
                if st.button("↩️ Deshacer Cambios", width='stretch'):
                    st.session_state.registros_editados = False
                    st.session_state.tabla_editada = False
                    # Restaurar el estado original
                    if hasattr(st.session_state, 'registros_estado_original'):
                        st.session_state.registros = []
                        for reg in st.session_state.registros_estado_original:
                            st.session_state.registros.append(dict(reg))
                        # Limpiar el estado original después de restaurar
                        delattr(st.session_state, 'registros_estado_original')
                    st.rerun()

        with c3:
            if st.button("🗑️ Limpiar registros", width='stretch'):
                st.session_state.registros = []
                st.session_state.registros_editados = False
                st.session_state.tabla_editada = False
                # Limpiar también el estado original
                if hasattr(st.session_state, 'registros_estado_original'):
                    delattr(st.session_state, 'registros_estado_original')
                st.rerun()

    # ==========================
    # Estadísticas + Tabla del día (si hay parámetros)
    # Siempre se muestran cuando ya cerraste el expander,
    # aunque no haya registros en edición.
    # ==========================
        # ==========================
    # Estadísticas + Tabla del día (versión original con estilo)
    # ==========================
    if st.session_state.parametros_reporte:
        st.markdown("---")

        # Obtener la fecha de los parámetros de captura
        fecha_reporte = st.session_state.parametros_reporte.get('fecha_reporte')

        try:
            from datetime import datetime
            fecha_dt = datetime.strptime(fecha_reporte, '%d/%m/%Y')
            fecha_consulta = fecha_dt.strftime('%Y-%m-%d')
            reportes, estadisticas = db.get_reportes_por_fecha(fecha_consulta)
            st.caption(f"📅 Mostrando reportes del: {fecha_reporte}")
        except (ValueError, TypeError):
            st.error("❌ Error en el formato de la fecha. Asegúrate de usar el formato DD/MM/YYYY")
            reportes, estadisticas = [], {}

        st.subheader("📊 Estadísticas del Día")

        if estadisticas:
            col1, col2, col3, col4 = st.columns(4)

            def crear_tarjeta(column, titulo, valor=None, subtitulos=None):
                with column:
                    with st.container():
                        st.markdown(f"""
                            <div style="
                                font-size: 0.9rem;
                                color: #2e7d32;
                                font-weight: 600;
                                margin-bottom: 10px;
                                white-space: nowrap;
                                overflow: hidden;
                                text-overflow: ellipsis;
                            ">{titulo}</div>
                        """, unsafe_allow_html=True)

                        if valor is not None and valor != "":
                            st.markdown(f"""
                                <div style="
                                    font-size: 1.8rem;
                                    font-weight: 700;
                                    color: #1b5e20;
                                    margin-bottom: 10px;
                                    text-align: center;
                                    background-color: #e8f5e9;
                                    border-radius: 4px;
                                    padding: 10px 0;
                                    min-height: 60px;
                                    display: flex;
                                    align-items: center;
                                    justify-content: center;
                                ">{valor}</div>
                            """, unsafe_allow_html=True)

                        if subtitulos:
                            for item in subtitulos:
                                nombre = item.get('nombre','')
                                cantidad = str(item.get('cantidad',''))
                                st.markdown(f"""
                                    <div style="
                                        font-size: 0.75rem;
                                        color: #4caf50;
                                        margin: 5px 0;
                                        display: flex;
                                        justify-content: space-between;
                                        align-items: center;
                                    ">
                                        <span>{nombre}</span>
                                        {'<span style="background-color: #e8f5e9; border-radius: 10px; padding: 0 6px; font-weight: 600; font-size: 0.7rem;">' + cantidad + '</span>' if cantidad else ''}
                                    </div>
                                """, unsafe_allow_html=True)

                        st.markdown("""
                            <style>
                                div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column"] > div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlock"] {
                                    background-color: #f0f9f0;
                                    border-radius: 8px;
                                    padding: 15px;
                                    border-left: 4px solid #2e7d32;
                                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                                    height: 100%;
                                    display: flex;
                                    flex-direction: column;
                                }
                            </style>
                        """, unsafe_allow_html=True)

            crear_tarjeta(col1, "📋 Total de Reportes", str(estadisticas.get('total', 0)))
            zonas = [{'nombre': z['zona'], 'cantidad': str(z['cantidad'])} for z in estadisticas.get('zonas_mas_reportadas', [])[:3]]
            crear_tarjeta(col2, "📍 Zonas más reportadas", subtitulos=zonas if zonas else [{'nombre':'Sin datos'}])
            sistemas = [{'nombre': s['sistema'], 'cantidad': str(s['cantidad'])} for s in estadisticas.get('sistemas_mas_utilizados', [])[:3]]
            crear_tarjeta(col3, "📡 Sistemas más usados", subtitulos=sistemas if sistemas else [{'nombre':'Sin datos'}])
            estados = [{'nombre': e['estado'], 'cantidad': str(e['cantidad'])} for e in estadisticas.get('estados_mas_reportados', [])[:3]]
            crear_tarjeta(col4, "🏙️ Estados más reportados", subtitulos=estados if estados else [{'nombre':'Sin datos'}])

        # Tabla de reportes del día
        if reportes:
            import pandas as pd
            def format_time(dt_str):
                if not dt_str: return ''
                for fmt in ('%Y-%m-%d %H:%M:%S','%d/%m/%Y %H:%M:%S'):
                    try: return datetime.strptime(dt_str, fmt).strftime('%H:%M')
                    except ValueError: continue
                return ''

            def format_date(dt_str):
                if not dt_str: return ''
                for fmt in ('%Y-%m-%d %H:%M:%S','%d/%m/%Y %H:%M:%S'):
                    try: return datetime.strptime(dt_str, fmt).strftime('%d/%m/%Y')
                    except ValueError: continue
                return ''

            df_reportes = pd.DataFrame([{
                'Indicativo': r.get('indicativo',''),
                'Nombre': r.get('nombre',''),
                'Sistema': r.get('sistema',''),
                'Zona': r.get('zona',''),
                'Estado': r.get('estado',''),
                'Ciudad': r.get('ciudad',''),
                'Señal': r.get('senal',''),
                'Fecha': format_date(r.get('fecha_reporte','')),
                'Hora': format_time(r.get('fecha_reporte')),
                'Origen': r.get('origen',''),
                'Capturado Por': r.get('qrz_captured_by',''),
                'Operando': r.get('qrz_station','')
            } for r in reportes])

            st.data_editor(
                df_reportes,
                column_config={
                    'Indicativo': st.column_config.TextColumn("Indicativo"),
                    'Nombre': st.column_config.TextColumn("Nombre"),
                    'Sistema': st.column_config.TextColumn("Sistema"),
                    'Zona': st.column_config.TextColumn("Zona"),
                    'Estado': st.column_config.TextColumn("Estado"),
                    'Ciudad': st.column_config.TextColumn("Ciudad"),
                    'Señal': st.column_config.NumberColumn("Señal"),
                    'Origen': st.column_config.TextColumn("Origen"),
                    'Hora': st.column_config.TextColumn("Hora")
                },
                hide_index=True,
                width='stretch'
            )
        else:
            st.info("No hay reportes registrados para el día de hoy.")

def show_registros():
    """Muestra la sección de registros con pestañas para Tradicional y Redes Sociales"""
    st.title("📋 Registros")

    # Pestañas principales: Tradicional y Redes Sociales
    t1, t2 = st.tabs(["📻 Tradicional", "📱 Redes Sociales"])

    # Tradicional: Lista y Editar
    with t1:
        tab1, tab2 = st.tabs(["📋 Lista", "✏️ Editar"])
        with tab1:
            show_lista_registros()
        with tab2:
            show_editar_registros()

    # Redes Sociales: seleccionar entre Registros e Interacciones, cada una con Lista/Editar
    with t2:
        rs_tab_reg, rs_tab_inter = st.tabs(["🧾 Registros", "🤝 Interacciones"])
        with rs_tab_reg:
            tab3, tab4 = st.tabs(["📋 Lista", "✏️ Editar"])
            with tab3:
                show_lista_registros_rs()
            with tab4:
                show_editar_registros_rs()
        with rs_tab_inter:
            tab5, tab6 = st.tabs(["📋 Lista", "✏️ Editar"])
            with tab5:
                show_lista_interacciones_rs()
            with tab6:
                show_editar_interacciones_rs()

def show_lista_registros():
    """Muestra la lista de registros con filtros y búsqueda"""
    st.subheader("📋 Lista de Registros")

    # Inicializar variables de sesión si no existen
    if 'registros_filtros' not in st.session_state:
        st.session_state.registros_filtros = {
            'fecha_inicio': None,
            'fecha_fin': None,
            'busqueda': '',
            'filtro_estado': '',
            'filtro_zona': '',
            'filtro_sistema': ''
        }

    # Filtros de fecha
    col1, col2 = st.columns(2)

    with col1:
        fecha_inicio = st.date_input(
            "Fecha inicio",
            value=st.session_state.registros_filtros['fecha_inicio'],
            help="Fecha de inicio para filtrar registros",
            key="fecha_inicio_lista"
        )

    with col2:
        fecha_fin = st.date_input(
            "Fecha fin",
            value=st.session_state.registros_filtros['fecha_fin'],
            help="Fecha de fin para filtrar registros",
            key="fecha_fin_lista"
        )

    # Campo de búsqueda unificado
    busqueda = st.text_input(
        "🔍 Buscar en todos los campos (insensible a acentos)",
        value=st.session_state.registros_filtros['busqueda'],
        placeholder="Indicativo, nombre, ciudad, estado, zona, sistema, tipo...",
        help="Busca simultáneamente en: indicativo, nombre, ciudad, estado, zona, sistema y tipo. Funciona con o sin acentos (boletin/boletín)",
        key="busqueda_lista"
    )

    # Botones de acción alineados al nivel de los filtros
    col_offset, col_buscar, col_limpiar, col_spacer = st.columns([1.2, 2.2, 2.2, 3.4])

    buscar_clicked = col_buscar.button(
        "🔍 Buscar Registros",
        type="primary",
        key="buscar_lista",
        width="stretch"
    )

    limpiar_clicked = col_limpiar.button(
        "🧹 Limpiar Filtros",
        key="limpiar_lista",
        width="stretch"
    )

    if buscar_clicked:
        st.session_state.registros_filtros.update({
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'busqueda': busqueda
        })
        st.rerun()

    if limpiar_clicked:
        st.session_state.registros_filtros = {
            'fecha_inicio': None,
            'fecha_fin': None,
            'busqueda': ''
        }
        st.rerun()

    # Obtener registros con filtros aplicados
    try:
        registros, total_registros = db.get_reportes_filtrados(
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            busqueda=busqueda
            # Los filtros específicos (estado, zona, sistema) se eliminan
            # La búsqueda ya se hace en todos los campos
        )

        # Mostrar estadísticas
        st.caption(f"Mostrando {len(registros)} de {total_registros} registros")

        if registros:
            # Convertir a DataFrame para mostrar en tabla
            import pandas as pd

            df_registros = pd.DataFrame([{
                'ID': r.get('id', ''),
                'Indicativo': r.get('indicativo', ''),
                'Nombre': r.get('nombre', ''),
                'Sistema': r.get('sistema', ''),
                'Zona': r.get('zona', ''),
                'Estado': r.get('estado', ''),
                'Ciudad': r.get('ciudad', ''),
                'Señal': r.get('senal', ''),
                'Tipo': r.get('tipo_reporte', ''),
                'Fecha': r.get('fecha_reporte', ''),
                'Observaciones': r.get('observaciones', '')[:50] + '...' if len(r.get('observaciones', '')) > 50 else r.get('observaciones', ''),
                'Operando': r.get('qrz_station', ''),
                'Capturado Por': r.get('qrz_captured_by', '')
            } for r in registros])

            # Mostrar la tabla
            st.data_editor(
                df_registros,
                column_config={
                    'ID': st.column_config.NumberColumn("ID", width="small"),
                    'Indicativo': st.column_config.TextColumn("Indicativo", width="medium"),
                    'Nombre': st.column_config.TextColumn("Nombre", width="large"),
                    'Sistema': st.column_config.TextColumn("Sistema", width="small"),
                    'Zona': st.column_config.TextColumn("Zona", width="small"),
                    'Estado': st.column_config.TextColumn("Estado", width="medium"),
                    'Ciudad': st.column_config.TextColumn("Ciudad", width="medium"),
                    'Señal': st.column_config.NumberColumn("Señal", width="small"),
                    'Tipo': st.column_config.TextColumn("Tipo", width="small"),
                    'Fecha': st.column_config.TextColumn("Fecha", width="medium"),
                    'Observaciones': st.column_config.TextColumn("Observaciones", width="large")
                },
                hide_index=True,
                use_container_width=True,
                disabled=True  # Solo lectura en la pestaña de lista
            )

            # Botón para exportar a Excel
            fecha_inicio_str = fecha_inicio.strftime('%Y%m%d') if fecha_inicio else "inicio"
            fecha_fin_str = fecha_fin.strftime('%Y%m%d') if fecha_fin else "fin"

            from io import BytesIO
            output = BytesIO()

            engine = None
            try:
                import importlib

                if importlib.util.find_spec("xlsxwriter"):
                    engine = "xlsxwriter"
            except Exception:
                engine = None

            try:
                with pd.ExcelWriter(output, engine=engine) as writer:
                    df_registros.to_excel(writer, index=False, sheet_name='Registros')

                    if engine == "xlsxwriter":
                        workbook = writer.book
                        worksheet = writer.sheets['Registros']

                        for i, col in enumerate(df_registros.columns):
                            max_length = max(df_registros[col].astype(str).apply(len).max(), len(col)) + 2
                            worksheet.set_column(i, i, max_length)

                data_bytes = output.getvalue()
                mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                file_name = f"registros_{fecha_inicio_str}_{fecha_fin_str}.xlsx"
            except Exception:
                csv_output = df_registros.to_csv(index=False).encode('utf-8-sig')
                data_bytes = csv_output
                mime_type = "text/csv"
                file_name = f"registros_{fecha_inicio_str}_{fecha_fin_str}.csv"

            st.download_button(
                label="📥 Exportar",
                data=data_bytes,
                file_name=file_name,
                mime=mime_type,
                key="descargar_excel_lista",
                width='stretch'
            )

        else:
            st.info("No se encontraron registros con los filtros aplicados")

    except Exception as e:
        st.error(f"Error al cargar los registros: {str(e)}")

def show_editar_registros():
    """Muestra la sección para editar registros con funcionalidades CRUD"""
    st.subheader("✏️ Editar Registros")

    # Inicializar variables de sesión si no existen
    if 'editando_registro_id' not in st.session_state:
        st.session_state.editando_registro_id = None
    if 'eliminando_registro_id' not in st.session_state:
        st.session_state.eliminando_registro_id = None

    # Si estamos editando un registro, mostrar formulario de edición
    if st.session_state.editando_registro_id:
        _mostrar_formulario_edicion_registro(st.session_state.editando_registro_id)
        return

    # Filtros de búsqueda (similares a la pestaña de lista)
    col1, col2 = st.columns(2)

    with col1:
        fecha_inicio = st.date_input(
            "Fecha inicio",
            help="Fecha de inicio para filtrar registros",
            key="fecha_inicio_editar"
        )

    with col2:
        fecha_fin = st.date_input(
            "Fecha fin",
            help="Fecha de fin para filtrar registros",
            key="fecha_fin_editar"
        )

    # Campo de búsqueda unificado
    busqueda = st.text_input(
        "🔍 Buscar en todos los campos (insensible a acentos)",
        placeholder="Indicativo, nombre, ciudad, estado, zona, sistema, tipo...",
        help="Busca simultáneamente en: indicativo, nombre, ciudad, estado, zona, sistema y tipo. Funciona con o sin acentos (boletin/boletín)",
        key="busqueda_editar"
    )

    # Botón de buscar
    if st.button("🔍 Buscar Registros", type="primary", key="buscar_editar"):
        st.session_state.registros_filtros_editar = {
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'busqueda': busqueda
        }
        st.rerun()

    # Obtener registros con filtros
    try:
        filtros = getattr(st.session_state, 'registros_filtros_editar', {
            'fecha_inicio': None,
            'fecha_fin': None,
            'busqueda': ''
        })

        registros, total_registros = db.get_reportes_filtrados(
            fecha_inicio=filtros['fecha_inicio'],
            fecha_fin=filtros['fecha_fin'],
            busqueda=filtros['busqueda']
            # Los filtros específicos se eliminan - la búsqueda ya es multicampo
        )
        # Inicializar variables de sesión para selección masiva si no existen
        if 'registros_seleccionados' not in st.session_state:
            st.session_state.registros_seleccionados = set()
        if 'eliminando_masivo' not in st.session_state:
            st.session_state.eliminando_masivo = False
        if 'show_delete_modal' not in st.session_state:
            st.session_state.show_delete_modal = False

        if registros:
            import pandas as pd

            registros_actuales = st.session_state.registros_seleccionados or set()

            col_acc1, col_acc2 = st.columns(2)
            with col_acc1:
                if st.button("✅ Seleccionar Todos", key="select_all_editar"):
                    st.session_state.registros_seleccionados = {r['id'] for r in registros if r.get('id') is not None}
                    st.session_state.eliminando_masivo = False
                    st.rerun()
            with col_acc2:
                if st.button("🧹 Limpiar Selección", key="clear_selection_editar"):
                    st.session_state.registros_seleccionados.clear()
                    st.session_state.eliminando_masivo = False
                    st.rerun()

            df_registros = pd.DataFrame([
                {
                    "ID": registro.get('id'),
                    "Indicativo": registro.get('indicativo', ''),
                    "Nombre": registro.get('nombre', ''),
                    "Sistema": registro.get('sistema', ''),
                    "Zona": registro.get('zona', ''),
                    "Estado": registro.get('estado', ''),
                    "Ciudad": registro.get('ciudad', ''),
                    "Señal": registro.get('senal', ''),
                    "Tipo": registro.get('tipo_reporte', ''),
                    "Fecha": registro.get('fecha_reporte', ''),
                    "Observaciones": (
                        registro.get('observaciones', '')[:50] + '...'
                        if registro.get('observaciones') and len(registro.get('observaciones', '')) > 50
                        else registro.get('observaciones', ''),
                    ),
                    "Operando": registro.get('qrz_station', ''),
                    "Capturado Por": registro.get('qrz_captured_by', '')
                }
                for registro in registros
            ])

            if not df_registros.empty:
                df_registros.insert(0, "Seleccionar", df_registros["ID"].isin(registros_actuales))

            with st.form("tabla_editar_registros"):
                edited_df = st.data_editor(
                    df_registros,
                    hide_index=True,
                    width='stretch',
                    num_rows="fixed",
                    key=f"tabla_editar_registros_{len(df_registros)}",
                    column_config={
                        "Seleccionar": st.column_config.CheckboxColumn(
                            "Seleccionar",
                            help="Marca los registros para editarlos o eliminarlos"
                        ),
                        "ID": st.column_config.NumberColumn("ID", width="small"),
                        "Indicativo": st.column_config.TextColumn("Indicativo", width="medium"),
                        "Nombre": st.column_config.TextColumn("Nombre", width="large"),
                        "Sistema": st.column_config.TextColumn("Sistema", width="small"),
                        "Zona": st.column_config.TextColumn("Zona", width="small"),
                        "Estado": st.column_config.TextColumn("Estado", width="medium"),
                        "Ciudad": st.column_config.TextColumn("Ciudad", width="medium"),
                        "Señal": st.column_config.NumberColumn(
                            "Señal",
                            min_value=1,
                            max_value=99,
                            step=1,
                            format="%d"
                        ),
                        "Tipo": st.column_config.TextColumn("Tipo", width="small"),
                        "Fecha": st.column_config.TextColumn("Fecha", width="medium"),
                        "Observaciones": st.column_config.TextColumn("Observaciones", width="large")
                    },
                    disabled=[
                        "ID", "Indicativo", "Nombre", "Sistema", "Zona", "Estado",
                        "Ciudad", "Señal", "Tipo", "Fecha", "Observaciones"
                    ]
                )

                col_form1, col_form2 = st.columns([1, 1])
                editar_submit = col_form1.form_submit_button("✏️ Editar Seleccionado", type="primary")
                eliminar_submit = col_form2.form_submit_button("🗑️ Eliminar Seleccionados", type="secondary")

            selected_ids = set()
            if not edited_df.empty and "Seleccionar" in edited_df.columns:
                seleccionados_df = edited_df[edited_df["Seleccionar"]]
                selected_ids = {
                    int(id_)
                    for id_ in seleccionados_df["ID"].tolist()
                    if pd.notna(id_)
                }

            if not eliminar_submit:
                st.session_state.eliminando_masivo = st.session_state.eliminando_masivo and bool(selected_ids)

            st.session_state.registros_seleccionados = selected_ids

            if st.session_state.registros_seleccionados:
                st.caption(f"✅ {len(st.session_state.registros_seleccionados)} registros seleccionados")

            if editar_submit:
                if len(selected_ids) != 1:
                    st.warning("Selecciona exactamente un registro para editarlo.")
                else:
                    registro_a_editar = next(iter(selected_ids))
                    st.session_state.registros_seleccionados = {registro_a_editar}
                    st.session_state.editando_registro_id = registro_a_editar
                    st.rerun()

            if eliminar_submit:
                if not selected_ids:
                    st.warning("Selecciona al menos un registro para eliminar.")
                else:
                    st.session_state.eliminando_masivo = True
                    st.session_state.show_delete_modal = True
                    st.rerun()

            if st.session_state.eliminando_masivo and not st.session_state.registros_seleccionados:
                st.session_state.eliminando_masivo = False
                st.session_state.show_delete_modal = False

            if st.session_state.eliminando_masivo and st.session_state.show_delete_modal:
                total_eliminar = len(st.session_state.registros_seleccionados)

                with st.container(border=True):
                    st.warning(
                        f"¿Estás seguro de que quieres eliminar {total_eliminar} registro"
                        f"{'s' if total_eliminar != 1 else ''}? Esta acción no se puede deshacer."
                    )

                    if not seleccionados_df.empty:
                        st.dataframe(
                            seleccionados_df.drop(columns=["Seleccionar"], errors="ignore"),
                            hide_index=True,
                            width='stretch',
                        )

                    col_conf1, col_conf2 = st.columns(2)

                    with col_conf1:
                        if st.button("✅ Confirmar", type="primary", key="confirm_bulk_delete_modal"):
                            try:
                                registros_eliminados = 0
                                for registro_id in st.session_state.registros_seleccionados:
                                    if db.delete_reporte(registro_id):
                                        registros_eliminados += 1

                                if registros_eliminados > 0:
                                    st.success(
                                        f"✅ {registros_eliminados} registro"
                                        f"{'s' if registros_eliminados != 1 else ''} eliminados correctamente"
                                    )
                                    st.session_state.registros_seleccionados.clear()
                                    st.session_state.eliminando_masivo = False
                                    st.session_state.show_delete_modal = False
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    st.error("No se pudo eliminar ningún registro")
                            except Exception as e:
                                st.error(f"Error al eliminar registros: {str(e)}")

                    with col_conf2:
                        if st.button("❌ Cancelar", key="cancel_bulk_delete_modal"):
                            st.session_state.eliminando_masivo = False
                            st.session_state.show_delete_modal = False
                            st.rerun()

        else:
            st.info("No se encontraron registros con los filtros aplicados")

    except Exception as e:
        st.error(f"Error al cargar los registros: {str(e)}")

def _mostrar_formulario_edicion_registro(registro_id):
    """Muestra el formulario para editar un registro existente"""
    st.header("✏️ Editar Registro")

    try:
        # Obtener los datos actuales del registro
        registro = db.get_reporte_por_id(registro_id)

        if not registro:
            st.error("No se encontró el registro especificado")
            if st.button("Volver a la lista", key="volver_lista_error"):
                del st.session_state.editando_registro_id
                st.rerun()
            return

        # Mostrar información del registro
        st.info(f"Editando registro: {registro['indicativo']} - {registro['nombre'] or 'Sin nombre'}")

        sistemas_options = _get_sistemas_options()
        if "" not in sistemas_options:
            sistemas_options = [""] + sistemas_options

        # Formulario de edición
        with st.form(key=f'editar_registro_form_{registro_id}'):
            # Campos editables
            col1, col2 = st.columns(2)

            with col1:
                indicativo = st.text_input(
                    "Indicativo",
                    value=registro['indicativo'],
                    help="Indicativo del radioexperimentador"
                )

                nombre = st.text_input(
                    "Nombre",
                    value=registro['nombre'] or '',
                    help="Nombre del radioexperimentador"
                )

                sistema_index = 0
                if registro['sistema'] and registro['sistema'] in sistemas_options:
                    sistema_index = sistemas_options.index(registro['sistema'])

                sistema = st.selectbox(
                    "Sistema",
                    options=sistemas_options,
                    index=sistema_index,
                    help="Sistema de comunicación utilizado"
                )

            with col1:
                estado = st.selectbox(
                    "Estado",
                    options=[""] + [e['estado'] for e in _get_estados_options() if e and 'estado' in e],
                    index=0 if not registro['estado'] else [e['estado'] for e in _get_estados_options() if e and 'estado' in e].index(registro['estado']) + 1,
                    help="Estado donde reside el radioexperimentador"
                )

            with col2:
                # Obtener opciones para zonas desde la base de datos
                try:
                    zonas_db = db.get_zonas(incluir_inactivas=False)
                    zonas_options = [""] + [z['zona'] for z in zonas_db if z and 'zona' in z]
                except Exception as e:
                    st.error(f"Error al cargar zonas: {str(e)}")
                    zonas_options = [""]

                zona = st.selectbox(
                    "Zona",
                    options=zonas_options,
                    index=0 if not registro['zona'] else zonas_options.index(registro['zona']) if registro['zona'] in zonas_options else 0,
                    help="Zona del radioexperimentador"
                )

                ciudad = st.text_input(
                    "Ciudad",
                    value=registro['ciudad'] or '',
                    help="Ciudad donde reside el radioexperimentador"
                )

                senal = st.number_input(
                    "Señal",
                    min_value=1,
                    max_value=99,
                    value=registro['senal'],
                    help="Nivel de señal reportado"
                )

                tipo_reporte = st.selectbox(
                    "Tipo de Reporte",
                    options=["Boletín", "Retransmisión", "Otro"],
                    index=["Boletín", "Retransmisión", "Otro"].index(registro['tipo_reporte']) if registro['tipo_reporte'] in ["Boletín", "Retransmisión", "Otro"] else 0,
                    help="Tipo de reporte"
                )

            # Observaciones
            observaciones = st.text_area(
                "Observaciones",
                value=registro.get('observaciones', ''),
                help="Observaciones adicionales del reporte"
            )

            # Campos específicos de HF si el sistema es HF
            frecuencia = ""
            modo = ""
            potencia = ""

            if sistema == 'HF':
                st.subheader("📻 Parámetros HF")

                col_hf1, col_hf2, col_hf3 = st.columns(3)

                with col_hf1:
                    frecuencia = st.text_input(
                        "Frecuencia (MHz)",
                        value=registro.get('frecuencia', ''),
                        placeholder="Ej: 7.100",
                        help="Frecuencia en MHz"
                    )

                with col_hf2:
                    modo = st.selectbox(
                        "Modo",
                        options=["SSB", "CW", "FT8", "RTTY", "PSK31", "Otro"],
                        index=0 if not registro.get('modo') else ["SSB", "CW", "FT8", "RTTY", "PSK31", "Otro"].index(registro.get('modo')),
                        help="Modo de operación"
                    )

                with col_hf3:
                    potencia = st.selectbox(
                        "Potencia",
                        options=["QRP (≤5W)", "Baja (≤50W)", "Media (≤200W)", "Alta (≤1kW)", "Máxima (>1kW)"],
                        index=0 if not registro.get('potencia') else ["QRP (≤5W)", "Baja (≤50W)", "Media (≤200W)", "Alta (≤1kW)", "Máxima (>1kW)"].index(registro.get('potencia')),
                        help="Nivel de potencia utilizado"
                    )

            # Botones de acción
            col1, col2, col3 = st.columns([1, 1, 2])

            with col1:
                if st.form_submit_button("💾 Guardar Cambios", type="primary"):
                    # Validar campos obligatorios
                    if not indicativo or not tipo_reporte:
                        st.error("Los campos de indicativo y tipo de reporte son obligatorios")
                    else:
                        try:
                            # Preparar datos para actualizar
                            datos_actualizados = {
                                'indicativo': indicativo.upper(),
                                'nombre': nombre,
                                'sistema': sistema,
                                'estado': estado,
                                'ciudad': ciudad,
                                'zona': zona,
                                'senal': senal,
                                'tipo_reporte': tipo_reporte,
                                'observaciones': observaciones
                            }

                            # Agregar campos HF si corresponde
                            if sistema == 'HF':
                                datos_actualizados.update({
                                    'frecuencia': frecuencia,
                                    'modo': modo,
                                    'potencia': potencia
                                })

                            # Actualizar registro
                            if db.update_reporte(registro_id, datos_actualizados):
                                st.success("¡Los cambios se guardaron correctamente!")
                                time.sleep(2)
                                del st.session_state.editando_registro_id
                                st.rerun()
                            else:
                                st.error("No se pudieron guardar los cambios. Intente nuevamente.")

                        except Exception as e:
                            st.error(f"Error al guardar los cambios: {str(e)}")

            with col2:
                if st.form_submit_button("❌ Cancelar"):
                    del st.session_state.editando_registro_id
                    st.rerun()

            with col3:
                if st.form_submit_button("🗑️ Eliminar Registro", type="secondary"):
                    st.session_state.eliminando_registro_id = registro_id
                    st.session_state.volver_a_editar = True
                    st.rerun()

    except Exception as e:
        st.error(f"Error al cargar el formulario de edición: {str(e)}")
        if st.button("Volver a la lista", key="volver_lista_error2"):
            if 'editando_registro_id' in st.session_state:
                del st.session_state.editando_registro_id
            st.rerun()

def show_lista_registros_rs():
    """Lista registros de Redes Sociales con filtros y exportación"""
    st.subheader("📋 Lista de Registros (Redes Sociales)")

    if 'rs_registros_filtros' not in st.session_state:
        st.session_state.rs_registros_filtros = {
            'fecha_inicio': None,
            'fecha_fin': None,
            'busqueda': ''
        }

    col1, col2 = st.columns(2)
    with col1:
        fecha_inicio = st.date_input(
            "Fecha inicio",
            value=st.session_state.rs_registros_filtros['fecha_inicio'],
            key="rs_fecha_inicio_lista"
        )
    with col2:
        fecha_fin = st.date_input(
            "Fecha fin",
            value=st.session_state.rs_registros_filtros['fecha_fin'],
            key="rs_fecha_fin_lista"
        )

    busqueda = st.text_input(
        "🔍 Buscar en todos los campos (insensible a acentos)",
        value=st.session_state.rs_registros_filtros['busqueda'],
        placeholder="Indicativo, operador, ciudad, estado, zona, plataforma, capturó...",
        key="rs_busqueda_lista"
    )

    c_off, c_buscar, c_limpiar, _ = st.columns([1.2, 2.2, 2.2, 3.4])
    buscar_clicked = c_buscar.button("🔍 Buscar Registros", type="primary", key="rs_buscar_lista", width='stretch')
    limpiar_clicked = c_limpiar.button("🧹 Limpiar Filtros", key="rs_limpiar_lista", width='stretch')

    if buscar_clicked:
        st.session_state.rs_registros_filtros.update({
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'busqueda': busqueda
        })
        st.rerun()

    if limpiar_clicked:
        st.session_state.rs_registros_filtros = {'fecha_inicio': None, 'fecha_fin': None, 'busqueda': ''}
        st.rerun()

    try:
        fecha_inicio_str = fecha_inicio.strftime('%Y-%m-%d') if fecha_inicio else None
        fecha_fin_str = fecha_fin.strftime('%Y-%m-%d') if fecha_fin else None
        reportes, total = db.get_reportes_rs_filtrados(
            fecha_inicio=fecha_inicio_str,
            fecha_fin=fecha_fin_str,
            busqueda=busqueda
        )
        st.caption(f"Mostrando {len(reportes)} de {total} registros")

        if reportes:
            import pandas as pd
            df = pd.DataFrame([
                {
                    'ID': r.get('id'),
                    'Indicativo': r.get('indicativo', ''),
                    'Operador': r.get('operador', ''),
                    'Estado': r.get('estado', ''),
                    'Ciudad': r.get('ciudad', ''),
                    'Zona': r.get('zona', ''),
                    'Señal': r.get('senal', ''),
                    'Plataforma': r.get('plataforma_nombre', ''),
                    'Fecha': r.get('fecha_reporte', ''),
                    'Capturado Por': r.get('qrz_captured_by', ''),
                    'Operando': r.get('qrz_station', ''),
                    'Observaciones': r.get('observaciones', '')
                } for r in reportes
            ])
            st.data_editor(
                df,
                hide_index=True,
                width='stretch',
                disabled=True,
                column_config={
                    'ID': st.column_config.NumberColumn("ID", width="small"),
                    'Indicativo': st.column_config.TextColumn("Indicativo", width="medium"),
                    'Operador': st.column_config.TextColumn("Operador", width="large"),
                    'Estado': st.column_config.TextColumn("Estado", width="medium"),
                    'Ciudad': st.column_config.TextColumn("Ciudad", width="medium"),
                    'Zona': st.column_config.TextColumn("Zona", width="small"),
                    'Señal': st.column_config.NumberColumn("Señal", width="small"),
                    'Plataforma': st.column_config.TextColumn("Plataforma", width="medium"),
                    'Fecha': st.column_config.TextColumn("Fecha", width="medium"),
                    'Observaciones': st.column_config.TextColumn("Observaciones", width="large"),
                }
            )

            # Exportación
            fecha_inicio_tag = fecha_inicio.strftime('%Y%m%d') if fecha_inicio else "inicio"
            fecha_fin_tag = fecha_fin.strftime('%Y%m%d') if fecha_fin else "fin"
            from io import BytesIO
            output = BytesIO()
            engine = None
            try:
                import importlib
                if importlib.util.find_spec("xlsxwriter"):
                    engine = "xlsxwriter"
            except Exception:
                engine = None
            try:
                with pd.ExcelWriter(output, engine=engine) as writer:
                    df.to_excel(writer, index=False, sheet_name='RS')
                    if engine == "xlsxwriter":
                        wb = writer.book
                        ws = writer.sheets['RS']
                        for i, col in enumerate(df.columns):
                            max_len = max(df[col].astype(str).apply(len).max(), len(col)) + 2
                            ws.set_column(i, i, max_len)
                data_bytes = output.getvalue()
                mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                fname = f"registros_rs_{fecha_inicio_tag}_{fecha_fin_tag}.xlsx"
            except Exception:
                data_bytes = df.to_csv(index=False).encode('utf-8-sig')
                mime = "text/csv"
                fname = f"registros_rs_{fecha_inicio_tag}_{fecha_fin_tag}.csv"

            st.download_button("📥 Exportar", data=data_bytes, file_name=fname, mime=mime, key="rs_export", width='stretch')
        else:
            st.info("No se encontraron registros con los filtros aplicados")
    except Exception as e:
        st.error(f"Error al cargar los registros RS: {str(e)}")

def show_editar_registros_rs():
    """Editar registros de Redes Sociales con selección múltiple y borrado"""
    st.subheader("✏️ Editar Registros (Redes Sociales)")

    if 'rs_editando_registro_id' not in st.session_state:
        st.session_state.rs_editando_registro_id = None
    if 'rs_eliminando_registro_id' not in st.session_state:
        st.session_state.rs_eliminando_registro_id = None

    if st.session_state.rs_editando_registro_id:
        _mostrar_formulario_edicion_registro_rs(st.session_state.rs_editando_registro_id)
        return

    col1, col2 = st.columns(2)
    with col1:
        fecha_inicio = st.date_input("Fecha inicio", key="rs_fecha_inicio_editar")
    with col2:
        fecha_fin = st.date_input("Fecha fin", key="rs_fecha_fin_editar")
    busqueda = st.text_input(
        "🔍 Buscar en todos los campos (insensible a acentos)",
        key="rs_busqueda_editar",
        placeholder="Indicativo, operador, ciudad, estado, zona, plataforma..."
    )

    if st.button("🔍 Buscar Registros", type="primary", key="rs_buscar_editar"):
        st.session_state.rs_registros_filtros_editar = {
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'busqueda': busqueda
        }
        st.rerun()

    try:
        filtros = getattr(st.session_state, 'rs_registros_filtros_editar', {'fecha_inicio': None, 'fecha_fin': None, 'busqueda': ''})
        fi = filtros['fecha_inicio'].strftime('%Y-%m-%d') if filtros['fecha_inicio'] else None
        ff = filtros['fecha_fin'].strftime('%Y-%m-%d') if filtros['fecha_fin'] else None
        reportes, _ = db.get_reportes_rs_filtrados(fecha_inicio=fi, fecha_fin=ff, busqueda=filtros['busqueda'])

        if 'rs_registros_seleccionados' not in st.session_state:
            st.session_state.rs_registros_seleccionados = set()
        if 'rs_eliminando_masivo' not in st.session_state:
            st.session_state.rs_eliminando_masivo = False
        if 'rs_show_delete_modal' not in st.session_state:
            st.session_state.rs_show_delete_modal = False

        if reportes:
            import pandas as pd
            seleccionados_actuales = st.session_state.rs_registros_seleccionados or set()

            col_acc1, col_acc2 = st.columns(2)
            with col_acc1:
                if st.button("✅ Seleccionar Todos", key="rs_select_all"):
                    st.session_state.rs_registros_seleccionados = {r['id'] for r in reportes if r.get('id') is not None}
                    st.session_state.rs_eliminando_masivo = False
                    st.rerun()
            with col_acc2:
                if st.button("🧹 Limpiar Selección", key="rs_clear_selection"):
                    st.session_state.rs_registros_seleccionados.clear()
                    st.session_state.rs_eliminando_masivo = False
                    st.rerun()

            df = pd.DataFrame([
                {
                    'ID': r.get('id'),
                    'Seleccionar': r.get('id') in seleccionados_actuales,
                    'Indicativo': r.get('indicativo', ''),
                    'Operador': r.get('operador', ''),
                    'Estado': r.get('estado', ''),
                    'Ciudad': r.get('ciudad', ''),
                    'Zona': r.get('zona', ''),
                    'Señal': r.get('senal', ''),
                    'Plataforma': r.get('plataforma_nombre', ''),
                    'Fecha': r.get('fecha_reporte', ''),
                    'Observaciones': (r.get('observaciones', '')[:50] + '...') if r.get('observaciones') and len(r.get('observaciones', '')) > 50 else r.get('observaciones', ''),
                    'Capturado Por': r.get('qrz_captured_by', ''),
                    'Operando': r.get('qrz_station', ''),
                } for r in reportes
            ])

            with st.form("tabla_editar_registros_rs"):
                edited_df = st.data_editor(
                    df,
                    hide_index=True,
                    width='stretch',
                    num_rows="fixed",
                    key=f"tabla_editar_registros_rs_{len(df)}",
                    column_config={
                        'Seleccionar': st.column_config.CheckboxColumn("Seleccionar"),
                        'ID': st.column_config.NumberColumn("ID", width="small"),
                        'Indicativo': st.column_config.TextColumn("Indicativo", width="medium"),
                        'Operador': st.column_config.TextColumn("Operador", width="large"),
                        'Estado': st.column_config.TextColumn("Estado", width="medium"),
                        'Ciudad': st.column_config.TextColumn("Ciudad", width="medium"),
                        'Zona': st.column_config.TextColumn("Zona", width="small"),
                        'Señal': st.column_config.NumberColumn("Señal", min_value=1, max_value=99, step=1, format="%d"),
                        'Plataforma': st.column_config.TextColumn("Plataforma", width="medium"),
                        'Fecha': st.column_config.TextColumn("Fecha", width="medium"),
                        'Observaciones': st.column_config.TextColumn("Observaciones", width="large"),
                    },
                    disabled=['ID', 'Indicativo', 'Operador', 'Estado', 'Ciudad', 'Zona', 'Señal', 'Plataforma', 'Fecha', 'Observaciones', 'Capturado Por', 'Operando']
                )

                c1, c2 = st.columns(2)
                editar_submit = c1.form_submit_button("✏️ Editar Seleccionado", type="primary")
                eliminar_submit = c2.form_submit_button("🗑️ Eliminar Seleccionados", type="secondary")

            selected_ids = set()
            if not edited_df.empty and "Seleccionar" in edited_df.columns:
                seleccionados_df = edited_df[edited_df["Seleccionar"]]
                for id_ in seleccionados_df['ID'].tolist():
                    if pd.notna(id_):
                        selected_ids.add(int(id_))

            if not eliminar_submit:
                st.session_state.rs_eliminando_masivo = st.session_state.rs_eliminando_masivo and bool(selected_ids)

            st.session_state.rs_registros_seleccionados = selected_ids
            if selected_ids:
                st.caption(f"✅ {len(selected_ids)} registros seleccionados")

            if editar_submit:
                if len(selected_ids) != 1:
                    st.warning("Selecciona exactamente un registro para editarlo.")
                else:
                    reporte_id = next(iter(selected_ids))
                    st.session_state.rs_registros_seleccionados = {reporte_id}
                    st.session_state.rs_editando_registro_id = reporte_id
                    st.rerun()

            if eliminar_submit:
                if not selected_ids:
                    st.warning("Selecciona al menos un registro para eliminar.")
                else:
                    st.session_state.rs_eliminando_masivo = True
                    st.session_state.rs_show_delete_modal = True
                    st.rerun()

            if st.session_state.rs_eliminando_masivo and st.session_state.rs_show_delete_modal:
                total = len(st.session_state.rs_registros_seleccionados)
                with st.container(border=True):
                    st.warning(f"¿Estás seguro de que quieres eliminar {total} registro{'s' if total != 1 else ''}? Esta acción no se puede deshacer.")
                    if not seleccionados_df.empty:
                        st.dataframe(
                            seleccionados_df.drop(columns=["Seleccionar"], errors="ignore"),
                            hide_index=True,
                            width='stretch',
                        )
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        if st.button("✅ Confirmar", type="primary", key="rs_confirm_bulk_delete"):
                            try:
                                eliminados = 0
                                for rid in st.session_state.rs_registros_seleccionados:
                                    if db.delete_reporte_rs(rid):
                                        eliminados += 1
                                if eliminados:
                                    st.success(f"✅ {eliminados} registro{'s' if eliminados != 1 else ''} eliminados correctamente")
                                    st.session_state.rs_registros_seleccionados.clear()
                                    st.session_state.rs_eliminando_masivo = False
                                    st.session_state.rs_show_delete_modal = False
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    st.error("No se pudo eliminar ningún registro")
                            except Exception as e:
                                st.error(f"Error al eliminar registros: {str(e)}")
                    with cc2:
                        if st.button("❌ Cancelar", key="rs_cancel_bulk_delete"):
                            st.session_state.rs_eliminando_masivo = False
                            st.session_state.rs_show_delete_modal = False
                            st.rerun()
        else:
            st.info("No se encontraron registros con los filtros aplicados")
    except Exception as e:
        st.error(f"Error al cargar los registros: {str(e)}")

def _mostrar_formulario_edicion_registro_rs(reporte_id: int):
    """Formulario de edición para un registro RS"""
    st.header("✏️ Editar Registro RS")
    try:
        reporte = db.get_reporte_rs_por_id(reporte_id)
        if not reporte:
            st.error("No se encontró el registro especificado")
            if st.button("Volver a la lista", key="rs_volver_lista_error"):
                del st.session_state.rs_editando_registro_id
                st.rerun()
            return

        st.info(f"Editando registro RS: {reporte.get('indicativo','')} - {reporte.get('operador') or 'Sin operador'}")

        # Opciones
        sistemas_options = _get_sistemas_options()
        if "" not in sistemas_options:
            sistemas_options = [""] + sistemas_options

        # Plataformas RS
        plataformas = db.get_rs_entries(active_only=True) or []
        plat_labels = [f"{p.get('plataforma','')} - {p.get('nombre','')}".strip(" - ") for p in plataformas]
        plat_ids = [p.get('id') for p in plataformas]
        try:
            idx_plat = plat_ids.index(reporte.get('plataforma_id')) if reporte.get('plataforma_id') in plat_ids else 0
        except Exception:
            idx_plat = 0

        from datetime import datetime
        fecha_val = None
        try:
            val = reporte.get('fecha_reporte') or ''
            fecha_val = datetime.strptime(val[:10], '%Y-%m-%d').date()
        except Exception:
            fecha_val = None

        with st.form(key=f'editar_registro_rs_form_{reporte_id}'):
            col1, col2 = st.columns(2)
            with col1:
                indicativo = st.text_input("Indicativo", value=reporte.get('indicativo',''))
                operador = st.text_input("Operador", value=reporte.get('operador') or '')
                estado = st.selectbox(
                    "Estado",
                    options=[""] + [e['estado'] for e in _get_estados_options() if e and 'estado' in e],
                    index=0 if not reporte.get('estado') else ([""] + [e['estado'] for e in _get_estados_options() if e and 'estado' in e]).index(reporte.get('estado')) if reporte.get('estado') in [e['estado'] for e in _get_estados_options() if e and 'estado' in e] else 0,
                )
                ciudad = st.text_input("Ciudad", value=reporte.get('ciudad') or '')
            with col2:
                zona = st.selectbox(
                    "Zona",
                    options=[""] + [z['zona'] for z in _get_zonas_options() if z and 'zona' in z],
                    index=0 if not reporte.get('zona') else ([""] + [z['zona'] for z in _get_zonas_options() if z and 'zona' in z]).index(reporte.get('zona')) if reporte.get('zona') in [z['zona'] for z in _get_zonas_options() if z and 'zona' in z] else 0,
                )
                senal = st.number_input("Señal", min_value=1, max_value=99, value=int(reporte.get('senal') or 59))
                fecha = st.date_input("Fecha del Reporte", value=fecha_val)

            plataforma_sel = st.selectbox("Plataforma", options=plat_labels or [""], index=idx_plat)
            observaciones = st.text_area("Observaciones", value=reporte.get('observaciones') or '')

            c1, c2, c3 = st.columns([1,1,2])
            with c1:
                if st.form_submit_button("💾 Guardar Cambios", type="primary"):
                    if not indicativo:
                        st.error("El indicativo es obligatorio")
                    else:
                        try:
                            plat_idx = plat_labels.index(plataforma_sel) if plataforma_sel in plat_labels else 0
                            plat_id = plat_ids[plat_idx] if plat_ids else None
                            plat_name = plataforma_sel
                            datos = {
                                'indicativo': indicativo.upper(),
                                'operador': operador,
                                'estado': estado,
                                'ciudad': ciudad,
                                'zona': zona,
                                'senal': senal,
                                'observaciones': observaciones,
                                'plataforma_id': plat_id,
                                'plataforma_nombre': plat_name,
                                'fecha_reporte': fecha.strftime('%Y-%m-%d') if fecha else None,
                            }
                            if db.update_reporte_rs(reporte_id, datos):
                                st.success("¡Los cambios se guardaron correctamente!")
                                time.sleep(2)
                                del st.session_state.rs_editando_registro_id
                                st.rerun()
                            else:
                                st.error("No se pudieron guardar los cambios. Intente nuevamente.")
                        except Exception as e:
                            st.error(f"Error al guardar los cambios: {str(e)}")
            with c2:
                if st.form_submit_button("❌ Cancelar"):
                    del st.session_state.rs_editando_registro_id
                    st.rerun()
            with c3:
                if st.form_submit_button("🗑️ Eliminar Registro", type="secondary"):
                    st.session_state.rs_eliminando_registro_id = reporte_id
                    st.session_state.rs_volver_a_editar = True
                    st.rerun()

    except Exception as e:
        st.error(f"Error al cargar el formulario de edición: {str(e)}")
        if st.button("Volver a la lista", key="rs_volver_lista_error2"):
            if 'rs_editando_registro_id' in st.session_state:
                del st.session_state.rs_editando_registro_id
            st.rerun()

def show_lista_interacciones_rs():
    """Lista interacciones (tabla estadisticas_rs) con filtros y exportación"""
    st.subheader("📋 Lista de Interacciones (Redes Sociales)")

    if 'rs_inter_filtros' not in st.session_state:
        st.session_state.rs_inter_filtros = {'fecha_inicio': None, 'fecha_fin': None, 'busqueda': ''}

    col1, col2 = st.columns(2)
    with col1:
        fecha_inicio = st.date_input("Fecha inicio", value=st.session_state.rs_inter_filtros['fecha_inicio'], key="rs_inter_fecha_inicio")
    with col2:
        fecha_fin = st.date_input("Fecha fin", value=st.session_state.rs_inter_filtros['fecha_fin'], key="rs_inter_fecha_fin")
    busqueda = st.text_input("🔍 Buscar", value=st.session_state.rs_inter_filtros['busqueda'], key="rs_inter_busqueda", placeholder="Plataforma, usuario, observaciones, valores...")

    b1, b2, _ = st.columns([2,2,6])
    if b1.button("🔍 Buscar Interacciones", type="primary", key="rs_inter_buscar_btn"):
        st.session_state.rs_inter_filtros = {'fecha_inicio': fecha_inicio, 'fecha_fin': fecha_fin, 'busqueda': busqueda}
        st.rerun()
    if b2.button("🧹 Limpiar Filtros", key="rs_inter_limpiar_btn"):
        st.session_state.rs_inter_filtros = {'fecha_inicio': None, 'fecha_fin': None, 'busqueda': ''}
        st.rerun()

    fi = fecha_inicio.strftime('%Y-%m-%d') if fecha_inicio else None
    ff = fecha_fin.strftime('%Y-%m-%d') if fecha_fin else None
    interacciones, total = db.get_estadisticas_rs_filtradas(fi, ff, busqueda)
    st.caption(f"Mostrando {len(interacciones)} de {total} interacciones")

    if interacciones:
        import pandas as pd
        df = pd.DataFrame([
            {
                'ID': it.get('id'),
                'Plataforma ID': it.get('plataforma_id'),
                'Plataforma': it.get('plataforma_nombre', ''),
                'Me gusta': it.get('me_gusta', 0),
                'Comentarios': it.get('comentarios', 0),
                'Compartidos': it.get('compartidos', 0),
                'Reproducciones': it.get('reproducciones', 0),
                'Alcance': it.get('alcance', 0),
                'Interacciones': it.get('interacciones', 0),
                'Fecha': it.get('fecha_reporte', ''),
                'Capturado Por': it.get('captured_by', ''),
                'Observaciones': it.get('observaciones', ''),
                'Metadata': it.get('metadata_json', ''),
            } for it in interacciones
        ])
        st.data_editor(
            df,
            hide_index=True,
            width='stretch',
            disabled=True,
            column_config={
                'ID': st.column_config.NumberColumn("ID", width="small"),
                'Plataforma ID': st.column_config.NumberColumn("Plataforma ID", width="small"),
                'Plataforma': st.column_config.TextColumn("Plataforma", width="medium"),
                'Me gusta': st.column_config.NumberColumn("Me gusta", width="small"),
                'Comentarios': st.column_config.NumberColumn("Comentarios", width="small"),
                'Compartidos': st.column_config.NumberColumn("Compartidos", width="small"),
                'Reproducciones': st.column_config.NumberColumn("Reproducciones", width="small"),
                'Alcance': st.column_config.NumberColumn("Alcance", width="small"),
                'Interacciones': st.column_config.NumberColumn("Interacciones", width="small"),
                'Fecha': st.column_config.TextColumn("Fecha", width="medium"),
                'Capturado Por': st.column_config.TextColumn("Capturado Por", width="medium"),
                'Observaciones': st.column_config.TextColumn("Observaciones", width="large"),
                'Metadata': st.column_config.TextColumn("Metadata", width="large"),
            }
        )

        # Exportación
        from io import BytesIO
        output = BytesIO()
        try:
            import pandas as pd
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name='Interacciones')
                wb = writer.book
                ws = writer.sheets['Interacciones']
                for i, col in enumerate(df.columns):
                    max_len = max(df[col].astype(str).apply(len).max(), len(col)) + 2
                    ws.set_column(i, i, max_len)
            data_bytes = output.getvalue()
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            fname = "interacciones_rs.xlsx"
        except Exception:
            data_bytes = df.to_csv(index=False).encode('utf-8-sig')
            mime = "text/csv"
            fname = "interacciones_rs.csv"
        st.download_button("📥 Exportar", data=data_bytes, file_name=fname, mime=mime, key="rs_inter_export", width='stretch')
    else:
        st.info("No se encontraron interacciones con los filtros aplicados")

def show_editar_interacciones_rs():
    """Editar interacciones (estadisticas_rs) con selección múltiple y borrado"""
    st.subheader("✏️ Editar Interacciones (Redes Sociales)")

    if 'rs_inter_editando_id' not in st.session_state:
        st.session_state.rs_inter_editando_id = None
    if 'rs_inter_eliminando_masivo' not in st.session_state:
        st.session_state.rs_inter_eliminando_masivo = False
    if 'rs_inter_show_delete_modal' not in st.session_state:
        st.session_state.rs_inter_show_delete_modal = False

    if st.session_state.rs_inter_editando_id:
        _mostrar_formulario_edicion_interaccion_rs(st.session_state.rs_inter_editando_id)
        return

    col1, col2 = st.columns(2)
    with col1:
        fecha_inicio = st.date_input("Fecha inicio", key="rs_inter_fecha_inicio_editar")
    with col2:
        fecha_fin = st.date_input("Fecha fin", key="rs_inter_fecha_fin_editar")
    busqueda = st.text_input("🔍 Buscar", key="rs_inter_buscar_editar")

    if st.button("🔍 Buscar Interacciones", type="primary", key="rs_inter_buscar_btn_editar"):
        st.session_state.rs_inter_filtros_editar = {'fecha_inicio': fecha_inicio, 'fecha_fin': fecha_fin, 'busqueda': busqueda}
        st.rerun()

    filtros = getattr(st.session_state, 'rs_inter_filtros_editar', {'fecha_inicio': None, 'fecha_fin': None, 'busqueda': ''})
    fi = filtros['fecha_inicio'].strftime('%Y-%m-%d') if filtros['fecha_inicio'] else None
    ff = filtros['fecha_fin'].strftime('%Y-%m-%d') if filtros['fecha_fin'] else None
    filas, _ = db.get_estadisticas_rs_filtradas(fi, ff, filtros['busqueda'])

    if 'rs_inter_seleccionados' not in st.session_state:
        st.session_state.rs_inter_seleccionados = set()

    if filas:
        import pandas as pd
        seleccionados_actuales = st.session_state.rs_inter_seleccionados or set()

        col_acc1, col_acc2 = st.columns(2)
        with col_acc1:
            if st.button("✅ Seleccionar Todos", key="rs_inter_select_all"):
                st.session_state.rs_inter_seleccionados = {f['id'] for f in filas if f.get('id') is not None}
                st.session_state.rs_inter_eliminando_masivo = False
                st.rerun()
        with col_acc2:
            if st.button("🧹 Limpiar Selección", key="rs_inter_clear_selection"):
                st.session_state.rs_inter_seleccionados.clear()
                st.session_state.rs_inter_eliminando_masivo = False
                st.rerun()

        df = pd.DataFrame([
            {
                'ID': f.get('id'),
                'Seleccionar': f.get('id') in seleccionados_actuales,
                'Plataforma': f.get('plataforma_nombre', ''),
                'Fecha': f.get('fecha_reporte', ''),
                'Me gusta': f.get('me_gusta', 0),
                'Comentarios': f.get('comentarios', 0),
                'Compartidos': f.get('compartidos', 0),
                'Reproducciones': f.get('reproducciones', 0),
                'Alcance': f.get('alcance', 0),
                'Interacciones': f.get('interacciones', 0),
                'Capturado Por': f.get('captured_by', ''),
                'Observaciones': (f.get('observaciones', '')[:50] + '...') if f.get('observaciones') and len(f.get('observaciones', '')) > 50 else f.get('observaciones', ''),
            } for f in filas
        ])

        with st.form("tabla_editar_interacciones_rs"):
            edited_df = st.data_editor(
                df,
                hide_index=True,
                width='stretch',
                num_rows="fixed",
                key=f"tabla_editar_interacciones_rs_{len(df)}",
                column_config={
                    'Seleccionar': st.column_config.CheckboxColumn("Seleccionar"),
                    'ID': st.column_config.NumberColumn("ID", width="small"),
                    'Plataforma': st.column_config.TextColumn("Plataforma", width="medium"),
                    'Fecha': st.column_config.TextColumn("Fecha", width="medium"),
                    'Me gusta': st.column_config.NumberColumn("Me gusta", width="small"),
                    'Comentarios': st.column_config.NumberColumn("Comentarios", width="small"),
                    'Compartidos': st.column_config.NumberColumn("Compartidos", width="small"),
                    'Reproducciones': st.column_config.NumberColumn("Reproducciones", width="small"),
                    'Alcance': st.column_config.NumberColumn("Alcance", width="small"),
                    'Interacciones': st.column_config.NumberColumn("Interacciones", width="small"),
                    'Observaciones': st.column_config.TextColumn("Observaciones", width="large"),
                },
                disabled=['ID', 'Plataforma', 'Fecha', 'Me gusta', 'Comentarios', 'Compartidos', 'Reproducciones', 'Alcance', 'Interacciones', 'Observaciones', 'Capturado Por']
            )

            c1, c2 = st.columns(2)
            editar_submit = c1.form_submit_button("✏️ Editar Seleccionado", type="primary")
            eliminar_submit = c2.form_submit_button("🗑️ Eliminar Seleccionados", type="secondary")

        selected_ids = set()
        if not edited_df.empty and "Seleccionar" in edited_df.columns:
            seleccionados_df = edited_df[edited_df["Seleccionar"]]
            for id_ in seleccionados_df['ID'].tolist():
                if pd.notna(id_):
                    selected_ids.add(int(id_))

        if editar_submit:
            if len(selected_ids) != 1:
                st.warning("Selecciona exactamente un registro para editarlo.")
            else:
                st.session_state.rs_inter_editando_id = next(iter(selected_ids))
                st.rerun()

        if eliminar_submit:
            if not selected_ids:
                st.warning("Selecciona al menos un registro para eliminar.")
            else:
                st.session_state.rs_inter_seleccionados = selected_ids
                st.session_state.rs_inter_eliminando_masivo = True
                st.session_state.rs_inter_show_delete_modal = True
                st.rerun()

        if st.session_state.rs_inter_eliminando_masivo and st.session_state.rs_inter_show_delete_modal:
            total = len(st.session_state.rs_inter_seleccionados)
            with st.container(border=True):
                st.warning(f"¿Eliminar {total} interacción(es)? Esta acción no se puede deshacer.")
                if not seleccionados_df.empty:
                    st.dataframe(
                        seleccionados_df.drop(columns=["Seleccionar"], errors="ignore"),
                        hide_index=True,
                        width='stretch',
                    )
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("✅ Confirmar", type="primary", key="rs_inter_confirm_bulk_delete"):
                        try:
                            eliminados = 0
                            for rid in st.session_state.rs_inter_seleccionados:
                                if db.delete_estadistica_rs(rid):
                                    eliminados += 1
                            if eliminados:
                                st.success(f"✅ {eliminados} interacción(es) eliminadas")
                                st.session_state.rs_inter_seleccionados.clear()
                                st.session_state.rs_inter_eliminando_masivo = False
                                st.session_state.rs_inter_show_delete_modal = False
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error("No se pudo eliminar ningún registro")
                        except Exception as e:
                            st.error(f"Error al eliminar: {str(e)}")
                with cc2:
                    if st.button("❌ Cancelar", key="rs_inter_cancel_bulk_delete"):
                        st.session_state.rs_inter_eliminando_masivo = False
                        st.session_state.rs_inter_show_delete_modal = False
                        st.rerun()
    else:
        st.info("No se encontraron interacciones con los filtros aplicados")

def _mostrar_formulario_edicion_interaccion_rs(estadistica_id: int):
    """Formulario para editar una interacción (estadisticas_rs)"""
    st.header("✏️ Editar Interacción RS")
    try:
        fila = db.get_estadistica_rs_por_id(estadistica_id)
        if not fila:
            st.error("No se encontró la interacción especificada")
            if st.button("Volver a la lista", key="rs_inter_volver_lista_error"):
                st.session_state.rs_inter_editando_id = None
                st.rerun()
            return

        plataformas = db.get_rs_entries(active_only=True) or []
        plat_labels = [f"{p.get('plataforma','')} - {p.get('nombre','')}".strip(" - ") for p in plataformas]
        plat_ids = [p.get('id') for p in plataformas]
        try:
            idx_plat = plat_ids.index(fila.get('plataforma_id')) if fila.get('plataforma_id') in plat_ids else 0
        except Exception:
            idx_plat = 0

        from datetime import datetime
        fecha_val = None
        try:
            val = fila.get('fecha_reporte') or ''
            fecha_val = datetime.strptime(val[:10], '%Y-%m-%d').date()
        except Exception:
            fecha_val = None

        with st.form(key=f'editar_interaccion_rs_form_{estadistica_id}'):
            col1, col2 = st.columns(2)
            with col1:
                plataforma_sel = st.selectbox("Plataforma", options=plat_labels or [""], index=idx_plat)
                me_gusta = st.number_input("Me gusta", min_value=0, value=int(fila.get('me_gusta') or 0))
                comentarios = st.number_input("Comentarios", min_value=0, value=int(fila.get('comentarios') or 0))
                compartidos = st.number_input("Compartidos", min_value=0, value=int(fila.get('compartidos') or 0))
            with col2:
                reproducciones = st.number_input("Reproducciones", min_value=0, value=int(fila.get('reproducciones') or 0))
                alcance = st.number_input("Alcance", min_value=0, value=int(fila.get('alcance') or 0))
                fecha = st.date_input("Fecha del Reporte", value=fecha_val)

            captured_by = st.text_input("Capturado Por", value=fila.get('captured_by') or '')
            observaciones = st.text_area("Observaciones", value=fila.get('observaciones') or '')
            metadata = st.text_area("Metadata (JSON)", value=fila.get('metadata_json') or '')

            c1, c2, c3 = st.columns([1,1,2])
            with c1:
                if st.form_submit_button("💾 Guardar Cambios", type="primary"):
                    try:
                        plat_idx = plat_labels.index(plataforma_sel) if plataforma_sel in plat_labels else 0
                        plat_id = plat_ids[plat_idx] if plat_ids else None
                        interacciones = int(me_gusta) + int(comentarios) + int(compartidos)
                        datos = {
                            'plataforma_id': plat_id,
                            'plataforma_nombre': plataforma_sel,
                            'me_gusta': int(me_gusta),
                            'comentarios': int(comentarios),
                            'compartidos': int(compartidos),
                            'reproducciones': int(reproducciones),
                            'alcance': int(alcance),
                            'interacciones': int(interacciones),
                            'fecha_reporte': fecha.strftime('%Y-%m-%d') if fecha else None,
                            'captured_by': captured_by,
                            'observaciones': observaciones,
                            'metadata_json': metadata,
                        }
                        if db.update_estadistica_rs(estadistica_id, datos):
                            st.success("¡Los cambios se guardaron correctamente!")
                            time.sleep(2)
                            st.session_state.rs_inter_editando_id = None
                            st.rerun()
                        else:
                            st.error("No se pudieron guardar los cambios. Intente nuevamente.")
                    except Exception as e:
                        st.error(f"Error al guardar: {str(e)}")
            with c2:
                if st.form_submit_button("❌ Cancelar"):
                    st.session_state.rs_inter_editando_id = None
                    st.rerun()
            with c3:
                if st.form_submit_button("🗑️ Eliminar Interacción", type="secondary"):
                    # Usar flujo de eliminación masiva para confirmar, con un solo elemento
                    st.session_state.rs_inter_seleccionados = {estadistica_id}
                    st.session_state.rs_inter_eliminando_masivo = True
                    st.session_state.rs_inter_show_delete_modal = True
                    st.rerun()
    except Exception as e:
        st.error(f"Error al cargar el formulario: {str(e)}")

@st.cache_data(ttl=300)  # Cache por 5 minutos
def _get_estados_options():
    """Obtiene las opciones de Estado con caché"""
    try:
        return db.get_estados(incluir_extranjero=True)
    except Exception as e:
        st.error(f"Error al cargar estados: {str(e)}")
        return []

@st.cache_data(ttl=300)
def _get_sistemas_options():
    """Obtiene las opciones de sistemas disponibles"""
    try:
        sistemas = db.get_sistemas()

        if isinstance(sistemas, dict):
            opciones = sorted([str(k) for k in sistemas.keys() if k])
        elif isinstance(sistemas, list):
            opciones = sorted({str(item.get('codigo')) for item in sistemas if item and item.get('codigo')})
        else:
            opciones = []

        return opciones
    except Exception as e:
        st.error(f"Error al cargar sistemas: {str(e)}")
        return []

@st.cache_data(ttl=300)  # Cache por 5 minutos
def _get_zonas_options():
    """Obtiene las opciones de Zona con caché"""
    try:
        return db.get_zonas(incluir_inactivas=False)
    except Exception as e:
        st.error(f"Error al cargar zonas: {str(e)}")
        return []
    """
    Obtiene los datos necesarios para un reporte basado en el indicativo y sistema proporcionados.
    
    Args:
        indicativo (str): El indicativo del radioexperimentador
        sistema (str): El sistema de comunicación utilizado
        
    Returns:
        dict: Un diccionario con los datos del reporte
    """
    # Obtener datos del radioexperimentador si existe
    radioexperimentador = db.get_radioexperimentador_por_indicativo(indicativo)
    
    if radioexperimentador:
        # Si existe en la base de datos, copiar todos los campos relevantes
        datos = {
            'indicativo': radioexperimentador.get('indicativo', indicativo),
            'nombre_operador': radioexperimentador.get('nombre_completo', ''),  # ← CORREGIDO: usar 'nombre_completo'
            'apellido_paterno': radioexperimentador.get('apellido_paterno', ''),
            'apellido_materno': radioexperimentador.get('apellido_materno', ''),
            'estado': radioexperimentador.get('estado', ''),           # ← Correcto
            'ciudad': radioexperimentador.get('municipio', ''),        # ← CORREGIDO: usar 'municipio'
            'colonia': radioexperimentador.get('colonia', ''),
            'codigo_postal': radioexperimentador.get('codigo_postal', ''),
            'telefono': radioexperimentador.get('telefono', ''),
            'email': radioexperimentador.get('email', ''),
            'zona': radioexperimentador.get('zona', ''),               # ← Usar zona de BD o calcular
            'sistema': sistema,  # Usar el sistema proporcionado
            'senal': '59',  # Valor por defecto para la señal
            'activo': radioexperimentador.get('activo', 1)  # Mantener el estado activo/inactivo
        }

        # Si no hay zona en BD, calcularla automáticamente
        if not datos['zona']:
            if len(indicativo) >= 3:
                prefijo = indicativo[:3]
                if prefijo.startswith('XE') and indicativo[2] in ['1', '2', '3']:
                    datos['zona'] = f"XE{indicativo[2]}"
    else:
        # Si no existe, crear un registro básico
        datos = {
            'indicativo': indicativo,
            'nombre_operador': '',
            'estado': '',
            'ciudad': '',
            'zona': '',
            'sistema': sistema,
            'senal': '59'  # Valor por defecto para la señal
        }
        
        # Intentar determinar la zona basada en el prefijo
        if len(indicativo) >= 3:
            prefijo = indicativo[:3]
            if prefijo.startswith('XE') and indicativo[2] in ['1', '2', '3']:
                datos['zona'] = f"XE{indicativo[2]}"
    
    return datos

def main():
    # Inicializar variables de sesión si no existen
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "home"
    
    # Verificar autenticación
    if 'user' not in st.session_state:
        # Modo público con mapa y botón de Login (o login completo si se solicita)
        st.set_page_config(
            page_title="QMS Público - FMRE",
            page_icon="📻",
            layout="wide"
        )
        if st.session_state.get('force_login'):
            auth.show_login()
        else:
            show_public_home()
    else:
        # Configurar página con barra lateral solo cuando está autenticado
        st.set_page_config(
            page_title="Sistema de Gestión de QSOs",
            page_icon="📻",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        # Mostrar la barra lateral solo cuando está autenticado
        show_sidebar()
        
        # Navegación
        current_page = st.session_state.get('current_page', 'home')
        
        if current_page == 'home':
            show_home()
        elif current_page == 'gestion':
            show_gestion()
        elif current_page == 'toma_reportes':
            show_toma_reportes()
        elif current_page == 'registros':
            show_registros()
        elif current_page == 'reportes':
            show_reportes()
        elif current_page == 'reports':
            show_reports()
        elif current_page == 'settings':
            show_settings()
        elif current_page == 'send_reports':
            try:
                from enviar_reportes import show_enviar_reportes
                show_enviar_reportes()
            except Exception as e:
                st.error(f"❌ Error al cargar la página de envío de reportes: {e}")
        # Mantener compatibilidad con la navegación antigua
        elif current_page == 'users':
            st.session_state.current_page = 'gestion'
            st.rerun()

def show_gestion_zonas():
    """Muestra la gestión de zonas con pestañas para listar y crear zonas"""
    # Mostrar pestañas
    tab_lista, tab_crear = st.tabs(["📋 Lista de Zonas", "➕ Crear Zona"])
    
    with tab_lista:
        _show_lista_zonas()
    
    with tab_crear:
        _show_crear_zona()

def _show_lista_zonas():
    """Muestra la lista de zonas con opciones de búsqueda y filtrado"""
    st.subheader("📍 Lista de Zonas")
    
    # Barra de búsqueda y filtros
    col1, col2 = st.columns([3, 1])
    with col1:
        busqueda = st.text_input("Buscar zona", "", placeholder="Buscar por código o nombre...")
    with col2:
        mostrar_inactivas = st.checkbox("Mostrar inactivas", value=False)
    
    # Obtener zonas con filtros
    zonas = db.get_zonas(incluir_inactivas=mostrar_inactivas)
        
    if busqueda:
        busqueda = busqueda.lower()
        zonas = [z for z in zonas if 
                busqueda in z['zona'].lower() or 
                busqueda in z['nombre'].lower()]
    
    if zonas:
        # Mostrar estadísticas rápidas
        activas = sum(1 for z in zonas if z.get('activo', 1) == 1)
        inactivas = len(zonas) - activas
        st.caption(f"Mostrando {len(zonas)} zonas ({activas} activas, {inactivas} inactivas)")
        
        # Mostrar zonas en una tabla
        for zona in zonas:
            # Determinar si estamos editando esta zona
            is_editing = st.session_state.get(f'editing_zona_{zona["zona"]}', False)
            
            with st.expander(
                f"{'✅' if zona.get('activo', 1) == 1 else '⏸️'} {zona['zona']} - {zona['nombre']}",
                expanded=is_editing  # Expandir si está en modo edición
            ):
                if not is_editing:
                    # Vista normal de la zona
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        # Mostrar estado
                        estado = "Activa" if zona.get('activo', 1) == 1 else "Inactiva"
                        st.markdown(f"**Zona:** {zona['zona']}")
                        st.markdown(f"**Estado:** {estado}")
                    
                    with col2:
                        # Botones de acción
                        col_btn1, col_btn2 = st.columns(2)
                        
                        with col_btn1:
                            if st.button("✏️ Editar", key=f"edit_{zona['zona']}", width='stretch'):
                                st.session_state[f'editing_zona_{zona["zona"]}'] = True
                                st.rerun()
                        
                        with col_btn2:
                            estado_btn = "❌ Desactivar" if zona.get('activo', 1) == 1 else "✅ Activar"
                            if st.button(estado_btn, key=f"toggle_{zona['zona']}", width='stretch'):
                                nuevo_estado = 0 if zona.get('activo', 1) == 1 else 1
                                db.update_zona(zona['zona'], activo=nuevo_estado)
                                st.success(f"Zona {'activada' if nuevo_estado == 1 else 'desactivada'} correctamente")
                                time.sleep(2)
                                st.rerun()
                        
                        # Botón de eliminar con confirmación
                        if st.button("🗑️ Eliminar", key=f"delete_{zona['zona']}", 
                                   type="primary", width='stretch',
                                   help="Eliminar permanentemente esta zona"):
                            # Mostrar diálogo de confirmación
                            if st.session_state.get(f'confirm_delete_{zona["zona"]}') != True:
                                st.session_state[f'confirm_delete_{zona["zona"]}'] = True
                                st.rerun()
                            else:
                                if db.delete_zona(zona['zona']):
                                    st.success("Zona eliminada correctamente")
                                    time.sleep(2)
                                    # Limpiar estado de confirmación
                                    if f'confirm_delete_{zona["zona"]}' in st.session_state:
                                        del st.session_state[f'confirm_delete_{zona["zona"]}']
                                    st.rerun()
                                else:
                                    st.error("Error al eliminar la zona")
                                    if f'confirm_delete_{zona["zona"]}' in st.session_state:
                                        del st.session_state[f'confirm_delete_{zona["zona"]}']
                        
                        # Mostrar mensaje de confirmación si es necesario
                        if st.session_state.get(f'confirm_delete_{zona["zona"]}') == True:
                            st.warning("¿Estás seguro de que quieres eliminar esta zona? Esta acción no se puede deshacer.")
                            if st.button("✅ Confirmar eliminación", key=f"confirm_del_{zona['zona']}", 
                                       type="primary", width='stretch'):
                                if db.delete_zona(zona['zona']):
                                    st.success("Zona eliminada correctamente")
                                    time.sleep(2)
                                    # Limpiar estado de confirmación
                                    if f'confirm_delete_{zona["zona"]}' in st.session_state:
                                        del st.session_state[f'confirm_delete_{zona["zona"]}']
                                    st.rerun()
                                else:
                                    st.error("Error al eliminar la zona")
                            
                            if st.button("❌ Cancelar", key=f"cancel_del_{zona['zona']}", 
                                       width='stretch'):
                                del st.session_state[f'confirm_delete_{zona["zona"]}']
                                st.rerun()
                else:
                    # Mostrar formulario de edición
                    with st.form(f"edit_zona_{zona['zona']}"):
                        # Obtener datos actuales de la zona
                        zona_data = db.get_zona(zona['zona'])
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            zona_valor = st.text_input("Zona", value=zona_data['zona'])
                            nombre = st.text_input("Nombre de la zona", value=zona_data['nombre'])
                        
                        with col2:
                            st.write("")
                            st.write("")
                            activo = st.checkbox("Activa", value=bool(zona_data.get('activo', 1)))
                        
                        # Botones del formulario
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            if st.form_submit_button("💾 Guardar cambios", width='stretch'):
                                if not zona_valor or not nombre:
                                    st.error("La zona y el nombre son campos obligatorios")
                                else:
                                    try:
                                        # Actualizar la zona
                                        if db.update_zona(
                                            zona_original=zona['zona'],
                                            zona=zona_valor,
                                            nombre=nombre,
                                            activo=1 if activo else 0
                                        ):
                                            st.success("✅ Zona actualizada correctamente")
                                            time.sleep(2)
                                            # Limpiar estado de edición
                                            del st.session_state[f'editing_zona_{zona["zona"]}']
                                            st.rerun()
                                        else:
                                            st.error("❌ Error al actualizar la zona. Verifica que la zona no esté duplicada.")
                                    except Exception as e:
                                        st.error(f"Error al actualizar la zona: {str(e)}")
                        
                        with col2:
                            if st.form_submit_button("❌ Cancelar", type="secondary", width='stretch'):
                                # Cancelar edición
                                del st.session_state[f'editing_zona_{zona["zona"]}']
                                st.rerun()
        
        if not zonas:
            st.info("No se encontraron zonas que coincidan con los criterios de búsqueda")
    else:
        st.info("No hay zonas registradas")

def show_gestion_radioexperimentadores():
    """Muestra la gestión de radioexperimentadores con pestañas"""
    tab1, tab2, tab3 = st.tabs([
        "📋 Lista de Radioexperimentadores",
        "➕ Agregar Radioexperimentador",
        "📤 Importar desde Excel"
    ])
    
    with tab1:
        _show_lista_radioexperimentadores()
    
    with tab2:
        _show_crear_radioexperimentador()
    
    with tab3:
        _show_importar_radioexperimentadores()

@st.cache_data(ttl=300)  # Cache por 5 minutos
def _get_radioexperimentadores(incluir_inactivos=False):
    """Obtiene la lista de radioexperimentadores con caché"""
    try:
        return db.get_radioexperimentadores(incluir_inactivos=incluir_inactivos)
    except Exception as e:
        st.error(f"Error al cargar los radioexperimentadores: {str(e)}")
        return []

def _show_lista_radioexperimentadores():
    """Muestra la lista de radioexperimentadores con opciones de búsqueda y acciones"""
    st.header("📋 Lista de Radioexperimentadores")
    
    # Inicializar variables de sesión si no existen
    if 'editando_radio_id' not in st.session_state:
        st.session_state.editando_radio_id = None
    if 'eliminando_radio_id' not in st.session_state:
        st.session_state.eliminando_radio_id = None
    
    # Si estamos en modo edición, mostrar el formulario de edición
    if st.session_state.editando_radio_id:
        _mostrar_formulario_edicion(st.session_state.editando_radio_id)
        return
    
    # Barra de búsqueda y filtros
    col1, col2 = st.columns([3, 1])
    
    with col1:
        busqueda = st.text_input("Buscar por indicativo, nombre o municipio:", "")
    
    with col2:
        incluir_inactivos = st.checkbox("Mostrar inactivos", False, key="mostrar_inactivos_radio")
    
    # Obtener y mostrar la lista de radioexperimentadores
    try:
        radioexperimentadores = []
        
        if busqueda:
            # Primero intentar buscar por indicativo exacto
            busqueda_upper = busqueda.upper()
            radio = db.get_radioexperimentador_por_indicativo(busqueda_upper)
            
            if radio:
                # Si encontramos por indicativo exacto, mostramos solo ese
                radioexperimentadores = [radio]
            else:
                radioexperimentadores = db.get_radioexperimentadores(
                    incluir_inactivos=incluir_inactivos
                )
                
                # Filtrar localmente para mejor control de la búsqueda
                busqueda_terms = busqueda_upper.split()
                radioexperimentadores = [
                    r for r in radioexperimentadores
                    if (busqueda_upper in r['indicativo'].upper() or
                        all(term in r['nombre_completo'].upper() for term in busqueda_terms) or
                        busqueda_upper in (r['municipio'] or '').upper() or
                        busqueda_upper in (r['estado'] or '').upper())
                ]
        else:
            # Si no hay búsqueda, obtener todos los activos (o inactivos si está marcado)
            radioexperimentadores = _get_radioexperimentadores(
                incluir_inactivos=incluir_inactivos
            )
        
        # Mostrar contador de resultados
        total_aficionados = len(radioexperimentadores)
        st.subheader(f"📊 {total_aficionados} aficionado{'s' if total_aficionados != 1 else ''} encontrado{'s' if total_aficionados != 1 else ''}")
        
        if radioexperimentadores:
            # Mostrar la lista en un formato de tabla mejorado
            for radio in radioexperimentadores:
                with st.expander(f"{radio['indicativo']} - {radio['nombre_completo']}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Municipio:** {radio['municipio'] or 'No especificado'}")
                        st.write(f"**Estado:** {radio['estado'] or 'No especificado'}")
                        st.write(f"**País:** {radio['pais'] or 'No especificado'}")
                        
                    with col2:
                        st.write(f"**Tipo de licencia:** {radio['tipo_licencia'] or 'No especificado'}")
                        st.write(f"**Estatus:** {radio['estatus'] or 'No especificado'}")
                        st.write(f"**Activo:** {'Sí' if radio.get('activo', 1) == 1 else 'No'}")
                    
                    # Mostrar botones de acción
                    col_btn1, col_btn2, col_btn3 = st.columns(3)
                    
                    with col_btn1:
                        if st.button(f"✏️ Editar", key=f"editar_{radio['id']}"):
                            st.session_state.editando_radio_id = radio['id']
                            st.rerun()
                    
                    with col_btn2:
                        if radio.get('activo', 1) == 1:
                            if st.button(f"⏸️ Desactivar", key=f"desactivar_{radio['id']}"):
                                try:
                                    if db.delete_radioexperimentador(radio['id']):
                                        st.success(f"Radioexperimentador {radio['indicativo']} desactivado correctamente")
                                        time.sleep(2)
                                        st.rerun()
                                    else:
                                        st.error("No se pudo desactivar el radioexperimentador")
                                except Exception as e:
                                    st.error(f"Error al desactivar: {str(e)}")
                        else:
                            if st.button(f"▶️ Activar", key=f"activar_{radio['id']}"):
                                try:
                                    if db.activar_radioexperimentador(radio['id']):
                                        st.success(f"Radioexperimentador {radio['indicativo']} activado correctamente")
                                        time.sleep(2)
                                        st.rerun()
                                    else:
                                        st.error("No se pudo activar el radioexperimentador")
                                except Exception as e:
                                    st.error(f"Error al activar: {str(e)}")
                    
                    with col_btn3:
                        if st.button(f"🗑️ Eliminar", key=f"eliminar_{radio['id']}"):
                            st.session_state.eliminando_radio_id = radio['id']
                            st.rerun()
                    
                    # Mostrar confirmación de eliminación si corresponde
                    if st.session_state.get('eliminando_radio_id') == radio['id']:
                        st.warning("¿Estás seguro de que deseas eliminar permanentemente este registro? Esta acción no se puede deshacer.")
                        
                        col_conf1, col_conf2 = st.columns(2)
                        
                        with col_conf1:
                            if st.button("✅ Confirmar eliminación", type="primary", key=f"confirmar_eliminar_{radio['id']}"):
                                try:
                                    if db.delete_radioexperimentador(radio['id'], force_delete=True):
                                        st.success(f"Radioexperimentador {radio['indicativo']} eliminado permanentemente")
                                        del st.session_state.eliminando_radio_id
                                        time.sleep(2)
                                        st.rerun()
                                    else:
                                        st.error("No se pudo eliminar el radioexperimentador")
                                except Exception as e:
                                    st.error(f"Error al eliminar: {str(e)}")
                        
                        with col_conf2:
                            if st.button("❌ Cancelar", key=f"cancelar_eliminar_{radio['id']}"):
                                if 'eliminando_radio_id' in st.session_state:
                                    del st.session_state.eliminando_radio_id
                                st.rerun()
        else:
            st.info("No se encontraron radioexperimentadores que coincidan con los criterios de búsqueda")
    
    except Exception as e:
        st.error(f"Error al cargar la lista de radioexperimentadores: {str(e)}")

@st.cache_data(ttl=300)  # Cache por 5 minutos
def _get_radioexperimentador_por_id(radio_id):
    """Obtiene un radioexperimentador por su ID con caché"""
    try:
        return db.get_radioexperimentador_por_id(radio_id)
    except Exception as e:
        st.error(f"Error al cargar el radioexperimentador: {str(e)}")
        return None

def _mostrar_formulario_edicion(radio_id):
    """Muestra el formulario para editar un radioexperimentador existente"""
    st.header("✏️ Editar Radioexperimentador")
    
    try:
        # Obtener los datos actuales del radioexperimentador
        radio = _get_radioexperimentador_por_id(radio_id)
        
        if not radio:
            st.error("No se encontró el radioexperimentador especificado")
            if st.button("Volver a la lista"):
                del st.session_state.editando_radio_id
                st.rerun()
            return
        
        # Mostrar el indicativo como texto (no editable)
        st.write(f"**Indicativo:** {radio['indicativo']}")
        
        # Campos editables
        with st.form(key='editar_radio_form'):
            nombre = st.text_input("Nombre completo", value=radio['nombre_completo'])
            
            col1, col2 = st.columns(2)
            with col1:
                municipio = st.text_input("Municipio", value=radio['municipio'] or '')
            with col2:
                estado = st.text_input("Estado", value=radio['estado'] or '')
            
            pais = st.text_input("País", value=radio['pais'] or 'México')
            
            # Convertir fechas de string a date si existen
            fecha_nacimiento = None
            if radio['fecha_nacimiento']:
                try:
                    fecha_nacimiento = datetime.strptime(radio['fecha_nacimiento'], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass
            
            fecha_expedicion = None
            if radio['fecha_expedicion']:
                try:
                    fecha_expedicion = datetime.strptime(radio['fecha_expedicion'], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass
            
            col1, col2 = st.columns(2)
            with col1:
                fecha_nac = st.date_input("Fecha de Nacimiento", value=fecha_nacimiento)
            with col2:
                fecha_exp = st.date_input("Fecha de Expedición", value=fecha_expedicion)
            
            nacionalidad = st.text_input("Nacionalidad", value=radio['nacionalidad'] or 'MEXICANA')
            
            genero = st.selectbox("Género", ["MASCULINO", "FEMENINO", "OTRO"], 
                                index=0 if not radio['genero'] else ["MASCULINO", "FEMENINO", "OTRO"].index(radio['genero'])
                                if radio['genero'] in ["MASCULINO", "FEMENINO", "OTRO"] else 0)
            
            tipo_licencia = st.selectbox("Tipo de Licencia", 
                                       ["NOVATO", "AVANZADO", "GENERAL", "EXTRA"],
                                       index=0 if not radio['tipo_licencia'] else 
                                       ["NOVATO", "AVANZADO", "GENERAL", "EXTRA"].index(radio['tipo_licencia'])
                                       if radio['tipo_licencia'] in ["NOVATO", "AVANZADO", "GENERAL", "EXTRA"] else 0)
            
            estatus = st.selectbox("Estatus", 
                                 ["ACTIVO", "INACTIVO", "SUSPENDIDO", "EN TRÁMITE"],
                                 index=0 if not radio['estatus'] else 
                                 ["ACTIVO", "INACTIVO", "SUSPENDIDO", "EN TRÁMITE"].index(radio['estatus'])
                                 if radio['estatus'] in ["ACTIVO", "INACTIVO", "SUSPENDIDO", "EN TRÁMITE"] else 0)
            
            observaciones = st.text_area("Observaciones", value=radio['observaciones'] or '')
            
            # Sección de datos SWL
            st.subheader("Datos SWL")
            col_swl1, col_swl2 = st.columns(2)
            
            with col_swl1:
                swl_estado = st.text_input(
                    "Estado SWL",
                    value=radio.get('swl_estado', ''),
                    help="Estado para reportes SWL"
                )
                
            with col_swl2:
                swl_ciudad = st.text_input(
                    "Ciudad SWL",
                    value=radio.get('swl_ciudad', ''),
                    help="Ciudad para reportes SWL"
                )
            
            # Botones de acción
            col1, col2, col3 = st.columns([1, 1, 2])
            
            with col1:
                if st.form_submit_button("💾 Guardar Cambios", type="primary"):
                    # Validar campos obligatorios
                    if not nombre or not radio['indicativo']:
                        st.error("Los campos de nombre e indicativo son obligatorios")
                    else:
                        # Función para formatear texto en formato oración
                        def formatear_oracion(texto):
                            if not texto or not isinstance(texto, str):
                                return texto
                            return ' '.join(word.capitalize() for word in texto.split())
                        
                        # Preparar datos para actualizar
                        datos_actualizados = {
                            'nombre_completo': formatear_oracion(nombre),
                            'municipio': formatear_oracion(municipio) if municipio else None,
                            'estado': formatear_oracion(estado) if estado else None,
                            'pais': formatear_oracion(pais) if pais else None,
                            'fecha_nacimiento': fecha_nac.strftime('%Y-%m-%d') if fecha_nac else None,
                            'nacionalidad': nacionalidad.upper() if nacionalidad else None,  # Se mantiene en mayúsculas
                            'genero': genero.upper() if genero else None,  # Se mantiene en mayúsculas
                            'tipo_licencia': tipo_licencia.upper() if tipo_licencia else None,  # Se mantiene en mayúsculas
                            'fecha_expedicion': fecha_exp.strftime('%Y-%m-%d') if fecha_exp else None,
                            'estatus': estatus.upper() if estatus else 'ACTIVO',  # Se mantiene en mayúsculas
                            'observaciones': observaciones,  # No se formatea para mantener el formato original
                            'swl_estado': swl_estado.strip() if swl_estado else None,
                            'swl_ciudad': swl_ciudad.strip() if swl_ciudad else None,
                            'activo': 1 if estatus == "ACTIVO" else 0
                        }
                        
                        try:
                            if db.update_radioexperimentador(radio['id'], datos_actualizados):
                                st.success("¡Los cambios se guardaron correctamente!")
                                time.sleep(2)
                                del st.session_state.editando_radio_id
                                st.rerun()
                            else:
                                st.error("No se pudieron guardar los cambios. Intente nuevamente.")
                        except Exception as e:
                            st.error(f"Error al guardar los cambios: {str(e)}")
            
            with col2:
                if st.form_submit_button("❌ Cancelar"):
                    del st.session_state.editando_radio_id
                    st.rerun()
            
            with col3:
                if st.form_submit_button("🗑️ Eliminar Radioexperimentador", type="secondary"):
                    st.session_state.eliminando_radio_id = radio['id']
                    st.session_state.volver_a_editar = True
                    st.rerun()
    
    except Exception as e:
        st.error(f"Error al cargar el formulario de edición: {str(e)}")
        if st.button("Volver a la lista"):
            if 'editando_radio_id' in st.session_state:
                del st.session_state.editando_radio_id
            st.rerun()

def _show_importar_radioexperimentadores():
    """Muestra el formulario para importar radioexperimentadores desde Excel"""
    st.header("📤 Importar Radioexperimentadores desde Excel")
    
    # Sección de descarga de plantilla
    st.subheader("📥 Descargar plantilla")
    st.write("Descarga esta plantilla para asegurar el formato correcto:")
    
    # Crear un DataFrame de ejemplo
    import pandas as pd
    from io import BytesIO
    
    # Datos de ejemplo
    data = {
        'INDICATIVO': ['XE1ABC', 'XE2DEF'],
        'NOMBRE': ['JUAN PEREZ LOPEZ', 'MARIA GONZALEZ'],
        'MUNICIPIO': ['TOLUCA', 'GUADALAJARA'],
        'ESTADO': ['MEXICO', 'JALISCO'],
        'PAIS': ['MEXICO', 'MEXICO'],
        'FECHA_NACIMIENTO': ['1980-01-15', '1985-05-20'],
        'NACIONALIDAD': ['MEXICANA', 'MEXICANA'],
        'GENERO': ['MASCULINO', 'FEMENINO'],
        'TIPO_LICENCIA': ['NOVATO', 'AVANZADO'],
        'FECHA_EXPEDICION': ['2023-01-01', '2023-01-01'],
        'ESTATUS': ['ACTIVO', 'ACTIVO'],
        'OBSERVACIONES': ['', '']
    }
    
    df_template = pd.DataFrame(data)
    
    # Crear un buffer para el archivo Excel
    output = BytesIO()
    
    try:
        # Intentar usar xlsxwriter si está disponible
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_template.to_excel(writer, index=False, sheet_name='Plantilla')
            
            # Formato de la hoja solo disponible con xlsxwriter
            workbook = writer.book
            worksheet = writer.sheets['Plantilla']
            
            # Ajustar el ancho de las columnas
            for i, col in enumerate(df_template.columns):
                max_length = max(df_template[col].astype(str).apply(len).max(), len(col)) + 2
                worksheet.set_column(i, i, max_length)
    except ImportError:
        # Si xlsxwriter no está instalado, usar openpyxl (menos opciones de formato)
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_template.to_excel(writer, index=False, sheet_name='Plantilla')
    
    # Crear botón de descarga
    st.download_button(
        label="📥 Descargar Plantilla de Ejemplo",
        data=output.getvalue(),
        file_name="plantilla_radioexperimentadores.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    st.markdown("---")
    st.subheader("Subir archivo")
    st.info("""
    **Instrucciones para la importación:**
    1. Usa la plantilla de arriba o asegúrate que tu archivo Excel tenga al menos estas columnas:
       - `INDICATIVO` (obligatorio)
       - `NOMBRE` o `NOMBRE COMPLETO` (obligatorio)
    2. La primera fila debe contener los nombres de las columnas.
    3. Los demás campos son opcionales.
    """)
    
    # Usar una clave de sesión para controlar la importación
    if 'import_in_progress' not in st.session_state:
        st.session_state.import_in_progress = False
        st.session_state.import_complete = False
        st.session_state.import_errors = []
    
    uploaded_file = st.file_uploader("Selecciona un archivo Excel", type=["xlsx", "xls"])
    
    # Mostrar vista previa del archivo
    if uploaded_file is not None and not st.session_state.import_in_progress and not st.session_state.import_complete:
        st.subheader("Vista previa del archivo")
        try:
            import pandas as pd
            df_preview = pd.read_excel(uploaded_file)
            st.dataframe(df_preview.head(5))  # Mostrar solo las primeras 5 filas
            st.caption(f"Total de filas en el archivo: {len(df_preview)}")
            
            # Mostrar botón de confirmación
            if st.button("✅ Confirmar e importar", type="primary"):
                st.session_state.import_in_progress = True
                
                # Guardar el archivo temporalmente
                import tempfile
                import os
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_file_path = tmp_file.name
                
                try:
                    # Importar el archivo
                    with st.spinner('Procesando archivo...'):
                        total, creados, actualizados, errores = db.import_radioexperimentadores_from_excel(tmp_file_path)
                    
                    # Mostrar resultados
                    st.success(f"✅ Importación completada con éxito!")
                    st.info(f"• Total de registros: {total}")
                    st.info(f"• Nuevos registros: {creados}")
                    st.info(f"• Registros actualizados: {actualizados}")
                    
                    if errores:
                        st.session_state.import_errors = errores
                        with st.expander(f"⚠️ {len(errores)} errores encontrados (haz clic para ver)", expanded=False):
                            for error in errores[:10]:  # Mostrar solo los primeros 10 errores
                                st.error(f"• {error}")
                            if len(errores) > 10:
                                st.warning(f"... y {len(errores) - 10} errores más.")
                    
                    st.balloons()  # Efecto de animación al completar
                    st.session_state.import_complete = True
                    
                except Exception as e:
                    st.error(f"❌ Error al importar el archivo: {str(e)}")
                    st.session_state.import_in_progress = False
                finally:
                    # Limpiar archivo temporal
                    try:
                        os.unlink(tmp_file_path)
                    except:
                        pass
                    
        except Exception as e:
            st.error(f"❌ No se pudo leer el archivo: {str(e)}")
    
    # Mostrar botón para reiniciar la importación
    if st.session_state.import_complete:
        if st.button("🔄 Realizar nueva importación"):
            st.session_state.import_in_progress = False
            st.session_state.import_complete = False
            st.session_state.import_errors = []
            st.rerun()
            
        # Botón para descargar reporte de errores si hay errores
        if st.session_state.import_errors:
            import pandas as pd
            df_errores = pd.DataFrame({"Errores": st.session_state.import_errors})
            st.download_button(
                label="📥 Descargar reporte de errores",
                data=df_errores.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'),
                file_name="errores_importacion_radioexperimentadores.csv",
                mime="text/csv"
            )

def _show_crear_zona():
    """Muestra el formulario para crear o editar una zona"""
    # Verificar si estamos en modo edición
    if 'editing_zona' in st.session_state:
        st.subheader("✏️ Editar Zona")
        zona_data = db.get_zona(st.session_state.editing_zona)
        
        if not zona_data:
            st.error("No se encontró la zona a editar")
            del st.session_state.editing_zona
            return
            
        # Inicializar valores por defecto
        zona_valor = zona_data.get('zona', '')
        nombre = zona_data.get('nombre', '')
        activo = zona_data.get('activo', 1) == 1
    else:
        st.subheader("➕ Crear Nueva Zona")
        # Valores por defecto para nueva zona
        zona_valor = ""
        nombre = ""
        activo = True
    
    # Formulario para crear/editar zona
    with st.form("zona_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            zona_valor = st.text_input("Zona*", value=zona_valor, 
                                     disabled='editing_zona' in st.session_state)
            nombre = st.text_input("Nombre de la zona*", value=nombre)
        
        with col2:
            st.write("")
            st.write("")
            activo = st.checkbox("Activa", value=activo)
        
        # Botones del formulario
        col1, col2 = st.columns(2)
        
        with col1:
            if st.form_submit_button("💾 Guardar Zona", width='stretch'):
                if not zona_valor or not nombre:
                    st.error("Los campos marcados con * son obligatorios")
                else:
                    try:
                        if 'editing_zona' in st.session_state:
                            # Actualizar zona existente
                            if db.update_zona(
                                zona_original=st.session_state.editing_zona,
                                zona=zona_valor,
                                nombre=nombre,
                                activo=1 if activo else 0
                            ):
                                st.success("✅ Zona actualizada correctamente")
                                time.sleep(2)
                                # Limpiar estado de edición
                                del st.session_state.editing_zona
                                st.rerun()
                            else:
                                st.error("❌ Error al actualizar la zona. Verifica que la zona no esté duplicada.")
                        else:
                            # Crear nueva zona
                            if db.create_zona(
                                zona=zona_valor,
                                nombre=nombre
                            ):
                                st.success("✅ Zona creada correctamente")
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error("❌ Error al crear la zona. Verifica que la zona no esté duplicada.")
                    except Exception as e:
                        st.error(f"Error al procesar la solicitud: {str(e)}")
        
        with col2:
            if st.form_submit_button("❌ Cancelar", type="secondary", width='stretch'):
                if 'editing_zona' in st.session_state:
                    del st.session_state.editing_zona
                st.rerun()

@st.cache_data(ttl=86400)  # Cache por 24 horas
def _get_estados_cached():
    """Obtiene la lista de estados con caché mejorada"""
    try:
        # Usar una variable de sesión para cachear los estados
        if 'estados_cache' not in st.session_state:
            estados = db.get_estados()
            estados_list = [""] + [e['nombre'] for e in estados]
            st.session_state.estados_cache = estados_list
        return st.session_state.estados_cache
    except Exception as e:
        st.error(f"Error al cargar los estados: {str(e)}")
        return [""]

@st.cache_data(ttl=86400)  # Cache por 24 horas
def _get_opciones_estaticas():
    """Obtiene opciones estáticas con caché"""
    # Usar una variable de sesión para cachear las opciones
    if 'opciones_estaticas' not in st.session_state:
        st.session_state.opciones_estaticas = {
            'paises': ['México', 'Estados Unidos', 'España', 'Colombia', 'Argentina', 'Otro'],
            'genero': ['', 'MASCULINO', 'FEMENINO', 'OTRO'],
            'licencia': ['', 'NOVATO', 'AVANZADO', 'GENERAL', 'EXTRA'],
            'estatus': ['ACTIVO', 'INACTIVO', 'SUSPENDIDO', 'EN TRÁMITE']
        }
    return st.session_state.opciones_estaticas

def _formatear_oracion(texto):
    """Formatea el texto en formato oración"""
    if not texto or not isinstance(texto, str):
        return texto
    return ' '.join(word.capitalize() for word in texto.split())

@st.cache_data(ttl=3600, show_spinner=False)
def _get_estados_list():
    """Obtiene la lista de estados con caché"""
    try:
        estados = db.get_estados()
        return [""] + list(estados.values())
    except Exception as e:
        st.error(f"Error al cargar los estados: {str(e)}")
        return [""]

@st.cache_data(ttl=3600, show_spinner=False)
def _get_estados_cached():
    """Obtiene la lista de estados con caché mejorada"""
    try:
        estados = db.get_estados()
        # get_estados() returns a list of state names, not a dictionary
        return [""] + [estado for estado in estados if estado]  # Filter out any None or empty values
    except Exception as e:
        st.error(f"Error al cargar los estados: {str(e)}")
        return [""]

def _show_crear_radioexperimentador():
    """Muestra el formulario para crear un nuevo radioexperimentador con mejoras de rendimiento"""
    st.header("🆕 Agregar Nuevo Radioexperimentador")
    
    # Obtener opciones estáticas y estados con caché
    opciones = _get_opciones_estaticas()
    estados_list = _get_estados_cached()
    
    # Inicializar el estado del formulario si no existe
    if 'form_data' not in st.session_state:
        st.session_state.form_data = {
            'indicativo': '',
            'nombre': '',
            'municipio': '',
            'estado': '',
            'pais': 'México',
            'fecha_nac': None,
            'fecha_exp': None,
            'nacionalidad': 'MEXICANA',
            'genero': '',
            'tipo_licencia': '',
            'estatus': 'ACTIVO',
            'observaciones': '',
            'swl_estado': '',
            'swl_ciudad': ''
        }
    
    # Obtener referencias directas a los datos del formulario
    form_data = st.session_state.form_data
    
# Cargar opciones estáticas una sola vez
    opciones = _get_opciones_estaticas()
    estados_list = _get_estados_cached()
    
    # Usar st.form para agrupar los campos
    with st.form(key='crear_radio_form'):
        col1, col2 = st.columns(2)
        
        with col1:
            # Usar st.text_input con key única para cada campo
            form_data['indicativo'] = st.text_input(
                "Indicativo*", 
                value=form_data['indicativo'],
                key='form_indicativo'
            )
            
            form_data['nombre'] = st.text_input(
                "Nombre completo*", 
                value=form_data['nombre'],
                key='form_nombre'
            )
            
            form_data['municipio'] = st.text_input(
                "Municipio", 
                value=form_data['municipio'],
                key='form_municipio'
            )
            
            # Estado con datos en caché
            estado_index = estados_list.index(form_data['estado']) if form_data['estado'] in estados_list else 0
            form_data['estado'] = st.selectbox(
                "Estado",
                estados_list,
                index=estado_index,
                key='form_estado'
            )
            
            pais_index = opciones['paises'].index(form_data['pais']) if form_data['pais'] in opciones['paises'] else 0
            form_data['pais'] = st.selectbox(
                "País",
                opciones['paises'],
                index=pais_index,
                key='form_pais'
            )
            
        with col2:
            form_data['fecha_nac'] = st.date_input(
                "Fecha de Nacimiento", 
                value=form_data['fecha_nac'],
                key='form_fecha_nac'
            )
            
            form_data['fecha_exp'] = st.date_input(
                "Fecha de Expedición", 
                value=form_data['fecha_exp'],
                key='form_fecha_exp'
            )
            
            form_data['nacionalidad'] = st.text_input(
                "Nacionalidad", 
                value=form_data['nacionalidad'],
                key='form_nacionalidad'
            )
            
            genero_index = opciones['genero'].index(form_data['genero']) if form_data['genero'] in opciones['genero'] else 0
            form_data['genero'] = st.selectbox(
                "Género", 
                opciones['genero'],
                index=genero_index,
                key='form_genero'
            )
            
            licencia_index = opciones['licencia'].index(form_data['tipo_licencia']) if form_data['tipo_licencia'] in opciones['licencia'] else 0
            form_data['tipo_licencia'] = st.selectbox(
                "Tipo de Licencia",
                opciones['licencia'],
                index=licencia_index,
                key='form_licencia'
            )
            
            estatus_index = opciones['estatus'].index(form_data['estatus']) if form_data['estatus'] in opciones['estatus'] else 0
            form_data['estatus'] = st.selectbox(
                "Estatus",
                opciones['estatus'],
                index=estatus_index,
                key='form_estatus'
            )
        
        form_data['observaciones'] = st.text_area(
            "Observaciones", 
            value=form_data['observaciones'],
            key='form_observaciones'
        )
        
        # Campos SWL
        st.subheader("Datos SWL")
        col_swl1, col_swl2 = st.columns(2)
        
        with col_swl1:
            form_data['swl_estado'] = st.text_input(
                "Estado SWL",
                value=form_data['swl_estado'],
                key='form_swl_estado',
                help="Estado para reportes SWL"
            )
            
        with col_swl2:
            form_data['swl_ciudad'] = st.text_input(
                "Ciudad SWL",
                value=form_data['swl_ciudad'],
                key='form_swl_ciudad',
                help="Ciudad para reportes SWL"
            )
        
        # Botones del formulario
        col_btn1, col_btn2, _ = st.columns([1, 1, 4])
        
        with col_btn1:
            guardar = st.form_submit_button("💾 Guardar", type="primary", width='stretch')
        
        with col_btn2:
            cancelar = st.form_submit_button("❌ Cancelar", type="secondary", width='stretch')
        
        # Procesar guardado o cancelación
        if guardar:
            # Validar campos obligatorios
            if not form_data['indicativo'] or not form_data['nombre']:
                st.error("Los campos marcados con * son obligatorios")
            else:
                # Validar formato del indicativo
                es_valido, mensaje_error = utils.validate_call_sign(form_data['indicativo'])
                if not es_valido:
                    st.error(f"Error en el indicativo: {mensaje_error}")
                    st.stop()  # Detener la ejecución para evitar procesamiento adicional
                try:
                    # Preparar datos para guardar
                    datos = {
                        'indicativo': form_data['indicativo'].upper(),
                        'nombre_completo': _formatear_oracion(form_data['nombre']),
                        'municipio': _formatear_oracion(form_data['municipio']) if form_data['municipio'] else None,
                        'estado': _formatear_oracion(form_data['estado']) if form_data['estado'] else None,
                        'pais': _formatear_oracion(form_data['pais']) if form_data['pais'] else None,
                        'fecha_nacimiento': form_data['fecha_nac'].strftime('%Y-%m-%d') if form_data['fecha_nac'] else None,
                        'nacionalidad': form_data['nacionalidad'].upper(),
                        'genero': form_data['genero'].upper() if form_data['genero'] else None,
                        'tipo_licencia': form_data['tipo_licencia'].upper() if form_data['tipo_licencia'] else None,
                        'fecha_expedicion': form_data['fecha_exp'].strftime('%Y-%m-%d') if form_data['fecha_exp'] else None,
                        'estatus': form_data['estatus'].upper(),
                        'observaciones': form_data['observaciones'],
                        'swl_estado': form_data['swl_estado'],
                        'swl_ciudad': form_data['swl_ciudad'],
                        'activo': 1 if form_data['estatus'] == 'ACTIVO' else 0
                    }
                    
                    # Intentar crear el radioexperimentador
                    with st.spinner('Guardando radioexperimentador...'):
                        radio_id = db.create_radioexperimentador(datos)
                    
                    if radio_id:
                        st.success("¡Radioexperimentador creado exitosamente!")
                        time.sleep(2)
                        # Limpiar el formulario después de guardar exitosamente
                        for key in st.session_state.form_data:
                            if key == 'pais':
                                st.session_state.form_data[key] = 'México'
                            elif key == 'estatus':
                                st.session_state.form_data[key] = 'ACTIVO'
                            elif key == 'nacionalidad':
                                st.session_state.form_data[key] = 'MEXICANA'
                            elif key in ['fecha_nac', 'fecha_exp']:
                                st.session_state.form_data[key] = None
                            else:
                                st.session_state.form_data[key] = ''
                        st.rerun()
                    else:
                        st.error("No se pudo crear el radioexperimentador. Verifica los datos e intenta nuevamente.")
                except Exception as e:
                    if "UNIQUE constraint failed: radioexperimentadores.indicativo" in str(e):
                        st.error("Ya existe un radioexperimentador con este indicativo.")
                    else:
                        st.error(f"Error al crear el radioexperimentador: {str(e)}")
        
        # Manejar cancelación
        if cancelar:
            # Restablecer el formulario a los valores por defecto sin recargar la página
            for key in st.session_state.form_data:
                if key in ['pais', 'estatus']:
                    st.session_state.form_data[key] = 'México' if key == 'pais' else 'ACTIVO'
                elif key in ['fecha_nac', 'fecha_exp']:
                    st.session_state.form_data[key] = None
                elif key == 'nacionalidad':
                    st.session_state.form_data[key] = 'MEXICANA'
                else:
                    st.session_state.form_data[key] = ''
            
            # Usar st.rerun() para forzar la actualización
            st.rerun()
        

try:
    with open("assets/LogoFMRE_small.png", "rb") as _lf:
        _logo_fmre_b64 = base64.b64encode(_lf.read()).decode()
except Exception:
    _logo_fmre_b64 = ""
_footer_html = f"""
<div style="margin-top:24px;padding:12px 0;text-align:center;color:#555;font:12px/1.4 system-ui,-apple-system,'Segoe UI',Roboto,Arial,'Noto Sans'">
  <div style="margin-bottom:6px;">
    <img src="data:image/png;base64,{_logo_fmre_b64}" alt="FMRE" style="height:18px;vertical-align:middle;margin-right:8px;">
    <strong>Federación Mexicana de Radioexperimentadores A.C.</strong>
  </div>
  <div style="margin-bottom:4px;">QMS — Sistema de Gestión de QSO</div>
  <div>Desarrollado por integrantes del Radio Club Guadiana · <a href="https://rcg.org.mx" target="_blank" rel="noopener">rcg.org.mx</a></div>
</div>
"""

if __name__ == "__main__":
    main()
    st.markdown(_footer_html, unsafe_allow_html=True)
