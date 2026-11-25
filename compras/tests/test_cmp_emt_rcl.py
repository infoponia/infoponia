# Pruebas de CMP-EMT-RCL · Emitir Reclamo a Proveedor y de la lectura de reclamos (CMP-06, paso 3): ``reclamos``, ``ficha_de_reclamo`` y ``emitir_reclamo`` de ``compras/servicios/reclamos.py``.
# Fuente: docs/casos_de_uso/compras/correccion_y_reclamos.md (CMP-EMT-RCL, alto nivel v0.1: precondiciones a y b, postcondiciones a a d, reglas 1 a 4 y R1 y R2), «Cómo se aplica (código)»,
# D-87 punto 5 (la alerta del Gerente y su ``AlertaCompras``), D-86, D-30 y docs/modelo/compras.md («ReclamoProveedor»).
#
# API que fijan estas pruebas (el módulo se toma dentro de cada prueba con ``perezoso``):
#   reclamos(actor, filtros=None) -> list[FilaDeReclamo(reclamo, recepcion, orden, proveedor, invernadero, inconvenientes)]    del más reciente al más antiguo; solo lectura
#       ``filtros["estado"]``: ``"sin_emitir"``, ``"emitido_abierto"`` o ``"cerrado"`` (otro valor se ignora). Los ve el Gerente (todos) y el Agrónomo (los de los invernaderos a cargo);
#       ``PermissionDenied`` para los demás roles, inactivos y ``None``.
#   ficha_de_reclamo(actor, reclamo_id) -> FichaDeReclamo(reclamo, recepcion, orden, proveedor, invernadero, inconvenientes, acciones)     ``Http404`` si no existe; ``PermissionDenied`` fuera del
#       alcance. ``acciones`` es ``frozenset``: ``{"emitir"}`` para el Gerente con el reclamo sin emitir, ``{"cerrar"}`` con el reclamo emitido y abierto; vacío en cualquier otro caso (D-30).
#   emitir_reclamo(actor, reclamo_id) -> ReclamoProveedor      atómico; solo el Gerente activo. Errores (``ErrorDeCompras``): ``reclamo_ya_emitido``.
# El correo al proveedor sale en ``on_commit``.

from django.core import mail
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import override_settings

from compras.errores import ErrorDeCompras
from compras.models import AlertaCompras, ReclamoProveedor
from compras.tests.base_correcciones import DANADA, ReclamoBase, reclamos
from compras.tests.base_recepciones import D
from compras.tests.fabricas import ref
from core.models import Agronomo, RegistroAuditoria
from core.tests.fabricas import BACKEND_QUE_FALLA, crear_administrador, crear_capataz, crear_cuenta, crear_gerente
from inventario.servicios.formato import texto_cantidad
from maestros.models import Alerta
from maestros.servicios import alertas as servicio_de_alertas
from maestros.tests.fabricas import crear_agronomo, crear_vendedor


def registro_de_la_emision():
    """El registro de auditoría de la emisión (la acción se resuelve acá para que un nombre mal escrito falle en la prueba y no al importar)."""
    return RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.EMISION_RECLAMO)


class CmpEmtRclPostcondicionesTests(ReclamoBase):
    """Postcondiciones a a d y el flujo: el Gerente emite el reclamo que dejó la recepción con inconvenientes."""

    def test_flujo_principal_el_gerente_emite_el_reclamo_y_sigue_abierto(self):
        """Postcondición a: el reclamo queda emitido, con el Gerente que lo emitió (R008) y la fecha de emisión igual a la de hoy; sigue «abierto»."""
        _, reclamo = self.recepcion_con_reclamo()
        self.assertFalse(reclamo.emitido)
        emitido = self.emitir(self.gerente, reclamo)
        reclamo.refresh_from_db()
        self.assertEqual((reclamo.gerente_id, reclamo.fecha_reclamo, reclamo.estado_reclamo, reclamo.emitido), (self.gerente.pk, self.hoy, "abierto", True))
        self.assertEqual(emitido.pk, reclamo.pk)

    def test_post_b_la_alerta_recepcion_con_inconvenientes_del_reclamo_queda_resuelta(self):
        """Postcondición b y D-87 punto 5: la alerta del Gerente asociada al reclamo (por su ``AlertaCompras``) pasa a «resuelta», con su fecha de resolución; las alertas de otros reclamos no se tocan."""
        _, reclamo = self.recepcion_con_reclamo()
        otra, linea, _ = self.otra_orden(self.ana, self.norte, cantidad=6, total="60.00", n=5)
        self.registrar(self.ana, [self.linea(linea, 6, inconvenientes=[(DANADA, 1, "")])], orden=otra, proveedor=linea.proveedor, invernadero=self.norte)
        ajeno = ReclamoProveedor.objects.exclude(pk=reclamo.pk).get()
        self.assertEqual(self.alerta_de(reclamo).estado_alerta, Alerta.Estado.ACTIVA)
        self.emitir(self.gerente, reclamo)
        resuelta = self.alerta_de(reclamo)
        self.assertEqual(resuelta.estado_alerta, Alerta.Estado.RESUELTA)
        self.assertIsNotNone(resuelta.fecha_resolucion)
        self.assertEqual(self.alerta_de(ajeno).estado_alerta, Alerta.Estado.ACTIVA)

    def test_post_b_si_la_alerta_ya_estaba_resuelta_la_emision_no_falla(self):
        """Postcondición b: la alerta se resuelve por su ``AlertaCompras``; si alguien ya la había resuelto, emitir igual se registra y la alerta sigue resuelta."""
        _, reclamo = self.recepcion_con_reclamo()
        servicio_de_alertas.resolver_alerta(AlertaCompras.objects.get(reclamo=reclamo).alerta_id)
        self.emitir(self.gerente, reclamo)
        self.assertTrue(ReclamoProveedor.objects.get(pk=reclamo.pk).emitido)
        self.assertEqual(self.alerta_de(reclamo).estado_alerta, Alerta.Estado.RESUELTA)

    def test_post_c_el_proveedor_recibe_un_correo_con_la_recepcion_la_orden_y_cada_inconveniente(self):
        """Postcondición c y R1: un correo al proveedor (y solo a él) con la recepción, la orden y cada inconveniente (tipo, cantidad afectada y descripción). No menciona a otros proveedores."""
        recepcion, reclamo = self.recepcion_con_reclamo(descripcion="Cajas rotas")
        antes = len(mail.outbox)
        self.emitir(self.gerente, reclamo)
        nuevos = mail.outbox[antes:]
        self.assertEqual(len(nuevos), 1)
        correo = nuevos[0]
        self.assertEqual(correo.to, ["ventas@sur.com"])
        self.assertIn(str(self.orden), correo.subject)
        for texto in (str(recepcion), str(self.orden), "Fertilizante", "Mercadería dañada", texto_cantidad(D("2"), "kg"), "Cajas rotas", self.proveedor.nombre_para_mostrar, str(reclamo)):
            self.assertIn(texto, correo.body)
        self.assertNotIn(self.proveedor_b.nombre_para_mostrar, correo.body)

    def test_post_c_el_correo_lista_todos_los_inconvenientes_del_reclamo(self):
        """Postcondición c: con dos inconvenientes (en dos líneas de la recepción) el correo trae los dos."""
        recepcion = self.registrar(
            self.ana,
            [
                self.linea(self.l_fert, 4, self.vence, inconvenientes=[(DANADA, 2, "Cajas rotas")]),
                self.linea(self.l_maceta, 5, inconvenientes=[("producto_distinto", 3, "Macetas de otro tamaño")]),
            ],
        )
        reclamo = ReclamoProveedor.objects.get(recepcion=recepcion)
        antes = len(mail.outbox)
        self.emitir(self.gerente, reclamo)
        cuerpo = mail.outbox[antes].body
        for texto in ("Cajas rotas", "Macetas de otro tamaño", "Mercadería dañada", "Producto distinto", "Maceta"):
            self.assertIn(texto, cuerpo)

    def test_post_d_un_registro_de_auditoria_nombra_el_reclamo_y_el_cambio(self):
        """Postcondición d y D-36: un registro ``emision_reclamo`` de quien actuó (el Gerente) con el reclamo, la recepción y el proveedor entre los afectados, el cambio de emisión (Gerente y fecha) en
        ``cambios`` y la alerta resuelta en ``datos``."""
        recepcion, reclamo = self.recepcion_con_reclamo()
        self.emitir(self.gerente, reclamo)
        registro = registro_de_la_emision()
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        self.assertTrue({("compras.reclamoproveedor", reclamo.pk), ("compras.recepcion", recepcion.pk), ("compras.proveedor", self.proveedor.pk)} <= afectados)
        self.assertEqual(registro.detalle["datos"]["alertas_resueltas"], [ref(self.alerta_de(reclamo))])
        self.assertIn("fecha_reclamo", str(registro.detalle["cambios"]))
        self.assertEqual(str(reclamo), f"REC-{reclamo.pk:04d}")

    def test_regla_3_emitir_no_toca_lo_recibido_ni_el_stock_ni_los_pagos(self):
        """Regla 3 («reclamar significa dejar registrado lo que pasó»): emitir no cambia el stock, las líneas de la orden, el estado de la orden ni el pago pendiente."""
        self.recepcion_con_reclamo()
        reclamo = ReclamoProveedor.objects.get()
        antes = self.instantanea()
        self.emitir(self.gerente, reclamo)
        despues = self.instantanea()
        # lo único que cambia entre las dos fotos es la auditoría y los correos (la alerta resuelta no cambia la cantidad de alertas)
        self.assertEqual(antes[:10] + antes[11:14], despues[:10] + despues[11:14])
        self.assertEqual(despues[14], antes[14] + 1)


class CmpEmtRclPrecondicionesTests(ReclamoBase):
    """Precondiciones a y b y los errores."""

    def test_pre_a_solo_el_gerente_activo_emite(self):
        """Precondición a: ni el Agrónomo (aunque sea quien registró la recepción), el Vendedor, el Capataz, el Contador o el Administrador, ni un Gerente inactivo, ni nadie (``None``). No cambia nada."""
        _, reclamo = self.recepcion_con_reclamo()
        antes = self.instantanea_de_reclamos()
        gerente_inactivo = crear_gerente(email="otro.gerente@infoponia.com", activo=False)
        for actor in (self.ana, crear_agronomo(), crear_vendedor(), crear_capataz(), self.contador, crear_administrador(), gerente_inactivo, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                reclamos.emitir_reclamo(actor, reclamo.pk)
        self.sin_cambios_de_reclamos(antes)

    def test_pre_b_un_reclamo_ya_emitido_no_se_vuelve_a_emitir(self):
        """Precondición b: solo se emite un reclamo «abierto» sin emitir; el segundo intento es ``reclamo_ya_emitido`` y no cambia nada (ni un segundo correo)."""
        _, reclamo = self.recepcion_con_reclamo()
        self.emitir(self.gerente, reclamo)
        antes = self.instantanea_de_reclamos()
        error = self.error_de_reclamo("emitir_reclamo", self.gerente, reclamo)
        self.assertEqual(error.codigo, "reclamo_ya_emitido")
        self.sin_cambios_de_reclamos(antes)

    def test_pre_b_un_reclamo_que_no_existe_es_404(self):
        """Un reclamo que no existe es ``Http404``."""
        with self.assertRaises(Http404):
            reclamos.emitir_reclamo(self.gerente, 9999)

    @override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA)
    def test_ext_correo_que_falla_la_emision_queda_registrada(self):
        """Regla de uso de ``core.correo`` (D-88 punto 6: sin reintentos): si el correo no sale, el reclamo permanece emitido y la alerta resuelta (el correo sale fuera de la transacción)."""
        _, reclamo = self.recepcion_con_reclamo()
        self.emitir(self.gerente, reclamo)
        self.assertTrue(ReclamoProveedor.objects.get(pk=reclamo.pk).emitido)
        self.assertEqual(self.alerta_de(reclamo).estado_alerta, Alerta.Estado.RESUELTA)

    @override_settings(CORREO_CONFIGURADO=False)
    def test_ext_sin_el_correo_configurado_no_sale_nada_y_se_emite(self):
        """D-33: sin el correo configurado no sale ningún correo y el reclamo se emite igual."""
        _, reclamo = self.recepcion_con_reclamo()
        antes = len(mail.outbox)
        self.emitir(self.gerente, reclamo)
        self.assertEqual(len(mail.outbox), antes)
        self.assertTrue(ReclamoProveedor.objects.get(pk=reclamo.pk).emitido)

    def test_garantia_minima_si_la_auditoria_falla_no_queda_la_emision_a_medias(self):
        """Todo o nada: si la emisión falla después de cambiar el reclamo (la auditoría), no queda emitido, ni la alerta resuelta, ni correo."""
        from unittest import mock

        _, reclamo = self.recepcion_con_reclamo()
        antes = self.instantanea_de_reclamos()
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla forzada")):
            with self.assertRaises(RuntimeError), self.captureOnCommitCallbacks(execute=True):
                reclamos.emitir_reclamo(self.gerente, reclamo.pk)
        self.sin_cambios_de_reclamos(antes)


class CmpEmtRclLecturaTests(ReclamoBase):
    """Reglas 2 y 4: el Gerente ve el reclamo con la recepción, el proveedor, el invernadero y cada inconveniente; se llega desde la lista; el Agrónomo lo ve en su alcance."""

    def test_regla_2_la_ficha_trae_la_recepcion_el_proveedor_el_invernadero_y_los_inconvenientes(self):
        """Regla 2: la ficha trae la recepción, la orden, el proveedor, el invernadero y cada inconveniente (tipo, cantidad afectada y descripción); no se modifican ni se agregan."""
        recepcion, reclamo = self.recepcion_con_reclamo()
        ficha = reclamos.ficha_de_reclamo(self.gerente, reclamo.pk)
        self.assertEqual((ficha.reclamo.pk, ficha.recepcion.pk, ficha.orden.pk, ficha.proveedor.pk, ficha.invernadero.pk), (reclamo.pk, recepcion.pk, self.orden.pk, self.proveedor.pk, self.norte.pk))
        self.assertEqual([(i.tipo_inconveniente, i.cantidad_afectada, i.descripcion_inconveniente) for i in ficha.inconvenientes], [(DANADA, D("2"), "Cajas rotas")])

    def test_regla_4_las_acciones_de_la_ficha_siguen_el_estado_del_reclamo_y_el_rol(self):
        """Regla 4 y D-30 (ningún botón lleva a un 403): el Gerente ve «emitir» con el reclamo sin emitir y «cerrar» con el reclamo emitido y abierto; el Agrónomo, nada; con el reclamo cerrado, nadie."""
        _, reclamo = self.recepcion_con_reclamo()
        self.assertEqual(reclamos.ficha_de_reclamo(self.gerente, reclamo.pk).acciones, frozenset({"emitir"}))
        self.assertEqual(reclamos.ficha_de_reclamo(self.ana, reclamo.pk).acciones, frozenset())
        self.emitir(self.gerente, reclamo)
        self.assertEqual(reclamos.ficha_de_reclamo(self.gerente, reclamo.pk).acciones, frozenset({"cerrar"}))
        self.cerrar(self.gerente, reclamo)
        self.assertEqual(reclamos.ficha_de_reclamo(self.gerente, reclamo.pk).acciones, frozenset())

    def test_regla_4_el_agronomo_solo_ve_los_reclamos_de_sus_invernaderos(self):
        """Alcance (como la ficha de la orden): Beto (Sur) no ve la ficha ni la lista de un reclamo de Norte; Ana sí; una cuenta sin rol de compras no ve nada; un reclamo que no existe es ``Http404``."""
        _, reclamo = self.recepcion_con_reclamo()
        self.assertEqual([f.reclamo.pk for f in reclamos.reclamos(self.ana)], [reclamo.pk])
        self.assertEqual(reclamos.reclamos(self.beto), [])
        with self.assertRaises(PermissionDenied):
            reclamos.ficha_de_reclamo(self.beto, reclamo.pk)
        for actor in (crear_vendedor(), crear_capataz(), self.contador, None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    reclamos.reclamos(actor)
                with self.assertRaises(PermissionDenied):
                    reclamos.ficha_de_reclamo(actor, reclamo.pk)
        with self.assertRaises(Http404):
            reclamos.ficha_de_reclamo(self.gerente, reclamo.pk + 9999)

    def test_regla_la_lista_se_filtra_por_estado_y_sale_del_mas_reciente_al_mas_antiguo(self):
        """El prototipo (``tabRcl``): «Sin emitir», «Emitidos abiertos» y «Cerrados»; sin filtro, todos del más reciente al más antiguo; un filtro desconocido se ignora."""
        _, primero = self.recepcion_con_reclamo()
        otra, linea, _ = self.otra_orden(self.ana, self.norte, cantidad=6, total="60.00", n=5)
        self.registrar(self.ana, [self.linea(linea, 6, inconvenientes=[(DANADA, 1, "")])], orden=otra, proveedor=linea.proveedor, invernadero=self.norte)
        segundo = ReclamoProveedor.objects.exclude(pk=primero.pk).get()
        self.emitir(self.gerente, primero)
        self.assertEqual([f.reclamo.pk for f in reclamos.reclamos(self.gerente)], [segundo.pk, primero.pk])
        self.assertEqual([f.reclamo.pk for f in reclamos.reclamos(self.gerente, {"estado": "sin_emitir"})], [segundo.pk])
        self.assertEqual([f.reclamo.pk for f in reclamos.reclamos(self.gerente, {"estado": "emitido_abierto"})], [primero.pk])
        self.assertEqual(reclamos.reclamos(self.gerente, {"estado": "cerrado"}), [])
        self.cerrar(self.gerente, primero)
        self.assertEqual([f.reclamo.pk for f in reclamos.reclamos(self.gerente, {"estado": "cerrado"})], [primero.pk])
        self.assertEqual(len(reclamos.reclamos(self.gerente, {"estado": "inventado"})), 2)
        fila = reclamos.reclamos(self.gerente)[1]
        self.assertEqual((fila.recepcion.pk, fila.orden.pk, fila.proveedor.pk, fila.invernadero.pk, len(fila.inconvenientes)), (primero.recepcion_id, self.orden.pk, self.proveedor.pk, self.norte.pk, 1))
