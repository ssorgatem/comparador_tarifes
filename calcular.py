"""
Port del dispatcher principal `Function FACTURA` (Módulo1.bas ~L3236-3552):
combina un mes de `Datos` amb una fila de `Tarifas` i calcula l'import.

Ús típic:
    tarifas = json.load(open("tarifas.json"))
    datos = json.load(open("datos.json"))
    for mes in datos["meses"]:
        for tarifa in tarifas:
            r = calcular_factura_mes(mes, tarifa, datos["globals"])
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from factura_engine import (
    PEAJE_P1, PEAJE_P2, PEAJE_P3, POT_BOE_P1, POT_BOE_P2,
    MODOS_GENERICOS, calcular_potencia, calcular_energia, calcular_descuento_despues_iva,
    calcular_bono_social, calcular_mag, calcular_valor_excedentes,
    calcular_impuesto_electrico, factura_generica,
    factura_naturgy, factura_factor, factura_bonpreu, factura_nufri,
    factura_proxima_con_bv, factura_proxima_sin_bv, factura_lidera, factura_helios,
    factura_lumio, factura_som_energia, factura_octopus, factura_agri, factura_esluz,
    factura_bassols, factura_met, factura_met2, factura_bassols_bna, factura_esmiluz_bna,
    factura_iberdola, factura_imagina, factura_repsol, factura_repsol2,
    recalcular_precio_energia_si_es_indexada, ResultatFactura,
)

# Mètodes amb estat (bateria virtual / balanç net) que ja tenen la seva
# funció Python. Als que hi falten (cap ara mateix) caldria afegir l'entrada
# aquí i el `elif` corresponent a `_calcular_especifica`.
MODOS_AMB_ESTAT = {
    "BateriaNat", "BateriaFE", "BateriaBP", "BateriaEN", "BateriaPE", "Proxima",
    "BateriaLE", "BateriaHE", "BateriaLumio", "BateriaSom", "BateriaOE", "BateriaOE2",
    "BateriaAgri", "BateriaEL", "BateriaBE", "BateriaME", "BateriaME2", "BNA_BE",
    "BNA_EE", "BateriaIber", "BateriaIE", "BateriaRep", "BateriaRep2",
}


def _n(v, default=0.0):
    """None/"" -> default, altrament float(v). Equivalent a IsEmpty(...) del VBA."""
    if v is None or v == "":
        return default
    return float(v)


@dataclass
class ResultatMes:
    total: Optional[float]          # None == "" a Excel (sense dades suficients per calcular)
    desglossament: Optional[dict] = None
    motiu_buit: Optional[str] = None
    hucha_nueva: float = 0.0        # saldo de bateria virtual a passar al mes següent (0 si no aplica)


def calcular_factura_mes(mes: dict, tarifa: dict, globals_: dict, hucha_anterior: float = 0.0,
                          consumo_acumulado_anterior: float = 0.0, excedentes_acumulados_anterior: float = 0.0) -> ResultatMes:
    """
    mes: un element de datos["meses"] (extract_datos.py)
    tarifa: un element de tarifas.json (extract_tarifas.py)
    globals_: datos["globals"]
    hucha_anterior: saldo de bateria/balanç acumulat fins al mes anterior (0 si no aplica)
    consumo_acumulado_anterior / excedentes_acumulados_anterior: només rellevants per BateriaRep2
    """
    modo = tarifa.get("metodo")

    kwh_p1 = _n(mes.get("consumo_p1"))
    kwh_p2 = _n(mes.get("consumo_p2"))
    kwh_p3 = _n(mes.get("consumo_p3"))
    excedentes_finales = _n(mes.get("kwh_exc"))

    # --- Autoconsumo estimat (Módulo1.bas L3307-3355) ---------------------
    autocons_estimado = _n(mes.get("autoconsumo_estimado"))
    if 0 < autocons_estimado <= 1:
        autocons_p1 = kwh_p1 * autocons_estimado
        autocons_p2 = kwh_p2 * autocons_estimado
        autocons_p3 = kwh_p3 * autocons_estimado
        total_autocons = autocons_p1 + autocons_p2 + autocons_p3
        if total_autocons > excedentes_finales:
            # Es reparteix el 100% de la producció entre les franges (40h+40h+88h/setmana)
            kwh_p1 -= (excedentes_finales * 40) / 168
            kwh_p2 -= (excedentes_finales * 40) / 168
            kwh_p3 -= (excedentes_finales * 88) / 168
            excedentes_finales = 0.0
        else:
            excedentes_finales -= total_autocons
            kwh_p1 -= autocons_p1
            kwh_p2 -= autocons_p2
            kwh_p3 -= autocons_p3

    total_kwh = kwh_p1 + kwh_p2 + kwh_p3
    total_peajes = (kwh_p1 * PEAJE_P1 / 100) + (kwh_p2 * PEAJE_P2 / 100) + (kwh_p3 * PEAJE_P3 / 100)

    dias = int(mes.get("dias") or 0)
    em = _n(tarifa.get("extra_mensual"))
    ee = _n(tarifa.get("extra_excedentes"))
    # ekwp = _n(tarifa.get("extra_kwp"))  # només usat pels mètodes BNA_* (pendents)

    campo_churro = tarifa.get("info_tecnica_indexada")
    tipo_franja = tarifa.get("franjas_horarias") or "Normal"

    precio_p1, precio_p2, precio_p3, _params = recalcular_precio_energia_si_es_indexada(
        campo_churro,
        _n(tarifa.get("precio_energia_punta")),
        _n(tarifa.get("precio_energia_llana")),
        _n(tarifa.get("precio_energia_valle")),
        PEAJE_P1, PEAJE_P2, PEAJE_P3,
        tipo_franja,
    )

    p = calcular_potencia(dias, _n(mes.get("pot_p1")), _n(tarifa.get("precio_potencia_punta")),
                           _n(mes.get("pot_p2")), _n(tarifa.get("precio_potencia_valle")))
    p_boe = calcular_potencia(dias, _n(mes.get("pot_p1")), POT_BOE_P1, _n(mes.get("pot_p2")), POT_BOE_P2)

    en = calcular_energia(
        kwh_p1, precio_p1, kwh_p2, precio_p2, kwh_p3, precio_p3, tipo_franja,
        mes.get("kwh_barato_nocturna"), mes.get("kwh_caro_nocturna"),
        mes.get("kwh_barato_ve"), mes.get("kwh_caro_ve"),
        mes.get("kwh_barato_solar"), mes.get("kwh_caro_solar"),
        mes.get("kwh_50h_gratis"), mes.get("kwh_2h_gratis"), mes.get("kwh_3h_gratis"),
        mes.get("kwh_promo_sunclub"), mes.get("kwh_gratis_sunclub"), mes.get("kwh_no_promo_sunclub"),
    )
    descuento_despues_iva = calcular_descuento_despues_iva(
        kwh_p1, precio_p1, kwh_p2, precio_p2, kwh_p3, precio_p3, tipo_franja,
        mes.get("kwh_barato_nocturna"), mes.get("kwh_caro_nocturna"),
        mes.get("kwh_barato_ve"), mes.get("kwh_caro_ve"),
        mes.get("kwh_barato_solar"), mes.get("kwh_caro_solar"),
        mes.get("kwh_50h_gratis"), mes.get("kwh_2h_gratis"), mes.get("kwh_3h_gratis"),
        mes.get("kwh_promo_sunclub"), mes.get("kwh_gratis_sunclub"), mes.get("kwh_no_promo_sunclub"),
    )
    valor_excedentes = calcular_valor_excedentes(excedentes_finales, tarifa.get("precio_excedente"))

    # GasIncluido està forçat a "N" al VBA actual (paràmetre anul·lat) -> MAG sempre 0
    valor_mag = calcular_mag(total_kwh, 0)

    bono_social = calcular_bono_social(_n(globals_.get("bono_social_dia")), dias)

    if modo in ("PVPC", "BateriaAgri", "BateriaME2", "BateriaEL"):
        ie = calcular_impuesto_electrico(p, en, valor_excedentes, total_kwh,
                                          _n(globals_.get("impuesto_electrico_pct")), bono_social, total_peajes)
    elif modo == "BateriaRep":
        ie = calcular_impuesto_electrico(p, en, 0, total_kwh,
                                          _n(globals_.get("impuesto_electrico_pct")), bono_social, 0)
    else:
        ie = calcular_impuesto_electrico(p, en, valor_excedentes, total_kwh,
                                          _n(globals_.get("impuesto_electrico_pct")), bono_social, 0)

    alq_cont = _n(globals_.get("alquiler_contador_dia")) * dias

    franjas_definidas = en > 0
    if not (p > 0 and franjas_definidas):
        return ResultatMes(total=None, motiu_buit="Sense prou dades (potència o franges a 0)",
                            hucha_nueva=hucha_anterior)

    potencia_pico = _n(globals_.get("potencia_fotovoltaica_kw"))
    consumo_acumulado = consumo_acumulado_anterior + total_kwh
    excedentes_acumulados = excedentes_acumulados_anterior + excedentes_finales

    if modo in MODOS_GENERICOS:
        resultat = factura_generica(
            dias=dias, consumo_total=total_kwh, termino_potencia=p, potencia_boe=p_boe,
            termino_energia=en, total_peajes=total_peajes, bono_social=bono_social, modo=modo,
            valor_mag=valor_mag, valor_excedentes=valor_excedentes, ie=ie, alq_cont=alq_cont,
            iva=_n(globals_.get("iva_pct")), margen_mensual=em, margen_excedentes=ee,
            descuento_despues_iva=descuento_despues_iva, campo_churro=campo_churro,
        )
        return ResultatMes(total=resultat.total, desglossament=resultat.desglossament, hucha_nueva=0.0)

    ekwp = _n(tarifa.get("extra_kwp"))
    gas_incluido = False  # forçat a "N" al VBA actual

    if modo == "BateriaNat":
        r = factura_naturgy(hucha_anterior, dias, total_kwh, p, p_boe, en, bono_social, valor_mag,
                             valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")), em)
    elif modo == "BateriaFE":
        r = factura_factor(hucha_anterior, dias, total_kwh, p, p_boe, en, bono_social, gas_incluido,
                            valor_mag, valor_excedentes, excedentes_finales, ie, alq_cont, _n(globals_.get("iva_pct")))
    elif modo == "BateriaBP":
        r = factura_bonpreu(hucha_anterior, dias, total_kwh, p, p_boe, en, total_peajes, bono_social,
                             gas_incluido, valor_mag, valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")),
                             em, campo_churro)
    elif modo == "BateriaEN":
        r = factura_nufri(hucha_anterior, dias, total_kwh, p, p_boe, en, bono_social, valor_mag,
                           valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")), em)
    elif modo == "BateriaPE":
        r = factura_proxima_con_bv(hucha_anterior, dias, total_kwh, p, p_boe, en, total_peajes, bono_social,
                                    valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")), em, ee,
                                    excedentes_finales, campo_churro)
    elif modo == "Proxima":
        total = factura_proxima_sin_bv(dias, total_kwh, p, p_boe, en, total_peajes, bono_social,
                                        valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")), em, ee, campo_churro)
        return ResultatMes(total=total, hucha_nueva=0.0)
    elif modo == "BateriaLE":
        r = factura_lidera(hucha_anterior, dias, total_kwh, p, p_boe, en, total_peajes, bono_social,
                            valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")), em, campo_churro)
    elif modo == "BateriaHE":
        r = factura_helios(hucha_anterior, dias, total_kwh, p, p_boe, en, total_peajes, bono_social,
                            valor_excedentes, excedentes_finales, ie, alq_cont, _n(globals_.get("iva_pct")),
                            em, campo_churro)
    elif modo == "BateriaLumio":
        r = factura_lumio(hucha_anterior, dias, total_kwh, p, p_boe, en, total_peajes, bono_social,
                           valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")), campo_churro)
    elif modo == "BateriaSom":
        r = factura_som_energia(hucha_anterior, dias, total_kwh, p, p_boe, en, total_peajes, bono_social,
                                 gas_incluido, valor_mag, valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")),
                                 campo_churro)
    elif modo == "BateriaOE":
        r = factura_octopus(hucha_anterior, dias, total_kwh, p, p_boe, en, total_peajes, bono_social, em,
                             gas_incluido, valor_mag, valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")),
                             0, campo_churro)
    elif modo == "BateriaOE2":
        limite_hucha = 1000 * _n(tarifa.get("precio_excedente")) / 100
        r = factura_octopus(hucha_anterior, dias, total_kwh, p, p_boe, en, total_peajes, bono_social, em,
                             gas_incluido, valor_mag, valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")),
                             limite_hucha, campo_churro)
    elif modo == "BateriaAgri":
        r = factura_agri(hucha_anterior, dias, total_kwh, p, p_boe, en, total_peajes, bono_social,
                          gas_incluido, valor_mag, valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")), em)
    elif modo == "BateriaEL":
        r = factura_esluz(hucha_anterior, dias, total_kwh, p, p_boe, en, total_peajes, bono_social,
                           gas_incluido, valor_mag, valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")),
                           em, campo_churro)
    elif modo == "BateriaBE":
        r = factura_bassols(hucha_anterior, dias, total_kwh, p, p_boe, en, total_peajes, bono_social,
                             gas_incluido, valor_mag, valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")),
                             em, campo_churro)
    elif modo == "BateriaME":
        r = factura_met(hucha_anterior, dias, total_kwh, p, p_boe, en, total_peajes, bono_social,
                         gas_incluido, valor_mag, valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")),
                         em, campo_churro)
    elif modo == "BateriaME2":
        r = factura_met2(hucha_anterior, dias, total_kwh, p, p_boe, en, total_peajes, bono_social,
                          gas_incluido, valor_mag, valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")),
                          em, campo_churro)
    elif modo == "BNA_BE":
        r = factura_bassols_bna(hucha_anterior, dias, total_kwh, p, p_boe, en, total_peajes, bono_social,
                                 potencia_pico, valor_mag, excedentes_finales, ie, alq_cont, _n(globals_.get("iva_pct")),
                                 em, ekwp, campo_churro)
    elif modo == "BNA_EE":
        r = factura_esmiluz_bna(hucha_anterior, dias, total_kwh, p, p_boe, en, total_peajes, bono_social,
                                 potencia_pico, valor_mag, excedentes_finales, ie, alq_cont, _n(globals_.get("iva_pct")), ekwp)
    elif modo == "BateriaIber":
        r = factura_iberdola(hucha_anterior, dias, total_kwh, p, p_boe, en, bono_social, valor_mag,
                              valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")), em)
    elif modo == "BateriaIE":
        r = factura_imagina(hucha_anterior, dias, total_kwh, p, p_boe, en, bono_social, valor_mag,
                             valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")), em)
    elif modo == "BateriaRep":
        r = factura_repsol(hucha_anterior, dias, total_kwh, p, p_boe, en, bono_social, valor_mag,
                            valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")), em)
    elif modo == "BateriaRep2":
        r = factura_repsol2(hucha_anterior, dias, total_kwh, p, p_boe, en, bono_social, valor_mag,
                             valor_excedentes, ie, alq_cont, _n(globals_.get("iva_pct")), em,
                             excedentes_finales, consumo_acumulado, excedentes_acumulados)
    else:
        raise ValueError(f"Mètode desconegut: {modo!r} (tarifa {tarifa.get('comercializadora')} / {tarifa.get('tarifa')})")

    return ResultatMes(total=r.total_factura, desglossament=r.desglossament, hucha_nueva=r.hucha_nueva)


def calcular_tarifa_meses(tarifa: dict, meses: list[dict], globals_: dict) -> list[ResultatMes]:
    """Processa tots els mesos d'una tarifa EN ORDRE, encadenant l'estat
    (bateria virtual / balanç net / acumulats) d'un mes al següent, tal com fa
    Excel amb GetBatteryInfo(fila, columna-1)/AddBatteryInfo."""
    resultats = []
    hucha = 0.0
    consumo_acum = 0.0
    excedentes_acum = 0.0
    for mes in meses:
        r = calcular_factura_mes(mes, tarifa, globals_, hucha, consumo_acum, excedentes_acum)
        resultats.append(r)
        hucha = r.hucha_nueva
        consumo_acum += _n(mes.get("consumo_p1")) + _n(mes.get("consumo_p2")) + _n(mes.get("consumo_p3"))
        excedentes_acum += _n(mes.get("kwh_exc"))
    return resultats
