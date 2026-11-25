# Pruebas de COM-PCT-SUM, Pactar Suministro (COM-03a, paso 4; docs/casos_de_uso/comercial/suministro.md): `pactar_suministro`,
# `datos_del_formulario`, `resumen`, `puede_pactar` y el comprobante del suministro. Una prueba por regla, postcondición y extensión.
# Las que escriben verifican al final los invariantes del patrón de stock maduro (secciones 6 y 7). La concurrencia está en
# `test_suministros_concurrencia.py`.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar):
#   - `DatosDeSuministro(vendedor_id, cliente_id, duracion, tolerados, multa, plazo_pago, indemnizacion_pago, renglones)` y
#     `RenglonDeSuministro(indice, variedad_id, direccion_id, cantidad, periodo, primera_entrega, mecanismo, precio, porcentaje, meses,
#     plazo_entrega, indemnizacion_retraso, cantidad_minima, indemnizacion_faltante, continuar_superpuesto)`, todo texto (como llegó).
#   - Errores: `ValidationError` por campo. Campos: `vendedor`, `cliente`, `duracion`, `tolerados`, `multa`, `plazo_pago`,
#     `indemnizacion_pago`, `detalle-<i>-<campo>` (con `variedad`, `direccion`, `cantidad`, `periodo`, `primera_entrega`, `mecanismo`,
#     `precio`, `porcentaje`, `meses`, `plazo_entrega`, `indemnizacion_retraso`, `cantidad_minima`, `indemnizacion_faltante`, `continuar`)
#     y `__all__`.
#   - Códigos: `vendedor_obligatorio|invalido|inactivo|sin_invernaderos`, `cliente_obligatorio|inactivo|sin_correo`, `duracion_invalida`,
#     `tolerados_invalidos`, `multa_invalida`, `plazo_pago_invalido`, `indemnizacion_pago_invalida`, `variedad_obligatoria|inactiva`,
#     `direccion_obligatoria|no_valida`, `cantidad_invalida`, `periodo_invalido`, `fecha_obligatoria|fecha_invalida|fecha_fuera_de_rango` (campo `primera_entrega`),
#     `mecanismo_invalido`, `precio_invalido`, `porcentaje_invalido`, `meses_invalidos`, `plazo_entrega_invalido`,
#     `indemnizacion_retraso_invalida`, `cantidad_minima_invalida`, `indemnizacion_faltante_invalida`, `par_repetido`,
#     `superposicion_sin_confirmar`, `supera_disponible` (9e, al revisar), `stock_insuficiente` (14a, al confirmar), `sin_detalles`
#     (12a), `cambio_simultaneo`. Las advertencias (9d y 9f) no son errores: `fila.advertencias` de `datos_del_formulario`.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from comercial.models import (
    Cliente,
    ClausulaSuministrado,
    ClausulaSuministrante,
    DetalleReserva,
    DetalleSuministro,
    ReservaStock,
    Suministro,
)
from comercial.servicios import calendario, comprobantes, suministros
from comercial.servicios.suministros import DatosDeSuministro, RenglonDeSuministro
from comercial.tests.fabricas import (
    cliente as crear_cliente,
    detalle_suministro,
    direccion_de_cliente,
    escenario_comercial,
    reserva_de_periodo,
    suministro,
    verificar_invariantes_de_reservas,
)
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Direccion
from maestros.tests.fabricas import crear_vendedor
from produccion.models import Cosecha
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def iso(dias):
    """La fecha de dentro de ``dias`` días, como la manda el calendario del formulario."""
    return str(HOY + timedelta(days=dias))


def codigos_de(error, campo):
    """Los códigos de los errores de un campo."""
    return [e.code for e in error.error_dict.get(campo, [])]


def todos_los_codigos(error):
    """Todos los códigos de una ``ValidationError``, con campos o sin ellos."""
    if hasattr(error, "error_dict"):
        return [e.code for lista in error.error_dict.values() for e in lista]
    return [e.code for e in error.error_list]


class BaseDePacto(ConDatosDeInventario, TestCase):
    """Un invernadero con Capataz, Agrónomo y Vendedor con 100 plantas en Maduración, y un cliente con correo y una dirección."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 100)
        self.gerente = crear_gerente()
        self.addCleanup(verificar_invariantes_de_reservas)

    def renglon(self, indice=0, **extra):
        """Un detalle de 30 plantas cada 7 días, la primera dentro de 3 días (períodos en la ventana: dentro de 3 y de 10 días)."""
        valores = dict(
            indice=indice,
            variedad_id=str(self.e.variedad.pk),
            direccion_id=str(self.e.direccion.pk),
            cantidad="30",
            periodo="7",
            primera_entrega=iso(3),
            mecanismo="fijo",
            precio="1500,50",
            porcentaje="",
            meses="",
            plazo_entrega="1",
            indemnizacion_retraso="100",
            cantidad_minima="10",
            indemnizacion_faltante="50",
            continuar_superpuesto="",
        )
        valores.update(extra)
        return RenglonDeSuministro(**valores)

    def datos(self, renglones=None, **extra):
        """Un pacto de 6 meses con un detalle (se pisa con ``extra``)."""
        valores = dict(
            vendedor_id="",
            cliente_id=str(self.e.cliente.pk),
            duracion="6",
            tolerados="3",
            multa="50000",
            plazo_pago="15",
            indemnizacion_pago="100",
            renglones=renglones if renglones is not None else [self.renglon()],
        )
        valores.update(extra)
        return DatosDeSuministro(**valores)

    def pactar(self, actor=None, renglones=None, **extra):
        """Pacta con los datos por defecto como ``actor`` (por defecto, el Vendedor)."""
        return suministros.pactar_suministro(actor or self.e.vendedor, self.datos(renglones, **extra))

    def rechazo(self, actor=None, renglones=None, **extra):
        """Pacta esperando una ``ValidationError`` y la devuelve."""
        with self.assertRaises(ValidationError) as contexto:
            self.pactar(actor, renglones, **extra)
        return contexto.exception

    def otra_direccion(self):
        """Otra dirección activa del mismo cliente (la ``Direccion``, no el vínculo)."""
        return direccion_de_cliente(self.e.cliente).direccion


class FlujoPrincipalTests(BaseDePacto):
    """Postcondiciones a a i del flujo principal."""

    def test_flujo_principal_pacta_el_suministro_con_su_clausula_su_detalle_y_su_reserva(self):
        """Postcondiciones a, b y c: suministro «vigente» de hoy con su duración, su fecha de fin, sus tolerados, su multa y 0
        incumplimientos, asociado al cliente y al Vendedor, con la cláusula del suministrado; un detalle «vigente» con sus datos, su
        cláusula del suministrante y `fecha_base_ajuste` = la fecha de realización."""
        s = self.pactar()
        self.assertEqual(
            (s.estado_suministro, s.fecha_realizacion, s.duracion_meses, s.fecha_fin, s.incumplimientos_tolerados, s.multa_resolucion,
             s.cantidad_incumplimientos, s.cliente_id, s.vendedor_id),
            ("vigente", HOY, 6, calendario.sumar_meses(HOY, 6), 3, Decimal("50000.00"), 0, self.e.cliente.pk, self.e.vendedor.pk),
        )
        self.assertEqual(s.codigo, f"SUM-{s.numero:04d}")
        clausula = ClausulaSuministrado.objects.get(suministro=s)
        self.assertEqual((clausula.plazo_pago_dias, clausula.indemnizacion_retraso_pago), (15, Decimal("100.00")))
        (d,) = s.detalles.all()
        self.assertEqual(
            (d.variedad_id, d.direccion_id, d.cantidad_por_periodo, d.periodo_entrega_dias, d.fecha_primer_entrega, d.mecanismo_precio,
             d.precio_unitario_suministro, d.porcentaje_ajuste, d.meses_ajuste, d.estado_detalle_suministro, d.fecha_base_ajuste,
             d.fecha_fin_detalle, d.reemplaza_a_id),
            (self.e.variedad.pk, self.e.direccion.pk, 30, 7, HOY + timedelta(days=3), "fijo", Decimal("1500.50"), None, None, "vigente",
             HOY, None, None),
        )
        c = ClausulaSuministrante.objects.get(detalle=d)
        self.assertEqual(
            (c.plazo_entrega_dias, c.indemnizacion_retraso_entrega, c.cantidad_minima, c.indemnizacion_faltante),
            (1, Decimal("100.00"), 10, Decimal("50.00")),
        )

    def test_post_d_reserva_los_periodos_de_la_ventana_y_solo_esos(self):
        """Postcondición d y regla «Ventana de pre-reserva»: con 14 días de ventana y entregas dentro de 3, 10 y 17 días, se reservan los dos
        primeros períodos (cada uno con su fecha y sus 30 plantas); el del día 17 queda para la pre-reserva diaria."""
        s = self.pactar()
        d = s.detalles.get()
        reservas = ReservaStock.objects.filter(detalle_suministro=d).order_by("fecha_entrega_reserva")
        self.assertEqual([r.fecha_entrega_reserva for r in reservas], [HOY + timedelta(days=3), HOY + timedelta(days=10)])
        for r in reservas:
            self.assertEqual(sum(l.cantidad_reservada for l in r.lineas.all()), 30)
            self.assertIsNone(r.detalle_venta_id)
        self.assertEqual((s.periodos_reservados, s.cosechas_programadas), (2, 2))

    def test_post_e_cada_reserva_con_lote_tiene_su_cosecha_y_se_notifica_al_capataz_y_al_agronomo(self):
        """Postcondición e: una cosecha «a realizar» por reserva con lote, con el Capataz del invernadero, y su aviso al Capataz y al Agrónomo."""
        self.pactar()
        self.assertEqual(Cosecha.objects.count(), 2)
        self.assertEqual(
            sorted(Notificacion.objects.values_list("destinatario_id", flat=True)),
            sorted([self.e.capataz.pk, self.e.agronomo.pk] * 2),
        )

    def test_post_h_i_un_solo_registro_de_auditoria_con_todo_lo_creado(self):
        """Postcondiciones h e i (D-36): UN registro `pacto_suministro` con el usuario y, entre los afectados, el suministro (primero), su cláusula,
        el detalle y su cláusula, y lo que devolvió `asignar` (reservas, líneas y cosechas)."""
        s = self.pactar()
        (registro,) = RegistroAuditoria.objects.filter(accion="pacto_suministro")
        self.assertEqual(registro.usuario_id, self.e.vendedor.pk)
        modelos = [a["modelo"] for a in registro.afectados]
        for esperado in (
            "comercial.suministro", "comercial.clausulasuministrado", "comercial.detallesuministro", "comercial.clausulasuministrante",
            "comercial.reservastock", "comercial.detallereserva", "produccion.cosecha",
        ):
            self.assertIn(esperado, modelos)
        self.assertEqual(registro.afectados[0]["texto"], s.codigo)
        self.assertEqual(registro.detalle["datos"]["vendedor"]["id"], self.e.vendedor.pk)

    def test_post_a_el_numero_sale_de_la_secuencia_y_no_se_repite(self):
        """Ficha de Suministro: dos pactos seguidos tienen números distintos y crecientes (`comercial_suministro_numero_seq`)."""
        a = self.pactar()
        b = self.pactar(renglones=[self.renglon(cantidad="10", primera_entrega=iso(40), continuar_superpuesto="1")])
        self.assertGreater(b.numero, a.numero)

    def test_ext_1a_el_gerente_elige_al_vendedor_y_queda_como_quien_lo_cargo(self):
        """Extensión 1a y regla «Vendedor responsable»: el contrato es del Vendedor elegido; el log de auditoría registra al Gerente."""
        s = self.pactar(self.gerente, vendedor_id=str(self.e.vendedor.pk))
        self.assertEqual(s.vendedor_id, self.e.vendedor.pk)
        (registro,) = RegistroAuditoria.objects.filter(accion="pacto_suministro")
        self.assertEqual(registro.usuario_id, self.gerente.pk)

    def test_ext_1a_el_gerente_sin_vendedor_o_con_uno_invalido_es_rechazado(self):
        """Extensión 1a: sin elegir, `vendedor_obligatorio`; un Vendedor inexistente, de otro rol o sin invernaderos activos, `vendedor_invalido`."""
        self.assertEqual(codigos_de(self.rechazo(self.gerente), "vendedor"), ["vendedor_obligatorio"])
        sin_invernaderos = crear_vendedor(email="sin@infoponia.com")
        for valor in ("999999", "abc", str(self.e.agronomo.pk), str(sin_invernaderos.pk)):
            with self.subTest(valor=valor):
                self.assertEqual(codigos_de(self.rechazo(self.gerente, vendedor_id=valor), "vendedor"), ["vendedor_invalido"])

    def test_regla_vendedor_responsable_el_vendedor_ignora_el_vendedor_que_mande(self):
        """Regla «Vendedor responsable»: si actúa un Vendedor, el responsable es él (no elige)."""
        otro = crear_vendedor(email="otro@infoponia.com")
        self.assertEqual(self.pactar(vendedor_id=str(otro.pk)).vendedor_id, self.e.vendedor.pk)

    def test_pre_a_solo_el_vendedor_y_el_gerente_activos_pactan(self):
        """Precondición a: otro rol, una cuenta inactiva o ninguna cuenta: `PermissionDenied`."""
        for actor in (self.e.agronomo, self.e.capataz, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                suministros.pactar_suministro(actor, self.datos())
        type(self.e.vendedor).objects.filter(pk=self.e.vendedor.pk).update(is_active=False)
        self.e.vendedor.refresh_from_db()
        with self.assertRaises(PermissionDenied):
            self.pactar()

    def test_pre_b_c_sin_invernaderos_o_sin_variedades_activas_no_se_puede_pactar(self):
        """Precondiciones b y c: `puede_pactar` da el motivo de «Pactar suministro» deshabilitado."""
        self.assertEqual(suministros.puede_pactar(self.e.vendedor), (True, ""))
        self.assertEqual(suministros.puede_pactar(self.gerente), (True, ""))
        type(self.e.variedad).objects.filter(pk=self.e.variedad.pk).update(estado_variedad="inactivo")
        self.assertEqual(suministros.puede_pactar(self.e.vendedor), (False, "No hay variedades activas."))
        type(self.e.variedad).objects.filter(pk=self.e.variedad.pk).update(estado_variedad="activo")
        type(self.e.invernadero).objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertFalse(suministros.puede_pactar(self.e.vendedor)[0])
        self.assertFalse(suministros.puede_pactar(self.gerente)[0])

    def test_regla_con_tolerados_cero_se_acepta(self):
        """PCU 16: incumplimientos tolerados de 0 a 99; con 0, el primero resuelve el contrato (se pacta sin error)."""
        self.assertEqual(self.pactar(tolerados="0").incumplimientos_tolerados, 0)
        fuera = [self.renglon(cantidad="10", primera_entrega=iso(40), continuar_superpuesto="1")]  # fuera de la ventana y superpuesto a propósito
        self.assertEqual(self.pactar(tolerados="99", renglones=fuera).incumplimientos_tolerados, 99)


class ClienteTests(BaseDePacto):
    """Extensiones 3a, 4a y 4b."""

    def test_ext_4a_un_cliente_inactivo_o_inexistente_o_sin_elegir_se_rechaza(self):
        """Extensión 4a: `cliente_inactivo` para uno dado de baja; `cliente_obligatorio` sin elegir; uno inexistente, `cliente_obligatorio`."""
        Cliente.objects.filter(pk=self.e.cliente.pk).update(estado_cliente="inactivo")
        self.assertEqual(codigos_de(self.rechazo(), "cliente"), ["cliente_inactivo"])
        self.assertEqual(codigos_de(self.rechazo(cliente_id=""), "cliente"), ["cliente_obligatorio"])
        self.assertEqual(codigos_de(self.rechazo(cliente_id="999999"), "cliente"), ["cliente_obligatorio"])

    def test_ext_4b_un_cliente_sin_correo_no_se_puede_pactar(self):
        """Extensión 4b y regla 18 de 8.20: el correo es obligatorio para pactar (`cliente_sin_correo`); el formulario lo avisa."""
        Cliente.objects.filter(pk=self.e.cliente.pk).update(email_cliente="")
        self.assertEqual(codigos_de(self.rechazo(), "cliente"), ["cliente_sin_correo"])
        self.assertTrue(suministros.datos_del_formulario(self.e.vendedor, self.datos()).cliente_sin_correo)
        self.assertEqual(Suministro.objects.count(), 0)


class DatosDelContratoTests(BaseDePacto):
    """Extensión 6a y reglas «Datos del contrato» y «Cláusula del suministrado»."""

    def test_ext_6a_cada_dato_del_contrato_fuera_de_rango_se_rechaza_en_su_campo(self):
        """6a: duración de 1 a 120 meses; tolerados de 0 a 99; multa de 0 a 99.999.999,99; plazo de pago de 0 a 365 días; indemnización por
        atraso de 0 a 9.999.999,99. Texto, vacío y decimales de más también."""
        casos = {
            "duracion": ("duracion_invalida", ["0", "121", "", "abc", "1,5"], ["1", "120"]),
            "tolerados": ("tolerados_invalidos", ["-1", "100", "", "x"], ["0", "99"]),
            "multa": ("multa_invalida", ["-1", "100000000", "", "x", "10,005"], ["0", "99999999,99", "1.500,50"]),
            "plazo_pago": ("plazo_pago_invalido", ["-1", "366", "", "x"], ["0", "365"]),
            "indemnizacion_pago": ("indemnizacion_pago_invalida", ["-1", "10000000", "", "x"], ["0", "9999999,99"]),
        }
        for campo, (codigo, malos, buenos) in casos.items():
            for valor in malos:
                with self.subTest(campo=campo, valor=valor):
                    self.assertEqual(codigos_de(self.rechazo(**{campo: valor}), campo), [codigo])
            for valor in buenos:
                with self.subTest(campo=campo, bueno=valor):
                    self.assertEqual(suministros.resumen(self.e.vendedor, self.datos(**{campo: valor})).formulario.errores, {})

    def test_regla_fecha_de_fin_es_el_mismo_dia_del_mes_n_meses_despues(self):
        """Regla «Fecha de fin»: la que muestra el formulario y la que guarda el contrato es `sumar_meses(hoy, duración)`."""
        for meses in (1, 6, 12, 120):
            with self.subTest(meses=meses):
                formulario = suministros.datos_del_formulario(self.e.vendedor, self.datos(duracion=str(meses)))
                self.assertEqual(formulario.fecha_fin, calendario.sumar_meses(HOY, meses))
        self.assertEqual(self.pactar(duracion="12", renglones=[self.renglon(primera_entrega=iso(40))]).fecha_fin, calendario.sumar_meses(HOY, 12))

    def test_regla_los_importes_aceptan_coma_o_punto_decimal(self):
        """Formatos: «1.500,50» y «1500.50» valen lo mismo."""
        a = self.pactar(multa="1.500,50", renglones=[self.renglon(precio="2.500,25")])
        b = self.pactar(multa="1500.50", renglones=[self.renglon(precio="2500.25", primera_entrega=iso(40), continuar_superpuesto="1")])
        self.assertEqual((a.multa_resolucion, b.multa_resolucion), (Decimal("1500.50"), Decimal("1500.50")))
        self.assertEqual(a.detalles.get().precio_unitario_suministro, Decimal("2500.25"))


class DatosDelDetalleTests(BaseDePacto):
    """Extensiones 8a, 8b, 9a, 9b, 9c, 11a y 11b y reglas «Datos del detalle», «Datos del precio» y «Cláusula del suministrante»."""

    def campo(self, indice, nombre):
        return f"detalle-{indice}-{nombre}"

    def test_ext_8a_la_direccion_tiene_que_ser_una_activa_del_cliente(self):
        """Regla «Dirección y modalidad» y extensión 8a: una dirección de otro cliente, una inactiva o una inexistente: `direccion_no_valida`;
        sin elegir, `direccion_obligatoria`; una dirección que se acaba de agregar al cliente sirve."""
        ajena = direccion_de_cliente(crear_cliente(razon_social="Otro S.A.", email="otro@ejemplo.com")).direccion
        inactiva = self.otra_direccion()
        Direccion.objects.filter(pk=inactiva.pk).update(estado_direccion="inactivo")
        for valor in (str(ajena.pk), str(inactiva.pk), "999999", "abc"):
            with self.subTest(valor=valor):
                error = self.rechazo(renglones=[self.renglon(direccion_id=valor)])
                self.assertEqual(codigos_de(error, self.campo(0, "direccion")), ["direccion_no_valida"])
        self.assertEqual(
            codigos_de(self.rechazo(renglones=[self.renglon(direccion_id="")]), self.campo(0, "direccion")), ["direccion_obligatoria"]
        )
        nueva = self.otra_direccion()
        self.assertEqual(self.pactar(renglones=[self.renglon(direccion_id=str(nueva.pk))]).detalles.get().direccion_id, nueva.pk)

    def test_regla_la_variedad_tiene_que_estar_activa(self):
        """Paso 7 y precondición c: `variedad_obligatoria` sin elegir; `variedad_inactiva` si no existe o está dada de baja."""
        self.assertEqual(
            codigos_de(self.rechazo(renglones=[self.renglon(variedad_id="")]), self.campo(0, "variedad")), ["variedad_obligatoria"]
        )
        type(self.e.variedad).objects.filter(pk=self.e.variedad.pk).update(estado_variedad="inactivo")
        self.assertEqual(codigos_de(self.rechazo(), self.campo(0, "variedad")), ["variedad_inactiva"])

    def test_ext_8b_con_ajuste_periodico_se_guardan_el_porcentaje_y_los_meses(self):
        """Extensión 8b: el detalle de ajuste periódico guarda el porcentaje y cada cuántos meses; el precio inicial queda como inicial."""
        s = self.pactar(renglones=[self.renglon(mecanismo="ajuste_periodico", porcentaje="3,5", meses="2")])
        d = s.detalles.get()
        self.assertEqual((d.mecanismo_precio, d.porcentaje_ajuste, d.meses_ajuste, d.precio_unitario_suministro), ("ajuste_periodico", Decimal("3.50"), 2, Decimal("1500.50")))

    def test_ext_8b_con_ajuste_periodico_el_porcentaje_y_los_meses_son_obligatorios_y_estan_en_rango(self):
        """Datos del precio: porcentaje de 0,01 a 100 y meses de 1 a 60, solo con ajuste periódico."""
        base = dict(mecanismo="ajuste_periodico")
        for valor in ("", "0", "100,01", "x"):
            with self.subTest(porcentaje=valor):
                error = self.rechazo(renglones=[self.renglon(**base, porcentaje=valor, meses="2")])
                self.assertEqual(codigos_de(error, self.campo(0, "porcentaje")), ["porcentaje_invalido"])
        for valor in ("", "0", "61", "x", "1,5"):
            with self.subTest(meses=valor):
                error = self.rechazo(renglones=[self.renglon(**base, porcentaje="3", meses=valor)])
                self.assertEqual(codigos_de(error, self.campo(0, "meses")), ["meses_invalidos"])
        for porcentaje, meses in (("0,01", "1"), ("100", "60")):
            with self.subTest(limites=(porcentaje, meses)):
                self.assertEqual(
                    suministros.resumen(self.e.vendedor, self.datos([self.renglon(**base, porcentaje=porcentaje, meses=meses)])).formulario.errores, {}
                )

    def test_regla_con_precio_fijo_el_porcentaje_y_los_meses_quedan_vacios(self):
        """Datos del precio: con mecanismo fijo esos dos datos quedan vacíos (aunque lleguen cargados) y no se validan."""
        d = self.pactar(renglones=[self.renglon(porcentaje="999", meses="999")]).detalles.get()
        self.assertEqual((d.porcentaje_ajuste, d.meses_ajuste), (None, None))

    def test_regla_el_mecanismo_tiene_que_ser_fijo_o_ajuste_periodico(self):
        """Datos del detalle: `mecanismo_invalido` con cualquier otro valor."""
        self.assertEqual(
            codigos_de(self.rechazo(renglones=[self.renglon(mecanismo="variable")]), self.campo(0, "mecanismo")), ["mecanismo_invalido"]
        )

    def test_ext_9a_la_primera_entrega_va_de_hoy_a_la_fecha_de_fin(self):
        """Extensión 9a y regla «Datos del detalle»: anterior a hoy o posterior a la fecha de fin: `fecha_fuera_de_rango` con el
        rango en el mensaje; hoy y la fecha de fin valen; vacía, `fecha_obligatoria`; no es fecha, `fecha_invalida`."""
        fin = calendario.sumar_meses(HOY, 6)
        for valor in (str(HOY - timedelta(days=1)), str(fin + timedelta(days=1))):
            with self.subTest(valor=valor):
                error = self.rechazo(renglones=[self.renglon(primera_entrega=valor)])
                self.assertEqual(codigos_de(error, self.campo(0, "primera_entrega")), ["fecha_fuera_de_rango"])
                self.assertIn(f"{fin:%d/%m/%Y}", error.error_dict[self.campo(0, "primera_entrega")][0].message)
        for valor in (str(HOY), str(fin)):
            with self.subTest(valido=valor):
                self.assertEqual(suministros.resumen(self.e.vendedor, self.datos([self.renglon(primera_entrega=valor, periodo="30")])).formulario.errores.get(self.campo(0, "primera_entrega")), None)
        self.assertEqual(
            codigos_de(self.rechazo(renglones=[self.renglon(primera_entrega="")]), self.campo(0, "primera_entrega")), ["fecha_obligatoria"]
        )
        self.assertEqual(
            codigos_de(self.rechazo(renglones=[self.renglon(primera_entrega="ayer")]), self.campo(0, "primera_entrega")), ["fecha_invalida"]
        )

    def test_ext_9b_cada_dato_del_detalle_y_del_precio_fuera_de_rango_se_rechaza_en_su_campo(self):
        """9b: cantidad de 1 a 500.000; período de 1 a 365 días; precio de 0,01 a 9.999.999,99 con hasta 2 decimales."""
        casos = {
            "cantidad": ("cantidad_invalida", ["0", "500001", "", "x", "1,5"], ["1", "500000"], {"cantidad_minima": "1", "primera_entrega": iso(40)}),
            "periodo": ("periodo_invalido", ["0", "366", "", "x"], ["1", "365"], {}),
            "precio": ("precio_invalido", ["0", "0,001", "10000000", "", "x"], ["0,01", "9999999,99"], {}),
        }
        for campo, (codigo, malos, buenos, aparte) in casos.items():
            for valor in malos:
                with self.subTest(campo=campo, valor=valor):
                    error = self.rechazo(renglones=[self.renglon(**{campo: valor}, **aparte)])
                    self.assertIn(codigo, codigos_de(error, self.campo(0, campo)))
            for valor in buenos:
                with self.subTest(campo=campo, bueno=valor):
                    formulario = suministros.datos_del_formulario(self.e.vendedor, self.datos([self.renglon(**{campo: valor}, **aparte)]))
                    self.assertNotIn(self.campo(0, campo), formulario.errores)

    def test_ext_9c_el_contrato_no_repite_el_par_variedad_y_direccion(self):
        """Extensión 9c: `par_repetido` en la variedad del segundo detalle, con el detalle existente en el mensaje (el número es el del
        formulario, desde 1); con otra dirección se admite."""
        error = self.rechazo(renglones=[self.renglon(0), self.renglon(1)])
        self.assertEqual(codigos_de(error, self.campo(1, "variedad")), ["par_repetido"])
        self.assertIn("es el detalle 1", error.error_dict[self.campo(1, "variedad")][0].message)
        s = self.pactar(renglones=[self.renglon(0, cantidad="10"), self.renglon(1, cantidad="10", direccion_id=str(self.otra_direccion().pk))])
        self.assertEqual(s.detalles.count(), 2)

    def test_ext_11a_la_cantidad_minima_va_de_uno_a_la_cantidad_por_periodo(self):
        """Extensión 11a: cero o más que la cantidad por período: `cantidad_minima_invalida`; 1 y la cantidad por período valen."""
        for valor in ("0", "31", "", "x"):
            with self.subTest(valor=valor):
                error = self.rechazo(renglones=[self.renglon(cantidad_minima=valor)])
                self.assertEqual(codigos_de(error, self.campo(0, "cantidad_minima")), ["cantidad_minima_invalida"])
        for valor in ("1", "30"):
            with self.subTest(valido=valor):
                self.assertEqual(suministros.resumen(self.e.vendedor, self.datos([self.renglon(cantidad_minima=valor)])).formulario.errores, {})

    def test_ext_11b_los_plazos_y_las_indemnizaciones_del_suministrante_estan_en_rango(self):
        """Extensión 11b y regla «Cláusula del suministrante»: tolerancia de 0 a 365 días (obligatoria: el prototipo la deja opcional);
        indemnizaciones de 0 a 9.999.999,99."""
        casos = {
            "plazo_entrega": ("plazo_entrega_invalido", ["-1", "366", "", "x"], ["0", "365"]),
            "indemnizacion_retraso": ("indemnizacion_retraso_invalida", ["-1", "10000000", "", "x"], ["0", "9999999,99"]),
            "indemnizacion_faltante": ("indemnizacion_faltante_invalida", ["-1", "10000000", "", "x"], ["0", "9999999,99"]),
        }
        for campo, (codigo, malos, buenos) in casos.items():
            for valor in malos:
                with self.subTest(campo=campo, valor=valor):
                    error = self.rechazo(renglones=[self.renglon(**{campo: valor})])
                    self.assertEqual(codigos_de(error, self.campo(0, campo)), [codigo])
            for valor in buenos:
                with self.subTest(campo=campo, bueno=valor):
                    self.assertEqual(
                        suministros.resumen(self.e.vendedor, self.datos([self.renglon(**{campo: valor})])).formulario.errores, {}
                    )


class SuperposicionYAjusteTests(BaseDePacto):
    """Extensiones 9d y 9f (advertencias)."""

    def otro_contrato_vigente(self, estado_contrato="vigente", estado_detalle="vigente", cliente_=None):
        """Otro suministro del mismo cliente (o de ``cliente_``) con la misma variedad y la misma dirección."""
        otro = suministro(self.e, cliente_=cliente_, estado=estado_contrato)
        extra = {"fecha_fin_detalle": HOY} if estado_detalle == "finalizado" else {}
        detalle_suministro(otro, self.e.variedad, direccion=self.e.direccion, estado=estado_detalle, **extra)
        return otro

    def test_ext_9d_el_formulario_advierte_la_superposicion_con_el_codigo_del_otro_contrato(self):
        """Extensión 9d: el cliente ya tiene un suministro vigente de la misma variedad a la misma dirección: advertencia con su código y la
        casilla «Continuar igual» (no es un error del formulario)."""
        otro = self.otro_contrato_vigente()
        fila = suministros.datos_del_formulario(self.e.vendedor, self.datos()).filas[0]
        (advertencia,) = [a for a in fila.advertencias if a.codigo == "superposicion"]
        self.assertEqual(advertencia.contrato.pk, otro.pk)
        self.assertEqual(fila.errores, {})

    def test_ext_9d_sin_la_casilla_se_rechaza_y_con_la_casilla_se_registra(self):
        """Regla «Suministro superpuesto»: continuar es una decisión explícita del Vendedor: sin la casilla, `superposicion_sin_confirmar`
        (y no se registra nada); con ella, el pacto se registra."""
        self.otro_contrato_vigente()
        error = self.rechazo()
        self.assertEqual(codigos_de(error, self.campo_continuar()), ["superposicion_sin_confirmar"])
        self.assertEqual(Suministro.objects.count(), 1)
        s = self.pactar(renglones=[self.renglon(continuar_superpuesto="1")])
        self.assertEqual(Suministro.objects.count(), 2)
        self.assertEqual(s.detalles.count(), 1)

    def campo_continuar(self):
        return "detalle-0-continuar"

    def test_ext_9d_no_hay_superposicion_con_otro_cliente_otro_estado_u_otra_direccion(self):
        """9d: no cuentan un contrato de otro cliente, uno que no está vigente, un detalle finalizado ni otra dirección."""
        otro_cliente = crear_cliente(razon_social="Otro S.A.", email="otro@ejemplo.com")
        direccion_de_cliente(otro_cliente)
        self.otro_contrato_vigente(cliente_=otro_cliente)
        self.otro_contrato_vigente(estado_contrato="finalizado")
        self.otro_contrato_vigente(estado_detalle="finalizado")
        fila = suministros.datos_del_formulario(self.e.vendedor, self.datos()).filas[0]
        self.assertEqual([a for a in fila.advertencias if a.codigo == "superposicion"], [])
        self.assertEqual(self.pactar().detalles.count(), 1)

    def test_ext_9f_un_ajuste_que_nunca_se_aplica_se_advierte_sin_bloquear(self):
        """Extensión 9f: con meses de ajuste mayores que la duración, advertencia «El precio no se ajustará durante el contrato» (con el
        primer ajuste después del fin); el pacto se registra igual."""
        renglon = self.renglon(mecanismo="ajuste_periodico", porcentaje="3", meses="12")
        fila = suministros.datos_del_formulario(self.e.vendedor, self.datos([renglon], duracion="6")).filas[0]
        (advertencia,) = [a for a in fila.advertencias if a.codigo == "ajuste_sin_efecto"]
        self.assertIn(f"{calendario.sumar_meses(HOY, 12):%d/%m/%Y}", advertencia.mensaje)
        self.assertEqual(self.pactar(renglones=[renglon]).detalles.count(), 1)
        sin_aviso = suministros.datos_del_formulario(self.e.vendedor, self.datos([renglon], duracion="12")).filas[0]
        self.assertEqual([a for a in sin_aviso.advertencias if a.codigo == "ajuste_sin_efecto"], [])


class CalendarioYPreciosTests(BaseDePacto):
    """Paso 9 y extensión 8b: el calendario y el precio de cada entrega, que muestra el formulario."""

    def test_paso_9_el_formulario_muestra_la_cantidad_de_entregas_el_total_y_las_fechas_de_la_ventana(self):
        """Paso 9: cantidad de entregas, total de plantas y las fechas con «se reserva ahora» las de la ventana (hasta 14 días)."""
        fila = suministros.datos_del_formulario(self.e.vendedor, self.datos(duracion="1")).filas[0]
        fechas = calendario.calendario(DetalleSuministro(
            fecha_primer_entrega=HOY + timedelta(days=3), periodo_entrega_dias=7,
            suministro=Suministro(fecha_fin=calendario.sumar_meses(HOY, 1)),
        ))
        self.assertEqual((fila.cantidad_de_entregas, fila.total_de_plantas), (len(fechas), len(fechas) * 30))
        self.assertEqual([p.fecha for p in fila.periodos_de_la_ventana], [HOY + timedelta(days=3), HOY + timedelta(days=10)])
        self.assertEqual(fila.fechas_visibles, fechas[:12])
        self.assertEqual(fila.fechas_restantes, max(0, len(fechas) - 12))

    def test_paso_9_con_mas_de_12_fechas_se_ven_las_primeras_12_y_cuantas_faltan(self):
        """Paso 9: «Si hay más de 12 fechas, las primeras 12 y “y N más hasta el dd/mm/aaaa”»."""
        fila = suministros.datos_del_formulario(self.e.vendedor, self.datos([self.renglon(periodo="1")], duracion="6")).filas[0]
        self.assertEqual(len(fila.fechas_visibles), 12)
        self.assertEqual(fila.fechas_restantes, fila.cantidad_de_entregas - 12)
        self.assertEqual(fila.ultima_fecha, calendario.sumar_meses(HOY, 6))

    def test_ext_8b_con_ajuste_periodico_el_formulario_muestra_los_tramos_de_precio(self):
        """Extensión 8b: el precio que tendrá cada entrega, como tramos «Desde el dd/mm: $ …» (`tramos_de_precio`)."""
        renglon = self.renglon(mecanismo="ajuste_periodico", porcentaje="3", meses="2", periodo="30", primera_entrega=iso(0), precio="1000")
        fila = suministros.datos_del_formulario(self.e.vendedor, self.datos([renglon], duracion="6")).filas[0]
        self.assertEqual([precio for _, precio in fila.tramos_de_precio], [Decimal("1000.00"), Decimal("1030.00"), Decimal("1060.90")])
        fijo = suministros.datos_del_formulario(self.e.vendedor, self.datos()).filas[0]
        self.assertEqual(len(fijo.tramos_de_precio), 1)

    def test_ext_9e_cada_periodo_de_la_ventana_muestra_lo_que_hay_disponible_despues_de_los_anteriores(self):
        """Extensión 9e y regla «Stock maduro libre»: con 100 plantas y dos períodos de 60, el primero ve 100 y el segundo, 40; el segundo
        no alcanza y se marca en la fila (sin bloquear el formulario)."""
        fila = suministros.datos_del_formulario(self.e.vendedor, self.datos([self.renglon(cantidad="60", cantidad_minima="1")])).filas[0]
        self.assertEqual([(p.cantidad, p.disponible, p.alcanza) for p in fila.periodos_de_la_ventana], [(60, 100, True), (60, 40, False)])
        self.assertIn("cantidad", fila.errores)

    def test_requisito_la_cantidad_de_consultas_no_depende_de_los_detalles(self):
        """Requisito «no más de 1 segundo»: `assertNumQueries` igual con 1 y con 4 detalles (una consulta por tabla, nada por renglón)."""
        direcciones = [self.otra_direccion() for _ in range(3)]
        uno = self.datos([self.renglon(0, cantidad="5", cantidad_minima="1")])
        cuatro = self.datos(
            [self.renglon(0, cantidad="5", cantidad_minima="1")]
            + [self.renglon(i + 1, cantidad="5", cantidad_minima="1", direccion_id=str(d.pk)) for i, d in enumerate(direcciones)]
        )
        suministros.datos_del_formulario(self.e.vendedor, uno)  # calienta cachés (configuración)
        with CaptureQueriesContext(connection) as con_uno:
            suministros.datos_del_formulario(self.e.vendedor, uno)
        with CaptureQueriesContext(connection) as con_cuatro:
            suministros.datos_del_formulario(self.e.vendedor, cuatro)
        self.assertEqual(len(con_uno), len(con_cuatro))


class VerificacionAcumuladaTests(BaseDePacto):
    """Extensión 9e y regla «Stock maduro libre para la fecha de un período»: verificación acumulada por variedad."""

    def con_periodo_largo(self, **extra):
        """Un detalle con un solo período en la ventana (el siguiente cae a los 33 días)."""
        return self.renglon(periodo="30", **extra)

    def test_ext_9e_un_periodo_sin_stock_suficiente_se_rechaza_con_la_cantidad_disponible(self):
        """Extensión 9e: `supera_disponible` en la cantidad del detalle con el disponible y la fecha en el mensaje."""
        error = self.rechazo(renglones=[self.con_periodo_largo(cantidad="101", cantidad_minima="1")])
        self.assertEqual(codigos_de(error, "detalle-0-cantidad"), ["supera_disponible"])
        mensaje = error.error_dict["detalle-0-cantidad"][0].message
        self.assertIn("100 plantas disponibles", mensaje)
        self.assertIn(f"{HOY + timedelta(days=3):%d/%m}", mensaje)
        self.assertEqual(Suministro.objects.count(), 0)

    def test_ext_9e_la_verificacion_es_acumulada_entre_los_detalles_de_la_misma_variedad(self):
        """Regla «Stock maduro libre»: dos detalles de la misma variedad (otra dirección) de 60 con 100 de stock: el segundo ve 40."""
        renglones = [
            self.con_periodo_largo(cantidad="60", cantidad_minima="1"),
            self.con_periodo_largo(indice=1, cantidad="60", cantidad_minima="1", direccion_id=str(self.otra_direccion().pk)),
        ]
        error = self.rechazo(renglones=renglones)
        self.assertEqual(codigos_de(error, "detalle-0-cantidad"), [])
        self.assertEqual(codigos_de(error, "detalle-1-cantidad"), ["supera_disponible"])
        self.assertIn("40 plantas disponibles", error.error_dict["detalle-1-cantidad"][0].message)

    def test_ext_9e_los_periodos_de_los_detalles_se_cubren_en_orden_de_fecha(self):
        """Patrón, sección 7: los períodos de todos los detalles de la variedad se verifican **en orden de fecha**, no de detalle: un
        detalle de 60 el día 3 y otro de 60 el día 5, el que va primero en el formulario no importa."""
        renglones = [
            self.con_periodo_largo(cantidad="60", cantidad_minima="1", primera_entrega=iso(5)),
            self.con_periodo_largo(indice=1, cantidad="60", cantidad_minima="1", primera_entrega=iso(3), direccion_id=str(self.otra_direccion().pk)),
        ]
        error = self.rechazo(renglones=renglones)
        self.assertEqual(codigos_de(error, "detalle-0-cantidad"), ["supera_disponible"])  # el del día 5 va después del del día 3
        self.assertEqual(codigos_de(error, "detalle-1-cantidad"), [])

    def test_ext_9e_un_periodo_fuera_de_la_ventana_no_verifica_stock(self):
        """Paso 14: solo los períodos que caen dentro de la ventana de pre-reserva se verifican y se reservan; uno fuera de ella se acepta sin
        stock, y no toma stock ni bloquea lotes (`assertNumQueries` menor que con períodos en la ventana)."""
        cosechas_antes = Cosecha.objects.count()
        s = self.pactar(renglones=[self.renglon(primera_entrega=iso(20), cantidad="5000", cantidad_minima="1")])
        self.assertEqual((s.periodos_reservados, ReservaStock.objects.count(), Cosecha.objects.count()), (0, 0, cosechas_antes))

    def test_ext_9e_sin_periodos_en_la_ventana_no_toma_stock_ni_bloquea_lotes(self):
        """Paso 14, `bloquear_candidatos`: sin períodos en la ventana no se lee ni se bloquea nada de lotes ni partidas."""
        with mock.patch.object(suministros.stock_maduro, "bloquear_candidatos") as bloquear, mock.patch.object(
            suministros.stock_maduro, "asignar"
        ) as asignar:
            self.pactar(renglones=[self.renglon(primera_entrega=iso(20))])
        bloquear.assert_not_called()
        asignar.assert_not_called()

    def test_regla_el_stock_de_otro_vendedor_no_cuenta(self):
        """Regla «Vendedor responsable»: el stock sale solo de los invernaderos del Vendedor del contrato; el de otro no alcanza."""
        otro = escenario_comercial(sufijo="2")
        lote_maduro(otro, 1000, variedad=self.e.variedad)
        error = self.rechazo(renglones=[self.con_periodo_largo(cantidad="101", cantidad_minima="1")])
        self.assertEqual(codigos_de(error, "detalle-0-cantidad"), ["supera_disponible"])

    def test_ext_14a_si_el_stock_cambio_no_se_registra_nada_e_informa_el_maximo(self):
        """Extensión 14a: lo que se veía ya no alcanza al confirmar (`stock_insuficiente` por detalle con la cantidad disponible); se revierte
        todo: suministro, cláusulas, detalles, reservas, cosechas, notificaciones y auditoría."""
        falso = {self.e.variedad.pk: [suministros.stock_maduro.Cobertura(HOY + timedelta(days=3), 500, 1000)]}
        with mock.patch.object(suministros.stock_maduro, "simular_varias", return_value=falso):
            with self.assertRaises(ValidationError) as contexto:
                self.pactar(renglones=[self.con_periodo_largo(cantidad="500", cantidad_minima="1")])
        error = contexto.exception
        self.assertEqual(codigos_de(error, "detalle-0-cantidad"), ["stock_insuficiente"])
        self.assertIn("100 plantas disponibles", error.error_dict["detalle-0-cantidad"][0].message)
        self.assertEqual(codigos_de(error, "__all__"), ["stock_insuficiente"])
        for modelo in (Suministro, ClausulaSuministrado, DetalleSuministro, ClausulaSuministrante, ReservaStock, DetalleReserva, Cosecha, Notificacion):
            self.assertEqual(modelo.objects.count(), 0, modelo.__name__)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="pacto_suministro").exists())

    def test_ext_14a_si_un_periodo_de_la_ventana_queda_sin_cubrir_se_revierte_todo(self):
        """14a con el segundo período: el primero se reserva y el segundo no alcanza (otro consumió el stock): no queda ni la primera reserva."""
        falso = {self.e.variedad.pk: [
            suministros.stock_maduro.Cobertura(HOY + timedelta(days=3), 30, 1000),
            suministros.stock_maduro.Cobertura(HOY + timedelta(days=10), 30, 1000),
        ]}
        reserva_de_periodo(
            detalle_suministro(suministro(self.e), self.e.variedad, direccion=self.e.direccion, cantidad=70, primera_en_dias=10),
            HOY + timedelta(days=10), [(self.lote, 70)],
        )
        with mock.patch.object(suministros.stock_maduro, "simular_varias", return_value=falso):
            error = self.rechazo(renglones=[self.renglon(continuar_superpuesto="1")])  # el otro contrato es del mismo par: se continúa igual
        self.assertEqual(codigos_de(error, "detalle-0-cantidad"), ["stock_insuficiente"])
        self.assertEqual(ReservaStock.objects.count(), 1)  # solo la del otro contrato, que ya estaba
        self.assertEqual(Suministro.objects.count(), 1)

    def test_regla_nunca_se_reserva_mas_que_el_stock_libre_de_un_lote(self):
        """Garantía mínima 3: dos pactos por lo que hay: el segundo no alcanza (`supera_disponible` con el máximo nuevo, 40)."""
        self.pactar(renglones=[self.con_periodo_largo(cantidad="60", cantidad_minima="1")])
        error = self.rechazo(renglones=[self.con_periodo_largo(cantidad="61", cantidad_minima="1", primera_entrega=iso(4))])
        self.assertEqual(error.error_dict["detalle-0-cantidad"][0].message.count("40 plantas disponibles"), 1)


class RenglonesEnBlancoTests(BaseDePacto):
    """Extensiones 7-11a y 12a (D-61, criterio de COM-02): los renglones en blanco se conservan en pantalla y se ignoran al resumir y registrar."""

    def test_ext_12a_sin_ningun_detalle_cargado_se_rechaza(self):
        """12a: `sin_detalles` en `__all__`, tanto sin renglones como con solo renglones en blanco."""
        for renglones in ([], [RenglonDeSuministro(indice=0)]):
            with self.subTest(renglones=len(renglones)):
                self.assertEqual(codigos_de(self.rechazo(renglones=renglones), "__all__"), ["sin_detalles"])

    def test_ext_7_11a_un_renglon_en_blanco_se_conserva_en_pantalla_sin_errores(self):
        """«Agregar detalle» suma un renglón en blanco: `datos_del_formulario` lo conserva, sin validarlo, y no cuenta como cargado."""
        formulario = suministros.datos_del_formulario(self.e.vendedor, self.datos([self.renglon(0), RenglonDeSuministro(indice=1)]))
        self.assertEqual(len(formulario.filas), 2)
        self.assertEqual(len(formulario.cargadas), 1)
        self.assertEqual(formulario.errores, {})

    def test_ext_7_11a_los_renglones_en_blanco_se_ignoran_al_resumir_y_al_registrar(self):
        """Los renglones vacíos no son detalles: al resumir y al registrar se ignoran (y el índice de los demás se conserva)."""
        datos = self.datos([RenglonDeSuministro(indice=0), self.renglon(1), RenglonDeSuministro(indice=2)])
        self.assertEqual(len(suministros.resumen(self.e.vendedor, datos).formulario.cargadas), 1)
        self.assertEqual(suministros.pactar_suministro(self.e.vendedor, datos).detalles.count(), 1)

    def test_ext_7_11a_quitar_un_detalle_recalcula_el_calendario_y_el_resumen(self):
        """7-11a: con un detalle menos, el formulario muestra solo el que queda."""
        dos = self.datos([self.renglon(0, cantidad="10"), self.renglon(1, cantidad="10", direccion_id=str(self.otra_direccion().pk))])
        self.assertEqual(len(suministros.datos_del_formulario(self.e.vendedor, dos).filas), 2)
        uno = self.datos([self.renglon(1, cantidad="10", direccion_id=str(self.otra_direccion().pk))])
        self.assertEqual([f.renglon.indice for f in suministros.datos_del_formulario(self.e.vendedor, uno).filas], [1])


class CorreccionesDelResumenTests(BaseDePacto):
    """Extensión 13a: lo que cambia al corregir un dato del resumen y vuelve a calcularse."""

    def test_ext_13a_1a_al_cambiar_el_vendedor_se_vuelve_a_verificar_el_stock_de_la_ventana(self):
        """13a.1a: el Gerente cambia al Vendedor responsable por otro sin stock: los detalles que ya no pueden cubrirse se informan (en el
        formulario y al revisar); los demás datos se conservan."""
        otro = escenario_comercial(sufijo="2")
        renglon = self.renglon(periodo="30", cantidad="30", cantidad_minima="1")
        con_el_primero = suministros.datos_del_formulario(self.gerente, self.datos([renglon], vendedor_id=str(self.e.vendedor.pk)))
        self.assertEqual(con_el_primero.filas[0].errores, {})
        con_el_otro = suministros.datos_del_formulario(self.gerente, self.datos([renglon], vendedor_id=str(otro.vendedor.pk)))
        self.assertIn("cantidad", con_el_otro.filas[0].errores)
        self.assertEqual(con_el_otro.datos.duracion, "6")
        error = self.rechazo(self.gerente, renglones=[renglon], vendedor_id=str(otro.vendedor.pk))
        self.assertEqual(codigos_de(error, "detalle-0-cantidad"), ["supera_disponible"])

    def test_ext_13a_1b_al_cambiar_el_cliente_se_descarta_la_direccion_de_cada_detalle(self):
        """13a.1b: la dirección elegida era del cliente anterior: en pantalla se descarta (sin error) y se ofrecen las del nuevo; al revisar,
        `direccion_no_valida`."""
        nuevo = crear_cliente(razon_social="Nuevo S.A.", email="nuevo@ejemplo.com")
        propia = direccion_de_cliente(nuevo).direccion
        datos = self.datos(cliente_id=str(nuevo.pk))
        formulario = suministros.datos_del_formulario(self.e.vendedor, datos)
        self.assertIsNone(formulario.filas[0].direccion)
        self.assertNotIn("direccion", formulario.filas[0].errores)
        self.assertEqual([d.pk for d in formulario.direcciones], [propia.pk])
        self.assertEqual(codigos_de(self.rechazo(cliente_id=str(nuevo.pk)), "detalle-0-direccion"), ["direccion_no_valida"])

    def test_ext_13a_1c_al_cambiar_la_duracion_se_recalculan_la_fecha_de_fin_y_el_calendario(self):
        """13a.1c: con una duración menor, se recalcula la fecha de fin y se vuelve a verificar la primera entrega y el calendario."""
        largo = suministros.datos_del_formulario(self.e.vendedor, self.datos([self.renglon(primera_entrega=iso(45))], duracion="6"))
        corto = suministros.datos_del_formulario(self.e.vendedor, self.datos([self.renglon(primera_entrega=iso(45))], duracion="1"))
        self.assertEqual((largo.fecha_fin, corto.fecha_fin), (calendario.sumar_meses(HOY, 6), calendario.sumar_meses(HOY, 1)))
        self.assertNotIn("primera_entrega", largo.filas[0].errores)
        self.assertIn("primera_entrega", corto.filas[0].errores)
        self.assertGreater(largo.filas[0].cantidad_de_entregas, 1)

    def test_regla_pantalla_no_estricto_lo_que_todavia_no_se_cargo_no_es_un_error(self):
        """Cada cambio de pantalla no valida lo que todavía no se eligió (sin cliente, sin fecha, sin precio): ningún error; el resumen sí."""
        vacio = suministros.datos_del_formulario(self.e.vendedor, DatosDeSuministro())
        self.assertEqual(vacio.errores, {})
        self.assertFalse(vacio.puede_revisar)
        self.assertTrue(suministros.datos_del_formulario(self.e.vendedor, self.datos()).puede_revisar)

    def test_regla_el_resumen_no_escribe_nada_y_trae_lo_que_se_va_a_pactar(self):
        """Paso 12: el resumen valida como al registrar y no escribe (ni reserva, ni audita, ni envía)."""
        resumen = suministros.resumen(self.e.vendedor, self.datos())
        self.assertEqual(resumen.formulario.cliente.pk, self.e.cliente.pk)
        self.assertEqual((Suministro.objects.count(), ReservaStock.objects.count(), RegistroAuditoria.objects.filter(accion="pacto_suministro").count()), (0, 0, 0))


class CambiosDuranteLaCargaTests(BaseDePacto):
    """Lo que cambia entre que se carga el pacto y se confirma (lo ve el registro después de bloquear)."""

    def entre_la_carga_y_la_confirmacion(self, cambio, actor=None, **extra):
        """Pacta con una función que corre ``cambio()`` justo después del análisis previo (antes de bloquear)."""
        real = suministros._analizar

        def con_cambio(*args, **kwargs):
            resultado = real(*args, **kwargs)
            cambio()
            return resultado

        with mock.patch.object(suministros, "_analizar", side_effect=con_cambio), self.assertRaises(ValidationError) as contexto:
            self.pactar(actor, **extra)
        return contexto.exception

    def test_regla_cliente_dado_de_baja_entre_la_carga_y_la_confirmacion(self):
        """Bloqueos, nivel 2b: `cliente_inactivo` («El cliente se dio de baja mientras cargabas el contrato.»); no queda nada."""
        error = self.entre_la_carga_y_la_confirmacion(lambda: Cliente.objects.filter(pk=self.e.cliente.pk).update(estado_cliente="inactivo"))
        self.assertEqual(codigos_de(error, "cliente"), ["cliente_inactivo"])
        self.assertEqual(Suministro.objects.count(), 0)

    def test_regla_cliente_que_perdio_el_correo_entre_la_carga_y_la_confirmacion(self):
        """Regla 18 de 8.20, vuelta a verificar tras bloquear el cliente: `cliente_sin_correo`; no queda nada."""
        error = self.entre_la_carga_y_la_confirmacion(lambda: Cliente.objects.filter(pk=self.e.cliente.pk).update(email_cliente=""))
        self.assertEqual(codigos_de(error, "cliente"), ["cliente_sin_correo"])
        self.assertEqual(Suministro.objects.count(), 0)

    def test_regla_direccion_desactivada_entre_la_carga_y_la_confirmacion(self):
        """Bloqueos: la dirección de cada detalle sigue activa y es del cliente (`direccion_no_valida`, en el campo de ese detalle)."""
        error = self.entre_la_carga_y_la_confirmacion(lambda: Direccion.objects.filter(pk=self.e.direccion.pk).update(estado_direccion="inactivo"))
        self.assertEqual(codigos_de(error, "detalle-0-direccion"), ["direccion_no_valida"])
        self.assertEqual(Suministro.objects.count(), 0)

    def test_regla_variedad_dada_de_baja_entre_la_carga_y_la_confirmacion(self):
        """Bloqueos, nivel 3: la variedad sigue activa (`variedad_inactiva`); no queda nada."""
        error = self.entre_la_carga_y_la_confirmacion(lambda: type(self.e.variedad).objects.filter(pk=self.e.variedad.pk).update(estado_variedad="inactivo"))
        self.assertEqual(codigos_de(error, "detalle-0-variedad"), ["variedad_inactiva"])
        self.assertEqual(Suministro.objects.count(), 0)

    def test_regla_vendedor_dado_de_baja_entre_la_carga_y_la_confirmacion(self):
        """Bloqueos, nivel 1: el Vendedor responsable (elegido por el Gerente) sigue activo (`vendedor_inactivo`)."""
        error = self.entre_la_carga_y_la_confirmacion(
            lambda: type(self.e.vendedor).objects.filter(pk=self.e.vendedor.pk).update(is_active=False),
            actor=self.gerente, vendedor_id=str(self.e.vendedor.pk),
        )
        self.assertEqual(codigos_de(error, "vendedor"), ["vendedor_inactivo"])
        self.assertEqual(Suministro.objects.count(), 0)

    def test_regla_invernaderos_del_vendedor_que_cambiaron_entre_la_carga_y_la_confirmacion(self):
        """Paso 14: si cambiaron los invernaderos del Vendedor mientras se cargaba (uno nuevo), `cambio_simultaneo`: se vuelve a intentar."""
        from comercial.tests.fabricas import segundo_invernadero

        error = self.entre_la_carga_y_la_confirmacion(lambda: segundo_invernadero(self.e))
        self.assertIn("cambio_simultaneo", todos_los_codigos(error))
        self.assertEqual(Suministro.objects.count(), 0)

    def test_regla_sin_invernaderos_activos_el_vendedor_no_puede_pactar_ni_con_la_pantalla_vieja(self):
        """Precondición b, también al confirmar: un Vendedor sin invernaderos activos recibe `vendedor_sin_invernaderos`; no queda nada."""
        error = self.entre_la_carga_y_la_confirmacion(
            lambda: type(self.e.invernadero).objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        )
        self.assertIn("vendedor_sin_invernaderos", todos_los_codigos(error))
        self.assertEqual(Suministro.objects.count(), 0)


class ComprobanteTests(BaseDePacto):
    """Paso 15 y extensión 15a (D-14, D-54): el comprobante del suministro, fuera de la transacción."""

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_g_con_correo_el_comprobante_sale_y_el_suministro_queda_enviado(self):
        """Postcondición g y paso 15: se envía al cliente el comprobante (asunto «Comprobante de tu suministro SUM-…», plantilla del
        suministro); `estado_comprobante = enviado`."""
        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", return_value=True) as enviar:
            s = self.pactar()
        cuenta, asunto, plantilla, contexto = enviar.call_args.args
        self.assertEqual((cuenta.email, cuenta.pk), (self.e.cliente.email_cliente, self.e.cliente.pk))
        self.assertEqual(asunto, f"Comprobante de tu suministro {s.codigo}")
        self.assertEqual(plantilla, "comercial/correos/comprobante_suministro.txt")
        self.assertEqual(contexto["suministro"].pk, s.pk)
        self.assertEqual(s.estado_comprobante, "enviado")
        self.assertEqual(Suministro.objects.get(pk=s.pk).estado_comprobante, "enviado")

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_15a_si_el_correo_falla_el_suministro_queda_registrado_con_el_comprobante_pendiente(self):
        """Extensión 15a: el contrato permanece registrado; `pendiente_envio` (el reintento es manual: «Reenviar comprobante»)."""
        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", return_value=False):
            s = self.pactar()
        self.assertEqual(Suministro.objects.get(pk=s.pk).estado_comprobante, "pendiente_envio")

    def test_ext_15a_sin_el_correo_del_sistema_configurado_queda_pendiente_de_envio(self):
        """Extensión 15a: con el correo del sistema sin configurar (las pruebas lo apagan), `pendiente_envio`."""
        self.assertEqual(self.pactar().estado_comprobante, "pendiente_envio")

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_15a_si_pacto_el_gerente_el_vendedor_recibe_el_aviso_del_comprobante_pendiente(self):
        """15a: si pactó el Gerente, el Vendedor responsable recibe «El comprobante de SUM-… quedó pendiente de envío.»."""
        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", return_value=False):
            s = self.pactar(self.gerente, vendedor_id=str(self.e.vendedor.pk))
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor, titulo="Comprobante pendiente de envío")
        self.assertEqual(aviso.detalle, f"El comprobante de {s.codigo} quedó pendiente de envío.")

    @override_settings(CORREO_CONFIGURADO=True)
    def test_requisito_el_correo_sale_fuera_de_la_transaccion(self):
        """D-14, D-54 y criterio de COM-02: el correo se manda después de confirmar, nunca con los bloqueos tomados (la profundidad de
        bloques atómicos es la de la prueba)."""
        base = len(connection.savepoint_ids)

        def enviar(*args):
            self.assertEqual(len(connection.savepoint_ids), base)
            return True

        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", side_effect=enviar) as simulado:
            self.pactar()
        simulado.assert_called_once()

    def test_regla_si_el_pacto_se_revierte_no_sale_ningun_correo(self):
        """Garantía mínima: un pacto rechazado no manda el comprobante."""
        with override_settings(CORREO_CONFIGURADO=True), mock.patch("comercial.servicios.comprobantes.correo.enviar_correo") as enviar:
            self.rechazo(renglones=[self.renglon(cantidad="5000", cantidad_minima="1")])
        enviar.assert_not_called()

    def test_regla_el_comprobante_dice_el_contrato_las_clausulas_y_el_calendario_resumido(self):
        """Variación 15a: cliente, Vendedor, duración y vigencia, tolerados, multa, cláusula del suministrado y, por detalle, variedad,
        dirección, cantidad, período, **calendario resumido** (primera y última fecha, cantidad de entregas y tramos de precio, no cada
        fecha), precio y mecanismo y su cláusula del suministrante."""
        s = self.pactar(renglones=[self.renglon(mecanismo="ajuste_periodico", porcentaje="3", meses="2", periodo="30", primera_entrega=iso(0), precio="1000")])
        contexto = suministros.datos_del_comprobante(s)
        self.assertEqual((contexto["suministro"].pk, contexto["cliente"].pk, contexto["clausula"].plazo_pago_dias), (s.pk, self.e.cliente.pk, 15))
        (fila,) = contexto["filas"]
        self.assertEqual(fila.primera_fecha, HOY)
        self.assertEqual(fila.ultima_fecha, calendario.calendario(s.detalles.get())[-1])
        self.assertEqual(fila.cantidad_de_entregas, len(calendario.calendario(s.detalles.get())))
        self.assertEqual([p for _, p in fila.tramos_de_precio], [Decimal("1000.00"), Decimal("1030.00"), Decimal("1060.90")])
        self.assertEqual(fila.clausula.cantidad_minima, 10)

    def test_regla_el_texto_del_correo_trae_el_codigo_y_aclara_que_no_tiene_validez_fiscal(self):
        """Variación 15a: el texto del correo aclara que es un comprobante interno sin validez fiscal y trae el código del contrato."""
        from django.template.loader import render_to_string

        s = self.pactar()
        texto = render_to_string("comercial/correos/comprobante_suministro.txt", suministros.datos_del_comprobante(s))
        self.assertIn(s.codigo, texto)
        self.assertIn("Comprobante interno, sin validez fiscal.", texto)
        self.assertIn("Lechuga", texto)

    def test_regla_reenviar_el_comprobante_de_un_suministro_funciona_como_el_de_una_compra_venta(self):
        """«Reenviar comprobante» (15a): el Vendedor responsable o el Gerente, solo desde «pendiente de envío»; sin auditoría; con otro
        Vendedor, `PermissionDenied`."""
        s = self.pactar()
        antes = RegistroAuditoria.objects.count()
        with override_settings(CORREO_CONFIGURADO=True), mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", return_value=True) as enviar:
            self.assertEqual(comprobantes.reenviar_comprobante(self.e.vendedor, s.pk), "enviado")
        self.assertEqual(enviar.call_args.args[1], f"Comprobante de tu suministro {s.codigo}")
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
        with self.assertRaises(PermissionDenied):
            comprobantes.reenviar_comprobante(crear_vendedor(email="otro@infoponia.com"), s.pk)


class PlanificacionDeLaEntregaTests(BaseDePacto):
    """Postcondición f (COM-05a1; D-66 punto 5): cada período que salió todo de cámara programa su entrega con `on_commit`."""

    def test_post_f_los_periodos_que_salen_de_camara_programan_su_entrega_despues_de_confirmar(self):
        """Postcondición f: un período por fecha (los de la ventana: a los 3 y a los 10 días) con todas sus reservas «lista para entrega»: una entrega por período, después de confirmar."""
        from comercial.models import Entrega
        from comercial.tests.fabricas import partida_cosechada, transportista_con_vehiculo

        partida_cosechada(self.lote, 100)
        transportista_con_vehiculo(self.e.invernadero, "800")
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            suministro = self.pactar()
            self.assertEqual(Entrega.objects.count(), 0)
        for callback in callbacks:
            callback()
        self.assertEqual(sorted(e.fecha_programada_orden for e in Entrega.objects.filter(contrato_entrega_id=suministro.pk)), [HOY + timedelta(days=3), HOY + timedelta(days=10)])
