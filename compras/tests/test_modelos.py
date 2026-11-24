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


# ---------------------------------------------------------------------------------------------------------------------------------
# CMP-02a, paso 1: Pedido, DetallePedido, InvitacionPedido, EnlaceProveedor, Cotizacion y DetalleCotizacion.
# Fuente: docs/modelo/compras.md y D-88. Lo que la base garantiza por sí sola (respaldo de las reglas de los servicios).
# ---------------------------------------------------------------------------------------------------------------------------------

from datetime import timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402

from django.utils import timezone  # noqa: E402

from compras.models import DetalleCotizacion, EnlaceProveedor, Pedido  # noqa: E402
from compras.tests.fabricas import cotizacion_de, detalle_de_pedido, enlace_de, invitar  # noqa: E402
from compras.tests.fabricas import pedido as armar_pedido  # noqa: E402
from core.tests.fabricas import crear_gerente  # noqa: E402
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo  # noqa: E402
from maestros.tests.fabricas import crear_agronomo, crear_agronomo_con_invernadero  # noqa: E402


class PedidosRestriccionesTests(ConDatosDeInventario, TestCase):
    """Las restricciones de la base de los pedidos, sus detalles, invitaciones, enlaces y cotizaciones."""

    def setUp(self):
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero()
        self.existencia = existencia(insumo(), self.invernadero, minimo=10, precio="12.50")
        self.proveedor = proveedor()
        self.pedido = armar_pedido(self.agronomo)

    def rechazo(self, crear, restriccion):
        """Falla la prueba si la base no rechaza ``crear()`` con un ``IntegrityError`` que nombre ``restriccion``."""
        with self.assertRaises(IntegrityError) as contexto:
            with transaction.atomic():
                crear()
        nombres = (restriccion,) if isinstance(restriccion, str) else restriccion
        self.assertTrue(any(n in str(contexto.exception) for n in nombres), str(contexto.exception))

    def crear_pedido_crudo(self, **campos):
        """Un ``Pedido`` con fecha límite pasado mañana y ``campos`` pisados, sin pasar por la fábrica."""
        hoy = timezone.localdate()
        datos = {"agronomo": self.agronomo, "fecha_pedido": hoy, "fecha_limite_cotizaciones": hoy + timedelta(days=2)}
        datos.update(campos)
        return Pedido.objects.create(**datos)

    # ---- Pedido ----

    def test_regla_pedido_nace_en_cotizacion_sin_fecha_de_cierre(self):
        """CMP-RLZ-PED postcondición a: el pedido nace «en cotización» y sin fecha de cierre; se muestra como «P-0031»."""
        self.assertEqual(self.pedido.estado_pedido, "en_cotizacion")
        self.assertIsNone(self.pedido.fecha_cierre_pedido)
        self.assertEqual(str(self.pedido), f"P-{self.pedido.pk:04d}")
        self.assertTrue(self.pedido.en_cotizacion)

    def test_modelo_pedido_cerrado_o_cancelado_exige_fecha_de_cierre_y_en_cotizacion_no_la_tiene(self):
        """Modelo «Pedido»: ``estado ∈ {cerrado, cancelado}`` ⇔ ``fecha_cierre_pedido`` no nula (MD-124)."""
        with self.subTest("cerrado sin fecha de cierre"):
            self.rechazo(lambda: self.crear_pedido_crudo(estado_pedido="cerrado"), "pedido_cierre_coherente_con_estado")
        with self.subTest("en cotización con fecha de cierre"):
            self.rechazo(
                lambda: self.crear_pedido_crudo(fecha_cierre_pedido=timezone.localdate()), "pedido_cierre_coherente_con_estado"
            )

    def test_modelo_pedido_cancelado_exige_causa_y_solo_el_cancelado_la_tiene(self):
        """Modelo «Pedido»: ``estado = cancelado`` ⇔ ``causa_cancelacion`` no nula."""
        hoy = timezone.localdate()
        with self.subTest("cancelado sin causa"):
            self.rechazo(
                lambda: self.crear_pedido_crudo(estado_pedido="cancelado", fecha_cierre_pedido=hoy),
                "pedido_causa_coherente_con_estado",
            )
        with self.subTest("cerrado con causa"):
            self.rechazo(
                lambda: armar_pedido(self.agronomo, estado="cerrado", causa="nadie_cotizo"), "pedido_causa_coherente_con_estado"
            )

    def test_modelo_pedido_cancelacion_manual_exige_motivo_y_las_automaticas_no(self):
        """Modelo «Pedido» (MD-124): ``causa = manual`` ⇒ motivo no vacío; las automáticas guardan su texto fijo, pero la base no lo exige."""
        self.rechazo(
            lambda: armar_pedido(self.agronomo, estado="cancelado", causa="manual", motivo=""), "pedido_manual_con_motivo"
        )
        manual = armar_pedido(self.agronomo, estado="cancelado", causa="manual", motivo="Ya no hace falta")
        automatico = armar_pedido(self.agronomo, estado="cancelado", causa="nadie_cotizo")
        self.assertEqual((manual.causa_cancelacion, automatico.causa_cancelacion), ("manual", "nadie_cotizo"))

    def test_regla_fecha_limite_es_posterior_al_dia_del_pedido(self):
        """CMP-RLZ-PED regla «Fecha límite de cotizaciones»: como mínimo el día siguiente al del pedido (extensión 8a)."""
        hoy = timezone.localdate()
        self.rechazo(lambda: self.crear_pedido_crudo(fecha_limite_cotizaciones=hoy), "pedido_limite_posterior_al_pedido")

    def test_modelo_estado_y_causa_son_de_lista_cerrada(self):
        """Modelo «Pedido»: el estado y la causa solo toman los valores del modelo."""
        self.rechazo(
            lambda: armar_pedido(self.agronomo, estado="vencido", cerrado_el=timezone.localdate()),
            # Un estado inventado también rompe la coherencia con la fecha de cierre: Postgres informa la primera que encuentra.
            ("pedido_estado_valido", "pedido_cierre_coherente_con_estado"),
        )
        self.rechazo(
            lambda: armar_pedido(self.agronomo, estado="cancelado", causa="porque_si", motivo="x"), "pedido_causa_valida"
        )

    # ---- DetallePedido ----

    def test_regla_detalle_unico_un_par_insumo_invernadero_por_pedido(self):
        """CMP-RLZ-PED regla «Detalle único» (extensión 4b): un pedido no repite el par insumo–invernadero; en otro pedido sí."""
        detalle_de_pedido(self.pedido, self.existencia)
        self.rechazo(lambda: detalle_de_pedido(self.pedido, self.existencia), "detalle_pedido_unico_por_insumo_invernadero")
        detalle_de_pedido(armar_pedido(self.agronomo), self.existencia)

    def test_regla_detalle_cantidad_y_precio_son_mayores_que_cero(self):
        """CMP-RLZ-PED regla «Cantidad pedida» y modelo «DetallePedido»: cantidad > 0 y precio de referencia > 0."""
        self.rechazo(lambda: detalle_de_pedido(self.pedido, self.existencia, cantidad="0"), "detalle_pedido_cantidad_positiva")
        self.rechazo(lambda: detalle_de_pedido(self.pedido, self.existencia, precio="0"), "detalle_pedido_precio_positivo")

    def test_regla_monto_estimado_es_la_suma_de_cantidad_por_precio_de_referencia(self):
        """CMP-RLZ-PED regla «Precio y monto estimado»: el subtotal es cantidad × precio copiado (2 decimales) y el monto, su suma;
        ``con_monto`` da lo mismo que la suma de los subtotales."""
        otra = existencia(insumo("Fertilizante", unidad="kg"), self.invernadero, minimo=1, precio="3.33")
        d1 = detalle_de_pedido(self.pedido, self.existencia, cantidad="4", precio="12.50")
        d2 = detalle_de_pedido(self.pedido, otra, cantidad="2.5", precio="3.33")
        self.assertEqual((d1.subtotal, d2.subtotal), (Decimal("50.00"), Decimal("8.33")))
        self.assertEqual(Pedido.objects.con_monto().get(pk=self.pedido.pk).monto_estimado, Decimal("58.33"))
        self.assertEqual(Pedido.objects.con_monto().get(pk=armar_pedido(self.agronomo).pk).monto_estimado, Decimal("0.00"))

    # ---- InvitacionPedido y EnlaceProveedor ----

    def test_regla_un_proveedor_se_invita_una_sola_vez_por_pedido(self):
        """CMP-RLZ-PED postcondición c y R157: única ``(pedido, proveedor)``."""
        invitar(self.pedido, self.proveedor)
        self.rechazo(lambda: invitar(self.pedido, self.proveedor), "invitacion_pedido_unica_por_proveedor")

    def test_d88_a_lo_sumo_un_enlace_vigente_por_invitacion(self):
        """D-88 punto 1: índice único parcial «un ``vigente`` por invitación»; los demás estados pueden repetirse."""
        invitacion = invitar(self.pedido, self.proveedor)
        enlace_de(invitacion)
        self.rechazo(lambda: enlace_de(invitacion), "enlace_un_vigente_por_invitacion")
        enlace_de(invitacion, estado="reemplazado")
        enlace_de(invitacion, estado="anulado")

    def test_d88_usado_si_y_solo_si_tiene_fecha_de_uso(self):
        """Modelo «EnlaceProveedor»: ``estado = usado`` ⇔ ``fecha_uso`` no nula."""
        invitacion = invitar(self.pedido, self.proveedor)
        self.rechazo(
            lambda: EnlaceProveedor.objects.create(invitacion=invitacion, token_resumen="a" * 64, estado="usado"),
            "enlace_usado_coherente_con_fecha_de_uso",
        )
        self.rechazo(
            lambda: EnlaceProveedor.objects.create(
                invitacion=invitacion, token_resumen="b" * 64, estado="vigente", fecha_uso=timezone.now()
            ),
            "enlace_usado_coherente_con_fecha_de_uso",
        )

    def test_d88_el_resumen_del_token_es_unico_y_el_estado_de_envio_de_lista_cerrada(self):
        """D-88 punto 1: ``token_resumen`` único; ``estado_envio`` nulo, ``enviado`` o ``pendiente_envio``."""
        invitacion = invitar(self.pedido, self.proveedor)
        enlace, _ = enlace_de(invitacion, estado="anulado")
        self.rechazo(
            lambda: EnlaceProveedor.objects.create(invitacion=invitacion, token_resumen=enlace.token_resumen, estado="anulado"),
            "token_resumen",
        )
        self.rechazo(
            lambda: EnlaceProveedor.objects.create(
                invitacion=invitacion, token_resumen="c" * 64, estado="anulado", estado_envio="roto"
            ),
            "enlace_estado_envio_valido",
        )

    # ---- Cotizacion y DetalleCotizacion ----

    def test_c8_una_cotizacion_por_proveedor_y_por_pedido(self):
        """CMP-ENV-COT regla «Una cotización por proveedor y por pedido» (C8): única ``(pedido, proveedor)``; el mismo proveedor
        puede cotizar otro pedido."""
        detalle = detalle_de_pedido(self.pedido, self.existencia)
        cotizacion_de(self.pedido, self.proveedor, [(detalle, 10, "100.00", 3)])
        self.rechazo(
            lambda: cotizacion_de(self.pedido, self.proveedor, [(detalle, 10, "90.00", 3)]),
            "cotizacion_unica_por_pedido_y_proveedor",
        )
        cotizacion_de(armar_pedido(self.agronomo), self.proveedor, [])

    def test_regla_una_linea_por_detalle_del_pedido_en_cada_cotizacion(self):
        """CMP-ENV-COT regla «Líneas de la cotización»: a lo sumo una línea por detalle de pedido."""
        detalle = detalle_de_pedido(self.pedido, self.existencia)
        cotizacion = cotizacion_de(self.pedido, self.proveedor, [(detalle, 10, "100.00", 3)])
        self.rechazo(
            lambda: DetalleCotizacion.objects.create(
                cotizacion=cotizacion, detalle_pedido=detalle, cantidad_cotizada=1, total_linea=Decimal("1.00"), plazo_entrega_dias=1
            ),
            "linea_cotizacion_unica_por_detalle",
        )

    def test_regla_cantidad_total_y_plazo_de_la_linea(self):
        """CMP-ENV-COT reglas 6a y 6c con las actualizaciones de A0: cantidad > 0 (puede superar la pedida: P2), total > 0 y plazo ≥ 1."""
        detalle = detalle_de_pedido(self.pedido, self.existencia, cantidad="10")
        mayor = cotizacion_de(self.pedido, self.proveedor, [(detalle, 25, "250.00", 1)])
        self.assertEqual(mayor.lineas.get().cantidad_cotizada, Decimal("25.000"))
        for cantidad, total, plazo, restriccion in (
            (0, "10.00", 1, "linea_cotizacion_cantidad_positiva"),
            (5, "0", 1, "linea_cotizacion_total_positivo"),
            (5, "10.00", 0, "linea_cotizacion_plazo_minimo"),
        ):
            with self.subTest(restriccion=restriccion):
                otro = armar_pedido(self.agronomo)
                d = detalle_de_pedido(otro, self.existencia)
                self.rechazo(lambda: cotizacion_de(otro, self.proveedor, [(d, cantidad, total, plazo)]), restriccion)

    def test_regla_monto_de_la_cotizacion_es_la_suma_de_los_totales_de_sus_lineas(self):
        """CMP-ENV-COT regla «Subtotal y monto» (D-89 punto 5): el monto es derivado, la suma de los ``total_linea``."""
        otra = existencia(insumo("Fertilizante", unidad="kg"), self.invernadero, minimo=1)
        d1 = detalle_de_pedido(self.pedido, self.existencia)
        d2 = detalle_de_pedido(self.pedido, otra)
        cotizacion = cotizacion_de(self.pedido, self.proveedor, [(d1, 10, "100.10", 3), (d2, 10, "50.05", 2)])
        self.assertEqual(cotizacion.monto_cotizacion, Decimal("150.15"))
        self.assertEqual(cotizacion.estado_cotizacion, "propuesta")

    def test_regla_los_pedidos_se_ven_segun_el_rol(self):
        """CMP-CNS-PED regla 1: el Agrónomo ve los pedidos que él realizó; el Gerente, todos; nadie más."""
        otro_agronomo = crear_agronomo(email="otro.agronomo@infoponia.com")
        ajeno = armar_pedido(otro_agronomo)
        self.assertEqual(set(Pedido.objects.en_alcance_de(self.agronomo)), {self.pedido})
        self.assertEqual(set(Pedido.objects.en_alcance_de(crear_gerente())), {self.pedido, ajeno})
        sin_alcance = (
            crear_capataz(),
            crear_vendedor(),
            crear_administrador(),
            crear_agronomo(email="baja@infoponia.com", activo=False),
            None,
        )
        for cuenta in sin_alcance:
            with self.subTest(cuenta=cuenta):
                self.assertEqual(list(Pedido.objects.en_alcance_de(cuenta)), [])

    def test_las_dos_acciones_nuevas_son_de_negocio_y_los_campos_tienen_nombre_visible(self):
        """D-87 punto 8 y D-36: ``alta_pedido`` y ``alta_cotizacion`` están clasificadas; los campos nuevos tienen etiqueta y los
        roles externos, su texto («Proveedor (mediante enlace)»)."""
        from core.models import ACCIONES_DE_NEGOCIO

        Accion = RegistroAuditoria.Accion
        self.assertTrue({Accion.ALTA_PEDIDO, Accion.ALTA_COTIZACION} <= ACCIONES_DE_NEGOCIO)
        for clave in ("fecha_limite_cotizaciones", "monto_estimado", "detalles", "invitaciones", "monto_cotizacion", "lineas_cotizadas"):
            self.assertIn(clave, RegistroAuditoria.ETIQUETAS)
        self.assertEqual(RegistroAuditoria.VALORES_VISIBLES["rol"]["proveedor_enlace"], "Proveedor (mediante enlace)")
