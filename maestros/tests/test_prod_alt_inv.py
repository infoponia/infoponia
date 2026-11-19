# Pruebas de PROD-ALT-INV · Alta Invernadero (docs/casos_de_uso/maestros/invernaderos.md) y de lo que cita: D-22 (la
# auditoría en la misma transacción), D-36 (formato del detalle), D-37 (el servicio vive en maestros), D-38 (sin
# alertas ni notificaciones) y D-39 (decisiones de MAE-01).
#
# Servicio que se prueba (maestros/servicios/invernaderos.py), tomado del módulo dentro de cada prueba para que,
# mientras no exista, falle cada prueba por separado:
#   alta_invernadero(actor, nombre, *, tipo_direccion, localidad_id, calle="", numero_calle="", piso="",
#                    departamento_unidad="", barrio="", referencias="", ruta="", kilometro="", lote_rural="",
#                    agronomo_id=None, capataz_id=None, vendedor_id=None, tecnico_id=None) -> Invernadero
#   Todo lo que sigue a ``actor, nombre`` es solo por nombre (``*``): con tantos parámetros del mismo tipo, así no se
#   pueden pasar en el orden equivocado.
#   - Precondición a: ``actor`` no es un Gerente activo -> PermissionDenied.
#   - Falla con ValidationError por campo (claves: nombre, tipo_direccion, localidad, calle, numero_calle, ruta,
#     kilometro, agronomo, capataz, vendedor, tecnico) y no cambia nada.
#
# Fuera de alcance de esta tarea (D-38 y «Límites» de MAE-01): las postcondiciones d y e (alertas y notificaciones).

import importlib
import inspect
from unittest import mock

from django.apps import apps as django_apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.test import TestCase
from django.urls import reverse

from core.models import RegistroAuditoria, referencia
from core.tests.fabricas import afectado, crear_administrador, crear_capataz, crear_gerente
from maestros.models import (
    Departamento,
    DireccionRural,
    DireccionUrbana,
    Invernadero,
    Localidad,
    Provincia,
)
from maestros.servicios import invernaderos
from maestros.tests.fabricas import (
    ConGeoref,
    crear_agronomo,
    crear_capataz_activo,
    crear_invernadero,
    crear_tecnico,
    crear_vendedor,
    datos_alta,
    localidad,
)

ALTA = RegistroAuditoria.Accion.ALTA_INVERNADERO


def errores_de(llamada):
    """Ejecuta ``llamada`` y devuelve el diccionario de errores de la ``ValidationError`` que lanza; si no la
    lanza, la prueba falla."""
    try:
        llamada()
    except ValidationError as error:
        return error.message_dict
    raise AssertionError("Se esperaba una ValidationError y no se lanzó.")


class ProdAltInvServicioTests(ConGeoref, TestCase):
    """Servicio ``alta_invernadero`` (PROD-ALT-INV): precondiciones, reglas 1 a 8 y postcondiciones a, b, c y f."""

    def setUp(self):
        self.gerente = crear_gerente()

    def alta(self, tipo="urbana", **extra):
        """Da de alta un invernadero como el Gerente con datos válidos."""
        return invernaderos.alta_invernadero(self.gerente, **datos_alta(tipo, **extra))

    # ---- Firma ----

    def test_firma_todo_despues_de_actor_y_nombre_es_solo_por_nombre(self):
        """Firma de ``alta_invernadero``: solo ``actor`` y ``nombre`` son posicionales; el resto, solo por nombre."""
        parametros = inspect.signature(invernaderos.alta_invernadero).parameters.values()
        posicionales = [p.name for p in parametros if p.kind is not inspect.Parameter.KEYWORD_ONLY]
        self.assertEqual(posicionales, ["actor", "nombre"])

    def test_firma_un_tercer_argumento_posicional_se_rechaza(self):
        """Firma de ``alta_invernadero``: pasar la dirección por posición (``"urbana"``) es un ``TypeError``."""
        with self.assertRaises(TypeError):
            invernaderos.alta_invernadero(self.gerente, "Invernadero A", "urbana", localidad().pk)

    # ---- Precondiciones ----

    def test_pre_a_un_gerente_activo_da_de_alta(self):
        """PROD-ALT-INV, precondición a: el Gerente activo puede dar de alta."""
        self.assertEqual(self.alta().nombre_invernadero, "Invernadero A")

    def test_pre_a_otro_rol_no_da_de_alta(self):
        """PROD-ALT-INV, precondición a: un Agrónomo, un Capataz o un Administrador reciben PermissionDenied."""
        for actor in (crear_agronomo(), crear_capataz(), crear_administrador()):
            with self.subTest(actor=actor.email), self.assertRaises(PermissionDenied):
                invernaderos.alta_invernadero(actor, **datos_alta())
        self.assertFalse(Invernadero.objects.exists())

    def test_pre_a_un_gerente_inactivo_no_da_de_alta(self):
        """PROD-ALT-INV, precondición a: «con una cuenta activa de Gerente»."""
        self.gerente.is_active = False
        self.gerente.save()
        with self.assertRaises(PermissionDenied):
            invernaderos.alta_invernadero(self.gerente, **datos_alta())

    def test_pre_a_sin_actor_no_da_de_alta(self):
        """PROD-ALT-INV, precondición a: sin cuenta que actúe, PermissionDenied."""
        with self.assertRaises(PermissionDenied):
            invernaderos.alta_invernadero(None, **datos_alta())

    def test_pre_b_nombre_repetido_se_rechaza(self):
        """PROD-ALT-INV, precondición b: no existe otro invernadero con el mismo nombre."""
        self.alta(nombre="Invernadero Sur")
        errores = errores_de(lambda: self.alta(nombre="Invernadero Sur"))
        self.assertIn("nombre", errores)
        self.assertEqual(Invernadero.objects.count(), 1)

    # ---- Reglas ----

    def test_regla_1_nombre_obligatorio(self):
        """PROD-ALT-INV, regla 1: el nombre es obligatorio (vacío o solo espacios)."""
        for nombre in ("", "   "):
            with self.subTest(nombre=nombre):
                self.assertIn("nombre", errores_de(lambda: self.alta(nombre=nombre)))

    def test_regla_1_nombre_unico_sin_distinguir_mayusculas_ni_espacios(self):
        """PROD-ALT-INV, regla 1: único sin distinguir mayúsculas ni espacios al principio o al final."""
        self.alta(nombre="Invernadero Sur")
        for repetido in ("invernadero sur", "INVERNADERO SUR", "  Invernadero Sur  "):
            with self.subTest(nombre=repetido):
                self.assertIn("nombre", errores_de(lambda: self.alta(nombre=repetido)))

    def test_regla_1_nombre_unico_entre_activos_e_inactivos(self):
        """PROD-ALT-INV, regla 1: único entre todos los invernaderos, activos o inactivos."""
        crear_invernadero(nombre="Viejo", activo=False)
        self.assertIn("nombre", errores_de(lambda: self.alta(nombre="viejo")))

    def test_regla_1_nombre_se_guarda_sin_espacios_en_los_extremos(self):
        """PROD-ALT-INV, regla 1: el nombre se recorta antes de guardarse."""
        self.assertEqual(self.alta(nombre="  Invernadero Norte ").nombre_invernadero, "Invernadero Norte")

    def test_regla_2_urbana_exige_calle_y_numero(self):
        """PROD-ALT-INV, regla 2: en la urbana, la calle y el número son obligatorios."""
        errores = errores_de(lambda: self.alta(calle="", numero_calle=" "))
        self.assertIn("calle", errores)
        self.assertIn("numero_calle", errores)

    def test_regla_2_urbana_guarda_los_datos_opcionales(self):
        """PROD-ALT-INV, regla 2: piso, departamento (unidad), barrio y referencias son opcionales y se guardan."""
        direccion = self.alta(
            piso="2", departamento_unidad="B", barrio="Villa Sarita", referencias="Frente a la plaza"
        ).direccion.concreta()
        self.assertEqual(
            (direccion.piso, direccion.departamento, direccion.barrio, direccion.referencias),
            ("2", "B", "Villa Sarita", "Frente a la plaza"),
        )

    def test_regla_2_urbana_sin_opcionales_es_valida(self):
        """PROD-ALT-INV, regla 2: la urbana se crea con solo calle y número."""
        direccion = self.alta().direccion.concreta()
        self.assertEqual((direccion.piso, direccion.departamento, direccion.barrio, direccion.referencias), ("",) * 4)

    def test_regla_2_rural_exige_ruta_y_kilometro(self):
        """PROD-ALT-INV, regla 2: en la rural, la ruta o camino y el kilómetro son obligatorios."""
        errores = errores_de(lambda: self.alta("rural", ruta="", kilometro=""))
        self.assertIn("ruta", errores)
        self.assertIn("kilometro", errores)

    def test_regla_2_rural_el_lote_es_opcional(self):
        """PROD-ALT-INV, regla 2: el lote de la rural es opcional y se guarda si viene."""
        self.assertEqual(self.alta("rural", lote_rural="Lote 12").direccion.concreta().lote, "Lote 12")
        self.assertEqual(self.alta("rural", nombre="Otro").direccion.concreta().lote, "")

    def test_regla_2_el_tipo_es_urbana_o_rural(self):
        """PROD-ALT-INV, regla 2: «la dirección es urbana o rural»; cualquier otro valor se rechaza."""
        for tipo in ("", "suburbana"):
            with self.subTest(tipo=tipo):
                self.assertIn("tipo_direccion", errores_de(lambda: self.alta(tipo)))

    def test_regla_2_ignora_los_datos_del_otro_tipo(self):
        """PROD-ALT-INV, regla 2: una dirección urbana no guarda ruta ni kilómetro, y una rural no guarda calle."""
        self.alta("urbana", ruta="Ruta 14", kilometro="9")
        self.alta("rural", nombre="Rural", calle="Calle", numero_calle="1")
        self.assertEqual(DireccionUrbana.objects.count(), 1)
        self.assertEqual(DireccionRural.objects.count(), 1)

    # Formato de kilómetro y de número de calle: la regla 2 no lo define (hueco del caso de uso, para pendientes_CU);
    # se eligió en D-39, con el estilo del validador del teléfono (D-21).

    def test_regla_2_kilometro_acepta_entero_y_un_decimal_con_coma(self):
        """PROD-ALT-INV, regla 2 y D-39: el kilómetro es un entero de hasta 4 dígitos, con una coma y como máximo un
        decimal («4», «4,5», «875,5»): en el interior las rutas se referencian con medios kilómetros."""
        for orden, valor in enumerate(("4", "4,5", "875,5", "0", "1234", "1234,5", " 4,5 ")):
            with self.subTest(kilometro=valor):
                invernadero = self.alta("rural", nombre=f"Rural {orden}", kilometro=valor)
                self.assertEqual(invernadero.direccion.concreta().kilometro, valor.strip())

    def test_regla_2_kilometro_rechaza_otros_formatos(self):
        """PROD-ALT-INV, regla 2 y D-39: texto, punto decimal, más de un decimal, más de 4 dígitos, coma sin decimal o
        sin entero y negativos se rechazan en el campo ``kilometro``."""
        for valor in ("abc", "6,7777", "4.5", "4,55", "4,", ",5", "12345", "-4", "4 km", "4,5,5"):
            with self.subTest(kilometro=valor):
                self.assertIn("kilometro", errores_de(lambda: self.alta("rural", kilometro=valor)))
        self.assertFalse(Invernadero.objects.exists())

    def test_regla_2_numero_calle_acepta_sn_o_un_numero_al_comienzo(self):
        """PROD-ALT-INV, regla 2 y D-39: el número es «S/N» (sin distinguir mayúsculas) o empieza con un número
        («1234», «1234 bis»)."""
        for orden, valor in enumerate(("1234", "1234 bis", "S/N", "s/n", "S/n", "12a", " 7 ")):
            with self.subTest(numero_calle=valor):
                invernadero = self.alta(nombre=f"Urbana {orden}", numero_calle=valor)
                self.assertEqual(invernadero.direccion.concreta().numero_calle, valor.strip())

    def test_regla_2_numero_calle_rechaza_otros_formatos(self):
        """PROD-ALT-INV, regla 2 y D-39: un texto que no empieza con un número y no es «S/N» («casa», «bis») se
        rechaza en el campo ``numero_calle``."""
        for valor in ("casa", "bis", "SN", "S/N 5", "-3", "S/"):
            with self.subTest(numero_calle=valor):
                self.assertIn("numero_calle", errores_de(lambda: self.alta(numero_calle=valor)))
        self.assertFalse(Invernadero.objects.exists())

    def test_regla_2_el_formato_no_pisa_el_error_de_obligatorio(self):
        """PROD-ALT-INV, regla 2: vacío sigue siendo «obligatorio», no un error de formato."""
        self.assertEqual(errores_de(lambda: self.alta(numero_calle=""))["numero_calle"], ["Ingresá el número."])
        self.assertEqual(
            errores_de(lambda: self.alta("rural", kilometro=""))["kilometro"], ["Ingresá el kilómetro."]
        )

    def test_regla_2_el_formato_tambien_vale_en_el_modelo(self):
        """PROD-ALT-INV, regla 2 y D-39: los campos del modelo llevan los mismos validadores, así que cualquier otra
        puerta de entrada (admin, formularios) aplica el mismo formato."""
        kilometro = DireccionRural._meta.get_field("kilometro")
        numero = DireccionUrbana._meta.get_field("numero_calle")
        kilometro.run_validators("4,5")
        numero.run_validators("S/N")
        with self.assertRaises(ValidationError):
            kilometro.run_validators("abc")
        with self.assertRaises(ValidationError):
            numero.run_validators("casa")

    # Texto libre con contenido real: la regla 2 dice qué campos son obligatorios, pero no que tengan contenido (hueco del
    # caso de uso, para pendientes_CU; D-39). El texto sigue siendo libre: «12», «RN 12» y «Ruta Nacional 12» valen.

    def test_regla_1_nombre_exige_una_letra_o_un_numero(self):
        """PROD-ALT-INV, regla 1 y D-39: un nombre sin ninguna letra ni número («---», «...») se rechaza."""
        for valor in ("---", "...", "  - _ ", "¿?"):
            with self.subTest(nombre=valor):
                self.assertIn("nombre", errores_de(lambda: self.alta(nombre=valor)))
        self.assertFalse(Invernadero.objects.exists())

    def test_regla_1_nombre_acepta_cualquier_texto_con_una_letra_o_un_numero(self):
        """PROD-ALT-INV, regla 1 y D-39: el nombre sigue siendo texto libre; basta una letra (también con tilde o ñ)
        o un número."""
        for valor in ("A", "12", "Ñandú-1", "Invernadero - Sur", "--a--"):
            with self.subTest(nombre=valor):
                self.assertEqual(self.alta(nombre=valor).nombre_invernadero, valor)

    def test_regla_2_calle_y_ruta_exigen_una_letra_o_un_numero(self):
        """PROD-ALT-INV, regla 2 y D-39: una calle o una ruta de puros símbolos («-----------------») se rechaza."""
        self.assertIn("calle", errores_de(lambda: self.alta(calle="-----------------")))
        self.assertIn("ruta", errores_de(lambda: self.alta("rural", ruta="-----------------")))
        self.assertFalse(Invernadero.objects.exists())

    def test_regla_2_calle_y_ruta_siguen_siendo_texto_libre(self):
        """PROD-ALT-INV, regla 2 y D-39: «12», «RN 12», «Ruta Nacional 12» y el nombre de un camino son válidos."""
        for orden, valor in enumerate(("12", "RN 12", "Ruta Nacional 12", "Camino del Ñandú", "Av. 9 de Julio")):
            with self.subTest(valor=valor):
                self.assertEqual(self.alta("rural", nombre=f"R{orden}", ruta=valor).direccion.concreta().ruta, valor)
                self.assertEqual(self.alta(nombre=f"U{orden}", calle=valor).direccion.concreta().calle, valor)

    def test_regla_2_los_opcionales_cargados_exigen_una_letra_o_un_numero(self):
        """PROD-ALT-INV, regla 2 y D-39: si piso, departamento (unidad), barrio, referencias o lote están cargados,
        tienen que tener al menos una letra o un número."""
        for campo in ("piso", "departamento_unidad", "barrio", "referencias"):
            with self.subTest(campo=campo):
                self.assertIn(campo, errores_de(lambda: self.alta(**{campo: "---"})))
        with self.subTest(campo="lote_rural"):
            self.assertIn("lote_rural", errores_de(lambda: self.alta("rural", lote_rural="---")))
        self.assertFalse(Invernadero.objects.exists())

    def test_regla_2_los_opcionales_vacios_no_se_validan(self):
        """PROD-ALT-INV, regla 2 y D-39: un opcional vacío (o de solo espacios) no es un error y se guarda vacío."""
        direccion = self.alta(
            piso="  ", departamento_unidad="", barrio=" ", referencias=""
        ).direccion.concreta()
        self.assertEqual((direccion.piso, direccion.departamento, direccion.barrio, direccion.referencias), ("",) * 4)
        self.assertEqual(self.alta("rural", nombre="Rural", lote_rural="  ").direccion.concreta().lote, "")

    def test_regla_2_los_opcionales_con_contenido_se_aceptan(self):
        """PROD-ALT-INV, regla 2 y D-39: un opcional con una letra o un número se acepta («2», «B», «Villa Sarita»)."""
        direccion = self.alta(
            piso="2", departamento_unidad="B", barrio="Villa Sarita", referencias="Frente a la plaza 9"
        ).direccion.concreta()
        self.assertEqual((direccion.piso, direccion.departamento), ("2", "B"))

    def test_regla_2_el_contenido_no_pisa_el_error_de_obligatorio(self):
        """PROD-ALT-INV, regla 2: vacío sigue siendo «obligatorio», no un error de contenido."""
        self.assertEqual(errores_de(lambda: self.alta(calle=""))["calle"], ["Ingresá la calle."])
        self.assertEqual(errores_de(lambda: self.alta("rural", ruta=" "))["ruta"], ["Ingresá la ruta o el camino."])
        self.assertEqual(errores_de(lambda: self.alta(nombre=" "))["nombre"], ["Ingresá el nombre del invernadero."])

    def test_regla_2_el_contenido_tambien_vale_en_el_modelo(self):
        """PROD-ALT-INV, reglas 1 y 2 y D-39: los campos de texto libre del modelo llevan el mismo validador; un
        opcional vacío no se valida."""
        campos = (
            (Invernadero, "nombre_invernadero"),
            (DireccionUrbana, "calle"),
            (DireccionUrbana, "piso"),
            (DireccionUrbana, "departamento"),
            (DireccionUrbana, "barrio"),
            (DireccionUrbana, "referencias"),
            (DireccionRural, "ruta"),
            (DireccionRural, "lote"),
        )
        for modelo, nombre in campos:
            campo = modelo._meta.get_field(nombre)
            with self.subTest(campo=f"{modelo.__name__}.{nombre}"):
                campo.run_validators("RN 12")
                campo.run_validators("")  # un opcional vacío no se valida
                with self.assertRaises(ValidationError):
                    campo.run_validators("-----")

    def test_regla_2_los_textos_largos_se_rechazan_con_error_de_campo(self):
        """PROD-ALT-INV, reglas 1 y 2 y D-39 (decisión 6): un texto más largo que su columna es un error de campo, no
        un error de la base."""
        self.assertIn("nombre", errores_de(lambda: self.alta(nombre="N" * 81)))
        self.assertIn("calle", errores_de(lambda: self.alta(calle="C" * 101)))
        self.assertIn("numero_calle", errores_de(lambda: self.alta(numero_calle="1" * 11)))
        self.assertIn("kilometro", errores_de(lambda: self.alta("rural", kilometro="9" * 11)))
        self.assertFalse(Invernadero.objects.exists())

    def test_regla_3_la_migracion_carga_georef(self):
        """PROD-ALT-INV, regla 3 y MD-88: la migración 0002 carga provincias, departamentos y localidades de Georef
        (24, 527 y 3923: D-39, decisión 2) y su vuelta las borra. Se prueba la función de la migración sobre tablas
        vacías, así que no depende del estado de la base de pruebas."""
        migracion = importlib.import_module("maestros.migrations.0002_cargar_georef")
        Localidad.objects.all().delete()
        Departamento.objects.all().delete()
        Provincia.objects.all().delete()
        migracion.cargar(django_apps, None)
        self.assertEqual(
            (Provincia.objects.count(), Departamento.objects.count(), Localidad.objects.count()), (24, 527, 3923)
        )
        self.assertEqual(localidad("Campo Viera", "Oberá").id_georef, "54091030")
        migracion.descargar(django_apps, None)
        self.assertFalse(Provincia.objects.exists())

    def test_regla_3_la_localidad_es_obligatoria(self):
        """PROD-ALT-INV, regla 3: la localidad se elige de la lista; sin ella se rechaza."""
        self.assertIn("localidad", errores_de(lambda: self.alta(localidad_id=None)))

    def test_regla_3_la_localidad_tiene_que_existir(self):
        """PROD-ALT-INV, regla 3: no se crean localidades desde este caso de uso; un id inexistente se rechaza."""
        cantidad = Localidad.objects.count()
        self.assertIn("localidad", errores_de(lambda: self.alta(localidad_id=0)))
        self.assertEqual(Localidad.objects.count(), cantidad)

    def test_regla_4_el_personal_es_opcional(self):
        """PROD-ALT-INV, regla 4: el invernadero puede existir sin personal."""
        invernadero = self.alta()
        self.assertEqual(
            (invernadero.agronomo, invernadero.capataz, invernadero.vendedor, invernadero.tecnico), (None,) * 4
        )

    def test_regla_4_solo_cuentas_activas_del_rol(self):
        """PROD-ALT-INV, regla 4: se ofrecen solo las cuentas activas de cada rol; una inactiva o de otro rol se
        rechaza en el campo de ese rol."""
        inactivo = crear_agronomo("inactivo@infoponia.com", activo=False)
        errores = errores_de(lambda: self.alta(agronomo_id=inactivo.pk))
        self.assertIn("agronomo", errores)
        capataz = crear_capataz_activo()
        errores = errores_de(lambda: self.alta(agronomo_id=capataz.pk))
        self.assertIn("agronomo", errores)
        self.assertFalse(Invernadero.objects.exists())

    def test_regla_4_una_cuenta_puede_estar_a_cargo_de_varios_invernaderos(self):
        """PROD-ALT-INV, regla 4: una misma cuenta puede estar a cargo de varios invernaderos."""
        agronomo = crear_agronomo()
        primero = self.alta(agronomo_id=agronomo.pk)
        segundo = self.alta(nombre="Invernadero C", agronomo_id=agronomo.pk)
        self.assertEqual(primero.agronomo, segundo.agronomo)

    def test_regla_5_el_tecnico_no_es_obligatorio(self):
        """PROD-ALT-INV, regla 5: un invernadero nuevo no tiene IoT, así que no hace falta Técnico."""
        invernadero = self.alta(agronomo_id=crear_agronomo().pk)
        self.assertNotIn("tecnico", [atributo for atributo, _, _ in invernadero.roles_faltantes()])

    def test_regla_7_el_alta_no_crea_sectores(self):
        """PROD-ALT-INV, regla 7: no crea sectores; el invernadero queda marcado como «sin sectores»."""
        self.assertFalse(self.alta().tiene_sectores())

    # ---- Postcondiciones ----

    def test_post_a_crea_el_invernadero_activo_y_sin_iot(self):
        """PROD-ALT-INV, postcondición a: invernadero activo, con su nombre, sin sectores y sin sistema IoT."""
        invernadero = self.alta()
        self.assertEqual(invernadero.estado_invernadero, "activo")
        self.assertEqual(invernadero.nombre_invernadero, "Invernadero A")
        self.assertFalse(invernadero.tiene_sectores())
        self.assertFalse(invernadero.tiene_sistema_iot())

    def test_post_b_crea_la_direccion_en_la_localidad_elegida(self):
        """PROD-ALT-INV, postcondición b: se creó su dirección, urbana o rural, ubicada en la localidad elegida."""
        urbano = self.alta().direccion.concreta()
        rural = self.alta("rural", nombre="Rural", localidad_id=localidad("Campo Viera", "Oberá").pk).direccion.concreta()
        self.assertIsInstance(urbano, DireccionUrbana)
        self.assertEqual((urbano.calle, urbano.numero_calle, urbano.localidad), ("Av. Uruguay", "2450", localidad()))
        self.assertIsInstance(rural, DireccionRural)
        self.assertEqual((rural.ruta, rural.kilometro, rural.localidad.nombre_localidad), ("Ruta Provincial 105", "4", "Campo Viera"))

    def test_post_c_asocia_al_personal_asignado(self):
        """PROD-ALT-INV, postcondición c: el invernadero queda asociado a su Agrónomo, Capataz y Vendedor (y Técnico)."""
        agronomo, capataz, vendedor, tecnico = crear_agronomo(), crear_capataz_activo(), crear_vendedor(), crear_tecnico()
        invernadero = self.alta(
            agronomo_id=agronomo.pk, capataz_id=capataz.pk, vendedor_id=vendedor.pk, tecnico_id=tecnico.pk
        )
        invernadero.refresh_from_db()
        self.assertEqual(
            (invernadero.agronomo, invernadero.capataz, invernadero.vendedor, invernadero.tecnico),
            (agronomo, capataz, vendedor, tecnico),
        )

    def test_post_c_asigna_solo_los_roles_indicados(self):
        """PROD-ALT-INV, postcondición c: «si se asignaron»: los demás roles quedan sin asignar."""
        agronomo = crear_agronomo()
        invernadero = self.alta(agronomo_id=agronomo.pk)
        self.assertEqual((invernadero.agronomo, invernadero.capataz, invernadero.vendedor), (agronomo, None, None))

    def test_post_f_audita_el_alta(self):
        """PROD-ALT-INV, postcondición f y D-36: un registro con quien actuó, la acción y el invernadero afectado."""
        invernadero = self.alta()
        registro = RegistroAuditoria.objects.get(accion=ALTA)
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual(registro.rol, "gerente")
        self.assertEqual(
            registro.afectados,
            [{"modelo": "maestros.invernadero", "id": invernadero.pk, "texto": "Invernadero A"}],
        )

    def test_post_f_el_detalle_tiene_los_datos_cargados_con_antes_nulo(self):
        """PROD-ALT-INV, postcondición f y D-36: ``cambios`` con cada dato cargado (antes nulo) y las referencias
        con ``referencia()``; los datos opcionales vacíos no figuran."""
        invernadero = self.alta(barrio="Villa Sarita")
        registro = RegistroAuditoria.objects.get(accion=ALTA)
        esperado = {
            "nombre": "Invernadero A",
            "estado": "activo",
            "tipo_direccion": "urbana",
            "localidad": referencia(localidad()),
            "calle": "Av. Uruguay",
            "numero_calle": "2450",
            "barrio": "Villa Sarita",
        }
        self.assertEqual(registro.detalle, {"cambios": {k: {"antes": None, "despues": v} for k, v in esperado.items()}})
        self.assertEqual(registro.afectados[0]["id"], invernadero.pk)

    def test_post_f_el_detalle_de_una_rural(self):
        """PROD-ALT-INV, postcondición f: la rural audita ruta, kilómetro y, si se cargó, el lote (``lote_rural``)."""
        self.alta("rural", lote_rural="Lote 12")
        cambios = RegistroAuditoria.objects.get(accion=ALTA).detalle["cambios"]
        self.assertEqual(cambios["tipo_direccion"]["despues"], "rural")
        self.assertEqual(
            (cambios["ruta"]["despues"], cambios["kilometro"]["despues"], cambios["lote_rural"]["despues"]),
            ("Ruta Provincial 105", "4", "Lote 12"),
        )
        self.assertNotIn("calle", cambios)

    def test_post_f_registra_al_personal_asignado_como_referencia_y_afectado(self):
        """PROD-ALT-INV, postcondición f y D-36: cada persona asignada va como referencia y como afectada, para
        que el alta aparezca en la auditoría de su cuenta."""
        agronomo, capataz = crear_agronomo(), crear_capataz_activo()
        self.alta(agronomo_id=agronomo.pk, capataz_id=capataz.pk)
        registro = RegistroAuditoria.objects.get(accion=ALTA)
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["agronomo"], {"antes": None, "despues": referencia(agronomo)})
        self.assertEqual(cambios["capataz"], {"antes": None, "despues": referencia(capataz)})
        self.assertNotIn("vendedor", cambios)
        self.assertIn(afectado(agronomo), registro.afectados)
        self.assertIn(afectado(capataz), registro.afectados)

    def test_post_f_un_solo_registro_por_alta(self):
        """PROD-ALT-INV, postcondición f: «una acción = un registro» (D-36)."""
        self.alta(agronomo_id=crear_agronomo().pk)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=ALTA).count(), 1)

    def test_post_f_un_alta_rechazada_no_audita(self):
        """PROD-ALT-INV, postcondición f: si el alta falla, no queda ningún registro ni invernadero."""
        errores_de(lambda: self.alta(nombre=""))
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())

    # ---- D-22: misma transacción ----

    def test_d22_si_falla_la_auditoria_no_queda_el_invernadero(self):
        """D-22: la auditoría se escribe en la misma transacción; si falla, se deshace todo (invernadero y dirección)."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError), transaction.atomic():
                self.alta()
        self.assertFalse(Invernadero.objects.exists())
        self.assertFalse(DireccionUrbana.objects.exists())

    # ---- D-38: fuera de alcance ----

    def test_d38_el_alta_no_genera_alertas_ni_notificaciones(self):
        """D-38: las alertas son de MAE-02 y las notificaciones no se modelan; el alta solo audita."""
        self.alta()
        self.assertEqual(RegistroAuditoria.objects.count(), 1)


class ProdAltInvVistaTests(ConGeoref, TestCase):
    """Pantalla «Nuevo invernadero» (integración, PROD-ALT-INV): flujo principal, errores del servicio, listas
    encadenadas de Georef (regla 3) y acceso por rol (SEG-13, D-30)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.client.force_login(self.gerente)
        self.url = reverse("maestros:invernadero_nuevo")
        self.misiones = Provincia.objects.get(nombre_provincia="Misiones")
        self.capital = Departamento.objects.get(nombre_departamento="Capital", provincia=self.misiones)

    def datos(self, **extra):
        """Un POST válido de una dirección urbana, como lo manda el navegador (ids como texto)."""
        return {
            "nombre": "Invernadero A",
            "tipo_direccion": "urbana",
            "provincia": self.misiones.pk,
            "departamento": self.capital.pk,
            "localidad": localidad().pk,
            "calle": "Av. Uruguay",
            "numero_calle": "2450",
        } | extra

    def test_flujo_principal_crea_el_invernadero_y_va_a_la_ficha(self):
        """PROD-ALT-INV, flujo principal: el Gerente completa el formulario, se crea y vuelve a la ficha con el aviso."""
        respuesta = self.client.post(self.url, self.datos(agronomo=crear_agronomo().pk), follow=True)
        invernadero = Invernadero.objects.get()
        self.assertRedirects(respuesta, reverse("maestros:invernadero", args=[invernadero.pk]))
        self.assertContains(respuesta, "Invernadero creado: Invernadero A.")
        self.assertEqual(invernadero.agronomo.email, "agronomo@infoponia.com")
        self.assertEqual(RegistroAuditoria.objects.filter(accion=ALTA).count(), 1)

    def test_flujo_principal_el_formulario_se_ve_con_sus_secciones(self):
        """PROD-ALT-INV: el formulario ofrece nombre, tipo de dirección, listas de Georef y personal opcional."""
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Nuevo invernadero")
        self.assertContains(respuesta, "Urbana")
        self.assertContains(respuesta, "Rural")
        self.assertContains(respuesta, "Misiones")
        self.assertContains(respuesta, "Sin asignar")
        self.assertContains(respuesta, "Es opcional")

    def test_regla_1_nombre_repetido_vuelve_al_formulario_con_el_error(self):
        """PROD-ALT-INV, regla 1: el error del servicio se ve junto al campo y no se crea nada."""
        crear_invernadero("Invernadero A")
        respuesta = self.client.post(self.url, self.datos())
        self.assertContains(respuesta, "Ya existe un invernadero con ese nombre.")
        self.assertEqual(Invernadero.objects.count(), 1)

    def test_regla_2_los_errores_de_la_direccion_vuelven_al_formulario(self):
        """PROD-ALT-INV, regla 2: una rural sin ruta ni kilómetro vuelve con los dos errores y con lo ya escrito."""
        respuesta = self.client.post(self.url, self.datos(tipo_direccion="rural", nombre="Rural"))
        self.assertContains(respuesta, "Ingresá la ruta o el camino.")
        self.assertContains(respuesta, "Ingresá el kilómetro.")
        self.assertContains(respuesta, 'value="Rural"')
        self.assertFalse(Invernadero.objects.exists())

    def test_regla_2_el_formato_del_kilometro_vuelve_al_formulario_con_el_error(self):
        """PROD-ALT-INV, regla 2 y D-39: un kilómetro con formato inválido vuelve al formulario con el mensaje, junto al
        campo y con lo escrito."""
        respuesta = self.client.post(
            self.url, self.datos(tipo_direccion="rural", nombre="Rural", ruta="Ruta 14", kilometro="abc")
        )
        self.assertContains(respuesta, "Ingresá el kilómetro como un número")
        self.assertContains(respuesta, 'value="abc"')
        self.assertFalse(Invernadero.objects.exists())

    def test_regla_2_el_contenido_de_la_calle_vuelve_al_formulario_con_el_error(self):
        """PROD-ALT-INV, regla 2 y D-39: una calle de puros símbolos vuelve al formulario con el mensaje y con lo escrito."""
        respuesta = self.client.post(self.url, self.datos(calle="-----------------"))
        self.assertContains(respuesta, "Ingresá un texto con al menos una letra o un número.")
        self.assertContains(respuesta, 'value="-----------------"')
        self.assertFalse(Invernadero.objects.exists())

    def test_regla_3_la_localidad_vuelve_elegida_tras_un_error(self):
        """PROD-ALT-INV, regla 3: tras un error, la provincia, el departamento y la localidad siguen elegidos."""
        respuesta = self.client.post(self.url, self.datos(nombre=""))
        self.assertContains(respuesta, "Ingresá el nombre del invernadero.")
        self.assertContains(respuesta, f'<option value="{localidad().pk}" selected>Garupá</option>', html=True)

    def test_regla_3_actualizar_arma_las_listas_sin_guardar(self):
        """PROD-ALT-INV, regla 3: sin JavaScript, «Actualizar» reenvía el formulario y no guarda nada."""
        respuesta = self.client.post(self.url, self.datos(actualizar="1"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Invernadero.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_3_el_fragmento_de_departamentos_ofrece_solo_los_de_la_provincia(self):
        """PROD-ALT-INV, regla 3: al elegir Misiones, los departamentos son los de Misiones y la localidad queda vacía."""
        respuesta = self.client.get(reverse("maestros:departamentos"), {"provincia": self.misiones.pk})
        self.assertContains(respuesta, "Oberá")
        self.assertContains(respuesta, "Capital")
        self.assertNotContains(respuesta, "Ituzaingó")
        self.assertNotContains(respuesta, "Posadas")

    def test_regla_3_el_fragmento_de_localidades_ofrece_solo_las_del_departamento(self):
        """PROD-ALT-INV, regla 3: al elegir el departamento Capital de Misiones, se ofrecen sus localidades."""
        respuesta = self.client.get(reverse("maestros:localidades"), {"departamento": self.capital.pk})
        self.assertContains(respuesta, "Posadas")
        self.assertContains(respuesta, "Garupá")
        self.assertNotContains(respuesta, "Campo Viera")

    def test_regla_3_un_id_mal_formado_da_listas_vacias(self):
        """PROD-ALT-INV, regla 3: un id que no es un número no rompe el fragmento: la lista queda vacía."""
        for nombre, parametro in (("maestros:departamentos", "provincia"), ("maestros:localidades", "departamento")):
            with self.subTest(fragmento=nombre):
                respuesta = self.client.get(reverse(nombre), {parametro: "abc"})
                self.assertEqual(respuesta.status_code, 200)
                self.assertNotContains(respuesta, "Posadas")

    def test_regla_2_el_fragmento_de_direccion_cambia_con_el_tipo(self):
        """PROD-ALT-INV, regla 2: la urbana pide calle y número; la rural, ruta y kilómetro."""
        urbana = self.client.get(reverse("maestros:campos_direccion"), {"tipo_direccion": "urbana"})
        rural = self.client.get(reverse("maestros:campos_direccion"), {"tipo_direccion": "rural"})
        self.assertContains(urbana, 'name="calle"')
        self.assertNotContains(urbana, 'name="ruta"')
        self.assertContains(rural, 'name="ruta"')
        self.assertNotContains(rural, 'name="calle"')

    def test_regla_4_el_formulario_ofrece_solo_cuentas_activas(self):
        """PROD-ALT-INV, regla 4: se ofrecen solo las cuentas activas de cada rol."""
        crear_agronomo("activo@infoponia.com", nombre="Activa", apellido="Perez")
        crear_agronomo("baja@infoponia.com", nombre="Inactiva", apellido="Gomez", activo=False)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Activa Perez")
        self.assertNotContains(respuesta, "Inactiva Gomez")

    def test_pre_a_otros_roles_reciben_403(self):
        """PROD-ALT-INV, precondición a y SEG-13: el Agrónomo y el Capataz no abren el alta ni sus fragmentos."""
        for cuenta in (crear_agronomo(), crear_capataz()):
            self.client.force_login(cuenta)
            for nombre in ("maestros:invernadero_nuevo", "maestros:departamentos", "maestros:localidades"):
                with self.subTest(cuenta=cuenta.email, pantalla=nombre):
                    self.assertEqual(self.client.get(reverse(nombre)).status_code, 403)
            self.assertEqual(self.client.post(self.url, self.datos()).status_code, 403)
        self.assertFalse(Invernadero.objects.exists())

    def test_pre_a_sin_sesion_pide_iniciar_sesion(self):
        """SEG-13: sin sesión se redirige al inicio de sesión."""
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_fragmentos_no_aceptan_post(self):
        """Los fragmentos de HTMX son de solo lectura: un POST da 405."""
        for nombre in ("maestros:departamentos", "maestros:localidades", "maestros:campos_direccion"):
            with self.subTest(fragmento=nombre):
                self.assertEqual(self.client.post(reverse(nombre)).status_code, 405)
