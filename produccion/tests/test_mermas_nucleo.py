# Pruebas del NÚCLEO de la merma de un lote en pie (PRD-02, paso 3): `produccion/servicios/mermas.py`, `aplicar_merma` y
# `merma_acumulada`. No es un caso de uso: lo llama Concretar Transición (PRD-02) y lo llamarán Registrar Merma (PRD-03, con
# `por_sector`) y Sector fuera de servicio (PRD-04, con `sector_ids` y `ordenes_excluidas`). Una prueba por regla y por postcondición
# que aplica (a, b, c, k, l, m, n; la d, el movimiento de stock, y la e, el asiento, quedan fuera de la ronda: D-45).
# Fuente: docs/casos_de_uso/produccion/transicion.md (extracto de PROD-REG-MRM y «Núcleo de la merma desde la transición»),
# docs/api/produccion.md (sección 6), docs/patrones/costo_del_lote.md, D-50 punto 6 y D-51 punto 5.
# `mermas` se toma del módulo dentro de cada prueba: mientras no exista, falla cada prueba por separado.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.db import connections
from django.test import TestCase
from django.utils import timezone

from core.models import Notificacion, RegistroAuditoria
from inventario.tests.fabricas import ConDatosDeInventario, perezoso
from maestros.alertas import Clase, Destinatario, Origen, tipo_de_alerta
from maestros.models import Alerta, ConfiguracionOperativa, Invernadero
from produccion.errores import ErrorDeProduccion
from produccion.models import AlertaDeMerma, Bitacora, Lote, Merma, OcupacionSector
from produccion.servicios import costos
from produccion.tests.fabricas import invernadero_con_produccion, lote_con_ciclo, orden_de_transicion

mermas = perezoso("produccion.servicios.mermas")

HOY = timezone.localdate()
UMBRAL = "produccion_merma_umbral"
COMPROMETIDAS = "produccion_plantas_comprometidas"


class BaseDeMermas(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()

    def lote(self, cantidad=100, costo="100.00", etapa="crecimiento"):
        """Un lote activo de `cantidad` plantas en `etapa` (con su fábrica `lote_con_ciclo`)."""
        return lote_con_ciclo(self.e, cantidad=cantidad, costo=costo, etapa=etapa)

    def aplicar(self, lote, cantidad, causa="plaga", descripcion="", fecha=None, responsable=None, **extra):
        """Llama al núcleo (los tests de Django ya corren dentro de una transacción) y devuelve el `ResultadoMerma`."""
        return mermas.aplicar_merma(lote, cantidad, causa, descripcion, fecha or HOY, responsable or self.e.capataz, **extra)

    def merma_previa(self, lote, cantidad, causa="plaga", con_etapa=True):
        """Una merma ya registrada, escrita directo en la base (sin pasar por el núcleo), para armar la merma acumulada."""
        return Merma.objects.create(
            invernadero=lote.invernadero, lote=lote, etapa=lote.etapa if con_etapa else None, tipo_evento="merma",
            fecha_bitacora=HOY, hora_bitacora=timezone.localtime().time(), cant_merma=cantidad, causa=causa,
        )

    def alertas(self, tipo=None):
        """Las alertas creadas, por tipo si se pide."""
        consulta = Alerta.objects.all()
        return consulta.filter(tipo_alerta=tipo) if tipo else consulta


class PostcondicionesDeLaMermaTests(BaseDeMermas):
    def test_post_a_crea_la_bitacora_de_tipo_merma_en_la_etapa_de_origen_con_la_fecha_efectiva_y_la_hora_actual(self):
        """PROD-REG-MRM, postcondición a (desde CNC-TRN): registro de bitácora tipo «merma», con la cantidad, la causa, el
        responsable, el lote, su etapa (la de ORIGEN, porque se ejecuta antes del traslado), el invernadero, la fecha efectiva (que
        puede ser anterior a hoy) y la hora actual."""
        lote = self.lote()
        etapa_de_origen = lote.etapa
        fecha = HOY - timedelta(days=2)
        antes = timezone.localtime().time()
        resultado = self.aplicar(lote, 12, causa="plaga", fecha=fecha)
        despues = timezone.localtime().time()
        merma = Merma.objects.get(pk=resultado.merma.pk)
        self.assertEqual((merma.cant_merma, merma.causa), (12, "plaga"))
        self.assertEqual(merma.tipo_evento, Bitacora.TipoEvento.MERMA)
        self.assertEqual((merma.lote, merma.etapa, merma.invernadero), (lote, etapa_de_origen, lote.invernadero))
        self.assertEqual((merma.fecha_bitacora, merma.responsable_id), (fecha, self.e.capataz.pk))
        self.assertTrue(antes <= merma.hora_bitacora <= despues)

    def test_post_a_la_descripcion_del_evento_es_legible_y_suma_la_descripcion_del_capataz(self):
        """El texto es «Merma de 12 plantas por plaga.»; si el Capataz escribió una descripción, va a continuación. En singular:
        «Merma de 1 planta por plaga.» (decisión del estudiante, 22/11/2026)."""
        lote = self.lote()
        self.assertEqual(self.aplicar(lote, 12).merma.descripcion_evento, "Merma de 12 plantas por plaga.")
        self.assertEqual(self.aplicar(lote, 1).merma.descripcion_evento, "Merma de 1 planta por plaga.")
        con_texto = self.aplicar(lote, 2, causa="dano_mecanico", descripcion="Se cayó una bandeja.")
        self.assertEqual(con_texto.merma.descripcion_evento, "Merma de 2 plantas por daño mecánico. Se cayó una bandeja.")

    def test_post_a_los_sectores_de_la_bitacora_son_los_que_pasa_el_llamador(self):
        """D-51 punto 2: `Bitacora.sectores` = `sector_ids`; desde la transición se llama con `sector_ids=()` y queda vacío."""
        lote = self.lote()
        self.assertEqual(list(self.aplicar(lote, 1).merma.sectores.all()), [])
        sector = self.e.sectores["crecimiento"]
        self.assertEqual(list(self.aplicar(lote, 1, sector_ids=(sector.pk,)).merma.sectores.all()), [sector])

    def test_post_b_baja_la_cantidad_actual_y_el_costo_acumulado_como_el_patron(self):
        """Postcondición b y `costo_del_lote.md`: la cantidad baja en lo perdido y el costo acumulado, en
        `costo_de_la_merma`; las plantas que quedan conservan su costo unitario (200 plantas, 1000,00 → 20 plantas cuestan 100,00)."""
        lote = self.lote(cantidad=200, costo="1000.00")
        resultado = self.aplicar(lote, 20)
        self.assertEqual(resultado.costo, Decimal("100.00"))
        lote.refresh_from_db()
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado), (180, Decimal("900.00")))
        self.assertEqual(costos.costo_por_planta(lote), Decimal("5.00"))

    def test_post_b_el_costo_redondea_como_el_patron_y_actualiza_la_instancia_del_llamador(self):
        """`costo_del_lote.md`, tercer ejemplo: 3 plantas, 10,00: perder 1 cuesta 3,33 y el lote queda con 6,67. El núcleo cambia
        también la instancia que recibe (el caso de uso que lo llama sigue usándola, por ejemplo Concretar Transición)."""
        lote = self.lote(cantidad=3, costo="10.00")
        resultado = self.aplicar(lote, 1)
        self.assertEqual(resultado.costo, Decimal("3.33"))
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado), (2, Decimal("6.67")))
        lote.refresh_from_db()
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado), (2, Decimal("6.67")))

    def test_post_b_si_se_pierde_el_lote_entero_queda_finalizado_con_costo_cero_y_con_el_costo_completo(self):
        """Postcondición b y `costo_del_lote.md`: con la cantidad actual en cero el lote pasa a «finalizado», su costo vale 0 y el
        costo de la merma es el costo acumulado ENTERO (K = 10,01, c = 3: sin perder un centavo)."""
        lote = self.lote(cantidad=3, costo="10.01")
        sector = self.e.sectores["crecimiento"]
        resultado = self.aplicar(lote, 3, por_sector={sector.pk: 3})
        self.assertEqual(resultado.costo, Decimal("10.01"))
        lote.refresh_from_db()
        self.assertEqual((lote.cantidad_actual, lote.estado_lote, lote.costo_acumulado), (0, Lote.Estado.FINALIZADO, Decimal("0.00")))

    def test_regla_el_lote_nunca_queda_con_cantidad_negativa_ni_se_pierde_mas_de_lo_que_hay(self):
        """«Garantías»: una merma mayor que la cantidad actual, de cero o negativa, se rechaza con `cantidad_invalida` y no cambia
        nada (ni el lote ni la bitácora)."""
        lote = self.lote(cantidad=10)
        for cantidad in (11, 0, -1):
            with self.subTest(cantidad=cantidad):
                with self.assertRaises(ErrorDeProduccion) as rechazo:
                    self.aplicar(lote, cantidad)
                self.assertEqual(rechazo.exception.codigo, "cantidad_invalida")
        lote.refresh_from_db()
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado), (10, Decimal("100.00")))
        self.assertFalse(Merma.objects.exists())

    def test_regla_causa_obligatoria_y_dentro_de_la_lista_del_lote_en_pie(self):
        """Regla «Causa»: es obligatoria; sin causa, `causa_obligatoria` (campo `causa`); una de cámara o inventada, `causa_invalida`;
        las siete del lote en pie, incluido el descarte por selección, se aceptan."""
        lote = self.lote()
        with self.assertRaises(ErrorDeProduccion) as sin_causa:
            self.aplicar(lote, 1, causa="")
        self.assertEqual((sin_causa.exception.codigo, sin_causa.exception.campo), ("causa_obligatoria", "causa"))
        for causa in ("vencimiento_en_camara", "dano_en_camara", "otro"):
            with self.subTest(causa=causa), self.assertRaises(ErrorDeProduccion) as invalida:
                self.aplicar(lote, 1, causa=causa)
            self.assertEqual(invalida.exception.codigo, "causa_invalida")
        for causa in Merma.CAUSAS_EN_PIE:  # COM-04a: `Merma.Causa` suma las de cámara y entrega; las del lote en pie son estas siete
            self.aplicar(lote, 1, causa=causa)
        self.assertEqual(Merma.objects.count(), 7)

    def test_regla_la_descripcion_admite_hasta_300_caracteres_y_la_bitacora_entra_en_500(self):
        """Descripción opcional de hasta 300 caracteres (`descripcion_larga` si pasa): con el texto legible entra siempre en los 500
        de `descripcion_evento`."""
        lote = self.lote()
        con_300 = self.aplicar(lote, 1, causa="falla_riego_o_nutrientes", descripcion="x" * 300)
        self.assertLessEqual(len(con_300.merma.descripcion_evento), 500)
        with self.assertRaises(ErrorDeProduccion) as larga:
            self.aplicar(lote, 1, descripcion="x" * 301)
        self.assertEqual((larga.exception.codigo, larga.exception.campo), ("descripcion_larga", "descripcion"))

    def test_regla_la_fecha_de_la_merma_no_es_posterior_a_hoy(self):
        """«La fecha de la bitácora no puede ser posterior a hoy» (modelo): `fecha_invalida`, sin cambios."""
        lote = self.lote()
        with self.assertRaises(ErrorDeProduccion) as rechazo:
            self.aplicar(lote, 1, fecha=HOY + timedelta(days=1))
        self.assertEqual(rechazo.exception.codigo, "fecha_invalida")
        self.assertFalse(Merma.objects.exists())

    def test_post_c_con_por_sector_baja_los_agujeros_ocupados_de_cada_ocupacion_afectada(self):
        """Postcondición c (solo si viene `por_sector`, que pasa PRD-03): los agujeros ocupados de cada ocupación del lote bajan en
        lo perdido en ese sector; los demás no cambian."""
        lote = self.lote(cantidad=50)
        primera = OcupacionSector.objects.get(lote=lote, cant_agujeros_ocupados__gt=0)
        segunda = OcupacionSector.objects.create(
            orden=primera.orden, sector=self.e.sectores["floracion"], lote=lote, cant_agujeros_planificados=20, cant_agujeros_ocupados=20
        )
        OcupacionSector.objects.filter(pk=primera.pk).update(cant_agujeros_ocupados=30)
        self.aplicar(lote, 7, por_sector={primera.sector_id: 5, segunda.sector_id: 2})
        primera.refresh_from_db(), segunda.refresh_from_db()
        self.assertEqual((primera.cant_agujeros_ocupados, segunda.cant_agujeros_ocupados), (25, 18))

    def test_post_c_lo_perdido_por_sector_suma_la_cantidad_y_no_supera_lo_que_ocupa(self):
        """Con `por_sector`: la suma debe ser la cantidad perdida y ningún sector pierde más de lo que ocupa el lote ahí ni uno
        donde no tiene plantas: `cantidad_invalida`, sin cambios."""
        lote = self.lote(cantidad=50)
        propio = self.e.sectores["crecimiento"].pk
        ajeno = self.e.sectores["floracion"].pk
        for por_sector in ({propio: 3}, {propio: 51}, {ajeno: 5}, {propio: 4, ajeno: 1}):
            with self.subTest(por_sector=por_sector), self.assertRaises(ErrorDeProduccion) as rechazo:
                self.aplicar(lote, 5, por_sector=por_sector)
            self.assertEqual(rechazo.exception.codigo, "cantidad_invalida")
        self.assertEqual(OcupacionSector.objects.get(lote=lote, cant_agujeros_ocupados__gt=0).cant_agujeros_ocupados, 50)
        self.assertFalse(Merma.objects.exists())

    def test_post_c_desde_la_transicion_no_toca_ocupaciones_ni_sectores(self):
        """Extensión desde PROD-CNC-TRN: sin `por_sector` la merma no libera agujeros (los libera la transición, todos los de
        origen): las ocupaciones quedan igual aunque el lote pierda plantas."""
        lote = self.lote(cantidad=50)
        antes = list(OcupacionSector.objects.order_by("pk").values_list("pk", "cant_agujeros_ocupados"))
        self.aplicar(lote, 10)
        self.assertEqual(list(OcupacionSector.objects.order_by("pk").values_list("pk", "cant_agujeros_ocupados")), antes)

    def test_post_d_no_hay_movimiento_de_stock_en_la_ronda(self):
        """D-45: no existe `MovimientoStock` ni stock de plantas en la ronda; el núcleo no lo crea ni lo nombra (la «salida por
        merma» la suma COM-04a)."""
        resultado = self.aplicar(self.lote(), 1)
        self.assertEqual(set(resultado._fields), {"merma", "costo", "alertas"})


class MermaAcumuladaTests(BaseDeMermas):
    def test_regla_merma_acumulada_es_el_porcentaje_sobre_la_cantidad_inicial_sin_descarte_por_seleccion(self):
        """Regla «Merma acumulada de un lote»: Σ de las mermas del lote en pie ÷ cantidad inicial; el «descarte por selección» no
        suma; devuelve un `Decimal` en porcentaje con dos decimales (`ROUND_HALF_UP`)."""
        lote = self.lote(cantidad=3)
        self.assertEqual(mermas.merma_acumulada(lote), Decimal("0.00"))
        self.merma_previa(lote, 1)
        self.assertEqual(mermas.merma_acumulada(lote), Decimal("33.33"))
        self.merma_previa(lote, 1, causa="descarte_por_seleccion")
        self.assertEqual(mermas.merma_acumulada(lote), Decimal("33.33"))

    def test_regla_merma_acumulada_no_cuenta_las_mermas_sin_etapa_ni_las_de_otro_lote(self):
        """Regla 7 de 8.9: la merma acumulada cuenta solo las mermas con etapa (lote en pie, no las de cámara) y las de ESE lote."""
        lote, otro = self.lote(cantidad=10), self.lote(cantidad=10)
        self.merma_previa(lote, 2)
        self.merma_previa(lote, 4, con_etapa=False)
        self.merma_previa(otro, 5)
        self.assertEqual(mermas.merma_acumulada(lote), Decimal("20.00"))


class AlertaDeUmbralTests(BaseDeMermas):
    def test_post_k_cruza_el_umbral_y_alerta_al_agronomo_y_al_gerente_enlazada_a_la_merma(self):
        """Postcondición k y extensión 10b: si la merma acumulada supera el porcentaje máximo (15 %), alerta para el Agrónomo a
        cargo y para el Gerente, enlazada con la merma por `AlertaDeMerma`, con el lote y el porcentaje en la descripción."""
        lote = self.lote(cantidad=100)
        resultado = self.aplicar(lote, 16)
        alerta = self.alertas(UMBRAL).get()
        self.assertEqual(resultado.alertas, [alerta])
        self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (self.e.agronomo.pk, True))
        self.assertEqual(alerta.nivel_severidad, Alerta.Severidad.CRITICA)
        self.assertEqual(AlertaDeMerma.objects.get(alerta=alerta).merma_id, resultado.merma.pk)
        self.assertLessEqual(len(alerta.descripcion_alerta), 200)
        self.assertIn(lote.codigo, alerta.descripcion_alerta)
        self.assertIn("16,0 %", alerta.descripcion_alerta)
        self.assertIn("15 %", alerta.descripcion_alerta)

    def test_regla_umbral_exactamente_en_el_porcentaje_no_alerta_y_una_planta_mas_si(self):
        """Regla «Umbral de merma»: se alerta si la merma acumulada SUPERA el porcentaje (15 de 100 es 15 %: no); con una planta más
        sí."""
        lote = self.lote(cantidad=100)
        self.aplicar(lote, 15)
        self.assertFalse(self.alertas(UMBRAL).exists())
        self.aplicar(lote, 1)
        self.assertEqual(self.alertas(UMBRAL).count(), 1)

    def test_regla_umbral_se_cruza_una_sola_vez_por_lote(self):
        """Regla «Umbral de merma»: la alerta se genera una sola vez por lote; las mermas siguientes no crean otra."""
        lote = self.lote(cantidad=100)
        self.aplicar(lote, 20)
        self.aplicar(lote, 10)
        self.assertEqual(self.alertas(UMBRAL).count(), 1)
        self.assertEqual(AlertaDeMerma.objects.count(), 1)

    def test_regla_umbral_un_lote_ya_por_encima_sin_alerta_previa_la_recibe_aunque_cambie_la_configuracion(self):
        """Decisión del estudiante (22/11/2026): «supera el umbral y el lote no tuvo una alerta de umbral». Un lote con 20 de merma
        sin alerta (por ejemplo, el Gerente bajó el porcentaje después) la recibe con la próxima merma, y solo una vez."""
        lote = self.lote(cantidad=100)
        self.merma_previa(lote, 20)
        self.aplicar(lote, 1)
        self.assertEqual(self.alertas(UMBRAL).count(), 1)
        self.aplicar(lote, 1)
        self.assertEqual(self.alertas(UMBRAL).count(), 1)

    def test_regla_umbral_el_descarte_por_seleccion_no_suma_y_no_dispara(self):
        """Regla «Merma acumulada»: el descarte por selección no cuenta para el umbral aunque descarte el 50 % del lote; sí baja
        plantas y costo."""
        lote = self.lote(cantidad=100, costo="100.00")
        resultado = self.aplicar(lote, 50, causa="descarte_por_seleccion")
        self.assertFalse(self.alertas(UMBRAL).exists())
        self.assertEqual(resultado.alertas, [])
        self.assertEqual(mermas.merma_acumulada(lote), Decimal("0.00"))
        lote.refresh_from_db()
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado), (50, Decimal("50.00")))

    def test_regla_umbral_con_la_merma_acumulada_en_cero_no_alerta(self):
        """Borde: con la merma acumulada en 0 % (solo descarte por selección) no hay alerta, cualquiera sea el porcentaje máximo."""
        lote = self.lote(cantidad=10)
        self.aplicar(lote, 10, causa="descarte_por_seleccion", por_sector={self.e.sectores["crecimiento"].pk: 10})
        self.assertFalse(self.alertas().exists())

    def test_regla_umbral_usa_el_porcentaje_de_la_configuracion_operativa(self):
        """El porcentaje máximo sale de `ConfiguracionOperativa` (1 a 100): con el mínimo (1 %) una planta de 50 ya lo supera; con 100 %
        nunca se supera."""
        ConfiguracionOperativa.objects.update(porc_merma_maxima=100)
        lote = self.lote(cantidad=50)
        self.aplicar(lote, 49)
        self.assertFalse(self.alertas(UMBRAL).exists())
        ConfiguracionOperativa.objects.update(porc_merma_maxima=1)
        otro = self.lote(cantidad=50)
        self.aplicar(otro, 1)
        self.assertEqual(self.alertas(UMBRAL).count(), 1)

    def test_post_k_con_el_invernadero_inactivo_la_merma_se_registra_y_no_hay_alerta(self):
        """Post e de PROD-BAJ-INV: un invernadero inactivo no genera alertas (`crear_alerta_de_evento` da `None`): la merma se
        registra igual, sin alerta ni enlace."""
        lote = self.lote(cantidad=10)
        resultado = self.aplicar(lote, 9)
        self.assertEqual(len(resultado.alertas), 1)
        otro = self.lote(cantidad=10)
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        resultado = self.aplicar(otro, 9)
        self.assertEqual(resultado.alertas, [])
        self.assertEqual(AlertaDeMerma.objects.count(), 1)
        self.assertTrue(Merma.objects.filter(pk=resultado.merma.pk).exists())


class PlantasComprometidasTests(BaseDeMermas):
    """Condición 2 de la regla 15 de 8.8 (extensión 10a de PROD-REG-MRM): la transición «a realizar» del lote queda con más plantas
    planificadas que `cantidad_actual`. Desde Concretar Transición no puede dispararse (la orden que se concreta se excluye): se prueba
    LLAMANDO A LA FUNCIÓN con una transición ajena «a realizar», como pide la tarea."""

    def test_post_l_la_transicion_a_realizar_queda_con_menos_plantas_que_las_planificadas_y_alerta_al_agronomo(self):
        """Postcondición l: alerta para el Agrónomo a cargo (`AGRONOMO_O_GERENTE`: con Agrónomo activo, solo a él), enlazada con la
        merma, que nombra el lote, la transición y las dos cantidades."""
        lote = self.lote(cantidad=50)
        transicion = orden_de_transicion(self.e, lote)
        resultado = self.aplicar(lote, 5)
        alerta = self.alertas(COMPROMETIDAS).get()
        self.assertEqual(resultado.alertas, [alerta])
        self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (self.e.agronomo.pk, False))
        self.assertEqual(alerta.nivel_severidad, Alerta.Severidad.ADVERTENCIA)
        self.assertEqual(AlertaDeMerma.objects.get(alerta=alerta).merma_id, resultado.merma.pk)
        for texto in (lote.codigo, transicion.codigo, "45", "50"):
            self.assertIn(texto, alerta.descripcion_alerta)
        self.assertLessEqual(len(alerta.descripcion_alerta), 200)

    def test_regla_la_orden_excluida_no_cuenta_para_la_condicion_2(self):
        """Extensión 10a de CNC-TRN: se evalúa SIN contar la orden de transición que se está concretando (`ordenes_excluidas`):
        no hay alerta."""
        lote = self.lote(cantidad=50)
        transicion = orden_de_transicion(self.e, lote)
        self.aplicar(lote, 5, ordenes_excluidas=(transicion.pk,))
        self.assertFalse(self.alertas(COMPROMETIDAS).exists())

    def test_regla_sin_transicion_a_realizar_o_con_plantas_suficientes_no_alerta(self):
        """No alerta si el lote no tiene transición «a realizar» (una cancelada o concretada no cuenta), ni si lo que queda cubre lo
        planificado (planificadas 40, quedan 45)."""
        lote = self.lote(cantidad=50)
        orden_de_transicion(self.e, lote, estado="cancelada")
        self.aplicar(lote, 1)
        self.assertFalse(self.alertas(COMPROMETIDAS).exists())
        parcial = self.lote(cantidad=50)
        orden_de_transicion(self.e, parcial, distribucion={"floracion": 40})
        self.aplicar(parcial, 5)
        self.assertFalse(self.alertas(COMPROMETIDAS).exists())

    def test_regla_la_condicion_2_suma_los_agujeros_planificados_de_todos_los_sectores_destino(self):
        """Condición 2: la cantidad planificada es la suma de los agujeros planificados de las ocupaciones destino (50 = 30 + 20)."""
        lote = self.lote(cantidad=50)
        orden_de_transicion(self.e, lote, distribucion={"floracion": 30, "fructificacion": 20})
        self.aplicar(lote, 1)
        self.assertEqual(self.alertas(COMPROMETIDAS).count(), 1)

    def test_regla_las_dos_alertas_en_una_misma_merma(self):
        """Una merma puede cruzar el umbral y dejar la transición sin cobertura: las dos alertas, las dos enlazadas con la merma."""
        lote = self.lote(cantidad=100)
        orden_de_transicion(self.e, lote)
        resultado = self.aplicar(lote, 20)
        self.assertEqual(sorted(a.tipo_alerta for a in resultado.alertas), sorted([COMPROMETIDAS, UMBRAL]))
        self.assertEqual(AlertaDeMerma.objects.filter(merma=resultado.merma).count(), 2)


class ContratoDelNucleoTests(BaseDeMermas):
    def test_regla_corre_en_la_transaccion_del_llamador_y_sin_ella_lanza_runtime_error(self):
        """D-51 punto 5 y `docs/api/produccion.md`: es una función interna; sin transacción abierta lanza `RuntimeError` y no cambia
        nada."""
        lote = self.lote()
        with mock.patch.object(connections["default"], "in_atomic_block", False), self.assertRaises(RuntimeError):
            self.aplicar(lote, 1)
        self.assertFalse(Merma.objects.exists())

    def test_regla_no_audita_ni_notifica(self):
        """«No audita ni notifica: el CU que llama arma su único registro» (D-36, D-42)."""
        lote = self.lote(cantidad=100)
        orden_de_transicion(self.e, lote)
        auditoria, avisos = RegistroAuditoria.objects.count(), Notificacion.objects.count()
        self.aplicar(lote, 20)
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), (auditoria, avisos))

    def test_m_n_devuelve_lo_creado_para_el_registro_de_auditoria_del_llamador(self):
        """Postcondiciones m y n: el `ResultadoMerma` trae la merma, su costo y las alertas, para que el caso de uso las ponga en su
        único registro (`concrecion_transicion`)."""
        lote = self.lote(cantidad=100)
        resultado = self.aplicar(lote, 20)
        self.assertEqual(resultado.merma.cant_merma, 20)
        self.assertEqual(resultado.costo, Decimal("20.00"))
        self.assertEqual([a.tipo_alerta for a in resultado.alertas], [UMBRAL])

    def test_d51_la_firma_completa_acepta_por_sector_sector_ids_y_ordenes_excluidas_como_palabras_clave(self):
        """D-51 punto 5: PRD-03 (`por_sector`) y PRD-04 (`sector_ids`, `ordenes_excluidas`) la llaman sin reescribirla."""
        lote = self.lote(cantidad=10)
        sector = self.e.sectores["crecimiento"]
        resultado = mermas.aplicar_merma(
            lote, 2, "plaga", "", HOY, None, por_sector={sector.pk: 2}, sector_ids=(sector.pk,), ordenes_excluidas=()
        )
        self.assertIsNone(resultado.merma.responsable)  # InfoPonia
        self.assertEqual(list(resultado.merma.sectores.all()), [sector])


class RegistroDeLosTiposDeAlertaTests(TestCase):
    def test_ext_produccion_registra_los_dos_tipos_de_alerta_de_la_merma(self):
        """`docs/api/produccion.md`, sección 3: `produccion` registra `produccion_merma_umbral` (Agrónomo y Gerente, evento, origen
        merma) y `produccion_plantas_comprometidas` (Agrónomo o Gerente, evento, origen merma), con los nombres y severidades del
        prototipo (decisión del estudiante, 22/11/2026). Sin tocar `maestros/alertas.py`."""
        umbral = tipo_de_alerta(UMBRAL)
        self.assertEqual(
            (umbral.destinatario, umbral.clase, umbral.origen, umbral.severidad),
            (Destinatario.AGRONOMO_Y_GERENTE, Clase.EVENTO, Origen.MERMA, Alerta.Severidad.CRITICA),
        )
        self.assertEqual(umbral.nombre, "Merma sobre el umbral")
        comprometidas = tipo_de_alerta(COMPROMETIDAS)
        self.assertEqual(
            (comprometidas.destinatario, comprometidas.clase, comprometidas.origen, comprometidas.severidad),
            (Destinatario.AGRONOMO_O_GERENTE, Clase.EVENTO, Origen.MERMA, Alerta.Severidad.ADVERTENCIA),
        )
        self.assertEqual(comprometidas.nombre, "Plantas comprometidas por una transición")


class CuidadosDelNucleoTests(BaseDeMermas):
    def test_regla_la_descripcion_de_las_alertas_nunca_pasa_de_200_caracteres(self):
        """`Alerta.descripcion_alerta` admite 200: si el nombre de la variedad no entra, se acorta con «…» y el resto del texto queda
        completo (revisión del estudiante, 22/11/2026)."""
        mermas_internas = mermas
        texto = mermas_internas._acotar("L-3: merma de 16,0 % (", "V" * 400, "). Superó el 15 % tolerado.")
        self.assertEqual(len(texto), 200)
        self.assertTrue(texto.startswith("L-3: merma de 16,0 % (V"))
        self.assertTrue(texto.endswith("…). Superó el 15 % tolerado."))
        corto = mermas_internas._acotar("a (", "variedad", ").")
        self.assertEqual(corto, "a (variedad).")

    def test_post_c_si_el_lote_se_pierde_entero_las_ocupaciones_quedan_en_cero_y_conservan_su_lote(self):
        """Mismo criterio que la concreción de una transición (postcondición d de CNC-TRN): al llegar a cero las ocupaciones quedan con
        0 agujeros ocupados y siguen asociadas al lote (no se borran ni se desasocian)."""
        lote = self.lote(cantidad=10)
        ocupacion = OcupacionSector.objects.get(lote=lote, cant_agujeros_ocupados__gt=0)
        self.aplicar(lote, 10, por_sector={ocupacion.sector_id: 10})
        ocupacion.refresh_from_db()
        self.assertEqual((ocupacion.cant_agujeros_ocupados, ocupacion.lote_id), (0, lote.pk))
