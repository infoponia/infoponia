# Pruebas de CMP-MOD-PRV · Modificar Proveedor (docs/casos_de_uso/compras/proveedores.md). Cita D-22, D-28, D-36 y D-58.
#
# Servicios que se prueban (compras/servicios/proveedores.py), tomados del módulo dentro de cada prueba:
#   modificar_proveedor(actor, proveedor_id, datos) -> Proveedor
#     - ``datos``: las mismas claves que el alta (``cuit``, ``razon_social``, ``nombre``, ``apellido``, ``email``, ``telefono``,
#       ``especialidades``); el tipo NO se cambia (decisión del estudiante: queda fijo desde el alta) y una clave ``tipo`` se ignora.
#     - Precondición a: Gerente activo. Precondición b: el proveedor está activo (``ErrorDeCompras`` ``proveedor_inactivo``).
#     - Regla 1: las mismas validaciones que el alta, con el CUIT único entre todos (``cuit_repetido``) y validado (``cuit_invalido``).
#     - Regla 2: teléfono, correo, nombre, apellido, razón social y especialidades se modifican siempre; el CUIT no se modifica si el
#       proveedor tiene pedidos u órdenes (``tiene_pedidos_u_ordenes(proveedor)``, hoy ``False``: se completa en CMP-02a) → ``cuit_con_pedidos``.
#     - Regla 3: el correo cambia sin tocar los enlaces ya enviados (todavía no hay enlaces: se prueba en CMP-02a).
#     - Regla 4: el vínculo con una categoría dada de baja se conserva.
#     - D-28: sin cambios no se escribe ni se audita. Postcondición b: un registro ``modificacion_proveedor`` con los campos modificados.

from unittest import mock

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase

from compras.errores import ErrorDeCompras
from compras.tests.fabricas import GERENTE, afectado_de, con_guiones, cuit_valido, datos_de, proveedor, ref, tipo_de_insumo
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.tests.fabricas import perezoso
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_vendedor, error_de

proveedores = perezoso("compras.servicios.proveedores")
MODIFICACION = RegistroAuditoria.Accion.MODIFICACION_PROVEEDOR


class CmpModPrvServicioTests(TestCase):
    """Precondiciones, reglas y postcondiciones de CMP-MOD-PRV."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.limpieza = tipo_de_insumo("Limpieza")
        self.proveedor = proveedor("Semillas del Sur S. A.", n=1, telefono="376 400-1001", especialidades=[self.limpieza])

    def modificar(self, actor=GERENTE, **cambios):
        return proveedores.modificar_proveedor(self.gerente if actor is GERENTE else actor, self.proveedor.pk, datos_de(self.proveedor, **cambios))

    def error(self, **cambios):
        return error_de(lambda: self.modificar(**cambios))

    def registros(self):
        return RegistroAuditoria.objects.filter(accion=MODIFICACION)

    # ---- precondiciones ----

    def test_pre_a_solo_un_gerente_activo_modifica(self):
        """CMP-MOD-PRV precondición a: solo el Gerente (el Agrónomo consulta)."""
        for actor in (crear_agronomo(), crear_capataz(), crear_vendedor(), crear_administrador(), crear_gerente(email="b@infoponia.com", activo=False), None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                self.modificar(actor=actor, email="otro@mail.com")
        self.proveedor.refresh_from_db()
        self.assertEqual(self.proveedor.email_proveedor, "ventas@semillasdelsur.com")

    def test_pre_b_un_proveedor_inactivo_no_se_modifica(self):
        """CMP-MOD-PRV precondición b: el proveedor está «activo»; uno inactivo solo se reactiva (con el alta)."""
        inactivo = proveedor("Agro Norte S. R. L.", n=2, activo=False)
        with self.assertRaises(ErrorDeCompras) as contexto:
            proveedores.modificar_proveedor(self.gerente, inactivo.pk, datos_de(inactivo, email="otro@mail.com"))
        self.assertEqual(contexto.exception.codigo, "proveedor_inactivo")
        inactivo.refresh_from_db()
        self.assertNotEqual(inactivo.email_proveedor, "otro@mail.com")
        self.assertFalse(self.registros().exists())

    def test_un_proveedor_que_no_existe_da_404(self):
        """docs/patrones/abm.md, sección 2: un id inexistente da ``Http404``."""
        with self.assertRaises(Http404):
            proveedores.modificar_proveedor(self.gerente, 999999, datos_de(self.proveedor))

    # ---- postcondición a y regla 2: lo que se modifica siempre ----

    def test_regla_2_telefono_correo_razon_social_y_especialidades_se_modifican_siempre(self):
        """CMP-MOD-PRV regla 2 y postcondición a: teléfono, correo, razón social y especialidades se actualizan."""
        nutrientes = tipo_de_insumo("Nutrientes")
        modificado = self.modificar(
            razon_social="Semillas del Sur S. R. L.", email="info@semillasdelsur.com", telefono="", especialidades=[nutrientes.pk]
        )
        modificado.refresh_from_db()
        self.assertEqual(
            (modificado.razon_social_proveedor, modificado.email_proveedor, modificado.telefono_proveedor),
            ("Semillas del Sur S. R. L.", "info@semillasdelsur.com", ""),
        )
        self.assertEqual(list(modificado.especialidades.all()), [nutrientes])

    def test_regla_2_el_nombre_y_el_apellido_de_una_persona_fisica_se_modifican(self):
        """CMP-MOD-PRV regla 2: nombre y apellido de una persona física."""
        fisica = proveedor(n=3, tipo="fisica", nombre="Ana", apellido="Gómez")
        modificado = proveedores.modificar_proveedor(self.gerente, fisica.pk, datos_de(fisica, nombre="Anita", apellido="Gómez Paz"))
        self.assertEqual((modificado.nombre_proveedor, modificado.apellido_proveedor), ("Anita", "Gómez Paz"))

    def test_regla_2_el_tipo_no_se_cambia(self):
        """Decisión del estudiante (CMP-01): el tipo queda fijo desde el alta; una clave ``tipo`` o los datos del otro tipo se ignoran."""
        modificado = self.modificar(tipo="fisica", nombre="Ana", apellido="Gómez")
        modificado.refresh_from_db()
        self.assertEqual(
            (modificado.tipo_proveedor, modificado.razon_social_proveedor, modificado.nombre_proveedor, modificado.apellido_proveedor),
            ("juridica", "Semillas del Sur S. A.", "", ""),
        )
        self.assertFalse(self.registros().exists())

    def test_regla_2_el_cuit_se_modifica_si_no_tiene_pedidos_ni_ordenes(self):
        """CMP-MOD-PRV regla 2: sin pedidos ni órdenes el CUIT se puede corregir (en 11 dígitos, aunque se escriba con guiones)."""
        modificado = self.modificar(cuit=con_guiones(cuit_valido(9)))
        modificado.refresh_from_db()
        self.assertEqual(modificado.cuit_proveedor, cuit_valido(9))

    def test_regla_2_el_cuit_no_se_modifica_si_tiene_pedidos_u_ordenes(self):
        """CMP-MOD-PRV regla 2: con pedidos u órdenes, un CUIT distinto se rechaza (``cuit_con_pedidos``) y no cambia nada. La consulta
        ``tiene_pedidos_u_ordenes`` hoy da ``False``; CMP-02a la completa: acá se simula que da ``True``."""
        with mock.patch("compras.servicios.proveedores.tiene_pedidos_u_ordenes", return_value=True):
            error = self.error(cuit=cuit_valido(9), email="otro@mail.com")
        self.assertEqual(codigos_de(error, "cuit"), ["cuit_con_pedidos"])
        self.proveedor.refresh_from_db()
        self.assertEqual((self.proveedor.cuit_proveedor, self.proveedor.email_proveedor), (cuit_valido(1), "ventas@semillasdelsur.com"))
        self.assertFalse(self.registros().exists())

    def test_regla_2_con_pedidos_u_ordenes_el_mismo_cuit_no_es_un_cambio(self):
        """CMP-MOD-PRV regla 2: con pedidos u órdenes el resto de los datos se modifica siempre; mandar el mismo CUIT (aun con guiones) no lo cambia."""
        with mock.patch("compras.servicios.proveedores.tiene_pedidos_u_ordenes", return_value=True):
            modificado = self.modificar(cuit=con_guiones(cuit_valido(1)), email="otro@mail.com")
        self.assertEqual(modificado.email_proveedor, "otro@mail.com")

    def test_regla_2_hoy_la_consulta_de_pedidos_y_ordenes_da_falso(self):
        """«Cómo se aplica»: ``tiene_pedidos_u_ordenes`` ya existe y hoy da ``False`` (no hay pedidos hasta CMP-02a)."""
        self.assertFalse(proveedores.tiene_pedidos_u_ordenes(self.proveedor))

    # ---- regla 1: las mismas validaciones que el alta ----

    def test_regla_1_las_validaciones_son_las_del_alta(self):
        """CMP-MOD-PRV regla 1: correo obligatorio, razón social con contenido, teléfono con el formato de D-21 y CUIT válido; todos los errores juntos."""
        error = self.error(razon_social="  ", email="", telefono="abc", cuit="30712345670")
        self.assertEqual(set(error.error_dict), {"razon_social", "email", "telefono", "cuit"})
        self.assertEqual(codigos_de(error, "cuit"), ["cuit_invalido"])
        self.assertFalse(self.registros().exists())

    def test_regla_1_el_cuit_es_unico_entre_todos_activos_e_inactivos(self):
        """CMP-MOD-PRV regla 1 (H14): el CUIT de otro proveedor, activo o inactivo, se rechaza (``cuit_repetido``)."""
        proveedor("Agro Norte S. R. L.", n=2)
        proveedor("Vivero Viejo", n=3, activo=False)
        for n in (2, 3):
            with self.subTest(n=n):
                self.assertEqual(codigos_de(self.error(cuit=cuit_valido(n)), "cuit"), ["cuit_repetido"])

    def test_regla_1_el_telefono_puede_quedar_vacio(self):
        """CMP-MOD-PRV regla 1: el teléfono es opcional (P5)."""
        self.assertEqual(self.modificar(telefono="").telefono_proveedor, "")

    def test_regla_1_una_categoria_dada_de_baja_no_se_puede_elegir_de_nuevo(self):
        """CMP-MOD-PRV regla 1 y «Cómo se aplica»: solo categorías activas para elegir."""
        baja = tipo_de_insumo("Vieja", activo=False)
        self.assertEqual(codigos_de(self.error(especialidades=[baja.pk]), "especialidades"), ["categoria_inactiva"])

    # ---- regla 4: categorías dadas de baja ----

    def test_regla_4_el_vinculo_con_una_categoria_dada_de_baja_se_conserva(self):
        """CMP-MOD-PRV regla 4: si una categoría se da de baja, el vínculo se conserva aunque la pantalla no la muestre al elegir."""
        vieja = tipo_de_insumo("Vieja")
        self.proveedor.especialidades.add(vieja)
        vieja.estado_tipo_insumo = "inactivo"
        vieja.save()
        nutrientes = tipo_de_insumo("Nutrientes")
        modificado = self.modificar(especialidades=[self.limpieza.pk, nutrientes.pk])
        self.assertEqual(set(modificado.especialidades.all()), {vieja, self.limpieza, nutrientes})

    def test_regla_4_se_puede_quitar_una_categoria_activa_pero_no_una_dada_de_baja(self):
        """CMP-MOD-PRV regla 2 y 4: quitar de la lista una categoría activa la desvincula; las dadas de baja no se ofrecen, así que quedan."""
        vieja = tipo_de_insumo("Vieja")
        self.proveedor.especialidades.add(vieja)
        vieja.estado_tipo_insumo = "inactivo"
        vieja.save()
        modificado = self.modificar(especialidades=[])
        self.assertEqual(list(modificado.especialidades.all()), [vieja])

    # ---- D-28: sin cambios ----

    def test_d28_sin_cambios_no_se_escribe_ni_se_audita(self):
        """D-28: si los datos no cambian (ni siquiera el orden de las especialidades), no se guarda y no se deja registro."""
        self.modificar(cuit=con_guiones(cuit_valido(1)), razon_social="  Semillas del Sur S. A. ")
        self.assertFalse(self.registros().exists())

    # ---- postcondición b: auditoría ----

    def test_post_b_audita_solo_los_campos_modificados_con_antes_y_despues(self):
        """CMP-MOD-PRV postcondición b y D-36: usuario, rol, identificador y los campos modificados con su valor anterior y nuevo."""
        nutrientes = tipo_de_insumo("Nutrientes")
        self.modificar(email="info@semillasdelsur.com", telefono="", especialidades=[self.limpieza.pk, nutrientes.pk])
        registro = self.registros().get()
        self.assertEqual((registro.usuario_id, registro.rol), (self.gerente.pk, "gerente"))
        self.assertEqual(registro.afectados, [afectado_de(self.proveedor)])
        self.assertEqual(
            registro.detalle["cambios"],
            {
                "email": {"antes": "ventas@semillasdelsur.com", "despues": "info@semillasdelsur.com"},
                "telefono": {"antes": "376 400-1001", "despues": ""},
                "especialidades": {"antes": [ref(self.limpieza)], "despues": [ref(self.limpieza), ref(nutrientes)]},
            },
        )

    def test_post_b_la_auditoria_lista_los_nombres_de_las_categorias_antes_y_despues(self):
        """«Cómo se aplica»: la auditoría de la modificación lista los nombres de las categorías antes y después (se lee en pantalla)."""
        nutrientes = tipo_de_insumo("Nutrientes")
        self.modificar(especialidades=[nutrientes.pk])
        filas = dict((campo, (antes, despues)) for campo, antes, despues in self.registros().get().filas_de_cambios())
        self.assertEqual(filas["Categorías de insumos"], ("Limpieza", "Nutrientes"))

    def test_post_b_un_cambio_de_cuit_se_audita_con_los_once_digitos(self):
        """CMP-MOD-PRV postcondición b: el CUIT se registra con sus 11 dígitos, como cuit_organizacion en perfil.py (los guiones se agregan al mostrar, D-58)."""
        self.modificar(cuit=cuit_valido(9))
        self.assertEqual(
            self.registros().get().detalle["cambios"], {"cuit": {"antes": cuit_valido(1), "despues": cuit_valido(9)}}
        )

    def test_post_b_una_modificacion_rechazada_no_deja_registro(self):
        """D-22: la auditoría se escribe en la misma transacción; si la modificación falla no queda registro ni cambio."""
        self.error(razon_social="", email="otro@mail.com")
        self.assertFalse(self.registros().exists())
        self.proveedor.refresh_from_db()
        self.assertEqual(self.proveedor.email_proveedor, "ventas@semillasdelsur.com")
