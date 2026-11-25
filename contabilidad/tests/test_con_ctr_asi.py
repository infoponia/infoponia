# Pruebas de CON-CTR-ASI «Contraasentar Asiento» (CON-03b paso 2; docs/casos_de_uso/contabilidad/asientos_manuales.md; D-84 puntos 1, 2, 4, 5 y 9; D-85 puntos 5 y 7; D-42; D-30):
# `asientos.contraasentar`, `asientos.resumir_contraasiento` y `asientos.datos_para_correccion`. Cada prueba arma sus datos y recibe «hoy».
# Escenario común: ejercicio cerrado (2025), en cierre (2026) y abierto (2027); hoy es el 10/3/2027. El asiento a anular es un manual del 1/2/2027 en el abierto.
# La concurrencia está en `test_asientos_concurrencia.py` y las pantallas en `test_asientos_vistas.py`.
#
# Contrato que fijan estas pruebas (lo implementa el paso 2; lo del paso 1 —`ErrorContable.errores`, `ErroresContables`, `_bloquear_ejercicio`— ya existe):
#   - `contraasentar(actor, asiento_id, fecha, descripcion, *, hoy=None) -> AsientoContable` (el contraasiento). `descripcion` es el motivo y queda como descripción.
#   - `asiento_no_anulable` (campo `None`) cuando el asiento es un contraasiento o ya tiene el suyo; en el segundo caso el mensaje nombra el contraasiento (N.º)
#     y `datos` trae `contraasiento_ejercicio_id` y `contraasiento_numero`. Un asiento inexistente es `Http404`.
#   - `asientos._bloquear_asiento(asiento_id)` bloquea y devuelve el asiento releído; se llama ANTES que `_bloquear_ejercicio` (docs/patrones/asientos.md, sección 2).
#   - El aviso se crea con `core.notificaciones.notificar_a_varios([gerente], titulo, detalle, excluir=actor)` (se llama por el módulo, así se puede reemplazar).
#   - `resumir_contraasiento(actor, asiento_id, fecha, descripcion, *, hoy=None) -> ResumenDeContraasiento` con `asiento` (el que se anula), `ejercicio_numero`,
#     `ejercicio_inicio`, `ejercicio_cierre`, `ejercicio_estado`, `ejercicio_por_abrir`, `lineas` (las INVERTIDAS, `LineaDeResumen`), `total` y `es_automatico`.
#     No escribe, no audita y no bloquea nada.
#   - `datos_para_correccion(actor, asiento_id) -> {"descripcion", "movimientos", "numero_anulado"}` con las líneas del asiento anulado (no las invertidas).
import datetime
from decimal import Decimal
from unittest import mock

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, EjercicioContable, MovimientoContable, OrigenDocumento
from contabilidad.servicios import asientos, ejercicios
from contabilidad.tests.fabricas import (
    PlanDeCuentasMixin,
    asiento_de_prueba,
    ejercicio,
    origen_de_prueba,
    verificar_invariantes_contables,
)
from core.models import Agronomo, Contador, Gerente, Notificacion, RegistroAuditoria, Vendedor
from core.tests.fabricas import crear_cuenta

Estado = EjercicioContable.Estado
Accion = RegistroAuditoria.Accion
HOY = datetime.date(2027, 3, 10)
FECHA = datetime.date(2027, 3, 1)  # distinta de hoy: así se ve que el aviso usa la fecha del contraasiento
EN_EL_EN_CIERRE = datetime.date(2026, 12, 1)
EN_EL_CERRADO = datetime.date(2025, 6, 1)
ANTES_DEL_PRIMERO = datetime.date(2024, 6, 1)
MOTIVO = "Se cargó un importe de más"
MOVIMIENTOS = [
    (cuentas.GASTOS_GENERALES, DEBE, Decimal("1000.00")),
    (cuentas.INSUMOS_EN_STOCK, DEBE, Decimal("500.50")),
    (cuentas.CAJA, HABER, Decimal("1500.50")),
]


def _errores(error):
    return [(e.codigo, e.campo) for e in error.errores]


class FalloDePrueba(Exception):
    """Fallo forzado en una prueba de «todo o nada»."""


class ConCtrAsiBase(PlanDeCuentasMixin, TestCase):
    """Cuentas, ejercicios y un asiento manual a anular; ayudas para llamar al servicio con `hoy` fijo."""

    def setUp(self):
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com", nombre="Cora", apellido="Díaz")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com", nombre="Gabriela", apellido="Sosa")
        self.cerrado = ejercicio(Estado.CERRADO, datetime.date(2025, 1, 1))
        self.en_cierre = ejercicio(Estado.EN_CIERRE, datetime.date(2026, 1, 1))
        self.abierto = ejercicio(Estado.ABIERTO, datetime.date(2027, 1, 1))
        self.original = asiento_de_prueba(self.abierto, datetime.date(2027, 2, 1), MOVIMIENTOS, descripcion="Pago de la luz")

    def contraasentar(self, actor=None, asiento=None, fecha=FECHA, motivo=MOTIVO, **extra):
        return asientos.contraasentar(actor or self.contador, (asiento or self.original).pk, fecha, motivo, **{"hoy": HOY, **extra})

    def resumir(self, actor=None, asiento=None, fecha=FECHA, motivo=MOTIVO, **extra):
        return asientos.resumir_contraasiento(actor or self.contador, (asiento or self.original).pk, fecha, motivo, **{"hoy": HOY, **extra})

    def recargar(self, ej):
        return EjercicioContable.objects.get(pk=ej.pk)

    def assert_sin_contraasiento(self):
        """Garantías mínimas: el asiento no quedó anulado, no hay otro asiento, el número no se consumió y no hay avisos ni auditoría nueva."""
        self.assertEqual(AsientoContable.objects.count(), 1)
        self.assertFalse(AsientoContable.objects.filter(anula__isnull=False).exists())
        self.assertEqual(self.recargar(self.abierto).ultimo_numero_asiento, 1)
        self.assertFalse(Notificacion.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.filter(accion__in=[Accion.ALTA_ASIENTO_CONTABLE, Accion.ALTA_MOVIMIENTO_CONTABLE]).exists())


class ConCtrAsiQuienRegistraTests(ConCtrAsiBase):
    """Precondición a, regla «Quién registra» y extensión 1a."""

    def test_regla_quien_registra_el_contador_activo_contraasienta(self):
        """Regla «Quién registra»: el Contador activo contraasienta."""
        contraasiento = self.contraasentar(self.contador)

        self.assertEqual(contraasiento.anula_id, self.original.pk)
        verificar_invariantes_contables()

    def test_ext_1a_el_gerente_contraasienta_sin_contador_activo_y_queda_como_autor(self):
        """Extensión 1a, puntos 1 y 2: sin Contador activo contraasienta el Gerente y la auditoría lo deja como autor, con rol Gerente."""
        Contador.objects.update(is_active=False)

        contraasiento = self.contraasentar(self.gerente)

        registro = RegistroAuditoria.objects.get(accion=Accion.ALTA_ASIENTO_CONTABLE, afectados__contains=[{"id": contraasiento.pk}])
        self.assertEqual((registro.usuario_id, registro.rol), (self.gerente.pk, "gerente"))

    def test_ext_1a_el_gerente_con_contador_activo_no_contraasienta(self):
        """Extensión 1a, punto 4: con un Contador activo el Gerente no contraasienta («Lo registra el Contador»); no se escribe nada."""
        with self.assertRaises(PermissionDenied) as contexto:
            self.contraasentar(self.gerente)

        self.assertIn("Lo registra el Contador", str(contexto.exception))
        self.assert_sin_contraasiento()

    def test_regla_quien_registra_el_vendedor_y_los_demas_no_contraasientan(self):
        """Regla «Quién registra» (X3, D-85 punto 8): ni el Vendedor ni otro rol, aunque no haya Contador activo."""
        Contador.objects.update(is_active=False)
        for actor in (crear_cuenta(Vendedor, email="v@infoponia.com"), crear_cuenta(Agronomo, email="a@infoponia.com")):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                self.contraasentar(actor)
        with self.assertRaises(PermissionDenied):
            asientos.contraasentar(None, self.original.pk, FECHA, MOTIVO, hoy=HOY)
        self.assert_sin_contraasiento()

    def test_regla_d30_el_actor_que_deja_de_ser_responsable_mientras_espera_no_contraasienta(self):
        """D-30 punto 3: se vuelve a verificar que quien actúa siga siendo el responsable antes de bloquear nada."""

        def da_de_baja_al_contador(*args, **kwargs):
            Contador.objects.update(is_active=False)

        with mock.patch.object(ejercicios, "abrir_ejercicio_si_corresponde", side_effect=da_de_baja_al_contador):
            with self.assertRaises(PermissionDenied):
                self.contraasentar(self.contador)
        self.assert_sin_contraasiento()


class ConCtrAsiQueSeAnulaTests(ConCtrAsiBase):
    """Regla «Qué se anula» (R161; reglas 15 y 17 de 8.20) y extensión 1b."""

    def test_regla_que_se_anula_un_asiento_automatico_tambien_se_anula(self):
        """Regla «Qué se anula»: cualquier asiento, manual o automático. El contraasiento NO tiene origen: no revierte la operación (C5, «Sin efecto operativo»)."""
        origen = origen_de_prueba()
        automatico = asiento_de_prueba(self.abierto, datetime.date(2027, 2, 2), origen=origen)
        documentos = OrigenDocumento.objects.count()

        contraasiento = self.contraasentar(asiento=automatico)

        self.assertEqual(contraasiento.anula_id, automatico.pk)
        self.assertIsNone(contraasiento.origen_id)
        self.assertEqual(OrigenDocumento.objects.count(), documentos)
        self.assertEqual(AsientoContable.objects.get(pk=automatico.pk).origen_id, origen.pk)  # el original sigue igual
        verificar_invariantes_contables()

    def test_regla_que_se_anula_un_asiento_de_un_ejercicio_cerrado_tambien_se_anula(self):
        """Regla «Qué se anula» y C3: lo que se mira es la fecha del contraasiento, no el ejercicio del original; uno de un ejercicio cerrado se contraasienta con fecha en uno abierto."""
        viejo = asiento_de_prueba(self.cerrado, datetime.date(2025, 6, 1), MOVIMIENTOS, descripcion="Gasto de 2025")

        contraasiento = self.contraasentar(asiento=viejo, fecha=FECHA)

        self.assertEqual(contraasiento.ejercicio_id, self.abierto.pk)
        self.assertEqual(contraasiento.anula_id, viejo.pk)
        self.assertEqual(self.recargar(self.cerrado).ultimo_numero_asiento, 1)  # el ejercicio cerrado no se toca
        verificar_invariantes_contables()

    def test_ext_1b_un_contraasiento_no_se_anula(self):
        """Extensión 1b y regla 17 de 8.20: un contraasiento no se anula; el mensaje lo explica."""
        contraasiento = self.contraasentar()

        with self.assertRaises(ErrorContable) as contexto:
            self.contraasentar(asiento=contraasiento)

        self.assertEqual(_errores(contexto.exception), [("asiento_no_anulable", None)])
        self.assertIn("contraasiento", contexto.exception.mensaje)
        self.assertEqual(AsientoContable.objects.count(), 2)

    def test_ext_1b_un_asiento_ya_anulado_no_se_anula_dos_veces_y_se_muestra_su_contraasiento(self):
        """Extensión 1b y 6a (R161): un asiento se anula una sola vez; el mensaje y `datos` nombran el contraasiento que ya tiene."""
        primero = self.contraasentar()

        with self.assertRaises(ErrorContable) as contexto:
            self.contraasentar()

        self.assertEqual(contexto.exception.codigo, "asiento_no_anulable")
        self.assertIn(f"N.º {primero.numero_asiento}", contexto.exception.mensaje)
        self.assertEqual(contexto.exception.datos, {"contraasiento_ejercicio_id": primero.ejercicio_id, "contraasiento_numero": primero.numero_asiento})
        self.assertEqual(AsientoContable.objects.count(), 2)
        self.assertEqual(self.recargar(self.abierto).ultimo_numero_asiento, 2)  # no se consumió otro número

    def test_ext_6a_otro_usuario_lo_anula_mientras_se_esperaba_el_bloqueo(self):
        """Extensión 6a: si al bloquear el asiento ya tiene contraasiento (lo anuló otro usuario), no se registra nada y se informa cuál es."""
        bloquear = asientos._bloquear_asiento

        def otro_usuario_lo_anula_justo_antes(pk):
            asiento_de_prueba(self.recargar(self.abierto), datetime.date(2027, 3, 2), anula=self.original, descripcion="Anulado por otro")
            return bloquear(pk)

        with mock.patch.object(asientos, "_bloquear_asiento", side_effect=otro_usuario_lo_anula_justo_antes):
            with self.assertRaises(ErrorContable) as contexto:
                self.contraasentar()

        self.assertEqual(contexto.exception.codigo, "asiento_no_anulable")
        self.assertIn("N.º 2", contexto.exception.mensaje)
        # No se cuenta aquí: el «otro usuario» se simula dentro de la transacción del servicio, que el rechazo deshace; el real ya habría confirmado. Que no
        # se creó el nuestro lo prueba el mensaje (nombra el N.º 2, que es el del otro) y la prueba de concurrencia real (`test_asientos_concurrencia.py`).
        self.assertIsNone(contexto.exception.__cause__)  # sale de la verificación posterior al bloqueo, no de una restricción de la base

    def test_ext_1b_un_asiento_inexistente_es_404(self):
        """Un asiento que no existe es `Http404`, no un error de base."""
        with self.assertRaises(Http404):
            asientos.contraasentar(self.contador, 987654, FECHA, MOTIVO, hoy=HOY)


class ConCtrAsiDatosYFechaTests(ConCtrAsiBase):
    """Regla «Motivo» (extensión 3a), regla «Ejercicio y fecha» (C2, C3; extensiones 3b y 3c), «Numeración» (H8) y los bloqueos."""

    def test_ext_3a_falta_el_motivo(self):
        """Extensión 3a y regla «Motivo»: el motivo (la descripción del contraasiento) es obligatorio; uno vacío o de espacios se rechaza en el campo `descripcion`."""
        for motivo in ("", "   ", None):
            with self.subTest(motivo=motivo), self.assertRaises(ErrorContable) as contexto:
                self.contraasentar(motivo=motivo)
            self.assertEqual(_errores(contexto.exception), [("descripcion_obligatoria", "descripcion")])
        self.assert_sin_contraasiento()

    def test_regla_motivo_de_mas_de_300_caracteres_se_rechaza(self):
        """Modelo `descripcion_asiento` (máximo 300): un motivo más largo se rechaza con un mensaje."""
        with self.assertRaises(ErrorContable) as contexto:
            self.contraasentar(motivo="m" * 301)
        self.assertEqual(contexto.exception.codigo, "descripcion_muy_larga")
        self.assert_sin_contraasiento()

    def test_regla_ejercicio_y_fecha_la_fecha_de_hoy_es_valida_y_va_al_abierto(self):
        """Regla «Ejercicio y fecha»: por defecto hoy; va al ejercicio abierto que la contiene."""
        contraasiento = self.contraasentar(fecha=HOY)

        self.assertEqual((contraasiento.fecha_asiento, contraasiento.ejercicio_id), (HOY, self.abierto.pk))

    def test_ext_3b_la_fecha_en_un_ejercicio_en_cierre_se_acepta(self):
        """Extensión 3b y C3: el contraasiento puede caer en el ejercicio en cierre (distinto del del asiento original); lleva el número de ese ejercicio."""
        contraasiento = self.contraasentar(fecha=EN_EL_EN_CIERRE)

        self.assertEqual(contraasiento.ejercicio_id, self.en_cierre.pk)
        self.assertEqual(contraasiento.numero_asiento, 1)
        self.assertEqual(self.recargar(self.en_cierre).ultimo_numero_asiento, 1)
        self.assertEqual(self.recargar(self.abierto).ultimo_numero_asiento, 1)  # el del original, sin tocar
        verificar_invariantes_contables()

    def test_ext_3c_la_fecha_en_un_ejercicio_cerrado_anterior_o_futura_se_rechaza(self):
        """Extensión 3c y C2: una fecha en un ejercicio cerrado, anterior al primer ejercicio o posterior a hoy se rechaza con su código y un mensaje que explica el motivo."""
        casos = [
            (EN_EL_CERRADO, "fecha_en_ejercicio_cerrado"),
            (ANTES_DEL_PRIMERO, "fecha_anterior_al_primer_ejercicio"),
            (HOY + datetime.timedelta(days=1), "fecha_futura"),
        ]
        for fecha, codigo in casos:
            with self.subTest(codigo=codigo), self.assertRaises(ErrorContable) as contexto:
                self.contraasentar(fecha=fecha)
            self.assertEqual(_errores(contexto.exception), [(codigo, "fecha")])
        self.assert_sin_contraasiento()

    def test_regla_h8_el_contraasiento_toma_el_numero_siguiente_del_ejercicio(self):
        """Regla «Numeración» (H8): el siguiente al último del ejercicio, correlativo y sin hueco."""
        otro = asiento_de_prueba(self.abierto, datetime.date(2027, 2, 3), MOVIMIENTOS, descripcion="Otro gasto")

        primero = self.contraasentar()
        segundo = self.contraasentar(asiento=otro)

        self.assertEqual((primero.numero_asiento, segundo.numero_asiento), (3, 4))
        self.assertEqual(self.recargar(self.abierto).ultimo_numero_asiento, 4)
        verificar_invariantes_contables()

    def test_regla_bloqueos_se_bloquea_primero_el_asiento_y_despues_el_ejercicio(self):
        """Requisitos especiales y docs/patrones/asientos.md, sección 2: el asiento a anular se bloquea ANTES que el ejercicio, que es siempre lo último."""
        orden = []
        bloquear_asiento, bloquear_ejercicio = asientos._bloquear_asiento, asientos._bloquear_ejercicio

        def asiento(pk):
            orden.append("asiento")
            return bloquear_asiento(pk)

        def ejercicio_(pk):
            orden.append("ejercicio")
            return bloquear_ejercicio(pk)

        with mock.patch.object(asientos, "_bloquear_asiento", side_effect=asiento), mock.patch.object(asientos, "_bloquear_ejercicio", side_effect=ejercicio_):
            self.contraasentar()

        self.assertEqual(orden, ["asiento", "ejercicio"])

    def test_ext_6b_el_ejercicio_cambia_de_estado_mientras_se_registra(self):
        """Extensión 6b: si al bloquear el ejercicio destino ya pasó a «cerrado», no se registra nada, el asiento no queda anulado y se informa `cambio_simultaneo`."""
        bloquear = asientos._bloquear_ejercicio

        def cierran_el_ejercicio_justo_antes_de_bloquearlo(pk):
            EjercicioContable.objects.filter(pk=pk).update(estado_ejercicio=Estado.CERRADO)
            return bloquear(pk)

        with mock.patch.object(asientos, "_bloquear_ejercicio", side_effect=cierran_el_ejercicio_justo_antes_de_bloquearlo):
            with self.assertRaises(ErrorContable) as contexto:
                self.contraasentar(fecha=EN_EL_EN_CIERRE)

        self.assertEqual(contexto.exception.codigo, "cambio_simultaneo")
        self.assertIn("cerrado", contexto.exception.mensaje)
        self.assertEqual(AsientoContable.objects.count(), 1)
        self.assertEqual(self.recargar(self.en_cierre).ultimo_numero_asiento, 0)
        self.assertFalse(Notificacion.objects.exists())


class ConCtrAsiPostcondicionesTests(ConCtrAsiBase):
    """Postcondiciones a a e y «Sin efecto operativo» (CON-CTR-ASI)."""

    def test_flujo_principal_el_contador_anula_un_asiento_erroneo(self):
        """Flujo principal (pasos 3 a 8): el contraasiento queda registrado, vinculado al asiento anulado, y el original queda marcado como anulado."""
        contraasiento = self.contraasentar()

        anulado = AsientoContable.objects.get(pk=self.original.pk)
        self.assertEqual(anulado.contraasiento.pk, contraasiento.pk)
        self.assertEqual(contraasiento.tipo, AsientoContable.Tipo.CONTRAASIENTO)
        verificar_invariantes_contables()

    def test_post_a_numero_fecha_descripcion_vinculo_y_sin_origen(self):
        """Postcondición a: número siguiente del ejercicio, la fecha indicada, el motivo como descripción, vinculado al asiento anulado (R161) y sin documento de origen."""
        contraasiento = self.contraasentar(motivo="  " + MOTIVO + " ")

        self.assertEqual(
            (contraasiento.numero_asiento, contraasiento.fecha_asiento, contraasiento.descripcion_asiento, contraasiento.anula_id, contraasiento.origen_id),
            (2, FECHA, MOTIVO, self.original.pk, None),
        )

    def test_post_b_los_movimientos_son_los_del_anulado_con_debe_y_haber_invertidos(self):
        """Postcondición b y regla «Movimientos» (regla 17 de 8.20): misma cuenta y mismo importe, Debe y Haber invertidos; el usuario no los carga."""
        contraasiento = self.contraasentar()

        invertidos = [(m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in contraasiento.movimientos.select_related("cuenta").order_by("id")]
        self.assertEqual(
            invertidos,
            [(cuentas.GASTOS_GENERALES, HABER, Decimal("1000.00")), (cuentas.INSUMOS_EN_STOCK, HABER, Decimal("500.50")), (cuentas.CAJA, DEBE, Decimal("1500.50"))],
        )

    def test_post_b_el_asiento_anulado_y_sus_movimientos_no_se_modifican(self):
        """«Además»: no se modifica ni se elimina el asiento anulado ni sus movimientos."""
        antes = [(m.pk, m.cuenta_id, m.tipo_movimiento, m.importe_movimiento) for m in self.original.movimientos.order_by("id")]

        self.contraasentar()

        original = AsientoContable.objects.get(pk=self.original.pk)
        despues = [(m.pk, m.cuenta_id, m.tipo_movimiento, m.importe_movimiento) for m in original.movimientos.order_by("id")]
        self.assertEqual(despues, antes)
        self.assertEqual((original.numero_asiento, original.descripcion_asiento), (1, "Pago de la luz"))

    def test_post_c_el_ejercicio_guarda_el_nuevo_ultimo_numero(self):
        """Postcondición c: el ejercicio que contiene al contraasiento guarda el nuevo último número."""
        self.contraasentar()

        self.assertEqual(self.recargar(self.abierto).ultimo_numero_asiento, 2)

    def test_post_d_se_notifica_al_gerente_con_el_texto_del_extracto(self):
        """Postcondición d y paso 7: el Gerente recibe el aviso «Contraasiento N.º X del asiento N.º Y» con quién lo registró, la fecha y el motivo."""
        contraasiento = self.contraasentar(self.contador)

        aviso = Notificacion.objects.get()
        self.assertEqual(aviso.destinatario_id, self.gerente.pk)
        self.assertEqual(aviso.titulo, f"Contraasiento N.º {contraasiento.numero_asiento} del asiento N.º {self.original.numero_asiento}")
        self.assertEqual(aviso.detalle, f"Lo registró Cora Díaz el 01/03/2027. Motivo: {MOTIVO}")

    def test_post_d_el_gerente_que_contraasienta_no_se_notifica_a_si_mismo(self):
        """Postcondición d (salvo que lo haya registrado él mismo) y extensión 1a, punto 3: sin Contador activo, el Gerente no recibe aviso de lo suyo (H21)."""
        Contador.objects.update(is_active=False)

        self.contraasentar(self.gerente)

        self.assertFalse(Notificacion.objects.exists())

    def test_ext_7a_sin_gerente_activo_el_contraasiento_queda_y_se_deja_constancia_en_la_auditoria(self):
        """Extensión 7a: sin Gerente activo no se puede avisar; el contraasiento permanece registrado y la auditoría deja `datos.aviso_al_gerente`."""
        Gerente.objects.update(is_active=False)

        contraasiento = self.contraasentar()

        self.assertFalse(Notificacion.objects.exists())
        registro = RegistroAuditoria.objects.get(accion=Accion.ALTA_ASIENTO_CONTABLE, afectados__contains=[{"id": contraasiento.pk}])
        self.assertEqual(registro.detalle["datos"], {"aviso_al_gerente": "no enviado: sin Gerente activo"})

    def test_post_e_se_audita_el_contraasiento_sus_movimientos_y_el_vinculo(self):
        """Postcondición e: un registro por el contraasiento (con el vínculo `anula`), uno por cada movimiento y todos con usuario y rol."""
        contraasiento = self.contraasentar()

        registro = RegistroAuditoria.objects.get(accion=Accion.ALTA_ASIENTO_CONTABLE)
        self.assertEqual((registro.usuario_id, registro.rol), (self.contador.pk, "contador"))
        ids = {a["id"] for a in registro.afectados if a["modelo"] == "contabilidad.asientocontable"}
        self.assertEqual(ids, {contraasiento.pk, self.original.pk})
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["anula"]["antes"], None)
        self.assertEqual(cambios["anula"]["despues"]["id"], self.original.pk)
        self.assertEqual(cambios["descripcion_asiento"]["despues"], MOTIVO)
        self.assertEqual(cambios["fecha_asiento"]["despues"], "2027-03-01")
        movimientos = RegistroAuditoria.objects.filter(accion=Accion.ALTA_MOVIMIENTO_CONTABLE)
        self.assertEqual(movimientos.count(), 3)
        self.assertEqual({r.usuario_id for r in movimientos}, {self.contador.pk})
        self.assertEqual(movimientos.order_by("id")[0].detalle["cambios"]["tipo_movimiento"]["despues"], HABER)  # ya invertido

    def test_regla_sin_efecto_operativo_no_toca_otras_entidades(self):
        """Regla «Sin efecto operativo» (C5): solo se crea el contraasiento con sus movimientos; ningún documento de origen nuevo."""
        documentos = OrigenDocumento.objects.count()

        self.contraasentar()

        self.assertEqual(OrigenDocumento.objects.count(), documentos)
        self.assertEqual(AsientoContable.objects.count(), 2)
        self.assertEqual(MovimientoContable.objects.count(), 6)

    def test_garantias_minimas_si_falla_la_auditoria_no_queda_nada(self):
        """Garantías mínimas: si falla la auditoría de un movimiento no queda contraasiento, ni número consumido, ni aviso, ni auditoría parcial, y el asiento no queda anulado."""
        llamadas = []
        real = RegistroAuditoria.objects.registrar

        def falla_en_el_ultimo(*args, **kwargs):
            llamadas.append(1)
            if len(llamadas) == 4:  # el contraasiento y sus tres movimientos
                raise FalloDePrueba
            return real(*args, **kwargs)

        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=falla_en_el_ultimo):
            with self.assertRaises(FalloDePrueba):
                self.contraasentar()

        self.assertEqual(len(llamadas), 4)
        self.assert_sin_contraasiento()

    def test_garantias_minimas_si_falla_el_aviso_no_queda_nada(self):
        """Requisitos especiales (D-42): la notificación se crea dentro de la transacción; si falla, se deshace todo el contraasiento."""
        with mock.patch("core.notificaciones.notificar_a_varios", side_effect=FalloDePrueba):
            with self.assertRaises(FalloDePrueba):
                self.contraasentar()

        self.assert_sin_contraasiento()


class ConCtrAsiEjercicioVencidoTests(PlanDeCuentasMixin, TestCase):
    """D-84 punto 2 y H9: con el abierto vencido, contraasentar autorrecupera ANTES de validar la fecha; el resumen no escribe nunca."""

    def setUp(self):
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com")
        self.vencido = ejercicio(Estado.ABIERTO, datetime.date(2026, 1, 1))  # terminó el 31/12/2026; hoy es el 10/3/2027
        self.original = asiento_de_prueba(self.vencido, datetime.date(2026, 11, 1), MOVIMIENTOS, descripcion="Gasto de 2026")

    def estado_de_la_base(self):
        return (
            list(EjercicioContable.objects.order_by("id").values_list("id", "estado_ejercicio", "ultimo_numero_asiento")),
            AsientoContable.objects.count(),
            MovimientoContable.objects.count(),
            RegistroAuditoria.objects.count(),
            Notificacion.objects.count(),
        )

    def test_regla_h9_contraasentar_con_fecha_de_hoy_abre_el_ejercicio_nuevo_y_asienta_ahi(self):
        """D-84 punto 2: una fecha válida (hoy) no se rechaza como «cerrado»: la autorrecuperación abre el de 2027 y el contraasiento va ahí; el vencido pasa a «en cierre»."""
        contraasiento = asientos.contraasentar(self.contador, self.original.pk, HOY, MOTIVO, hoy=HOY)

        self.assertEqual(contraasiento.ejercicio.fecha_inicio_ejercicio, datetime.date(2027, 1, 1))
        self.assertEqual(contraasiento.numero_asiento, 1)
        self.assertEqual(EjercicioContable.objects.get(pk=self.vencido.pk).estado_ejercicio, Estado.EN_CIERRE)
        verificar_invariantes_contables()

    def test_regla_h9_el_resumen_no_crea_ejercicios_asientos_auditoria_ni_avisos(self):
        """El resumen con el abierto vencido muestra el ejercicio que se abriría (N.º 2, por abrir) y no escribe nada: ni ejercicio, ni asiento, ni auditoría, ni cambio de estado."""
        antes = self.estado_de_la_base()

        resumen = asientos.resumir_contraasiento(self.contador, self.original.pk, HOY, MOTIVO, hoy=HOY)

        self.assertEqual((resumen.ejercicio_numero, resumen.ejercicio_estado, resumen.ejercicio_por_abrir), (2, Estado.ABIERTO, True))
        self.assertEqual(self.estado_de_la_base(), antes)

    def test_regla_h9_el_resumen_con_fecha_del_vencido_lo_muestra_en_cierre_sin_haberlo_cambiado(self):
        """El ejercicio vencido aparece «en cierre» en el resumen (será así al registrar) sin cambiar todavía en la base."""
        antes = self.estado_de_la_base()

        resumen = asientos.resumir_contraasiento(self.contador, self.original.pk, datetime.date(2026, 12, 1), MOTIVO, hoy=HOY)

        self.assertEqual((resumen.ejercicio_numero, resumen.ejercicio_estado, resumen.ejercicio_por_abrir), (1, Estado.EN_CIERRE, False))
        self.assertEqual(self.estado_de_la_base(), antes)


class ConCtrAsiResumenTests(ConCtrAsiBase):
    """Paso 4 del flujo básico: `resumir_contraasiento` hace las mismas validaciones y no escribe ni bloquea."""

    def test_flujo_principal_el_resumen_trae_el_ejercicio_los_movimientos_invertidos_y_el_total(self):
        """Paso 4: el ejercicio al que irá el contraasiento, los movimientos resultantes (invertidos) y que el asiento quedará anulado."""
        resumen = self.resumir()

        self.assertEqual(resumen.asiento.pk, self.original.pk)
        self.assertEqual((resumen.ejercicio_numero, resumen.ejercicio_estado, resumen.ejercicio_por_abrir), (3, Estado.ABIERTO, False))
        self.assertEqual((resumen.ejercicio_inicio, resumen.ejercicio_cierre), (datetime.date(2027, 1, 1), datetime.date(2027, 12, 31)))
        self.assertEqual(
            [(l.codigo, l.tipo_movimiento, l.importe, l.tipo_cuenta_texto) for l in resumen.lineas],
            [
                (cuentas.GASTOS_GENERALES, HABER, Decimal("1000.00"), "Resultado negativo"),
                (cuentas.INSUMOS_EN_STOCK, HABER, Decimal("500.50"), "Activo"),
                (cuentas.CAJA, DEBE, Decimal("1500.50"), "Activo"),
            ],
        )
        self.assertEqual(resumen.total, Decimal("1500.50"))
        self.assertFalse(resumen.es_automatico)

    def test_flujo_principal_el_resumen_de_un_automatico_advierte_que_no_anula_la_operacion(self):
        """Paso 2 y C5: para un asiento automático el resumen lo indica (`es_automatico`) para advertir que el contraasiento no anula la operación de origen."""
        automatico = asiento_de_prueba(self.abierto, datetime.date(2027, 2, 2), origen=origen_de_prueba())

        self.assertTrue(self.resumir(asiento=automatico).es_automatico)

    def test_ext_3b_el_resumen_indica_que_va_al_ejercicio_en_cierre(self):
        """Extensión 3b, punto 2: el resumen del paso 4 indica que el contraasiento va al ejercicio en cierre."""
        resumen = self.resumir(fecha=EN_EL_EN_CIERRE)

        self.assertEqual((resumen.ejercicio_numero, resumen.ejercicio_estado), (2, Estado.EN_CIERRE))

    def test_regla_el_resumen_hace_las_mismas_validaciones_que_contraasentar(self):
        """«Resumen previo»: mismos errores (motivo, fecha, asiento no anulable) con los mismos códigos y campos que el registro."""
        ya_anulado = asiento_de_prueba(self.abierto, datetime.date(2027, 2, 4), MOVIMIENTOS, descripcion="Otro")
        self.contraasentar(asiento=ya_anulado)
        casos = {
            "motivo": dict(motivo=""),
            "cerrado": dict(fecha=EN_EL_CERRADO),
            "anterior": dict(fecha=ANTES_DEL_PRIMERO),
            "futura": dict(fecha=HOY + datetime.timedelta(days=1)),
            "ya_anulado": dict(asiento=ya_anulado),
        }
        for nombre, argumentos in casos.items():
            with self.subTest(nombre):
                with self.assertRaises(ErrorContable) as del_resumen:
                    self.resumir(**argumentos)
                with self.assertRaises(ErrorContable) as del_registro:
                    self.contraasentar(**argumentos)
                self.assertEqual(_errores(del_resumen.exception), _errores(del_registro.exception))

    def test_regla_el_resumen_respeta_quien_registra(self):
        """«Quién registra»: el Gerente con un Contador activo tampoco pide el resumen."""
        with self.assertRaises(PermissionDenied):
            self.resumir(self.gerente)

    def test_regla_el_resumen_no_escribe_ni_audita_ni_avisa_ni_bloquea(self):
        """Resumen previo y garantías mínimas: no deja asiento, auditoría, aviso ni número consumido y no toma ningún bloqueo."""
        with mock.patch.object(asientos, "_bloquear_asiento", side_effect=AssertionError("el resumen no bloquea")), mock.patch.object(
            asientos, "_bloquear_ejercicio", side_effect=AssertionError("el resumen no bloquea")
        ):
            self.resumir()
            self.resumir(fecha=EN_EL_EN_CIERRE)

        self.assert_sin_contraasiento()


class ConCtrAsiDatosParaCorreccionTests(ConCtrAsiBase):
    """Paso 8 y CON-REG-ASI extensión 1b (C4): `datos_para_correccion` precarga el asiento correcto con las líneas del anulado."""

    def test_c4_trae_las_lineas_del_anulado_y_la_descripcion_sugerida(self):
        """C4 y «Cómo se aplica»: las líneas del asiento anulado (NO las invertidas) y «corrección del asiento N.º X»."""
        datos = asientos.datos_para_correccion(self.contador, self.original.pk)

        self.assertEqual(datos["movimientos"], MOVIMIENTOS)
        self.assertEqual(datos["descripcion"], "corrección del asiento N.º 1")
        self.assertEqual(datos["numero_anulado"], 1)

    def test_c4_desde_el_contraasiento_usa_el_asiento_que_anuló(self):
        """C4: el paso 8 ofrece corregir desde el contraasiento; se precarga con las líneas y el número del asiento anulado, no con los del contraasiento."""
        contraasiento = self.contraasentar()

        datos = asientos.datos_para_correccion(self.contador, contraasiento.pk)

        self.assertEqual(datos["movimientos"], MOVIMIENTOS)
        self.assertEqual(datos["numero_anulado"], 1)
        self.assertEqual(datos["descripcion"], "corrección del asiento N.º 1")

    def test_c4_respeta_quien_registra_y_no_escribe(self):
        """El Gerente con Contador activo no precarga («Lo registra el Contador»); pedir los datos no escribe nada."""
        with self.assertRaises(PermissionDenied):
            asientos.datos_para_correccion(self.gerente, self.original.pk)
        with self.assertRaises(Http404):
            asientos.datos_para_correccion(self.contador, 987654)

        asientos.datos_para_correccion(self.contador, self.original.pk)
        self.assert_sin_contraasiento()

    def test_c4_el_asiento_correcto_es_un_manual_comun_sin_vinculo_con_el_contraasiento(self):
        """CON-REG-ASI extensión 1b, punto 2 y CON-CTR-ASI C4: el asiento correcto se registra con `registrar_asiento_manual`, como cualquier manual, y no queda vinculado."""
        self.contraasentar()
        datos = asientos.datos_para_correccion(self.contador, self.original.pk)

        correcto = asientos.registrar_asiento_manual(self.contador, FECHA, datos["descripcion"], datos["movimientos"], hoy=HOY)

        self.assertEqual(correcto.tipo, AsientoContable.Tipo.MANUAL)
        self.assertIsNone(correcto.anula_id)
        self.assertFalse(hasattr(correcto, "contraasiento"))
        verificar_invariantes_contables()
