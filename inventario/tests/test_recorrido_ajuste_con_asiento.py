# Recorrido de CON-04b (D-96, `docs/patrones/verificacion_a_mano.md`): una prueba larga con el cliente de Django que hace de punta a punta lo que hará la persona en la
# «Verificación a mano», por rol y por estado. Modelo: `contabilidad/tests/test_recorrido_libro_y_cierre.py`.
# Agrónomo: sin ejercicio todavía → carga inicial de 10 L a $ 500 (resumen con el asiento, confirmar) → rotura de 2 L → un ajuste cuyo importe redondea a $ 0,00 (se registra, sin asiento).
# Contador y Gerente: el libro muestra los dos asientos (cuentas, importes, origen «Movimiento de insumo», sin enlace: inventario no registra enlace de origen) y su ficha.
# Capataz, Vendedor y un Agrónomo: el libro les da 403. Sin pruebas de navegador: el CSRF, el encabezado Origin y el JavaScript los cubre el paso de «navegador real».
from decimal import Decimal

from django.urls import reverse

from contabilidad import cuentas
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas
from contabilidad.tests.fabricas import verificar_invariantes_contables
from core.models import Agronomo, Capataz, Contador, Gerente, Vendedor
from core.tests.fabricas import crear_cuenta
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.tests.test_ajuste_vistas import AjusteVistaBase, en

D = Decimal
LIBRO = reverse("contabilidad:libro")


class RecorridoDeAjusteConAsientoTests(AjusteVistaBase):
    """Recorrido del ajuste de stock con su asiento, por rol (Agrónomo, Contador, Gerente, otros) y por estado (sin ejercicio, con ejercicio abierto, importe cero)."""

    def setUp(self):
        super().setUp()
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(referencia_precio=D("500.00"))
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com")

    def ajustar(self, motivo, **campos):
        """Lo que hace el Agrónomo: «Ver resumen» y después «Confirmar ajuste», con la huella y la firma que la pantalla mostró."""
        self.client.force_login(self.agronomo)
        calculo = self.calcular(motivo, **campos)
        self.assertEqual(calculo.status_code, 200)
        self.assertContains(calculo, "Confirmar ajuste")
        respuesta = self.confirmar_con(calculo, motivo, **campos)
        self.assertRedirects(respuesta, self.lista)
        return calculo

    def ver(self, usuario, url):
        self.client.force_login(usuario)
        return self.client.get(url)

    def test_recorrido_del_ajuste_con_su_asiento_por_rol_y_por_estado(self):
        # --- Sin ejercicio todavía (regla 9 de CON-INI-EJE, CON-05): la carga inicial no se registra y se explica; después se inicia la contabilidad con el helper ---
        EjercicioContable.objects.all().delete()  # la base de la clase trae el ejercicio del helper
        self.assertEqual(EjercicioContable.objects.count(), 0)
        campos = {"cantidad": "10", "vencimiento": en(60).isoformat()}
        self.client.force_login(self.agronomo)
        calculo = self.calcular("carga_inicial", **campos)
        sin_ejercicio = self.confirmar_con(calculo, "carga_inicial", **campos)
        self.assertContains(sin_ejercicio, "La operación no se registró.")
        self.assertEqual((EjercicioContable.objects.count(), AsientoContable.objects.count(), LoteInsumo.objects.count()), (0, 0, 0))
        iniciar_contabilidad_para_pruebas()

        # --- Agrónomo: carga inicial de 10 L a $ 500 ---
        resumen = self.ajustar("carga_inicial", **campos).context["resumen"]
        self.assertEqual([(a.debe[1], a.haber[1], a.importe) for a in resumen.asientos], [("Insumos en Stock", "Capital Inicial", D("5000.00"))])
        [ejercicio] = EjercicioContable.objects.all()
        self.assertEqual(ejercicio.estado_ejercicio, EjercicioContable.Estado.ABIERTO)
        lote = LoteInsumo.objects.get(insumo_invernadero=self.iin)

        # --- Con ejercicio abierto: rotura de 2 L del lote ---
        calculo = self.ajustar("rotura_o_perdida", lote_id=str(lote.pk), cantidad="2", descripcion="Se cayó el bidón")
        self.assertContains(calculo, "Debe Diferencias de Inventario de Insumos / Haber Insumos en Stock")
        self.assertEqual(self.stock(), 8)

        # --- Importe que redondea a $ 0,00: se registra el ajuste, sin asiento y sin error ---
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(referencia_precio=D("0.01"))
        calculo = self.ajustar("rotura_o_perdida", lote_id=str(lote.pk), cantidad="0.001")
        self.assertContains(calculo, "Sin asiento: el importe redondea a $ 0,00.")
        self.assertEqual(MovimientoInsumo.objects.filter(tipo_movimiento="ajuste_negativo").count(), 2)
        self.assertEqual(AsientoContable.objects.count(), 2)  # los dos de arriba, ninguno por este

        # --- Los dos asientos, con su origen ---
        carga, rotura = AsientoContable.objects.order_by("numero_asiento")
        self.assertEqual((carga.numero_asiento, rotura.numero_asiento), (1, 2))
        self.assertEqual(carga.origen.movimientoinsumo.motivo_ajuste, "carga_inicial")
        self.assertEqual(rotura.origen.movimientoinsumo.motivo_ajuste, "rotura_o_perdida")
        self.assertEqual(
            [(m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in carga.movimientos.order_by("cuenta__codigo_cuenta")],
            [(cuentas.INSUMOS_EN_STOCK, "D", D("5000.00")), (cuentas.CAPITAL_INICIAL, "H", D("5000.00"))],
        )
        self.assertEqual(
            [(m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in rotura.movimientos.order_by("cuenta__codigo_cuenta")],
            [(cuentas.INSUMOS_EN_STOCK, "H", D("1000.00")), (cuentas.DIFERENCIAS_DE_INVENTARIO, "D", D("1000.00"))],
        )

        # --- Contador y Gerente: el libro y la ficha (el origen se nombra, sin enlace) ---
        for usuario in (self.contador, self.gerente):
            libro = self.ver(usuario, LIBRO)
            self.assertEqual(libro.status_code, 200)
            self.assertContains(libro, "Movimiento de insumo")
            self.assertContains(libro, f"Ajuste de stock (carga inicial): Nutriente A, lote {lote.pk}")
            self.assertContains(libro, f"Ajuste de stock (rotura o pérdida): Nutriente A, lote {lote.pk}")
            for asiento, nombres in ((carga, ("Insumos en Stock", "Capital Inicial")), (rotura, ("Insumos en Stock", "Diferencias de Inventario de Insumos"))):
                ficha = self.ver(usuario, reverse("contabilidad:asiento", args=[asiento.ejercicio_id, asiento.numero_asiento]))
                self.assertEqual(ficha.status_code, 200)
                self.assertEqual(ficha.context["ficha"].origen_texto, "Movimiento de insumo")
                self.assertIsNone(ficha.context["ficha"].origen_url)
                for nombre in nombres:
                    self.assertContains(ficha, nombre)

        # --- Otros roles: sin acceso al libro ---
        for clase, email in ((Capataz, "capataz@infoponia.com"), (Vendedor, "vendedor@infoponia.com"), (Agronomo, "otro-agronomo@infoponia.com")):
            self.assertEqual(self.ver(crear_cuenta(clase, email=email), LIBRO).status_code, 403, clase.__name__)
        self.assertEqual(self.ver(self.agronomo, LIBRO).status_code, 403)

        verificar_invariantes_contables()
