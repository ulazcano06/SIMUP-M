import io
import os
import re
import zipfile
import tempfile
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

from config import (
    DATA_DIR, INEGI_EFIPEM_LANDING, CONEVAL_POBREZA_ZIP,
    ENTIDAD_OBJETIVO, CVE_ENTIDAD, ANIOS_SOCIALES
)
from utils import limpiar_columnas, normaliza_texto, normaliza_columna, a_numero, busca_columna
from municipios import MUNICIPIOS_HIDALGO

HEADERS = {"User-Agent": "Mozilla/5.0 SIMUP-M/1.0"}

def _get(url, timeout=60):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r

def _read_tabular_bytes(name, content):
    lname = name.lower()
    if lname.endswith(".csv"):
        for enc in ("utf-8-sig", "latin1", "utf-8"):
            try:
                return pd.read_csv(io.BytesIO(content), encoding=enc, low_memory=False)
            except Exception:
                pass
        return pd.read_csv(io.BytesIO(content), low_memory=False)
    if lname.endswith((".xlsx", ".xls")):
        xls = pd.ExcelFile(io.BytesIO(content))
        frames = []
        for sh in xls.sheet_names:
            try:
                d = pd.read_excel(xls, sheet_name=sh)
                d["__hoja__"] = sh
                frames.append(d)
            except Exception:
                continue
        if not frames:
            raise ValueError(f"No fue posible leer {name}")
        return pd.concat(frames, ignore_index=True, sort=False)
    raise ValueError(f"Formato no soportado: {name}")

def _extract_tables_from_zip(content):
    out = []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for name in z.namelist():
            if name.lower().endswith((".csv", ".xlsx", ".xls")) and not name.startswith("__MACOSX"):
                try:
                    out.append((name, _read_tabular_bytes(name, z.read(name))))
                except Exception:
                    continue
    return out

def descargar_coneval(force=False):
    cache = DATA_DIR / "coneval_municipal_hidalgo.csv"
    if cache.exists() and not force:
        return pd.read_csv(cache), f"Cache local: {cache.name}"

    r = _get(CONEVAL_POBREZA_ZIP)
    tablas = _extract_tables_from_zip(r.content)
    if not tablas:
        raise RuntimeError("El ZIP de CONEVAL no contiene tablas legibles.")

    candidatas = []
    for name, df in tablas:
        d = limpiar_columnas(df)
        score = 0
        joined = " ".join(d.columns)
        for palabra in ["municip", "pobreza", "pobre", "entidad", "clave"]:
            score += joined.count(palabra)
        candidatas.append((score, name, d))
    candidatas.sort(key=lambda x: x[0], reverse=True)
    raw = candidatas[0][2]

    entidad_col = busca_columna(raw.columns, ["entidad_federativa", "entidad", "nom_ent"])
    cve_ent_col = busca_columna(raw.columns, ["cve_ent", "clave_entidad", "ent"])
    municipio_col = busca_columna(raw.columns, ["municipio", "nom_mun", "nombre_municipio"])
    cve_mun_col = busca_columna(raw.columns, ["cve_mun", "clave_municipio", "mun"])
    anio_col = busca_columna(raw.columns, ["anio", "año"])

    d = raw.copy()
    mask = pd.Series(True, index=d.index)
    if cve_ent_col is not None:
        ce = d[cve_ent_col].astype(str).str.extract(r"(\d+)")[0].str.zfill(2)
        mask &= ce.eq(CVE_ENTIDAD)
    elif entidad_col is not None:
        mask &= d[entidad_col].astype(str).map(normaliza_texto).str.contains("hidalgo", na=False)

    d = d[mask].copy()

    if municipio_col is None and cve_mun_col is not None:
        cm = d[cve_mun_col].astype(str).str.extract(r"(\d+)")[0].str[-3:].str.zfill(3)
        d["municipio"] = cm.map(MUNICIPIOS_HIDALGO)
        municipio_col = "municipio"
    elif municipio_col is not None:
        d["municipio"] = d[municipio_col].astype(str).str.strip()
        municipio_col = "municipio"

    if cve_mun_col is not None:
        d["cve_mun"] = d[cve_mun_col].astype(str).str.extract(r"(\d+)")[0].str[-3:].str.zfill(3)
    else:
        inv = {normaliza_texto(v): k for k, v in MUNICIPIOS_HIDALGO.items()}
        d["cve_mun"] = d["municipio"].map(lambda x: inv.get(normaliza_texto(x)))

    # CONEVAL puede venir en formato ancho (indicadores 2010/2015/2020)
    # o largo. Normalizamos ambos.
    if anio_col is not None:
        d["anio"] = pd.to_numeric(d[anio_col], errors="coerce").astype("Int64")
        largo = d
    else:
        id_cols = [c for c in ["cve_mun", "municipio"] if c in d.columns]
        rows = []
        for _, row in d.iterrows():
            base = {c: row[c] for c in id_cols}
            por_anio = {a: dict(base, anio=a) for a in ANIOS_SOCIALES}
            for col in d.columns:
                m = re.search(r"(2010|2015|2020)", col)
                if not m:
                    continue
                a = int(m.group(1))
                nuevo = re.sub(r"_?(2010|2015|2020).*", "", col).strip("_")
                if nuevo:
                    por_anio[a][nuevo] = row[col]
            rows.extend(por_anio.values())
        largo = pd.DataFrame(rows)

    largo = limpiar_columnas(largo)

    # Mapeo flexible de indicadores.
    aliases = {
        "pobreza_pct": [
            r"^pobreza$", r"pobreza_porcentaje", r"pobreza_pct",
            r"porcentaje.*pobreza", r"pobreza.*porc"
        ],
        "pobreza_extrema_pct": [
            r"pobreza_extrema", r"porcentaje.*pobreza_extrema"
        ],
        "carencia_servicios_basicos_pct": [
            r"servicios_basicos", r"carencia.*servicios_basicos"
        ],
        "rezago_educativo_pct": [
            r"rezago_educativo"
        ],
        "carencia_salud_pct": [
            r"acceso.*salud", r"carencia.*salud"
        ],
        "carencia_seguridad_social_pct": [
            r"seguridad_social"
        ],
        "carencia_vivienda_pct": [
            r"calidad.*espacios.*vivienda", r"carencia.*vivienda"
        ],
        "carencia_alimentacion_pct": [
            r"aliment", r"carencia.*aliment"
        ],
        "poblacion": [
            r"poblacion_total", r"pobtot", r"poblacion"
        ]
    }

    final = largo[[c for c in ["cve_mun","municipio","anio"] if c in largo.columns]].copy()
    for nuevo, pats in aliases.items():
        encontrado = None
        for c in largo.columns:
            nc = normaliza_texto(c).replace(" ", "_")
            if any(re.search(p, nc) for p in pats):
                # Evita columnas de número de personas cuando buscamos porcentaje.
                if nuevo.endswith("_pct") and any(k in nc for k in ["personas", "poblacion_", "numero"]):
                    continue
                encontrado = c
                break
        if encontrado:
            final[nuevo] = a_numero(largo[encontrado])

    final = final[final["anio"].isin(ANIOS_SOCIALES)].copy()
    final = final.dropna(subset=["municipio", "anio"]).drop_duplicates(["municipio","anio"])
    final.to_csv(cache, index=False, encoding="utf-8-sig")
    return final, "CONEVAL: Medición de pobreza municipal 2010, 2015 y 2020"

def _links_in_page(url):
    html = _get(url).text
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        links.append(urljoin(url, a["href"]))
    # También inspeccionamos el HTML por URLs incrustadas en scripts.
    for m in re.findall(r'https?://[^"\'\s<>]+', html):
        links.append(m.replace("\\/", "/"))
    return list(dict.fromkeys(links))

def descubrir_url_efipem():
    links = _links_in_page(INEGI_EFIPEM_LANDING)
    candidatos = []
    for u in links:
        lu = u.lower()
        if any(ext in lu for ext in [".zip", ".csv"]) and any(k in lu for k in ["finanz", "efipem", "municip"]):
            score = 0
            score += 4 if "municip" in lu else 0
            score += 2 if "efipem" in lu or "finanz" in lu else 0
            score += 1 if ".zip" in lu else 0
            candidatos.append((score, u))
    if not candidatos:
        return None
    candidatos.sort(reverse=True)
    return candidatos[0][1]

def cargar_efipem_desde_archivo(path):
    path = Path(path)
    content = path.read_bytes()
    if path.suffix.lower() == ".zip":
        tablas = _extract_tables_from_zip(content)
        if not tablas:
            raise ValueError("El ZIP no contiene CSV/XLSX legibles.")
        # Preferimos tabla municipal.
        tablas.sort(key=lambda x: ("municip" in x[0].lower(), len(x[1])), reverse=True)
        df = tablas[0][1]
    else:
        df = _read_tabular_bytes(path.name, content)
    return normalizar_efipem(df)

def descargar_efipem(force=False, url_directa=None):
    cache = DATA_DIR / "efipem_hidalgo.csv"
    if cache.exists() and not force:
        return pd.read_csv(cache), f"Cache local: {cache.name}"

    url = url_directa or descubrir_url_efipem()
    if not url:
        raise RuntimeError(
            "No fue posible descubrir automáticamente el archivo de datos abiertos EFIPEM. "
            "Carga el CSV/ZIP oficial desde la pestaña Datos o pega su URL directa."
        )
    r = _get(url)
    name = url.split("?")[0].split("/")[-1] or "efipem.zip"
    if ".zip" in name.lower():
        tablas = _extract_tables_from_zip(r.content)
        tablas.sort(key=lambda x: ("municip" in x[0].lower(), len(x[1])), reverse=True)
        if not tablas:
            raise RuntimeError("No se encontró una tabla municipal en el archivo EFIPEM.")
        raw = tablas[0][1]
    else:
        raw = _read_tabular_bytes(name, r.content)

    d = normalizar_efipem(raw)
    d.to_csv(cache, index=False, encoding="utf-8-sig")
    return d, f"INEGI EFIPEM: {url}"

def normalizar_efipem(raw):
    d = limpiar_columnas(raw)

    anio = busca_columna(d.columns, ["anio"], obligatoria=True)
    entidad = busca_columna(d.columns, ["entidad"], obligatoria=True)
    municipio = busca_columna(d.columns, ["municipio"], obligatoria=True)
    categoria = busca_columna(d.columns, ["categoria"], obligatoria=True)
    concepto = busca_columna(d.columns, ["concepto"], obligatoria=True)
    valor = busca_columna(d.columns, ["valorenpesos", "valor_en_pesos", "valor"], obligatoria=True)

    out = pd.DataFrame({
        "anio": pd.to_numeric(d[anio], errors="coerce").astype("Int64"),
        "entidad": d[entidad].astype(str).str.strip(),
        "municipio": d[municipio].astype(str).str.strip(),
        "categoria": d[categoria].astype(str).str.strip(),
        "concepto": d[concepto].astype(str).str.strip(),
        "valor": a_numero(d[valor])
    })

    out = out[out["entidad"].map(normaliza_texto).str.contains("hidalgo", na=False)].copy()
    out = out.dropna(subset=["anio","municipio","concepto","valor"])
    return out

CAPITULOS_INGRESO = {
    "impuestos": ["impuestos"],
    "cuotas_aport_seg_social": ["cuotas y aportaciones de seguridad social"],
    "contribuciones_mejoras": ["contribuciones de mejoras"],
    "derechos": ["derechos"],
    "productos": ["productos"],
    "aprovechamientos": ["aprovechamientos"],
    "venta_bienes_servicios": ["ingresos por venta de bienes", "venta de bienes y servicios"],
    "participaciones_aportaciones": [
        "participaciones, aportaciones, convenios",
        "participaciones y aportaciones",
        "participaciones"
    ],
    "transferencias": ["transferencias, asignaciones, subsidios", "transferencias y asignaciones"],
    "financiamiento": ["ingresos derivados de financiamientos", "financiamientos"]
}

CAPITULOS_GASTO = {
    "g_servicios_personales": ["servicios personales"],
    "g_materiales_suministros": ["materiales y suministros"],
    "g_servicios_generales": ["servicios generales"],
    "g_transferencias_ayudas": ["transferencias, asignaciones, subsidios y otras ayudas"],
    "g_bienes_muebles": ["bienes muebles, inmuebles e intangibles"],
    "g_inversion_publica": ["inversión pública", "inversion publica"],
    "g_inversiones_financieras": ["inversiones financieras y otras provisiones"],
    "g_participaciones_aportaciones": ["participaciones y aportaciones"],
    "g_deuda_publica": ["deuda pública", "deuda publica"]
}

def _match_capitulo(concepto, variantes):
    c = normaliza_texto(concepto)
    # Coincidencia exacta o prácticamente exacta evita doble contar partidas internas.
    return any(c == normaliza_texto(v) for v in variantes)

def agregar_finanzas(efipem):
    d = efipem.copy()
    rows = []
    for (mun, anio), g in d.groupby(["municipio","anio"], dropna=False):
        rec = {"municipio": mun, "anio": int(anio)}
        for key, variantes in CAPITULOS_INGRESO.items():
            rec[key] = float(g.loc[g["concepto"].map(lambda x: _match_capitulo(x, variantes)), "valor"].sum())
        for key, variantes in CAPITULOS_GASTO.items():
            rec[key] = float(g.loc[g["concepto"].map(lambda x: _match_capitulo(x, variantes)), "valor"].sum())

        propios = sum(rec[k] for k in [
            "impuestos","cuotas_aport_seg_social","contribuciones_mejoras",
            "derechos","productos","aprovechamientos","venta_bienes_servicios"
        ])
        transfer = rec["participaciones_aportaciones"] + rec["transferencias"]
        total_ing = propios + transfer + rec["financiamiento"]
        total_gasto = sum(rec[k] for k in CAPITULOS_GASTO)

        rec["ingresos_propios"] = propios
        rec["transferencias_total"] = transfer
        rec["ingresos_totales_calc"] = total_ing
        rec["gasto_total_calc"] = total_gasto
        rec["autonomia_financiera"] = propios / total_ing if total_ing > 0 else None
        rec["dependencia_transferencias"] = transfer / total_ing if total_ing > 0 else None
        for k in CAPITULOS_GASTO:
            rec[k + "_pct"] = (rec[k] / total_gasto * 100) if total_gasto > 0 else None
        rows.append(rec)
    return pd.DataFrame(rows)

def construir_base_maestra(efipem, coneval):
    fin = agregar_finanzas(efipem)
    social = coneval.copy()
    base = fin.merge(social, on=["municipio","anio"], how="left")

    if "poblacion" in base.columns:
        p = pd.to_numeric(base["poblacion"], errors="coerce")
        base["ingresos_propios_pc"] = base["ingresos_propios"] / p.where(p > 0)
        base["gasto_total_pc"] = base["gasto_total_calc"] / p.where(p > 0)
        base["log_poblacion"] = p.where(p > 0).map(lambda x: __import__("math").log1p(x) if pd.notna(x) else None)

    base = base.sort_values(["municipio","anio"])
    return base
