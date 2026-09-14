"""
Tests del dispatcher `calcular_factura_mes` / `calcular_tarifa_meses` amb
dades sintètiques. No depenen de cap fixture externa — sempre s'executen a CI.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from calcular import calcular_factura_mes, calcular_tarifa_meses

GLOBALS = dict(alquiler_contador_dia=0.02663, bono_social_dia=0.0246885,
               potencia_fotovoltaica_kw=3, impuesto_electrico_pct=5.1127, iva_pct=21)


def approx(a, b, tol=0.01):
    return math.isclose(a, b, abs_tol=tol)


def mes(**kwargs):
    base = dict(dias=30, pot_p1=4.6, pot_p2=4.6, consumo_p1=100, consumo_p2=150,
                consumo_p3=250, kwh_exc=0)
    base.update(kwargs)
    return base


def tarifa(**kwargs):
    base = dict(comercializadora="Test", tarifa="Simple", precio_potencia_punta=30,
                precio_potencia_valle=1, precio_energia_punta=20, precio_energia_llana=15,
                precio_energia_valle=10, precio_excedente=None, metodo=None,
                franjas_horarias="Normal", extra_mensual=None, extra_kwp=None,
                extra_excedentes=None, info_tecnica_indexada=None)
    base.update(kwargs)
    return base


class TestModeGeneric:
    def test_regressio_cas_sintetic(self):
        r = calcular_factura_mes(mes(), tarifa(), GLOBALS)
        assert approx(r.total, 102.67, tol=0.02)
        assert r.hucha_nueva == 0

    def test_sense_potencia_ni_franges_dona_buit(self):
        r = calcular_factura_mes(mes(pot_p1=0, pot_p2=0, consumo_p1=0, consumo_p2=0, consumo_p3=0),
                                  tarifa(), GLOBALS)
        assert r.total is None
        assert r.motiu_buit is not None


class TestModeBateriaNat:
    def test_metode_desconegut_llença_error(self):
        import pytest
        with pytest.raises(ValueError):
            calcular_factura_mes(mes(), tarifa(metodo="MètodeQueNoExisteix"), GLOBALS)

    def test_hucha_s_encadena_entre_mesos(self):
        meses = [
            mes(consumo_p1=20, consumo_p2=30, consumo_p3=50, kwh_exc=200),  # genera hucha
            mes(consumo_p1=100, consumo_p2=150, consumo_p3=250, kwh_exc=0),  # la consumeix
        ]
        t = tarifa(metodo="BateriaNat", precio_excedente=10)  # 10 c€/kWh
        resultats = calcular_tarifa_meses(t, meses, GLOBALS)
        assert len(resultats) == 2
        assert resultats[0].hucha_nueva > 0
        # el mes 2 hauria de sortir més barat que si no hi hagués hucha acumulada
        r2_sense_hucha = calcular_factura_mes(meses[1], t, GLOBALS, hucha_anterior=0)
        assert resultats[1].total < r2_sense_hucha.total
