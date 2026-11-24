# Pruebas de los cálculos de una entrega (COM-05a1, paso 2; `comercial/servicios/entregas.py`): cantidad planificada, peso, «en curso» y «atrasada», los candidatos con su
# motivo (uno por prueba y en su orden), `seleccionar` y `motivo_de_alerta` (de tabla, funciones puras) y el agrupamiento (una condición por prueba). Sin consultas por fila.
# Fuente: docs/casos_de_uso/comercial/entregas.md («Candidatos, verificaciones y selección», «Agrupamiento»), docs/modelo/comercial.md («Lo que se calcula») y D-66 puntos 4 y 7.

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from comercial.servicios import entregas
from comercial.servicios.entregas import Candidato
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    direccion_de_cliente,
    entrega,
    escenario_comercial,
    partida_cosechada,
    reserva,
    reserva_lista,
    transportista_con_vehiculo,
)
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import ConfiguracionOperativa, Localidad, Variedad
from maestros.tests.fabricas import localidad
from produccion.models import ReservaInsumo
from produccion.tests.fabricas import lote_maduro, reservar

HOY = timezone.localdate()
M = entregas


def candidato(pk, entregas_del_dia=0, capacidad_libre="100", motivo=None):
    """Un `Candidato` mínimo para las pruebas de tabla de las funciones puras."""
    return Candidato(SimpleNamespace(pk=pk), None, entregas_del_dia, Decimal("0"), frozenset(), Decimal(capacidad_libre), motivo)


class SeleccionarTests(TestCase):
    def test_regla_seleccion_gana_el_que_menos_entregas_tiene(self):
        """Regla «Selección del transportista» (paso 7): el que menos entregas tiene asignadas en la fecha."""
        elegido = entregas.seleccionar([candidato(1, 3), candidato(2, 1), candidato(3, 2)])
        self.assertEqual(elegido.transportista.pk, 2)

    def test_ext_7a_con_el_mismo_numero_de_entregas_gana_la_mayor_capacidad_libre(self):
        """Extensión 7a.1: si empatan, el de mayor capacidad libre."""
        elegido = entregas.seleccionar([candidato(1, 1, "50"), candidato(2, 1, "400"), candidato(3, 1, "100")])
        self.assertEqual(elegido.transportista.pk, 2)

    def test_ext_7a_si_siguen_empatados_gana_el_de_menor_identificador(self):
        """Extensión 7a.2: si siguen empatados, el de menor identificador."""
        elegido = entregas.seleccionar([candidato(7, 0, "50"), candidato(3, 0, "50"), candidato(5, 0, "50")])
        self.assertEqual(elegido.transportista.pk, 3)

    def test_regla_seleccion_ignora_a_los_que_no_cumplen(self):
        """Solo compiten los que cumplen (`motivo` nulo); sin ninguno, `None`."""
        self.assertEqual(entregas.seleccionar([candidato(1, 0, motivo="Inactivo"), candidato(2, 5)]).transportista.pk, 2)
        self.assertIsNone(entregas.seleccionar([candidato(1, 0, motivo="En ruta")]))
        self.assertIsNone(entregas.seleccionar([]))


class MotivoDeAlertaTests(TestCase):
    def test_ext_6a_sin_transportistas_el_motivo_es_el_de_la_flota(self):
        """Extensión 6a.2: sin ningún transportista en el invernadero, «sin transportistas activos con vehículo activo»."""
        self.assertEqual(entregas.motivo_de_alerta([]), "sin transportistas activos con vehículo activo")

    def test_ext_6a_si_todos_estan_inactivos_o_sin_vehiculo_es_el_de_la_flota(self):
        """«Inactivo» y «Sin vehículo activo» juntos se dicen como «sin transportistas activos con vehículo activo»."""
        candidatos = [candidato(1, motivo="Inactivo"), candidato(2, motivo="Sin vehículo activo")]
        self.assertEqual(entregas.motivo_de_alerta(candidatos), "sin transportistas activos con vehículo activo")

    def test_ext_6a_los_motivos_distintos_van_en_minuscula_en_el_orden_de_la_regla(self):
        """Los motivos distintos, en el orden de la regla, en minúscula y separados por « · » (aunque lleguen repetidos y desordenados)."""
        candidatos = [
            candidato(1, motivo="En ruta"),
            candidato(2, motivo="Capacidad de carga insuficiente"),
            candidato(3, motivo="En ruta"),
        ]
        self.assertEqual(entregas.motivo_de_alerta(candidatos), "en ruta · capacidad de carga insuficiente")

    def test_ext_6a_cada_motivo_se_dice_con_su_texto(self):
        """Los cinco motivos de la ext. 6a.2, uno por uno."""
        esperado = {
            "En ruta": "en ruta",
            "Capacidad de carga insuficiente": "capacidad de carga insuficiente",
            "Máximo de entregas diarias": "máximo de entregas diarias",
            "Máximo de localidades distintas por día": "máximo de localidades distintas por día",
        }
        for motivo, texto in esperado.items():
            self.assertEqual(entregas.motivo_de_alerta([candidato(1, motivo=motivo)]), texto)


class Base(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 5000)
        cls.t = transportista_con_vehiculo(cls.e.invernadero, "800")

    def venta_con_reserva(self, cantidad=100, dias=3, **opciones):
        venta = compra_venta(self.e, dias=dias, **opciones)
        det = detalle(venta, self.e.variedad, cantidad)
        return venta, det, reserva_lista(det, self.lote, cantidad)

    def entrega_de(self, cantidad=100, dias=3, transportista=None, **opciones):
        venta, det, r = self.venta_con_reserva(cantidad, dias, **opciones)
        return entrega(venta, [r], transportista=transportista)

    def peso_por_planta(self, gramos):
        Variedad.objects.filter(pk=self.e.variedad.pk).update(peso_promedio_planta=gramos)


class CantidadYPesoTests(Base):
    def test_regla_cantidad_planificada_es_la_suma_de_lo_cubierto_de_sus_reservas_no_liberadas(self):
        """Regla «Cantidad planificada de una línea» (regla 9 de 8.8): Σ la cantidad cubierta de las reservas no liberadas; una liberada no cuenta."""
        venta, det, r = self.venta_con_reserva(60)
        otra = reserva_lista(det, self.lote, 40)
        liberada = reserva_lista(det, self.lote, 25)
        liberada.estado_reserva = "liberada"
        liberada.save()
        e = entrega(venta, [r, otra, liberada])
        linea = e.lineas.get()
        self.assertEqual(entregas.cantidades_planificadas([linea.pk]), {linea.pk: 100})

    def test_regla_cantidad_planificada_de_una_linea_de_lote_cosechado_es_el_minimo(self):
        """Regla 9 de 8.8: de un lote cosechado, `min(cosechada, reservada)`."""
        venta = compra_venta(self.e)
        det = detalle(venta, self.e.variedad, 50)
        r = reserva(det, [(self.lote, 50)], estado="lista_para_entrega", con_cosecha=False)
        r.lineas.update(cantidad_cosechada=30)
        linea = entrega(venta, [r]).lineas.get()
        self.assertEqual(entregas.cantidades_planificadas([linea.pk])[linea.pk], 30)

    def test_d66_4_una_linea_con_todas_sus_reservas_liberadas_queda_en_cero(self):
        """D-66 punto 4: una línea cuyas reservas quedaron todas liberadas queda en 0 (no se borra)."""
        venta, det, r = self.venta_con_reserva(10)
        linea = entrega(venta, [r]).lineas.get()
        r.estado_reserva = "liberada"
        r.save()
        self.assertEqual(entregas.cantidades_planificadas([linea.pk]), {linea.pk: 0})
        self.assertEqual(entregas.cantidades_planificadas([]), {})

    def test_regla_peso_de_una_entrega_es_cantidad_por_gramos_dividido_mil(self):
        """Regla «Peso de una entrega»: Σ cantidad planificada × peso promedio por planta (g) / 1.000, en kg con dos decimales (MD-69): 100 × 150 g = 15,00 kg."""
        e = self.entrega_de(100)
        self.assertEqual(entregas.peso_de_entregas([e.pk]), {e.pk: Decimal("15.00")})

    def test_regla_peso_se_redondea_hacia_arriba_en_el_medio(self):
        """`ROUND_HALF_UP`: 1.001 plantas × 5 g = 5,005 kg → 5,01 (el redondeo bancario daría 5,00)."""
        self.peso_por_planta(5)
        e = self.entrega_de(1001)
        self.assertEqual(entregas.peso_de_entregas([e.pk])[e.pk], Decimal("5.01"))

    def test_regla_peso_de_varias_entregas_con_pocas_consultas(self):
        """El peso de varias entregas en una sola llamada, sin consultas por entrega."""
        ids = [self.entrega_de(10 * (i + 1)).pk for i in range(4)]
        with CaptureQueriesContext(connection) as consultas:
            pesos = entregas.peso_de_entregas(ids)
        self.assertEqual([pesos[i] for i in ids], [Decimal("1.50"), Decimal("3.00"), Decimal("4.50"), Decimal("6.00")])
        self.assertLessEqual(len(consultas), 4)

    def test_regla_peso_de_una_entrega_vacia_es_cero(self):
        """Una entrega sin lo planificado pesa 0,00."""
        venta, det, r = self.venta_con_reserva(10)
        e = entrega(venta, [r])
        r.estado_reserva = "liberada"
        r.save()
        self.assertEqual(entregas.peso_de_entregas([e.pk])[e.pk], Decimal("0.00"))

    def test_md_118_una_entrega_esta_en_curso_si_su_vehiculo_esta_en_ruta_y_la_fecha_es_hoy_o_anterior(self):
        """MD-118 y modelo, «En curso»: con envío, `fecha_programada_orden <= hoy` y el vehículo de su transportista `esta_en_ruta(hoy)`."""
        en_ruta = transportista_con_vehiculo(self.e.invernadero, "800", en_ruta=True)
        e = self.entrega_de(10, dias=0, transportista=en_ruta)
        self.assertTrue(entregas.en_curso(e, HOY))
        futura = self.entrega_de(10, dias=2, transportista=en_ruta)
        self.assertFalse(entregas.en_curso(futura, HOY))
        quieta = self.entrega_de(10, dias=0, transportista=self.t)
        self.assertFalse(entregas.en_curso(quieta, HOY))
        sin = self.entrega_de(10, dias=0)
        self.assertFalse(entregas.en_curso(sin, HOY))

    def test_md_139_una_entrega_a_realizar_con_fecha_pasada_esta_atrasada(self):
        """MD-139: «atrasada» = «a realizar» y `fecha_programada_orden < hoy`."""
        venta, det, r = self.venta_con_reserva(10)
        atrasada = entrega(venta, [r], fecha=HOY - timedelta(days=2))
        self.assertTrue(entregas.atrasada(atrasada, HOY))
        self.assertFalse(entregas.atrasada(self.entrega_de(10, dias=0), HOY))
        atrasada.estado_orden = "cancelada"
        self.assertFalse(entregas.atrasada(atrasada, HOY))


class CandidatosTests(Base):
    def candidatos(self, peso="5", fecha=None, localidad_id=None, **extra):
        fecha = fecha or HOY + timedelta(days=3)
        localidad_id = localidad_id or self.e.direccion.localidad_id
        return entregas.candidatos_para(self.e.invernadero, fecha, Decimal(peso), localidad_id, hoy=HOY, **extra)

    def de(self, candidatos, transportista):
        return next(c for c in candidatos if c.transportista.pk == transportista.pk)

    def test_regla_candidato_cumple_si_ninguna_verificacion_falla(self):
        """Regla «Transportista candidato» y pasos 5 y 6: del invernadero, activo, con vehículo activo y dentro de los límites: `motivo` nulo."""
        c = self.de(self.candidatos(), self.t)
        self.assertIsNone(c.motivo)
        self.assertEqual((c.entregas_del_dia, c.peso_del_dia, c.capacidad_libre), (0, Decimal("0"), Decimal("800")))

    def test_motivo_1_inactivo(self):
        """Motivo «Inactivo»: la cuenta no está activa."""
        t = transportista_con_vehiculo(self.e.invernadero, activo=False)
        self.assertEqual(self.de(self.candidatos(), t).motivo, "Inactivo")

    def test_motivo_2_sin_vehiculo_activo(self):
        """Motivo «Sin vehículo activo»: sin vehículo."""
        t = transportista_con_vehiculo(self.e.invernadero, con_vehiculo=False)
        self.assertEqual(self.de(self.candidatos(), t).motivo, "Sin vehículo activo")

    def test_motivo_3_en_ruta_solo_si_la_fecha_es_hoy(self):
        """Motivo «En ruta»: `fecha == hoy` y el vehículo está en ruta; para otro día, no."""
        t = transportista_con_vehiculo(self.e.invernadero, en_ruta=True)
        self.assertEqual(self.de(self.candidatos(fecha=HOY), t).motivo, "En ruta")
        self.assertIsNone(self.de(self.candidatos(fecha=HOY + timedelta(days=1)), t).motivo)

    def test_motivo_4_capacidad_de_carga_insuficiente(self):
        """Motivo «Capacidad de carga insuficiente»: Σ peso de sus entregas no canceladas de la fecha + el nuevo > capacidad."""
        chico = transportista_con_vehiculo(self.e.invernadero, "10")
        self.assertEqual(self.de(self.candidatos(peso="10.01"), chico).motivo, "Capacidad de carga insuficiente")
        self.assertIsNone(self.de(self.candidatos(peso="10.00"), chico).motivo)

    def test_motivo_4_cuenta_las_entregas_del_dia_concretadas_y_a_realizar_pero_no_las_canceladas(self):
        """Regla «Capacidad de carga»: las del día cuentan «a realizar» y «concretada»; la cancelada no."""
        chico = transportista_con_vehiculo(self.e.invernadero, "20")
        fecha = HOY + timedelta(days=3)
        for estado in ("a_realizar", "concretada", "cancelada"):
            venta, det, r = self.venta_con_reserva(40)
            entrega(venta, [r], transportista=chico, estado=estado, fecha=fecha)
        c = self.de(self.candidatos(peso="1", fecha=fecha), chico)
        self.assertEqual((c.entregas_del_dia, c.peso_del_dia, c.motivo), (2, Decimal("12.00"), None))
        self.assertEqual(self.de(self.candidatos(peso="9", fecha=fecha), chico).motivo, "Capacidad de carga insuficiente")

    def test_motivo_5_maximo_de_entregas_diarias(self):
        """Motivo «Máximo de entregas diarias»: sus entregas no canceladas de la fecha + 1 > `cant_maxima_entregas_diarias`."""
        ConfiguracionOperativa.objects.update(cant_maxima_entregas_diarias=1)
        fecha = HOY + timedelta(days=3)
        venta, det, r = self.venta_con_reserva(10)
        entrega(venta, [r], transportista=self.t, fecha=fecha)
        self.assertEqual(self.de(self.candidatos(fecha=fecha), self.t).motivo, "Máximo de entregas diarias")
        self.assertIsNone(self.de(self.candidatos(fecha=fecha + timedelta(days=1)), self.t).motivo)

    def test_motivo_6_maximo_de_localidades_distintas(self):
        """Motivo «Máximo de localidades distintas por día»: las localidades distintas de destino de esas entregas, con la nueva, > `cant_max_ciudades_distintas_diarias`;
        repetir una localidad no suma."""
        ConfiguracionOperativa.objects.update(cant_max_ciudades_distintas_diarias=1)
        fecha = HOY + timedelta(days=3)
        otra = Localidad.objects.exclude(pk=localidad().pk).first()
        lejana = direccion_de_cliente(self.e.cliente, localidad_id=otra.pk).direccion
        venta, det, r = self.venta_con_reserva(10, direccion=lejana)
        entrega(venta, [r], transportista=self.t, fecha=fecha)
        propia = self.e.direccion.localidad_id
        self.assertEqual(self.de(self.candidatos(fecha=fecha, localidad_id=propia), self.t).motivo, "Máximo de localidades distintas por día")
        self.assertIsNone(self.de(self.candidatos(fecha=fecha, localidad_id=otra.pk), self.t).motivo)

    def test_los_motivos_se_evaluan_en_el_orden_de_la_regla(self):
        """El primero que falla: un transportista inactivo y sin vehículo es «Inactivo»."""
        t = transportista_con_vehiculo(self.e.invernadero, activo=False, con_vehiculo=False)
        self.assertEqual(self.de(self.candidatos(), t).motivo, "Inactivo")

    def test_ext_excluir_saca_al_transportista_actual(self):
        """COM-ASG-TRP usa `excluir` = el transportista actual: no aparece entre los candidatos."""
        otro = transportista_con_vehiculo(self.e.invernadero)
        pks = [c.transportista.pk for c in self.candidatos(excluir=self.t)]
        self.assertNotIn(self.t.pk, pks)
        self.assertIn(otro.pk, pks)

    def test_regla_un_transportista_de_otro_invernadero_no_es_candidato(self):
        """MD-138: los candidatos son los del invernadero de origen."""
        from comercial.tests.fabricas import segundo_invernadero

        sur = segundo_invernadero(self.e)
        ajeno = transportista_con_vehiculo(sur.invernadero)
        self.assertNotIn(ajeno.pk, [c.transportista.pk for c in self.candidatos()])

    def test_candidatos_sin_consultas_por_transportista(self):
        """Una consulta por tabla: con más transportistas no suben las consultas."""
        with CaptureQueriesContext(connection) as pocas:
            self.candidatos()
        for _ in range(4):
            transportista_con_vehiculo(self.e.invernadero)
        with CaptureQueriesContext(connection) as muchas:
            self.candidatos()
        self.assertEqual(len(pocas), len(muchas))


class AgrupamientoTests(Base):
    def setUp(self):
        self.fecha = HOY + timedelta(days=3)
        self.venta, self.det, r = self.venta_con_reserva(100)
        self.existente = entrega(self.venta, [r], transportista=self.t)

    def agrupar(self, peso="5", **cambios):
        argumentos = dict(
            contrato=self.venta, invernadero=self.e.invernadero, destino=self.venta.direccion_envio_id, fecha=self.fecha, peso_nuevo=Decimal(peso), hoy=HOY
        )
        argumentos.update(cambios)
        return entregas.entrega_para_agrupar(**argumentos)

    def test_ext_4a_la_que_cumple_todo_se_elige(self):
        """Extensión 4a y regla «Agrupamiento»: mismo contrato, invernadero, destino y fecha; «a realizar»; sin envasado; con lugar y fuera de ruta."""
        self.assertEqual(self.agrupar().pk, self.existente.pk)

    def test_regla_agrupamiento_mismo_contrato(self):
        """Condición: es del mismo contrato."""
        otra = compra_venta(self.e, dias=3)
        self.assertIsNone(self.agrupar(contrato=otra))

    def test_regla_agrupamiento_mismo_invernadero(self):
        """Condición: es del mismo invernadero de origen."""
        from comercial.tests.fabricas import segundo_invernadero

        self.assertIsNone(self.agrupar(invernadero=segundo_invernadero(self.e).invernadero))

    def test_regla_agrupamiento_mismo_destino(self):
        """Condición: la misma dirección de destino (o retiro)."""
        otra = direccion_de_cliente(self.e.cliente, calle="Otra").direccion
        self.assertIsNone(self.agrupar(destino=otra.pk))
        self.assertIsNone(self.agrupar(destino=None))

    def test_regla_agrupamiento_misma_fecha_programada(self):
        """Condición: la misma fecha programada."""
        self.assertIsNone(self.agrupar(fecha=self.fecha + timedelta(days=1)))

    def test_regla_agrupamiento_esta_a_realizar(self):
        """Condición: la entrega está «a realizar» (una cancelada o concretada no recibe líneas)."""
        for estado in ("cancelada", "concretada"):
            venta, det, r = self.venta_con_reserva(10)
            otra = entrega(venta, [r], estado=estado)
            self.assertIsNone(self.agrupar(contrato=venta, fecha=otra.fecha_programada_orden, destino=venta.direccion_envio_id))

    def test_regla_agrupamiento_sin_envasado_planificado(self):
        """Condición: no tiene reservas de insumo «activas» (sin envasado planificado)."""
        reservar(self.existente, self.e.existencia_semilla, 1)
        self.assertEqual(ReservaInsumo.objects.filter(orden_id=self.existente.pk, estado="activa").count(), 1)
        self.assertIsNone(self.agrupar())

    def test_regla_agrupamiento_una_reserva_de_insumo_cancelada_no_impide(self):
        """Una reserva de insumo cancelada ya no es envasado planificado."""
        reservar(self.existente, self.e.existencia_semilla, 1, estado="cancelada")
        self.assertEqual(self.agrupar().pk, self.existente.pk)

    def test_regla_agrupamiento_con_transportista_no_supera_la_capacidad(self):
        """Condición: con transportista, el peso del día + el nuevo no supera la capacidad de su vehículo (la entrega ya cuenta en el día: 15 kg de 800)."""
        self.assertEqual(self.agrupar(peso="785").pk, self.existente.pk)
        self.assertIsNone(self.agrupar(peso="785.01"))

    def test_regla_agrupamiento_con_transportista_en_ruta_hoy_no_se_agrupa(self):
        """Condición: si tiene transportista, no está en ruta (la fecha de hoy)."""
        en_ruta = transportista_con_vehiculo(self.e.invernadero, "800", en_ruta=True)
        venta, det, r = self.venta_con_reserva(10, dias=0)
        otra = entrega(venta, [r], transportista=en_ruta)
        self.assertIsNone(self.agrupar(contrato=venta, fecha=HOY, destino=venta.direccion_envio_id))
        self.assertEqual(otra.fecha_programada_orden, HOY)

    def test_regla_agrupamiento_sin_transportista_se_agrupa_igual(self):
        """Sin transportista no hay capacidad ni ruta que mirar."""
        venta, det, r = self.venta_con_reserva(10)
        sin = entrega(venta, [r])
        self.assertEqual(self.agrupar(contrato=venta, fecha=sin.fecha_programada_orden, destino=venta.direccion_envio_id, peso="99999").pk, sin.pk)

    def test_regla_agrupamiento_si_hay_mas_de_una_gana_la_de_menor_id(self):
        """Si hay más de una que cumple, la de menor id."""
        venta, det, r = self.venta_con_reserva(10)
        primera = entrega(venta, [r])
        segunda = entrega(venta, [reserva_lista(det, self.lote, 5)])
        self.assertLess(primera.pk, segunda.pk)
        elegida = self.agrupar(contrato=venta, fecha=primera.fecha_programada_orden, destino=venta.direccion_envio_id)
        self.assertEqual(elegida.pk, primera.pk)
