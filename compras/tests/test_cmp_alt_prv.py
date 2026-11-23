# Pruebas de CMP-ALT-PRV · Alta Proveedor, con su reactivación (docs/casos_de_uso/compras/proveedores.md). Cita D-22, D-36, D-58 y D-87.
#
# Servicios que se prueban (compras/servicios/proveedores.py), tomados del módulo dentro de cada prueba:
#   alta_proveedor(actor, datos) -> Proveedor
#     - ``datos``: ``tipo`` («juridica» o «fisica»), ``cuit``, ``razon_social``, ``nombre``, ``apellido``, ``email``, ``telefono`` y
#       ``especialidades`` (ids o categorías de insumos). Un CUIT con o sin guiones; se guarda en 11 dígitos.
#     - Precondición a: Gerente activo (PermissionDenied si no).
#     - Regla 1: jurídica ⇒ razón social; física ⇒ nombre y apellido (los datos del otro tipo se ignoran); correo obligatorio; teléfono
#       opcional y con el formato de D-21. Todos los errores de campo juntos en un solo ValidationError (docs/patrones/abm.md, sección 2).
#     - Regla 2: CUIT obligatorio y válido (``cuit_invalido``, D-58); único entre activos e inactivos. El de un activo da el error de campo
#       ``cuit_repetido``; el de un inactivo lanza ``ErrorDeCompras`` ``cuit_de_inactivo`` con el id, y la pantalla ofrece reactivarlo.
#     - Regla 3: especialidades, cero o más categorías activas (``categoria_inactiva``, ``categoria_inexistente``).
#     - Postcondición b: un registro ``alta_proveedor`` (D-36).
#   reactivar_proveedor(actor, proveedor_id, datos) -> Proveedor
#     - Postcondición c: el proveedor inactivo pasa a activo con los datos indicados (el CUIT y el tipo no cambian) y se audita como
#       ``reactivacion_proveedor``, en lugar de crear uno nuevo. Uno que no está inactivo: ``ErrorDeCompras`` ``proveedor_no_inactivo``.

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import TestCase

from compras.errores import ErrorDeCompras
from compras.models import Proveedor
from compras.tests.fabricas import GERENTE, afectado_de, con_guiones, cuit_valido, datos_de, datos_de_alta, proveedor, ref, tipo_de_insumo
from core.models import RegistroAuditoria, Usuario
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.tests.fabricas import perezoso
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_vendedor, error_de

proveedores = perezoso("compras.servicios.proveedores")
ALTA = RegistroAuditoria.Accion.ALTA_PROVEEDOR
REACTIVACION = RegistroAuditoria.Accion.REACTIVACION_PROVEEDOR
LARGA = "x" * 300


class CmpAltPrvServicioTests(TestCase):
    """Precondiciones, reglas y postcondiciones de CMP-ALT-PRV."""

    def setUp(self):
        self.gerente = crear_gerente()

    def alta(self, actor=GERENTE, **cambios):
        return proveedores.alta_proveedor(self.gerente if actor is GERENTE else actor, datos_de_alta(**cambios))

    def error(self, **cambios):
        """La ValidationError que lanza un alta con ``cambios``."""
        return error_de(lambda: self.alta(**cambios))

    def mensajes(self, error, campo):
        return [e.message for e in error.error_dict[campo]]

    # ---- precondición a ----

    def test_pre_a_solo_un_gerente_activo_da_de_alta(self):
        """CMP-ALT-PRV precondición a y actores: solo el Gerente (el Agrónomo consulta; CU-86 decía «Agrónomo o superior» y cambió)."""
        sin_permiso = (
            crear_agronomo(),
            crear_capataz(),
            crear_vendedor(),
            crear_administrador(),
            crear_gerente(email="anterior@infoponia.com", activo=False),
            None,
        )
        for actor in sin_permiso:
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                self.alta(actor=actor)
        self.assertEqual(Proveedor.objects.count(), 0)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())

    # ---- flujo principal y postcondición a ----

    def test_flujo_principal_crea_una_persona_juridica_activa(self):
        """CMP-ALT-PRV postcondición a: se creó el proveedor «activo» con CUIT, razón social, correo y teléfono si se indicó."""
        categoria = tipo_de_insumo("Limpieza")
        creado = self.alta(telefono="+54 376 400-1001", especialidades=[categoria.pk])
        creado.refresh_from_db()
        self.assertEqual(
            (creado.tipo_proveedor, creado.cuit_proveedor, creado.razon_social_proveedor, creado.nombre_proveedor, creado.apellido_proveedor),
            ("juridica", cuit_valido(1), "Semillas del Sur S. A.", "", ""),
        )
        self.assertEqual((creado.email_proveedor, creado.telefono_proveedor), ("ventas@semillasdelsur.com", "+54 376 400-1001"))
        self.assertEqual(creado.estado_proveedor, "activo")
        self.assertEqual(list(creado.especialidades.all()), [categoria])

    def test_post_a_crea_una_persona_fisica_con_nombre_y_apellido(self):
        """CMP-ALT-PRV regla 1 y postcondición a: una persona física lleva nombre y apellido, sin razón social."""
        creado = self.alta(tipo="fisica", razon_social="", nombre="Ana", apellido="Gómez")
        self.assertEqual(
            (creado.tipo_proveedor, creado.razon_social_proveedor, creado.nombre_proveedor, creado.apellido_proveedor),
            ("fisica", "", "Ana", "Gómez"),
        )
        self.assertEqual(str(creado), "Ana Gómez")

    def test_regla_1_los_datos_del_otro_tipo_se_ignoran(self):
        """CMP-ALT-PRV regla 1: una jurídica guarda vacíos el nombre y el apellido; una física, vacía la razón social."""
        juridica = self.alta(nombre="Ana", apellido="Gómez")
        fisica = self.alta(tipo="fisica", cuit=cuit_valido(2), razon_social="Semillas del Sur S. A.", nombre="Ana", apellido="Gómez")
        self.assertEqual((juridica.nombre_proveedor, juridica.apellido_proveedor), ("", ""))
        self.assertEqual(fisica.razon_social_proveedor, "")

    def test_regla_1_el_telefono_es_opcional(self):
        """CMP-ALT-PRV regla 1 (P5): sin teléfono se crea igual."""
        self.assertEqual(self.alta(telefono="").telefono_proveedor, "")

    def test_regla_1_los_textos_se_guardan_recortados(self):
        """CMP-ALT-PRV regla 1 y docs/patrones/abm.md: los espacios al borde se quitan."""
        creado = self.alta(razon_social="  Semillas del Sur S. A.  ", email="  ventas@semillasdelsur.com ", telefono=" 376 400-1001 ")
        self.assertEqual(
            (creado.razon_social_proveedor, creado.email_proveedor, creado.telefono_proveedor),
            ("Semillas del Sur S. A.", "ventas@semillasdelsur.com", "376 400-1001"),
        )

    # ---- regla 1: datos ----

    def test_regla_1_el_tipo_es_obligatorio_y_uno_de_los_dos(self):
        """CMP-ALT-PRV regla 1: razón social (organización) o nombre y apellido (persona): hay que elegir cuál."""
        self.assertEqual(codigos_de(self.error(tipo=""), "tipo"), ["obligatorio"])
        self.assertEqual(codigos_de(self.error(tipo="otro"), "tipo"), ["invalido"])

    def test_regla_1_la_razon_social_es_obligatoria_con_contenido_y_de_hasta_150(self):
        """CMP-ALT-PRV regla 1 y modelo: la razón social de una jurídica no está vacía, tiene letras o números y llega a 150."""
        self.assertEqual(codigos_de(self.error(razon_social="   "), "razon_social"), ["obligatorio"])
        self.assertEqual(codigos_de(self.error(razon_social="-----"), "razon_social"), ["sin_contenido"])
        self.assertEqual(codigos_de(self.error(razon_social="x" * 151), "razon_social"), ["demasiado_largo"])
        self.assertEqual(self.alta(razon_social="x" * 150).razon_social_proveedor, "x" * 150)

    def test_regla_1_una_fisica_necesita_nombre_y_apellido_de_hasta_80(self):
        """CMP-ALT-PRV regla 1 y modelo: nombre y apellido obligatorios, con contenido y de hasta 80."""
        error = self.error(tipo="fisica", razon_social="", nombre="", apellido="")
        self.assertEqual(codigos_de(error, "nombre"), ["obligatorio"])
        self.assertEqual(codigos_de(error, "apellido"), ["obligatorio"])
        error = self.error(tipo="fisica", nombre="x" * 81, apellido="-")
        self.assertEqual(codigos_de(error, "nombre"), ["demasiado_largo"])
        self.assertEqual(codigos_de(error, "apellido"), ["sin_contenido"])

    def test_regla_1_el_correo_es_obligatorio(self):
        """CMP-ALT-PRV regla 1: el correo es obligatorio porque el proveedor solo recibe pedidos y órdenes por correo."""
        self.assertEqual(codigos_de(self.error(email=""), "email"), ["obligatorio"])
        self.assertEqual(codigos_de(self.error(email="   "), "email"), ["obligatorio"])

    def test_regla_1_el_correo_tiene_que_parecer_un_correo_de_hasta_254(self):
        """CMP-ALT-PRV regla 1 y modelo: formato de correo y 254 caracteres como máximo."""
        for malo in ("ventas", "ventas@", "@mail.com", "ventas mail.com"):
            with self.subTest(email=malo):
                self.assertEqual(codigos_de(self.error(email=malo), "email"), ["email_invalido"])
        self.assertEqual(codigos_de(self.error(email="x" * 250 + "@mail.com"), "email"), ["demasiado_largo"])

    def test_regla_1_el_telefono_sigue_el_formato_de_d_21(self):
        """CMP-ALT-PRV regla 1 y D-21: solo dígitos, espacios y + - ( ), con entre 8 y 15 dígitos y hasta 25 caracteres."""
        self.assertEqual(codigos_de(self.error(telefono="abc"), "telefono"), ["telefono_formato"])
        self.assertEqual(codigos_de(self.error(telefono="1234"), "telefono"), ["telefono_digitos"])
        self.assertEqual(codigos_de(self.error(telefono="1" * 26), "telefono"), ["telefono_largo"])

    def test_regla_1_todos_los_errores_de_campo_vienen_juntos(self):
        """docs/patrones/abm.md, sección 2: un solo ValidationError con un error por campo, para marcarlos todos a la vez."""
        error = self.error(cuit="", razon_social="", email="", telefono="abc")
        self.assertEqual(set(error.error_dict), {"cuit", "razon_social", "email", "telefono"})
        self.assertEqual(Proveedor.objects.count(), 0)

    # ---- regla 2: CUIT ----

    def test_regla_2_el_cuit_es_obligatorio(self):
        """CMP-ALT-PRV regla 2: sin CUIT no hay alta."""
        self.assertEqual(codigos_de(self.error(cuit=""), "cuit"), ["obligatorio"])

    def test_regla_2_el_cuit_se_valida_con_la_api_publica_de_maestros(self):
        """CMP-ALT-PRV regla 2 y D-58: un CUIT con el verificador equivocado o de otro largo da ``cuit_invalido``."""
        for malo in ("30712345670", "3071234567", "abc"):
            with self.subTest(cuit=malo):
                self.assertEqual(codigos_de(self.error(cuit=malo), "cuit"), ["cuit_invalido"])

    def test_regla_2_el_cuit_con_guiones_se_guarda_en_once_digitos(self):
        """CMP-ALT-PRV regla 2 y D-58: se acepta con guiones y se guarda sin ellos."""
        self.assertEqual(self.alta(cuit=con_guiones(cuit_valido(1))).cuit_proveedor, cuit_valido(1))

    def test_regla_2_el_cuit_de_un_proveedor_activo_se_rechaza_con_un_error_de_campo(self):
        """CMP-ALT-PRV regla 2 (H14): ``cuit_repetido`` en el campo ``cuit``, con el nombre de quien ya lo tiene; no se crea ni se audita nada."""
        proveedor("Agro Norte S. R. L.", n=1)
        error = self.error()
        self.assertEqual(codigos_de(error, "cuit"), ["cuit_repetido"])
        self.assertIn("Agro Norte S. R. L.", self.mensajes(error, "cuit")[0])
        self.assertEqual(Proveedor.objects.count(), 1)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())

    def test_regla_2_el_cuit_repetido_se_detecta_aunque_se_escriba_con_guiones(self):
        """CMP-ALT-PRV regla 2: el CUIT se compara en 11 dígitos, como se guarda."""
        proveedor(n=1)
        self.assertEqual(codigos_de(self.error(cuit=con_guiones(cuit_valido(1))), "cuit"), ["cuit_repetido"])

    def test_regla_2_el_cuit_de_un_inactivo_ofrece_reactivarlo(self):
        """CMP-ALT-PRV regla 2: si es el de un proveedor inactivo, el Sistema ofrece reactivarlo: ``ErrorDeCompras`` ``cuit_de_inactivo``
        con el id (la pantalla ofrece ``reactivar_proveedor``). No se crea un proveedor ni se audita."""
        inactivo = proveedor("Agro Norte S. R. L.", n=1, activo=False)
        with self.assertRaises(ErrorDeCompras) as contexto:
            self.alta()
        self.assertEqual(contexto.exception.codigo, "cuit_de_inactivo")
        self.assertEqual(contexto.exception.campo, "cuit")
        self.assertEqual(contexto.exception.datos, {"proveedor_id": inactivo.pk})
        self.assertIn("Agro Norte S. R. L.", contexto.exception.mensaje)
        self.assertEqual(Proveedor.objects.count(), 1)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())

    def test_regla_2_los_errores_de_otros_campos_van_antes_que_la_oferta_de_reactivar(self):
        """docs/patrones/abm.md: si el formulario tiene errores de campo, se informan primero (todos juntos), aun con el CUIT de un inactivo."""
        proveedor(n=1, activo=False)
        self.assertEqual(codigos_de(self.error(email=""), "email"), ["obligatorio"])

    # ---- regla 3: especialidades ----

    def test_regla_3_las_especialidades_son_cero_o_mas_categorias(self):
        """CMP-ALT-PRV regla 3: cero o más tipos de insumo; se pueden pasar como ids o como categorías."""
        limpieza, nutrientes = tipo_de_insumo("Limpieza"), tipo_de_insumo("Nutrientes")
        self.assertEqual(self.alta(especialidades=[]).especialidades.count(), 0)
        con_ids = self.alta(cuit=cuit_valido(2), especialidades=[limpieza.pk, nutrientes.pk])
        con_objetos = self.alta(cuit=cuit_valido(3), especialidades=[limpieza])
        self.assertEqual(set(con_ids.especialidades.all()), {limpieza, nutrientes})
        self.assertEqual(set(con_objetos.especialidades.all()), {limpieza})

    def test_regla_3_una_categoria_dada_de_baja_no_se_puede_elegir(self):
        """CMP-ALT-PRV regla 3 y «Cómo se aplica»: solo categorías activas para elegir (``categoria_inactiva``)."""
        baja = tipo_de_insumo("Vieja", activo=False)
        error = self.error(especialidades=[baja.pk])
        self.assertEqual(codigos_de(error, "especialidades"), ["categoria_inactiva"])
        self.assertEqual(Proveedor.objects.count(), 0)

    def test_regla_3_una_categoria_que_no_existe_se_rechaza(self):
        """Un id de categoría que no existe (un formulario manipulado) da un error de campo, nunca un 500."""
        self.assertEqual(codigos_de(self.error(especialidades=[999999]), "especialidades"), ["categoria_inexistente"])

    # ---- regla 4 ----

    def test_regla_4_el_proveedor_no_tiene_cuenta(self):
        """CMP-ALT-PRV regla 4: participa solo por enlace; el alta no crea ninguna cuenta de usuario."""
        cuentas = Usuario.objects.count()
        self.alta()
        self.assertEqual(Usuario.objects.count(), cuentas)

    # ---- postcondición b: auditoría ----

    def test_post_b_audita_el_alta_con_usuario_rol_y_el_proveedor_creado(self):
        """CMP-ALT-PRV postcondición b y D-36: usuario, rol, identificador del proveedor y los datos con «antes» nulo."""
        limpieza, nutrientes = tipo_de_insumo("Limpieza"), tipo_de_insumo("Nutrientes")
        creado = self.alta(telefono="376 400-1001", especialidades=[nutrientes.pk, limpieza.pk])
        registro = RegistroAuditoria.objects.get(accion=ALTA)
        self.assertEqual((registro.usuario_id, registro.rol), (self.gerente.pk, "gerente"))
        self.assertEqual(registro.afectados, [afectado_de(creado)])
        self.assertEqual(
            registro.detalle["cambios"],
            {
                "tipo_proveedor": {"antes": None, "despues": "juridica"},
                "cuit": {"antes": None, "despues": cuit_valido(1)},
                "razon_social": {"antes": None, "despues": "Semillas del Sur S. A."},
                "email": {"antes": None, "despues": "ventas@semillasdelsur.com"},
                "telefono": {"antes": None, "despues": "376 400-1001"},
                "especialidades": {"antes": None, "despues": [ref(limpieza), ref(nutrientes)]},
                "estado": {"antes": None, "despues": "activo"},
            },
        )

    def test_post_b_una_persona_fisica_audita_nombre_y_apellido_y_no_los_datos_que_no_se_cargaron(self):
        """CMP-ALT-PRV postcondición b: el teléfono y las especialidades solo figuran si se indicaron; la razón social, solo en una jurídica."""
        self.alta(tipo="fisica", razon_social="", nombre="Ana", apellido="Gómez")
        cambios = RegistroAuditoria.objects.get(accion=ALTA).detalle["cambios"]
        self.assertEqual(set(cambios), {"tipo_proveedor", "cuit", "nombre", "apellido", "email", "estado"})
        self.assertEqual(cambios["nombre"], {"antes": None, "despues": "Ana"})

    def test_post_b_el_registro_se_lee_en_la_pantalla_de_auditoria(self):
        """D-36: las filas de cambios se muestran con el nombre visible de cada campo y de cada valor."""
        categoria = tipo_de_insumo("Limpieza")
        self.alta(especialidades=[categoria.pk])
        filas = RegistroAuditoria.objects.get(accion=ALTA).filas_de_cambios()
        self.assertEqual(
            filas,
            [
                ("Email", "—", "ventas@semillasdelsur.com"),
                ("Estado", "—", "Activo"),
                ("CUIT", "—", cuit_valido(1)),
                ("Razón social", "—", "Semillas del Sur S. A."),
                ("Tipo de proveedor", "—", "Persona jurídica"),
                ("Categorías de insumos", "—", "Limpieza"),
            ],
        )

    def test_post_b_un_alta_rechazada_no_deja_registro(self):
        """D-22: la auditoría se escribe en la misma transacción; si el alta falla, no queda ningún registro."""
        with self.assertRaises(ValidationError):
            self.alta(email="")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())


class CmpAltPrvReactivacionTests(TestCase):
    """Postcondición c y regla 2 de CMP-ALT-PRV: reactivar al inactivo con ese CUIT en lugar de crear uno nuevo (mismo criterio que MD-48
    para clientes). Es parte del caso de uso de alta (no de modificar), como el cliente (D-58, consecuencias)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.limpieza = tipo_de_insumo("Limpieza")
        self.inactivo = proveedor("Agro Norte S. R. L.", n=1, activo=False, email="viejo@agronorte.com", telefono="376 400-1001")

    def reactivar(self, actor=GERENTE, **cambios):
        return proveedores.reactivar_proveedor(self.gerente if actor is GERENTE else actor, self.inactivo.pk, datos_de(self.inactivo, **cambios))

    def test_pre_a_solo_un_gerente_activo_reactiva(self):
        """CMP-ALT-PRV precondición a: solo el Gerente."""
        for actor in (crear_agronomo(), crear_capataz(), crear_administrador(), None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                self.reactivar(actor=actor)
        self.inactivo.refresh_from_db()
        self.assertEqual(self.inactivo.estado_proveedor, "inactivo")

    def test_post_c_el_proveedor_pasa_a_activo_con_los_datos_indicados(self):
        """CMP-ALT-PRV postcondición c: pasó a «activo» con los datos que el actor indicó; es el mismo proveedor, no uno nuevo."""
        cantidad = Proveedor.objects.count()
        reactivado = self.reactivar(
            razon_social="Agro Norte S. A.", email="ventas@agronorte.com", telefono="", especialidades=[self.limpieza.pk]
        )
        reactivado.refresh_from_db()
        self.assertEqual(reactivado.pk, self.inactivo.pk)
        self.assertEqual(Proveedor.objects.count(), cantidad)
        self.assertEqual(reactivado.estado_proveedor, "activo")
        self.assertEqual(
            (reactivado.razon_social_proveedor, reactivado.email_proveedor, reactivado.telefono_proveedor),
            ("Agro Norte S. A.", "ventas@agronorte.com", ""),
        )
        self.assertEqual(list(reactivado.especialidades.all()), [self.limpieza])

    def test_post_c_el_cuit_y_el_tipo_no_cambian(self):
        """CMP-ALT-PRV regla 2: el proveedor se reconoce por su CUIT; reactivar no lo cambia ni cambia el tipo."""
        reactivado = self.reactivar(cuit=cuit_valido(7), nombre="Ana", apellido="Gómez")
        self.assertEqual((reactivado.cuit_proveedor, reactivado.tipo_proveedor, reactivado.nombre_proveedor), (cuit_valido(1), "juridica", ""))

    def test_regla_4_de_mod_una_categoria_dada_de_baja_conserva_su_vinculo_al_reactivar(self):
        """CMP-MOD-PRV regla 4 (mismos datos que el alta): los vínculos a categorías dadas de baja se conservan."""
        vieja = tipo_de_insumo("Vieja", activo=False)
        self.inactivo.especialidades.set([vieja])
        reactivado = self.reactivar(especialidades=[self.limpieza.pk])
        self.assertEqual(set(reactivado.especialidades.all()), {vieja, self.limpieza})

    def test_post_c_audita_la_reactivacion_con_el_cambio_de_estado_y_los_datos_que_cambiaron(self):
        """CMP-ALT-PRV postcondición c y D-36: un log ``reactivacion_proveedor`` con el cambio de estado (más lo modificado), y ningún ``alta_proveedor``."""
        self.reactivar(email="ventas@agronorte.com")
        registro = RegistroAuditoria.objects.get(accion=REACTIVACION)
        self.assertEqual((registro.usuario_id, registro.rol), (self.gerente.pk, "gerente"))
        self.assertEqual(registro.afectados, [afectado_de(self.inactivo)])
        self.assertEqual(
            registro.detalle["cambios"],
            {
                "estado": {"antes": "inactivo", "despues": "activo"},
                "email": {"antes": "viejo@agronorte.com", "despues": "ventas@agronorte.com"},
            },
        )
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ALTA).exists())

    def test_post_c_sin_cambios_de_datos_solo_registra_el_estado(self):
        """CMP-ALT-PRV postcondición c: si el actor no cambia ningún dato, el log trae solo el cambio de estado."""
        self.reactivar()
        registro = RegistroAuditoria.objects.get(accion=REACTIVACION)
        self.assertEqual(registro.detalle["cambios"], {"estado": {"antes": "inactivo", "despues": "activo"}})

    def test_regla_1_los_datos_se_validan_como_en_el_alta_y_no_se_reactiva_si_hay_errores(self):
        """CMP-ALT-PRV regla 1 y postcondición c: los mismos controles; con un error de campo el proveedor sigue inactivo y no se audita."""
        error = error_de(lambda: self.reactivar(email="", telefono="abc"))
        self.assertEqual(set(error.error_dict), {"email", "telefono"})
        self.inactivo.refresh_from_db()
        self.assertEqual(self.inactivo.estado_proveedor, "inactivo")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=REACTIVACION).exists())

    def test_regla_2_un_proveedor_activo_no_se_reactiva(self):
        """CMP-ALT-PRV postcondición c: solo se reactiva a un inactivo (``proveedor_no_inactivo``)."""
        activo = proveedor("Semillas del Sur S. A.", n=2)
        with self.assertRaises(ErrorDeCompras) as contexto:
            proveedores.reactivar_proveedor(self.gerente, activo.pk, datos_de(activo))
        self.assertEqual(contexto.exception.codigo, "proveedor_no_inactivo")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=REACTIVACION).exists())

    def test_un_proveedor_que_no_existe_da_404(self):
        """docs/patrones/abm.md, sección 2: un id inexistente da ``Http404``."""
        with self.assertRaises(Http404):
            proveedores.reactivar_proveedor(self.gerente, 999999, datos_de_alta())

    def test_regla_4_de_baj_se_reactiva_con_el_alta_al_ingresar_su_cuit(self):
        """CMP-BAJ-PRV regla 4 y CMP-ALT-PRV regla 2: baja, nueva alta con el mismo CUIT (se ofrece reactivar) y reactivación."""
        activo = proveedores.alta_proveedor(self.gerente, datos_de_alta(cuit=cuit_valido(5)))
        proveedores.baja_proveedor(self.gerente, activo.pk)
        with self.assertRaises(ErrorDeCompras) as contexto:
            proveedores.alta_proveedor(self.gerente, datos_de_alta(cuit=cuit_valido(5)))
        self.assertEqual(contexto.exception.datos, {"proveedor_id": activo.pk})
        reactivado = proveedores.reactivar_proveedor(
            self.gerente, contexto.exception.datos["proveedor_id"], datos_de_alta(cuit=cuit_valido(5), email="nuevo@mail.com")
        )
        self.assertEqual((reactivado.pk, reactivado.estado_proveedor, reactivado.email_proveedor), (activo.pk, "activo", "nuevo@mail.com"))
        self.assertEqual(Proveedor.objects.filter(cuit_proveedor=cuit_valido(5)).count(), 1)
