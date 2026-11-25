# Pruebas de ``pagos_pendientes`` y ``avisar_si_quedo_para_pagar`` de ``compras/servicios/pagos.py`` (CMP-05, paso 2). Fuente: docs/decisiones/D-91.md (puntos 2 y 3), D-89 punto 4 (el monto),
# D-85 (a quién se avisa), D-42 (la notificación va dentro de la transacción, no se audita), H21 (nunca se notifica a quien hizo la acción) y docs/casos_de_uso/compras/pagos.md
# («Reglas de negocio»: Pago diferido, Sin recepción sin pago, Monto, Aviso y bandeja).
#
# API que fijan estas pruebas (el módulo se toma dentro de cada prueba con ``perezoso``):
#   pagos_pendientes(*, proveedor=None, orden=None) -> list[PagoPendiente(orden, proveedor, cantidad_de_lineas, monto, listo_desde)]
#       La consulta única de D-91 punto 2 (bandeja, atajo de órdenes, baja del proveedor). Un par (orden, proveedor) sin ``Pago`` con todas sus líneas «completo» o «cerrado con faltante» y algo recibido.
#       ``monto`` es Σ ``valor_recibido(línea, recibido)`` (D-89); ``listo_desde`` es la mayor fecha entre la última recepción y el último cierre con faltante del par; del más antiguo al más reciente.
#   avisar_si_quedo_para_pagar(orden, proveedor, *, actor) -> Notificacion | None
#       Si el par quedó para pagar, avisa «Proveedor para pagar» al responsable contable (``excluir=actor``). La llaman, dentro de la transacción, ``registrar_recepcion`` y ``cerrar_con_faltante``.

from datetime import timedelta
from unittest import mock

from compras.models import DetalleOrdenCompra, Pago
from compras.tests.base_pagos import D, PagosBase, pagos
from compras.tests.base_recepciones import recepciones
from core.models import Notificacion, RegistroAuditoria


class PagosPendientesTests(PagosBase):
    """D-91 punto 2: cuándo un par (orden, proveedor) está pendiente de pago, cuánto se paga y desde cuándo espera."""

    def pares(self, **filtros):
        return [(p.orden.pk, p.proveedor.pk) for p in pagos.pagos_pendientes(**filtros)]

    def test_regla_pago_diferido_sin_nada_recibido_no_hay_pagos_pendientes(self):
        """Regla «Pago diferido»: se paga después de recibir. Una orden recién aprobada no deja nada para pagar."""
        self.assertEqual(pagos.pagos_pendientes(), [])

    def test_regla_pago_diferido_un_proveedor_con_todo_recibido_figura_con_su_monto(self):
        """D-91 punto 2: A, con sus dos líneas completas, figura con sus dos líneas y los $300,00 que suman sus totales (D-89); B, con su línea pendiente, no."""
        self.recibir_a()
        pendientes = pagos.pagos_pendientes()
        self.assertEqual([(p.orden.pk, p.proveedor.pk, p.cantidad_de_lineas, p.monto) for p in pendientes], [(self.orden.pk, self.proveedor.pk, 2, D("300.00"))])
        self.assertEqual(pendientes[0].listo_desde, self.hoy)

    def test_regla_pago_diferido_con_una_linea_pendiente_el_proveedor_todavia_no_figura(self):
        """Regla «Pago diferido»: «cuando todos sus detalles en la orden están completos o cerrados». Con la Maceta pendiente, A no figura."""
        self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence)])
        self.assertEqual(pagos.pagos_pendientes(), [])

    def test_regla_sin_recepcion_sin_pago_si_de_ninguna_linea_se_recibio_algo_no_figura(self):
        """Regla «Sin recepción, sin pago» (regla 13 de 8.20; H11): si todas las líneas de B se cierran con faltante sin haber recibido nada, B no figura. A, que sí recibió, figura."""
        with self.captureOnCommitCallbacks(execute=True):
            recepciones.cerrar_con_faltante(self.ana, [(self.l_tomate.pk, "No llega.")])
        self.recibir_a()
        self.assertEqual(self.pares(), [(self.orden.pk, self.proveedor.pk)])

    def test_regla_monto_con_una_recepcion_parcial_y_un_cierre_con_faltante_se_paga_lo_recibido(self):
        """Regla «Monto» (D-89 punto 4): del Fertilizante entraron 4 de 10 (4 × $10,00 = $40,00) y se cerró el resto; la Maceta entró entera ($200,00): el monto es $240,00."""
        self.recibir_a_con_faltante()
        pendiente = pagos.pagos_pendientes()[0]
        self.assertEqual((pendiente.proveedor.pk, pendiente.monto, pendiente.cantidad_de_lineas), (self.proveedor.pk, D("240.00"), 2))
        self.assertEqual(self.estado_de(self.l_fert), "cerrado_con_faltante")

    def test_regla_monto_una_linea_cerrada_sin_haber_recibido_nada_no_suma(self):
        """Regla «Monto»: una línea cerrada con faltante sin nada recibido vale cero; con la otra línea recibida entera, el proveedor figura por esa sola línea ($200,00)."""
        with self.captureOnCommitCallbacks(execute=True):
            recepciones.cerrar_con_faltante(self.ana, [(self.l_fert.pk, "No llega.")])
        self.registrar(self.ana, [self.linea(self.l_maceta, 20)])
        self.assertEqual([(p.proveedor.pk, p.monto) for p in pagos.pagos_pendientes()], [(self.proveedor.pk, D("200.00"))])

    def test_regla_pagado_un_par_con_pago_ya_no_figura_y_el_otro_proveedor_de_la_orden_sigue(self):
        """D-91 punto 2: «un par sin ``Pago``». Con A pagado, solo B figura (no es todo-o-nada por orden)."""
        self.recibir_a()
        self.recibir_b()
        self.assertEqual(sorted(self.pares()), sorted([(self.orden.pk, self.proveedor.pk), (self.orden.pk, self.proveedor_b.pk)]))
        self.pagar()
        self.assertEqual(self.pares(), [(self.orden.pk, self.proveedor_b.pk)])

    def test_regla_filtros_por_proveedor_y_por_orden(self):
        """D-91 punto 2: el mismo cálculo sirve a la baja del proveedor (``proveedor=``) y al atajo de la lista de órdenes (``orden=``)."""
        otra, otro_proveedor = self.otra_pagable(5)
        self.recibir_a()
        self.assertEqual(self.pares(proveedor=self.proveedor), [(self.orden.pk, self.proveedor.pk)])
        self.assertEqual(self.pares(proveedor=otro_proveedor), [(otra.pk, otro_proveedor.pk)])
        self.assertEqual(self.pares(orden=otra), [(otra.pk, otro_proveedor.pk)])
        self.assertEqual(self.pares(orden=self.orden, proveedor=self.proveedor_b), [])

    def test_regla_orden_de_la_bandeja_del_mas_antiguo_al_mas_reciente(self):
        """Paso 2 y D-91 punto 2: ordenados por la fecha en que quedó todo completo o cerrado. A (recibido hace 5 días) va antes que B (hace 2), aunque B se recibió primero."""
        self.recibir_b()
        self.fechar_recepciones(2)
        self.recibir_a()
        from compras.models import Recepcion

        Recepcion.objects.filter(proveedor=self.proveedor).update(fecha_recepcion=self.hoy - timedelta(days=5))
        pendientes = pagos.pagos_pendientes()
        self.assertEqual([p.proveedor.pk for p in pendientes], [self.proveedor.pk, self.proveedor_b.pk])
        self.assertEqual([p.listo_desde for p in pendientes], [self.hoy - timedelta(days=5), self.hoy - timedelta(days=2)])

    def test_regla_listo_desde_es_la_mayor_entre_la_ultima_recepcion_y_el_ultimo_cierre_con_faltante(self):
        """D-91 punto 2: «la mayor entre la última recepción y el último cierre con faltante». El Fertilizante se cerró hace 20 días y la última recepción (la Maceta) fue hace 3: listo desde hace 3 días;
        y con el cierre hace 1 día, hace 1 día."""
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        with self.captureOnCommitCallbacks(execute=True):
            recepciones.cerrar_con_faltante(self.ana, [(self.l_fert.pk, "No repone.")])
        self.registrar(self.ana, [self.linea(self.l_maceta, 20)])
        self.fechar_recepciones(3)
        DetalleOrdenCompra.objects.filter(pk=self.l_fert.pk).update(fecha_cierre_faltante=self.hoy - timedelta(days=20))
        self.assertEqual(pagos.pagos_pendientes()[0].listo_desde, self.hoy - timedelta(days=3))
        DetalleOrdenCompra.objects.filter(pk=self.l_fert.pk).update(fecha_cierre_faltante=self.hoy - timedelta(days=1))
        self.assertEqual(pagos.pagos_pendientes()[0].listo_desde, self.hoy - timedelta(days=1))

    def test_regla_la_consulta_no_hace_una_consulta_por_fila(self):
        """Una consulta por tabla, no una por fila: con tres pares la cantidad de consultas es la misma que con uno."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.recibir_a()
        with CaptureQueriesContext(connection) as con_un_par:
            self.assertEqual(len(pagos.pagos_pendientes()), 1)
        self.recibir_b()
        self.otra_pagable(5)
        with CaptureQueriesContext(connection) as con_tres:
            self.assertEqual(len(pagos.pagos_pendientes()), 3)
        self.assertEqual(len(con_tres), len(con_un_par))


class AvisoParaPagarTests(PagosBase):
    """D-91 punto 3 y H23 punto 2: el aviso «Proveedor para pagar» cuando todos los detalles del proveedor quedan completos o cerrados (con algo recibido)."""

    def test_regla_aviso_al_quedar_el_proveedor_listo_lo_recibe_el_contador(self):
        """Regla «Aviso y bandeja»: la recepción que deja a A listo avisa al Contador, con el proveedor, la orden y el monto a pagar; el Gerente no recibe nada (hay Contador activo)."""
        self.recibir_a()
        avisos = self.avisos_de_pago(self.contador)
        self.assertEqual(len(avisos), 1)
        for texto in (self.proveedor.nombre_para_mostrar, str(self.orden), "300.00"):
            self.assertIn(texto, avisos[0].detalle)
        self.assertEqual(self.avisos_de_pago(self.gerente), [])

    def test_regla_aviso_sin_contador_activo_lo_recibe_el_gerente(self):
        """D-85 puntos 4 y 5: sin Contador activo, el responsable es el Gerente, y la recepción la registra Ana, no él."""
        self.sin_contador()
        self.recibir_a()
        self.assertEqual(len(self.avisos_de_pago(self.gerente)), 1)

    def test_regla_aviso_h21_nunca_se_notifica_a_quien_hizo_la_accion(self):
        """H21 y regla «Aviso y bandeja»: si el Gerente registra la recepción y él sería quien recibe el aviso (no hay Contador activo), no se la envía (el pago igual figura en la bandeja)."""
        self.sin_contador()
        self.recibir_a(actor=self.gerente)
        self.assertEqual(Notificacion.objects.filter(titulo="Proveedor para pagar").count(), 0)
        self.assertEqual(len(pagos.pagos_pendientes()), 1)

    def test_regla_aviso_la_recepcion_del_gerente_con_contador_activo_si_avisa_al_contador(self):
        """H21: ``excluir`` es el actor y no el Gerente: si el Gerente registra la recepción con un Contador activo, el Contador sí recibe el aviso."""
        self.recibir_a(actor=self.gerente)
        self.assertEqual(len(self.avisos_de_pago(self.contador)), 1)

    def test_regla_aviso_no_sale_mientras_al_proveedor_le_quedan_lineas_pendientes(self):
        """D-91 punto 3: solo si el par pasó a «listo». Con la Maceta pendiente no hay aviso; sale una sola vez, con la recepción que la completa."""
        self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence)])
        self.assertEqual(self.avisos_de_pago(self.contador), [])
        self.registrar(self.ana, [self.linea(self.l_maceta, 20)])
        self.assertEqual(len(self.avisos_de_pago(self.contador)), 1)

    def test_regla_aviso_sale_una_vez_por_proveedor_y_la_recepcion_del_otro_no_repite_el_de_a(self):
        """Regla «Aviso y bandeja»: un aviso por cada proveedor que queda listo; la recepción de B no vuelve a avisar por A."""
        self.recibir_a()
        self.recibir_b()
        avisos = self.avisos_de_pago(self.contador)
        self.assertEqual(len(avisos), 2)
        self.assertIn(self.proveedor.nombre_para_mostrar, avisos[0].detalle)
        self.assertIn(self.proveedor_b.nombre_para_mostrar, avisos[1].detalle)

    def test_regla_aviso_una_recepcion_parcial_con_lo_demas_pendiente_no_avisa(self):
        """Una recepción que no completa nada de A (4 de 10 del Fertilizante) no deja a A listo: no avisa."""
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        self.assertEqual(self.avisos_de_pago(self.contador), [])

    def test_regla_aviso_el_cierre_con_faltante_que_deja_listo_al_proveedor_avisa(self):
        """D-91 punto 3 (CMP-CRR-FLT): recibido todo el Fertilizante, cerrar con faltante la Maceta deja a A listo por $100,00: avisa al Contador."""
        self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence)])
        self.assertEqual(self.avisos_de_pago(self.contador), [])
        with self.captureOnCommitCallbacks(execute=True):
            recepciones.cerrar_con_faltante(self.ana, [(self.l_maceta.pk, "No repone.")])
        avisos = self.avisos_de_pago(self.contador)
        self.assertEqual(len(avisos), 1)
        self.assertIn("100.00", avisos[0].detalle)

    def test_regla_aviso_el_cierre_de_un_proveedor_sin_nada_recibido_no_avisa(self):
        """«Sin recepción, sin pago»: cerrar con faltante la única línea de B sin haber recibido nada no lo deja para pagar: sin aviso."""
        with self.captureOnCommitCallbacks(execute=True):
            recepciones.cerrar_con_faltante(self.ana, [(self.l_tomate.pk, "No llega.")])
        self.assertEqual(Notificacion.objects.filter(titulo="Proveedor para pagar").count(), 0)

    def test_regla_aviso_un_cierre_de_varios_proveedores_avisa_por_cada_uno_que_quedo_listo(self):
        """Un cierre puede dejar listos a dos proveedores a la vez (A con su Fertilizante recibido y Maceta cerrada; B con su Tomate recibido a medias y cerrado): un aviso por cada uno."""
        self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence)])
        self.registrar(self.ana, [self.linea(self.l_tomate, 3)], proveedor=self.proveedor_b, invernadero=self.norte2)
        with self.captureOnCommitCallbacks(execute=True):
            recepciones.cerrar_con_faltante(self.ana, [(self.l_maceta.pk, "No repone."), (self.l_tomate.pk, "No repone.")])
        self.assertEqual(len(self.avisos_de_pago(self.contador)), 2)

    def test_regla_aviso_el_cierre_que_hace_el_gerente_sin_contador_no_le_avisa_a_el(self):
        """H21 en el cierre: sin Contador activo y cerrando el Gerente, el responsable es el actor: no se le avisa."""
        self.sin_contador()
        self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence)])
        with self.captureOnCommitCallbacks(execute=True):
            recepciones.cerrar_con_faltante(self.gerente, [(self.l_maceta.pk, "No repone.")])
        self.assertEqual(Notificacion.objects.filter(titulo="Proveedor para pagar").count(), 0)

    def test_regla_aviso_sin_responsable_contable_no_falla_y_no_avisa(self):
        """D-14 y D-85: sin Contador ni Gerente activos no hay a quién avisar y la recepción se registra igual."""
        self.sin_contador()
        self.gerente.__class__.objects.filter(pk=self.gerente.pk).update(is_active=False)
        self.recibir_a()
        self.assertEqual(Notificacion.objects.filter(titulo="Proveedor para pagar").count(), 0)
        self.assertEqual(len(pagos.pagos_pendientes()), 1)

    def test_regla_aviso_directo_devuelve_la_notificacion_o_none(self):
        """``avisar_si_quedo_para_pagar``: con el par listo devuelve la notificación creada; con el par que todavía no está listo, ``None`` y no crea nada."""
        self.recibir_a()
        self.assertIsNone(pagos.avisar_si_quedo_para_pagar(self.orden, self.proveedor_b, actor=self.ana))
        aviso = pagos.avisar_si_quedo_para_pagar(self.orden, self.proveedor, actor=self.ana)
        self.assertEqual((aviso.destinatario_id, aviso.titulo), (self.contador.pk, "Proveedor para pagar"))

    def test_regla_aviso_un_par_ya_pagado_no_se_avisa(self):
        """D-91 punto 2: lo pendiente es lo que no tiene ``Pago``; si ya está pagado, el aviso directo no sale."""
        self.recibir_a()
        self.pagar()
        antes = Notificacion.objects.count()
        self.assertIsNone(pagos.avisar_si_quedo_para_pagar(self.orden, self.proveedor, actor=self.ana))
        self.assertEqual(Notificacion.objects.count(), antes)

    def test_d42_el_aviso_va_dentro_de_la_transaccion_si_la_recepcion_falla_no_queda_aviso(self):
        """D-42 y regla 1 de docs/api/notificaciones.md: la notificación se crea dentro del ``atomic()``. Si falla la auditoría de la recepción (lo último que se escribe), no queda ninguna."""
        real = RegistroAuditoria.objects.registrar

        def falla_la_de_la_recepcion(*args, **kwargs):
            accion = kwargs.get("accion", args[1] if len(args) > 1 else None)
            if accion == RegistroAuditoria.Accion.RECEPCION_MERCADERIA:
                raise RuntimeError("falla de la auditoría")
            return real(*args, **kwargs)

        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=falla_la_de_la_recepcion):
            with self.assertRaises(RuntimeError):
                self.recibir_a()
        self.assertEqual(Notificacion.objects.filter(titulo="Proveedor para pagar").count(), 0)
        self.assertEqual(Pago.objects.count(), 0)

    def test_d42_el_aviso_no_se_audita_ni_cambia_la_auditoria_de_la_recepcion(self):
        """D-42: las notificaciones no se auditan: la recepción deja el mismo único registro de siempre (más el del asiento y sus movimientos), sin uno por el aviso."""
        self.recibir_a()
        acciones = list(RegistroAuditoria.objects.values_list("accion", flat=True))
        self.assertEqual(acciones.count(RegistroAuditoria.Accion.RECEPCION_MERCADERIA), 1)
        self.assertEqual(Notificacion.objects.filter(titulo="Proveedor para pagar").count(), 1)
        self.assertNotIn("notificacion", " ".join(acciones))


