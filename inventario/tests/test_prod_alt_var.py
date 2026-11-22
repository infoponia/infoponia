# Pruebas de PROD-ALT-VAR · Alta Variedad (INV-03, paso 4) y de la creación de su semilla (`inventario/servicios/semillas.py`).
# Fuente: docs/casos_de_uso/inventario/variedades.md (reglas 1 a 10, precondiciones a a c, postcondiciones a a d y «Decisiones de
# aplicación»), D-36 (auditoría), D-49 y docs/api/variedades.md. Cada regla y postcondición tiene su prueba.
#
# Contrato que fijan estas pruebas:
#   - ``DatosDeVariedad`` (dataclass; todo lo escrito llega como texto o número crudo): ``nombre``, ``perfil_familia``, ``etapas`` (pares
#     ``(codigo, dias)``), los ocho límites de los rangos, ``duracion_post_cosecha`` y ``peso_promedio_planta``.
#   - ``resumen_de_alta(actor, cultivo_id, datos)`` valida todo y devuelve ``ResumenDeAlta`` SIN escribir; ``alta_variedad(actor,
#     cultivo_id, datos)`` vuelve a validar dentro de la transacción y crea todo o nada.
#   - Errores: un solo ``ValidationError`` con un error por campo. Campos: ``nombre``, ``perfil_familia``, ``etapas``,
#     ``duracion_<codigo>`` (por etapa), ``<variable>_min`` y ``<variable>_max`` de cada rango, ``duracion_post_cosecha`` y
#     ``peso_promedio_planta``. Un cultivo inactivo es un error general (``cultivo_inactivo``).

from decimal import Decimal
from unittest import mock

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.models import Insumo, InsumoInvernadero, Semilla
from inventario.tests.fabricas import ConDatosDeInventario, insumo, perezoso, tipo_de_insumo, variedad_con_semilla
from maestros.models import Ciclo, EtapaProductiva, Variedad
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_cultivo, error_de

variedades = perezoso("inventario.servicios.variedades")
semillas = perezoso("inventario.servicios.semillas")
ciclos = perezoso("inventario.servicios.ciclos")

ETAPAS_BASICAS = (("germinacion", "5"), ("crecimiento", "10"), ("maduracion", "20"))


def datos(**cambios):
    """Los ``DatosDeVariedad`` de una variedad válida (hoja verde, 35 días de ciclo, 15 hasta la maduración); ``cambios`` pisa campos."""
    base = {
        "nombre": "Butterhead",
        "perfil_familia": "hoja_verde",
        "etapas": ETAPAS_BASICAS,
        "temp_ambiente_min": "18.5", "temp_ambiente_max": "24",
        "humedad_min": "60", "humedad_max": "80",
        "intensidad_luz_min": "200", "intensidad_luz_max": "400",
        "fotoperiodo_min": "12", "fotoperiodo_max": "16",
        "duracion_post_cosecha": "7",
        "peso_promedio_planta": "150",
    }
    base.update(cambios)
    return variedades.DatosDeVariedad(**base)


class AltaVariedadBase(ConDatosDeInventario, TestCase):
    """Un Agrónomo sin invernadero (regla 1: no pertenece a un invernadero) y el cultivo «Lechuga»."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.cultivo = crear_cultivo("Lechuga")

    def alta(self, **cambios):
        return variedades.alta_variedad(self.agronomo, self.cultivo.pk, datos(**cambios))

    def error(self, **cambios):
        return error_de(lambda: self.alta(**cambios))

    def nada_creado(self):
        """Verdadero si no quedó ninguna fila de las que crea el alta (todo o nada)."""
        return not (
            Variedad.objects.exists()
            or Ciclo.objects.exists()
            or EtapaProductiva.objects.exists()
            or Semilla.objects.exists()
            or RegistroAuditoria.objects.filter(accion="alta_variedad").exists()
        )


class PreCondicionesTests(AltaVariedadBase):
    """Precondiciones a y b."""

    def test_pre_a_un_gerente_no_da_de_alta(self):
        """PROD-ALT-VAR precondición a: solo un Agrónomo activo."""
        with self.assertRaises(PermissionDenied):
            variedades.alta_variedad(crear_gerente(), self.cultivo.pk, datos())
        self.assertTrue(self.nada_creado())

    def test_pre_a_un_agronomo_inactivo_no_da_de_alta(self):
        """PROD-ALT-VAR precondición a: la cuenta tiene que estar activa."""
        with self.assertRaises(PermissionDenied):
            variedades.alta_variedad(crear_agronomo("inactivo@infoponia.com", activo=False), self.cultivo.pk, datos())

    def test_pre_b_un_cultivo_inactivo_no_admite_variedades(self):
        """PROD-ALT-VAR precondición b: el cultivo está activo (se verifica DESPUÉS de bloquearlo): error general ``cultivo_inactivo``."""
        self.cultivo.estado_cultivo = "inactivo"
        self.cultivo.save()
        error = self.error()
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["cultivo_inactivo"])
        self.assertTrue(self.nada_creado())

    def test_pre_b_un_cultivo_inexistente_da_404(self):
        """PROD-ALT-VAR precondición b: un cultivo que no existe es 404."""
        with self.assertRaises(Http404):
            variedades.alta_variedad(self.agronomo, 999999, datos())


class FlujoYPostcondicionesTests(AltaVariedadBase):
    """Flujo principal y postcondiciones a, b y c."""

    def test_flujo_principal_crea_todo_y_devuelve_la_variedad(self):
        """PROD-ALT-VAR: el alta crea variedad, ciclo, etapas y semilla; cualquier Agrónomo activo, sin invernadero (regla 1)."""
        variedad = self.alta()
        self.assertIsInstance(variedad, Variedad)
        self.assertEqual(
            (Variedad.objects.count(), Ciclo.objects.count(), EtapaProductiva.objects.count(), Semilla.objects.count()), (1, 1, 3, 1)
        )

    def test_post_a_la_variedad_queda_activa_con_sus_datos(self):
        """PROD-ALT-VAR postcondición a: activa, asociada a su cultivo, con nombre, perfil, rangos, postcosecha y peso."""
        variedad = Variedad.objects.get(pk=self.alta().pk)
        self.assertEqual((variedad.cultivo, variedad.nombre_variedad, variedad.perfil_familia), (self.cultivo, "Butterhead", "hoja_verde"))
        self.assertEqual(variedad.estado_variedad, "activo")
        self.assertEqual((variedad.temp_ambiente_min, variedad.temp_ambiente_max), (Decimal("18.50"), Decimal("24.00")))
        self.assertEqual((variedad.humedad_min, variedad.humedad_max), (Decimal("60.00"), Decimal("80.00")))
        self.assertEqual((variedad.intensidad_luz_min, variedad.intensidad_luz_max), (Decimal("200.00"), Decimal("400.00")))
        self.assertEqual((variedad.fotoperiodo_min, variedad.fotoperiodo_max), (Decimal("12.00"), Decimal("16.00")))
        self.assertEqual((variedad.duracion_post_cosecha, variedad.peso_promedio_planta), (7, 150))

    def test_post_b_se_crea_el_ciclo_con_una_etapa_por_tipo_incluido(self):
        """PROD-ALT-VAR postcondición b: un ciclo y una etapa por cada tipo incluido, con su duración, y la duración total derivada."""
        variedad = self.alta()
        etapas = ciclos.etapas_de([variedad.pk])[variedad.pk]
        self.assertEqual([(e.codigo, e.duracion_dias) for e in etapas], [("germinacion", 5), ("crecimiento", 10), ("maduracion", 20)])
        self.assertEqual(ciclos.duracion_del_ciclo([variedad.pk])[variedad.pk], 35)
        self.assertEqual(ciclos.dias_hasta_maduracion([variedad.pk])[variedad.pk], 15)
        self.assertTrue(Ciclo.objects.filter(variedad=variedad).exists())

    def test_post_c_se_crea_su_semilla_como_pide_el_caso_de_uso(self):
        """PROD-ALT-VAR postcondición c: «Semilla {cultivo} {variedad}», activa, categoría Semillas, por unidad, con control de
        vencimiento, asociada a la variedad y sin habilitar en ningún invernadero."""
        variedad = self.alta()
        semilla = Semilla.objects.get(variedad=variedad)
        self.assertEqual(semilla.nombre_insumo, "Semilla Lechuga Butterhead")
        self.assertEqual((semilla.estado_insumo, semilla.tipo_insumo.codigo), ("activo", "semillas"))
        self.assertEqual((semilla.unidad_medida_insumo, semilla.controla_vencimiento), ("unidad", True))
        self.assertFalse(InsumoInvernadero.objects.exists())

    def test_post_c_el_alta_no_toca_existencias_ni_invernaderos(self):
        """PROD-ALT-VAR regla 9: habilitar la semilla es un paso aparte (CMP-HAB-IIN); el alta no crea ``InsumoInvernadero``."""
        self.alta()
        self.assertEqual(InsumoInvernadero.objects.count(), 0)

    def test_regla_1_cualquier_agronomo_activo_da_de_alta(self):
        """PROD-ALT-VAR regla 1: la variedad no pertenece a un invernadero; otro Agrónomo cualquiera también puede."""
        otro = crear_agronomo("otro@infoponia.com")
        self.assertIsNotNone(variedades.alta_variedad(otro, self.cultivo.pk, datos()).pk)


class AuditoriaTests(AltaVariedadBase):
    """Postcondición d y D-36: un solo registro por caso de uso."""

    def test_post_d_un_solo_registro_con_variedad_ciclo_etapas_y_semilla_como_afectados(self):
        """PROD-ALT-VAR postcondición d y D-49: un registro ``alta_variedad`` con usuario y los cuatro tipos de objeto creados."""
        variedad = self.alta()
        registros = RegistroAuditoria.objects.filter(accion="alta_variedad")
        self.assertEqual(registros.count(), 1)
        registro = registros.get()
        self.assertEqual(registro.usuario_id, self.agronomo.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        esperados = {(variedad._meta.label_lower, variedad.pk), (Ciclo._meta.label_lower, variedad.ciclo.pk), (Semilla._meta.label_lower, variedad.semilla.pk)}
        esperados |= {(EtapaProductiva._meta.label_lower, e.pk) for e in EtapaProductiva.objects.filter(ciclo=variedad.ciclo)}
        self.assertEqual(afectados, esperados)
        self.assertEqual(len(afectados), 6)

    def test_post_d_los_cambios_llevan_los_datos_nuevos_con_antes_nulo_y_los_rangos_como_texto(self):
        """D-36: ``cambios`` con «antes» nulo; los ``Decimal`` van como texto (``_validar_valor`` rechaza ``Decimal``)."""
        self.alta()
        cambios = RegistroAuditoria.objects.get(accion="alta_variedad").detalle["cambios"]
        self.assertEqual(cambios["nombre"], {"antes": None, "despues": "Butterhead"})
        self.assertEqual(cambios["perfil_familia"], {"antes": None, "despues": "hoja_verde"})
        self.assertEqual(cambios["estado"], {"antes": None, "despues": "activo"})
        self.assertEqual(cambios["temp_ambiente_min"], {"antes": None, "despues": "18.50"})
        self.assertEqual(cambios["fotoperiodo_max"], {"antes": None, "despues": "16.00"})
        self.assertEqual(cambios["duracion_post_cosecha"], {"antes": None, "despues": "7"})
        self.assertEqual(str(cambios["peso_promedio_planta"]["despues"]), "150")

    def test_post_d_los_datos_llevan_el_cultivo_las_etapas_y_el_nombre_de_la_semilla(self):
        """D-49 y variedades.md, «Auditoría»: ``datos`` con el cultivo (referencia), las etapas incluidas con su duración (lista de
        textos) y la semilla creada."""
        self.alta()
        datos_del_registro = RegistroAuditoria.objects.get(accion="alta_variedad").detalle["datos"]
        self.assertEqual(datos_del_registro["cultivo"], {"id": self.cultivo.pk, "texto": "Lechuga"})
        self.assertEqual(datos_del_registro["etapas"], ["Germinación: 5 días", "Crecimiento: 10 días", "Maduración: 20 días"])
        self.assertEqual(datos_del_registro["nombre_semilla"], "Semilla Lechuga Butterhead")

    def test_post_d_un_error_no_deja_registro(self):
        """D-22: no queda un registro de una operación que no se hizo."""
        self.error(nombre="")
        self.assertFalse(RegistroAuditoria.objects.filter(accion="alta_variedad").exists())

    def test_post_d_si_falla_la_auditoria_no_queda_nada_creado(self):
        """D-22 y «Todo en una transacción»: si la auditoría falla, se deshacen la variedad, el ciclo, las etapas y la semilla."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla simulada")):
            with self.assertRaises(RuntimeError):
                self.alta()
        self.assertTrue(self.nada_creado())


class NombreTests(AltaVariedadBase):
    """Regla 2 (y precondición c): nombre obligatorio, recortado, único dentro del cultivo, de hasta 50 caracteres."""

    def test_regla_2_el_nombre_es_obligatorio(self):
        """PROD-ALT-VAR regla 2: sin nombre, error en el campo ``nombre``."""
        self.assertEqual(codigos_de(self.error(nombre="   "), "nombre"), ["obligatorio"])

    def test_regla_2_el_nombre_necesita_alguna_letra_o_numero(self):
        """Mismo criterio que cultivos e insumos: un texto sin contenido se rechaza."""
        self.assertEqual(codigos_de(self.error(nombre="!!!"), "nombre"), ["sin_contenido"])

    def test_regla_2_se_recortan_los_espacios_al_principio_y_al_final(self):
        """PROD-ALT-VAR regla 2: sin espacios al principio o al final; se guarda recortado y la semilla también lo usa."""
        variedad = self.alta(nombre="  Butterhead  ")
        self.assertEqual(variedad.nombre_variedad, "Butterhead")
        self.assertEqual(variedad.semilla.nombre_insumo, "Semilla Lechuga Butterhead")

    def test_regla_2_repetido_con_otras_mayusculas_y_con_espacios(self):
        """PROD-ALT-VAR precondición c y regla 2: único dentro del cultivo sin distinguir mayúsculas ni espacios al borde."""
        self.alta()
        for repetido in ("butterhead", "BUTTERHEAD", "  Butterhead ", " bUtTeRhEaD"):
            with self.subTest(nombre=repetido):
                self.assertEqual(codigos_de(self.error(nombre=repetido), "nombre"), ["nombre_repetido"])
        self.assertEqual(Variedad.objects.count(), 1)

    def test_regla_2_se_cuentan_tambien_las_variedades_dadas_de_baja(self):
        """PROD-ALT-VAR regla 2: una variedad inactiva sigue ocupando su nombre."""
        variedad_con_semilla(self.cultivo, "Butterhead", activa=False)
        self.assertEqual(codigos_de(self.error(), "nombre"), ["nombre_repetido"])

    def test_regla_2_el_mismo_nombre_en_otro_cultivo_es_valido(self):
        """PROD-ALT-VAR regla 2: dos cultivos pueden tener variedades con el mismo nombre."""
        variedad_con_semilla(crear_cultivo("Acelga"), "Butterhead")
        self.assertEqual(self.alta().nombre_variedad, "Butterhead")

    def test_regla_2_el_nombre_admite_hasta_50_caracteres_y_la_semilla_entra_en_100(self):
        """D-49: variedad hasta 50 y cultivo hasta 40; «Semilla {cultivo} {variedad}» llega a 99 y entra en los 100 del insumo."""
        largo = crear_cultivo("C" * 40)
        variedad = variedades.alta_variedad(self.agronomo, largo.pk, datos(nombre="V" * 50))
        self.assertEqual(len(variedad.semilla.nombre_insumo), 99)

    def test_regla_2_un_nombre_de_51_caracteres_se_rechaza(self):
        """D-49: más de 50 caracteres es un error del campo ``nombre`` (no se trunca)."""
        self.assertEqual(codigos_de(self.error(nombre="V" * 51), "nombre"), ["demasiado_largo"])

    def test_regla_10_el_nombre_de_la_semilla_ya_usado_por_un_insumo_se_rechaza_en_el_campo_nombre(self):
        """Decisión del 22/11/2026: si «Semilla {cultivo} {variedad}» choca con otro insumo, error de campo ``nombre`` (no un 500) y
        no se crea nada."""
        insumo("Semilla Lechuga Butterhead", tipo=tipo_de_insumo("Varios"))
        self.assertEqual(codigos_de(self.error(), "nombre"), ["semilla_repetida"])
        self.assertTrue(self.nada_creado())

    def test_regla_10_el_choque_entre_cultivo_y_variedad_con_el_mismo_texto_se_rechaza(self):
        """Decisión del 22/11/2026: «Lechuga Roja» + «Crespa» y «Lechuga» + «Roja Crespa» dan la misma semilla: la segunda se rechaza."""
        roja = crear_cultivo("Lechuga Roja")
        variedades.alta_variedad(self.agronomo, roja.pk, datos(nombre="Crespa"))
        self.assertEqual(codigos_de(self.error(nombre="Roja Crespa"), "nombre"), ["semilla_repetida"])
        self.assertEqual(Variedad.objects.count(), 1)


class PerfilYEtapasTests(AltaVariedadBase):
    """Reglas 3, 4 y 5: perfil familiar, etapas permitidas y duraciones."""

    def test_regla_3_el_perfil_es_obligatorio_y_del_catalogo(self):
        """PROD-ALT-VAR regla 3: el perfil se elige del catálogo fijo."""
        self.assertEqual(codigos_de(self.error(perfil_familia=""), "perfil_familia"), ["obligatorio"])
        self.assertEqual(codigos_de(self.error(perfil_familia="verdura"), "perfil_familia"), ["perfil_invalido"])

    def test_regla_3_los_seis_perfiles_son_validos(self):
        """PROD-ALT-VAR regla 3: Hoja verde, Pastura, Frutos grandes, Frutos pequeños, Flores y Hierbas."""
        for numero, perfil in enumerate(["hoja_verde", "pastura", "frutos_grandes", "frutos_pequenos", "flores", "hierbas"]):
            with self.subTest(perfil=perfil):
                self.assertEqual(self.alta(nombre=f"V{numero}", perfil_familia=perfil).perfil_familia, perfil)

    def test_regla_4_floracion_solo_para_frutos_grandes_pequenos_y_flores(self):
        """PROD-ALT-VAR regla 4: Floración se ofrece para Frutos grandes, Frutos pequeños y Flores; no para los demás."""
        con_floracion = (("germinacion", "5"), ("floracion", "7"), ("maduracion", "20"))
        for perfil in ("frutos_grandes", "frutos_pequenos", "flores"):
            with self.subTest(permitido=perfil):
                self.assertIsNotNone(self.alta(nombre=perfil, perfil_familia=perfil, etapas=con_floracion).pk)
        for perfil in ("hoja_verde", "pastura", "hierbas"):
            with self.subTest(rechazado=perfil):
                self.assertEqual(codigos_de(self.error(perfil_familia=perfil, etapas=con_floracion), "etapas"), ["etapa_no_permitida"])

    def test_regla_4_fructificacion_solo_para_frutos_grandes_y_pequenos(self):
        """PROD-ALT-VAR regla 4: Fructificación solo para Frutos grandes y Frutos pequeños."""
        con_fructificacion = (("germinacion", "5"), ("fructificacion", "7"), ("maduracion", "20"))
        for perfil in ("frutos_grandes", "frutos_pequenos"):
            with self.subTest(permitido=perfil):
                self.assertIsNotNone(self.alta(nombre=perfil, perfil_familia=perfil, etapas=con_fructificacion).pk)
        for perfil in ("hoja_verde", "pastura", "flores", "hierbas"):
            with self.subTest(rechazado=perfil):
                self.assertEqual(codigos_de(self.error(perfil_familia=perfil, etapas=con_fructificacion), "etapas"), ["etapa_no_permitida"])

    def test_regla_4_frutos_grandes_admite_las_cinco_etapas(self):
        """PROD-ALT-VAR regla 4: el perfil más amplio admite las cinco."""
        cinco = (("germinacion", "5"), ("crecimiento", "10"), ("floracion", "7"), ("fructificacion", "8"), ("maduracion", "20"))
        variedad = self.alta(perfil_familia="frutos_grandes", etapas=cinco)
        self.assertEqual(ciclos.duracion_del_ciclo([variedad.pk])[variedad.pk], 50)

    def test_regla_4_germinacion_y_maduracion_son_obligatorias(self):
        """PROD-ALT-VAR regla 4: sin Germinación o sin Maduración, error en ``etapas``."""
        for faltante in ("germinacion", "maduracion"):
            with self.subTest(sin=faltante):
                etapas = tuple(e for e in ETAPAS_BASICAS if e[0] != faltante)
                self.assertEqual(codigos_de(self.error(etapas=etapas), "etapas"), ["etapa_obligatoria"])

    def test_regla_4_crecimiento_es_optativa(self):
        """PROD-ALT-VAR regla 4: Crecimiento se puede omitir."""
        self.assertIsNotNone(self.alta(etapas=(("germinacion", "5"), ("maduracion", "20"))).pk)

    def test_regla_4_las_etapas_se_guardan_en_el_orden_del_catalogo_aunque_lleguen_desordenadas(self):
        """PROD-ALT-VAR regla 4: las etapas siguen el orden del catálogo de tipos de etapa."""
        variedad = self.alta(etapas=(("maduracion", "20"), ("crecimiento", "10"), ("germinacion", "5")))
        self.assertEqual([e.codigo for e in ciclos.etapas_de([variedad.pk])[variedad.pk]], ["germinacion", "crecimiento", "maduracion"])

    def test_regla_4_una_etapa_repetida_o_desconocida_se_rechaza(self):
        """El servicio no confía en la pantalla: un tipo repetido o que no existe es un error en ``etapas``."""
        self.assertEqual(codigos_de(self.error(etapas=ETAPAS_BASICAS + (("crecimiento", "3"),)), "etapas"), ["etapa_repetida"])
        self.assertEqual(codigos_de(self.error(etapas=ETAPAS_BASICAS + (("invierno", "3"),)), "etapas"), ["etapa_invalida"])

    def test_regla_5_la_duracion_de_cada_etapa_es_un_entero_mayor_que_cero(self):
        """PROD-ALT-VAR regla 5: 0, negativa, decimal, texto o vacía se rechazan, en el campo de esa etapa."""
        for malo in ("0", "-3", "2.5", "abc"):
            with self.subTest(dias=malo):
                etapas = (("germinacion", malo), ("crecimiento", "10"), ("maduracion", "20"))
                error = self.error(etapas=etapas)
                self.assertEqual(codigos_de(error, "duracion_germinacion"), ["entero_mayor_que_cero"])
                self.assertEqual(list(error.error_dict), ["duracion_germinacion"])
        self.assertEqual(
            codigos_de(self.error(etapas=(("germinacion", ""), ("maduracion", "20"))), "duracion_germinacion"), ["obligatorio"]
        )

    def test_regla_5_una_duracion_de_un_dia_es_valida(self):
        """PROD-ALT-VAR regla 5: el mínimo es 1 día."""
        self.assertIsNotNone(self.alta(etapas=(("germinacion", "1"), ("maduracion", "1"))).pk)


class RangosYPostcosechaTests(AltaVariedadBase):
    """Reglas 6 y 7 y los topes de D-49."""

    def test_regla_6_cada_limite_es_obligatorio(self):
        """PROD-ALT-VAR regla 6: mínimo y máximo obligatorios en los cuatro rangos."""
        for variable in ("temp_ambiente", "humedad", "intensidad_luz", "fotoperiodo"):
            for lado in ("min", "max"):
                with self.subTest(campo=f"{variable}_{lado}"):
                    error = self.error(**{f"{variable}_{lado}": ""})
                    self.assertEqual(codigos_de(error, f"{variable}_{lado}"), ["obligatorio"])

    def test_regla_6_un_texto_que_no_es_numero_se_rechaza(self):
        """PROD-ALT-VAR regla 6: el límite es un número."""
        self.assertEqual(codigos_de(self.error(temp_ambiente_min="caliente"), "temp_ambiente_min"), ["numero_invalido"])

    def test_regla_6_admite_decimales_con_coma_o_punto_y_hasta_dos(self):
        """Decisiones de aplicación, «Números»: acepta coma o punto y guarda ``Decimal`` con 2 decimales; más de 2 se rechaza."""
        self.assertEqual(self.alta(temp_ambiente_min="18,25").temp_ambiente_min, Decimal("18.25"))
        self.assertEqual(codigos_de(self.error(nombre="Otra", temp_ambiente_min="18.256"), "temp_ambiente_min"), ["demasiados_decimales"])

    def test_regla_6_el_minimo_no_puede_ser_mayor_que_el_maximo(self):
        """PROD-ALT-VAR regla 6: error en el campo del máximo, en cada rango."""
        for variable, (minimo, maximo) in {"temp_ambiente": ("30", "20"), "humedad": ("90", "80"), "intensidad_luz": ("500", "400"), "fotoperiodo": ("18", "16")}.items():
            with self.subTest(rango=variable):
                error = self.error(**{f"{variable}_min": minimo, f"{variable}_max": maximo})
                self.assertEqual(codigos_de(error, f"{variable}_max"), ["minimo_mayor_que_maximo"])

    def test_regla_6_minimo_igual_al_maximo_es_valido(self):
        """PROD-ALT-VAR regla 6: mínimo igual al máximo es válido."""
        self.assertIsNotNone(self.alta(temp_ambiente_min="20", temp_ambiente_max="20").pk)

    def test_d49_humedad_entre_0_y_100(self):
        """D-49 y variedades.md: «Ingresá un valor entre 0 y 100.» para 100,01 y −1; 0 y 100 son válidos."""
        self.assertEqual(codigos_de(self.error(humedad_max="100.01"), "humedad_max"), ["fuera_de_rango"])
        self.assertEqual(codigos_de(self.error(humedad_min="-1"), "humedad_min"), ["fuera_de_rango"])
        self.assertEqual(self.error(humedad_max="100.01").error_dict["humedad_max"][0].message, "Ingresá un valor entre 0 y 100.")
        self.assertIsNotNone(self.alta(humedad_min="0", humedad_max="100").pk)

    def test_d49_fotoperiodo_entre_0_y_24(self):
        """D-49 y variedades.md: «Ingresá un valor entre 0 y 24.» para 24,01 y −1; 0 y 24 son válidos."""
        self.assertEqual(codigos_de(self.error(fotoperiodo_max="24.01"), "fotoperiodo_max"), ["fuera_de_rango"])
        self.assertEqual(codigos_de(self.error(fotoperiodo_min="-1"), "fotoperiodo_min"), ["fuera_de_rango"])
        self.assertEqual(self.error(fotoperiodo_max="24.01").error_dict["fotoperiodo_max"][0].message, "Ingresá un valor entre 0 y 24.")
        self.assertIsNotNone(self.alta(fotoperiodo_min="0", fotoperiodo_max="24").pk)

    def test_d49_temperatura_e_intensidad_no_tienen_tope(self):
        """D-49: temperatura e intensidad lumínica sin tope (admiten negativos y valores grandes)."""
        self.assertIsNotNone(self.alta(temp_ambiente_min="-10", temp_ambiente_max="900", intensidad_luz_min="0", intensidad_luz_max="9000").pk)

    def test_regla_7_la_postcosecha_es_un_entero_de_1_a_60(self):
        """PROD-ALT-VAR regla 7: 0 y 61 se rechazan; 1 y 60 valen; también un decimal o un texto."""
        for malo in ("0", "61", "2.5", "abc"):
            with self.subTest(dias=malo):
                self.assertEqual(codigos_de(self.error(duracion_post_cosecha=malo), "duracion_post_cosecha"), ["entero_entre_1_y_60"])
        self.assertEqual(codigos_de(self.error(duracion_post_cosecha=""), "duracion_post_cosecha"), ["obligatorio"])
        self.assertEqual(self.alta(nombre="Uno", duracion_post_cosecha="1").duracion_post_cosecha, 1)
        self.assertEqual(self.alta(nombre="Sesenta", duracion_post_cosecha="60").duracion_post_cosecha, 60)

    def test_regla_7_el_peso_es_un_entero_de_gramos_mayor_que_cero(self):
        """PROD-ALT-VAR regla 7: 0 y con decimales se rechazan; 1 vale."""
        for malo in ("0", "1.5", "abc"):
            with self.subTest(peso=malo):
                self.assertEqual(codigos_de(self.error(peso_promedio_planta=malo), "peso_promedio_planta"), ["entero_mayor_que_cero"])
        self.assertEqual(codigos_de(self.error(peso_promedio_planta=""), "peso_promedio_planta"), ["obligatorio"])
        self.assertEqual(self.alta(peso_promedio_planta="1").peso_promedio_planta, 1)

    def test_regla_8_todos_los_errores_salen_juntos_y_no_se_crea_nada(self):
        """Patrón ABM, sección 2: un solo ``ValidationError`` con un error por campo, para que la pantalla los marque a la vez."""
        vacios = variedades.DatosDeVariedad()
        error = error_de(lambda: variedades.alta_variedad(self.agronomo, self.cultivo.pk, vacios))
        self.assertTrue(
            {"nombre", "perfil_familia", "etapas", "temp_ambiente_min", "temp_ambiente_max", "humedad_min", "humedad_max",
             "intensidad_luz_min", "intensidad_luz_max", "fotoperiodo_min", "fotoperiodo_max", "duracion_post_cosecha",
             "peso_promedio_planta"} <= set(error.error_dict)
        )
        self.assertTrue(self.nada_creado())


class ResumenDeAltaTests(AltaVariedadBase):
    """Regla 8: el resumen se calcula sin escribir y con las mismas validaciones."""

    def test_regla_8_el_resumen_trae_los_datos_el_ciclo_y_el_nombre_de_la_semilla_sin_escribir(self):
        """PROD-ALT-VAR regla 8: todos los datos, la duración del ciclo (suma), la cosecha estimada y el nombre de la semilla."""
        resumen = variedades.resumen_de_alta(self.agronomo, self.cultivo.pk, datos(nombre="  Butterhead "))
        self.assertEqual((resumen.cultivo, resumen.nombre, resumen.nombre_semilla), ("Lechuga", "Butterhead", "Semilla Lechuga Butterhead"))
        self.assertEqual((resumen.duracion_del_ciclo, resumen.dias_hasta_maduracion), (35, 15))
        self.assertEqual(resumen.etapas, [("germinacion", "Germinación", 5), ("crecimiento", "Crecimiento", 10), ("maduracion", "Maduración", 20)])
        self.assertTrue(self.nada_creado())
        self.assertFalse(Insumo.objects.filter(nombre_insumo__startswith="Semilla").exists())

    def test_regla_8_el_resumen_valida_lo_mismo_que_el_alta(self):
        """PROD-ALT-VAR regla 8: el resumen rechaza lo que rechaza el alta (por ejemplo, un nombre repetido o el choque de la semilla)."""
        self.alta()
        error = error_de(lambda: variedades.resumen_de_alta(self.agronomo, self.cultivo.pk, datos()))
        self.assertEqual(codigos_de(error, "nombre"), ["nombre_repetido"])
        error = error_de(lambda: variedades.resumen_de_alta(self.agronomo, self.cultivo.pk, datos(etapas=())))
        self.assertEqual(codigos_de(error, "etapas"), ["etapa_obligatoria"])

    def test_regla_8_el_resumen_exige_un_agronomo_activo_y_un_cultivo_activo(self):
        """PROD-ALT-VAR precondiciones a y b también en el resumen."""
        with self.assertRaises(PermissionDenied):
            variedades.resumen_de_alta(crear_gerente(), self.cultivo.pk, datos())
        self.cultivo.estado_cultivo = "inactivo"
        self.cultivo.save()
        error = error_de(lambda: variedades.resumen_de_alta(self.agronomo, self.cultivo.pk, datos()))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["cultivo_inactivo"])


class CrearSemillaTests(ConDatosDeInventario, TestCase):
    """``semillas.crear_semilla(variedad)``: la categoría se busca por ``codigo``, no toca existencias ni audita (lo hace el caso de uso)."""

    def setUp(self):
        self.cultivo = crear_cultivo("Lechuga")

    def variedad_sin_semilla(self, activa=True, nombre="Crespa"):
        from maestros.tests.fabricas import crear_variedad

        return crear_variedad(self.cultivo, nombre, activa=activa)

    def test_post_c_crea_la_semilla_con_su_nombre_categoria_unidad_y_vencimiento(self):
        """PROD-ALT-VAR postcondición c: «Semilla {cultivo} {variedad}», categoría Semillas, unidad, con vencimiento."""
        variedad = self.variedad_sin_semilla()
        semilla = semillas.crear_semilla(variedad)
        self.assertEqual(semilla.nombre_insumo, "Semilla Lechuga Crespa")
        self.assertEqual((semilla.tipo_insumo.codigo, semilla.unidad_medida_insumo, semilla.controla_vencimiento), ("semillas", "unidad", True))
        self.assertEqual(semilla.variedad, variedad)

    def test_post_c_el_estado_de_la_semilla_es_el_de_su_variedad(self):
        """docs/modelo/inventario.md, «Semilla»: estado igual al de su variedad."""
        self.assertEqual(semillas.crear_semilla(self.variedad_sin_semilla(activa=False)).estado_insumo, "inactivo")

    def test_post_c_no_habilita_la_semilla_en_ningun_invernadero(self):
        """PROD-ALT-VAR postcondición c: sin habilitar; ninguna función de semillas toca existencias."""
        semillas.crear_semilla(self.variedad_sin_semilla())
        self.assertEqual(InsumoInvernadero.objects.count(), 0)

    def test_decision_un_nombre_ya_usado_por_otro_insumo_da_error_de_campo(self):
        """Decisión del 22/11/2026: choque con ``insumo_nombre_unico`` → ``ValidationError`` en ``nombre`` (``semilla_repetida``)."""
        insumo("semilla lechuga crespa", tipo=tipo_de_insumo("Varios"))
        error = error_de(lambda: semillas.crear_semilla(self.variedad_sin_semilla()))
        self.assertEqual(codigos_de(error, "nombre"), ["semilla_repetida"])

    def test_decision_un_nombre_de_mas_de_100_caracteres_se_rechaza_sin_truncar(self):
        """variedades.md, «Largos de los nombres»: si un nombre ya guardado pasara, error por campo en vez de truncar."""
        variedad = self.variedad_sin_semilla()
        variedad.cultivo.nombre_cultivo = "C" * 95  # solo en memoria: datos viejos que ya no entran
        error = error_de(lambda: semillas.crear_semilla(variedad))
        self.assertEqual(codigos_de(error, "nombre"), ["semilla_demasiado_larga"])
        self.assertFalse(Semilla.objects.exists())
