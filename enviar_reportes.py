import streamlit as st
import pandas as pd
from datetime import date, datetime
import io
from typing import List, Dict, Tuple

from database import FMREDatabase
from email_sender import EmailSender


def _parse_emails(raw: str) -> List[str]:
    if not raw:
        return []
    parts = [p.strip() for p in raw.replace(';', ',').split(',')]
    return [p for p in parts if p]


def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode('utf-8')


def _df_to_xlsx_bytes(df: pd.DataFrame, sheet_name: str = 'Reporte') -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    buf.seek(0)
    return buf.read()


def _ensure_session_keys():
    for k, v in {
        'send_reports.attachments': {},
        'send_reports.preview': {},
        'send_reports.last_generation': None,
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _load_eventos(db: FMREDatabase) -> List[str]:
    try:
        eventos = db.get_all_eventos()
        if not eventos:
            return []
        return [e['tipo'] for e in eventos if e.get('activo', 1) == 1]
    except Exception:
        return []


def _build_tradicional_data(db: FMREDatabase, f_ini: str, f_fin: str, eventos_sel: List[str],
                            secciones: List[str]) -> Dict[str, pd.DataFrame]:
    data: Dict[str, pd.DataFrame] = {}
    reportes, stats = db.get_reportes_por_fecha_rango(f_ini, f_fin)
    df = pd.DataFrame(reportes) if reportes else pd.DataFrame()

    # Por Tipo de Evento (filtrado)
    if 'Por Tipo de Evento' in secciones:
        if not df.empty:
            if 'tipo_evento' in df.columns and eventos_sel:
                df_evento = df[df['tipo_evento'].isin(eventos_sel)].copy()
            else:
                df_evento = df.copy()
        else:
            df_evento = pd.DataFrame()
        data['tradicional_por_tipo_evento'] = df_evento

    # Total (resumen)
    if 'Total' in secciones:
        resumen_rows = []
        total_reportes = stats.get('total_reportes') if isinstance(stats, dict) else None
        estaciones_unicas = stats.get('estaciones_unicas') if isinstance(stats, dict) else None
        if total_reportes is None and not df.empty:
            total_reportes = len(df)
        if estaciones_unicas is None and not df.empty and 'indicativo' in df.columns:
            estaciones_unicas = df['indicativo'].nunique()
        resumen_rows.append({'total_reportes': total_reportes or 0,
                             'estaciones_unicas': estaciones_unicas or 0})
        data['tradicional_totales'] = pd.DataFrame(resumen_rows)

    # Por Estación (agrupación)
    if 'Por Estación' in secciones:
        if not df.empty and 'indicativo' in df.columns:
            por_estacion = (df.groupby('indicativo', as_index=False)
                              .size()
                              .rename(columns={'size': 'conteo'}))
        else:
            por_estacion = pd.DataFrame(columns=['indicativo', 'conteo'])
        data['tradicional_por_estacion'] = por_estacion

    return data


def _build_rs_data(db: FMREDatabase, f_ini: str, f_fin: str, secciones: List[str]) -> Dict[str, pd.DataFrame]:
    data: Dict[str, pd.DataFrame] = {}

    # Totales de Interacción
    if 'Totales de Interacción' in secciones:
        tot = db.get_estadisticas_rs_por_fecha(f_ini, f_fin) or {}
        df_tot = pd.DataFrame([{k: tot.get(k, 0) for k in [
            'total_me_gusta', 'total_comentarios', 'total_compartidos', 'total_reproducciones', 'total_interacciones'
        ]}])
        data['rs_totales_interaccion'] = df_tot

    # Por Plataforma y Por Estación desde reportes_rs
    reportes_rs = db.get_reportes_rs_por_fecha(f_ini, f_fin)
    dfr = pd.DataFrame(reportes_rs) if reportes_rs else pd.DataFrame()

    if 'Por Plataforma' in secciones:
        if not dfr.empty and 'plataforma_nombre' in dfr.columns:
            por_plataforma = (dfr.groupby('plataforma_nombre', as_index=False)
                                .size()
                                .rename(columns={'size': 'conteo'}))
        else:
            por_plataforma = pd.DataFrame(columns=['plataforma_nombre', 'conteo'])
        data['rs_por_plataforma'] = por_plataforma

    if 'Por Estación' in secciones:
        if not dfr.empty and 'indicativo' in dfr.columns:
            por_estacion = (dfr.groupby('indicativo', as_index=False)
                              .size()
                              .rename(columns={'size': 'conteo'}))
        else:
            por_estacion = pd.DataFrame(columns=['indicativo', 'conteo'])
        data['rs_por_estacion'] = por_estacion

    return data


def show_enviar_reportes():
    st.title('📧 Enviar Reportes')
    _ensure_session_keys()

    db = FMREDatabase()
    mailer = EmailSender(db)

    # Configuración
    st.subheader('Configuración')
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        tipo = st.selectbox('Tipo', ['Tradicional', 'RS'], index=0)
    with col2:
        rango = st.date_input('Rango de fechas', value=(date.today(), date.today()))
        if isinstance(rango, tuple):
            f_ini_d, f_fin_d = rango
        else:
            f_ini_d, f_fin_d = rango, rango
        f_ini = f_ini_d.strftime('%Y-%m-%d')
        f_fin = f_fin_d.strftime('%Y-%m-%d')

    # Secciones dinámicas
    secciones = []
    eventos_sel: List[str] = []

    if tipo == 'Tradicional':
        st.markdown('#### Secciones de Tradicional')
        eventos_disp = _load_eventos(db)
        colt1, colt2 = st.columns([2, 1])
        with colt1:
            eventos_sel = st.multiselect('Por Tipo de Evento', options=eventos_disp, default=events_disp if (events_disp := eventos_disp) else [])
        with colt2:
            totales = st.checkbox('Total', value=True)
            por_estacion = st.checkbox('Por Estación', value=True)
        secciones = []
        if eventos_sel:
            secciones.append('Por Tipo de Evento')
        if totales:
            secciones.append('Total')
        if por_estacion:
            secciones.append('Por Estación')
    else:
        st.markdown('#### Secciones de RS')
        colr1, colr2, colr3 = st.columns(3)
        with colr1:
            totales_i = st.checkbox('Totales de Interacción', value=True)
        with colr2:
            por_plat = st.checkbox('Por Plataforma', value=True)
        with colr3:
            por_est = st.checkbox('Por Estación', value=False)
        secciones = [s for s, on in [
            ('Totales de Interacción', totales_i),
            ('Por Plataforma', por_plat),
            ('Por Estación', por_est),
        ] if on]

    st.markdown('#### Formatos')
    formatos = st.multiselect('Selecciona formatos', options=['CSV', 'Excel (.xlsx)', 'PDF'], default=['CSV', 'Excel (.xlsx)'])

    st.markdown('#### Destinatarios')
    to_raw = st.text_input('Correos (separados por coma)')
    asunto = st.text_input('Asunto', value=f"Reporte {tipo} {f_ini} — {f_fin}")
    cuerpo = st.text_area('Cuerpo del correo (HTML permitido)', value=f"<p>Se adjunta reporte {tipo} del {f_ini} al {f_fin}.</p>")

    colb1, colb2, colb3 = st.columns(3)

    with colb1:
        if st.button('👁️ Vista previa', type='secondary', use_container_width=True):
            if tipo == 'Tradicional':
                prev = _build_tradicional_data(db, f_ini, f_fin, eventos_sel, secciones)
            else:
                prev = _build_rs_data(db, f_ini, f_fin, secciones)
            st.session_state['send_reports.preview'] = prev

    with colb2:
        if st.button('📦 Generar adjuntos', type='primary', use_container_width=True):
            attachments: Dict[str, bytes] = {}
            if tipo == 'Tradicional':
                data = _build_tradicional_data(db, f_ini, f_fin, eventos_sel, secciones)
            else:
                data = _build_rs_data(db, f_ini, f_fin, secciones)

            for key, df in data.items():
                if df is None or df.empty:
                    continue
                base = f"{tipo.lower()}_{key}_{f_ini}_{f_fin}"
                if 'CSV' in formatos:
                    attachments[f"{base}.csv"] = _df_to_csv_bytes(df)
                if 'Excel (.xlsx)' in formatos:
                    attachments[f"{base}.xlsx"] = _df_to_xlsx_bytes(df)
                # PDF pendiente de implementar (fase 2)

            st.session_state['send_reports.attachments'] = attachments
            st.session_state['send_reports.last_generation'] = datetime.now().isoformat()

    with colb3:
        if st.button('📨 Enviar', type='primary', use_container_width=True):
            emails = _parse_emails(to_raw)
            if not emails:
                st.error('Ingrese al menos un destinatario')
            elif not st.session_state.get('send_reports.attachments'):
                st.error('Genere adjuntos antes de enviar')
            else:
                try:
                    files = []
                    for fname, blob in st.session_state['send_reports.attachments'].items():
                        # determinar mime básico
                        if fname.endswith('.csv'):
                            mime = 'text/csv'
                        elif fname.endswith('.xlsx'):
                            mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                        else:
                            mime = 'application/octet-stream'
                        files.append((fname, blob, mime))

                    ok = mailer.send_email_with_attachments(
                        to_emails=emails,
                        subject=asunto,
                        body=cuerpo,
                        attachments=files,
                        is_html=True
                    )
                    if ok:
                        st.success('✅ Correo enviado')
                    else:
                        st.error('No se pudo enviar el correo')
                except Exception as e:
                    st.error(f'❌ Error al enviar: {e}')

    st.markdown('---')
    # Mostrar vista previa y adjuntos
    prev = st.session_state.get('send_reports.preview') or {}
    if prev:
        st.subheader('Vista previa')
        for k, df in prev.items():
            st.caption(k)
            if isinstance(df, pd.DataFrame) and not df.empty:
                st.dataframe(df.head(50), hide_index=True, use_container_width=True)
            else:
                st.info('Sin datos para esta sección')

    atts = st.session_state.get('send_reports.attachments') or {}
    if atts:
        st.subheader('Adjuntos generados')
        for fname, blob in atts.items():
            st.download_button(
                label=f'⬇️ Descargar {fname}',
                file_name=fname,
                data=blob,
                mime='application/octet-stream',
                use_container_width=True
            )
