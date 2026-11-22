# Pruebas de IOT-MOD-SIS · Modificar Sistema IoT, con regenerar el token (docs/casos_de_uso/iot/sistema_iot.md, v0.2, con «Cómo se
# aplica en la ronda IoT 1») y de lo que cita: D-70 (el token), D-28 (sin cambios no se audita) y D-36. Se escribieron ANTES que el servicio.
#
# Servicios que se prueban (iot/servicios/sistemas.py), tomados del módulo dentro de cada prueba:
#   modificar_sistema_iot(actor, sistema_id, datos: DatosDeSistema) -> SistemaIoT
#       Cambia el nombre, el modelo y el número de serie del nodo y el rango de la solución (regla 2 y 7); ignora el resto de ``datos``.
#   regenerar_token(actor, sistema_id) -> token
# Errores: ``PermissionDenied`` (rol), ``Http404`` (sistema inexistente), ``ValidationError`` por campo (las validaciones del registro) o
# general (``fuera_de_alcance``, ``sistema_dado_de_baja``).

import json
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from core.enlaces import resumen_de
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.tests.fabricas import perezoso
from iot.models import NodoCentral, SistemaIoT
from iot.tests import fabricas
from iot.tests.fabricas import datos_de_sistema_guardado as guardado
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_invernadero, crear_tecnico, error_de

sistemas = perezoso("iot.servicios.sistemas")
MODIFICACION = "modificacion_sistema_iot"
REGENERACION = "regeneracion_token_iot"


class IotModSisServicioTests(fabricas.ConCatalogoIot, TestCase):
    """Precondiciones, reglas y postcondiciones de IOT-MOD-SIS."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura, tecnico=crear_tecnico("t@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte, token_resumen=resumen_de("token-original"), token_generado_en=timezone.now())
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)

    def modificar(self, datos=None, sistema=None, actor=None):
        """Llama al servicio (el sistema de Norte, sin cambios y como Laura por defecto)."""
        sistema = sistema or self.sistema
        return sistemas.modificar_sistema_iot(actor or self.laura, sistema.pk, datos or guardado(sistema))

    def cambiar(self, **campos):
        """Los datos guardados con ``campos`` pisados."""
        return guardado(self.sistema, **campos)

    def codigos(self, datos, campo=None):
        return codigos_de(error_de(lambda: self.modificar(datos)), campo)

    def recargar(self):
        self.sistema.refresh_from_db()
        self.nodo.refresh_from_db()

    # ---- precondiciones y alcance (regla 1, regla 6) ----

    def test_pre_a_otros_roles_no_modifican_ni_regeneran(self):
        """IOT-MOD-SIS precondición a: cuenta activa de Agrónomo o de Gerente; los demás roles reciben 403."""
        for actor in (crear_capataz(), crear_tecnico("otro@infoponia.com"), crear_administrador()):
            with self.subTest(actor=actor.email):
                with self.assertRaises(PermissionDenied):
                    self.modificar(actor=actor)
                with self.assertRaises(PermissionDenied):
                    sistemas.regenerar_token(actor, self.sistema.pk)

    def test_pre_a_una_cuenta_inactiva_no_modifica(self):
        """IOT-MOD-SIS precondición a: «cuenta activa»."""
        self.laura.is_active = False
        self.laura.save()
        with self.assertRaises(PermissionDenied):
            self.modificar()

    def test_pre_b_un_sistema_que_no_existe_da_404(self):
        """IOT-MOD-SIS precondición b: un id que no existe da ``Http404``."""
        with self.assertRaises(Http404):
            sistemas.modificar_sistema_iot(self.laura, 999999, guardado(self.sistema))
        with self.assertRaises(Http404):
            sistemas.regenerar_token(self.laura, 999999)

    def test_pre_b_un_sistema_desconectado_se_modifica_y_se_regenera(self):
        """IOT-MOD-SIS precondición b: el sistema está «activo» o «desconectado»."""
        otro = fabricas.sistema(crear_invernadero("Otro", agronomo=self.laura), "desconectado")
        self.modificar(guardado(otro, nombre="Nuevo nombre"), otro)
        self.assertEqual(NodoCentral.objects.get(sistema=otro).nombre_nodo, "Nuevo nombre")
        self.assertTrue(sistemas.regenerar_token(self.laura, otro.pk))

    def test_regla_6_un_sistema_dado_de_baja_no_se_modifica(self):
        """IOT-MOD-SIS regla 6 (regla 2 de IOT-BAJ-SIS): un sistema dado de baja no se modifica ni se le regenera el token."""
        baja = fabricas.sistema(crear_invernadero("Viejo", agronomo=self.laura), "inactivo")
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(guardado(baja, nombre="X"), baja))), ["sistema_dado_de_baja"])
        self.assertEqual(codigos_de(error_de(lambda: sistemas.regenerar_token(self.laura, baja.pk))), ["sistema_dado_de_baja"])

    def test_regla_1_el_agronomo_de_otro_invernadero_no_modifica(self):
        """IOT-MOD-SIS regla 1 (alcance de IOT-DSC-SIS): el Agrónomo opera solo los invernaderos a su cargo."""
        otra = crear_agronomo("otra@infoponia.com")
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(actor=otra))), ["fuera_de_alcance"])
        self.assertEqual(codigos_de(error_de(lambda: sistemas.regenerar_token(otra, self.sistema.pk))), ["fuera_de_alcance"])

    def test_regla_1_el_gerente_solo_consulta_si_hay_agronomo_activo(self):
        """IOT-MOD-SIS regla 1: el Gerente opera solo donde no hay Agrónomo activo; en los demás, solo consulta."""
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(actor=self.gerente))), ["fuera_de_alcance"])
        self.assertEqual(codigos_de(error_de(lambda: sistemas.regenerar_token(self.gerente, self.sistema.pk))), ["fuera_de_alcance"])
        libre = fabricas.sistema(crear_invernadero("Libre"))
        self.modificar(guardado(libre, nombre="Del gerente"), libre, self.gerente)
        self.assertEqual(NodoCentral.objects.get(sistema=libre).nombre_nodo, "Del gerente")

    # ---- reglas 2, 5 y 7: qué cambia y qué no ----

    def test_regla_2_cambia_el_nombre_el_modelo_y_el_numero_de_serie_del_nodo(self):
        """IOT-MOD-SIS regla 2: se pueden cambiar el nombre, el modelo y el número de serie del nodo, en cualquier momento."""
        self.modificar(self.cambiar(nombre="  Nodo del fondo ", modelo="Pi 5", numero_serie="SN-9"))
        self.recargar()
        self.assertEqual((self.nodo.nombre_nodo, self.nodo.modelo_hardware, self.nodo.numero_serie), ("Nodo del fondo", "Pi 5", "SN-9"))

    def test_regla_2_el_numero_de_serie_se_puede_quitar(self):
        """IOT-MOD-SIS regla 2 y regla «Datos del nodo central»: el número de serie es opcional."""
        self.modificar(self.cambiar(numero_serie="SN-9"))
        self.modificar(self.cambiar(numero_serie=""))
        self.recargar()
        self.assertEqual(self.nodo.numero_serie, "")

    def test_regla_2_no_cambia_la_fecha_ni_el_insumo_ni_el_invernadero(self):
        """IOT-MOD-SIS regla 2: solo esos datos; la fecha de instalación, el insumo y el invernadero del formulario se ignoran."""
        fecha, insumo = self.nodo.fecha_instalacion, self.nodo.insumo
        otro = crear_invernadero("Otro", agronomo=self.laura)
        self.modificar(
            self.cambiar(
                nombre="Nuevo", fecha_instalacion="2026-01-01", insumo_id=fabricas.insumo_de_hardware().pk, invernadero_id=otro.pk
            )
        )
        self.recargar()
        self.assertEqual((self.nodo.fecha_instalacion, self.nodo.insumo, self.sistema.invernadero), (fecha, insumo, self.norte))

    def test_regla_2_las_mismas_validaciones_del_registro(self):
        """IOT-MOD-SIS regla 2 y «Cómo se aplica»: «con las mismas validaciones del registro»; todos los errores juntos."""
        error = error_de(lambda: self.modificar(self.cambiar(nombre="", modelo="x" * 61, numero_serie="s" * 61)))
        self.assertEqual(sorted(error.error_dict), ["modelo", "nombre", "numero_serie"])
        self.assertEqual(codigos_de(error, "nombre"), ["obligatorio"])
        self.assertEqual(codigos_de(error, "modelo"), ["demasiado_largo"])

    def test_regla_5_no_cambia_el_estado_del_sistema(self):
        """IOT-MOD-SIS regla 5: el estado no se cambia acá (se desactiva con IOT-DSC-SIS y se activa con IOT-ACT-SIS)."""
        desconectado = fabricas.sistema(crear_invernadero("Otro", agronomo=self.laura), "desconectado")
        self.modificar(guardado(desconectado, nombre="Nuevo"), desconectado)
        desconectado.refresh_from_db()
        self.assertEqual(desconectado.estado_sistema, "desconectado")

    def test_regla_7_define_cambia_y_quita_el_rango_de_la_solucion(self):
        """IOT-MOD-SIS regla 7: rango opcional, mínimo y máximo en °C; se define, se cambia y se quita (los dos vacíos)."""
        self.modificar(self.cambiar(temp_min="18", temp_max="24"))
        self.recargar()
        self.assertEqual((self.sistema.temp_solucion_min, self.sistema.temp_solucion_max), (Decimal("18.0"), Decimal("24.0")))
        self.modificar(self.cambiar(temp_min="16.5", temp_max="26"))
        self.recargar()
        self.assertEqual((self.sistema.temp_solucion_min, self.sistema.temp_solucion_max), (Decimal("16.5"), Decimal("26.0")))
        self.modificar(self.cambiar(temp_min="", temp_max=""))
        self.recargar()
        self.assertEqual((self.sistema.temp_solucion_min, self.sistema.temp_solucion_max), (None, None))

    def test_regla_7_el_rango_sigue_las_mismas_reglas_que_el_registro(self):
        """IOT-MOD-SIS regla 7: el mínimo menor que el máximo, los dos o ninguno, con un decimal."""
        self.assertEqual(self.codigos(self.cambiar(temp_min="24", temp_max="18"), "temp_solucion_max"), ["rango_invertido"])
        self.assertEqual(self.codigos(self.cambiar(temp_min="18", temp_max=""), "temp_solucion_max"), ["rango_incompleto"])
        self.assertEqual(self.codigos(self.cambiar(temp_min="18.55", temp_max="24"), "temp_solucion_min"), ["rango_un_decimal"])

    def test_regla_2_modificar_no_toca_el_token(self):
        """IOT-MOD-SIS: modificar el nodo no regenera ni cambia el token."""
        resumen = self.sistema.token_resumen
        self.modificar(self.cambiar(nombre="Nuevo"))
        self.recargar()
        self.assertEqual(self.sistema.token_resumen, resumen)

    # ---- postcondiciones a y c de la modificación, y D-28 ----

    def test_d28_sin_cambios_no_se_escribe_ni_se_audita(self):
        """D-28 y «Cómo se aplica» (IOT-MOD-SIS): sin cambios no se escribe ni se audita."""
        self.modificar()
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_post_c_audita_el_antes_y_el_despues_del_nodo_y_del_rango(self):
        """IOT-MOD-SIS postcondición c y «Auditoría»: ``modificacion_sistema_iot`` con el antes y el después de lo que cambió."""
        self.modificar(self.cambiar(nombre="Nodo nuevo", temp_min="18", temp_max="24"))
        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertEqual((registro.usuario_id, registro.rol), (self.laura.pk, "agronomo"))
        self.assertEqual(
            [(a["modelo"], a["id"]) for a in registro.afectados],
            [("iot.sistemaiot", self.sistema.pk), ("iot.nodocentral", self.nodo.pk)],
        )
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["nombre_nodo"], {"antes": "Nodo de prueba", "despues": "Nodo nuevo"})
        self.assertEqual(cambios["temp_solucion_min"], {"antes": None, "despues": "18.0"})
        self.assertEqual(cambios["temp_solucion_max"], {"antes": None, "despues": "24.0"})
        self.assertNotIn("modelo_hardware", cambios)  # lo que no cambió no figura

    def test_post_c_el_registro_se_puede_leer_en_la_pantalla_de_auditoria(self):
        """D-36: los campos del registro tienen su nombre visible (``ETIQUETAS``) y el Gerente lo ve."""
        self.modificar(self.cambiar(nombre="Nodo nuevo", numero_serie="SN-1", temp_min="18", temp_max="24"))
        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        filas = {campo for campo, _, _ in registro.filas_de_cambios()}
        self.assertTrue({"Nombre del nodo", "Número de serie", "Temperatura mínima de la solución (°C)"} <= filas)
        self.assertIn(registro, RegistroAuditoria.objects.visibles_para(self.gerente))

    def test_post_c_una_modificacion_rechazada_no_audita_ni_cambia_nada(self):
        """D-22: no queda un registro ni un cambio de una operación que no se hizo."""
        self.codigos(self.cambiar(nombre="Nuevo", temp_min="30", temp_max="20"))
        self.recargar()
        self.assertEqual(self.nodo.nombre_nodo, "Nodo de prueba")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    # ---- regenerar el token (postcondición b, reglas 3 y 4) ----

    def test_post_b_regenerar_devuelve_un_token_nuevo_y_guarda_solo_su_resumen(self):
        """IOT-MOD-SIS postcondición b y regla 4: token nuevo, solo su resumen en la base, ``token_generado_en`` actualizado."""
        antes = self.sistema.token_generado_en
        token = sistemas.regenerar_token(self.laura, self.sistema.pk)
        self.recargar()
        self.assertEqual(self.sistema.token_resumen, resumen_de(token))
        self.assertNotIn(token, str(self.sistema.token_resumen))
        self.assertGreater(self.sistema.token_generado_en, antes)

    def test_post_b_el_token_anterior_deja_de_servir(self):
        """IOT-MOD-SIS postcondición b y D-70: el resumen anterior ya no corresponde a ningún sistema; el nuevo, sí."""
        token = sistemas.regenerar_token(self.laura, self.sistema.pk)
        self.assertFalse(SistemaIoT.objects.filter(token_resumen=resumen_de("token-original")).exists())
        self.assertEqual(SistemaIoT.objects.get(token_resumen=resumen_de(token)), self.sistema)

    def test_post_b_dos_regeneraciones_dan_tokens_distintos(self):
        """D-70: cada token es nuevo; el primero deja de servir cuando se regenera otro."""
        uno = sistemas.regenerar_token(self.laura, self.sistema.pk)
        dos = sistemas.regenerar_token(self.laura, self.sistema.pk)
        self.assertNotEqual(uno, dos)
        self.assertFalse(SistemaIoT.objects.filter(token_resumen=resumen_de(uno)).exists())

    def test_post_b_regenerar_no_cambia_nada_mas(self):
        """IOT-MOD-SIS reglas 3 y 5: regenerar solo reemplaza el token; el estado y los datos del nodo quedan como estaban."""
        sistemas.regenerar_token(self.laura, self.sistema.pk)
        self.recargar()
        self.assertEqual(
            (self.sistema.estado_sistema, self.nodo.nombre_nodo, self.nodo.estado_hardware), ("activo", "Nodo de prueba", "activo")
        )

    def test_post_c_regenerar_audita_sin_ningun_token(self):
        """IOT-MOD-SIS postcondición c y «Auditoría»: ``regeneracion_token_iot``, sin token (ni el viejo, ni el nuevo, ni sus resúmenes)."""
        token = sistemas.regenerar_token(self.laura, self.sistema.pk)
        registro = RegistroAuditoria.objects.get(accion=REGENERACION)
        self.assertEqual(
            [(a["modelo"], a["id"]) for a in registro.afectados],
            [("iot.sistemaiot", self.sistema.pk), ("iot.nodocentral", self.nodo.pk)],
        )
        todo = json.dumps([{"d": r.detalle, "a": r.afectados} for r in RegistroAuditoria.objects.all()], ensure_ascii=False)
        for secreto in (token, "token-original", resumen_de(token), resumen_de("token-original")):
            self.assertNotIn(secreto, todo)
        self.assertIn(registro, RegistroAuditoria.objects.visibles_para(self.gerente))

    def test_post_c_regenerar_se_puede_leer_en_la_pantalla_de_auditoria(self):
        """D-36: el registro de la regeneración tiene sus datos con nombre visible."""
        sistemas.regenerar_token(self.laura, self.sistema.pk)
        registro = RegistroAuditoria.objects.get(accion=REGENERACION)
        self.assertIn("Invernadero", dict(registro.filas_de_datos()))

    def test_post_c_una_regeneracion_rechazada_no_cambia_el_token(self):
        """IOT-MOD-SIS regla 1: si el actor no opera el invernadero, el token sigue siendo el mismo y no hay registro."""
        resumen = self.sistema.token_resumen
        self.assertEqual(codigos_de(error_de(lambda: sistemas.regenerar_token(self.gerente, self.sistema.pk))), ["fuera_de_alcance"])
        self.recargar()
        self.assertEqual(self.sistema.token_resumen, resumen)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=REGENERACION).exists())
