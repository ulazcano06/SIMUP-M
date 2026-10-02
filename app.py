import os
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import gradio as gr
from config import APP_TITLE,APP_SUBTITLE,VERSION,DATA_DIR
from municipios import MUNICIPIOS_HIDALGO
from demo import crear_demo
from evaluation import evaluar

STATE={"base":None,"modo":"Sin datos"}

def status():
    return f"**Estado:** {STATE['modo']}" if STATE['base'] is None else f"**Estado:** {STATE['modo']} · {len(STATE['base'])} registros"

def cargar_demo():
    STATE['base']=crear_demo(); STATE['modo']='DEMO SINTÉTICO — NO USAR COMO EVIDENCIA'
    return status(),STATE['base'].head(20),gr.update(choices=sorted(STATE['base'].municipio.unique()),value='Zimapán')

def cargar_base(file):
    if file is None: raise gr.Error('Selecciona un CSV o XLSX.')
    p=Path(file)
    df=pd.read_csv(p) if p.suffix.lower()=='.csv' else pd.read_excel(p)
    req={'municipio','anio'}
    if not req.issubset(df.columns): raise gr.Error('La base debe incluir al menos municipio y anio.')
    STATE['base']=df; STATE['modo']='BASE CARGADA POR EL USUARIO'
    return status(),df.head(20),gr.update(choices=sorted(df.municipio.dropna().astype(str).unique()),value=str(df.municipio.iloc[0]))

def fila_mun(mun):
    if STATE['base'] is None: raise gr.Error('Carga una base o activa el modo demo.')
    d=STATE['base'][STATE['base'].municipio.astype(str)==str(mun)]
    if d.empty: raise gr.Error('Municipio no encontrado.')
    return d.sort_values('anio').iloc[-1]

def diagnostico(mun):
    f=fila_mun(mun)
    campos=['rezago_educativo_pct','escolaridad_anios','analfabetismo_pct','cobertura_educativa_pct','pobreza_pct','pobreza_extrema_pct','ingresos_municipales','ingresos_propios','gasto_publico','inversion_publica']
    labels=['Rezago educativo (%)','Escolaridad (años)','Analfabetismo (%)','Cobertura educativa (%)','Pobreza (%)','Pobreza extrema (%)','Ingresos municipales','Ingresos propios','Gasto público','Inversión pública']
    t=pd.DataFrame({'Indicador':labels,'Valor':[f.get(c,None) for c in campos]})
    return f"## {mun}\n**Año:** {int(f.get('anio',0))} · **Población:** {int(f.get('poblacion',0)):,}",t

def simular(mun,nombre,costo,benef,duracion,cambio):
    f=fila_mun(mun); costo=float(costo or 0); benef=float(benef or 0); duracion=float(duracion or 1); cambio=float(cambio or 0)
    tabla,iee,sema=evaluar(f,costo,benef,duracion,cambio)
    actual=float(f.get('rezago_educativo_pct',0)); sim=max(0,actual-cambio)
    fig=go.Figure(go.Bar(x=['Actual','Escenario'],y=[actual,sim])); fig.update_layout(title='Rezago educativo: línea base vs. escenario',yaxis_title='%')
    md=f"""## Resultado — {nombre or 'Escenario'}
**Municipio:** {mun}  
**IEE prototipo:** {iee:.1f}/100 · **{sema}**  
**Rezago educativo base:** {actual:.2f}% → **escenario parametrizado:** {sim:.2f}%

> **Advertencia:** en V0.2 el cambio de rezago es un parámetro introducido por el usuario y el IEE usa reglas provisionales/pesos iguales. No es una estimación causal ni un resultado validado para la tesis.
"""
    return md,tabla,fig

with gr.Blocks(title=APP_TITLE) as app:
    gr.Markdown(f"# {APP_TITLE}\n### {APP_SUBTITLE}\n**{VERSION} — Hidalgo**")
    st=gr.Markdown(status())
    with gr.Tab('Inicio'):
        gr.Markdown('''### Flujo de trabajo\n**Diagnóstico → propuesta → escenario → evaluación multidimensional → semáforo → reporte.**\n\nEsta versión sirve para desarrollar y probar la arquitectura. Los datos demo son sintéticos y las reglas del semáforo son provisionales.''')
    with gr.Tab('Datos'):
        with gr.Row():
            bdem=gr.Button('Cargar demo sintético',variant='secondary')
            up=gr.File(label='Cargar base CSV/XLSX',file_types=['.csv','.xlsx'])
            bup=gr.Button('Cargar archivo',variant='primary')
        preview=gr.Dataframe(label='Vista previa',interactive=False)
    with gr.Tab('Diagnóstico'):
        mun=gr.Dropdown(choices=MUNICIPIOS_HIDALGO,value='Zimapán',label='Municipio')
        bdiag=gr.Button('Generar diagnóstico',variant='primary'); dmd=gr.Markdown(); dt=gr.Dataframe(interactive=False)
    with gr.Tab('Evaluar propuesta'):
        mun2=gr.Dropdown(choices=MUNICIPIOS_HIDALGO,value='Zimapán',label='Municipio')
        nombre=gr.Textbox(label='Nombre de la propuesta',value='Programa municipal de permanencia escolar')
        with gr.Row():
            costo=gr.Number(label='Costo total estimado ($)',value=2000000)
            benef=gr.Number(label='Beneficiarios estimados',value=500)
            dur=gr.Number(label='Duración (años)',value=3)
            cambio=gr.Number(label='Reducción de rezago planteada (puntos porcentuales)',value=3)
        bsim=gr.Button('Evaluar escenario',variant='primary'); smd=gr.Markdown(); stab=gr.Dataframe(interactive=False); spl=gr.Plot()
    with gr.Tab('Metodología y límites'):
        gr.Markdown('''### Estado metodológico de V0.2\n- El sistema es **exploratorio**, no causal.\n- El semáforo tiene cinco dimensiones: impacto educativo, desarrollo municipal, viabilidad financiera, cobertura y sostenibilidad.\n- Los pesos iguales y umbrales 70/45 son **solo de interfaz/prototipo**; deberán sustituirse por criterios validados.\n- El parámetro de cambio educativo no se interpreta como efecto demostrado de una política.\n- La siguiente fase debe integrar datos oficiales y estimar relaciones con el panel municipio-año.''')
    bdem.click(cargar_demo,outputs=[st,preview,mun]).then(lambda: gr.update(choices=sorted(STATE['base'].municipio.unique()),value='Zimapán'),outputs=mun2)
    bup.click(cargar_base,inputs=up,outputs=[st,preview,mun]).then(lambda: gr.update(choices=sorted(STATE['base'].municipio.astype(str).unique()),value=str(STATE['base'].municipio.iloc[0])),outputs=mun2)
    bdiag.click(diagnostico,inputs=mun,outputs=[dmd,dt])
    bsim.click(simular,inputs=[mun2,nombre,costo,benef,dur,cambio],outputs=[smd,stab,spl])

if __name__=='__main__':
    app.launch(server_name='0.0.0.0',server_port=int(os.environ.get('PORT',7860)))
