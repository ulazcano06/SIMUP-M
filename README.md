# SIMUP-M 1.0
## Sistema de Simulación de Política Pública Municipal

Versión inicial enfocada en los 84 municipios de Hidalgo.

## Funciones
- Integración de INEGI EFIPEM + CONEVAL.
- Tabla maestra municipio-año.
- Diagnóstico financiero.
- Gráficas interactivas.
- Modelo predictivo exploratorio.
- Simulación Monte Carlo.
- Optimización presupuestaria restringida.
- Aplicación web con Gradio.

## Instalación local

```bash
python -m venv .venv
```

Windows:
```bash
.venv\Scripts\activate
```

macOS/Linux:
```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
python app.py
```

## Hugging Face Spaces (Gradio)
1. Crear una cuenta en Hugging Face.
2. Crear un Space nuevo.
3. Elegir SDK: **Gradio**.
4. Subir todos los archivos de esta carpeta.
5. El archivo principal es `app.py`.
6. El Space instalará automáticamente `requirements.txt`.

## Datos oficiales
### CONEVAL
La app intenta descargar automáticamente el archivo:
`Concentrado_indicadores_de_pobreza_2020.zip`.

### INEGI EFIPEM
La app intenta descubrir el enlace de datos abiertos desde la página oficial. Como la estructura web del INEGI puede cambiar, se incluye una segunda vía:
- descargar el archivo municipal CSV/ZIP desde **EFIPEM > Datos abiertos**;
- cargarlo en la pestaña **Datos**.

No se debe sustituir la fuente oficial por el modo demo.

## Modo demo
`demo.py` genera datos sintéticos únicamente para:
- comprobar que Gradio abre;
- probar gráficas;
- probar entrenamiento;
- probar Monte Carlo;
- probar optimización.

**Nunca deben utilizarse esos valores en tesis, artículos, informes o decisiones públicas.**

## Diseño metodológico de V1
El modelo es correlacional-predictivo. No es causal.

El optimizador minimiza el indicador social seleccionado dentro de una función predictiva, manteniendo constante la suma de las categorías de gasto controladas y limitando las variaciones.

## Archivos
- `app.py`: interfaz Gradio.
- `config.py`: configuración y fuentes.
- `data_sources.py`: descarga, extracción, limpieza e integración.
- `modeling.py`: entrenamiento, Monte Carlo y optimización.
- `municipios.py`: catálogo de los 84 municipios.
- `utils.py`: utilidades.
- `demo.py`: datos sintéticos de prueba.
- `data/catalogo_variables.csv`: matriz inicial de variables.
