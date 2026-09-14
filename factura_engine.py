"""
Port a Python del motor de càlcul de factures del Simulador de Tarifes.

Estat actual: implementa fidelment el camí GENÈRIC (funció `FacturaGenerica`
de Módulo1.bas), que cobreix les tarifes amb Método buit, "PVPC" o "Consumo"
al full Tarifas (~52% de les tarifes reals a la versió V249, i el mètode
per defecte per a qualsevol tarifa nova que no necessiti bateria virtual).

Els mètodes "BateriaXXX" / "BNA_XXX" / "Proxima" criden a funcions
específiques per comercialitzadora que ENCARA NO estan portades (veure
`FACTURA_ESPECIFICAS_PENDENTS` al final). Cridar-les avui llença
`FacturaNoImplementada`.

Cada funció porta el nom i la línia aproximada de la funció VBA original
(Módulo1.bas / Módulo2.bas) de la qual s'ha traduït, per facilitar la
comparació i la validació.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Constants "hardcoded" a Módulo1.bas, Function FACTURA (línies ~3272-3277).
# L'autor original ja avisa que cal actualitzar-les manualment quan canvien
# els peatges i càrrecs regulats o la potència BOE de referència.
# ---------------------------------------------------------------------------
PEAJE_P1 = 9.7553   # c€/kWh
PEAJE_P2 = 2.9267   # c€/kWh
PEAJE_P3 = 0.33     # c€/kWh

POT_BOE_P1 = 27.7044  # €/kW y año
POT_BOE_P2 = 0.7254   # €/kW y año


class FacturaNoImplementada(NotImplementedError):
    """El mètode de càlcul d'aquesta tarifa encara no s'ha portat a Python."""


# ---------------------------------------------------------------------------
# DecodeParams (Módulo2.bas ~L210) — parseja el "campo churro" de la columna
# N de Tarifas (info_tecnica_indexada), amb format "IDX=Nom|DSV=0,2|FNEE=..."
# ---------------------------------------------------------------------------
@dataclass
class ParametrosIndexada:
    indexada: str = ""
    dsv: float = 0.15
    fnee: float = 0.0975
    gdo: float = 0.5
    fee: float = 0.0
    bs: float = 0.0


def decode_params(campo_churro: Optional[str]) -> ParametrosIndexada:
    p = ParametrosIndexada()
    if campo_churro:
        for trozo in str(campo_churro).strip().split("|"):
            trozo = trozo.strip()
            if not trozo:
                continue
            partes = trozo.split("=", 1)
            prop = partes[0].strip()
            valor = partes[1].strip() if len(partes) > 1 else None

            if prop == "IDX":
                p.indexada = valor if valor else "Default"
            elif prop == "DSV" and valor is not None:
                p.dsv = _num(valor)
            elif prop == "FNEE" and valor is not None:
                p.fnee = _num(valor)
            elif prop == "GdO" and valor is not None:
                p.gdo = _num(valor)
            elif prop == "FEE" and valor is not None:
                p.fee = _num(valor)
            elif prop == "BS" and valor is not None:
                p.bs = _num(valor)

    if p.indexada == "":
        # Si no és indexada (o no hi ha campo_churro), tot a zero (Módulo2.bas L264-270)
        p.dsv = p.fnee = p.gdo = p.fee = p.bs = 0.0

    return p


def _num(s: str) -> float:
    """Equivalent a ConvertirNumeroComoStringToDecimal: accepta coma o punt decimal."""
    return float(str(s).replace(",", "."))


# ---------------------------------------------------------------------------
# RecalcularPrecioEnergiaSiEsIndexada (Módulo1.bas ~L37-152)
#
# IMPORTANT (comentari original, textual): "Todos los valores aquí
# expresados son céntimos por kWh. Los precios P1, P2 y P3 para una
# indexada que no sea PVPC ya vienen elevados a pérdidas, pero sin FEE ni
# TM ni FNEE ni GdO. Vienen ya con los peajes."
# ---------------------------------------------------------------------------
TM = 1.015   # Tasas Municipales 1.5%
PERD = 1.2   # Elevación a pérdidas ~20%


def recalcular_precio_energia_si_es_indexada(
    campo_churro: Optional[str],
    precio_p1: float, precio_p2: float, precio_p3: float,
    peaje_p1: float, peaje_p2: float, peaje_p3: float,
    tipo_franja: str,
) -> tuple[float, float, float, ParametrosIndexada]:
    """Retorna (precioP1, precioP2, precioP3, params) ajustats si la tarifa és indexada."""
    params = decode_params(campo_churro)
    idx = params.indexada
    dsv, fnee, gdo, fee, bs = params.dsv, params.fnee, params.gdo, params.fee, params.bs

    if tipo_franja != "Normal" or idx == "":
        return precio_p1, precio_p2, precio_p3, params

    def ajustar(p, peaje, formula):
        return formula(p, peaje)

    if idx == "PVPC":
        pass  # no es toca; PVPC ja ve amb el preu mitjà
    elif idx == "Bassols":
        precio_p1 = (precio_p1 - peaje_p1 * TM) + peaje_p1
        precio_p2 = (precio_p2 - peaje_p2 * TM) + peaje_p2
        precio_p3 = (precio_p3 - peaje_p3 * TM) + peaje_p3
    elif idx == "Bonarea":
        precio_p1 = (((precio_p1 - peaje_p1 + (fnee + dsv) * PERD) + fee) * TM) + peaje_p1
        precio_p2 = (((precio_p2 - peaje_p2 + (fnee + dsv) * PERD) + fee) * TM) + peaje_p2
        precio_p3 = (((precio_p3 - peaje_p3 + (fnee + dsv) * PERD) + fee) * TM) + peaje_p3
    elif idx == "Bonpreu":
        precio_p1 = ((precio_p1 - peaje_p1 + (fnee + fee + dsv + gdo) * PERD) * TM) + peaje_p1
        precio_p2 = ((precio_p2 - peaje_p2 + (fnee + fee + dsv + gdo) * PERD) * TM) + peaje_p2
        precio_p3 = ((precio_p3 - peaje_p3 + (fnee + fee + dsv + gdo) * PERD) * TM) + peaje_p3
    elif idx == "Chippio":
        gf = 0.2
        precio_p1 = (((precio_p1 - peaje_p1 + (fnee + dsv) * PERD) + gf) * TM) + peaje_p1
        precio_p2 = (((precio_p2 - peaje_p2 + (fnee + dsv) * PERD) + gf) * TM) + peaje_p2
        precio_p3 = (((precio_p3 - peaje_p3 + (fnee + dsv) * PERD) + gf) * TM) + peaje_p3
    elif idx == "Clarity":
        precio_p1 = ((precio_p1 - peaje_p1 + (fnee + fee) * PERD) * TM) + peaje_p1
        precio_p2 = ((precio_p2 - peaje_p2 + (fnee + fee) * PERD) * TM) + peaje_p2
        precio_p3 = ((precio_p3 - peaje_p3 + (fnee + fee) * PERD) * TM) + peaje_p3
    elif idx == "E-Luz":
        precio_p1 = (precio_p1 - peaje_p1 + fnee + fee) * TM + peaje_p1
        precio_p2 = (precio_p2 - peaje_p2 + fnee + fee) * TM + peaje_p2
        precio_p3 = (precio_p3 - peaje_p3 + fnee + fee) * TM + peaje_p3
    elif idx == "Esmiluz":
        precio_p1 = (((precio_p1 - peaje_p1 + (fee + dsv) * PERD) + fnee) * TM) + gdo + peaje_p1
        precio_p2 = (((precio_p2 - peaje_p2 + (fee + dsv) * PERD) + fnee) * TM) + gdo + peaje_p2
        precio_p3 = (((precio_p3 - peaje_p3 + (fee + dsv) * PERD) + fnee) * TM) + gdo + peaje_p3
    elif idx == "Fenie":
        precio_p1 = ((precio_p1 - peaje_p1 + (fnee + fee) * PERD) * TM) + peaje_p1
        precio_p2 = ((precio_p2 - peaje_p2 + (fnee + fee) * PERD) * TM) + peaje_p2
        precio_p3 = ((precio_p3 - peaje_p3 + (fnee + fee) * PERD) * TM) + peaje_p3
    elif idx == "Helios":
        precio_p1 = (((precio_p1 - peaje_p1) + fnee * PERD + fee + dsv) * TM) + peaje_p1
        precio_p2 = (((precio_p2 - peaje_p2) + fnee * PERD + fee + dsv) * TM) + peaje_p2
        precio_p3 = (((precio_p3 - peaje_p3) + fnee * PERD + fee + dsv) * TM) + peaje_p3
    elif idx == "HeliosGrinch":
        precio_p1 = (((precio_p1 - peaje_p1) + fnee + fee * PERD) * TM) + peaje_p1
        precio_p2 = (((precio_p2 - peaje_p2) + fnee + fee * PERD) * TM) + peaje_p2
        precio_p3 = (((precio_p3 - peaje_p3) + fnee + fee * PERD) * TM) + peaje_p3
    elif idx == "Lidera":
        precio_p1 = (precio_p1 - peaje_p1 * TM) + fnee + dsv + peaje_p1
        precio_p2 = (precio_p2 - peaje_p2 * TM) + fnee + dsv + peaje_p2
        precio_p3 = (precio_p3 - peaje_p3 * TM) + fnee + dsv + peaje_p3
    elif idx == "Lumio":
        precio_p1 = ((precio_p1 - peaje_p1 + fnee) * TM) + peaje_p1
        precio_p2 = ((precio_p2 - peaje_p2 + fnee) * TM) + peaje_p2
        precio_p3 = ((precio_p3 - peaje_p3 + fnee) * TM) + peaje_p3
    elif idx == "Met":
        precio_p1 = ((precio_p1 - peaje_p1 + (bs + fee + dsv) * PERD) * TM) + peaje_p1
        precio_p2 = ((precio_p2 - peaje_p2 + (bs + fee + dsv) * PERD) * TM) + peaje_p2
        precio_p3 = ((precio_p3 - peaje_p3 + (bs + fee + dsv) * PERD) * TM) + peaje_p3
    elif idx == "Octopus":
        precio_p1 = (((precio_p1 - peaje_p1 + fnee * PERD) + fee) * TM) + peaje_p1
        precio_p2 = (((precio_p2 - peaje_p2 + fnee * PERD) + fee) * TM) + peaje_p2
        precio_p3 = (((precio_p3 - peaje_p3 + fnee * PERD) + fee) * TM) + peaje_p3
    elif idx == "Proxima":
        pass  # tot es factura a part
    elif idx == "Som":
        precio_p1 = ((precio_p1 - peaje_p1 + dsv + gdo) * TM) + fnee + fee + peaje_p1
        precio_p2 = ((precio_p2 - peaje_p2 + dsv + gdo) * TM) + fnee + fee + peaje_p2
        precio_p3 = ((precio_p3 - peaje_p3 + dsv + gdo) * TM) + fnee + fee + peaje_p3
    elif idx == "Wekiwi":
        precio_p1 = (((precio_p1 - peaje_p1) + (fnee + fee + dsv) * PERD) * TM) + peaje_p1
        precio_p2 = (((precio_p2 - peaje_p2) + (fnee + fee + dsv) * PERD) * TM) + peaje_p2
        precio_p3 = (((precio_p3 - peaje_p3) + (fnee + fee + dsv) * PERD) * TM) + peaje_p3
    elif idx == "Default":
        precio_p1 = ((precio_p1 - peaje_p1 + (fnee + fee + gdo) * PERD) * TM) + peaje_p1
        precio_p2 = ((precio_p2 - peaje_p2 + (fnee + fee + gdo) * PERD) * TM) + peaje_p2
        precio_p3 = ((precio_p3 - peaje_p3 + (fnee + fee + gdo) * PERD) * TM) + peaje_p3
    # si idx no coincideix amb cap dels anteriors, no es toca (igual que el VBA)

    return precio_p1, precio_p2, precio_p3, params


# ---------------------------------------------------------------------------
# Funcions auxiliars petites (Módulo1.bas ~L29-239)
# ---------------------------------------------------------------------------
def calcular_potencia(dias, pot_p1, precio_pot_p1, pot_p2, precio_pot_p2):
    return dias * (pot_p1 * precio_pot_p1 + pot_p2 * precio_pot_p2) / 365


def calcular_energia(kwh_p1, precio_p1, kwh_p2, precio_p2, kwh_p3, precio_p3, tipo_franja,
                      kwh_barato_nocturna, kwh_caro_nocturna, kwh_barato_ve, kwh_caro_ve,
                      kwh_barato_solar, kwh_caro_solar, kwh_50h_gratis, kwh_2h_gratis,
                      kwh_3h_gratis, kwh_promo_sunclub, kwh_gratis_sunclub, kwh_no_promo_sunclub):
    total_kwh = kwh_p1 + kwh_p2 + kwh_p3

    if tipo_franja == "Normal":
        return (precio_p1 * kwh_p1 + precio_p2 * kwh_p2 + precio_p3 * kwh_p3) / 100
    elif tipo_franja == "Nocturna-14h" and abs(total_kwh - ((kwh_caro_nocturna or 0) + (kwh_barato_nocturna or 0))) < 1:
        return (precio_p1 * kwh_caro_nocturna + precio_p3 * kwh_barato_nocturna) / 100
    elif tipo_franja == "VE-6h" and abs(total_kwh - ((kwh_caro_ve or 0) + (kwh_barato_ve or 0))) < 1:
        return (precio_p1 * kwh_caro_ve + precio_p3 * kwh_barato_ve) / 100
    elif (tipo_franja == "VE2-6h" and kwh_caro_ve is not None and kwh_barato_ve is not None
          and abs(total_kwh - (kwh_caro_ve + kwh_barato_ve)) < 1):
        if total_kwh and (kwh_caro_ve / total_kwh) < 0.4:
            return (precio_p1 * 0.4 * total_kwh + precio_p3 * 0.6 * total_kwh) / 100
        return (precio_p1 * kwh_caro_ve + precio_p3 * kwh_barato_ve) / 100
    elif tipo_franja == "Solar-16h" and abs(total_kwh - ((kwh_caro_solar or 0) + (kwh_barato_solar or 0))) < 1:
        return (precio_p1 * kwh_caro_solar + precio_p3 * kwh_barato_solar) / 100
    elif tipo_franja == "VE-NyF":
        return (precio_p1 * (kwh_p1 + kwh_p2) + precio_p3 * kwh_p3) / 100
    elif tipo_franja == "50hGratis" and kwh_50h_gratis not in (None, ""):
        return (precio_p1 * (total_kwh - kwh_50h_gratis)) / 100
    elif tipo_franja == "2hGratis" and kwh_2h_gratis not in (None, ""):
        return (precio_p1 * (total_kwh - kwh_2h_gratis)) / 100
    elif tipo_franja == "3hGratis" and kwh_3h_gratis not in (None, ""):
        return (precio_p1 * (total_kwh - kwh_3h_gratis)) / 100
    elif (tipo_franja == "Sun-Club" and abs(total_kwh - (
            (kwh_promo_sunclub or 0) + (kwh_gratis_sunclub or 0) + (kwh_no_promo_sunclub or 0))) < 1):
        return (precio_p1 * ((kwh_no_promo_sunclub or 0) + (kwh_gratis_sunclub or 0) + (kwh_promo_sunclub or 0))) / 100
    return 0.0


def calcular_descuento_despues_iva(kwh_p1, precio_p1, kwh_p2, precio_p2, kwh_p3, precio_p3, tipo_franja,
                                    kwh_barato_nocturna, kwh_caro_nocturna, kwh_barato_ve, kwh_caro_ve,
                                    kwh_barato_solar, kwh_caro_solar, kwh_50h_gratis, kwh_2h_gratis,
                                    kwh_3h_gratis, kwh_promo_sunclub, kwh_gratis_sunclub, kwh_no_promo_sunclub):
    total_kwh = kwh_p1 + kwh_p2 + kwh_p3
    if (tipo_franja == "Sun-Club" and abs(total_kwh - (
            (kwh_promo_sunclub or 0) + (kwh_gratis_sunclub or 0) + (kwh_no_promo_sunclub or 0))) < 1):
        return (precio_p1 * kwh_promo_sunclub - precio_p3 * kwh_promo_sunclub + precio_p1 * kwh_gratis_sunclub) / 100
    return 0.0


def calcular_bono_social(aportacion_diaria, dias):
    return aportacion_diaria * dias


def calcular_mag(consumo_total_kwh, precio_ajuste_gas_centimos):
    return consumo_total_kwh * precio_ajuste_gas_centimos / 100


def calcular_valor_excedentes(kwh_exc, precio_exc):
    if kwh_exc is None or precio_exc is None:
        return 0.0
    return (kwh_exc * precio_exc) / 100


def calcular_impuesto_electrico(termino_potencia, termino_energia, valor_excedentes,
                                 consumo_total, ie, bono_social, peajes):
    max_excedentes = valor_excedentes
    if valor_excedentes > 0 and peajes > 0:
        energia_no_compensable = min(termino_energia, peajes)
        max_excedentes = min(valor_excedentes, termino_energia - energia_no_compensable)
    valor_energia = termino_energia - max_excedentes
    if valor_energia < 0:
        valor_energia = 0

    impuesto = (termino_potencia + valor_energia + bono_social) * ie / 100
    impuesto_por_consumo = consumo_total * 0.001
    return max(impuesto, impuesto_por_consumo)


def calcular_margen_consumo(idx: str, fee: float) -> float:
    if idx in ("Bonpreu", "Clarity"):
        return fee * 1.2
    return fee


# ---------------------------------------------------------------------------
# FacturaGenerica (Módulo1.bas ~L374-612)
# Aquí no reconstrueixo el text "sFactura" de depuració (és només per mostrar
# el desglossat a Excel); en canvi retorno un desglossament estructurat.
# ---------------------------------------------------------------------------
@dataclass
class ResultatFactura:
    total: float
    desglossament: dict = field(default_factory=dict)


def factura_generica(dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                      total_peajes, bono_social, modo, valor_mag, valor_excedentes, ie,
                      alq_cont, iva, margen_mensual, margen_excedentes, descuento_despues_iva,
                      campo_churro) -> ResultatFactura:
    params = decode_params(campo_churro)
    idx = params.indexada
    fee = params.fee
    indexada = idx != ""

    gas_incluido = False  # sempre fals: FACTURA() ho força així (veure comentari a Módulo1.bas L3263)

    autoconsumo = (modo not in (None, "")) and (valor_excedentes > 0)
    energia_no_compensable = 0.0

    margen_energia = 0.0
    if indexada:
        margen_energia = consumo_total * calcular_margen_consumo(idx, fee) / 100

    limite_primera_compensacion = termino_energia
    if not gas_incluido:
        limite_primera_compensacion = termino_energia + valor_mag
        energia_no_compensable = valor_mag

    if autoconsumo:
        if modo == "Consumo":
            pass  # càlcul per defecte
        elif modo == "Energía-MAG":
            energia_no_compensable = valor_mag
            limite_primera_compensacion = termino_energia
        elif modo == "PVPC":
            if gas_incluido:
                energia_no_compensable = total_peajes + valor_mag
                limite_primera_compensacion = termino_energia - energia_no_compensable
            else:
                energia_no_compensable = min(termino_energia, total_peajes)
                limite_primera_compensacion = termino_energia - energia_no_compensable

    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        excedentes_regalados = valor_excedentes - limite_primera_compensacion
    else:
        excedentes_destinados_energia = valor_excedentes
        excedentes_regalados = 0.0

    conceptos_compensables_facturados = (limite_primera_compensacion - excedentes_destinados_energia) + energia_no_compensable

    cuota_energia = ((margen_mensual * 12) / 365) * dias
    cuota_excedentes = ((margen_excedentes * 12) / 365) * dias
    if valor_excedentes < cuota_excedentes:
        cuota_excedentes = cuota_excedentes * (valor_excedentes / cuota_excedentes) if cuota_excedentes else 0.0

    garantias_origen = 0.0
    fondo_nee = 0.0
    margen_fee_en_factura = 0.0
    tasa_municipal = 0.0

    if idx == "Proxima":
        fondo_nee = consumo_total * params.fnee / 100

    if idx in ("Proxima", "Lumio"):
        margen_fee_en_factura = consumo_total * fee / 100

    if idx == "Proxima":
        tasa_municipal = ((termino_energia - total_peajes) + fondo_nee + garantias_origen + bono_social) * 1.5 / 100

    if idx in ("Proxima", "Lumio", "Bassols"):
        garantias_origen = consumo_total * params.gdo / 100
        ie = ie + garantias_origen * 5.1127 / 100
        if idx == "Proxima":
            ie = ie + fondo_nee * 5.1127 / 100
            ie = ie + tasa_municipal * 5.1127 / 100

    base_imponible = (termino_potencia + conceptos_compensables_facturados + bono_social + alq_cont
                       + ie + fondo_nee + tasa_municipal + garantias_origen + margen_fee_en_factura)

    base_imponible_servicios = 0.0
    if idx == "Proxima":
        base_imponible += cuota_energia + cuota_excedentes
    else:
        base_imponible_servicios = cuota_energia + cuota_excedentes

    if indexada and idx == "Met":
        base_imponible -= bono_social

    total_iva = base_imponible * iva / 100
    total_iva_servicios = base_imponible_servicios * 21 / 100
    total = base_imponible + total_iva + base_imponible_servicios + total_iva_servicios

    if descuento_despues_iva > 0:
        total -= descuento_despues_iva

    return ResultatFactura(
        total=total,
        desglossament=dict(
            potencia_facturada=termino_potencia,
            energia_consumida=termino_energia,
            peajes_y_cargos=total_peajes,
            excedente_energia=valor_excedentes,
            excedentes_destino_energia=excedentes_destinados_energia,
            excedentes_regalados=excedentes_regalados,
            energia_facturada_final=conceptos_compensables_facturados,
            bono_social=bono_social,
            alquiler_equipos=alq_cont,
            impuesto_electricidad=ie,
            cuota_energia=cuota_energia if idx == "Proxima" else None,
            cuota_por_fee=margen_fee_en_factura if margen_fee_en_factura > 0 else None,
            cuota_excedentes=cuota_excedentes if idx == "Proxima" else None,
            fnee=fondo_nee if fondo_nee > 0 else None,
            garantias_origen=garantias_origen if garantias_origen > 0 else None,
            tasa_municipal=tasa_municipal if tasa_municipal > 0 else None,
            base_imponible=base_imponible,
            iva=total_iva,
            base_imponible_servicios=base_imponible_servicios if base_imponible_servicios > 0 else None,
            iva_servicios=total_iva_servicios if base_imponible_servicios > 0 else None,
            descuento_siguiente_factura=descuento_despues_iva if descuento_despues_iva > 0 else None,
            margen_consumo=margen_energia if indexada else None,
        ),
    )


# ---------------------------------------------------------------------------
# FacturaNaturgy (Módulo1.bas ~L2919-3018) — bateria virtual ("hucha")
#
# A diferència del genèric, aquí SÍ hi ha estat entre mesos: els excedents
# que no s'han pogut compensar dins del mateix mes es queden a la "hucha"
# (Bateria Virtual) i es fan servir per pagar factures de mesos següents.
# HuchaAnterior/HuchaNueva es passen de mes en mes en ordre cronològic.
# ---------------------------------------------------------------------------
@dataclass
class ResultatFacturaBateria:
    total_factura: float           # el que realment es paga aquest mes (després d'usar la bateria)
    hucha_nueva: float             # saldo de bateria virtual que passa al mes següent
    desglossament: dict = field(default_factory=dict)


def factura_naturgy(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe,
                     termino_energia, bono_social, valor_mag, valor_excedentes, ie,
                     alq_cont, iva, extra_mensual) -> ResultatFacturaBateria:
    factura_con_bateria_virtual = (valor_excedentes > 0) or (hucha_anterior > 0)

    limite_primera_compensacion = termino_energia + valor_mag

    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
    else:
        excedentes_destinados_energia = valor_excedentes
        incremento_bateria_virtual = 0.0

    cuota_mensual = 0.0
    if extra_mensual > 0 and factura_con_bateria_virtual:
        cuota_mensual = extra_mensual * 12 / 365 * dias

    energia_facturada = limite_primera_compensacion - excedentes_destinados_energia
    base_imponible = termino_potencia + energia_facturada + bono_social + alq_cont + ie
    base_imponible_servicios = cuota_mensual
    total_iva = base_imponible * iva / 100
    total_iva_servicios = base_imponible_servicios * 21 / 100
    total = base_imponible + total_iva + base_imponible_servicios + total_iva_servicios

    if hucha_anterior >= total:
        uso_bateria_virtual = total
        hucha_restante = hucha_anterior - uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_anterior
        hucha_restante = 0.0

    hucha_nueva = hucha_restante + incremento_bateria_virtual
    total_factura = total - uso_bateria_virtual

    return ResultatFacturaBateria(
        total_factura=total_factura,
        hucha_nueva=hucha_nueva,
        desglossament=dict(
            potencia_facturada=termino_potencia,
            energia_consumida=termino_energia,
            ajuste_gas=valor_mag,
            excedente_energia=valor_excedentes if factura_con_bateria_virtual else None,
            excedentes_destino_energia=excedentes_destinados_energia if factura_con_bateria_virtual else None,
            incremento_bateria_virtual=incremento_bateria_virtual if factura_con_bateria_virtual else None,
            energia_facturada=energia_facturada if factura_con_bateria_virtual else None,
            bono_social=bono_social,
            alquiler_equipos=alq_cont,
            impuesto_electricidad=ie,
            base_imponible=base_imponible,
            iva=total_iva,
            cuota_mensual_bateria=cuota_mensual if cuota_mensual > 0 else None,
            iva_servicios=total_iva_servicios if cuota_mensual > 0 else None,
            total_antes_bateria=total,
            uso_bateria_virtual=uso_bateria_virtual if factura_con_bateria_virtual else None,
            acumulas_bateria_virtual=hucha_nueva if factura_con_bateria_virtual else None,
        ),
    )


def factura_naturgy(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe,
                     termino_energia, bono_social, valor_mag, valor_excedentes, ie,
                     alq_cont, iva, extra_mensual) -> ResultatFacturaBateria:
    factura_con_bateria_virtual = (valor_excedentes > 0) or (hucha_anterior > 0)

    limite_primera_compensacion = termino_energia + valor_mag

    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
    else:
        excedentes_destinados_energia = valor_excedentes
        incremento_bateria_virtual = 0.0

    cuota_mensual = 0.0
    if extra_mensual > 0 and factura_con_bateria_virtual:
        cuota_mensual = extra_mensual * 12 / 365 * dias

    energia_facturada = limite_primera_compensacion - excedentes_destinados_energia
    base_imponible = termino_potencia + energia_facturada + bono_social + alq_cont + ie
    base_imponible_servicios = cuota_mensual
    total_iva = base_imponible * iva / 100
    total_iva_servicios = base_imponible_servicios * 21 / 100
    total = base_imponible + total_iva + base_imponible_servicios + total_iva_servicios

    if hucha_anterior >= total:
        uso_bateria_virtual = total
        hucha_restante = hucha_anterior - uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_anterior
        hucha_restante = 0.0

    hucha_nueva = hucha_restante + incremento_bateria_virtual
    total_factura = total - uso_bateria_virtual

    return ResultatFacturaBateria(total_factura=total_factura, hucha_nueva=hucha_nueva, desglossament={})


# --- Patró compartit "hucha simple": tot el que no es compensi de seguida
# s'acumula i es descompta íntegrament (capital+IVA) al primer mes que hi hagi
# prou saldo. FacturaFactor, Bonpreu, Nufri, Lidera, Lumio, SomEnergia, Agri,
# EsLuz, Bassols, MET, MET2, Repsol, Repsol2, Iberdrola i Imagina en són
# variacions amb petites diferències de marge/límit/base imposable. --------

def factura_factor(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                    bono_social, gas_incluido, valor_mag, valor_bruto_excedentes, kwh_excedentes,
                    ie, alq_cont, iva) -> ResultatFacturaBateria:
    limite_primera_compensacion = termino_energia if gas_incluido else termino_energia + valor_mag

    margen_excedentes = kwh_excedentes * 0.003 if kwh_excedentes else 0.0
    valor_excedentes = valor_bruto_excedentes - margen_excedentes

    hucha_mas_excedentes = hucha_anterior + valor_excedentes
    if hucha_mas_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
        hucha_nueva = hucha_anterior + incremento_bateria_virtual
    else:
        excedentes_destinados_energia = hucha_mas_excedentes
        incremento_bateria_virtual = -hucha_anterior
        hucha_nueva = 0.0

    energia_facturada = limite_primera_compensacion - excedentes_destinados_energia
    base_imponible = termino_potencia + energia_facturada + bono_social + alq_cont + ie
    total_iva = base_imponible * iva / 100
    total = base_imponible + total_iva

    if incremento_bateria_virtual > 0 and kwh_excedentes:
        precio_excedentes_sin_margen = valor_bruto_excedentes / kwh_excedentes
        kwh_incremento_bateria = incremento_bateria_virtual / precio_excedentes_sin_margen if precio_excedentes_sin_margen else 0
        margen_bateria = kwh_incremento_bateria * (0.007 - 0.003)
        incremento_bateria_virtual -= margen_bateria
        hucha_nueva = hucha_anterior + incremento_bateria_virtual

    return ResultatFacturaBateria(total_factura=total, hucha_nueva=hucha_nueva, desglossament={})


def factura_bonpreu(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                     total_peajes, bono_social, gas_incluido, valor_mag, valor_excedentes, ie, alq_cont,
                     iva, margen_mensual, campo_churro) -> ResultatFacturaBateria:
    limite_primera_compensacion = termino_energia if gas_incluido else termino_energia + valor_mag

    hucha_mas_excedentes = hucha_anterior + valor_excedentes
    if hucha_mas_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
        hucha_nueva = hucha_anterior + incremento_bateria_virtual
    else:
        excedentes_destinados_energia = hucha_mas_excedentes
        incremento_bateria_virtual = -hucha_anterior
        hucha_nueva = 0.0

    cuota_mensual = (margen_mensual * 12) / 365 * dias
    energia_facturada = limite_primera_compensacion - excedentes_destinados_energia
    base_imponible = termino_potencia + energia_facturada + bono_social + alq_cont + ie + cuota_mensual
    total_iva = base_imponible * iva / 100
    total = base_imponible + total_iva

    return ResultatFacturaBateria(total_factura=total, hucha_nueva=hucha_nueva, desglossament={})


def factura_nufri(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                   bono_social, valor_mag, valor_excedentes, ie, alq_cont, iva, extra_mensual) -> ResultatFacturaBateria:
    limite_primera_compensacion = termino_energia + valor_mag

    hucha_mas_excedentes = hucha_anterior + valor_excedentes
    if hucha_mas_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
        hucha_nueva = hucha_anterior + incremento_bateria_virtual
    else:
        excedentes_destinados_energia = hucha_mas_excedentes
        incremento_bateria_virtual = -hucha_anterior
        hucha_nueva = 0.0

    energia_facturada = limite_primera_compensacion - excedentes_destinados_energia
    base_imponible = termino_potencia + energia_facturada + bono_social + alq_cont + ie
    total_iva = base_imponible * iva / 100
    total = base_imponible + total_iva

    if hucha_nueva >= total:
        uso_bateria_virtual = total
        hucha_nueva -= uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_nueva
        hucha_nueva = 0.0

    return ResultatFacturaBateria(total_factura=total - uso_bateria_virtual, hucha_nueva=hucha_nueva, desglossament={})


def factura_proxima_con_bv(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                            total_peajes, bono_social, valor_excedentes, ie, alq_cont, iva,
                            margen_mensual, margen_excedentes, total_exced, campo_churro) -> ResultatFacturaBateria:
    params = decode_params(campo_churro)
    gdo, fnee, fee = params.gdo, params.fnee, params.fee

    if margen_excedentes > 2:
        margen_por_excedentes = 0.0
    else:
        margen_por_excedentes = total_exced * margen_excedentes / 100
        valor_excedentes = valor_excedentes - margen_por_excedentes

    limite_primera_compensacion = termino_potencia + termino_energia + bono_social
    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
    else:
        excedentes_destinados_energia = valor_excedentes
        incremento_bateria_virtual = 0.0

    conceptos_facturados = limite_primera_compensacion - excedentes_destinados_energia

    reserva_excedentes = incremento_bateria_virtual * 0.07
    incremento_bateria_virtual -= reserva_excedentes

    if margen_excedentes > 2:
        cuota_energia = (4.9 * 12) / 365 * dias
        cuota_bateria = ((margen_mensual - 4.9) * 12) / 365 * dias
    else:
        cuota_energia = 0.0
        cuota_bateria = (margen_mensual * 12) / 365 * dias

    if valor_excedentes == 0 and hucha_anterior < cuota_bateria and cuota_bateria:
        cuota_bateria = cuota_bateria * (hucha_anterior / cuota_bateria)

    cuota_excedentes = (margen_excedentes * 12) / 365 * dias
    if valor_excedentes < cuota_excedentes and cuota_excedentes:
        cuota_excedentes = cuota_excedentes * (valor_excedentes / cuota_excedentes)

    garantias_origen = consumo_total * gdo / 100
    fondo_nee = consumo_total * fnee / 100
    margen_fee_en_factura = consumo_total * fee / 100
    tasa_municipal = ((termino_energia - total_peajes) + fondo_nee + garantias_origen + bono_social) * 1.5 / 100

    base_imponible = (conceptos_facturados + alq_cont + ie + cuota_energia + cuota_bateria + cuota_excedentes
                       + fondo_nee + tasa_municipal + garantias_origen + margen_fee_en_factura)
    total_iva = base_imponible * iva / 100
    total = base_imponible + total_iva

    hucha_nueva = hucha_anterior + incremento_bateria_virtual
    if hucha_nueva >= total:
        uso_bateria_virtual = total
        hucha_nueva -= uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_nueva
        hucha_nueva = 0.0

    return ResultatFacturaBateria(total_factura=total - uso_bateria_virtual, hucha_nueva=hucha_nueva, desglossament={})


def factura_proxima_sin_bv(dias, consumo_total, termino_potencia, potencia_boe, termino_energia, total_peajes,
                            bono_social, valor_excedentes, ie, alq_cont, iva, margen_mensual, margen_excedentes,
                            campo_churro) -> float:
    params = decode_params(campo_churro)
    gdo, fnee, fee = params.gdo, params.fnee, params.fee

    limite_primera_compensacion = termino_potencia + termino_energia + bono_social
    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
    else:
        excedentes_destinados_energia = valor_excedentes
    conceptos_facturados = limite_primera_compensacion - excedentes_destinados_energia

    cuota_energia = (margen_mensual * 12) / 365 * dias
    cuota_excedentes = (margen_excedentes * 12) / 365 * dias
    if valor_excedentes < cuota_excedentes and cuota_excedentes:
        cuota_excedentes = cuota_excedentes * (valor_excedentes / cuota_excedentes)

    garantias_origen = consumo_total * gdo / 100
    fondo_nee = consumo_total * fnee / 100
    margen_fee_en_factura = consumo_total * fee / 100
    tasa_municipal = ((termino_energia - total_peajes) + fondo_nee + garantias_origen + bono_social) * 1.5 / 100

    base_imponible = (conceptos_facturados + alq_cont + ie + cuota_energia + cuota_excedentes
                       + fondo_nee + tasa_municipal + garantias_origen + margen_fee_en_factura)
    total_iva = base_imponible * iva / 100
    return base_imponible + total_iva


def factura_lidera(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                    total_peajes, bono_social, valor_excedentes, ie, alq_cont, iva, margen_mensual,
                    campo_churro) -> ResultatFacturaBateria:
    limite_primera_compensacion = termino_potencia + termino_energia
    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
    else:
        excedentes_destinados_energia = valor_excedentes
        incremento_bateria_virtual = 0.0

    potencia_y_energia_facturada = limite_primera_compensacion - excedentes_destinados_energia
    cuota_mensual = (margen_mensual * 12) / 365 * dias
    base_imponible = potencia_y_energia_facturada + bono_social + alq_cont + ie + cuota_mensual
    total_iva = base_imponible * iva / 100
    total = base_imponible + total_iva

    hucha_nueva = hucha_anterior + incremento_bateria_virtual
    if hucha_nueva >= total:
        uso_bateria_virtual = total
        hucha_nueva -= uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_nueva
        hucha_nueva = 0.0

    return ResultatFacturaBateria(total_factura=total - uso_bateria_virtual, hucha_nueva=hucha_nueva, desglossament={})


def factura_helios(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                    total_peajes, bono_social, valor_bruto_excedentes, kwh_excedentes, ie, alq_cont, iva,
                    margen_mensual, campo_churro) -> ResultatFacturaBateria:
    reserva_excedentes = kwh_excedentes * 0.005 if kwh_excedentes else 0.0
    valor_excedentes = valor_bruto_excedentes - reserva_excedentes

    limite_primera_compensacion = termino_energia
    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
    else:
        excedentes_destinados_energia = valor_excedentes
        incremento_bateria_virtual = 0.0

    energia_facturada = limite_primera_compensacion - excedentes_destinados_energia
    cuota_mensual = (margen_mensual * 12) / 365 * dias
    base_imponible = termino_potencia + energia_facturada + bono_social + alq_cont + ie
    base_imponible_servicios = cuota_mensual
    total_iva = base_imponible * iva / 100
    total_iva_servicios = base_imponible_servicios * 21 / 100
    total = base_imponible + total_iva + base_imponible_servicios + total_iva_servicios

    hucha_nueva = hucha_anterior + incremento_bateria_virtual
    if hucha_nueva >= total:
        uso_bateria_virtual = total
        hucha_nueva -= uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_nueva
        hucha_nueva = 0.0

    return ResultatFacturaBateria(total_factura=total - uso_bateria_virtual, hucha_nueva=hucha_nueva, desglossament={})


def factura_lumio(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                   total_peajes, bono_social, valor_bruto_excedentes, ie, alq_cont, iva,
                   campo_churro) -> ResultatFacturaBateria:
    params = decode_params(campo_churro)
    idx, gdo, fee = params.indexada, params.gdo, params.fee

    valor_excedentes = valor_bruto_excedentes * 90 / 100  # Lumio es reserva un 10%

    limite_primera_compensacion = termino_energia
    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
    else:
        excedentes_destinados_energia = valor_excedentes
        incremento_bateria_virtual = 0.0

    energia_facturada = limite_primera_compensacion - excedentes_destinados_energia
    cuota_lumio = consumo_total * calcular_margen_consumo(idx, fee) / 100
    garantias_origen = consumo_total * gdo / 100

    base_imponible = termino_potencia + energia_facturada + bono_social + alq_cont + ie + cuota_lumio + garantias_origen
    total_iva = base_imponible * iva / 100
    total = base_imponible + total_iva

    hucha_nueva = hucha_anterior + incremento_bateria_virtual
    if hucha_nueva >= total:
        uso_bateria_virtual = total
        hucha_nueva -= uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_nueva
        hucha_nueva = 0.0

    return ResultatFacturaBateria(total_factura=total - uso_bateria_virtual, hucha_nueva=hucha_nueva, desglossament={})


def factura_som_energia(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                         total_peajes, bono_social, gas_incluido, valor_mag, valor_excedentes, ie, alq_cont,
                         iva, campo_churro) -> ResultatFacturaBateria:
    limite_primera_compensacion = termino_energia if gas_incluido else termino_energia + valor_mag

    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
        excedentes_regalados = incremento_bateria_virtual * 0.2
        incremento_bateria_virtual -= excedentes_regalados
    else:
        excedentes_destinados_energia = valor_excedentes
        incremento_bateria_virtual = 0.0

    hucha_nueva = hucha_anterior + incremento_bateria_virtual

    energia_facturada = limite_primera_compensacion - excedentes_destinados_energia
    base_imponible = termino_potencia + energia_facturada + bono_social + alq_cont + ie

    if hucha_anterior > 0:
        if hucha_anterior >= base_imponible:
            uso_bateria_virtual = base_imponible
            hucha_nueva -= uso_bateria_virtual
        else:
            uso_bateria_virtual = hucha_anterior
            hucha_nueva = 0.0
    else:
        uso_bateria_virtual = 0.0

    base_imponible2 = base_imponible - uso_bateria_virtual
    total_iva = base_imponible2 * iva / 100
    total = base_imponible2 + total_iva

    return ResultatFacturaBateria(total_factura=total, hucha_nueva=hucha_nueva, desglossament={})


def factura_octopus(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                     total_peajes, bono_social, extra_mensual, gas_incluido, valor_mag, valor_excedentes,
                     ie, alq_cont, iva, limite_hucha, campo_churro) -> ResultatFacturaBateria:
    limite_primera_compensacion = termino_energia if gas_incluido else termino_energia + valor_mag

    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
    else:
        excedentes_destinados_energia = valor_excedentes
        incremento_bateria_virtual = 0.0

    cuota_mensual = extra_mensual * 12 / 365 * dias if extra_mensual > 0 else 0.0

    energia_facturada = limite_primera_compensacion - excedentes_destinados_energia
    base_imponible = termino_potencia + energia_facturada + bono_social + alq_cont + ie + cuota_mensual
    total_iva = base_imponible * iva / 100
    total = base_imponible + total_iva

    excedente_usado_en_factura0 = min(incremento_bateria_virtual, total) if incremento_bateria_virtual > total else incremento_bateria_virtual
    incremento_bateria_virtual -= excedente_usado_en_factura0
    total_pendiente_compensar = total - excedente_usado_en_factura0

    if limite_hucha > 0 and incremento_bateria_virtual > limite_hucha:
        incremento_bateria_virtual = limite_hucha

    hucha_nueva = hucha_anterior + incremento_bateria_virtual

    if hucha_nueva >= total_pendiente_compensar:
        uso_bateria_virtual = total_pendiente_compensar
        hucha_nueva -= uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_nueva
        hucha_nueva = 0.0

    uso_bateria_virtual += excedente_usado_en_factura0
    return ResultatFacturaBateria(total_factura=total - uso_bateria_virtual, hucha_nueva=hucha_nueva, desglossament={})


def factura_agri(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                  total_peajes, bono_social, gas_incluido, valor_mag, valor_excedentes, ie, alq_cont,
                  iva, cuota_mensual_base) -> ResultatFacturaBateria:
    if gas_incluido:
        limite_primera_compensacion = termino_energia - total_peajes
    else:
        limite_primera_compensacion = termino_energia - total_peajes - valor_mag

    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
    else:
        excedentes_destinados_energia = valor_excedentes
        incremento_bateria_virtual = 0.0

    cuota_bateria = (cuota_mensual_base * 12) / 365 * dias
    energia_facturada = limite_primera_compensacion - excedentes_destinados_energia + total_peajes + valor_mag
    base_imponible = termino_potencia + energia_facturada + cuota_bateria + bono_social + alq_cont + ie
    total_iva = base_imponible * iva / 100
    total = base_imponible + total_iva

    hucha_nueva = hucha_anterior + incremento_bateria_virtual
    if hucha_nueva >= total:
        uso_bateria_virtual = total
        hucha_nueva -= uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_nueva
        hucha_nueva = 0.0

    return ResultatFacturaBateria(total_factura=total - uso_bateria_virtual, hucha_nueva=hucha_nueva, desglossament={})


def factura_esluz(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                   total_peajes, bono_social, gas_incluido, valor_mag, valor_excedentes, ie, alq_cont,
                   iva, extra_mensual, campo_churro) -> ResultatFacturaBateria:
    if gas_incluido:
        limite_primera_compensacion = termino_energia - total_peajes
    else:
        limite_primera_compensacion = termino_energia - total_peajes - valor_mag

    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
    else:
        excedentes_destinados_energia = valor_excedentes
        incremento_bateria_virtual = 0.0

    cuota_mensual = extra_mensual * 12 / 365 * dias if extra_mensual > 0 else 0.0

    if gas_incluido:
        energia_facturada = limite_primera_compensacion - excedentes_destinados_energia + total_peajes
    else:
        energia_facturada = limite_primera_compensacion - excedentes_destinados_energia + total_peajes + valor_mag

    cuota_remit_acer = 0.56
    base_imponible = termino_potencia + energia_facturada + cuota_mensual + bono_social + alq_cont + cuota_remit_acer + ie

    if hucha_anterior >= base_imponible:
        uso_bateria_virtual = base_imponible
        hucha_restante = hucha_anterior - uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_anterior
        hucha_restante = 0.0

    hucha_nueva = hucha_restante + incremento_bateria_virtual
    total_iva = (base_imponible - uso_bateria_virtual) * iva / 100
    total = (base_imponible - uso_bateria_virtual) + total_iva

    return ResultatFacturaBateria(total_factura=total, hucha_nueva=hucha_nueva, desglossament={})


def factura_bassols(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                     total_peajes, bono_social, gas_incluido, valor_mag, valor_excedentes, ie, alq_cont,
                     iva, extra_mensual, campo_churro) -> ResultatFacturaBateria:
    params = decode_params(campo_churro)
    idx, gdo = params.indexada, params.gdo

    if gas_incluido:
        limite_primera_compensacion = termino_energia - total_peajes
    else:
        limite_primera_compensacion = termino_energia - total_peajes - valor_mag

    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
    else:
        excedentes_destinados_energia = valor_excedentes
        incremento_bateria_virtual = 0.0

    cuota_mensual = extra_mensual * 12 / 365 * dias if extra_mensual > 0 else 0.0

    if gas_incluido:
        energia_facturada = limite_primera_compensacion - excedentes_destinados_energia + total_peajes
    else:
        energia_facturada = limite_primera_compensacion - excedentes_destinados_energia + total_peajes + valor_mag

    garantias_origen = consumo_total * gdo / 100 if idx == "Bassols" else 0.0

    base_imponible = termino_potencia + energia_facturada + cuota_mensual + bono_social + alq_cont + ie + garantias_origen
    total_iva = base_imponible * iva / 100
    total = base_imponible + total_iva

    hucha_nueva = hucha_anterior + incremento_bateria_virtual
    if hucha_nueva >= total:
        uso_bateria_virtual = total
        hucha_nueva -= uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_nueva
        hucha_nueva = 0.0

    return ResultatFacturaBateria(total_factura=total - uso_bateria_virtual, hucha_nueva=hucha_nueva, desglossament={})


def factura_met(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                 total_peajes, bono_social, gas_incluido, valor_mag, valor_excedentes, ie, alq_cont,
                 iva, extra_mensual, campo_churro) -> ResultatFacturaBateria:
    params = decode_params(campo_churro)
    idx, fee = params.indexada, params.fee
    indexada = idx != ""

    limite_primera_compensacion = termino_energia if gas_incluido else termino_energia + valor_mag

    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
    else:
        excedentes_destinados_energia = valor_excedentes
        incremento_bateria_virtual = 0.0

    cuota_mensual = extra_mensual * 12 / 365 * dias if (valor_excedentes > 0 and extra_mensual > 0) else 0.0

    if gas_incluido:
        energia_facturada = limite_primera_compensacion - excedentes_destinados_energia
    else:
        energia_facturada = limite_primera_compensacion - excedentes_destinados_energia + valor_mag

    base_imponible = termino_potencia + energia_facturada + alq_cont + ie
    if not indexada:
        base_imponible += bono_social

    total_iva = base_imponible * iva / 100
    total_iva_servicios = cuota_mensual * 21 / 100
    total = base_imponible + total_iva + cuota_mensual + total_iva_servicios

    hucha_nueva = hucha_anterior + incremento_bateria_virtual
    if hucha_nueva >= total:
        uso_bateria_virtual = total
        hucha_nueva -= uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_nueva
        hucha_nueva = 0.0

    return ResultatFacturaBateria(total_factura=total - uso_bateria_virtual, hucha_nueva=hucha_nueva, desglossament={})


def factura_met2(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                  total_peajes, bono_social, gas_incluido, valor_mag, valor_excedentes, ie, alq_cont,
                  iva, extra_mensual, campo_churro) -> ResultatFacturaBateria:
    params = decode_params(campo_churro)
    idx = params.indexada
    indexada = idx != ""

    if gas_incluido:
        limite_primera_compensacion = termino_energia - total_peajes
    else:
        limite_primera_compensacion = termino_energia - total_peajes - valor_mag

    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
    else:
        excedentes_destinados_energia = valor_excedentes
        incremento_bateria_virtual = 0.0

    cuota_mensual = extra_mensual * 12 / 365 * dias if (valor_excedentes > 0 and extra_mensual > 0) else 0.0

    if gas_incluido:
        energia_facturada = limite_primera_compensacion - excedentes_destinados_energia + total_peajes
    else:
        energia_facturada = limite_primera_compensacion - excedentes_destinados_energia + total_peajes + valor_mag

    base_imponible = termino_potencia + energia_facturada + bono_social + alq_cont + ie + cuota_mensual
    if indexada:
        base_imponible -= bono_social

    total_iva = base_imponible * iva / 100
    total = base_imponible + total_iva

    hucha_nueva = hucha_anterior + incremento_bateria_virtual
    if hucha_nueva >= total:
        uso_bateria_virtual = total
        hucha_nueva -= uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_nueva
        hucha_nueva = 0.0

    return ResultatFacturaBateria(total_factura=total - uso_bateria_virtual, hucha_nueva=hucha_nueva, desglossament={})


# --- "Balance Neto" (BNA): hucha en kWh, no en €. -------------------------
def factura_bassols_bna(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                         total_peajes, bono_social, potencia_pico_instalada, valor_mag, kwh_exc, ie, alq_cont,
                         iva, extra_mensual, extra_kwp, campo_churro) -> ResultatFacturaBateria:
    params = decode_params(campo_churro)
    gdo = params.gdo

    if kwh_exc + hucha_anterior >= consumo_total:
        energia_facturada = 0.0
        energia_ahorrada = termino_energia
    else:
        kwh_no_compensados = consumo_total - (kwh_exc + hucha_anterior)
        energia_facturada = (kwh_no_compensados * termino_energia) / consumo_total if consumo_total else 0.0
        energia_ahorrada = termino_energia - energia_facturada

    hucha_nueva = max(0.0, kwh_exc + hucha_anterior - consumo_total)

    if kwh_exc > 0:
        cuota_mensual = (extra_kwp * 12 / 365 * dias) * potencia_pico_instalada
    elif extra_mensual > 0:
        cuota_mensual = extra_mensual * 12 / 365 * dias
    else:
        cuota_mensual = 0.0

    garantias_origen = consumo_total * gdo / 100

    base_imponible = termino_potencia + energia_facturada + valor_mag + cuota_mensual + bono_social + alq_cont + ie + garantias_origen
    total_iva = (base_imponible + energia_ahorrada) * iva / 100
    total = base_imponible + total_iva

    return ResultatFacturaBateria(total_factura=total, hucha_nueva=hucha_nueva, desglossament={})


def factura_esmiluz_bna(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                         total_peajes, bono_social, potencia_pico_instalada, valor_mag, kwh_exc, ie, alq_cont,
                         iva, extra_kwp) -> ResultatFacturaBateria:
    # NOTA: el VBA original no crida DecodeParams aquí (probablement un oblit),
    # de manera que el "marge per consum (FEE)" sempre val 0 -- ho reproduïm igual.
    if kwh_exc + hucha_anterior >= consumo_total:
        energia_facturada = 0.0
        kwh_no_compensados = 0.0
    else:
        kwh_no_compensados = consumo_total - (kwh_exc + hucha_anterior)
        energia_facturada = (kwh_no_compensados * termino_energia) / consumo_total if consumo_total else 0.0

    hucha_nueva = max(0.0, kwh_exc + hucha_anterior - consumo_total)
    margen_por_consumo = 0.0  # veure nota anterior

    cuota_mensual = (extra_kwp * 12 / 365 * dias) * potencia_pico_instalada if kwh_exc > 0 else 0.0

    base_imponible = (termino_potencia + (energia_facturada + margen_por_consumo) + total_peajes + valor_mag
                       + cuota_mensual + bono_social + alq_cont + ie)
    total_iva = base_imponible * iva / 100
    total = base_imponible + total_iva

    return ResultatFacturaBateria(total_factura=total, hucha_nueva=hucha_nueva, desglossament={})


def factura_iberdola(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                      bono_social, valor_mag, valor_excedentes, ie, alq_cont, iva, extra_mensual) -> ResultatFacturaBateria:
    terminos_compensables = (termino_energia + valor_mag) + (termino_potencia + bono_social)
    limite_primera_compensacion = termino_energia + valor_mag
    limite_segunda_compensacion = terminos_compensables - limite_primera_compensacion

    total_excedentes_mas_hucha = valor_excedentes + hucha_anterior
    total_solar_cloud = total_excedentes_mas_hucha

    if total_solar_cloud >= limite_primera_compensacion:
        termino_compensacion_excedentes = limite_primera_compensacion
        if limite_primera_compensacion > valor_excedentes:
            hucha_anterior = hucha_anterior - (limite_primera_compensacion - valor_excedentes)
        total_solar_cloud -= termino_compensacion_excedentes
        if hucha_anterior >= limite_segunda_compensacion:
            termino_solar_cloud = limite_segunda_compensacion
        else:
            termino_solar_cloud = hucha_anterior
        total_solar_cloud -= termino_solar_cloud
    else:
        termino_compensacion_excedentes = total_solar_cloud
        termino_solar_cloud = 0.0
        total_solar_cloud = 0.0

    total_a_pagar = terminos_compensables - termino_compensacion_excedentes - termino_solar_cloud
    asistente_smart = (extra_mensual * 12) / 365 * dias
    importe_total = total_a_pagar + ie + alq_cont
    total_iva_reducido = (importe_total + termino_solar_cloud) * iva / 100
    total_iva_servicios = asistente_smart * 21 / 100
    total_factura = importe_total + total_iva_reducido + asistente_smart + total_iva_servicios

    hucha_nueva = total_solar_cloud
    limite_mensual = 1000  # €/mes (aparent error d'unitats a l'original: comentat com si fossin kWh)
    if (hucha_nueva - hucha_anterior) > limite_mensual:
        hucha_nueva = hucha_anterior + limite_mensual

    return ResultatFacturaBateria(total_factura=total_factura, hucha_nueva=hucha_nueva, desglossament={})


def factura_imagina(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                     bono_social, valor_mag, valor_excedentes, ie, alq_cont, iva, extra_mensual) -> ResultatFacturaBateria:
    limite_primera_compensacion = termino_energia + valor_mag
    if valor_excedentes >= limite_primera_compensacion:
        excedentes_destinados_energia = limite_primera_compensacion
        incremento_bateria_virtual = valor_excedentes - limite_primera_compensacion
    else:
        excedentes_destinados_energia = valor_excedentes
        incremento_bateria_virtual = 0.0

    energia_facturada = limite_primera_compensacion - excedentes_destinados_energia
    base_imponible = termino_potencia + energia_facturada + bono_social + alq_cont + ie
    total_iva = base_imponible * iva / 100
    total = base_imponible + total_iva

    if hucha_anterior >= total:
        uso_bateria_virtual = total
        hucha_restante = hucha_anterior - uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_anterior
        hucha_restante = 0.0

    hucha_nueva = hucha_restante + incremento_bateria_virtual
    return ResultatFacturaBateria(total_factura=total - uso_bateria_virtual, hucha_nueva=hucha_nueva, desglossament={})


def factura_repsol(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                    bono_social, valor_mag, valor_excedentes, ie, alq_cont, iva, extra_mensual) -> ResultatFacturaBateria:
    factura_con_bateria_virtual = (valor_excedentes > 0) or (hucha_anterior > 0)
    incremento_bateria_virtual = valor_excedentes if valor_excedentes >= 0 else 0.0

    cuota_mensual = extra_mensual * 12 / 365 * dias if (extra_mensual > 0 and factura_con_bateria_virtual) else 0.0

    energia_facturada = termino_energia + valor_mag
    base_imponible = termino_potencia + energia_facturada + bono_social + alq_cont + ie
    base_imponible_servicios = cuota_mensual
    total_iva = base_imponible * iva / 100
    total_iva_servicios = base_imponible_servicios * 21 / 100
    total = base_imponible + total_iva + base_imponible_servicios + total_iva_servicios

    if hucha_anterior >= total:
        uso_bateria_virtual = total
        hucha_restante = hucha_anterior - uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_anterior
        hucha_restante = 0.0

    hucha_nueva = hucha_restante + incremento_bateria_virtual
    return ResultatFacturaBateria(total_factura=total - uso_bateria_virtual, hucha_nueva=hucha_nueva, desglossament={})


def factura_repsol2(hucha_anterior, dias, consumo_total, termino_potencia, potencia_boe, termino_energia,
                     bono_social, valor_mag, valor_excedentes, ie, alq_cont, iva, extra_mensual,
                     excedentes_mes, consumo_acumulado, excedentes_acumulados) -> ResultatFacturaBateria:
    if excedentes_acumulados > consumo_acumulado * 1.4:
        valor_excedentes = calcular_valor_excedentes(excedentes_mes, 5)  # 5 c€/kWh

    factura_con_bateria_virtual = (valor_excedentes > 0) or (hucha_anterior > 0)
    incremento_bateria_virtual = valor_excedentes if valor_excedentes >= 0 else 0.0

    cuota_mensual = extra_mensual * 12 / 365 * dias if (extra_mensual > 0 and factura_con_bateria_virtual) else 0.0

    energia_facturada = termino_energia + valor_mag
    base_imponible = termino_potencia + energia_facturada + bono_social + alq_cont + ie
    base_imponible_servicios = cuota_mensual
    total_iva = base_imponible * iva / 100
    total_iva_servicios = base_imponible_servicios * 21 / 100
    total = base_imponible + total_iva + base_imponible_servicios + total_iva_servicios

    if hucha_anterior >= total:
        uso_bateria_virtual = total
        hucha_restante = hucha_anterior - uso_bateria_virtual
    else:
        uso_bateria_virtual = hucha_anterior
        hucha_restante = 0.0

    hucha_nueva = hucha_restante + incremento_bateria_virtual
    return ResultatFacturaBateria(total_factura=total - uso_bateria_virtual, hucha_nueva=hucha_nueva, desglossament={})


# ---------------------------------------------------------------------------
# Mètodes específics de comercialitzadora ENCARA NO PORTATS.
# Prioritzats per nombre de tarifes reals que els fan servir a V249
# (veure `extract_tarifas.py`, resum de "Distribució per mètode").
# ---------------------------------------------------------------------------
FACTURA_ESPECIFICAS_PENDENTS = {}

# "Modo" que van pel camí genèric (no necessiten estat/bateria virtual)
MODOS_GENERICOS = {None, "", "PVPC", "Consumo", "Energía-MAG"}
