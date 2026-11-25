# Recorrido de CON-04a · Asientos de producción, de punta a punta con el cliente de Django, por rol y por estado (D-96; docs/patrones/verificacion_a_mano.md).
# Una prueba larga a propósito: lo que se verifica es que el flujo ENCADENA bien. El Capataz concreta una siembra (consumo de semilla), concreta la transición del
# lote con plantas perdidas, registra una merma y una aplicación a gasto; el Agrónomo pone fuera de servicio el sector con plantas sin reubicar; y el Contador (y el
# Gerente) leen cada asiento en el libro de gestión y en su ficha, con el texto de su origen y sin enlace. Una segunda prueba arma el estado «la fecha del hecho cae en
# un ejercicio ya cerrado». Las reglas sueltas las prueban `test_prod_cnc_smb.py`, `test_prod_cnc_trn.py`, `test_prod_reg_mrm.py`, `test_prod_reg_apl.py` y
# `test_prod_pnr_fds.py`. Lo que solo ve un navegador (CSRF, `Origin`, JavaScript) va en la «Verificación a mano» de la tarea.

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import AsientoContable, EjercicioContable, MovimientoContable
from contabilidad.tests.fabricas import PlanDeCuentasMixin, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.models import Contador
from core.tests.fabricas import crear_cuenta, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, lote as lote_de_insumo, tipo_de_insumo
from maestros.models import SectorProduccion
from maestros.tests.fabricas import crear_vendedor
from produccion.models import Lote, Merma, OrdenTrabajo
from produccion.tests.fabricas import invernadero_con_produccion, orden_de_siembra, orden_de_transicion

D = Decimal


def hoy():
    return timezone.localdate()


class RecorridoDeAsientosDeProduccionTests(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    def lineas(self, asiento):
        return sorted(
            (m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento)
            for m in MovimientoContable.objects.filter(asiento=asiento).select_related("cuenta")
        )

    def test_recorrido_del_capataz_el_agronomo_y_el_contador_con_un_invernadero_sin_contabilidad_previa(self):
        e = invernadero_con_produccion()
        gerente, contador = crear_gerente(), crear_cuenta(Contador, email="contador@infoponia.com")
        tipo = tipo_de_insumo("Cat gasto", consumo="como_gasto")
        limpiador = existencia(insumo("Limpiador", tipo=tipo, unidad="l"), e.invernadero, precio="5.00")
        lote_de_insumo(limpiador, 20)
        cliente = self.client
        libro = reverse("contabilidad:libro")
        self.assertEqual(EjercicioContable.objects.count(), 0)  # estado inicial: contabilidad sin ejercicio, todavía sin poner en marcha

        # --- 1. El Capataz concreta la siembra (PROD-CNC-SMB): «Ver resumen» no asienta; «Confirmar» crea el asiento del consumo de la semilla y abre el primer ejercicio ---
        orden = orden_de_siembra(e, plantines=50)
        cliente.force_login(e.capataz)
        url = reverse("produccion:concretar", args=[orden.pk])
        resumen = cliente.post(url, {"accion": "calcular"})
        self.assertEqual(AsientoContable.objects.count(), 0)
        confirmada = cliente.post(url, {"accion": "confirmar", "firma": resumen.context["firma"]})
        self.assertRedirects(confirmada, reverse("produccion:bandeja"))
        lote = Lote.objects.get(siembra=orden)
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado), (50, D("100.00")))
        siembra_asiento = AsientoContable.objects.get()
        self.assertEqual((siembra_asiento.numero_asiento, siembra_asiento.fecha_asiento), (1, hoy()))
        self.assertEqual(
            self.lineas(siembra_asiento),
            sorted([(cuentas.PRODUCTOS_EN_PROCESO, DEBE, D("100.00")), (cuentas.INSUMOS_EN_STOCK, HABER, D("100.00"))]),
        )
        self.assertEqual(EjercicioContable.objects.get().estado_ejercicio, EjercicioContable.Estado.ABIERTO)

        # --- 2. El Capataz concreta la transición del lote con 10 plantas perdidas (PROD-CNC-TRN + merma): $20,00 de Pérdidas por Mermas ---
        transicion = orden_de_transicion(e, lote)
        destino = e.sectores["crecimiento"]
        url = reverse("produccion:concretar", args=[transicion.pk])
        datos = {"fecha_efectiva": hoy().isoformat(), "cantidad_vista": "50", f"ubicadas_{destino.pk}": "40", "causa": "plaga", "descripcion": "Hongo"}
        resumen = cliente.post(url, {**datos, "accion": "calcular"})
        self.assertEqual(AsientoContable.objects.count(), 1)
        cliente.post(url, {**datos, "accion": "confirmar", "firma": resumen.context["firma"]})
        merma_de_transicion = Merma.objects.get()
        asiento = AsientoContable.objects.get(origen_id=merma_de_transicion.pk)
        self.assertEqual(asiento.numero_asiento, 2)
        self.assertEqual(self.lineas(asiento), sorted([(cuentas.PERDIDAS_POR_MERMAS, DEBE, D("20.00")), (cuentas.PRODUCTOS_EN_PROCESO, HABER, D("20.00"))]))

        # --- 3. El Capataz registra una merma de 4 plantas del lote en crecimiento (PROD-REG-MRM): costo 80,00 × 4 ÷ 40 = $8,00 ---
        url = reverse("produccion:registrar_merma")
        datos = {"invernadero": e.invernadero.pk, "lote": lote.pk, f"cant_{destino.pk}": "4", "causa": "plaga", "descripcion": ""}
        resumen = cliente.post(url, {**datos, "accion": "calcular"})
        self.assertEqual(Merma.objects.count(), 1)
        cliente.post(url, {**datos, "accion": "confirmar", "firma": resumen.context["firma"], "visto_cantidad": "40", "visto_ocupados": f"{destino.pk}:40"})
        self.assertEqual(Merma.objects.count(), 2)
        merma = Merma.objects.exclude(pk=merma_de_transicion.pk).get()
        self.assertEqual(self.lineas(AsientoContable.objects.get(origen_id=merma.pk))[0][2], D("8.00"))

        # --- 4. El Capataz registra una aplicación de 2 L de limpiador (categoría «como gasto», PROD-REG-APL): Gastos de Producción, $10,00; no ve importes ---
        url = reverse("produccion:registrar_aplicacion")
        datos = {"invernadero": e.invernadero.pk, "alcance": "todo", f"cantidad_{limpiador.pk}": "2", "descripcion": ""}
        resumen = cliente.post(url, {**datos, "accion": "calcular"})
        self.assertNotIn("$", resumen.content.decode())  # «Qué ve cada rol»: el Capataz no ve valores
        cliente.post(
            url,
            {**datos, "accion": "confirmar", "firma": resumen.context["firma"], "plantas_vistas": resumen.context["plantas_vistas"],
             f"vistos_{limpiador.pk}": resumen.context["vistos"][limpiador.pk]},
        )
        asiento_gasto = AsientoContable.objects.get(numero_asiento=4)
        self.assertEqual(self.lineas(asiento_gasto), sorted([(cuentas.GASTOS_DE_PRODUCCION, DEBE, D("10.00")), (cuentas.INSUMOS_EN_STOCK, HABER, D("10.00"))]))

        # --- 5. El Agrónomo pone fuera de servicio el sector de crecimiento (PROD-PNR-FDS): las 36 plantas se pierden, $72,00 (el costo que le queda al lote) ---
        cliente.force_login(e.agronomo)
        url = reverse("produccion:fuera_de_servicio")
        datos = {"sector": destino.pk, "motivo": "Se rompió el canal de retorno", "fecha": hoy().isoformat(), f"causa_{lote.pk}": "plaga", f"desc_{lote.pk}": ""}
        resumen = cliente.post(url, {**datos, "accion": "calcular"})
        self.assertEqual(AsientoContable.objects.count(), 4)
        campos = {n: resumen.context["firma"] if n == "firma" else resumen.context["vistos"][n.removeprefix("visto_")] for n in ("firma", "visto_plantas", "visto_libres", "visto_ordenes")}
        cliente.post(url, {**datos, "accion": "confirmar", **campos})
        self.assertEqual(SectorProduccion.objects.get(pk=destino.pk).estado_sector, "fuera_de_servicio")
        self.assertEqual(Lote.objects.get(pk=lote.pk).estado_lote, "finalizado")
        asiento_fds = AsientoContable.objects.get(numero_asiento=5)
        self.assertEqual(self.lineas(asiento_fds), sorted([(cuentas.PERDIDAS_POR_MERMAS, DEBE, D("72.00")), (cuentas.PRODUCTOS_EN_PROCESO, HABER, D("72.00"))]))
        verificar_invariantes_contables()

        # --- 6. Quién lee el libro: el Contador y el Gerente; el Capataz, el Agrónomo y el Vendedor no (D-30: 403) ---
        for cuenta in (e.capataz, e.agronomo, crear_vendedor()):
            cliente.force_login(cuenta)
            self.assertEqual(cliente.get(libro).status_code, 403, cuenta)
        cliente.force_login(contador)
        pagina = cliente.get(libro).content.decode()
        self.assertIn("Totales (5 asientos)", pagina)
        for texto in ("Pérdidas por Mermas", "Gastos de Producción", "Productos en Proceso", "Insumos en Stock"):
            self.assertIn(texto, pagina)
        cliente.force_login(gerente)
        self.assertEqual(cliente.get(libro).status_code, 200)

        # --- 7. La ficha de cada asiento: el texto de su origen, sin enlace (el Contador no abre las pantallas de producción) ---
        cliente.force_login(contador)
        ejercicio_abierto_ = EjercicioContable.objects.get()
        fichas = {n: cliente.get(reverse("contabilidad:asiento", args=[ejercicio_abierto_.pk, n])).content.decode() for n in range(1, 6)}
        self.assertIn("Consumo · Siembra", fichas[1])
        self.assertIn(f"Merma del lote {lote.codigo}", fichas[2])
        self.assertIn(f"Merma del lote {lote.codigo}", fichas[3])
        self.assertIn("Consumo · Aplicación: Limpiador", fichas[4])
        self.assertIn(f"Merma del lote {lote.codigo}", fichas[5])
        for ficha in fichas.values():
            self.assertNotIn("/produccion/", ficha)  # sin enlace a una pantalla que el Contador no puede abrir
        self.assertEqual(OrdenTrabajo.objects.get(pk=orden.pk).estado_orden, "concretada")

    def test_recorrido_con_la_fecha_del_hecho_en_un_ejercicio_ya_cerrado(self):
        """Estado «la fecha efectiva cae en un ejercicio cerrado» (D-102): la siembra se concreta, el asiento va al ejercicio abierto con la fecha de hoy y la ficha
        aclara la fecha real del hecho."""
        e = invernadero_con_produccion()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        cerrado = ejercicio(EjercicioContable.Estado.CERRADO, hoy() - timedelta(days=60), hoy() - timedelta(days=1))
        abierto = ejercicio_abierto(hoy())
        orden = orden_de_siembra(e, plantines=10, sector="crecimiento", dias=-5)
        fecha = hoy() - timedelta(days=3)
        self.client.force_login(e.capataz)
        url = reverse("produccion:concretar", args=[orden.pk])
        datos = {"fecha_efectiva": fecha.isoformat()}
        resumen = self.client.post(url, {**datos, "accion": "calcular"})
        self.client.post(url, {**datos, "accion": "confirmar", "firma": resumen.context["firma"]})
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.ejercicio_id, asiento.fecha_asiento), (abierto.pk, hoy()))
        self.assertEqual(AsientoContable.objects.filter(ejercicio=cerrado).count(), 0)
        self.client.force_login(contador)
        ficha = self.client.get(reverse("contabilidad:asiento", args=[abierto.pk, 1])).content.decode()
        self.assertIn(f"Fecha del hecho: {fecha:%d/%m/%Y}", ficha)
        verificar_invariantes_contables()
