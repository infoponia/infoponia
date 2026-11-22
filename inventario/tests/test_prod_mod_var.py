# Pruebas de PROD-MOD-VAR · Modificar Variedad (INV-03, paso 5; la reactivación está en test_prod_mod_var_reactivar.py).
# Fuente: docs/casos_de_uso/inventario/variedades.md (reglas 1 a 9, precondiciones a a c, postcondiciones a a e y «Decisiones de
# aplicación»), docs/api/variedades.md, D-28 (sin cambios no escribe), D-36 (auditoría) y D-42 (notificaciones). Lotes y órdenes de la
# variedad se simulan con registrantes falsos (`usos_de_variedad_de_prueba`, `variedades_presentes_de_prueba`): `produccion` no existe.
#
# Contrato que fijan estas pruebas:
#   - ``modificar_variedad(actor, variedad_id, datos, *, advertencia_confirmada=False)`` recibe los mismos ``DatosDeVariedad`` que el alta
#     (con TODOS los campos: el formulario siempre los envía) y devuelve la variedad. Mismos campos de error y mismos códigos que el alta,
#     más: ``variedad_inactiva`` y ``variedad_en_uso_por_otros`` (errores generales), ``etapas_con_lotes`` (en ``etapas``) y
#     ``perfil_con_lotes_u_ordenes`` (en ``perfil_familia``). Si un cambio de perfil deja una etapa no permitida, el error
#     ``etapa_no_permitida`` va en ``perfil_familia``; si el perfil no cambió, en ``etapas``.
#   - Con incompatibilidades de rangos y sin ``advertencia_confirmada``, lanza ``FaltaConfirmarAdvertencia(avisos)`` (``avisos`` son
#     ``Incompatibilidad``) y no cambia nada.
#   - ``resumen_de_modificacion(actor, variedad_id, datos)`` valida como ``modificar_variedad`` y devuelve ``ResumenDeModificacion``
#     (``hay_cambios``, ``cambios`` {campo: (antes, despues)} como texto, ``nombre_semilla`` nuevo o ``None``, ``a_notificar`` con los
#     nombres de los invernaderos cuyo Agrónomo recibirá un aviso y ``advertencias``) SIN escribir.

from decimal import Decimal
from unittest import mock

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import TestCase

from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.extensiones import UsoDeVariedad
from inventario.models import Insumo, InsumoInvernadero
from inventario.servicios import ciclos
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    existencia,
    insumo,
    perezoso,
    tipo_de_insumo,
    usos_de_variedad_de_prueba,
    variedad_con_semilla,
    variedades_presentes_de_prueba,
)
from maestros.models import Ciclo, EtapaProductiva, Variedad
from maestros.servicios.sectores import FaltaConfirmarAdvertencia
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_cultivo, crear_invernadero, error_de

variedades = perezoso("inventario.servicios.variedades")

ETAPAS = [("germinacion", 5), ("crecimiento", 10), ("maduracion", 20)]


def datos_de(variedad, **cambios):
    """Los ``DatosDeVariedad`` con lo que hoy tiene guardado ``variedad`` (como los reenvía el formulario); ``cambios`` pisa campos."""
    v = Variedad.objects.get(pk=variedad.pk)
    base = {
        "nombre": v.nombre_variedad,
        "perfil_familia": v.perfil_familia,
        "etapas": tuple((e.codigo, str(e.duracion_dias)) for e in ciclos.etapas_de([v.pk])[v.pk]),
        "duracion_post_cosecha": str(v.duracion_post_cosecha),
        "peso_promedio_planta": str(v.peso_promedio_planta),
    }
    for columna in variedades.COLUMNAS_DE_RANGO:
        base[columna] = str(getattr(v, columna))
    base.update(cambios)
    return variedades.DatosDeVariedad(**base)


def con_lotes(variedad, activos=1, ordenes=0, invernaderos=()):
    """Un registrante falso de `produccion`: la variedad tiene lotes (``activos`` activos) y ``ordenes`` órdenes a realizar."""
    return usos_de_variedad_de_prueba(
        {variedad.pk: UsoDeVariedad(True, activos, ordenes, frozenset(g.pk for g in invernaderos))}
    )


class ModVarBase(ConDatosDeInventario, TestCase):
    """«Lechuga Crespa» (hoja verde, germinación 5, crecimiento 10, maduración 20) y dos Agrónomos con un invernadero cada uno."""

    def setUp(self):
        self.ana = crear_agronomo("ana@infoponia.com", nombre="Ana", apellido="Pérez")
        self.beto = crear_agronomo("beto@infoponia.com", nombre="Beto", apellido="Gómez")
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.ana)
        self.sur = crear_invernadero("Invernadero Sur", agronomo=self.beto)
        self.cultivo = crear_cultivo("Lechuga")
        self.variedad = variedad_con_semilla(self.cultivo, "Crespa", etapas=ETAPAS)

    def modificar(self, actor=None, variedad=None, **cambios):
        confirmada = cambios.pop("advertencia_confirmada", False)
        variedad = variedad or self.variedad
        return variedades.modificar_variedad(
            actor or self.ana, variedad.pk, datos_de(variedad, **cambios), advertencia_confirmada=confirmada
        )

    def error(self, **cambios):
        return error_de(lambda: self.modificar(**cambios))

    def recargada(self, variedad=None):
        return Variedad.objects.get(pk=(variedad or self.variedad).pk)

    def registros(self, accion="modificacion_variedad"):
        return RegistroAuditoria.objects.filter(accion=accion)


class PreCondicionesTests(ModVarBase):
    """Precondiciones a, b y c, y regla 9 (una variedad inactiva no se modifica)."""

    def test_pre_a_un_gerente_no_modifica(self):
        """PROD-MOD-VAR precondición a: solo un Agrónomo activo."""
        with self.assertRaises(PermissionDenied):
            self.modificar(actor=crear_gerente(), nombre="Otra")

    def test_pre_a_un_agronomo_inactivo_no_modifica(self):
        """PROD-MOD-VAR precondición a: la cuenta tiene que estar activa."""
        with self.assertRaises(PermissionDenied):
            self.modificar(actor=crear_agronomo("inactivo@infoponia.com", activo=False), nombre="Otra")

    def test_pre_a_una_variedad_inexistente_da_404(self):
        """Una variedad que no existe es 404."""
        with self.assertRaises(Http404):
            variedades.modificar_variedad(self.ana, 999999, datos_de(self.variedad))

    def test_pre_b_si_ningun_invernadero_la_usa_cualquier_agronomo_la_modifica(self):
        """PROD-MOD-VAR regla 1: si ningún invernadero la usa, cualquier Agrónomo activo."""
        self.assertEqual(self.modificar(actor=self.beto, nombre="Otra").nombre_variedad, "Otra")

    def test_pre_b_la_modifica_el_agronomo_de_un_invernadero_que_la_usa(self):
        """PROD-MOD-VAR regla 1: la modifica el Agrónomo de algún invernadero que la use."""
        existencia(self.variedad.semilla, self.norte)
        self.assertEqual(self.modificar(actor=self.ana, nombre="Otra").nombre_variedad, "Otra")

    def test_pre_b_quien_no_la_gestiona_recibe_quienes_la_usan_y_no_se_cambia_nada(self):
        """PROD-MOD-VAR precondición b y regla 1: error general con los invernaderos que la usan y sus Agrónomos."""
        existencia(self.variedad.semilla, self.norte)
        error = self.error(actor=self.beto, nombre="Otra")
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["variedad_en_uso_por_otros"])
        self.assertIn("Invernadero Norte (Ana Pérez)", error.error_dict[NON_FIELD_ERRORS][0].message)
        self.assertEqual(self.recargada().nombre_variedad, "Crespa")
        self.assertFalse(self.registros().exists())

    def test_pre_c_el_nombre_nuevo_no_puede_ser_de_otra_variedad_del_cultivo(self):
        """PROD-MOD-VAR precondición c y regla 2 de ALT: sin distinguir mayúsculas ni espacios al borde, bajas incluidas."""
        variedad_con_semilla(self.cultivo, "Lisa")
        variedad_con_semilla(self.cultivo, "Roja", activa=False)
        for repetido in ("lisa", "  LISA ", "roja"):
            with self.subTest(nombre=repetido):
                self.assertEqual(codigos_de(self.error(nombre=repetido), "nombre"), ["nombre_repetido"])

    def test_pre_c_cambiar_solo_las_mayusculas_del_propio_nombre_es_valido(self):
        """PROD-MOD-VAR precondición c: el nombre de la propia variedad no cuenta como repetido; la semilla sigue su nombre."""
        variedad = self.modificar(nombre="CRESPA")
        self.assertEqual((variedad.nombre_variedad, variedad.semilla.nombre_insumo), ("CRESPA", "Semilla Lechuga CRESPA"))

    def test_pre_c_el_mismo_nombre_en_otro_cultivo_es_valido(self):
        """PROD-ALT-VAR regla 2: dos cultivos pueden tener variedades con el mismo nombre."""
        variedad_con_semilla(crear_cultivo("Acelga"), "Lisa")
        self.assertEqual(self.modificar(nombre="Lisa").nombre_variedad, "Lisa")

    def test_regla_9_una_variedad_inactiva_no_se_modifica(self):
        """PROD-MOD-VAR regla 9: solo se reactiva. Error general ``variedad_inactiva`` y nada cambia."""
        inactiva = variedad_con_semilla(self.cultivo, "Vieja", activa=False)
        error = error_de(lambda: variedades.modificar_variedad(self.ana, inactiva.pk, datos_de(inactiva, nombre="Nueva")))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["variedad_inactiva"])
        self.assertEqual(self.recargada(inactiva).nombre_variedad, "Vieja")


class SinCambiosTests(ModVarBase):
    """D-28: guardar sin haber cambiado nada no escribe, no audita y no notifica."""

    def test_d28_sin_cambios_no_escribe_ni_audita_ni_notifica(self):
        """D-28: la modificación sin cambios devuelve la variedad sin crear registro ni notificación."""
        existencia(self.variedad.semilla, self.norte)  # la usa Norte (de Ana, que actúa) y también Sur
        existencia(self.variedad.semilla, self.sur)
        variedad = self.modificar()
        self.assertEqual(variedad.pk, self.variedad.pk)
        self.assertFalse(self.registros().exists())
        self.assertFalse(Notificacion.objects.exists())

    def test_d28_reenviar_los_mismos_valores_con_otro_formato_tampoco_cambia_nada(self):
        """D-28: «  Crespa », «18,5» por «18.50» o «5» por «5» no son cambios (se compara lo normalizado)."""
        self.variedad.temp_ambiente_min = Decimal("18.50")
        self.variedad.save()
        self.modificar(nombre="  Crespa ", temp_ambiente_min="18,5")
        self.assertFalse(self.registros().exists())
        self.assertEqual(self.recargada().temp_ambiente_min, Decimal("18.50"))


class ValidacionTests(ModVarBase):
    """Regla 2: los datos se validan con las reglas 2 a 7 de PROD-ALT-VAR (mismos campos y códigos que el alta)."""

    def test_regla_2_las_reglas_del_alta_se_aplican_a_la_modificacion(self):
        """PROD-MOD-VAR regla 2: nombre vacío, etapa sin días, mínimo mayor que máximo, humedad 100,01, postcosecha 61 y peso 0."""
        casos = {
            "nombre": ({"nombre": ""}, "obligatorio"),
            "duracion_crecimiento": ({"etapas": (("germinacion", "5"), ("crecimiento", "0"), ("maduracion", "20"))}, "entero_mayor_que_cero"),
            "temp_ambiente_max": ({"temp_ambiente_min": "30", "temp_ambiente_max": "20"}, "minimo_mayor_que_maximo"),
            "humedad_max": ({"humedad_max": "100.01"}, "fuera_de_rango"),
            "fotoperiodo_max": ({"fotoperiodo_max": "24.01"}, "fuera_de_rango"),
            "duracion_post_cosecha": ({"duracion_post_cosecha": "61"}, "entero_entre_1_y_60"),
            "peso_promedio_planta": ({"peso_promedio_planta": "0"}, "entero_mayor_que_cero"),
        }
        for campo, (cambios, codigo) in casos.items():
            with self.subTest(campo=campo):
                self.assertEqual(codigos_de(self.error(**cambios), campo), [codigo])
        self.assertEqual(self.recargada().nombre_variedad, "Crespa")

    def test_regla_2_todos_los_errores_salen_juntos(self):
        """Patrón ABM, sección 2: un solo ``ValidationError`` con un error por campo."""
        error = self.error(nombre="", perfil_familia="", peso_promedio_planta="0", duracion_post_cosecha="")
        self.assertTrue({"nombre", "perfil_familia", "peso_promedio_planta", "duracion_post_cosecha"} <= set(error.error_dict))

    def test_regla_2_germinacion_y_maduracion_siguen_siendo_obligatorias(self):
        """PROD-ALT-VAR regla 4, aplicada a la modificación."""
        self.assertEqual(codigos_de(self.error(etapas=(("germinacion", "5"), ("crecimiento", "10"))), "etapas"), ["etapa_obligatoria"])


class EtapasTests(ModVarBase):
    """Regla 3: las etapas no se agregan ni se quitan si la variedad tiene lotes (aunque estén terminados); las duraciones sí se cambian."""

    def test_regla_3_con_lotes_no_se_agregan_etapas(self):
        """PROD-MOD-VAR regla 3: con lotes (aunque estén terminados), no se agregan etapas."""
        corta = variedad_con_semilla(self.cultivo, "Corta", etapas=[("germinacion", 5), ("maduracion", 20)])
        with con_lotes(corta, activos=0):
            error = error_de(
                lambda: variedades.modificar_variedad(
                    self.ana, corta.pk, datos_de(corta, etapas=(("germinacion", "5"), ("crecimiento", "10"), ("maduracion", "20")))
                )
            )
        self.assertEqual(codigos_de(error, "etapas"), ["etapas_con_lotes"])
        self.assertEqual(EtapaProductiva.objects.filter(ciclo__variedad=corta).count(), 2)

    def test_regla_3_con_lotes_no_se_quitan_etapas(self):
        """PROD-MOD-VAR regla 3: con lotes no se quitan etapas (el origen de las transiciones se deduce de su orden, regla 5 de 8.20)."""
        with con_lotes(self.variedad):
            error = self.error(etapas=(("germinacion", "5"), ("maduracion", "20")))
        self.assertEqual(codigos_de(error, "etapas"), ["etapas_con_lotes"])
        self.assertEqual(EtapaProductiva.objects.filter(ciclo__variedad=self.variedad).count(), 3)

    def test_regla_3_con_lotes_las_duraciones_si_se_cambian(self):
        """PROD-MOD-VAR regla 3: las duraciones se cambian siempre y rigen para los cálculos desde ese momento."""
        with con_lotes(self.variedad):
            self.modificar(etapas=(("germinacion", "6"), ("crecimiento", "10"), ("maduracion", "25")))
        self.assertEqual(ciclos.duracion_del_ciclo([self.variedad.pk])[self.variedad.pk], 41)
        self.assertEqual(ciclos.dias_hasta_maduracion([self.variedad.pk])[self.variedad.pk], 16)

    def test_regla_3_sin_lotes_se_pueden_quitar_y_agregar_etapas(self):
        """PROD-MOD-VAR regla 3: sin lotes, las etapas se agregan y se quitan; el ciclo sigue el orden del catálogo."""
        self.modificar(etapas=(("germinacion", "5"), ("maduracion", "20")))
        self.assertEqual([e.codigo for e in ciclos.etapas_de([self.variedad.pk])[self.variedad.pk]], ["germinacion", "maduracion"])
        self.assertEqual(EtapaProductiva.objects.filter(ciclo__variedad=self.variedad).count(), 2)
        self.modificar(etapas=(("maduracion", "20"), ("crecimiento", "8"), ("germinacion", "5")))
        self.assertEqual(
            [(e.codigo, e.duracion_dias) for e in ciclos.etapas_de([self.variedad.pk])[self.variedad.pk]],
            [("germinacion", 5), ("crecimiento", 8), ("maduracion", 20)],
        )
        self.assertEqual(Ciclo.objects.filter(variedad=self.variedad).count(), 1)

    def test_regla_3_una_etapa_que_sigue_conserva_su_fila(self):
        """Solo cambia lo que cambió: la etapa cuya duración se actualiza es la misma fila (no se borra y se vuelve a crear)."""
        antes = EtapaProductiva.objects.get(ciclo__variedad=self.variedad, tipo_etapa__codigo="germinacion").pk
        self.modificar(etapas=(("germinacion", "9"), ("crecimiento", "10"), ("maduracion", "20")))
        self.assertEqual(EtapaProductiva.objects.get(ciclo__variedad=self.variedad, tipo_etapa__codigo="germinacion").pk, antes)


class PerfilTests(ModVarBase):
    """Regla 4: el perfil no se cambia mientras la variedad tenga lotes activos u órdenes a realizar."""

    def test_regla_4_con_lotes_activos_no_se_cambia_el_perfil(self):
        """PROD-MOD-VAR regla 4: con lotes activos, error en ``perfil_familia``."""
        with con_lotes(self.variedad, activos=2):
            error = self.error(perfil_familia="pastura")
        self.assertEqual(codigos_de(error, "perfil_familia"), ["perfil_con_lotes_u_ordenes"])
        self.assertEqual(self.recargada().perfil_familia, "hoja_verde")

    def test_regla_4_con_ordenes_a_realizar_no_se_cambia_el_perfil(self):
        """PROD-MOD-VAR regla 4: con órdenes a realizar (de siembra o de transición), tampoco."""
        with con_lotes(self.variedad, activos=0, ordenes=1):
            error = self.error(perfil_familia="pastura")
        self.assertEqual(codigos_de(error, "perfil_familia"), ["perfil_con_lotes_u_ordenes"])

    def test_regla_4_con_lotes_terminados_el_perfil_si_se_cambia(self):
        """PROD-MOD-VAR regla 4: solo bloquean los lotes ACTIVOS y las órdenes a realizar; los terminados no."""
        with con_lotes(self.variedad, activos=0, ordenes=0):
            self.assertEqual(self.modificar(perfil_familia="pastura").perfil_familia, "pastura")

    def test_regla_4_sin_lotes_ni_ordenes_el_perfil_se_cambia(self):
        """PROD-MOD-VAR regla 4: sin lotes ni órdenes el perfil se cambia."""
        self.assertEqual(self.modificar(perfil_familia="hierbas").perfil_familia, "hierbas")

    def test_regla_4_con_lotes_activos_reenviar_el_mismo_perfil_no_molesta(self):
        """PROD-MOD-VAR regla 4: lo que se bloquea es CAMBIAR el perfil, no reenviarlo igual."""
        with con_lotes(self.variedad, activos=2):
            self.assertEqual(self.modificar(nombre="Otra").nombre_variedad, "Otra")

    def test_regla_4_un_cambio_de_perfil_que_deja_una_etapa_no_permitida_da_error_en_el_perfil(self):
        """variedades.md, «Perfil y etapas permitidas»: un cambio de perfil que deje una etapa no permitida se rechaza con un error en
        el campo del perfil."""
        tomate = variedad_con_semilla(
            self.cultivo, "Cherry", perfil="frutos_pequenos", etapas=[("germinacion", 5), ("floracion", 7), ("maduracion", 20)]
        )
        error = error_de(lambda: variedades.modificar_variedad(self.ana, tomate.pk, datos_de(tomate, perfil_familia="hoja_verde")))
        self.assertEqual(codigos_de(error, "perfil_familia"), ["etapa_no_permitida"])
        self.assertEqual(self.recargada(tomate).perfil_familia, "frutos_pequenos")

    def test_regla_4_agregar_una_etapa_no_permitida_sin_cambiar_el_perfil_da_error_en_etapas(self):
        """PROD-ALT-VAR regla 4: si el perfil no cambió, el error de la etapa no permitida va en ``etapas``."""
        error = self.error(etapas=(("germinacion", "5"), ("floracion", "7"), ("maduracion", "20")))
        self.assertEqual(codigos_de(error, "etapas"), ["etapa_no_permitida"])


class AdvertenciaDeRangosTests(ModVarBase):
    """Regla 5: advertir si un cambio de rangos deja incompatible a la variedad (con lotes activos) con otra de un invernadero."""

    def setUp(self):
        super().setUp()
        self.otra = variedad_con_semilla(self.cultivo, "Lisa")  # 18-24 °C, igual que Crespa

    def con_lotes_y_presentes(self):
        """Crespa con lotes activos en Norte, donde también está Lisa."""
        return con_lotes(self.variedad, invernaderos=[self.norte]), variedades_presentes_de_prueba({self.norte.pk: {self.variedad.pk, self.otra.pk}})

    def test_regla_5_si_el_cambio_deja_incompatible_pide_confirmar_y_no_cambia_nada(self):
        """PROD-MOD-VAR regla 5: se advierte en qué invernadero y en qué variable; ``FaltaConfirmarAdvertencia`` y nada cambia."""
        lotes, presentes = self.con_lotes_y_presentes()
        with lotes, presentes, self.assertRaises(FaltaConfirmarAdvertencia) as contexto:
            self.modificar(temp_ambiente_min="30", temp_ambiente_max="35")
        self.assertEqual(
            contexto.exception.avisos, [variedades.Incompatibilidad(self.norte.pk, "temp_ambiente", self.otra.pk)]
        )
        self.assertEqual(self.recargada().temp_ambiente_min, Decimal("18.00"))
        self.assertFalse(self.registros().exists())

    def test_regla_5_guardar_igual_aplica_el_cambio(self):
        """PROD-MOD-VAR regla 5: «guardar igual» (``advertencia_confirmada``): los lotes siguen donde están y se guarda con el rango nuevo."""
        lotes, presentes = self.con_lotes_y_presentes()
        with lotes, presentes:
            variedad = self.modificar(temp_ambiente_min="30", temp_ambiente_max="35", advertencia_confirmada=True)
        self.assertEqual(variedad.temp_ambiente_min, Decimal("30.00"))
        self.assertEqual(self.registros().count(), 1)

    def test_regla_5_un_cambio_que_no_toca_los_rangos_no_advierte(self):
        """Advertencia de rangos: solo si el cambio modifica algún rango (aunque hoy ya hubiera incompatibilidad)."""
        lotes, presentes = self.con_lotes_y_presentes()
        with lotes, presentes:
            self.assertEqual(self.modificar(nombre="Otra").nombre_variedad, "Otra")

    def test_regla_5_un_cambio_de_rangos_compatible_no_advierte(self):
        """PROD-MOD-VAR regla 5: si el rango nuevo se cruza con el de las otras variedades, no hay advertencia."""
        lotes, presentes = self.con_lotes_y_presentes()
        with lotes, presentes:
            self.assertEqual(self.modificar(temp_ambiente_min="20", temp_ambiente_max="30").temp_ambiente_max, Decimal("30.00"))

    def test_regla_5_sin_lotes_activos_no_hay_advertencia(self):
        """PROD-MOD-VAR regla 5: solo si la variedad tiene lotes activos."""
        with variedades_presentes_de_prueba({self.norte.pk: {self.variedad.pk, self.otra.pk}}):
            self.assertEqual(self.modificar(temp_ambiente_min="30", temp_ambiente_max="35").temp_ambiente_min, Decimal("30.00"))

    def test_regla_5_el_resumen_trae_las_advertencias_sin_lanzar(self):
        """PROD-MOD-VAR regla 8: el resumen muestra la advertencia antes de guardar (no la lanza)."""
        lotes, presentes = self.con_lotes_y_presentes()
        with lotes, presentes:
            resumen = variedades.resumen_de_modificacion(
                self.ana, self.variedad.pk, datos_de(self.variedad, temp_ambiente_min="30", temp_ambiente_max="35")
            )
        self.assertEqual(resumen.advertencias, [variedades.Incompatibilidad(self.norte.pk, "temp_ambiente", self.otra.pk)])


class SemillaTests(ModVarBase):
    """Regla 6 y postcondición b: si cambia el nombre, cambia el de su semilla."""

    def test_post_b_el_cambio_de_nombre_renombra_la_semilla(self):
        """PROD-MOD-VAR postcondición b y regla 6: «Semilla {cultivo} {variedad nueva}», en la misma transacción."""
        self.modificar(nombre="Butterhead")
        self.assertEqual(Insumo.objects.get(pk=self.variedad.semilla.pk).nombre_insumo, "Semilla Lechuga Butterhead")

    def test_post_b_si_el_nombre_no_cambia_la_semilla_no_se_toca(self):
        """PROD-MOD-VAR postcondición b: solo si cambió el nombre."""
        self.modificar(peso_promedio_planta="200")
        self.assertEqual(Insumo.objects.get(pk=self.variedad.semilla.pk).nombre_insumo, "Semilla Lechuga Crespa")

    def test_post_b_el_renombre_no_toca_las_existencias_de_la_semilla(self):
        """docs/api/variedades.md: ninguna función de semillas toca existencias."""
        iin = existencia(self.variedad.semilla, self.norte)
        self.modificar(nombre="Butterhead")
        iin.refresh_from_db()
        self.assertEqual((InsumoInvernadero.objects.count(), iin.estado_insumo_invernadero), (1, "activo"))

    def test_regla_6_si_el_nombre_de_la_semilla_ya_lo_usa_otro_insumo_es_un_error_del_campo_nombre(self):
        """Decisión del 22/11/2026: ``semilla_repetida`` en ``nombre``; no se cambia nada (ni la variedad)."""
        insumo("Semilla Lechuga Butterhead", tipo=tipo_de_insumo("Varios"))
        self.assertEqual(codigos_de(self.error(nombre="Butterhead"), "nombre"), ["semilla_repetida"])
        self.assertEqual(self.recargada().nombre_variedad, "Crespa")
        self.assertEqual(Insumo.objects.get(pk=self.variedad.semilla.pk).nombre_insumo, "Semilla Lechuga Crespa")

    def test_regla_6_el_resumen_informa_el_nombre_nuevo_de_la_semilla(self):
        """PROD-MOD-VAR regla 6 y 8: el Sistema informa el nuevo nombre de la semilla antes de confirmar; ``None`` si no cambia."""
        con_cambio = variedades.resumen_de_modificacion(self.ana, self.variedad.pk, datos_de(self.variedad, nombre="Butterhead"))
        sin_cambio = variedades.resumen_de_modificacion(self.ana, self.variedad.pk, datos_de(self.variedad, peso_promedio_planta="200"))
        self.assertEqual((con_cambio.nombre_semilla, sin_cambio.nombre_semilla), ("Semilla Lechuga Butterhead", None))


class NotificacionesTests(ModVarBase):
    """Postcondición c y regla 7: al Agrónomo de cada OTRO invernadero que usa la variedad, una vez por cuenta, solo si cambió el nombre,
    las duraciones, las etapas o los rangos; sin el actor; sin Agrónomo no se avisa (D-14); dentro de la transacción (D-42)."""

    def setUp(self):
        super().setUp()
        existencia(self.variedad.semilla, self.norte)
        existencia(self.variedad.semilla, self.sur)

    def avisos_de(self, cuenta):
        return list(Notificacion.objects.filter(destinatario=cuenta))

    def test_post_c_cambiar_el_nombre_avisa_al_agronomo_del_otro_invernadero_y_no_al_actor(self):
        """PROD-MOD-VAR postcondición c y regla 7: Beto (Sur) recibe el aviso; Ana, que actúa, no."""
        self.modificar(nombre="Butterhead")
        (aviso,) = self.avisos_de(self.beto)
        self.assertEqual(aviso.titulo, "Cambió la variedad Lechuga Crespa")
        self.assertIn("Invernadero Sur", aviso.detalle)
        self.assertIn("Butterhead", aviso.detalle)
        self.assertEqual(self.avisos_de(self.ana), [])

    def test_regla_7_cada_cambio_que_corresponde_avisa(self):
        """PROD-MOD-VAR regla 7: nombre, duraciones, etapas o rangos avisan; cada uno por separado."""
        casos = {
            "duracion": {"etapas": (("germinacion", "6"), ("crecimiento", "10"), ("maduracion", "20"))},
            "etapas": {"etapas": (("germinacion", "5"), ("maduracion", "20"))},
            "rangos": {"humedad_max": "85"},
        }
        for nombre, cambios in casos.items():
            with self.subTest(cambio=nombre):
                Notificacion.objects.all().delete()
                self.modificar(**cambios)
                self.assertEqual(len(self.avisos_de(self.beto)), 1)

    def test_regla_7_el_perfil_la_postcosecha_y_el_peso_no_avisan(self):
        """PROD-MOD-VAR regla 7: solo nombre, duraciones, etapas o rangos; no perfil, postcosecha ni peso."""
        self.modificar(perfil_familia="pastura", duracion_post_cosecha="9", peso_promedio_planta="300")
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertEqual(self.registros().count(), 1)

    def test_regla_7_un_agronomo_con_dos_invernaderos_recibe_un_solo_aviso_con_los_dos(self):
        """Decisiones de aplicación, «Notificaciones»: una vez por cuenta (no por invernadero), con los invernaderos que le corresponden."""
        este = crear_invernadero("Invernadero Este", agronomo=self.beto)
        existencia(self.variedad.semilla, este)
        self.modificar(nombre="Butterhead")
        (aviso,) = self.avisos_de(self.beto)
        self.assertIn("Invernadero Sur", aviso.detalle)
        self.assertIn("Invernadero Este", aviso.detalle)

    def test_regla_7_un_invernadero_sin_agronomo_no_recibe_nada(self):
        """D-14: sin Agrónomo no se avisa ni falla."""
        existencia(self.variedad.semilla, crear_invernadero("Invernadero Oeste"))
        self.modificar(nombre="Butterhead")
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_regla_7_los_invernaderos_con_lotes_activos_tambien_cuentan_como_usuarios(self):
        """PROD-MOD-VAR regla 1: también usa la variedad el invernadero con lotes activos de ella."""
        gaby = crear_agronomo("gaby@infoponia.com", nombre="Gaby", apellido="Ruiz")
        este = crear_invernadero("Invernadero Este", agronomo=gaby)
        with con_lotes(self.variedad, invernaderos=[este]):
            self.modificar(nombre="Butterhead")
        self.assertEqual(len(self.avisos_de(gaby)), 1)

    def test_regla_7_un_invernadero_inactivo_no_recibe_aviso(self):
        """PROD-MOD-VAR regla 1: solo cuentan los invernaderos activos."""
        gaby = crear_agronomo("gaby@infoponia.com")
        viejo = crear_invernadero("Invernadero Viejo", activo=False, agronomo=gaby)
        existencia(self.variedad.semilla, viejo)
        self.modificar(nombre="Butterhead")
        self.assertEqual(self.avisos_de(gaby), [])

    def test_regla_7_el_aviso_va_dentro_de_la_transaccion(self):
        """D-42: si el caso de uso falla (por ejemplo, la auditoría), no queda ni el cambio ni la notificación."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla simulada")):
            with self.assertRaises(RuntimeError):
                self.modificar(nombre="Butterhead")
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertEqual(self.recargada().nombre_variedad, "Crespa")
        self.assertEqual(Insumo.objects.get(pk=self.variedad.semilla.pk).nombre_insumo, "Semilla Lechuga Crespa")

    def test_regla_8_el_resumen_dice_a_quienes_se_notificara_y_no_notifica(self):
        """PROD-MOD-VAR regla 7: el Sistema avisa a quiénes notificará antes de confirmar; y la notificación no se manda desde el resumen."""
        resumen = variedades.resumen_de_modificacion(self.ana, self.variedad.pk, datos_de(self.variedad, nombre="Butterhead"))
        self.assertEqual(resumen.a_notificar, ["Invernadero Sur"])
        self.assertEqual(Notificacion.objects.count(), 0)
        sin_aviso = variedades.resumen_de_modificacion(self.ana, self.variedad.pk, datos_de(self.variedad, peso_promedio_planta="9"))
        self.assertEqual(sin_aviso.a_notificar, [])


class PostcondicionesTests(ModVarBase):
    """Postcondiciones a y e: datos actualizados y un único registro de auditoría con lo que cambió."""

    def test_post_a_se_actualizan_los_datos_el_ciclo_y_las_etapas(self):
        """PROD-MOD-VAR postcondición a: datos de la variedad, de su ciclo y de sus etapas."""
        self.modificar(
            nombre="Butterhead", perfil_familia="pastura", temp_ambiente_min="17,5", fotoperiodo_max="18",
            duracion_post_cosecha="10", peso_promedio_planta="210",
            etapas=(("germinacion", "6"), ("maduracion", "22")),
        )
        v = self.recargada()
        self.assertEqual((v.nombre_variedad, v.perfil_familia), ("Butterhead", "pastura"))
        self.assertEqual((v.temp_ambiente_min, v.fotoperiodo_max), (Decimal("17.50"), Decimal("18.00")))
        self.assertEqual((v.duracion_post_cosecha, v.peso_promedio_planta), (10, 210))
        self.assertEqual([(e.codigo, e.duracion_dias) for e in ciclos.etapas_de([v.pk])[v.pk]], [("germinacion", 6), ("maduracion", 22)])

    def test_post_e_un_solo_registro_con_usuario_y_solo_lo_que_cambio(self):
        """PROD-MOD-VAR postcondición e y D-36: ``cambios`` con «antes» y «después» solo de lo que cambió; números como texto."""
        self.modificar(nombre="Butterhead", humedad_max="85", duracion_post_cosecha="10")
        registro = self.registros().get()
        self.assertEqual(registro.usuario_id, self.ana.pk)
        self.assertEqual(
            registro.detalle["cambios"],
            {
                "nombre": {"antes": "Crespa", "despues": "Butterhead"},
                "humedad_max": {"antes": "80.00", "despues": "85.00"},
                "duracion_post_cosecha": {"antes": "7", "despues": "10"},
                "nombre_semilla": {"antes": "Semilla Lechuga Crespa", "despues": "Semilla Lechuga Butterhead"},
            },
        )

    def test_post_e_las_etapas_van_como_lista_de_textos_antes_y_despues(self):
        """variedades.md, «Auditoría»: «etapas» antes y después, con una lista de textos «Germinación: 5 días»."""
        self.modificar(etapas=(("germinacion", "6"), ("maduracion", "20")))
        self.assertEqual(
            self.registros().get().detalle["cambios"]["etapas"],
            {
                "antes": ["Germinación: 5 días", "Crecimiento: 10 días", "Maduración: 20 días"],
                "despues": ["Germinación: 6 días", "Maduración: 20 días"],
            },
        )

    def test_post_e_los_afectados_son_la_variedad_y_lo_que_se_modifico(self):
        """PROD-MOD-VAR postcondición e: la variedad siempre; el ciclo y sus etapas si cambiaron las etapas; la semilla si se renombró."""
        etapas = {(e._meta.label_lower, e.pk) for e in EtapaProductiva.objects.filter(ciclo__variedad=self.variedad)}
        propios = {(self.variedad._meta.label_lower, self.variedad.pk)}
        semilla = {(self.variedad.semilla._meta.label_lower, self.variedad.semilla.pk)}
        ciclo = {(Ciclo._meta.label_lower, self.variedad.ciclo.pk)}

        self.modificar(peso_promedio_planta="200")
        self.assertEqual({(a["modelo"], a["id"]) for a in self.registros().get().afectados}, propios)

        self.modificar(nombre="Butterhead")
        ultimo = self.registros().order_by("-id").first()
        self.assertEqual({(a["modelo"], a["id"]) for a in ultimo.afectados}, propios | semilla)

        self.modificar(etapas=(("germinacion", "6"), ("crecimiento", "10"), ("maduracion", "20")))
        ultimo = self.registros().order_by("-id").first()
        afectados = {(a["modelo"], a["id"]) for a in ultimo.afectados}
        self.assertTrue(propios | ciclo <= afectados)
        self.assertTrue(any(modelo == EtapaProductiva._meta.label_lower for modelo, _ in afectados))
        self.assertFalse(semilla & afectados)
        self.assertTrue(afectados <= propios | ciclo | etapas)

    def test_post_e_un_registro_por_modificacion(self):
        """D-36: un registro por caso de uso."""
        self.modificar(nombre="Butterhead", humedad_max="85")
        self.assertEqual(self.registros().count(), 1)


class ResumenDeModificacionTests(ModVarBase):
    """Regla 8: el resumen muestra los datos nuevos, los valores anteriores cuando cambian y el nombre nuevo de la semilla, sin escribir."""

    def test_regla_8_el_resumen_trae_los_cambios_con_su_valor_anterior(self):
        """PROD-MOD-VAR regla 8: los valores anteriores cuando cambian (texto)."""
        resumen = variedades.resumen_de_modificacion(
            self.ana, self.variedad.pk, datos_de(self.variedad, nombre="Butterhead", humedad_max="85", duracion_post_cosecha="10")
        )
        self.assertTrue(resumen.hay_cambios)
        self.assertEqual(
            resumen.cambios,
            {
                "nombre": ("Crespa", "Butterhead"),
                "humedad_max": ("80.00", "85.00"),
                "duracion_post_cosecha": ("7", "10"),
            },
        )

    def test_regla_8_sin_cambios_el_resumen_lo_dice(self):
        """D-28: sin cambios no hay nada que confirmar."""
        resumen = variedades.resumen_de_modificacion(self.ana, self.variedad.pk, datos_de(self.variedad))
        self.assertEqual((resumen.hay_cambios, resumen.cambios, resumen.nombre_semilla, resumen.a_notificar), (False, {}, None, []))

    def test_regla_8_el_resumen_no_escribe_ni_audita(self):
        """PROD-MOD-VAR regla 8: el resumen no cambia nada."""
        variedades.resumen_de_modificacion(self.ana, self.variedad.pk, datos_de(self.variedad, nombre="Butterhead"))
        self.assertEqual(self.recargada().nombre_variedad, "Crespa")
        self.assertFalse(RegistroAuditoria.objects.filter(accion="modificacion_variedad").exists())

    def test_regla_8_el_resumen_valida_y_exige_lo_mismo_que_la_modificacion(self):
        """PROD-MOD-VAR regla 8: el resumen rechaza lo que rechaza la modificación (datos, permisos y variedad inactiva)."""
        error = error_de(lambda: variedades.resumen_de_modificacion(self.ana, self.variedad.pk, datos_de(self.variedad, nombre="")))
        self.assertEqual(codigos_de(error, "nombre"), ["obligatorio"])
        with self.assertRaises(PermissionDenied):
            variedades.resumen_de_modificacion(crear_gerente(), self.variedad.pk, datos_de(self.variedad))
        inactiva = variedad_con_semilla(self.cultivo, "Vieja", activa=False)
        error = error_de(lambda: variedades.resumen_de_modificacion(self.ana, inactiva.pk, datos_de(inactiva)))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["variedad_inactiva"])
