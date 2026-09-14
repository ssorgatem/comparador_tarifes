"""
Tests unitaris de les funcions pures de `factura_engine.py`. No depenen de
cap fitxer extern (ni Excel ni fixtures) — sempre s'executen a CI.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factura_engine import (
    calcular_potencia, calcular_energia, calcular_valor_excedentes,
    calcular_impuesto_electrico, calcular_bono_social, calcular_mag,
    decode_params, recalcular_precio_energia_si_es_indexada,
    factura_generica, factura_naturgy, PEAJE_P1, PEAJE_P2, PEAJE_P3,
)


def approx(a, b, tol=0.01):
    return math.isclose(a, b, abs_tol=tol)


class TestCalcularPotencia:
    def test_potencia_basica(self):
        # 30 dies, 4.6 kW als dos períodes, preus 30 i 1 €/kW/any
        p = calcular_potencia(30, 4.6, 30, 4.6, 1)
        assert approx(p, 30 * (4.6 * 30 + 4.6 * 1) / 365)

    def test_potencia_zero_dies(self):
        assert calcular_potencia(0, 4.6, 30, 4.6, 1) == 0


class TestCalcularEnergia:
    def test_franja_normal(self):
        e = calcular_energia(100, 20, 150, 15, 250, 10, "Normal",
                              None, None, None, None, None, None, None, None, None, None, None, None)
        assert approx(e, (20 * 100 + 15 * 150 + 10 * 250) / 100)

    def test_franja_desconeguda_retorna_zero(self):
        e = calcular_energia(100, 20, 150, 15, 250, 10, "FranjaQueNoExisteix",
                              None, None, None, None, None, None, None, None, None, None, None, None)
        assert e == 0


class TestDecodeParams:
    def test_sense_campo_churro(self):
        p = decode_params(None)
        assert p.indexada == ""
        assert p.dsv == p.fnee == p.gdo == p.fee == p.bs == 0

    def test_amb_idx_i_valors(self):
        p = decode_params("IDX=Bonpreu|DSV=0,2|FNEE=0,1")
        assert p.indexada == "Bonpreu"
        assert approx(p.dsv, 0.2)
        assert approx(p.fnee, 0.1)
        # GdO/FEE/BS no especificats: es queden als valors per defecte d'indexada
        assert approx(p.gdo, 0.5)


class TestCalcularImpuestoElectrico:
    def test_impuesto_minim_per_consum(self):
        # Amb base molt petita, ha d'aplicar el mínim de 0,001 €/kWh
        ie = calcular_impuesto_electrico(0, 0, 0, 10000, 5.1127, 0, 0)
        assert approx(ie, 10000 * 0.001)


class TestFacturaGenerica:
    def test_cas_sintetic_sense_autoconsum(self):
        """Regressió contra el valor calculat i verificat a mà en el
        desenvolupament original (veure conversa): 500 kWh/mes, sense
        excedents, tarifa simple -> ~102.67 €."""
        precio_p1, precio_p2, precio_p3, _ = recalcular_precio_energia_si_es_indexada(
            None, 20, 15, 10, PEAJE_P1, PEAJE_P2, PEAJE_P3, "Normal")
        p = calcular_potencia(30, 4.6, 30, 4.6, 1)
        en = calcular_energia(100, precio_p1, 150, precio_p2, 250, precio_p3, "Normal",
                               None, None, None, None, None, None, None, None, None, None, None, None)
        total_peajes = (100 * PEAJE_P1 + 150 * PEAJE_P2 + 250 * PEAJE_P3) / 100
        bono_social = calcular_bono_social(0.0246885, 30)
        ie = calcular_impuesto_electrico(p, en, 0, 500, 5.1127, bono_social, 0)
        alq_cont = 0.02663 * 30

        r = factura_generica(
            dias=30, consumo_total=500, termino_potencia=p, potencia_boe=0,
            termino_energia=en, total_peajes=total_peajes, bono_social=bono_social, modo=None,
            valor_mag=0, valor_excedentes=0, ie=ie, alq_cont=alq_cont, iva=21,
            margen_mensual=0, margen_excedentes=0, descuento_despues_iva=0, campo_churro=None,
        )
        assert approx(r.total, 102.67, tol=0.02)


class TestFacturaNaturgy:
    def test_sense_excedents_hucha_es_manté_a_zero(self):
        r = factura_naturgy(hucha_anterior=0, dias=30, consumo_total=500, termino_potencia=10,
                             potencia_boe=8, termino_energia=60, bono_social=0.7, valor_mag=0,
                             valor_excedentes=0, ie=3, alq_cont=0.8, iva=21, extra_mensual=0)
        assert r.hucha_nueva == 0
        assert r.total_factura > 0

    def test_excedent_superior_a_energia_incrementa_la_hucha(self):
        r = factura_naturgy(hucha_anterior=0, dias=30, consumo_total=100, termino_potencia=10,
                             potencia_boe=8, termino_energia=20, bono_social=0.7, valor_mag=0,
                             valor_excedentes=50, ie=3, alq_cont=0.8, iva=21, extra_mensual=0)
        assert r.hucha_nueva > 0

    def test_hucha_es_fa_servir_per_pagar_mes_seguent(self):
        # Mes 1: genera saldo a la hucha
        r1 = factura_naturgy(hucha_anterior=0, dias=30, consumo_total=50, termino_potencia=10,
                              potencia_boe=8, termino_energia=10, bono_social=0.7, valor_mag=0,
                              valor_excedentes=80, ie=3, alq_cont=0.8, iva=21, extra_mensual=0)
        assert r1.hucha_nueva > 0
        # Mes 2: sense excedents, la factura ha de sortir més barata gràcies a la hucha
        r2_amb_hucha = factura_naturgy(hucha_anterior=r1.hucha_nueva, dias=30, consumo_total=200,
                                        termino_potencia=10, potencia_boe=8, termino_energia=40,
                                        bono_social=0.7, valor_mag=0, valor_excedentes=0, ie=3,
                                        alq_cont=0.8, iva=21, extra_mensual=0)
        r2_sense_hucha = factura_naturgy(hucha_anterior=0, dias=30, consumo_total=200,
                                          termino_potencia=10, potencia_boe=8, termino_energia=40,
                                          bono_social=0.7, valor_mag=0, valor_excedentes=0, ie=3,
                                          alq_cont=0.8, iva=21, extra_mensual=0)
        assert r2_amb_hucha.total_factura < r2_sense_hucha.total_factura
