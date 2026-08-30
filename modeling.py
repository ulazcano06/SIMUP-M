import numpy as np
import pandas as pd
from dataclasses import dataclass
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold, cross_val_score
from sklearn.metrics import mean_absolute_error, r2_score
from scipy.optimize import minimize
import joblib

from config import DATA_DIR, RANDOM_STATE, MAX_CAMBIO_PP

FEATURES_BASE = [
    "autonomia_financiera",
    "dependencia_transferencias",
    "g_servicios_personales_pct",
    "g_materiales_suministros_pct",
    "g_servicios_generales_pct",
    "g_transferencias_ayudas_pct",
    "g_bienes_muebles_pct",
    "g_inversion_publica_pct",
    "g_deuda_publica_pct",
    "log_poblacion"
]

OBJETIVOS = {
    "Pobreza (%)": "pobreza_pct",
    "Pobreza extrema (%)": "pobreza_extrema_pct",
    "Carencia de servicios básicos (%)": "carencia_servicios_basicos_pct",
    "Rezago educativo (%)": "rezago_educativo_pct"
}

@dataclass
class ModeloSIMUP:
    objetivo_nombre: str
    objetivo_col: str
    pipeline: object
    features: list
    mae_cv: float
    r2_fit: float
    residuals: np.ndarray
    n: int
    importancias: pd.DataFrame

def _pipeline_rf():
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", RandomForestRegressor(
            n_estimators=500,
            min_samples_leaf=3,
            max_features=0.8,
            random_state=RANDOM_STATE
        ))
    ])

def _pipeline_ridge():
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", Ridge(alpha=2.0))
    ])

def entrenar_modelo(base, objetivo_nombre="Pobreza (%)"):
    objetivo = OBJETIVOS[objetivo_nombre]
    if objetivo not in base.columns:
        raise ValueError(f"La base no contiene el objetivo: {objetivo}")

    features = [f for f in FEATURES_BASE if f in base.columns]
    d = base.dropna(subset=[objetivo]).copy()
    # Para una V1 exigimos al menos 25 observaciones reales.
    if len(d) < 25:
        raise ValueError(
            f"Hay {len(d)} observaciones con {objetivo}. "
            "Se requieren al menos 25 para entrenar la versión inicial."
        )
    X = d[features]
    y = pd.to_numeric(d[objetivo], errors="coerce")
    ok = y.notna()
    X, y = X.loc[ok], y.loc[ok]

    n_splits = min(5, max(3, len(y)//20))
    cv = KFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_STATE)

    candidatos = {"Random Forest": _pipeline_rf(), "Ridge": _pipeline_ridge()}
    resultados = {}
    for nombre, pipe in candidatos.items():
        scores = -cross_val_score(pipe, X, y, scoring="neg_mean_absolute_error", cv=cv)
        resultados[nombre] = (scores.mean(), pipe)

    mejor_nombre = min(resultados, key=lambda k: resultados[k][0])
    mae, pipe = resultados[mejor_nombre]
    pipe.fit(X, y)
    pred = pipe.predict(X)
    residuals = np.asarray(y - pred)
    r2 = r2_score(y, pred)

    model = pipe.named_steps["model"]
    if hasattr(model, "feature_importances_"):
        imp = model.feature_importances_
    elif hasattr(model, "coef_"):
        imp = np.abs(np.asarray(model.coef_))
    else:
        imp = np.zeros(len(features))
    imp_df = pd.DataFrame({"variable":features, "importancia":imp}).sort_values("importancia", ascending=False)

    out = ModeloSIMUP(
        objetivo_nombre=objetivo_nombre,
        objetivo_col=objetivo,
        pipeline=pipe,
        features=features,
        mae_cv=float(mae),
        r2_fit=float(r2),
        residuals=residuals,
        n=len(y),
        importancias=imp_df
    )
    joblib.dump(out, DATA_DIR / "modelo_simup.joblib")
    return out

def predecir(modelo, fila):
    X = pd.DataFrame([{f: fila.get(f, np.nan) for f in modelo.features}])
    return float(modelo.pipeline.predict(X)[0])

def monte_carlo(modelo, fila, n=5000, seed=RANDOM_STATE):
    rng = np.random.default_rng(seed)
    centro = predecir(modelo, fila)
    if len(modelo.residuals) >= 5:
        ruido = rng.choice(modelo.residuals, size=int(n), replace=True)
    else:
        ruido = rng.normal(0, modelo.mae_cv if modelo.mae_cv > 0 else 1.0, size=int(n))
    sim = centro + ruido
    # Indicadores porcentuales se acotan a 0-100.
    if modelo.objetivo_col.endswith("_pct"):
        sim = np.clip(sim, 0, 100)
    return sim

GASTO_FEATURES = [
    "g_servicios_personales_pct",
    "g_materiales_suministros_pct",
    "g_servicios_generales_pct",
    "g_transferencias_ayudas_pct",
    "g_bienes_muebles_pct",
    "g_inversion_publica_pct",
    "g_deuda_publica_pct",
]

def optimizar(modelo, fila, cambio_max_pp=MAX_CAMBIO_PP):
    presentes = [g for g in GASTO_FEATURES if g in modelo.features and pd.notna(fila.get(g))]
    if len(presentes) < 3:
        raise ValueError("No hay suficientes participaciones de gasto disponibles para optimizar.")

    x0 = np.array([float(fila[g]) for g in presentes], dtype=float)
    total = x0.sum()
    if total <= 0:
        raise ValueError("Las participaciones de gasto son inválidas.")

    # Conservamos el total observado de las categorías controladas.
    bounds = [(max(0, v-cambio_max_pp), min(100, v+cambio_max_pp)) for v in x0]

    def obj(x):
        nueva = dict(fila)
        for g, v in zip(presentes, x):
            nueva[g] = float(v)
        # Objetivos disponibles son carencias: menor es mejor.
        return predecir(modelo, nueva)

    cons = {"type":"eq", "fun": lambda x: x.sum() - total}
    res = minimize(obj, x0, method="SLSQP", bounds=bounds, constraints=[cons],
                   options={"maxiter":500, "ftol":1e-8})
    if not res.success:
        raise RuntimeError("La optimización no convergió: " + str(res.message))

    nueva = dict(fila)
    for g, v in zip(presentes, res.x):
        nueva[g] = float(v)
    return nueva, float(obj(res.x)), pd.DataFrame({
        "categoria": presentes,
        "actual_pct": x0,
        "optimizado_pct": res.x,
        "cambio_pp": res.x-x0
    })
