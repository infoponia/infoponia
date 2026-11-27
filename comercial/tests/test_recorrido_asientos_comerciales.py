# Recorrido de CON-04c · Asientos de cosecha, cámara y entregas, de punta a punta con el cliente de Django, por rol y por estado (D-96; docs/patrones/verificacion_a_mano.md).
# Una prueba larga a propósito: lo que se verifica es que el flujo ENCADENA bien. El Capataz concreta una cosecha con plantas perdidas (el asiento de la salida por cosecha y el de la
# merma); el Transportista concreta la entrega de un suministro con pérdidas (la merma «daño en la entrega» y el compuesto, con Deudores por Ventas) y el Vendedor un retiro de
# compra-venta cobrado en efectivo (Caja); el paso diario vence una partida (y corrido dos veces no duplica); y el Contador (y el Gerente) leen cada asiento en el libro y en su ficha,
# con el texto de su origen y sin enlace. Una segunda prueba arma el estado «la fecha del hecho cae en un ejercicio ya cerrado». Las reglas sueltas las prueban `test_prod_cnc_csc.py`,
# `test_prod_reg_mrm_camara.py`, `test_prod_vnc_cam.py` y `test_com_cnc_ent.py`. Lo que solo ve un navegador (CSRF, `Origin`, JavaScript) va en la «Verificación a mano» de la tarea.

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comercial.models import Entrega
from comercial.servicios import camara
from comercial.tests.fabricas import (
    compra_venta,
    cosecha_manual,
    detalle,
    detalle_suministro,
    entrega,
    escenario_comercial,
    iniciar_ruta_de,
    partida,
    reserva_lista,
    suministro,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
)
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import AsientoContable, EjercicioContable, MovimientoContable
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas
from contabilidad.tests.fabricas import PlanDeCuentasMixin, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.models import Contador
from core.tests.fabricas import crear_cuenta, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.models import Merma
from produccion.tests.fabricas import lote_maduro

D = Decimal
HOY = timezone.localdate()


def iso(dias=0):
    return (HOY + timedelta(days=dias)).isoformat()


class RecorridoDeAsientosComercialesTests(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 100)  # 100 plantas, costo 100,00: 1,00 por planta
        self.sector = self.e.sectores["maduracion"]
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)
        self.addCleanup(verificar_invariantes_contables)

    def lineas(self, asiento):
        return sorted(
            (m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento)
            for m in MovimientoContable.objects.filter(asiento=asiento).select_related("cuenta")
        )

    def entrar(self, cuenta):
        self.client.force_login(cuenta)

    def concretar_entrega(self, entrega_, datos):
        """Los dos pasos de la pantalla de la entrega: «Ver resumen» (con su huella) y «Confirmar entrega»."""
        resumen = self.client.post(reverse("comercial:entrega_concretar_calcular", args=[entrega_.pk]), datos)
        html = resumen.content.decode()
        i = html.index('name="huella" value="') + len('name="huella" value="')
        huella = html[i : html.index('"', i)].replace("&quot;", '"').replace("&amp;", "&")
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("comercial:entrega_concretar", args=[entrega_.pk]), {**datos, "huella": huella})

    def test_recorrido_del_capataz_el_transportista_el_vendedor_el_paso_diario_y_el_contador(self):
        libro = reverse("contabilidad:libro")
        gerente = crear_gerente()
        self.assertEqual(EjercicioContable.objects.count(), 0)  # estado inicial: contabilidad sin ejercicio, todavía sin poner en marcha

        # --- 1. El Capataz concreta una cosecha de 40 reservadas: cosecha 30 y pierde 4 (PROD-CNC-CSC post. f y ext. 10a). «Ver resumen» no asienta ---
        venta = compra_venta(self.e, dias=10)
        cosecha = cosecha_manual(self.e, [(self.lote, 40)], detalle_=detalle(venta, self.e.variedad, 50))
        self.entrar(self.e.capataz)
        datos = {
            "fecha_efectiva": iso(0), f"cant_{self.lote.pk}_{self.sector.pk}": "30", f"perd_{self.lote.pk}_{self.sector.pk}": "4",
            f"causa_{self.lote.pk}": "plaga", f"desc_{self.lote.pk}": "",
        }
        resumen = self.client.post(reverse("comercial:cosecha_concretar_revisar", args=[cosecha.pk]), datos)
        self.assertEqual((resumen.status_code, AsientoContable.objects.count()), (200, 0))
        # --- 1a. Regla 9 de CON-INI-EJE (CON-05): sin ejercicio, «Confirmar» no registra nada (el middleware muestra la ventana). Después se inicia la contabilidad con el helper y no con
        #         `iniciar_ejercicio`, cuyo asiento de apertura N.º 1 correría los números de los asientos de abajo ---
        sin_ejercicio = self.client.post(reverse("comercial:cosecha_concretar", args=[cosecha.pk]), {**datos, "firma": resumen.context["firma"]})
        self.assertContains(sin_ejercicio, "La operación no se registró.")
        self.assertEqual((EjercicioContable.objects.count(), AsientoContable.objects.count()), (0, 0))
        iniciar_contabilidad_para_pruebas()
        self.client.post(reverse("comercial:cosecha_concretar", args=[cosecha.pk]), {**datos, "firma": resumen.context["firma"]})
        salida, merma_de_cosecha = AsientoContable.objects.get(numero_asiento=1), AsientoContable.objects.get(numero_asiento=2)
        self.assertEqual(self.lineas(salida), sorted([(cuentas.PRODUCTOS_TERMINADOS, DEBE, D("30.00")), (cuentas.PRODUCTOS_EN_PROCESO, HABER, D("30.00"))]))
        self.assertEqual(self.lineas(merma_de_cosecha), sorted([(cuentas.PERDIDAS_POR_MERMAS, DEBE, D("4.00")), (cuentas.PRODUCTOS_EN_PROCESO, HABER, D("4.00"))]))
        self.assertEqual(EjercicioContable.objects.get().estado_ejercicio, EjercicioContable.Estado.ABIERTO)

        # --- 2. El Transportista concreta la entrega de un suministro (mínimo 100): llegan 95 de 100 → merma por daño y asiento compuesto con Deudores por Ventas ---
        t = transportista_con_vehiculo(self.e.invernadero, "800")
        sum_ = suministro(self.e, plazo_pago=15)
        det = detalle_suministro(sum_, self.e.variedad, cantidad=100, minima=100, primera_en_dias=0)
        e_sum = entrega(sum_, [reserva_lista(None, self.lote, 100, fecha_entrega=det.fecha_primer_entrega, detalle_suministro=det)], transportista=t, fecha=HOY)
        iniciar_ruta_de(t)
        self.entrar(t)
        linea = e_sum.lineas.get().pk
        self.concretar_entrega(e_sum, {f"llego_{linea}": "95", f"recibio_{linea}": "95", "sin_envases": "1"})
        monto = Entrega.objects.get(pk=e_sum.pk).monto_total_entrega
        self.assertGreater(monto, 0)
        dano = Merma.objects.get(causa="dano_en_entrega")
        self.assertEqual(self.lineas(AsientoContable.objects.get(origen_id=dano.pk)), sorted([(cuentas.PERDIDAS_POR_MERMAS, DEBE, D("5.00")), (cuentas.PRODUCTOS_TERMINADOS, HABER, D("5.00"))]))
        self.assertEqual(
            self.lineas(AsientoContable.objects.get(origen_id=e_sum.pk)),
            sorted([(cuentas.DEUDORES_POR_VENTAS, DEBE, monto), (cuentas.VENTAS, HABER, monto), (cuentas.COSTO_DE_PRODUCCION_VENDIDA, DEBE, D("95.00")), (cuentas.PRODUCTOS_TERMINADOS, HABER, D("95.00"))]),
        )

        # --- 3. El Vendedor concreta un retiro de compra-venta de 20 plantas a $100, cobrado en efectivo: Caja / Ventas $2.000,00 y costo $20,00 ---
        retiro = compra_venta(self.e, dias=0, modalidad="retiro")
        e_retiro = entrega(retiro, [reserva_lista(detalle(retiro, self.e.variedad, 20), self.lote, 20)], fecha=HOY)
        self.entrar(self.e.vendedor)
        linea = e_retiro.lineas.get().pk
        self.concretar_entrega(e_retiro, {f"llego_{linea}": "20", f"acepta_{linea}": "1", "sin_envases": "1", "medio_pago": "efectivo"})
        self.assertEqual(
            self.lineas(AsientoContable.objects.get(origen_id=e_retiro.pk)),
            sorted([(cuentas.CAJA, DEBE, D("2000.00")), (cuentas.VENTAS, HABER, D("2000.00")), (cuentas.COSTO_DE_PRODUCCION_VENDIDA, DEBE, D("20.00")), (cuentas.PRODUCTOS_TERMINADOS, HABER, D("20.00"))]),
        )

        # --- 4. El paso diario vence una partida de cámara (40 × $2,50 = $100,00); corrido dos veces no duplica ---
        antes = AsientoContable.objects.count()
        partida(self.lote, 40, fecha_limite=HOY - timedelta(days=1), costo="2.5000")
        camara.vencer_partidas_en_camara(HOY)
        camara.vencer_partidas_en_camara(HOY)
        self.assertEqual(AsientoContable.objects.count(), antes + 1)
        vencimiento = AsientoContable.objects.get(origen_id=Merma.objects.get(causa="vencimiento_en_camara").pk)
        self.assertEqual(self.lineas(vencimiento), sorted([(cuentas.PERDIDAS_POR_MERMAS, DEBE, D("100.00")), (cuentas.PRODUCTOS_TERMINADOS, HABER, D("100.00"))]))
        verificar_invariantes_contables()

        # --- 5. Quién lee el libro: el Contador y el Gerente; el Capataz, el Agrónomo, el Vendedor y el Transportista no (403) ---
        for cuenta in (self.e.capataz, self.e.agronomo, self.e.vendedor, t):
            self.entrar(cuenta)
            self.assertEqual(self.client.get(libro).status_code, 403, cuenta)
        self.entrar(self.contador)
        pagina = self.client.get(libro).content.decode()
        self.assertIn(f"Totales ({AsientoContable.objects.count()} asientos)", pagina)
        for texto in ("Productos Terminados", "Pérdidas por Mermas", "Deudores por Ventas", "Costo de Producción Vendida"):
            self.assertIn(texto, pagina)
        self.entrar(gerente)
        self.assertEqual(self.client.get(libro).status_code, 200)

        # --- 6. La ficha de cada asiento: el texto de su origen, sin enlace (el Contador no abre las pantallas de cosecha ni de entrega) ---
        self.entrar(self.contador)
        abierto = EjercicioContable.objects.get()
        ficha = lambda n: self.client.get(reverse("contabilidad:asiento", args=[abierto.pk, n])).content.decode()  # noqa: E731
        self.assertIn(f"Salida por cosecha · {cosecha.codigo}, lote {self.lote.codigo}, 30 plantas", ficha(1))
        self.assertIn(f"Merma del lote {self.lote.codigo}", ficha(2))
        self.assertIn(f"Entrega {e_sum.codigo} · {sum_.codigo}", ficha(AsientoContable.objects.get(origen_id=e_sum.pk).numero_asiento))
        self.assertIn(f"Entrega {e_retiro.codigo} · {retiro.codigo}", ficha(AsientoContable.objects.get(origen_id=e_retiro.pk).numero_asiento))
        for n in range(1, AsientoContable.objects.count() + 1):
            for prohibido in ("/comercial/", "/produccion/"):
                self.assertNotIn(prohibido, ficha(n))

    def test_recorrido_con_la_fecha_del_hecho_en_un_ejercicio_ya_cerrado(self):
        """Estado «la fecha efectiva cae en un ejercicio cerrado» (D-102): la cosecha se concreta, el asiento va al ejercicio abierto con la fecha de hoy y la ficha aclara la
        fecha real del hecho."""
        cerrado = ejercicio(EjercicioContable.Estado.CERRADO, HOY - timedelta(days=60), HOY - timedelta(days=1))
        abierto = ejercicio_abierto(HOY)
        venta = compra_venta(self.e, dias=10)
        cosecha = cosecha_manual(self.e, [(self.lote, 30)], detalle_=detalle(venta, self.e.variedad, 50), dias=-5)
        fecha = HOY - timedelta(days=3)
        self.entrar(self.e.capataz)
        datos = {"fecha_efectiva": fecha.isoformat(), f"cant_{self.lote.pk}_{self.sector.pk}": "30"}
        resumen = self.client.post(reverse("comercial:cosecha_concretar_revisar", args=[cosecha.pk]), datos)
        self.client.post(reverse("comercial:cosecha_concretar", args=[cosecha.pk]), {**datos, "firma": resumen.context["firma"]})
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.ejercicio_id, asiento.fecha_asiento), (abierto.pk, HOY))
        self.assertEqual(AsientoContable.objects.filter(ejercicio=cerrado).count(), 0)
        self.entrar(self.contador)
        ficha = self.client.get(reverse("contabilidad:asiento", args=[abierto.pk, 1])).content.decode()
        self.assertIn(f"Fecha del hecho: {fecha:%d/%m/%Y}", ficha)
