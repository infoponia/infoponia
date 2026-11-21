# Pruebas de ADM-MOD-ORG (Modificar Perfil de la Organización, MAE-04): precondición, reglas 1 a 7, postcondiciones a y b,
# D-28, D-45 (sin logo), la identidad de D-48 y la concurrencia. Fuente: docs/casos_de_uso/maestros/configuracion.md.
# Servicio: ``maestros/servicios/perfil.py``. CUIT válido de prueba: 30-71234567-1 (el del prototipo).

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.test import TestCase, TransactionTestCase, tag

from core.extensiones import Identidad
from core.models import RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez, separar
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from maestros.models import PerfilOrganizacion
from maestros.servicios import perfil
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    asegurar_datos_de_maestros,
    codigos_de,
    crear_agronomo,
    error_de,
)

CUIT_VALIDO = "30712345671"
CAMPOS_COLOR = ["color_primario", "color_secundario", "color_terciario", "color_cuaternario"]


def guardado():
    """El perfil guardado."""
    return PerfilOrganizacion.objects.get()


def auditorias():
    """Los registros de ``modificacion_perfil``, del más viejo al más nuevo."""
    return list(RegistroAuditoria.objects.filter(accion="modificacion_perfil").order_by("id"))


class AdmModOrgServicioTests(ConDatosDeMaestros, TestCase):
    """ADM-MOD-ORG: las reglas del servicio."""

    def setUp(self):
        self.gerente = crear_gerente()

    def modificar(self, **datos):
        """Modifica el perfil como el Gerente."""
        return perfil.modificar_perfil(self.gerente, **datos)

    def errores(self, **datos):
        """La ``ValidationError`` que lanza modificar con ``datos``."""
        return error_de(lambda: self.modificar(**datos))

    # ---- precondición a y regla 1 ----

    def test_pre_a_solo_un_gerente_activo_modifica(self):
        """ADM-MOD-ORG precondición a y regla 1: cualquier otra cuenta, o ninguna, recibe ``PermissionDenied``."""
        gerente_inactivo = crear_gerente(email="baja@infoponia.com", activo=False)
        for actor in (crear_agronomo(), crear_capataz(), crear_administrador(), gerente_inactivo, None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    perfil.modificar_perfil(actor, nombre_organizacion="Otro")
        self.assertEqual(guardado().nombre_organizacion, settings.NOMBRE_ORGANIZACION)
        self.assertEqual(auditorias(), [])

    def test_regla_1_obtener_crea_la_fila_si_faltara(self):
        """Regla 1 y patrón de singletons: sin fila, ``obtener`` la crea con el nombre de NOMBRE_ORGANIZACION."""
        PerfilOrganizacion.objects.all().delete()
        fila = perfil.obtener()
        self.assertEqual(PerfilOrganizacion.objects.count(), 1)
        self.assertEqual(fila.nombre_organizacion, settings.NOMBRE_ORGANIZACION)

    def test_regla_1_el_perfil_no_tiene_logo(self):
        """D-45: el campo del logo no se crea."""
        self.assertNotIn("logo", [f.name for f in PerfilOrganizacion._meta.get_fields()])

    # ---- regla 2: nombre y opcionales ----

    def test_regla_2_el_nombre_es_obligatorio(self):
        """Regla 2: el nombre vacío (o de espacios) da error en su campo."""
        for nombre in ("", "   ", None):
            with self.subTest(nombre=nombre):
                error = self.errores(nombre_organizacion=nombre)
                self.assertEqual(codigos_de(error, "nombre_organizacion"), ["obligatorio"])

    def test_regla_2_el_nombre_se_recorta_y_tiene_un_maximo(self):
        """Regla 2 y ficha del modelo: el nombre se recorta y admite hasta 120 caracteres."""
        self.modificar(nombre_organizacion="  Vivero Los Álamos  ")
        self.assertEqual(guardado().nombre_organizacion, "Vivero Los Álamos")
        self.modificar(nombre_organizacion="x" * 120)
        error = self.errores(nombre_organizacion="x" * 121)
        self.assertEqual(codigos_de(error, "nombre_organizacion"), ["demasiado_largo"])

    def test_regla_2_los_demas_datos_son_opcionales(self):
        """Regla 2: solo el nombre es obligatorio; con todo lo demás vacío se guarda."""
        self.modificar(nombre_organizacion="Vivero", cuit_organizacion="", telefono_organizacion="",
                       email_organizacion="", direccion_organizacion="")
        self.assertEqual(guardado().cuit_organizacion, "")

    def test_regla_2_la_direccion_tiene_un_maximo_de_200(self):
        """Ficha del modelo: dirección de hasta 200 caracteres."""
        self.modificar(direccion_organizacion="d" * 200)
        error = self.errores(direccion_organizacion="d" * 201)
        self.assertEqual(codigos_de(error, "direccion_organizacion"), ["demasiado_largo"])

    def test_regla_2_telefono_con_el_formato_de_d21(self):
        """Ficha del modelo y D-21: 8 a 15 dígitos, espacios y ``+ - ( )``; lo demás da error en el campo del teléfono."""
        self.modificar(telefono_organizacion="+54 376 400-1000")
        self.assertEqual(guardado().telefono_organizacion, "+54 376 400-1000")
        for telefono in ("abc", "123", "1" * 16):
            with self.subTest(telefono=telefono):
                error = self.errores(telefono_organizacion=telefono)
                self.assertEqual(len(codigos_de(error, "telefono_organizacion")), 1)

    # ---- regla 3: email y CUIT ----

    def test_regla_3_email_por_formato(self):
        """Regla 3: el email se valida por formato."""
        self.modificar(email_organizacion="contacto@vivero.com.ar")
        for email in ("sin-arroba", "a@b", "a b@c.com", "@x.com"):
            with self.subTest(email=email):
                error = self.errores(email_organizacion=email)
                self.assertEqual(codigos_de(error, "email_organizacion"), ["email_invalido"])

    def test_regla_3_cuit_con_o_sin_guiones_se_guarda_sin_guiones(self):
        """Regla 3 y ficha: el CUIT se acepta con o sin guiones y se guarda con los 11 dígitos."""
        for escrito in ("30-71234567-1", "30712345671", " 30 71234567 1 "):
            with self.subTest(escrito=escrito):
                self.modificar(cuit_organizacion=escrito)
                self.assertEqual(guardado().cuit_organizacion, CUIT_VALIDO)

    def test_regla_3_cuit_con_digito_verificador_incorrecto_se_rechaza(self):
        """Regla 3: el dígito verificador se controla (módulo 11, pesos 5,4,3,2,7,6,5,4,3,2)."""
        for cuit in ("30-71234567-2", "30712345670", "11111111111"):
            with self.subTest(cuit=cuit):
                error = self.errores(cuit_organizacion=cuit)
                self.assertEqual(codigos_de(error, "cuit_organizacion"), ["cuit_invalido"])

    def test_regla_3_cuit_con_formato_incorrecto_se_rechaza(self):
        """Regla 3: el CUIT son 11 dígitos; menos, más o letras dan error."""
        for cuit in ("3071234567", "307123456712", "30-7123456A-1"):
            with self.subTest(cuit=cuit):
                error = self.errores(cuit_organizacion=cuit)
                self.assertEqual(codigos_de(error, "cuit_organizacion"), ["cuit_invalido"])

    def test_regla_3_cuit_cuyo_digito_calculado_es_10_se_rechaza_y_11_vale_0(self):
        """Regla 3 (``cuitOk``): si el cálculo da 10 el CUIT no es válido; si da 11 se toma como 0."""
        pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
        base_diez = next(
            f"{n:010d}" for n in range(10**6) if (11 - sum(p * int(d) for p, d in zip(pesos, f"{n:010d}")) % 11) == 10
        )
        base_once = next(
            f"{n:010d}" for n in range(10**6) if (11 - sum(p * int(d) for p, d in zip(pesos, f"{n:010d}")) % 11) == 11
        )
        for verificador in range(10):
            error = self.errores(cuit_organizacion=base_diez + str(verificador))
            self.assertEqual(codigos_de(error, "cuit_organizacion"), ["cuit_invalido"])
        self.modificar(cuit_organizacion=base_once + "0")
        self.assertEqual(guardado().cuit_organizacion, base_once + "0")

    # ---- regla 5: colores ----

    def test_regla_5_colores_con_formato_rrggbb(self):
        """Regla 5 y D-48: cada color es ``#RRGGBB``; otra cosa da error en el campo del color."""
        for color in ("rojo", "#12345", "#1234567", "123456", "#GGGGGG", "javascript:alert(1)"):
            with self.subTest(color=color):
                error = self.errores(color_primario=color)
                self.assertEqual(codigos_de(error, "color_primario"), ["color_formato"])

    def test_regla_5_los_colores_se_cargan_en_orden(self):
        """Regla 5: no se carga el 2.º sin el 1.º, ni el 3.º sin el 2.º, ni el 4.º sin el 3.º; el error va en el color
        cargado fuera de orden."""
        error = self.errores(color_secundario="#112233")
        self.assertEqual(codigos_de(error, "color_secundario"), ["color_fuera_de_orden"])
        error = self.errores(color_primario="#112233", color_terciario="#445566")
        self.assertEqual(codigos_de(error, "color_terciario"), ["color_fuera_de_orden"])
        error = self.errores(color_primario="#112233", color_secundario="#445566", color_cuaternario="#778899")
        self.assertEqual(codigos_de(error, "color_cuaternario"), ["color_fuera_de_orden"])

    def test_regla_5_cuatro_colores_en_orden_se_guardan_en_mayusculas(self):
        """Regla 5 y decisión de la tarea: hasta cuatro colores, guardados en mayúsculas de modo uniforme."""
        self.modificar(color_primario="#2e7d32", color_secundario="#aabbcc", color_terciario="#112233",
                       color_cuaternario="#FFeeDD")
        fila = guardado()
        self.assertEqual([getattr(fila, c) for c in CAMPOS_COLOR], ["#2E7D32", "#AABBCC", "#112233", "#FFEEDD"])

    def test_regla_5_sin_ningun_color_se_usa_la_paleta_del_sistema(self):
        """Regla 5: sin colores el perfil guarda vacío y ``identidad`` no trae color principal."""
        self.modificar(color_primario="#2E7D32")
        self.modificar(color_primario="")
        self.assertEqual(guardado().color_primario, "")
        self.assertEqual(perfil.identidad().color_principal, "")

    # ---- regla 7: todo o nada ----

    def test_regla_7_un_dato_invalido_no_guarda_ninguno_y_marca_todos_los_campos_con_error(self):
        """Regla 7: con tres campos inválidos y uno válido, se devuelven los tres errores juntos y no se guarda ni el válido."""
        antes = PerfilOrganizacion.objects.values().get()
        error = self.errores(nombre_organizacion="", cuit_organizacion="123", email_organizacion="x",
                             direccion_organizacion="Av. Uruguay 2450")
        self.assertEqual(set(error.error_dict), {"nombre_organizacion", "cuit_organizacion", "email_organizacion"})
        self.assertEqual(PerfilOrganizacion.objects.values().get(), antes)
        self.assertEqual(auditorias(), [])

    def test_regla_7_un_campo_desconocido_se_rechaza(self):
        """Un dato que no existe (por ejemplo, ``logo``, D-45) es un error de programación: ``TypeError``."""
        with self.assertRaises(TypeError):
            self.modificar(logo="x.png")

    # ---- postcondiciones ----

    def test_post_a_actualiza_solo_los_datos_indicados(self):
        """Postcondición a: se actualizan los datos indicados y lo demás queda igual."""
        self.modificar(email_organizacion="a@b.com")
        self.modificar(nombre_organizacion="Vivero Los Álamos")
        fila = guardado()
        self.assertEqual((fila.nombre_organizacion, fila.email_organizacion), ("Vivero Los Álamos", "a@b.com"))

    def test_post_b_audita_con_el_antes_y_el_despues_de_cada_dato(self):
        """Postcondición b y D-36: un registro con usuario, el perfil como afectado y, de cada dato modificado, su valor
        anterior y su valor nuevo; un opcional vacío va como nulo y no figuran los que no cambiaron."""
        self.modificar(nombre_organizacion="Vivero Los Álamos", cuit_organizacion="30-71234567-1",
                       color_primario="#2e7d32")
        (registro,) = auditorias()
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual(registro.detalle, {"cambios": {
            "nombre_organizacion": {"antes": settings.NOMBRE_ORGANIZACION, "despues": "Vivero Los Álamos"},
            "cuit_organizacion": {"antes": None, "despues": CUIT_VALIDO},
            "color_primario": {"antes": None, "despues": "#2E7D32"},
        }})
        self.assertEqual([(a["modelo"], a["id"]) for a in registro.afectados],
                         [("maestros.perfilorganizacion", guardado().pk)])

    def test_post_b_vaciar_un_dato_se_audita_con_despues_nulo(self):
        """Postcondición b: al vaciar un opcional, el «después» es nulo."""
        self.modificar(email_organizacion="a@b.com")
        self.modificar(email_organizacion="")
        self.assertEqual(
            auditorias()[-1].detalle["cambios"], {"email_organizacion": {"antes": "a@b.com", "despues": None}}
        )

    def test_d28_sin_cambios_no_escribe_ni_audita(self):
        """D-28: guardar los mismos datos (con el CUIT con guiones, que se normaliza igual) no audita."""
        self.modificar(cuit_organizacion="30-71234567-1")
        antes = len(auditorias())
        self.modificar(nombre_organizacion=guardado().nombre_organizacion, cuit_organizacion="30-71234567-1")
        self.assertEqual(len(auditorias()), antes)

    # ---- identidad (D-48) ----

    def test_d48_identidad_devuelve_el_nombre_y_el_color_principal(self):
        """D-48: ``identidad`` devuelve ``Identidad(nombre, color_principal)`` del perfil guardado."""
        self.modificar(nombre_organizacion="Vivero Los Álamos", color_primario="#2E7D32")
        self.assertEqual(perfil.identidad(), Identidad("Vivero Los Álamos", "#2E7D32"))

    def test_d48_identidad_sin_fila_o_con_nombre_vacio_es_none_y_no_crea_la_fila(self):
        """D-48: sin fila, o con el nombre vacío, devuelve ``None`` (core usa NOMBRE_ORGANIZACION); no crea la fila."""
        PerfilOrganizacion.objects.update(nombre_organizacion="")
        self.assertIsNone(perfil.identidad())
        PerfilOrganizacion.objects.all().delete()
        self.assertIsNone(perfil.identidad())
        self.assertEqual(PerfilOrganizacion.objects.count(), 0)


@tag("concurrencia")
class AdmModOrgConcurrenciaTests(ConDatosDeMaestros, TransactionTestCase):
    """Bloqueo de la fila única: gana el último y el segundo audita contra lo ya modificado."""

    def setUp(self):
        asegurar_datos_de_maestros()
        self.gerente = crear_gerente()

    def test_regla_7_dos_modificaciones_a_la_vez_gana_la_ultima_y_audita_contra_lo_releido(self):
        """El segundo pedido espera el bloqueo, relee y su «antes» es el «después» del primero; nunca un error 500."""
        resultados = correr_a_la_vez(
            lambda: perfil.modificar_perfil(self.gerente, nombre_organizacion="Vivero A"),
            lambda: perfil.modificar_perfil(self.gerente, nombre_organizacion="Vivero B"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(guardado().nombre_organizacion, "Vivero B")
        self.assertEqual(
            [r.detalle["cambios"]["nombre_organizacion"] for r in auditorias()],
            [{"antes": settings.NOMBRE_ORGANIZACION, "despues": "Vivero A"}, {"antes": "Vivero A", "despues": "Vivero B"}],
        )

    def test_d28_el_segundo_pedido_con_el_mismo_valor_ya_guardado_no_audita(self):
        """D-28 con bloqueo: si el primero ya dejó el valor que pide el segundo, no se audita dos veces."""
        resultados = correr_a_la_vez(
            lambda: perfil.modificar_perfil(self.gerente, nombre_organizacion="Vivero A"),
            lambda: perfil.modificar_perfil(self.gerente, nombre_organizacion="Vivero A"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(len(auditorias()), 1)
