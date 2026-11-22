# Pruebas de la compatibilidad de los actuadores (docs/casos_de_uso/iot/hardware.md, «Cómo se aplica», «Compatibilidad»; regla 14 de IOT-ALT-HDW,
# regla 10 de IOT-MOD-HDW, regla 9 y postcondición c de IOT-MOD-TAC). Se escribieron ANTES que el servicio.
#
# Servicios que se prueban (iot/servicios/compatibilidad.py), tomados del módulo dentro de cada prueba:
#   calcular_compatibilidad(sistema, identificador, tipo) -> Compatibilidad(estado, acciones_incompatibles)      (solo lee; para avisar antes de guardar)
#   recalcular_compatibilidad(actuadores) -> [Actuador]            (LA ÚNICA que calcula y escribe: la usan el alta, la modificación, la reactivación,
#                                                                    IOT-MOD-TAC y la API de anuncios de IOT-03; genera o resuelve la alerta y su ``AlertaIot``)
# Sin anuncio: ``sin_verificar`` y ninguna acción incompatible. Con anuncio: ``compatible`` o ``incompatible`` según los comandos de las acciones
# ACTIVAS del tipo contra los anunciados para ese identificador (sin distinguir mayúsculas) en el sistema del actuador.

from django.test import TestCase

from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import AlertaIot
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_tecnico

compatibilidad = perezoso("iot.servicios.compatibilidad")
tipos = perezoso("iot.servicios.tipos_actuador")
TIPO_DE_ALERTA = "iot_configuracion_incompatible"


class CompatibilidadTests(fabricas.ConCatalogoIot, TestCase):
    """Un solo lugar calcula la compatibilidad y genera o resuelve su alerta."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura, tecnico=crear_tecnico("t@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte)
        self.tipo = fabricas.tipo_actuador("Extractor", acciones=[("Encender", "ENCENDER"), ("Apagar", "APAGAR"), ("Velocidad", "FIJAR_NIVEL", 0, 100, "%")])
        self.actuador = fabricas.actuador(self.sistema, self.tipo, "norte/ventilador")

    def recalcular(self, *actuadores):
        return compatibilidad.recalcular_compatibilidad(list(actuadores) or [self.actuador])

    def alertas(self):
        return Alerta.objects.filter(tipo_alerta=TIPO_DE_ALERTA)

    # ---- sin anuncio ----

    def test_regla_14_sin_anuncio_queda_sin_verificar_y_sin_acciones_incompatibles(self):
        """IOT-ALT-HDW regla 14: si el nodo no anuncia el equipo, «sin verificar» y no se restringe ninguna acción."""
        self.recalcular()
        self.actuador.refresh_from_db()
        self.assertEqual((self.actuador.compatibilidad, self.actuador.acciones_incompatibles.count()), ("sin_verificar", 0))
        self.assertFalse(self.alertas().exists())

    def test_regla_14_un_anuncio_de_otro_equipo_no_cuenta(self):
        """IOT-ALT-HDW regla 14: se compara con lo anunciado PARA ESE identificador, en el sistema del actuador (no el de otro sistema)."""
        fabricas.equipo_anunciado(self.sistema, "otro/equipo", ("ENCENDER", "APAGAR", "FIJAR_NIVEL"))
        otro = fabricas.sistema(crear_invernadero("Sur", agronomo=self.laura))
        fabricas.equipo_anunciado(otro, "norte/ventilador", ("ENCENDER",))
        self.recalcular()
        self.actuador.refresh_from_db()
        self.assertEqual(self.actuador.compatibilidad, "sin_verificar")

    # ---- con anuncio ----

    def test_regla_14_con_todos_los_comandos_anunciados_queda_compatible(self):
        """IOT-ALT-HDW regla 14: el anuncio cubre los comandos de todas las acciones activas del tipo: «compatible», sin alerta."""
        fabricas.equipo_anunciado(self.sistema, "norte/ventilador", ("ENCENDER", "APAGAR", "FIJAR_NIVEL", "ABRIR"))
        self.recalcular()
        self.actuador.refresh_from_db()
        self.assertEqual((self.actuador.compatibilidad, self.actuador.acciones_incompatibles.count()), ("compatible", 0))
        self.assertFalse(self.alertas().exists())

    def test_regla_14_con_comandos_que_faltan_queda_incompatible_con_sus_acciones_y_su_alerta(self):
        """IOT-ALT-HDW regla 14 y postcondición d de IOT-MOD-HDW: «incompatible» con las acciones que el nodo no soporta y la alerta «configuración incompatible»."""
        fabricas.equipo_anunciado(self.sistema, "norte/ventilador", ("ENCENDER", "APAGAR"))
        self.recalcular()
        self.actuador.refresh_from_db()
        self.assertEqual(self.actuador.compatibilidad, "incompatible")
        self.assertEqual([a.nombre_accion for a in self.actuador.acciones_incompatibles.all()], ["Velocidad"])
        alerta = self.alertas().get()
        self.assertEqual((alerta.clave_estado, alerta.estado_alerta, alerta.invernadero), (f"hw:{self.actuador.pk}", "activa", self.norte))

    def test_regla_14_la_alerta_se_vincula_con_su_sistema_y_su_equipo(self):
        """docs/modelo/iot.md, «AlertaIot» (D-72): crea su ``AlertaIot`` con el sistema y el equipo (R052)."""
        fabricas.equipo_anunciado(self.sistema, "norte/ventilador", ("ENCENDER",))
        self.recalcular()
        vinculo = AlertaIot.objects.get(alerta=self.alertas().get())
        self.assertEqual((vinculo.sistema, vinculo.hardware_id, vinculo.telemetria), (self.sistema, self.actuador.pk, None))

    def test_regla_14_la_comparacion_del_identificador_no_distingue_mayusculas(self):
        """IOT-ALT-HDW regla 14 y regla 2: el identificador se compara sin distinguir mayúsculas."""
        fabricas.equipo_anunciado(self.sistema, "NORTE/Ventilador", ("ENCENDER", "APAGAR", "FIJAR_NIVEL"))
        self.recalcular()
        self.actuador.refresh_from_db()
        self.assertEqual(self.actuador.compatibilidad, "compatible")

    def test_regla_14_solo_cuentan_las_acciones_activas_del_tipo(self):
        """«Cómo se aplica», «Compatibilidad»: «los comandos de las acciones ACTIVAS del tipo»: una acción inactiva no hace incompatible."""
        self.tipo.acciones.filter(nombre_accion="Velocidad").update(estado="inactiva")
        fabricas.equipo_anunciado(self.sistema, "norte/ventilador", ("ENCENDER", "APAGAR"))
        self.recalcular()
        self.actuador.refresh_from_db()
        self.assertEqual(self.actuador.compatibilidad, "compatible")

    # ---- resolver y no duplicar ----

    def test_regla_14_la_alerta_se_resuelve_cuando_vuelve_a_ser_compatible(self):
        """IOT-MOD-HDW postcondición d: «su alerta se generó o se resolvió»: al anunciar el comando que faltaba, queda compatible y la alerta, resuelta."""
        anuncio = fabricas.equipo_anunciado(self.sistema, "norte/ventilador", ("ENCENDER", "APAGAR"))
        self.recalcular()
        self.assertEqual(self.alertas().filter(estado_alerta="activa").count(), 1)
        anuncio.comandos.add(fabricas.comando_del_catalogo("FIJAR_NIVEL"))
        self.recalcular()
        self.actuador.refresh_from_db()
        self.assertEqual((self.actuador.compatibilidad, self.actuador.acciones_incompatibles.count()), ("compatible", 0))
        self.assertEqual(self.alertas().get().estado_alerta, "resuelta")

    def test_regla_14_la_alerta_se_resuelve_si_el_nodo_deja_de_anunciar_el_equipo(self):
        """Regla 14 de IOT-ALT-HDW: si el nodo no anuncia sus equipos, «sin verificar» y no se restringe nada: la alerta pasa a «resuelta»."""
        anuncio = fabricas.equipo_anunciado(self.sistema, "norte/ventilador", ("ENCENDER",))
        self.recalcular()
        anuncio.delete()
        self.recalcular()
        self.actuador.refresh_from_db()
        self.assertEqual(self.actuador.compatibilidad, "sin_verificar")
        self.assertEqual(self.alertas().get().estado_alerta, "resuelta")

    def test_regla_14_recalcular_dos_veces_no_duplica_la_alerta_ni_su_vinculo(self):
        """docs/api/alertas.md, sección 2: una activa por invernadero, tipo y clave; ``AlertaIot`` es uno por alerta."""
        fabricas.equipo_anunciado(self.sistema, "norte/ventilador", ("ENCENDER",))
        self.recalcular()
        self.recalcular()
        self.assertEqual((self.alertas().count(), AlertaIot.objects.count()), (1, 1))

    def test_regla_14_una_incompatibilidad_nueva_despues_de_resuelta_crea_otra_alerta(self):
        """docs/api/alertas.md: una alerta resuelta es historial; si vuelve la incompatibilidad se crea una nueva, con su propio vínculo."""
        anuncio = fabricas.equipo_anunciado(self.sistema, "norte/ventilador", ("ENCENDER",))
        self.recalcular()
        anuncio.comandos.set(fabricas.ComandoCatalogo.objects.filter(codigo__in=["ENCENDER", "APAGAR", "FIJAR_NIVEL"]))
        self.recalcular()
        anuncio.comandos.set(fabricas.ComandoCatalogo.objects.filter(codigo__in=["ENCENDER"]))
        self.recalcular()
        self.assertEqual(sorted(self.alertas().values_list("estado_alerta", flat=True)), ["activa", "resuelta"])
        self.assertEqual(AlertaIot.objects.count(), 2)

    # ---- quién se recalcula ----

    def test_regla_14_un_actuador_dado_de_baja_no_tiene_compatibilidad_ni_alerta(self):
        """Regla 14: la compatibilidad es de los actuadores en uso: uno dado de baja se deja como está y no genera alerta."""
        fabricas.equipo_anunciado(self.sistema, "norte/ventilador", ("ENCENDER",))
        self.actuador.estado_hardware = "inactivo"
        self.actuador.save()
        self.recalcular()
        self.actuador.refresh_from_db()
        self.assertEqual(self.actuador.compatibilidad, "sin_verificar")
        self.assertFalse(self.alertas().exists())

    def test_regla_14_recalcular_varios_actuadores_de_varios_invernaderos(self):
        """IOT-MOD-TAC postcondición c: la lista puede traer actuadores de distintos invernaderos, y cada alerta es del suyo."""
        sur = fabricas.sistema(crear_invernadero("Sur", agronomo=self.laura, tecnico=crear_tecnico("t2@infoponia.com")))
        otro = fabricas.actuador(sur, self.tipo, "sur/ventilador")
        fabricas.equipo_anunciado(self.sistema, "norte/ventilador", ("ENCENDER",))
        fabricas.equipo_anunciado(sur, "sur/ventilador", ("ENCENDER", "APAGAR", "FIJAR_NIVEL"))
        self.recalcular(otro, self.actuador)
        self.assertEqual([(a.invernadero.nombre_invernadero, a.clave_estado) for a in self.alertas()], [("Norte", f"hw:{self.actuador.pk}")])
        otro.refresh_from_db()
        self.assertEqual(otro.compatibilidad, "compatible")

    # ---- calcular sin escribir ----

    def test_regla_10_calcular_avisa_antes_de_guardar_sin_escribir_nada(self):
        """IOT-MOD-HDW regla 10: «informa el resultado antes de guardar»: ``calcular_compatibilidad`` no escribe ni genera alertas."""
        fabricas.equipo_anunciado(self.sistema, "norte/ventilador", ("ENCENDER", "APAGAR"))
        resultado = compatibilidad.calcular_compatibilidad(self.sistema, "NORTE/ventilador", self.tipo)
        self.assertEqual(resultado.estado, "incompatible")
        self.assertEqual([a.nombre_accion for a in resultado.acciones_incompatibles], ["Velocidad"])
        self.assertEqual(compatibilidad.calcular_compatibilidad(self.sistema, "no/anunciado", self.tipo).estado, "sin_verificar")
        self.actuador.refresh_from_db()
        self.assertEqual(self.actuador.compatibilidad, "sin_verificar")
        self.assertFalse(self.alertas().exists())

    # ---- IOT-MOD-TAC ----

    def test_post_c_de_mod_tac_modificar_las_acciones_de_un_tipo_recalcula_a_sus_actuadores(self):
        """IOT-MOD-TAC postcondición c y regla 9: al cambiar las acciones de un tipo se recalcula la compatibilidad de sus actuadores (no dados de baja)."""
        from iot.tests.fabricas import accion_de_formulario as accion, datos_de

        fabricas.equipo_anunciado(self.sistema, "norte/ventilador", ("ENCENDER", "APAGAR", "FIJAR_NIVEL"))
        self.recalcular()
        datos = datos_de(self.tipo)
        datos.acciones.append(accion("Abrir", "ABRIR"))
        tipos.modificar_tipo_actuador(self.gerente, self.tipo.pk, datos)
        self.actuador.refresh_from_db()
        self.assertEqual(self.actuador.compatibilidad, "incompatible")
        self.assertEqual([a.nombre_accion for a in self.actuador.acciones_incompatibles.all()], ["Abrir"])
        self.assertTrue(self.alertas().filter(estado_alerta="activa").exists())

    def test_post_c_de_mod_tac_los_actuadores_dados_de_baja_del_tipo_no_se_recalculan(self):
        """IOT-MOD-TAC regla 6: los equipos afectados son los no dados de baja."""
        from iot.tests.fabricas import accion_de_formulario as accion, datos_de

        baja = fabricas.actuador(self.sistema, self.tipo, "norte/viejo", estado="inactivo")
        fabricas.equipo_anunciado(self.sistema, "norte/viejo", ("ENCENDER",))
        datos = datos_de(self.tipo)
        datos.acciones.append(accion("Abrir", "ABRIR"))
        tipos.modificar_tipo_actuador(self.gerente, self.tipo.pk, datos)
        baja.refresh_from_db()
        self.assertEqual(baja.compatibilidad, "sin_verificar")
