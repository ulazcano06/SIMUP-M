from pathlib import Path

APP_TITLE = "SIMUP-M 1.0"
APP_SUBTITLE = "Sistema de Simulación de Política Pública Municipal"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Fuentes oficiales.
INEGI_EFIPEM_LANDING = "https://www.inegi.org.mx/programas/finanzas/default.html#Datos_abiertos"
INEGI_EFIPEM_INFO = "https://www.inegi.org.mx/programas/finanzas/default.html"
CONEVAL_POBREZA_PAGE = "https://www.coneval.org.mx/Medicion/Paginas/Pobreza-municipio-2010-2020.aspx"
CONEVAL_POBREZA_ZIP = "https://www.coneval.org.mx/Medicion/Documents/Pobreza_municipal/2020/Concentrado_indicadores_de_pobreza_2020.zip"

ENTIDAD_OBJETIVO = "Hidalgo"
CVE_ENTIDAD = "13"
ANIOS_SOCIALES = [2010, 2015, 2020]

# Número de iteraciones por defecto. Se puede modificar desde la interfaz.
MONTE_CARLO_DEFAULT = 5000
RANDOM_STATE = 360

# Cambio máximo sugerido en optimización sobre cada participación de gasto,
# expresado en puntos porcentuales.
MAX_CAMBIO_PP = 15.0
