import numpy as np, pandas as pd
DIM_COLS=["Impacto educativo","Desarrollo municipal","Viabilidad financiera","Cobertura","Sostenibilidad"]

def clamp(x,a=0,b=100): return float(np.clip(x,a,b))
def color(score):
    if score>=70: return "🟢 Verde"
    if score>=45: return "🟡 Amarillo"
    return "🔴 Rojo"

def evaluar(fila,costo,beneficiarios,duracion,cambio_rezago):
    pobl=max(float(fila.get("poblacion",1)),1); ingresos=max(float(fila.get("ingresos_municipales",1)),1)
    rez=max(float(fila.get("rezago_educativo_pct",0)),1)
    impacto=clamp(50 + 5*(cambio_rezago/rez*100))
    desarrollo=clamp(50 + 0.45*(impacto-50))
    carga=100*costo/ingresos
    financiera=clamp(100-4*carga)
    cobertura=clamp(100*beneficiarios/pobl)
    sosten=clamp(85-7*max(duracion-1,0)-1.5*carga)
    scores=dict(zip(DIM_COLS,[impacto,desarrollo,financiera,cobertura,sosten]))
    # Pesos iguales SOLO para prototipo; no son pesos validados para la tesis.
    iee=float(np.mean(list(scores.values())))
    tabla=pd.DataFrame({"Dimensión":DIM_COLS,"Puntuación prototipo":[round(scores[x],1) for x in DIM_COLS],"Semáforo":[color(scores[x]) for x in DIM_COLS]})
    return tabla,iee,color(iee)
