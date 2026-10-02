# SIMUP-M V0.2
Sistema de Simulación para la Gestión Pública Municipal — prototipo académico para Hidalgo.

## Qué incluye
- Interfaz web Gradio.
- Carga de CSV/XLSX.
- Modo demo sintético (solo pruebas).
- Diagnóstico municipal.
- Captura y evaluación de una propuesta.
- Semáforo multidimensional: educación, desarrollo, finanzas, cobertura y sostenibilidad.
- IEE prototipo y comparación de línea base vs. escenario.

## Ejecutar localmente
```bash
pip install -r requirements.txt
python app.py
```
Abrir http://127.0.0.1:7860

## Render
- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `python app.py`

## Hugging Face Spaces
Crear un Space con SDK Gradio y subir todos los archivos. `app.py` es el archivo principal.

## Advertencia metodológica
V0.2 es un demostrador de arquitectura. Los datos de `demo.py` son sintéticos. Los umbrales del semáforo y los pesos iguales del IEE son provisionales y NO deben usarse como evidencia de tesis ni para decisiones públicas. La siguiente fase debe reemplazar estas reglas con criterios validados y datos oficiales.

## Columnas recomendadas para una base real
`cve_mun, municipio, anio, poblacion, rezago_educativo_pct, escolaridad_anios, analfabetismo_pct, cobertura_educativa_pct, pobreza_pct, pobreza_extrema_pct, rezago_social_indice, ingresos_municipales, ingresos_propios, gasto_publico, inversion_publica`
