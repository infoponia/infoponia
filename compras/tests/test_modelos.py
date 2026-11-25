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


# ---------------------------------------------------------------------------------------------------------------------------------
# CMP-03, paso 1: OrdenCompra y DetalleOrdenCompra. Fuente: docs/modelo/compras.md («OrdenCompra», «DetalleOrdenCompra»), reglas 13, 16, 18, 23 y 24
# de 8.16, D-89 (total guardado, unitario derivado) y D-87 punto 8 (acciones de auditoría).
# ---------------------------------------------------------------------------------------------------------------------------------

from compras.models import DetalleOrdenCompra, OrdenCompra  # noqa: E402
from compras.precios import precio_unitario  # noqa: E402
from compras.tests.fabricas import orden_de  # noqa: E402


class OrdenesRestriccionesTests(ConDatosDeInventario, TestCase):
    """Las restricciones de la base de las órdenes de compra y de sus detalles, y lo que se deriva (monto, R026, proveedor, alcance)."""

    def setUp(self):
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero()
        self.gerente = crear_gerente()
        self.existencia = existencia(insumo(), self.invernadero, minimo=10, precio="12.50")
        self.proveedor_a = proveedor(n=1)
        self.proveedor_b = proveedor("Vivero Norte S. R. L.", n=2, email="vivero@norte.com")
        self.pedido = armar_pedido(self.agronomo)
        self.detalle = detalle_de_pedido(self.pedido, self.existencia, cantidad="20")
        self.cotizacion = cotizacion_de(self.pedido, self.proveedor_a, [(self.detalle, "12", "120.00", 3)])
        self.otra = cotizacion_de(self.pedido, self.proveedor_b, [(self.detalle, "8", "100.00", 5)])

    def rechazo(self, crear, restriccion):
        """Falla la prueba si la base no rechaza ``crear()`` con un ``IntegrityError`` que nombre ``restriccion``."""
        with self.assertRaises(IntegrityError) as contexto:
            with transaction.atomic():
                crear()
        self.assertIn(restriccion, str(contexto.exception))

    def orden_cruda(self, pedido=None, **campos):
        """Una ``OrdenCompra`` con ``campos`` pisados, sin pasar por la fábrica."""
        datos = {"pedido": pedido or self.pedido, "fecha_emision": timezone.localdate()}
        datos.update(campos)
        return OrdenCompra.objects.create(**datos)

    def otro_agronomo_con_orden(self):
        """Un segundo Agrónomo con su invernadero, su pedido y su orden. Devuelve ``(agronomo, pedido, detalle_de_pedido, orden)``."""
        agronomo, invernadero = crear_agronomo_con_invernadero(email="otro.agronomo@infoponia.com", nombre="Invernadero Sur")
        ajena = existencia(insumo("Fertilizante"), invernadero, minimo=10, precio="5.00")
        pedido = armar_pedido(agronomo)
        detalle = detalle_de_pedido(pedido, ajena, cantidad="5")
        orden = orden_de(pedido, [cotizacion_de(pedido, self.proveedor_a, [(detalle, "5", "25.00", 2)])])
        return agronomo, pedido, detalle, orden

    def test_regla_13_de_8_16_un_pedido_tiene_a_lo_sumo_una_orden(self):
        """Regla 13 de 8.16: la base impide dos órdenes para el mismo pedido (``OneToOne``); se llega a ella con ``pedido.orden_compra``."""
        orden = self.orden_cruda()
        self.assertEqual(self.pedido.orden_compra, orden)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.orden_cruda()

    def test_regla_orden_nace_pendiente_sin_gerente_ni_fecha_de_resolucion(self):
        """CMP-GNR-ODC postcondición a: la orden nace «pendiente de aprobación», sin Gerente ni resolución; se muestra como «OC-0007»."""
        orden = self.orden_cruda()
        self.assertEqual(orden.estado_orden_compra, "pendiente_aprobacion")
        self.assertTrue(orden.pendiente)
        self.assertIsNone(orden.gerente)
        self.assertIsNone(orden.fecha_resolucion)
        self.assertEqual(str(orden), f"OC-{orden.pk:04d}")
        self.assertEqual(str(OrdenCompra()), "OC-nueva")

    def test_regla_orden_resuelta_si_y_solo_si_tiene_gerente_y_fecha_de_resolucion(self):
        """CMP-APR-ODC regla «Orden resoluble» (R011): una orden tiene Gerente y fecha de resolución si y solo si está resuelta."""
        hoy = timezone.localdate()
        coherente = "orden_resolucion_coherente_con_estado"
        self.rechazo(lambda: self.orden_cruda(estado_orden_compra="aprobada"), coherente)
        self.rechazo(lambda: self.orden_cruda(estado_orden_compra="aprobada", gerente=self.gerente), coherente)
        self.rechazo(lambda: self.orden_cruda(estado_orden_compra="aprobada", fecha_resolucion=hoy), coherente)
        self.rechazo(lambda: self.orden_cruda(gerente=self.gerente, fecha_resolucion=hoy), coherente)
        self.rechazo(lambda: self.orden_cruda(fecha_resolucion=hoy), coherente)
        aprobada = self.orden_cruda(estado_orden_compra="aprobada", gerente=self.gerente, fecha_resolucion=hoy)
        self.assertFalse(aprobada.pendiente)

    def test_regla_orden_rechazada_si_y_solo_si_tiene_motivo(self):
        """CMP-APR-ODC regla «Rechazo»: el motivo es obligatorio al rechazar y solo una orden rechazada lo tiene."""
        hoy = timezone.localdate()
        coherente = "orden_motivo_de_rechazo_coherente_con_estado"
        resuelta = {"gerente": self.gerente, "fecha_resolucion": hoy}
        self.rechazo(lambda: self.orden_cruda(estado_orden_compra="rechazada", **resuelta), coherente)
        self.rechazo(lambda: self.orden_cruda(estado_orden_compra="aprobada", motivo_rechazo="No hay presupuesto", **resuelta), coherente)
        self.rechazo(lambda: self.orden_cruda(motivo_rechazo="No hay presupuesto"), coherente)
        rechazada = self.orden_cruda(estado_orden_compra="rechazada", motivo_rechazo="No hay presupuesto", **resuelta)
        self.assertEqual(rechazada.motivo_rechazo, "No hay presupuesto")

    def test_regla_24_de_8_16_el_estado_de_la_orden_es_de_lista_cerrada(self):
        """Regla 24 de 8.16: seis estados (pendiente, aprobada, rechazada, parcialmente recibida, recibida, recibida con faltante)."""
        self.rechazo(lambda: self.orden_cruda(estado_orden_compra="cancelada"), "orden_estado_valido")
        self.assertEqual(
            [valor for valor, _ in OrdenCompra.Estado.choices],
            ["pendiente_aprobacion", "aprobada", "rechazada", "parcialmente_recibida", "recibida", "recibida_con_faltante"],
        )

    def test_regla_16_de_8_16_cada_linea_de_cotizacion_genera_un_solo_detalle_de_orden(self):
        """Regla 16 de 8.16 y R023: el detalle copia cantidad y total de su línea; una línea no genera dos detalles."""
        orden = orden_de(self.pedido, [self.cotizacion])
        detalle = orden.detalles.get()
        self.assertEqual(detalle.cantidad_detalle_orden, Decimal("12.000"))
        self.assertEqual(detalle.total_linea, Decimal("120.00"))
        self.assertEqual(detalle.estado_detalle_orden, "pendiente")
        self.assertIsNone(detalle.fecha_entrega_esperada)
        linea = self.cotizacion.lineas.get()
        self.assertEqual(linea.detalle_orden, detalle)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DetalleOrdenCompra.objects.create(orden=orden, detalle_cotizacion=linea, cantidad_detalle_orden="1", total_linea="1")

    def test_regla_5_de_8_17_r026_y_el_proveedor_se_derivan_de_la_linea(self):
        """Regla 5 de 8.17 (técnico): el detalle del pedido y el proveedor de un detalle de orden salen de su línea de cotización."""
        detalle = orden_de(self.pedido, [self.cotizacion]).detalles.get()
        self.assertEqual(detalle.detalle_pedido, self.detalle)
        self.assertEqual(detalle.proveedor, self.proveedor_a)
        self.assertEqual(str(detalle), str(self.detalle))

    def test_regla_detalle_cantidad_y_total_son_mayores_que_cero(self):
        """Modelo, «DetalleOrdenCompra»: cantidad y total de la línea mayores que cero."""
        orden = self.orden_cruda()
        linea = self.cotizacion.lineas.get()
        for campos, restriccion in (
            ({"cantidad_detalle_orden": "0", "total_linea": "10"}, "detalle_orden_cantidad_positiva"),
            ({"cantidad_detalle_orden": "1", "total_linea": "0"}, "detalle_orden_total_positivo"),
        ):
            with self.subTest(restriccion=restriccion):
                self.rechazo(lambda: DetalleOrdenCompra.objects.create(orden=orden, detalle_cotizacion=linea, **campos), restriccion)

    def test_regla_detalle_estado_y_cierre_con_faltante_coherentes(self):
        """Modelo, «DetalleOrdenCompra»: cerrado con faltante ⇔ motivo y fecha de cierre; el estado es de lista cerrada."""
        detalle = orden_de(self.pedido, [self.cotizacion]).detalles.get()
        coherente = "detalle_orden_faltante_coherente_con_estado"
        hoy = timezone.localdate()
        for campos in (
            {"estado_detalle_orden": "cerrado_con_faltante"},
            {"estado_detalle_orden": "cerrado_con_faltante", "motivo_cierre_faltante": "No llegó"},
            {"estado_detalle_orden": "cerrado_con_faltante", "fecha_cierre_faltante": hoy},
            {"motivo_cierre_faltante": "No llegó"},
            {"fecha_cierre_faltante": hoy},
        ):
            with self.subTest(campos=campos):
                self.rechazo(lambda: DetalleOrdenCompra.objects.filter(pk=detalle.pk).update(**campos), coherente)
        self.rechazo(lambda: DetalleOrdenCompra.objects.filter(pk=detalle.pk).update(estado_detalle_orden="perdido"), "detalle_orden_estado_valido")
        DetalleOrdenCompra.objects.filter(pk=detalle.pk).update(
            estado_detalle_orden="cerrado_con_faltante", motivo_cierre_faltante="No llegó", fecha_cierre_faltante=hoy
        )

    def test_regla_18_de_8_16_el_monto_es_la_suma_de_los_totales_de_sus_detalles(self):
        """Regla 18 de 8.16 y D-89 punto 5: monto = Σ total de línea; es derivado (propiedad y anotación), no una columna."""
        orden = orden_de(self.pedido, [self.cotizacion, self.otra])
        self.assertEqual(orden.monto_total, Decimal("220.00"))
        self.assertEqual(OrdenCompra.objects.con_monto().get(pk=orden.pk).monto_orden, Decimal("220.00"))
        vacia = self.orden_cruda(pedido=armar_pedido(self.agronomo))
        self.assertEqual(vacia.monto_total, Decimal("0.00"))
        self.assertEqual(OrdenCompra.objects.con_monto().get(pk=vacia.pk).monto_orden, Decimal("0.00"))
        self.assertNotIn("monto_total", [campo.name for campo in OrdenCompra._meta.concrete_fields])

    def test_d89_el_unitario_de_la_orden_es_derivado_con_cuatro_decimales(self):
        """D-89 punto 1: el detalle de orden guarda el total; ``precio_unitario`` lo deriva con la cantidad de la orden (120 / 12 = 10,0000)."""
        detalle = orden_de(self.pedido, [self.cotizacion]).detalles.get()
        self.assertEqual(precio_unitario(detalle), Decimal("10.0000"))
        self.assertNotIn("precio_unitario", [campo.name for campo in DetalleOrdenCompra._meta.concrete_fields])

    def test_regla_las_ordenes_se_ven_segun_el_rol(self):
        """CMP-CNS-ODC regla 1: el Agrónomo ve las órdenes con algún destino a su cargo; el Gerente, todas; nadie más."""
        propia = orden_de(self.pedido, [self.cotizacion])
        otro_agronomo, _, _, ajena = self.otro_agronomo_con_orden()
        self.assertEqual(set(OrdenCompra.objects.en_alcance_de(self.agronomo)), {propia})
        self.assertEqual(set(OrdenCompra.objects.en_alcance_de(otro_agronomo)), {ajena})
        self.assertEqual(set(OrdenCompra.objects.en_alcance_de(self.gerente)), {propia, ajena})
        sin_alcance = (
            crear_capataz(),
            crear_vendedor(),
            crear_administrador(),
            crear_agronomo(email="baja@infoponia.com", activo=False),
            None,
        )
        for cuenta in sin_alcance:
            with self.subTest(cuenta=cuenta):
                self.assertEqual(list(OrdenCompra.objects.en_alcance_de(cuenta)), [])

    def test_regla_el_agronomo_ve_la_orden_si_algun_destino_esta_a_su_cargo(self):
        """CMP-CNS-ODC regla 1: una orden con destinos de dos Agrónomos la ven los dos (basta un destino a su cargo)."""
        otro_agronomo, invernadero = crear_agronomo_con_invernadero(email="otro.agronomo@infoponia.com", nombre="Invernadero Sur")
        segundo = detalle_de_pedido(self.pedido, existencia(insumo("Fertilizante"), invernadero, minimo=10, precio="5.00"), cantidad="5")
        cotizacion = cotizacion_de(self.pedido, proveedor("Hortalizas S. A.", n=3, email="h@h.com"), [(segundo, "5", "25.00", 2)])
        orden = orden_de(self.pedido, [self.otra, cotizacion])
        self.assertEqual(set(OrdenCompra.objects.en_alcance_de(self.agronomo)), {orden})
        self.assertEqual(set(OrdenCompra.objects.en_alcance_de(otro_agronomo)), {orden})

    def test_regla_una_orden_con_dos_detalles_no_se_repite_en_el_alcance(self):
        """El alcance del Agrónomo no duplica la orden aunque tenga varios detalles a su cargo."""
        orden = orden_de(self.pedido, [self.cotizacion, self.otra])
        self.assertEqual(list(OrdenCompra.objects.en_alcance_de(self.agronomo)), [orden])


# ---------------------------------------------------------------------------------------------------------------------------------
# CMP-04, paso 1: Recepcion, DetalleRecepcion, DetalleRecepcionMovimiento, InconvenienteRecepcion, ReclamoProveedor y AlertaCompras.
# Fuente: docs/modelo/compras.md (esas fichas), D-90 (puntos 3, 6 y 7), D-87 punto 5, D-52 (herencia de OrigenDocumento) y regla 10 de 8.20.
# ---------------------------------------------------------------------------------------------------------------------------------

from contabilidad.models import OrigenDocumento  # noqa: E402
from compras.models import (  # noqa: E402
    AlertaCompras,
    DetalleRecepcion,
    DetalleRecepcionMovimiento,
    InconvenienteRecepcion,
    Recepcion,
    ReclamoProveedor,
)
from inventario.models import MovimientoInsumo  # noqa: E402
from inventario.tests.fabricas import lote, movimiento  # noqa: E402
from maestros.tests.fabricas import crear_alerta  # noqa: E402


class RecepcionesRestriccionesTests(ConDatosDeInventario, TestCase):
    """Las restricciones de la base de las recepciones, sus líneas, sus inconvenientes, el reclamo sin emitir y el vínculo con las alertas."""

    def setUp(self):
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero()
        self.gerente = crear_gerente()
        self.existencia = existencia(insumo(), self.invernadero, minimo=10, precio="12.50", transito=12)
        self.proveedor = proveedor(n=1)
        self.pedido = armar_pedido(self.agronomo)
        self.detalle_de_pedido = detalle_de_pedido(self.pedido, self.existencia, cantidad="20")
        self.cotizacion = cotizacion_de(self.pedido, self.proveedor, [(self.detalle_de_pedido, "12", "120.00", 3)])
        self.orden = orden_de(self.pedido, [self.cotizacion], estado="aprobada", gerente=self.gerente)
        self.detalle_orden = self.orden.detalles.get()

    def rechazo(self, crear, restriccion):
        """Falla la prueba si la base no rechaza ``crear()`` con un ``IntegrityError`` que nombre ``restriccion``."""
        with self.assertRaises(IntegrityError) as contexto:
            with transaction.atomic():
                crear()
        self.assertIn(restriccion, str(contexto.exception))

    def recepcion(self, **campos):
        """Una ``Recepcion`` de la orden, del proveedor y del invernadero de la prueba, registrada por el Agrónomo; ``campos`` pisa lo que se pase."""
        datos = {
            "orden": self.orden,
            "fecha_recepcion": timezone.localdate(),
            "agronomo": self.agronomo,
            "proveedor": self.proveedor,
            "invernadero": self.invernadero,
        }
        datos.update(campos)
        return Recepcion.objects.create(**datos)

    def linea(self, recepcion=None, cantidad="5"):
        """Un ``DetalleRecepcion`` de la línea de la orden."""
        return DetalleRecepcion.objects.create(
            recepcion=recepcion or self.recepcion(), detalle_orden=self.detalle_orden, cantidad_recibida_detalle=Decimal(cantidad)
        )

    def reclamo(self, recepcion=None, **campos):
        """Un ``ReclamoProveedor`` abierto y sin emitir de la recepción."""
        recepcion = recepcion or self.recepcion()
        return ReclamoProveedor.objects.create(recepcion=recepcion, proveedor=self.proveedor, **campos)

    # --- Recepcion (D-52, D-90 punto 3) ---

    def test_d90_la_recepcion_es_un_documento_de_origen_de_tipo_recepcion(self):
        """D-90 punto 3 y D-52: ``Recepcion`` hereda de ``OrigenDocumento``; su ``tipo`` lo fija la clase (``recepcion``) y comparte el ``id`` con el padre."""
        recepcion = self.recepcion()
        self.assertEqual(recepcion.tipo, OrigenDocumento.Tipo.RECEPCION)
        self.assertEqual(OrigenDocumento.objects.get(pk=recepcion.pk).tipo, "recepcion")
        self.assertEqual(OrigenDocumento.objects.get(pk=recepcion.pk).recepcion, recepcion)
        self.assertEqual(recepcion.origendocumento_ptr_id, recepcion.pk)

    def test_d90_la_recepcion_se_muestra_como_rcp_y_el_tipo_se_llama_recepcion(self):
        """El identificador que ven las pantallas, los correos y la auditoría es «RCP-0001»; el tipo de origen se muestra como «Recepción»."""
        recepcion = self.recepcion()
        self.assertEqual(str(recepcion), f"RCP-{recepcion.pk:04d}")
        self.assertEqual(str(Recepcion()), "RCP-nueva")
        self.assertEqual(OrigenDocumento.Tipo.RECEPCION.label, "Recepción")
        self.assertEqual(OrigenDocumento.objects.get(pk=recepcion.pk).get_tipo_display(), "Recepción")

    def test_regla_r039_el_agronomo_de_la_recepcion_es_opcional(self):
        """Modelo, «Recepcion» (R039, 0..1): si la registró el Gerente, la recepción queda sin Agrónomo."""
        self.assertIsNone(self.recepcion(agronomo=None).agronomo)
        self.assertEqual(self.recepcion().agronomo.pk, self.agronomo.pk)

    def test_regla_la_recepcion_es_de_una_orden_un_proveedor_y_un_invernadero(self):
        """Regla 7 de 8.20: la recepción apunta a su orden, a su proveedor y a su invernadero; se llega desde cada uno."""
        recepcion = self.recepcion()
        self.assertEqual(list(self.orden.recepciones.all()), [recepcion])
        self.assertEqual(list(self.proveedor.recepciones.all()), [recepcion])
        self.assertEqual(list(self.invernadero.recepciones.all()), [recepcion])

    # --- DetalleRecepcion ---

    def test_regla_9_de_8_20_la_cantidad_recibida_no_es_negativa_y_puede_ser_cero(self):
        """Regla 9 de 8.20 y extensión 7c: ``cantidad_recibida_detalle`` ≥ 0 (0 solo si todo lo que llegó tuvo un inconveniente); un negativo lo rechaza la base."""
        recepcion = self.recepcion()
        self.rechazo(lambda: self.linea(recepcion, cantidad="-1"), "detalle_recepcion_cantidad_no_negativa")
        self.assertEqual(self.linea(recepcion, cantidad="0").cantidad_recibida_detalle, Decimal("0"))

    def test_regla_7_de_8_20_una_linea_de_la_orden_aparece_una_sola_vez_por_recepcion(self):
        """Modelo, «DetalleRecepcion»: único ``(recepcion, detalle_orden)``; en otra recepción la misma línea sí puede aparecer."""
        recepcion = self.recepcion()
        self.linea(recepcion)
        self.rechazo(lambda: self.linea(recepcion), "detalle_recepcion_unico_por_linea")
        self.linea(self.recepcion())
        self.assertEqual(self.detalle_orden.detalles_de_recepcion.count(), 2)

    def test_regla_el_detalle_de_recepcion_se_muestra_como_su_linea_de_la_orden(self):
        """El texto del detalle de recepción en la auditoría es el de su línea de la orden («Insumo · Invernadero»)."""
        self.assertEqual(str(self.linea()), str(self.detalle_orden))

    # --- DetalleRecepcionMovimiento (R032, D-90 punto 3) ---

    def test_r032_cada_movimiento_se_vincula_a_una_sola_linea_de_recepcion(self):
        """R032 y D-90 punto 3: el vínculo es ``OneToOne`` con el movimiento (``vinculo_de_recepcion``); una línea tiene varios vínculos (``vinculos_de_movimiento``)."""
        recepcion = self.recepcion()
        linea = self.linea(recepcion)
        lote_ = lote(self.existencia, 5)
        ingreso = movimiento(lote_, MovimientoInsumo.TipoMovimiento.INGRESO_POR_RECEPCION, 5, origen=recepcion)
        vinculo = DetalleRecepcionMovimiento.objects.create(detalle_recepcion=linea, movimiento=ingreso)
        self.assertEqual(ingreso.vinculo_de_recepcion, vinculo)
        self.assertEqual(list(linea.vinculos_de_movimiento.all()), [vinculo])
        otra = self.linea(self.recepcion())
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DetalleRecepcionMovimiento.objects.create(detalle_recepcion=otra, movimiento=ingreso)
        segundo = movimiento(lote(self.existencia, 3), MovimientoInsumo.TipoMovimiento.INGRESO_POR_RECEPCION, 3, origen=recepcion)
        DetalleRecepcionMovimiento.objects.create(detalle_recepcion=linea, movimiento=segundo)
        self.assertEqual(linea.vinculos_de_movimiento.count(), 2)

    def test_d90_un_ingreso_por_recepcion_acepta_la_recepcion_como_origen(self):
        """D-90 punto 3 (control previo): la restricción de origen de ``MovimientoInsumo`` acepta una ``Recepcion`` como origen de un ingreso, y la rechaza sin origen."""
        recepcion = self.recepcion()
        ingreso = movimiento(lote(self.existencia, 5), MovimientoInsumo.TipoMovimiento.INGRESO_POR_RECEPCION, 5, origen=recepcion)
        self.assertEqual(ingreso.origen_id, recepcion.pk)
        self.assertEqual(list(recepcion.movimientos_de_insumo.all()), [ingreso])
        self.rechazo(
            lambda: MovimientoInsumo.objects.create(
                lote_insumo=ingreso.lote_insumo, cantidad=1, tipo_movimiento="ingreso_por_recepcion", origen=None
            ),
            "movimiento_insumo_origen_segun_tipo",
        )

    # --- ReclamoProveedor (R008 en 0..1, regla 10 de 8.20) ---

    def test_regla_10_de_8_20_el_reclamo_nace_abierto_y_sin_emitir(self):
        """Regla 10 de 8.20 y R008 en 0..1: el reclamo de CMP-04 nace «abierto», sin Gerente y sin fecha de emisión; se muestra como «REC-0001»."""
        reclamo = self.reclamo()
        self.assertEqual(reclamo.estado_reclamo, "abierto")
        self.assertIsNone(reclamo.gerente)
        self.assertIsNone(reclamo.fecha_reclamo)
        self.assertFalse(reclamo.emitido)
        self.assertEqual(str(reclamo), f"REC-{reclamo.pk:04d}")
        self.assertEqual(str(ReclamoProveedor()), "REC-nuevo")

    def test_regla_10_de_8_20_emitido_si_y_solo_si_tiene_gerente_y_fecha(self):
        """Modelo, «ReclamoProveedor»: un reclamo está emitido si y solo si tiene Gerente, y solo entonces tiene fecha de emisión."""
        coherente = "reclamo_gerente_si_y_solo_si_fecha"
        self.rechazo(lambda: self.reclamo(gerente=self.gerente), coherente)
        self.rechazo(lambda: self.reclamo(fecha_reclamo=timezone.localdate()), coherente)
        emitido = self.reclamo(gerente=self.gerente, fecha_reclamo=timezone.localdate())
        self.assertTrue(emitido.emitido)

    def test_regla_10_de_8_20_solo_se_cierra_un_reclamo_emitido(self):
        """Modelo, «ReclamoProveedor»: ``cerrado`` exige Gerente; un reclamo sin emitir no puede estar cerrado. El estado es de lista cerrada."""
        self.rechazo(lambda: self.reclamo(estado_reclamo="cerrado"), "reclamo_cerrado_esta_emitido")
        self.rechazo(lambda: self.reclamo(estado_reclamo="archivado"), "reclamo_estado_valido")
        cerrado = self.reclamo(estado_reclamo="cerrado", gerente=self.gerente, fecha_reclamo=timezone.localdate())
        self.assertEqual(cerrado.estado_reclamo, "cerrado")

    def test_regla_10_de_8_20_una_recepcion_tiene_a_lo_sumo_un_reclamo(self):
        """Regla 10 de 8.20 (técnico): ``recepcion`` es ``OneToOne`` (``recepcion.reclamo``): un reclamo por recepción con inconvenientes."""
        recepcion = self.recepcion()
        reclamo = self.reclamo(recepcion)
        self.assertEqual(recepcion.reclamo, reclamo)
        self.rechazo(lambda: self.reclamo(recepcion), "recepcion_id")

    # --- InconvenienteRecepcion (D-90 punto 7, P4, MD-130) ---

    def inconveniente(self, linea, reclamo, tipo="mercaderia_danada", cantidad="2", descripcion=""):
        """Un ``InconvenienteRecepcion`` de la línea, agrupado en el reclamo."""
        return InconvenienteRecepcion.objects.create(
            detalle_recepcion=linea,
            reclamo=reclamo,
            tipo_inconveniente=tipo,
            cantidad_afectada=Decimal(cantidad),
            descripcion_inconveniente=descripcion,
        )

    def test_d90_los_tipos_de_inconveniente_son_los_de_p4(self):
        """D-90 punto 7 (P4, MD-130): cinco tipos; el retraso no se declara (no es un tipo)."""
        self.assertEqual(
            [valor for valor, _ in InconvenienteRecepcion.Tipo.choices],
            ["mercaderia_danada", "calidad_no_conforme", "producto_distinto", "vencido_o_por_vencer", "otro"],
        )
        linea = self.linea()
        reclamo = self.reclamo(linea.recepcion)
        self.rechazo(lambda: self.inconveniente(linea, reclamo, tipo="retraso"), "inconveniente_tipo_valido")

    def test_regla_10_de_8_20_una_linea_tiene_a_lo_sumo_un_inconveniente_de_cada_tipo(self):
        """Modelo, «InconvenienteRecepcion»: único ``(detalle_recepcion, tipo)``; otro tipo en la misma línea sí puede."""
        linea = self.linea()
        reclamo = self.reclamo(linea.recepcion)
        self.inconveniente(linea, reclamo, "mercaderia_danada")
        self.rechazo(lambda: self.inconveniente(linea, reclamo, "mercaderia_danada", cantidad="1"), "inconveniente_unico_por_tipo_y_linea")
        self.inconveniente(linea, reclamo, "calidad_no_conforme")
        self.assertEqual(reclamo.inconvenientes.count(), 2)

    def test_regla_extension_7e_la_cantidad_afectada_es_mayor_que_cero(self):
        """Extensión 7e y modelo, «InconvenienteRecepcion»: la cantidad afectada es mayor que cero."""
        linea = self.linea()
        reclamo = self.reclamo(linea.recepcion)
        self.rechazo(lambda: self.inconveniente(linea, reclamo, cantidad="0"), "inconveniente_cantidad_positiva")

    def test_regla_extension_7e_el_tipo_otro_exige_descripcion(self):
        """Extensión 7e y modelo, «InconvenienteRecepcion»: la descripción es obligatoria en «otro» y opcional en los demás tipos."""
        linea = self.linea()
        reclamo = self.reclamo(linea.recepcion)
        self.rechazo(lambda: self.inconveniente(linea, reclamo, tipo="otro"), "inconveniente_otro_con_descripcion")
        self.inconveniente(linea, reclamo, tipo="otro", descripcion="Llegó otro producto")
        self.inconveniente(linea, reclamo, tipo="producto_distinto", descripcion="")

    def test_regla_el_inconveniente_se_muestra_con_el_nombre_de_su_tipo(self):
        """El texto del inconveniente en la auditoría es el nombre de su tipo («Mercadería dañada»)."""
        linea = self.linea()
        reclamo = self.reclamo(linea.recepcion)
        self.assertEqual(str(self.inconveniente(linea, reclamo)), "Mercadería dañada")

    # --- AlertaCompras (D-87 punto 5, patrón de AlertaComercial, D-63) ---

    def test_d87_la_alerta_de_compras_vincula_una_alerta_con_su_reclamo(self):
        """D-87 punto 5 y D-63: ``AlertaCompras`` une una alerta de ``maestros`` con el reclamo sin emitir (``alerta.vinculo_de_compras``, ``reclamo.alertas``)."""
        reclamo = self.reclamo()
        alerta = crear_alerta(self.invernadero, "compras_recepcion_con_inconvenientes")
        vinculo = AlertaCompras.objects.create(alerta=alerta, reclamo=reclamo)
        self.assertEqual(alerta.vinculo_de_compras, vinculo)
        self.assertEqual(list(reclamo.alertas.all()), [vinculo])

    def test_d87_una_alerta_tiene_un_solo_vinculo_de_compras(self):
        """D-87 punto 5: ``alerta`` es ``OneToOne``; la misma alerta no se vincula a dos reclamos."""
        alerta = crear_alerta(self.invernadero, "compras_recepcion_con_inconvenientes")
        AlertaCompras.objects.create(alerta=alerta, reclamo=self.reclamo())
        otro = self.reclamo(self.recepcion())
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AlertaCompras.objects.create(alerta=alerta, reclamo=otro)

    # --- Lo que no se borra ---

    def test_regla_nada_de_una_recepcion_se_borra(self):
        """Las claves que apuntan a una recepción son ``PROTECT`` (D-52, «nadie borra un documento de origen»): una recepción con líneas no se puede borrar."""
        from django.db.models import ProtectedError

        recepcion = self.recepcion()
        self.linea(recepcion)
        with self.assertRaises(ProtectedError):
            recepcion.delete()
