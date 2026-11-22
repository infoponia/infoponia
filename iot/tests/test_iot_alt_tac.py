# Pruebas de IOT-ALT-TAC · Alta Tipo de Actuador (docs/casos_de_uso/iot/tipos_de_actuador.md, v0.4) y de lo que cita: D-36
# (auditoría), D-72 y docs/modelo/iot.md («TipoActuador» y «Accion»). Se escribieron ANTES que el servicio (orden de
# .claude/rules/pruebas.md).
#
# Servicio que se prueba (iot/servicios/tipos_actuador.py), tomado del módulo dentro de cada prueba:
#   alta_tipo_actuador(actor, datos: DatosDeTipoActuador) -> TipoActuador
#     - Precondición a / regla 1: actor no es un Gerente activo -> PermissionDenied.
#     - Reglas 2 a 4, 8, 9 y 10: errores por campo (``nombre``, ``tiempo_minimo``, ``acciones``): un ``ValidationError`` con
#       ``error_dict``; los de varios campos van juntos.

from django.core.exceptions import PermissionDenied
from django.http import QueryDict
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import Accion, TipoActuador
from iot.tests import fabricas
from iot.tests.fabricas import accion_de_formulario as accion
from iot.tests.fabricas import datos_de_tipo
from maestros.tests.fabricas import codigos_de, crear_agronomo, error_de

tipos = perezoso("iot.servicios.tipos_actuador")
ALTA = RegistroAuditoria.Accion.ALTA_TIPO_ACTUADOR


class IotAltTacServicioTests(fabricas.ConCatalogoIot, TestCase):
    """Precondiciones, reglas y postcondiciones de IOT-ALT-TAC."""

    def setUp(self):
        self.gerente = crear_gerente()

    def alta(self, datos=None, actor=None):
        """Llama al servicio con datos válidos por defecto."""
        return tipos.alta_tipo_actuador(actor or self.gerente, datos or datos_de_tipo())

    def errores(self, datos, campo):
        """Los códigos de error de ``campo`` que da el alta con ``datos``."""
        return codigos_de(error_de(lambda: self.alta(datos)), campo)

    # ---- precondición a y regla 1 ----

    def test_pre_a_un_agronomo_no_da_de_alta(self):
        """IOT-ALT-TAC regla 6: el Agrónomo no registra tipos de actuador."""
        with self.assertRaises(PermissionDenied):
            self.alta(actor=crear_agronomo())

    def test_pre_a_otro_rol_no_da_de_alta(self):
        """IOT-ALT-TAC precondición a: solo el Gerente."""
        with self.assertRaises(PermissionDenied):
            self.alta(actor=crear_capataz())

    def test_pre_a_un_gerente_inactivo_no_da_de_alta(self):
        """IOT-ALT-TAC precondición a: la cuenta tiene que estar activa."""
        self.gerente.is_active = False
        self.gerente.save()
        with self.assertRaises(PermissionDenied):
            self.alta()

    def test_regla_1_la_alta_no_tiene_alcance_por_invernadero(self):
        """IOT-ALT-TAC regla 1: el tipo describe un modelo de equipo, no un invernadero: lo da de alta el Gerente sin elegir ninguno."""
        self.assertIsNone(getattr(self.alta(), "invernadero", None))

    # ---- flujo principal y postcondición a ----

    def test_flujo_principal_crea_el_tipo_activo_con_sus_acciones(self):
        """IOT-ALT-TAC postcondición a: tipo activo con su nombre, su tiempo mínimo y al menos una acción."""
        datos = datos_de_tipo("Extractor", 30, [accion("Encender", "ENCENDER"), accion("Fijar velocidad", "FIJAR_NIVEL", 0, 100, "%")])

        tipo = self.alta(datos)

        tipo.refresh_from_db()
        self.assertEqual((tipo.nombre_actuador, tipo.tiempo_minimo_entre_comandos, tipo.estado), ("Extractor", 30, "activo"))
        guardadas = list(tipo.acciones.order_by("id"))
        self.assertEqual([a.nombre_accion for a in guardadas], ["Encender", "Fijar velocidad"])
        self.assertTrue(all(a.estado == "activa" for a in guardadas))

    def test_post_a_cada_accion_guarda_su_comando_unidad_y_rango(self):
        """IOT-ALT-TAC postcondición a: cada acción con su comando y, si lo lleva, unidad, mínimo y máximo."""
        tipo = self.alta(
            datos_de_tipo("Ventana propia", 60, [accion("Abrir", "ABRIR"), accion("Fijar posición", "FIJAR_POSICION", 0, 90, "°")])
        )
        abrir, fijar = tipo.acciones.order_by("id")
        self.assertEqual((abrir.comando.codigo, abrir.unidad_valor, abrir.valor_minimo, abrir.valor_maximo), ("ABRIR", None, None, None))
        self.assertEqual((fijar.comando.codigo, fijar.unidad_valor, fijar.valor_minimo, fijar.valor_maximo), ("FIJAR_POSICION", "°", 0, 90))

    def test_regla_8_si_la_accion_lleva_valor_se_deduce_de_su_comando(self):
        """IOT-ALT-TAC regla 8 (MD-103): «requiere valor» no se elige ni se guarda: es ``comando.lleva_valor``."""
        tipo = self.alta(datos_de_tipo("Mixto", 60, [accion("Encender", "ENCENDER"), accion("Nivel", "FIJAR_NIVEL", 1, 5, "rpm")]))
        self.assertEqual([a.requiere_valor for a in tipo.acciones.order_by("id")], [False, True])

    # ---- regla 2: nombre ----

    def test_regla_2_el_nombre_es_obligatorio(self):
        """IOT-ALT-TAC regla 2."""
        for vacio in ("", "   ", None):
            with self.subTest(vacio=vacio):
                self.assertEqual(self.errores(datos_de_tipo(vacio), "nombre"), ["obligatorio"])

    def test_regla_2_el_nombre_tiene_que_tener_contenido(self):
        """IOT-ALT-TAC regla 2 y D-39: no puede ser solo símbolos."""
        self.assertEqual(self.errores(datos_de_tipo("-----"), "nombre"), ["sin_contenido"])

    def test_regla_2_el_nombre_tiene_hasta_60_caracteres(self):
        """docs/modelo/iot.md, «TipoActuador»: hasta 60, con un error de campo y no un 500."""
        self.alta(datos_de_tipo("a" * 60))
        self.assertEqual(self.errores(datos_de_tipo("b" * 61), "nombre"), ["demasiado_largo"])

    def test_regla_2_el_nombre_se_guarda_recortado(self):
        """IOT-ALT-TAC regla 2: sin espacios al principio ni al final."""
        self.assertEqual(self.alta(datos_de_tipo("  Extractor  ")).nombre_actuador, "Extractor")

    def test_regla_2_el_nombre_es_unico_sin_distinguir_mayusculas_ni_espacios(self):
        """IOT-ALT-TAC regla 2: único entre todos, con el mensaje del extracto."""
        self.alta(datos_de_tipo("Extractor"))
        error = error_de(lambda: self.alta(datos_de_tipo("  eXtractor ")))
        self.assertEqual(codigos_de(error, "nombre"), ["nombre_repetido"])
        self.assertEqual(error.error_dict["nombre"][0].message, "Ya existe un tipo de actuador con ese nombre.")

    def test_regla_2_el_nombre_es_unico_tambien_frente_a_los_inactivos_y_a_los_iniciales(self):
        """IOT-ALT-TAC regla 2: cuentan los inactivos y los seis tipos iniciales (por ejemplo, «Ventilador»)."""
        self.assertEqual(self.errores(datos_de_tipo("ventilador"), "nombre"), ["nombre_repetido"])
        fabricas.tipo_actuador("Dado de baja", activo=False)
        self.assertEqual(self.errores(datos_de_tipo("DADO DE BAJA"), "nombre"), ["nombre_repetido"])

    def test_regla_2_un_nombre_repetido_no_crea_nada(self):
        """IOT-ALT-TAC regla 2: un alta rechazada no deja ni el tipo ni sus acciones ni un registro de auditoría."""
        tipos_antes, acciones_antes, registros_antes = TipoActuador.objects.count(), Accion.objects.count(), RegistroAuditoria.objects.count()
        self.errores(datos_de_tipo("Ventilador"), "nombre")
        self.assertEqual(
            (TipoActuador.objects.count(), Accion.objects.count(), RegistroAuditoria.objects.count()),
            (tipos_antes, acciones_antes, registros_antes),
        )

    # ---- regla 9: tiempo mínimo ----

    def test_regla_9_el_tiempo_minimo_es_un_entero_de_cero_en_adelante(self):
        """IOT-ALT-TAC regla 9: 0 y 60 valen; texto o número con decimales, negativos y vacío, no."""
        for valido in (0, 60, "45", " 7 "):
            with self.subTest(valido=valido):
                self.alta(datos_de_tipo(f"Tipo {valido!r}", valido))
        for invalido in ("", None, "abc", "1.5", "-1", -1, 1.5, True, "9" * 12):
            with self.subTest(invalido=invalido):
                error = error_de(lambda: self.alta(datos_de_tipo("Otro", invalido)))
                self.assertEqual(codigos_de(error, "tiempo_minimo"), ["tiempo_invalido"])
                self.assertEqual(error.error_dict["tiempo_minimo"][0].message, "Ingresá un número entero de segundos (0 o más).")

    # ---- regla 3: acciones ----

    def test_regla_3_un_tipo_necesita_al_menos_una_accion(self):
        """IOT-ALT-TAC regla 3 (R059) y mensaje del prototipo."""
        error = error_de(lambda: self.alta(datos_de_tipo("Sin acciones", 60, [])))
        self.assertEqual(codigos_de(error, "acciones"), ["sin_acciones"])
        self.assertEqual(error.error_dict["acciones"][0].message, "El tipo necesita al menos una acción activa.")

    def test_regla_3_cada_accion_necesita_un_nombre(self):
        """IOT-ALT-TAC regla 3 y mensaje del prototipo."""
        error = error_de(lambda: self.alta(datos_de_tipo("X", 60, [accion("  ", "ENCENDER")])))
        self.assertEqual([e.message for e in error.error_dict["acciones"]], ["Cada acción necesita un nombre."])

    def test_regla_3_el_nombre_de_la_accion_tiene_hasta_40_caracteres(self):
        """docs/modelo/iot.md, «Accion»: hasta 40 caracteres."""
        self.alta(datos_de_tipo("Largo 40", 60, [accion("a" * 40, "ENCENDER")]))
        self.assertEqual(self.errores(datos_de_tipo("Largo 41", 60, [accion("b" * 41, "ENCENDER")]), "acciones"), ["accion_nombre_largo"])

    def test_regla_3_cada_accion_necesita_un_comando_del_catalogo(self):
        """IOT-ALT-TAC regla 3 y mensaje del prototipo: sin comando, o con uno que no está en el catálogo."""
        for comando in ("", None, "EXPLOTAR"):
            with self.subTest(comando=comando):
                error = error_de(lambda: self.alta(datos_de_tipo("X", 60, [accion("Prender", comando)])))
                self.assertEqual([e.message for e in error.error_dict["acciones"]], ["Elegí el comando de «Prender»."])

    def test_regla_3_los_nombres_de_las_acciones_son_unicos_en_el_tipo(self):
        """IOT-ALT-TAC regla 3 y mensaje del prototipo: sin distinguir mayúsculas ni espacios."""
        error = error_de(lambda: self.alta(datos_de_tipo("X", 60, [accion("Encender", "ENCENDER"), accion(" encender ", "APAGAR")])))
        self.assertEqual([e.message for e in error.error_dict["acciones"]], ["La acción «encender» está repetida."])

    def test_regla_3_dos_acciones_del_tipo_no_usan_el_mismo_comando(self):
        """IOT-ALT-TAC regla 3 y mensaje del prototipo."""
        error = error_de(lambda: self.alta(datos_de_tipo("X", 60, [accion("Encender", "ENCENDER"), accion("Prender", "ENCENDER")])))
        self.assertEqual([e.message for e in error.error_dict["acciones"]], ["Dos acciones usan el comando ENCENDER."])

    # ---- regla 4: valor, unidad y rango ----

    def test_regla_4_un_comando_con_valor_necesita_minimo_y_maximo_enteros_con_minimo_menor(self):
        """IOT-ALT-TAC regla 4 y mensaje del prototipo."""
        mensaje = "“Fijar velocidad” necesita un mínimo y un máximo enteros, con el mínimo menor al máximo."
        for minimo, maximo in ((None, 100), (0, None), ("", ""), (50, 50), (60, 10), ("a", 10), (0.5, 10), ("1.5", "9")):
            with self.subTest(minimo=minimo, maximo=maximo):
                error = error_de(lambda: self.alta(datos_de_tipo("X", 60, [accion("Fijar velocidad", "FIJAR_NIVEL", minimo, maximo, "%")])))
                self.assertEqual([e.message for e in error.error_dict["acciones"]], [mensaje])

    def test_regla_4_el_rango_puede_ser_negativo_y_viene_como_texto_del_formulario(self):
        """IOT-ALT-TAC regla 4: enteros; el formulario los manda como texto."""
        tipo = self.alta(datos_de_tipo("X", 60, [accion("Fijar", "FIJAR_NIVEL", "-10", " 50 ", "%")]))
        fijar = tipo.acciones.get()
        self.assertEqual((fijar.valor_minimo, fijar.valor_maximo), (-10, 50))

    def test_regla_4_un_comando_con_valor_necesita_unidad(self):
        """IOT-ALT-TAC regla 4 y mensaje del prototipo."""
        for unidad in ("", None, "  "):
            with self.subTest(unidad=unidad):
                error = error_de(lambda: self.alta(datos_de_tipo("X", 60, [accion("Fijar velocidad", "FIJAR_NIVEL", 0, 100, unidad)])))
                self.assertEqual([e.message for e in error.error_dict["acciones"]], ["“Fijar velocidad” necesita una unidad."])

    def test_regla_10_la_unidad_se_elige_de_la_lista_cerrada_del_comando(self):
        """IOT-ALT-TAC regla 10: FIJAR_NIVEL admite %, rpm y L/min; FIJAR_POSICION, %, ° y cm; ninguna otra."""
        for comando, unidad in (("FIJAR_NIVEL", "rpm"), ("FIJAR_NIVEL", "L/min"), ("FIJAR_POSICION", "cm"), ("FIJAR_POSICION", "°")):
            with self.subTest(comando=comando, unidad=unidad):
                self.alta(datos_de_tipo(f"{comando} {unidad}", 60, [accion("Fijar", comando, 0, 10, unidad)]))
        for comando, unidad in (("FIJAR_NIVEL", "cm"), ("FIJAR_NIVEL", "porcentaje"), ("FIJAR_POSICION", "rpm"), ("FIJAR_POSICION", "pct")):
            with self.subTest(comando=comando, unidad=unidad):
                self.assertEqual(
                    self.errores(datos_de_tipo("Otro", 60, [accion("Fijar", comando, 0, 10, unidad)]), "acciones"), ["unidad_invalida"]
                )

    def test_regla_4_un_comando_sin_valor_no_tiene_unidad_ni_rango(self):
        """IOT-ALT-TAC regla 4: si el comando no lleva valor, la acción no tiene unidad ni rango (aunque el formulario los mande)."""
        tipo = self.alta(datos_de_tipo("X", 60, [accion("Encender", "ENCENDER", 0, 100, "%")]))
        encender = tipo.acciones.get()
        self.assertEqual((encender.unidad_valor, encender.valor_minimo, encender.valor_maximo), (None, None, None))

    # ---- los errores van juntos ----

    def test_regla_2_los_errores_de_varios_campos_llegan_juntos(self):
        """docs/patrones/abm.md, sección 2, paso 2: un solo ``ValidationError`` con un error por campo."""
        error = error_de(lambda: self.alta(datos_de_tipo("", "x", [])))
        self.assertEqual(sorted(error.error_dict), ["acciones", "nombre", "tiempo_minimo"])

    # ---- postcondición b: auditoría ----

    def test_post_b_audita_el_tipo_y_cada_accion_creada(self):
        """IOT-ALT-TAC postcondición b y «Cómo se aplica», «Auditoría»: ``alta_tipo_actuador`` con el tipo y cada acción creada."""
        tipo = self.alta(datos_de_tipo("Extractor", 30, [accion("Encender", "ENCENDER"), accion("Fijar velocidad", "FIJAR_NIVEL", 0, 100, "%")]))
        registro = RegistroAuditoria.objects.get(accion=ALTA)
        encender, fijar = tipo.acciones.order_by("id")

        self.assertEqual((registro.usuario_id, registro.rol), (self.gerente.pk, "gerente"))
        self.assertEqual(
            registro.afectados,
            [
                {"modelo": "iot.tipoactuador", "id": tipo.pk, "texto": "Extractor"},
                {"modelo": "iot.accion", "id": encender.pk, "texto": "Encender"},
                {"modelo": "iot.accion", "id": fijar.pk, "texto": "Fijar velocidad"},
            ],
        )
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["nombre"], {"antes": None, "despues": "Extractor"})
        self.assertEqual(cambios["tiempo_minimo_entre_comandos"], {"antes": None, "despues": 30})
        self.assertEqual(cambios["estado"], {"antes": None, "despues": "activo"})
        self.assertEqual(
            registro.detalle["datos"]["acciones_creadas"],
            [{"id": encender.pk, "texto": "Encender"}, {"id": fijar.pk, "texto": "Fijar velocidad"}],
        )

    def test_post_b_el_registro_se_puede_leer_en_la_pantalla_de_auditoria(self):
        """D-36: los campos y el estado del registro tienen su nombre visible (``ETIQUETAS``)."""
        self.alta()
        registro = RegistroAuditoria.objects.get(accion=ALTA)
        filas = {campo: (antes, despues) for campo, antes, despues in registro.filas_de_cambios()}
        self.assertEqual(filas["Tiempo mínimo entre comandos (s)"], ("—", "60"))
        self.assertEqual(filas["Estado"], ("—", "Activo"))
        self.assertIn("Acciones creadas", dict(registro.filas_de_datos()))

    def test_post_b_un_alta_rechazada_no_audita(self):
        """D-22: no queda un registro de una operación que no se hizo."""
        self.errores(datos_de_tipo(""), "nombre")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())

    def test_post_b_el_detalle_solo_tiene_cambios_y_datos(self):
        """D-36: el detalle del alta tiene las dos claves del formato y ninguna más."""
        self.alta()
        self.assertEqual(set(RegistroAuditoria.objects.get(accion=ALTA).detalle), {"cambios", "datos"})


class DatosDeTipoActuadorDesdePostTests(fabricas.ConCatalogoIot, TestCase):
    """``DatosDeTipoActuador.desde_post``: arma los datos del servicio desde lo que manda el formulario."""

    def test_desde_post_arma_los_datos_y_cada_fila_con_su_id_original(self):
        """Los campos del formulario: ``nombre``, ``tiempo_minimo``, ``acciones_total`` y ``accion_<i>_<campo>``."""
        post = QueryDict(mutable=True)
        post.update(
            {
                "nombre": "Extractor",
                "tiempo_minimo": "30",
                "acciones_total": "2",
                "accion_0_id": "7",
                "accion_0_nombre": "Encender",
                "accion_0_comando": "ENCENDER",
                "accion_1_id": "",
                "accion_1_nombre": "Fijar velocidad",
                "accion_1_comando": "FIJAR_NIVEL",
                "accion_1_minimo": "0",
                "accion_1_maximo": "100",
                "accion_1_unidad": "%",
            }
        )

        datos = tipos.DatosDeTipoActuador.desde_post(post)

        self.assertEqual((datos.nombre, datos.tiempo_minimo), ("Extractor", "30"))
        self.assertEqual([(a.id, a.nombre, a.comando) for a in datos.acciones], [(7, "Encender", "ENCENDER"), (None, "Fijar velocidad", "FIJAR_NIVEL")])
        self.assertEqual((datos.acciones[1].minimo, datos.acciones[1].maximo, datos.acciones[1].unidad), ("0", "100", "%"))

    def test_desde_post_tolera_campos_que_faltan_y_totales_raros(self):
        """Un formulario armado a mano (sin campos, con un total que no es número o desmedido) no rompe: los errores los da el servicio."""
        vacio = tipos.DatosDeTipoActuador.desde_post(QueryDict(""))
        self.assertEqual((vacio.nombre, vacio.tiempo_minimo, vacio.acciones), ("", "", []))
        raro = QueryDict(mutable=True)
        raro.update({"acciones_total": "99999999"})
        self.assertLessEqual(len(tipos.DatosDeTipoActuador.desde_post(raro).acciones), 50)
        raro.update({"acciones_total": "mucho"})
        self.assertEqual(tipos.DatosDeTipoActuador.desde_post(raro).acciones, [])

    def test_desde_post_un_id_que_no_es_un_numero_se_ignora(self):
        """Un ``accion_<i>_id`` mal formado se trata como «acción nueva»."""
        post = QueryDict(mutable=True)
        post.update({"acciones_total": "1", "accion_0_id": "abc", "accion_0_nombre": "X", "accion_0_comando": "ENCENDER"})
        self.assertIsNone(tipos.DatosDeTipoActuador.desde_post(post).acciones[0].id)
