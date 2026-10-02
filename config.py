from pathlib import Path
APP_TITLE = "SIMUP-M"
APP_SUBTITLE = "Sistema de Simulación para la Gestión Pública Municipal"
VERSION = "0.2 — prototipo académico"
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DIMENSIONES = ["Impacto educativo", "Desarrollo municipal", "Viabilidad financiera", "Cobertura", "Sostenibilidad"]
