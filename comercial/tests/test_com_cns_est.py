# Pruebas de COM-CNS-EST, Consultar Estadísticas Comerciales (COM-08c; docs/casos_de_uso/comercial/estadisticas.md; D-94, punto 15): `filtros_de_estadisticas`, `estadisticas` y `resultados_del_mes`.
# Una prueba por regla (numeración del caso de uso, reglas 1 a 11), más la postcondición a (consulta pura) y el rendimiento (sin consultas por fila). Cada prueba arma sus propios datos.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar), en `comercial/servicios/estadisticas.py`:
#   - `filtros_de_estadisticas(actor, get, hoy) -> FiltrosDeEstadisticas(desde, hasta, periodo, invernadero_id, vendedor_id, meses, invernaderos, vendedores)`. `get` es un diccionario (o `QueryDict`) con
#     `periodo` («AAAA-MM» o «rango»), `desde`, `hasta` (fechas ISO), `invernadero` y `vendedor` (ids). `meses` es `((«AAAA-MM», texto), ...)`; `invernaderos` y `vendedores`, `((id, nombre), ...)`.
#     Errores (`ValidationError` con código estable): `periodo_invalido`, `invernadero_fuera_de_alcance`, `vendedor_no_admitido`; `PermissionDenied` para otro rol (`sin_permiso`).
#   - `estadisticas(actor, filtros, hoy) -> Estadisticas(filtros, ventas, puntualidad, incumplimientos, cobranza, faltantes, clientes, enlaces)`; los campos de cada indicador son los de las
#     `namedtuple` del módulo (`Ventas`, `Puntualidad`, `Incumplimientos`, `Cobranza`, `Faltantes`, `ClienteConMasCompras`, `Enlaces`). Montos en `Decimal` de dos decimales; los porcentajes y el
#     promedio de retraso, en `Decimal` SIN redondear (`None` si no hay entregas / con retraso).
#   - `resultados_del_mes(actor, hoy) -> ResultadosDelMes(desde, hasta, ventas, puntualidad, incumplimientos)`: el mes de `hoy`, del 1 a `hoy`.
#   - Funciones internas, una por indicador: `_ventas(actor, filtros)`, `_puntualidad(actor, filtros)`, `_incumplimientos(actor, filtros)`, `_cobranza(actor, filtros, hoy)`, `_faltantes(actor, filtros)`
#     y `_clientes(actor, filtros)`.
#   - Variedad: el texto `str(variedad)` («Cultivo Variedad»). Enlaces: `Enlaces` con las URL de la regla 10 (los destinos no admiten rango: ver el «Cierre» de COM-08c).

from datetime import date, datetime, timedelta, timezone as zona
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from comercial.models import CompraVenta, DetalleEntrega, DetalleVenta, Entrega, IntentoFallido, SolicitudRevision
from comercial.servicios import entregas
from comercial.servicios import estadisticas
from comercial.servicios.estadisticas import FiltrosDeEstadisticas, VentaDeVariedad
from comercial.tests.base_cobranza import codigos
from comercial.tests.fabricas import (
    _aceptar,
    anulacion,
    anulacion_de_cobro,
    cliente,
    cobro,
    compra_venta,
    detalle,
    direccion_de_cliente,
    discrepancia,
    discrepancia_aceptada,
    entrega_concretada,
    entrega_de_suministro,
    entrega_en_mora,
    escenario_comercial,
    marcar_concretada,
    queja_aceptada,
    reserva_lista,
    segundo_invernadero,
    solicitud_rechazada,
)
from core.models import RegistroAuditoria, Usuario, Vendedor
from core.tests.fabricas import crear_gerente
from inventario.servicios import stock
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_transportista, crear_vendedor
from produccion.tests.fabricas import lote_maduro, variedad_con_stock

D = Decimal
HOY = timezone.localdate()
ULTIMO_DEL_MES_ANTERIOR = HOY.replace(day=1) - timedelta(days=1)
HACE_UN_MES = (HOY - ULTIMO_DEL_MES_ANTERIOR).days  # concretada ese día: cae en el mes anterior, cualquiera sea el día de hoy
PERIODO_ANTERIOR = f"{ULTIMO_DEL_MES_ANTERIOR.year}-{ULTIMO_DEL_MES_ANTERIOR.month:02d}"
UN_DIA = timedelta(days=1)


class BaseDeEstadisticas(ConDatosDeInventario, TestCase):
    """Un invernadero con su Vendedor, un lote de 5.000 plantas, un Gerente y un segundo Vendedor con su cliente. Ayudas para armar entregas concretadas de compra-venta y de suministro, con la
    fecha de concreción que se pida (`hace` días atrás)."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 5000)
        cls.gerente = crear_gerente()
        cls.otro_vendedor = crear_vendedor(email="otro.vendedor@infoponia.com")
        cls.otro_cliente = cliente(razon_social="Otro Cliente S.A.")
        direccion_de_cliente(cls.otro_cliente)

    # ---- armado de datos ----

    def venta(self, *, cantidad=10, precio="100.00", pactada=1, hace=0, lote=None, variedad=None, cliente_=None, vendedor=None, cantidades=None):
        """Una compra-venta (con retiro) con una entrega concretada hace `hace` días; `pactada` es cuántos días desde hoy cae la fecha pactada. Devuelve la entrega."""
        variedad = variedad or self.e.variedad
        venta_ = compra_venta(self.e, dias=pactada, modalidad="retiro", cliente_=cliente_, vendedor=vendedor)
        detalle_ = detalle(venta_, variedad, cantidad, precio)
        reserva_ = reserva_lista(detalle_, lote or self.lote, cantidad)
        cobrada = cantidades is None or any(entregada for entregada, _, _ in cantidades)  # un pago es de más de $ 0: si el cliente rechazó todo al recibir, no hay cobro
        nueva = entrega_concretada(venta_, [reserva_], cantidades=cantidades, con_pago=cobrada)
        return marcar_concretada(nueva, cantidades=cantidades, hace_dias=hace) if hace else nueva

    def suministro(self, *, hace=0, cantidad=10, precio="100.00", plazo=10, vendedor=None, cliente_=None, lote=None, cantidades=None):
        """Un suministro nuevo con una entrega concretada hace `hace` días (su primer período cae hoy)."""
        return entrega_de_suministro(self.e, lote or self.lote, cantidad=cantidad, precio=precio, plazo_pago=plazo, hace_dias=hace, vendedor=vendedor, cliente_=cliente_, cantidades=cantidades)

    def en_mora(self, dias_de_mora, **extra):
        """Una entrega de suministro de $ 1.000,00 que venció hace `dias_de_mora` días."""
        return entrega_en_mora(self.e, self.lote, dias_de_mora=dias_de_mora, **extra)

    def del_otro_vendedor(self, **extra):
        """Una entrega de suministro de $ 1.000,00 de `otro_vendedor`, con su cliente."""
        return self.suministro(vendedor=self.otro_vendedor, cliente_=self.otro_cliente, **extra)

    def otra_variedad(self):
        """Una segunda variedad del invernadero con su lote maduro de 5.000 plantas: `(variedad, lote)`."""
        variedad, _ = variedad_con_stock(self.e, nombre="Rúcula Selvática")
        return variedad, lote_maduro(self.e, 5000, variedad=variedad)

    def prometer(self, entrega_, fecha):
        """Cambia la fecha del período de todas las líneas de suministro de la entrega (la fecha prometida al cliente)."""
        DetalleEntrega.objects.filter(entrega=entrega_).update(fecha_periodo=fecha)

    def reprogramar(self, entrega_, fecha):
        """Deja la fecha programada de la entrega en `fecha` (reprogramada), sin tocar la prometida ni la de concreción."""
        Entrega.objects.filter(pk=entrega_.pk).update(fecha_creacion_orden=fecha, fecha_programada_orden=fecha)

    def intento(self, entrega_, cuando=None, motivo="cliente_ausente"):
        """Un intento fallido de la entrega, en `cuando` (por omisión, ahora)."""
        transportista = crear_transportista(email=f"transportista{IntentoFallido.objects.count() + 1}@infoponia.com")
        return IntentoFallido.objects.create(entrega=entrega_, transportista=transportista, fecha_hora=cuando or timezone.now(), fecha_programada=HOY, motivo=motivo)

    def con_faltante(self, estado="pendiente_decision", *, cuando=None, cantidad=10, lotes=None, variedad=None):
        """Un detalle de compra-venta en `estado` con `fecha_pendiente_decision` = `cuando` (por omisión, hoy) y una reserva de `cantidad` por cada lote de `lotes` (por omisión, el del escenario)."""
        venta_ = compra_venta(self.e, modalidad="retiro")
        detalle_ = detalle(venta_, variedad or self.e.variedad, cantidad, "100.00")
        for lote_ in lotes or [self.lote]:
            reserva_lista(detalle_, lote_, cantidad)
        DetalleVenta.objects.filter(pk=detalle_.pk).update(estado_detalle_venta=estado, fecha_pendiente_decision=cuando or HOY)
        return DetalleVenta.objects.get(pk=detalle_.pk)

    # ---- lectura ----

    def filtros(self, actor=None, hoy=None, **get):
        return estadisticas.filtros_de_estadisticas(actor or self.e.vendedor, get, hoy or HOY)

    def stats(self, actor=None, **get):
        actor = actor or self.e.vendedor
        return estadisticas.estadisticas(actor, self.filtros(actor, **get), HOY)

    def error(self, funcion, *args, **kwargs):
        """El `ValidationError` que lanza `funcion` (la prueba falla si no lanza)."""
        with self.assertRaises(ValidationError) as c:
            funcion(*args, **kwargs)
        return c.exception


class Regla1AlcanceTests(BaseDeEstadisticas):
    def test_regla_1_el_vendedor_ve_solo_los_datos_de_sus_contratos(self):
        """Regla 1: el Vendedor ve solo lo de sus contratos; el Gerente, todo."""
        self.venta(cantidad=10, precio="100.00")  # propia: $ 1.000,00
        self.del_otro_vendedor(cantidad=20, precio="100.00")  # ajena: $ 2.000,00
        self.assertEqual(self.stats(self.e.vendedor).ventas.total, D("1000.00"))
        self.assertEqual(self.stats(self.otro_vendedor).ventas.total, D("2000.00"))
        self.assertEqual(self.stats(self.gerente).ventas.total, D("3000.00"))

    def test_regla_1_el_gerente_filtra_por_vendedor(self):
        """Regla 1: el Gerente puede filtrar por Vendedor y el resultado es el de los contratos de ese Vendedor."""
        self.venta(cantidad=10, precio="100.00")
        self.del_otro_vendedor(cantidad=20, precio="100.00")
        propio = self.stats(self.gerente, vendedor=str(self.e.vendedor.pk))
        ajeno = self.stats(self.gerente, vendedor=str(self.otro_vendedor.pk))
        self.assertEqual((propio.ventas.total, ajeno.ventas.total), (D("1000.00"), D("2000.00")))
        self.assertEqual(propio.filtros.vendedor_id, self.e.vendedor.pk)

    def test_regla_1_el_vendedor_no_filtra_por_vendedor(self):
        """D-94 punto 15 (`vendedor_no_admitido`): el Vendedor no puede pedir otro Vendedor, ni siquiera él mismo."""
        for pedido in (str(self.otro_vendedor.pk), str(self.e.vendedor.pk)):
            self.assertIn("vendedor_no_admitido", codigos(self.error(estadisticas.filtros_de_estadisticas, self.e.vendedor, {"vendedor": pedido}, HOY)))

    def test_regla_1_el_gerente_no_filtra_por_un_vendedor_sin_contratos(self):
        """El Gerente elige entre los Vendedores que tienen algún contrato: uno sin contratos, o un valor que no es un id, da `vendedor_no_admitido`."""
        self.venta()
        for pedido in (str(self.otro_vendedor.pk), "99999999", "abc"):
            self.assertIn("vendedor_no_admitido", codigos(self.error(estadisticas.filtros_de_estadisticas, self.gerente, {"vendedor": pedido}, HOY)), pedido)

    def test_regla_1_los_vendedores_del_gerente_son_los_que_tienen_contratos_activos_o_no(self):
        """El desplegable de Vendedores del Gerente lista a todo Vendedor con algún contrato (también el de cuenta inactiva) y a ninguno sin contratos."""
        self.venta()
        self.del_otro_vendedor()
        Usuario.objects.filter(pk=self.otro_vendedor.pk).update(is_active=False)
        sin_contratos = crear_vendedor(email="sin.contratos@infoponia.com")
        ids = [pk for pk, _ in self.filtros(self.gerente).vendedores]
        self.assertIn(self.e.vendedor.pk, ids)
        self.assertIn(self.otro_vendedor.pk, ids)
        self.assertNotIn(sin_contratos.pk, ids)
        self.assertEqual(self.filtros(self.e.vendedor).vendedores, ())  # el Vendedor no tiene este filtro

    def test_regla_1_otro_rol_o_una_cuenta_inactiva_recibe_403(self):
        """Regla 1 y precondición a: solo un Vendedor o un Gerente con la cuenta activa; cualquier otro, `PermissionDenied`, en las dos funciones."""
        inactivo = Vendedor.objects.get(pk=self.e.vendedor.pk)
        inactivo.is_active = False
        filtros = FiltrosDeEstadisticas(desde=HOY, hasta=HOY)
        for actor in (self.e.agronomo, self.e.capataz, crear_transportista(email="transportista@infoponia.com"), inactivo, None):
            with self.assertRaises(PermissionDenied, msg=str(actor)):
                estadisticas.filtros_de_estadisticas(actor, {}, HOY)
            with self.assertRaises(PermissionDenied, msg=str(actor)):
                estadisticas.estadisticas(actor, filtros, HOY)
            with self.assertRaises(PermissionDenied, msg=str(actor)):
                estadisticas.resultados_del_mes(actor, HOY)

    def test_regla_1_estadisticas_vuelve_a_verificar_el_alcance(self):
        """`estadisticas` no se fía de los filtros que recibe (EST-03 puede armar los suyos): el Vendedor con un Vendedor o con el invernadero de otro, `ValidationError`."""
        ajeno = crear_vendedor(email="dueno.de.otro.invernadero@infoponia.com")
        otro_invernadero = segundo_invernadero(escenario_comercial("2"), "Invernadero Ajeno").invernadero
        casos = (
            (FiltrosDeEstadisticas(desde=HOY, hasta=HOY, vendedor_id=ajeno.pk), "vendedor_no_admitido"),
            (FiltrosDeEstadisticas(desde=HOY, hasta=HOY, invernadero_id=otro_invernadero.pk), "invernadero_fuera_de_alcance"),
        )
        for filtros, codigo in casos:
            self.assertIn(codigo, codigos(self.error(estadisticas.estadisticas, self.e.vendedor, filtros, HOY)))


class Regla2FiltrosTests(BaseDeEstadisticas):
    DIA = date(2026, 11, 26)  # un «hoy» fijo para probar los filtros sin datos

    def periodo(self, **get):
        f = self.filtros(self.gerente, hoy=self.DIA, **get)
        return f.desde, f.hasta, f.periodo

    def test_regla_2_por_omision_es_el_mes_actual_hasta_hoy(self):
        """Regla 2: por omisión, del 1 del mes actual hasta hoy."""
        self.assertEqual(self.periodo(), (date(2026, 11, 1), self.DIA, "2026-11"))
        self.assertEqual(self.periodo(periodo="2026-11"), (date(2026, 11, 1), self.DIA, "2026-11"))

    def test_regla_2_un_mes_pasado_va_del_1_al_ultimo_dia(self):
        """Regla 2 («otro mes»): un mes pasado completo, del 1 al último día (febrero de 2026 tiene 28)."""
        self.assertEqual(self.periodo(periodo="2026-10"), (date(2026, 10, 1), date(2026, 10, 31), "2026-10"))
        self.assertEqual(self.periodo(periodo="2026-02"), (date(2026, 2, 1), date(2026, 2, 28), "2026-02"))
        self.assertEqual(self.periodo(periodo="2025-08"), (date(2025, 8, 1), date(2025, 8, 31), "2025-08"))

    def test_regla_2_un_rango_de_fechas(self):
        """Regla 2 («un rango de fechas»): con `periodo=rango`, o sin `periodo` pero con fechas, se usa `desde` y `hasta` (inclusive)."""
        esperado = (date(2026, 11, 3), date(2026, 11, 10), "rango")
        self.assertEqual(self.periodo(periodo="rango", desde="2026-11-03", hasta="2026-11-10"), esperado)
        self.assertEqual(self.periodo(desde="2026-11-03", hasta="2026-11-10"), esperado)
        self.assertEqual(self.periodo(periodo="rango", desde="2026-11-26", hasta="2026-11-26")[:2], (self.DIA, self.DIA))  # un solo día, hasta hoy

    def test_regla_2_con_un_mes_elegido_las_fechas_del_formulario_no_cuentan(self):
        """El formulario manda siempre «desde» y «hasta» (sin JavaScript se ven): con un mes elegido se ignoran."""
        self.assertEqual(self.periodo(periodo="2026-10", desde="2026-11-03", hasta="2026-11-10"), (date(2026, 10, 1), date(2026, 10, 31), "2026-10"))

    def test_regla_2_un_periodo_mal_formado_o_futuro_da_periodo_invalido(self):
        """`periodo_invalido`: un mes que no existe, un texto que no es un mes o un mes que todavía no empezó."""
        for periodo in ("2026-13", "2026-00", "abc", "2026", "2026-1", "2026-12", "2027-01"):
            self.assertIn("periodo_invalido", codigos(self.error(estadisticas.filtros_de_estadisticas, self.gerente, {"periodo": periodo}, self.DIA)), periodo)

    def test_regla_2_un_rango_invalido_da_periodo_invalido(self):
        """`periodo_invalido`: fecha mal escrita, una sola de las dos, inicio posterior al fin, fin posterior a hoy o sin fechas."""
        casos = (
            {"periodo": "rango", "desde": "2026-13-01", "hasta": "2026-11-10"},
            {"periodo": "rango", "desde": "2026-11-03", "hasta": "ayer"},
            {"periodo": "rango", "desde": "2026-11-03"},
            {"periodo": "rango", "hasta": "2026-11-10"},
            {"periodo": "rango"},
            {"periodo": "rango", "desde": "2026-11-10", "hasta": "2026-11-03"},
            {"periodo": "rango", "desde": "2026-11-20", "hasta": "2026-11-27"},
        )
        for get in casos:
            self.assertIn("periodo_invalido", codigos(self.error(estadisticas.filtros_de_estadisticas, self.gerente, get, self.DIA)), str(get))

    def test_regla_2_el_rango_maximo_es_de_366_dias(self):
        """D-94 punto 15: hasta 366 días (inclusive) está bien; 367 da `periodo_invalido`."""
        limite = self.DIA - timedelta(days=365)  # 366 días contando los dos extremos
        f = self.filtros(self.gerente, hoy=self.DIA, periodo="rango", desde=limite.isoformat(), hasta=self.DIA.isoformat())
        self.assertEqual((f.desde, f.hasta), (limite, self.DIA))
        pasado = limite - UN_DIA
        self.assertIn("periodo_invalido", codigos(self.error(estadisticas.filtros_de_estadisticas, self.gerente, {"periodo": "rango", "desde": pasado.isoformat(), "hasta": self.DIA.isoformat()}, self.DIA)))

    def test_regla_2_estadisticas_acepta_un_rango_de_mas_de_un_anio(self):
        """Para EST-03: los límites de la pantalla son de `filtros_de_estadisticas`; `estadisticas` calcula cualquier `desde` y `hasta` que traiga el `FiltrosDeEstadisticas`."""
        self.venta(hace=400)
        self.venta(hace=1)
        f = FiltrosDeEstadisticas(desde=HOY - timedelta(days=500), hasta=HOY)
        self.assertEqual(estadisticas.estadisticas(self.gerente, f, HOY).ventas.entregas, 2)

    def test_regla_2_los_desplegables_ofrecen_el_mes_actual_y_los_doce_anteriores(self):
        """Regla 2: el mes actual («… (hasta hoy)») y los doce anteriores, del más nuevo al más viejo, también cruzando el año."""
        meses = self.filtros(self.gerente, hoy=date(2026, 3, 9)).meses
        self.assertEqual(len(meses), 13)
        self.assertEqual(meses[0], ("2026-03", "Marzo de 2026 (hasta hoy)"))
        self.assertEqual(meses[1], ("2026-02", "Febrero de 2026"))
        self.assertEqual(meses[-1], ("2025-03", "Marzo de 2025"))
        self.assertEqual(meses[3], ("2025-12", "Diciembre de 2025"))

    def test_regla_2_un_mes_mas_viejo_se_suma_a_las_opciones(self):
        """Un mes pedido por la URL que está fuera de los trece se suma al final para que el desplegable lo muestre elegido."""
        meses = self.filtros(self.gerente, hoy=self.DIA, periodo="2025-08").meses
        self.assertEqual(len(meses), 14)
        self.assertEqual(meses[-1], ("2025-08", "Agosto de 2025"))

    def test_regla_2_el_vendedor_elige_entre_sus_invernaderos(self):
        """Regla 2: el Vendedor, entre los suyos activos; un invernadero ajeno, uno inexistente o un valor que no es un id dan `invernadero_fuera_de_alcance`."""
        suyo = segundo_invernadero(self.e, "Invernadero Sur").invernadero
        ajeno = segundo_invernadero(escenario_comercial("2"), "Invernadero Ajeno").invernadero
        self.assertEqual(self.filtros(self.e.vendedor, invernadero=str(suyo.pk)).invernadero_id, suyo.pk)
        self.assertEqual([pk for pk, _ in self.filtros(self.e.vendedor).invernaderos], [self.e.invernadero.pk, suyo.pk])  # por nombre: Norte, Sur
        for pedido in (str(ajeno.pk), "99999999", "abc"):
            self.assertIn("invernadero_fuera_de_alcance", codigos(self.error(estadisticas.filtros_de_estadisticas, self.e.vendedor, {"invernadero": pedido}, HOY)), pedido)

    def test_regla_2_un_invernadero_inactivo_se_ofrece_solo_si_el_vendedor_tuvo_contratos_ahi(self):
        """«Los suyos activos (y los inactivos donde tuvo contratos)»: un invernadero dado de baja sin entregas de sus contratos no se ofrece; con una entrega, sí."""
        sur = segundo_invernadero(self.e, "Invernadero Sur")
        self.venta(lote=lote_maduro(sur, 100))
        from maestros.models import Invernadero

        Invernadero.objects.filter(pk=sur.invernadero.pk).update(estado_invernadero="inactivo")
        sin_historia = segundo_invernadero(self.e, "Invernadero Viejo", activo=False).invernadero
        ids = [pk for pk, _ in self.filtros(self.e.vendedor).invernaderos]
        self.assertIn(sur.invernadero.pk, ids)
        self.assertNotIn(sin_historia.pk, ids)

    def test_regla_2_el_gerente_elige_entre_todos_los_invernaderos(self):
        """Regla 2: el Gerente, entre todos (también los de otros Vendedores)."""
        ajeno = segundo_invernadero(escenario_comercial("2"), "Invernadero Ajeno").invernadero
        self.assertEqual(self.filtros(self.gerente, invernadero=str(ajeno.pk)).invernadero_id, ajeno.pk)
        self.assertIn(ajeno.pk, [pk for pk, _ in self.filtros(self.gerente).invernaderos])
        self.assertIn("invernadero_fuera_de_alcance", codigos(self.error(estadisticas.filtros_de_estadisticas, self.gerente, {"invernadero": "99999999"}, HOY)))

    def test_regla_2_cada_indicador_usa_su_fecha_y_el_filtro_de_invernadero_acota_las_entregas(self):
        """Regla 2: el invernadero filtra las entregas por su invernadero de origen (D-94 punto 15)."""
        sur = segundo_invernadero(self.e, "Invernadero Sur")
        self.venta(cantidad=10, precio="100.00")  # sale del Norte
        self.venta(cantidad=30, precio="100.00", lote=lote_maduro(sur, 5000))  # sale del Sur
        self.assertEqual(self.stats().ventas.total, D("4000.00"))
        self.assertEqual(self.stats(invernadero=str(self.e.invernadero.pk)).ventas.total, D("1000.00"))
        self.assertEqual(self.stats(invernadero=str(sur.invernadero.pk)).ventas.total, D("3000.00"))


class Regla3VentasTests(BaseDeEstadisticas):
    def test_regla_3_suma_compra_ventas_y_suministros_por_variedad_de_mayor_a_menor_monto(self):
        """Regla 3: las líneas de las entregas concretadas en el período, de compra-ventas y de suministros, por variedad (plantas y monto), con el total; orden: monto descendente."""
        otra, lote_otra = self.otra_variedad()
        self.venta(cantidad=10, precio="100.00")  # variedad del escenario: $ 1.000,00
        self.suministro(cantidad=20, precio="50.00")  # variedad del escenario: $ 1.000,00
        self.venta(cantidad=5, precio="500.00", variedad=otra, lote=lote_otra)  # la otra: $ 2.500,00
        ventas = self.stats().ventas
        self.assertEqual(ventas.variedades[0], VentaDeVariedad(str(otra), 5, D("2500.00")))
        self.assertEqual(ventas.variedades[1], VentaDeVariedad(str(self.e.variedad), 30, D("2000.00")))
        self.assertEqual((ventas.total, ventas.entregas, ventas.plantas), (D("4500.00"), 3, 35))

    def test_regla_3_no_descuenta_indemnizaciones(self):
        """Regla 3: las ventas son lo que registró cada entrega; lo indemnizado va en el indicador 5."""
        entrega_ = self.suministro(cantidad=10, precio="100.00")
        discrepancia_aceptada(entrega_, monto="400.00", descontado="400.00", con_alerta=False)
        estad = self.stats()
        self.assertEqual(estad.ventas.total, D("1000.00"))
        self.assertEqual(estad.incumplimientos.descuentos, D("400.00"))

    def test_regla_3_usa_el_monto_de_la_entrega_y_no_el_precio_de_hoy(self):
        """D-94 punto 15 / lo que difiere del prototipo: el monto es `monto_pagar`, con el precio al concretar; un cambio posterior del precio del detalle no lo mueve."""
        entrega_ = self.suministro(cantidad=10, precio="100.00")
        detalle_ = entrega_.lineas.get().detalle_suministro
        type(detalle_).objects.filter(pk=detalle_.pk).update(precio_unitario_suministro=D("999.00"))
        self.assertEqual(self.stats().ventas.total, D("1000.00"))

    def test_regla_3_cuenta_por_fecha_de_concrecion_y_solo_entregas_concretadas(self):
        """Regla 3: solo cuentan las concretadas con `fecha_resolucion_orden` en el período (no la fecha pactada ni las «a realizar» o canceladas)."""
        self.venta(cantidad=10, hace=0)
        self.venta(cantidad=20, hace=HACE_UN_MES)  # el mes anterior
        pendiente = self.venta(cantidad=40)
        Entrega.objects.filter(pk=pendiente.pk).update(estado_orden="a_realizar", fecha_resolucion_orden=None, monto_total_entrega=None)  # no concretada
        self.assertEqual(self.stats().ventas.total, D("1000.00"))
        self.assertEqual(self.stats(periodo=PERIODO_ANTERIOR).ventas.total, D("2000.00"))
        rango = {"periodo": "rango", "desde": (HOY - timedelta(days=HACE_UN_MES + 1)).isoformat(), "hasta": HOY.isoformat()}
        self.assertEqual(self.stats(**rango).ventas.total, D("3000.00"))

    def test_regla_3_una_linea_rechazada_al_recibir_no_suma_plantas_ni_variedad(self):
        """Una línea entregada en 0 (el cliente la rechazó al recibir) no es una venta: no figura (va al indicador 7)."""
        self.venta(cantidad=10, precio="100.00", cantidades=[(0, 0, 10)])
        ventas = self.stats().ventas
        self.assertEqual((ventas.total, ventas.plantas, ventas.variedades), (D("0.00"), 0, ()))

    def test_regla_3_sin_ventas_el_total_es_cero(self):
        """Sin entregas en el período: total $ 0,00, ninguna variedad."""
        ventas = self.stats().ventas
        self.assertEqual((ventas.total, ventas.entregas, ventas.plantas, ventas.variedades), (D("0.00"), 0, 0, ()))


class Regla4PuntualidadTests(BaseDeEstadisticas):
    def test_regla_4_a_tiempo_es_en_la_fecha_prometida_o_antes_y_con_retraso_las_demas(self):
        """Regla 4: a tiempo = concretada en la fecha prometida o antes; con retraso, las demás. Cantidad, porcentaje y promedio de días de retraso de las con retraso."""
        self.venta(pactada=1)  # concretada hoy, prometida mañana: a tiempo
        self.venta(pactada=0)  # el mismo día: a tiempo
        self.venta(pactada=-3)  # 3 días de retraso
        self.venta(pactada=-1)  # 1 día de retraso
        p = self.stats().puntualidad
        self.assertEqual((p.total, p.a_tiempo, p.con_retraso), (4, 2, 2))
        self.assertEqual((p.porcentaje_a_tiempo, p.porcentaje_con_retraso), (D(50), D(50)))
        self.assertEqual(p.promedio_de_retraso, D(2))

    def test_regla_4_los_porcentajes_y_el_promedio_no_se_redondean(self):
        """Los porcentajes y el promedio se redondean recién para mostrar: el servicio devuelve el `Decimal` completo."""
        self.venta(pactada=1)
        self.venta(pactada=-1)
        self.venta(pactada=-2)
        p = self.stats().puntualidad
        self.assertEqual(p.porcentaje_a_tiempo, D(100) / D(3))
        self.assertEqual(p.porcentaje_con_retraso, D(200) / D(3))
        self.assertEqual(p.promedio_de_retraso, D("1.5"))

    def test_regla_4_sin_entregas_no_hay_porcentajes_ni_promedio(self):
        """Sin entregas concretadas en el período: porcentajes y promedio `None` («—» en la pantalla), no 0 %."""
        p = self.stats().puntualidad
        self.assertEqual((p.total, p.a_tiempo, p.con_retraso), (0, 0, 0))
        self.assertEqual((p.porcentaje_a_tiempo, p.porcentaje_con_retraso, p.promedio_de_retraso), (None, None, None))

    def test_regla_4_todas_a_tiempo_no_tienen_promedio_de_retraso(self):
        """Sin entregas con retraso el promedio es `None`, no 0."""
        self.venta(pactada=1)
        p = self.stats().puntualidad
        self.assertEqual((p.porcentaje_a_tiempo, p.promedio_de_retraso), (D(100), None))

    def test_regla_4_una_entrega_reprogramada_concretada_en_la_fecha_prometida_es_a_tiempo(self):
        """«Hecho cuando» de COM-08c: lo que cuenta es la fecha prometida (la pactada o la del período), no la programada, que pudo moverse."""
        venta_ = self.venta(pactada=-2, hace=2)  # prometida hace 2 días y concretada hace 2 días
        self.reprogramar(venta_, HOY - timedelta(days=3))  # programada antes de la concreción: con la programada sería retraso
        periodica = self.suministro(hace=3)  # el período cae hoy y se concretó hace 3 días: antes de lo prometido
        self.prometer(periodica, HOY - timedelta(days=3))  # prometida el mismo día de la concreción
        self.reprogramar(periodica, HOY - timedelta(days=4))
        p = self.stats(periodo="rango", desde=(HOY - timedelta(days=5)).isoformat(), hasta=HOY.isoformat()).puntualidad
        self.assertEqual((p.total, p.a_tiempo, p.con_retraso), (2, 2, 0))

    def test_regla_4_en_un_suministro_la_fecha_prometida_es_la_menor_de_las_lineas(self):
        """D-94 punto 15: en un suministro, la menor `fecha_periodo` de las líneas de la entrega (aunque la programada sea posterior)."""
        entrega_ = self.suministro()  # un período que cae hoy; concretada hoy: a tiempo
        linea = entrega_.lineas.get()
        DetalleEntrega.objects.create(
            entrega=entrega_, detalle_suministro=linea.detalle_suministro, fecha_periodo=HOY - timedelta(days=5), precio_unitario=linea.precio_unitario,
            cant_entregada=10, cant_perdida=0, cant_devuelta=0, monto_pagar=D("1000.00"),
        )
        self.reprogramar(entrega_, HOY + timedelta(days=10))  # una programada tardía haría parecer que llegó a tiempo
        p = self.stats().puntualidad
        self.assertEqual((p.total, p.a_tiempo, p.con_retraso, p.promedio_de_retraso), (1, 0, 1, D(5)))

    def test_regla_4_cuenta_solo_entregas_concretadas_en_el_periodo(self):
        """Las canceladas, las «a realizar» y las concretadas en otro período no entran."""
        self.venta(pactada=1, hace=HACE_UN_MES)
        cancelada = self.venta(pactada=-5)
        Entrega.objects.filter(pk=cancelada.pk).update(estado_orden="cancelada", motivo_cancelacion="Motivo de prueba", monto_total_entrega=None)
        self.assertEqual(self.stats().puntualidad.total, 0)
        self.assertEqual(self.stats(periodo=PERIODO_ANTERIOR).puntualidad.total, 1)

    def test_regla_4_los_intentos_fallidos_del_periodo_se_cuentan_aparte(self):
        """Regla 4: los intentos fallidos con fecha en el período, de las entregas del alcance, de cualquier estado; no son entregas con retraso."""
        entrega_ = self.suministro()
        self.intento(entrega_)
        self.intento(entrega_)
        self.intento(entrega_, cuando=timezone.now() - timedelta(days=HACE_UN_MES + 3))  # otro mes
        self.intento(self.del_otro_vendedor())  # de un contrato ajeno
        p = self.stats().puntualidad
        self.assertEqual(p.intentos_fallidos, 2)
        self.assertEqual(p.total, 1)
        self.assertEqual(self.stats(self.gerente).puntualidad.intentos_fallidos, 3)

    def test_regla_11_los_dias_se_toman_en_la_zona_horaria_de_argentina(self):
        """Regla 11: un intento a las 01:30 UTC del 27/11 es del 26/11 a las 22:30 (UTC−03:00): cuenta en el 26 y no en el 27."""
        entrega_ = self.suministro()
        self.intento(entrega_, cuando=datetime(2026, 11, 27, 1, 30, tzinfo=zona.utc))
        dia = {"periodo": "rango", "desde": "2026-11-26", "hasta": "2026-11-26"}
        siguiente = {"periodo": "rango", "desde": "2026-11-27", "hasta": "2026-11-27"}
        hoy = date(2026, 11, 27)
        self.assertEqual(estadisticas.estadisticas(self.gerente, estadisticas.filtros_de_estadisticas(self.gerente, dia, hoy), hoy).puntualidad.intentos_fallidos, 1)
        self.assertEqual(estadisticas.estadisticas(self.gerente, estadisticas.filtros_de_estadisticas(self.gerente, siguiente, hoy), hoy).puntualidad.intentos_fallidos, 0)

    def test_regla_11_la_fecha_actual_es_la_de_la_zona_del_sistema(self):
        """Regla 11: `stock.hoy()` (la que usa la pantalla) es la fecha en Argentina, no la de UTC."""
        from unittest import mock

        with mock.patch("django.utils.timezone.now", return_value=datetime(2026, 11, 27, 1, 30, tzinfo=zona.utc)):
            self.assertEqual(stock.hoy(), date(2026, 11, 26))


class Regla5IncumplimientosTests(BaseDeEstadisticas):
    def test_regla_5_suma_lo_aceptado_separando_descuentos_y_pagos_en_dinero(self):
        """Regla 5: quejas y discrepancias aceptadas en el período (por tipo), con Σ `monto_descontado` («descuentos») y Σ `monto_reintegrado` («pagadas en dinero»), y el total."""
        discrepancia_aceptada(self.suministro(), monto="300.00", descontado="300.00", con_alerta=False)
        queja_aceptada(self.suministro(), monto="500.00", descontado="200.00", reintegrado="300.00", medio="transferencia", con_alerta=False)
        i = self.stats().incumplimientos
        self.assertEqual((i.cantidad, i.quejas, i.discrepancias), (2, 1, 1))
        self.assertEqual((i.descuentos, i.pagos_en_dinero, i.total), (D("500.00"), D("300.00"), D("800.00")))

    def test_regla_5_solo_cuentan_las_aceptadas(self):
        """Las pendientes y las rechazadas no cuentan."""
        discrepancia(self.suministro(), con_alerta=False)  # pendiente
        solicitud_rechazada(discrepancia(self.suministro(), con_alerta=False))
        self.assertEqual(self.stats().incumplimientos, estadisticas.Incumplimientos(0, 0, 0, D("0.00"), D("0.00"), D("0.00")))

    def test_regla_5_cuenta_por_fecha_de_resolucion_y_no_por_fecha_de_la_solicitud(self):
        """Regla 5: «por fecha de resolución»: una solicitud de hace dos meses aceptada hoy cuenta hoy; una de hoy aceptada el mes anterior, en el mes anterior."""
        vieja = discrepancia_aceptada(self.suministro(), monto="100.00", con_alerta=False)
        SolicitudRevision.objects.filter(pk=vieja.pk).update(fecha_solicitud=HOY - timedelta(days=60))
        reciente = discrepancia_aceptada(self.suministro(), monto="200.00", con_alerta=False)
        SolicitudRevision.objects.filter(pk=reciente.pk).update(fecha_resolucion=ULTIMO_DEL_MES_ANTERIOR)
        self.assertEqual(self.stats().incumplimientos.total, D("100.00"))
        self.assertEqual(self.stats(periodo=PERIODO_ANTERIOR).incumplimientos.total, D("200.00"))

    def test_regla_5_una_resolucion_anulada_no_cuenta(self):
        """«Hecho cuando» de COM-08c y COM-ANL-SRV: una resolución anulada dejó la solicitud «pendiente» y no cuenta."""
        solicitud = discrepancia_aceptada(self.suministro(), monto="300.00", con_alerta=False)
        self.assertEqual(self.stats().incumplimientos.cantidad, 1)
        anulacion(solicitud)
        self.assertEqual(self.stats().incumplimientos, estadisticas.Incumplimientos(0, 0, 0, D("0.00"), D("0.00"), D("0.00")))

    def test_regla_5_una_resolucion_aceptada_otra_vez_cuenta_con_su_fecha_nueva(self):
        """D-94 punto 15: anulada y vuelta a aceptar en otro mes, cuenta en el mes de la aceptación nueva y no en el de la primera."""
        solicitud = discrepancia_aceptada(self.suministro(), monto="300.00", con_alerta=False)
        anulacion(solicitud)
        _aceptar(solicitud, monto="300.00", descontado=None, reintegrado="0.00", medio=None, gerente=None, observaciones="", contar=True)
        SolicitudRevision.objects.filter(pk=solicitud.pk).update(fecha_resolucion=ULTIMO_DEL_MES_ANTERIOR)
        self.assertEqual(self.stats().incumplimientos.cantidad, 0)
        self.assertEqual(self.stats(periodo=PERIODO_ANTERIOR).incumplimientos.cantidad, 1)

    def test_regla_5_respeta_el_alcance_y_el_invernadero(self):
        """Solo las solicitudes de las entregas del alcance y del invernadero pedido."""
        sur = segundo_invernadero(self.e, "Invernadero Sur")
        discrepancia_aceptada(self.suministro(), monto="100.00", con_alerta=False)
        discrepancia_aceptada(self.suministro(lote=lote_maduro(sur, 5000)), monto="200.00", con_alerta=False)
        discrepancia_aceptada(self.del_otro_vendedor(), monto="400.00", con_alerta=False)
        self.assertEqual(self.stats().incumplimientos.total, D("300.00"))
        self.assertEqual(self.stats(invernadero=str(sur.invernadero.pk)).incumplimientos.total, D("200.00"))
        self.assertEqual(self.stats(self.gerente).incumplimientos.total, D("700.00"))


class Regla6CobranzaTests(BaseDeEstadisticas):
    def test_regla_6_separa_pendientes_y_en_mora_y_las_en_mora_por_antiguedad(self):
        """Regla 6: monto a cobrar de las entregas de suministro sin pagar, pendientes y en mora, y las en mora por antigüedad: hasta 30, 31 a 60 y más de 60 días (los días 30, 31, 60 y 61)."""
        self.suministro(hace=0)  # vence en 10 días: pendiente
        self.suministro(hace=10)  # vence hoy: todavía pendiente
        self.en_mora(1)
        self.en_mora(30)  # hasta 30
        self.en_mora(31)
        self.en_mora(60)  # de 31 a 60
        self.en_mora(61)  # más de 60
        c = self.stats().cobranza
        self.assertEqual((c.pendiente_cantidad, c.pendiente_total), (2, D("2000.00")))
        self.assertEqual((c.en_mora_cantidad, c.en_mora_total), (5, D("5000.00")))
        self.assertEqual((c.hasta_30, c.de_31_a_60, c.mas_de_60), (D("2000.00"), D("2000.00"), D("1000.00")))

    def test_regla_6_es_una_foto_a_hoy_y_no_depende_del_periodo(self):
        """Regla 6: «foto a la fecha actual, no por período»: el mismo resultado con cualquier período."""
        self.en_mora(5)
        self.suministro(hace=0)
        actual = self.stats().cobranza
        self.assertEqual(self.stats(periodo=PERIODO_ANTERIOR).cobranza, actual)
        self.assertEqual(self.stats(periodo="rango", desde=(HOY - timedelta(days=100)).isoformat(), hasta=(HOY - timedelta(days=90)).isoformat()).cobranza, actual)
        self.assertEqual((actual.en_mora_total, actual.pendiente_total), (D("1000.00"), D("1000.00")))

    def test_regla_6_una_entrega_pagada_no_cuenta_y_un_cobro_anulado_vuelve_a_contar_como_deuda(self):
        """«Hecho cuando» de COM-08c y MD-136: con un cobro vigente la entrega no es deuda; si el cobro se anula, vuelve a contar."""
        entrega_ = self.en_mora(5)
        pago = cobro([entrega_])
        self.assertEqual(self.stats().cobranza.en_mora_total, D("0.00"))
        anulacion_de_cobro(pago)
        c = self.stats().cobranza
        self.assertEqual((c.en_mora_cantidad, c.en_mora_total), (1, D("1000.00")))

    def test_regla_6_usa_el_monto_a_cobrar_con_los_descuentos_y_una_saldada_no_cuenta(self):
        """El monto es el «monto a cobrar» (total menos lo descontado por solicitudes aceptadas, MD-115); si quedó en 0 (saldada, MD-125) no es deuda."""
        con_descuento = self.en_mora(5)
        discrepancia_aceptada(con_descuento, monto="300.00", descontado="300.00", con_alerta=False)
        saldada = self.en_mora(5)
        discrepancia_aceptada(saldada, monto="1000.00", descontado="1000.00", con_alerta=False)
        c = self.stats().cobranza
        self.assertEqual((c.en_mora_cantidad, c.en_mora_total), (1, D("700.00")))

    def test_regla_6_coincide_con_estado_de_pago_y_monto_a_cobrar(self):
        """Las fórmulas del indicador y las del estado de pago de la entrega no se separan: la suma coincide con `entregas.estado_de_pago` y `entregas.monto_a_cobrar`."""
        lista = [self.en_mora(3), self.en_mora(45), self.suministro(), self.suministro(hace=10), self.en_mora(70)]
        discrepancia_aceptada(lista[1], monto="250.00", descontado="250.00", con_alerta=False)
        cobro([lista[4]])
        ids = [e.pk for e in lista]
        estados, montos = entregas.estado_de_pago(ids, HOY), entregas.monto_a_cobrar(ids)
        c = self.stats().cobranza
        self.assertEqual(c.en_mora_total, sum((montos[i] for i in ids if estados[i] == "en_mora"), D("0.00")))
        self.assertEqual(c.pendiente_total, sum((montos[i] for i in ids if estados[i] == "pendiente"), D("0.00")))
        self.assertEqual(c.en_mora_cantidad, sum(1 for i in ids if estados[i] == "en_mora"))

    def test_regla_6_solo_entregas_de_suministro_concretadas(self):
        """Una entrega de compra-venta (se cobra al entregar) o de suministro «a realizar» no es cobranza."""
        self.venta()
        a_realizar = self.en_mora(5)
        Entrega.objects.filter(pk=a_realizar.pk).update(estado_orden="a_realizar", fecha_resolucion_orden=None, monto_total_entrega=None, fecha_vencimiento_pago=None)
        c = self.stats().cobranza
        self.assertEqual((c.pendiente_cantidad, c.en_mora_cantidad), (0, 0))

    def test_regla_6_respeta_el_alcance_y_el_invernadero(self):
        """Regla 1 y 2: el Vendedor ve su cobranza; el Gerente, la de todos; el filtro de invernadero acota."""
        sur = segundo_invernadero(self.e, "Invernadero Sur")
        self.en_mora(5)
        entrega_en_mora(self.e, lote_maduro(sur, 5000), dias_de_mora=5)
        self.del_otro_vendedor(hace=15)  # en mora, de otro Vendedor
        self.assertEqual(self.stats().cobranza.en_mora_total, D("2000.00"))
        self.assertEqual(self.stats(invernadero=str(sur.invernadero.pk)).cobranza.en_mora_total, D("1000.00"))
        self.assertEqual(self.stats(self.gerente).cobranza.en_mora_total, D("3000.00"))


class Regla7FaltantesTests(BaseDeEstadisticas):
    def test_regla_7_cuenta_los_detalles_que_pasaron_a_pendiente_de_decision_en_el_periodo(self):
        """Regla 7: «con faltante» = `fecha_pendiente_decision` en el período (D-94 punto 15), cualquiera sea el estado de hoy del detalle."""
        self.con_faltante("pendiente_decision")
        self.con_faltante("confirmado")  # el cliente aceptó la cantidad menor
        self.con_faltante("pendiente_decision", cuando=ULTIMO_DEL_MES_ANTERIOR)  # otro mes
        self.assertEqual(self.stats().faltantes.con_faltante, 2)
        self.assertEqual(self.stats(periodo=PERIODO_ANTERIOR).faltantes.con_faltante, 1)

    def test_regla_7_rechazados_por_cantidad_reducida_son_los_que_el_cliente_rechazo_sin_entrega(self):
        """D-94 punto 15: de los que tuvieron faltante en el período, los que hoy están «rechazado» y no tienen línea en una entrega concretada."""
        self.con_faltante("rechazado")  # lo rechazó el cliente
        self.con_faltante("confirmado")  # lo aceptó
        self.con_faltante("pendiente_decision")  # todavía no decidió
        self.con_faltante("rechazado", cuando=ULTIMO_DEL_MES_ANTERIOR)  # rechazado, pero con faltante en otro mes
        f = self.stats().faltantes
        self.assertEqual((f.con_faltante, f.rechazados_por_cantidad), (3, 1))

    def test_regla_7_un_rechazo_al_recibir_no_es_un_rechazo_por_cantidad_reducida(self):
        """Un detalle con una línea en una entrega concretada (el rechazo fue al recibir) no cuenta como rechazado por cantidad reducida."""
        entrega_ = self.venta(cantidades=[(0, 0, 10)])
        detalle_ = entrega_.lineas.get().detalle_venta
        DetalleVenta.objects.filter(pk=detalle_.pk).update(estado_detalle_venta="rechazado", fecha_pendiente_decision=HOY)
        f = self.stats().faltantes
        self.assertEqual((f.con_faltante, f.rechazados_por_cantidad, f.rechazados_al_recibir), (1, 0, 1))

    def test_regla_7_rechazados_al_recibir_son_las_lineas_de_venta_entregadas_en_cero_en_el_periodo(self):
        """D-94 punto 15: líneas de venta con `cant_entregada = 0` en entregas concretadas en el período; no las de suministro ni las de otro período."""
        self.venta(cantidades=[(0, 0, 10)])
        self.venta(cantidades=[(4, 0, 6)])  # recibió una parte: no es un rechazo
        self.venta(cantidades=[(0, 0, 10)], hace=HACE_UN_MES)  # otro mes
        self.suministro(cantidades=[(0, 0, 10)])  # una línea de suministro no es una línea de venta
        self.assertEqual(self.stats().faltantes.rechazados_al_recibir, 1)
        self.assertEqual(self.stats(periodo=PERIODO_ANTERIOR).faltantes.rechazados_al_recibir, 1)

    def test_regla_7_cancelados_son_los_detalles_cancelados_de_ventas_canceladas_en_el_periodo(self):
        """MD-130: detalles «cancelado» cuya venta tiene `fecha_cancelacion_venta` en el período, también si la venta se cobró por lo entregado («concretada»)."""
        for fecha, estado_venta in ((HOY, "cancelada"), (HOY, "concretada"), (ULTIMO_DEL_MES_ANTERIOR, "cancelada")):
            venta_ = compra_venta(self.e, modalidad="retiro", estado=estado_venta)
            detalle(venta_, self.e.variedad, 10, "100.00", estado="cancelado")
            CompraVenta.objects.filter(pk=venta_.pk).update(motivo_cancelacion_venta="cliente_desistio", fecha_cancelacion_venta=fecha)
        detalle(compra_venta(self.e, modalidad="retiro"), self.e.variedad, 10, "100.00", estado="abierto")  # una venta que no se canceló
        self.assertEqual(self.stats().faltantes.cancelados, 2)
        self.assertEqual(self.stats(periodo=PERIODO_ANTERIOR).faltantes.cancelados, 1)

    def test_regla_7_el_invernadero_de_un_detalle_es_el_de_sus_reservas(self):
        """D-94 punto 15: un detalle con reservas en dos invernaderos cuenta en los dos filtros y una sola vez sin filtro."""
        sur = segundo_invernadero(self.e, "Invernadero Sur")
        lote_sur = lote_maduro(sur, 5000)
        self.con_faltante(lotes=[self.lote, lote_sur], cantidad=5)  # en los dos
        self.con_faltante(lotes=[self.lote])  # solo en el Norte
        self.assertEqual(self.stats().faltantes.con_faltante, 2)
        self.assertEqual(self.stats(invernadero=str(self.e.invernadero.pk)).faltantes.con_faltante, 2)
        self.assertEqual(self.stats(invernadero=str(sur.invernadero.pk)).faltantes.con_faltante, 1)

    def test_regla_7_respeta_el_alcance(self):
        """El Vendedor cuenta solo los detalles de sus ventas; el Gerente, todos y por Vendedor."""
        self.con_faltante()
        ajena = compra_venta(self.e, modalidad="retiro", vendedor=self.otro_vendedor)
        ajeno = detalle(ajena, self.e.variedad, 10, "100.00")
        reserva_lista(ajeno, self.lote, 10)
        DetalleVenta.objects.filter(pk=ajeno.pk).update(estado_detalle_venta="pendiente_decision", fecha_pendiente_decision=HOY)
        self.assertEqual(self.stats().faltantes.con_faltante, 1)
        self.assertEqual(self.stats(self.gerente).faltantes.con_faltante, 2)
        self.assertEqual(self.stats(self.gerente, vendedor=str(self.otro_vendedor.pk)).faltantes.con_faltante, 1)


class Regla8ClientesTests(BaseDeEstadisticas):
    def cliente_con_ventas(self, nombre, *montos):
        """Un cliente con una entrega de compra-venta por cada monto (una planta por $ 1)."""
        cliente_ = cliente(razon_social=nombre)
        for monto in montos:
            self.venta(cantidad=1, precio=monto, cliente_=cliente_)
        return cliente_

    def test_regla_8_los_diez_clientes_con_mas_ventas_con_entregas_y_porcentaje(self):
        """Regla 8: los diez con más ventas del período (mismo cálculo que el indicador 3), con la cantidad de entregas y el porcentaje sobre el total."""
        for i in range(1, 13):
            self.cliente_con_ventas(f"Cliente {i:02d}", f"{i * 100}.00")  # $ 100,00 … $ 1.200,00
        top = self.stats().clientes
        self.assertEqual(len(top), 10)
        self.assertEqual([c.nombre for c in top], [f"Cliente {i:02d}" for i in range(12, 2, -1)])
        total = sum(D(i * 100) for i in range(1, 13))  # $ 7.800,00
        self.assertEqual(self.stats().ventas.total, total)
        self.assertEqual((top[0].monto, top[0].entregas, top[0].porcentaje), (D("1200.00"), 1, D(1200) * 100 / total))

    def test_regla_8_cuenta_las_entregas_de_cada_cliente_y_suma_sus_montos(self):
        """Un cliente con dos entregas suma sus montos y cuenta dos entregas."""
        grande = self.cliente_con_ventas("Cliente Grande", "300.00", "200.00")
        self.cliente_con_ventas("Cliente Chico", "400.00")
        top = self.stats().clientes
        self.assertEqual([(c.nombre, c.entregas, c.monto) for c in top], [("Cliente Grande", 2, D("500.00")), ("Cliente Chico", 1, D("400.00"))])
        self.assertEqual(top[0].cliente_id, grande.pk)

    def test_regla_8_a_igualdad_de_monto_ordena_por_nombre(self):
        """Regla 8: monto descendente y, a igualdad, por nombre; el empate en el décimo lugar lo decide el nombre."""
        for nombre in ("Beta", "Alfa", "Delta", "Gamma"):
            self.cliente_con_ventas(nombre, "500.00")
        for i in range(8):
            self.cliente_con_ventas(f"Relleno {i}", "600.00")
        top = self.stats().clientes
        self.assertEqual([c.nombre for c in top][-2:], ["Alfa", "Beta"])  # Delta y Gamma quedan afuera
        self.assertEqual(len(top), 10)

    def test_regla_8_son_los_clientes_del_alcance_y_del_periodo(self):
        """Solo las ventas del alcance y concretadas en el período."""
        self.cliente_con_ventas("Propio", "100.00")
        self.venta(cantidad=1, precio="900.00", cliente_=self.otro_cliente, vendedor=self.otro_vendedor)  # de otro Vendedor
        self.venta(cantidad=1, precio="800.00", cliente_=cliente(razon_social="Viejo"), hace=HACE_UN_MES)
        self.assertEqual([c.nombre for c in self.stats().clientes], ["Propio"])
        self.assertEqual([c.nombre for c in self.stats(self.gerente).clientes], ["Otro Cliente S.A.", "Propio"])

    def test_regla_8_sin_ventas_no_hay_clientes(self):
        """Sin entregas en el período, la lista está vacía."""
        self.assertEqual(self.stats().clientes, ())


class Regla10EnlacesTests(BaseDeEstadisticas):
    def test_regla_10_cada_indicador_lleva_a_su_consulta_con_el_mismo_filtro(self):
        """Regla 10: ventas y clientes a las listas de contratos (compra-ventas y suministros); entregas a la lista con estado «concretada» y el invernadero; incumplimientos a las solicitudes aceptadas;
        cobranza a «Cobranza»; faltantes a las compra-ventas. El Gerente suma el Vendedor. Los destinos no admiten rango: no se lo pasan (se anota en el «Cierre»)."""
        sur = segundo_invernadero(self.e, "Invernadero Sur").invernadero
        contratos, entregas_, solicitudes, cobranza = (reverse(f"comercial:{n}") for n in ("contratos", "entregas", "solicitudes", "cobranza"))
        propio = self.stats(invernadero=str(sur.pk)).enlaces
        self.assertEqual(propio.compra_ventas, contratos)
        self.assertEqual(propio.suministros, f"{contratos}?tipo=suministro")
        self.assertEqual(propio.entregas, f"{entregas_}?estado=concretada&invernadero={sur.pk}")
        self.assertEqual(propio.solicitudes, f"{solicitudes}?estado=aceptada")
        self.assertEqual(propio.cobranza, cobranza)
        self.assertEqual(propio.faltantes, contratos)
        self.venta()  # el Gerente elige entre los Vendedores que tienen contratos
        vendedor = self.e.vendedor.pk
        del_gerente = self.stats(self.gerente, vendedor=str(vendedor)).enlaces
        self.assertEqual(del_gerente.compra_ventas, f"{contratos}?vendedor={vendedor}")
        self.assertEqual(del_gerente.suministros, f"{contratos}?tipo=suministro&vendedor={vendedor}")
        self.assertEqual(del_gerente.entregas, f"{entregas_}?estado=concretada")
        self.assertEqual(del_gerente.solicitudes, f"{solicitudes}?estado=aceptada&vendedor={vendedor}")
        self.assertEqual(del_gerente.faltantes, f"{contratos}?vendedor={vendedor}")

    def test_regla_10_cada_cliente_lleva_a_sus_contratos(self):
        """Indicador 8: la fila de cada cliente lleva a las listas de contratos con ese cliente (y el Vendedor, si el Gerente filtra)."""
        cliente_ = cliente(razon_social="Cliente Enlazado")
        self.venta(cantidad=1, precio="100.00", cliente_=cliente_)
        contratos = reverse("comercial:contratos")
        fila = self.stats().clientes[0]
        self.assertEqual(fila.url_compra_ventas, f"{contratos}?cliente={cliente_.pk}")
        self.assertEqual(fila.url_suministros, f"{contratos}?tipo=suministro&cliente={cliente_.pk}")
        con_vendedor = self.stats(self.gerente, vendedor=str(self.e.vendedor.pk)).clientes[0]
        self.assertEqual(con_vendedor.url_compra_ventas, f"{contratos}?cliente={cliente_.pk}&vendedor={self.e.vendedor.pk}")


class PostcondicionYRendimientoTests(BaseDeEstadisticas):
    def poblar(self, cantidad):
        """`cantidad` de cada cosa: ventas, suministros en mora con una solicitud aceptada y un intento fallido, y detalles con faltante, rechazados y cancelados."""
        for i in range(cantidad):
            self.venta(pactada=-1 if i % 2 else 1, cliente_=cliente(razon_social=f"Cliente {i}"))
            entrega_ = self.en_mora(i + 1)
            discrepancia_aceptada(entrega_, monto="100.00", descontado="100.00", con_alerta=False)
            self.intento(entrega_)
            self.con_faltante("rechazado" if i % 2 else "pendiente_decision")
            cancelada = compra_venta(self.e, modalidad="retiro", estado="cancelada")
            detalle(cancelada, self.e.variedad, 10, "100.00", estado="cancelado")
            CompraVenta.objects.filter(pk=cancelada.pk).update(motivo_cancelacion_venta="otro", fecha_cancelacion_venta=HOY)

    def consultas(self, funcion, *args):
        with CaptureQueriesContext(connection) as capturadas:
            funcion(*args)
        return len(capturadas)

    def indicadores(self):
        f = self.filtros(self.gerente)
        return {
            "ventas": (estadisticas._ventas, self.gerente, f),
            "puntualidad": (estadisticas._puntualidad, self.gerente, f),
            "incumplimientos": (estadisticas._incumplimientos, self.gerente, f),
            "cobranza": (estadisticas._cobranza, self.gerente, f, HOY),
            "faltantes": (estadisticas._faltantes, self.gerente, f),
            "clientes": (estadisticas._clientes, self.gerente, f),
        }

    def test_post_a_es_una_consulta_pura_no_escribe_ni_audita(self):
        """Postcondición a: ninguna escritura ni registro de auditoría. Todas las sentencias son `SELECT` y la cantidad de filas de auditoría, de solicitudes y de entregas no cambia."""
        self.poblar(2)
        antes = (RegistroAuditoria.objects.count(), SolicitudRevision.objects.count(), Entrega.objects.count(), DetalleVenta.objects.count())
        with CaptureQueriesContext(connection) as capturadas:
            estadisticas.estadisticas(self.gerente, self.filtros(self.gerente), HOY)
            estadisticas.estadisticas(self.e.vendedor, self.filtros(self.e.vendedor), HOY)
            estadisticas.resultados_del_mes(self.e.vendedor, HOY)
        escrituras = [q["sql"] for q in capturadas if not q["sql"].lstrip().upper().startswith(("SELECT", "WITH"))]
        self.assertEqual(escrituras, [])
        despues = (RegistroAuditoria.objects.count(), SolicitudRevision.objects.count(), Entrega.objects.count(), DetalleVenta.objects.count())
        self.assertEqual(antes, despues)

    def test_rendimiento_cada_indicador_hace_las_mismas_consultas_con_2_y_con_20_entregas(self):
        """Requisito de rendimiento: una consulta agregada por indicador, sin consultas por fila; la cantidad de consultas no depende de cuántas entregas haya."""
        self.poblar(2)
        con_2 = {nombre: self.consultas(*args) for nombre, args in self.indicadores().items()}
        total_con_2 = self.consultas(estadisticas.estadisticas, self.gerente, self.filtros(self.gerente), HOY)
        self.poblar(18)
        con_20 = {nombre: self.consultas(*args) for nombre, args in self.indicadores().items()}
        total_con_20 = self.consultas(estadisticas.estadisticas, self.gerente, self.filtros(self.gerente), HOY)
        self.assertEqual(con_2, con_20)
        self.assertEqual(total_con_2, total_con_20)
        for nombre, cantidad in con_2.items():
            self.assertLessEqual(cantidad, 4, nombre)  # el indicador 7 son cuatro consultas; los demás, menos
        self.assertGreaterEqual(self.stats(self.gerente).ventas.entregas, 20)  # y las entregas están contadas


class ResultadosDelMesTests(BaseDeEstadisticas):
    def test_regla_3_a_5_resultados_del_mes_son_los_del_mes_en_curso_del_vendedor(self):
        """«Resultados del mes en curso»: ventas, entregas a tiempo e indemnizado del 1 a hoy, solo de los contratos del Vendedor, con el mismo cálculo que `estadisticas`."""
        self.venta(cantidad=10, precio="100.00", pactada=1)  # a tiempo
        self.venta(cantidad=20, precio="100.00", pactada=-2)  # con retraso
        self.venta(cantidad=40, precio="100.00", hace=HACE_UN_MES)  # el mes anterior: no cuenta
        self.del_otro_vendedor()  # ajena
        discrepancia_aceptada(self.suministro(), monto="250.00", descontado="250.00", con_alerta=False)
        r = estadisticas.resultados_del_mes(self.e.vendedor, HOY)
        self.assertEqual((r.desde, r.hasta), (HOY.replace(day=1), HOY))
        self.assertEqual(r.ventas.total, D("4000.00"))  # 1.000 + 2.000 + el suministro de 1.000
        self.assertEqual((r.puntualidad.total, r.puntualidad.a_tiempo, r.puntualidad.con_retraso), (3, 2, 1))
        self.assertEqual(r.incumplimientos.total, D("250.00"))
        completo = self.stats(self.e.vendedor)
        self.assertEqual((r.ventas, r.puntualidad, r.incumplimientos), (completo.ventas, completo.puntualidad, completo.incumplimientos))

    def test_regla_3_a_5_el_mes_lo_define_el_parametro_hoy(self):
        """`hoy` es un parámetro: el mes en curso es el de `hoy`, no el del reloj."""
        self.venta(hace=HACE_UN_MES)
        r = estadisticas.resultados_del_mes(self.e.vendedor, ULTIMO_DEL_MES_ANTERIOR)
        self.assertEqual((r.desde, r.hasta), (ULTIMO_DEL_MES_ANTERIOR.replace(day=1), ULTIMO_DEL_MES_ANTERIOR))
        self.assertEqual(r.ventas.entregas, 1)


class FuncionesPublicasRendimientoTests(BaseDeEstadisticas):
    """Lo mismo para las tres funciones públicas (las que llama EST-03 y la pantalla), no solo para cada indicador."""

    poblar = PostcondicionYRendimientoTests.poblar  # los mismos datos, sin heredar (y repetir) las pruebas de la otra clase
    consultas = PostcondicionYRendimientoTests.consultas

    def publicas(self):
        return {
            "filtros_gerente": (estadisticas.filtros_de_estadisticas, self.gerente, {}, HOY),
            "filtros_vendedor": (estadisticas.filtros_de_estadisticas, self.e.vendedor, {}, HOY),
            "estadisticas_gerente": (estadisticas.estadisticas, self.gerente, FiltrosDeEstadisticas(HOY.replace(day=1), HOY), HOY),
            "estadisticas_vendedor": (estadisticas.estadisticas, self.e.vendedor, FiltrosDeEstadisticas(HOY.replace(day=1), HOY), HOY),
            "resultados_del_mes": (estadisticas.resultados_del_mes, self.e.vendedor, HOY),
        }

    def test_rendimiento_las_funciones_publicas_hacen_las_mismas_consultas_con_2_y_con_20_entregas(self):
        """Cada función pública hace las mismas consultas con 2 que con 20 entregas (y con más Vendedores): sin consultas por fila."""
        self.poblar(2)
        con_2 = {nombre: self.consultas(*args) for nombre, args in self.publicas().items()}
        self.poblar(18)
        for i in range(5):
            crear_vendedor(email=f"mas.vendedores{i}@infoponia.com")
            self.del_otro_vendedor()
        con_20 = {nombre: self.consultas(*args) for nombre, args in self.publicas().items()}
        self.assertEqual(con_2, con_20)
        self.assertLessEqual(con_2["estadisticas_gerente"], 20)
        self.assertLessEqual(con_2["resultados_del_mes"], 8)
        self.assertLessEqual(con_2["filtros_gerente"], 4)

    def test_regla_2_la_convencion_de_dias_es_la_de_las_otras_pantallas_de_estadisticas(self):
        """Días inclusivos, `hasta <= hoy`, `desde <= hasta` y 366 días como máximo: la convención de EST-01 y EST-02 (D-93 punto 2). La comparación con `estadisticas.periodos.validar` está en
        `estadisticas/tests/test_convencion_de_periodo.py` (`comercial` no puede importar de `estadisticas`, A1 de D-37; ni siquiera sus pruebas)."""
        dia = date(2026, 11, 26)
        casos = (
            (dia, dia, True), (dia - timedelta(days=1), dia, True), (dia - timedelta(days=364), dia, True), (dia - timedelta(days=365), dia, True),
            (dia - timedelta(days=366), dia, False), (dia - timedelta(days=400), dia, False), (dia, dia - UN_DIA, False), (dia, dia + UN_DIA, False), (dia - UN_DIA, dia + UN_DIA, False),
        )
        for desde, hasta, valido in casos:
            try:
                self.filtros(self.gerente, hoy=dia, periodo="rango", desde=desde.isoformat(), hasta=hasta.isoformat())
                obtenido = True
            except ValidationError:
                obtenido = False
            self.assertEqual(obtenido, valido, (desde, hasta))
