# Pruebas de CMP-CRR-RCL · Cerrar Reclamo a Proveedor (CMP-06, paso 3): ``cerrar_reclamo`` de ``compras/servicios/reclamos.py``. Fuente: docs/casos_de_uso/compras/correccion_y_reclamos.md
# (CMP-CRR-RCL, alto nivel v0.1: precondiciones a y b, postcondiciones a y b y reglas 1 a 3), «Cómo se aplica (código)», D-36 y docs/modelo/compras.md («ReclamoProveedor»).
#
# API que fijan estas pruebas: ``cerrar_reclamo(actor, reclamo_id) -> ReclamoProveedor`` (atómico; solo el Gerente activo). Errores (``ErrorDeCompras``): ``reclamo_sin_emitir`` (regla 1: solo se
# cierra un reclamo emitido) y ``reclamo_ya_cerrado`` (regla 2: no se reabre ni se vuelve a cerrar). ``Http404`` si no existe; ``PermissionDenied`` si no es el Gerente activo. No manda correo.

from django.core import mail
from django.core.exceptions import PermissionDenied
from django.http import Http404

from compras.models import ReclamoProveedor
from compras.tests.base_correcciones import ReclamoBase, reclamos
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from maestros.tests.fabricas import crear_agronomo, crear_vendedor


def registro_del_cierre():
    """El registro de auditoría del cierre (la acción se resuelve acá para que un nombre mal escrito falle en la prueba y no al importar)."""
    return RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.CIERRE_RECLAMO)


class CmpCrrRclTests(ReclamoBase):
    """El Gerente cierra el reclamo ya emitido, una vez tratada la situación con el proveedor por fuera del Sistema."""

    def emitido(self):
        recepcion, reclamo = self.recepcion_con_reclamo()
        self.emitir(self.gerente, reclamo)
        return recepcion, reclamo

    def test_flujo_principal_el_gerente_cierra_el_reclamo_emitido(self):
        """Postcondición a: el reclamo pasa a «cerrado» y conserva su Gerente y su fecha de emisión."""
        _, reclamo = self.emitido()
        cerrado = self.cerrar(self.gerente, reclamo)
        reclamo.refresh_from_db()
        self.assertEqual((reclamo.estado_reclamo, reclamo.gerente_id, reclamo.fecha_reclamo), ("cerrado", self.gerente.pk, self.hoy))
        self.assertEqual(cerrado.pk, reclamo.pk)

    def test_post_b_un_registro_de_auditoria_nombra_el_reclamo_y_el_cambio_de_estado(self):
        """Postcondición b y D-36: un registro ``cierre_reclamo`` de quien actuó con el reclamo entre los afectados y el cambio de estado («abierto» → «cerrado») en ``cambios``."""
        _, reclamo = self.emitido()
        self.cerrar(self.gerente, reclamo)
        registro = registro_del_cierre()
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertIn(("compras.reclamoproveedor", reclamo.pk), {(a["modelo"], a["id"]) for a in registro.afectados})
        self.assertEqual(registro.detalle["cambios"]["estado_reclamo"], {"antes": "abierto", "despues": "cerrado"})

    def test_regla_1_solo_se_cierra_un_reclamo_emitido(self):
        """Regla 1 y precondición b: un reclamo sin emitir no se cierra (``reclamo_sin_emitir``) y no cambia nada; lo respalda también la restricción de la base."""
        _, reclamo = self.recepcion_con_reclamo()
        antes = self.instantanea_de_reclamos()
        self.assertEqual(self.error_de_reclamo("cerrar_reclamo", self.gerente, reclamo).codigo, "reclamo_sin_emitir")
        self.sin_cambios_de_reclamos(antes)

    def test_regla_2_un_reclamo_cerrado_no_se_reabre_ni_se_cierra_dos_veces(self):
        """Regla 2: un reclamo cerrado no se reabre; cerrarlo otra vez es ``reclamo_ya_cerrado`` y emitirlo, ``reclamo_ya_emitido``; no cambia nada."""
        _, reclamo = self.emitido()
        self.cerrar(self.gerente, reclamo)
        antes = self.instantanea_de_reclamos()
        self.assertEqual(self.error_de_reclamo("cerrar_reclamo", self.gerente, reclamo).codigo, "reclamo_ya_cerrado")
        self.assertEqual(self.error_de_reclamo("emitir_reclamo", self.gerente, reclamo).codigo, "reclamo_ya_emitido")
        self.sin_cambios_de_reclamos(antes)
        self.assertEqual(ReclamoProveedor.objects.get(pk=reclamo.pk).estado_reclamo, "cerrado")

    def test_regla_3_el_cierre_no_cambia_el_stock_las_lineas_ni_el_pago_ni_manda_correo(self):
        """Regla 3: cerrar no cambia el stock, las líneas de la orden ni el pago, y no manda ningún correo."""
        _, reclamo = self.emitido()
        antes = self.instantanea()
        correos = len(mail.outbox)
        self.cerrar(self.gerente, reclamo)
        despues = self.instantanea()
        self.assertEqual(antes[:10] + antes[11:14], despues[:10] + despues[11:14])  # sin tocar los registros de auditoría (posición 10) ni los correos (14)
        self.assertEqual(len(mail.outbox), correos)

    def test_pre_a_solo_el_gerente_activo_cierra(self):
        """Precondición a: ni el Agrónomo, el Vendedor, el Capataz, el Contador o el Administrador, ni un Gerente inactivo, ni nadie (``None``)."""
        _, reclamo = self.emitido()
        antes = self.instantanea_de_reclamos()
        gerente_inactivo = crear_gerente(email="otro.gerente@infoponia.com", activo=False)
        for actor in (self.ana, crear_agronomo(), crear_vendedor(), crear_capataz(), self.contador, crear_administrador(), gerente_inactivo, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                reclamos.cerrar_reclamo(actor, reclamo.pk)
        self.sin_cambios_de_reclamos(antes)

    def test_pre_a_un_reclamo_que_no_existe_es_404(self):
        """Un reclamo que no existe es ``Http404``."""
        with self.assertRaises(Http404):
            reclamos.cerrar_reclamo(self.gerente, 9999)
