"""
Test de validació completa contra un Excel real ja calculat. S'omet
automàticament si no hi ha les fixtures locals (no es pugen al repositori
perquè contenen dades de consum real — veure tools/export_referencia.py).

Per generar-les localment:
    python3 extract_tarifas.py el_teu_fitxer.xlsm --out tests/fixtures/tarifas.json
    python3 extract_datos.py   el_teu_fitxer.xlsm --out tests/fixtures/datos.json
    python3 tools/export_referencia.py el_teu_fitxer.xlsm
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from calcular import calcular_tarifa_meses

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TARIFAS_PATH = FIXTURES / "tarifas.json"
DATOS_PATH = FIXTURES / "datos.json"
REFERENCIA_PATH = FIXTURES / "facturas_referencia.json"

# Cel·les on ja sabem (per anàlisi manual, veure conversa/README) que hi ha
# valors obsolets al propi Excel de referència, no errors del port. Format:
# (comercializadora, tarifa, índex de mes 0-11).
DISCREPANCIES_CONEGUDES = {
    ("Repsol", "Tarifa Solar Batería Virtual", 1),
    ("Esmiluz Energía", "SIE (BNA) con media 12 meses con FV", 2),
}

falten_fixtures = not (TARIFAS_PATH.exists() and DATOS_PATH.exists() and REFERENCIA_PATH.exists())

pytestmark = pytest.mark.skipif(
    falten_fixtures,
    reason="Fixtures locals (tests/fixtures/*.json) no trobades — genera-les amb tools/export_referencia.py",
)


@pytest.fixture(scope="module")
def dades():
    tarifas = json.load(open(TARIFAS_PATH, encoding="utf-8"))
    datos = json.load(open(DATOS_PATH, encoding="utf-8"))
    referencia = json.load(open(REFERENCIA_PATH, encoding="utf-8"))
    return tarifas, datos, referencia


def test_totes_les_tarifes_coincideixen_amb_excel(dades):
    tarifas, datos, referencia = dades
    globals_ = datos["globals"]
    meses = datos["meses"]

    mismatches = []
    n_ok = 0

    for t in tarifas:
        fila = str(t["_fila_excel"] - 1)
        valors_referencia = referencia.get(fila)
        if valors_referencia is None:
            continue

        resultats = calcular_tarifa_meses(t, meses, globals_)
        clau = (t.get("comercializadora"), t.get("tarifa"))

        for i, (r, excel_val) in enumerate(zip(resultats, valors_referencia)):
            if (*clau, i) in DISCREPANCIES_CONEGUDES:
                continue
            if excel_val is None and r.total is None:
                n_ok += 1
                continue
            if excel_val is None or r.total is None:
                mismatches.append((*clau, i, r.total, excel_val))
                continue
            if abs(r.total - excel_val) < 0.01:
                n_ok += 1
            else:
                mismatches.append((*clau, i, round(r.total, 4), excel_val))

    assert not mismatches, f"{len(mismatches)} discrepàncies (de {n_ok + len(mismatches)} comprovades): {mismatches[:20]}"
