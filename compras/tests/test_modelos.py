# Pruebas del modelo Proveedor (CMP-01, paso 1): restricciones de la base, relación con las categorías de insumos, texto para la
# auditoría y alcance por usuario. Fuente: docs/modelo/compras.md («Proveedor»), docs/casos_de_uso/compras/proveedores.md (reglas de
# CMP-ALT-PRV y CMP-CNS-PRV) y D-87.

from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError, transaction
from django.test import TestCase

from compras.models import Proveedor
from compras.tests.fabricas import cuit_valido, proveedor, tipo_de_insumo
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from maestros.tests.fabricas import crear_agronomo, crear_vendedor


class ProveedorRestriccionesTests(TestCase):
    """Lo que la base garantiza por sí sola (respaldo de las reglas del servicio)."""

    def crear_directo(self, **campos):
        """Un ``Proveedor`` jurídico válido, con ``campos`` pisados, dentro de un punto de guardado para seguir usando la prueba."""
        datos = {
            "tipo_proveedor": "juridica",
            "cuit_proveedor": cuit_valido(1),
            "razon_social_proveedor": "Semillas del Sur S. A.",
            "email_proveedor": "ventas@semillasdelsur.com",
        }
        datos.update(campos)
        with transaction.atomic():
            return Proveedor.objects.create(**datos)

    def rechazo(self, excepcion=IntegrityError, **campos):
        """El texto con que la base rechaza crear un proveedor con ``campos`` (falla la prueba si no lo rechaza)."""
        with self.assertRaises(excepcion) as contexto:
            self.crear_directo(**campos)
        return str(contexto.exception)

    def test_regla_2_el_cuit_es_unico_entre_activos_e_inactivos(self):
        """CMP-ALT-PRV regla 2 (H14): dos proveedores no comparten CUIT, aunque el primero esté dado de baja."""
        proveedor(n=1, activo=False)
        with self.assertRaises(IntegrityError) as contexto:
            self.crear_directo(cuit_proveedor=cuit_valido(1))
        self.assertIn("proveedor_cuit_unico", str(contexto.exception))

    def test_regla_2_el_cuit_tiene_once_digitos(self):
        """CMP-ALT-PRV regla 2 y modelo (MD-122): el CUIT guardado son 11 dígitos, sin guiones ni letras."""
        for cuit in ("3071234567", "3071234567A", "30-712345-1"):
            with self.subTest(cuit=cuit):
                self.assertIn("proveedor_cuit_11_digitos", self.rechazo(cuit_proveedor=cuit))

    def test_regla_2_un_cuit_con_mas_de_once_caracteres_no_entra_en_la_columna(self):
        """CMP-ALT-PRV regla 2: la columna es de 11 caracteres; «30-71234567-1» (con guiones) no se guarda tal cual."""
        for cuit in ("307123456712", "30-71234567-1"):
            with self.subTest(cuit=cuit):
                self.rechazo(DataError, cuit_proveedor=cuit)

    def test_regla_1_una_persona_juridica_lleva_razon_social_y_no_nombre_ni_apellido(self):
        """CMP-ALT-PRV regla 1: razón social si es una organización; el nombre y el apellido quedan vacíos."""
        for campos in (
            {"razon_social_proveedor": ""},
            {"nombre_proveedor": "Ana"},
            {"apellido_proveedor": "Gómez"},
        ):
            with self.subTest(campos=campos):
                self.assertIn("proveedor_datos_segun_tipo", self.rechazo(**campos))

    def test_regla_1_una_persona_fisica_lleva_nombre_y_apellido_y_no_razon_social(self):
        """CMP-ALT-PRV regla 1: nombre y apellido si es una persona; la razón social queda vacía."""
        fisica = {"tipo_proveedor": "fisica", "razon_social_proveedor": "", "nombre_proveedor": "Ana", "apellido_proveedor": "Gómez"}
        self.assertEqual(str(self.crear_directo(**fisica)), "Ana Gómez")
        for pisado in (
            {"nombre_proveedor": "", "cuit_proveedor": cuit_valido(2)},
            {"apellido_proveedor": "", "cuit_proveedor": cuit_valido(3)},
            {"razon_social_proveedor": "Semillas", "cuit_proveedor": cuit_valido(4)},
        ):
            with self.subTest(pisado=pisado):
                self.assertIn("proveedor_datos_segun_tipo", self.rechazo(**{**fisica, **pisado}))

    def test_regla_1_el_tipo_y_el_estado_son_de_una_lista_cerrada(self):
        """Modelo de compras: ``tipo_proveedor`` es juridica o fisica y ``estado_proveedor`` es activo o inactivo. Un tipo inválido
        lo rechaza ya la restricción por tipo (que lo implica) o la propia lista; cualquiera de las dos basta."""
        texto = self.rechazo(tipo_proveedor="otro")
        self.assertTrue("proveedor_tipo_valido" in texto or "proveedor_datos_segun_tipo" in texto)
        self.assertIn("proveedor_estado_valido", self.rechazo(estado_proveedor="suspendido"))

    def test_regla_1_el_telefono_es_opcional_y_el_correo_obligatorio_en_el_modelo(self):
        """CMP-ALT-PRV regla 1 (P5): sin teléfono se guarda; el correo es un campo obligatorio del formulario del modelo."""
        creado = self.crear_directo()
        self.assertEqual(creado.telefono_proveedor, "")
        creado.email_proveedor = ""
        with self.assertRaises(ValidationError) as contexto:
            creado.full_clean()
        self.assertIn("email_proveedor", contexto.exception.error_dict)

    def test_nuevo_proveedor_queda_activo_por_defecto(self):
        """CMP-ALT-PRV postcondición a: el proveedor se crea «activo»."""
        creado = self.crear_directo()
        self.assertEqual(creado.estado_proveedor, "activo")
        self.assertTrue(creado.activo)


class ProveedorEspecialidadesTests(TestCase):
    """«Se especializa en» (MD-121): una asociación nueva, opcional, con las categorías de insumos."""

    def test_regla_3_un_proveedor_puede_no_tener_especialidades(self):
        """CMP-ALT-PRV regla 3: cero o más tipos de insumo."""
        self.assertEqual(proveedor().especialidades.count(), 0)

    def test_regla_3_un_proveedor_se_especializa_en_varias_categorias_y_una_categoria_tiene_varios_proveedores(self):
        """CMP-ALT-PRV regla 3 (M2M, ``related_name="proveedores_especializados"``)."""
        limpieza, nutrientes = tipo_de_insumo("Limpieza"), tipo_de_insumo("Nutrientes")
        uno = proveedor(n=1, especialidades=[limpieza, nutrientes])
        otro = proveedor("Agro Norte S. R. L.", n=2, especialidades=[limpieza])
        self.assertEqual(set(uno.especialidades.all()), {limpieza, nutrientes})
        self.assertEqual(set(limpieza.proveedores_especializados.all()), {uno, otro})

    def test_regla_4_de_mod_una_categoria_dada_de_baja_conserva_el_vinculo(self):
        """CMP-MOD-PRV regla 4: si la categoría se da de baja, el vínculo sigue (el filtro de la pantalla muestra solo las activas)."""
        limpieza = tipo_de_insumo("Limpieza")
        creado = proveedor(especialidades=[limpieza])
        limpieza.estado_tipo_insumo = "inactivo"
        limpieza.save()
        self.assertEqual(list(creado.especialidades.all()), [limpieza])


class ProveedorTextoTests(TestCase):
    """El texto del proveedor, que es el que guarda la auditoría (D-36)."""

    def test_el_texto_de_una_organizacion_es_su_razon_social(self):
        """D-36: ``referencia(proveedor)`` guarda el ``__str__``."""
        self.assertEqual(str(proveedor("Semillas del Sur S. A.")), "Semillas del Sur S. A.")

    def test_el_texto_de_una_persona_es_nombre_y_apellido(self):
        """D-36: «Nombre Apellido»."""
        self.assertEqual(str(proveedor(n=2, tipo="fisica", nombre="Ana", apellido="Gómez")), "Ana Gómez")


class ProveedorAlcanceTests(TestCase):
    """Regla 1 de CMP-CNS-PRV: el Gerente y el Agrónomo activos ven todos los proveedores; nadie más."""

    def setUp(self):
        self.activo = proveedor(n=1)
        self.inactivo = proveedor("Agro Norte S. R. L.", n=2, activo=False)

    def test_regla_1_el_gerente_y_el_agronomo_ven_activos_e_inactivos(self):
        """CMP-CNS-PRV regla 1."""
        for cuenta in (crear_gerente(), crear_agronomo()):
            with self.subTest(rol=cuenta.rol):
                self.assertEqual(set(Proveedor.objects.en_alcance_de(cuenta)), {self.activo, self.inactivo})

    def test_regla_1_los_demas_roles_y_las_cuentas_inactivas_no_ven_ninguno(self):
        """CMP-CNS-PRV regla 1 y SEG-13."""
        sin_alcance = (
            crear_capataz(),
            crear_vendedor(),
            crear_administrador(),
            crear_agronomo(email="baja@infoponia.com", activo=False),
            None,
        )
        for cuenta in sin_alcance:
            with self.subTest(cuenta=cuenta):
                self.assertEqual(list(Proveedor.objects.en_alcance_de(cuenta)), [])


class AuditoriaDeProveedoresTests(TestCase):
    """Las cuatro acciones nuevas de ``core`` (D-87 punto 8): están en la lista cerrada y el Gerente las ve (acciones de negocio)."""

    def test_las_cuatro_acciones_existen_y_son_de_negocio(self):
        """D-36: cada acción nueva se clasifica; las de proveedores son de negocio, así el Gerente las ve en «Auditoría»."""
        from core.models import ACCIONES_DE_NEGOCIO

        Accion = RegistroAuditoria.Accion
        nuevas = {Accion.ALTA_PROVEEDOR, Accion.MODIFICACION_PROVEEDOR, Accion.BAJA_PROVEEDOR, Accion.REACTIVACION_PROVEEDOR}
        self.assertEqual({a.value for a in nuevas}, {"alta_proveedor", "modificacion_proveedor", "baja_proveedor", "reactivacion_proveedor"})
        self.assertTrue(nuevas <= ACCIONES_DE_NEGOCIO)

    def test_los_campos_nuevos_tienen_nombre_visible(self):
        """docs/patrones/auditoria.md, paso 3: sin etiqueta la pantalla mostraría la clave tal cual."""
        etiquetas = RegistroAuditoria.ETIQUETAS
        for clave in ("tipo_proveedor", "cuit", "razon_social", "especialidades"):
            self.assertIn(clave, etiquetas)
        self.assertEqual(RegistroAuditoria.VALORES_VISIBLES["tipo_proveedor"], {"juridica": "Persona jurídica", "fisica": "Persona física"})
