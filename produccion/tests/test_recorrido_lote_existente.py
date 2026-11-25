# Recorrido de PRD-05 · Registrar Lote Existente, de punta a punta con el cliente de Django, por rol y por estado (D-96; docs/patrones/verificacion_a_mano.md).
# Una prueba larga a propósito: lo que se verifica es que el flujo ENCADENA bien: el Agrónomo ve la acción, carga un lote en Maduración en dos sectores con costo
# $12.000, mira el lote, la bitácora, la orden y el libro; carga otro en una etapa intermedia con costo $0 y planifica y concreta su transición con la fecha de
# ingreso cargada; y, concretada una siembra normal en el invernadero, la acción desaparece y no vuelve. Las reglas sueltas las prueban `test_prod_reg_lte.py`
# y `test_prod_reg_lte_vistas.py`. Lo que solo ve un navegador (CSRF, `Origin`, JavaScript) va en la «Verificación a mano» de la tarea.

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from contabilidad import cuentas
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import libro
from contabilidad.tests.fabricas import PlanDeCuentasMixin, verificar_invariantes_contables
from core.models import Contador, RegistroAuditoria
from core.tests.fabricas import crear_cuenta, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import EtapaProductiva, SectorProduccion
from maestros.servicios import sectores as api_sectores
from maestros.tests.fabricas import crear_sector
from produccion.models import Bitacora, Lote, OcupacionSector, OrdenTrabajo, Siembra, TransicionEtapa
from produccion.servicios import transiciones
from produccion.tests.fabricas import invernadero_con_produccion, lote_activo

URL = reverse("produccion:registrar_lote_existente")
D = Decimal


def hoy():
    return timezone.localdate()


class RecorridoDeLoteExistenteTests(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    def test_recorrido_del_agronomo_con_un_invernadero_sin_siembras(self):
        e = invernadero_con_produccion()
        segundo = crear_sector(e.invernadero, nombre="Sector maduracion 2", tipo="maduracion", agujeros=100)
        gerente, contador = crear_gerente(), crear_cuenta(Contador, email="contador@infoponia.com")
        cliente = self.client

        def etapa(codigo):
            return EtapaProductiva.objects.get(ciclo__variedad=e.variedad, tipo_etapa__codigo=codigo).pk

        def formulario(codigo, cantidad, distribucion, costo, siembra, ingreso):
            datos = {
                "invernadero": e.invernadero.pk, "variedad": e.variedad.pk, "etapa": etapa(codigo), "cantidad": cantidad,
                "costo_estimado": costo, "fecha_siembra": siembra.isoformat(), "fecha_ingreso_etapa": ingreso.isoformat(),
            }
            datos.update({f"sector_{sector.pk}": plantas for sector, plantas in distribucion})
            return datos

        # --- Paso 1 (PROD-REG-LTE, precondición a y extensión 2a): quién ve la acción ---
        cliente.force_login(e.agronomo)
        self.assertIn("Registrar lote existente", cliente.get(reverse("produccion:ordenes")).content.decode())
        cliente.force_login(gerente)
        self.assertNotIn("Registrar lote existente", cliente.get(reverse("produccion:ordenes")).content.decode())
        self.assertEqual(cliente.get(URL).status_code, 404)  # D-30: el Gerente no ve la pantalla
        cliente.force_login(e.capataz)
        self.assertEqual(cliente.get(URL).status_code, 403)

        # --- Pasos 2 a 6: invernadero → variedad → etapa → sectores con sus libres (cada paso redibuja sin validar) ---
        cliente.force_login(e.agronomo)
        self.assertIn(e.invernadero.nombre_invernadero, cliente.get(URL).content.decode())
        pagina = cliente.get(URL, {"invernadero": e.invernadero.pk, "variedad": e.variedad.pk, "etapa": etapa("maduracion")}).content.decode()
        self.assertIn("(libres: 100)", pagina)
        self.assertIn("Sector maduracion 2", pagina)

        # --- Extensiones 5b y 7b: errores por campo; «Ver resumen» no escribe ---
        mal = cliente.post(URL, {**formulario("maduracion", "0", [(e.sectores["maduracion"], "100")], "12000", hoy() - timedelta(days=40), hoy() - timedelta(days=10)), "accion": "calcular"})
        self.assertIn("cantidad", mal.context["errores"])
        incompleta = cliente.post(URL, {**formulario("maduracion", "180", [(e.sectores["maduracion"], "100")], "12000", hoy() - timedelta(days=40), hoy() - timedelta(days=10)), "accion": "calcular"})
        self.assertIn("distribucion", incompleta.context["errores"])
        self.assertEqual((Lote.objects.count(), Siembra.objects.count(), AsientoContable.objects.count()), (0, 0, 0))

        # --- Paso 8 y 9: el resumen con el asiento y la confirmación ---
        ingreso = hoy() - timedelta(days=10)
        datos = formulario("maduracion", "180", [(e.sectores["maduracion"], "100"), (segundo, "80")], "12000", hoy() - timedelta(days=40), ingreso)
        resumen = cliente.post(URL, {**datos, "accion": "calcular"})
        contenido = resumen.content.decode()
        self.assertIn("Productos en Proceso", contenido)
        self.assertIn("Capital Inicial", contenido)
        confirmada = cliente.post(URL, {**datos, "accion": "confirmar", "firma": resumen.context["firma"]})
        self.assertEqual(confirmada.status_code, 302)
        lote = Lote.objects.get()
        self.assertEqual(confirmada["Location"], f"{URL}?registrado={lote.pk}")
        self.assertIn(lote.codigo, cliente.get(confirmada["Location"]).content.decode())

        # --- Postcondiciones a, b y c: la siembra de carga inicial, el lote, las ocupaciones y los agujeros ---
        siembra = Siembra.objects.get(pk=lote.siembra_id)
        self.assertEqual((siembra.tipo_siembra, siembra.estado_orden), ("carga_inicial", "concretada"))
        self.assertIsNone(siembra.capataz_id)
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado, lote.etapa.tipo_etapa.codigo), (180, D("12000.00"), "maduracion"))
        agujeros = api_sectores.agujeros_de([e.sectores["maduracion"], segundo])
        self.assertEqual((agujeros[e.sectores["maduracion"].pk].libres, agujeros[segundo.pk].libres), (0, 20))
        self.assertEqual(OcupacionSector.objects.filter(lote=lote).count(), 2)

        # --- El lote en la lista de la pestaña, y la orden en la lista y el detalle (sin Capataz) para el Agrónomo y el Gerente ---
        from produccion.servicios import registrantes

        self.assertIn(lote.codigo, registrantes.pestana_de_lotes(e.agronomo, e.invernadero))
        for cuenta in (e.agronomo, gerente):
            cliente.force_login(cuenta)
            self.assertIn("carga inicial", cliente.get(reverse("produccion:ordenes")).content.decode())
            self.assertIn("Sin Capataz", cliente.get(reverse("produccion:orden", args=[siembra.pk])).content.decode())
        cliente.force_login(e.capataz)
        self.assertNotIn(siembra.codigo, cliente.get(reverse("produccion:bandeja")).content.decode())

        # --- Postcondición b: la bitácora muestra «Carga inicial» (Agrónomo y Gerente) y el filtro la encuentra ---
        for cuenta in (e.agronomo, gerente):
            cliente.force_login(cuenta)
            bit = cliente.get(reverse("produccion:bitacora"), {"invernadero": e.invernadero.pk, "tipo": "carga_inicial"}).content.decode()
            self.assertIn("Carga inicial", bit)
            self.assertIn(lote.codigo, bit)

        # --- Postcondición d: el asiento (fecha actual, Debe Productos en Proceso / Haber Capital Inicial) y la auditoría ---
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.origen_id, asiento.fecha_asiento), (siembra.pk, hoy()))
        saldos = libro.saldo_por_cuenta(asiento.ejercicio_id)
        self.assertEqual((saldos[cuentas.PRODUCTOS_EN_PROCESO].debe, saldos[cuentas.CAPITAL_INICIAL].haber), (D("12000.00"), D("12000.00")))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_lote_existente").count(), 1)

        # --- El libro de gestión, con el Contador (y con el Gerente) ---
        for cuenta in (contador, gerente):
            cliente.force_login(cuenta)
            libro_html = cliente.get(reverse("contabilidad:libro"), {"ejercicio": asiento.ejercicio_id}).content.decode()
            self.assertIn(f"Carga inicial del lote {lote.codigo}", libro_html)

        # --- Segunda carga: Crecimiento con costo $0 (sin asiento) y la fecha de ingreso cargada ---
        cliente.force_login(e.agronomo)
        ingreso2 = hoy() - timedelta(days=4)
        datos2 = formulario("crecimiento", "50", [(e.sectores["crecimiento"], "50")], "0", hoy() - timedelta(days=30), ingreso2)
        resumen2 = cliente.post(URL, {**datos2, "accion": "calcular"})
        self.assertIn("con costo $0 no se registra ningún asiento", resumen2.content.decode())
        cliente.post(URL, {**datos2, "accion": "confirmar", "firma": resumen2.context["firma"]})
        otro = Lote.objects.exclude(pk=lote.pk).get()
        self.assertEqual(AsientoContable.objects.count(), 1)  # el de costo 0 no tiene asiento

        # --- Hecho cuando: planificar la transición del lote cargado usa la fecha de ingreso cargada; el Capataz la concreta ---
        self.assertEqual(transiciones.fecha_minima_de_transicion(otro), ingreso2)
        ofrecido = transiciones.datos_de_planificacion(e.agronomo, otro.pk)
        self.assertEqual(ofrecido.lote.fecha_estimada_de_fin, ingreso2 + timedelta(days=10))  # entrada + duración de Crecimiento (10)
        plan = {
            "lote": otro.pk, "fecha_programada": (hoy() + timedelta(days=2)).isoformat(), "cantidad_vista": "50", "etapa_vista": otro.etapa_id,
            "prioridad": "", "descripcion": "", f"sector_{e.sectores['floracion'].pk}": "50",
        }
        vista = cliente.post(reverse("produccion:nueva_transicion"), {**plan, "accion": "calcular"})
        self.assertIsNotNone(vista.context["resumen"], vista.context["errores"])
        cliente.post(reverse("produccion:nueva_transicion"), {**plan, "accion": "confirmar", "firma": vista.context["firma"]})
        orden = TransicionEtapa.objects.get(lote=otro)
        concretada = transiciones.concretar_transicion(e.capataz, orden.pk, transiciones.DatosDeConcrecionDeTransicion(fecha_efectiva=hoy()))
        self.assertEqual(Lote.objects.get(pk=otro.pk).etapa.tipo_etapa.codigo, "floracion")
        self.assertEqual(concretada.estado_orden, OrdenTrabajo.Estado.CONCRETADA)
        self.assertEqual(Bitacora.objects.filter(tipo_evento="carga_inicial").count(), 2)

        # --- Hecho cuando: concretada una siembra normal, la acción desaparece y no vuelve; la pantalla lo explica y una carga a mano se rechaza ---
        lote_activo(e, cantidad=5)
        self.assertNotIn("Registrar lote existente", cliente.get(reverse("produccion:ordenes")).content.decode())
        self.assertIn("No hay invernaderos donde cargar un lote existente", cliente.get(URL).content.decode())
        rechazada = cliente.post(URL, {**datos, "accion": "confirmar", "firma": resumen.context["firma"]})
        self.assertIn("invernadero", rechazada.context["errores"])
        self.assertEqual(Lote.objects.filter(siembra__tipo_siembra="carga_inicial").count(), 2)
        self.assertNotIn("Registrar lote existente", registrantes.pestana_de_lotes(e.agronomo, e.invernadero))

        verificar_invariantes_contables()
        self.assertEqual(EjercicioContable.objects.filter(estado_ejercicio="abierto").count(), 1)
