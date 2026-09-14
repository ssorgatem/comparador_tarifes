# Simulador de Tarifes — reimplementació en Python

Port complet del motor de càlcul del `Simulador_de_Tarifas_Anual_V249.xlsm`
(funció VBA `FACTURA` i les ~20 funcions específiques per comercialitzadora
de Módulo1.bas).

## Estat: 153/153 tarifes implementades

**Validat contra l'Excel real** (6+ mesos de dades reals, 153 tarifes × 12
columnes = 1.836 cel·les comparades): **1.834/1.836 exactes (99,9%, marge
<0,01€)**. Les 2 úniques discrepàncies (Repsol "Tarifa Solar Batería
Virtual" a 10/2025, Esmiluz "SIE (BNA)" a 11/2025) són valors aïllats d'un
sol mes que no encaixen amb el patró dels mesos veïns (que sí coincideixen
exactament) — tot apunta a una cel·la de l'Excel amb un valor de càlcul
obsolet (aquest disseny basat en una taula VBA global oculta és fràgil
davant recàlculs parcials; el propi autor de l'Excel ja avisa que el
recàlcul no sempre funciona bé). Si vols, torna a prémer CALCULAR fent un
recàlcul complet (Ctrl+Alt+F9) a Excel i reenvia'm el fitxer per confirmar-ho.

## Fitxers

- `extract_tarifas.py` — full `Tarifas` (xlsm) → `tarifas.json`. Re-executable amb qualsevol versió futura del fitxer.
- `extract_datos.py` — full `Datos` (xlsm) → `datos.json`.
- `factura_engine.py` — totes les funcions de càlcul pures: el motor genèric i les 20 funcions específiques (Naturgy, Octopus, Bassols, Som Energia, E-Luz, MET, MET2, Bassols BNA, Esmiluz BNA, Iberdrola, Imagina, Repsol, Repsol2, Lidera, Helios, Lumio, Próxima (amb i sense bateria), Bonpreu, Factor, Nufri, Agri).
- `calcular.py` — `calcular_factura_mes(...)` (dispatcher, equivalent a `FACTURA()`) i `calcular_tarifa_meses(...)` (encadena l'estat de bateria virtual / balanç net mes a mes per a una tarifa).
- `ranking.py` — calcula el total anual de cada tarifa i les ordena (equivalent al full `Facturas`).
- `ranking_validacio.csv` — resultat del ranking complet sobre les teves dades reals (setembre 2025 – agost 2026), de referència.

## Ús

```bash
python3 extract_tarifas.py Simulador_de_Tarifas_Anual_V249.xlsm --out tarifas.json
python3 extract_datos.py   Simulador_de_Tarifas_Anual_V249.xlsm --out datos.json
python3 ranking.py tarifas.json datos.json --csv ranking.csv
```

## Notes sobre fidelitat

- Les constants de peatges/càrrecs (`PEAJE_P1/P2/P3`, `POT_BOE_P1/P2` a
  `factura_engine.py`) estan "hardcoded" igual que a l'Excel original —
  caldrà actualitzar-les manualment quan canviïn (com ja calia fer a l'Excel).
- El paràmetre "Ajuste del Gas" (MAG) està forçat a 0 pertot arreu, igual que
  a la versió actual del VBA (el propi autor el va anul·lar).
- `FacturaEsmiluzBNA` reprodueix fidelment un possible oblit de l'Excel
  original: no crida `DecodeParams`, així que el "marge per consum (FEE)"
  hi val sempre 0 — es manté igual per fidelitat, no és un bug del port.
- No s'ha reconstruït el text de desglossament de factura (`sFactura`) que
  a Excel es mostra com a comentari de cada cel·la; en canvi cada resultat
  inclou un `desglossament` (dict) amb els mateixos conceptes en forma
  estructurada.
