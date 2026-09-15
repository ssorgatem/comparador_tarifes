#!/usr/bin/env python3
"""
Actualitza els CSVs de consum: mira quina és la darrera data ja
descarregada localment i baixa, via l'API d'e-distribución, tot el que
falta fins al dia més recent disponible, partit per mesos naturals.
"""
import os
import csv
import calendar
from glob import glob
from datetime import date, datetime, timedelta
from EdistribucionAPI.Edistribucion import Edistribucion

CSV_PATTERN = "csvs/ES*_*.csv"
FIELDNAMES = ["CUPS", "Data", "Hora", "AE_kWh", "AS_KWh", "AE_AUTOCONS_kWh", "LECTURA REAL/ESTIMADA"]


def find_last_date():
    """Retorna la data (date) més recent present als CSVs ja descarregats, o None si no n'hi ha cap."""
    last = None
    for fn in glob(CSV_PATTERN):
        with open(fn, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                raw_date = row.get("Data") or row.get("Fecha")
                if not raw_date:
                    continue
                try:
                    d = datetime.strptime(raw_date, "%d/%m/%Y").date()
                except ValueError:
                    continue
                if last is None or d > last:
                    last = d
    return last


def month_ranges(start, end):
    """Genera trams (inici, fi) partits per mesos naturals entre start i end (ambdós inclosos)."""
    cur = start
    while cur <= end:
        last_day = calendar.monthrange(cur.year, cur.month)[1]
        month_end = date(cur.year, cur.month, last_day)
        chunk_end = min(month_end, end)
        yield cur, chunk_end
        cur = chunk_end + timedelta(days=1)


def fetch_range(edis, cups, start, end):
    raw = edis.get_meas_interval(cups["Id"], start.isoformat(), end.isoformat())
    rows = []
    days = set()
    for day in raw:              # una llista per dia
        try:
            for r in day:              # una entrada per hora
                rows.append({
                    "CUPS": cups["CUPS"],
                    "Data": r["date"],             # dd/mm/aaaa
                    "Hora": r["hourCCH"],           # 1..24(25)
                    "AE_kWh": r["value"],           # consum, string amb coma
                    "AS_KWh": r["a2"],              # excedent, string amb coma
                    "AE_AUTOCONS_kWh": "",
                    "LECTURA REAL/ESTIMADA": r["obtainingMethod"],  # 'R' o 'E'
                })
        except KeyError:
            continue
        last_day = int(r["date"].split("/")[0])
        days.add(last_day)
    if len(days) != end.day:
        print(f"Total de dies complets al mes {end.month}: {len(days)}, periode incomplet!")
        return[]
    elif last_day != end.day:
        print(f"Darrer dia del mes {end.month}: {last_day}, periode incomplet!")
        return []
    return rows


def save_csv(rows, filename):
    with open(filename, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, delimiter=";")
        w.writeheader()
        w.writerows(rows)


def main():
    last = find_last_date()
    last_day_last_month = date.today().replace(day=1) - timedelta(days=1)  # avui sol venir incomplet

    if last is None:
        # Sense CSVs previs: tria un punt de partida raonable, per exemple fa 1 any.
        start = last_day_last_month.replace(year=last_day_last_month.year - 1)
        print("No s'ha trobat cap CSV previ, es descarregarà des de", start)
    else:
        start = last + timedelta(days=1)
        print("Última data present als CSVs:", last)

    if start > last_day_last_month:
        print("Ja està tot al dia, no cal descarregar res.")
        return

    edis = Edistribucion()
    edis.login()
    cups = edis.get_list_cups()[0]  # ajusta l'índex si tens més d'un CUPS
    print("CUPS:", cups["CUPS"])

    for chunk_start, chunk_end in month_ranges(start, last_day_last_month):
        print(f"Descarregant {chunk_start} -> {chunk_end}")
        rows = fetch_range(edis, cups, chunk_start, chunk_end)
        if not rows:
            print("  (cap dada retornada, es descarta)")
            continue
        fn = f"csvs/{cups['CUPS']}_{chunk_start:%Y%m%d}_{chunk_end:%Y%m%d}.csv"
        save_csv(rows, fn)
        print(f"  Escrit {fn} amb {len(rows)} files")


if __name__ == "__main__":
    main()
