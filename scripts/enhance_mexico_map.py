from pathlib import Path

APP_PATH = Path(r"c:\Users\xe2mbe\OneDrive\Documentos\Development\qms\app.py")

OLD_LAYOUT = """                    fig.update_layout(\n                        geo=dict(\n                            scope='north america',\n                            center=dict(lat=23.0, lon=-102.0),\n                            projection_scale=5.0,\n                            showland=True,\n                            landcolor='rgb(235, 235, 235)',\n                            showcountries=True,\n                            countrycolor='rgb(204, 204, 204)'\n                        ),\n                        coloraxis_colorbar=dict(title='Reportes'),\n                        margin=dict(l=0, r=0, t=0, b=0)\n                    )"""

NEW_LAYOUT = """                    fig.update_layout(\n                        geo=dict(\n                            scope='north america',\n                            center=dict(lat=23.0, lon=-102.0),\n                            projection_scale=5.0,\n                            showland=True,\n                            landcolor='rgb(235, 235, 235)',\n                            showcountries=True,\n                            countrycolor='rgb(204, 204, 204)',\n                            showsubunits=True,\n                            subunitcolor='rgb(160, 160, 160)',\n                            subunitwidth=1,\n                            showcoastlines=True,\n                            coastlinecolor='rgb(150, 150, 150)'\n                        ),\n                        coloraxis_colorbar=dict(title='Reportes'),\n                        margin=dict(l=0, r=0, t=0, b=0)\n                    )"""


def main() -> None:
    text = APP_PATH.read_text(encoding="utf-8")
    if OLD_LAYOUT not in text:
        raise SystemExit("No se encontró el bloque de layout esperado.")
    text = text.replace(OLD_LAYOUT, NEW_LAYOUT, 1)
    APP_PATH.write_text(text, encoding="utf-8")
    print("Layout actualizado con límites políticos de estados.")


if __name__ == "__main__":
    main()
