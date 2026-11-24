# Pruebas de IOT-ENT-INF, parte de las reglas de actuación (paso 6; extensiones 1b.3, 5c, 6a, 6a.1a, 6b, 6c y 6d; postcondiciones i a l; reglas «Disparo de una regla», «Actuador ocupado» y
# «Comando automático»; docs/casos_de_uso/iot/entregar_informacion.md, «Reglas de actuación») y de D-75 (puntos 2 y 3), D-78 (puntos 8 y 9) y D-82.
# Se escribieron ANTES que el servicio (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Todo entra por donde entra en producción: ``lecturas.registrar_lectura(contexto, lectura, ahora)`` (``evaluar_reglas_de_la_lectura`` es parte de ese camino) y
# ``nodo.registrar_modo(sistema_id, modo, ahora)`` (extensión 1b.3: ``al_volver_a_remoto``). Además:
#   reglas.reiniciar_reglas(reglas) -> int                    (ya existe: IOT-ALT-RGL)
#   lecturas._motivo_de_ocupado(actuador, accion, valor, ahora) -> str | None
#       el único lugar donde se decide que el actuador de una regla está ocupado (6a.1a: comando pendiente, actuador no activo, ``validar_comando`` o tiempo mínimo); ``None`` = libre.
#       Las pruebas lo anulan con ``mock.patch`` para llegar a la red de seguridad: el índice único «un pendiente por actuador» y su ``IntegrityError``.
# Datos: umbral efectivo de «Crespa» (temperatura 18 a 24 °C, humedad 60 a 80 % HR); histéresis iniciales 1 °C, 3 % HR; 3 lecturas de confirmación; 60 s entre comandos del Ventilador.

from datetime import datetime, timedelta, timezone as zona
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso, variedad_con_semilla, variedades_presentes_de_prueba
from iot.api.traduccion import LecturaRecibida
from iot.models import Comando, NodoCentral, RegistroComando, ReglaActuacion, Telemetria, TipoActuador
from iot.tests import fabricas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

lecturas = perezoso("iot.servicios.lecturas")
nodo = perezoso("iot.servicios.nodo")
reglas = perezoso("iot.servicios.reglas")

AHORA = datetime(2026, 11, 23, 15, 0, 0, tzinfo=zona.utc)
ESPACIO = timedelta(seconds=10)  # entre una lectura y la siguiente


class IotEntInfReglasServicioTests(fabricas.ConCatalogoIot, TestCase):
    """El disparo de las reglas de actuación: la máquina de estados de D-78 (punto 8), el actuador ocupado, los reinicios y las postcondiciones i a l."""

    def setUp(self):
        cache.clear()
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura)
        self.sistema = fabricas.sistema(self.norte)
        self.temp = fabricas.sensor(self.sistema, "norte/sectorA/temperatura")
        self.hum = fabricas.sensor(self.sistema, "norte/sectorA/humedad", "humedad", valor_calibracion_min=0, valor_calibracion_max=100)
        self.tipo_ventilador = TipoActuador.objects.get(nombre_actuador="Ventilador")
        self.tipo_ventana = TipoActuador.objects.get(nombre_actuador="Ventana")
        self.ventilador = fabricas.actuador(self.sistema, self.tipo_ventilador, "norte/ventilador")
        self.ventana = fabricas.actuador(self.sistema, self.tipo_ventana, "norte/ventana")
        self.encender = self.tipo_ventilador.acciones.get(nombre_accion="Encender")
        self.apagar = self.tipo_ventilador.acciones.get(nombre_accion="Apagar")
        self.fijar = self.tipo_ventana.acciones.get(nombre_accion="Fijar posición")
        self.n = 0
        self.ahora = AHORA
        self.con_umbral()

    # ---- ayudas ----

    def con_umbral(self, *variedades):
        """Deja presentes las variedades dadas (por omisión, «Crespa»: temperatura 18 a 24, humedad 60 a 80)."""
        variedades = variedades or (variedad_con_semilla(nombre=f"Crespa {self.n}"),)
        self.enterContext(variedades_presentes_de_prueba({self.norte.pk: {v.pk for v in variedades}}))

    def lectura(self, valor, sensor=None):
        """Registra UNA lectura reciente (medida 5 s antes de ``ahora``), 10 s después de la anterior, con su propio contexto del mensaje."""
        sensor = sensor or self.temp
        self.n += 1
        self.ahora = AHORA + ESPACIO * self.n
        contexto = lecturas.contexto_del_mensaje(self.sistema, self.ahora)
        recibida = LecturaRecibida(self.n, sensor.identificador_equipo, sensor.identificador_equipo, Decimal(str(valor)), (self.ahora - timedelta(seconds=5)).isoformat())
        return lecturas.registrar_lectura(contexto, recibida, self.ahora)

    def lecturas_seguidas(self, valor, veces, sensor=None):
        for _ in range(veces):
            self.lectura(valor, sensor)

    def regla(self, condicion="supera_maximo", accion=None, sensor=None, actuador=None, **extra):
        actuador = actuador or self.ventilador
        accion = accion or (self.encender if actuador.pk == self.ventilador.pk else self.fijar)
        return fabricas.regla(sensor or self.temp, actuador, accion, condicion, **extra)

    def estado(self, regla):
        regla.refresh_from_db()
        return regla.ultima_evaluacion, regla.contador_confirmacion

    def comandos(self):
        return Comando.objects.order_by("pk")

    def resuelto_hace(self, segundos, estado="ejecutado", actuador=None):
        """Un comando ya resuelto del actuador, que se resolvió ``segundos`` antes de la PRÓXIMA lectura (la de ``self.n + 1``)."""
        proxima = AHORA + ESPACIO * (self.n + 1)
        return fabricas.comando(actuador or self.ventilador, self.encender, estado=estado, resuelto_en=proxima - timedelta(seconds=segundos), emitido_en=proxima - timedelta(minutes=10))

    # ---- extensión 6c y 6a: la confirmación y la emisión ----

    def test_ext_6c_la_condicion_se_cumple_pero_falta_confirmar_suma_uno_sin_emitir(self):
        """Extensión 6c: con 3 lecturas de confirmación, las dos primeras suman uno al contador y no emiten (la regla sigue «no cumplida»)."""
        regla = self.regla()
        self.lectura("25")
        self.assertEqual(self.estado(regla), ("no_cumplida", 1))
        self.lectura("25")
        self.assertEqual(self.estado(regla), ("no_cumplida", 2))
        self.assertEqual(self.comandos().count(), 0)

    def test_post_i_cada_lectura_actualiza_la_ultima_evaluacion_y_el_contador(self):
        """Postcondición i: la última evaluación y el contador de cada regla activa del sensor se actualizan con cada lectura; una que no cumple vuelve el contador a cero."""
        regla = self.regla()
        self.assertEqual(self.estado(regla), ("sin_evaluar", 0))
        self.lectura("21")
        self.assertEqual(self.estado(regla), ("no_cumplida", 0))
        self.lectura("25")
        self.lectura("25")
        self.assertEqual(self.estado(regla), ("no_cumplida", 2))
        self.lectura("21")
        self.assertEqual(self.estado(regla), ("no_cumplida", 0))

    def test_ext_6a_al_completar_la_confirmacion_emite_el_comando_automatico(self):
        """Extensión 6a y postcondición j: un comando «pendiente» con la fecha y hora de emisión, la acción y el valor de la regla, 0 intentos, su actuador, sin Agrónomo y asociado a la regla; la regla queda «cumplida» con el contador en 0."""
        regla = self.regla()
        self.lecturas_seguidas("25", 3)
        comando = self.comandos().get()
        self.assertEqual((comando.estado_comando, comando.actuador_id, comando.accion_id, comando.regla_id), ("pendiente", self.ventilador.pk, self.encender.pk, regla.pk))
        self.assertEqual((comando.cantidad_intentos, comando.emitido_en, comando.agronomo_id, comando.valor_comando), (0, self.ahora, None, None))
        self.assertEqual(self.estado(regla), ("cumplida", 0))

    def test_post_j_el_valor_a_aplicar_de_la_regla_pasa_al_comando(self):
        """Postcondición j: el comando lleva el valor a aplicar de la regla (una acción con valor)."""
        self.regla(actuador=self.ventana, aplicar_valor=40)
        self.lecturas_seguidas("25", 3)
        self.assertEqual(self.comandos().get().valor_comando, 40)

    def test_post_j_la_descripcion_indica_la_regla_que_lo_disparo(self):
        """Postcondición j y D-78 punto 9: «Regla {id}: cuando {sensor} {condición}, {acción}[ {valor} {unidad}].», hasta 300 caracteres."""
        regla = self.regla(actuador=self.ventana, aplicar_valor=40)
        self.lecturas_seguidas("25", 3)
        descripcion = self.comandos().get().descripcion_comando
        self.assertTrue(descripcion.startswith(f"Regla {regla.pk}: cuando "), descripcion)
        for parte in ("norte/sectorA/temperatura", "supera el máximo del umbral efectivo", "Fijar posición 40 %"):
            self.assertIn(parte, descripcion)
        self.assertTrue(descripcion.endswith("."))
        self.assertLessEqual(len(descripcion), 300)

    def test_post_k_la_lectura_que_completo_la_confirmacion_queda_asociada_a_la_regla(self):
        """Postcondición k (R062): la última lectura, la que completó la confirmación, queda en ``regla.telemetrias`` (y por eso no la borra la retención)."""
        regla = self.regla()
        self.lecturas_seguidas("25", 3)
        self.assertEqual([t.pk for t in regla.telemetrias.all()], [Telemetria.objects.order_by("-medida_en").first().pk])

    def test_post_l_crea_el_registro_de_bitacora_del_comando_sin_responsable(self):
        """Postcondición l y D-78 punto 3: un ``RegistroComando`` «emitido», de tipo «comando», sin lote y sin responsable (lo emitió InfoPonia), con el actuador y la acción."""
        self.regla()
        self.lecturas_seguidas("25", 3)
        registro = RegistroComando.objects.get()
        self.assertEqual((registro.comando_id, registro.resultado, registro.numero_intento, registro.responsable_id), (self.comandos().get().pk, "emitido", None, None))
        self.assertEqual((registro.tipo_evento, registro.invernadero_id, registro.lote_id), ("comando", self.norte.pk, None))
        for texto in ("Ventilador", "norte/ventilador", "Encender"):
            self.assertIn(texto, registro.descripcion_evento)

    def test_post_z_la_auditoria_de_la_lectura_suma_el_comando_y_su_registro(self):
        """Postcondición z: ``entrega_informacion_iot`` suma el comando y el registro de bitácora creados, con actor ``None`` (InfoPonia)."""
        self.regla()
        self.lecturas_seguidas("25", 3)
        auditoria = RegistroAuditoria.objects.filter(accion="entrega_informacion_iot").latest("pk")
        afectados = {(a["modelo"], a["id"]) for a in auditoria.afectados}
        self.assertIn(("iot.comando", self.comandos().get().pk), afectados)
        self.assertIn(("iot.registrocomando", RegistroComando.objects.get().pk), afectados)
        self.assertIsNone(auditoria.usuario_id)

    def test_garantia_si_falla_el_registro_de_bitacora_no_queda_ni_la_lectura_ni_el_comando(self):
        """Garantías mínimas: la lectura, sus comandos y su bitácora se registran juntos o no se registra ninguno."""
        regla = self.regla()
        self.lecturas_seguidas("25", 2)
        with mock.patch("iot.servicios.comandos.registrar_hecho", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                self.lectura("25")
        self.assertEqual((self.comandos().count(), Telemetria.objects.count()), (0, 2))
        self.assertEqual(self.estado(regla), ("no_cumplida", 2))

    # ---- extensión 6b: no repite ----

    def test_ext_6b_no_repite_el_comando_mientras_la_condicion_sigue_cumpliendose(self):
        """Extensión 6b: con la regla «cumplida» y la lectura todavía fuera, no se emite otro comando (aunque el anterior ya se haya resuelto)."""
        regla = self.regla()
        self.lecturas_seguidas("25", 3)
        Comando.objects.update(estado_comando="ejecutado", resuelto_en=self.ahora - timedelta(minutes=5))
        self.lecturas_seguidas("26", 5)
        self.assertEqual(self.comandos().count(), 1)
        self.assertEqual(self.estado(regla), ("cumplida", 0))

    # ---- las tres condiciones, con su histéresis y su borde (D-78, punto 8) ----

    def test_regla_supera_maximo_se_cumple_con_mas_que_el_maximo_no_con_el_maximo(self):
        """«Supera el máximo» (máximo 24): 24,00 no cuenta; 24,01 sí."""
        regla = self.regla()
        self.lecturas_seguidas("24.00", 3)
        self.assertEqual((self.estado(regla), self.comandos().count()), (("no_cumplida", 0), 0))
        self.lecturas_seguidas("24.01", 3)
        self.assertEqual(self.comandos().count(), 1)

    def test_regla_supera_maximo_sigue_cumplida_hasta_bajar_del_maximo_menos_la_histeresis(self):
        """«Supera el máximo» cumplida: sigue cumplida con 23,00 (máximo − 1 °C, el borde) y deja de cumplirse con 22,99, con el contador en 0."""
        regla = self.regla()
        self.lecturas_seguidas("25", 3)
        self.lectura("23.00")
        self.assertEqual(self.estado(regla), ("cumplida", 0))
        self.lectura("22.99")
        self.assertEqual(self.estado(regla), ("no_cumplida", 0))

    def test_regla_baja_del_minimo_es_simetrica_con_su_histeresis(self):
        """«Baja del mínimo» (mínimo 18): 18,00 no cuenta, 17,99 sí; cumplida, sigue con 19,00 (mínimo + 1 °C) y deja de cumplirse con 19,01."""
        regla = self.regla("baja_del_minimo")
        self.lecturas_seguidas("18.00", 3)
        self.assertEqual(self.comandos().count(), 0)
        self.lecturas_seguidas("17.99", 3)
        self.assertEqual(self.comandos().count(), 1)
        self.lectura("19.00")
        self.assertEqual(self.estado(regla), ("cumplida", 0))
        self.lectura("19.01")
        self.assertEqual(self.estado(regla), ("no_cumplida", 0))

    def test_regla_vuelve_al_rango_se_cumple_solo_a_mas_de_la_histeresis_de_cada_limite(self):
        """«Vuelve a quedar dentro» desde «no cumplida»: se cumple con valores de 19,00 a 23,00 (mínimo + h a máximo − h); 23,01 y 18,99 no cuentan."""
        regla = self.regla("vuelve_al_rango", self.apagar)
        self.lecturas_seguidas("23.01", 3)
        self.lecturas_seguidas("18.99", 3)
        self.assertEqual(self.comandos().count(), 0)
        self.lectura("19.00")
        self.lectura("23.00")
        self.assertEqual(self.estado(regla), ("no_cumplida", 2))
        self.lectura("21")
        self.assertEqual(self.comandos().get().accion_id, self.apagar.pk)

    def test_regla_vuelve_al_rango_cumplida_sigue_mientras_el_valor_este_entre_el_minimo_y_el_maximo(self):
        """«Vuelve a quedar dentro» cumplida: sigue con 24,00 y con 18,00 (los límites) y deja de cumplirse con 24,01 o 17,99."""
        regla = self.regla("vuelve_al_rango", self.apagar)
        self.lecturas_seguidas("21", 3)
        for valor in ("24.00", "18.00"):
            self.lectura(valor)
            self.assertEqual(self.estado(regla), ("cumplida", 0), valor)
        self.lectura("24.01")
        self.assertEqual(self.estado(regla), ("no_cumplida", 0))

    def test_regla_vuelve_al_rango_desde_sin_evaluar_dispara_al_confirmarse(self):
        """D-78, punto 8: «sin evaluar» cuenta como «no cumplida»: con la lectura dentro del umbral, la regla dispara y deja el actuador en el estado de la regla."""
        regla = self.regla("vuelve_al_rango", self.apagar)
        self.assertEqual(self.estado(regla), ("sin_evaluar", 0))
        self.lecturas_seguidas("21", 3)
        self.assertEqual(self.comandos().count(), 1)

    def test_regla_una_lectura_que_no_cumple_vuelve_el_contador_a_cero(self):
        """«Disparo de una regla»: la confirmación es de lecturas SEGUIDAS; una que no cumple vuelve el contador a cero."""
        self.regla()
        self.lecturas_seguidas("25", 2)
        self.lectura("21")
        self.lecturas_seguidas("25", 2)
        self.assertEqual(self.comandos().count(), 0)
        self.lectura("25")
        self.assertEqual(self.comandos().count(), 1)

    def test_regla_las_lecturas_de_confirmacion_salen_de_la_configuracion_operativa(self):
        """«Disparo de una regla»: la cantidad de lecturas de confirmación es la de la Configuración Operativa (aquí 2)."""
        from maestros.servicios import configuracion

        configuracion.obtener().__class__.objects.update(cant_lecturas_confirmacion=2)
        cache.clear()
        self.regla()
        self.lecturas_seguidas("25", 2)
        self.assertEqual(self.comandos().count(), 1)

    def test_d75_2_con_un_umbral_angosto_la_histeresis_es_la_mitad_del_ancho(self):
        """D-75, punto 2 (la misma histéresis que las alertas): con un umbral de 23 a 24, h = min(1; 0,5) = 0,5: cumplida, «supera el máximo» sigue con 23,50 y deja de cumplirse con 23,49."""
        self.con_umbral(variedad_con_semilla(nombre="Crespa angosta"), variedad_con_semilla(nombre="Lisa", temp_ambiente_min="23", temp_ambiente_max="30"))
        regla = self.regla()
        self.lecturas_seguidas("25", 3)
        self.lectura("23.50")
        self.assertEqual(self.estado(regla), ("cumplida", 0))
        self.lectura("23.49")
        self.assertEqual(self.estado(regla), ("no_cumplida", 0))

    # ---- extensión 6a.1a: el actuador ocupado ----

    def test_ext_6a_1a_con_un_comando_pendiente_no_emite_y_vuelve_a_intentar_con_la_lectura_siguiente(self):
        """Extensión 6a.1a y D-78 punto 8: con un pendiente en el actuador la regla no emite; queda «no cumplida» con el contador EN la confirmación; con la lectura siguiente, sin esperar otra confirmación, emite."""
        regla = self.regla()
        manual = fabricas.comando(self.ventilador, self.apagar)
        self.lecturas_seguidas("25", 3)
        self.assertEqual((self.estado(regla), self.comandos().count()), (("no_cumplida", 3), 1))
        Comando.objects.filter(pk=manual.pk).update(estado_comando="cancelado", resuelto_en=self.ahora)
        self.lectura("25")
        self.assertEqual(self.comandos().count(), 2)
        self.assertEqual(self.comandos().last().regla_id, regla.pk)
        self.assertEqual(self.estado(regla), ("cumplida", 0))

    def test_ext_6a_1a_nunca_hay_dos_pendientes_por_actuador(self):
        """Garantía: ningún actuador queda con dos comandos pendientes, por más lecturas que lleguen."""
        self.regla()
        self.lecturas_seguidas("25", 8)
        self.assertEqual(self.comandos().filter(estado_comando="pendiente").count(), 1)

    def test_ext_6a_1a_con_el_actuador_fuera_de_servicio_no_emite(self):
        """Extensión 6a.1a: el actuador no está activo."""
        regla = self.regla()
        type(self.ventilador).objects.filter(pk=self.ventilador.pk).update(estado_hardware="fuera_de_servicio")
        self.lecturas_seguidas("25", 4)
        self.assertEqual((self.estado(regla), self.comandos().count()), (("no_cumplida", 3), 0))
        type(self.ventilador).objects.filter(pk=self.ventilador.pk).update(estado_hardware="activo")
        self.lectura("25")
        self.assertEqual(self.comandos().count(), 1)

    def test_ext_6a_1a_con_la_accion_incompatible_con_el_nodo_no_emite(self):
        """Extensión 6a.1a: la acción es incompatible con el nodo (``validar_comando``)."""
        regla = self.regla()
        self.ventilador.acciones_incompatibles.add(self.encender)
        self.lecturas_seguidas("25", 4)
        self.assertEqual((self.estado(regla), self.comandos().count()), (("no_cumplida", 3), 0))

    def test_ext_6a_1a_si_la_accion_dejo_de_ser_valida_la_regla_queda_ocupada(self):
        """Extensión 6a.1a y «Comando válido»: una acción inactiva, o un valor fuera del rango, no se emite (``validar_comando``); la regla queda ocupada y no hay 500."""
        regla = self.regla()
        self.encender.estado = "inactiva"
        self.encender.save()
        self.lecturas_seguidas("25", 4)
        self.assertEqual((self.estado(regla), self.comandos().count()), (("no_cumplida", 3), 0))
        valor = self.regla(actuador=self.ventana, aplicar_valor=500, sensor=self.hum)
        self.lecturas_seguidas("90", 4, sensor=self.hum)
        self.assertEqual((self.estado(valor), self.comandos().count()), (("no_cumplida", 3), 0))

    def test_ext_6a_1a_no_emite_si_no_paso_el_tiempo_minimo_desde_el_ultimo_comando_ejecutado(self):
        """Extensión 6a.1a, D-78 punto 7: se mide desde ``resuelto_en`` del último comando EJECUTADO; con 60 s mínimos, 59 s no alcanzan y 60 s sí (el borde)."""
        regla = self.regla()
        self.lecturas_seguidas("25", 2)
        self.resuelto_hace(59)
        self.lectura("25")
        self.assertEqual((self.estado(regla), self.comandos().filter(regla=regla).count()), (("no_cumplida", 3), 0))
        Comando.objects.update(resuelto_en=AHORA + ESPACIO * (self.n + 1) - timedelta(seconds=60))
        self.lectura("25")
        self.assertEqual(self.comandos().filter(regla=regla).count(), 1)

    def test_ext_6a_1a_un_comando_fallido_o_cancelado_no_cuenta_para_el_tiempo_minimo(self):
        """D-78 punto 7: solo el último comando EJECUTADO cuenta, no el último emitido, fallido ni cancelado."""
        regla = self.regla()
        self.lecturas_seguidas("25", 2)
        self.resuelto_hace(5, estado="fallido")
        self.resuelto_hace(5, estado="cancelado")
        self.lectura("25")
        self.assertEqual(self.comandos().filter(regla=regla).count(), 1)

    def test_ext_6a_1a_si_la_base_rechaza_el_pendiente_la_regla_queda_ocupada_y_no_hay_500(self):
        """Red de seguridad: si otra regla o una persona emitió a la vez y el chequeo no lo vio, el índice único de la base lo rechaza; el ``IntegrityError`` se toma en un ``atomic`` anidado, la lectura se guarda y la regla queda ocupada."""
        regla = self.regla()
        fabricas.comando(self.ventilador, self.apagar)  # el pendiente que el chequeo «no ve»
        self.lecturas_seguidas("25", 2)
        with mock.patch("iot.servicios.lecturas._motivo_de_ocupado", return_value=None):
            resultado = self.lectura("25")
        self.assertEqual(resultado.resultado, "aceptada")
        self.assertEqual((self.estado(regla), self.comandos().count(), Telemetria.objects.count()), (("no_cumplida", 3), 1, 3))
        self.assertEqual(RegistroComando.objects.count(), 0)

    def test_regla_actuador_ocupado_dos_reglas_sobre_el_mismo_actuador_una_emite_y_la_otra_espera(self):
        """«Actuador ocupado»: una regla de la temperatura emite y, cuando la de la humedad confirma sobre el mismo actuador, queda ocupada (no emite un segundo pendiente) y espera."""
        por_temperatura = self.regla()
        por_humedad = self.regla(sensor=self.hum)
        self.lecturas_seguidas("25", 3)
        self.lecturas_seguidas("85", 3, sensor=self.hum)
        self.assertEqual([c.regla_id for c in self.comandos()], [por_temperatura.pk])
        self.assertEqual(self.estado(por_humedad), ("no_cumplida", 3))

    def test_regla_dos_reglas_de_un_sensor_sobre_actuadores_distintos_emiten_las_dos(self):
        """Cada regla es independiente: dos reglas del mismo sensor que confirman con la misma lectura emiten cada una a su actuador (en orden de id)."""
        primera = self.regla()
        segunda = self.regla(actuador=self.ventana, aplicar_valor=100)
        self.lecturas_seguidas("25", 3)
        self.assertEqual([c.regla_id for c in self.comandos()], [primera.pk, segunda.pk])

    def test_regla_una_regla_inactiva_no_se_evalua(self):
        """Una regla dada de baja no se evalúa: ni contador, ni comandos."""
        regla = self.regla(estado_regla="inactiva")
        self.lecturas_seguidas("25", 4)
        self.assertEqual((self.estado(regla), self.comandos().count()), (("sin_evaluar", 0), 0))

    # ---- extensión 6d y reglas de cuándo no se evalúa ----

    def test_ext_6d_en_modo_local_no_se_evaluan_las_reglas_pero_la_lectura_se_guarda(self):
        """Extensión 6d: con el nodo en «local», la última evaluación y el contador no cambian y no se emite nada; la lectura sí se registra."""
        regla = self.regla()
        self.lecturas_seguidas("25", 2)
        NodoCentral.objects.filter(sistema=self.sistema).update(modo="local")
        resultado = self.lectura("25")
        self.assertEqual((resultado.resultado, Telemetria.objects.count()), ("aceptada", 3))
        self.assertEqual((self.estado(regla), self.comandos().count()), (("no_cumplida", 2), 0))

    def test_regla_una_lectura_atrasada_invalida_o_de_un_sensor_fuera_de_servicio_no_evalua_reglas(self):
        """Reglas «Cuándo no se evalúa una lectura» y garantía: atrasada, inválida o de un sensor fuera de servicio no tocan las reglas."""
        regla = self.regla()
        self.lecturas_seguidas("25", 2)
        self.lectura("99")  # fuera de la calibración: inválida
        self.assertEqual(self.estado(regla), ("no_cumplida", 2))
        contexto = lecturas.contexto_del_mensaje(self.sistema, self.ahora + ESPACIO)
        vieja = LecturaRecibida(99, "norte/sectorA/temperatura", "norte/sectorA/temperatura", Decimal("25"), (self.ahora - timedelta(minutes=30)).isoformat())
        lecturas.registrar_lectura(contexto, vieja, self.ahora + ESPACIO)
        self.assertEqual(self.estado(regla), ("no_cumplida", 2))
        type(self.temp).objects.filter(pk=self.temp.pk).update(estado_hardware="fuera_de_servicio")
        self.lectura("25")
        self.assertEqual((self.estado(regla), self.comandos().count()), (("no_cumplida", 2), 0))

    # ---- reinicios ----

    def test_reiniciar_reglas_deja_sin_evaluar_con_el_contador_en_cero(self):
        """``reiniciar_reglas``: «sin evaluar» y contador 0 en las reglas dadas (instancias o ids), y nada más."""
        cumplida, a_medias, otra = self.regla(), self.regla("baja_del_minimo"), self.regla(sensor=self.hum)
        ReglaActuacion.objects.filter(pk=cumplida.pk).update(ultima_evaluacion="cumplida")
        ReglaActuacion.objects.filter(pk=a_medias.pk).update(ultima_evaluacion="no_cumplida", contador_confirmacion=2)
        ReglaActuacion.objects.filter(pk=otra.pk).update(ultima_evaluacion="cumplida")
        self.assertEqual(reglas.reiniciar_reglas([cumplida, a_medias.pk]), 2)
        self.assertEqual((self.estado(cumplida), self.estado(a_medias), self.estado(otra)), (("sin_evaluar", 0), ("sin_evaluar", 0), ("cumplida", 0)))

    def test_ext_1b_3_al_volver_a_remoto_se_reinician_todas_las_reglas_activas_del_sistema(self):
        """Extensión 1b.3: al volver de «local» a «remoto», las reglas ACTIVAS de todos los sensores del sistema vuelven a «sin evaluar» con el contador en 0 (una dada de baja no se toca); la confirmación empieza de cero."""
        por_temperatura, por_humedad = self.regla(), self.regla(sensor=self.hum, actuador=self.ventana, aplicar_valor=10)
        inactiva = self.regla("baja_del_minimo", estado_regla="inactiva")
        ReglaActuacion.objects.filter(pk=por_temperatura.pk).update(ultima_evaluacion="cumplida")
        ReglaActuacion.objects.filter(pk=por_humedad.pk).update(ultima_evaluacion="no_cumplida", contador_confirmacion=2)
        ReglaActuacion.objects.filter(pk=inactiva.pk).update(ultima_evaluacion="cumplida")
        NodoCentral.objects.filter(sistema=self.sistema).update(modo="local")
        self.assertTrue(nodo.registrar_modo(self.sistema.pk, "remoto", self.ahora))
        self.assertEqual((self.estado(por_temperatura), self.estado(por_humedad), self.estado(inactiva)), (("sin_evaluar", 0), ("sin_evaluar", 0), ("cumplida", 0)))
        self.lecturas_seguidas("25", 2)
        self.assertEqual(self.comandos().count(), 0)
        self.lectura("25")
        self.assertEqual(self.comandos().count(), 1)

    def test_ext_1b_3_pasar_a_local_no_reinicia_nada(self):
        """Extensión 1b.2 y 6d: al pasar a «local» las reglas conservan su evaluación y su contador."""
        regla = self.regla()
        self.lecturas_seguidas("25", 2)
        nodo.registrar_modo(self.sistema.pk, "local", self.ahora)
        self.assertEqual(self.estado(regla), ("no_cumplida", 2))

    def test_ext_5c_sin_umbral_efectivo_reinicia_las_reglas_activas_del_sensor(self):
        """Extensión 5c: cuando el invernadero se queda sin umbral, la última evaluación de las reglas del sensor pasa a «sin evaluar» y su contador, a cero; las de otro sensor no se tocan."""
        cumplida, a_medias = self.regla(), self.regla("baja_del_minimo")
        de_la_humedad = self.regla(sensor=self.hum)
        ReglaActuacion.objects.filter(pk=cumplida.pk).update(ultima_evaluacion="cumplida")
        ReglaActuacion.objects.filter(pk=a_medias.pk).update(ultima_evaluacion="no_cumplida", contador_confirmacion=2)
        ReglaActuacion.objects.filter(pk=de_la_humedad.pk).update(ultima_evaluacion="cumplida")
        self.enterContext(variedades_presentes_de_prueba())  # ya no hay variedades presentes
        self.lectura("25")
        self.assertEqual((self.estado(cumplida), self.estado(a_medias), self.estado(de_la_humedad)), (("sin_evaluar", 0), ("sin_evaluar", 0), ("cumplida", 0)))
        self.assertEqual(self.comandos().count(), 0)

    def test_d75_3_con_la_variable_del_umbral_vacia_se_reinician_las_reglas_y_no_disparan_con_una_sola_lectura(self):
        """D-75, punto 3 (decisión del estudiante del 23/11/2026; hueco de «Reglas de actuación», que solo nombra el caso «sin umbral»): con las variedades presentes sin superposición en la temperatura, la
        variable «no se compara, igual que en 5c»: una regla «cumplida» y otra con el contador en 2 de 3 quedan «sin evaluar» con el contador en 0. Cuando la variable vuelve a tener rango, ninguna dispara con una sola lectura."""
        cumplida, a_medias = self.regla(), self.regla("baja_del_minimo")
        ReglaActuacion.objects.filter(pk=cumplida.pk).update(ultima_evaluacion="cumplida")
        ReglaActuacion.objects.filter(pk=a_medias.pk).update(ultima_evaluacion="no_cumplida", contador_confirmacion=2)
        self.con_umbral(
            variedad_con_semilla(nombre="Crespa baja", temp_ambiente_min="18", temp_ambiente_max="20"),
            variedad_con_semilla(nombre="Lisa alta", temp_ambiente_min="22", temp_ambiente_max="24"),
        )
        self.lectura("30")
        self.assertEqual((self.estado(cumplida), self.estado(a_medias)), (("sin_evaluar", 0), ("sin_evaluar", 0)))
        self.con_umbral()  # la temperatura vuelve a tener rango (18 a 24)
        self.lectura("30")
        self.assertEqual((self.estado(cumplida), self.estado(a_medias)), (("no_cumplida", 1), ("no_cumplida", 0)))
        self.lectura("10")
        self.assertEqual((self.estado(cumplida), self.estado(a_medias)), (("no_cumplida", 0), ("no_cumplida", 1)))
        self.assertEqual(self.comandos().count(), 0)
