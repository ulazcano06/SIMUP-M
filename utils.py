import re
import unicodedata
from pathlib import Path
import pandas as pd
import numpy as np

def normaliza_texto(s):
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s)
    return s

def normaliza_columna(c):
    c = normaliza_texto(c)
    c = re.sub(r"[^a-z0-9]+", "_", c).strip("_")
    return c

def limpiar_columnas(df):
    out = df.copy()
    out.columns = [normaliza_columna(c) for c in out.columns]
    return out

def a_numero(s):
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce")
    return pd.to_numeric(
        s.astype(str)
         .str.replace(",", "", regex=False)
         .str.replace("$", "", regex=False)
         .str.replace("%", "", regex=False)
         .str.strip(),
        errors="coerce"
    )

def busca_columna(cols, patrones, obligatoria=False):
    ncols = {c: normaliza_texto(c) for c in cols}
    for p in patrones:
        p = normaliza_texto(p)
        for original, norm in ncols.items():
            if p == norm or p in norm:
                return original
    if obligatoria:
        raise ValueError(f"No se encontró columna compatible con: {patrones}")
    return None

def percentil_serie(serie, valor):
    s = pd.to_numeric(serie, errors="coerce").dropna()
    if len(s) == 0 or pd.isna(valor):
        return np.nan
    return float((s <= float(valor)).mean() * 100)

def guardar_csv(df, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path
