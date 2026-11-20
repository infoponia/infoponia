# Pruebas de MAE-02a · Alerta (modelo, registro de tipos y API de servicios). Fuentes: docs/modelo/maestros.md (ficha
# Alerta; regla 1 de 8.9; reglas 3 y 4 de 8.22; regla 7 de 8.18), D-38 (Alerta vive en maestros), D-36 (auditoría),
# D-40 (orden de bloqueos) y D-41 (diseño de MAE-02a). Contrato para los demás módulos: docs/api/alertas.md.
#
# Lo que se prueba (maestros/servicios/alertas.py y maestros/alertas.py), tomado del módulo dentro de cada prueba:
#   bloquear_invernadero_para_alertas(invernadero_id) -> Invernadero: bloquea y devuelve, activo o no; 404 si no existe.
#   crear_alerta_de_evento(invernadero_id, tipo, descripcion) -> Alerta | None (None con el invernadero inactivo).
#   asegurar_alerta_de_estado(invernadero_id, tipo, clave="", descripcion=None) -> Alerta | None (idempotente).
#   resolver_alerta_de_estado(invernadero_id, tipo, clave="") -> Alerta | None.
#   resolver_alerta(alerta_id) -> Alerta | None.
#   sincronizar_alertas_de_personal(invernadero, roles=None) -> Cambios(creadas, resueltas). ``roles`` (MAE-02b, D-43):
#       con una lista de atributos, solo asegura y resuelve (y bloquea) esos roles.
#   abrir_alerta(actor, alerta_id) -> Alerta (MAE-02b, regla 7 de 8.18): marca «leída»; PermissionDenied / Http404.
#   resolver_alertas_activas(invernadero), traspasar_alertas_del_agronomo(invernadero, saliente, entrante) y
#   contar_alertas_que_recibe(invernadero, saliente, entrante).
#   Alerta.objects.para(usuario) / .activas() / .no_leidas(); registro de tipos: registrar_tipo_de_alerta, tipo_de_alerta,
#   codigos_con_destinatario.
# ``tipo`` es el código registrado (str). Los tipos falsos se registran con ``tipo_de_alerta_de_prueba``, que los quita
# al salir. Las pruebas de los cuatro servicios del invernadero están en test_prod_{alt,mod,baj}_inv.py; las de
# concurrencia (P1 a P4, ``AlertaConcurrenciaTests``) están al final del archivo (docs/tareas/maestros/MAE-02a-alerta.md).

import time
from unittest import mock

from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, IntegrityError, transaction
from django.http import Http404
from django.test import SimpleTestCase, TestCase, TransactionTestCase, tag
from django.utils import timezone

from core.models import RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez, separar
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from maestros import alertas as registro
from maestros.alertas import Clase, Destinatario, Origen
from maestros.models import Alerta, Invernadero
from maestros.servicios import alertas, invernaderos
from maestros.tests.fabricas import (
    ConGeoref,
    crear_agronomo,
    crear_alerta,
    crear_capataz_activo,
    crear_invernadero,
    crear_invernadero_con_geografia_propia,
    crear_vendedor,
    tipo_de_alerta_de_prueba,
    tipo_falso,
)

ROLES_DE_PERSONAL = ("agronomo", "capataz", "vendedor", "tecnico")
NOMBRES_DE_ROL = {f"sin_{atributo}": nombre for atributo, nombre in Invernadero.ROLES}


class AlertaModeloTests(ConGeoref, TestCase):
    """Restricciones de la base de ``Alerta`` (migración 0003): regla 1 de 8.9, regla 7 de 8.18 y unicidad de las de estado."""

    def setUp(self):
        self.invernadero = crear_invernadero("Invernadero A")

    def test_regla_8_9_1_la_base_rechaza_una_alerta_sin_destinatario(self):
        """Regla 1 de 8.9: toda alerta tiene al menos un destinatario (el Gerente o el Agrónomo)."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            crear_alerta(self.invernadero, para_gerente=False, agronomo=None)

    def test_regla_8_9_1_alcanza_con_el_agronomo_o_con_el_gerente(self):
        """Regla 1 de 8.9: con el Agrónomo solo, o con el Gerente solo, o con los dos, la base acepta la alerta."""
        agronomo = crear_agronomo()
        crear_alerta(self.invernadero, para_gerente=False, agronomo=agronomo)
        crear_alerta(self.invernadero, para_gerente=True, agronomo=None)
        crear_alerta(self.invernadero, para_gerente=True, agronomo=agronomo)
        self.assertEqual(Alerta.objects.count(), 3)

    def test_regla_8_18_7_nace_activa_y_no_leida(self):
        """Regla 7 de 8.18: ``estadoAlerta`` nace «activa» y ``estadoLecturaAlerta`` nace «no leída»."""
        alerta = crear_alerta(self.invernadero)
        self.assertEqual(alerta.estado_alerta, "activa")
        self.assertEqual(alerta.estado_lectura_alerta, "no_leida")
        self.assertIsNone(alerta.fecha_resolucion)

    def test_regla_8_18_7_la_base_rechaza_resuelta_sin_fecha(self):
        """Regla 7 de 8.18: al pasar a resuelta se carga ``fechaResolucion``; una resuelta sin fecha no existe."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            crear_alerta(self.invernadero, estado_alerta="resuelta")

    def test_regla_8_18_7_la_base_rechaza_activa_con_fecha_de_resolucion(self):
        """Regla 7 de 8.18: la fecha de resolución se carga solo al resolver; una activa no la tiene."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            crear_alerta(self.invernadero, fecha_resolucion=timezone.now())

    def test_regla_8_18_7_los_dos_estados_son_independientes(self):
        """Regla 7 de 8.18: «una alerta puede estar leída y seguir activa»; y una resuelta puede estar sin leer."""
        leida_y_activa = crear_alerta(self.invernadero, estado_lectura_alerta="leida")
        resuelta_sin_leer = crear_alerta(self.invernadero, resuelta=True)
        self.assertEqual((leida_y_activa.estado_alerta, leida_y_activa.estado_lectura_alerta), ("activa", "leida"))
        self.assertEqual(
            (resuelta_sin_leer.estado_alerta, resuelta_sin_leer.estado_lectura_alerta), ("resuelta", "no_leida")
        )

    def test_d41_la_base_rechaza_dos_alertas_de_estado_activas_iguales(self):
        """D-41: a lo sumo una alerta de estado activa por invernadero, tipo y clave (índice parcial, respaldo del bloqueo)."""
        crear_alerta(self.invernadero, tipo_alerta="sin_capataz", clave_estado="")
        with self.assertRaises(IntegrityError), transaction.atomic():
            crear_alerta(self.invernadero, tipo_alerta="sin_capataz", clave_estado="")

    def test_d41_la_unicidad_no_alcanza_a_resueltas_otras_claves_otros_invernaderos_ni_eventos(self):
        """D-41: se puede tener una resuelta y una activa del mismo estado; la misma condición con otra clave o en otro
        invernadero; y todas las alertas de evento (``clave_estado`` nula) que se quiera."""
        otro = crear_invernadero("Invernadero B")
        crear_alerta(self.invernadero, tipo_alerta="sin_capataz", clave_estado="", resuelta=True)
        crear_alerta(self.invernadero, tipo_alerta="sin_capataz", clave_estado="")
        crear_alerta(self.invernadero, tipo_alerta="sin_capataz", clave_estado="lote:1")
        crear_alerta(otro, tipo_alerta="sin_capataz", clave_estado="")
        crear_alerta(self.invernadero, tipo_alerta="evento")
        crear_alerta(self.invernadero, tipo_alerta="evento")
        self.assertEqual(Alerta.objects.count(), 6)

    def test_d41_el_agronomo_de_la_alerta_es_el_mismo_modelo_que_el_del_invernadero(self):
        """D-41 (confirmación del plan): ``Alerta.agronomo`` apunta al mismo modelo que ``Invernadero.agronomo``."""
        self.assertIs(
            Alerta._meta.get_field("agronomo").related_model, Invernadero._meta.get_field("agronomo").related_model
        )

    def test_d41_la_descripcion_es_el_texto_de_la_alerta_para_la_auditoria(self):
        """D-36: el texto de una referencia sale del ``__str__``; el de la alerta es su descripción."""
        alerta = crear_alerta(self.invernadero, descripcion_alerta="Invernadero A sin Capataz activo")
        self.assertEqual(str(alerta), "Invernadero A sin Capataz activo")


class AlertaAlcanceTests(ConGeoref, TestCase):
    """``Alerta.objects.para(usuario)``: el único lugar del alcance (D-28; regla 1 de 8.9). ``activas`` y ``no_leidas``."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.otro_agronomo = crear_agronomo("otro.agronomo@infoponia.com")
        self.invernadero = crear_invernadero("Invernadero A", agronomo=self.agronomo)
        self.del_gerente = crear_alerta(self.invernadero, para_gerente=True)
        self.del_agronomo = crear_alerta(self.invernadero, para_gerente=False, agronomo=self.agronomo)
        self.de_los_dos = crear_alerta(self.invernadero, para_gerente=True, agronomo=self.agronomo)
        self.del_otro = crear_alerta(self.invernadero, para_gerente=False, agronomo=self.otro_agronomo)

    def test_regla_8_9_1_el_gerente_activo_recibe_las_marcadas_para_gerente(self):
        """Regla 1 de 8.9 (R007): el Gerente activo recibe las alertas ``para_gerente``."""
        self.assertCountEqual(Alerta.objects.para(self.gerente), [self.del_gerente, self.de_los_dos])

    def test_regla_8_9_1_el_agronomo_activo_recibe_las_suyas(self):
        """Regla 1 de 8.9 (R049): el Agrónomo activo recibe las suyas y no las del Gerente ni las de otro Agrónomo."""
        self.assertCountEqual(Alerta.objects.para(self.agronomo), [self.del_agronomo, self.de_los_dos])
        self.assertCountEqual(Alerta.objects.para(self.otro_agronomo), [self.del_otro])

    def test_regla_8_9_1_otros_roles_cuentas_inactivas_y_sin_actor_no_reciben_ninguna(self):
        """Regla 1 de 8.9: «otros roles reciben notificaciones, no alertas». Una cuenta inactiva o ``None``, tampoco."""
        inactivo = crear_agronomo("inactivo@infoponia.com", activo=False)
        crear_alerta(self.invernadero, para_gerente=False, agronomo=inactivo)
        for usuario in (crear_capataz(), crear_administrador(), inactivo, None):
            with self.subTest(usuario=getattr(usuario, "email", None)):
                self.assertEqual(list(Alerta.objects.para(usuario)), [])

    def test_regla_8_18_7_activas_deja_solo_las_activas(self):
        """Regla 7 de 8.18: las resueltas ya no son activas."""
        resuelta = crear_alerta(self.invernadero, resuelta=True)
        activas = Alerta.objects.activas()
        self.assertNotIn(resuelta, activas)
        self.assertCountEqual(activas, [self.del_gerente, self.del_agronomo, self.de_los_dos, self.del_otro])

    def test_regla_8_18_7_no_leidas_deja_solo_las_no_leidas_aunque_sigan_activas(self):
        """Regla 7 de 8.18: la lectura es independiente del estado: una leída sigue activa pero no cuenta como no leída."""
        Alerta.objects.filter(pk=self.del_gerente.pk).update(estado_lectura_alerta="leida")
        self.assertNotIn(self.del_gerente, Alerta.objects.no_leidas())
        self.assertIn(self.del_gerente, Alerta.objects.activas())
        self.assertIn(self.del_agronomo, Alerta.objects.no_leidas())

    def test_d41_para_se_encadena_con_activas_y_no_leidas(self):
        """D-41: ``para(usuario).no_leidas()`` es lo que cuenta la campana (docs/api/alertas.md)."""
        crear_alerta(self.invernadero, para_gerente=True, resuelta=True)
        self.assertCountEqual(Alerta.objects.para(self.gerente).activas().no_leidas(), [self.del_gerente, self.de_los_dos])


class AlertaTiposTests(SimpleTestCase):
    """Registro de tipos de alerta (D-41, D7, regla A4 de D-37): ``maestros/alertas.py``."""

    def test_d41_maestros_registra_los_cuatro_tipos_de_personal(self):
        """D11 y regla 3 de 8.22: «invernadero sin {rol} activo» son de estado, de severidad «advertencia» y van solo al Gerente."""
        for atributo in ROLES_DE_PERSONAL:
            with self.subTest(rol=atributo):
                tipo = registro.tipo_de_alerta(f"sin_{atributo}")
                self.assertEqual(tipo.destinatario, Destinatario.GERENTE)
                self.assertEqual(tipo.clase, Clase.ESTADO)
                self.assertEqual(tipo.severidad, Alerta.Severidad.ADVERTENCIA)
                self.assertIsNone(tipo.origen)

    def test_d41_registrar_dos_veces_la_misma_definicion_no_falla(self):
        """D7 (corrección 2): ``ready()`` puede correr más de una vez; registrar la misma definición es idempotente."""
        tipo = tipo_falso("prueba_doble")
        with mock.patch.dict(registro._TIPOS):
            registro.registrar_tipo_de_alerta(tipo)
            registro.registrar_tipo_de_alerta(tipo)
            registro.registrar_tipo_de_alerta(tipo_falso("prueba_doble"))  # igual definición, otra instancia
            self.assertEqual(registro.tipo_de_alerta("prueba_doble"), tipo)

    def test_d41_un_codigo_repetido_con_otra_definicion_falla(self):
        """D7 (corrección 2): solo falla un código repetido con una definición distinta."""
        with mock.patch.dict(registro._TIPOS):
            registro.registrar_tipo_de_alerta(tipo_falso("prueba_doble", destinatario=Destinatario.GERENTE))
            with self.assertRaises(ValueError):
                registro.registrar_tipo_de_alerta(tipo_falso("prueba_doble", destinatario=Destinatario.AGRONOMO_O_GERENTE))

    def test_d41_un_tipo_no_registrado_se_rechaza(self):
        """D7: un código que ninguna app registró es un ``ValueError`` (la base no valida el código: lo valida el registro)."""
        with self.assertRaises(ValueError):
            registro.tipo_de_alerta("no_existe")

    def test_d41_el_tipo_de_prueba_se_quita_al_salir(self):
        """Corrección 2: ``tipo_de_alerta_de_prueba`` no contamina el registro global, ni siquiera si la prueba falla."""
        with self.assertRaises(ValueError):
            registro.tipo_de_alerta("prueba_efimero")
        with self.assertRaises(KeyError):
            with tipo_de_alerta_de_prueba(tipo_falso("prueba_efimero")):
                self.assertEqual(registro.tipo_de_alerta("prueba_efimero").codigo, "prueba_efimero")
                raise KeyError("la prueba falla")
        with self.assertRaises(ValueError):
            registro.tipo_de_alerta("prueba_efimero")

    def test_d41_codigos_con_destinatario_filtra_por_destinatario(self):
        """D4 (D-41): ``codigos_con_destinatario`` es lo que usa el traspaso para filtrar por el destinatario del tipo."""
        with tipo_de_alerta_de_prueba(
            tipo_falso("prueba_o", destinatario=Destinatario.AGRONOMO_O_GERENTE),
            tipo_falso("prueba_y", destinatario=Destinatario.AGRONOMO_Y_GERENTE),
        ):
            self.assertIn("prueba_o", registro.codigos_con_destinatario(Destinatario.AGRONOMO_O_GERENTE))
            self.assertNotIn("prueba_o", registro.codigos_con_destinatario(Destinatario.AGRONOMO_Y_GERENTE))
            self.assertIn("prueba_y", registro.codigos_con_destinatario(Destinatario.AGRONOMO_Y_GERENTE))
            self.assertIn("sin_capataz", registro.codigos_con_destinatario(Destinatario.GERENTE))

    def test_d41_el_origen_es_solo_una_declaracion_del_tipo(self):
        """C5 y D-38: el tipo declara su origen (``Origen``); el enlace lo crea la app de origen, no ``maestros``."""
        tipo = tipo_falso("prueba_origen", origen=Origen.TELEMETRIA)
        with tipo_de_alerta_de_prueba(tipo):
            self.assertEqual(registro.tipo_de_alerta("prueba_origen").origen, Origen.TELEMETRIA)


class AlertaServicioTests(ConGeoref, TestCase):
    """API de ``maestros/servicios/alertas.py`` (D-41). Se corre dentro de la transacción de ``TestCase``."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Invernadero A", agronomo=self.agronomo)
        self.tipo_evento = tipo_falso("prueba_evento")
        self.tipo_estado = tipo_falso("prueba_estado", clase=Clase.ESTADO)

    def inactivar(self):
        Invernadero.objects.filter(pk=self.invernadero.pk).update(estado_invernadero="inactivo")

    # ---- Bloqueo ----

    def test_d40_bloquear_para_alertas_devuelve_el_invernadero_activo(self):
        """D-40 y D-41: bloquea y devuelve el invernadero, releído."""
        with transaction.atomic():
            self.assertEqual(alertas.bloquear_invernadero_para_alertas(self.invernadero.pk), self.invernadero)

    def test_post_e_bloquear_para_alertas_no_rechaza_un_invernadero_inactivo(self):
        """Post e de PROD-BAJ-INV («dejó de generar alertas», no es un error): a diferencia de
        ``bloquear_invernadero_activo``, devuelve el inactivo sin lanzar."""
        self.inactivar()
        with transaction.atomic():
            invernadero = alertas.bloquear_invernadero_para_alertas(self.invernadero.pk)
        self.assertFalse(invernadero.activo)

    def test_d40_bloquear_para_alertas_un_invernadero_inexistente_da_404(self):
        """D-40: un id que no existe es ``Http404``."""
        with self.assertRaises(Http404), transaction.atomic():
            alertas.bloquear_invernadero_para_alertas(0)

    # ---- Alertas de evento ----

    def test_d41_crear_alerta_de_evento_la_crea_activa_no_leida_y_con_la_severidad_del_tipo(self):
        """D-41: una alerta de evento nace activa y no leída (regla 7 de 8.18), con la severidad del tipo y sin clave."""
        with tipo_de_alerta_de_prueba(self.tipo_evento):
            alerta = alertas.crear_alerta_de_evento(self.invernadero.pk, "prueba_evento", "Lectura fuera de rango")
        self.assertEqual(alerta.invernadero_id, self.invernadero.pk)
        self.assertEqual(alerta.tipo_alerta, "prueba_evento")
        self.assertEqual(alerta.descripcion_alerta, "Lectura fuera de rango")
        self.assertEqual(alerta.nivel_severidad, Alerta.Severidad.ADVERTENCIA)
        self.assertEqual((alerta.estado_alerta, alerta.estado_lectura_alerta), ("activa", "no_leida"))
        self.assertIsNone(alerta.clave_estado)
        self.assertIsNone(alerta.fecha_resolucion)

    def test_d41_las_de_evento_se_acumulan(self):
        """D-41: dos lecturas fuera de rango son dos alertas (la unicidad es solo de las de estado)."""
        with tipo_de_alerta_de_prueba(self.tipo_evento):
            primera = alertas.crear_alerta_de_evento(self.invernadero.pk, "prueba_evento", "Una")
            segunda = alertas.crear_alerta_de_evento(self.invernadero.pk, "prueba_evento", "Otra")
        self.assertNotEqual(primera.pk, segunda.pk)

    def test_post_e_un_invernadero_inactivo_no_genera_alertas_de_evento(self):
        """Post e de PROD-BAJ-INV: «el invernadero dejó de generar alertas»: devuelve ``None`` y no crea nada."""
        self.inactivar()
        with tipo_de_alerta_de_prueba(self.tipo_evento):
            self.assertIsNone(alertas.crear_alerta_de_evento(self.invernadero.pk, "prueba_evento", "Algo"))
        self.assertFalse(Alerta.objects.exists())

    def test_d41_un_tipo_no_registrado_se_rechaza_al_crear_asegurar_y_resolver(self):
        """D7: la API rechaza un código no registrado con ``ValueError`` y no crea nada."""
        for llamada in (
            lambda: alertas.crear_alerta_de_evento(self.invernadero.pk, "no_existe", "x"),
            lambda: alertas.asegurar_alerta_de_estado(self.invernadero.pk, "no_existe"),
            lambda: alertas.resolver_alerta_de_estado(self.invernadero.pk, "no_existe"),
        ):
            with self.subTest(), self.assertRaises(ValueError):
                llamada()
        self.assertFalse(Alerta.objects.exists())

    # ---- Destinatarios al crear (regla 1 de 8.9 y regla 4 de 8.22) ----

    def crear(self, destinatario):
        tipo = tipo_falso("prueba_destino", destinatario=destinatario)
        with tipo_de_alerta_de_prueba(tipo):
            return alertas.crear_alerta_de_evento(self.invernadero.pk, "prueba_destino", "x")

    def test_regla_8_22_4_agronomo_o_gerente_con_agronomo_activo_va_al_agronomo(self):
        """Regla 4 de 8.22: las alertas van al Agrónomo del invernadero; al Gerente, solo mientras no haya uno activo."""
        alerta = self.crear(Destinatario.AGRONOMO_O_GERENTE)
        self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (self.agronomo.pk, False))

    def test_regla_8_22_4_agronomo_o_gerente_sin_agronomo_activo_va_al_gerente(self):
        """Regla 4 de 8.22 y MD-61: sin Agrónomo (o con el Agrónomo inactivo) la alerta va al Gerente."""
        sin_agronomo = crear_invernadero("Sin agrónomo")
        inactivo = crear_agronomo("inactivo@infoponia.com", activo=False)
        con_inactivo = crear_invernadero("Con inactivo", agronomo=inactivo)
        for invernadero in (sin_agronomo, con_inactivo):
            with self.subTest(invernadero=invernadero.nombre_invernadero):
                tipo = tipo_falso("prueba_destino", destinatario=Destinatario.AGRONOMO_O_GERENTE)
                with tipo_de_alerta_de_prueba(tipo):
                    alerta = alertas.crear_alerta_de_evento(invernadero.pk, "prueba_destino", "x")
                self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (None, True))

    def test_regla_8_22_4_agronomo_y_gerente_va_a_los_dos(self):
        """Regla 2 de 8.9 (umbral de merma): «al Agrónomo y al Gerente»."""
        alerta = self.crear(Destinatario.AGRONOMO_Y_GERENTE)
        self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (self.agronomo.pk, True))

    def test_regla_8_22_4_agronomo_y_gerente_sin_agronomo_va_solo_al_gerente(self):
        """Regla 1 de 8.9: sin Agrónomo activo queda el Gerente, para que haya al menos un destinatario."""
        self.agronomo.is_active = False
        self.agronomo.save()
        alerta = self.crear(Destinatario.AGRONOMO_Y_GERENTE)
        self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (None, True))

    def test_regla_8_22_4_tipo_gerente_no_va_al_agronomo(self):
        """D11 y regla 3 de 8.22: un tipo de destinatario ``GERENTE`` no va al Agrónomo aunque haya uno activo."""
        alerta = self.crear(Destinatario.GERENTE)
        self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (None, True))

    # ---- Alertas de estado ----

    def test_d41_asegurar_crea_la_alerta_de_estado_con_su_clave(self):
        """D-41: crea la alerta de estado, activa, con la clave que se pidió (``""`` por omisión)."""
        with tipo_de_alerta_de_prueba(self.tipo_estado):
            alerta = alertas.asegurar_alerta_de_estado(self.invernadero.pk, "prueba_estado")
            con_clave = alertas.asegurar_alerta_de_estado(self.invernadero.pk, "prueba_estado", clave="lote:7")
        self.assertEqual((alerta.estado_alerta, alerta.clave_estado), ("activa", ""))
        self.assertEqual(con_clave.clave_estado, "lote:7")
        self.assertNotEqual(alerta.pk, con_clave.pk)

    def test_d41_asegurar_es_idempotente(self):
        """D-41: asegurar dos veces devuelve la misma alerta y no crea otra (a lo sumo una activa por tipo y clave)."""
        with tipo_de_alerta_de_prueba(self.tipo_estado):
            primera = alertas.asegurar_alerta_de_estado(self.invernadero.pk, "prueba_estado")
            segunda = alertas.asegurar_alerta_de_estado(self.invernadero.pk, "prueba_estado")
        self.assertEqual(primera.pk, segunda.pk)
        self.assertEqual(Alerta.objects.filter(tipo_alerta="prueba_estado").count(), 1)

    def test_d41_asegurar_usa_la_descripcion_pedida_o_por_omision_el_nombre_del_tipo(self):
        """D-41 (decisión 2): sin descripción, la de la alerta es solo el nombre del tipo, sin el del invernadero (que ya
        está en la FK y quedaría viejo si se lo renombra); con descripción, esa."""
        with tipo_de_alerta_de_prueba(self.tipo_estado):
            por_omision = alertas.asegurar_alerta_de_estado(self.invernadero.pk, "prueba_estado")
            pedida = alertas.asegurar_alerta_de_estado(self.invernadero.pk, "prueba_estado", "k", "Mi descripción")
        self.assertEqual(por_omision.descripcion_alerta, "Tipo prueba_estado")
        self.assertNotIn("Invernadero A", por_omision.descripcion_alerta)
        self.assertEqual(pedida.descripcion_alerta, "Mi descripción")

    def test_d41_asegurar_con_un_invernadero_inactivo_devuelve_none_y_no_crea(self):
        """Post e de PROD-BAJ-INV: un invernadero inactivo no genera alertas de estado."""
        self.inactivar()
        with tipo_de_alerta_de_prueba(self.tipo_estado):
            self.assertIsNone(alertas.asegurar_alerta_de_estado(self.invernadero.pk, "prueba_estado"))
        self.assertFalse(Alerta.objects.exists())

    def test_d41_resolver_la_de_estado_la_pasa_a_resuelta_con_su_fecha(self):
        """Regla 7 de 8.18: al resolverse se carga ``fechaResolucion``; no toca la lectura."""
        with tipo_de_alerta_de_prueba(self.tipo_estado):
            creada = alertas.asegurar_alerta_de_estado(self.invernadero.pk, "prueba_estado")
            antes = time.time()
            resuelta = alertas.resolver_alerta_de_estado(self.invernadero.pk, "prueba_estado")
        self.assertEqual(resuelta.pk, creada.pk)
        self.assertEqual(resuelta.estado_alerta, "resuelta")
        self.assertIsNotNone(resuelta.fecha_resolucion)
        self.assertGreaterEqual(resuelta.fecha_resolucion.timestamp(), antes - 5)
        self.assertEqual(resuelta.estado_lectura_alerta, "no_leida")

    def test_d41_resolver_sin_alerta_activa_devuelve_none(self):
        """D-41: si no había una activa (ni siquiera una resuelta) devuelve ``None`` y no falla."""
        with tipo_de_alerta_de_prueba(self.tipo_estado):
            self.assertIsNone(alertas.resolver_alerta_de_estado(self.invernadero.pk, "prueba_estado"))
            alertas.asegurar_alerta_de_estado(self.invernadero.pk, "prueba_estado")
            alertas.resolver_alerta_de_estado(self.invernadero.pk, "prueba_estado")
            self.assertIsNone(alertas.resolver_alerta_de_estado(self.invernadero.pk, "prueba_estado"))

    def test_d41_resolver_solo_resuelve_el_tipo_y_la_clave_pedidos(self):
        """D-41: resolver una condición no toca las demás del invernadero."""
        with tipo_de_alerta_de_prueba(self.tipo_estado):
            alertas.asegurar_alerta_de_estado(self.invernadero.pk, "prueba_estado", "a")
            otra = alertas.asegurar_alerta_de_estado(self.invernadero.pk, "prueba_estado", "b")
            alertas.resolver_alerta_de_estado(self.invernadero.pk, "prueba_estado", "a")
        otra.refresh_from_db()
        self.assertEqual(otra.estado_alerta, "activa")

    def test_d41_despues_de_resolver_la_condicion_puede_volver_a_darse(self):
        """D-41: la unicidad es solo entre las activas: la misma condición puede volver a alertar después de resolverse."""
        with tipo_de_alerta_de_prueba(self.tipo_estado):
            primera = alertas.asegurar_alerta_de_estado(self.invernadero.pk, "prueba_estado")
            alertas.resolver_alerta_de_estado(self.invernadero.pk, "prueba_estado")
            segunda = alertas.asegurar_alerta_de_estado(self.invernadero.pk, "prueba_estado")
        self.assertNotEqual(primera.pk, segunda.pk)
        self.assertEqual(segunda.estado_alerta, "activa")

    def test_d41_resolver_alerta_resuelve_una_de_evento_y_es_idempotente(self):
        """D-41: ``resolver_alerta`` resuelve una de evento con su fecha; resolver otra vez devuelve ``None``."""
        with tipo_de_alerta_de_prueba(self.tipo_evento):
            alerta = alertas.crear_alerta_de_evento(self.invernadero.pk, "prueba_evento", "x")
        resuelta = alertas.resolver_alerta(alerta.pk)
        self.assertEqual(resuelta.estado_alerta, "resuelta")
        self.assertIsNotNone(resuelta.fecha_resolucion)
        self.assertIsNone(alertas.resolver_alerta(alerta.pk))

    def test_d41_resolver_alerta_inexistente_da_404(self):
        """D-41: un id que no existe es ``Http404``."""
        with self.assertRaises(Http404):
            alertas.resolver_alerta(0)

    # ---- Resolver todas (post e de PROD-BAJ-INV) ----

    def test_post_e_resolver_alertas_activas_resuelve_de_estado_y_de_evento_y_devuelve_las_que_cambio(self):
        """Post e de PROD-BAJ-INV: todas las activas del invernadero pasan a «resuelta» (de estado y de evento); las ya
        resueltas conservan su fecha; las de otro invernadero no se tocan."""
        otro = crear_invernadero("Invernadero B")
        de_estado = crear_alerta(self.invernadero, tipo_alerta="sin_capataz", clave_estado="")
        de_evento = crear_alerta(self.invernadero)
        vieja = crear_alerta(self.invernadero, resuelta=True)
        fecha_vieja = vieja.fecha_resolucion
        ajena = crear_alerta(otro)
        with transaction.atomic():
            cambiadas = alertas.resolver_alertas_activas(self.invernadero)
        self.assertCountEqual(cambiadas, [de_estado, de_evento])
        for alerta in (de_estado, de_evento, vieja, ajena):
            alerta.refresh_from_db()
        self.assertEqual((de_estado.estado_alerta, de_evento.estado_alerta), ("resuelta", "resuelta"))
        self.assertIsNotNone(de_estado.fecha_resolucion)
        self.assertEqual(vieja.fecha_resolucion, fecha_vieja)
        self.assertEqual(ajena.estado_alerta, "activa")

    # ---- sincronizar_alertas_de_personal (post d de ALT y MOD, post e de MOD; regla 3 de 8.22 y MD-87) ----

    def sincronizar(self, invernadero=None):
        with transaction.atomic():
            return alertas.sincronizar_alertas_de_personal(invernadero or Invernadero.objects.get(pk=self.invernadero.pk))

    def activas_de(self, invernadero=None):
        return sorted(
            Alerta.objects.filter(invernadero=invernadero or self.invernadero, estado_alerta="activa").values_list(
                "tipo_alerta", flat=True
            )
        )

    def test_regla_8_22_3_crea_una_alerta_por_cada_rol_sin_asignar_para_el_gerente(self):
        """Regla 3 de 8.22 y MD-87: una alerta «sin {rol} activo» por cada rol sin asignar, para el Gerente. El Técnico no
        cuenta sin sistema IoT (regla 5 de PROD-ALT-INV)."""
        cambios = self.sincronizar()  # solo tiene Agrónomo
        self.assertEqual(self.activas_de(), ["sin_capataz", "sin_vendedor"])
        self.assertCountEqual([a.tipo_alerta for a in cambios.creadas], ["sin_capataz", "sin_vendedor"])
        self.assertEqual(list(cambios.resueltas), [])
        for alerta in Alerta.objects.all():
            self.assertEqual((alerta.para_gerente, alerta.agronomo_id, alerta.clave_estado), (True, None, ""))
            self.assertEqual(alerta.nivel_severidad, Alerta.Severidad.ADVERTENCIA)
            # D-41 (decisión 2): la descripción es el nombre del tipo, sin el del invernadero.
            self.assertEqual(alerta.descripcion_alerta, f"Invernadero sin {NOMBRES_DE_ROL[alerta.tipo_alerta]} activo")
            self.assertNotIn("Invernadero A", alerta.descripcion_alerta)

    def test_regla_8_22_3_con_sistema_iot_sin_tecnico_crea_la_alerta_del_tecnico(self):
        """Regla 3 de 8.22: la del Técnico solo con ``SistemaIoT`` (hoy no existe: se simula ``tiene_sistema_iot``)."""
        with mock.patch.object(Invernadero, "tiene_sistema_iot", return_value=True):
            self.sincronizar()
        self.assertIn("sin_tecnico", self.activas_de())

    def test_regla_8_22_3_con_el_personal_completo_no_crea_alertas(self):
        """Regla 3 de 8.22: con los tres roles activos (y sin IoT) no hay nada que alertar."""
        completo = crear_invernadero(
            "Completo",
            agronomo=crear_agronomo("a2@infoponia.com"),
            capataz=crear_capataz_activo(),
            vendedor=crear_vendedor(),
        )
        cambios = self.sincronizar(completo)
        self.assertEqual((list(cambios.creadas), list(cambios.resueltas)), ([], []))
        self.assertFalse(Alerta.objects.exists())

    def test_regla_8_22_3_una_persona_inactiva_cuenta_como_faltante(self):
        """Regla 3 de 8.22: cuando el asignado pasa a inactivo, el rol queda sin una persona activa y alerta."""
        inactivo = crear_capataz_activo(activo=False)
        invernadero = crear_invernadero("Con inactivo", agronomo=self.agronomo, capataz=inactivo, vendedor=crear_vendedor())
        self.sincronizar(invernadero)
        self.assertEqual(self.activas_de(invernadero), ["sin_capataz"])

    def test_regla_8_22_3_resuelve_la_alerta_del_rol_que_ya_tiene_una_persona_activa(self):
        """Regla 3 de 8.22: «se resuelve al asignar al nuevo»; las de los roles que siguen vacíos siguen activas."""
        self.sincronizar()
        Invernadero.objects.filter(pk=self.invernadero.pk).update(capataz=crear_capataz_activo())
        cambios = self.sincronizar()
        self.assertEqual([a.tipo_alerta for a in cambios.resueltas], ["sin_capataz"])
        self.assertEqual(self.activas_de(), ["sin_vendedor"])
        resuelta = Alerta.objects.get(tipo_alerta="sin_capataz")
        self.assertEqual(resuelta.estado_alerta, "resuelta")
        self.assertIsNotNone(resuelta.fecha_resolucion)

    def test_d41_sincronizar_es_idempotente(self):
        """D-41: sincronizar dos veces no crea alertas repetidas y la segunda no cambia nada."""
        self.sincronizar()
        cambios = self.sincronizar()
        self.assertEqual((list(cambios.creadas), list(cambios.resueltas)), ([], []))
        self.assertEqual(Alerta.objects.count(), 2)

    def test_post_e_sincronizar_un_invernadero_inactivo_no_crea_alertas(self):
        """Post e de PROD-BAJ-INV: un invernadero inactivo «dejó de generar alertas»."""
        self.inactivar()
        cambios = self.sincronizar()
        self.assertEqual((list(cambios.creadas), list(cambios.resueltas)), ([], []))
        self.assertFalse(Alerta.objects.exists())

    # ---- Traspaso de las alertas del Agrónomo (MD-60, regla 3 de PROD-MOD-INV, D4) ----

    def alerta_de(self, destinatario, **campos):
        """Una alerta activa de un tipo falso del ``destinatario``, creada directo en la base."""
        return crear_alerta(self.invernadero, tipo_alerta=f"prueba_{destinatario.value}", **campos)

    def traspasar(self, saliente, entrante):
        with transaction.atomic():
            return alertas.traspasar_alertas_del_agronomo(
                Invernadero.objects.get(pk=self.invernadero.pk), saliente, entrante
            )

    def tipos_de_traspaso(self):
        return tipo_de_alerta_de_prueba(
            tipo_falso("prueba_agronomo_o_gerente", destinatario=Destinatario.AGRONOMO_O_GERENTE),
            tipo_falso("prueba_agronomo_y_gerente", destinatario=Destinatario.AGRONOMO_Y_GERENTE),
            tipo_falso("prueba_gerente", destinatario=Destinatario.GERENTE),
        )

    def test_post_b_las_activas_del_saliente_pasan_al_entrante_y_se_devuelven(self):
        """MD-60 y post b de PROD-MOD-INV: las alertas activas del Agrónomo saliente pasan al entrante. Las resueltas y las
        de otro invernadero o de otro Agrónomo no se mueven; la lectura no cambia."""
        entrante = crear_agronomo("nuevo@infoponia.com")
        otro_agronomo = crear_agronomo("otro@infoponia.com")
        otro_invernadero = crear_invernadero("Invernadero B", agronomo=self.agronomo)
        propia = self.alerta_de(Destinatario.AGRONOMO_O_GERENTE, para_gerente=False, agronomo=self.agronomo,
                                estado_lectura_alerta="leida")
        de_los_dos = self.alerta_de(Destinatario.AGRONOMO_Y_GERENTE, para_gerente=True, agronomo=self.agronomo)
        resuelta = self.alerta_de(Destinatario.AGRONOMO_O_GERENTE, para_gerente=False, agronomo=self.agronomo,
                                  resuelta=True)
        ajena_de_invernadero = crear_alerta(otro_invernadero, para_gerente=False, agronomo=self.agronomo)
        ajena_de_agronomo = self.alerta_de(Destinatario.AGRONOMO_O_GERENTE, para_gerente=False, agronomo=otro_agronomo)
        with self.tipos_de_traspaso():
            cambiadas = self.traspasar(self.agronomo, entrante)
        self.assertCountEqual(cambiadas, [propia, de_los_dos])
        for alerta in (propia, de_los_dos, resuelta, ajena_de_invernadero, ajena_de_agronomo):
            alerta.refresh_from_db()
        self.assertEqual((propia.agronomo, de_los_dos.agronomo), (entrante, entrante))
        self.assertEqual(propia.estado_lectura_alerta, "leida")
        self.assertEqual(resuelta.agronomo_id, self.agronomo.pk)
        self.assertEqual(ajena_de_invernadero.agronomo_id, self.agronomo.pk)
        self.assertEqual(ajena_de_agronomo.agronomo_id, otro_agronomo.pk)

    def test_regla_3_sin_entrante_las_de_agronomo_o_gerente_quedan_para_el_gerente(self):
        """Regla 3 de PROD-MOD-INV y MD-61: quitado el Agrónomo, sus alertas ``AGRONOMO_O_GERENTE`` pasan al Gerente; las
        ``AGRONOMO_Y_GERENTE`` quedan solo con el Gerente (sin Agrónomo); las de tipo ``GERENTE`` no se tocan."""
        o_gerente = self.alerta_de(Destinatario.AGRONOMO_O_GERENTE, para_gerente=False, agronomo=self.agronomo)
        y_gerente = self.alerta_de(Destinatario.AGRONOMO_Y_GERENTE, para_gerente=True, agronomo=self.agronomo)
        de_gerente = self.alerta_de(Destinatario.GERENTE, para_gerente=True)
        with self.tipos_de_traspaso():
            cambiadas = self.traspasar(self.agronomo, None)
        self.assertCountEqual(cambiadas, [o_gerente, y_gerente])
        for alerta in (o_gerente, y_gerente, de_gerente):
            alerta.refresh_from_db()
            self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (None, True))

    def test_d41_con_entrante_las_que_fueron_al_gerente_por_falta_de_agronomo_pasan_a_el(self):
        """D4 (i): al asignar un Agrónomo, ``AGRONOMO_O_GERENTE`` → ``agronomo=entrante, para_gerente=False``;
        ``AGRONOMO_Y_GERENTE`` → ``agronomo=entrante`` y ``para_gerente`` sigue; ``GERENTE`` no se toca."""
        entrante = crear_agronomo("nuevo@infoponia.com")
        Invernadero.objects.filter(pk=self.invernadero.pk).update(agronomo=None)
        o_gerente = self.alerta_de(Destinatario.AGRONOMO_O_GERENTE, para_gerente=True)
        y_gerente = self.alerta_de(Destinatario.AGRONOMO_Y_GERENTE, para_gerente=True)
        de_gerente = self.alerta_de(Destinatario.GERENTE, para_gerente=True)
        with self.tipos_de_traspaso():
            cambiadas = self.traspasar(None, entrante)
        self.assertCountEqual(cambiadas, [o_gerente, y_gerente])
        for alerta in (o_gerente, y_gerente, de_gerente):
            alerta.refresh_from_db()
        self.assertEqual((o_gerente.agronomo, o_gerente.para_gerente), (entrante, False))
        self.assertEqual((y_gerente.agronomo, y_gerente.para_gerente), (entrante, True))
        self.assertEqual((de_gerente.agronomo_id, de_gerente.para_gerente), (None, True))

    def test_d41_contar_cuenta_lo_que_recibiria_el_entrante_y_no_cambia_nada(self):
        """Regla 2 de PROD-MOD-INV: ``contar_alertas_que_recibe`` cuenta las activas que pasarían al entrante (las del
        saliente y las que fueron al Gerente por falta de Agrónomo, sin las de tipo ``GERENTE`` ni las resueltas)."""
        entrante = crear_agronomo("nuevo@infoponia.com")
        propia = self.alerta_de(Destinatario.AGRONOMO_O_GERENTE, para_gerente=False, agronomo=self.agronomo)
        self.alerta_de(Destinatario.AGRONOMO_O_GERENTE, para_gerente=False, agronomo=self.agronomo, resuelta=True)
        self.alerta_de(Destinatario.GERENTE, para_gerente=True)
        with self.tipos_de_traspaso():
            cantidad = alertas.contar_alertas_que_recibe(self.invernadero, self.agronomo, entrante)
        self.assertEqual(cantidad, 1)
        propia.refresh_from_db()
        self.assertEqual(propia.agronomo_id, self.agronomo.pk)


    # ---- sincronizar_alertas_de_personal(invernadero, roles) (MAE-02b, D-43) ----

    def test_d43_sincronizar_con_roles_solo_asegura_esos_roles(self):
        """D-43: con ``roles=["capataz"]`` solo se asegura la alerta del Capataz. El invernadero también está sin Vendedor,
        pero esa alerta no se crea ahora. Control: la del Capataz sí se crea."""
        with transaction.atomic():
            cambios = alertas.sincronizar_alertas_de_personal(
                Invernadero.objects.get(pk=self.invernadero.pk), roles=["capataz"]
            )

        self.assertEqual(self.activas_de(), ["sin_capataz"])
        self.assertEqual([alerta.tipo_alerta for alerta in cambios.creadas], ["sin_capataz"])
        self.assertEqual(list(cambios.resueltas), [])

    def test_d43_sincronizar_con_roles_solo_resuelve_esos_roles(self):
        """D-43: con ``roles=["capataz"]`` solo se resuelve la alerta del Capataz. La del Vendedor ya no corresponde (tiene un
        Vendedor activo), pero una sincronización completa la resolvería y esta la deja intacta. Control: la del Capataz
        se resuelve."""
        Invernadero.objects.filter(pk=self.invernadero.pk).update(
            capataz=crear_capataz_activo(), vendedor=crear_vendedor()
        )
        del_capataz = crear_alerta(
            self.invernadero, "sin_capataz", clave_estado="", descripcion_alerta="Invernadero sin Capataz activo"
        )
        del_vendedor = crear_alerta(
            self.invernadero, "sin_vendedor", clave_estado="", descripcion_alerta="Invernadero sin Vendedor activo"
        )

        with transaction.atomic():
            cambios = alertas.sincronizar_alertas_de_personal(
                Invernadero.objects.get(pk=self.invernadero.pk), roles=["capataz"]
            )

        del_capataz.refresh_from_db()
        del_vendedor.refresh_from_db()
        self.assertEqual([alerta.pk for alerta in cambios.resueltas], [del_capataz.pk])
        self.assertEqual(del_capataz.estado_alerta, "resuelta")
        self.assertEqual(del_vendedor.estado_alerta, "activa")
        self.assertIsNone(del_vendedor.fecha_resolucion)

    def test_d43_sincronizar_con_roles_none_se_ocupa_de_todos(self):
        """D-43: con ``roles=None`` (como la llaman el alta, la modificación y la reactivación del invernadero) se ocupa de
        los cuatro roles, como siempre."""
        with transaction.atomic():
            cambios = alertas.sincronizar_alertas_de_personal(
                Invernadero.objects.get(pk=self.invernadero.pk), roles=None
            )

        self.assertEqual(self.activas_de(), ["sin_capataz", "sin_vendedor"])
        self.assertEqual(len(cambios.creadas), 2)

    def test_d43_sincronizar_con_un_rol_desconocido_lanza_value_error(self):
        """D-43: ``roles`` solo admite los atributos de ``Invernadero.ROLES``; un rol desconocido (por ejemplo, un error de
        tipeo) lanza ``ValueError`` y no cambia nada. Control: un rol válido no lanza y se ocupa de su alerta."""
        invernadero = Invernadero.objects.get(pk=self.invernadero.pk)

        for roles in (["capatas"], ["capataz", "chofer"], ["Capataz"]):
            with self.subTest(roles=roles):
                with self.assertRaises(ValueError):
                    with transaction.atomic():
                        alertas.sincronizar_alertas_de_personal(invernadero, roles=roles)
        self.assertEqual(Alerta.objects.count(), 0)

        with transaction.atomic():
            cambios = alertas.sincronizar_alertas_de_personal(invernadero, roles=["capataz"])
        self.assertEqual([alerta.tipo_alerta for alerta in cambios.creadas], ["sin_capataz"])


class AlertaAbrirServicioTests(ConGeoref, TestCase):
    """``abrir_alerta`` (regla 7 de 8.18, MAE-02b): un destinatario abre la alerta y pasa a «leída». No audita (SEG-14, D-41)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.otro_agronomo = crear_agronomo("otro.agronomo@infoponia.com")
        self.invernadero = crear_invernadero("Invernadero A", agronomo=self.agronomo)
        self.del_gerente = crear_alerta(self.invernadero, "prueba_evento", para_gerente=True)
        self.del_agronomo = crear_alerta(self.invernadero, "prueba_evento", para_gerente=False, agronomo=self.agronomo)

    def test_regla_8_18_7_el_gerente_destinatario_la_marca_leida(self):
        """Regla 7 de 8.18: la alerta nace «no leída» y pasa a «leída» cuando uno de sus destinatarios la abre. El Gerente, si
        es ``para_gerente``. Devuelve la alerta ya leída."""
        self.assertEqual(self.del_gerente.estado_lectura_alerta, "no_leida")

        alerta = alertas.abrir_alerta(self.gerente, self.del_gerente.pk)

        self.assertEqual(alerta.pk, self.del_gerente.pk)
        self.assertEqual(alerta.estado_lectura_alerta, "leida")
        self.del_gerente.refresh_from_db()
        self.assertEqual(self.del_gerente.estado_lectura_alerta, "leida")

    def test_regla_8_18_7_el_agronomo_destinatario_la_marca_leida(self):
        """Regla 7 de 8.18: el Agrónomo destinatario la marca «leída». La del Gerente, en cambio, no cambia."""
        alertas.abrir_alerta(self.agronomo, self.del_agronomo.pk)

        self.del_agronomo.refresh_from_db()
        self.del_gerente.refresh_from_db()
        self.assertEqual(self.del_agronomo.estado_lectura_alerta, "leida")
        self.assertEqual(self.del_gerente.estado_lectura_alerta, "no_leida")

    def test_regla_8_18_7_abrir_no_cambia_el_estado_activa(self):
        """Regla 7 de 8.18: los dos estados son independientes. Abrir una alerta activa la deja activa y sin fecha de
        resolución."""
        alertas.abrir_alerta(self.gerente, self.del_gerente.pk)

        self.del_gerente.refresh_from_db()
        self.assertEqual(self.del_gerente.estado_lectura_alerta, "leida")
        self.assertEqual(self.del_gerente.estado_alerta, "activa")
        self.assertIsNone(self.del_gerente.fecha_resolucion)

    def test_regla_8_18_7_una_resuelta_abierta_queda_leida_y_resuelta(self):
        """Regla 7 de 8.18: una alerta resuelta y no leída, al abrirla, queda leída y sigue resuelta, con su fecha."""
        resuelta = crear_alerta(self.invernadero, "prueba_evento", para_gerente=True, resuelta=True)
        fecha = resuelta.fecha_resolucion

        alertas.abrir_alerta(self.gerente, resuelta.pk)

        resuelta.refresh_from_db()
        self.assertEqual(resuelta.estado_lectura_alerta, "leida")
        self.assertEqual(resuelta.estado_alerta, "resuelta")
        self.assertEqual(resuelta.fecha_resolucion, fecha)

    def test_regla_8_18_7_abrir_dos_veces_la_deja_leida(self):
        """Regla 7 de 8.18: abrir una alerta ya leída no falla y la deja leída."""
        alertas.abrir_alerta(self.gerente, self.del_gerente.pk)
        alerta = alertas.abrir_alerta(self.gerente, self.del_gerente.pk)

        self.assertEqual(alerta.estado_lectura_alerta, "leida")

    def test_d43_quien_no_es_destinatario_recibe_permission_denied_y_no_cambia(self):
        """D-41 y D-43: quien no recibe la alerta (otro Agrónomo, el Gerente ante una que no es para él, un Capataz, un
        Agrónomo dado de baja, ``None``) recibe ``PermissionDenied`` y la alerta no cambia. Control: el destinatario sí."""
        inactivo = crear_agronomo("inactivo.agronomo@infoponia.com", activo=False)
        del_inactivo = crear_alerta(self.invernadero, "prueba_evento", para_gerente=False, agronomo=inactivo)
        casos = (
            (self.otro_agronomo, self.del_agronomo),
            (self.gerente, self.del_agronomo),
            (crear_capataz(), self.del_gerente),
            (inactivo, del_inactivo),
            (None, self.del_gerente),
        )

        for actor, alerta in casos:
            with self.subTest(actor=getattr(actor, "email", None), alerta=alerta.pk):
                with self.assertRaises(PermissionDenied):
                    alertas.abrir_alerta(actor, alerta.pk)
                alerta.refresh_from_db()
                self.assertEqual(alerta.estado_lectura_alerta, "no_leida")
        self.assertEqual(alertas.abrir_alerta(self.agronomo, self.del_agronomo.pk).estado_lectura_alerta, "leida")

    def test_d28_una_alerta_inexistente_da_404(self):
        """D-28: un id que no existe da ``Http404``, igual que ``obtener_invernadero``; fuera del alcance, ``PermissionDenied``.
        Control: una que existe se abre."""
        self.assertEqual(alertas.abrir_alerta(self.gerente, self.del_gerente.pk).pk, self.del_gerente.pk)

        with self.assertRaises(Http404):
            alertas.abrir_alerta(self.gerente, self.del_gerente.pk + 1000)

    def test_d41_abrir_una_alerta_no_audita(self):
        """D-41 y SEG-14: abrir una alerta (marcarla leída) no deja registro de auditoría. Control: sí se marcó leída."""
        alertas.abrir_alerta(self.gerente, self.del_gerente.pk)

        self.del_gerente.refresh_from_db()
        self.assertEqual(self.del_gerente.estado_lectura_alerta, "leida")
        self.assertFalse(RegistroAuditoria.objects.exists())


class _Pausa:
    """Punto de parada de las pruebas de concurrencia: ``correr_a_la_vez(..., detener_antes_de=(pausa, "punto"))`` detiene a
    la operación ``primera`` justo ANTES de llamarlo, con lo que haya tomado hasta ahí (el invernadero bloqueado y la
    alerta todavía sin confirmar)."""

    def punto(self):
        """No hace nada: solo es el lugar donde se detiene ``primera``."""


pausa = _Pausa()


@tag("concurrencia")
class AlertaConcurrenciaTests(TransactionTestCase):
    """Bloqueos de la API de alertas (docs/patrones/bloqueos.md, D-30, D-32 y D-40; D-41): dos hilos, dos conexiones, el
    orden fijado con ``primera`` (``core/tests/concurrencia.py``). Orden de bloqueos: las cuentas, el invernadero, las
    alertas del invernadero y las filas de las apps altas. Cada prueba falla si se quita la protección que cuida. Usan su
    propia geografía: el ``flush`` de un ``TransactionTestCase`` vacía Georef."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero_con_geografia_propia("Invernadero A", agronomo=self.agronomo)

    def baja(self):
        return lambda: invernaderos.baja_invernadero(self.gerente, self.invernadero.pk)

    def crear_evento(self, tipo="prueba_evento", con_pausa=False):
        """Una operación de IoT simulada: crea una alerta de evento. Con ``con_pausa``, llama a ``pausa.punto()`` dentro de
        la transacción, después de crearla y antes de confirmar."""

        def operacion():
            with transaction.atomic():
                alerta = alertas.crear_alerta_de_evento(self.invernadero.pk, tipo, "Lectura fuera de rango")
                if con_pausa:
                    pausa.punto()
                return alerta

        return operacion

    def asegurar_estado(self, con_pausa=False):
        """Una operación de IoT simulada: asegura una alerta de estado. Con ``con_pausa``, como ``crear_evento``."""

        def operacion():
            with transaction.atomic():
                alerta = alertas.asegurar_alerta_de_estado(self.invernadero.pk, "prueba_estado")
                if con_pausa:
                    pausa.punto()
                return alerta

        return operacion

    def modificar_agronomo(self, entrante):
        """Un llamado a ``modificar_invernadero`` que solo cambia al Agrónomo por ``entrante``."""
        invernadero = Invernadero.objects.get(pk=self.invernadero.pk)
        return lambda: invernaderos.modificar_invernadero(
            self.gerente,
            invernadero.pk,
            invernadero.nombre_invernadero,
            tipo_direccion="urbana",
            localidad_id=invernadero.direccion.localidad_id,
            calle="Calle 122",
            numero_calle="3310",
            agronomo_id=entrante.pk,
            personal_confirmado=True,
        )

    def tipos(self):
        """Los tipos falsos de estas pruebas, registrados mientras dura el bloque."""
        return tipo_de_alerta_de_prueba(
            tipo_falso("prueba_evento"),
            tipo_falso("prueba_estado", clase=Clase.ESTADO),
            tipo_falso("prueba_agronomo_o_gerente", destinatario=Destinatario.AGRONOMO_O_GERENTE),
        )

    def test_d41_la_baja_espera_a_quien_crea_una_alerta_y_la_resuelve(self):
        """P1, post e de PROD-BAJ-INV: el creador va primero y se detiene con el invernadero bloqueado y la alerta sin
        confirmar; la baja espera, y cuando sigue ve la alerta y la resuelve. Sin el bloqueo del creador (el ``INSERT`` solo
        toma ``FOR KEY SHARE``, que no choca con el ``FOR NO KEY UPDATE`` de la baja), la baja no espera, no ve la alerta
        sin confirmar y queda una alerta activa en un invernadero inactivo."""
        with self.tipos():
            resultados = correr_a_la_vez(
                self.crear_evento(con_pausa=True), self.baja(), primera="a", detener_antes_de=(pausa, "punto")
            )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        self.assertFalse(Invernadero.objects.get(pk=self.invernadero.pk).activo)
        self.assertEqual(Alerta.objects.filter(invernadero=self.invernadero, estado_alerta="activa").count(), 0)
        self.assertEqual(Alerta.objects.filter(tipo_alerta="prueba_evento", estado_alerta="resuelta").count(), 1)

    def test_d41_quien_crea_una_alerta_espera_a_la_baja_y_no_la_crea(self):
        """P2, post e de PROD-BAJ-INV: la baja va primero y el creador espera el bloqueo del invernadero; cuando sigue, lo
        lee inactivo y no crea nada (devuelve ``None``, no es un error). Sin el bloqueo del creador, ve el invernadero
        activo (la baja no confirmó) y crea una alerta activa sobre un invernadero dado de baja."""
        with self.tipos():
            resultados = correr_a_la_vez(self.baja(), self.crear_evento(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        self.assertIsNone(resultados["b"])
        self.assertFalse(Invernadero.objects.get(pk=self.invernadero.pk).activo)
        self.assertFalse(Alerta.objects.filter(tipo_alerta="prueba_evento").exists())

    def test_d41_dos_alertas_de_estado_iguales_a_la_vez_dejan_una_sola(self):
        """P3, unicidad de las alertas de estado (D-41): la segunda espera el bloqueo del invernadero y, cuando sigue,
        encuentra la alerta que creó la primera y la devuelve: queda una sola, la misma para las dos. Sin el bloqueo ni el
        índice parcial ``alerta_de_estado_unica`` (se cubren entre sí: falla solo si faltan los dos), quedan dos activas.
        El índice tiene además su prueba unitaria en ``AlertaModeloTests``."""
        with self.tipos():
            resultados = correr_a_la_vez(
                self.asegurar_estado(con_pausa=True),
                self.asegurar_estado(),
                primera="a",
                detener_antes_de=(pausa, "punto"),
            )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        self.assertEqual(resultados["a"].pk, resultados["b"].pk)
        self.assertEqual(Alerta.objects.filter(tipo_alerta="prueba_estado", estado_alerta="activa").count(), 1)

    def test_d41_una_alerta_creada_mientras_cambia_el_agronomo_va_al_entrante(self):
        """P4, regla 4 de 8.22 y MD-60: la modificación va primero (cambia el Agrónomo y no confirma); el creador espera el
        bloqueo del invernadero y, cuando sigue, lo LEE DE NUEVO y manda la alerta al Agrónomo entrante. Sin releer el
        Agrónomo después de bloquear, usa el que leyó antes y la alerta queda con el saliente."""
        entrante = crear_agronomo("nuevo.agronomo@infoponia.com")
        with self.tipos():
            resultados = correr_a_la_vez(
                self.modificar_agronomo(entrante),
                self.crear_evento("prueba_agronomo_o_gerente"),
                primera="a",
            )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []))
        alerta = Alerta.objects.get(tipo_alerta="prueba_agronomo_o_gerente")
        self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (entrante.pk, False))

    def test_d43_sincronizar_con_roles_no_bloquea_las_alertas_de_otros_roles(self):
        """D-43 (no es una de las P de MAE-02): con ``roles=["capataz"]``, la sincronización bloquea solo las alertas de ese rol.
        Una transacción ``primera`` sincroniza y se detiene antes de confirmar; otra intenta tomar cada alerta con ``NOWAIT``:
        la del Vendedor está libre y la del Capataz, bloqueada (que es el control de que la prueba detecta los bloqueos). Con
        ``roles=None`` las dos quedan bloqueadas, como siempre."""
        Invernadero.objects.filter(pk=self.invernadero.pk).update(
            capataz=crear_capataz_activo(), vendedor=crear_vendedor()
        )

        def sincronizar(roles):
            def operacion():
                with transaction.atomic():
                    alertas.sincronizar_alertas_de_personal(
                        Invernadero.objects.get(pk=self.invernadero.pk), roles=roles
                    )
                    pausa.punto()

            return operacion

        def probar_bloqueos():
            estados = {}
            with transaction.atomic():
                for codigo in ("sin_vendedor", "sin_capataz"):
                    try:
                        with transaction.atomic():
                            list(
                                Alerta.objects.select_for_update(no_key=True, nowait=True).filter(
                                    invernadero=self.invernadero, tipo_alerta=codigo
                                )
                            )
                        estados[codigo] = "libre"
                    except DatabaseError:
                        estados[codigo] = "bloqueada"
            return estados

        for roles, esperado in (
            (None, {"sin_vendedor": "bloqueada", "sin_capataz": "bloqueada"}),
            (["capataz"], {"sin_vendedor": "libre", "sin_capataz": "bloqueada"}),
        ):
            with self.subTest(roles=roles):
                Alerta.objects.filter(invernadero=self.invernadero).delete()
                for atributo in ("capataz", "vendedor"):
                    crear_alerta(
                        self.invernadero,
                        f"sin_{atributo}",
                        clave_estado="",
                        descripcion_alerta=f"Invernadero sin {atributo} activo",
                    )

                resultados = correr_a_la_vez(
                    sincronizar(roles), probar_bloqueos, primera="a", detener_antes_de=(pausa, "punto")
                )

                exitos, rechazos, otros = separar(resultados)
                self.assertEqual((rechazos, otros), ([], []))
                self.assertEqual(resultados["b"], esperado)
