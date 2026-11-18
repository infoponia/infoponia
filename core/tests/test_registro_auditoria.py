# Pruebas del registro de auditoría (D-22 y D-36): se usa desde los servicios de todos los casos de uso que
# auditan (SEG-14), así que sus reglas propias se prueban acá, aparte de cada caso de uso: solo agregar, sin
# contraseñas y con el formato obligatorio del detalle y de los afectados. Cada prueba arma sus propios datos.
# Los nombres nuevos de D-36 se toman del módulo dentro de cada prueba (``modelos.referencia``), para que mientras
# no existan falle cada prueba por separado y no la importación del archivo.

from django.test import TestCase

import core.models as modelos
from core.models import (
    GrupoCuentas,
    RegistroAuditoria,
    RegistroAuditoriaInmutableError,
    Usuario,
)
from core.tests.fabricas import crear_administrador, crear_capataz

# Un detalle válido en el formato de D-36, para las pruebas que no miran el detalle.
DETALLE_DE_EJEMPLO = {"cambios": {"telefono": {"antes": "", "despues": "1155554444"}}}


def registrar(usuario, afectados, detalle=None):
    """Registra una modificación de cuenta de ejemplo y devuelve el registro."""
    return RegistroAuditoria.objects.registrar(
        usuario=usuario,
        accion=RegistroAuditoria.Accion.MODIFICACION,
        afectados=afectados,
        detalle=detalle if detalle is not None else DETALLE_DE_EJEMPLO,
    )


class RegistroAuditoriaTests(TestCase):
    """Reglas del registro de auditoría (D-22, SEG-02 y SEG-14)."""

    def test_d22_guarda_el_rol_del_momento(self):
        """D-22 y D-10: el registro guarda la cuenta que actuó y el rol con el que operaba en ese
        momento; el Administrador queda como «administrador»."""
        capataz = crear_capataz()
        administrador = crear_administrador()

        for usuario, rol in ((capataz, "capataz"), (administrador, "administrador")):
            with self.subTest(rol=rol):
                registro = registrar(usuario, afectados=[capataz])

                registro.refresh_from_db()
                self.assertEqual(registro.usuario_id, usuario.pk)
                self.assertEqual(registro.rol, rol)
                self.assertEqual(registro.accion, RegistroAuditoria.Accion.MODIFICACION)
                self.assertIsNotNone(registro.fecha_hora)

    def test_d22_identifica_las_cuentas_afectadas_como_usuario(self):
        """D-22 y D-36: guarda cada cuenta afectada como «core.usuario», aunque se pase la instancia del rol
        (Capataz), para poder buscar todos los registros de una cuenta por su id; con el texto que tenía en ese
        momento («Nombre Apellido (email)», o solo el email si no tiene nombre) y su rol, que no cambia (MD-55).
        El Administrador queda con el rol «administrador»."""
        capataz = crear_capataz()
        sin_nombre = crear_capataz(email="otra@infoponia.com", first_name="", last_name="")
        administrador = crear_administrador()
        usuario_base = Usuario.objects.get(pk=sin_nombre.pk)

        registro = registrar(capataz, afectados=[capataz, usuario_base, administrador])

        registro.refresh_from_db()
        self.assertEqual(
            registro.afectados,
            [
                {
                    "modelo": "core.usuario",
                    "id": capataz.pk,
                    "texto": "Juan Pérez (capataz@infoponia.com)",
                    "rol": "capataz",
                },
                {
                    "modelo": "core.usuario",
                    "id": sin_nombre.pk,
                    "texto": "otra@infoponia.com",
                    "rol": "capataz",
                },
                {
                    "modelo": "core.usuario",
                    "id": administrador.pk,
                    "texto": "Adrián Mena (admin@infoponia.com)",
                    "rol": "administrador",
                },
            ],
        )

    def test_d36_afectado_que_no_es_cuenta_lleva_su_texto_sin_rol(self):
        """D-36: un objeto afectado que no es una cuenta (por ejemplo, un grupo; en el futuro, un invernadero) se
        guarda con su modelo, su id y su texto (``str``), sin rol."""
        capataz = crear_capataz()
        grupo = GrupoCuentas.objects.create()

        registro = registrar(capataz, afectados=[grupo])

        registro.refresh_from_db()
        self.assertEqual(
            registro.afectados,
            [{"modelo": "core.grupocuentas", "id": grupo.pk, "texto": f"Grupo {grupo.pk}"}],
        )

    def test_d22_accion_de_infoponia_sin_usuario_guarda_rol_infoponia(self):
        """D-22 (por ejemplo, MD-62): una acción que hace InfoPonia, sin una cuenta que actúe, se
        registra sin usuario y con el rol «infoponia»."""
        capataz = crear_capataz()

        registro = registrar(None, afectados=[capataz])

        registro.refresh_from_db()
        self.assertIsNone(registro.usuario)
        self.assertEqual(registro.rol, "infoponia")

    def test_d22_registro_no_se_modifica(self):
        """D-22: al registro solo se le agregan filas; una fila guardada no se modifica, ni desde la
        instancia ni con ``update()``."""
        capataz = crear_capataz()
        registro = registrar(capataz, afectados=[capataz])

        with self.subTest("save() de una fila existente"):
            registro.detalle = {"cambios": {"telefono": {"antes": "", "despues": "otro"}}}
            with self.assertRaises(RegistroAuditoriaInmutableError):
                registro.save()

        with self.subTest("update() del queryset"):
            with self.assertRaises(RegistroAuditoriaInmutableError):
                RegistroAuditoria.objects.filter(pk=registro.pk).update(rol="gerente")

        registro.refresh_from_db()
        self.assertEqual(registro.detalle, DETALLE_DE_EJEMPLO)
        self.assertEqual(registro.rol, "capataz")

    def test_d22_registro_no_se_borra(self):
        """D-22: una fila del registro no se borra, ni desde la instancia ni desde el queryset."""
        capataz = crear_capataz()
        registro = registrar(capataz, afectados=[capataz])

        with self.subTest("delete() de la instancia"):
            with self.assertRaises(RegistroAuditoriaInmutableError):
                registro.delete()

        with self.subTest("delete() del queryset"):
            with self.assertRaises(RegistroAuditoriaInmutableError):
                RegistroAuditoria.objects.all().delete()

        self.assertTrue(RegistroAuditoria.objects.filter(pk=registro.pk).exists())

    def test_d22_rechaza_detalle_con_contrasenas(self):
        """D-22, SEG-02 y SEG-14: ninguna contraseña queda en la auditoría. Un detalle con una clave
        que nombra una contraseña se rechaza y no se crea el registro, esté en los cambios o en los datos
        (D-36)."""
        capataz = crear_capataz()

        for clave in ("contrasena", "contrasena_nueva", "password", "Password_hash"):
            for detalle in (
                {"cambios": {clave: {"antes": None, "despues": "algo"}}},
                {"datos": {clave: "algo"}},
            ):
                with self.subTest(clave=clave, detalle=detalle):
                    with self.assertRaises(ValueError):
                        registrar(capataz, afectados=[capataz], detalle=detalle)

        self.assertFalse(RegistroAuditoria.objects.exists())


class FormatoDetalleTests(TestCase):
    """Formato obligatorio del detalle de la auditoría (D-36): ``cambios`` con antes y después, ``datos`` de
    contexto y referencias ``{id, texto}``. ``registrar`` rechaza cualquier otra forma con ``ValueError`` y no
    crea el registro."""

    def assertRechaza(self, detalle):
        """``registrar`` rechaza ``detalle`` con ``ValueError`` y no queda ningún registro."""
        capataz = crear_capataz(email=f"capataz{Usuario.objects.count()}@infoponia.com")
        with self.assertRaises(ValueError):
            registrar(capataz, afectados=[capataz], detalle=detalle)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_d36_rechaza_clave_de_primer_nivel_distinta_de_cambios_y_datos(self):
        """D-36: el detalle solo tiene las claves «cambios» y «datos»; el formato viejo (``{campo: [antes,
        después]}`` o valores sueltos) se rechaza."""
        for detalle in (
            {"telefono": ["", "1155554444"]},
            {"estado": ["activo", "inactivo"]},
            {"era_temporal": True},
            {"cambios": {}, "otra": 1},
        ):
            with self.subTest(detalle=detalle):
                self.assertRechaza(detalle)

    def test_d36_rechaza_cambio_sin_antes_y_despues(self):
        """D-36: cada cambio es exactamente ``{"antes": ..., "despues": ...}``. Lo que hace obligatorio el valor
        anterior: un cambio sin «antes», sin «despues», con una clave de más o que no es un diccionario se
        rechaza."""
        for cambio in (
            {"despues": "1155554444"},
            {"antes": ""},
            {"antes": "", "despues": "1", "extra": 2},
            ["", "1155554444"],
            "1155554444",
        ):
            with self.subTest(cambio=cambio):
                self.assertRechaza({"cambios": {"telefono": cambio}})

    def test_d36_rechaza_cambio_con_antes_igual_a_despues(self):
        """D-36: un cambio en el que el valor no cambió no es un cambio y se rechaza."""
        self.assertRechaza({"cambios": {"telefono": {"antes": "1", "despues": "1"}}})
        self.assertRechaza({"cambios": {"grupo": {"antes": None, "despues": None}}})

    def test_d36_rechaza_cambios_o_datos_que_no_son_diccionarios(self):
        """D-36: «cambios» y «datos» son diccionarios."""
        for detalle in ({"cambios": [1, 2]}, {"datos": ["acceso"]}, {"datos": "temporal"}):
            with self.subTest(detalle=detalle):
                self.assertRechaza(detalle)

    def test_d36_rechaza_referencia_mal_formada(self):
        """D-36: un diccionario dentro de un valor solo puede ser una referencia a otro objeto, con exactamente
        «id» y «texto»; también dentro de una lista."""
        for valor in ({"id": 3}, {"texto": "Grupo 3"}, {"id": 3, "texto": "Grupo 3", "modelo": "x"}, {"a": 1}):
            with self.subTest(valor=valor):
                self.assertRechaza({"datos": {"grupo": valor}})
                self.assertRechaza({"cambios": {"grupo": {"antes": valor, "despues": None}}})
                self.assertRechaza({"datos": {"grupos": [valor]}})

    def test_d36_acepta_cambios_datos_ambos_o_ninguno(self):
        """D-36: las dos claves son opcionales. Se aceptan solo «cambios», solo «datos», las dos o ninguna, con
        referencias ``{id, texto}``, nulos, booleanos y listas de escalares o de referencias; el detalle se guarda
        tal cual."""
        capataz = crear_capataz()
        grupo = {"id": 4, "texto": "Grupo 4"}
        for detalle in (
            {"cambios": {"estado": {"antes": "activo", "despues": "inactivo"}}},
            {"datos": {"era_temporal": False, "grupo": grupo, "lista": [1, "dos", grupo]}},
            {
                "cambios": {"grupo": {"antes": grupo, "despues": None}, "rol": {"antes": None, "despues": "capataz"}},
                "datos": {"acceso": "temporal", "grupo_unido": None},
            },
            {},
        ):
            with self.subTest(detalle=detalle):
                registro = registrar(capataz, afectados=[capataz], detalle=detalle)
                registro.refresh_from_db()
                self.assertEqual(registro.detalle, detalle)

    def test_d36_detalle_nulo_se_guarda_vacio(self):
        """D-36 y D-22: sin detalle, el registro guarda un diccionario vacío (válido: las dos claves son
        opcionales)."""
        capataz = crear_capataz()

        registro = RegistroAuditoria.objects.registrar(
            usuario=capataz, accion=RegistroAuditoria.Accion.BAJA, afectados=[capataz]
        )

        registro.refresh_from_db()
        self.assertEqual(registro.detalle, {})

    def test_d36_referencia_arma_id_y_texto_del_momento(self):
        """D-36: ``referencia(objeto)`` arma ``{"id", "texto"}`` con el texto que el objeto tiene ahora: una cuenta,
        «Nombre Apellido (email)»; otro objeto, su ``str``."""
        capataz = crear_capataz()
        grupo = GrupoCuentas.objects.create()

        self.assertEqual(
            modelos.referencia(capataz), {"id": capataz.pk, "texto": "Juan Pérez (capataz@infoponia.com)"}
        )
        self.assertEqual(modelos.referencia(grupo), {"id": grupo.pk, "texto": f"Grupo {grupo.pk}"})


class TextosLegiblesTests(TestCase):
    """Lo que la pantalla de la auditoría necesita para mostrar textos legibles (D-36, regla 3 de AUD-CNS-REG):
    nombre visible de cada campo y de cada dato, y cada valor en texto."""

    def test_d36_filas_de_cambios_con_etiquetas_y_raya_para_nulo(self):
        """D-36 y regla 3 de AUD-CNS-REG: cada cambio es una fila (campo, antes, después) con el nombre visible
        del campo; un valor nulo se muestra como «—», una referencia con su texto guardado y los valores con
        lista cerrada con su nombre visible (rol, estado). Un campo sin nombre visible se muestra tal cual."""
        capataz = crear_capataz()
        registro = registrar(
            capataz,
            afectados=[capataz],
            detalle={
                "cambios": {
                    "rol": {"antes": None, "despues": "agronomo"},
                    "estado": {"antes": "activo", "despues": "inactivo"},
                    "telefono": {"antes": "", "despues": "1155554444"},
                    "grupo": {"antes": {"id": 4, "texto": "Grupo 4"}, "despues": None},
                    "campo_raro": {"antes": 1, "despues": 2},
                }
            },
        )

        self.assertEqual(
            registro.filas_de_cambios(),
            [
                ("Rol", "—", "Agrónomo"),
                ("Estado", "Activo", "Inactivo"),
                ("Teléfono", "", "1155554444"),
                ("Grupo de cuentas vinculadas", "Grupo 4", "—"),
                ("campo_raro", "1", "2"),
            ],
        )

    def test_d36_filas_de_datos_con_etiquetas_y_si_no(self):
        """D-36 y regla 3 de AUD-CNS-REG: cada dato de contexto es una fila (dato, valor) con su nombre visible;
        un booleano se muestra «Sí» o «No», la forma de acceso con su nombre, una referencia con su texto y un
        nulo como «—». El rol «administrador» se muestra «Administrador»."""
        capataz = crear_capataz()
        registro = registrar(
            capataz,
            afectados=[capataz],
            detalle={
                "cambios": {"rol": {"antes": None, "despues": "administrador"}},
                "datos": {
                    "acceso": "invitacion",
                    "era_temporal": True,
                    "invitacion_pendiente": False,
                    "grupo": {"id": 4, "texto": "Grupo 4"},
                    "grupo_unido": None,
                },
            },
        )

        self.assertEqual(registro.filas_de_cambios(), [("Rol", "—", "Administrador")])
        self.assertEqual(
            registro.filas_de_datos(),
            [
                ("Forma de acceso", "Invitación por correo"),
                ("La contraseña era temporal", "Sí"),
                ("Tenía una invitación pendiente", "No"),
                ("Grupo de cuentas vinculadas", "Grupo 4"),
                ("Grupo que se unió", "—"),
            ],
        )

    def test_d36_sin_cambios_ni_datos_no_hay_filas(self):
        """D-36: un registro sin «cambios» ni «datos» no tiene filas."""
        capataz = crear_capataz()
        registro = registrar(capataz, afectados=[capataz], detalle={})

        self.assertEqual(registro.filas_de_cambios(), [])
        self.assertEqual(registro.filas_de_datos(), [])
