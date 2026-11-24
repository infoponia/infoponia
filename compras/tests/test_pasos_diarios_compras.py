# Pruebas de los pasos diarios 60, 61 y 62 de compras (CMP-03, paso 5): ``paso_pedidos_vencidos``, ``paso_recordatorio_de_validez`` y
# ``paso_pedidos_sin_cotizacion_elegible`` de ``compras/procesos.py``. Fuente: D-87 punto 4 (tabla de los pasos 60 a 62 y «Sin aviso dado» y «recordado» se guardan
# en el pedido), D-56 (el contrato del proceso diario: ``funcion(hoy) -> ResumenDePaso``, idempotente, una unidad por transacción, ``hoy`` como parámetro y nunca la
# hora, si un paso falla los demás siguen), docs/casos_de_uso/compras/ordenes_de_compra.md («Pasos diarios 60 a 62», la regla «Aviso de vencimiento» de CMP-GNR-ODC y
# «Actualizaciones de A0 que mandan», H16), CMP-CNL-PED («Cancelaciones automáticas», causas ``nadie_cotizo`` y ``sin_cotizaciones_elegibles``) y H21 (a quién se avisa).
#
# Los pasos que fijan estas pruebas (``ResumenDePaso(procesados, creados, resueltos, detalle)``):
#   60 ``pedidos_vencidos`` («Pedidos vencidos»): por pedido «en cotización», con la fecha límite anterior a ``hoy`` y ``aviso_vencimiento_dado`` en falso. Sin
#       cotizaciones: lo cancela («nadie cotizó»). Con cotizaciones: avisa al Agrónomo, pone ``aviso_vencimiento_dado`` y pasa a «vencido» sus enlaces vigentes.
#       procesados = pedidos tratados; creados = pedidos avisados; resueltos = pedidos cancelados.
#   61 ``recordatorio_de_validez`` («Recordatorio de validez de cotizaciones»): por pedido vencido sin resolver, si la **primera** cotización elegible (la de fecha de
#       validez más próxima) vence mañana (``fecha_validez == hoy + 1``) y no se recordó ya esa fecha (``recordatorio_validez_para``), avisa y la guarda.
#       procesados = pedidos revisados; creados = recordatorios; resueltos = 0.
#   62 ``pedidos_sin_cotizacion_elegible`` («Pedidos sin cotización elegible»): por pedido vencido sin resolver con cotizaciones «propuesta» pero ninguna elegible (validez
#       vencida o proveedor inactivo), lo cancela («sin cotizaciones elegibles»). procesados = pedidos revisados; creados = 0; resueltos = pedidos cancelados.
# Los tres: reciben ``hoy`` (un ``date``) y nunca leen la fecha por su cuenta (la fecha de cierre de una cancelación es ``hoy``: ``cancelar_pedido_automaticamente``
# acepta ``hoy``); un pedido por transacción; si uno falla se registra y los demás siguen, y al terminar el paso lanza ``RuntimeError`` (como el paso 10 de inventario)
# para que ``proceso_diario`` lo informe como fallido. Un pedido «vencido» es el «en cotización» con ``fecha_limite_cotizaciones < hoy`` (el último día todavía se cotiza).
# Los avisos y las marcas técnicas no se auditan (D-42). Los destinatarios son los de H21 sin excluir a nadie (no hay actor humano).
# El módulo se toma dentro de cada prueba (``perezoso``).

from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from compras.models import EnlaceProveedor, Pedido
from compras.tests.fabricas import cotizacion_de, detalle_de_pedido, enlace_de, invitar, proveedor
from compras.tests.fabricas import pedido as armar_pedido
from core import procesos as procesos_de_core
from core.models import Notificacion, RegistroAuditoria
from core.procesos import ResumenDePaso
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, perezoso
from maestros.models import Invernadero
from maestros.servicios import configuracion
from maestros.tests.fabricas import crear_agronomo_con_invernadero, crear_invernadero

pasos = perezoso("compras.procesos")
pedidos_de_compras = perezoso("compras.servicios.pedidos")

PASOS = {"pedidos_vencidos": ("Pedidos vencidos", 60), "recordatorio_de_validez": ("Recordatorio de validez de cotizaciones", 61), "pedidos_sin_cotizacion_elegible": ("Pedidos sin cotización elegible", 62)}


def el_paso(codigo):
    """El paso real registrado por `compras`."""
    return next(p for p in procesos_de_core.pasos_diarios() if p.codigo == codigo)


def proceso_diario(*args):
    """Corre ``proceso_diario`` y devuelve lo que imprimió."""
    salida = StringIO()
    call_command("proceso_diario", *args, stdout=salida)
    return salida.getvalue()


class PasosBase(ConDatosDeInventario, TestCase):
    """Ana (Norte y Norte 2), un Gerente y un pedido de Ana: 20 lechugas en Norte y 20 tomates en Norte 2, vencido ayer, con tolerancia 10 % (mínimo 18). Dos
    proveedores: A (cubre el pedido solo) y B."""

    def setUp(self):
        self.hoy = timezone.localdate()
        self.ana, self.norte = crear_agronomo_con_invernadero("Norte", email="ana@infoponia.com")
        self.norte2 = crear_invernadero("Norte 2", agronomo=self.ana)
        self.gerente = crear_gerente()
        self.lechuga_iin = existencia(insumo("Lechuga", unidad="unidad"), self.norte, minimo=0, precio="12.50")
        self.tomate_iin = existencia(insumo("Tomate", unidad="unidad"), self.norte2, minimo=0, precio="10.00")
        fila = configuracion.obtener()
        fila.porc_tolerancia_cobertura_pedido = 10
        fila.save(update_fields=["porc_tolerancia_cobertura_pedido"])
        self.a = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com")
        self.b = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.pedido, self.lechuga, self.tomate = self.nuevo_pedido()

    def nuevo_pedido(self, vencido_hace=1, agronomo=None):
        """Un pedido con los dos detalles, que venció hace ``vencido_hace`` días (con ``0`` vence hoy: todavía se cotiza). Devuelve ``(pedido, lechuga, tomate)``."""
        pedido = armar_pedido(agronomo or self.ana)
        lechuga = detalle_de_pedido(pedido, self.lechuga_iin, cantidad="20")
        tomate = detalle_de_pedido(pedido, self.tomate_iin, cantidad="20")
        Pedido.objects.filter(pk=pedido.pk).update(fecha_pedido=self.hoy - timedelta(days=7), fecha_limite_cotizaciones=self.hoy - timedelta(days=vencido_hace))
        pedido.refresh_from_db()
        return pedido, lechuga, tomate

    def cotizar_todo(self, pedido=None, proveedor_=None, validez_en_dias=10):
        """Una cotización de ``proveedor_`` (por omisión A) que cubre los dos detalles del pedido de ``self`` (o el indicado) y vence dentro de ``validez_en_dias``."""
        pedido = pedido or self.pedido
        lineas = [(d, 20, "100.00", 3) for d in pedido.detalles.order_by("id")]
        return cotizacion_de(pedido, proveedor_ or self.a, lineas, validez_en_dias=validez_en_dias)

    def ejecutar(self, codigo, hoy=None):
        return el_paso(codigo).funcion(hoy or self.hoy)

    def avisos(self, usuario=None, pedido=None):
        consulta = Notificacion.objects.filter(destinatario=usuario or self.ana)
        return consulta.filter(titulo__contains=str(pedido)) if pedido is not None else consulta

    def recargar(self, pedido=None):
        pedido = pedido or self.pedido
        pedido.refresh_from_db()
        return pedido


class RegistroDeLosPasosTests(PasosBase):
    """D-87 punto 4 y D-56: los tres pasos están registrados por ``ComprasConfig.ready()`` con su código, su nombre y su orden."""

    def test_d87_los_tres_pasos_estan_registrados_con_su_codigo_nombre_y_orden(self):
        registrados = {p.codigo: (p.nombre, p.orden) for p in procesos_de_core.pasos_diarios() if p.codigo in PASOS}
        self.assertEqual(registrados, PASOS)

    def test_d87_los_pasos_corren_despues_de_los_de_comercial_y_en_orden(self):
        """D-56 punto 6 y D-87: el 60 antes que el 61 y el 62; todos después del 50 reservado (planificar entregas)."""
        codigos = [p.codigo for p in procesos_de_core.pasos_diarios()]
        self.assertEqual([c for c in codigos if c in PASOS], ["pedidos_vencidos", "recordatorio_de_validez", "pedidos_sin_cotizacion_elegible"])
        self.assertTrue(all(p.orden > 50 for p in procesos_de_core.pasos_diarios() if p.codigo in PASOS))

    def test_d56_registrarlos_otra_vez_no_falla_ni_duplica(self):
        """``ready()`` puede correr más de una vez: un registro idéntico es idempotente."""
        for codigo in PASOS:
            paso = el_paso(codigo)
            procesos_de_core.registrar_paso_diario(paso.codigo, paso.nombre, paso.orden, paso.funcion)
            self.assertEqual([p.codigo for p in procesos_de_core.pasos_diarios()].count(codigo), 1)

    def test_d56_listar_muestra_los_pasos_60_a_62(self):
        """«Hecho cuando»: los pasos aparecen en el resumen del proceso diario (``--listar``)."""
        salida = proceso_diario("--listar")
        for codigo, (nombre, orden) in PASOS.items():
            self.assertIn(f"{orden} · {codigo} · {nombre}", salida)

    def test_d56_los_pasos_devuelven_un_resumen_de_paso(self):
        for codigo in PASOS:
            with self.subTest(codigo=codigo):
                self.assertIsInstance(self.ejecutar(codigo), ResumenDePaso)

    def test_d56_el_comando_corre_el_paso_con_una_fecha_simulada_y_lo_informa(self):
        """«Verificación a mano» 3: ``proceso_diario --fecha <un día después de la fecha límite> --solo pedidos_vencidos`` deja el pedido avisado y lo cuenta."""
        self.cotizar_todo()
        otro, _, _ = self.nuevo_pedido()
        Pedido.objects.filter(pk=otro.pk).update(fecha_limite_cotizaciones=self.hoy + timedelta(days=3), fecha_pedido=self.hoy)
        salida = proceso_diario("--fecha", (self.hoy + timedelta(days=4)).isoformat(), "--solo", "pedidos_vencidos")
        self.assertIn("Pedidos vencidos: procesados 2 · creados 1 · resueltos 1", salida)  # uno avisado (con cotización) y uno cancelado (nadie cotizó)


class PedidosVencidosTests(PasosBase):
    """Paso 60: avisa del pedido vencido con cotizaciones y cancela el que nadie cotizó."""

    def test_con_cotizaciones_avisa_al_agronomo_y_marca_el_aviso(self):
        """D-87 punto 4: el pedido vencido con cotizaciones avisa al Agrónomo del pedido y guarda ``aviso_vencimiento_dado``; el pedido sigue «en cotización»."""
        self.cotizar_todo()
        resumen = self.ejecutar("pedidos_vencidos")
        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (1, 1, 0))
        self.assertEqual(self.avisos(pedido=self.pedido).count(), 1)
        pedido = self.recargar()
        self.assertEqual((pedido.estado_pedido, pedido.aviso_vencimiento_dado), ("en_cotizacion", True))

    def test_regla_aviso_de_vencimiento_el_texto_dice_cuantas_cotizaciones_hay_para_revisar(self):
        """Regla «Aviso de vencimiento» de CMP-GNR-ODC: «venció la fecha límite del pedido N; hay X cotizaciones para revisar»."""
        self.cotizar_todo()
        self.cotizar_todo(proveedor_=self.b)
        self.ejecutar("pedidos_vencidos")
        aviso = self.avisos(pedido=self.pedido).get()
        texto = f"{aviso.titulo} {aviso.detalle}".lower()
        self.assertIn(f"venció la fecha límite del pedido {self.pedido}".lower(), texto)
        self.assertIn("hay 2 cotizaciones para revisar", texto)

    def test_regla_aviso_de_vencimiento_indica_por_detalle_cuantas_lineas_llegaron_y_si_alcanzan(self):
        """Regla «Aviso de vencimiento»: «por cada detalle, cuántas líneas recibió y si alcanzan la cobertura mínima». Con A, que cubre los dos: 1 línea, alcanza."""
        self.cotizar_todo()
        self.ejecutar("pedidos_vencidos")
        detalle = self.avisos(pedido=self.pedido).get().detalle
        for detalle_del_pedido in (self.lechuga, self.tomate):
            self.assertIn(f"{detalle_del_pedido}: 1 línea, alcanza la cantidad mínima", detalle)
        self.assertNotIn("deberá cancelarse", detalle)

    def test_regla_aviso_de_vencimiento_si_un_detalle_no_puede_cubrirse_anticipa_la_cancelacion(self):
        """Regla «Aviso de vencimiento»: «si algún detalle no puede cubrirse, anticipa que el pedido deberá cancelarse». B cotiza solo 10 lechugas: la lechuga no
        alcanza (mínimo 18) y el tomate no tiene líneas."""
        cotizacion_de(self.pedido, self.b, [(self.lechuga, 10, "100.00", 3)])
        self.ejecutar("pedidos_vencidos")
        detalle = self.avisos(pedido=self.pedido).get().detalle
        self.assertIn(f"{self.lechuga}: 1 línea, no alcanza la cantidad mínima", detalle)
        self.assertIn(f"{self.tomate}: 0 líneas, no alcanza la cantidad mínima", detalle)
        self.assertIn("deberá cancelarse", detalle)

    def test_post_los_enlaces_vigentes_pasan_a_vencido_y_los_usados_se_conservan(self):
        """D-87 punto 4: «pasa a ``vencido`` sus enlaces vigentes»; el ``usado`` es del proveedor que ya cotizó y no se toca."""
        usado, _ = enlace_de(invitar(self.pedido, self.a), estado="usado")
        vigente, _ = enlace_de(invitar(self.pedido, self.b))
        self.cotizar_todo()
        self.ejecutar("pedidos_vencidos")
        self.assertEqual((EnlaceProveedor.objects.get(pk=usado.pk).estado, EnlaceProveedor.objects.get(pk=vigente.pk).estado), ("usado", "vencido"))

    def test_sin_cotizaciones_lo_cancela_por_nadie_cotizo(self):
        """D-87 punto 4: sin cotizaciones, «lo cancela (nadie cotizó)»: causa ``nadie_cotizo``, su motivo fijo, la fecha de cierre de ``hoy``."""
        resumen = self.ejecutar("pedidos_vencidos")
        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (1, 0, 1))
        pedido = self.recargar()
        self.assertEqual((pedido.estado_pedido, pedido.causa_cancelacion, pedido.motivo_cancelacion, pedido.fecha_cierre_pedido), ("cancelado", "nadie_cotizo", "nadie cotizó", self.hoy))

    def test_sin_cotizaciones_avisa_la_cancelacion_segun_h21_y_no_el_vencimiento(self):
        """CMP-CNL-PED «Cancelaciones automáticas» y H21: la cancelación avisa al Agrónomo activo de cada destino; no se manda además el aviso de vencimiento."""
        self.ejecutar("pedidos_vencidos")
        (aviso,) = self.avisos(pedido=self.pedido)
        self.assertIn("cancelado", aviso.titulo)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_pedido").count(), 1)

    def test_una_cotizacion_descartada_no_cuenta_como_cotizacion_recibida(self):
        """Sin cotizaciones «propuesta» el pedido no tiene nada para revisar: se cancela por «nadie cotizó» aunque exista una cotización descartada."""
        self.cotizar_todo()
        from compras.models import Cotizacion

        Cotizacion.objects.filter(pedido=self.pedido).update(estado_cotizacion="descartada")
        self.ejecutar("pedidos_vencidos")
        self.assertEqual(self.recargar().causa_cancelacion, "nadie_cotizo")

    def test_regla_el_dia_de_la_fecha_limite_el_pedido_todavia_no_esta_vencido(self):
        """D-88 punto 2: el último día todavía se cotiza; el pedido vence al día siguiente."""
        pedido, _, _ = self.nuevo_pedido(vencido_hace=0)
        resumen = self.ejecutar("pedidos_vencidos")
        self.assertEqual(self.recargar(pedido).estado_pedido, "en_cotizacion")
        self.assertFalse(pedido.aviso_vencimiento_dado)
        self.assertEqual(resumen.procesados, 1)  # solo el pedido del setUp (vencido ayer)

    def test_un_pedido_cerrado_o_cancelado_no_se_trata(self):
        """Solo los pedidos «en cotización»: uno cerrado o cancelado ya se resolvió."""
        for estado, causa in (("cerrado", None), ("cancelado", "manual")):
            Pedido.objects.filter(pk=self.pedido.pk).update(estado_pedido=estado, causa_cancelacion=causa, motivo_cancelacion="x" if causa else "", fecha_cierre_pedido=self.hoy)
            self.assertEqual(self.ejecutar("pedidos_vencidos").procesados, 0)

    def test_idempotencia_correr_dos_veces_el_mismo_dia_no_repite_avisos_ni_cancelaciones(self):
        """Idempotencia (D-56 y D-87): la segunda corrida del mismo día no trata a nadie ni crea ninguna notificación; sirve con el pedido avisado y con el cancelado."""
        self.cotizar_todo()
        sin_cotizar, _, _ = self.nuevo_pedido()
        primera = self.ejecutar("pedidos_vencidos")
        avisos, auditorias = Notificacion.objects.count(), RegistroAuditoria.objects.filter(accion="cancelacion_pedido").count()
        segunda = self.ejecutar("pedidos_vencidos")
        self.assertEqual((primera.procesados, primera.creados, primera.resueltos), (2, 1, 1))
        self.assertEqual((segunda.procesados, segunda.creados, segunda.resueltos), (0, 0, 0))
        self.assertEqual(Notificacion.objects.count(), avisos)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_pedido").count(), auditorias)
        self.assertEqual(self.recargar(sin_cotizar).estado_pedido, "cancelado")

    def test_h21_con_destinos_de_dos_agronomos_avisa_a_los_dos_y_sin_agronomo_activo_al_gerente(self):
        """H21: el Agrónomo activo de cada destino; por cada destino sin Agrónomo activo, el Gerente (una sola vez). Aquí no hay actor humano que excluir."""
        beto, _ = crear_agronomo_con_invernadero("Sur", email="beto@infoponia.com")
        Invernadero.objects.filter(pk=self.norte2.pk).update(agronomo=beto)
        self.cotizar_todo()
        self.ejecutar("pedidos_vencidos")
        self.assertEqual(set(Notificacion.objects.values_list("destinatario_id", flat=True)), {self.ana.pk, beto.pk})
        Invernadero.objects.filter(pk=self.norte2.pk).update(agronomo=None)
        otro, _, _ = self.nuevo_pedido()
        self.cotizar_todo(pedido=otro)
        self.ejecutar("pedidos_vencidos")
        self.assertEqual(self.avisos(self.gerente, otro).count(), 1)

    def test_d56_el_paso_usa_la_fecha_que_recibe_y_no_la_del_reloj(self):
        """D-56 punto 4: ``hoy`` es un parámetro. Con una fecha anterior al límite no trata nada; con una posterior sí, y la fecha de cierre de la cancelación es ``hoy``."""
        pedido, _, _ = self.nuevo_pedido(vencido_hace=-3)  # vence dentro de 3 días
        simulado = self.hoy + timedelta(days=10)
        self.assertEqual(self.ejecutar("pedidos_vencidos", self.hoy - timedelta(days=30)).procesados, 0)
        self.assertEqual(self.ejecutar("pedidos_vencidos", simulado).procesados, 2)
        self.assertEqual(self.recargar(pedido).fecha_cierre_pedido, simulado)
        self.assertEqual(self.recargar().fecha_cierre_pedido, simulado)

    def test_d56_un_pedido_que_falla_no_impide_tratar_a_los_demas_y_se_reintenta_despues(self):
        """D-56 puntos 4 y 5: una transacción por pedido; si la del primero falla, el segundo igual se avisa; el paso lanza al terminar, y el pedido que falló no
        queda marcado (se reintenta en la próxima corrida)."""
        otro, _, _ = self.nuevo_pedido()
        self.cotizar_todo()
        self.cotizar_todo(pedido=otro)
        llamadas = []
        original = pasos.notificaciones.notificar_a_varios

        def falla_la_primera(*args, **kwargs):
            llamadas.append(1)
            if len(llamadas) == 1:
                raise RuntimeError("falla simulada")
            return original(*args, **kwargs)

        with mock.patch.object(pasos.notificaciones, "notificar_a_varios", side_effect=falla_la_primera):
            with self.assertRaises(RuntimeError):
                self.ejecutar("pedidos_vencidos")
        marcados = {p.pk: p.aviso_vencimiento_dado for p in Pedido.objects.filter(pk__in=[self.pedido.pk, otro.pk])}
        self.assertEqual(sorted(marcados.values()), [False, True])
        reintento = self.ejecutar("pedidos_vencidos")
        self.assertEqual((reintento.procesados, reintento.creados), (1, 1))
        self.assertTrue(all(p.aviso_vencimiento_dado for p in Pedido.objects.filter(pk__in=[self.pedido.pk, otro.pk])))


class RecordatorioDeValidezTests(PasosBase):
    """Paso 61: «Mañana vence la cotización de {proveedor} en el pedido P-…: si querés elegirla, generá la orden hoy»."""

    def test_si_la_primera_elegible_vence_manana_recuerda_al_agronomo(self):
        """D-87 punto 4: el pedido vencido sin resolver, con la primera cotización elegible venciendo mañana, avisa al Agrónomo con el texto fijo."""
        self.cotizar_todo(validez_en_dias=1)
        resumen = self.ejecutar("recordatorio_de_validez")
        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (1, 1, 0))
        aviso = self.avisos(pedido=self.pedido).get()
        self.assertIn(f"Mañana vence la cotización de Semillas del Sur S. A. en el pedido {self.pedido}: si querés elegirla, generá la orden hoy", f"{aviso.titulo} {aviso.detalle}")

    def test_se_guarda_la_fecha_recordada_en_el_pedido(self):
        """D-87 punto 4: ``recordatorio_validez_para`` guarda la fecha de validez que recordó."""
        self.cotizar_todo(validez_en_dias=1)
        self.ejecutar("recordatorio_de_validez")
        self.assertEqual(self.recargar().recordatorio_validez_para, self.hoy + timedelta(days=1))

    def test_idempotencia_una_vez_por_pedido_y_fecha(self):
        """D-87 punto 4: «una vez por pedido y fecha»: correr dos veces el mismo día no repite el aviso."""
        self.cotizar_todo(validez_en_dias=1)
        primera = self.ejecutar("recordatorio_de_validez")
        avisos = Notificacion.objects.count()
        segunda = self.ejecutar("recordatorio_de_validez")
        self.assertEqual((primera.creados, segunda.creados), (1, 0))
        self.assertEqual(Notificacion.objects.count(), avisos)

    def test_otra_fecha_de_validez_vuelve_a_recordar(self):
        """«Una vez por pedido **y fecha**»: cuando la primera elegible deja de serlo y la siguiente vence mañana, se recuerda de nuevo, con su fecha. La cotización de A
        es válida hasta hoy + 1 y la de B hasta hoy + 3; el día hoy + 2 la de A ya no sirve y la de B vence mañana."""
        self.cotizar_todo(validez_en_dias=1)
        self.cotizar_todo(proveedor_=self.b, validez_en_dias=3)
        self.ejecutar("recordatorio_de_validez")
        self.assertEqual(self.recargar().recordatorio_validez_para, self.hoy + timedelta(days=1))
        resumen = self.ejecutar("recordatorio_de_validez", self.hoy + timedelta(days=2))
        self.assertEqual(resumen.creados, 1)
        self.assertEqual(self.recargar().recordatorio_validez_para, self.hoy + timedelta(days=3))
        self.assertEqual(self.avisos(pedido=self.pedido).count(), 2)
        self.assertIn("Viveros del Este S. R. L.", self.avisos(pedido=self.pedido).order_by("-id").first().detalle)

    def test_si_la_primera_elegible_no_vence_manana_no_avisa(self):
        """Solo si **mañana** vence: una validez a 2 o más días, o ya vencida, no genera recordatorio."""
        self.cotizar_todo(validez_en_dias=2)
        self.assertEqual(self.ejecutar("recordatorio_de_validez").creados, 0)
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_una_cotizacion_no_elegible_no_cuenta_para_el_recordatorio(self):
        """Solo las elegibles: la de un proveedor inactivo que vence mañana no se recuerda (no se puede elegir)."""
        self.cotizar_todo(validez_en_dias=1)
        self.a.estado_proveedor = "inactivo"
        self.a.save(update_fields=["estado_proveedor"])
        self.assertEqual(self.ejecutar("recordatorio_de_validez").creados, 0)

    def test_un_pedido_que_todavia_admite_cotizaciones_no_se_recuerda(self):
        """Solo los pedidos vencidos sin resolver: con la fecha límite de hoy todavía llegan cotizaciones."""
        pedido, _, _ = self.nuevo_pedido(vencido_hace=0)
        self.cotizar_todo(pedido=pedido, validez_en_dias=1)
        self.assertEqual(self.ejecutar("recordatorio_de_validez").creados, 0)

    def test_un_pedido_cerrado_o_cancelado_no_se_recuerda(self):
        self.cotizar_todo(validez_en_dias=1)
        Pedido.objects.filter(pk=self.pedido.pk).update(estado_pedido="cerrado", fecha_cierre_pedido=self.hoy)
        self.assertEqual(self.ejecutar("recordatorio_de_validez").procesados, 0)

    def test_h21_avisa_a_cada_agronomo_de_los_destinos(self):
        """H21: el aviso va a quien corresponde (acá, el Agrónomo activo de los dos destinos, una sola vez)."""
        self.cotizar_todo(validez_en_dias=1)
        self.ejecutar("recordatorio_de_validez")
        self.assertEqual(list(Notificacion.objects.values_list("destinatario_id", flat=True)), [self.ana.pk])

    def test_d56_el_paso_usa_la_fecha_que_recibe(self):
        """D-56: con ``hoy`` simulado dos días después la cotización que vencía mañana ya venció (no es elegible) y no se recuerda."""
        self.cotizar_todo(validez_en_dias=1)
        self.assertEqual(self.ejecutar("recordatorio_de_validez", self.hoy + timedelta(days=2)).creados, 0)
        self.assertEqual(self.ejecutar("recordatorio_de_validez", self.hoy).creados, 1)


class PedidosSinCotizacionElegibleTests(PasosBase):
    """Paso 62: el pedido vencido cuyas cotizaciones ya no se pueden elegir se cancela solo."""

    def test_con_todas_las_cotizaciones_vencidas_lo_cancela(self):
        """D-87 punto 4: sin ninguna cotización elegible (validez vencida) se cancela por ``sin_cotizaciones_elegibles``, con la fecha de cierre de ``hoy``."""
        self.cotizar_todo(validez_en_dias=2)
        resumen = self.ejecutar("pedidos_sin_cotizacion_elegible", self.hoy + timedelta(days=3))
        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (1, 0, 1))
        pedido = self.recargar()
        self.assertEqual((pedido.estado_pedido, pedido.causa_cancelacion, pedido.motivo_cancelacion, pedido.fecha_cierre_pedido), ("cancelado", "sin_cotizaciones_elegibles", "sin cotizaciones elegibles", self.hoy + timedelta(days=3)))

    def test_con_el_proveedor_inactivo_tambien_lo_cancela(self):
        """D-87 punto 4: «validez vencida o proveedor inactivo»."""
        self.cotizar_todo()
        self.a.estado_proveedor = "inactivo"
        self.a.save(update_fields=["estado_proveedor"])
        self.ejecutar("pedidos_sin_cotizacion_elegible")
        self.assertEqual(self.recargar().causa_cancelacion, "sin_cotizaciones_elegibles")

    def test_con_una_sola_cotizacion_elegible_no_lo_cancela(self):
        """Basta una elegible: la de A está vencida pero la de B sirve."""
        self.cotizar_todo(validez_en_dias=1)
        self.cotizar_todo(proveedor_=self.b, validez_en_dias=10)
        self.assertEqual(self.ejecutar("pedidos_sin_cotizacion_elegible", self.hoy + timedelta(days=2)).resueltos, 0)
        self.assertEqual(self.recargar().estado_pedido, "en_cotizacion")

    def test_la_validez_de_hoy_todavia_es_elegible(self):
        """El día de la fecha de validez todavía se puede elegir: con ``hoy`` igual a la validez no se cancela."""
        self.cotizar_todo(validez_en_dias=2)
        self.assertEqual(self.ejecutar("pedidos_sin_cotizacion_elegible", self.hoy + timedelta(days=2)).resueltos, 0)

    def test_sin_cotizaciones_propuesta_no_lo_toca(self):
        """El pedido sin ninguna cotización «propuesta» es del paso 60 («nadie cotizó»): el 62 no lo cancela."""
        resumen = self.ejecutar("pedidos_sin_cotizacion_elegible")
        self.assertEqual((resumen.procesados, resumen.resueltos), (0, 0))
        self.assertEqual(self.recargar().estado_pedido, "en_cotizacion")

    def test_un_pedido_que_todavia_admite_cotizaciones_no_se_cancela(self):
        """Solo los vencidos: con la fecha límite de hoy todavía puede llegar una cotización elegible."""
        pedido, _, _ = self.nuevo_pedido(vencido_hace=0)
        self.cotizar_todo(pedido=pedido, validez_en_dias=1)
        self.a.estado_proveedor = "inactivo"
        self.a.save(update_fields=["estado_proveedor"])
        resumen = self.ejecutar("pedidos_sin_cotizacion_elegible")
        self.assertEqual((resumen.procesados, resumen.resueltos), (0, 0))  # el del setUp no tiene cotizaciones (es del paso 60) y este todavía no venció
        self.assertEqual(self.recargar(pedido).estado_pedido, "en_cotizacion")

    def test_avisa_la_cancelacion_segun_h21_con_el_texto_del_motivo(self):
        """CMP-CNL-PED «Cancelaciones automáticas» y D-87: «Se canceló el pedido P-… porque ninguna cotización se puede elegir (validez vencida o proveedor inactivo)»
        al Agrónomo activo de cada destino; se audita como InfoPonia."""
        self.cotizar_todo()
        self.a.estado_proveedor = "inactivo"
        self.a.save(update_fields=["estado_proveedor"])
        self.ejecutar("pedidos_sin_cotizacion_elegible")
        aviso = self.avisos(pedido=self.pedido).get()
        self.assertIn(f"Se canceló el pedido {self.pedido} porque ninguna cotización se puede elegir (validez vencida o proveedor inactivo)", f"{aviso.titulo} {aviso.detalle}")
        registro = RegistroAuditoria.objects.get(accion="cancelacion_pedido")
        self.assertIsNone(registro.usuario_id)

    def test_idempotencia_correr_dos_veces_el_mismo_dia_no_repite_cancelaciones(self):
        self.cotizar_todo()
        self.a.estado_proveedor = "inactivo"
        self.a.save(update_fields=["estado_proveedor"])
        primera = self.ejecutar("pedidos_sin_cotizacion_elegible")
        avisos = Notificacion.objects.count()
        segunda = self.ejecutar("pedidos_sin_cotizacion_elegible")
        self.assertEqual((primera.resueltos, segunda.procesados, segunda.resueltos), (1, 0, 0))
        self.assertEqual(Notificacion.objects.count(), avisos)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_pedido").count(), 1)

    def test_d56_un_pedido_que_falla_no_impide_cancelar_los_demas(self):
        """D-56 puntos 4 y 5: si la cancelación del primero falla, el segundo igual se cancela; el paso lanza al terminar y el que falló se reintenta."""
        otro, _, _ = self.nuevo_pedido()
        for pedido in (self.pedido, otro):
            self.cotizar_todo(pedido=pedido)
        self.a.estado_proveedor = "inactivo"
        self.a.save(update_fields=["estado_proveedor"])
        original = pedidos_de_compras.cancelar_pedido_automaticamente
        llamadas = []

        def falla_la_primera(pedido, causa, **kwargs):
            llamadas.append(pedido.pk)
            if len(llamadas) == 1:
                raise RuntimeError("falla simulada")
            return original(pedido, causa, **kwargs)

        with mock.patch("compras.servicios.pedidos.cancelar_pedido_automaticamente", side_effect=falla_la_primera):
            with self.assertRaises(RuntimeError):
                self.ejecutar("pedidos_sin_cotizacion_elegible")
        self.assertEqual(sorted(Pedido.objects.filter(pk__in=[self.pedido.pk, otro.pk]).values_list("estado_pedido", flat=True)), ["cancelado", "en_cotizacion"])
        self.assertEqual(self.ejecutar("pedidos_sin_cotizacion_elegible").resueltos, 1)

    def test_d56_el_paso_usa_la_fecha_que_recibe(self):
        """D-56: con ``hoy`` anterior al vencimiento de la validez no cancela; con una posterior, sí."""
        self.cotizar_todo(validez_en_dias=3)
        self.assertEqual(self.ejecutar("pedidos_sin_cotizacion_elegible", self.hoy).resueltos, 0)
        self.assertEqual(self.ejecutar("pedidos_sin_cotizacion_elegible", self.hoy + timedelta(days=4)).resueltos, 1)


class LosTresPasosJuntosTests(PasosBase):
    """«Hecho cuando»: los pasos 60 a 62 corren solos, en orden, y son idempotentes."""

    def test_el_dia_que_vence_la_ultima_cotizacion_el_proceso_avisa_y_cancela_una_sola_vez(self):
        """Con una única cotización que venció ayer: el proceso diario completo avisa el vencimiento (60: hay una cotización para revisar), no recuerda nada (61: ya no
        hay ninguna elegible) y cancela el pedido (62); una segunda corrida del mismo día no repite nada."""
        self.cotizar_todo(validez_en_dias=0)  # válida hasta hoy
        manana = self.hoy + timedelta(days=1)
        primera = {p.codigo: r for p, r, e in procesos_de_core.correr_proceso_diario(manana) if p.codigo in PASOS}
        self.assertEqual((primera["pedidos_vencidos"].creados, primera["recordatorio_de_validez"].creados, primera["pedidos_sin_cotizacion_elegible"].resueltos), (1, 0, 1))
        self.assertEqual(self.recargar().estado_pedido, "cancelado")
        avisos = Notificacion.objects.count()
        segunda = {p.codigo: r for p, r, e in procesos_de_core.correr_proceso_diario(manana) if p.codigo in PASOS}
        self.assertEqual(sum(r.procesados for r in segunda.values()), 0)
        self.assertEqual(Notificacion.objects.count(), avisos)
