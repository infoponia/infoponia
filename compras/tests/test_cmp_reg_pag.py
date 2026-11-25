# Pruebas de CMP-REG-PAG · Registrar Pago a Proveedor (CMP-05, paso 3): ``detalle_del_pago``, ``resumir_pago`` y ``registrar_pago`` de ``compras/servicios/pagos.py``, y la precondición d de
# CMP-BAJ-PRV (``proveedores.impedimentos_de_baja``). Fuente: docs/casos_de_uso/compras/pagos.md (CMP-REG-PAG v0.1: precondiciones a a c, garantías mínimas, postcondiciones a a e, flujo básico,
# extensiones *a, *b, 1a, 2a, 5a, 5b, 8a, 8b y 9a, y las reglas «Quién registra», «Pago diferido», «Sin recepción, sin pago», «Monto», «Medio de pago», «Asiento», «Fecha», «Sin anulación»,
# «Aviso y bandeja» y «Baja del proveedor»), «Cómo se aplica (código)», D-91, D-89 punto 4, D-85, D-86, D-102 y docs/casos_de_uso/compras/proveedores.md (CMP-BAJ-PRV precondición d).
#
# API que fijan estas pruebas (el módulo se toma dentro de cada prueba con ``perezoso``):
#   detalle_del_pago(actor, orden_id, proveedor_id) -> DetalleDelPago(orden, proveedor, lineas, monto, recepciones, listo_desde)      paso 4; solo lectura
#       lineas: list[LineaDePago(detalle, insumo, pedida, recibida, total, unitario, a_pagar, estado, motivo_cierre, no_aceptada)]: ``unitario`` es el derivado con dos decimales (D-89 punto 7),
#       ``a_pagar`` es ``valor_recibido`` y ``no_aceptada`` suma lo declarado como inconveniente que no es «otro»; recepciones: las ``Recepcion`` del proveedor en la orden
#   resumir_pago(actor, orden_id, proveedor_id, medio, fecha, *, hoy=None) -> ResumenDePago(detalle, medio, fecha, movimientos, ejercicio)    paso 6; solo lectura
#       movimientos: [(código de cuenta, "D" | "H", importe)]; ``ejercicio`` es donde caerá el asiento (``ejercicio_para(fecha, automatico=False)``)
#   registrar_pago(actor, orden_id, proveedor_id, medio, fecha, *, hoy=None) -> Pago      paso 8; atómico. ``fecha=None`` es hoy. No recibe el monto: lo calcula (regla «Monto»)
# Quién: ``responsables.puede_registrar_asientos`` (``PermissionDenied``; con un Contador activo el Gerente recibe «Lo registra el Contador»). Errores de negocio (``ErrorDeCompras``):
# ``sin_pago_pendiente`` (2a/b: nada recibido o con líneas pendientes), ``proveedor_ajeno`` (no es de la orden), ``pago_ya_registrado`` (8a; ``datos["pago_id"]``), ``medio_obligatorio`` (5a) y
# ``medio_invalido`` (``campo="medio_pago"``). La fecha (5b) la valida ``ejercicio_para(fecha, automatico=False)``: ``ErrorContable`` ``fecha_futura``, ``fecha_en_ejercicio_cerrado`` y
# ``fecha_anterior_al_primer_ejercicio`` (``campo="fecha"``). Un ``Http404`` si la orden no existe. El correo al proveedor sale en ``on_commit``.

import inspect
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import override_settings

from compras.errores import ErrorDeCompras
from compras.models import DetalleOrdenCompra, DetalleRecepcion, Pago, Recepcion
from compras.tests.base_pagos import D, PagosBase, pagos
from compras.tests.base_recepciones import recepciones
from compras.tests.fabricas import proveedor as crear_proveedor
from compras.tests.fabricas import ref
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, CuentaContable, EjercicioContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.tests.fabricas import ejercicio, verificar_invariantes_contables
from core.models import Contador, RegistroAuditoria
from core.tests.fabricas import BACKEND_QUE_FALLA, crear_administrador, crear_capataz, crear_cuenta, crear_gerente
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from maestros.tests.fabricas import crear_agronomo, crear_vendedor

Estado = EjercicioContable.Estado
DANADA = "mercaderia_danada"


def registro_del_pago():
    """El registro de auditoría del pago (la acción se resuelve acá para que un nombre mal escrito falle en la prueba y no al importar)."""
    return RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.REGISTRO_PAGO_PROVEEDOR)


class CmpRegPagPostcondicionesTests(PagosBase):
    """Postcondiciones a a e y el flujo básico: el Contador paga a A por lo recibido."""

    def test_flujo_principal_el_contador_registra_el_pago_de_lo_recibido(self):
        """Flujo básico, pasos 7 a 10: el Contador confirma y el Sistema crea el pago con el monto calculado, su asiento y su auditoría."""
        self.recibir_a()
        pago = self.pagar(medio="transferencia")
        self.assertEqual((pago.orden_id, pago.proveedor_id, pago.monto_pago, pago.medio_pago, pago.fecha_pago), (self.orden.pk, self.proveedor.pk, D("300.00"), "transferencia", self.hoy))
        self.assertTrue(self.asiento_del_pago(pago))
        verificar_invariantes_contables()

    def test_post_a_el_pago_queda_asociado_a_la_orden_y_al_proveedor_con_la_fecha_el_medio_y_el_monto(self):
        """Postcondición a: un pago de la orden y del proveedor, con la fecha indicada, el medio indicado y el monto calculado (es un ``OrigenDocumento`` de tipo ``pago``)."""
        self.recibir_a()
        fecha = self.hoy
        pago = self.pagar(medio="tarjeta_debito", fecha=fecha)
        guardado = Pago.objects.get(pk=pago.pk)
        self.assertEqual((guardado.orden, guardado.proveedor, guardado.fecha_pago, guardado.medio_pago, guardado.tipo), (self.orden, self.proveedor, fecha, "tarjeta_debito", "pago"))

    def test_post_a_el_monto_por_linea_es_el_total_si_se_recibio_todo(self):
        """Postcondición a, primer caso: todo recibido, la suma de los totales de las líneas ($100,00 + $200,00)."""
        self.recibir_a()
        self.assertEqual(self.pagar().monto_pago, D("300.00"))

    def test_post_a_el_monto_por_linea_es_lo_recibido_por_el_unitario_si_se_recibio_una_parte_o_se_cerro_con_faltante(self):
        """Postcondición a, segundo y tercer caso: 4 de 10 del Fertilizante cerrado con faltante (4 × $10,00 = $40,00) más la Maceta entera ($200,00)."""
        self.recibir_a_con_faltante()
        self.assertEqual(self.pagar().monto_pago, D("240.00"))

    def test_regla_monto_no_lo_escribe_el_actor_el_servicio_no_recibe_un_monto(self):
        """Regla «Monto»: «no es editable»: ``registrar_pago`` y ``resumir_pago`` no tienen un parámetro de monto."""
        for funcion in (pagos.registrar_pago, pagos.resumir_pago):
            self.assertNotIn("monto", inspect.signature(funcion).parameters)

    def test_post_b_el_asiento_es_debe_proveedores_haber_banco_para_los_medios_que_no_son_efectivo(self):
        """Postcondición b y regla «Medio de pago» (regla 15 de 8.13): transferencia, tarjeta de débito y tarjeta de crédito van a Banco c/c; el asiento es de la fecha del pago, por el monto y su origen es el pago."""
        for n, medio in enumerate(("transferencia", "tarjeta_debito", "tarjeta_credito"), start=5):
            with self.subTest(medio=medio):
                orden, proveedor = self.otra_pagable(n, total="60.00")
                pago = self.pagar(medio=medio, orden=orden, proveedor=proveedor)
                asiento = self.asiento_del_pago(pago)
                self.assertEqual(self.movimientos_de(asiento), [(cuentas.PROVEEDORES, DEBE, D("60.00")), (cuentas.BANCO, HABER, D("60.00"))])
                self.assertEqual((asiento.origen_id, asiento.fecha_asiento, asiento.ejercicio_id), (pago.pk, self.hoy, self.abierto.pk))

    def test_post_b_el_efectivo_sale_de_caja(self):
        """Postcondición b y regla «Medio de pago»: el efectivo se imputa a Caja."""
        self.recibir_a()
        asiento = self.asiento_del_pago(self.pagar(medio="efectivo"))
        self.assertEqual(self.movimientos_de(asiento), [(cuentas.PROVEEDORES, DEBE, D("300.00")), (cuentas.CAJA, HABER, D("300.00"))])

    def test_post_b_el_asiento_lleva_la_fecha_elegida_del_pago(self):
        """Regla «Fecha» y D-91 punto 4: la fecha se pasa tal cual al asiento: un pago de hace 3 días queda asentado hace 3 días si cae en un ejercicio que lo admite (acá, uno «en cierre»)."""
        en_cierre = ejercicio(Estado.EN_CIERRE, self.hoy - timedelta(days=365), self.hoy - timedelta(days=1))
        self.recibir_a()
        fecha = self.hoy - timedelta(days=3)
        asiento = self.asiento_del_pago(self.pagar(fecha=fecha))
        self.assertEqual((asiento.fecha_asiento, asiento.ejercicio_id, asiento.numero_asiento), (fecha, en_cierre.pk, 1))
        verificar_invariantes_contables()

    def test_post_b_la_cuenta_proveedores_de_la_orden_y_el_proveedor_queda_en_cero(self):
        """«Hecho cuando» y D-89 punto 4: después de la recepción (Haber Proveedores $300,00) y del pago (Debe Proveedores $300,00) la cuenta queda en cero."""
        self.recibir_a()
        self.pagar()
        from contabilidad.servicios import libro

        saldo = libro.saldo_por_cuenta(self.abierto.pk)[cuentas.PROVEEDORES]
        self.assertEqual((saldo.debe, saldo.haber, saldo.saldo), (D("300.00"), D("300.00"), D("0.00")))

    def test_post_c_el_proveedor_deja_de_figurar_en_la_bandeja_y_el_aviso_queda_como_historia(self):
        """Postcondición c y D-91 punto 3: la bandeja se calcula, así que el par desaparece; la notificación no tiene estado «resuelta» (D-42) y queda como historia."""
        self.recibir_a()
        avisos = self.avisos_de_pago(self.contador)
        self.pagar()
        self.assertEqual(pagos.pagos_pendientes(), [])
        self.assertEqual(self.avisos_de_pago(self.contador), avisos)

    def test_post_d_el_proveedor_recibe_un_correo_con_el_monto_el_medio_la_fecha_y_la_orden(self):
        """Postcondición d: un correo al proveedor (y solo a él) con el monto, el medio de pago, la fecha y la orden."""
        self.recibir_a()
        antes = len(mail.outbox)
        fecha = self.hoy
        self.pagar(medio="transferencia", fecha=fecha)
        nuevos = mail.outbox[antes:]
        self.assertEqual(len(nuevos), 1)
        correo = nuevos[0]
        self.assertEqual(correo.to, ["ventas@sur.com"])
        self.assertIn(str(self.orden), correo.subject)
        for texto in ("300.00", "Transferencia", str(self.orden), f"{fecha:%d/%m/%Y}", self.proveedor.nombre_para_mostrar):
            self.assertIn(texto, correo.body)
        self.assertNotIn(self.proveedor_b.nombre_para_mostrar, correo.body)

    @override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA)
    def test_ext_9a_si_el_correo_no_sale_el_pago_queda_registrado(self):
        """Extensión 9a: si no se logra enviar el correo, el pago permanece registrado (el correo sale fuera de la transacción)."""
        self.recibir_a()
        pago = self.pagar()
        self.assertTrue(Pago.objects.filter(pk=pago.pk).exists())
        self.assertTrue(AsientoContable.objects.filter(origen_id=pago.pk).exists())

    @override_settings(CORREO_CONFIGURADO=False)
    def test_ext_9a_sin_el_correo_configurado_no_sale_nada_y_el_pago_se_registra(self):
        """D-33: sin el correo configurado no sale ningún correo y el pago se registra igual."""
        self.recibir_a()
        antes = len(mail.outbox)
        self.pagar()
        self.assertEqual(len(mail.outbox), antes)
        self.assertEqual(Pago.objects.count(), 1)

    def test_post_e_se_audita_el_pago_con_el_actor_los_afectados_y_el_asiento(self):
        """Postcondición e y D-36: un solo registro ``registro_pago_proveedor`` con quien pagó, el pago, la orden y el proveedor como afectados y, en ``datos``, el asiento, el medio, la fecha y el monto.
        El asiento y sus movimientos los audita la función de asientos (D-86 punto 4): acá no se repiten."""
        self.recibir_a()
        antes = RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ALTA_ASIENTO_CONTABLE).count()
        pago = self.pagar(medio="efectivo")
        registro = registro_del_pago()
        self.assertEqual(registro.usuario_id, self.contador.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        self.assertLessEqual({("compras.pago", pago.pk), ("compras.ordencompra", self.orden.pk), ("compras.proveedor", self.proveedor.pk)}, afectados)
        datos = registro.detalle["datos"]
        self.assertEqual(datos["asiento"], ref(self.asiento_del_pago(pago)))
        self.assertEqual((datos["medio_pago"], datos["fecha_pago"], datos["monto_pago"]), ("efectivo", self.hoy.isoformat(), "300.00"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ALTA_ASIENTO_CONTABLE).count(), antes + 1)

    def test_regla_pago_no_modifica_el_stock_las_recepciones_ni_los_estados(self):
        """Garantías mínimas, «Además»: este caso de uso no modifica el stock, las recepciones, los reclamos ni los estados de la orden o de sus detalles."""
        self.recibir_a()
        self.recibir_b()

        def foto():
            return (
                self.stock_de(self.fertilizante),
                self.transito(self.fertilizante),
                tuple(DetalleOrdenCompra.objects.order_by("id").values_list("estado_detalle_orden", flat=True)),
                self.estado_de_la_orden(),
                Recepcion.objects.count(),
                DetalleRecepcion.objects.count(),
                LoteInsumo.objects.count(),
                MovimientoInsumo.objects.count(),
                tuple(InsumoInvernadero.objects.order_by("id").values_list("cant_transito_insumo", flat=True)),
            )

        antes = foto()
        self.pagar()
        self.assertEqual(foto(), antes)

    def test_regla_el_pago_se_muestra_como_pag_y_se_audita_con_ese_texto(self):
        """D-36: el texto del pago en la auditoría es «PAG-0001»."""
        self.recibir_a()
        pago = self.pagar()
        textos = {(a["modelo"], a["id"]): a["texto"] for a in registro_del_pago().afectados}
        self.assertEqual(textos[("compras.pago", pago.pk)], f"PAG-{pago.pk:04d}")


class CmpRegPagPermisosTests(PagosBase):
    """Precondición a y extensión 1a: quién registra (D-85 punto 5)."""

    def test_pre_a_el_contador_activo_registra(self):
        self.recibir_a()
        self.assertEqual(self.pagar(actor=self.contador).proveedor_id, self.proveedor.pk)

    def test_ext_1a_sin_contador_activo_el_gerente_registra_y_queda_como_autor_en_la_auditoria(self):
        """Extensión 1a: con el Contador dado de baja, el Gerente hace el pago y queda como autor en el log (1a.2)."""
        self.recibir_a()
        self.sin_contador()
        self.pagar(actor=self.gerente)
        self.assertEqual(registro_del_pago().usuario_id, self.gerente.pk)

    def test_ext_1a_con_contador_activo_el_gerente_no_registra(self):
        """Extensión 1a.3: si hay un Contador activo el Sistema no permite el registro al Gerente: «Lo registra el Contador». No queda nada."""
        self.recibir_a()
        antes = self.instantanea_de_pagos()
        with self.assertRaises(PermissionDenied) as contexto:
            self.pagar(actor=self.gerente)
        self.assertIn("Lo registra el Contador", str(contexto.exception))
        self.sin_cambios_de_pagos(antes)

    def test_pre_a_nadie_mas_registra_pagos(self):
        """Precondición a: ni el Agrónomo, el Vendedor, el Capataz o el Administrador, ni un Contador dado de baja, ni un Gerente inactivo, ni nadie (``None``)."""
        self.recibir_a()
        antes = self.instantanea_de_pagos()
        inactivo = crear_cuenta(Contador, email="viejo@infoponia.com", activo=False)
        self.sin_contador()
        gerente_inactivo = crear_gerente(email="otro.gerente@infoponia.com", activo=False)
        for actor in (self.ana, crear_agronomo(), crear_vendedor(), crear_capataz(), crear_administrador(), inactivo, gerente_inactivo, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                pagos.registrar_pago(actor, self.orden.pk, self.proveedor.pk, "efectivo", self.hoy)
        self.sin_cambios_de_pagos(antes)

    def test_pre_a_ni_el_detalle_ni_el_resumen_se_muestran_a_quien_no_puede_registrar(self):
        """Los pasos 4 y 6 son del responsable contable: el Gerente con un Contador activo y el Agrónomo reciben ``PermissionDenied``."""
        self.recibir_a()
        for actor in (self.gerente, self.ana):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    pagos.detalle_del_pago(actor, self.orden.pk, self.proveedor.pk)
                with self.assertRaises(PermissionDenied):
                    pagos.resumir_pago(actor, self.orden.pk, self.proveedor.pk, "efectivo", self.hoy)

    def test_pre_a_el_gerente_sin_contador_ve_el_detalle_y_el_resumen(self):
        """Extensión 1a.1: el caso de uso sigue con el Gerente como actor."""
        self.recibir_a()
        self.sin_contador()
        self.assertEqual(pagos.detalle_del_pago(self.gerente, self.orden.pk, self.proveedor.pk).monto, D("300.00"))
        self.assertEqual(pagos.resumir_pago(self.gerente, self.orden.pk, self.proveedor.pk, "efectivo", self.hoy).medio, "efectivo")


class CmpRegPagPrecondicionesTests(PagosBase):
    """Precondición b, extensiones 2a y 8a, y reglas «Pago diferido» y «Sin recepción, sin pago»."""

    def test_pre_b_con_lineas_pendientes_no_hay_pago_que_registrar(self):
        """Precondición b y regla «Pago diferido»: B tiene su línea pendiente: ``sin_pago_pendiente``. No queda nada."""
        self.recibir_a()
        antes = self.instantanea_de_pagos()
        self.assertEqual(self.error_de_pago(proveedor=self.proveedor_b).codigo, "sin_pago_pendiente")
        self.sin_cambios_de_pagos(antes)

    def test_pre_b_con_una_sola_linea_pendiente_de_las_dos_tampoco(self):
        """Regla «Pago diferido»: «todos sus detalles» completos o cerrados; con la Maceta pendiente A no se paga."""
        self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence)])
        self.assertEqual(self.error_de_pago().codigo, "sin_pago_pendiente")

    def test_regla_sin_recepcion_sin_pago_si_de_ninguna_linea_se_recibio_algo_no_hay_pago_ni_asiento(self):
        """Regla «Sin recepción, sin pago» (regla 13 de 8.20; H11): todas las líneas de B cerradas con faltante sin nada recibido: no hay pago ni asiento."""
        with self.captureOnCommitCallbacks(execute=True):
            recepciones.cerrar_con_faltante(self.ana, [(self.l_tomate.pk, "No llega.")])
        antes = self.instantanea_de_pagos()
        self.assertEqual(self.error_de_pago(proveedor=self.proveedor_b).codigo, "sin_pago_pendiente")
        self.sin_cambios_de_pagos(antes)

    def test_ext_8a_un_segundo_pago_del_mismo_par_se_rechaza_y_dice_cual_es(self):
        """Extensión 8a y «Hecho cuando» («un segundo pago se rechaza»): ``pago_ya_registrado`` con el id del pago existente; no se registra ningún cambio."""
        self.recibir_a()
        primero = self.pagar()
        antes = self.instantanea_de_pagos()
        error = self.error_de_pago(medio="efectivo")
        self.assertEqual((error.codigo, error.datos["pago_id"]), ("pago_ya_registrado", primero.pk))
        self.sin_cambios_de_pagos(antes)

    def test_ext_8a_el_detalle_de_un_par_ya_pagado_informa_el_pago(self):
        """Extensión 8a: quien abre el detalle de un par ya pagado (otro usuario lo registró) recibe el mismo ``pago_ya_registrado``."""
        self.recibir_a()
        pago = self.pagar()
        with self.assertRaises(ErrorDeCompras) as contexto:
            pagos.detalle_del_pago(self.contador, self.orden.pk, self.proveedor.pk)
        self.assertEqual((contexto.exception.codigo, contexto.exception.datos["pago_id"]), ("pago_ya_registrado", pago.pk))

    def test_regla_pago_diferido_el_otro_proveedor_de_la_orden_se_paga_aparte(self):
        """R158: un pago por proveedor y por orden. Pagar a A no impide pagar a B de la misma orden."""
        self.recibir_a()
        self.recibir_b()
        self.pagar()
        self.assertEqual(self.pagar(proveedor=self.proveedor_b, medio="efectivo").monto_pago, D("80.00"))
        self.assertEqual(self.orden.pagos.count(), 2)
        verificar_invariantes_contables()

    def test_regla_un_proveedor_que_no_es_de_la_orden_no_se_paga(self):
        """El proveedor es uno de los de la orden (modelo, «Pago»): otro proveedor recibe ``proveedor_ajeno``."""
        self.recibir_a()
        ajeno = crear_proveedor("Ajeno S. A.", n=9)
        self.assertEqual(self.error_de_pago(proveedor=ajeno).codigo, "proveedor_ajeno")

    def test_regla_una_orden_que_no_existe_da_404(self):
        with self.assertRaises(Http404):
            pagos.registrar_pago(self.contador, 999999, self.proveedor.pk, "efectivo", self.hoy)
        with self.assertRaises(Http404):
            pagos.detalle_del_pago(self.contador, 999999, self.proveedor.pk)


class CmpRegPagMedioYFechaTests(PagosBase):
    """Extensiones 5a (medio obligatorio, sin preselección) y 5b (fecha), y la extensión 8b (ejercicio o cuentas)."""

    def setUp(self):
        super().setUp()
        self.recibir_a()
        self.antes = self.instantanea_de_pagos()

    def test_ext_5a_el_medio_es_obligatorio_y_no_se_preselecciona_ninguno(self):
        """Extensión 5a (H23): sin medio, ``medio_obligatorio`` en el campo ``medio_pago``; no se registra nada. Vale para el resumen y para el registro."""
        for medio in ("", None):
            with self.subTest(medio=medio):
                error = self.error_de_pago(medio=medio)
                self.assertEqual((error.codigo, error.campo), ("medio_obligatorio", "medio_pago"))
                with self.assertRaises(ErrorDeCompras) as contexto:
                    pagos.resumir_pago(self.contador, self.orden.pk, self.proveedor.pk, medio, self.hoy)
                self.assertEqual(contexto.exception.codigo, "medio_obligatorio")
        self.sin_cambios_de_pagos(self.antes)

    def test_ext_5a_un_medio_que_no_es_de_la_lista_se_rechaza(self):
        """Regla «Medio de pago»: solo efectivo, transferencia, tarjeta de débito o tarjeta de crédito (un valor armado a mano: ``medio_invalido``)."""
        error = self.error_de_pago(medio="cheque")
        self.assertEqual((error.codigo, error.campo), ("medio_invalido", "medio_pago"))
        self.sin_cambios_de_pagos(self.antes)

    def test_ext_5b_una_fecha_posterior_a_hoy_se_rechaza(self):
        """Extensión 5b y D-91 punto 4: una fecha futura es ``fecha_futura`` (campo ``fecha``), también en el resumen. No se registra nada."""
        manana = self.hoy + timedelta(days=1)
        error = self.error_de_pago(fecha=manana, clase=ErrorContable)
        self.assertEqual((error.codigo, error.campo), ("fecha_futura", "fecha"))
        with self.assertRaises(ErrorContable):
            pagos.resumir_pago(self.contador, self.orden.pk, self.proveedor.pk, "efectivo", manana)
        self.sin_cambios_de_pagos(self.antes)

    def test_ext_5b_una_fecha_anterior_al_primer_ejercicio_se_rechaza(self):
        """Extensión 5b: el primer ejercicio empieza hoy; un pago de ayer no cae en ninguno: ``fecha_anterior_al_primer_ejercicio``."""
        error = self.error_de_pago(fecha=self.hoy - timedelta(days=1), clase=ErrorContable)
        self.assertEqual(error.codigo, "fecha_anterior_al_primer_ejercicio")
        self.sin_cambios_de_pagos(self.antes)

    def test_ext_5b_una_fecha_de_un_ejercicio_cerrado_se_rechaza(self):
        """Extensión 5b y D-91 punto 4 («rechaza fecha futura y ejercicio cerrado, como un asiento manual»): ``fecha_en_ejercicio_cerrado``."""
        ejercicio(Estado.CERRADO, self.hoy - timedelta(days=730), self.hoy - timedelta(days=366))
        error = self.error_de_pago(fecha=self.hoy - timedelta(days=400), clase=ErrorContable)
        self.assertEqual(error.codigo, "fecha_en_ejercicio_cerrado")
        self.sin_cambios_de_pagos(self.antes)

    def test_ext_5b_una_fecha_en_un_ejercicio_en_cierre_se_acepta(self):
        """Regla «Fecha»: «debe caer en un ejercicio abierto o en cierre»."""
        ejercicio(Estado.EN_CIERRE, self.hoy - timedelta(days=365), self.hoy - timedelta(days=1))
        self.assertEqual(self.pagar(fecha=self.hoy - timedelta(days=10)).fecha_pago, self.hoy - timedelta(days=10))

    def test_regla_fecha_sin_fecha_es_hoy(self):
        """Regla «Fecha»: por defecto hoy (``fecha=None``); ``hoy`` se recibe para no leer el reloj."""
        with self.captureOnCommitCallbacks(execute=True):
            pago = pagos.registrar_pago(self.contador, self.orden.pk, self.proveedor.pk, "efectivo", None, hoy=self.hoy)
        self.assertEqual(pago.fecha_pago, self.hoy)

    def test_d102_la_fecha_se_valida_con_ejercicio_para_manual_y_el_asiento_va_con_la_fecha_pasada(self):
        """D-91 punto 4 y D-102 punto 3: se valida con ``ejercicio_para(fecha, automatico=False)`` y se pasa **tal cual** a ``registrar_asiento_automatico``."""
        from contabilidad.servicios import ejercicios

        ejercicio(Estado.EN_CIERRE, self.hoy - timedelta(days=365), self.hoy - timedelta(days=1))
        fecha = self.hoy - timedelta(days=2)
        real = ejercicios.ejercicio_para
        with mock.patch("contabilidad.servicios.ejercicios.ejercicio_para", side_effect=real) as validacion:
            with mock.patch("contabilidad.servicios.asientos.registrar_asiento_automatico", side_effect=AssertionError("corta acá")) as asiento:
                with self.assertRaises(AssertionError):
                    self.pagar(fecha=fecha)
        self.assertTrue(any(c.args[:1] == (fecha,) and c.kwargs.get("automatico") is False for c in validacion.call_args_list))
        self.assertIn(fecha, asiento.call_args.args)  # la fecha del pago, no hoy

    def test_ext_8b_si_falta_la_cuenta_caja_no_se_registra_nada_y_se_informa_cual(self):
        """Extensión 8b y precondición c: si falta una cuenta (acá Caja, con un pago en efectivo), no se registra ningún cambio e informa qué falta (``cuenta_inexistente``)."""
        CuentaContable.objects.filter(codigo_cuenta=cuentas.CAJA).delete()
        error = self.error_de_pago(medio="efectivo", clase=ErrorContable)
        self.assertEqual(error.codigo, "cuenta_inexistente")
        self.assertIn(cuentas.CAJA, error.mensaje)
        self.sin_cambios_de_pagos(self.antes)
        with self.assertRaises(ErrorContable):
            pagos.resumir_pago(self.contador, self.orden.pk, self.proveedor.pk, "efectivo", self.hoy)

    def test_ext_8b_con_banco_las_cuentas_que_no_se_usan_no_importan(self):
        """Solo hacen falta las cuentas del asiento: sin Caja, un pago por transferencia se registra."""
        CuentaContable.objects.filter(codigo_cuenta=cuentas.CAJA).delete()
        self.assertEqual(self.pagar(medio="transferencia").medio_pago, "transferencia")


class CmpRegPagTodoONadaTests(PagosBase):
    """Garantías mínimas y extensión *b: el registro es una única transacción (pago, asiento y logs juntos o ninguno)."""

    def test_ext_b_si_falla_el_asiento_no_queda_pago_ni_auditoria_ni_correo(self):
        """Garantías mínimas: si el asiento falla no queda ningún pago, asiento, log ni correo, y el proveedor sigue en la bandeja."""
        self.recibir_a()
        antes = self.instantanea_de_pagos()
        with mock.patch("contabilidad.servicios.asientos.registrar_asiento_automatico", side_effect=RuntimeError("falla del asiento")):
            with self.assertRaises(RuntimeError):
                self.pagar()
        self.sin_cambios_de_pagos(antes)
        self.assertEqual(len(pagos.pagos_pendientes()), 1)

    def test_ext_b_si_falla_la_auditoria_del_pago_tampoco_queda_el_asiento(self):
        """Extensión *b: si falla lo último que se escribe (el log del pago), se revierte todo, también el asiento y sus logs."""
        self.recibir_a()
        antes = self.instantanea_de_pagos()
        real = RegistroAuditoria.objects.registrar

        def falla_la_del_pago(*args, **kwargs):
            accion = kwargs.get("accion", args[1] if len(args) > 1 else None)
            if accion == RegistroAuditoria.Accion.REGISTRO_PAGO_PROVEEDOR:
                raise RuntimeError("falla de la auditoría")
            return real(*args, **kwargs)

        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=falla_la_del_pago):
            with self.assertRaises(RuntimeError):
                self.pagar()
        self.sin_cambios_de_pagos(antes)

    def test_d86_el_asiento_se_pide_una_sola_vez_con_el_pago_ya_creado_y_con_la_fecha_y_los_movimientos(self):
        """D-86 punto 2 y «Cómo se aplica»: el asiento va **por último** (cuando se lo pide, el pago ya existe) y se pide una sola vez, con el pago de origen, la fecha del pago y Debe Proveedores / Haber Banco."""
        self.recibir_a()
        vistos = {}
        real = servicio_de_asientos.registrar_asiento_automatico

        def espiar(actor, origen, fecha, movimientos, **kwargs):
            vistos.update(pagos=Pago.objects.count(), origen=origen.pk, fecha=fecha, movimientos=movimientos, auditorias=RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.REGISTRO_PAGO_PROVEEDOR).count())
            return real(actor, origen, fecha, movimientos, **kwargs)

        with mock.patch("contabilidad.servicios.asientos.registrar_asiento_automatico", side_effect=espiar) as llamadas:
            pago = self.pagar(medio="transferencia")
        self.assertEqual(llamadas.call_count, 1)
        self.assertEqual(vistos, {"pagos": 1, "origen": pago.pk, "fecha": self.hoy, "movimientos": [(cuentas.PROVEEDORES, DEBE, D("300.00")), (cuentas.BANCO, HABER, D("300.00"))], "auditorias": 0})


class CmpRegPagConsultasTests(PagosBase):
    """Pasos 4 y 6: el detalle del pago y el resumen. Ninguno escribe."""

    def test_paso_4_el_detalle_muestra_por_linea_lo_pedido_lo_recibido_el_total_el_unitario_y_el_subtotal(self):
        """Paso 4: por cada línea, el insumo, la cantidad pedida, la recibida, el total de la línea, el precio unitario calculado y el subtotal a pagar; y el monto total y las recepciones."""
        recepcion = self.recibir_a()
        detalle = pagos.detalle_del_pago(self.contador, self.orden.pk, self.proveedor.pk)
        self.assertEqual((detalle.orden.pk, detalle.proveedor.pk, detalle.monto), (self.orden.pk, self.proveedor.pk, D("300.00")))
        self.assertEqual(
            [(l.insumo.nombre_insumo, l.pedida, l.recibida, l.total, l.unitario, l.a_pagar, l.estado) for l in detalle.lineas],
            [("Fertilizante", D("10"), D("10"), D("100.00"), D("10.00"), D("100.00"), "completo"), ("Maceta", D("20"), D("20"), D("200.00"), D("10.00"), D("200.00"), "completo")],
        )
        self.assertEqual([r.pk for r in detalle.recepciones], [recepcion.pk])

    def test_paso_4_las_lineas_cerradas_con_faltante_y_lo_no_aceptado_se_muestran_pero_no_se_pagan(self):
        """Paso 4: «las líneas cerradas con faltante y lo no aceptado por daño (que no se pagan)». El Fertilizante: 4 de 10, con 6 dañados declarados, cerrado con faltante: se paga 4 × $10,00."""
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence, inconvenientes=[(DANADA, 6, "Cajas aplastadas")]), self.linea(self.l_maceta, 20)])
        with self.captureOnCommitCallbacks(execute=True):
            recepciones.cerrar_con_faltante(self.ana, [(self.l_fert.pk, "El proveedor no repone.")])
        detalle = pagos.detalle_del_pago(self.contador, self.orden.pk, self.proveedor.pk)
        fert = detalle.lineas[0]
        self.assertEqual((fert.estado, fert.motivo_cierre, fert.recibida, fert.a_pagar, fert.no_aceptada), ("cerrado_con_faltante", "El proveedor no repone.", D("4"), D("40.00"), D("6")))
        self.assertEqual(detalle.monto, D("240.00"))

    def test_paso_4_solo_trae_las_lineas_del_proveedor(self):
        """Paso 4: el detalle de A no incluye la línea de B (regla 7 de 8.20: cada proveedor se paga por lo suyo)."""
        self.recibir_a()
        self.recibir_b()
        detalle = pagos.detalle_del_pago(self.contador, self.orden.pk, self.proveedor_b.pk)
        self.assertEqual(([l.insumo.nombre_insumo for l in detalle.lineas], detalle.monto), (["Tomate"], D("80.00")))

    def test_paso_6_el_resumen_dice_el_monto_el_medio_y_el_asiento_que_se_registrara_sin_escribir(self):
        """Paso 6: el resumen trae el detalle, el medio, la fecha, los movimientos del asiento (Debe Proveedores / Haber Caja o Banco c/c) y el ejercicio donde caerá. No escribe nada."""
        self.recibir_a()
        antes = self.instantanea_de_pagos()
        resumen = pagos.resumir_pago(self.contador, self.orden.pk, self.proveedor.pk, "efectivo", self.hoy)
        self.assertEqual((resumen.medio, resumen.fecha, resumen.detalle.monto, resumen.ejercicio.pk), ("efectivo", self.hoy, D("300.00"), self.abierto.pk))
        self.assertEqual(resumen.movimientos, [(cuentas.PROVEEDORES, DEBE, D("300.00")), (cuentas.CAJA, HABER, D("300.00"))])
        self.sin_cambios_de_pagos(antes)
        self.assertEqual(pagos.resumir_pago(self.contador, self.orden.pk, self.proveedor.pk, "tarjeta_credito", self.hoy).movimientos[1], (cuentas.BANCO, HABER, D("300.00")))

    def test_paso_6_el_resumen_de_un_par_que_no_esta_listo_se_rechaza(self):
        """Las mismas validaciones que el registro: sin pago pendiente no hay resumen."""
        with self.assertRaises(ErrorDeCompras) as contexto:
            pagos.resumir_pago(self.contador, self.orden.pk, self.proveedor.pk, "efectivo", self.hoy)
        self.assertEqual(contexto.exception.codigo, "sin_pago_pendiente")


class CmpBajPrvPrecondicionDTests(PagosBase):
    """CMP-BAJ-PRV precondición d y regla 2 (H22): un pago pendiente impide la baja del proveedor, con enlace a la orden."""

    def setUp(self):
        super().setUp()
        from compras.servicios import proveedores

        self.proveedores = proveedores
        # Con las dos recibidas la orden queda «recibida» y no es un impedimento por «orden no terminada».
        self.recibir_a()
        self.recibir_b()

    def impedimentos(self, proveedor=None):
        return self.proveedores.impedimentos_de_baja(proveedor or self.proveedor)

    def test_pre_d_un_pago_pendiente_es_un_impedimento_con_su_enlace_a_la_orden(self):
        """Precondición d: ``pago_pendiente`` por cada par pendiente del proveedor, con el texto, cómo resolverlo y el enlace a la ficha de la orden."""
        from django.urls import reverse

        impedimentos = self.impedimentos()
        self.assertEqual([i.codigo for i in impedimentos], ["pago_pendiente"])
        self.assertIn(str(self.orden), impedimentos[0].texto)
        self.assertTrue(impedimentos[0].como_resolver)
        self.assertEqual(impedimentos[0].url, reverse("compras:orden_ficha", args=[self.orden.pk]))

    def test_pre_d_sin_pago_pendiente_no_hay_impedimento_y_con_el_pago_registrado_se_levanta(self):
        """Precondición d: pagado, el proveedor ya no tiene el impedimento; el otro proveedor (B) sigue con el suyo."""
        self.pagar()
        self.assertEqual(self.impedimentos(), [])
        self.assertEqual([i.codigo for i in self.impedimentos(self.proveedor_b)], ["pago_pendiente"])

    def test_pre_d_una_orden_con_lineas_pendientes_no_es_un_pago_pendiente_sino_una_orden_sin_terminar(self):
        """El impedimento de pago es solo para lo que ya está listo: una orden con mercadería por recibir sigue siendo ``orden_no_terminada``."""
        otra, proveedor_otro = self.otra_pagable(5)
        orden_sin_recibir, linea, _ = self.otra_orden(self.ana, self.norte, "Sustrato nuevo", n=6)
        self.assertEqual([i.codigo for i in self.impedimentos(linea.proveedor)], ["orden_no_terminada"])
        self.assertEqual([i.codigo for i in self.impedimentos(proveedor_otro)], ["pago_pendiente"])

    def test_regla_2_la_baja_con_un_pago_pendiente_se_rechaza_con_el_impedimento_y_no_cambia_nada(self):
        """CMP-BAJ-PRV regla 2: ``baja_con_impedimentos`` con el ``pago_pendiente`` entre los impedimentos; el proveedor sigue activo y no queda registro de baja."""
        with self.assertRaises(ErrorDeCompras) as contexto:
            self.proveedores.baja_proveedor(self.gerente, self.proveedor.pk)
        self.assertEqual(contexto.exception.codigo, "baja_con_impedimentos")
        self.assertEqual([i.codigo for i in contexto.exception.datos["impedimentos"]], ["pago_pendiente"])
        self.proveedor.refresh_from_db()
        self.assertEqual(self.proveedor.estado_proveedor, "activo")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.BAJA_PROVEEDOR).exists())

    def test_regla_2_pagado_el_proveedor_se_da_de_baja(self):
        """Resuelto el impedimento (registrado el pago), la baja procede."""
        self.pagar()
        self.assertEqual(self.proveedores.baja_proveedor(self.gerente, self.proveedor.pk).estado_proveedor, "inactivo")

