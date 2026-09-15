import pandas as pd
import holidays
import os
import sys
import json
import datetime


p1 = [11, 12, 13, 14, 19, 20, 21, 22]
p2 = [9, 10, 15, 16, 17, 18, 23, 24, 25]
p3 =[1, 2, 3, 4, 5, 6, 7, 8]

#DEFAULTS
PPUNTA = 2.7
PVALLE = 3.7
BONOS = 0.0246885
LLOGUER = 0.02663
POTENCIAFV = 4.8
IMPE = 5.1127
IVA = 21

def grinch(df, ppunta=PPUNTA, pvalle=PVALLE, xlout="dades_grinch.xlsx"):

    gdf = pd.DataFrame()
    mesos = sorted(sorted(df.mes.unique()), key=lambda x: x.split("/")[1])[-12:]

    gcols = []
    n=1
    for mes in mesos:
        gcol = pd.Series()
        gcol["Descripción"] = mes
        mdf = df[df.mes == mes]
        gcol["Días"] = round(len(mdf.index)/24)
        gcol["ppunta"] = ppunta
        gcol["pvalle"] = pvalle
        ps = mdf.groupby("p").sum()["AE_kWh"]
        gcol["Punta"] = float(ps.p1)
        gcol["Llana"] = float(ps.p2)
        gcol["Valle"] = float(ps.p3)
        gcol["Total"] = None
        gcol["kWh"] = float(mdf["AS_KWh"].sum())
        mdf = mdf.reset_index()
        #de 22 a 12
        promo = [23,24, 25,1,2,3,4,5,6,7,8,9,10,11,12]
        gcol["PromoN"] = float(mdf[mdf.Hora.isin(promo)].AE_kWh.sum())
        gcol["No PromoN"] = float(mdf[~mdf.Hora.isin(promo)].AE_kWh.sum())
        gcol["TotalN"] = None
        #de 1 a 7
        promo = [2,3,4,5,6,7]
        gcol["PromoVE"] = float(mdf[mdf.Hora.isin(promo)].AE_kWh.sum())
        gcol["No PromoVE"] = float(mdf[~mdf.Hora.isin(promo)].AE_kWh.sum())
        gcol["TotalVE"] = None
        #de 17 a 9
        promo = [18,19,20,21,22,23,24,25,1,2,3,4,5,6,7,8,9]
        gcol["PromoS"] = float(mdf[mdf.Hora.isin(promo)].AE_kWh.sum())
        gcol["No PromoS"] = float(mdf[~mdf.Hora.isin(promo)].AE_kWh.sum())
        gcol["TotalS"] = None
        #No
        gcol["Promo50"] = None
        gcol["No Promo50"] = None
        gcol["Total50"] =None
        #2h
        promo = [21,22]
        gcol["Promo2h"] = float(mdf[mdf.Hora.isin(promo)].AE_kWh.sum())
        gcol["No Promo2h"] =  None
        gcol["Total2h"] = None
        #3h
        promo = [21,22,23]
        gcol["Promo3h"] = float(mdf[mdf.Hora.isin(promo)].AE_kWh.sum())
        gcol["No Promo3h"] =  None
        gcol["Total3h"] = None
        #de 12 a 18
        promo = [13,14,15,16,17,18]
        gcol["PromoSC"] = float(mdf[mdf.Hora.isin(promo)].AE_kWh.sum())
        gcol["No PromoSC"] =  float(mdf[~mdf.Hora.isin(promo)].AE_kWh.sum())
        gcol["TotalSC"] = None
        gdf[n] = gcol
        n +=1
    print(gdf)
    if xlout:
        gdf.to_excel(xlout)
    return gdf


# Correspondència entre les etiquetes de la Series que genera grinch() i els
# noms de camp que fa servir datos.json (mateixos noms que extract_datos.py
# quan llegeix el full "Datos" de l'Excel -- veure MONTH_ROWS en aquell fitxer).
DATOS_JSON_FIELD_MAP = {
    "Descripción": "descripcion",
    "Días": "dias",
    "ppunta": "pot_p1",
    "pvalle": "pot_p2",
    "Punta": "consumo_p1",
    "Llana": "consumo_p2",
    "Valle": "consumo_p3",
    "kWh": "kwh_exc",
    "PromoN": "kwh_barato_nocturna",
    "No PromoN": "kwh_caro_nocturna",
    "PromoVE": "kwh_barato_ve",
    "No PromoVE": "kwh_caro_ve",
    "PromoS": "kwh_barato_solar",
    "No PromoS": "kwh_caro_solar",
    "Promo50": "kwh_50h_gratis",
    "Promo2h": "kwh_2h_gratis",
    "Promo3h": "kwh_3h_gratis",
    "PromoSC": "kwh_promo_sunclub",
    "No PromoSC": "kwh_no_promo_sunclub",
}

# Camps de datos.json que grinch() no pot omplir perquè no surten de la corba
# de consum (calcular.py els tracta com "sense dada" si es deixen a None).
CAMPS_SENSE_ORIGEN_A_GRINCH = {"kwh_gratis_sunclub": None, "autoconsumo_estimado": None}


def to_datos_json(gdf, out="datos.json", alquiler_contador_dia=0.02663, bono_social_dia=0.0246885,
                   potencia_fotovoltaica_kw=3, impuesto_electrico_pct=5.1127, iva_pct=21):
    """
    Converteix el DataFrame que retorna grinch() al mateix format que
    `extract_datos.py` genera llegint el full "Datos" de l'Excel -- mateixa
    estructura {"globals": {...}, "meses": [...]}, directament consumible per
    `calcular.py` (calcular_tarifa_meses) sense passar per l'Excel.

    IMPORTANT: els 5 paràmetres globals NO surten de la corba de consum --
    són valors regulats (alquiler de comptador, bo social, impost elèctric,
    IVA) o de la teva pròpia instal·lació (potència fotovoltaica), i poden
    canviar amb el temps. Els valors per defecte són els que hem fet servir
    en converses anteriors; revisa'ls (per exemple contra el full "Datos" B1:B5
    d'una versió recent de l'Excel) abans de confiar-hi per a un càlcul real.
    """
    globals_ = dict(
        alquiler_contador_dia=alquiler_contador_dia,
        bono_social_dia=bono_social_dia,
        potencia_fotovoltaica_kw=potencia_fotovoltaica_kw,
        impuesto_electrico_pct=impuesto_electrico_pct,
        iva_pct=iva_pct,
    )

    meses = []
    for num_mes in gdf.columns:  # 1, 2, 3... tal com els numera grinch()
        gcol = gdf[num_mes]
        mes = {"num_mes": int(num_mes)}
        mes.update(CAMPS_SENSE_ORIGEN_A_GRINCH)
        for label, field in DATOS_JSON_FIELD_MAP.items():
            mes[field] = gcol.get(label)
        meses.append(mes)

    data = {"globals": globals_, "meses": meses}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Escrits {len(meses)} mesos -> {out}", file=sys.stderr)
    return data

def parse_csvs(csvlist):
    ps = dict()
    for h in range (1, 26):
        if h in p1:
            p = "p1"
        elif h in p2:
            p = "p2"
        else:
            p = "p3"
        ps[h] = p

    alldf = pd.concat([pd.read_csv(c, sep=";") for c in csvlist])
    if "Fecha" in alldf.columns:
        if  "Data" not in alldf.columns:
            alldf["Data"] =  alldf.Fecha
        else:
            alldf.Data = alldf.Data.fillna("") + alldf.Fecha.fillna("")
        alldf = alldf.drop("Fecha", axis=1)
    
    if "REAL/ESTIMADO" in alldf.columns:
        if  "LECTURA REAL/ESTIMADA" not in alldf.columns:
            alldf["LECTURA REAL/ESTIMADA"] =  alldf["REAL/ESTIMADO"]
        else:
            alldf["LECTURA REAL/ESTIMADA"] = alldf["LECTURA REAL/ESTIMADA"].fillna("") + alldf["REAL/ESTIMADO"].fillna("")
        alldf = alldf.drop("REAL/ESTIMADO", axis=1)
        
    if 'AS_KWh' not in alldf.columns:
        alldf['AS_KWh'] = "0"
    alldf["mes"] = alldf.Data.apply(lambda x: x[3:])

    os.makedirs("mes", exist_ok=True)
    for mes in alldf.mes.unique():
        fn = "mes/{}.csv".format(mes.replace("/", "-"))
        if os.path.isfile(fn): continue    
        alldf[alldf.mes == mes].drop("mes", axis=1).to_csv(fn, sep=";", index=False)

    def is_working_day(day):
        day = datetime.datetime.strptime(day, "%d/%m/%Y")
        return holidays.Spain().is_working_day(day)

    alldf = alldf.reset_index()
    alldf["p"] = alldf.Hora.map(ps)
    alldf.loc[alldf[~alldf.Data.apply(is_working_day)].index, "p"] = "p3"
    alldf = alldf[['Data', 'Hora', 'AE_kWh', 'AS_KWh' ,'mes', 'p']].set_index(["Data", "Hora"])
    alldf = alldf.groupby(level=[0,1]).last() #drop dups
    alldf = alldf.map(lambda x: x if "," not in x else float(x.replace(",",".")))

    bn_import = alldf[alldf["AS_KWh"] < alldf["AE_kWh"]].query("AS_KWh > 0")

    alldf.loc[bn_import.index, "AS_KWh"] = 0
    alldf.loc[bn_import.index, "AE_kWh"] = (bn_import.AE_kWh - bn_import.AS_KWh)


    bn_export = alldf[alldf["AE_kWh"] < alldf["AS_KWh"]].query("AE_kWh > 0")

    alldf.loc[bn_export.index, "AE_kWh"] = 0
    alldf.loc[bn_export.index, "AS_KWh"] = (bn_export.AS_KWh - bn_export.AE_kWh)
    return alldf


if __name__ == "__main__":
    import argparse
    from glob import glob

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csvs", nargs="*", help="Fitxers CSV a processar.")
    ap.add_argument("--ppunta", type=float, default=PPUNTA, help="Potència contractada P1/punta, kW")
    ap.add_argument("--pvalle", type=float, default=PVALLE, help="Potència contractada P2/valle, kW")
    ap.add_argument("--alquiler-contador-dia", type=float, default=LLOGUER)
    ap.add_argument("--bono-social-dia", type=float, default=BONOS)
    ap.add_argument("--potencia-fotovoltaica-kw", type=float, default=POTENCIAFV)
    ap.add_argument("--impuesto-electrico-pct", type=float, default=IMPE)
    ap.add_argument("--iva-pct", type=float, default=IVA)
    ap.add_argument("--out-json", default="datos.json")
    args = ap.parse_args()

    csvlist = args.csvs
    if not csvlist:
        raise SystemExit("Cap CSV trobat proveït")

    alldf = parse_csvs(csvlist)
    gdf = grinch(alldf, ppunta=args.ppunta, pvalle=args.pvalle, xlout=args.out_json.replace("json", "xlsx"))
    to_datos_json(
        gdf, out=args.out_json,
        alquiler_contador_dia=args.alquiler_contador_dia,
        bono_social_dia=args.bono_social_dia,
        potencia_fotovoltaica_kw=args.potencia_fotovoltaica_kw,
        impuesto_electrico_pct=args.impuesto_electrico_pct,
        iva_pct=args.iva_pct,
    )

