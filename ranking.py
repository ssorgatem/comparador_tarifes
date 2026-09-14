"""
Equivalent del full "Facturas": per a cada tarifa, suma l'import de tots els
mesos disponibles a Datos i les ordena de més barata a més cara.

Ús:
    python3 ranking.py tarifas.json datos.json [--csv sortida.csv]
"""
import argparse
import csv
import json
import sys

from calcular import calcular_tarifa_meses


def calcular_ranking(tarifas: list[dict], datos: dict):
    globals_ = datos["globals"]
    meses = datos["meses"]

    files = []

    for tarifa in tarifas:
        modo = tarifa.get("metodo")
        nom = f"{tarifa.get('comercializadora')} — {tarifa.get('tarifa')}"

        resultats = calcular_tarifa_meses(tarifa, meses, globals_)
        total_anual = 0.0
        mesos_calculats = 0
        for r in resultats:
            if r.total is not None:
                total_anual += r.total
                mesos_calculats += 1

        if mesos_calculats == 0:
            total_anual = None

        files.append({
            "comercializadora": tarifa.get("comercializadora"),
            "tarifa": tarifa.get("tarifa"),
            "metodo": modo or "(genèric)",
            "total_anual": round(total_anual, 2) if total_anual is not None else None,
            "mesos_calculats": mesos_calculats,
            "enlace": tarifa.get("enlace"),
        })

    files_calculades = [f for f in files if f["total_anual"] is not None]
    files_calculades.sort(key=lambda f: f["total_anual"])

    return files_calculades, []


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tarifas_json")
    ap.add_argument("datos_json")
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    tarifas = json.load(open(args.tarifas_json, encoding="utf-8"))
    datos = json.load(open(args.datos_json, encoding="utf-8"))

    ranking, pendents = calcular_ranking(tarifas, datos)

    print(f"{'#':>3}  {'Total anual':>12}  {'Mesos':>5}  Comercialitzadora — Tarifa", file=sys.stderr)
    for i, f in enumerate(ranking, 1):
        print(f"{i:>3}  {f['total_anual']:>10.2f} €  {f['mesos_calculats']:>5}  "
              f"{f['comercializadora']} — {f['tarifa']}", file=sys.stderr)

    metodos_pendents = sorted(set(m for _, m in pendents)) if pendents else []
    if pendents:
        print(f"\n{len(pendents)} tarifes NO calculades (mètode encara no portat: {metodos_pendents})", file=sys.stderr)

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["comercializadora", "tarifa", "metodo", "total_anual",
                                               "mesos_calculats", "enlace"])
            w.writeheader()
            w.writerows(ranking)
        print(f"\nEscrit {args.csv}", file=sys.stderr)


if __name__ == "__main__":
    main()
