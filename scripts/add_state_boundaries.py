import re
from pathlib import Path

APP_PATH = Path(r"c:\Users\xe2mbe\OneDrive\Documentos\Development\qms\app.py")

PATTERN = re.compile(
    r"fig\.update_layout\(\n\s+geo=dict\([\s\S]+?\)\n\s*\)",
    re.MULTILINE,
)

REPLACEMENT = """                        fig.update_geos(
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
                        )"""


def main() -> None:
    text = APP_PATH.read_text(encoding="utf-8")
    if not PATTERN.search(text):
        raise SystemExit("No se encontró el bloque geo en app.py (puede haber cambiado el formato).")
    text, count = PATTERN.subn(REPLACEMENT, text, count=1)
    if count != 1:
        raise SystemExit(f"Se reemplazaron {count} bloques; se esperaba 1.")
    APP_PATH.write_text(text, encoding="utf-8")
    print("Configuración geográfica actualizada con límites políticos.")


if __name__ == "__main__":
    main()
