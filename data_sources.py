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
    """
    Lector robusto para archivos oficiales.
    - CSV/TXT: autodetecta coma, punto y coma, tabulador, etc.
    - XLS/XLSX: detecta encabezados aunque la hoja tenga títulos arriba.
    """
    lname = name.lower()

    if lname.endswith((".csv", ".txt")):
        ultimo = None
        for enc in ("utf-8-sig", "latin1", "utf-8", "cp1252"):
            try:
                # sep=None + engine=python detecta automáticamente el delimitador.
                return pd.read_csv(
                    io.BytesIO(content),
                    encoding=enc,
                    sep=None,
                    engine="python",
                    low_memory=False
                )
            except Exception as e:
                ultimo = e
        raise ValueError(f"No fue posible leer {name}: {ultimo}")

    if lname.endswith((".xlsx", ".xls")):
        xls = pd.ExcelFile(io.BytesIO(content))
        frames = []

        claves_header = {
            "municipio", "nom_mun", "nombre_municipio", "cve_mun",
            "clave_municipio", "entidad", "entidad_federativa", "cve_ent",
            "anio", "año", "categoria", "concepto", "valorenpesos",
            "valor_en_pesos"
        }

        for sh in xls.sheet_names:
            try:
                # Primero leemos sin encabezado para localizar la fila real de títulos.
                preview = pd.read_excel(xls, sheet_name=sh, header=None, nrows=30)
                mejor_fila = 0
                mejor_score = -1

                for i in range(len(preview)):
                    vals = [
                        normaliza_columna(v)
                        for v in preview.iloc[i].tolist()
                        if pd.notna(v)
                    ]
                    score = sum(
                        1 for v in vals
                        if any(k == v or k in v for k in claves_header)
                    )
                    if score > mejor_score:
                        mejor_score = score
                        mejor_fila = i

                d = pd.read_excel(xls, sheet_name=sh, header=mejor_fila)
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
            if name.lower().endswith((".csv", ".txt", ".xlsx", ".xls")) and not name.startswith("__MACOSX"):
                try:
                    out.append((name, _read_tabular_bytes(name, z.read(name))))
                except Exception:
                    continue
    return out

def descargar_coneval(force=False):
    cache = DATA_DIR / "coneval_municipal_hidalgo.csv"
    if cache.exists() and not force:
        dcache = pd.read_csv(cache)
        if {"municipio", "anio"}.issubset(dcache.columns):
            return dcache, f"Cache local: {cache.name}"

    r = _get(CONEVAL_POBREZA_ZIP)
    tablas = _extract_tables_from_zip(r.content)
    if not tablas:
        raise RuntimeError("El ZIP de CONEVAL no contiene tablas legibles.")

    # No elegimos simplemente la tabla con más palabras.
    # Probamos cada tabla y preferimos aquella que realmente contiene identificación municipal.
    candidatas = []
    for name, df in tablas:
        try:
            d = limpiar_columnas(df)
            cols = list(d.columns)

            entidad_col = busca_columna(cols, [
                "entidad_federativa", "nombre_entidad", "nom_ent", "entidad"
            ])
            cve_ent_col = busca_columna(cols, [
                "cve_ent", "clave_entidad", "clave_de_entidad", "cve_entidad"
            ])
            municipio_col = busca_columna(cols, [
                "municipio", "nombre_municipio", "nom_mun", "nombre_del_municipio"
            ])
            cve_mun_col = busca_columna(cols, [
                "cve_mun", "clave_municipio", "clave_de_municipio",
                "cve_municipio", "cvegeo"
            ])
            anio_col = busca_columna(cols, ["anio", "ano", "año"])

            tiene_municipio = municipio_col is not None or cve_mun_col is not None
            tiene_entidad = entidad_col is not None or cve_ent_col is not None
            tiene_anios = (
                anio_col is not None or
                any(re.search(r"(2010|2015|2020)", c) for c in cols)
            )
            tiene_indicadores = any(
                k in " ".join(cols)
                for k in ["pobreza", "rezago", "aliment", "servicios", "salud"]
            )

            if tiene_municipio and tiene_entidad and tiene_anios and tiene_indicadores:
                score = (
                    10 * int(tiene_municipio) +
                    6 * int(tiene_entidad) +
                    5 * int(tiene_anios) +
                    5 * int(tiene_indicadores) +
                    min(len(d.columns), 50) / 100
                )
                candidatas.append((score, name, d))
        except Exception:
            continue

    if not candidatas:
        nombres = ", ".join(name for name, _ in tablas[:10])
        raise RuntimeError(
            "CONEVAL: no se encontró una tabla con identificación municipal "
            f"y años 2010/2015/2020. Archivos examinados: {nombres}"
        )

    candidatas.sort(key=lambda x: x[0], reverse=True)
    errores = []

    for _, nombre, raw in candidatas:
        try:
            entidad_col = busca_columna(raw.columns, [
                "entidad_federativa", "nombre_entidad", "nom_ent", "entidad"
            ])
            cve_ent_col = busca_columna(raw.columns, [
                "cve_ent", "clave_entidad", "clave_de_entidad", "cve_entidad"
            ])
            municipio_col = busca_columna(raw.columns, [
                "municipio", "nombre_municipio", "nom_mun", "nombre_del_municipio"
            ])
            cve_mun_col = busca_columna(raw.columns, [
                "cve_mun", "clave_municipio", "clave_de_municipio",
                "cve_municipio", "cvegeo"
            ])
            anio_col = busca_columna(raw.columns, ["anio", "ano", "año"])

            d = raw.copy()
            mask = pd.Series(True, index=d.index)

            if cve_ent_col is not None:
                ce = (
                    d[cve_ent_col].astype(str)
                    .str.extract(r"(\d+)")[0]
                    .str[:2].str.zfill(2)
                )
                mask &= ce.eq(CVE_ENTIDAD)
            elif entidad_col is not None:
                mask &= (
                    d[entidad_col].astype(str)
                    .map(normaliza_texto)
                    .str.contains("hidalgo", na=False)
                )

            d = d[mask].copy()
            if d.empty:
                raise ValueError("La tabla no produjo filas de Hidalgo.")

            # Municipio
            if municipio_col is not None:
                d["municipio"] = d[municipio_col].astype(str).str.strip()
            elif cve_mun_col is not None:
                cm_raw = d[cve_mun_col].astype(str).str.extract(r"(\d+)")[0]
                # CVEGEO puede ser 5 dígitos (13 + municipio); tomamos los últimos 3.
                cm = cm_raw.str[-3:].str.zfill(3)
                d["municipio"] = cm.map(MUNICIPIOS_HIDALGO)
            else:
                raise ValueError("La tabla no contiene municipio ni clave municipal.")

            # Clave municipal
            if cve_mun_col is not None:
                d["cve_mun"] = (
                    d[cve_mun_col].astype(str)
                    .str.extract(r"(\d+)")[0]
                    .str[-3:].str.zfill(3)
                )
            else:
                inv = {normaliza_texto(v): k for k, v in MUNICIPIOS_HIDALGO.items()}
                d["cve_mun"] = d["municipio"].map(
                    lambda x: inv.get(normaliza_texto(x))
                )

            d = d[d["municipio"].notna()].copy()
            if d.empty:
                raise ValueError("No fue posible mapear municipios de Hidalgo.")

            # Formato largo/ancho
            if anio_col is not None:
                d["anio"] = pd.to_numeric(d[anio_col], errors="coerce").astype("Int64")
                largo = d
            else:
                id_cols = [c for c in ["cve_mun", "municipio"] if c in d.columns]
                rows = []
                for _, row in d.iterrows():
                    base_id = {c: row[c] for c in id_cols}
                    por_anio = {a: dict(base_id, anio=a) for a in ANIOS_SOCIALES}
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
                "rezago_educativo_pct": [r"rezago_educativo"],
                "carencia_salud_pct": [
                    r"acceso.*salud", r"carencia.*salud"
                ],
                "carencia_seguridad_social_pct": [r"seguridad_social"],
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

            final = largo[
                [c for c in ["cve_mun", "municipio", "anio"] if c in largo.columns]
            ].copy()

            if not {"municipio", "anio"}.issubset(final.columns):
                raise ValueError("La tabla normalizada no contiene municipio y año.")

            for nuevo, pats in aliases.items():
                encontrado = None
                for c in largo.columns:
                    nc = normaliza_texto(c).replace(" ", "_")
                    if any(re.search(p, nc) for p in pats):
                        if nuevo.endswith("_pct") and any(
                            k in nc for k in ["personas", "poblacion_", "numero"]
                        ):
                            continue
                        encontrado = c
                        break
                if encontrado:
                    final[nuevo] = a_numero(largo[encontrado])

            final["anio"] = pd.to_numeric(final["anio"], errors="coerce").astype("Int64")
            final = final[final["anio"].isin(ANIOS_SOCIALES)].copy()
            final = final.dropna(subset=["municipio", "anio"])
            final = final.drop_duplicates(["municipio", "anio"])

            if final.empty:
                raise ValueError("La tabla final quedó vacía.")

            final.to_csv(cache, index=False, encoding="utf-8-sig")
            return (
                final,
                f"CONEVAL: Medición de pobreza municipal 2010, 2015 y 2020 ({nombre})"
            )

        except Exception as e:
            errores.append(f"{nombre}: {type(e).__name__}: {e}")

    raise RuntimeError(
        "CONEVAL: se encontraron tablas candidatas, pero ninguna pudo normalizarse. "
        + " | ".join(errores[:5])
    )

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
        if not any(ext in lu for ext in [".zip", ".csv", ".txt"]):
            continue

        score = 0
        if "municip" in lu:
            score += 10
        if "efipem" in lu or "finanz" in lu:
            score += 7
        if "datos" in lu or "descarga" in lu:
            score += 2
        if ".zip" in lu:
            score += 2

        # Penalizar enlaces claramente ajenos al archivo municipal.
        if any(k in lu for k in ["estatal", "alcaldia", "trimestral"]):
            score -= 6

        if score > 0:
            candidatos.append((score, u))

    if not candidatos:
        return None

    candidatos.sort(key=lambda x: x[0], reverse=True)
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

    # Si llegó un archivo de una sola columna, casi siempre hubo un delimitador no detectado.
    if len(d.columns) <= 1:
        raise ValueError(
            f"EFIPEM: el archivo quedó con {len(d.columns)} columna(s). "
            "Probablemente usa un delimitador no reconocido."
        )

    anio = busca_columna(d.columns, ["anio", "ano", "año"], obligatoria=True)

    entidad = busca_columna(d.columns, [
        "entidad", "entidad_federativa", "nombre_entidad", "nom_ent"
    ])
    cve_ent = busca_columna(d.columns, [
        "cve_ent", "clave_entidad", "id_entidad", "cve_entidad"
    ])

    municipio = busca_columna(d.columns, [
        "municipio", "nombre_municipio", "nom_mun"
    ])
    cve_mun = busca_columna(d.columns, [
        "cve_mun", "clave_municipio", "id_municipio", "cve_municipio"
    ])
    cvegeo = busca_columna(d.columns, ["cvegeo", "cve_geo"])

    categoria = busca_columna(d.columns, [
        "categoria", "categoría", "nivel", "tipo"
    ], obligatoria=True)
    concepto = busca_columna(d.columns, [
        "concepto", "descripcion_concepto", "descripcion"
    ], obligatoria=True)
    valor = busca_columna(d.columns, [
        "valorenpesos", "valor_en_pesos", "valor", "monto"
    ], obligatoria=True)

    # Entidad: usar nombre si existe; si no, filtrar con clave 13.
    if entidad is not None:
        serie_entidad = d[entidad].astype(str).str.strip()
        mask_hgo = serie_entidad.map(normaliza_texto).str.contains("hidalgo", na=False)
    elif cve_ent is not None:
        ce = d[cve_ent].astype(str).str.extract(r"(\d+)")[0].str[:2].str.zfill(2)
        serie_entidad = pd.Series("Hidalgo", index=d.index)
        mask_hgo = ce.eq(CVE_ENTIDAD)
    elif cvegeo is not None:
        cg = d[cvegeo].astype(str).str.extract(r"(\d+)")[0].str.zfill(5)
        serie_entidad = pd.Series("Hidalgo", index=d.index)
        mask_hgo = cg.str[:2].eq(CVE_ENTIDAD)
    else:
        raise ValueError(
            "EFIPEM: no se encontró nombre ni clave de entidad "
            f"(columnas recibidas: {list(d.columns)[:20]})."
        )

    # Municipio: usar nombre si existe; si no, mapear la clave INEGI.
    if municipio is not None:
        serie_municipio = d[municipio].astype(str).str.strip()
    else:
        clave_m = None
        if cve_mun is not None:
            clave_m = (
                d[cve_mun].astype(str)
                .str.extract(r"(\d+)")[0]
                .str[-3:].str.zfill(3)
            )
        elif cvegeo is not None:
            clave_m = (
                d[cvegeo].astype(str)
                .str.extract(r"(\d+)")[0]
                .str[-3:].str.zfill(3)
            )

        if clave_m is None:
            raise ValueError(
                "EFIPEM: no se encontró nombre ni clave municipal "
                f"(columnas recibidas: {list(d.columns)[:20]})."
            )
        serie_municipio = clave_m.map(MUNICIPIOS_HIDALGO)

    out = pd.DataFrame({
        "anio": pd.to_numeric(d[anio], errors="coerce").astype("Int64"),
        "entidad": serie_entidad,
        "municipio": serie_municipio,
        "categoria": d[categoria].astype(str).str.strip(),
        "concepto": d[concepto].astype(str).str.strip(),
        "valor": a_numero(d[valor])
    })

    out = out[mask_hgo].copy()
    out = out.dropna(subset=["anio", "municipio", "concepto", "valor"])

    if out.empty:
        raise ValueError(
            "EFIPEM: el archivo fue reconocido, pero no produjo registros válidos de Hidalgo."
        )

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
