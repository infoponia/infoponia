# Recorrido de EST-02 «Estadísticas consolidadas» (D-96): una prueba larga con el cliente de Django que hace los pasos de punta a punta como lo haría el Gerente,
# por rol y por estado. No reemplaza la «Verificación a mano» (el navegador real, el JavaScript y el CSRF no se ven acá): la complementa. Los datos se arman con los
# servicios reales de recepción y corrección de compras y se les fija la fecha en la base; el día de «hoy» se fija en `HOY` solo mientras se pide la pantalla (el patch de
# `timezone.localdate` es global y no tiene que alcanzar a los servicios que arman los datos).

from datetime import date
from decimal import Decimal
from unittest import mock

from django.urls import reverse

from compras.models import CorreccionRecepcion, Recepcion
from compras.tests.base_correcciones import CorreccionBase
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import EjercicioContable
from contabilidad.tests.fabricas import asiento_de_prueba, ejercicio
from core.models import RegistroAuditoria
from estadisticas.tests.fabricas import HOY, dos_invernaderos, lote_sembrado, merma_de, merma_de_camara, salida_por_cosecha
from inventario.models import Insumo
from inventario.tests.fabricas import tipo_de_insumo
from iot.tests.fabricas import ConCatalogoIot
from maestros.tests.fabricas import crear_tecnico, crear_vendedor

URL = reverse("estadisticas:consolidadas")
D = Decimal
TABS = ("resumen", "produccion", "compras", "resultados")


class RecorridoDeEstadisticasConsolidadasTests(ConCatalogoIot, CorreccionBase):
    """El Gerente recorre las cuatro pestañas de un mes con dos ejercicios contables, recepciones parciales, correcciones dentro y fuera del período y mermas en cámara.

    Compras (D-89), con las fechas fijadas: R1 20/10 (A: 4 kg de Fertilizante $ 40,00 y 20 Macetas $ 200,00), C0 25/10 (− $ 10,00), R2 10/11 ($ 60,00), R3 12/11 (B: Tomates $ 80,00)
    y C1 22/11 (− $ 20,00). Libro: el ejercicio 1 va del 01/01 al 15/11 y el 2 desde el 16/11; ventas de $ 1.000,00 (10/11) y $ 500,00 (20/11) y un gasto de $ 300,00 (12/11)."""

    def setUp(self):
        super().setUp()
        # Compras
        Insumo.objects.filter(pk=self.tomate.insumo_id).update(tipo_insumo=tipo_de_insumo("Plantines"))
        self.r1 = self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence), self.linea(self.l_maceta, 20)])
        self.c0 = self.corregir(self.ana, self.r1, [(self.detalle_de(self.r1, self.l_fert), 1)])
        self.r2 = self.registrar(self.ana, [self.linea(self.l_fert, 6, self.vence)])
        self.r3 = self.recibir_b()
        self.c1 = self.corregir(self.ana, self.r2, [(self.detalle_de(self.r2, self.l_fert), 2)])
        for recepcion, dia in ((self.r1, date(2026, 10, 20)), (self.r2, date(2026, 11, 10)), (self.r3, date(2026, 11, 12))):
            Recepcion.objects.filter(pk=recepcion.pk).update(fecha_recepcion=dia)
        for correccion, dia in ((self.c0, date(2026, 10, 25)), (self.c1, date(2026, 11, 22))):
            CorreccionRecepcion.objects.filter(pk=correccion.pk).update(fecha_correccion=dia)
        # Libro: dos ejercicios (el abierto de `PagosBase` empieza hoy: se lo mueve al 16/11).
        EjercicioContable.objects.filter(pk=self.abierto.pk).update(fecha_inicio_ejercicio=date(2026, 11, 16), fecha_cierre_ejercicio=date(2027, 11, 15))
        self.abierto.refresh_from_db()
        self.e1 = ejercicio(EjercicioContable.Estado.CERRADO, date(2026, 1, 1), date(2026, 11, 15))
        asiento_de_prueba(self.e1, date(2026, 11, 10), [(cuentas.CAJA, DEBE, D("1000.00")), (cuentas.VENTAS, HABER, D("1000.00"))])
        asiento_de_prueba(self.e1, date(2026, 11, 12), [(cuentas.GASTOS_DE_PRODUCCION, DEBE, D("300.00")), (cuentas.CAJA, HABER, D("300.00"))])
        asiento_de_prueba(self.abierto, date(2026, 11, 20), [(cuentas.CAJA, DEBE, D("500.00")), (cuentas.VENTAS, HABER, D("500.00"))])
        # Producción: dos invernaderos propios de `produccion`, con una merma de lote y otra en cámara.
        self.n, self.s = dos_invernaderos()
        self.lote = lote_sembrado(self.n, 100, date(2026, 11, 5))
        salida_por_cosecha(self.lote, 30, date(2026, 11, 10), "2.0000")
        merma_de(self.lote, 10, "plaga", date(2026, 11, 12))
        merma_de_camara(self.lote, 4, "dano_en_camara", date(2026, 11, 13))
        lote_sembrado(self.s, 40, date(2026, 11, 6), variedad=self.s.variedad)

    def ver(self, cuenta, **parametros):
        """Abre la pantalla como `cuenta` con `hoy` = 26/11/2026 (el patch vale solo durante el pedido)."""
        self.client.force_login(cuenta)
        with mock.patch("estadisticas.views.timezone.localdate", return_value=HOY):
            return self.client.get(URL, parametros)

    def test_recorrido_del_gerente_por_las_cuatro_pestanas(self):
        """Gerente: abre «Estadísticas» desde el menú, recorre Resumen, Producción, Compras y Resultados del mes y ve cada cosa donde corresponde."""
        auditoria = RegistroAuditoria.objects.count()

        # 1. Resumen (la pestaña por defecto): ventas de dos ejercicios, compras netas, resultado y plantas cosechadas.
        respuesta = self.ver(self.gerente)
        self.assertEqual((respuesta.status_code, respuesta.context["pestana"]), (200, "resumen"))
        a = respuesta.context["resultado"].actual
        self.assertEqual((a.libro.ventas, a.libro.resultado, a.compras.total, a.por_invernadero.total.cosechadas), (D("1500.00"), D("1200.00"), D("120.00"), 30))
        for texto in ("$ 1.500,00", "$ 120,00", "$ 1.200,00", "Plantas cosechadas"):
            self.assertContains(respuesta, texto)

        # 2. Producción: una fila por invernadero con el total; la merma en cámara va aparte y no entra en el % de merma de las plantas.
        respuesta = self.ver(self.gerente, pestana="produccion")
        a = respuesta.context["resultado"].actual
        nombres = {f.nombre for f in a.por_invernadero.filas}
        self.assertIn("Invernadero Norte", nombres)
        self.assertIn("Invernadero Sur", nombres)
        total = a.por_invernadero.total
        self.assertEqual((total.sembradas, total.cosechadas, total.merma), (140, 30, D("7.1")))  # 10 perdidas ÷ (100 + 40): las 4 de cámara no entran
        self.assertEqual((a.merma_en_camara.plantas, a.merma_en_camara.valor, a.merma_en_camara.sin_asiento), (4, None, True))
        self.assertContains(respuesta, "Todavía no hay asientos para estas mermas.")

        # 3. Compras: lo recibido menos lo corregido dentro del mes (60 + 80 − 20), por proveedor y por rubro.
        respuesta = self.ver(self.gerente, pestana="compras")
        compras = respuesta.context["resultado"].actual.compras
        self.assertEqual(compras.total, D("120.00"))
        self.assertEqual([(f.nombre, f.monto) for f in compras.por_proveedor], [("Viveros del Este S. R. L.", D("80.00")), ("Semillas del Sur S. A.", D("40.00"))])
        self.assertEqual([(f.nombre, f.monto) for f in compras.por_categoria], [("Plantines", D("80.00")), ("Limpieza", D("40.00"))])
        self.assertContains(respuesta, "Semillas del Sur S. A.")
        self.assertContains(respuesta, "$ 120,00")

        # 4. Resultados: el período cruza los dos ejercicios y suma los dos; hay un enlace al libro por ejercicio.
        respuesta = self.ver(self.gerente, pestana="resultados")
        libro = respuesta.context["resultado"].actual.libro
        self.assertEqual((libro.ingresos, libro.egresos, libro.resultado), (D("1500.00"), D("300.00"), D("1200.00")))
        self.assertContains(respuesta, "El período cruza dos ejercicios")
        self.assertEqual([t for t, _ in respuesta.context["enlaces_al_libro"]], ["Ejercicio 1", "Ejercicio 2"])

        # Una consulta no deja huella en la auditoría (regla 7).
        self.assertEqual(RegistroAuditoria.objects.count(), auditoria)

    def test_recorrido_de_una_correccion_dentro_y_otra_fuera_del_periodo(self):
        """Gerente: en octubre cuentan la recepción R1 y la corrección C0 (230,00) pero no la C1 de noviembre; del 22/10 al 26/11 entra la C0 sin la R1 (110,00); y el total
        coincide con lo que sumaron los asientos de recepción y de corrección de esas fechas."""
        octubre = self.ver(self.gerente, pestana="compras", periodo="personalizado", desde="2026-10-01", hasta="2026-10-31").context["resultado"].actual.compras
        self.assertEqual(octubre.total, D("230.00"))
        recorte = self.ver(self.gerente, pestana="compras", periodo="personalizado", desde="2026-10-22", hasta="2026-11-26").context["resultado"].actual.compras
        self.assertEqual(recorte.total, D("110.00"))
        self.assertEqual({f.nombre: f.monto for f in recorte.por_proveedor}["Semillas del Sur S. A."], D("30.00"))
        # Contra los asientos (D-89 y D-90): 240 + 60 + 80 (recepciones) − 10 − 20 (correcciones) = 350 en todo el período 15/10 al 26/11.
        todo = self.ver(self.gerente, pestana="compras", periodo="personalizado", desde="2026-10-15", hasta="2026-11-26").context["resultado"].actual.compras
        self.assertEqual(todo.total, D("350.00"))
        self.assertEqual([(f.anio, f.mes, f.monto) for f in todo.por_mes], [(2026, 10, D("230.00")), (2026, 11, D("120.00"))])

    def test_recorrido_de_los_demas_roles_y_de_un_periodo_invalido(self):
        """Todos los demás roles reciben 403 en las cuatro pestañas; el Gerente con un período inválido ve el mensaje y el formulario, sin datos."""
        otros = [self.ana, self.beto, self.contador, crear_vendedor(), crear_tecnico()]
        for cuenta in otros:
            for pestana in TABS:
                with self.subTest(cuenta=str(cuenta), pestana=pestana):
                    self.assertEqual(self.ver(cuenta, pestana=pestana).status_code, 403)
        respuesta = self.ver(self.gerente, periodo="personalizado", desde="2026-11-20", hasta="2026-11-10")
        self.assertContains(respuesta, "La fecha “desde” no puede ser posterior a “hasta”.")
        self.assertIsNone(respuesta.context["resultado"])
