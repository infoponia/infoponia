# Pruebas de IOT-EMT-CMD · Emitir Comando (docs/casos_de_uso/iot/emitir_comando.md, v0.2, con «Cómo se aplica en la ronda «IoT 1»») y de lo que cita: D-28 (alcance), D-36 (auditoría),
# D-78 (puntos 3, 7 y 11) y D-82 (el tipo de actuador se bloquea antes que el invernadero). Se escribieron ANTES que el servicio (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicios que se prueban (iot/servicios/comandos.py), tomados del módulo dentro de cada prueba:
#   datos_para_emitir(actor, invernadero_id, ahora, actuador_id=None) -> DatosParaEmitir        (pasos 2 y 4; ``ahora`` es un parámetro más que el extracto: lo necesitan la conectividad y 6f)
#       .invernadero .sistema .nodo .conectividad .modo .actuadores [FilaDeEmision] .elegido (FilaDeEmision | None) .acciones [Accion compatibles y activas]
#       .acciones_incompatibles [Accion] .reglas [ReglaActuacion activas del elegido] .bloqueo (texto | None: por qué no se puede emitir)
#       FilaDeEmision: .actuador .sector («General» si no tiene) .estado_texto («Desconocido») .desde .sin_confirmar .compatibilidad .comando_pendiente (Comando | None)
#   validar_comando(actuador, accion, valor) -> {campo: [ValidationError]}                        (la regla «Comando válido», una sola función; vacío si está bien)
#   resumen_de_comando(actor, actuador_id, datos, ahora) -> ResumenDeComando                     (paso 6: valida sin escribir) .actuador .accion .valor .descripcion .advertencias [Advertencia(clave, texto)]
#   emitir_comando(actor, actuador_id, datos, ahora) -> Comando                                   (paso 8)
#   DatosDeComando(accion_id, valor, descripcion)
# Advertencias (claves, en este orden): reglas (6b), mismo_estado (6c), sin_confirmar (6d), sin_senal (6e), tiempo_minimo (6f), modo_local (6g).
# Errores: ``PermissionDenied`` (otro rol), ``Http404`` (fuera del alcance de consulta o inexistente), ``ValidationError`` general (``fuera_de_alcance``, ``sistema_no_activo``,
# ``actuador_no_activo``, ``accion_no_disponible``, ``comando_pendiente``) o por campo (``accion``, ``valor``, ``descripcion``).

from datetime import datetime, timedelta, timezone as zona
from unittest import mock

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import Comando, NodoCentral, RegistroComando
from iot.tests import fabricas
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_invernadero, crear_sector, crear_tecnico, error_de

comandos = perezoso("iot.servicios.comandos")
tipos = perezoso("iot.servicios.tipos_actuador")
AHORA = datetime(2026, 11, 23, 15, 0, tzinfo=zona.utc)
ACCIONES_DEL_VENTILADOR = [("Encender", "ENCENDER"), ("Apagar", "APAGAR"), ("Fijar velocidad", "FIJAR_NIVEL", 0, 100, "%")]


class IotEmtCmdServicioTests(fabricas.ConCatalogoIot, TestCase):
    """Precondiciones, flujo, extensiones, reglas y postcondiciones de IOT-EMT-CMD."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura)
        self.sistema = fabricas.sistema(self.norte)
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        self.sector = crear_sector(self.norte, "Sector A")
        self.tipo = fabricas.tipo_actuador("Extractor", tiempo_minimo=60, acciones=ACCIONES_DEL_VENTILADOR)
        self.actuador = fabricas.actuador(self.sistema, self.tipo, "norte/ventilador", sector=self.sector, ultimo_mensaje_en=AHORA - timedelta(minutes=1))
        self.encender, self.apagar, self.velocidad = self.tipo.acciones.order_by("id")
        self.nodo_en_linea()

    # ---- ayudas ----

    def nodo_en_linea(self, segundos=30):
        """El nodo se comunicó hace ``segundos``: «en línea» (el parámetro inicial son 3 minutos)."""
        NodoCentral.objects.filter(pk=self.nodo.pk).update(ultima_comunicacion=AHORA - timedelta(seconds=segundos))

    def datos(self, accion=None, valor=None, descripcion=""):
        return comandos.DatosDeComando(accion_id=(accion or self.encender).pk, valor=valor, descripcion=descripcion)

    def emitir(self, accion=None, valor=None, descripcion="", actor=None, actuador=None):
        return comandos.emitir_comando(actor or self.laura, (actuador or self.actuador).pk, self.datos(accion, valor, descripcion), AHORA)

    def resumen(self, accion=None, valor=None, descripcion="", actor=None):
        return comandos.resumen_de_comando(actor or self.laura, self.actuador.pk, self.datos(accion, valor, descripcion), AHORA)

    def claves(self, resumen):
        return [a.clave for a in resumen.advertencias]

    def codigos_generales(self, llamada):
        return codigos_de(error_de(llamada), NON_FIELD_ERRORS)

    def sin_cambios(self):
        """Verifica que no quedó nada: ni comando, ni registro de bitácora, ni auditoría (garantía mínima: el registro es atómico)."""
        self.assertEqual(
            (Comando.objects.count(), RegistroComando.objects.count(), RegistroAuditoria.objects.filter(accion="emision_comando").count()), (0, 0, 0)
        )

    # ---- postcondiciones ----

    def test_post_a_crea_un_comando_pendiente_con_sus_datos(self):
        """IOT-EMT-CMD, postcondición a: pendiente, con fecha y hora de emisión, valor, descripción, cero intentos, sin recepción ni resultado, del actuador y la acción, del Agrónomo y de ninguna regla."""
        comando = self.emitir(self.velocidad, 60, "Antes del mediodía")
        comando.refresh_from_db()
        self.assertEqual(
            (comando.estado_comando, comando.emitido_en, comando.valor_comando, comando.descripcion_comando, comando.cantidad_intentos),
            ("pendiente", AHORA, 60, "Antes del mediodía", 0),
        )
        self.assertEqual((comando.ultimo_intento_en, comando.resuelto_en, comando.resultado_comando), (None, None, None))
        self.assertEqual((comando.actuador_id, comando.accion_id, comando.agronomo_id, comando.regla_id), (self.actuador.pk, self.velocidad.pk, self.laura.pk, None))

    def test_post_a_una_accion_sin_valor_queda_sin_valor_y_sin_descripcion(self):
        """Postcondición a: el valor es nulo si la acción no lo lleva; la descripción es opcional."""
        comando = self.emitir(self.encender)
        self.assertEqual((comando.valor_comando, comando.descripcion_comando), (None, ""))

    def test_post_b_crea_el_registro_de_bitacora_de_tipo_comando(self):
        """Postcondición b y D-78 punto 3: un RegistroComando «emitido», sin lote, con el actuador, la acción y el valor en su descripción, del Agrónomo y con el número de intento nulo."""
        comando = self.emitir(self.velocidad, 60)
        registro = RegistroComando.objects.get()
        self.assertEqual((registro.comando_id, registro.resultado, registro.numero_intento), (comando.pk, "emitido", None))
        self.assertEqual((registro.tipo_evento, registro.invernadero_id, registro.lote_id, registro.responsable_id), ("comando", self.norte.pk, None, self.laura.pk))
        for texto in ("Extractor", "norte/ventilador", "Fijar velocidad", "60 %"):
            self.assertIn(texto, registro.descripcion_evento)
        self.assertLessEqual(len(registro.descripcion_evento), 500)

    def test_post_b_la_fecha_y_la_hora_del_registro_salen_del_ahora_recibido(self):
        """Postcondición b: los servicios no leen la hora por su cuenta; el registro lleva la de ``ahora`` (hora local)."""
        self.emitir()
        registro = RegistroComando.objects.get()
        from django.utils import timezone

        local = timezone.localtime(AHORA)
        self.assertEqual((registro.fecha_bitacora, registro.hora_bitacora), (local.date(), local.time()))

    def test_post_c_audita_la_emision_con_el_usuario_el_comando_y_el_registro(self):
        """Postcondición c y D-36: acción ``emision_comando``, usuario y rol de quien emitió, y como afectados el comando y su registro de bitácora."""
        comando = self.emitir(self.velocidad, 60)
        auditoria = RegistroAuditoria.objects.get(accion="emision_comando")
        self.assertEqual(auditoria.usuario_id, self.laura.pk)
        registro = RegistroComando.objects.get()
        self.assertEqual({(a["modelo"], a["id"]) for a in auditoria.afectados}, {("iot.comando", comando.pk), ("iot.registrocomando", registro.pk)})

    def test_garantia_emitir_no_cambia_el_actuador_ni_el_sistema(self):
        """Garantías mínimas: emitir no cambia el estado del actuador, del sistema IoT ni de las reglas de actuación."""
        regla = fabricas.regla(fabricas.sensor(self.sistema), self.actuador)
        self.emitir()
        self.actuador.refresh_from_db()
        self.sistema.refresh_from_db()
        regla.refresh_from_db()
        self.assertEqual((self.actuador.estado_hardware, self.actuador.estado_informado, self.sistema.estado_sistema), ("activo", None, "activo"))
        self.assertEqual((regla.estado_regla, regla.ultima_evaluacion, regla.contador_confirmacion), ("activa", "sin_evaluar", 0))

    def test_garantia_si_falla_la_auditoria_no_queda_nada(self):
        """Garantías mínimas: el registro es atómico; si falla la auditoría no queda ni el comando ni el registro de bitácora."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                self.emitir()
        self.sin_cambios()

    # ---- alcance y actor (precondición a, regla «Alcance», extensiones 1a y 8b) ----

    def test_regla_alcance_otros_roles_reciben_403(self):
        """Precondición a: solo Agrónomo y Gerente; un Técnico o un Capataz no emiten."""
        for otro in (crear_tecnico(), crear_capataz()):
            with self.assertRaises(PermissionDenied):
                self.emitir(actor=otro)
        self.sin_cambios()

    def test_regla_alcance_un_agronomo_de_otro_invernadero_recibe_404(self):
        """D-28: un invernadero fuera del alcance de consulta no existe para quien lo pide."""
        otro = crear_agronomo("otro@infoponia.com")
        crear_invernadero("Sur", agronomo=otro)
        with self.assertRaises(Http404):
            self.emitir(actor=otro)
        self.sin_cambios()

    def test_regla_alcance_una_cuenta_inactiva_no_emite(self):
        """Precondición a: la cuenta tiene que estar activa."""
        self.laura.is_active = False
        self.laura.save()
        with self.assertRaises(PermissionDenied):
            self.emitir()

    def test_ext_1a_el_gerente_no_emite_en_un_invernadero_con_agronomo_activo(self):
        """Extensión 1a y regla «Alcance»: en los invernaderos con Agrónomo activo, el Gerente solo consulta (``fuera_de_alcance``)."""
        self.assertEqual(self.codigos_generales(lambda: self.emitir(actor=self.gerente)), ["fuera_de_alcance"])
        self.sin_cambios()

    def test_ext_1a_el_gerente_emite_en_un_invernadero_sin_agronomo(self):
        """Extensión 1a: sin Agrónomo asignado, el Gerente opera."""
        self.norte.agronomo = None
        self.norte.save()
        self.assertEqual(self.emitir(actor=self.gerente).estado_comando, "pendiente")

    def test_ext_1a_el_gerente_emite_si_el_agronomo_asignado_esta_inactivo(self):
        """Regla «Alcance»: con el Agrónomo inactivo, el Gerente opera hasta que se asigne uno."""
        self.laura.is_active = False
        self.laura.save()
        self.assertEqual(self.emitir(actor=self.gerente).estado_comando, "pendiente")

    def test_regla_quien_lo_emitio_el_comando_del_gerente_queda_sin_agronomo_y_la_persona_va_en_la_auditoria(self):
        """Regla «Quién lo emitió» (R050 en 0..1): el comando del Gerente no tiene Agrónomo; la persona real queda en el log de auditoría y el responsable de la bitácora."""
        self.norte.agronomo = None
        self.norte.save()
        comando = self.emitir(actor=self.gerente)
        self.assertIsNone(comando.agronomo_id)
        self.assertEqual(RegistroAuditoria.objects.get(accion="emision_comando").usuario_id, self.gerente.pk)
        self.assertEqual(RegistroComando.objects.get().responsable_id, self.gerente.pk)

    def test_ext_8b_el_invernadero_sale_del_alcance_antes_de_confirmar(self):
        """Extensión 8b: si el Gerente emitía por no haber Agrónomo y se asigna uno antes de confirmar, no se registra nada."""
        self.norte.agronomo = None
        self.norte.save()
        self.resumen(actor=self.gerente)
        self.norte.agronomo = self.laura
        self.norte.save()
        self.assertEqual(self.codigos_generales(lambda: self.emitir(actor=self.gerente)), ["fuera_de_alcance"])
        self.sin_cambios()

    # ---- precondición b, regla «Actuador elegible» y extensión 8b ----

    def test_regla_actuador_elegible_un_sistema_desconectado_no_recibe_comandos(self):
        """Regla «Actuador elegible» y extensión 8b: con el sistema no activo, no se registra nada."""
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save()
        self.assertEqual(self.codigos_generales(self.emitir), ["sistema_no_activo"])
        self.sin_cambios()

    def test_regla_actuador_elegible_un_actuador_fuera_de_servicio_no_recibe_comandos(self):
        """Regla «Actuador elegible»: un actuador fuera de servicio no recibe comandos."""
        self.actuador.estado_hardware = "fuera_de_servicio"
        self.actuador.save()
        self.assertEqual(self.codigos_generales(self.emitir), ["actuador_no_activo"])
        self.sin_cambios()

    def test_regla_actuador_elegible_un_actuador_dado_de_baja_no_recibe_comandos(self):
        """Regla «Actuador elegible»: un actuador dado de baja tampoco."""
        self.actuador.estado_hardware = "inactivo"
        self.actuador.save()
        self.assertEqual(self.codigos_generales(self.emitir), ["actuador_no_activo"])

    def test_ext_8b_la_accion_ya_no_esta_activa(self):
        """Extensión 8b: una acción desactivada entre el resumen y la confirmación se rechaza con su motivo, sin registrar nada."""
        self.apagar.estado = "inactiva"
        self.apagar.save()
        error = error_de(lambda: self.emitir(self.apagar))
        self.assertEqual(codigos_de(error, "accion"), ["accion_no_disponible"])
        self.sin_cambios()

    def test_ext_8b_la_accion_es_de_otro_tipo(self):
        """Regla «Comando válido»: la acción tiene que ser una de las del tipo del actuador."""
        ajena = fabricas.tipo_actuador("Aspersor").acciones.first()
        self.assertEqual(codigos_de(error_de(lambda: self.emitir(ajena)), "accion"), ["accion_no_disponible"])

    # ---- extensión 3a y 8a: un comando pendiente por actuador ----

    def test_ext_3a_un_actuador_con_comando_pendiente_no_recibe_otro(self):
        """Extensión 3a y regla «Un comando pendiente por actuador»: se rechaza con ``comando_pendiente`` y el mensaje nombra el pendiente (su código CMD-n)."""
        pendiente = fabricas.comando(self.actuador, self.encender)
        error = error_de(self.emitir)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["comando_pendiente"])
        self.assertIn(f"CMD-{pendiente.pk}", error.messages[0])
        self.assertEqual(Comando.objects.count(), 1)

    def test_ext_3a_el_resumen_tampoco_deja_seguir(self):
        """Extensión 3a: ya desde el resumen se informa el pendiente y no se permite emitir otro."""
        fabricas.comando(self.actuador, self.encender)
        self.assertEqual(self.codigos_generales(self.resumen), ["comando_pendiente"])

    def test_ext_3a_un_comando_resuelto_no_impide_emitir(self):
        """Regla «Un comando pendiente por actuador»: los resueltos no cuentan."""
        for estado in ("ejecutado", "fallido", "cancelado"):
            fabricas.comando(self.actuador, self.encender, estado=estado)
        self.assertEqual(self.emitir().estado_comando, "pendiente")

    def test_ext_8a_dos_emisiones_seguidas_la_segunda_recibe_el_pendiente_y_no_registra_nada(self):
        """Extensión 8a: la segunda emisión informa el comando pendiente y no deja comando, registro ni auditoría de más."""
        primero = self.emitir()
        self.assertEqual(self.codigos_generales(lambda: self.emitir(self.apagar)), ["comando_pendiente"])
        self.assertEqual((Comando.objects.count(), RegistroComando.objects.count(), RegistroAuditoria.objects.filter(accion="emision_comando").count()), (1, 1, 1))
        self.assertEqual(Comando.objects.get().pk, primero.pk)

    def test_ext_8a_el_indice_unico_de_la_base_se_traduce_al_mismo_error_y_no_a_un_500(self):
        """Extensión 8a: si la verificación previa no vio el pendiente (otra transacción lo confirmó en el medio), el ``IntegrityError`` del índice único se traduce al mismo error, nunca un 500."""
        fabricas.comando(self.actuador, self.encender)
        with mock.patch("iot.servicios.comandos._pendiente_de", return_value=None):
            self.assertEqual(self.codigos_generales(lambda: self.emitir(self.apagar)), ["comando_pendiente"])
        self.assertEqual((Comando.objects.count(), RegistroComando.objects.count()), (1, 0))

    # ---- regla «Comando válido» y extensión 6a ----

    def test_regla_comando_valido_una_accion_valida_no_da_errores(self):
        """Regla «Comando válido»: sin errores para una acción activa del tipo, compatible, y con el valor en el rango."""
        self.assertEqual(comandos.validar_comando(self.actuador, self.encender, None), {})
        self.assertEqual(comandos.validar_comando(self.actuador, self.velocidad, 60), {})

    def test_ext_6a_el_valor_es_obligatorio_si_la_accion_lo_lleva(self):
        """Extensión 6a: falta el valor."""
        for falta in (None, "", "  "):
            errores = comandos.validar_comando(self.actuador, self.velocidad, falta)
            self.assertEqual([e.code for e in errores["valor"]], ["valor_requerido"])

    def test_ext_6a_el_valor_tiene_que_ser_un_entero(self):
        """Extensión 6a y lista de variaciones 5a: un número entero, sin decimales ni texto."""
        for malo in ("12.5", "abc", 12.5, "1e2", True):
            errores = comandos.validar_comando(self.actuador, self.velocidad, malo)
            self.assertEqual([e.code for e in errores["valor"]], ["valor_invalido"], malo)

    def test_ext_6a_el_valor_tiene_que_estar_en_el_rango_e_informa_el_rango(self):
        """Extensión 6a: fuera del mínimo y el máximo de la acción (inclusivos), y el mensaje informa el rango con su unidad."""
        for fuera in (-1, 101, "101", "-5"):
            errores = comandos.validar_comando(self.actuador, self.velocidad, fuera)
            self.assertEqual([e.code for e in errores["valor"]], ["valor_invalido"])
            self.assertIn("entre 0 y 100 %", errores["valor"][0].message)
        for dentro in (0, 100, "0", " 100 ", 55):
            self.assertEqual(comandos.validar_comando(self.actuador, self.velocidad, dentro), {})

    def test_ext_6a_una_accion_sin_valor_no_admite_valor_de_mas(self):
        """Regla «Comando válido»: si la acción no lleva valor, el comando no lleva valor."""
        errores = comandos.validar_comando(self.actuador, self.encender, 5)
        self.assertEqual([e.code for e in errores["valor"]], ["valor_de_mas"])

    def test_ext_6a_emitir_con_un_valor_malo_no_registra_nada(self):
        """Extensión 6a: el error vuelve por campo y no se escribe nada."""
        self.assertEqual(codigos_de(error_de(lambda: self.emitir(self.velocidad, 150)), "valor"), ["valor_invalido"])
        self.assertEqual(codigos_de(error_de(lambda: self.emitir(self.velocidad)), "valor"), ["valor_requerido"])
        self.sin_cambios()

    def test_ext_6a_el_resumen_valida_antes_de_mostrarse(self):
        """Paso 6: el resumen verifica los datos (los mismos errores) y no escribe."""
        self.assertEqual(codigos_de(error_de(lambda: self.resumen(self.velocidad, 150)), "valor"), ["valor_invalido"])
        self.assertEqual(Comando.objects.count(), 0)

    def test_regla_descripcion_es_opcional_se_recorta_y_tiene_hasta_300_caracteres(self):
        """Regla «Descripción»: opcional, sin espacios al borde, hasta 300."""
        self.assertEqual(self.emitir(descripcion="  Ventilar antes del riego  ").descripcion_comando, "Ventilar antes del riego")
        Comando.objects.update(estado_comando="cancelado", resuelto_en=AHORA)  # libera al actuador (las FK son PROTECT: no se borra)
        self.assertEqual(codigos_de(error_de(lambda: self.emitir(descripcion="x" * 301)), "descripcion"), ["descripcion_larga"])
        self.assertEqual(self.emitir(descripcion="x" * 300).descripcion_comando, "x" * 300)

    def test_ext_4a_una_accion_incompatible_con_el_nodo_no_se_emite(self):
        """Extensión 4a y regla «Comando válido»: una acción marcada incompatible (el nodo no la soporta) se rechaza."""
        self.actuador.acciones_incompatibles.add(self.apagar)
        self.assertEqual(codigos_de(error_de(lambda: self.emitir(self.apagar)), "accion"), ["accion_incompatible"])
        self.assertEqual(comandos.validar_comando(self.actuador, self.apagar, None)["accion"][0].code, "accion_incompatible")
        self.sin_cambios()

    # ---- pasos 2 y 4: datos_para_emitir ----

    def test_paso_2_lista_los_actuadores_activos_con_sus_datos(self):
        """Paso 2: el nodo (conectividad y modo) y los actuadores activos del sistema con su tipo, su sector o «General», su estado informado («Desconocido» si no hay), «sin confirmar», su compatibilidad y su pendiente."""
        general = fabricas.actuador(self.sistema, self.tipo, "norte/general")  # sin sector y sin ningún mensaje
        fabricas.actuador(self.sistema, self.tipo, "norte/baja", estado="inactivo")
        fabricas.actuador(self.sistema, self.tipo, "norte/falla", estado="fuera_de_servicio")
        datos = comandos.datos_para_emitir(self.laura, self.norte.pk, AHORA)
        self.assertEqual((datos.conectividad.estado, datos.modo, datos.bloqueo), ("en_linea", "remoto", None))
        por_id = {fila.actuador.identificador_equipo: fila for fila in datos.actuadores}
        self.assertEqual(set(por_id), {"norte/ventilador", "norte/general"})
        self.assertEqual((por_id["norte/ventilador"].sector, por_id["norte/ventilador"].sin_confirmar), ("Sector A", False))
        self.assertEqual((por_id["norte/general"].sector, por_id["norte/general"].sin_confirmar, por_id["norte/general"].estado_texto), ("General", True, "Desconocido"))
        self.assertEqual(general.compatibilidad, por_id["norte/general"].compatibilidad)

    def test_paso_2_muestra_el_estado_informado_con_su_hora(self):
        """Lista de variaciones 2a: el estado tal como lo informó el nodo, con su fecha y hora."""
        self.actuador.estado_informado, self.actuador.estado_informado_en = "encendido", AHORA - timedelta(hours=1)
        self.actuador.save()
        fila = comandos.datos_para_emitir(self.laura, self.norte.pk, AHORA).actuadores[0]
        self.assertEqual((fila.estado_texto, fila.desde), ("Encendido", AHORA - timedelta(hours=1)))

    def test_paso_2_un_actuador_con_comando_pendiente_lo_trae(self):
        """Paso 2 y extensión 3a: el actuador muestra su comando pendiente."""
        pendiente = fabricas.comando(self.actuador, self.encender)
        fila = comandos.datos_para_emitir(self.laura, self.norte.pk, AHORA).actuadores[0]
        self.assertEqual(fila.comando_pendiente.pk, pendiente.pk)

    def test_paso_2_sin_sistema_activo_informa_por_que_no_se_puede_emitir(self):
        """Precondición b: sin un sistema activo no hay nada que ofrecer; ``bloqueo`` dice por qué (desconectado o sin sistema)."""
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save()
        datos = comandos.datos_para_emitir(self.laura, self.norte.pk, AHORA)
        self.assertEqual(datos.actuadores, [])
        self.assertIn("desconectado", datos.bloqueo)
        sin_sistema = crear_invernadero("Sur", agronomo=self.laura)
        self.assertIn("no tiene", comandos.datos_para_emitir(self.laura, sin_sistema.pk, AHORA).bloqueo)

    def test_paso_2_el_nodo_sin_senal_y_en_modo_local_se_informan(self):
        """Paso 2: la conectividad y el modo del nodo."""
        self.nodo_en_linea(segundos=600)
        NodoCentral.objects.filter(pk=self.nodo.pk).update(modo="local")
        datos = comandos.datos_para_emitir(self.laura, self.norte.pk, AHORA)
        self.assertEqual((datos.conectividad.estado, datos.modo), ("sin_senal", "local"))

    def test_paso_4_ofrece_solo_las_acciones_activas_y_compatibles_del_tipo(self):
        """Paso 4 y extensión 4a: las acciones activas compatibles; las incompatibles, aparte (con el aviso); las inactivas, no."""
        self.actuador.acciones_incompatibles.add(self.apagar)
        datos = comandos.datos_para_emitir(self.laura, self.norte.pk, AHORA, actuador_id=self.actuador.pk)
        self.assertEqual([a.pk for a in datos.acciones], [self.encender.pk, self.velocidad.pk])
        self.assertEqual([a.pk for a in datos.acciones_incompatibles], [self.apagar.pk])
        self.velocidad.estado = "inactiva"
        self.velocidad.save()
        datos = comandos.datos_para_emitir(self.laura, self.norte.pk, AHORA, actuador_id=self.actuador.pk)
        self.assertEqual([a.pk for a in datos.acciones], [self.encender.pk])

    def test_ext_1b_desde_la_ficha_el_actuador_ya_esta_elegido(self):
        """Extensión 1b: con ``actuador_id`` el actuador viene elegido y se ofrecen sus acciones; sin él, no hay elegido ni acciones."""
        sin = comandos.datos_para_emitir(self.laura, self.norte.pk, AHORA)
        self.assertEqual((sin.elegido, sin.acciones), (None, []))
        con = comandos.datos_para_emitir(self.laura, self.norte.pk, AHORA, actuador_id=self.actuador.pk)
        self.assertEqual(con.elegido.actuador.pk, self.actuador.pk)

    def test_ext_1b_un_actuador_de_otro_invernadero_es_404(self):
        """D-28: el actuador elegido tiene que ser del invernadero pedido."""
        sur = crear_invernadero("Sur", agronomo=self.laura)
        ajeno = fabricas.actuador(fabricas.sistema(sur), self.tipo, "sur/ventilador")
        with self.assertRaises(Http404):
            comandos.datos_para_emitir(self.laura, self.norte.pk, AHORA, actuador_id=ajeno.pk)

    def test_ext_1b_un_actuador_fuera_de_servicio_viene_elegido_con_su_motivo_y_sin_acciones(self):
        """Extensión 1b desde la ficha: si el actuador no está activo, no se ofrecen acciones y ``bloqueo`` lo explica (hay que volver a activarlo desde Hardware)."""
        self.actuador.estado_hardware = "fuera_de_servicio"
        self.actuador.save()
        datos = comandos.datos_para_emitir(self.laura, self.norte.pk, AHORA, actuador_id=self.actuador.pk)
        self.assertEqual(datos.acciones, [])
        self.assertIn("fuera de servicio", datos.bloqueo)

    def test_paso_4_trae_las_reglas_activas_del_actuador(self):
        """Paso 4: las reglas de actuación activas del actuador (vacías hasta IOT-06, que es quien las crea)."""
        sensor = fabricas.sensor(self.sistema)
        activa = fabricas.regla(sensor, self.actuador)
        fabricas.regla(sensor, self.actuador, condicion="baja_del_minimo", estado_regla="inactiva")
        datos = comandos.datos_para_emitir(self.laura, self.norte.pk, AHORA, actuador_id=self.actuador.pk)
        self.assertEqual([r.pk for r in datos.reglas], [activa.pk])

    def test_paso_2_otros_roles_y_fuera_del_alcance(self):
        """Precondición a y D-28: 403 a otros roles y 404 a un invernadero fuera del alcance de consulta."""
        with self.assertRaises(PermissionDenied):
            comandos.datos_para_emitir(crear_tecnico(), self.norte.pk, AHORA)
        with self.assertRaises(Http404):
            comandos.datos_para_emitir(crear_agronomo("otro@infoponia.com"), self.norte.pk, AHORA)

    # ---- paso 6: el resumen y sus advertencias ----

    def test_paso_6_el_resumen_trae_el_actuador_la_accion_el_valor_y_la_descripcion(self):
        """Paso 6: el resumen que se muestra antes de confirmar."""
        resumen = self.resumen(self.velocidad, "60", "Ventilar")
        self.assertEqual((resumen.actuador.pk, resumen.accion.pk, resumen.valor, resumen.descripcion), (self.actuador.pk, self.velocidad.pk, 60, "Ventilar"))
        self.assertEqual(self.claves(resumen), [])
        self.assertEqual(Comando.objects.count(), 0)

    def test_ext_6b_advierte_de_las_reglas_activas(self):
        """Extensión 6b: el comando puede contradecir las reglas activas, y una regla solo vuelve a actuar cuando su condición pasa a cumplirse."""
        sensor = fabricas.sensor(self.sistema)
        fabricas.regla(sensor, self.actuador)
        fabricas.regla(sensor, self.actuador, condicion="baja_del_minimo", estado_regla="inactiva")
        resumen = self.resumen()
        self.assertEqual(self.claves(resumen), ["reglas"])
        self.assertIn("1 regla(s) activa(s)", resumen.advertencias[0].texto)
        self.assertIn("solo vuelve a actuar cuando su condición pasa a cumplirse", resumen.advertencias[0].texto)

    def test_ext_6c_advierte_si_el_actuador_ya_esta_en_ese_estado(self):
        """Extensión 6c: «encender» un ventilador encendido, según el estado que informó el nodo."""
        self.actuador.estado_informado, self.actuador.estado_informado_en = "encendido", AHORA - timedelta(hours=1)
        self.actuador.save()
        resumen = self.resumen(self.encender)
        self.assertEqual(self.claves(resumen), ["mismo_estado"])
        self.assertIn("ya está encendido", resumen.advertencias[0].texto)
        self.assertEqual(self.claves(self.resumen(self.apagar)), [])

    def test_ext_6c_compara_tambien_los_estados_con_valor(self):
        """D-78 y «Lo que difiere del prototipo»: el sistema compara con ``ESTADO_QUE_DEJA``, también ``nivel:<n>`` y ``posicion:<n>``."""
        self.actuador.estado_informado, self.actuador.estado_informado_en = "nivel:60", AHORA
        self.actuador.save()
        self.assertEqual(self.claves(self.resumen(self.velocidad, 60)), ["mismo_estado"])
        self.assertEqual(self.claves(self.resumen(self.velocidad, 50)), [])

    def test_ext_6c_no_aplica_si_el_estado_es_desconocido(self):
        """Regla «Estado actual de un actuador»: si el nodo nunca informó el estado, es «desconocido» y 6c no se aplica."""
        self.assertIsNone(self.actuador.estado_informado)
        self.assertEqual(self.claves(self.resumen(self.encender)), [])

    def test_ext_6d_advierte_si_el_actuador_esta_sin_confirmar(self):
        """Extensión 6d: del actuador nunca llegó ningún mensaje."""
        self.actuador.ultimo_mensaje_en = None
        self.actuador.save()
        resumen = self.resumen()
        self.assertEqual(self.claves(resumen), ["sin_confirmar"])
        self.assertIn("nunca llegó ningún mensaje", resumen.advertencias[0].texto)

    def test_ext_6e_advierte_si_el_nodo_esta_sin_senal(self):
        """Extensión 6e: el comando queda pendiente, sin consumir intentos, hasta que el nodo se comunique."""
        self.nodo_en_linea(segundos=600)
        resumen = self.resumen()
        self.assertEqual(self.claves(resumen), ["sin_senal"])
        self.assertIn("sin señal", resumen.advertencias[0].texto)

    def test_ext_6e_un_nodo_que_nunca_se_comunico_esta_sin_senal(self):
        """Extensión 6e: sin ninguna comunicación, «sin señal»."""
        NodoCentral.objects.filter(pk=self.nodo.pk).update(ultima_comunicacion=None)
        self.assertEqual(self.claves(self.resumen()), ["sin_senal"])

    def test_ext_6g_advierte_si_el_nodo_esta_en_modo_local(self):
        """Extensión 6g: el comando queda pendiente hasta que el nodo vuelva a «remoto»."""
        NodoCentral.objects.filter(pk=self.nodo.pk).update(modo="local")
        resumen = self.resumen()
        self.assertEqual(self.claves(resumen), ["modo_local"])
        self.assertIn("modo local", resumen.advertencias[0].texto)

    def test_ext_6f_advierte_si_el_ultimo_ejecutado_es_mas_reciente_que_el_tiempo_minimo(self):
        """Extensión 6f: cuánto hace que cambió de estado y cuánto falta (tiempo mínimo del tipo: 60 s)."""
        fabricas.comando(self.actuador, self.apagar, estado="ejecutado", resuelto_en=AHORA - timedelta(seconds=20))
        resumen = self.resumen()
        self.assertEqual(self.claves(resumen), ["tiempo_minimo"])
        self.assertIn("hace 20 s", resumen.advertencias[0].texto)
        self.assertIn("faltan 40 s", resumen.advertencias[0].texto)
        self.assertIn("Podés emitirlo igual", resumen.advertencias[0].texto)

    def test_ext_6f_se_mide_desde_el_ultimo_comando_ejecutado_y_no_desde_otros(self):
        """D-78, punto 7: el tiempo mínimo se mide desde ``resuelto_en`` del último comando EJECUTADO; uno fallido o cancelado reciente no cuenta, y uno ejecutado hace más del mínimo, tampoco."""
        fabricas.comando(self.actuador, self.apagar, estado="fallido", resuelto_en=AHORA - timedelta(seconds=5))
        fabricas.comando(self.actuador, self.apagar, estado="cancelado", resuelto_en=AHORA - timedelta(seconds=5))
        fabricas.comando(self.actuador, self.apagar, estado="ejecutado", resuelto_en=AHORA - timedelta(seconds=120))
        self.assertEqual(self.claves(self.resumen()), [])

    def test_ext_6f_usa_el_tiempo_minimo_del_tipo(self):
        """Regla «Tiempo mínimo entre comandos»: cada tipo fija el suyo."""
        self.tipo.tiempo_minimo_entre_comandos = 300
        self.tipo.save()
        fabricas.comando(self.actuador, self.apagar, estado="ejecutado", resuelto_en=AHORA - timedelta(seconds=120))
        self.assertEqual(self.claves(self.resumen()), ["tiempo_minimo"])

    def test_regla_advertencias_no_bloquean_y_salen_en_el_orden_6b_a_6g(self):
        """Regla «Advertencias que no bloquean»: salen todas juntas, en el orden 6b, 6c, 6d, 6e, 6f, 6g, y el comando se puede emitir igual."""
        fabricas.regla(fabricas.sensor(self.sistema), self.actuador)
        self.actuador.estado_informado, self.actuador.estado_informado_en, self.actuador.ultimo_mensaje_en = "encendido", AHORA, None
        self.actuador.save()
        self.nodo_en_linea(segundos=600)
        NodoCentral.objects.filter(pk=self.nodo.pk).update(modo="local")
        fabricas.comando(self.actuador, self.apagar, estado="ejecutado", resuelto_en=AHORA - timedelta(seconds=10))
        self.assertEqual(self.claves(self.resumen(self.encender)), ["reglas", "mismo_estado", "sin_confirmar", "sin_senal", "tiempo_minimo", "modo_local"])
        self.assertEqual(self.emitir(self.encender).estado_comando, "pendiente")

    def test_regla_bitacora_todo_comando_deja_un_registro_y_las_advertencias_no_cambian_lo_que_se_registra(self):
        """Regla «Bitácora»: emitir con advertencias registra lo mismo que sin ellas."""
        NodoCentral.objects.filter(pk=self.nodo.pk).update(modo="local")
        self.emitir()
        self.assertEqual(RegistroComando.objects.filter(resultado="emitido").count(), 1)


    # ---- agregadas tras la revisión: doble de prueba de las reglas, resumen sin escritura y motivo de cada causa de 8b ----

    def test_ext_6b_con_un_doble_de_prueba_de_las_reglas_activas(self):
        """Extensión 6b: hasta IOT-06 no hay reglas; un doble que simula dos reglas activas (``_reglas_activas``) alcanza para ver la advertencia, con su cantidad."""
        falsas = [mock.Mock(pk=1), mock.Mock(pk=2)]
        with mock.patch("iot.servicios.comandos._reglas_activas", return_value=falsas):
            resumen = self.resumen()
        self.assertEqual(self.claves(resumen), ["reglas"])
        self.assertIn("2 regla(s) activa(s)", resumen.advertencias[0].texto)

    def test_regla_advertencias_el_orden_6b_a_6g_con_6b_simulada(self):
        """Regla «Advertencias que no bloquean»: el orden 6b, 6c, 6d, 6e, 6f, 6g, con la regla de 6b simulada por un doble de prueba."""
        self.actuador.estado_informado, self.actuador.estado_informado_en, self.actuador.ultimo_mensaje_en = "encendido", AHORA, None
        self.actuador.save()
        self.nodo_en_linea(segundos=600)
        NodoCentral.objects.filter(pk=self.nodo.pk).update(modo="local")
        fabricas.comando(self.actuador, self.apagar, estado="ejecutado", resuelto_en=AHORA - timedelta(seconds=10))
        with mock.patch("iot.servicios.comandos._reglas_activas", return_value=[mock.Mock(pk=1)]):
            resumen = self.resumen(self.encender)
        self.assertEqual(self.claves(resumen), ["reglas", "mismo_estado", "sin_confirmar", "sin_senal", "tiempo_minimo", "modo_local"])

    def test_paso_6_el_resumen_no_escribe_ni_comando_ni_bitacora_ni_auditoria(self):
        """Paso 6: ``resumen_de_comando`` valida sin escribir, también con todas las advertencias."""
        NodoCentral.objects.filter(pk=self.nodo.pk).update(modo="local")
        antes = (Comando.objects.count(), RegistroComando.objects.count(), RegistroAuditoria.objects.count())
        self.resumen(self.velocidad, 60, "Ventilar")
        self.assertEqual((Comando.objects.count(), RegistroComando.objects.count(), RegistroAuditoria.objects.count()), antes)

    def test_ext_8b_sistema_no_activo_informa_su_motivo_y_no_deja_registros(self):
        """Extensión 8b: el sistema IoT ya no está activo."""
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save()
        self.assertIn("desconectado", error_de(self.emitir).messages[0])
        self.sin_cambios()

    def test_ext_8b_actuador_no_activo_informa_su_motivo_y_no_deja_registros(self):
        """Extensión 8b: el actuador ya no está activo."""
        self.actuador.estado_hardware = "fuera_de_servicio"
        self.actuador.save()
        self.assertIn("fuera de servicio", error_de(self.emitir).messages[0])
        self.sin_cambios()

    def test_ext_8b_accion_desactivada_informa_su_motivo_y_no_deja_registros(self):
        """Extensión 8b: la acción ya no está activa."""
        self.apagar.estado = "inactiva"
        self.apagar.save()
        self.assertIn("ya no está disponible", error_de(lambda: self.emitir(self.apagar)).messages[0])
        self.sin_cambios()

    def test_ext_8b_accion_incompatible_informa_su_motivo_y_no_deja_registros(self):
        """Extensión 8b: la acción es incompatible con lo que anunció el nodo."""
        self.actuador.acciones_incompatibles.add(self.apagar)
        self.assertIn("no la soporta", error_de(lambda: self.emitir(self.apagar)).messages[0])
        self.sin_cambios()

    def test_ext_8b_invernadero_fuera_del_alcance_informa_su_motivo_y_no_deja_registros(self):
        """Extensión 8b: el Gerente deja de operar el invernadero porque se le asignó un Agrónomo activo."""
        self.assertIn("Agrónomo activo", error_de(lambda: self.emitir(actor=self.gerente)).messages[0])
        self.sin_cambios()


class IotEmtCmdAccionesDelTipoTests(fabricas.ConCatalogoIot, TestCase):
    """Lo que IOT-05 completa de IOT-01 (disparador «Cuando existan actuadores, comandos y reglas del IoT», punto 1): ``acciones_en_uso`` y ``acciones_con_historial`` por comandos."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.norte = crear_invernadero("Norte", agronomo=crear_agronomo("laura@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte)
        self.tipo = fabricas.tipo_actuador("Extractor", acciones=ACCIONES_DEL_VENTILADOR)
        self.actuador = fabricas.actuador(self.sistema, self.tipo, "norte/ventilador")
        self.encender, self.apagar, self.velocidad = self.tipo.acciones.order_by("id")

    def test_regla_4_de_mod_tac_un_comando_pendiente_pone_su_accion_en_uso_con_su_codigo_y_valor(self):
        """IOT-MOD-TAC regla 4: ``acciones_en_uso`` devuelve por acción sus usos (``CMD-n`` y el valor) de los comandos PENDIENTES."""
        pendiente = fabricas.comando(self.actuador, self.velocidad, valor_comando=60)
        usos = tipos.acciones_en_uso(self.tipo)
        self.assertEqual(list(usos), [self.velocidad.pk])
        self.assertEqual([(u.codigo, u.valor) for u in usos[self.velocidad.pk]], [(f"CMD-{pendiente.pk}", 60)])

    def test_regla_4_de_mod_tac_los_comandos_resueltos_no_ponen_la_accion_en_uso(self):
        """IOT-MOD-TAC regla 4: ejecutado, fallido o cancelado ya no usan la acción (solo dejan historial)."""
        for estado in ("ejecutado", "fallido", "cancelado"):
            fabricas.comando(self.actuador, self.encender, estado=estado)
        self.assertEqual(tipos.acciones_en_uso(self.tipo), {})

    def test_regla_4_de_mod_tac_no_mezcla_los_usos_de_otro_tipo(self):
        """``acciones_en_uso`` mira solo las acciones del tipo pedido."""
        otro = fabricas.tipo_actuador("Aspersor")
        fabricas.comando(fabricas.actuador(self.sistema, otro, "norte/bomba"), otro.acciones.first())
        self.assertEqual(tipos.acciones_en_uso(self.tipo), {})

    def test_regla_4_de_mod_tac_acciones_con_historial_son_las_que_tuvieron_algun_comando(self):
        """IOT-MOD-TAC regla 4: ``acciones_con_historial`` incluye las acciones con cualquier comando (pendiente o resuelto)."""
        fabricas.comando(self.actuador, self.encender, estado="ejecutado")
        fabricas.comando(self.actuador, self.apagar)
        self.assertEqual(tipos.acciones_con_historial(self.tipo), {self.encender.pk, self.apagar.pk})
        self.assertNotIn(self.velocidad.pk, tipos.acciones_con_historial(self.tipo))

    def test_regla_4_de_mod_tac_no_se_quita_una_accion_con_un_comando_pendiente(self):
        """IOT-MOD-TAC regla 4, de punta a punta: el Gerente no puede quitar una acción que usa un comando pendiente, y el error lo nombra."""
        pendiente = fabricas.comando(self.actuador, self.apagar)
        datos = fabricas.datos_de(self.tipo)
        datos.acciones = [a for a in datos.acciones if a.nombre != "Apagar"]
        error = error_de(lambda: tipos.modificar_tipo_actuador(self.gerente, self.tipo.pk, datos))
        self.assertEqual(codigos_de(error, "acciones"), ["accion_en_uso"])
        self.assertIn(f"CMD-{pendiente.pk}", error.messages[0])

    def test_regla_4_de_mod_tac_una_accion_con_historial_pero_sin_pendientes_queda_inactiva_al_quitarla(self):
        """IOT-MOD-TAC regla 8 y postcondición a: quitada una acción con comandos en su historial, queda inactiva y no se borra."""
        fabricas.comando(self.actuador, self.apagar, estado="ejecutado")
        datos = fabricas.datos_de(self.tipo)
        datos.acciones = [a for a in datos.acciones if a.nombre != "Apagar"]
        tipos.modificar_tipo_actuador(self.gerente, self.tipo.pk, datos)
        self.apagar.refresh_from_db()
        self.assertEqual(self.apagar.estado, "inactiva")
