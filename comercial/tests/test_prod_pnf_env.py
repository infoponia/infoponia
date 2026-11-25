# Pruebas de PROD-PNF-ENV · Planificar Envasado (COM-05a2; `comercial/servicios/envasado.py`): `ProdPnfEnvServicioTests`. Una por regla, por postcondición (a a f) y por extensión (2a, 3a,
# 3b, 4a, 4b, 6a, 6b, 6c, 8a, 8b, 8c, 10a, 10b, 10c). Las de concurrencia están en `test_envasado_concurrencia.py` y las de las vistas, en `test_envasado_vistas.py`.
# Fuente: docs/casos_de_uso/produccion/envasado.md («Cómo se aplica en la ronda «Comercial 1»», «Reglas en el código», «Pruebas»), D-66 puntos 8 y 11 y D-36.

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.http import Http404
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from comercial.models import Entrega
from comercial.servicios import envasado
from comercial.servicios.envasado import CargaDeEnvasado
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    entrega,
    envase,
    escenario_comercial,
    iniciar_ruta_de,
    marcar_concretada,
    reserva_lista,
    segundo_invernadero,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
)
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.models import LoteInsumo
from inventario.servicios import stock
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, lote, tipo_de_insumo
from maestros.models import Invernadero
from maestros.tests.fabricas import crear_agronomo
from produccion.models import OrdenTrabajo, ReservaInsumo
from produccion.tests.fabricas import lote_maduro, reservar

HOY = timezone.localdate()


def codigos(error):
    """Los códigos de un `ValidationError` con diccionario de campos."""
    return [e.code for lista in error.error_dict.values() for e in lista]


class Base(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 5000)
        cls.agronomo = cls.e.agronomo

    def entrega_nueva(self, cantidad=100, dias=3, **opciones):
        venta = compra_venta(self.e, dias=dias)
        det = detalle(venta, self.e.variedad, cantidad)
        reserva = reserva_lista(det, self.lote, cantidad)
        return entrega(venta, [reserva], **opciones)

    def carga(self, entrega_, *filas, huella=None, reemplazados=()):
        """`CargaDeEnvasado` con `(InsumoInvernadero, cantidad)` y la huella actual de la entrega."""
        return CargaDeEnvasado(
            entrega_.pk,
            tuple(sorted((i.pk, str(c)) for i, c in filas)),
            envasado.huella_de(entrega_.pk) if huella is None else huella,
            tuple(reemplazados),
        )

    def planificar(self, entrega_, *filas, actor=None, **opciones):
        return envasado.planificar_envasado(actor or self.agronomo, self.carga(entrega_, *filas, **opciones))

    def activas(self, entrega_):
        return {r.insumo_invernadero_id: r for r in ReservaInsumo.objects.filter(orden_id=entrega_.pk, estado="activa")}

    def rechazo(self, llamada):
        with self.assertRaises(ValidationError) as ctx:
            llamada()
        return ctx.exception

    def avisos(self, cuenta):
        return list(Notificacion.objects.filter(destinatario=cuenta))

    def tearDown(self):
        verificar_invariantes_de_entregas()


class ProdPnfEnvServicioTests(Base):
    # ---- quién (regla «Quién lo ejecuta») ----

    def test_regla_quien_lo_ejecuta_el_agronomo_a_cargo_planifica(self):
        """Regla «Quién lo ejecuta»: el Agrónomo a cargo del invernadero de origen."""
        e, b = self.entrega_nueva(), envase(self.e.invernadero)
        self.planificar(e, (b, 10))
        self.assertEqual(self.activas(e)[b.pk].cantidad_reservada, 10)

    def test_regla_quien_lo_ejecuta_rechaza_a_otro_agronomo_al_gerente_al_capataz_y_a_una_cuenta_inactiva(self):
        """Regla «Quién lo ejecuta» y requisito «Solo el Agrónomo a cargo»: cualquier otro rol o cuenta, `PermissionDenied`, en los cuatro servicios."""
        e, b = self.entrega_nueva(), envase(self.e.invernadero)
        otro = crear_agronomo(email="otro.agronomo@infoponia.com")
        inactiva = crear_agronomo(email="inactiva@infoponia.com", activo=False)
        self.assertEqual(envasado.entregas_para_envasar(otro), [])  # un Agrónomo sin invernaderos a cargo no ve entregas (no es un error: la lista está vacía)
        for actor in (otro, crear_gerente(), self.e.capataz, self.e.vendedor, inactiva):
            for llamada in (
                lambda: envasado.entregas_para_envasar(actor) if actor is not otro else envasado.datos_de_envasado(actor, e.pk),
                lambda: envasado.datos_de_envasado(actor, e.pk),
                lambda: envasado.resumen_de_envasado(actor, self.carga(e, (b, 5))),
                lambda: envasado.planificar_envasado(actor, self.carga(e, (b, 5))),
            ):
                with self.assertRaises(PermissionDenied):
                    llamada()
        self.assertFalse(ReservaInsumo.objects.filter(orden_id=e.pk).exists())

    def test_regla_quien_lo_ejecuta_un_agronomo_de_otro_invernadero_no_ve_la_entrega(self):
        """Regla «Quién lo ejecuta»: el invernadero de origen tiene que estar a cargo de quien actúa."""
        e = self.entrega_nueva()
        from maestros.tests.fabricas import crear_invernadero

        ajeno = crear_agronomo(email="agronomo.ajeno@infoponia.com")
        crear_invernadero("Invernadero Ajeno", agronomo=ajeno)
        with self.assertRaises(PermissionDenied):
            envasado.datos_de_envasado(ajeno, e.pk)
        self.assertEqual(envasado.entregas_para_envasar(ajeno), [])

    def test_regla_una_orden_que_no_es_entrega_es_404(self):
        """Un id que no es una entrega (o no existe) da `Http404` (D-28)."""
        from produccion.tests.fabricas import orden_suelta

        suelta = orden_suelta(self.e.invernadero, OrdenTrabajo.Tipo.MANTENIMIENTO)
        for entrega_id in (suelta.pk, 9999999):
            with self.assertRaises(Http404):
                envasado.datos_de_envasado(self.agronomo, entrega_id)

    # ---- envase ----

    def test_regla_envase_solo_los_de_la_categoria_envases_activos_y_habilitados(self):
        """Regla «Envase»: insumo de la categoría del sistema «Envases» (por código), con el insumo y el insumo del invernadero activos. Uno de otra categoría, uno inactivo,
        uno con el insumo inactivo y uno no habilitado en el invernadero de origen no se ofrecen."""
        e = self.entrega_nueva()
        bueno = envase(self.e.invernadero, nombre="Bandeja buena")
        envase(self.e.invernadero, nombre="Cajón inactivo", activo=False)
        envase(self.e.invernadero, nombre="Cajón de insumo inactivo", insumo_activo=False)
        existencia(insumo("Detergente de limpieza", tipo=tipo_de_insumo("Limpieza2")), self.e.invernadero)
        sur = segundo_invernadero(self.e, "Invernadero Sur")
        envase(sur.invernadero, nombre="Bandeja del sur")
        datos = envasado.datos_de_envasado(self.agronomo, e.pk)
        self.assertEqual([o.insumo_invernadero_id for o in datos.ofrecidos], [bueno.pk])

    def test_regla_envase_se_identifica_por_la_categoria_y_no_por_el_nombre(self):
        """Regla «Envase»: un insumo que se llama «Envase…» pero es de otra categoría no se ofrece."""
        e = self.entrega_nueva()
        existencia(insumo("Envase falso", tipo=tipo_de_insumo("Limpieza3")), self.e.invernadero)
        self.assertEqual(envasado.datos_de_envasado(self.agronomo, e.pk).ofrecidos, [])

    def test_ext_4a_sin_envases_habilitados_lo_informa_y_ofrece_habilitarlos(self):
        """Extensión 4a: «Este invernadero no tiene envases habilitados.» y el acceso a la pantalla de insumos del invernadero (CMP-HAB-IIN)."""
        datos = envasado.datos_de_envasado(self.agronomo, self.entrega_nueva().pk)
        self.assertEqual(datos.ofrecidos, [])
        self.assertIn("Este invernadero no tiene envases habilitados.", datos.avisos)
        self.assertTrue(datos.url_habilitar.endswith("/existencias/"))

    def test_regla_envase_un_envase_reservado_que_dejo_de_ofrecerse_se_puede_bajar_pero_no_subir(self):
        """Extensión 3a y regla «Envase»: un envase ya reservado cuyo insumo del invernadero se dio de baja se puede mantener, bajar o quitar, pero no subir."""
        e, b = self.entrega_nueva(), envase(self.e.invernadero)
        self.planificar(e, (b, 10))
        type(b).objects.filter(pk=b.pk).update(estado_insumo_invernadero="inactivo")
        error = self.rechazo(lambda: self.planificar(e, (b, 12)))
        self.assertEqual(codigos(error), ["envase_no_ofrecido"])
        self.planificar(e, (b, 8))
        self.assertEqual(self.activas(e)[b.pk].cantidad_reservada, 8)

    def test_regla_envase_de_otro_invernadero_no_se_puede_reservar(self):
        """Un envase de otro invernadero (un id armado a mano) se rechaza: `envase_no_ofrecido`."""
        e = self.entrega_nueva()
        sur = segundo_invernadero(self.e, "Invernadero Sur")
        ajeno = envase(sur.invernadero, nombre="Bandeja del sur")
        error = self.rechazo(lambda: self.planificar(e, (ajeno, 3)))
        self.assertEqual(codigos(error), ["envase_no_ofrecido"])
        self.assertFalse(ReservaInsumo.objects.filter(orden_id=e.pk).exists())

    # ---- disponible y fecha de referencia ----

    def test_regla_disponible_no_cuenta_los_lotes_que_estaran_vencidos_en_la_fecha_de_referencia(self):
        """Regla «Disponible para planificar»: stock libre menos los lotes vencidos en la fecha de referencia. Fecha programada en 3 días: un lote que vence mañana no cuenta."""
        e = self.entrega_nueva(dias=3)
        b = envase(self.e.invernadero, 10, vence=HOY + timedelta(days=365))
        lote(b, 5, vence=HOY + timedelta(days=1))
        datos = envasado.datos_de_envasado(self.agronomo, e.pk)
        self.assertEqual(datos.ofrecidos[0].disponible, 10)

    def test_regla_disponible_cuenta_el_lote_que_todavia_no_vence_en_la_fecha_de_referencia(self):
        """Regla «Disponible para planificar»: con la entrega para hoy, el lote que vence mañana todavía cuenta."""
        e = self.entrega_nueva(fecha=HOY)
        b = envase(self.e.invernadero, 10, vence=HOY + timedelta(days=365))
        lote(b, 5, vence=HOY + timedelta(days=1))
        self.assertEqual(envasado.datos_de_envasado(self.agronomo, e.pk).ofrecidos[0].disponible, 15)

    def test_ext_4b_la_fecha_de_referencia_de_una_entrega_atrasada_es_hoy(self):
        """Regla «Fecha de referencia» y extensión 4b: la fecha programada o, si ya pasó, la fecha actual; la entrega se indica atrasada."""
        e = self.entrega_nueva(fecha=HOY - timedelta(days=2))
        b = envase(self.e.invernadero, 10, vence=HOY + timedelta(days=365))
        lote(b, 5, vence=HOY - timedelta(days=1))  # vencido ayer: no cuenta con la fecha de referencia en hoy
        datos = envasado.datos_de_envasado(self.agronomo, e.pk)
        self.assertEqual(datos.fecha_de_referencia, HOY)
        self.assertEqual(datos.ofrecidos[0].disponible, 10)
        self.assertTrue(datos.fila.atrasada)
        self.assertIn("La entrega está atrasada: lo disponible se calcula a la fecha de hoy.", datos.avisos)

    def test_regla_disponible_al_modificar_suma_la_propia_reserva(self):
        """Regla «Disponible al modificar» y extensión 3a: para un envase que la entrega ya reservó, lo disponible incluye su propia cantidad."""
        e, b = self.entrega_nueva(), envase(self.e.invernadero, 30)
        self.planificar(e, (b, 25))
        self.assertEqual(stock.disponible_para_planificar([b.pk], HOY)[b.pk], 5)
        datos = envasado.datos_de_envasado(self.agronomo, e.pk)
        self.assertEqual(datos.ofrecidos[0].disponible, 30)
        self.planificar(e, (b, 30))  # sube hasta lo que hay: lo propio cuenta
        self.assertEqual(self.activas(e)[b.pk].cantidad_reservada, 30)

    # ---- cantidad válida ----

    def test_ext_6a_cantidad_cero_negativa_o_vacia_se_rechaza_con_el_texto_de_la_unidad(self):
        """Extensión 6a: menor o igual que cero, vacía o con más decimales que la unidad: error en la fila con los decimales que admite."""
        e = self.entrega_nueva()
        b = envase(self.e.invernadero, 30)
        g = envase(self.e.invernadero, 30, "g", nombre="Frasco chico")
        for filas, esperado in (
            ([(b, "0")], "Ingresá una cantidad mayor que 0, un número entero (unidad)."),
            ([(b, "-2")], "Ingresá una cantidad mayor que 0, un número entero (unidad)."),
            ([(b, "")], "Ingresá una cantidad mayor que 0, un número entero (unidad)."),
            ([(b, "2,5")], "Ingresá una cantidad mayor que 0, un número entero (unidad)."),
            ([(g, "1,234")], "Ingresá una cantidad mayor que 0, con hasta 2 decimales (g)."),
        ):
            error = self.rechazo(lambda: self.planificar(e, *filas))
            self.assertEqual(codigos(error), ["cantidad_invalida"])
            self.assertIn(esperado, [m for lista in error.message_dict.values() for m in lista])
        self.assertFalse(ReservaInsumo.objects.filter(orden_id=e.pk).exists())

    def test_regla_cantidad_valida_admite_los_decimales_de_cada_unidad_con_coma_o_punto(self):
        """Regla «Cantidad válida» (regla 2 de 8.23): unidad 0; g, mL, m y m² 2; kg, L y m³ 3. Coma o punto."""
        e = self.entrega_nueva()
        kg = envase(self.e.invernadero, 30, "kg", nombre="Bolsa kg")
        g = envase(self.e.invernadero, 30, "g", nombre="Sobre g")
        self.planificar(e, (kg, "1,125"), (g, "2.5"))
        activas = self.activas(e)
        self.assertEqual((activas[kg.pk].cantidad_reservada, activas[g.pk].cantidad_reservada), (Decimal("1.125"), Decimal("2.5")))

    # ---- 6b y 10b ----

    def test_ext_6b_supera_lo_disponible_informa_lo_que_queda_y_la_ayuda(self):
        """Extensión 6b: «Supera lo disponible: quedan 30 unidades (sin contar los lotes que estarán vencidos el dd/mm).» y la ayuda para pedir o ajustar stock."""
        e, b = self.entrega_nueva(), envase(self.e.invernadero, 30)
        datos = envasado.datos_de_envasado(self.agronomo, e.pk, self.carga(e, (b, 40)))
        fila = datos.filas[0]
        self.assertEqual(fila.codigo_de_error, "supera_disponible")
        self.assertEqual(fila.error, f"Supera lo disponible: quedan 30 unidades (sin contar los lotes que estarán vencidos el {e.fecha_programada_orden:%d/%m}).")
        self.assertEqual(fila.ayuda, "Si necesitás más, pedilo con un pedido de compra o, si el depósito tiene más de lo registrado, ajustá el stock.")
        error = self.rechazo(lambda: envasado.resumen_de_envasado(self.agronomo, self.carga(e, (b, 40))))
        self.assertEqual(codigos(error), ["supera_disponible"])

    def test_ext_10b_otra_operacion_redujo_lo_disponible_no_registra_nada_y_conserva_la_carga(self):
        """Extensión 10b: entre la carga y la confirmación otra operación redujo lo disponible: `disponible_cambio`, nada se registra y la carga se puede volver a mostrar."""
        e, b = self.entrega_nueva(), envase(self.e.invernadero, 30)
        carga = self.carga(e, (b, 25))
        otra = self.entrega_nueva()
        self.planificar(otra, (b, 20))  # otro envasado deja 10 libres
        auditoria = RegistroAuditoria.objects.count()
        error = self.rechazo(lambda: envasado.planificar_envasado(self.agronomo, carga))
        self.assertEqual(codigos(error), ["disponible_cambio"])
        self.assertIn("Bandeja PET 1 kg", str(error))
        self.assertFalse(ReservaInsumo.objects.filter(orden_id=e.pk).exists())
        self.assertEqual(RegistroAuditoria.objects.count(), auditoria)
        datos = envasado.datos_de_envasado(self.agronomo, e.pk, carga)
        self.assertEqual([f.cantidad for f in datos.filas], ["25"])  # la carga se conserva
        self.assertEqual(datos.filas[0].disponible, 10)

    # ---- una reserva por envase (6c) ----

    def test_ext_6c_indicar_otra_vez_un_envase_reemplaza_la_cantidad_con_aviso(self):
        """Extensión 6c: un envase que ya está en la carga reemplaza su cantidad (una reserva por envase) y avisa «Ya estaba en la lista: se reemplazó la cantidad.»."""
        from django.http import QueryDict

        e, b = self.entrega_nueva(), envase(self.e.invernadero, 30)
        post = QueryDict(mutable=True)
        post.update({f"cantidad_{b.pk}": "5", "agregar": str(b.pk), f"nueva_{b.pk}": "9", "huella": envasado.huella_de(e.pk)})
        carga = CargaDeEnvasado.desde_post(e.pk, post)
        self.assertEqual(carga.filas, ((b.pk, "9"),))
        self.assertEqual(carga.reemplazados, (b.pk,))
        datos = envasado.datos_de_envasado(self.agronomo, e.pk, carga)
        self.assertEqual(datos.filas[0].aviso, "Ya estaba en la lista: se reemplazó la cantidad.")
        envasado.planificar_envasado(self.agronomo, carga)
        self.assertEqual(ReservaInsumo.objects.filter(orden_id=e.pk).count(), 1)

    def test_regla_una_reserva_por_envase_quitar_y_volver_a_agregar_deja_una_cancelada_y_una_activa(self):
        """D-66 punto 8 y regla «Una reserva por envase»: quitar un envase cancela su reserva y, al volver a agregarlo, nace otra (dos filas: una cancelada y una activa)."""
        e, b, c = self.entrega_nueva(), envase(self.e.invernadero), envase(self.e.invernadero, nombre="Cajón")
        self.planificar(e, (b, 10), (c, 4))
        self.planificar(e, (c, 4))  # quita la bandeja
        self.planificar(e, (b, 7), (c, 4))  # vuelve a agregarla
        estados = sorted(ReservaInsumo.objects.filter(orden_id=e.pk, insumo_invernadero=b).values_list("estado", "cantidad_reservada"))
        self.assertEqual(estados, [("activa", Decimal("7.000")), ("cancelada", Decimal("10.000"))])

    # ---- postcondiciones ----

    def test_post_a_crea_reservas_activas_con_cantidad_y_fecha_de_hoy_sin_utilizada_ni_devuelta(self):
        """Postcondición a: una reserva «activa» por envase nuevo, con la cantidad reservada, la fecha actual y utilizada y devuelta vacías."""
        e, b, c = self.entrega_nueva(), envase(self.e.invernadero), envase(self.e.invernadero, nombre="Cajón")
        self.planificar(e, (b, 10), (c, "4"))
        for reserva in ReservaInsumo.objects.filter(orden_id=e.pk):
            self.assertEqual((reserva.estado, reserva.fecha_reserva), ("activa", HOY))
            self.assertEqual((reserva.cantidad_utilizada, reserva.cantidad_devuelta), (None, None))
        self.assertEqual(self.activas(e)[b.pk].cantidad_reservada, 10)

    def test_post_b_cambia_la_cantidad_conserva_la_fecha_y_cancela_el_quitado(self):
        """Postcondición b: la reserva que cambió de cantidad conserva su fecha de reserva y la del envase quitado pasa a «cancelada»."""
        e, b, c = self.entrega_nueva(), envase(self.e.invernadero), envase(self.e.invernadero, nombre="Cajón")
        self.planificar(e, (b, 10), (c, 4))
        ReservaInsumo.objects.filter(orden_id=e.pk).update(fecha_reserva=HOY - timedelta(days=4))
        self.planificar(e, (b, 15))
        self.assertEqual(self.activas(e)[b.pk].cantidad_reservada, 15)
        self.assertEqual(self.activas(e)[b.pk].fecha_reserva, HOY - timedelta(days=4))
        cancelada = ReservaInsumo.objects.get(orden_id=e.pk, insumo_invernadero=c)
        self.assertEqual((cancelada.estado, cancelada.cantidad_utilizada, cancelada.cantidad_devuelta), ("cancelada", None, None))

    def test_post_c_el_stock_libre_baja_y_sube_pero_el_stock_actual_y_los_lotes_no_cambian(self):
        """Postcondición c y garantía mínima 2: el stock libre baja en lo reservado y sube en lo liberado; el stock actual y los lotes no se tocan."""
        e, b = self.entrega_nueva(), envase(self.e.invernadero, 30)
        lotes = list(LoteInsumo.objects.filter(insumo_invernadero=b).values_list("pk", "cantidad_disponible"))
        actual = stock.existencias([b.pk], HOY)[b.pk]
        self.planificar(e, (b, 20))
        despues = stock.existencias([b.pk], HOY)[b.pk]
        self.assertEqual((despues.libre, despues.actual), (actual.libre - 20, actual.actual))
        self.planificar(e, (b, 5))
        self.assertEqual(stock.existencias([b.pk], HOY)[b.pk].libre, actual.libre - 5)
        self.planificar(e)
        self.assertEqual(stock.existencias([b.pk], HOY)[b.pk].libre, actual.libre)
        self.assertEqual(list(LoteInsumo.objects.filter(insumo_invernadero=b).values_list("pk", "cantidad_disponible")), lotes)

    def test_post_d_la_entrega_no_cambia_ni_se_notifica_a_nadie(self):
        """Postcondición d: la entrega conserva estado, fecha, transportista, líneas y planificador (nulo); no se notifica a nadie."""
        t = transportista_con_vehiculo(self.e.invernadero)
        e, b = self.entrega_nueva(transportista=t), envase(self.e.invernadero)
        antes = (Entrega.objects.filter(pk=e.pk).values().get(), list(e.lineas.values_list("pk", flat=True)))
        avisos = Notificacion.objects.count()
        self.planificar(e, (b, 10))
        self.assertEqual((Entrega.objects.filter(pk=e.pk).values().get(), list(e.lineas.values_list("pk", flat=True))), antes)
        self.assertEqual(Notificacion.objects.count(), avisos)

    def test_post_e_audita_un_registro_con_las_reservas_creadas(self):
        """Postcondición e: un registro `planificacion_envasado` con usuario y rol, la entrega como principal y cada reserva creada afectada, con el envase, la cantidad y la fecha."""
        e, b = self.entrega_nueva(), envase(self.e.invernadero)
        self.planificar(e, (b, "10"))
        registro = RegistroAuditoria.objects.get(accion="planificacion_envasado")
        self.assertEqual(registro.usuario_id, self.agronomo.pk)
        self.assertEqual(len(registro.afectados), 2)  # la entrega y la reserva creada
        self.assertEqual({a["id"] for a in registro.afectados} >= {e.pk}, True)
        self.assertEqual(registro.detalle["datos"]["entrega"]["texto"], e.codigo)
        self.assertEqual(registro.detalle["datos"]["reservas_creadas"], [f"Bandeja PET 1 kg: 10 ({HOY:%d/%m/%Y})"])

    def test_post_f_audita_los_cambios_de_cantidad_y_de_estado(self):
        """Postcondición f: el mismo registro lleva, por cada reserva modificada, el cambio de cantidad reservada (antes → después) o de estado."""
        e, b, c = self.entrega_nueva(), envase(self.e.invernadero), envase(self.e.invernadero, nombre="Cajón")
        self.planificar(e, (b, 10), (c, 4))
        self.planificar(e, (b, 15))
        registro = RegistroAuditoria.objects.filter(accion="planificacion_envasado").latest("pk")
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["cantidad_reservada"], {"antes": ["Bandeja PET 1 kg: 10"], "despues": ["Bandeja PET 1 kg: 15"]})
        self.assertEqual(cambios["estado_reserva_insumo"], {"antes": ["Cajón: activa"], "despues": ["Cajón: cancelada"]})
        self.assertNotIn("reservas_creadas", registro.detalle["datos"])

    def test_regla_reservar_no_descuenta_stock_ni_crea_movimientos_ni_consumos(self):
        """Regla «Reservar no descuenta stock» y garantía mínima 2: no se registran consumos, movimientos de insumo ni asientos."""
        from inventario.models import MovimientoInsumo
        from produccion.models import Consumo

        e, b = self.entrega_nueva(), envase(self.e.invernadero)
        movimientos, consumos = MovimientoInsumo.objects.count(), Consumo.objects.count()
        self.planificar(e, (b, 10))
        self.assertEqual((MovimientoInsumo.objects.count(), Consumo.objects.count()), (movimientos, consumos))

    # ---- flujo, resumen, 8a, 8b, 8c ----

    def test_flujo_principal_lista_detalle_resumen_y_registro(self):
        """Pasos 2 a 11: la lista muestra la entrega «Sin planificar»; el detalle ofrece los envases; el resumen muestra lo que se reserva; confirmar registra."""
        e, b = self.entrega_nueva(), envase(self.e.invernadero, 30)
        (fila,) = envasado.entregas_para_envasar(self.agronomo)
        self.assertEqual((fila.codigo, fila.tiene_envasado, fila.en_curso, fila.atrasada), (e.codigo, False, False, False))
        datos = envasado.datos_de_envasado(self.agronomo, e.pk)
        self.assertEqual(datos.filas, [])
        self.assertEqual(datos.ofrecidos[0].disponible, 30)
        carga = self.carga(e, (b, 20))
        resumen = envasado.resumen_de_envasado(self.agronomo, carga)
        self.assertEqual([(f.nombre, f.anterior, f.nueva, f.queda, f.situacion) for f in resumen.filas], [("Bandeja PET 1 kg", None, 20, 10, "nuevo")])
        envasado.planificar_envasado(self.agronomo, carga)
        self.assertTrue(envasado.entregas_para_envasar(self.agronomo)[0].tiene_envasado)

    def test_ext_3a_la_modificacion_muestra_lo_reservado_y_el_resumen_anterior_y_nueva(self):
        """Extensión 3a: la entrega con envasado se abre con sus envases reservados y el resumen muestra la cantidad anterior y la nueva y los quitados."""
        e, b, c = self.entrega_nueva(), envase(self.e.invernadero, 30), envase(self.e.invernadero, 30, nombre="Cajón")
        self.planificar(e, (b, 20), (c, 4))
        datos = envasado.datos_de_envasado(self.agronomo, e.pk)
        self.assertEqual({(f.nombre, f.cantidad) for f in datos.filas}, {("Bandeja PET 1 kg", "20"), ("Cajón", "4")})
        resumen = envasado.resumen_de_envasado(self.agronomo, self.carga(e, (b, 25)))
        self.assertEqual([(f.anterior, f.nueva, f.situacion) for f in resumen.filas], [(20, 25, "cambia")])
        self.assertEqual([(n, c) for n, _, c in resumen.quitados], [("Cajón", 4)])
        self.assertFalse(resumen.aviso_sin_envasado)

    def test_ext_8a_sin_ningun_envase_y_sin_envasado_previo_pide_al_menos_uno(self):
        """Extensión 8a: «Indicá al menos un envase.»."""
        e = self.entrega_nueva()
        envase(self.e.invernadero)
        for llamada in (lambda: envasado.resumen_de_envasado(self.agronomo, self.carga(e)), lambda: self.planificar(e)):
            error = self.rechazo(llamada)
            self.assertEqual(codigos(error), ["sin_envases"])
            self.assertIn("Indicá al menos un envase.", error.messages)

    def test_ext_8b_quitar_todos_los_envases_reservados_avisa_y_se_puede_confirmar(self):
        """Extensión 8b: el resumen advierte que la entrega queda sin envasado planificado; al confirmar, sus reservas pasan a «cancelada»."""
        e, b = self.entrega_nueva(), envase(self.e.invernadero)
        self.planificar(e, (b, 10))
        resumen = envasado.resumen_de_envasado(self.agronomo, self.carga(e))
        self.assertTrue(resumen.aviso_sin_envasado)
        self.assertEqual([n for n, _, _ in resumen.quitados], ["Bandeja PET 1 kg"])
        self.planificar(e)
        self.assertEqual(self.activas(e), {})
        self.assertEqual(ReservaInsumo.objects.get(orden_id=e.pk).estado, "cancelada")

    def test_ext_8c_sin_cambios_informa_que_no_hay_nada_para_registrar(self):
        """Extensión 8c: «No hay cambios para registrar.»; no se escribe nada, ni siquiera la auditoría."""
        e, b = self.entrega_nueva(), envase(self.e.invernadero)
        self.planificar(e, (b, 10))
        auditoria = RegistroAuditoria.objects.count()
        for llamada in (lambda: envasado.resumen_de_envasado(self.agronomo, self.carga(e, (b, "10"))), lambda: self.planificar(e, (b, 10))):
            error = self.rechazo(llamada)
            self.assertEqual(codigos(error), ["sin_cambios"])
            self.assertIn("No hay cambios para registrar.", error.messages)
        self.assertEqual(RegistroAuditoria.objects.count(), auditoria)

    # ---- 2a, 3b, 10a, 10c ----

    def test_ext_2a_sin_entregas_a_realizar_la_lista_esta_vacia(self):
        """Extensión 2a: sin entregas «a realizar» en los invernaderos del Agrónomo, la lista está vacía (la pantalla dice «No hay entregas para envasar.»)."""
        self.assertEqual(envasado.entregas_para_envasar(self.agronomo), [])
        self.entrega_nueva(estado="concretada")
        self.entrega_nueva(estado="cancelada")
        self.assertEqual(envasado.entregas_para_envasar(self.agronomo), [])

    def test_regla_la_lista_va_por_fecha_programada_y_filtra_por_invernadero_y_fecha(self):
        """Paso 2: por fecha programada y después id; variación 2: filtros por invernadero de origen y por fecha programada exacta."""
        tarde, temprano = self.entrega_nueva(dias=6), self.entrega_nueva(dias=3)
        mismo_dia = self.entrega_nueva(dias=3)
        self.assertEqual([f.entrega.pk for f in envasado.entregas_para_envasar(self.agronomo)], [temprano.pk, mismo_dia.pk, tarde.pk])
        self.assertEqual([f.entrega.pk for f in envasado.entregas_para_envasar(self.agronomo, fecha=tarde.fecha_programada_orden)], [tarde.pk])
        self.assertEqual(envasado.entregas_para_envasar(self.agronomo, invernadero_id=self.e.invernadero.pk + 999), [])

    def test_regla_un_invernadero_inactivo_no_aparece_ni_se_envasa(self):
        """Regla «Invernadero inactivo» (garantía de `bloquear_invernadero_activo`): sus entregas no están en la lista y planificar da `invernadero_inactivo`."""
        e, b = self.entrega_nueva(), envase(self.e.invernadero)
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero=Invernadero.Estado.INACTIVO)
        self.assertEqual(envasado.entregas_para_envasar(self.agronomo), [])
        self.assertEqual(codigos(self.rechazo(lambda: envasado.datos_de_envasado(self.agronomo, e.pk))), ["invernadero_inactivo"])

    def test_regla_invernadero_sin_agronomo_nadie_planifica_y_el_que_se_asigne_ve_las_entregas(self):
        """Regla «Invernadero sin Agrónomo»: sin Agrónomo no hay quien planifique; el que se asigne ve y planifica las entregas que sigan «a realizar»."""
        e, b = self.entrega_nueva(), envase(self.e.invernadero)
        nuevo = crear_agronomo(email="nuevo.agronomo@infoponia.com")
        with self.assertRaises(PermissionDenied):
            envasado.datos_de_envasado(nuevo, e.pk)
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(agronomo=nuevo)
        self.assertEqual([f.entrega.pk for f in envasado.entregas_para_envasar(nuevo)], [e.pk])
        envasado.planificar_envasado(nuevo, self.carga(e, (b, 5)))
        self.assertEqual(RegistroAuditoria.objects.get(accion="planificacion_envasado").usuario_id, nuevo.pk)

    def test_ext_3b_una_entrega_en_curso_no_se_modifica(self):
        """Extensión 3b y regla «Entrega en curso»: con envío, fecha de hoy o anterior y el vehículo del transportista en ruta: se informa y no se puede cambiar."""
        t = transportista_con_vehiculo(self.e.invernadero)
        e, b = self.entrega_nueva(transportista=t, fecha=HOY), envase(self.e.invernadero)
        iniciar_ruta_de(t)  # COM-06a: la ruta se inicia de verdad (antes, la fábrica la dejaba en ruta)
        (fila,) = envasado.entregas_para_envasar(self.agronomo)
        self.assertTrue(fila.en_curso)
        datos = envasado.datos_de_envasado(self.agronomo, e.pk)
        self.assertEqual(datos.bloqueo, f"{t.get_full_name()} ya inició la ruta con esta entrega: su envasado no se puede cambiar. Los envases se confirman al concretarla.")
        self.assertEqual(codigos(self.rechazo(lambda: self.planificar(e, (b, 5)))), ["entrega_en_curso"])

    def test_regla_un_vehiculo_que_no_salio_no_pone_la_entrega_en_curso(self):
        """Regla «Entrega en curso»: con el vehículo del transportista sin salir a la ruta, el envasado se puede modificar."""
        sin_salir = transportista_con_vehiculo(self.e.invernadero)
        e, b = self.entrega_nueva(transportista=sin_salir, fecha=HOY), envase(self.e.invernadero)
        self.assertFalse(envasado.entregas_para_envasar(self.agronomo)[0].en_curso)
        self.planificar(e, (b, 5))

    def test_ext_10a_la_entrega_concretada_o_cancelada_no_registra_nada_e_informa(self):
        """Extensión 10a: al registrar, la entrega ya no está «a realizar»: nada cambia e informa la situación de la entrega."""
        b = envase(self.e.invernadero)
        for estado in ("concretada", "cancelada"):
            e = self.entrega_nueva()
            carga = self.carga(e, (b, 5))
            if estado == "concretada":
                marcar_concretada(e)  # COM-06a: una concretada trae sus cantidades y su monto (invariantes de entregas)
            else:
                OrdenTrabajo.objects.filter(pk=e.pk).update(estado_orden=estado, fecha_resolucion_orden=HOY, motivo_cancelacion="x")
            error = self.rechazo(lambda: envasado.planificar_envasado(self.agronomo, carga))
            self.assertEqual(codigos(error), ["entrega_no_a_realizar"], estado)
            self.assertIn(estado, str(error))
            self.assertFalse(ReservaInsumo.objects.filter(orden_id=e.pk).exists())

    def test_ext_10a_la_entrega_que_paso_a_estar_en_curso_no_registra_nada(self):
        """Extensión 10a (con 3b): entre la carga y la confirmación el transportista salió a la ruta."""
        t = transportista_con_vehiculo(self.e.invernadero)
        e, b = self.entrega_nueva(transportista=t, fecha=HOY), envase(self.e.invernadero)
        carga = self.carga(e, (b, 5))
        from comercial.models import Vehiculo

        Vehiculo.objects.filter(transportista=t).update(en_ruta=True, fecha_inicio_ruta=HOY)
        self.assertEqual(codigos(self.rechazo(lambda: envasado.planificar_envasado(self.agronomo, carga))), ["entrega_en_curso"])
        self.assertFalse(ReservaInsumo.objects.filter(orden_id=e.pk).exists())

    def test_ext_10c_otra_persona_cambio_el_envasado_no_registra_nada_y_vuelve_con_lo_vigente(self):
        """Extensión 10c: las reservas de la entrega cambiaron desde que se abrió la pantalla: `envasado_cambio`; al volver a abrir se ven las reservas vigentes."""
        e, b = self.entrega_nueva(), envase(self.e.invernadero, 30)
        carga = self.carga(e, (b, 5))  # la huella es la de las reservas vacías
        otra = envase(self.e.invernadero, nombre="Cajón")
        self.planificar(e, (otra, 3))  # otra persona (u otra pestaña) cambió el envasado
        auditoria = RegistroAuditoria.objects.count()
        error = self.rechazo(lambda: envasado.planificar_envasado(self.agronomo, carga))
        self.assertEqual(codigos(error), ["envasado_cambio"])
        self.assertEqual(RegistroAuditoria.objects.count(), auditoria)
        self.assertEqual(list(self.activas(e)), [otra.pk])
        datos = envasado.datos_de_envasado(self.agronomo, e.pk)
        self.assertEqual([f.nombre for f in datos.filas], ["Cajón"])
        self.assertEqual(datos.huella, envasado.huella_de(e.pk))

    def test_ext_10c_una_carga_sin_huella_se_rechaza(self):
        """La huella viaja con el formulario (como la de PROD-MOD-CSC): una carga sin huella no se confirma."""
        e, b = self.entrega_nueva(), envase(self.e.invernadero)
        self.assertEqual(codigos(self.rechazo(lambda: self.planificar(e, (b, 5), huella=""))), ["envasado_cambio"])

    # ---- lo que no cambia, y las consultas ----

    def test_garantia_la_operacion_es_atomica_si_falla_no_queda_ninguna_reserva_ni_registro(self):
        """Garantía mínima 1: si falla algo a mitad del registro, no queda ninguna reserva nueva ni log parcial."""
        from unittest import mock

        e, b, c = self.entrega_nueva(), envase(self.e.invernadero), envase(self.e.invernadero, nombre="Cajón")
        auditoria = RegistroAuditoria.objects.count()
        with mock.patch("comercial.servicios.envasado.RegistroAuditoria.objects.registrar", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                self.planificar(e, (b, 5), (c, 2))
        self.assertFalse(ReservaInsumo.objects.filter(orden_id=e.pk).exists())
        self.assertEqual(RegistroAuditoria.objects.count(), auditoria)

    def test_regla_la_lista_no_hace_consultas_por_fila(self):
        """Pruebas: `assertNumQueries` igual con una y con tres entregas (una consulta por tabla)."""
        self.entrega_nueva(transportista=transportista_con_vehiculo(self.e.invernadero))  # con transportista desde la primera: sin él, no se consultan los vehículos
        with CaptureQueriesContext(connection) as una:
            envasado.entregas_para_envasar(self.agronomo)
        self.entrega_nueva(dias=4)
        self.entrega_nueva(dias=5, transportista=transportista_con_vehiculo(self.e.invernadero))
        with CaptureQueriesContext(connection) as tres:
            envasado.entregas_para_envasar(self.agronomo)
        self.assertEqual(len(tres), len(una))
