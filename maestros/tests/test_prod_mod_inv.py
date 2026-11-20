# Pruebas de PROD-MOD-INV · Modificar Invernadero, con su reactivación (docs/casos_de_uso/maestros/invernaderos.md) y de lo
# que cita: regla 5 de PROD-BAJ-INV (se reactiva con PROD-MOD-INV), D-22 (auditoría en la misma transacción), D-28 (sin
# cambios no se audita), D-30 (ninguna acción lleva a un 403), D-36 (formato del detalle), D-37 (puntos de extensión) y
# D-38 (alertas). Modelo de dominio: ronda 22 (docs/modelo/maestros.md).
#
# Servicios que se prueban (maestros/servicios/invernaderos.py), tomados del módulo dentro de cada prueba:
#   modificar_invernadero(actor, invernadero_id, nombre, *, tipo_direccion, localidad_id, calle="", numero_calle="",
#                         piso="", departamento_unidad="", barrio="", referencias="", ruta="", kilometro="",
#                         lote_rural="", agronomo_id=None, capataz_id=None, vendedor_id=None, tecnico_id=None,
#                         personal_confirmado=False) -> Invernadero
#     Se envía el formulario completo: un rol sin id queda sin asignar. Todo después de ``nombre`` es solo por nombre.
#     - Precondición a: actor no es un Gerente activo -> PermissionDenied. Un id inexistente -> Http404.
#     - Errores por campo (ValidationError) como el alta; regla 5 -> error general, código ``invernadero_inactivo``.
#     - Regla 2: un cambio de personal sin ``personal_confirmado`` lanza FaltaConfirmarPersonal(aviso) y no guarda nada.
#       ``aviso`` es una lista con un dict por rol que cambia: rol, nombre_rol, saliente, entrante, recibe (lista de
#       (descripcion, cantidad) que sale de maestros.extensiones.contar_traspaso) y queda_vacio.
#   reactivar_invernadero(actor, invernadero_id) -> Invernadero; uno ya activo -> código ``invernadero_activo``.
#   acciones_permitidas(actor, invernadero) -> conjunto de {"modificar", "baja", "reactivar"}.
# Puntos de extensión que se prueban con registrantes falsos (maestros/extensiones.py): ``_TRASPASOS`` es una lista de
# pares (contar, traspasar); ``contar(invernadero, rol, saliente, entrante)`` y
# ``traspasar(actor, invernadero, rol, saliente, entrante)``; ``rol`` es el atributo ("capataz"); saliente y entrante
# son instancias de la clase del rol (Capataz, no Usuario) o None.
#
# Las postcondiciones b (alerta del rol), d y e (alertas) las conectó MAE-02a (D-41) y la c (notificaciones a quien queda a
# cargo), NOT-01 (D-42): sus pruebas son las ``test_post_c_…`` de ``ProdModInvServicioTests``.

import inspect
import json
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.test import TestCase, TransactionTestCase, tag
from django.urls import reverse

from core.models import Agronomo, Capataz, Notificacion, RegistroAuditoria, referencia
from core.servicios import baja_usuario
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import afectado, crear_administrador, crear_capataz, crear_gerente
from maestros import extensiones
from maestros.alertas import Destinatario
from maestros.models import Alerta, Departamento, Direccion, DireccionRural, DireccionUrbana, Invernadero, Provincia
from maestros.servicios import invernaderos
from maestros.tests.fabricas import (
    ConGeoref,
    crear_agronomo,
    crear_alerta,
    crear_capataz_activo,
    crear_invernadero,
    crear_invernadero_con_geografia_propia,
    crear_tecnico,
    crear_vendedor,
    localidad,
    tipo_de_alerta_de_prueba,
    tipo_falso,
)

MODIFICACION = RegistroAuditoria.Accion.MODIFICACION_INVERNADERO
REACTIVACION = RegistroAuditoria.Accion.REACTIVACION_INVERNADERO


class FallaDePrueba(Exception):
    """Falla propia de las pruebas: no es un ``RuntimeError``, para que un ``NotImplementedError`` (que sí lo es)
    no haga pasar por casualidad una prueba que espera que algo falle."""


def errores_de(llamada):
    """Ejecuta ``llamada`` y devuelve el diccionario de errores de la ``ValidationError`` que lanza; si no la
    lanza, la prueba falla."""
    try:
        llamada()
    except ValidationError as error:
        return error.message_dict
    raise AssertionError("Se esperaba una ValidationError y no se lanzó.")


def codigos_de(llamada):
    """Ejecuta ``llamada`` y devuelve los códigos de la ``ValidationError`` que lanza."""
    try:
        llamada()
    except ValidationError as error:
        return codigos(error)
    raise AssertionError("Se esperaba una ValidationError y no se lanzó.")


def datos_de(invernadero):
    """Los argumentos de ``modificar_invernadero`` (sin actor ni id) que dejan al invernadero exactamente como está."""
    invernadero = Invernadero.objects.get(pk=invernadero.pk)
    hija = invernadero.direccion.concreta()
    datos = {
        "nombre": invernadero.nombre_invernadero,
        "localidad_id": invernadero.direccion.localidad_id,
        **{f"{atributo}_id": getattr(invernadero, f"{atributo}_id") for atributo, _ in Invernadero.ROLES},
    }
    if isinstance(hija, DireccionUrbana):
        datos |= {
            "tipo_direccion": "urbana",
            "calle": hija.calle,
            "numero_calle": hija.numero_calle,
            "piso": hija.piso,
            "departamento_unidad": hija.departamento,
            "barrio": hija.barrio,
            "referencias": hija.referencias,
        }
    else:
        datos |= {"tipo_direccion": "rural", "ruta": hija.ruta, "kilometro": hija.kilometro, "lote_rural": hija.lote}
    return datos


class RegistranteDeTraspaso:
    """Registrante falso del punto de extensión de traspaso: anota cada llamada y cuenta lo que se le indique."""

    def __init__(self, recibe=None):
        self.recibe = recibe if recibe is not None else []
        self.traspasos = []
        self.contados = []
        self.vio = []

    def contar(self, invernadero, rol, saliente, entrante):
        self.contados.append((rol, saliente, entrante))
        return list(self.recibe)

    def traspasar(self, actor, invernadero, rol, saliente, entrante):
        self.traspasos.append((actor, invernadero, rol, saliente, entrante))
        # Lo que el invernadero tiene en la base en este momento (ajuste c: el UPDATE va antes de los traspasos).
        guardado = Invernadero.objects.get(pk=invernadero.pk)
        self.vio.append((guardado.nombre_invernadero, guardado.direccion_id, getattr(guardado, f"{rol}_id")))

    def patch(self):
        """Reemplaza la lista de registrantes por este y nada más."""
        return mock.patch.object(extensiones, "_TRASPASOS", [(self.contar, self.traspasar)])


class ProdModInvServicioTests(ConGeoref, TestCase):
    """Servicio ``modificar_invernadero`` (PROD-MOD-INV): precondiciones, reglas 1 a 5 y 7 y postcondiciones a, b y f."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.capataz = crear_capataz_activo()
        self.invernadero = crear_invernadero("Invernadero A", agronomo=self.agronomo, capataz=self.capataz)

    def mod(self, invernadero=None, actor=None, **cambios):
        """Modifica el invernadero con lo que ya tiene más ``cambios``."""
        invernadero = invernadero or self.invernadero
        datos = datos_de(invernadero) | cambios
        return invernaderos.modificar_invernadero(actor or self.gerente, invernadero.pk, **datos)

    def recargado(self):
        return Invernadero.objects.get(pk=self.invernadero.pk)

    # ---- Firma ----

    def test_firma_todo_despues_de_actor_id_y_nombre_es_solo_por_nombre(self):
        """Firma de ``modificar_invernadero`` (D-39, decisión «Firma» del alta): solo ``actor``, ``invernadero_id`` y
        ``nombre`` son posicionales; el resto, solo por nombre."""
        parametros = inspect.signature(invernaderos.modificar_invernadero).parameters.values()
        posicionales = [p.name for p in parametros if p.kind is not inspect.Parameter.KEYWORD_ONLY]
        self.assertEqual(posicionales, ["actor", "invernadero_id", "nombre"])

    def test_firma_un_cuarto_argumento_posicional_se_rechaza(self):
        """Firma de ``modificar_invernadero`` (D-39, decisión «Firma» del alta): pasar el tipo de dirección por
        posición es un ``TypeError``."""
        with self.assertRaises(TypeError):
            invernaderos.modificar_invernadero(self.gerente, self.invernadero.pk, "Otro", "urbana")

    # ---- Precondiciones ----

    def test_pre_a_un_gerente_activo_modifica(self):
        """PROD-MOD-INV, precondición a: el Gerente activo puede modificar."""
        self.assertEqual(self.mod(nombre="Invernadero Norte").nombre_invernadero, "Invernadero Norte")

    def test_pre_a_otro_rol_no_modifica(self):
        """PROD-MOD-INV, precondición a: un Agrónomo, un Capataz o un Administrador reciben PermissionDenied."""
        for actor in (self.agronomo, crear_capataz(), crear_administrador()):
            with self.subTest(actor=actor.email), self.assertRaises(PermissionDenied):
                self.mod(actor=actor, nombre="Otro nombre")
        self.assertEqual(self.recargado().nombre_invernadero, "Invernadero A")

    def test_pre_a_un_gerente_inactivo_no_modifica(self):
        """PROD-MOD-INV, precondición a: «con una cuenta activa de Gerente»."""
        self.gerente.is_active = False
        self.gerente.save()
        with self.assertRaises(PermissionDenied):
            self.mod(nombre="Otro nombre")

    def test_pre_a_sin_actor_no_modifica(self):
        """PROD-MOD-INV, precondición a: sin cuenta que actúe, PermissionDenied."""
        with self.assertRaises(PermissionDenied):
            invernaderos.modificar_invernadero(None, self.invernadero.pk, **datos_de(self.invernadero))

    def test_pre_a_un_invernadero_inexistente_da_404(self):
        """PROD-MOD-INV y D-28: un id que no existe es Http404."""
        with self.assertRaises(Http404):
            invernaderos.modificar_invernadero(self.gerente, 0, **datos_de(self.invernadero))

    def test_pre_b_el_nombre_de_otro_invernadero_se_rechaza(self):
        """PROD-MOD-INV, precondición b: si cambia el nombre, no existe otro invernadero con el nombre nuevo."""
        crear_invernadero("Invernadero Sur")
        errores = errores_de(lambda: self.mod(nombre="Invernadero Sur"))
        self.assertIn("nombre", errores)
        self.assertEqual(self.recargado().nombre_invernadero, "Invernadero A")

    # ---- Reglas ----

    def test_regla_1_el_nombre_ajeno_no_distingue_mayusculas_ni_espacios(self):
        """PROD-MOD-INV, regla 1 y regla 1 de PROD-ALT-INV: «invernadero sur » choca con «Invernadero Sur»."""
        crear_invernadero("Invernadero Sur")
        self.assertIn("nombre", errores_de(lambda: self.mod(nombre="  invernadero SUR ")))

    def test_regla_1_el_nombre_propio_en_otras_mayusculas_se_acepta(self):
        """PROD-MOD-INV, regla 1: el propio nombre no cuenta como repetido; se puede corregir su escritura."""
        self.assertEqual(self.mod(nombre="INVERNADERO A").nombre_invernadero, "INVERNADERO A")

    def test_regla_1_el_nombre_es_unico_tambien_entre_inactivos(self):
        """PROD-MOD-INV, regla 1: el nombre de un invernadero inactivo también cuenta."""
        crear_invernadero("Viejo", activo=False)
        self.assertIn("nombre", errores_de(lambda: self.mod(nombre="viejo")))

    def test_regla_1_nombre_obligatorio_y_con_contenido(self):
        """PROD-MOD-INV, regla 1: el nombre es obligatorio y tiene al menos una letra o un número."""
        self.assertIn("nombre", errores_de(lambda: self.mod(nombre="   ")))
        self.assertIn("nombre", errores_de(lambda: self.mod(nombre="-----")))

    def test_regla_1_el_nombre_se_guarda_sin_espacios_en_los_extremos(self):
        """PROD-MOD-INV, regla 1: se guarda recortado."""
        self.assertEqual(self.mod(nombre="  Norte  ").nombre_invernadero, "Norte")

    def test_regla_1_el_nombre_no_pasa_de_80_caracteres(self):
        """PROD-MOD-INV, regla 1 y D-39: un nombre largo es un error de campo, no un error de la base."""
        self.assertIn("nombre", errores_de(lambda: self.mod(nombre="N" * 81)))

    def test_regla_1_la_direccion_sigue_las_reglas_2_y_3_de_alta(self):
        """PROD-MOD-INV, regla 1 -> reglas 2 y 3 de PROD-ALT-INV: obligatorios, formato, contenido, largo y localidad."""
        casos = [
            ({"calle": ""}, "calle"),
            ({"numero_calle": ""}, "numero_calle"),
            ({"numero_calle": "casa"}, "numero_calle"),
            ({"calle": "-----"}, "calle"),
            ({"barrio": "***"}, "barrio"),
            ({"calle": "C" * 101}, "calle"),
            ({"tipo_direccion": "otra"}, "tipo_direccion"),
            ({"localidad_id": None}, "localidad"),
            ({"localidad_id": 0}, "localidad"),
        ]
        for cambios, campo in casos:
            with self.subTest(cambios=cambios):
                self.assertIn(campo, errores_de(lambda: self.mod(**cambios)))
        self.assertEqual(self.recargado().direccion.concreta().calle, "Calle 122")

    def test_regla_1_una_rural_exige_ruta_y_kilometro_con_formato(self):
        """PROD-MOD-INV, regla 1 -> regla 2 de PROD-ALT-INV: ruta y kilómetro obligatorios; el kilómetro, con formato."""
        rural = {"tipo_direccion": "rural", "ruta": "RN 14", "kilometro": "4,5", "lote_rural": ""}
        self.assertEqual(self.mod(**rural).direccion.concreta().kilometro, "4,5")
        for cambios, campo in (({"ruta": ""}, "ruta"), ({"kilometro": ""}, "kilometro"), ({"kilometro": "4.5"}, "kilometro")):
            with self.subTest(cambios=cambios):
                self.assertIn(campo, errores_de(lambda: self.mod(**(rural | cambios))))

    def test_regla_4_se_ofrecen_solo_cuentas_activas_del_rol(self):
        """PROD-MOD-INV, regla 4: una cuenta inactiva, o de otro rol, no se puede asignar."""
        inactivo = crear_vendedor(activo=False)
        self.assertIn("vendedor", errores_de(lambda: self.mod(vendedor_id=inactivo.pk, personal_confirmado=True)))
        self.assertIn("agronomo", errores_de(lambda: self.mod(agronomo_id=self.capataz.pk, personal_confirmado=True)))
        self.assertIn("tecnico", errores_de(lambda: self.mod(tecnico_id=0, personal_confirmado=True)))
        self.assertEqual(self.recargado().vendedor, None)

    def test_regla_4_una_cuenta_de_otro_rol_se_rechaza(self):
        """PROD-MOD-INV, regla 4 («se ofrecen solo las cuentas activas de cada rol»): el id de un Vendedor activo en
        ``capataz_id`` se rechaza con ``persona_invalida`` en ese campo y no guarda nada."""
        vendedor = crear_vendedor()
        with self.assertRaises(ValidationError) as contexto:
            self.mod(capataz_id=vendedor.pk, nombre="Invernadero Norte", personal_confirmado=True)
        errores = contexto.exception.error_dict
        self.assertEqual(list(errores), ["capataz"])
        self.assertEqual([e.code for e in errores["capataz"]], ["persona_invalida"])
        invernadero = self.recargado()
        self.assertEqual((invernadero.nombre_invernadero, invernadero.capataz_id), ("Invernadero A", self.capataz.pk))
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_4_la_persona_asignada_que_quedo_inactiva_se_conserva_sin_confirmar(self):
        """PROD-MOD-INV, regla 4: «se muestra con esa marca hasta que se la reemplace»; guardar sin tocarla no es un
        cambio de personal ni falla."""
        self.capataz.is_active = False
        self.capataz.save()
        modificado = self.mod(nombre="Invernadero Norte")
        self.assertEqual(modificado.capataz_id, self.capataz.pk)

    def test_regla_4_reemplazar_a_la_persona_inactiva_por_otra_inactiva_se_rechaza(self):
        """PROD-MOD-INV, regla 4: solo se puede cambiar por una cuenta activa."""
        self.capataz.is_active = False
        self.capataz.save()
        otro = crear_capataz_activo("otro.capataz@infoponia.com", activo=False)
        self.assertIn("capataz", errores_de(lambda: self.mod(capataz_id=otro.pk, personal_confirmado=True)))

    def test_regla_2_un_cambio_de_personal_sin_confirmar_no_guarda_y_avisa(self):
        """PROD-MOD-INV, regla 2: antes de confirmar un cambio de personal se informa qué pasa al guardar; el
        servicio lanza FaltaConfirmarPersonal y no cambia nada."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        with RegistranteDeTraspaso().patch(), self.assertRaises(invernaderos.FaltaConfirmarPersonal):
            self.mod(nombre="Invernadero Norte", capataz_id=nuevo.pk)
        self.assertEqual(self.recargado().nombre_invernadero, "Invernadero A")
        self.assertEqual(self.recargado().capataz_id, self.capataz.pk)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_regla_2_el_aviso_dice_quien_sale_quien_entra_y_lo_que_recibe(self):
        """PROD-MOD-INV, regla 2: el aviso trae, por rol que cambia, el saliente, el entrante y lo que recibiría el
        entrante (lo cuentan los registrantes del punto de extensión)."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        registrante = RegistranteDeTraspaso(recibe=[("órdenes a realizar", 3)])
        with registrante.patch(), self.assertRaises(invernaderos.FaltaConfirmarPersonal) as contexto:
            self.mod(capataz_id=nuevo.pk)
        (entrada,) = contexto.exception.aviso
        self.assertEqual(entrada["rol"], "capataz")
        self.assertEqual(entrada["nombre_rol"], "Capataz")
        self.assertEqual(entrada["saliente"], self.capataz)
        self.assertEqual(entrada["entrante"], nuevo)
        self.assertEqual(entrada["recibe"], [("órdenes a realizar", 3)])
        self.assertFalse(entrada["queda_vacio"])
        self.assertEqual(registrante.contados, [("capataz", self.capataz, nuevo)])

    def test_regla_2_el_aviso_dice_que_un_rol_queda_vacio(self):
        """PROD-MOD-INV, regla 2: «si un rol queda vacío, que no se podrán realizar las tareas que dependen de él hasta
        que se asigne a alguien»."""
        with RegistranteDeTraspaso().patch(), self.assertRaises(invernaderos.FaltaConfirmarPersonal) as contexto:
            self.mod(agronomo_id=None)
        (entrada,) = contexto.exception.aviso
        self.assertEqual((entrada["rol"], entrada["entrante"], entrada["saliente"]), ("agronomo", None, self.agronomo))
        self.assertTrue(entrada["queda_vacio"])

    def test_regla_2_asignar_a_un_rol_vacio_tambien_pide_confirmar(self):
        """PROD-MOD-INV, regla 2 y regla 3: lo que quedó sin responsable pasa a quien se asigne; es un cambio de
        personal y se confirma."""
        vendedor = crear_vendedor()
        with RegistranteDeTraspaso().patch(), self.assertRaises(invernaderos.FaltaConfirmarPersonal) as contexto:
            self.mod(vendedor_id=vendedor.pk)
        (entrada,) = contexto.exception.aviso
        self.assertEqual((entrada["rol"], entrada["saliente"], entrada["entrante"]), ("vendedor", None, vendedor))

    def test_regla_2_el_aviso_trae_una_entrada_por_rol_que_cambia(self):
        """PROD-MOD-INV, regla 2: solo los roles que cambian, en el orden de ``Invernadero.ROLES``."""
        vendedor, tecnico = crear_vendedor(), crear_tecnico()
        with RegistranteDeTraspaso().patch(), self.assertRaises(invernaderos.FaltaConfirmarPersonal) as contexto:
            self.mod(tecnico_id=tecnico.pk, vendedor_id=vendedor.pk)
        self.assertEqual([e["rol"] for e in contexto.exception.aviso], ["vendedor", "tecnico"])

    def test_regla_2_sin_cambio_de_personal_no_pide_confirmar(self):
        """PROD-MOD-INV, regla 2: cambiar solo el nombre o la dirección no es un cambio de personal."""
        registrante = RegistranteDeTraspaso()
        with registrante.patch():
            self.mod(nombre="Invernadero Norte", calle="Otra calle")
        self.assertEqual(registrante.contados, [])

    def test_regla_2_confirmado_guarda_el_cambio_de_personal(self):
        """PROD-MOD-INV, regla 2 y postcondición a: con ``personal_confirmado=True`` NO se lanza FaltaConfirmarPersonal
        y se guarda el cambio (también la auditoría)."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        try:
            with RegistranteDeTraspaso().patch():
                modificado = self.mod(capataz_id=nuevo.pk, personal_confirmado=True)
        except invernaderos.FaltaConfirmarPersonal:
            self.fail("Con personal_confirmado=True no debe pedir confirmación.")
        self.assertEqual(modificado.capataz_id, nuevo.pk)
        self.assertEqual(self.recargado().capataz_id, nuevo.pk)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=MODIFICACION).count(), 1)

    def test_regla_2_los_errores_de_validacion_van_antes_que_el_aviso(self):
        """PROD-MOD-INV, regla 2: con un dato inválido y un cambio de personal, se informa el error de campo."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        with RegistranteDeTraspaso().patch():
            self.assertIn("nombre", errores_de(lambda: self.mod(nombre="", capataz_id=nuevo.pk)))

    def test_regla_3_quitar_a_una_persona_sin_reemplazarla_deja_lo_suyo_sin_responsable(self):
        """PROD-MOD-INV, regla 3: se quita a una persona sin reemplazarla; el punto de extensión recibe el traspaso hacia
        nadie (``entrante`` None), y el invernadero queda sin esa persona."""
        registrante = RegistranteDeTraspaso()
        with registrante.patch():
            modificado = self.mod(capataz_id=None, personal_confirmado=True)
        self.assertIsNone(modificado.capataz_id)
        self.assertEqual(registrante.traspasos, [(self.gerente, modificado, "capataz", self.capataz, None)])

    def test_regla_3_asignar_a_un_rol_vacio_recibe_lo_que_quedo_sin_responsable(self):
        """PROD-MOD-INV, regla 3: al asignar a alguien en un rol vacío, el traspaso va de nadie (``saliente`` None)
        a la persona entrante."""
        vendedor = crear_vendedor()
        registrante = RegistranteDeTraspaso()
        with registrante.patch():
            modificado = self.mod(vendedor_id=vendedor.pk, personal_confirmado=True)
        self.assertEqual(registrante.traspasos, [(self.gerente, modificado, "vendedor", None, vendedor)])

    def test_regla_5_un_invernadero_inactivo_no_se_modifica(self):
        """PROD-MOD-INV, regla 5: «solo se reactiva»; modificarlo se rechaza con ``invernadero_inactivo``."""
        inactivo = crear_invernadero("Viejo", activo=False)
        self.assertEqual(codigos_de(lambda: self.mod(inactivo, nombre="Nuevo nombre")), ["invernadero_inactivo"])
        self.assertEqual(Invernadero.objects.get(pk=inactivo.pk).nombre_invernadero, "Viejo")
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_7_no_recibe_nada_del_sistema_iot(self):
        """PROD-MOD-INV, regla 7: el sistema IoT no se modifica acá; la firma no tiene ningún parámetro de IoT."""
        nombres = inspect.signature(invernaderos.modificar_invernadero).parameters
        self.assertFalse([n for n in nombres if "iot" in n.lower()])

    # ---- Postcondición a ----

    def test_post_a_actualiza_el_nombre(self):
        """PROD-MOD-INV, postcondición a: se actualizó el nombre indicado."""
        self.mod(nombre="Invernadero Norte")
        self.assertEqual(self.recargado().nombre_invernadero, "Invernadero Norte")

    def test_post_a_actualiza_la_direccion_del_mismo_tipo_en_el_lugar(self):
        """PROD-MOD-INV, postcondición a: con el mismo tipo, la dirección se actualiza y conserva su identidad."""
        antes = self.invernadero.direccion_id
        nueva = localidad("Campo Viera", "Oberá")
        self.mod(calle="Av. Libertad", numero_calle="12 bis", piso="2", localidad_id=nueva.pk)
        invernadero = self.recargado()
        hija = invernadero.direccion.concreta()
        self.assertEqual(invernadero.direccion_id, antes)
        self.assertEqual((hija.calle, hija.numero_calle, hija.piso), ("Av. Libertad", "12 bis", "2"))
        self.assertEqual(invernadero.direccion.localidad, nueva)

    def test_post_a_de_urbana_a_rural_crea_una_direccion_nueva_y_borra_la_anterior(self):
        """PROD-MOD-INV, postcondición a y D-39 (opción A): al cambiar el tipo se crea la dirección nueva, se apunta el
        invernadero a ella y se borra la anterior (nada más la referencia: Cliente y CompraVenta no existen)."""
        antes = self.invernadero.direccion_id
        self.mod(tipo_direccion="rural", ruta="Ruta Nacional 12", kilometro="1024", lote_rural="Lote 3")
        invernadero = self.recargado()
        self.assertNotEqual(invernadero.direccion_id, antes)
        self.assertIsInstance(invernadero.direccion.concreta(), DireccionRural)
        self.assertEqual(invernadero.direccion.concreta().ruta, "Ruta Nacional 12")
        self.assertFalse(Direccion.objects.filter(pk=antes).exists())
        self.assertFalse(DireccionUrbana.objects.exists())

    def test_post_a_de_rural_a_urbana_tambien(self):
        """PROD-MOD-INV, postcondición a: el cambio inverso (rural a urbana) hace lo mismo."""
        rural = crear_invernadero("Rural", tipo="rural")
        antes = rural.direccion_id
        self.mod(rural, tipo_direccion="urbana", calle="Av. Mitre", numero_calle="S/N")
        recargado = Invernadero.objects.get(pk=rural.pk)
        self.assertIsInstance(recargado.direccion.concreta(), DireccionUrbana)
        self.assertFalse(Direccion.objects.filter(pk=antes).exists())
        self.assertFalse(DireccionRural.objects.exists())

    def test_post_a_al_cambiar_el_tipo_no_queda_ninguna_direccion_huerfana(self):
        """PROD-MOD-INV, postcondición a y D-39 (opción A): al cambiar el tipo, en cualquiera de los dos sentidos, la
        cantidad de filas de ``Direccion`` (la padre) no cambia —una nace y una se borra— y toda dirección que queda
        es la de un invernadero."""
        rural = crear_invernadero("Rural", tipo="rural")
        casos = [
            (self.invernadero, {"tipo_direccion": "rural", "ruta": "RN 12", "kilometro": "9"}),
            (rural, {"tipo_direccion": "urbana", "calle": "Av. Mitre", "numero_calle": "S/N"}),
        ]
        for invernadero, cambios in casos:
            with self.subTest(a=cambios["tipo_direccion"]):
                antes = Direccion.objects.count()
                self.mod(invernadero, **cambios)
                self.assertEqual(Direccion.objects.count(), antes)
                self.assertEqual(
                    Direccion.objects.count(), DireccionUrbana.objects.count() + DireccionRural.objects.count()
                )
                self.assertFalse(Direccion.objects.filter(invernadero__isnull=True).exists())

    def test_post_a_cambiar_solo_la_localidad_conserva_el_tipo_y_los_datos_de_la_direccion(self):
        """PROD-MOD-INV, postcondición a y regla 3 de PROD-ALT-INV: con el mismo tipo, cambiar solo la localidad deja la
        dirección en su lugar (misma fila) con los demás datos intactos."""
        antes = self.invernadero.direccion_id
        nueva = localidad("Campo Viera", "Oberá")
        self.mod(localidad_id=nueva.pk)
        invernadero = self.recargado()
        hija = invernadero.direccion.concreta()
        self.assertEqual(invernadero.direccion_id, antes)
        self.assertEqual(invernadero.direccion.localidad, nueva)
        self.assertEqual((hija.calle, hija.numero_calle), ("Calle 122", "3310"))
        self.assertEqual(Direccion.objects.count(), 1)

    def test_post_a_ignora_los_datos_del_otro_tipo(self):
        """PROD-MOD-INV, postcondición a y regla 2 de PROD-ALT-INV: al cambiar a rural no se guarda nada de la urbana."""
        self.mod(tipo_direccion="rural", ruta="RN 12", kilometro="9", calle="Se ignora", numero_calle="1")
        self.assertEqual(self.recargado().direccion.concreta().ruta, "RN 12")
        self.assertFalse(DireccionUrbana.objects.exists())

    def test_post_a_actualiza_el_personal(self):
        """PROD-MOD-INV, postcondición a: asigna, reemplaza y quita personal en un mismo guardado."""
        vendedor, otro_agronomo = crear_vendedor(), crear_agronomo("otro.agronomo@infoponia.com")
        with RegistranteDeTraspaso().patch():
            self.mod(vendedor_id=vendedor.pk, agronomo_id=otro_agronomo.pk, capataz_id=None, personal_confirmado=True)
        invernadero = self.recargado()
        self.assertEqual(
            (invernadero.agronomo_id, invernadero.capataz_id, invernadero.vendedor_id),
            (otro_agronomo.pk, None, vendedor.pk),
        )

    def test_post_a_una_misma_cuenta_puede_estar_a_cargo_de_varios_invernaderos(self):
        """PROD-MOD-INV y regla 4 de PROD-ALT-INV: una misma cuenta puede estar a cargo de varios invernaderos."""
        otro = crear_invernadero("Otro")
        with RegistranteDeTraspaso().patch():
            self.mod(otro, agronomo_id=self.agronomo.pk, personal_confirmado=True)
        self.assertEqual(Invernadero.objects.filter(agronomo=self.agronomo).count(), 2)

    # ---- Postcondición b: traspaso (punto de extensión) ----

    def test_post_b_traspasa_solo_los_roles_que_cambiaron(self):
        """PROD-MOD-INV, postcondición b y MD-60: se llama a ``traspasar`` una vez por rol que cambió, con el actor, el
        invernadero, el rol, el saliente y el entrante."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        registrante = RegistranteDeTraspaso()
        with registrante.patch():
            modificado = self.mod(capataz_id=nuevo.pk, personal_confirmado=True)
        self.assertEqual(registrante.traspasos, [(self.gerente, modificado, "capataz", self.capataz, nuevo)])

    def test_post_b_solo_cambiar_el_nombre_no_traspasa_nada(self):
        """PROD-MOD-INV, postcondición b: sin cambio de personal no hay traspaso."""
        registrante = RegistranteDeTraspaso()
        with registrante.patch():
            self.mod(nombre="Invernadero Norte")
        self.assertEqual(registrante.traspasos, [])

    def test_post_b_el_traspaso_corre_despues_de_guardar_el_invernadero(self):
        """Ajuste c del plan: el UPDATE del invernadero (nombre, dirección y personal) se hace ANTES de llamar a los
        registrantes, para que ninguna transacción que lo haga esperar pueda estar esperando filas de las apps altas
        que esta ya tenga. El registrante ve en la base los datos nuevos."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        registrante = RegistranteDeTraspaso()
        with registrante.patch():
            modificado = self.mod(
                nombre="Invernadero Norte",
                tipo_direccion="rural",
                ruta="RN 12",
                kilometro="9",
                capataz_id=nuevo.pk,
                personal_confirmado=True,
            )
        self.assertEqual(registrante.vio, [("Invernadero Norte", modificado.direccion_id, nuevo.pk)])

    def test_post_b_si_el_traspaso_falla_no_queda_nada(self):
        """PROD-MOD-INV, postcondición b y D-22: el traspaso corre en la misma transacción; si falla, se deshace todo."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        registrante = RegistranteDeTraspaso()
        with mock.patch.object(registrante, "traspasar", side_effect=FallaDePrueba("falla")), registrante.patch():
            with self.assertRaises(FallaDePrueba), transaction.atomic():
                self.mod(nombre="Invernadero Norte", capataz_id=nuevo.pk, personal_confirmado=True)
        self.assertEqual(self.recargado().nombre_invernadero, "Invernadero A")
        self.assertEqual(self.recargado().capataz_id, self.capataz.pk)
        self.assertFalse(RegistroAuditoria.objects.exists())

    # ---- Postcondición f: auditoría ----

    def test_post_f_audita_la_modificacion_con_el_invernadero_como_afectado(self):
        """PROD-MOD-INV, postcondición f y D-36: un registro con quien actuó, la acción, el invernadero y los cambios."""
        self.mod(nombre="Invernadero Norte")
        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual(registro.rol, "gerente")
        self.assertEqual(
            registro.afectados,
            [{"modelo": "maestros.invernadero", "id": self.invernadero.pk, "texto": "Invernadero Norte"}],
        )
        # MAE-02a (D6, D-41): el invernadero de este ``setUp`` se creó directo en la base (sin pasar por
        # ``alta_invernadero``), así que no tiene la alerta «sin Vendedor». Es el caso de un invernadero viejo (D9): al
        # modificarlo se sincronizan sus alertas y esa alerta se crea, y va en ``datos.alertas_creadas``.
        sin_vendedor = Alerta.objects.get(tipo_alerta="sin_vendedor")
        self.assertEqual(
            registro.detalle,
            {
                "cambios": {"nombre": {"antes": "Invernadero A", "despues": "Invernadero Norte"}},
                "datos": {"alertas_creadas": [{"id": sin_vendedor.pk, "texto": sin_vendedor.descripcion_alerta}]},
            },
        )

    def test_post_f_el_detalle_solo_tiene_lo_que_cambio(self):
        """PROD-MOD-INV, postcondición f y D-36: ``cambios`` con cada dato que cambió, antes y después; una calle sola."""
        self.mod(calle="Av. Libertad")
        cambios = RegistroAuditoria.objects.get(accion=MODIFICACION).detalle["cambios"]
        self.assertEqual(cambios, {"calle": {"antes": "Calle 122", "despues": "Av. Libertad"}})

    def test_post_f_de_urbana_a_rural_deja_en_cambios_lo_urbano_a_nulo_y_lo_rural_desde_nulo(self):
        """PROD-MOD-INV, postcondición f y D-36: el cambio de urbana a rural es ``tipo_direccion`` y, de cada dato, su
        valor a nulo (lo urbano) o desde nulo (lo rural); es la misma forma que el alta, donde lo ausente es ``None``.
        El kilómetro es texto (D-39), como en el alta."""
        self.mod(tipo_direccion="rural", ruta="Ruta Nacional 14", kilometro="871")
        cambios = RegistroAuditoria.objects.get(accion=MODIFICACION).detalle["cambios"]
        self.assertEqual(
            cambios,
            {
                "tipo_direccion": {"antes": "urbana", "despues": "rural"},
                "calle": {"antes": "Calle 122", "despues": None},
                "numero_calle": {"antes": "3310", "despues": None},
                "ruta": {"antes": None, "despues": "Ruta Nacional 14"},
                "kilometro": {"antes": None, "despues": "871"},
            },
        )

    def test_post_f_de_rural_a_urbana_deja_en_cambios_lo_rural_a_nulo_y_lo_urbano_desde_nulo(self):
        """PROD-MOD-INV, postcondición f y D-36: el cambio inverso (de rural a urbana) es el espejo del de urbana a
        rural: ``tipo_direccion``, lo rural a nulo y lo urbano desde nulo (lo opcional vacío no figura)."""
        rural = crear_invernadero("Rural", tipo="rural")
        self.mod(rural, tipo_direccion="urbana", calle="Av. Mitre", numero_calle="S/N")
        cambios = RegistroAuditoria.objects.get(accion=MODIFICACION).detalle["cambios"]
        self.assertEqual(
            cambios,
            {
                "tipo_direccion": {"antes": "rural", "despues": "urbana"},
                "ruta": {"antes": "Ruta Nacional 14", "despues": None},
                "kilometro": {"antes": "871", "despues": None},
                "calle": {"antes": None, "despues": "Av. Mitre"},
                "numero_calle": {"antes": None, "despues": "S/N"},
            },
        )

    def test_post_f_un_cambio_de_localidad_es_una_referencia(self):
        """PROD-MOD-INV, postcondición f y D-36: la localidad va como ``referencia()``."""
        nueva = localidad("Campo Viera", "Oberá")
        viejo = self.invernadero.direccion.localidad
        self.mod(localidad_id=nueva.pk)
        cambios = RegistroAuditoria.objects.get(accion=MODIFICACION).detalle["cambios"]
        self.assertEqual(cambios, {"localidad": {"antes": referencia(viejo), "despues": referencia(nueva)}})

    def test_post_f_el_cambio_de_personal_va_como_referencias_y_los_afectados_incluyen_a_salientes_y_entrantes(self):
        """PROD-MOD-INV, postcondición f y D-36: cada rol que cambia es una referencia (o nulo) antes y después, y las
        personas que salen y entran figuran como afectadas, para que la modificación aparezca en su auditoría."""
        nuevo, vendedor = crear_capataz_activo("nuevo.capataz@infoponia.com"), crear_vendedor()
        with RegistranteDeTraspaso().patch():
            self.mod(capataz_id=nuevo.pk, vendedor_id=vendedor.pk, agronomo_id=None, personal_confirmado=True)
        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertEqual(
            registro.detalle["cambios"],
            {
                "agronomo": {"antes": referencia(self.agronomo), "despues": None},
                "capataz": {"antes": referencia(self.capataz), "despues": referencia(nuevo)},
                "vendedor": {"antes": None, "despues": referencia(vendedor)},
            },
        )
        self.assertEqual(registro.afectados[0]["modelo"], "maestros.invernadero")
        self.assertCountEqual(
            registro.afectados[1:], [afectado(self.agronomo), afectado(self.capataz), afectado(nuevo), afectado(vendedor)]
        )

    def test_post_f_un_solo_registro_por_modificacion(self):
        """PROD-MOD-INV, postcondición f: «una acción = un registro» (D-36), aunque cambie todo a la vez."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        with RegistranteDeTraspaso().patch():
            self.mod(
                nombre="Norte",
                tipo_direccion="rural",
                ruta="RN 12",
                kilometro="9",
                capataz_id=nuevo.pk,
                personal_confirmado=True,
            )
        self.assertEqual(RegistroAuditoria.objects.filter(accion=MODIFICACION).count(), 1)

    def test_post_f_una_modificacion_rechazada_no_audita(self):
        """PROD-MOD-INV, postcondición f: si falla, no queda ningún registro."""
        errores_de(lambda: self.mod(nombre=""))
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_d28_sin_cambios_no_guarda_ni_audita(self):
        """D-28 (como ``modificar_usuario``): si no cambió nada, devuelve el invernadero sin auditar."""
        devuelto = self.mod()
        self.assertEqual(devuelto.pk, self.invernadero.pk)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_d22_si_falla_la_auditoria_no_queda_la_modificacion(self):
        """D-22: la auditoría se escribe en la misma transacción; si falla, se deshace todo (también la dirección)."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=FallaDePrueba("falla")):
            with self.assertRaises(FallaDePrueba), transaction.atomic():
                self.mod(nombre="Norte", tipo_direccion="rural", ruta="RN 12", kilometro="9")
        invernadero = self.recargado()
        self.assertEqual(invernadero.nombre_invernadero, "Invernadero A")
        self.assertIsInstance(invernadero.direccion.concreta(), DireccionUrbana)
        self.assertFalse(DireccionRural.objects.exists())

    # ---- MAE-02a: alertas (postcondiciones b y d, regla 2, D4; reemplazan a test_d38_la_modificacion_…) ----
    # Las notificaciones (postcondición c) son de NOT-01 (D-42): sus pruebas están más arriba, en ``test_post_c_…``.

    def tipos_de_destinatario(self):
        """Un tipo falso por cada destinatario posible, registrados mientras dura el bloque."""
        return tipo_de_alerta_de_prueba(
            tipo_falso("prueba_agronomo_o_gerente", destinatario=Destinatario.AGRONOMO_O_GERENTE),
            tipo_falso("prueba_agronomo_y_gerente", destinatario=Destinatario.AGRONOMO_Y_GERENTE),
            tipo_falso("prueba_gerente", destinatario=Destinatario.GERENTE),
        )

    def alertas_de_destinatario(self, invernadero=None, **campos):
        """Una alerta activa de cada tipo de ``tipos_de_destinatario``: ``(o_gerente, y_gerente, de_gerente)``. La de
        tipo ``GERENTE`` siempre va solo al Gerente."""
        invernadero = invernadero or self.invernadero
        return (
            crear_alerta(invernadero, tipo_alerta="prueba_agronomo_o_gerente", **campos),
            crear_alerta(invernadero, tipo_alerta="prueba_agronomo_y_gerente", **campos),
            crear_alerta(invernadero, tipo_alerta="prueba_gerente", para_gerente=True),
        )

    def recargar(self, *alertas):
        for alerta in alertas:
            alerta.refresh_from_db()

    def test_post_b_asignar_un_rol_resuelve_su_alerta(self):
        """PROD-MOD-INV, postcondición b: la alerta «invernadero sin {rol} activo» de ese rol pasó a «resuelta» (con su
        fecha)."""
        sin_vendedor = crear_alerta(self.invernadero, tipo_alerta="sin_vendedor", clave_estado="")
        self.mod(vendedor_id=crear_vendedor().pk, personal_confirmado=True)
        sin_vendedor.refresh_from_db()
        self.assertEqual(sin_vendedor.estado_alerta, "resuelta")
        self.assertIsNotNone(sin_vendedor.fecha_resolucion)

    def test_post_b_asignar_un_rol_no_resuelve_las_alertas_de_los_otros_roles(self):
        """PROD-MOD-INV, postcondición b: solo la del rol que se asignó; los otros roles sin persona siguen alertando."""
        self.mod(vendedor_id=crear_vendedor().pk, personal_confirmado=True)
        self.mod(capataz_id=None, personal_confirmado=True)
        self.assertEqual(
            list(Alerta.objects.filter(estado_alerta="activa").values_list("tipo_alerta", flat=True)), ["sin_capataz"]
        )

    def test_post_b_las_alertas_activas_del_agronomo_pasan_al_entrante(self):
        """PROD-MOD-INV, postcondición b y MD-60: al Agrónomo entrante pasan las alertas activas del invernadero (las
        resueltas y las de tipo ``GERENTE`` no)."""
        nuevo = crear_agronomo("nuevo.agronomo@infoponia.com")
        with self.tipos_de_destinatario():
            o_gerente, y_gerente, de_gerente = self.alertas_de_destinatario(para_gerente=False, agronomo=self.agronomo)
            resuelta = crear_alerta(
                self.invernadero,
                tipo_alerta="prueba_agronomo_o_gerente",
                para_gerente=False,
                agronomo=self.agronomo,
                resuelta=True,
            )
            self.mod(agronomo_id=nuevo.pk, personal_confirmado=True)
        self.recargar(o_gerente, y_gerente, de_gerente, resuelta)
        self.assertEqual((o_gerente.agronomo, o_gerente.para_gerente), (nuevo, False))
        self.assertEqual(y_gerente.agronomo, nuevo)
        self.assertEqual((de_gerente.agronomo_id, de_gerente.para_gerente), (None, True))
        self.assertEqual(resuelta.agronomo_id, self.agronomo.pk)

    def test_regla_3_sin_entrante_las_alertas_del_agronomo_pasan_al_gerente(self):
        """PROD-MOD-INV, regla 3 y MD-61: si se quita al Agrónomo sin reemplazarlo, sus alertas quedan sin responsable y
        van al Gerente (mientras no haya un Agrónomo activo)."""
        with self.tipos_de_destinatario():
            o_gerente, y_gerente, de_gerente = self.alertas_de_destinatario(para_gerente=False, agronomo=self.agronomo)
            self.mod(agronomo_id=None, personal_confirmado=True)
        self.recargar(o_gerente, y_gerente, de_gerente)
        for alerta in (o_gerente, y_gerente, de_gerente):
            self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (None, True))

    def test_d41_asignar_agronomo_pasa_las_alertas_agronomo_o_gerente_y_el_gerente_deja_de_recibirlas(self):
        """D4 (i), destinatario ``AGRONOMO_O_GERENTE``: las que fueron al Gerente por falta de Agrónomo pasan al entrante
        (``agronomo=entrante, para_gerente=False``)."""
        sin_agronomo = crear_invernadero("Sin agrónomo", capataz=self.capataz)
        nuevo = crear_agronomo("nuevo.agronomo@infoponia.com")
        with self.tipos_de_destinatario():
            o_gerente, _, _ = self.alertas_de_destinatario(sin_agronomo, para_gerente=True, agronomo=None)
            self.mod(sin_agronomo, agronomo_id=nuevo.pk, personal_confirmado=True)
        o_gerente.refresh_from_db()
        self.assertEqual((o_gerente.agronomo, o_gerente.para_gerente), (nuevo, False))
        self.assertNotIn(o_gerente, Alerta.objects.para(self.gerente))
        self.assertIn(o_gerente, Alerta.objects.para(nuevo))

    def test_d41_asignar_agronomo_suma_al_agronomo_en_las_alertas_agronomo_y_gerente_y_el_gerente_sigue(self):
        """D4 (i), destinatario ``AGRONOMO_Y_GERENTE``: pasa al entrante (``agronomo=entrante``) y ``para_gerente`` sigue
        en ``True``."""
        sin_agronomo = crear_invernadero("Sin agrónomo", capataz=self.capataz)
        nuevo = crear_agronomo("nuevo.agronomo@infoponia.com")
        with self.tipos_de_destinatario():
            _, y_gerente, _ = self.alertas_de_destinatario(sin_agronomo, para_gerente=True, agronomo=None)
            self.mod(sin_agronomo, agronomo_id=nuevo.pk, personal_confirmado=True)
        y_gerente.refresh_from_db()
        self.assertEqual((y_gerente.agronomo, y_gerente.para_gerente), (nuevo, True))

    def test_d41_asignar_agronomo_no_toca_las_alertas_de_tipo_gerente(self):
        """D4 (i), destinatario ``GERENTE`` (por ejemplo, «invernadero sin Vendedor activo»): no se tocan al asignar un
        Agrónomo."""
        sin_agronomo = crear_invernadero("Sin agrónomo", capataz=self.capataz)
        nuevo = crear_agronomo("nuevo.agronomo@infoponia.com")
        sin_vendedor = crear_alerta(sin_agronomo, tipo_alerta="sin_vendedor", clave_estado="")
        with self.tipos_de_destinatario():
            _, _, de_gerente = self.alertas_de_destinatario(sin_agronomo, para_gerente=True, agronomo=None)
            self.mod(sin_agronomo, agronomo_id=nuevo.pk, personal_confirmado=True)
        self.recargar(de_gerente, sin_vendedor)
        for alerta in (de_gerente, sin_vendedor):
            self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (None, True))

    def test_post_d_dejar_un_rol_sin_asignar_crea_su_alerta(self):
        """PROD-MOD-INV, postcondición d: si dejó un rol sin asignar, una alerta activa «invernadero sin {rol} activo»
        para el Gerente."""
        self.mod(capataz_id=None, personal_confirmado=True)
        alerta = Alerta.objects.get(tipo_alerta="sin_capataz", estado_alerta="activa")
        self.assertEqual(
            (alerta.invernadero_id, alerta.para_gerente, alerta.agronomo_id), (self.invernadero.pk, True, None)
        )

    def test_post_d_la_del_tecnico_solo_con_sistema_iot(self):
        """PROD-MOD-INV, postcondición d: «la del Técnico solo se genera si el invernadero tiene sistema IoT»."""
        Invernadero.objects.filter(pk=self.invernadero.pk).update(tecnico=crear_tecnico())
        self.mod(tecnico_id=None, personal_confirmado=True)
        self.assertFalse(Alerta.objects.filter(tipo_alerta="sin_tecnico").exists())
        with mock.patch.object(Invernadero, "tiene_sistema_iot", return_value=True):
            self.mod(nombre="Otro nombre")
        self.assertTrue(Alerta.objects.filter(tipo_alerta="sin_tecnico", estado_alerta="activa").exists())

    def test_post_d_conservar_una_persona_inactiva_mantiene_la_alerta(self):
        """PROD-MOD-INV, postcondición d y regla 4: la persona asignada que quedó inactiva se conserva, y el rol sigue
        sin «una persona activa»: hay una alerta activa (una sola, aunque se modifique dos veces) hasta que se la
        reemplace."""
        Capataz.objects.filter(pk=self.capataz.pk).update(is_active=False)
        self.mod(nombre="Otro nombre")
        self.mod(nombre="Otro nombre más")
        self.assertEqual(Alerta.objects.filter(tipo_alerta="sin_capataz", estado_alerta="activa").count(), 1)
        self.assertEqual(self.recargado().capataz_id, self.capataz.pk)

    def test_post_d_las_alertas_de_personal_no_se_repiten_al_modificar_dos_veces(self):
        """PROD-MOD-INV, postcondición d: a lo sumo una activa por invernadero y tipo (D-41)."""
        self.mod(nombre="Uno")
        self.mod(nombre="Dos")
        self.assertEqual(Alerta.objects.filter(tipo_alerta="sin_vendedor", estado_alerta="activa").count(), 1)

    def test_d28_sin_cambios_no_crea_alertas(self):
        """D-28 y D-41: si no cambió nada, no se guarda, no se audita y no se tocan las alertas."""
        self.mod()
        self.assertFalse(Alerta.objects.exists())

    def test_regla_2_el_aviso_cuenta_las_alertas_que_recibe_el_agronomo(self):
        """PROD-MOD-INV, regla 2: el aviso del cambio de Agrónomo suma a «Recibe» las alertas activas que pasarían al
        entrante, como ``("alertas activas", N)``; no cuenta las resueltas."""
        nuevo = crear_agronomo("nuevo.agronomo@infoponia.com")
        with self.tipos_de_destinatario():
            self.alertas_de_destinatario(para_gerente=False, agronomo=self.agronomo)
            crear_alerta(
                self.invernadero,
                tipo_alerta="prueba_agronomo_o_gerente",
                agronomo=self.agronomo,
                para_gerente=False,
                resuelta=True,
            )
            with self.assertRaises(invernaderos.FaltaConfirmarPersonal) as contexto:
                self.mod(agronomo_id=nuevo.pk)
        entrada = next(e for e in contexto.exception.aviso if e["rol"] == "agronomo")
        self.assertIn(("alertas activas", 2), entrada["recibe"])
        self.assertEqual(Alerta.objects.filter(agronomo=self.agronomo, estado_alerta="activa").count(), 2)

    def test_regla_2_sin_alertas_el_aviso_no_suma_la_entrada_de_alertas(self):
        """PROD-MOD-INV, regla 2: sin alertas que pasar, «Recibe» no trae la entrada (no aparece «0 alertas»)."""
        nuevo = crear_agronomo("nuevo.agronomo@infoponia.com")
        with self.assertRaises(invernaderos.FaltaConfirmarPersonal) as contexto:
            self.mod(agronomo_id=nuevo.pk)
        entrada = next(e for e in contexto.exception.aviso if e["rol"] == "agronomo")
        self.assertEqual(entrada["recibe"], [])

    def test_post_f_un_solo_registro_con_las_alertas_en_datos(self):
        """PROD-MOD-INV, postcondición f y D-36 (D6 de MAE-02): sigue siendo un solo registro; las alertas creadas,
        resueltas y traspasadas van en ``datos`` como referencias, y solo las claves que no están vacías."""
        nuevo = crear_agronomo("nuevo.agronomo@infoponia.com")
        sin_vendedor = crear_alerta(self.invernadero, tipo_alerta="sin_vendedor", clave_estado="")
        propia = crear_alerta(self.invernadero, tipo_alerta="otro_tipo", para_gerente=False, agronomo=self.agronomo)
        with tipo_de_alerta_de_prueba(tipo_falso("otro_tipo", destinatario=Destinatario.AGRONOMO_O_GERENTE)):
            self.mod(agronomo_id=nuevo.pk, capataz_id=None, vendedor_id=crear_vendedor().pk, personal_confirmado=True)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=MODIFICACION).count(), 1)
        datos = RegistroAuditoria.objects.get(accion=MODIFICACION).detalle["datos"]
        creada = Alerta.objects.get(tipo_alerta="sin_capataz")
        self.assertEqual(datos["alertas_creadas"], [{"id": creada.pk, "texto": creada.descripcion_alerta}])
        self.assertEqual(datos["alertas_resueltas"], [{"id": sin_vendedor.pk, "texto": sin_vendedor.descripcion_alerta}])
        self.assertEqual(datos["alertas_traspasadas"], [{"id": propia.pk, "texto": propia.descripcion_alerta}])

    def test_post_f_sin_alertas_que_cambiar_el_detalle_no_trae_datos(self):
        """D-36 y D6 de MAE-02: si ninguna alerta cambió, el detalle conserva solo ``cambios`` (sin ``datos`` vacío)."""
        Invernadero.objects.filter(pk=self.invernadero.pk).update(vendedor=crear_vendedor())
        crear_alerta(self.invernadero, tipo_alerta="sin_vendedor", clave_estado="", resuelta=True)
        self.mod(nombre="Norte")
        self.assertNotIn("datos", RegistroAuditoria.objects.get(accion=MODIFICACION).detalle)

    def test_d22_si_falla_la_auditoria_no_quedan_alertas_nuevas(self):
        """D-22 y D-41: las alertas se crean en la misma transacción; si la auditoría falla, no queda ninguna."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=FallaDePrueba("falla")):
            with self.assertRaises(FallaDePrueba), transaction.atomic():
                self.mod(capataz_id=None, personal_confirmado=True)
        self.assertFalse(Alerta.objects.exists())


    # ---- NOT-01: avisos a las personas que quedan a cargo (postcondición c; D-42) ----
    # Texto aprobado: título «Quedó a cargo de {invernadero}»; detalle «El Gerente le asignó el rol de {rol}.» seguido de
    # «Recibe: {descripción}: {cantidad}, …» (solo cantidades mayores que cero) o de «No recibe nada pendiente.». Solo a
    # las personas ENTRANTES de este cambio (plan de NOT-01, paso 7; D-28: sin cambios, nada).

    def test_post_c_notifica_a_la_persona_que_queda_a_cargo_y_dice_que_no_recibe_nada_pendiente(self):
        """PROD-MOD-INV, postcondición c: la persona entrante recibe una notificación con el invernadero; sin nada que
        recibir, «No recibe nada pendiente.»."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        with RegistranteDeTraspaso().patch():
            self.mod(capataz_id=nuevo.pk, personal_confirmado=True)

        notificacion = Notificacion.objects.get()
        self.assertEqual(notificacion.destinatario_id, nuevo.pk)
        self.assertEqual(notificacion.titulo, "Quedó a cargo de Invernadero A")
        self.assertEqual(notificacion.detalle, "El Gerente le asignó el rol de Capataz. No recibe nada pendiente.")
        self.assertFalse(notificacion.leida)

    def test_post_c_el_aviso_dice_lo_que_recibe(self):
        """PROD-MOD-INV, postcondición c: «lo que recibió»: lo que cuentan los registrantes de ``contar_traspaso``."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        with RegistranteDeTraspaso(recibe=[("órdenes a realizar", 2), ("mantenimientos a realizar", 1)]).patch():
            self.mod(capataz_id=nuevo.pk, personal_confirmado=True)

        self.assertEqual(
            Notificacion.objects.get().detalle,
            "El Gerente le asignó el rol de Capataz. Recibe: órdenes a realizar: 2, mantenimientos a realizar: 1.",
        )

    def test_post_c_no_lista_lo_que_viene_en_cero(self):
        """PROD-MOD-INV, postcondición c: una cantidad en cero no se lista; si todo es cero, «No recibe nada pendiente.»."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        with RegistranteDeTraspaso(recibe=[("órdenes a realizar", 0), ("mantenimientos a realizar", 3)]).patch():
            self.mod(capataz_id=nuevo.pk, personal_confirmado=True)
        self.assertEqual(
            Notificacion.objects.get().detalle,
            "El Gerente le asignó el rol de Capataz. Recibe: mantenimientos a realizar: 3.",
        )

        Notificacion.objects.all().delete()
        otro = crear_capataz_activo("otro.capataz@infoponia.com")
        with RegistranteDeTraspaso(recibe=[("órdenes a realizar", 0)]).patch():
            self.mod(capataz_id=otro.pk, personal_confirmado=True)
        self.assertEqual(
            Notificacion.objects.get().detalle, "El Gerente le asignó el rol de Capataz. No recibe nada pendiente."
        )

    def test_post_c_el_agronomo_entrante_recibe_las_alertas_activas_que_le_pasan(self):
        """PROD-MOD-INV, postcondición c y regla 2: al Agrónomo entrante se le avisa de las alertas activas que recibe,
        contadas ANTES del traspaso (después ya no quedan en el saliente)."""
        nuevo = crear_agronomo("nuevo.agronomo@infoponia.com")
        with self.tipos_de_destinatario(), RegistranteDeTraspaso().patch():
            self.alertas_de_destinatario(para_gerente=False, agronomo=self.agronomo)
            self.mod(agronomo_id=nuevo.pk, personal_confirmado=True)

        notificacion = Notificacion.objects.get(destinatario=nuevo)
        self.assertEqual(
            notificacion.detalle, "El Gerente le asignó el rol de Agrónomo. Recibe: alertas activas: 2."
        )

    def test_post_c_la_persona_saliente_no_recibe_nada(self):
        """PROD-MOD-INV, postcondición c y «Solo prototipo»: el caso de uso solo notifica a la persona asignada; el
        prototipo avisaba también a la saliente y manda el caso de uso (L7)."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        with RegistranteDeTraspaso().patch():
            self.mod(capataz_id=nuevo.pk, personal_confirmado=True)

        self.assertFalse(Notificacion.objects.filter(destinatario=self.capataz).exists())

    def test_post_c_las_personas_que_siguen_a_cargo_no_reciben_nada(self):
        """PROD-MOD-INV, postcondición c: solo las que quedan a cargo EN ESTE CAMBIO; el Agrónomo y el Vendedor que no
        cambiaron no reciben nada."""
        vendedor = crear_vendedor()
        invernadero = crear_invernadero("Invernadero B", agronomo=self.agronomo, capataz=self.capataz, vendedor=vendedor)
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        with RegistranteDeTraspaso().patch():
            self.mod(invernadero, capataz_id=nuevo.pk, personal_confirmado=True)

        self.assertEqual([n.destinatario_id for n in Notificacion.objects.all()], [nuevo.pk])

    def test_post_c_si_cambian_dos_roles_cada_entrante_recibe_la_suya_con_su_rol(self):
        """PROD-MOD-INV, postcondición c: un aviso por persona entrante, con el rol que le tocó."""
        nuevo_agronomo = crear_agronomo("nuevo.agronomo@infoponia.com")
        vendedor = crear_vendedor()
        with RegistranteDeTraspaso().patch():
            self.mod(agronomo_id=nuevo_agronomo.pk, vendedor_id=vendedor.pk, personal_confirmado=True)

        detalles = {n.destinatario_id: n.detalle for n in Notificacion.objects.all()}
        self.assertEqual(set(detalles), {nuevo_agronomo.pk, vendedor.pk})
        self.assertIn("rol de Agrónomo", detalles[nuevo_agronomo.pk])
        self.assertIn("rol de Vendedor", detalles[vendedor.pk])

    def test_post_c_quitar_a_alguien_sin_reemplazarlo_no_notifica_a_nadie(self):
        """PROD-MOD-INV, regla 3: sin persona entrante no hay a quién avisar; la saliente tampoco recibe nada."""
        with RegistranteDeTraspaso().patch():
            self.mod(capataz_id=None, personal_confirmado=True)

        self.assertEqual(Notificacion.objects.count(), 0)

    def test_post_c_nunca_notifica_al_actor(self):
        """API, regla de uso 4: el Gerente que modifica no recibe nada."""
        with RegistranteDeTraspaso().patch():
            self.mod(capataz_id=crear_capataz_activo("nuevo.capataz@infoponia.com").pk, personal_confirmado=True)

        self.assertFalse(Notificacion.objects.filter(destinatario=self.gerente).exists())

    def test_d28_una_modificacion_sin_cambios_no_notifica(self):
        """D-28 y paso 7 de NOT-01: si no cambió nada, no se guarda, no se audita y no se notifica."""
        with RegistranteDeTraspaso().patch():
            self.mod()

        self.assertEqual(Notificacion.objects.count(), 0)

    def test_post_c_cambiar_solo_el_nombre_o_la_direccion_no_notifica(self):
        """PROD-MOD-INV, postcondición c: el aviso es por el personal que queda a cargo; un cambio de nombre o de dirección
        no lo es (plan de NOT-01, paso 7)."""
        with RegistranteDeTraspaso().patch():
            self.mod(nombre="Invernadero Norte", calle="Otra calle")

        self.assertEqual(Notificacion.objects.count(), 0)

    def test_post_c_un_cambio_de_personal_sin_confirmar_no_notifica(self):
        """PROD-MOD-INV, regla 2: sin confirmar no se guarda nada, y tampoco se avisa."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        with RegistranteDeTraspaso().patch(), self.assertRaises(invernaderos.FaltaConfirmarPersonal):
            self.mod(capataz_id=nuevo.pk)

        self.assertEqual(Notificacion.objects.count(), 0)

    def test_post_c_si_el_traspaso_falla_no_queda_ninguna_notificacion(self):
        """PROD-MOD-INV, postcondición c y regla de uso 1 de la API: el aviso es de la misma transacción."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        registrante = RegistranteDeTraspaso()
        with mock.patch.object(registrante, "traspasar", side_effect=FallaDePrueba("falla")), registrante.patch():
            with self.assertRaises(FallaDePrueba), transaction.atomic():
                self.mod(capataz_id=nuevo.pk, personal_confirmado=True)

        self.assertEqual(Notificacion.objects.count(), 0)

    def test_post_c_si_falla_al_notificar_se_deshace_el_cambio_de_personal(self):
        """API, regla de uso 1: si falla al notificar, la modificación entera se deshace."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        with RegistranteDeTraspaso().patch():
            with mock.patch.object(
                invernaderos.notificaciones, "notificar_a_varios", side_effect=FallaDePrueba("falla")
            ):
                with self.assertRaises(FallaDePrueba), transaction.atomic():
                    self.mod(nombre="Invernadero Norte", capataz_id=nuevo.pk, personal_confirmado=True)

        self.assertEqual(self.recargado().nombre_invernadero, "Invernadero A")
        self.assertEqual(self.recargado().capataz_id, self.capataz.pk)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_post_c_no_se_audita_el_texto_de_la_notificacion(self):
        """D-42: el texto del aviso no va al registro de auditoría."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        with RegistranteDeTraspaso(recibe=[("órdenes a realizar", 2)]).patch():
            self.mod(capataz_id=nuevo.pk, personal_confirmado=True)

        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertNotIn("Quedó a cargo", json.dumps(registro.detalle))
        self.assertNotIn("Recibe:", json.dumps(registro.detalle))


class ProdModInvReactivacionServicioTests(ConGeoref, TestCase):
    """Servicio ``reactivar_invernadero`` (PROD-MOD-INV: reactivación; regla 5 de PROD-BAJ-INV; reglas 5 y 6)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Viejo", activo=False, agronomo=self.agronomo)

    def recargado(self):
        return Invernadero.objects.get(pk=self.invernadero.pk)

    def test_pre_a_otro_rol_no_reactiva(self):
        """PROD-MOD-INV, precondición a: un Agrónomo, un Capataz o un Administrador reciben PermissionDenied."""
        for actor in (self.agronomo, crear_capataz(), crear_administrador()):
            with self.subTest(actor=actor.email), self.assertRaises(PermissionDenied):
                invernaderos.reactivar_invernadero(actor, self.invernadero.pk)
        self.assertFalse(self.recargado().activo)

    def test_pre_a_un_gerente_inactivo_o_sin_actor_no_reactiva(self):
        """PROD-MOD-INV, precondición a: «con una cuenta activa de Gerente»."""
        with self.assertRaises(PermissionDenied):
            invernaderos.reactivar_invernadero(None, self.invernadero.pk)
        self.gerente.is_active = False
        self.gerente.save()
        with self.assertRaises(PermissionDenied):
            invernaderos.reactivar_invernadero(self.gerente, self.invernadero.pk)

    def test_pre_a_un_invernadero_inexistente_da_404(self):
        """PROD-MOD-INV y D-28: un id que no existe es Http404."""
        with self.assertRaises(Http404):
            invernaderos.reactivar_invernadero(self.gerente, 0)

    def test_post_e_reactiva_el_invernadero(self):
        """PROD-MOD-INV, postcondición e (sin las alertas): el invernadero quedó en estado «activo»."""
        devuelto = invernaderos.reactivar_invernadero(self.gerente, self.invernadero.pk)
        self.assertTrue(devuelto.activo)
        self.assertTrue(self.recargado().activo)

    def test_post_e_conserva_el_nombre_la_direccion_y_el_personal(self):
        """PROD-MOD-INV, postcondición e y regla 1 de PROD-BAJ-INV: la reactivación solo cambia el estado."""
        antes = datos_de(self.invernadero)
        invernaderos.reactivar_invernadero(self.gerente, self.invernadero.pk)
        self.assertEqual(datos_de(self.invernadero), antes)

    def test_post_f_audita_la_reactivacion_con_el_cambio_de_estado(self):
        """PROD-MOD-INV, postcondición f y D-36: un registro ``reactivacion_invernadero`` con el estado inactivo a activo."""
        invernaderos.reactivar_invernadero(self.gerente, self.invernadero.pk)
        registro = RegistroAuditoria.objects.get(accion=REACTIVACION)
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual(
            registro.afectados, [{"modelo": "maestros.invernadero", "id": self.invernadero.pk, "texto": "Viejo"}]
        )
        # MAE-02a (D6, D-41): el invernadero de este ``setUp`` se creó directo en la base, con solo Agrónomo: al
        # reactivarlo se crean las alertas «sin Capataz» y «sin Vendedor» y van en ``datos.alertas_creadas``.
        alertas_creadas = [{"id": a.pk, "texto": a.descripcion_alerta} for a in Alerta.objects.order_by("pk")]
        self.assertEqual(len(alertas_creadas), 2)
        self.assertEqual(
            registro.detalle,
            {
                "cambios": {"estado": {"antes": "inactivo", "despues": "activo"}},
                "datos": {"alertas_creadas": alertas_creadas},
            },
        )
        self.assertEqual(RegistroAuditoria.objects.count(), 1)

    def test_regla_5_un_invernadero_activo_no_se_reactiva(self):
        """PROD-MOD-INV y PROD-BAJ-INV, regla 5: reactivar uno activo se rechaza con ``invernadero_activo``."""
        activo = crear_invernadero("Activo")
        self.assertEqual(
            codigos_de(lambda: invernaderos.reactivar_invernadero(self.gerente, activo.pk)), ["invernadero_activo"]
        )
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_5_despues_de_reactivarlo_se_modifica_como_cualquier_otro(self):
        """PROD-MOD-INV, regla 5: «después de reactivarlo, se modifica como cualquier otro»."""
        invernaderos.reactivar_invernadero(self.gerente, self.invernadero.pk)
        invernaderos.modificar_invernadero(
            self.gerente, self.invernadero.pk, **(datos_de(self.invernadero) | {"nombre": "Nuevo"})
        )
        self.assertEqual(self.recargado().nombre_invernadero, "Nuevo")

    def test_regla_6_la_reactivacion_no_corre_efectos_ni_traspasos_ni_impedimentos(self):
        """PROD-MOD-INV, regla 6: no reactiva sectores ni insumos; ninguno de los puntos de extensión interviene."""
        falla = mock.Mock(side_effect=AssertionError("no debe llamarse"))
        with (
            mock.patch.object(extensiones, "_EFECTOS_DE_BAJA", [falla]),
            mock.patch.object(extensiones, "_IMPEDIMENTOS", [falla]),
            mock.patch.object(extensiones, "_TRASPASOS", [(falla, falla)]),
        ):
            invernaderos.reactivar_invernadero(self.gerente, self.invernadero.pk)
        falla.assert_not_called()

    def test_d22_si_falla_la_auditoria_no_queda_reactivado(self):
        """D-22: la auditoría se escribe en la misma transacción; si falla, el invernadero sigue inactivo."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=FallaDePrueba("falla")):
            with self.assertRaises(FallaDePrueba), transaction.atomic():
                invernaderos.reactivar_invernadero(self.gerente, self.invernadero.pk)
        self.assertFalse(self.recargado().activo)

    # ---- MAE-02a: alertas (postcondición e; reemplazan a test_d38_la_reactivacion_…) ----

    def test_post_e_reactivar_crea_una_alerta_por_cada_rol_sin_persona_activa(self):
        """PROD-MOD-INV, postcondición e: al reactivar, una alerta «invernadero sin {rol} activo» por cada rol sin una
        persona activa (acá tiene solo Agrónomo: faltan el Capataz y el Vendedor; el Técnico no, sin IoT)."""
        invernaderos.reactivar_invernadero(self.gerente, self.invernadero.pk)
        activas = Alerta.objects.filter(invernadero=self.invernadero, estado_alerta="activa")
        self.assertCountEqual(activas.values_list("tipo_alerta", flat=True), ["sin_capataz", "sin_vendedor"])
        self.assertTrue(all(a.para_gerente and a.agronomo_id is None for a in activas))

    def test_post_e_reactivar_cuenta_como_faltante_a_la_persona_inactiva(self):
        """PROD-MOD-INV, postcondición e: «por cada rol sin una persona activa»: una persona asignada pero inactiva
        cuenta."""
        Agronomo.objects.filter(pk=self.agronomo.pk).update(is_active=False)
        invernaderos.reactivar_invernadero(self.gerente, self.invernadero.pk)
        self.assertTrue(Alerta.objects.filter(tipo_alerta="sin_agronomo", estado_alerta="activa").exists())

    def test_post_e_reactivar_con_el_personal_completo_no_crea_alertas(self):
        """PROD-MOD-INV, postcondición e: sin roles faltantes no hay alertas."""
        completo = crear_invernadero(
            "Completo",
            activo=False,
            agronomo=crear_agronomo("a2@infoponia.com"),
            capataz=crear_capataz_activo(),
            vendedor=crear_vendedor(),
        )
        invernaderos.reactivar_invernadero(self.gerente, completo.pk)
        self.assertFalse(Alerta.objects.filter(invernadero=completo).exists())

    def test_post_e_reactivar_un_invernadero_ya_activo_se_rechaza_y_no_crea_alertas(self):
        """PROD-MOD-INV, postcondición e: reactivar uno que ya está activo se rechaza y no crea alertas."""
        activo = crear_invernadero("Activo")
        with self.assertRaises(ValidationError):
            invernaderos.reactivar_invernadero(self.gerente, activo.pk)
        self.assertFalse(Alerta.objects.exists())

    def test_post_f_reactivar_audita_un_solo_registro_con_las_alertas_en_datos(self):
        """PROD-MOD-INV, postcondición f y D-36 (D6 de MAE-02): un solo registro con el cambio de estado en ``cambios`` y
        las alertas creadas en ``datos.alertas_creadas``."""
        invernaderos.reactivar_invernadero(self.gerente, self.invernadero.pk)
        self.assertEqual(RegistroAuditoria.objects.count(), 1)
        detalle = RegistroAuditoria.objects.get(accion=REACTIVACION).detalle
        self.assertEqual(detalle["cambios"], {"estado": {"antes": "inactivo", "despues": "activo"}})
        esperado = [{"id": a.pk, "texto": a.descripcion_alerta} for a in Alerta.objects.order_by("pk")]
        self.assertEqual(len(esperado), 2)
        self.assertEqual(detalle["datos"], {"alertas_creadas": esperado})


class ProdModInvAccionesTests(ConGeoref, TestCase):
    """``acciones_permitidas`` (D-30): ningún botón lleva a un 403; la pantalla muestra solo lo que esta función dice."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.activo = crear_invernadero("Activo")
        self.inactivo = crear_invernadero("Inactivo", activo=False)

    def test_d30_el_gerente_modifica_y_da_de_baja_un_invernadero_activo(self):
        """D-30 y PROD-CNS-INV, regla 6: sobre uno activo, el Gerente modifica y da de baja."""
        self.assertEqual(
            invernaderos.acciones_permitidas(self.gerente, self.activo), frozenset({"modificar", "baja"})
        )

    def test_d30_el_gerente_solo_reactiva_un_invernadero_inactivo(self):
        """D-30 y regla 5 de PROD-MOD-INV: sobre uno inactivo, solo reactiva."""
        self.assertEqual(invernaderos.acciones_permitidas(self.gerente, self.inactivo), frozenset({"reactivar"}))

    def test_d30_los_demas_no_tienen_ninguna_accion(self):
        """D-30 y PROD-CNS-INV, regla 6: el Agrónomo, un Gerente inactivo y quien no actúa no tienen acciones."""
        inactivo = crear_gerente("viejo.gerente@infoponia.com", activo=False)
        for actor in (crear_agronomo(), inactivo, None):
            with self.subTest(actor=getattr(actor, "email", None)):
                self.assertEqual(invernaderos.acciones_permitidas(actor, self.activo), frozenset())

    def test_d30_devuelve_un_frozenset_como_la_de_core(self):
        """D-30: igual que ``core.servicios.acciones_permitidas``, devuelve un ``frozenset`` (también vacío), para que
        la plantilla pregunte ``"baja" in acciones``."""
        for actor in (self.gerente, crear_agronomo(), None):
            with self.subTest(actor=getattr(actor, "email", None)):
                self.assertIsInstance(invernaderos.acciones_permitidas(actor, self.activo), frozenset)


@tag("concurrencia")
class ProdModInvConcurrenciaTests(TransactionTestCase):
    """Bloqueos de ``modificar_invernadero`` y ``reactivar_invernadero`` (docs/patrones/bloqueos.md, D-30 y D-32):
    dos hilos, dos conexiones, el orden fijado con ``primera`` (``core/tests/concurrencia.py``). Orden de bloqueos: las
    filas de ``Usuario`` de quien actúa y del personal enviado, el invernadero, los traspasos. Ninguna puede terminar con
    un error sin traducir (en pantalla sería un 500). Usan su propia geografía: el ``flush`` de un
    ``TransactionTestCase`` vacía Georef."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.capataz = crear_capataz_activo()
        self.vendedor = crear_vendedor()
        self.invernadero = crear_invernadero_con_geografia_propia("Invernadero A", capataz=self.capataz)

    def modificar(self, invernadero=None, **cambios):
        """Un llamado a ``modificar_invernadero`` ya armado (los datos se leen ahora, antes de arrancar los hilos)."""
        invernadero = invernadero or self.invernadero
        datos = datos_de(invernadero) | cambios
        return lambda: invernaderos.modificar_invernadero(self.gerente, invernadero.pk, **datos)

    def test_d30_dos_modificaciones_a_la_vez_gana_la_ultima_con_su_antes_real(self):
        """Dos Gerentes modifican el mismo invernadero (D-30, igual que ``modificar_usuario``): gana la última. La
        segunda espera, lee después de bloquear y calcula sus cambios contra lo que dejó la primera: el «antes» de su
        registro de auditoría es el «después» del de la primera. Sin los bloqueos, la segunda usa el nombre original."""
        resultados = correr_a_la_vez(
            self.modificar(nombre="Norte"), self.modificar(nombre="Sur"), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        registros = list(RegistroAuditoria.objects.filter(accion=MODIFICACION).order_by("id"))
        self.assertEqual(len(registros), 2)
        self.assertEqual(registros[0].detalle["cambios"]["nombre"], {"antes": "Invernadero A", "despues": "Norte"})
        self.assertEqual(registros[1].detalle["cambios"]["nombre"], {"antes": "Norte", "despues": "Sur"})
        self.assertEqual(Invernadero.objects.get(pk=self.invernadero.pk).nombre_invernadero, "Sur")

    def test_regla_5_una_modificacion_que_espera_a_una_baja_se_rechaza(self):
        """PROD-MOD-INV, regla 5: la baja va primera y la modificación espera el bloqueo del invernadero; cuando sigue,
        lo lee inactivo y se rechaza con ``invernadero_inactivo``. Sin el bloqueo, modifica un invernadero inactivo."""
        resultados = correr_a_la_vez(
            lambda: invernaderos.baja_invernadero(self.gerente, self.invernadero.pk),
            self.modificar(nombre="Norte"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["invernadero_inactivo"])
        invernadero = Invernadero.objects.get(pk=self.invernadero.pk)
        self.assertEqual((invernadero.nombre_invernadero, invernadero.activo), ("Invernadero A", False))
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_regla_5_una_baja_que_espera_a_una_modificacion_ve_el_nombre_nuevo(self):
        """PROD-BAJ-INV y PROD-MOD-INV: la modificación va primera y la baja espera; cuando sigue, lee el invernadero
        ya modificado y su registro de auditoría lleva el nombre nuevo. Sin el bloqueo, la baja audita el nombre viejo."""
        resultados = correr_a_la_vez(
            self.modificar(nombre="Norte"),
            lambda: invernaderos.baja_invernadero(self.gerente, self.invernadero.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        baja = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.BAJA_INVERNADERO)
        self.assertEqual(baja.afectados[0]["texto"], "Norte")
        self.assertFalse(Invernadero.objects.get(pk=self.invernadero.pk).activo)

    def test_regla_4_asignar_una_cuenta_que_se_da_de_baja_a_la_vez_se_rechaza(self):
        """PROD-MOD-INV, regla 4 y USR-BAJ-USR: la baja de la cuenta va primera y la asignación espera el bloqueo de la
        cuenta (el ``UPDATE`` del invernadero solo toma ``FOR KEY SHARE`` sobre la fila del rol, que no espera a la baja).
        Cuando sigue, vuelve a verificar que esté activa y se rechaza con ``persona_invalida``. Sin ese bloqueo, el
        invernadero queda con una cuenta inactiva asignada como si la hubieran ofrecido."""
        resultados = correr_a_la_vez(
            lambda: baja_usuario(self.gerente, self.vendedor.pk),
            self.modificar(vendedor_id=self.vendedor.pk, personal_confirmado=True),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["persona_invalida"])
        self.assertIn("vendedor", rechazos[0].error_dict)
        self.assertIsNone(Invernadero.objects.get(pk=self.invernadero.pk).vendedor_id)

    def test_regla_4_la_baja_de_una_cuenta_que_espera_a_su_asignacion_no_hace_deadlock(self):
        """MD-60 y regla 4: la asignación va primera y la baja de la cuenta espera; al seguir da de baja la cuenta y el
        invernadero la conserva (como historial). Las dos terminan, sin deadlock: las dos toman la cuenta antes que lo
        demás. Es el orden que tiene que seguir la baja de cuenta futura (disparador 4 de «Cuando exista Invernadero»);
        no hay una protección propia que quitar acá."""
        resultados = correr_a_la_vez(
            self.modificar(vendedor_id=self.vendedor.pk, personal_confirmado=True),
            lambda: baja_usuario(self.gerente, self.vendedor.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        self.assertEqual(Invernadero.objects.get(pk=self.invernadero.pk).vendedor_id, self.vendedor.pk)
        self.vendedor.refresh_from_db()
        self.assertFalse(self.vendedor.is_active)

    def test_regla_1_renombrar_dos_invernaderos_al_mismo_nombre_a_la_vez_responde_con_un_codigo(self):
        """PROD-MOD-INV, regla 1: los dos pasan la verificación previa (el otro todavía no confirmó), pero el índice único
        de la base rechaza al segundo, y se traduce a ``nombre_repetido`` en el campo: nunca un error sin traducir (un 500).
        Sin la traducción, la segunda modificación termina con un ``IntegrityError``."""
        otro = crear_invernadero_con_geografia_propia("Invernadero C")
        resultados = correr_a_la_vez(
            self.modificar(nombre="Mismo"), self.modificar(otro, nombre="Mismo"), primera="a"
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["nombre_repetido"])
        self.assertIn("nombre", rechazos[0].error_dict)
        self.assertEqual(Invernadero.objects.filter(nombre_invernadero="Mismo").count(), 1)

    def test_regla_5_dos_reactivaciones_a_la_vez_reactivan_una_sola_vez(self):
        """PROD-MOD-INV, regla 5: la segunda espera el bloqueo, lo lee activo y se rechaza con ``invernadero_activo``; queda
        un solo registro de reactivación. Sin el bloqueo, las dos reactivan y dejan dos registros."""
        inactivo = crear_invernadero_con_geografia_propia("Viejo", activo=False)
        resultados = correr_a_la_vez(
            lambda: invernaderos.reactivar_invernadero(self.gerente, inactivo.pk),
            lambda: invernaderos.reactivar_invernadero(self.gerente, inactivo.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["invernadero_activo"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion=REACTIVACION).count(), 1)


class ProdModInvVistaTests(ConGeoref, TestCase):
    """Pantalla «Modificar invernadero» y botón «Reactivar» (integración, PROD-MOD-INV): flujo principal, aviso de la
    regla 2, regla 5, errores del servicio y acceso por rol (SEG-13, D-30). Todo anda sin JavaScript: la ventana de
    confirmación viene en la página."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.client.force_login(self.gerente)
        self.agronomo, self.capataz = crear_agronomo(), crear_capataz_activo()
        self.invernadero = crear_invernadero("Invernadero A", agronomo=self.agronomo, capataz=self.capataz)
        self.url = reverse("maestros:invernadero_modificar", args=[self.invernadero.pk])
        self.ficha = reverse("maestros:invernadero", args=[self.invernadero.pk])
        self.misiones = Provincia.objects.get(nombre_provincia="Misiones")
        self.capital = Departamento.objects.get(nombre_departamento="Capital", provincia=self.misiones)

    def datos(self, **extra):
        """Un POST que deja al invernadero como está (ids como texto, como lo manda el navegador) más ``extra``."""
        return {
            "nombre": "Invernadero A",
            "tipo_direccion": "urbana",
            "provincia": self.misiones.pk,
            "departamento": self.capital.pk,
            "localidad": localidad().pk,
            "calle": "Calle 122",
            "numero_calle": "3310",
            "agronomo": self.agronomo.pk,
            "capataz": self.capataz.pk,
        } | extra

    def recargado(self):
        return Invernadero.objects.get(pk=self.invernadero.pk)

    def test_flujo_principal_modifica_el_invernadero_y_va_a_la_ficha(self):
        """PROD-MOD-INV, flujo principal: el Gerente cambia el nombre y la calle, se guarda y vuelve a la ficha con el aviso."""
        respuesta = self.client.post(self.url, self.datos(nombre="Invernadero Norte", calle="Av. Libertad"), follow=True)
        self.assertRedirects(respuesta, self.ficha)
        self.assertContains(respuesta, "Se guardaron los cambios de Invernadero A.")
        self.assertEqual(self.recargado().nombre_invernadero, "Invernadero Norte")
        self.assertEqual(self.recargado().direccion.concreta().calle, "Av. Libertad")
        self.assertEqual(RegistroAuditoria.objects.filter(accion=MODIFICACION).count(), 1)

    def test_flujo_principal_el_formulario_arranca_con_los_datos_del_invernadero(self):
        """PROD-MOD-INV, ``INIT['inv-form']``: el formulario muestra el nombre, la dirección, la localidad elegida y el
        personal actuales."""
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Modificar invernadero")
        self.assertContains(respuesta, "Guardar cambios")
        self.assertContains(respuesta, 'value="Invernadero A"')
        self.assertContains(respuesta, 'value="Calle 122"')
        self.assertContains(respuesta, f'<option value="{localidad().pk}" selected>Garupá</option>', html=True)
        self.assertContains(respuesta, f'<option value="{self.capataz.pk}" selected>Nombre Apellido</option>', html=True)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_4_la_persona_asignada_inactiva_se_muestra_con_su_marca(self):
        """PROD-MOD-INV, regla 4: «si la persona asignada está inactiva, se muestra con esa marca hasta que se la
        reemplace»; el resto de las cuentas inactivas no se ofrecen."""
        self.capataz.is_active = False
        self.capataz.save()
        crear_capataz_activo("baja@infoponia.com", activo=False, nombre="Otra", apellido="Baja")
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, "Nombre Apellido — inactivo")
        self.assertNotContains(respuesta, "Otra Baja")

    def test_regla_2_un_cambio_de_personal_muestra_la_ventana_y_no_guarda(self):
        """PROD-MOD-INV, regla 2: guardar un cambio de personal muestra la ventana con quién reemplaza a quién y no
        guarda hasta confirmar; el formulario conserva lo escrito."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com", nombre="Nuevo", apellido="Capataz")
        respuesta = self.client.post(self.url, self.datos(nombre="Invernadero Norte", capataz=nuevo.pk))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Confirmá el cambio de personal")
        self.assertContains(respuesta, "<b>Nuevo Capataz</b> pasa a ser Capataz y reemplaza a <b>Nombre Apellido</b>", html=False)
        self.assertContains(respuesta, 'value="Invernadero Norte"')
        self.assertEqual(self.recargado().nombre_invernadero, "Invernadero A")
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_2_la_ventana_dice_que_un_rol_queda_vacio(self):
        """PROD-MOD-INV, regla 2: si un rol queda vacío, la ventana lo dice y avisa que no se podrán hacer las tareas
        que dependen de él."""
        respuesta = self.client.post(self.url, self.datos(capataz=""))
        self.assertContains(respuesta, "El invernadero queda <b>sin Capataz</b>")
        self.assertContains(respuesta, "no se podrán realizar las tareas que dependen de ese rol")

    def test_regla_2_la_ventana_dice_lo_que_recibe_el_entrante(self):
        """PROD-MOD-INV, regla 2: lo que cuentan los registrantes del punto de extensión aparece en la ventana."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com", nombre="Nuevo", apellido="Capataz")
        with RegistranteDeTraspaso(recibe=[("órdenes a realizar", 3)]).patch():
            respuesta = self.client.post(self.url, self.datos(capataz=nuevo.pk))
        self.assertContains(respuesta, "Recibe 3 órdenes a realizar de este invernadero.")

    def test_regla_2_volver_reenvia_sin_guardar_ni_pedir_confirmar(self):
        """PROD-MOD-INV, regla 2: «Volver al formulario» (el botón «actualizar») no guarda y no vuelve a abrir la ventana."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        respuesta = self.client.post(self.url, self.datos(capataz=nuevo.pk, actualizar="1"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Confirmá el cambio de personal")
        self.assertEqual(self.recargado().capataz_id, self.capataz.pk)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_2_confirmar_guarda_y_va_a_la_ficha(self):
        """PROD-MOD-INV, regla 2: «Confirmar y guardar» (``personal_confirmado``) guarda el cambio de personal."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        respuesta = self.client.post(self.url, self.datos(capataz=nuevo.pk, personal_confirmado="1"))
        self.assertRedirects(respuesta, self.ficha)
        self.assertEqual(self.recargado().capataz_id, nuevo.pk)

    def test_regla_2_la_ventana_se_arma_en_el_servidor_sin_javascript(self):
        """Interfaz: la ventana de confirmación y sus dos botones vienen en la página y envían el formulario del
        invernadero (``form="form-invernadero"``), sin JavaScript propio ni campos ocultos."""
        nuevo = crear_capataz_activo("nuevo.capataz@infoponia.com")
        respuesta = self.client.post(self.url, self.datos(capataz=nuevo.pk))
        self.assertContains(respuesta, 'id="form-invernadero"')
        self.assertContains(respuesta, 'form="form-invernadero" name="actualizar"')
        self.assertContains(respuesta, 'form="form-invernadero" name="personal_confirmado"')
        self.assertNotContains(respuesta, "<script>")

    def test_regla_1_un_error_del_servicio_vuelve_al_formulario(self):
        """PROD-MOD-INV, regla 1: un nombre repetido vuelve al formulario con el error junto al campo y no guarda."""
        crear_invernadero("Invernadero Sur")
        respuesta = self.client.post(self.url, self.datos(nombre="invernadero sur"))
        self.assertContains(respuesta, "Ya existe un invernadero con ese nombre.")
        self.assertEqual(self.recargado().nombre_invernadero, "Invernadero A")

    def test_regla_1_de_urbana_a_rural_desde_la_pantalla(self):
        """PROD-MOD-INV, regla 1 y postcondición a: cambiar el tipo de dirección desde la pantalla crea la dirección nueva."""
        respuesta = self.client.post(self.url, self.datos(tipo_direccion="rural", ruta="Ruta Nacional 14", kilometro="871"))
        self.assertRedirects(respuesta, self.ficha)
        self.assertIsInstance(self.recargado().direccion.concreta(), DireccionRural)

    def test_regla_5_un_invernadero_inactivo_vuelve_a_la_ficha_con_el_motivo(self):
        """PROD-MOD-INV, regla 5 y D-30: abrir o enviar la modificación de uno inactivo lleva a la ficha con el motivo."""
        inactivo = crear_invernadero("Viejo", activo=False)
        url = reverse("maestros:invernadero_modificar", args=[inactivo.pk])
        respuesta = self.client.get(url, follow=True)
        self.assertRedirects(respuesta, reverse("maestros:invernadero", args=[inactivo.pk]))
        self.assertContains(respuesta, "solo se puede reactivar")
        self.assertRedirects(self.client.post(url, self.datos(nombre="Otro")), reverse("maestros:invernadero", args=[inactivo.pk]))
        self.assertEqual(Invernadero.objects.get(pk=inactivo.pk).nombre_invernadero, "Viejo")

    def test_regla_3_actualizar_arma_las_listas_sin_guardar(self):
        """PROD-MOD-INV y regla 3 de PROD-ALT-INV: sin JavaScript, «Actualizar» reenvía el formulario y no guarda nada."""
        respuesta = self.client.post(self.url, self.datos(nombre="Otro", actualizar="1"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self.recargado().nombre_invernadero, "Invernadero A")
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_7_ver_el_formulario_no_audita_ni_cambia_nada(self):
        """Interfaz y SEG-14: abrir la pantalla es solo lectura."""
        self.client.get(self.url)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_pre_a_otros_roles_y_sin_sesion_no_modifican(self):
        """PROD-MOD-INV, precondición a y SEG-13: el Agrónomo y el Capataz reciben 403; sin sesión, a iniciar sesión."""
        for cuenta in (self.agronomo, crear_capataz()):
            self.client.force_login(cuenta)
            with self.subTest(cuenta=cuenta.email):
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(self.client.post(self.url, self.datos(nombre="Otro")).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.recargado().nombre_invernadero, "Invernadero A")

    def test_pre_a_un_invernadero_inexistente_da_404(self):
        """PROD-MOD-INV y D-28: un id que no existe es 404."""
        self.assertEqual(self.client.get(reverse("maestros:invernadero_modificar", args=[0])).status_code, 404)

    def test_regla_4_de_cns_la_ficha_ofrece_asignar_personal(self):
        """PROD-CNS-INV, regla 4: si falta personal, la ficha le ofrece al Gerente ir a modificar para asignarlo."""
        faltante = crear_invernadero("Sin gente")
        respuesta = self.client.get(reverse("maestros:invernadero", args=[faltante.pk]))
        self.assertContains(respuesta, "Asignar personal")
        self.assertContains(respuesta, reverse("maestros:invernadero_modificar", args=[faltante.pk]))

    # ---- Reactivar ----

    def test_flujo_principal_reactiva_y_avisa_que_los_sectores_siguen_inactivos(self):
        """PROD-MOD-INV, reactivación y regla 6: «Reactivar» deja el invernadero activo y avisa que los sectores los
        reactiva el Agrónomo; sin ventana (``ACT['inv-react']`` del prototipo)."""
        inactivo = crear_invernadero("Viejo", activo=False)
        url = reverse("maestros:invernadero_reactivar", args=[inactivo.pk])
        respuesta = self.client.post(url, follow=True)
        self.assertRedirects(respuesta, reverse("maestros:invernadero", args=[inactivo.pk]))
        self.assertContains(respuesta, "Invernadero reactivado. Sus sectores siguen inactivos")
        self.assertTrue(Invernadero.objects.get(pk=inactivo.pk).activo)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=REACTIVACION).count(), 1)

    def test_regla_5_reactivar_uno_activo_vuelve_a_la_ficha_con_el_motivo(self):
        """PROD-MOD-INV: reactivar uno que ya está activo no cambia nada y avisa."""
        respuesta = self.client.post(reverse("maestros:invernadero_reactivar", args=[self.invernadero.pk]), follow=True)
        self.assertContains(respuesta, "El invernadero ya está activo.")
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_7_reactivar_solo_acepta_post(self):
        """Interfaz: reactivar cambia datos, así que un GET da 405 (el botón de la ficha es un formulario POST)."""
        inactivo = crear_invernadero("Viejo", activo=False)
        self.assertEqual(self.client.get(reverse("maestros:invernadero_reactivar", args=[inactivo.pk])).status_code, 405)
        self.assertFalse(Invernadero.objects.get(pk=inactivo.pk).activo)

    def test_pre_a_otros_roles_no_reactivan(self):
        """PROD-MOD-INV, precondición a y SEG-13: el Agrónomo y el Capataz reciben 403."""
        inactivo = crear_invernadero("Viejo", activo=False)
        url = reverse("maestros:invernadero_reactivar", args=[inactivo.pk])
        for cuenta in (self.agronomo, crear_capataz()):
            self.client.force_login(cuenta)
            with self.subTest(cuenta=cuenta.email):
                self.assertEqual(self.client.post(url).status_code, 403)
        self.assertFalse(Invernadero.objects.get(pk=inactivo.pk).activo)
