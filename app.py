import os
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gradio as gr

from config import APP_TITLE, APP_SUBTITLE, DATA_DIR, MONTE_CARLO_DEFAULT
from municipios import MUNICIPIOS_HIDALGO
from data_sources import (
    descargar_coneval, descargar_efipem, cargar_efipem_desde_archivo,
    construir_base_maestra
)
from modeling import entrenar_modelo, monte_carlo, optimizar, OBJETIVOS, predecir
from demo import crear_demo
from utils import percentil_serie

STATE = {"base": None, "modelo": None, "modo": None, "fuentes": ""}

def _status():
    if STATE["base"] is None:
        return "### Estado\nSin datos cargados."
    return f"""### Estado
**Modo:** {STATE["modo"]}  
**Filas:** {len(STATE["base"]):,}  
**Fuentes:** {STATE["fuentes"]}
"""

def cargar_demo():
    STATE["base"] = crear_demo()
    STATE["modo"] = "DEMO SINTÉTICO — NO USAR COMO EVIDENCIA"
    STATE["fuentes"] = "Generador interno para comprobar interfaz."
    STATE["modelo"] = None
    return _status(), STATE["base"].head(25), gr.update(choices=sorted(STATE["base"]["municipio"].unique()), value="Zimapán")

def actualizar_datos_reales(url_efipem=""):
    msgs = []
    coneval, src_c = descargar_coneval(force=True)
    msgs.append(src_c)
    efipem, src_e = descargar_efipem(force=True, url_directa=url_efipem.strip() or None)
    msgs.append(src_e)
    base = construir_base_maestra(efipem, coneval)
    base["__modo__"] = "REAL"
    base.to_csv(DATA_DIR / "base_maestra_hidalgo.csv", index=False, encoding="utf-8-sig")
    STATE["base"] = base
    STATE["modo"] = "DATOS OFICIALES"
    STATE["fuentes"] = " | ".join(msgs)
    STATE["modelo"] = None
    return _status(), base.head(50), gr.update(choices=sorted(base["municipio"].dropna().unique()), value="Zimapán")

def cargar_archivo_efipem(file):
    if file is None:
        raise gr.Error("Selecciona un archivo EFIPEM CSV o ZIP.")
    coneval, src_c = descargar_coneval(force=False)
    efipem = cargar_efipem_desde_archivo(file)
    base = construir_base_maestra(efipem, coneval)
    base["__modo__"] = "REAL"
    base.to_csv(DATA_DIR / "base_maestra_hidalgo.csv", index=False, encoding="utf-8-sig")
    STATE["base"] = base
    STATE["modo"] = "DATOS OFICIALES"
    STATE["fuentes"] = f"{src_c} | EFIPEM cargado manualmente: {Path(file).name}"
    STATE["modelo"] = None
    return _status(), base.head(50), gr.update(choices=sorted(base["municipio"].dropna().unique()), value="Zimapán")

def cargar_cache():
    p = DATA_DIR / "base_maestra_hidalgo.csv"
    if not p.exists():
        raise gr.Error("No existe base maestra local. Actualiza datos o usa el modo demo.")
    base = pd.read_csv(p)
    STATE["base"] = base
    STATE["modo"] = "DATOS OFICIALES (CACHE LOCAL)"
    STATE["fuentes"] = "Base maestra previamente construida."
    STATE["modelo"] = None
    return _status(), base.head(50), gr.update(choices=sorted(base["municipio"].dropna().unique()), value="Zimapán")

def tabla_filtrada(municipio):
    if STATE["base"] is None:
        return pd.DataFrame()
    d = STATE["base"]
    if municipio:
        d = d[d["municipio"] == municipio]
    cols = [c for c in [
        "municipio","anio","autonomia_financiera","dependencia_transferencias",
        "ingresos_propios","transferencias_total","gasto_total_calc",
        "g_servicios_personales_pct","g_servicios_generales_pct",
        "g_inversion_publica_pct","pobreza_pct","pobreza_extrema_pct",
        "carencia_servicios_basicos_pct","rezago_educativo_pct","__modo__"
    ] if c in d.columns]
    return d[cols].sort_values("anio", ascending=False)

def diagnostico(municipio, anio):
    if STATE["base"] is None:
        raise gr.Error("Primero carga datos.")
    d = STATE["base"]
    dm = d[d["municipio"] == municipio].copy()
    if dm.empty:
        raise gr.Error("Municipio sin datos.")
    if anio is None:
        anio = int(dm["anio"].max())
    f = dm[dm["anio"] == int(anio)]
    if f.empty:
        f = dm.sort_values("anio").tail(1)
    r = f.iloc[0]

    def pct(x):
        return "N/D" if pd.isna(x) else f"{100*x:.1f}%" if abs(x) <= 1.2 else f"{x:.1f}%"
    auto = r.get("autonomia_financiera", np.nan)
    dep = r.get("dependencia_transferencias", np.nan)
    pobreza = r.get("pobreza_pct", np.nan)
    inv = r.get("g_inversion_publica_pct", np.nan)

    peers = d[d["anio"] == int(r["anio"])]
    p_auto = percentil_serie(peers.get("autonomia_financiera", pd.Series(dtype=float)), auto)

    md = f"""## {municipio} — {int(r['anio'])}

| Indicador | Valor |
|---|---:|
| Autonomía financiera | {pct(auto)} |
| Dependencia de transferencias | {pct(dep)} |
| Inversión pública / gasto | {pct(inv)} |
| Pobreza | {pct(pobreza)} |
| Percentil estatal de autonomía | {"N/D" if pd.isna(p_auto) else f"{p_auto:.0f}"} |

> Los indicadores son descriptivos. No implican causalidad.
"""
    # Evolución
    plot_cols = [c for c in ["autonomia_financiera","dependencia_transferencias"] if c in dm.columns]
    if plot_cols:
        long = dm[["anio"]+plot_cols].melt("anio", var_name="indicador", value_name="valor")
        fig1 = px.line(long, x="anio", y="valor", color="indicador", markers=True,
                       title="Evolución financiera")
    else:
        fig1 = go.Figure()

    gasto_cols = [c for c in [
        "g_servicios_personales_pct","g_materiales_suministros_pct","g_servicios_generales_pct",
        "g_transferencias_ayudas_pct","g_bienes_muebles_pct","g_inversion_publica_pct","g_deuda_publica_pct"
    ] if c in f.columns]
    gb = pd.DataFrame({"categoria":gasto_cols, "porcentaje":[r.get(c,np.nan) for c in gasto_cols]}).dropna()
    fig2 = px.bar(gb, x="categoria", y="porcentaje", title="Composición del gasto") if len(gb) else go.Figure()
    return md, fig1, fig2, tabla_filtrada(municipio), gr.update(value=int(r["anio"]))

def entrenar(objetivo):
    if STATE["base"] is None:
        raise gr.Error("Primero carga datos.")
    if STATE["modo"] and "DEMO" in STATE["modo"]:
        aviso = "\n\n⚠️ **Modelo entrenado con datos sintéticos. Sólo prueba técnica.**"
    else:
        aviso = ""
    m = entrenar_modelo(STATE["base"], objetivo)
    STATE["modelo"] = m
    md = f"""## Modelo entrenado
**Objetivo:** {m.objetivo_nombre}  
**Observaciones:** {m.n}  
**MAE de validación cruzada:** {m.mae_cv:.2f} puntos porcentuales  
**R² dentro de muestra:** {m.r2_fit:.3f}

La métrica principal para V1 es el MAE de validación. El R² dentro de muestra no debe interpretarse como prueba de causalidad.{aviso}
"""
    fig = px.bar(m.importancias.head(12).sort_values("importancia"),
                 x="importancia", y="variable", orientation="h",
                 title="Importancia relativa de variables")
    return md, m.importancias, fig

def _fila(mun, anio):
    d = STATE["base"]
    dm = d[d["municipio"] == mun]
    f = dm[dm["anio"] == int(anio)] if anio is not None else pd.DataFrame()
    if f.empty:
        f = dm.sort_values("anio").tail(1)
    if f.empty:
        raise gr.Error("No hay datos para el municipio.")
    return f.iloc[0].to_dict()

def simular(mun, anio, n):
    if STATE["modelo"] is None:
        raise gr.Error("Entrena un modelo primero.")
    fila = _fila(mun, anio)
    sim = monte_carlo(STATE["modelo"], fila, int(n))
    base_pred = predecir(STATE["modelo"], fila)
    q05,q50,q95 = np.quantile(sim,[.05,.5,.95])
    resumen = f"""## Simulación Monte Carlo
**Predicción central:** {base_pred:.2f}  
**Media simulada:** {sim.mean():.2f}  
**Mediana:** {q50:.2f}  
**Intervalo P5–P95:** {q05:.2f} – {q95:.2f}  
**Desviación estándar:** {sim.std():.2f}  
**Iteraciones:** {len(sim):,}

La distribución refleja incertidumbre predictiva aproximada mediante remuestreo de residuos; no es una distribución causal.
"""
    fig = px.histogram(pd.DataFrame({"resultado":sim}), x="resultado", nbins=45,
                       title=f"Distribución simulada — {STATE['modelo'].objetivo_nombre}")
    return resumen, fig

def optimizar_ui(mun, anio):
    if STATE["modelo"] is None:
        raise gr.Error("Entrena un modelo primero.")
    fila = _fila(mun, anio)
    pred_actual = predecir(STATE["modelo"], fila)
    nueva, pred_opt, tabla = optimizar(STATE["modelo"], fila)
    mejora = pred_actual - pred_opt
    md = f"""## Escenario matemáticamente optimizado
**Resultado estimado actual:** {pred_actual:.2f}  
**Resultado estimado optimizado:** {pred_opt:.2f}  
**Reducción estimada del indicador:** {mejora:.2f} puntos

> Esta solución minimiza el indicador seleccionado **dentro del modelo**, manteniendo constante la suma de las categorías controladas y limitando cada cambio. No constituye una recomendación presupuestaria causal ni jurídica.
"""
    long = tabla.melt("categoria", value_vars=["actual_pct","optimizado_pct"],
                      var_name="escenario", value_name="porcentaje")
    fig = px.bar(long, x="categoria", y="porcentaje", color="escenario", barmode="group",
                 title="Estructura observada vs. escenario optimizado")
    return md, tabla, fig

def scatter_global(xvar, yvar):
    if STATE["base"] is None:
        return go.Figure()
    d = STATE["base"].dropna(subset=[xvar,yvar]).copy()
    return px.scatter(d, x=xvar, y=yvar, color="anio", hover_name="municipio",
                      trendline=None, title=f"{yvar} vs {xvar}")

CSS = """
.gradio-container {max-width: 1400px !important;}
.simup-title {text-align:center;}
.warning {border-left: 5px solid #b45309; padding: 10px;}
"""

with gr.Blocks(title=APP_TITLE) as demo:
    gr.Markdown(f"# {APP_TITLE}\n## {APP_SUBTITLE}\n**Versión inicial para Hidalgo**")
    status = gr.Markdown(_status())

    with gr.Tab("Inicio"):
        gr.Markdown("""
### ¿Qué hace esta versión?
1. Integra finanzas municipales de **INEGI–EFIPEM** y pobreza municipal de **CONEVAL**.
2. Construye indicadores de autonomía, dependencia y composición del gasto.
3. Genera tablas y gráficas municipales.
4. Entrena un modelo predictivo exploratorio.
5. Ejecuta simulación Monte Carlo.
6. Busca un escenario presupuestario matemáticamente optimizado.
7. Mantiene separado el **diagnóstico**, la **predicción** y la **recomendación pública**.

**Advertencia metodológica:** SIMUP-M 1.0 es un sistema de apoyo al análisis. Los modelos de esta versión identifican asociaciones predictivas y no prueban efectos causales.
""")

    with gr.Tab("Datos"):
        with gr.Row():
            btn_real = gr.Button("Actualizar datos oficiales", variant="primary")
            btn_cache = gr.Button("Cargar base local")
            btn_demo = gr.Button("Modo demo sintético")
        url_efipem = gr.Textbox(label="URL directa EFIPEM (opcional)",
                                placeholder="Déjala vacía para intentar autodetección desde INEGI")
        upload = gr.File(label="O carga manualmente el CSV/ZIP oficial de EFIPEM",
                         file_types=[".csv",".zip",".xlsx"])
        btn_upload = gr.Button("Construir base con archivo cargado")
        tabla_datos = gr.Dataframe(label="Vista previa", interactive=False, wrap=True)
        gr.Markdown("""
**Fuentes principales**
- INEGI — Estadística de Finanzas Públicas Estatales y Municipales (EFIPEM).
- CONEVAL — Medición de pobreza municipal 2010, 2015 y 2020.

La descarga automática de EFIPEM depende de que el sitio de INEGI exponga el archivo en el HTML público. Si INEGI cambia su estructura, carga el CSV/ZIP descargado desde la sección Datos abiertos.
""")

    with gr.Tab("Diagnóstico"):
        with gr.Row():
            mun = gr.Dropdown(choices=list(MUNICIPIOS_HIDALGO.values()), value="Zimapán", label="Municipio")
            anio = gr.Number(value=2020, precision=0, label="Año")
            btn_diag = gr.Button("Generar diagnóstico", variant="primary")
        diag_md = gr.Markdown()
        with gr.Row():
            diag_line = gr.Plot()
            diag_bar = gr.Plot()
        diag_table = gr.Dataframe(interactive=False, wrap=True)

    with gr.Tab("Modelo"):
        objetivo = gr.Dropdown(choices=list(OBJETIVOS.keys()), value="Pobreza (%)", label="Variable objetivo")
        btn_train = gr.Button("Entrenar / actualizar modelo", variant="primary")
        model_md = gr.Markdown()
        imp_table = gr.Dataframe(interactive=False)
        imp_plot = gr.Plot()

    with gr.Tab("Simulación Monte Carlo"):
        with gr.Row():
            mun_sim = gr.Dropdown(choices=list(MUNICIPIOS_HIDALGO.values()), value="Zimapán", label="Municipio")
            anio_sim = gr.Number(value=2020, precision=0, label="Año")
            n_sim = gr.Slider(1000, 20000, value=MONTE_CARLO_DEFAULT, step=1000, label="Iteraciones")
        btn_sim = gr.Button("Simular", variant="primary")
        sim_md = gr.Markdown()
        sim_plot = gr.Plot()

    with gr.Tab("Optimización"):
        with gr.Row():
            mun_opt = gr.Dropdown(choices=list(MUNICIPIOS_HIDALGO.values()), value="Zimapán", label="Municipio")
            anio_opt = gr.Number(value=2020, precision=0, label="Año")
        btn_opt = gr.Button("Buscar escenario optimizado", variant="primary")
        opt_md = gr.Markdown()
        opt_table = gr.Dataframe(interactive=False)
        opt_plot = gr.Plot()

    with gr.Tab("Exploración global"):
        with gr.Row():
            xvar = gr.Dropdown(
                choices=["autonomia_financiera","dependencia_transferencias",
                         "g_inversion_publica_pct","g_servicios_personales_pct"],
                value="autonomia_financiera", label="Eje X")
            yvar = gr.Dropdown(
                choices=["pobreza_pct","pobreza_extrema_pct",
                         "carencia_servicios_basicos_pct","rezago_educativo_pct"],
                value="pobreza_pct", label="Eje Y")
        btn_scatter = gr.Button("Graficar")
        scatter = gr.Plot()

    with gr.Tab("Metodología y límites"):
        gr.Markdown("""
### Estructura analítica de SIMUP-M 1.0

**Entradas financieras**
- Autonomía financiera = ingresos propios / ingresos totales calculados.
- Dependencia de transferencias = transferencias / ingresos totales calculados.
- Participación del gasto en servicios personales, materiales, servicios generales, transferencias/ayudas, bienes, inversión pública y deuda.

**Resultados sociales iniciales**
- Pobreza.
- Pobreza extrema.
- Carencia de servicios básicos.
- Rezago educativo.

### Lo que NO debe inferirse
Una asociación entre inversión pública y pobreza no significa que modificar el presupuesto produzca causalmente el cambio estimado. Los escenarios de V1 son **exploratorios y predictivos**.

### Evolución prevista
- V1.1: validación detallada del mapeo EFIPEM y serie financiera extendida.
- V1.2: pesos constantes e INPC.
- V1.3: datos de panel con rezagos.
- V2: optimización multiobjetivo y frontera de Pareto.
""")

    btn_demo.click(cargar_demo, outputs=[status, tabla_datos, mun])
    btn_cache.click(cargar_cache, outputs=[status, tabla_datos, mun])
    btn_real.click(actualizar_datos_reales, inputs=[url_efipem], outputs=[status, tabla_datos, mun])
    btn_upload.click(cargar_archivo_efipem, inputs=[upload], outputs=[status, tabla_datos, mun])

    btn_diag.click(diagnostico, inputs=[mun, anio],
                   outputs=[diag_md, diag_line, diag_bar, diag_table, anio])
    btn_train.click(entrenar, inputs=[objetivo], outputs=[model_md, imp_table, imp_plot])
    btn_sim.click(simular, inputs=[mun_sim, anio_sim, n_sim], outputs=[sim_md, sim_plot])
    btn_opt.click(optimizar_ui, inputs=[mun_opt, anio_opt], outputs=[opt_md, opt_table, opt_plot])
    btn_scatter.click(scatter_global, inputs=[xvar,yvar], outputs=[scatter])

if __name__ == "__main__":
    demo.launch(css=CSS)
