# Pruebas de CON-ABR-EJE, «Abrir Ejercicio Contable» (docs/casos_de_uso/contabilidad/ejercicio.md; D-84 puntos 2, 3 y 10), con `hoy` simulado:
# cada postcondición y regla, la idempotencia, el primer ejercicio, el anterior que se cierra solo, el sistema apagado más de un año, el tope
# de vueltas, los avisos y la auditoría. Cada prueba arma sus propios datos.
import datetime
from unittest import mock

from django.test import TestCase

from contabilidad.errores import ErrorContable
from contabilidad.models import EjercicioContable
from contabilidad.servicios import ejercicios
from contabilidad.tests.fabricas import ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.models import Contador, Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_cuenta, crear_gerente

Estado = EjercicioContable.Estado
INICIO = datetime.date(2027, 1, 1)
CIERRE = datetime.date(2027, 12, 31)
ULTIMO_DIA = datetime.date(2027, 12, 31)
DIA_SIGUIENTE = datetime.date(2028, 1, 1)


class FalloDePrueba(Exception):
    """Fallo forzado con `mock.patch`: una clase propia, para que ningún otro error (por ejemplo `NotImplementedError`, que es un
    `RuntimeError`) pase la prueba sin querer."""


def _estados():
    """`{inicio: estado}` de todos los ejercicios, para comparar de un vistazo."""
    return {e.fecha_inicio_ejercicio: e.estado_ejercicio for e in EjercicioContable.objects.all()}


class CierrePrevistoTests(TestCase):
    """Regla 3 de CON-ABR-EJE: cada ejercicio dura 12 meses (un año menos un día)."""

    def test_regla_3_el_cierre_es_un_anio_menos_un_dia_despues_del_inicio(self):
        """Regla 3 de CON-ABR-EJE y modelo (`fecha_cierre_ejercicio`): un año menos un día después del inicio."""
        self.assertEqual(ejercicios.cierre_previsto(datetime.date(2027, 1, 1)), datetime.date(2027, 12, 31))
        self.assertEqual(ejercicios.cierre_previsto(datetime.date(2027, 3, 15)), datetime.date(2028, 3, 14))
        self.assertEqual(ejercicios.cierre_previsto(datetime.date(2027, 3, 1)), datetime.date(2028, 2, 29))
        self.assertEqual(ejercicios.cierre_previsto(datetime.date(2028, 3, 1)), datetime.date(2029, 2, 28))

    def test_regla_3_un_29_de_febrero_cierra_el_28_de_febrero(self):
        """Regla 3 de CON-ABR-EJE: el año siguiente de un 29 de febrero se cuenta desde el 1 de marzo (cierre el 28 de febrero)."""
        self.assertEqual(ejercicios.cierre_previsto(datetime.date(2028, 2, 29)), datetime.date(2029, 2, 28))


class ConAbrEjeAperturaTests(TestCase):
    """CON-ABR-EJE: el día siguiente a la fecha de cierre del abierto, pasa a «en cierre» y se crea el siguiente."""

    def setUp(self):
        self.viejo = ejercicio_abierto(INICIO)

    def test_regla_1_si_el_abierto_no_vencio_no_hace_nada(self):
        """Precondición a y regla 2: el abierto vence cuando hoy es POSTERIOR a su cierre; el último día todavía vale. No escribe nada."""
        for hoy in (INICIO, datetime.date(2027, 6, 15), ULTIMO_DIA):
            resultado = ejercicios.abrir_ejercicio_si_corresponde(hoy)

            self.assertEqual(tuple(resultado[:4]), (None, None, None, None))
        self.assertEqual(_estados(), {INICIO: Estado.ABIERTO})
        self.assertFalse(RegistroAuditoria.objects.exists())
        self.assertFalse(Notificacion.objects.exists())

    def test_regla_2_al_dia_siguiente_del_cierre_abre_el_nuevo(self):
        """Regla 2 y postcondiciones a y b: el día siguiente al cierre previsto, el abierto pasa a «en cierre» y se crea el nuevo."""
        resultado = ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)

        self.assertEqual(resultado.paso_a_en_cierre.pk, self.viejo.pk)
        self.assertIsNone(resultado.primero_creado)
        self.assertIsNone(resultado.cerrado_solo)
        self.assertEqual(resultado.nuevo_abierto.fecha_inicio_ejercicio, DIA_SIGUIENTE)
        self.assertEqual(_estados(), {INICIO: Estado.EN_CIERRE, DIA_SIGUIENTE: Estado.ABIERTO})

    def test_post_a_el_ejercicio_abierto_pasa_a_en_cierre(self):
        """Postcondición a: el que estaba «abierto» pasó a «en cierre» (y conserva sus fechas, que no se modifican, H1)."""
        ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)

        self.viejo.refresh_from_db()
        self.assertEqual(self.viejo.estado_ejercicio, Estado.EN_CIERRE)
        self.assertEqual((self.viejo.fecha_inicio_ejercicio, self.viejo.fecha_cierre_ejercicio), (INICIO, CIERRE))

    def test_post_b_el_nuevo_empieza_el_dia_siguiente_al_cierre_del_anterior_y_dura_doce_meses(self):
        """Postcondición b: inicio el día siguiente al cierre del anterior, cierre previsto 12 meses después menos un día, sin asientos."""
        nuevo = ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE).nuevo_abierto

        self.assertEqual(nuevo.estado_ejercicio, Estado.ABIERTO)
        self.assertEqual(nuevo.fecha_inicio_ejercicio, datetime.date(2028, 1, 1))
        self.assertEqual(nuevo.fecha_cierre_ejercicio, datetime.date(2028, 12, 31))
        self.assertEqual(nuevo.ultimo_numero_asiento, 0)
        self.assertIsNone(nuevo.contador)

    def test_post_b_el_nuevo_empieza_el_dia_siguiente_al_cierre_aunque_pasen_dias(self):
        """Postcondición b: si el paso corre varios días tarde, el nuevo igual empieza el día siguiente al cierre previsto (no hoy)."""
        nuevo = ejercicios.abrir_ejercicio_si_corresponde(datetime.date(2028, 3, 10)).nuevo_abierto

        self.assertEqual(nuevo.fecha_inicio_ejercicio, DIA_SIGUIENTE)
        self.assertEqual(nuevo.fecha_cierre_ejercicio, datetime.date(2028, 12, 31))

    def test_post_c_avisa_al_contador_que_el_ejercicio_paso_a_en_cierre(self):
        """Postcondición c: se notifica al Contador activo (no al Gerente) que el ejercicio pasó a «en cierre» y le falta cerrarlo."""
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        gerente = crear_gerente()

        ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)

        avisos = Notificacion.objects.filter(destinatario=contador)
        self.assertEqual(avisos.count(), 1)
        self.assertEqual(avisos.get().titulo, "El ejercicio N.º 1 pasó a «en cierre»")
        self.assertEqual(
            avisos.get().detalle, "Terminó el 31/12/2027. Revisá el libro de gestión y cerralo cuando estés conforme."
        )
        self.assertFalse(Notificacion.objects.filter(destinatario=gerente).exists())

    def test_post_c_sin_contador_avisa_al_gerente(self):
        """Postcondición c: si no hay un Contador activo, el aviso es para el Gerente."""
        gerente = crear_gerente()
        crear_cuenta(Contador, email="anterior@infoponia.com", activo=False)

        ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)

        self.assertEqual(Notificacion.objects.get().destinatario_id, gerente.pk)

    def test_post_c_sin_responsable_no_avisa_y_no_falla(self):
        """Postcondición c y D-85 punto 5: sin Contador ni Gerente activos, no se avisa y la apertura igual se hace."""
        resultado = ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)

        self.assertIsNotNone(resultado.nuevo_abierto)
        self.assertFalse(Notificacion.objects.exists())

    def test_post_c_el_aviso_numera_el_ejercicio_por_fecha_de_inicio(self):
        """Pantallas del caso de uso: «el número de ejercicio es la posición por fecha de inicio»; el aviso del tercero dice N.º 3."""
        self.viejo.delete()
        ejercicio(Estado.CERRADO, datetime.date(2025, 1, 1))
        ejercicio(Estado.CERRADO, datetime.date(2026, 1, 1))
        ejercicio_abierto(INICIO)
        crear_gerente()

        ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)

        self.assertEqual(Notificacion.objects.get().titulo, "El ejercicio N.º 3 pasó a «en cierre»")

    def test_post_e_audita_con_origen_infoponia(self):
        """Postcondición e: un registro por cambio, con actor `None` (rol infoponia): el cambio de estado y el alta del nuevo (D-84 punto 9)."""
        resultado = ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)

        cambio = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.MODIFICACION_EJERCICIO_CONTABLE)
        self.assertIsNone(cambio.usuario)
        self.assertEqual(cambio.rol, "infoponia")
        self.assertEqual([a["id"] for a in cambio.afectados], [self.viejo.pk])
        self.assertEqual(cambio.afectados[0]["modelo"], "contabilidad.ejerciciocontable")
        self.assertEqual(cambio.detalle["cambios"], {"estado_ejercicio": {"antes": "abierto", "despues": "en_cierre"}})

        alta = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.ALTA_EJERCICIO_CONTABLE)
        self.assertIsNone(alta.usuario)
        self.assertEqual(alta.rol, "infoponia")
        self.assertEqual([a["id"] for a in alta.afectados], [resultado.nuevo_abierto.pk])
        self.assertEqual(
            alta.detalle["cambios"],
            {
                "fecha_inicio_ejercicio": {"antes": None, "despues": "2028-01-01"},
                "fecha_cierre_ejercicio": {"antes": None, "despues": "2028-12-31"},
                "estado_ejercicio": {"antes": None, "despues": "abierto"},
            },
        )
        self.assertEqual(alta.detalle["datos"], {"origen": "apertura automática"})

    def test_regla_5_es_idempotente(self):
        """Regla 5 y D-84 punto 2: correrla dos veces el mismo día no duplica el ejercicio ni los avisos ni la auditoría."""
        crear_gerente()
        ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)
        auditoria, avisos = RegistroAuditoria.objects.count(), Notificacion.objects.count()

        segunda = ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)

        self.assertEqual(tuple(segunda[:4]), (None, None, None, None))
        self.assertEqual(EjercicioContable.objects.count(), 2)
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), (auditoria, avisos))

    def test_regla_1_tras_la_apertura_hay_un_abierto_y_uno_en_cierre_a_lo_sumo(self):
        """Regla 1 de CON-ABR-EJE (H1) y modelo: los invariantes contables valen después de abrir."""
        ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)

        verificar_invariantes_contables()

    def test_regla_8_sin_hoy_usa_la_fecha_del_invernadero(self):
        """Regla 8 y D-84 punto 10: sin `hoy`, la fecha es `timezone.localdate()` (zona del invernadero)."""
        with mock.patch("django.utils.timezone.localdate", return_value=DIA_SIGUIENTE):
            resultado = ejercicios.abrir_ejercicio_si_corresponde()

        self.assertEqual(resultado.nuevo_abierto.fecha_inicio_ejercicio, DIA_SIGUIENTE)

    def test_d22_la_apertura_es_todo_o_nada(self):
        """D-22: si falla la auditoría (la del ejercicio nuevo, que es la última), no queda ningún cambio de estado ni ejercicio nuevo."""
        original = RegistroAuditoria.objects.registrar
        llamadas = []

        def falla_en_la_ultima(*args, **kwargs):
            llamadas.append(args)
            if len(llamadas) == 2:  # 1 = el cambio de estado del viejo, 2 = el alta del nuevo
                raise FalloDePrueba("falló la auditoría del ejercicio nuevo")
            return original(*args, **kwargs)

        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=falla_en_la_ultima):
            with self.assertRaises(FalloDePrueba):
                ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)

        self.assertEqual(len(llamadas), 2)  # llegó hasta la segunda auditoría: el cambio de estado ya estaba hecho y se deshizo
        self.assertEqual(_estados(), {INICIO: Estado.ABIERTO})
        self.assertEqual(RegistroAuditoria.objects.count(), 0)


class ConAbrEjeCierreSoloTests(TestCase):
    """Postcondición d y regla 1: si el anterior seguía «en cierre» al vencer el abierto, el Sistema lo cierra solo (C1)."""

    def setUp(self):
        self.anterior = ejercicio(Estado.EN_CIERRE, datetime.date(2026, 1, 1))
        self.abierto = ejercicio_abierto(INICIO)

    def test_post_d_el_anterior_en_cierre_se_cierra_solo_antes_de_abrir_el_nuevo(self):
        """Postcondición d y regla 1: se cierra el más viejo, el abierto pasa a «en cierre» y se crea el nuevo; nunca dos «en cierre»."""
        resultado = ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)

        self.assertEqual(resultado.cerrado_solo.pk, self.anterior.pk)
        self.assertEqual(resultado.paso_a_en_cierre.pk, self.abierto.pk)
        self.assertEqual(
            _estados(),
            {
                datetime.date(2026, 1, 1): Estado.CERRADO,
                INICIO: Estado.EN_CIERRE,
                DIA_SIGUIENTE: Estado.ABIERTO,
            },
        )

    def test_post_d_cerrado_sin_contador_aunque_haya_uno_activo(self):
        """Postcondición d: lo cerró el Sistema, sin Contador asociado (R010, C1): `contador` queda vacío."""
        crear_cuenta(Contador, email="contador@infoponia.com")

        ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)

        self.anterior.refresh_from_db()
        self.assertIsNone(self.anterior.contador)

    def test_post_d_avisa_que_se_cerro_solo(self):
        """Postcondición d: se avisa al responsable contable que el ejercicio se cerró solo (además del aviso del que pasó a «en cierre»)."""
        contador = crear_cuenta(Contador, email="contador@infoponia.com")

        ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)

        titulos = sorted(Notificacion.objects.filter(destinatario=contador).values_list("titulo", flat=True))
        self.assertEqual(titulos, ["El ejercicio N.º 1 se cerró solo", "El ejercicio N.º 2 pasó a «en cierre»"])
        cierre = Notificacion.objects.get(titulo="El ejercicio N.º 1 se cerró solo")
        self.assertEqual(cierre.detalle, "Se cerró solo porque venció el siguiente (terminó el 31/12/2026).")

    def test_post_e_audita_el_cierre_automatico(self):
        """Postcondición e y D-84 punto 9: el cierre automático se audita como `modificacion_ejercicio_contable` con `datos.origen`."""
        ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)

        cierre = RegistroAuditoria.objects.get(
            accion=RegistroAuditoria.Accion.MODIFICACION_EJERCICIO_CONTABLE, afectados__contains=[{"id": self.anterior.pk}]
        )
        self.assertIsNone(cierre.usuario)
        self.assertEqual(cierre.detalle["cambios"], {"estado_ejercicio": {"antes": "en_cierre", "despues": "cerrado"}})
        self.assertEqual(cierre.detalle["datos"], {"origen": "cierre automático"})
        verificar_invariantes_contables()


class ConAbrEjeSinEjercicioTests(TestCase):
    """Regla 4 de CON-ABR-EJE (cambió con CON-05) y regla 11 de CON-INI-EJE: el primer ejercicio lo crea CON-INI-EJE; la apertura automática
    nunca lo crea. Reemplaza las pruebas de la puesta en marcha técnica de D-84 punto 3 (`crear_primer_ejercicio`, retirada)."""

    HOY = datetime.date(2027, 5, 20)

    def test_regla_4_sin_ningun_ejercicio_no_crea_nada(self):
        """Regla 4 de CON-ABR-EJE y regla 11 de CON-INI-EJE: sin ningún ejercicio, la apertura no hace nada y devuelve todo `None`."""
        resultado = ejercicios.abrir_ejercicio_si_corresponde(self.HOY)

        self.assertEqual(tuple(resultado[:4]), (None, None, None, None))
        self.assertEqual((resultado.cantidad_creados, resultado.cantidad_cerrados_solos), (0, 0))
        self.assertFalse(EjercicioContable.objects.exists())

    def test_regla_4_sin_ningun_ejercicio_no_audita_ni_avisa(self):
        """Regla 4 de CON-ABR-EJE: sin ejercicio no queda ningún registro de auditoría ni aviso."""
        crear_gerente()

        ejercicios.abrir_ejercicio_si_corresponde(self.HOY)

        self.assertFalse(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ALTA_EJERCICIO_CONTABLE).exists())
        self.assertFalse(Notificacion.objects.exists())

    def test_regla_11_la_apertura_ya_no_crea_el_primero_aunque_se_repita(self):
        """Regla 5 de CON-ABR-EJE (idempotencia) con la regla 11 de CON-INI-EJE: correrla varias veces sin ejercicio sigue sin crear ninguno."""
        ejercicios.abrir_ejercicio_si_corresponde(self.HOY)
        ejercicios.abrir_ejercicio_si_corresponde(self.HOY + datetime.timedelta(days=400))

        self.assertFalse(EjercicioContable.objects.exists())

    def test_regla_11_crear_primer_ejercicio_ya_no_existe(self):
        """CON-05, decisión «Puesta en marcha contable» punto 3: se retiró `crear_primer_ejercicio` (la puesta en marcha es `iniciar_ejercicio`)."""
        self.assertFalse(hasattr(ejercicios, "crear_primer_ejercicio"))

    def test_regla_11_contabilidad_iniciada_es_falso_sin_ejercicios(self):
        """`ejercicios.contabilidad_iniciada()` (docs/api/asientos.md): falso si no existe ningún ejercicio."""
        self.assertFalse(ejercicios.contabilidad_iniciada())

    def test_regla_11_contabilidad_iniciada_es_verdadero_con_un_ejercicio_en_cualquier_estado(self):
        """`contabilidad_iniciada()`: verdadero con un ejercicio abierto, en cierre o cerrado."""
        for estado in (Estado.ABIERTO, Estado.EN_CIERRE, Estado.CERRADO):
            with self.subTest(estado=estado):
                EjercicioContable.objects.all().delete()
                ejercicio(estado, datetime.date(2026, 1, 1))
                self.assertTrue(ejercicios.contabilidad_iniciada())


class ConAbrEjeSistemaApagadoTests(TestCase):
    """Cómo se aplica: el sistema estuvo apagado y el paso repite hasta alcanzar el ejercicio actual (tope de 10 vueltas)."""

    def test_ext_un_sistema_apagado_mas_de_un_anio_alcanza_el_ejercicio_actual(self):
        """Cómo se aplica («sistema apagado más de un año»): dos vueltas en la misma transacción; queda uno abierto y uno en cierre."""
        ejercicio_abierto(INICIO)
        crear_gerente()

        resultado = ejercicios.abrir_ejercicio_si_corresponde(datetime.date(2029, 6, 1))

        self.assertEqual(
            _estados(),
            {INICIO: Estado.CERRADO, datetime.date(2028, 1, 1): Estado.EN_CIERRE, datetime.date(2029, 1, 1): Estado.ABIERTO},
        )
        self.assertEqual(resultado.nuevo_abierto.fecha_inicio_ejercicio, datetime.date(2029, 1, 1))
        self.assertEqual((resultado.cantidad_creados, resultado.cantidad_cerrados_solos), (2, 1))
        verificar_invariantes_contables()

    def test_ext_el_que_quedo_en_cierre_se_cierra_solo_sin_contador(self):
        """Cómo se aplica: el que se cierra solo en una vuelta intermedia queda sin Contador (C1)."""
        ejercicio_abierto(INICIO)
        crear_cuenta(Contador, email="contador@infoponia.com")

        ejercicios.abrir_ejercicio_si_corresponde(datetime.date(2029, 6, 1))

        self.assertIsNone(EjercicioContable.objects.get(fecha_inicio_ejercicio=INICIO).contador)

    def test_ext_sin_abierto_pero_con_ejercicios_todos_cerrados_abre_uno_nuevo(self):
        """Cómo se aplica («primer ejercicio sin condición de fecha»): sin abierto y con todos cerrados, abre uno desde el día siguiente al cierre del último."""
        ejercicio(Estado.CERRADO, datetime.date(2026, 1, 1))

        resultado = ejercicios.abrir_ejercicio_si_corresponde(datetime.date(2027, 6, 1))

        self.assertEqual(resultado.nuevo_abierto.fecha_inicio_ejercicio, datetime.date(2027, 1, 1))
        self.assertEqual(resultado.nuevo_abierto.estado_ejercicio, Estado.ABIERTO)
        self.assertEqual(
            _estados(), {datetime.date(2026, 1, 1): Estado.CERRADO, datetime.date(2027, 1, 1): Estado.ABIERTO}
        )

    def test_ext_sin_abierto_y_con_uno_en_cierre_abre_el_siguiente_y_deja_el_en_cierre(self):
        """Cómo se aplica: si solo hay uno «en cierre», se abre el siguiente (sin cerrar el que está en cierre)."""
        ejercicio(Estado.EN_CIERRE, datetime.date(2026, 1, 1))

        ejercicios.abrir_ejercicio_si_corresponde(datetime.date(2027, 3, 1))

        self.assertEqual(
            _estados(), {datetime.date(2026, 1, 1): Estado.EN_CIERRE, datetime.date(2027, 1, 1): Estado.ABIERTO}
        )

    def test_ext_diez_vueltas_todavia_se_permiten(self):
        """Cómo se aplica: el tope de seguridad es de 10 vueltas; con exactamente 10 se llega al ejercicio actual."""
        ejercicio_abierto(INICIO)  # 2027 .. 2036 vencidos = 10 vueltas; el 2037 es el actual

        resultado = ejercicios.abrir_ejercicio_si_corresponde(datetime.date(2037, 6, 1))

        self.assertEqual(resultado.nuevo_abierto.fecha_inicio_ejercicio, datetime.date(2037, 1, 1))
        verificar_invariantes_contables()

    def test_ext_once_vueltas_superan_el_tope_y_no_se_escribe_nada(self):
        """Cómo se aplica: superado el tope lanza `ErrorContable` `ejercicios_atrasados` y la transacción no deja nada a medias."""
        ejercicio_abierto(INICIO)  # 2027 .. 2037 vencidos = 11 vueltas

        with self.assertRaises(ErrorContable) as contexto:
            ejercicios.abrir_ejercicio_si_corresponde(datetime.date(2038, 6, 1))

        self.assertEqual(contexto.exception.codigo, "ejercicios_atrasados")
        self.assertEqual(_estados(), {INICIO: Estado.ABIERTO})
        self.assertFalse(RegistroAuditoria.objects.exists())


class EjerciciosLecturaTests(TestCase):
    """docs/api/asientos.md, «Lectura»: `ejercicio_abierto()` y `ejercicio_en_cierre()`."""

    def test_lectura_sin_ejercicios_devuelve_none(self):
        """API, «Lectura»: sin ejercicios, las dos devuelven `None`."""
        self.assertIsNone(ejercicios.ejercicio_abierto())
        self.assertIsNone(ejercicios.ejercicio_en_cierre())

    def test_lectura_devuelve_el_abierto_y_el_en_cierre(self):
        """API, «Lectura»: devuelven el ejercicio abierto y el en cierre (los cerrados no cuentan)."""
        ejercicio(Estado.CERRADO, datetime.date(2025, 1, 1))
        en_cierre = ejercicio(Estado.EN_CIERRE, datetime.date(2026, 1, 1))
        abierto = ejercicio_abierto(INICIO)

        self.assertEqual(ejercicios.ejercicio_abierto().pk, abierto.pk)
        self.assertEqual(ejercicios.ejercicio_en_cierre().pk, en_cierre.pk)
