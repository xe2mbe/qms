from pathlib import Path

APP_PATH = Path(r"c:\Users\xe2mbe\OneDrive\Documentos\Development\qms\app.py")

NORMALIZATION_BLOCK = """            df_geografico['Estado'] = df_geografico['Estado'].fillna('Desconocido')\n            df_geografico['estado_norm'] = df_geografico['Estado'].apply(_normalizar_estado_nombre)\n"""

MAP_BLOCK = """            st.subheader(\"🗺️ Mapa de Reportes por Estado\")\n\n            if px is None:\n                st.info(\"Instala la librería `plotly` para visualizar el mapa interactivo (pip install plotly).\")\n            else:\n                estado_label_map = {}\n                for norm, original in zip(df_geografico['estado_norm'], df_geografico['Estado']):\n                    if norm and norm not in estado_label_map:\n                        estado_label_map[norm] = original\n\n                df_estados_validos = df_geografico[df_geografico['estado_norm'] != '']\n\n                conteo_por_estado = (\n                    df_estados_validos\n                    .groupby('estado_norm')\n                    .size()\n                    .reset_index(name='reportes')\n                )\n\n                if conteo_por_estado.empty:\n                    st.info(\"No hay estados válidos para graficar en el mapa.\")\n                else:\n                    conteo_por_estado['Estado'] = conteo_por_estado['estado_norm'].apply(\n                        lambda s: estado_label_map.get(s, 'Desconocido')\n                    )\n                    conteo_por_estado['lat'] = conteo_por_estado['estado_norm'].map(\n                        lambda s: MEXICO_STATE_COORDS.get(s, (None, None))[0]\n                    )\n                    conteo_por_estado['lon'] = conteo_por_estado['estado_norm'].map(\n                        lambda s: MEXICO_STATE_COORDS.get(s, (None, None))[1]\n                    )\n\n                    conteo_valido = conteo_por_estado.dropna(subset=['lat', 'lon'])\n\n                    if conteo_valido.empty:\n                        st.warning(\"No se pudieron ubicar coordenadas para los estados reportados.\")\n                    else:\n                        fig = px.scatter_geo(\n                            conteo_valido,\n                            lat='lat',\n                            lon='lon',\n                            size='reportes',\n                            size_max=40,\n                            color='reportes',\n                            hover_name='Estado',\n                            hover_data={'reportes': True, 'lat': False, 'lon': False},\n                            projection='natural earth'\n                        )\n\n                        fig.update_layout(\n                            geo=dict(\n                                scope='north america',\n                                center=dict(lat=23.0, lon=-102.0),\n                                projection_scale=5.0,\n                                showland=True,\n                                landcolor='rgb(235, 235, 235)',\n                                showcountries=True,\n                                countrycolor='rgb(204, 204, 204)'\n                            ),\n                            coloraxis_colorbar=dict(title='Reportes'),\n                            margin=dict(l=0, r=0, t=0, b=0)\n                        )\n\n                        st.plotly_chart(fig, use_container_width=True)\n\n                estados_sin_coordenadas = conteo_por_estado[conteo_por_estado[['lat', 'lon']].isna().any(axis=1)]\n                if not estados_sin_coordenadas.empty:\n                    st.caption(\n                        \"⚠️ Estados sin coordenadas mapeadas: \"\n                        + \", ".join(sorted(estados_sin_coordenadas['Estado'].unique()))\n                    )\n\n"""


def main() -> None:
    text = APP_PATH.read_text(encoding="utf-8")

    # Consolidar bloque de normalización
    while text.count(NORMALIZATION_BLOCK) > 1:
        text = text.replace(NORMALIZATION_BLOCK, "", 1)
        text = text.replace("\n\n\n", "\n\n")
    if NORMALIZATION_BLOCK not in text:
        raise SystemExit("No se encontró el bloque de normalización tras limpiar.")

    # Asegurar que quede solo un bloque del mapa
    occurrences = text.count(MAP_BLOCK)
    if occurrences == 0:
        raise SystemExit("No se encontró el bloque del mapa para limpiar.")
    while text.count(MAP_BLOCK) > 1:
        text = text.replace(MAP_BLOCK, "", 1)
        text = text.replace("\n\n\n", "\n\n")
    if text.count(MAP_BLOCK) != 1:
        raise SystemExit("No se pudo consolidar el bloque del mapa correctamente.")

    APP_PATH.write_text(text, encoding="utf-8")
    print("Limpieza completada: un solo bloque de normalización y un solo mapa.")


if __name__ == "__main__":
    main()
