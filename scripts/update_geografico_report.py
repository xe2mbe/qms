from pathlib import Path

APP_PATH = Path(r"c:\Users\xe2mbe\OneDrive\Documentos\Development\qms\app.py")

def main() -> None:
    contenido = APP_PATH.read_text(encoding="utf-8")

    bloque_df_original = """            df_geografico = pd.DataFrame([{
                'Indicativo': r.get('indicativo', ''),
                'Estado': r.get('estado', ''),
                'Ciudad': r.get('ciudad', ''),
                'Zona': r.get('zona', ''),
                'Sistema': r.get('sistema', '')
            } for r in reportes])"""

    bloque_df_nuevo = bloque_df_original + """
            df_geografico['Estado'] = df_geografico['Estado'].fillna('Desconocido')
            df_geografico['estado_norm'] = df_geografico['Estado'].apply(_normalizar_estado_nombre)"""

    if bloque_df_original not in contenido:
        raise SystemExit("No se encontró el bloque de creación de df_geografico esperado.")

    contenido = contenido.replace(bloque_df_original, bloque_df_nuevo, 1)

    marcador_tabla = "            # Tabla detallada"
    if marcador_tabla not in contenido:
        raise SystemExit("No se encontró el marcador '# Tabla detallada' para insertar el mapa.")

    bloque_mapa = """
            st.subheader(\"🗺️ Mapa de Reportes por Estado\")

            if px is None:
                st.info(\"Instala la librería `plotly` para visualizar el mapa interactivo (pip install plotly).\")
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
                    st.info(\"No hay estados válidos para graficar en el mapa.\")
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

                    if conteo_valido.empty:
                        st.warning(\"No se pudieron ubicar coordenadas para los estados reportados.\")
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

                        fig.update_layout(
                            geo=dict(
                                scope='north america',
                                center=dict(lat=23.0, lon=-102.0),
                                projection_scale=5.0,
                                showland=True,
                                landcolor='rgb(235, 235, 235)',
                                showcountries=True,
                                countrycolor='rgb(204, 204, 204)'
                            ),
                            coloraxis_colorbar=dict(title='Reportes'),
                            margin=dict(l=0, r=0, t=0, b=0)
                        )

                        st.plotly_chart(fig, use_container_width=True)

                estados_sin_coordenadas = conteo_por_estado[conteo_por_estado[['lat', 'lon']].isna().any(axis=1)]
                if not estados_sin_coordenadas.empty:
                    st.caption(
                        \"⚠️ Estados sin coordenadas mapeadas: \"
                        + \", ".join(sorted(estados_sin_coordenadas['Estado'].unique()))
                    )

"""

    contenido = contenido.replace(marcador_tabla, bloque_mapa + marcador_tabla, 1)

    APP_PATH.write_text(contenido, encoding="utf-8")
    print("Cambios aplicados correctamente.")


if __name__ == "__main__":
    main()
