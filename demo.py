import numpy as np, pandas as pd
from municipios import MUNICIPIOS_HIDALGO

def crear_demo(seed=42):
    rng=np.random.default_rng(seed); rows=[]
    for i,m in enumerate(MUNICIPIOS_HIDALGO):
        pob=int(rng.integers(5000,300000)); rez=float(rng.uniform(12,38)); esc=float(rng.uniform(5.5,11.5))
        pobreza=float(np.clip(25+1.15*rez-2.2*(esc-7)+rng.normal(0,8),12,88))
        rows.append(dict(cve_mun=f"13{i+1:03d}",municipio=m,anio=2020,poblacion=pob,rezago_educativo_pct=round(rez,2),escolaridad_anios=round(esc,2),analfabetismo_pct=round(rng.uniform(2,22),2),cobertura_educativa_pct=round(rng.uniform(55,96),2),pobreza_pct=round(pobreza,2),pobreza_extrema_pct=round(max(2,pobreza*rng.uniform(.08,.35)),2),rezago_social_indice=round(rng.normal(0,1),3),ingresos_municipales=round(pob*rng.uniform(3500,9000),2),ingresos_propios=round(pob*rng.uniform(250,1800),2),gasto_publico=round(pob*rng.uniform(3200,8500),2),inversion_publica=round(pob*rng.uniform(350,2400),2),__modo__="DEMO SINTÉTICO"))
    return pd.DataFrame(rows)
