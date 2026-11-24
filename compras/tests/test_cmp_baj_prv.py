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
from compras.models import EnlaceProveedor, Proveedor
from compras.tests.fabricas import GERENTE, afectado_de, cotizacion_de, detalle_de_pedido, enlace_de, invitar, proveedor, tipo_de_insumo
from compras.tests.fabricas import pedido as armar_pedido
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, perezoso
from maestros.extensiones import Impedimento
from maestros.tests.fabricas import crear_agronomo, crear_agronomo_con_invernadero, crear_vendedor

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


class CmpBajPrvEnlacesTests(ConDatosDeInventario, TestCase):
    """Regla 3 de CMP-BAJ-PRV (CMP-02b): si el proveedor estaba invitado a un pedido «en cotización», su enlace deja de servir (pasa a «anulado», D-88 punto 2)
    y su cotización «propuesta» no se toca (la regla 3 solo dice que no se podrá elegir: eso lo controla CMP-GNR-ODC, CMP-03). La baja anula los enlaces
    vigentes de sus invitaciones a pedidos en cotización, los bloquea después del proveedor (proveedor → enlace, como al cotizar) y deja lo anulado en la auditoría."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.ana, self.invernadero = crear_agronomo_con_invernadero("Norte")
        self.lechuga = existencia(insumo("Lechuga", unidad="unidad"), self.invernadero, minimo=20, precio="12.50")
        self.proveedor = proveedor("Semillas del Sur S. A.", n=1)
        self.otro = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.pedido = armar_pedido(self.ana)
        self.detalle = detalle_de_pedido(self.pedido, self.lechuga, cantidad="20")
        self.enlace, _ = enlace_de(invitar(self.pedido, self.proveedor))
        self.enlace_del_otro, _ = enlace_de(invitar(self.pedido, self.otro))

    def baja(self):
        return proveedores.baja_proveedor(self.gerente, self.proveedor.pk)

    def estado(self, enlace):
        enlace.refresh_from_db()
        return enlace.estado

    def test_regla_3_el_enlace_vigente_pasa_a_anulado_y_el_de_otro_proveedor_no(self):
        """Regla 3: solo los enlaces del proveedor dado de baja."""
        self.baja()
        self.assertEqual((self.estado(self.enlace), self.estado(self.enlace_del_otro)), ("anulado", "vigente"))

    def test_regla_3_el_enlace_anulado_ya_no_sirve_para_cotizar(self):
        """D-88 punto 2: el portal dice que el enlace no se puede usar (el proveedor está inactivo y su enlace, anulado)."""
        from compras.servicios import enlaces

        self.baja()
        self.assertEqual(enlaces.situacion_del_enlace(enlaces.enlace_por_id(self.enlace.pk)), enlaces.ANULADO)

    def test_regla_3_anula_el_enlace_de_cada_pedido_en_cotizacion_donde_esta_invitado(self):
        """Regla 3: de todos los pedidos «en cotización», de cualquier Agrónomo."""
        otro_pedido = armar_pedido(self.ana, dias_al_limite=5)
        detalle_de_pedido(otro_pedido, self.lechuga, cantidad="5")
        otro_enlace, _ = enlace_de(invitar(otro_pedido, self.proveedor))
        self.baja()
        self.assertEqual((self.estado(self.enlace), self.estado(otro_enlace)), ("anulado", "anulado"))

    def test_regla_3_no_toca_los_enlaces_usados_ni_los_de_pedidos_que_ya_no_estan_en_cotizacion(self):
        """Regla 3: un enlace «usado» (ya cotizó) y los de un pedido cerrado o cancelado quedan como estaban; su cotización «propuesta» tampoco cambia."""
        cotizo = armar_pedido(self.ana, dias_al_limite=4)
        d = detalle_de_pedido(cotizo, self.lechuga, cantidad="5")
        usado, _ = enlace_de(invitar(cotizo, self.proveedor), estado="usado")
        cotizacion = cotizacion_de(cotizo, self.proveedor, [(d, 5, "60.00", 2)])
        cerrado = armar_pedido(self.ana, estado="cerrado")
        en_cerrado, _ = enlace_de(invitar(cerrado, self.proveedor))
        self.baja()
        cotizacion.refresh_from_db()
        self.assertEqual((self.estado(usado), self.estado(en_cerrado), cotizacion.estado_cotizacion), ("usado", "vigente", "propuesta"))

    def test_regla_3_la_baja_no_cambia_el_pedido(self):
        """Regla 5: el pedido sigue «en cotización»; solo cambian los enlaces del proveedor."""
        self.baja()
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado_pedido, "en_cotizacion")

    def test_post_b_los_enlaces_anulados_van_en_la_auditoria_de_la_baja_sin_token(self):
        """D-36: los enlaces anulados figuran entre los afectados y en ``datos``; el registro nunca lleva el token."""
        self.baja()
        registro = RegistroAuditoria.objects.get(accion=BAJA)
        self.assertEqual([a["id"] for a in registro.afectados if a["modelo"] == "compras.enlaceproveedor"], [self.enlace.pk])
        self.assertEqual([r["id"] for r in registro.detalle["datos"]["enlaces_anulados"]], [self.enlace.pk])
        self.assertEqual(registro.detalle["cambios"], {"estado": {"antes": "activo", "despues": "inactivo"}})
        self.assertNotIn(self.enlace.token_resumen, str(registro.detalle) + str(registro.afectados))

    def test_post_b_sin_enlaces_vigentes_el_registro_queda_como_siempre(self):
        """Sin enlaces que anular, no aparece ``datos`` en el registro."""
        EnlaceProveedor.objects.filter(pk=self.enlace.pk).update(estado="vencido")
        self.baja()
        self.assertEqual(RegistroAuditoria.objects.get(accion=BAJA).detalle, {"cambios": {"estado": {"antes": "activo", "despues": "inactivo"}}})

    def test_garantia_si_falla_la_auditoria_los_enlaces_siguen_vigentes(self):
        """La baja es atómica: si se revierte, el proveedor sigue activo y sus enlaces vigentes."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                self.baja()
        self.proveedor.refresh_from_db()
        self.assertEqual((self.proveedor.estado_proveedor, self.estado(self.enlace)), ("activo", "vigente"))

    def test_regla_3_reactivado_el_proveedor_los_enlaces_anulados_no_vuelven(self):
        """CMP-ALT-PRV (reactivación): los enlaces anulados siguen anulados; para volver a invitarlo hace falta «Reenviar invitación» (CMP-CNS-PED regla 7)."""
        self.baja()
        Proveedor.objects.filter(pk=self.proveedor.pk).update(estado_proveedor="activo")
        self.assertEqual(self.estado(self.enlace), "anulado")

from django.db import connection  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402



# ---------------------------------------------------------------------------------------------------------------------------------
# CMP-03, paso 4: la precondición c de CMP-BAJ-PRV (H22; disparador «Cuando se programen CMP-02a, CMP-02b, CMP-03 y CMP-05», punto 3). ``impedimentos_de_baja``
# suma, por cada orden **no terminada** (pendiente de aprobación, aprobada o parcialmente recibida) con una línea de una cotización de ese proveedor, un
# impedimento con el código ``orden_no_terminada``. Es distinto del impedimento del insumo ``orden_de_compra_aprobada`` (``compras/servicios/registrantes.py``).
# ---------------------------------------------------------------------------------------------------------------------------------

from compras.tests.fabricas import orden_de  # noqa: E402


class OrdenNoTerminadaImpideLaBajaTests(ConDatosDeInventario, TestCase):
    """CMP-BAJ-PRV precondición c y regla 2: «órdenes de compra no terminadas: pendiente de aprobación, aprobada o parcialmente recibida»."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.ana, self.norte = crear_agronomo_con_invernadero("Norte")
        self.iin = existencia(insumo("Lechuga", unidad="unidad"), self.norte, minimo=0, precio="10.00")
        self.proveedor = proveedor("Semillas del Sur S. A.", n=1)
        self.otro = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")

    def orden(self, estado="pendiente_aprobacion", proveedores=None):
        """Una orden en ``estado`` con una línea de cada proveedor de ``proveedores`` (por omisión, el del setUp)."""
        pedido = armar_pedido(self.ana)
        detalle = detalle_de_pedido(pedido, self.iin, cantidad="10")
        cotizaciones = [cotizacion_de(pedido, p, [(detalle, 5, "50.00", 2)]) for p in (proveedores or [self.proveedor])]
        return orden_de(pedido, cotizaciones, estado=estado, gerente=self.gerente, motivo="No hay presupuesto." if estado == "rechazada" else "")

    def test_pre_c_una_orden_no_terminada_impide_la_baja_con_su_codigo_y_como_resolverlo(self):
        """Precondición c: pendiente de aprobación, aprobada y parcialmente recibida impiden; el texto nombra la orden y su estado y dice cómo resolverlo."""
        ordenes_ = [self.orden(estado) for estado in ("pendiente_aprobacion", "aprobada", "parcialmente_recibida")]
        impedimentos = proveedores.impedimentos_de_baja(self.proveedor)
        self.assertEqual([i.codigo for i in impedimentos], ["orden_no_terminada"] * 3)
        for orden in ordenes_:
            (propio,) = [i for i in impedimentos if str(orden) in i.texto]
            self.assertIn(orden.get_estado_orden_compra_display().lower(), propio.texto.lower())
            self.assertTrue(propio.como_resolver)

    def test_pre_c_una_orden_terminada_no_impide(self):
        """Precondición c: rechazada, recibida y recibida con faltante ya terminaron (el pago pendiente lo trata CMP-05)."""
        for estado in ("rechazada", "recibida", "recibida_con_faltante"):
            self.orden(estado)
        self.assertEqual(proveedores.impedimentos_de_baja(self.proveedor), [])

    def test_pre_c_una_orden_de_otro_proveedor_no_impide(self):
        """Precondición c: solo cuentan las órdenes con líneas de este proveedor."""
        self.orden(proveedores=[self.otro])
        self.assertEqual(proveedores.impedimentos_de_baja(self.proveedor), [])
        self.assertEqual([i.codigo for i in proveedores.impedimentos_de_baja(self.otro)], ["orden_no_terminada"])

    def test_pre_c_una_orden_con_dos_proveedores_impide_la_baja_de_cada_uno(self):
        """Una orden puede incluir varios proveedores (regla 13 de 8.16): impide la baja de cada uno de ellos, una sola vez."""
        self.orden(proveedores=[self.proveedor, self.otro])
        for p in (self.proveedor, self.otro):
            self.assertEqual([i.codigo for i in proveedores.impedimentos_de_baja(p)], ["orden_no_terminada"])

    def test_regla_5_un_pedido_en_cotizacion_o_una_cotizacion_no_elegida_no_impide(self):
        """Regla 5 de CMP-BAJ-PRV: un pedido «en cotización» con su cotización «propuesta», o una cotización descartada, no impiden la baja."""
        pedido = armar_pedido(self.ana)
        detalle = detalle_de_pedido(pedido, self.iin, cantidad="10")
        cotizacion_de(pedido, self.proveedor, [(detalle, 5, "50.00", 2)])
        otro_pedido = armar_pedido(self.ana)
        otro_detalle = detalle_de_pedido(otro_pedido, self.iin, cantidad="10")
        cotizacion_de(otro_pedido, self.proveedor, [(otro_detalle, 5, "50.00", 2)], estado="descartada")
        self.assertEqual(proveedores.impedimentos_de_baja(self.proveedor), [])

    def test_baja_proveedor_con_una_orden_no_terminada_se_rechaza_y_no_cambia_nada(self):
        """Precondición c y regla 2: ``baja_proveedor`` informa el impedimento (``baja_con_impedimentos``) y el proveedor sigue «activo»; sin registro de auditoría."""
        self.orden("aprobada")
        with self.assertRaises(ErrorDeCompras) as contexto:
            proveedores.baja_proveedor(self.gerente, self.proveedor.pk)
        self.assertEqual(contexto.exception.codigo, "baja_con_impedimentos")
        self.assertEqual([i.codigo for i in contexto.exception.datos["impedimentos"]], ["orden_no_terminada"])
        self.proveedor.refresh_from_db()
        self.assertEqual(self.proveedor.estado_proveedor, "activo")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=BAJA).exists())

    def test_baja_proveedor_con_la_orden_rechazada_se_puede(self):
        """Con la orden «rechazada» (terminada) la baja procede: el historial se conserva."""
        self.orden("rechazada")
        self.assertEqual(proveedores.baja_proveedor(self.gerente, self.proveedor.pk).estado_proveedor, "inactivo")

    def test_sin_consultas_por_orden(self):
        """Sin consultas por fila: la misma cantidad de consultas con 1 o con 4 órdenes."""
        self.orden()
        with CaptureQueriesContext(connection) as con_una:
            proveedores.impedimentos_de_baja(self.proveedor)
        for _ in range(3):
            self.orden()
        with CaptureQueriesContext(connection) as con_cuatro:
            proveedores.impedimentos_de_baja(self.proveedor)
        self.assertEqual(len(con_cuatro), len(con_una))
