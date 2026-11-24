# Pruebas de PROD-CNS-BIT · Consultar Bitácora (PRD-03, paso 6; docs/casos_de_uso/produccion/bitacora.md, «PROD-CNS-BIT · decisiones de aplicación»).
# Se escriben ANTES que el servicio y deben fallar; el estudiante las revisa antes de implementar.
#
# CONTRATO que fijan estas pruebas (produccion/servicios/bitacora.py, el mismo módulo del evento):
# - invernaderos_de_bitacora(actor) -> list[Invernadero]: el Agrónomo, los que tiene a su cargo (también los dados de baja: regla 2); el Gerente, todos
#   (también los de baja); cualquier otra cuenta, o una inactiva, ninguno (el Capataz no consulta la bitácora). Por nombre. Si hay uno solo viene elegido
#   (regla 1: lo decide la pantalla con esta lista).
# - TIPOS_DE_FILTRO: `[(valor, texto)]` de los tipos que ofrece el filtro: siembra, transición, merma, aplicación, otro evento y (PRD-04) sector fuera de servicio y reubicación. No el interno `consumo` ni los
#   que no existen todavía (cosecha, incumplimiento de cláusula, fuera de servicio, reubicación: los suman sus rondas).
# - FiltrosDeBitacora(texto="", tipo="", lote_id=None, sector_id=None, desde=None, hasta=None): todos combinables (regla 6); `texto` es `icontains` en la
#   descripción; el sector encuentra los registros que lo tienen ENTRE los suyos; `desde` y `hasta` son inclusive.
# - consultar_bitacora(actor, invernadero_id, filtros=None, pagina=1) -> PaginaDeBitacora(invernadero, dias, total, pagina, paginas, hay_filtros):
#   `dias` es `[DiaDeBitacora(fecha, registros)]` del más reciente al más antiguo y, dentro de cada día, por (hora, id) descendente; de a 50 por página
#   (reglas 3 y 7: todo se ve en el listado). Cada `RegistroDeBitacora(id, fecha, hora, tipo, tipo_texto, lote, sectores, descripcion, responsable, consumos)`
#   trae el código del lote (`L-3`) o `None`, los nombres de los sectores, quien lo registró («Nombre Apellido», o «InfoPonia» si lo generó el Sistema) y, en una
#   aplicación, sus consumos como texto («Limpiador: 5 L»). El interno `consumo` no se lista. `pagina` fuera de rango se acota. No audita (SEG-14).
# - Errores: `sin_permiso` (cuenta que no consulta o invernadero ajeno), `Http404` (invernadero inexistente), `filtro_invalido` (campo `tipo`: un tipo que
#   no se ofrece). Un número constante de consultas, con 1 o con 50 registros.
#
# Una prueba por regla 1 a 9.

from datetime import date, time, timedelta

from django.db import connection
from django.http import Http404
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, perezoso
from maestros.models import Invernadero
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo, crear_invernadero
from produccion.errores import ErrorDeProduccion
from produccion.models import Bitacora, Merma
from produccion.tests.fabricas import invernadero_con_produccion, lote_activo
from produccion.tests.test_modelos_aplicacion import aplicacion_de, consumo_de

bitacora = perezoso("produccion.servicios.bitacora")

HOY = timezone.localdate()


def rechazo(llamada):
    """Ejecuta `llamada()` y devuelve el `ErrorDeProduccion` que lanza; si no lanza ninguno, la prueba falla."""
    try:
        llamada()
    except ErrorDeProduccion as error:
        return error
    raise AssertionError("Se esperaba un ErrorDeProduccion y no se lanzó ninguno.")


class Base(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()
        cls.lote = lote_activo(cls.e, cantidad=30, sector="germinacion")

    def evento(self, descripcion="Evento", tipo="otro_evento", dia=None, hora=time(10, 0), invernadero=None, responsable="cap", lote=None, sectores=(), clase=Bitacora, **extra):
        """Un registro de bitácora escrito directo en la base, con la fecha y la hora que se pidan."""
        quien = {"cap": self.e.capataz, "agro": self.e.agronomo, None: None}[responsable] if isinstance(responsable, (str, type(None))) else responsable
        registro = clase.objects.create(
            invernadero=invernadero or self.e.invernadero, tipo_evento=tipo, descripcion_evento=descripcion, fecha_bitacora=dia or HOY,
            hora_bitacora=hora, responsable=quien, lote=lote, **extra,
        )
        if sectores:
            registro.sectores.set([s.pk for s in sectores])
        return registro

    def consultar(self, actor=None, invernadero=None, pagina=1, **filtros):
        return bitacora.consultar_bitacora(
            actor or self.e.agronomo, (invernadero or self.e.invernadero).pk, bitacora.FiltrosDeBitacora(**filtros), pagina
        )

    def registros(self, pagina):
        return [r for dia in pagina.dias for r in dia.registros]


class AlcanceTests(Base):
    def test_regla_1_el_agronomo_ve_solo_los_invernaderos_a_su_cargo_y_el_gerente_todos(self):
        """Regla 1: el Agrónomo elige entre los invernaderos a su cargo; el Gerente, entre todos."""
        otro = crear_invernadero("Otro", agronomo=crear_agronomo(email="otro@infoponia.com"))
        self.assertEqual([i.pk for i in bitacora.invernaderos_de_bitacora(self.e.agronomo)], [self.e.invernadero.pk])
        self.assertEqual({i.pk for i in bitacora.invernaderos_de_bitacora(crear_gerente())}, {self.e.invernadero.pk, otro.pk})

    def test_regla_2_tambien_se_consultan_los_invernaderos_dados_de_baja(self):
        """Regla 2: la baja es lógica y conserva el historial: el Agrónomo (los suyos) y el Gerente (todos) siguen viendo los de baja y su bitácora."""
        self.evento("Antes de la baja")
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        gerente = crear_gerente()
        for actor in (self.e.agronomo, gerente):
            self.assertIn(self.e.invernadero.pk, [i.pk for i in bitacora.invernaderos_de_bitacora(actor)])
            self.assertEqual(len(self.registros(self.consultar(actor))), 1)

    def test_regla_precondicion_a_el_capataz_y_las_cuentas_inactivas_no_consultan(self):
        """Precondición a: solo una cuenta activa de Agrónomo o de Gerente; el Capataz no consulta la bitácora (el caso de uso no lo incluye)."""
        self.assertEqual(bitacora.invernaderos_de_bitacora(self.e.capataz), [])
        self.assertEqual(rechazo(lambda: self.consultar(self.e.capataz)).codigo, "sin_permiso")
        agronomo = self.e.agronomo
        agronomo.is_active = False
        agronomo.save()
        self.assertEqual(bitacora.invernaderos_de_bitacora(agronomo), [])
        self.assertEqual(rechazo(lambda: self.consultar(agronomo)).codigo, "sin_permiso")

    def test_regla_1_un_agronomo_no_consulta_un_invernadero_ajeno_y_uno_inexistente_es_404(self):
        """Regla 1: el Agrónomo solo consulta los suyos; uno que no existe es un 404."""
        ajeno = crear_invernadero("Ajeno", agronomo=crear_agronomo(email="otro@infoponia.com"))
        self.assertEqual(rechazo(lambda: self.consultar(invernadero=ajeno)).codigo, "sin_permiso")
        with self.assertRaises(Http404):
            bitacora.consultar_bitacora(self.e.agronomo, 999999, bitacora.FiltrosDeBitacora(), 1)

    def test_regla_1_los_registros_de_otro_invernadero_no_aparecen(self):
        """Regla 1: se consulta la bitácora de un invernadero por vez."""
        otro = crear_invernadero("Otro", agronomo=self.e.agronomo)
        self.evento("Mío")
        self.evento("Del otro", invernadero=otro)
        self.assertEqual([r.descripcion for r in self.registros(self.consultar())], ["Mío"])


class OrdenYPaginacionTests(Base):
    def test_regla_3_orden_del_mas_reciente_al_mas_antiguo_por_fecha_hora_e_id_y_agrupado_por_dia(self):
        """Regla 3: del más reciente al más antiguo, agrupados por día; dentro de un día, por hora y, si empatan, por id (el último creado, primero)."""
        ayer = HOY - timedelta(days=1)
        self.evento("ayer 08", dia=ayer, hora=time(8, 0))
        self.evento("hoy 09", hora=time(9, 0))
        primero = self.evento("hoy 10 (primero)", hora=time(10, 0))
        segundo = self.evento("hoy 10 (segundo)", hora=time(10, 0))
        pagina = self.consultar()
        self.assertEqual([d.fecha for d in pagina.dias], [HOY, ayer])
        self.assertEqual([r.descripcion for r in pagina.dias[0].registros], ["hoy 10 (segundo)", "hoy 10 (primero)", "hoy 09"])
        self.assertEqual([r.descripcion for r in pagina.dias[1].registros], ["ayer 08"])
        self.assertLess(primero.pk, segundo.pk)

    def test_regla_3_de_a_50_por_pagina(self):
        """Regla 3: 50 registros por página. 120 registros son 3 páginas (50, 50 y 20); una página fuera de rango se acota."""
        for n in range(120):
            self.evento(f"Evento {n:03d}", dia=HOY - timedelta(days=n % 7), hora=time(n % 24, n % 60))
        tamanos = [len(self.registros(self.consultar(pagina=p))) for p in (1, 2, 3)]
        self.assertEqual(tamanos, [50, 50, 20])
        primera = self.consultar(pagina=1)
        self.assertEqual((primera.total, primera.paginas, primera.pagina), (120, 3, 1))
        self.assertEqual(self.consultar(pagina=99).pagina, 3)
        self.assertEqual(self.consultar(pagina=0).pagina, 1)
        ids = [r.id for p in (1, 2, 3) for r in self.registros(self.consultar(pagina=p))]
        self.assertEqual(len(set(ids)), 120)

    def test_regla_8_sin_registros_informa_total_cero(self):
        """Regla 8: si el invernadero no tiene registros, la consulta devuelve el total en cero (la pantalla lo informa); sin filtros."""
        pagina = self.consultar()
        self.assertEqual((pagina.total, pagina.dias, pagina.hay_filtros), (0, [], False))


class ContenidoTests(Base):
    def test_regla_4_cada_registro_muestra_fecha_hora_tipo_lote_sectores_descripcion_y_quien_lo_registro(self):
        """Regla 4: fecha y hora, tipo, lote (`L-3`), sectores, descripción y quién lo registró."""
        sectores = (self.e.sectores["germinacion"], self.e.sectores["crecimiento"])
        self.evento("Merma de 3 plantas por plaga.", tipo="merma", hora=time(14, 5), lote=self.lote, sectores=sectores, clase=Merma, cant_merma=3, causa="plaga")
        registro = self.registros(self.consultar())[0]
        self.assertEqual((registro.fecha, registro.hora, registro.tipo, registro.tipo_texto), (HOY, time(14, 5), "merma", "Merma"))
        self.assertEqual((registro.lote, registro.descripcion), (self.lote.codigo, "Merma de 3 plantas por plaga."))
        self.assertEqual(set(registro.sectores), {s.nombre_sector for s in sectores})
        self.assertEqual(registro.responsable, f"{self.e.capataz.first_name} {self.e.capataz.last_name}".strip())

    def test_regla_4_un_registro_sin_lote_ni_sectores_los_muestra_vacios(self):
        """Regla 4: sin lote, `None`; sin sectores, lista vacía."""
        registro = self.evento("Corte de luz") and self.registros(self.consultar())[0]
        self.assertEqual((registro.lote, registro.sectores), (None, []))

    def test_regla_4_lo_que_genero_el_sistema_dice_infoponia(self):
        """Regla 4: si lo generó el Sistema (sin responsable), se indica como «InfoPonia»."""
        self.evento("Generado por el Sistema", responsable=None)
        self.assertEqual(self.registros(self.consultar())[0].responsable, "InfoPonia")

    def test_regla_5_se_listan_todos_los_tipos_de_la_ronda_con_su_texto(self):
        """Regla 5: siembra, transición, merma y otro evento (y aplicación) se listan, con el texto de su tipo; el filtro de tipos ofrece solo los de la ronda."""
        for tipo in ("siembra", "transicion", "merma", "otro_evento"):
            self.evento(f"de tipo {tipo}", tipo=tipo, hora=time(9, len(tipo)))
        self.evento("aplicacion", tipo="aplicacion", clase=Bitacora)
        textos = {r.tipo: r.tipo_texto for r in self.registros(self.consultar())}
        self.assertEqual(textos, {"siembra": "Siembra", "transicion": "Transición de etapa", "merma": "Merma", "otro_evento": "Otro evento", "aplicacion": "Aplicación de insumos"})
        # COM-04a suma `cosecha` y los dos de contrato al filtro (docs/disparadores.md, «Cuando exista `produccion` completa», punto 3).
        self.assertEqual(
            [v for v, _ in bitacora.TIPOS_DE_FILTRO],
            ["siembra", "transicion", "merma", "aplicacion", "otro_evento", "fuera_de_servicio", "reubicacion", "cosecha", "incumplimiento_de_clausula", "anulacion_de_resolucion"],
        )

    def test_regla_5_el_consumo_interno_de_una_aplicacion_no_se_lista_pero_se_muestra_dentro_de_su_aplicacion(self):
        """Regla 5 y D-51 punto 3: el consumo de una aplicación es de tipo interno `consumo` y no se lista; se ve dentro de su aplicación (insumo y cantidad)."""
        habilitado = existencia(insumo("Limpiador", unidad="l"), self.e.invernadero)
        aplicacion = aplicacion_de(self.e, descripcion_evento="Limpieza")
        consumo_de(self.e, habilitado, aplicacion=aplicacion, cant_consumo="5.000")
        registros = self.registros(self.consultar())
        self.assertEqual([r.tipo for r in registros], ["aplicacion"])
        self.assertEqual(len(registros[0].consumos), 1)
        self.assertIn("Limpiador", registros[0].consumos[0])
        self.assertIn("5", registros[0].consumos[0])

    def test_regla_5_el_consumo_de_una_siembra_se_lista_como_un_registro_de_siembra(self):
        """Decisión de aplicación: un consumo de siembra (hijo con tipo `siembra`) se lista como un registro «siembra» por insumo, como pide PROD-CNC-SMB."""
        habilitado = existencia(insumo("Semilla", unidad="unidad"), self.e.invernadero)
        consumo_de(self.e, habilitado, siembra=self.lote.siembra, tipo_evento="siembra", lote=self.lote, descripcion_evento="Siembra OT-1: Semilla, 30 unidades")
        registros = self.registros(self.consultar())
        self.assertEqual([(r.tipo, r.consumos) for r in registros], [("siembra", [])])

    def test_regla_7_una_aplicacion_en_varios_sectores_los_trae_todos_en_su_propio_registro(self):
        """Regla 7 y MD-28: toda la información de un registro se ve en el listado: una aplicación en varios sectores los muestra juntos."""
        sectores = (self.e.sectores["germinacion"], self.e.sectores["crecimiento"])
        aplicacion_de(self.e, descripcion_evento="Nutrientes").sectores.set([s.pk for s in sectores])
        self.assertEqual(set(self.registros(self.consultar())[0].sectores), {s.nombre_sector for s in sectores})


class FiltrosTests(Base):
    def setUp(self):
        self.germ, self.crec = self.e.sectores["germinacion"], self.e.sectores["crecimiento"]
        self.otro_lote = lote_activo(self.e, cantidad=10, sector="crecimiento")
        self.evento("Riego revisado", tipo="otro_evento", dia=HOY - timedelta(days=5), sectores=(self.germ,))
        self.evento("Pulgón en lechuga", tipo="merma", dia=HOY - timedelta(days=3), lote=self.lote, sectores=(self.germ,), clase=Merma, cant_merma=1, causa="plaga")
        self.evento("Nutrientes", tipo="aplicacion", dia=HOY - timedelta(days=1), sectores=(self.germ, self.crec))
        self.evento("Otro lote", tipo="merma", dia=HOY, lote=self.otro_lote, sectores=(self.crec,), clase=Merma, cant_merma=1, causa="plaga")

    def descripciones(self, **filtros):
        return sorted(r.descripcion for r in self.registros(self.consultar(**filtros)))

    def test_regla_6_filtra_por_texto_en_la_descripcion_sin_distinguir_mayusculas(self):
        """Regla 6: texto en la descripción (`icontains`)."""
        self.assertEqual(self.descripciones(texto="PULGÓN"), ["Pulgón en lechuga"])
        self.assertEqual(self.descripciones(texto="zzz"), [])

    def test_regla_6_filtra_por_tipo(self):
        """Regla 6: tipo de evento."""
        self.assertEqual(self.descripciones(tipo="merma"), ["Otro lote", "Pulgón en lechuga"])
        self.assertEqual(self.descripciones(tipo="aplicacion"), ["Nutrientes"])

    def test_regla_6_filtra_por_lote(self):
        """Regla 6: lote."""
        self.assertEqual(self.descripciones(lote_id=self.lote.pk), ["Pulgón en lechuga"])

    def test_regla_6_el_filtro_por_sector_encuentra_los_registros_que_lo_tienen_entre_los_suyos(self):
        """Regla 6 y MD-28: el sector encuentra los registros con ese sector entre los suyos, que pueden ser varios en una aplicación."""
        self.assertEqual(self.descripciones(sector_id=self.crec.pk), ["Nutrientes", "Otro lote"])
        self.assertEqual(self.descripciones(sector_id=self.germ.pk), ["Nutrientes", "Pulgón en lechuga", "Riego revisado"])

    def test_regla_6_el_rango_de_fechas_es_inclusivo_y_puede_ser_abierto(self):
        """Regla 6: rango de fechas; los extremos entran; con un solo extremo, abierto del otro lado."""
        self.assertEqual(self.descripciones(desde=HOY - timedelta(days=3), hasta=HOY - timedelta(days=1)), ["Nutrientes", "Pulgón en lechuga"])
        self.assertEqual(self.descripciones(desde=HOY - timedelta(days=1)), ["Nutrientes", "Otro lote"])
        self.assertEqual(self.descripciones(hasta=HOY - timedelta(days=5)), ["Riego revisado"])

    def test_regla_6_los_filtros_se_combinan(self):
        """Regla 6: los filtros se combinan (y): merma en el sector de crecimiento; y un texto que no coincide con el resto da vacío."""
        self.assertEqual(self.descripciones(tipo="merma", sector_id=self.crec.pk), ["Otro lote"])
        self.assertEqual(self.descripciones(tipo="merma", sector_id=self.crec.pk, texto="pulgón"), [])
        self.assertEqual(self.descripciones(tipo="merma", lote_id=self.lote.pk, desde=HOY - timedelta(days=4), texto="lechuga"), ["Pulgón en lechuga"])

    def test_regla_8_con_filtros_sin_coincidencias_informa_el_total_cero_y_que_hay_filtros(self):
        """Regla 8: si ninguno coincide, la consulta informa total 0 y que hay filtros aplicados (la pantalla ofrece «Quitar filtros»)."""
        pagina = self.consultar(texto="zzz")
        self.assertEqual((pagina.total, pagina.hay_filtros), (0, True))
        self.assertFalse(self.consultar().hay_filtros)

    def test_regla_6_un_tipo_que_no_se_ofrece_es_un_filtro_invalido(self):
        """Regla 5: el interno `consumo` y los tipos inventados no se ofrecen: pedirlos es un `filtro_invalido` en el campo `tipo` (COM-04a ya ofrece `cosecha`)."""
        for tipo in ("consumo", "comando", "inventado"):
            error = rechazo(lambda: self.consultar(tipo=tipo))
            self.assertEqual((error.codigo, error.campo), ("filtro_invalido", "tipo"))


class ConsultaTests(Base):
    def test_regla_9_la_consulta_no_genera_auditoria(self):
        """Regla 9 y SEG-14: la consulta no genera log de auditoría."""
        self.evento("Algo")
        antes = RegistroAuditoria.objects.count()
        bitacora.invernaderos_de_bitacora(self.e.agronomo)
        self.consultar(texto="Algo")
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_regla_7_una_consulta_por_pagina_sin_consultas_por_fila_con_1_o_con_50_registros(self):
        """Regla 7 y D-51: una consulta por tabla para toda la página, sin consultas por fila: el mismo número de consultas con 1 registro que con 50 (con
        lote, sectores, responsable y aplicaciones con sus consumos)."""
        limpiador = insumo("Limpiador", unidad="l")
        habilitado = existencia(limpiador, self.e.invernadero)
        pocos = crear_invernadero("Pocos", agronomo=self.e.agronomo)
        # Los dos escenarios tienen una aplicación con consumo en la página: si no, Django se saltea la consulta de los consumos y la comparación
        # mezclaría un caso con aplicaciones y otro sin ellas. La fecha y la hora van fijas (las aplicaciones más recientes que las mermas, siempre en la
        # página 1): con la hora actual, antes de las 09:50 quedaban en la página 2 y la prueba pasaba o fallaba según la hora de corrida.
        solo = aplicacion_de(self.e, invernadero=pocos, descripcion_evento="Aplicación única", fecha_bitacora=HOY, hora_bitacora=time(11, 0))
        consumo_de(self.e, existencia(limpiador, pocos), invernadero=pocos, aplicacion=solo)
        for n in range(50):
            self.evento(f"Merma {n}", tipo="merma", hora=time(9, n), lote=self.lote, sectores=(self.e.sectores["germinacion"], self.e.sectores["crecimiento"]), clase=Merma, cant_merma=1, causa="plaga")
        for n in range(5):
            aplicacion = aplicacion_de(self.e, descripcion_evento=f"Aplicación {n}", fecha_bitacora=HOY, hora_bitacora=time(11, n))
            aplicacion.sectores.set([self.e.sectores["germinacion"].pk])
            consumo_de(self.e, habilitado, aplicacion=aplicacion)
        with CaptureQueriesContext(connection) as con_uno:
            uno = self.consultar(invernadero=pocos)
        with CaptureQueriesContext(connection) as con_muchos:
            muchos = self.consultar()
        self.assertEqual(len(self.registros(uno)), 1)
        self.assertEqual(len(self.registros(muchos)), 50)
        self.assertEqual(sum(1 for r in self.registros(muchos) if r.tipo == "aplicacion" and r.consumos), 5)  # control: la página sí trae aplicaciones
        self.assertEqual(len(con_uno), len(con_muchos), [q["sql"][:80] for q in con_muchos.captured_queries])
