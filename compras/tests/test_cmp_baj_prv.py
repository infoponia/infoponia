# Pruebas de CMP-BAJ-PRV · Baja Proveedor (docs/casos_de_uso/compras/proveedores.md). Cita D-22, D-36 y D-87.
#
# Servicios que se prueban (compras/servicios/proveedores.py), tomados del módulo dentro de cada prueba:
#   baja_proveedor(actor, proveedor_id) -> Proveedor
#     - Precondición a: Gerente activo. Precondición b: el proveedor está activo (``ErrorDeCompras`` ``proveedor_inactivo``).
#     - Precondiciones c y d: sin órdenes de compra no terminadas ni pagos pendientes. En CMP-01 la lista de impedimentos está vacía: la
#       precondición c se completa en CMP-03 (``orden_no_terminada``) y la d en CMP-05 (``pago_pendiente``). Si hay impedimentos, se
#       rechaza con ``ErrorDeCompras`` ``baja_con_impedimentos`` con TODOS juntos (qué lo impide y cómo resolverlo, regla 2).
#     - Regla 1: la baja es lógica. Regla 3: anular los enlaces vigentes se completa en CMP-02b. Regla 5: un pedido «en cotización» donde está
#       invitado no bloquea la baja.
#     - Postcondición a: queda «inactivo». Postcondición b: un registro ``baja_proveedor`` con el cambio de estado.
#   impedimentos_de_baja(proveedor) -> list[Impedimento]  (``Impedimento(codigo, texto, como_resolver)`` de maestros.extensiones)

from unittest import mock

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase

from compras.errores import ErrorDeCompras
from compras.models import Proveedor
from compras.tests.fabricas import GERENTE, afectado_de, proveedor, tipo_de_insumo
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.tests.fabricas import perezoso
from maestros.extensiones import Impedimento
from maestros.tests.fabricas import crear_agronomo, crear_vendedor

proveedores = perezoso("compras.servicios.proveedores")
BAJA = RegistroAuditoria.Accion.BAJA_PROVEEDOR

ORDEN = Impedimento("orden_no_terminada", "Tiene la orden OC-3 sin terminar.", "Recibí o cerrá con faltante la mercadería en camino.")
PAGO = Impedimento("pago_pendiente", "Tiene un pago pendiente de la orden OC-2.", "Registrá el pago.")


class CmpBajPrvServicioTests(TestCase):
    """Precondiciones, reglas y postcondiciones de CMP-BAJ-PRV."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.proveedor = proveedor("Semillas del Sur S. A.", n=1, especialidades=[tipo_de_insumo("Limpieza")])

    def baja(self, actor=GERENTE, proveedor_id=None):
        return proveedores.baja_proveedor(self.gerente if actor is GERENTE else actor, proveedor_id or self.proveedor.pk)

    def registros(self):
        return RegistroAuditoria.objects.filter(accion=BAJA)

    # ---- precondiciones ----

    def test_pre_a_solo_un_gerente_activo_da_de_baja(self):
        """CMP-BAJ-PRV precondición a: solo el Gerente."""
        for actor in (crear_agronomo(), crear_capataz(), crear_vendedor(), crear_administrador(), crear_gerente(email="b@infoponia.com", activo=False), None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                self.baja(actor=actor)
        self.proveedor.refresh_from_db()
        self.assertEqual(self.proveedor.estado_proveedor, "activo")
        self.assertFalse(self.registros().exists())

    def test_pre_b_un_proveedor_inactivo_no_se_da_de_baja_otra_vez(self):
        """CMP-BAJ-PRV precondición b: el proveedor está «activo» (``proveedor_inactivo``)."""
        inactivo = proveedor("Agro Norte S. R. L.", n=2, activo=False)
        with self.assertRaises(ErrorDeCompras) as contexto:
            self.baja(proveedor_id=inactivo.pk)
        self.assertEqual(contexto.exception.codigo, "proveedor_inactivo")
        self.assertFalse(self.registros().exists())

    def test_un_proveedor_que_no_existe_da_404(self):
        """docs/patrones/abm.md, sección 2: un id inexistente da ``Http404``."""
        with self.assertRaises(Http404):
            self.baja(proveedor_id=999999)

    # ---- precondiciones c y d: impedimentos ----

    def test_pre_c_y_d_en_cmp_01_no_hay_impedimentos(self):
        """CMP-BAJ-PRV precondiciones c y d: ``impedimentos_de_baja`` existe y devuelve la lista vacía hasta CMP-03 (órdenes) y CMP-05 (pagos)."""
        self.assertEqual(proveedores.impedimentos_de_baja(self.proveedor), [])

    def test_pre_c_una_orden_no_terminada_impide_la_baja(self):
        """CMP-BAJ-PRV precondición c y regla 2: se rechaza con el código del impedimento y su texto; el proveedor sigue activo. La consulta la
        completa CMP-03: acá se simula con ``impedimentos_de_baja``."""
        with mock.patch("compras.servicios.proveedores.impedimentos_de_baja", return_value=[ORDEN]):
            with self.assertRaises(ErrorDeCompras) as contexto:
                self.baja()
        self.assertEqual(contexto.exception.codigo, "baja_con_impedimentos")
        self.assertEqual(contexto.exception.datos["impedimentos"], [ORDEN])
        self.assertIn(ORDEN.texto, contexto.exception.mensaje)
        self.proveedor.refresh_from_db()
        self.assertEqual(self.proveedor.estado_proveedor, "activo")
        self.assertFalse(self.registros().exists())

    def test_regla_2_se_informan_todos_los_impedimentos_juntos_con_como_resolverlos(self):
        """CMP-BAJ-PRV regla 2 y docs/patrones/abm.md, sección 3: no se queda con el primero; cada uno dice qué lo impide y cómo resolverlo."""
        with mock.patch("compras.servicios.proveedores.impedimentos_de_baja", return_value=[ORDEN, PAGO]):
            with self.assertRaises(ErrorDeCompras) as contexto:
                self.baja()
        impedimentos = contexto.exception.datos["impedimentos"]
        self.assertEqual([i.codigo for i in impedimentos], ["orden_no_terminada", "pago_pendiente"])
        self.assertTrue(all(i.texto and i.como_resolver for i in impedimentos))
        for impedimento in (ORDEN, PAGO):
            self.assertIn(impedimento.texto, contexto.exception.mensaje)
            self.assertIn(impedimento.como_resolver, contexto.exception.mensaje)

    def test_regla_2_los_impedimentos_se_calculan_con_el_proveedor_bloqueado(self):
        """docs/patrones/bloqueos.md: ``impedimentos_de_baja`` se llama dentro de la transacción, con el proveedor ya leído de nuevo."""
        llamados = []

        def impedimentos(proveedor_leido):
            llamados.append(proveedor_leido.pk)
            return []

        with mock.patch("compras.servicios.proveedores.impedimentos_de_baja", side_effect=impedimentos):
            self.baja()
        self.assertEqual(llamados, [self.proveedor.pk])

    # ---- postcondición a y reglas 1 y 5 ----

    def test_post_a_el_proveedor_queda_inactivo(self):
        """CMP-BAJ-PRV postcondición a: queda «inactivo» (baja lógica); devuelve el proveedor."""
        devuelto = self.baja()
        self.proveedor.refresh_from_db()
        self.assertEqual((devuelto.pk, self.proveedor.estado_proveedor), (self.proveedor.pk, "inactivo"))

    def test_regla_1_la_baja_es_logica_y_conserva_todos_sus_datos(self):
        """CMP-BAJ-PRV regla 1: no se borra ni se pierden sus datos ni sus especialidades; el CUIT sigue ocupado (se reactiva con el alta)."""
        antes = Proveedor.objects.get(pk=self.proveedor.pk)
        self.baja()
        despues = Proveedor.objects.get(pk=self.proveedor.pk)
        self.assertEqual(Proveedor.objects.count(), 1)
        self.assertEqual(
            (despues.cuit_proveedor, despues.razon_social_proveedor, despues.email_proveedor, set(despues.especialidades.all())),
            (antes.cuit_proveedor, antes.razon_social_proveedor, antes.email_proveedor, set(antes.especialidades.all())),
        )

    def test_regla_5_tener_pedidos_en_cotizacion_no_bloquea_la_baja(self):
        """CMP-BAJ-PRV regla 5: los pedidos «en cotización» donde está invitado no son un impedimento (hoy no hay pedidos: la lista es vacía)."""
        self.assertEqual([i.codigo for i in proveedores.impedimentos_de_baja(self.proveedor)], [])
        self.baja()

    # ---- postcondición b: auditoría ----

    def test_post_b_audita_la_baja_con_el_cambio_de_estado(self):
        """CMP-BAJ-PRV postcondición b y D-36: usuario, rol, identificador y el cambio de estado."""
        self.baja()
        registro = self.registros().get()
        self.assertEqual((registro.usuario_id, registro.rol), (self.gerente.pk, "gerente"))
        self.assertEqual(registro.afectados, [afectado_de(self.proveedor)])
        self.assertEqual(registro.detalle, {"cambios": {"estado": {"antes": "activo", "despues": "inactivo"}}})

    def test_post_b_el_registro_se_lee_en_la_pantalla_de_auditoria(self):
        """D-36: «Estado: Activo → Inactivo»."""
        self.baja()
        self.assertEqual(self.registros().get().filas_de_cambios(), [("Estado", "Activo", "Inactivo")])
