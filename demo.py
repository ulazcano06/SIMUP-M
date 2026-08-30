import numpy as np
import pandas as pd
from municipios import MUNICIPIOS_HIDALGO
from config import RANDOM_STATE

def crear_demo():
    """
    Datos SINTÉTICOS. Sólo sirven para probar la interfaz sin internet.
    Nunca deben usarse como evidencia de tesis.
    """
    rng = np.random.default_rng(RANDOM_STATE)
    rows = []
    for year in [2010, 2015, 2020]:
        for cve, mun in MUNICIPIOS_HIDALGO.items():
            pob = int(rng.lognormal(10.1, 0.7))
            autonomia = np.clip(rng.beta(2, 8), .02, .55)
            dep = np.clip(.90 - autonomia + rng.normal(0,.04), .25, .97)
            shares = rng.dirichlet([3.5,1.4,2.0,1.8,0.8,2.5,0.7])*100
            pobreza = np.clip(78 - 38*autonomia - .10*shares[5] + rng.normal(0,8), 15, 95)
            extrema = np.clip(pobreza*.22 + rng.normal(0,3), 1, 45)
            servicios = np.clip(pobreza*.55 + rng.normal(0,7), 2, 85)
            rezago = np.clip(pobreza*.28 + rng.normal(0,4), 2, 45)
            rows.append({
                "cve_mun": cve, "municipio":mun, "anio":year,
                "poblacion":pob, "log_poblacion":np.log1p(pob),
                "autonomia_financiera":autonomia,
                "dependencia_transferencias":dep,
                "ingresos_propios": autonomia*150_000_000,
                "transferencias_total": dep*150_000_000,
                "ingresos_totales_calc":150_000_000,
                "gasto_total_calc":145_000_000,
                "g_servicios_personales_pct":shares[0],
                "g_materiales_suministros_pct":shares[1],
                "g_servicios_generales_pct":shares[2],
                "g_transferencias_ayudas_pct":shares[3],
                "g_bienes_muebles_pct":shares[4],
                "g_inversion_publica_pct":shares[5],
                "g_deuda_publica_pct":shares[6],
                "pobreza_pct":pobreza,
                "pobreza_extrema_pct":extrema,
                "carencia_servicios_basicos_pct":servicios,
                "rezago_educativo_pct":rezago,
                "__modo__":"DEMO SINTÉTICO"
            })
    return pd.DataFrame(rows)
