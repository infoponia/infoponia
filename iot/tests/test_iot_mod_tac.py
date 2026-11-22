# Pruebas de IOT-MOD-TAC · Modificar Tipo de Actuador, con la reactivación (docs/casos_de_uso/iot/tipos_de_actuador.md, v0.4) y de lo
# que cita: D-28 (sin cambios no se audita), D-36 (auditoría), D-72 y docs/modelo/iot.md. Se escribieron ANTES que el servicio.
#
# Servicios que se prueban (iot/servicios/tipos_actuador.py), tomados del módulo dentro de cada prueba:
#   modificar_tipo_actuador(actor, tipo_id, datos: DatosDeTipoActuador) -> TipoActuador
#   reactivar_tipo_actuador(actor, tipo_id) -> TipoActuador
#     - Precondición a / regla 1: actor no es un Gerente activo -> PermissionDenied; un id que no existe -> Http404.
#     - Regla 2: las de IOT-ALT-TAC (errores por campo). Reglas 4, 5, 7 y 8: errores de ``acciones`` o generales (``__all__``).
#     - «En uso» y «con historial» (regla 4) las dan ``acciones_en_uso(tipo)`` y ``acciones_con_historial(tipo)``: en IOT-01 no
#       devuelven nada (se completan en IOT-05 e IOT-06), así que estas pruebas las reemplazan con ``mock.patch``.

from unittest import mock

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import TestCase
from django.urls import reverse

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import Accion, TipoActuador
from iot.tests import fabricas
from iot.tests.fabricas import accion_de_formulario as accion
from iot.tests.fabricas import datos_de
from maestros.tests.fabricas import codigos_de, crear_agronomo, error_de

tipos = perezoso("iot.servicios.tipos_actuador")
MODIFICACION = RegistroAuditoria.Accion.MODIFICACION_TIPO_ACTUADOR
REACTIVACION = RegistroAuditoria.Accion.REACTIVACION_TIPO_ACTUADOR
EN_USO = "iot.servicios.tipos_actuador.acciones_en_uso"
CON_HISTORIAL = "iot.servicios.tipos_actuador.acciones_con_historial"


class IotModTacServicioTests(fabricas.ConCatalogoIot, TestCase):
    """Precondiciones, reglas y postcondiciones de IOT-MOD-TAC."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.tipo = fabricas.tipo_actuador(
            "Extractor",
            30,
            [("Encender", "ENCENDER"), ("Apagar", "APAGAR"), ("Fijar velocidad", "FIJAR_NIVEL", 0, 100, "%")],
        )
        self.encender, self.apagar, self.fijar = self.tipo.acciones.order_by("id")

    def modificar(self, datos, tipo=None, actor=None):
        """Llama al servicio sobre ``tipo`` (el de la prueba por defecto)."""
        return tipos.modificar_tipo_actuador(actor or self.gerente, (tipo or self.tipo).pk, datos)

    def errores(self, datos, campo="acciones"):
        """Los códigos de error de ``campo`` que da la modificación con ``datos``."""
        return codigos_de(error_de(lambda: self.modificar(datos)), campo)

    def mensajes(self, datos, campo="acciones"):
        """Los textos de error de ``campo`` que da la modificación con ``datos``."""
        return [e.message for e in error_de(lambda: self.modificar(datos)).error_dict[campo]]

    def uso(self, accion_usada, codigo="RGL-3", valor=None):
        """``mock.patch`` de ``acciones_en_uso``: ``accion_usada`` está en uso por ``codigo`` con ese ``valor``."""
        return mock.patch(EN_USO, return_value={accion_usada.pk: [tipos.UsoDeAccion(codigo, valor)]})

    def con_historial(self, *acciones_usadas):
        """``mock.patch`` de ``acciones_con_historial``: esas acciones tienen comandos en su historial."""
        return mock.patch(CON_HISTORIAL, return_value={a.pk for a in acciones_usadas})

    def cambiar(self, datos, nombre_de_la_accion, **campos):
        """Cambia campos de la fila ``nombre_de_la_accion`` del formulario (``nombre``, ``comando``, ``minimo``, ``maximo``, ``unidad``)."""
        fila = next(a for a in datos.acciones if a.nombre == nombre_de_la_accion)
        for campo, valor in campos.items():
            setattr(fila, campo, valor)
        return datos

    # ---- precondición a, regla 1 y regla 7 ----

    def test_pre_a_un_agronomo_no_modifica(self):
        """IOT-MOD-TAC regla 1: solo el Gerente activo modifica un tipo."""
        with self.assertRaises(PermissionDenied):
            self.modificar(datos_de(self.tipo), actor=crear_agronomo())

    def test_pre_a_otro_rol_o_un_gerente_inactivo_no_modifican(self):
        """IOT-MOD-TAC precondición a."""
        with self.assertRaises(PermissionDenied):
            self.modificar(datos_de(self.tipo), actor=crear_capataz())
        self.gerente.is_active = False
        self.gerente.save()
        with self.assertRaises(PermissionDenied):
            self.modificar(datos_de(self.tipo))

    def test_pre_a_un_tipo_que_no_existe_da_404(self):
        """docs/patrones/abm.md, sección 2: un id inexistente da 404."""
        with self.assertRaises(Http404):
            tipos.modificar_tipo_actuador(self.gerente, 999999, datos_de(self.tipo))

    def test_regla_1_el_tipo_se_modifica_sin_alcance_por_invernadero(self):
        """IOT-MOD-TAC regla 1: el Gerente modifica un tipo aunque tenga equipos en invernaderos de cualquier Agrónomo."""
        from maestros.tests.fabricas import crear_invernadero

        fabricas.actuador(fabricas.sistema(crear_invernadero("Ajeno", agronomo=crear_agronomo())), self.tipo)
        datos = datos_de(self.tipo)
        datos.nombre = "Extractor grande"
        self.assertEqual(self.modificar(datos).nombre_actuador, "Extractor grande")

    def test_regla_7_un_tipo_inactivo_no_se_modifica(self):
        """IOT-MOD-TAC regla 7: solo se reactiva."""
        TipoActuador.objects.filter(pk=self.tipo.pk).update(estado="inactivo")
        datos = datos_de(self.tipo)
        datos.nombre = "Otro nombre"
        error = error_de(lambda: self.modificar(datos))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["tipo_inactivo"])

    # ---- regla 2: nombre y tiempo (las de IOT-ALT-TAC) ----

    def test_regla_2_el_nombre_no_puede_ser_el_de_otro_tipo(self):
        """IOT-MOD-TAC postcondición b de precondiciones y regla 2: sin distinguir mayúsculas; cuentan los inactivos."""
        fabricas.tipo_actuador("Calefactor propio", activo=False)
        for nombre in ("ventilador", "  CALEFACTOR PROPIO "):
            with self.subTest(nombre=nombre):
                datos = datos_de(self.tipo)
                datos.nombre = nombre
                self.assertEqual(self.errores(datos, "nombre"), ["nombre_repetido"])

    def test_regla_2_el_tipo_puede_cambiar_la_capitalizacion_de_su_propio_nombre(self):
        """IOT-MOD-TAC regla 2: el nombre propio no cuenta como repetido."""
        datos = datos_de(self.tipo)
        datos.nombre = "EXTRACTOR"
        self.assertEqual(self.modificar(datos).nombre_actuador, "EXTRACTOR")

    def test_regla_2_el_nombre_y_el_tiempo_siguen_las_reglas_del_alta(self):
        """IOT-MOD-TAC regla 2: obligatorio, 60 caracteres y tiempo entero de 0 en adelante; los errores llegan juntos."""
        datos = datos_de(self.tipo)
        datos.nombre, datos.tiempo_minimo = "", "-3"
        self.assertEqual(sorted(error_de(lambda: self.modificar(datos)).error_dict), ["nombre", "tiempo_minimo"])

    def test_regla_2_las_acciones_siguen_las_reglas_del_alta(self):
        """IOT-MOD-TAC regla 2: dos acciones con el mismo comando, o un comando con valor sin unidad, se rechazan."""
        datos = datos_de(self.tipo)
        self.cambiar(datos, "Apagar", comando="ENCENDER")
        self.assertEqual(self.errores(datos), ["comando_repetido"])
        datos = self.cambiar(datos_de(self.tipo), "Fijar velocidad", unidad="")
        self.assertEqual(self.errores(datos), ["unidad_obligatoria"])

    # ---- regla 3: cambios sin restricciones ----

    def test_regla_3_se_cambian_el_nombre_el_tiempo_y_se_agregan_acciones(self):
        """IOT-MOD-TAC regla 3 y postcondición a: agregar acciones, cambiar el nombre y el tiempo mínimo."""
        datos = datos_de(self.tipo)
        datos.nombre, datos.tiempo_minimo = "Extractor de aire", "90"
        datos.acciones.append(accion("Girar", "ABRIR"))

        tipo = self.modificar(datos)

        tipo.refresh_from_db()
        self.assertEqual((tipo.nombre_actuador, tipo.tiempo_minimo_entre_comandos), ("Extractor de aire", 90))
        self.assertEqual([a.nombre_accion for a in tipo.acciones.order_by("id")], ["Encender", "Apagar", "Fijar velocidad", "Girar"])
        self.assertEqual(set(tipo.acciones.values_list("pk", flat=True)) & {self.encender.pk, self.apagar.pk, self.fijar.pk}, {self.encender.pk, self.apagar.pk, self.fijar.pk})

    def test_regla_3_se_amplia_el_rango_de_una_accion_sin_restricciones(self):
        """IOT-MOD-TAC regla 3: ampliar el rango no se rechaza, ni siquiera con la acción en uso. (Con «rpm», que no tiene tope: D-80.)"""
        tipo = fabricas.tipo_actuador("Con rpm", acciones=[("Fijar velocidad", "FIJAR_NIVEL", 100, 200, "rpm")])
        accion_en_uso = tipo.acciones.get()
        datos = self.cambiar(datos_de(tipo), "Fijar velocidad", minimo="0", maximo="3000")
        with self.uso(accion_en_uso, valor=150):
            self.modificar(datos, tipo=tipo)
        accion_en_uso.refresh_from_db()
        self.assertEqual((accion_en_uso.valor_minimo, accion_en_uso.valor_maximo), (0, 3000))

    def test_d80_al_modificar_el_rango_sigue_la_regla_de_su_unidad(self):
        """D-80: ampliar un rango en «%» más allá de 0 a 100 se rechaza; en la modificación rige la misma regla que en el alta."""
        datos = self.cambiar(datos_de(self.tipo), "Fijar velocidad", minimo="-10", maximo="200")
        self.assertEqual(self.errores(datos), ["rango_fuera_de_unidad"])
        self.fijar.refresh_from_db()
        self.assertEqual((self.fijar.valor_minimo, self.fijar.valor_maximo), (0, 100))

    def test_regla_3_se_cambia_la_unidad_y_el_comando_de_una_accion_que_no_esta_en_uso_ni_tiene_historial(self):
        """IOT-MOD-TAC regla 4 (a contrario): sin uso ni historial, el comando y la unidad se pueden cambiar."""
        datos = self.cambiar(datos_de(self.tipo), "Fijar velocidad", unidad="rpm")
        self.cambiar(datos, "Encender", comando="ABRIR")
        self.modificar(datos)
        self.fijar.refresh_from_db()
        self.encender.refresh_from_db()
        self.assertEqual((self.fijar.unidad_valor, self.encender.comando.codigo), ("rpm", "ABRIR"))

    def test_regla_3_dos_acciones_pueden_intercambiar_sus_nombres_y_sus_comandos(self):
        """IOT-MOD-TAC regla 3: el intercambio es válido aunque a mitad de camino chocaría con los índices únicos."""
        datos = datos_de(self.tipo)
        primera, segunda = datos.acciones[0], datos.acciones[1]  # «Encender» y «Apagar»
        primera.nombre, primera.comando = "Apagar", "APAGAR"
        segunda.nombre, segunda.comando = "Encender", "ENCENDER"
        self.modificar(datos)
        self.encender.refresh_from_db()
        self.apagar.refresh_from_db()
        self.assertEqual((self.encender.nombre_accion, self.encender.comando.codigo), ("Apagar", "APAGAR"))
        self.assertEqual((self.apagar.nombre_accion, self.apagar.comando.codigo), ("Encender", "ENCENDER"))

    def test_regla_3_una_accion_con_historial_se_puede_renombrar_y_ampliar(self):
        """IOT-MOD-TAC regla 4: una acción con comandos en su historial no cambia su comando ni su unidad, pero sí el nombre y el rango."""
        tipo = fabricas.tipo_actuador("Con rpm", acciones=[("Fijar velocidad", "FIJAR_NIVEL", 0, 100, "rpm")])
        fijar = tipo.acciones.get()
        datos = self.cambiar(datos_de(tipo), "Fijar velocidad", nombre="Velocidad", minimo="0", maximo="150")
        with self.con_historial(fijar):
            self.modificar(datos, tipo=tipo)
        fijar.refresh_from_db()
        self.assertEqual((fijar.nombre_accion, fijar.valor_maximo), ("Velocidad", 150))

    # ---- regla 5: al menos una acción activa ----

    def test_regla_5_el_tipo_conserva_al_menos_una_accion_activa(self):
        """IOT-MOD-TAC regla 5 y mensaje del prototipo: quitar todas las acciones se rechaza."""
        datos = datos_de(self.tipo)
        datos.acciones = []
        error = error_de(lambda: self.modificar(datos))
        self.assertEqual([e.message for e in error.error_dict["acciones"]], ["El tipo necesita al menos una acción activa."])
        self.assertEqual(self.tipo.acciones.filter(estado="activa").count(), 3)

    # ---- regla 8 y postcondición a: quitar con y sin historial ----

    def test_regla_8_una_accion_quitada_con_historial_queda_inactiva(self):
        """IOT-MOD-TAC regla 8 y postcondición a: conserva su fila y su historial, deja de ofrecerse."""
        datos = datos_de(self.tipo)
        datos.acciones = [a for a in datos.acciones if a.nombre != "Apagar"]
        with self.con_historial(self.apagar):
            self.modificar(datos)
        self.apagar.refresh_from_db()
        self.assertEqual(self.apagar.estado, "inactiva")

    def test_post_a_una_accion_quitada_sin_historial_se_borra(self):
        """IOT-MOD-TAC postcondición a: una que no tenía comandos en su historial se elimina."""
        datos = datos_de(self.tipo)
        datos.acciones = [a for a in datos.acciones if a.nombre != "Apagar"]
        self.modificar(datos)
        self.assertFalse(Accion.objects.filter(pk=self.apagar.pk).exists())
        self.assertEqual(self.tipo.acciones.count(), 2)

    def test_regla_8_se_puede_volver_a_crear_una_accion_igual_a_una_inactiva(self):
        """docs/modelo/iot.md, «Accion»: los índices únicos son entre las ACTIVAS; una inactiva no impide crear otra con su nombre y su comando."""
        datos = datos_de(self.tipo)
        datos.acciones = [a for a in datos.acciones if a.nombre != "Apagar"]
        with self.con_historial(self.apagar):
            self.modificar(datos)
        datos = datos_de(self.tipo)
        datos.acciones.append(accion("Apagar", "APAGAR"))
        self.modificar(datos)
        self.assertEqual(self.tipo.acciones.filter(nombre_accion="Apagar").count(), 2)
        self.assertEqual(self.tipo.acciones.filter(nombre_accion="Apagar", estado="activa").count(), 1)

    def test_regla_8_una_accion_inactiva_no_se_ofrece_ni_se_toca_en_la_modificacion(self):
        """IOT-MOD-TAC regla 8: el formulario trae solo las activas; las inactivas siguen igual."""
        Accion.objects.filter(pk=self.apagar.pk).update(estado="inactiva")
        datos = datos_de(self.tipo)
        self.assertEqual([a.nombre for a in datos.acciones], ["Encender", "Fijar velocidad"])
        datos.nombre = "Extractor 2"
        self.modificar(datos)
        self.apagar.refresh_from_db()
        self.assertEqual(self.apagar.estado, "inactiva")

    # ---- regla 4: acción en uso ----

    def test_regla_4_una_accion_en_uso_no_se_quita(self):
        """IOT-MOD-TAC regla 4: el Sistema informa qué reglas o comandos lo impiden."""
        datos = datos_de(self.tipo)
        datos.acciones = [a for a in datos.acciones if a.nombre != "Apagar"]
        with self.uso(self.apagar, "RGL-3"):
            self.assertEqual(self.mensajes(datos), ["No se puede quitar «Apagar»: la usan RGL-3."])
        self.assertTrue(Accion.objects.filter(pk=self.apagar.pk, estado="activa").exists())

    def test_regla_4_el_mensaje_lista_todas_las_reglas_y_comandos_que_la_usan(self):
        """IOT-MOD-TAC regla 4: informa todos los usos."""
        datos = datos_de(self.tipo)
        datos.acciones = [a for a in datos.acciones if a.nombre != "Apagar"]
        usos = {self.apagar.pk: [tipos.UsoDeAccion("RGL-3", None), tipos.UsoDeAccion("CMD-7", None)]}
        with mock.patch(EN_USO, return_value=usos):
            self.assertEqual(self.mensajes(datos), ["No se puede quitar «Apagar»: la usan RGL-3, CMD-7."])

    def test_regla_4_una_accion_en_uso_no_se_renombra(self):
        """IOT-MOD-TAC regla 4."""
        datos = self.cambiar(datos_de(self.tipo), "Apagar", nombre="Parar")
        with self.uso(self.apagar, "CMD-7"):
            self.assertEqual(self.mensajes(datos), ["No se puede renombrar «Apagar»: la usan CMD-7."])

    def test_regla_4_una_accion_en_uso_no_cambia_su_comando(self):
        """IOT-MOD-TAC regla 4 y mensaje del prototipo."""
        datos = self.cambiar(datos_de(self.tipo), "Apagar", comando="CERRAR")
        with self.uso(self.apagar, "RGL-3"):
            self.assertEqual(
                self.mensajes(datos), ["No se puede cambiar el comando de «Apagar»: la usan RGL-3. Agregá una acción nueva."]
            )

    def test_regla_4_una_accion_en_uso_no_cambia_su_unidad(self):
        """IOT-MOD-TAC regla 4."""
        datos = self.cambiar(datos_de(self.tipo), "Fijar velocidad", unidad="rpm")
        with self.uso(self.fijar, "RGL-3", 50):
            self.assertEqual(
                self.mensajes(datos), ["No se puede cambiar la unidad de «Fijar velocidad»: la usan RGL-3. Agregá una acción nueva."]
            )

    def test_regla_4_el_rango_de_una_accion_en_uso_se_achica_solo_si_ningun_valor_queda_afuera(self):
        """IOT-MOD-TAC regla 4: un valor de una regla o de un comando fuera del rango nuevo lo impide; si todos quedan adentro, se achica."""
        usos = {self.fijar.pk: [tipos.UsoDeAccion("RGL-3", 40), tipos.UsoDeAccion("CMD-9", 80), tipos.UsoDeAccion("RGL-4", None)]}
        with mock.patch(EN_USO, return_value=usos):
            afuera = self.cambiar(datos_de(self.tipo), "Fijar velocidad", minimo="50", maximo="100")
            self.assertEqual(
                self.mensajes(afuera), ["No se puede achicar el rango de «Fijar velocidad»: quedarían afuera los valores de RGL-3."]
            )
            tambien_arriba = self.cambiar(datos_de(self.tipo), "Fijar velocidad", minimo="50", maximo="60")
            self.assertEqual(
                self.mensajes(tambien_arriba),
                ["No se puede achicar el rango de «Fijar velocidad»: quedarían afuera los valores de RGL-3, CMD-9."],
            )
            adentro = self.cambiar(datos_de(self.tipo), "Fijar velocidad", minimo="40", maximo="80")
            self.modificar(adentro)
        self.fijar.refresh_from_db()
        self.assertEqual((self.fijar.valor_minimo, self.fijar.valor_maximo), (40, 80))

    def test_regla_4_una_accion_con_historial_no_cambia_su_comando(self):
        """IOT-MOD-TAC regla 4 y mensaje del prototipo: para otro comando se agrega una acción nueva."""
        datos = self.cambiar(datos_de(self.tipo), "Apagar", comando="CERRAR")
        with self.con_historial(self.apagar):
            self.assertEqual(
                self.mensajes(datos),
                ["No se puede cambiar el comando de «Apagar»: tiene comandos en su historial. Agregá una acción nueva."],
            )

    def test_regla_4_una_accion_con_historial_no_cambia_su_unidad(self):
        """IOT-MOD-TAC regla 4."""
        datos = self.cambiar(datos_de(self.tipo), "Fijar velocidad", unidad="L/min")
        with self.con_historial(self.fijar):
            self.assertEqual(
                self.mensajes(datos),
                ["No se puede cambiar la unidad de «Fijar velocidad»: tiene comandos en su historial. Agregá una acción nueva."],
            )

    def test_regla_4_todos_los_impedimentos_llegan_juntos(self):
        """docs/patrones/abm.md, sección 2: no se queda con el primero."""
        datos = self.cambiar(datos_de(self.tipo), "Apagar", nombre="Parar")
        datos.acciones = [a for a in datos.acciones if a.nombre != "Encender"]
        usos = {self.apagar.pk: [tipos.UsoDeAccion("RGL-3", None)], self.encender.pk: [tipos.UsoDeAccion("CMD-7", None)]}
        with mock.patch(EN_USO, return_value=usos):
            self.assertEqual(len(self.mensajes(datos)), 2)

    def test_regla_4_modificar_consulta_el_uso_y_el_historial(self):
        """«Cómo se aplica», «Modificar»: ``acciones_en_uso`` y ``acciones_con_historial`` se llaman al modificar (IOT-05 e IOT-06 les suman la consulta)."""
        with mock.patch(EN_USO, wraps=tipos.acciones_en_uso) as en_uso, mock.patch(CON_HISTORIAL, wraps=tipos.acciones_con_historial) as historial:
            datos = datos_de(self.tipo)
            datos.nombre = "Extractor 2"
            self.modificar(datos)
        en_uso.assert_called()
        historial.assert_called()

    def test_regla_4_en_iot_01_ninguna_accion_esta_en_uso_ni_tiene_historial(self):
        """«Cómo se aplica», «Modificar»: hasta IOT-05 e IOT-06 las dos funciones devuelven «ninguna»."""
        self.assertEqual(tipos.acciones_en_uso(self.tipo), {})
        self.assertEqual(tipos.acciones_con_historial(self.tipo), set())

    # ---- D-28: sin cambios ----

    def test_d28_sin_cambios_no_se_escribe_ni_se_audita(self):
        """D-28: guardar el formulario sin tocar nada no escribe ni audita."""
        antes = RegistroAuditoria.objects.count()
        acciones = list(Accion.objects.order_by("id").values_list("id", "nombre_accion", "estado"))
        tipo = self.modificar(datos_de(self.tipo))
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
        self.assertEqual(list(Accion.objects.order_by("id").values_list("id", "nombre_accion", "estado")), acciones)
        self.assertEqual(tipo.pk, self.tipo.pk)

    def test_d28_un_nombre_que_solo_cambia_en_los_espacios_no_cuenta_como_cambio(self):
        """D-28: el nombre se compara recortado."""
        antes = RegistroAuditoria.objects.count()
        datos = datos_de(self.tipo)
        datos.nombre = "  Extractor "
        self.modificar(datos)
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    # ---- tampering y cambios simultáneos ----

    def test_una_accion_de_otro_tipo_o_inexistente_se_rechaza_como_cambio_simultaneo(self):
        """docs/patrones/bloqueos.md: lo que cambió mientras se esperaba se rechaza con ``cambio_simultaneo``."""
        otra = fabricas.tipo_actuador().acciones.first()
        for id_ajeno in (otra.pk, 999999, self.apagar.pk):
            with self.subTest(id=id_ajeno):
                datos = datos_de(self.tipo)
                if id_ajeno == self.apagar.pk:
                    Accion.objects.filter(pk=self.apagar.pk).update(estado="inactiva")
                datos.acciones[0].id = id_ajeno
                self.assertEqual(codigos_de(error_de(lambda: self.modificar(datos)), NON_FIELD_ERRORS), ["cambio_simultaneo"])

    def test_dos_filas_con_el_mismo_id_se_rechazan(self):
        """Un formulario armado a mano con una acción repetida no puede duplicar ni perder filas."""
        datos = datos_de(self.tipo)
        datos.acciones[1].id = datos.acciones[0].id
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(datos)), NON_FIELD_ERRORS), ["cambio_simultaneo"])

    # ---- postcondición d: auditoría ----

    def test_post_d_audita_los_cambios_del_tipo_y_cada_accion(self):
        """IOT-MOD-TAC postcondición d y «Cómo se aplica», «Auditoría»: nombre y tiempo con antes y después; las listas de acciones en ``datos``."""
        datos = datos_de(self.tipo)
        datos.nombre, datos.tiempo_minimo = "Extractor 2", "45"
        self.cambiar(datos, "Fijar velocidad", minimo="10")  # (un máximo de 120 con «%» lo rechaza D-80)
        datos.acciones = [a for a in datos.acciones if a.nombre != "Apagar"]
        datos.acciones.append(accion("Girar", "ABRIR"))
        with self.con_historial(self.encender):  # «Encender» se queda; solo cuenta el historial de las que se quitan
            self.modificar(datos)

        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        girar = self.tipo.acciones.get(nombre_accion="Girar")
        self.assertEqual((registro.usuario_id, registro.rol), (self.gerente.pk, "gerente"))
        self.assertEqual(registro.detalle["cambios"]["nombre"], {"antes": "Extractor", "despues": "Extractor 2"})
        self.assertEqual(registro.detalle["cambios"]["tiempo_minimo_entre_comandos"], {"antes": 30, "despues": 45})
        self.assertNotIn("estado", registro.detalle["cambios"])
        datos_del_registro = registro.detalle["datos"]
        self.assertEqual(datos_del_registro["acciones_creadas"], [{"id": girar.pk, "texto": "Girar"}])
        self.assertEqual(datos_del_registro["acciones_modificadas"], [{"id": self.fijar.pk, "texto": "Fijar velocidad"}])
        self.assertEqual(datos_del_registro["acciones_borradas"], [{"id": self.apagar.pk, "texto": "Apagar"}])
        self.assertNotIn("acciones_desactivadas", datos_del_registro)
        # Afectados: el tipo, la creada, la modificada y la borrada (esta, tomada antes de borrar).
        self.assertEqual(
            sorted((a["modelo"], a["id"]) for a in registro.afectados),
            sorted(
                [("iot.tipoactuador", self.tipo.pk), ("iot.accion", girar.pk), ("iot.accion", self.fijar.pk), ("iot.accion", self.apagar.pk)]
            ),
        )

    def test_post_d_una_accion_desactivada_va_a_acciones_desactivadas(self):
        """IOT-MOD-TAC postcondición d: la que quedó inactiva por su historial figura como desactivada, no como borrada."""
        datos = datos_de(self.tipo)
        datos.acciones = [a for a in datos.acciones if a.nombre != "Apagar"]
        with self.con_historial(self.apagar):
            self.modificar(datos)
        detalle = RegistroAuditoria.objects.get(accion=MODIFICACION).detalle
        self.assertEqual(detalle["datos"]["acciones_desactivadas"], [{"id": self.apagar.pk, "texto": "Apagar"}])
        self.assertNotIn("acciones_borradas", detalle["datos"])
        self.assertNotIn("cambios", detalle)

    def test_post_d_una_accion_modificada_deja_el_antes_y_el_despues_de_cada_cambio(self):
        """IOT-MOD-TAC postcondición d (reescrita) y D-36: de cada acción modificada, el antes y el después de su nombre, su comando, su
        unidad y su rango, uno por uno, con el nombre de la acción en la clave; lo que no cambió no figura."""
        datos = self.cambiar(datos_de(self.tipo), "Apagar", nombre="Parar", comando="CERRAR")
        self.cambiar(datos, "Fijar velocidad", minimo="10", maximo="90", unidad="rpm")
        self.modificar(datos)

        cambios = RegistroAuditoria.objects.get(accion=MODIFICACION).detalle["cambios"]
        self.assertEqual(cambios["Nombre de la acción «Apagar»"], {"antes": "Apagar", "despues": "Parar"})
        self.assertEqual(cambios["Comando de la acción «Apagar»"], {"antes": "APAGAR", "despues": "CERRAR"})
        self.assertEqual(cambios["Valor mínimo de la acción «Fijar velocidad»"], {"antes": 0, "despues": 10})
        self.assertEqual(cambios["Valor máximo de la acción «Fijar velocidad»"], {"antes": 100, "despues": 90})
        self.assertEqual(cambios["Unidad de la acción «Fijar velocidad»"], {"antes": "%", "despues": "rpm"})
        self.assertEqual(len(cambios), 5)  # nada de lo que no cambió (ni el tipo, ni «Encender», ni el nombre de «Fijar velocidad»)

    def test_post_d_la_pantalla_de_auditoria_muestra_los_cambios_de_las_acciones(self):
        """IOT-MOD-TAC postcondición d y D-36 («Detalle»): las filas Campo / Antes / Después y la página del registro muestran el antes y
        el después de cada cambio de cada acción modificada."""
        datos = self.cambiar(datos_de(self.tipo), "Apagar", nombre="Parar", comando="CERRAR")
        self.cambiar(datos, "Fijar velocidad", minimo="10")
        self.modificar(datos)
        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)

        filas = {campo: (antes, despues) for campo, antes, despues in registro.filas_de_cambios()}
        self.assertEqual(filas["Nombre de la acción «Apagar»"], ("Apagar", "Parar"))
        self.assertEqual(filas["Comando de la acción «Apagar»"], ("APAGAR", "CERRAR"))
        self.assertEqual(filas["Valor mínimo de la acción «Fijar velocidad»"], ("0", "10"))

        self.client.force_login(self.gerente)
        pagina = self.client.get(reverse("core:auditoria_registro", args=[registro.pk])).content.decode()
        for texto in ("Comando de la acción «Apagar»", "APAGAR", "CERRAR", "Nombre de la acción «Apagar»", "Parar", "Valor mínimo de la acción «Fijar velocidad»"):
            self.assertIn(texto, pagina)

    def test_post_d_renombrar_solo_el_tipo_no_inventa_cambios_de_acciones(self):
        """D-36: sin cambios en las acciones, el detalle no trae claves de acciones."""
        datos = datos_de(self.tipo)
        datos.nombre = "Extractor 2"
        self.modificar(datos)
        cambios = RegistroAuditoria.objects.get(accion=MODIFICACION).detalle["cambios"]
        self.assertEqual(list(cambios), ["nombre"])

    def test_post_d_una_modificacion_rechazada_no_cambia_nada_ni_audita(self):
        """D-22: una modificación que falla no deja cambios a medias ni un registro."""
        datos = datos_de(self.tipo)
        datos.nombre = "Cambio que no se guarda"
        datos.acciones = [a for a in datos.acciones if a.nombre != "Apagar"]
        with self.uso(self.apagar):
            self.errores(datos)
        self.tipo.refresh_from_db()
        self.assertEqual(self.tipo.nombre_actuador, "Extractor")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_post_d_el_registro_se_puede_leer_en_la_pantalla_de_auditoria(self):
        """D-36: los campos y las listas de acciones tienen su nombre visible (``ETIQUETAS``)."""
        datos = datos_de(self.tipo)
        datos.acciones.append(accion("Girar", "ABRIR"))
        self.modificar(datos)
        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertEqual(dict(registro.filas_de_datos())["Acciones creadas"], "Girar")

    # ---- postcondición c: compatibilidad (se completa en IOT-02) ----

    def test_post_c_la_compatibilidad_se_recalcula_sobre_los_actuadores_del_tipo(self):
        """IOT-MOD-TAC postcondición c: «Se completa en IOT-02». En IOT-01 el servicio ya hace el paso (con la lista vacía) y no falla
        aunque el tipo tenga actuadores: los deja «sin verificar»."""
        from maestros.tests.fabricas import crear_invernadero

        equipo = fabricas.actuador(fabricas.sistema(crear_invernadero("Norte")), self.tipo)
        datos = datos_de(self.tipo)
        datos.acciones.append(accion("Girar", "ABRIR"))
        self.modificar(datos)
        equipo.refresh_from_db()
        self.assertEqual(equipo.compatibilidad, "sin_verificar")


class IotModTacReactivacionServicioTests(fabricas.ConCatalogoIot, TestCase):
    """IOT-MOD-TAC, postcondición b y regla 7: reactivar un tipo dado de baja."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.tipo = fabricas.tipo_actuador("Extractor", activo=False)

    def reactivar(self, actor=None, tipo_id=None):
        """Llama al servicio sobre el tipo de la prueba."""
        return tipos.reactivar_tipo_actuador(actor or self.gerente, tipo_id or self.tipo.pk)

    def test_pre_a_solo_el_gerente_activo_reactiva(self):
        """IOT-MOD-TAC regla 1."""
        for actor in (crear_agronomo(), crear_capataz()):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                self.reactivar(actor)
        self.gerente.is_active = False
        self.gerente.save()
        with self.assertRaises(PermissionDenied):
            self.reactivar()

    def test_pre_a_un_tipo_que_no_existe_da_404(self):
        """docs/patrones/abm.md, sección 2."""
        with self.assertRaises(Http404):
            self.reactivar(tipo_id=999999)

    def test_post_b_reactiva_el_tipo_y_conserva_sus_acciones(self):
        """IOT-MOD-TAC postcondición b: el tipo queda «activo», con el nombre y las acciones que tenía."""
        acciones = list(self.tipo.acciones.values_list("id", flat=True))
        tipo = self.reactivar()
        tipo.refresh_from_db()
        self.assertEqual(tipo.estado, "activo")
        self.assertEqual(list(tipo.acciones.values_list("id", flat=True)), acciones)

    def test_regla_7_despues_de_reactivar_se_modifica_como_cualquier_otro(self):
        """IOT-MOD-TAC regla 7."""
        self.reactivar()
        datos = datos_de(self.tipo)
        datos.nombre = "Extractor nuevo"
        self.assertEqual(tipos.modificar_tipo_actuador(self.gerente, self.tipo.pk, datos).nombre_actuador, "Extractor nuevo")

    def test_regla_7_un_tipo_activo_no_se_reactiva(self):
        """IOT-MOD-TAC regla 7: «reactivar» solo vale para un tipo dado de baja."""
        TipoActuador.objects.filter(pk=self.tipo.pk).update(estado="activo")
        self.assertEqual(codigos_de(error_de(self.reactivar), NON_FIELD_ERRORS), ["tipo_no_inactivo"])

    def test_regla_2_la_unicidad_del_nombre_es_entre_todos_asi_que_reactivar_no_choca(self):
        """«Cómo se aplica», «Reactivar»: ningún otro tipo (activo o inactivo) puede tener su nombre; la base lo garantiza."""
        self.assertEqual(TipoActuador.objects.filter(nombre_actuador__iexact="Extractor").count(), 1)
        self.assertEqual(self.reactivar().estado, "activo")

    def test_post_d_la_reactivacion_se_audita_aparte_de_la_modificacion(self):
        """«Cómo se aplica», «Auditoría»: ``reactivacion_tipo_actuador`` con el cambio de estado."""
        self.reactivar()
        registro = RegistroAuditoria.objects.get(accion=REACTIVACION)
        self.assertEqual(registro.detalle["cambios"], {"estado": {"antes": "inactivo", "despues": "activo"}})
        self.assertEqual(registro.afectados, [{"modelo": "iot.tipoactuador", "id": self.tipo.pk, "texto": "Extractor"}])
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_post_d_una_reactivacion_rechazada_no_audita(self):
        """D-22."""
        TipoActuador.objects.filter(pk=self.tipo.pk).update(estado="activo")
        error_de(self.reactivar)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=REACTIVACION).exists())
