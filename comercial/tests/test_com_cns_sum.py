# Pruebas de COM-CNS-SUM, Consultar Suministro (COM-03a, paso 5; docs/casos_de_uso/comercial/suministro.md): `buscar_suministros`,
# `ficha_de_suministro` y `calendario_completo`. Una prueba por regla (numeración del caso de uso). Lo que se completa después (la
# rescisión en la ficha, «Ver historial de cambios», los botones de la regla 10, entregas, solicitudes y cobro) no se prueba acá (D-25).
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar):
#   - `FiltrosDeSuministros(cliente_id, cliente_texto, estado, fecha_de, desde, hasta, vendedor_id)` con `desde_get` (claves `cliente`,
#     `cliente_q`, `estado`, `fecha_de` («realizacion» o «fin»), `desde`, `hasta`, `vendedor`).
#   - `buscar_suministros(actor, filtros, pagina=1)` -> `Page` de `Suministro` con `detalles_vigentes` (int) y las propiedades de modelo
#     `al_limite` y `tiene_rescision_acordada`.
#   - `ficha_de_suministro(actor, id)` -> `FichaDeSuministro(suministro, clausula, detalles, calendario, desde, hasta, hay_mas_calendario,
#     ventana, aviso_de_limite, acciones)`; `detalles` son `FilaDeDetalle(detalle, historial, precio_hoy, con_cambios_desde)` y `calendario`
#     son `FilaDeCalendario(fecha, detalle, variedad, cantidad, precio, situacion, texto, faltan, condiciones_anteriores)`.
#   - `calendario_completo(actor, id, pagina=1)` -> `Page` de `FilaDeCalendario` (de a 100).
#   - Situaciones: `fuera_de_la_ventana`, `reservado`, `sin_cobertura`, `pasado`.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from comercial.models import Suministro
from comercial.servicios import calendario, suministros
from comercial.servicios.suministros import FiltrosDeSuministros
from comercial.tests.fabricas import (
    cliente as crear_cliente,
    compra_venta,
    detalle_suministro,
    direccion_de_cliente,
    escenario_comercial,
    reserva_de_periodo,
    suministro,
    verificar_invariantes_de_reservas,
)
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def dias(n):
    """La fecha de dentro de ``n`` días (``n`` negativo: de hace ``-n``)."""
    return HOY + timedelta(days=n)


class BaseDeConsulta(ConDatosDeInventario, TestCase):
    """Dos Vendedores con sus invernaderos, un Gerente y un suministro del primero con un detalle."""

    def setUp(self):
        self.e = escenario_comercial()
        self.otro = escenario_comercial(sufijo="2")
        self.gerente = crear_gerente()
        self.addCleanup(verificar_invariantes_de_reservas)

    def contrato(self, escenario=None, primera=3, **extra):
        """Un suministro con un detalle de 30 plantas cada 7 días (por defecto, para el Vendedor del escenario principal)."""
        e = escenario or self.e
        s = suministro(e, **extra)
        detalle_suministro(s, e.variedad, cantidad=30, periodo=7, primera_en_dias=primera)
        return s

    def buscar(self, actor=None, pagina=1, **filtros):
        return suministros.buscar_suministros(actor or self.gerente, FiltrosDeSuministros(**filtros), pagina)

    def codigos(self, pagina):
        return [s.pk for s in pagina.object_list]


class AlcanceYFiltrosTests(BaseDeConsulta):
    """Reglas 1 y 2."""

    def test_regla_1_el_vendedor_ve_solo_sus_suministros_y_el_gerente_todos(self):
        """Regla 1: alcance con `en_alcance_de` (D-28): el Vendedor, los suyos; el Gerente, todos."""
        mio, ajeno = self.contrato(), self.contrato(self.otro)
        self.assertEqual(set(self.codigos(self.buscar(self.e.vendedor))), {mio.pk})
        self.assertEqual(set(self.codigos(self.buscar(self.gerente))), {mio.pk, ajeno.pk})

    def test_regla_1_los_demas_roles_y_las_cuentas_inactivas_no_consultan(self):
        """Regla 1 y precondición a: otro rol, un Vendedor inactivo o ninguna cuenta: `PermissionDenied` (403 con mensaje)."""
        self.contrato()
        for actor in (self.e.agronomo, self.e.capataz, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                suministros.buscar_suministros(actor, FiltrosDeSuministros())
        type(self.e.vendedor).objects.filter(pk=self.e.vendedor.pk).update(is_active=False)
        self.e.vendedor.refresh_from_db()
        with self.assertRaises(PermissionDenied):
            suministros.buscar_suministros(self.e.vendedor, FiltrosDeSuministros())

    def test_regla_2_filtra_por_cliente_por_id_y_por_texto(self):
        """Regla 2: cliente, por id o por texto (nombre, razón social o CUIT, desde 2 caracteres)."""
        a = self.contrato()
        otro_cliente = crear_cliente(razon_social="Verdulería El Sol S.A.", email="sol@ejemplo.com")
        direccion_de_cliente(otro_cliente)
        b = suministro(self.e, cliente_=otro_cliente)
        self.assertEqual(self.codigos(self.buscar(cliente_id=str(otro_cliente.pk))), [b.pk])
        self.assertEqual(self.codigos(self.buscar(cliente_texto="Sol")), [b.pk])
        self.assertEqual(self.codigos(self.buscar(cliente_texto="Pinos")), [a.pk])
        self.assertEqual(set(self.codigos(self.buscar(cliente_texto="S"))), {a.pk, b.pk})  # menos de 2 caracteres: no filtra

    def test_regla_2_filtra_por_estado(self):
        """Regla 2: estado vigente, finalizado, resuelto o rescindido; uno inexistente no filtra."""
        vigente, finalizado = self.contrato(), self.contrato(estado="finalizado")
        resuelto = self.contrato()
        Suministro.objects.filter(pk=resuelto.pk).update(estado_suministro="resuelto", fecha_resolucion_suministro=HOY)
        rescindido = self.contrato()
        Suministro.objects.filter(pk=rescindido.pk).update(
            estado_suministro="rescindido", fecha_rescision=HOY, motivo_rescision="otro", fecha_acuerdo_rescision=HOY,
            fecha_registro_rescision=HOY, fecha_ultima_entrega_rescision=HOY,
        )
        esperado = {"vigente": vigente, "finalizado": finalizado, "resuelto": resuelto, "rescindido": rescindido}
        for estado, contrato in esperado.items():
            with self.subTest(estado=estado):
                self.assertEqual(self.codigos(self.buscar(estado=estado)), [contrato.pk])
        self.assertEqual(len(self.codigos(self.buscar(estado="inexistente"))), 4)

    def test_regla_2_filtra_por_rango_de_fechas_de_realizacion_o_de_fin(self):
        """Regla 2: rango de fechas «de realización» o «de fin»; los dos extremos incluidos."""
        viejo = self.contrato(fecha_realizacion=dias(-100), duracion=2)  # fin dentro de -40 días
        nuevo = self.contrato(fecha_realizacion=dias(-5), duracion=12)
        self.assertEqual(self.codigos(self.buscar(fecha_de="realizacion", desde=str(dias(-10)))), [nuevo.pk])
        self.assertEqual(self.codigos(self.buscar(fecha_de="realizacion", hasta=str(dias(-100)))), [viejo.pk])
        self.assertEqual(self.codigos(self.buscar(fecha_de="fin", hasta=str(dias(0)))), [viejo.pk])
        self.assertEqual(self.codigos(self.buscar(fecha_de="fin", desde=str(dias(0)))), [nuevo.pk])
        self.assertEqual(set(self.codigos(self.buscar(desde=str(dias(-100)), hasta=str(dias(0))))), {viejo.pk, nuevo.pk})

    def test_regla_2_el_vendedor_solo_lo_filtra_el_gerente(self):
        """Regla 2: «solo para el Gerente, Vendedor»: el Gerente filtra; si un Vendedor lo manda, se ignora (ve solo lo suyo)."""
        mio, ajeno = self.contrato(), self.contrato(self.otro)
        self.assertEqual(self.codigos(self.buscar(vendedor_id=str(self.otro.vendedor.pk))), [ajeno.pk])
        self.assertEqual(self.codigos(self.buscar(self.e.vendedor, vendedor_id=str(self.otro.vendedor.pk))), [mio.pk])

    def test_regla_2_los_filtros_salen_de_la_url(self):
        """Los filtros van en la URL (se pueden compartir y volver con «Atrás»): `desde_get` los arma de un `QueryDict`."""
        filtros = FiltrosDeSuministros.desde_get(
            {"cliente": "3", "cliente_q": "pinos", "estado": "vigente", "fecha_de": "fin", "desde": "2026-01-01", "hasta": "2026-12-31", "vendedor": "7"}
        )
        self.assertEqual(
            (filtros.cliente_id, filtros.cliente_texto, filtros.estado, filtros.fecha_de, filtros.desde, filtros.hasta, filtros.vendedor_id),
            ("3", "pinos", "vigente", "fin", "2026-01-01", "2026-12-31", "7"),
        )
        self.assertEqual(FiltrosDeSuministros.desde_get({}).fecha_de, "realizacion")


class ListadoTests(BaseDeConsulta):
    """Regla 3 y regla 9 (la marca «Al límite»)."""

    def test_regla_3_ordena_por_fecha_de_realizacion_y_numero_descendentes(self):
        """Regla 3 (prototipo): orden de fecha de realización descendente y, a igual fecha, número descendente."""
        viejo = self.contrato(fecha_realizacion=dias(-30))
        primero, segundo = self.contrato(), self.contrato()
        self.assertEqual(self.codigos(self.buscar()), [segundo.pk, primero.pk, viejo.pk])

    def test_regla_3_cada_fila_trae_los_detalles_vigentes_y_los_incumplimientos_frente_a_los_tolerados(self):
        """Regla 3: cantidad de detalles vigentes (los finalizados no cuentan), incumplimientos acumulados frente a tolerados y estado."""
        s = self.contrato(tolerados=5, incumplimientos=2)
        detalle_suministro(s, self.e.variedad, direccion=direccion_de_cliente(self.e.cliente).direccion, estado="finalizado", fecha_fin_detalle=HOY)
        detalle_suministro(s, self.e.variedad, direccion=direccion_de_cliente(self.e.cliente).direccion)
        (fila,) = self.buscar().object_list
        self.assertEqual((fila.detalles_vigentes, fila.cantidad_incumplimientos, fila.incumplimientos_tolerados, fila.estado_suministro), (2, 2, 5, "vigente"))

    def test_regla_9_la_marca_al_limite_cuando_queda_un_tolerado_o_ya_se_usaron_todos(self):
        """Regla 9 (aprobada por el estudiante): «Al límite» si el contrato vigente tiene incumplimientos ≥ tolerados − 1 (le queda uno, o ya
        usó todos); no con más margen, ni con un contrato que ya no está vigente."""
        casos = [(5, 0, False), (5, 3, False), (5, 4, True), (5, 5, True), (0, 0, True), (1, 0, True), (2, 0, False)]
        for tolerados, incumplimientos, esperado in casos:
            with self.subTest(tolerados=tolerados, incumplimientos=incumplimientos):
                s = Suministro(estado_suministro="vigente", incumplimientos_tolerados=tolerados, cantidad_incumplimientos=incumplimientos)
                self.assertEqual(s.al_limite, esperado)
        finalizado = Suministro(estado_suministro="finalizado", incumplimientos_tolerados=1, cantidad_incumplimientos=1)
        self.assertFalse(finalizado.al_limite)

    def test_regla_3_el_listado_se_pagina_de_a_50(self):
        """Regla 3: páginas de 50 (acá, con el tamaño reducido a 2)."""
        for _ in range(3):
            self.contrato()
        with mock.patch.object(suministros, "POR_PAGINA", 2):
            primera, segunda = self.buscar(pagina=1), self.buscar(pagina=2)
        self.assertEqual((len(primera.object_list), len(segunda.object_list), primera.paginator.num_pages), (2, 1, 2))
        self.assertEqual(suministros.POR_PAGINA, 50)

    def test_regla_3_sin_consultas_por_fila(self):
        """«Sin consultas por fila»: la misma cantidad de consultas con un suministro y con cuatro."""
        self.contrato()
        with CaptureQueriesContext(connection) as con_uno:
            list(self.buscar().object_list)
        for _ in range(3):
            self.contrato()
        with CaptureQueriesContext(connection) as con_cuatro:
            filas = list(self.buscar().object_list)
            [(f.cliente.pk, f.vendedor.pk, f.detalles_vigentes, f.al_limite) for f in filas]
        self.assertEqual(len(con_uno), len(con_cuatro))

    def test_regla_la_marca_de_rescision_acordada_la_da_el_modelo(self):
        """«Rescisión acordada» (la escribe COM-03b): un vigente con motivo de rescisión; no si ya está rescindido ni sin motivo."""
        s = self.contrato()
        self.assertFalse(Suministro.objects.get(pk=s.pk).tiene_rescision_acordada)
        Suministro.objects.filter(pk=s.pk).update(
            motivo_rescision="otro", fecha_acuerdo_rescision=HOY, fecha_registro_rescision=HOY, fecha_ultima_entrega_rescision=dias(14)
        )
        self.assertTrue(self.buscar().object_list[0].tiene_rescision_acordada)


class FichaTests(BaseDeConsulta):
    """Reglas 1, 4, 5, 9 y 10."""

    def ficha(self, s, actor=None):
        return suministros.ficha_de_suministro(actor or self.gerente, s.pk)

    def test_regla_1_la_ficha_fuera_del_alcance_es_403_y_un_id_que_no_existe_es_404(self):
        """Regla 1 y SEG-13: la ficha de un suministro de otro Vendedor, `PermissionDenied`; un id inexistente (o de una compra-venta), 404."""
        ajeno = self.contrato(self.otro)
        with self.assertRaises(PermissionDenied):
            self.ficha(ajeno, self.e.vendedor)
        with self.assertRaises(PermissionDenied):
            self.ficha(ajeno, self.e.agronomo)
        with self.assertRaises(Http404):
            suministros.ficha_de_suministro(self.gerente, 999999)
        with self.assertRaises(Http404):
            suministros.ficha_de_suministro(self.gerente, compra_venta(self.e).pk)
        self.assertEqual(self.ficha(ajeno).suministro.pk, ajeno.pk)

    def test_regla_4_la_ficha_trae_los_datos_del_contrato_y_su_clausula_del_suministrado(self):
        """Regla 4: duración y vigencia, tolerados y acumulados, multa, cláusula del suministrado y estado del comprobante."""
        s = self.contrato(duracion=6, tolerados=3, incumplimientos=1, multa="1234.50", plazo_pago=20, indemnizacion_pago="55.00")
        ficha = self.ficha(s)
        self.assertEqual(
            (ficha.suministro.duracion_meses, ficha.suministro.fecha_fin, ficha.suministro.incumplimientos_tolerados,
             ficha.suministro.cantidad_incumplimientos, ficha.suministro.multa_resolucion, ficha.suministro.estado_comprobante),
            (6, calendario.sumar_meses(HOY, 6), 3, 1, Decimal("1234.50"), "pendiente_envio"),
        )
        self.assertEqual((ficha.clausula.plazo_pago_dias, ficha.clausula.indemnizacion_retraso_pago), (20, Decimal("55.00")))

    def test_regla_4_un_contrato_resuelto_muestra_su_fecha_de_resolucion(self):
        """Regla 4 y MD-120: «si se resolvió, la fecha de resolución»."""
        s = self.contrato()
        Suministro.objects.filter(pk=s.pk).update(estado_suministro="resuelto", fecha_resolucion_suministro=dias(-2))
        self.assertEqual(self.ficha(s).suministro.fecha_resolucion_suministro, dias(-2))

    def test_regla_5_cada_detalle_va_en_una_linea_con_su_precio_vigente_hoy_y_su_clausula(self):
        """Regla 5: variedad, dirección, cantidad por período, período, precio (con el vigente hoy si es de ajuste periódico), cláusula del
        suministrante y estado."""
        s = suministro(self.e, duracion=12, fecha_realizacion=dias(-70))  # 2 meses y pico atrás
        d = detalle_suministro(
            s, self.e.variedad, mecanismo="ajuste_periodico", porcentaje="10.00", meses=2, precio="1000.00", minima=7, plazo_entrega=2,
            fecha_base_ajuste=dias(-70),
        )
        (fila,) = self.ficha(s).detalles
        self.assertEqual(fila.detalle.pk, d.pk)
        self.assertEqual(fila.precio_hoy, calendario.precio_en(d, HOY))
        self.assertEqual(fila.precio_hoy, Decimal("1100.00"))  # dos meses cumplidos: un ajuste del 10 %
        self.assertEqual((fila.detalle.clausula_suministrante.cantidad_minima, fila.detalle.clausula_suministrante.plazo_entrega_dias), (7, 2))
        self.assertEqual((fila.historial, fila.con_cambios_desde), ([], None))

    def test_regla_5_un_detalle_con_sucesores_se_muestra_como_una_sola_linea_con_su_historial(self):
        """Regla 5 y MD-131: una línea por cadena «reemplaza a» (la última versión), con «Con cambios desde el dd/mm» y las versiones anteriores
        en orden (qué condiciones rigieron hasta qué fecha)."""
        s = suministro(self.e, duracion=12)
        v1 = detalle_suministro(s, self.e.variedad, estado="finalizado", fecha_fin_detalle=dias(10), precio="100.00", primera_en_dias=-10)
        v2 = detalle_suministro(s, self.e.variedad, estado="finalizado", fecha_fin_detalle=dias(30), precio="120.00", primera_en_dias=11, reemplaza_a=v1)
        v3 = detalle_suministro(s, self.e.variedad, precio="150.00", primera_en_dias=31, reemplaza_a=v2)
        otro = detalle_suministro(s, self.e.variedad, direccion=direccion_de_cliente(self.e.cliente).direccion, precio="999.00")
        filas = self.ficha(s).detalles
        self.assertEqual(sorted(f.detalle.pk for f in filas), sorted([v3.pk, otro.pk]))
        cadena = next(f for f in filas if f.detalle.pk == v3.pk)
        self.assertEqual([d.pk for d in cadena.historial], [v1.pk, v2.pk])
        self.assertEqual(cadena.con_cambios_desde, v3.fecha_primer_entrega)
        self.assertIsNone(next(f for f in filas if f.detalle.pk == otro.pk).con_cambios_desde)

    def test_regla_9_el_aviso_de_limite_de_la_ficha(self):
        """Regla 9 (textos del prototipo): con un tolerado restante, «Al contrato le queda un incumplimiento tolerado.»; con todos usados, «El
        contrato ya usó sus N incumplimientos tolerados: el próximo lo resuelve y se aplica la multa.»; con 0 tolerados, que el primero lo
        resuelve; con margen o sin estar vigente, nada."""
        casos = {
            (5, 4, "vigente"): "Al contrato le queda un incumplimiento tolerado.",
            (5, 5, "vigente"): "El contrato ya usó sus 5 incumplimientos tolerados: el próximo lo resuelve y se aplica la multa.",
            (0, 0, "vigente"): "El contrato no tolera incumplimientos: el primero lo resuelve y se aplica la multa.",
            (5, 2, "vigente"): None,
            (5, 5, "finalizado"): None,
        }
        for (tolerados, incumplimientos, estado), esperado in casos.items():
            with self.subTest(tolerados=tolerados, incumplimientos=incumplimientos, estado=estado):
                s = self.contrato(tolerados=tolerados, incumplimientos=incumplimientos, estado=estado)
                self.assertEqual(self.ficha(s).aviso_de_limite, esperado)

    def test_regla_10_las_acciones_de_la_ficha_son_solo_las_que_existen_en_com_03a(self):
        """Regla 10 y D-25: «Ver cliente» siempre; «Reenviar comprobante» si está pendiente de envío y el cliente tiene correo; todavía no
        «Modificar», «Rescindir», «Dejar sin efecto la rescisión», «Registrar cobro» ni «Ver historial» (los suman COM-03b, COM-07 y COM-08)."""
        s = self.contrato(comprobante="pendiente_envio")
        self.assertEqual(self.ficha(s).acciones, frozenset({"ver_cliente", "reenviar_comprobante"}))
        enviado = self.contrato(comprobante="enviado")
        self.assertEqual(self.ficha(enviado).acciones, frozenset({"ver_cliente"}))
        para_imprimir = self.contrato(comprobante="para_imprimir")
        self.assertEqual(self.ficha(para_imprimir).acciones, frozenset({"ver_cliente"}))
        for prohibida in ("modificar", "rescindir", "dejar_sin_efecto", "registrar_cobro", "ver_historial"):
            self.assertNotIn(prohibida, self.ficha(s).acciones)


class CalendarioDeLaFichaTests(BaseDeConsulta):
    """Regla 6: el calendario de la ficha y la situación de cada período."""

    def setUp(self):
        super().setUp()
        self.lote = lote_maduro(self.e, 200)

    def contrato_en_curso(self, **extra):
        """Un contrato realizado hace 20 días, con un detalle de 30 cada 7 días que empezó hace 15: períodos en -15, -8, -1, 6, 13, 20…"""
        s = suministro(self.e, duracion=6, fecha_realizacion=dias(-20))
        d = detalle_suministro(s, self.e.variedad, cantidad=30, periodo=7, primera_en_dias=-15, **extra)
        return s, d

    def fila(self, s, fecha):
        return next(f for f in suministros.ficha_de_suministro(self.gerente, s.pk).calendario if f.fecha == fecha)

    def test_regla_6_la_situacion_de_cada_periodo(self):
        """Regla 6: «Pasado» (todavía no hay entregas), «Reservado» (sin cantidad sin cubrir), «Sin cobertura completa · faltan N» (con
        cantidad sin cubrir dentro de la ventana) y «Fuera de la ventana»."""
        s, d = self.contrato_en_curso()
        reserva_de_periodo(d, dias(6), [(self.lote, 30)])
        reserva_de_periodo(d, dias(13), [(self.lote, 10)])
        self.assertEqual((self.fila(s, dias(-1)).situacion, self.fila(s, dias(-1)).texto), ("pasado", "Pasado"))
        self.assertEqual((self.fila(s, dias(6)).situacion, self.fila(s, dias(6)).texto), ("reservado", "Reservado"))
        parcial = self.fila(s, dias(13))
        self.assertEqual((parcial.situacion, parcial.faltan, parcial.texto), ("sin_cobertura", 20, "Sin cobertura completa · faltan 20"))
        fuera = self.fila(s, dias(20))
        self.assertEqual((fuera.situacion, fuera.texto), ("fuera_de_la_ventana", "Fuera de la ventana"))

    def test_regla_6_un_periodo_de_la_ventana_sin_ninguna_reserva_no_tiene_cobertura(self):
        """Regla 6: dentro de la ventana y sin reservas, faltan todas las plantas del período."""
        s, _ = self.contrato_en_curso()
        fila = self.fila(s, dias(6))
        self.assertEqual((fila.situacion, fila.faltan, fila.texto), ("sin_cobertura", 30, "Sin cobertura completa · faltan 30"))

    def test_regla_6_el_ultimo_dia_de_la_ventana_todavia_esta_dentro(self):
        """Regla «Ventana de pre-reserva»: un período en `hoy + días de pre-reserva` está dentro de la ventana."""
        s = suministro(self.e, duracion=6)
        detalle_suministro(s, self.e.variedad, cantidad=30, periodo=7, primera_en_dias=(calendario.ventana(HOY) - HOY).days)
        self.assertEqual(self.fila(s, calendario.ventana(HOY)).situacion, "sin_cobertura")
        self.assertEqual(self.fila(s, calendario.ventana(HOY) + timedelta(days=7)).situacion, "fuera_de_la_ventana")

    def test_regla_6_por_defecto_muestra_30_dias_hacia_atras_y_hasta_28_despues_del_fin_de_la_ventana(self):
        """Regla 6: por defecto, los períodos de los últimos 30 días hasta 28 días después del fin de la ventana; `hay_mas_calendario` avisa
        que hay más («Ver todo el calendario»)."""
        s = suministro(self.e, duracion=12, fecha_realizacion=dias(-60))
        detalle_suministro(s, self.e.variedad, cantidad=30, periodo=7, primera_en_dias=-50)
        ficha = suministros.ficha_de_suministro(self.gerente, s.pk)
        self.assertEqual((ficha.desde, ficha.hasta), (dias(-30), calendario.ventana(HOY) + timedelta(days=28)))
        fechas = [f.fecha for f in ficha.calendario]
        self.assertTrue(all(ficha.desde <= f <= ficha.hasta for f in fechas))
        self.assertEqual(fechas[0], min(f for f in fechas))
        self.assertEqual(fechas, sorted(fechas))
        self.assertTrue(ficha.hay_mas_calendario)
        corto = self.contrato(duracion=1)
        self.assertFalse(suministros.ficha_de_suministro(self.gerente, corto.pk).hay_mas_calendario)

    def test_regla_6_cada_fila_trae_la_variedad_la_cantidad_y_el_precio_de_ese_periodo(self):
        """Regla 6 y prototipo: fecha, variedad, plantas y el precio de esa fecha (con ajuste periódico, el que rige ese día)."""
        s = suministro(self.e, duracion=12, fecha_realizacion=dias(-70))
        d = detalle_suministro(
            s, self.e.variedad, cantidad=30, periodo=30, primera_en_dias=-65, mecanismo="ajuste_periodico", porcentaje="10.00", meses=1,
            precio="1000.00", fecha_base_ajuste=dias(-70),
        )
        filas = suministros.ficha_de_suministro(self.gerente, s.pk).calendario
        for f in filas:
            self.assertEqual((f.variedad, f.cantidad, f.precio), (self.e.variedad, 30, calendario.precio_en(d, f.fecha)))
        self.assertGreater(filas[-1].precio, filas[0].precio)

    def test_regla_6_los_periodos_de_condiciones_anteriores_se_marcan(self):
        """MD-131: los períodos de un detalle ya reemplazado (finalizado con sucesor) siguen en el calendario, marcados «condiciones anteriores»."""
        s = suministro(self.e, duracion=6, fecha_realizacion=dias(-20))
        v1 = detalle_suministro(s, self.e.variedad, estado="finalizado", fecha_fin_detalle=dias(-1), primera_en_dias=-15)
        detalle_suministro(s, self.e.variedad, primera_en_dias=6, reemplaza_a=v1)
        ficha = suministros.ficha_de_suministro(self.gerente, s.pk)
        self.assertTrue(all(f.condiciones_anteriores for f in ficha.calendario if f.detalle.pk == v1.pk))
        self.assertTrue(any(not f.condiciones_anteriores for f in ficha.calendario))
        self.assertTrue(all(f.fecha <= dias(-1) for f in ficha.calendario if f.detalle.pk == v1.pk))

    def test_regla_6_el_calendario_completo_se_pagina_de_a_100(self):
        """Regla 6: «Ver todo el calendario» muestra todos los períodos, de a 100."""
        s = suministro(self.e, duracion=12)
        detalle_suministro(s, self.e.variedad, cantidad=1, periodo=1, primera_en_dias=0)
        pagina_1 = suministros.calendario_completo(self.gerente, s.pk, 1)
        pagina_4 = suministros.calendario_completo(self.gerente, s.pk, 4)
        total = len(calendario.calendario(s.detalles.get()))
        self.assertEqual((len(pagina_1.object_list), pagina_1.paginator.count), (100, total))
        self.assertEqual(len(pagina_4.object_list), total - 300)
        self.assertEqual([f.fecha for f in pagina_1.object_list], sorted(f.fecha for f in pagina_1.object_list))

    def test_regla_6_el_calendario_completo_respeta_el_alcance(self):
        """Regla 1: fuera del alcance, 403; un id inexistente, 404."""
        ajeno = self.contrato(self.otro)
        with self.assertRaises(PermissionDenied):
            suministros.calendario_completo(self.e.vendedor, ajeno.pk, 1)
        with self.assertRaises(Http404):
            suministros.calendario_completo(self.gerente, 999999, 1)

    def test_regla_6_sin_consultas_por_periodo(self):
        """La ficha hace las mismas consultas con 2 que con 8 períodos en pantalla."""
        corto = suministro(self.e, duracion=1)
        detalle_suministro(corto, self.e.variedad, cantidad=1, periodo=14, primera_en_dias=0)
        largo = suministro(self.e, duracion=1)
        detalle_suministro(largo, self.e.variedad, cantidad=1, periodo=3, primera_en_dias=0)
        suministros.ficha_de_suministro(self.gerente, corto.pk)  # calienta cachés
        with CaptureQueriesContext(connection) as con_pocos:
            suministros.ficha_de_suministro(self.gerente, corto.pk)
        with CaptureQueriesContext(connection) as con_muchos:
            suministros.ficha_de_suministro(self.gerente, largo.pk)
        self.assertEqual(len(con_pocos), len(con_muchos))
