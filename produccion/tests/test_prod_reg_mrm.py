# Pruebas de PROD-REG-MRM · Registrar Merma, solo de un lote en pie (PRD-03, paso 3; docs/casos_de_uso/produccion/merma.md, «Cómo se aplica en la
# ronda «Producción 1»»). Se escriben ANTES que el servicio y deben fallar; el estudiante las revisa antes de implementar.
#
# CONTRATO que fijan estas pruebas (para que el estudiante lo apruebe):
#
# produccion/servicios/alcance.py (nuevo, lo comparten merma, aplicación y evento):
# - invernaderos_del_actor(actor) -> list[Invernadero]: los invernaderos ACTIVOS que el actor puede usar para registrar: los que tiene a su cargo
#   (Agrónomo) o asignados (Capataz), por nombre. Cualquier otra cuenta, o una inactiva: lista vacía. Paso 2 de PROD-REG-MRM y de PROD-REG-APL.
#
# produccion/servicios/mermas.py (se agrega; el núcleo `aplicar_merma` y `merma_acumulada` de PRD-02 no cambian):
# - lotes_con_merma_posible(actor, invernadero_id) -> list[FilaDeLoteConMerma(lote_id, codigo, variedad, etapa, cantidad_actual)]: los lotes
#   ACTIVOS del invernadero (paso 4), por id. `[]` si no tiene (extensión 4b: la pantalla informa y ofrece otro invernadero o cancelar).
#   Http404 si el invernadero no existe; `sin_permiso` si no es del actor o el actor no es Capataz/Agrónomo activo; `invernadero_inactivo`.
# - datos_de_merma(actor, lote_id) -> PropuestaDeMerma(lote, variedad, etapa, invernadero, cantidad_actual, sectores=[FilaDeSectorConMerma(
#   sector_id, nombre, ocupados)], merma_acumulada, porcentaje_maximo, causas=[(valor, texto)]) (paso 6). Solo sectores con ocupación vigente;
#   las causas son las del lote en pie, incluido «descarte por selección». No escribe.
# - DatosDeMerma(lote_id, cantidades=((sector_id, plantas), ...), causa="", descripcion="", cantidad_actual=None, ocupados=None): lo que la
#   persona carga (paso 7) y VIO (`cantidad_actual` y `ocupados=((sector_id, ocupados), ...)`, para la extensión 10d; `None` no los verifica).
# - resumen_de_merma(actor, datos) -> ResumenDeMerma(lote, variedad, etapa, invernadero, por_sector=[(sector, plantas)], total, causa,
#   descripcion, cantidad_actual, cantidad_resultante, merma_acumulada_resultante, porcentaje_maximo, supera_umbral,
#   transiciones_sin_cobertura=[(orden, planificadas)], lote_finalizado) (paso 8). Valida TODO y no escribe ni bloquea.
# - registrar_merma(actor, datos) -> Merma: lo mismo, bajo bloqueos y repitiendo las verificaciones (10d), y escribe todo o nada con
#   `aplicar_merma(..., por_sector=...)`. UN registro de auditoría `registro_merma`.
#
# Códigos y campos de `ErrorDeProduccion`: sin_permiso; invernadero_inactivo; lote_no_activo (lote); cantidad_invalida (8a: campo
# `sector_<id>`, con `datos={"ocupados": n}`; 8b, total cero: campo `cantidad`); causa_obligatoria (8c); causa_invalida; descripcion_larga (300,
# D-83); cambio_simultaneo (10d, con `datos` = `cantidad_actual` y `ocupados` vigentes). La extensión 4b no es un error: es la lista vacía.
#
# Una prueba por regla y por postcondición a, b, c, e, k, l, m, n (la d y las f a j son de la cámara: fuera). CON-04a: la postcondición e (el
# asiento) se prueba en `RegistrarMermaAsientoTests`. El caso de uso
# dice «asocia al usuario» y «la fecha actual»: el responsable es quien actúa y la fecha es hoy.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import AsientoContable, EjercicioContable, MovimientoContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.tests.fabricas import PlanDeCuentasMixin, verificar_invariantes_contables
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, perezoso
from maestros.models import Alerta, ConfiguracionOperativa, Invernadero
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo, crear_invernadero, crear_sector
from produccion.errores import ErrorDeProduccion
from produccion.models import AlertaDeMerma, Bitacora, Lote, Merma, OcupacionSector
from produccion.tests.fabricas import invernadero_con_produccion, lote_con_ciclo, orden_de_transicion
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

alcance = perezoso("produccion.servicios.alcance")
mermas = perezoso("produccion.servicios.mermas")

HOY = timezone.localdate()
UMBRAL = "produccion_merma_umbral"
COMPROMETIDAS = "produccion_plantas_comprometidas"


def rechazo(llamada):
    """Ejecuta `llamada()` y devuelve el `ErrorDeProduccion` que lanza; si no lanza ninguno, la prueba falla."""
    try:
        llamada()
    except ErrorDeProduccion as error:
        return error
    raise AssertionError("Se esperaba un ErrorDeProduccion y no se lanzó ninguno.")


class Base(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento
        cls.e = invernadero_con_produccion()

    def lote(self, cantidad=100, costo="100.00", etapa="crecimiento"):
        """Un lote activo de `cantidad` plantas en `etapa`, con una sola ocupación en el sector de esa etapa."""
        return lote_con_ciclo(self.e, cantidad=cantidad, costo=costo, etapa=etapa)

    def lote_en_dos_sectores(self, en_uno=60, en_otro=40, costo="100.00"):
        """Un lote de `en_uno + en_otro` plantas repartido en el sector «crecimiento» y en otro sector de crecimiento. Devuelve
        `(lote, sector_uno, sector_otro)`."""
        lote = self.lote(cantidad=en_uno + en_otro, costo=costo)
        uno = self.e.sectores["crecimiento"]
        otro = crear_sector(self.e.invernadero, nombre="Crecimiento 2", tipo="crecimiento", agujeros=100)
        ocupacion = OcupacionSector.objects.get(lote=lote, sector=uno, cant_agujeros_ocupados__gt=0)
        OcupacionSector.objects.filter(pk=ocupacion.pk).update(cant_agujeros_ocupados=en_uno)
        OcupacionSector.objects.create(
            orden_id=ocupacion.orden_id, sector=otro, lote=lote, cant_agujeros_planificados=en_otro, cant_agujeros_ocupados=en_otro
        )
        return lote, uno, otro

    def datos(self, lote, cantidades=None, **cambios):
        """`DatosDeMerma` válidos: 5 plantas del sector de crecimiento por plaga (o las `cantidades` `{sector: plantas}`)."""
        cantidades = cantidades if cantidades is not None else {self.e.sectores["crecimiento"]: 5}
        base = dict(
            lote_id=lote.pk,
            cantidades=tuple((sector.pk, plantas) for sector, plantas in cantidades.items()),
            causa="plaga",
            descripcion="",
        )
        base.update(cambios)
        return mermas.DatosDeMerma(**base)

    def registrar(self, lote, cantidades=None, actor=None, **cambios):
        return mermas.registrar_merma(actor or self.e.capataz, self.datos(lote, cantidades, **cambios))

    def nada_se_escribio(self, lote):
        """Verifica el todo o nada: ninguna merma, ninguna alerta, ninguna auditoría y el lote igual."""
        self.assertFalse(Merma.objects.exists())
        self.assertFalse(Alerta.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.filter(accion="registro_merma").exists())
        despues = Lote.objects.get(pk=lote.pk)
        self.assertEqual((despues.cantidad_actual, despues.costo_acumulado), (lote.cantidad_actual, lote.costo_acumulado))


class AlcanceTests(Base):
    """Paso 2 y regla «Ámbito del actor»."""

    def test_regla_ambito_el_capataz_ve_solo_sus_invernaderos_activos_y_el_agronomo_los_que_tiene_a_cargo(self):
        """Regla «Ámbito del actor» (pasos 2 y 4): el Capataz, los asignados; el Agrónomo, los que tiene a su cargo; solo los activos."""
        otro = crear_invernadero("Otro", agronomo=crear_agronomo(email="otro@infoponia.com"), capataz=crear_capataz_activo(email="otro.c@infoponia.com"))
        self.assertEqual([i.pk for i in alcance.invernaderos_del_actor(self.e.capataz)], [self.e.invernadero.pk])
        self.assertEqual([i.pk for i in alcance.invernaderos_del_actor(self.e.agronomo)], [self.e.invernadero.pk])
        self.assertEqual([i.pk for i in alcance.invernaderos_del_actor(otro.capataz)], [otro.pk])

    def test_regla_ambito_el_gerente_y_las_cuentas_inactivas_no_tienen_invernaderos_para_registrar(self):
        """Regla «Ámbito del actor»: solo Capataz y Agrónomo; una cuenta inactiva, ninguno."""
        self.assertEqual(alcance.invernaderos_del_actor(crear_gerente()), [])
        self.e.capataz.is_active = False
        self.e.capataz.save()
        self.assertEqual(alcance.invernaderos_del_actor(self.e.capataz), [])

    def test_regla_ambito_un_invernadero_inactivo_no_se_ofrece(self):
        """Regla 4 de PROD-BAJ-INV: un invernadero inactivo no aparece en las operaciones nuevas."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(alcance.invernaderos_del_actor(self.e.agronomo), [])
        self.assertEqual(alcance.invernaderos_del_actor(self.e.capataz), [])


class LotesConMermaPosibleTests(Base):
    """Pasos 4 y extensión 4b."""

    def test_paso_4_lista_los_lotes_activos_con_variedad_etapa_y_cantidad_actual(self):
        """Paso 4: los lotes activos del invernadero, indicando variedad, etapa productiva actual y cantidad actual."""
        uno, otro = self.lote(cantidad=30), self.lote(cantidad=20)
        filas = mermas.lotes_con_merma_posible(self.e.capataz, self.e.invernadero.pk)
        self.assertEqual([f.lote_id for f in filas], [uno.pk, otro.pk])
        self.assertEqual((filas[0].codigo, filas[0].cantidad_actual), (uno.codigo, 30))
        self.assertEqual(filas[0].variedad, str(self.e.variedad))
        self.assertEqual(filas[0].etapa, uno.etapa.tipo_etapa.nombre_etapa)

    def test_paso_4_no_ofrece_los_lotes_finalizados(self):
        """Paso 4 y precondición b: solo los lotes en estado «activo»."""
        activo, terminado = self.lote(cantidad=30), self.lote(cantidad=20)
        Lote.objects.filter(pk=terminado.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)
        self.assertEqual([f.lote_id for f in mermas.lotes_con_merma_posible(self.e.agronomo, self.e.invernadero.pk)], [activo.pk])

    def test_ext_4b_sin_lotes_activos_devuelve_la_lista_vacia(self):
        """Extensión 4b: el invernadero sin lotes activos no es un error: la lista vacía, y la pantalla lo informa (formulario deshabilitado)."""
        self.assertEqual(mermas.lotes_con_merma_posible(self.e.capataz, self.e.invernadero.pk), [])

    def test_regla_ambito_un_invernadero_ajeno_se_rechaza_y_uno_inexistente_es_404(self):
        """Regla «Ámbito del actor»: el Capataz solo accede a los invernaderos asignados (`sin_permiso`); uno que no existe, 404."""
        otro = crear_invernadero("Otro", agronomo=crear_agronomo(email="otro@infoponia.com"))
        self.assertEqual(rechazo(lambda: mermas.lotes_con_merma_posible(self.e.capataz, otro.pk)).codigo, "sin_permiso")
        self.assertEqual(rechazo(lambda: mermas.lotes_con_merma_posible(crear_gerente(), self.e.invernadero.pk)).codigo, "sin_permiso")
        with self.assertRaises(Http404):
            mermas.lotes_con_merma_posible(self.e.capataz, 999999)

    def test_regla_un_invernadero_sin_capataz_activo_igual_admite_al_agronomo(self):
        """Decisión de aplicación: un invernadero sin Capataz activo igual admite que el Agrónomo registre una merma."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(capataz=None)
        lote = self.lote(cantidad=30)
        filas = mermas.lotes_con_merma_posible(self.e.agronomo, self.e.invernadero.pk)
        self.assertEqual([f.lote_id for f in filas], [lote.pk])

    def test_regla_invernadero_inactivo_se_rechaza(self):
        """Regla 4 de PROD-BAJ-INV: un invernadero inactivo no admite operaciones nuevas."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(rechazo(lambda: mermas.lotes_con_merma_posible(self.e.capataz, self.e.invernadero.pk)).codigo, "invernadero_inactivo")


class DatosDeMermaTests(Base):
    """Paso 6: lo que presenta la pantalla."""

    def test_paso_6_presenta_la_cantidad_los_sectores_con_ocupaciones_vigentes_y_la_merma_acumulada(self):
        """Paso 6: la cantidad actual del lote, los sectores donde tiene ocupaciones vigentes con los agujeros ocupados y la merma
        acumulada (sobre la cantidad inicial, sin el descarte por selección); el porcentaje máximo de la configuración."""
        lote, uno, otro = self.lote_en_dos_sectores(60, 40)
        Merma.objects.create(
            invernadero=lote.invernadero, lote=lote, etapa=lote.etapa, tipo_evento="merma", fecha_bitacora=HOY,
            hora_bitacora=timezone.localtime().time(), cant_merma=10, causa="plaga",
        )
        propuesta = mermas.datos_de_merma(self.e.capataz, lote.pk)
        self.assertEqual(propuesta.cantidad_actual, 100)
        self.assertEqual({(f.sector_id, f.ocupados) for f in propuesta.sectores}, {(uno.pk, 60), (otro.pk, 40)})
        self.assertEqual(propuesta.merma_acumulada, Decimal("10.00"))
        self.assertEqual(propuesta.porcentaje_maximo, ConfiguracionOperativa.objects.get().porc_merma_maxima)

    def test_paso_6_no_lista_los_sectores_sin_ocupacion_vigente(self):
        """Paso 6 y regla «Cantidad válida»: solo los sectores donde el lote tiene agujeros ocupados mayores que cero."""
        lote = self.lote(cantidad=50)
        self.assertEqual([f.sector_id for f in mermas.datos_de_merma(self.e.capataz, lote.pk).sectores], [self.e.sectores["crecimiento"].pk])
        # la ocupación de origen (germinación) quedó en cero tras la transición: no se ofrece
        self.assertGreater(OcupacionSector.objects.filter(lote=lote, cant_agujeros_ocupados=0).count(), 0)

    def test_regla_causa_ofrece_las_del_lote_en_pie_incluido_el_descarte_por_seleccion(self):
        """Regla «Causa»: plaga, enfermedad, falla de riego o nutrientes, condiciones ambientales, daño mecánico, descarte por selección y otra."""
        valores = [v for v, _ in mermas.datos_de_merma(self.e.capataz, self.lote().pk).causas]
        self.assertEqual(valores, list(Merma.CAUSAS_EN_PIE))  # COM-04a: `Merma.Causa` suma tres de cámara y entrega
        self.assertIn("descarte_por_seleccion", valores)

    def test_regla_ambito_lote_ajeno_sin_permiso_inexistente_404_y_finalizado_se_rechaza(self):
        """Regla «Ámbito del actor»; extensión 4b y precondición b: un lote ajeno es `sin_permiso`; uno inexistente, 404; uno finalizado, `lote_no_activo`."""
        lote = self.lote()
        self.assertEqual(rechazo(lambda: mermas.datos_de_merma(crear_gerente(), lote.pk)).codigo, "sin_permiso")
        with self.assertRaises(Http404):
            mermas.datos_de_merma(self.e.capataz, 999999)
        Lote.objects.filter(pk=lote.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)
        error = rechazo(lambda: mermas.datos_de_merma(self.e.capataz, lote.pk))
        self.assertEqual((error.codigo, error.campo), ("lote_no_activo", "lote"))


class ResumenDeMermaTests(Base):
    """Paso 8: el resumen no escribe y valida lo mismo que registrar."""

    def test_paso_8_resume_el_lote_las_plantas_por_sector_el_total_la_causa_y_la_cantidad_resultante(self):
        """Paso 8: lote, variedad, plantas perdidas por sector y en total, causa, cantidad actual resultante; sin escribir nada."""
        lote, uno, otro = self.lote_en_dos_sectores(60, 40)
        resumen = mermas.resumen_de_merma(self.e.capataz, self.datos(lote, {uno: 7, otro: 3}, causa="enfermedad", descripcion="Hongo"))
        self.assertEqual((resumen.total, resumen.cantidad_actual, resumen.cantidad_resultante), (10, 100, 90))
        self.assertEqual({(s.pk, p) for s, p in resumen.por_sector if p}, {(uno.pk, 7), (otro.pk, 3)})
        self.assertEqual((resumen.causa, resumen.descripcion, resumen.lote.pk), ("enfermedad", "Hongo", lote.pk))
        self.assertFalse(resumen.lote_finalizado)
        self.nada_se_escribio(lote)

    def test_paso_8_advierte_cuando_supera_el_umbral_y_no_cuenta_el_descarte(self):
        """Paso 8: advertencia de umbral superado (merma acumulada resultante sobre el máximo). El descarte por selección no suma."""
        lote = self.lote(cantidad=100)
        resumen = mermas.resumen_de_merma(self.e.capataz, self.datos(lote, {self.e.sectores["crecimiento"]: 16}))
        self.assertTrue(resumen.supera_umbral)
        self.assertEqual(resumen.merma_acumulada_resultante, Decimal("16.00"))
        descarte = mermas.resumen_de_merma(self.e.capataz, self.datos(lote, {self.e.sectores["crecimiento"]: 50}, causa="descarte_por_seleccion"))
        self.assertFalse(descarte.supera_umbral)
        self.assertEqual(descarte.merma_acumulada_resultante, Decimal("0.00"))

    def test_paso_8_advierte_la_transicion_que_queda_sin_cobertura(self):
        """Paso 8: advertencia de plantas comprometidas (condición 2): la transición «a realizar» queda con más plantas planificadas que las
        actuales; informa la orden y lo planificado."""
        lote = self.lote(cantidad=50)
        transicion = orden_de_transicion(self.e, lote)
        resumen = mermas.resumen_de_merma(self.e.capataz, self.datos(lote, {self.e.sectores["crecimiento"]: 5}))
        self.assertEqual([(o.pk, planificadas) for o, planificadas in resumen.transiciones_sin_cobertura], [(transicion.pk, 50)])

    def test_paso_8_si_pierde_todo_el_lote_avisa_que_quedara_finalizado(self):
        """Postcondición b: con la cantidad actual en cero el lote queda finalizado: el resumen lo anticipa."""
        lote = self.lote(cantidad=10)
        resumen = mermas.resumen_de_merma(self.e.capataz, self.datos(lote, {self.e.sectores["crecimiento"]: 10}))
        self.assertTrue(resumen.lote_finalizado)
        self.assertEqual(resumen.cantidad_resultante, 0)

    def test_paso_8_valida_igual_que_registrar(self):
        """Pasos 8 y 10: el resumen rechaza con el mismo código y campo que `registrar_merma` (sin causa)."""
        lote = self.lote()
        error = rechazo(lambda: mermas.resumen_de_merma(self.e.capataz, self.datos(lote, causa="")))
        self.assertEqual((error.codigo, error.campo), ("causa_obligatoria", "causa"))


class RegistrarMermaTests(Base):
    def test_flujo_principal_el_capataz_registra_una_merma_de_un_sector(self):
        """Flujo principal (pasos 1 a 11): devuelve la merma, que queda en la bitácora del lote."""
        lote = self.lote(cantidad=100)
        merma = self.registrar(lote, {self.e.sectores["crecimiento"]: 12}, descripcion="Pulgón en la hilera 3")
        self.assertIsInstance(merma, Merma)
        self.assertEqual(Merma.objects.get().pk, merma.pk)

    def test_post_a_la_merma_queda_en_la_bitacora_con_el_responsable_la_etapa_actual_y_la_fecha_y_hora_de_hoy(self):
        """Postcondición a: registro de bitácora tipo «merma» con la cantidad, la causa, la descripción, el lote, su etapa ACTUAL, el
        invernadero, los sectores con pérdidas, la fecha y hora actuales y el usuario responsable."""
        lote = self.lote(cantidad=100)
        antes = timezone.localtime().time()
        merma = self.registrar(lote, {self.e.sectores["crecimiento"]: 12}, causa="plaga", descripcion="Pulgón")
        despues = timezone.localtime().time()
        guardada = Merma.objects.get(pk=merma.pk)
        self.assertEqual(guardada.tipo_evento, "merma")
        self.assertEqual((guardada.cant_merma, guardada.causa), (12, "plaga"))
        self.assertEqual((guardada.lote_id, guardada.etapa_id, guardada.invernadero_id), (lote.pk, lote.etapa_id, self.e.invernadero.pk))
        self.assertEqual((guardada.responsable_id, guardada.fecha_bitacora), (self.e.capataz.pk, HOY))
        self.assertTrue(antes <= guardada.hora_bitacora <= despues)
        self.assertEqual([s.pk for s in guardada.sectores.all()], [self.e.sectores["crecimiento"].pk])
        self.assertEqual(guardada.descripcion_evento, "Merma de 12 plantas por plaga. Pulgón")

    def test_post_a_el_agronomo_tambien_registra_y_queda_como_responsable(self):
        """MD-77 (resuelto): cuando el Agrónomo registra, él es el responsable del registro de bitácora."""
        lote = self.lote(cantidad=100)
        merma = self.registrar(lote, actor=self.e.agronomo)
        self.assertEqual(Merma.objects.get(pk=merma.pk).responsable_id, self.e.agronomo.pk)

    def test_post_a_solo_los_sectores_con_perdidas_quedan_en_la_bitacora(self):
        """Regla «Valores propuestos» y D-51 punto 2: los sectores de la bitácora son los afectados; un sector con 0 no figura."""
        lote, uno, otro = self.lote_en_dos_sectores(60, 40)
        merma = self.registrar(lote, {uno: 0, otro: 4})
        self.assertEqual([s.pk for s in Merma.objects.get(pk=merma.pk).sectores.all()], [otro.pk])

    def test_post_b_baja_la_cantidad_actual_y_el_costo_total_pero_no_el_costo_por_planta(self):
        """Postcondición b y patrón del costo: la cantidad baja en lo perdido y el costo acumulado (no el unitario) en lo perdido × costo por planta."""
        lote = self.lote(cantidad=200, costo="1000.00")
        self.registrar(lote, {self.e.sectores["crecimiento"]: 20})
        lote.refresh_from_db()
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado), (180, Decimal("900.00")))
        self.assertEqual(lote.costo_acumulado / lote.cantidad_actual, Decimal("5"))

    def test_post_b_si_la_cantidad_llega_a_cero_el_lote_queda_finalizado_con_costo_cero(self):
        """Postcondición b: con la cantidad actual en cero, estado «finalizado» y costo 0; las ocupaciones quedan en 0 y conservan el lote."""
        lote = self.lote(cantidad=10, costo="10.01")
        self.registrar(lote, {self.e.sectores["crecimiento"]: 10})
        lote.refresh_from_db()
        self.assertEqual((lote.cantidad_actual, lote.estado_lote, lote.costo_acumulado), (0, Lote.Estado.FINALIZADO, Decimal("0.00")))
        self.assertFalse(OcupacionSector.objects.filter(lote=lote, cant_agujeros_ocupados__gt=0).exists())
        self.assertTrue(OcupacionSector.objects.filter(lote=lote).exists())

    def test_post_c_baja_los_agujeros_ocupados_de_cada_sector_afectado_y_libera_esos_agujeros(self):
        """Postcondición c: en cada sector afectado los agujeros ocupados bajan en las plantas perdidas ahí y los libres suben en lo mismo."""
        lote, uno, otro = self.lote_en_dos_sectores(60, 40)
        libres_antes = {s.pk: s.cant_agujeros_total - sum(o.cant_agujeros_ocupados for o in OcupacionSector.objects.filter(sector=s)) for s in (uno, otro)}
        self.registrar(lote, {uno: 7, otro: 3})
        ocupados = {o.sector_id: o.cant_agujeros_ocupados for o in OcupacionSector.objects.filter(lote=lote, cant_agujeros_ocupados__gt=0)}
        self.assertEqual(ocupados, {uno.pk: 53, otro.pk: 37})
        libres_despues = {s.pk: s.cant_agujeros_total - sum(o.cant_agujeros_ocupados for o in OcupacionSector.objects.filter(sector=s)) for s in (uno, otro)}
        self.assertEqual((libres_despues[uno.pk] - libres_antes[uno.pk], libres_despues[otro.pk] - libres_antes[otro.pk]), (7, 3))

    def test_regla_cantidad_valida_la_suma_de_los_sectores_es_la_cantidad_actual_menos_lo_perdido(self):
        """Regla «Cantidad válida»: la suma de los agujeros ocupados de las ocupaciones vigentes sigue igual a la cantidad actual (invariante)."""
        lote, uno, otro = self.lote_en_dos_sectores(60, 40)
        self.registrar(lote, {uno: 10, otro: 5})
        lote.refresh_from_db()
        suma = sum(o.cant_agujeros_ocupados for o in OcupacionSector.objects.filter(lote=lote))
        self.assertEqual((lote.cantidad_actual, suma), (85, 85))

    def test_ext_8a_una_cantidad_mayor_a_lo_ocupado_en_el_sector_se_rechaza_con_los_agujeros_ocupados(self):
        """Extensión 8a: la cantidad de un sector supera los agujeros ocupados por el lote ahí: error en el campo del sector, con lo ocupado."""
        lote, uno, otro = self.lote_en_dos_sectores(60, 40)
        error = rechazo(lambda: self.registrar(lote, {uno: 61}))
        self.assertEqual((error.codigo, error.campo, error.datos["ocupados"]), ("cantidad_invalida", f"sector_{uno.pk}", 60))
        self.nada_se_escribio(lote)

    def test_ext_8a_un_sector_donde_el_lote_no_tiene_plantas_o_una_cantidad_negativa_se_rechazan(self):
        """Extensión 8a y regla «Cantidad válida»: un sector ajeno al lote (ocupados 0) no admite plantas; una cantidad negativa tampoco."""
        lote = self.lote(cantidad=50)
        ajeno = self.e.sectores["maduracion"]
        error = rechazo(lambda: self.registrar(lote, {ajeno: 1}))
        self.assertEqual((error.codigo, error.campo, error.datos["ocupados"]), ("cantidad_invalida", f"sector_{ajeno.pk}", 0))
        error = rechazo(lambda: self.registrar(lote, {self.e.sectores["crecimiento"]: -1}))
        self.assertEqual(error.codigo, "cantidad_invalida")
        self.nada_se_escribio(lote)

    def test_ext_8b_un_total_de_cero_plantas_se_rechaza(self):
        """Extensión 8b: la merma debe ser de al menos una planta: con todos los sectores en 0 (o sin cantidades), error en `cantidad`."""
        lote = self.lote(cantidad=50)
        for cantidades in ({self.e.sectores["crecimiento"]: 0}, {}):
            error = rechazo(lambda: self.registrar(lote, cantidades))
            self.assertEqual((error.codigo, error.campo), ("cantidad_invalida", "cantidad"))
        self.nada_se_escribio(lote)

    def test_ext_8c_sin_causa_se_rechaza(self):
        """Extensión 8c: la causa es obligatoria."""
        lote = self.lote()
        error = rechazo(lambda: self.registrar(lote, causa=""))
        self.assertEqual((error.codigo, error.campo), ("causa_obligatoria", "causa"))
        self.nada_se_escribio(lote)

    def test_regla_causa_una_de_camara_o_de_otra_ronda_no_vale_en_un_lote_en_pie(self):
        """Regla «Causa»: en un lote en pie no valen «daño en cámara», «vencimiento en cámara» ni «daño en la entrega» (D-83: `causa_invalida`)."""
        lote = self.lote()
        for causa in ("dano_en_camara", "vencimiento_en_camara", "dano_en_entrega", "inventada"):
            self.assertEqual(rechazo(lambda: self.registrar(lote, causa=causa)).codigo, "causa_invalida")
        self.nada_se_escribio(lote)

    def test_regla_causa_el_descarte_por_seleccion_se_acepta_baja_plantas_y_costo_y_no_suma_a_la_merma_acumulada(self):
        """Regla «Causa» y «Merma acumulada» (MD-78): el descarte por selección es válido en un lote en pie, baja plantas y costo, pero no
        suma al umbral ni dispara su alerta."""
        lote = self.lote(cantidad=100, costo="100.00")
        self.registrar(lote, {self.e.sectores["crecimiento"]: 50}, causa="descarte_por_seleccion")
        lote.refresh_from_db()
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado), (50, Decimal("50.00")))
        self.assertEqual(mermas.merma_acumulada(lote), Decimal("0.00"))
        self.assertFalse(Alerta.objects.filter(tipo_alerta=UMBRAL).exists())

    def test_regla_la_descripcion_admite_hasta_300_caracteres(self):
        """D-83: la descripción libre admite hasta 300 caracteres; con 301, `descripcion_larga` en el campo `descripcion`."""
        lote = self.lote()
        self.registrar(lote, descripcion="a" * 300)
        error = rechazo(lambda: self.registrar(lote, descripcion="a" * 301))
        self.assertEqual((error.codigo, error.campo), ("descripcion_larga", "descripcion"))

    def test_regla_la_fecha_es_la_de_hoy_sin_importar_lo_que_se_envie(self):
        """Regla «Fecha» (decisiones de aplicación): la merma de este caso de uso es siempre de hoy; no hay fecha retroactiva ni campo para ella."""
        lote = self.lote()
        merma = self.registrar(lote)
        self.assertEqual(Merma.objects.get(pk=merma.pk).fecha_bitacora, HOY)
        self.assertNotIn("fecha", [campo for campo in mermas.DatosDeMerma.__dataclass_fields__])

    def test_post_k_cruzar_el_umbral_alerta_una_sola_vez_al_agronomo_y_al_gerente_enlazada_a_la_merma(self):
        """Postcondición k y extensión 10b: la merma acumulada pasa de 15 % → alerta para el Agrónomo a cargo y el Gerente, enlazada con la
        merma; una segunda merma por encima del umbral no crea otra."""
        crear_gerente()
        lote = self.lote(cantidad=100)
        primera = self.registrar(lote, {self.e.sectores["crecimiento"]: 16})
        alerta = Alerta.objects.get(tipo_alerta=UMBRAL)
        self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (self.e.agronomo.pk, True))
        self.assertEqual(AlertaDeMerma.objects.get(alerta=alerta).merma_id, primera.pk)
        self.registrar(lote, {self.e.sectores["crecimiento"]: 5})
        self.assertEqual(Alerta.objects.filter(tipo_alerta=UMBRAL).count(), 1)

    def test_post_k_con_el_porcentaje_maximo_en_el_borde_no_alerta_y_con_una_planta_mas_si(self):
        """Regla «Umbral de merma»: se alerta al SUPERAR el porcentaje (15 de 100 es 15 %: no); con una planta más, sí."""
        lote = self.lote(cantidad=100)
        self.registrar(lote, {self.e.sectores["crecimiento"]: 15})
        self.assertFalse(Alerta.objects.filter(tipo_alerta=UMBRAL).exists())
        self.registrar(lote, {self.e.sectores["crecimiento"]: 1})
        self.assertEqual(Alerta.objects.filter(tipo_alerta=UMBRAL).count(), 1)

    def test_post_k_con_el_porcentaje_maximo_en_uno_una_planta_de_cincuenta_ya_lo_supera(self):
        """Regla «Umbral de merma»: usa el porcentaje de la configuración operativa (mínimo 1 %): una planta de 50 es 2 %."""
        ConfiguracionOperativa.objects.update(porc_merma_maxima=1)
        lote = self.lote(cantidad=50)
        self.registrar(lote, {self.e.sectores["crecimiento"]: 1})
        self.assertEqual(Alerta.objects.filter(tipo_alerta=UMBRAL).count(), 1)

    def test_post_l_una_transicion_a_realizar_ajena_queda_sin_cobertura_y_alerta_al_agronomo(self):
        """Postcondición l y extensión 10a, condición 2 (de punta a punta, disparador de PRD-02): el lote tiene una transición «a realizar» de 50
        plantas y la merma lo deja con 45: alerta de plantas comprometidas para el Agrónomo, enlazada con la merma."""
        lote = self.lote(cantidad=50)
        transicion = orden_de_transicion(self.e, lote)
        merma = self.registrar(lote, {self.e.sectores["crecimiento"]: 5})
        alerta = Alerta.objects.get(tipo_alerta=COMPROMETIDAS)
        self.assertEqual(alerta.agronomo_id, self.e.agronomo.pk)
        self.assertEqual(AlertaDeMerma.objects.get(alerta=alerta).merma_id, merma.pk)
        self.assertIn(transicion.codigo, alerta.descripcion_alerta)

    def test_post_l_sin_transicion_a_realizar_no_hay_alerta_de_plantas_comprometidas(self):
        """Postcondición l: sin transición «a realizar» (o con plantas suficientes) no se alerta; la merma no se bloquea."""
        lote = self.lote(cantidad=50)
        self.registrar(lote, {self.e.sectores["crecimiento"]: 5})
        self.assertFalse(Alerta.objects.filter(tipo_alerta=COMPROMETIDAS).exists())

    def test_regla_no_hay_notificaciones_ni_avisos_al_capataz_ni_al_agronomo(self):
        """Decisión de aplicación: «No hay notificaciones (el caso de uso solo habla de alertas)»."""
        lote = self.lote(cantidad=100)
        self.registrar(lote, {self.e.sectores["crecimiento"]: 5})
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_post_m_n_un_solo_registro_de_auditoria_con_la_merma_el_lote_las_ocupaciones_los_sectores_y_las_alertas(self):
        """Postcondiciones m y n y D-36: UN registro `registro_merma` con quien actuó, la merma, el lote, las ocupaciones y los sectores
        afectados (agujeros ocupados antes → después, como texto), el cambio de cantidad y de costo del lote y las alertas creadas."""
        lote, uno, otro = self.lote_en_dos_sectores(60, 40, costo="100.00")
        ocupaciones = list(OcupacionSector.objects.filter(lote=lote, cant_agujeros_ocupados__gt=0))
        self.registrar(lote, {uno: 16, otro: 0})
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_merma").count(), 1)
        registro = RegistroAuditoria.objects.get(accion="registro_merma")
        self.assertEqual(registro.usuario_id, self.e.capataz.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        esperados = {("produccion.merma", Merma.objects.get().pk), ("produccion.lote", lote.pk), ("maestros.sectorproduccion", uno.pk)}
        esperados |= {("produccion.ocupacionsector", o.pk) for o in ocupaciones if o.sector_id == uno.pk}
        alerta = Alerta.objects.get(tipo_alerta=UMBRAL)
        esperados.add(("maestros.alerta", alerta.pk))
        self.assertTrue(esperados <= afectados, esperados - afectados)
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["cantidad_actual"], {"antes": "100", "despues": "84"})
        self.assertEqual(cambios["costo_acumulado"], {"antes": "100.00", "despues": "84.00"})
        self.assertEqual(
            cambios["agujeros_ocupados"],
            {"antes": [f"{uno.nombre_sector}: 60"], "despues": [f"{uno.nombre_sector}: 44"]},
        )

    def test_post_m_n_un_lote_que_se_finaliza_deja_su_cambio_de_estado_en_la_auditoria(self):
        """Postcondición n: el cambio de valor del lote incluye su estado cuando pasa a «finalizado»."""
        lote = self.lote(cantidad=10)
        self.registrar(lote, {self.e.sectores["crecimiento"]: 10})
        cambios = RegistroAuditoria.objects.get(accion="registro_merma").detalle["cambios"]
        self.assertEqual(cambios["estado"], {"antes": "activo", "despues": "finalizado"})

    def test_regla_la_consulta_previa_no_audita_y_registrar_no_audita_dos_veces(self):
        """D-36: un registro por caso de uso: datos, lotes y resumen no escriben auditoría; registrar escribe exactamente uno."""
        lote = self.lote()
        mermas.lotes_con_merma_posible(self.e.capataz, self.e.invernadero.pk)
        mermas.datos_de_merma(self.e.capataz, lote.pk)
        mermas.resumen_de_merma(self.e.capataz, self.datos(lote))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_merma").count(), 0)
        self.registrar(lote)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_merma").count(), 1)


class PermisosYEstadoTests(Base):
    def test_regla_ambito_un_capataz_de_otro_invernadero_se_rechaza_sin_escribir(self):
        """Regla «Ámbito del actor»: el Capataz solo registra mermas en los invernaderos que tiene asignados."""
        lote = self.lote()
        ajeno = crear_capataz_activo(email="ajeno@infoponia.com")
        self.assertEqual(rechazo(lambda: self.registrar(lote, actor=ajeno)).codigo, "sin_permiso")
        self.nada_se_escribio(lote)

    def test_regla_ambito_un_agronomo_de_otro_invernadero_y_el_gerente_se_rechazan(self):
        """Regla «Ámbito del actor»: el Agrónomo registra en los invernaderos a su cargo; el Gerente no registra mermas."""
        lote = self.lote()
        for actor in (crear_agronomo(email="otro@infoponia.com"), crear_gerente()):
            self.assertEqual(rechazo(lambda: self.registrar(lote, actor=actor)).codigo, "sin_permiso")
        self.nada_se_escribio(lote)

    def test_regla_una_cuenta_inactiva_se_rechaza(self):
        """Precondición a: el actor está autenticado con una cuenta activa."""
        lote = self.lote()
        actor = self.e.capataz
        actor.is_active = False
        actor.save()
        self.assertEqual(rechazo(lambda: self.registrar(lote, actor=actor)).codigo, "sin_permiso")
        self.nada_se_escribio(lote)

    def test_regla_un_lote_finalizado_se_rechaza(self):
        """Precondición b: solo un lote «activo» admite una merma."""
        lote = self.lote()
        Lote.objects.filter(pk=lote.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)
        error = rechazo(lambda: self.registrar(lote))
        self.assertEqual((error.codigo, error.campo), ("lote_no_activo", "lote"))

    def test_regla_un_invernadero_inactivo_se_rechaza(self):
        """Regla 4 de PROD-BAJ-INV: un invernadero inactivo no admite operaciones nuevas."""
        lote = self.lote()
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(rechazo(lambda: self.registrar(lote)).codigo, "invernadero_inactivo")

    def test_regla_un_lote_inexistente_es_404(self):
        """Un lote que no existe: `Http404`."""
        with self.assertRaises(Http404):
            mermas.registrar_merma(self.e.capataz, mermas.DatosDeMerma(lote_id=999999, cantidades=((1, 1),), causa="plaga"))

    def test_regla_todo_o_nada_un_error_no_deja_nada_a_medias(self):
        """Garantías mínimas: si el caso de uso falla, no se registra ninguna merma ni se modifica ningún lote, sector, alerta ni auditoría."""
        lote = self.lote(cantidad=100)
        rechazo(lambda: self.registrar(lote, {self.e.sectores["crecimiento"]: 50}, causa="inventada"))
        self.nada_se_escribio(lote)
        self.assertEqual(OcupacionSector.objects.get(lote=lote, cant_agujeros_ocupados__gt=0).cant_agujeros_ocupados, 100)


class CambioSimultaneoTests(Base):
    """Extensión 10d: entre las verificaciones y la confirmación, otra operación cambió la cantidad del lote o los agujeros de un sector."""

    def test_ext_10d_si_cambio_la_cantidad_actual_del_lote_no_registra_nada_e_informa_la_vigente(self):
        """Extensión 10d: la persona vio 100 plantas y ahora hay 90: `cambio_simultaneo` con la cantidad vigente, sin registrar nada."""
        lote = self.lote(cantidad=100)
        Lote.objects.filter(pk=lote.pk).update(cantidad_actual=90)
        error = rechazo(lambda: self.registrar(lote, cantidad_actual=100))
        self.assertEqual(error.codigo, "cambio_simultaneo")
        self.assertEqual(error.datos["cantidad_actual"], 90)
        self.assertFalse(Merma.objects.exists())

    def test_ext_10d_si_cambiaron_los_agujeros_ocupados_de_un_sector_informa_los_vigentes(self):
        """Extensión 10d: la persona vio 100 ocupados en el sector y ahora hay 95: `cambio_simultaneo` con lo vigente por sector."""
        lote = self.lote(cantidad=100)
        sector = self.e.sectores["crecimiento"]
        OcupacionSector.objects.filter(lote=lote, sector=sector).update(cant_agujeros_ocupados=95)
        error = rechazo(lambda: self.registrar(lote, ocupados=((sector.pk, 100),)))
        self.assertEqual(error.codigo, "cambio_simultaneo")
        self.assertEqual(error.datos["ocupados"], {sector.pk: 95})
        self.assertFalse(Merma.objects.exists())

    def test_ext_10d_con_lo_visto_vigente_registra_normalmente(self):
        """Extensión 10d: si lo que la persona vio sigue vigente, no hay conflicto."""
        lote = self.lote(cantidad=100)
        sector = self.e.sectores["crecimiento"]
        self.registrar(lote, cantidad_actual=100, ocupados=((sector.pk, 100),))
        self.assertEqual(Merma.objects.count(), 1)


class MovimientoDeStockDeLaMermaTests(Base):
    """COM-04a (D-64 punto 2, API sección 8): `aplicar_merma` suma el movimiento «salida por merma» del lote (origen: la merma;
    `costo_unitario` = el costo por planta de antes) y `merma_acumulada` cuenta solo las mermas con etapa."""

    def test_post_d_la_merma_de_un_lote_en_pie_crea_el_movimiento_salida_por_merma(self):
        """Postcondición d de PROD-REG-MRM (D-64 punto 2): `salida_por_merma` con la cantidad, el lote, la merma como origen y el costo por
        planta de antes de la merma (100,00 ÷ 100 = 1,0000)."""
        from produccion.models import MovimientoStock

        lote = self.lote(cantidad=100, costo="100.00")
        self.registrar(lote, {self.e.sectores["crecimiento"]: 5})
        merma = Merma.objects.get()
        m = MovimientoStock.objects.get()
        self.assertEqual(
            (m.tipo_movimiento, m.cantidad, m.lote_id, m.partida_id, m.origen_id, m.costo_unitario),
            ("salida_por_merma", 5, lote.pk, None, merma.pk, Decimal("1.0000")),
        )

    def test_regla_una_merma_de_camara_no_suma_a_la_merma_acumulada_del_lote(self):
        """Regla 7 de 8.9 (API, sección 8): `merma_acumulada` cuenta solo las mermas con etapa; una merma de partida (sin etapa) no suma."""
        lote = self.lote(cantidad=100)
        Merma.objects.create(
            invernadero=lote.invernadero, lote=lote, etapa=None, tipo_evento="merma", fecha_bitacora=timezone.localdate(),
            hora_bitacora=timezone.localtime().time(), cant_merma=50, causa="dano_en_camara",
        )
        self.assertEqual(mermas.merma_acumulada(lote), Decimal("0.00"))


class RegistrarMermaAsientoTests(Base):
    """CON-04a · PROD-REG-MRM postcondición e (D-92 puntos 2 a 6 y 9, D-86): un asiento por la merma, originado en ella, Debe Pérdidas por Mermas /
    Haber Productos en Proceso por el costo de las plantas perdidas (`ResultadoMerma.costo`), con la fecha de la merma (hoy)."""

    def lineas(self, asiento):
        return sorted(
            (m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento)
            for m in MovimientoContable.objects.filter(asiento=asiento).select_related("cuenta")
        )

    def test_post_e_asiento_perdidas_por_mermas_contra_productos_en_proceso_por_el_costo_de_las_plantas(self):
        """Postcondición e: 12 de 100 plantas a $100,00 cuestan $12,00; el asiento tiene la merma como origen, la fecha de hoy y baja del lote
        exactamente lo mismo. No había ejercicio: lo abre la autorrecuperación (H9)."""
        lote = self.lote(cantidad=100, costo="100.00")
        merma = self.registrar(lote, {self.e.sectores["crecimiento"]: 12})
        asiento = AsientoContable.objects.get(origen_id=merma.pk)
        self.assertEqual(asiento.fecha_asiento, HOY)
        self.assertEqual(self.lineas(asiento), sorted([(cuentas.PERDIDAS_POR_MERMAS, DEBE, Decimal("12.00")), (cuentas.PRODUCTOS_EN_PROCESO, HABER, Decimal("12.00"))]))
        self.assertEqual(Lote.objects.get(pk=lote.pk).costo_acumulado, Decimal("88.00"))
        self.assertEqual(EjercicioContable.objects.get().ultimo_numero_asiento, 1)
        verificar_invariantes_contables()

    def test_post_e_el_costo_se_redondea_a_dos_decimales_half_up(self):
        """D-92 punto 5 y `costo_del_lote.md`: 1 de 3 plantas a $10,00 cuestan $3,33 (10 × 1 ÷ 3 redondeado)."""
        lote = self.lote(cantidad=3, costo="10.00")
        merma = self.registrar(lote, {self.e.sectores["crecimiento"]: 1})
        asiento = AsientoContable.objects.get(origen_id=merma.pk)
        self.assertEqual(self.lineas(asiento), sorted([(cuentas.PERDIDAS_POR_MERMAS, DEBE, Decimal("3.33")), (cuentas.PRODUCTOS_EN_PROCESO, HABER, Decimal("3.33"))]))

    def test_post_e_si_el_lote_se_pierde_entero_el_asiento_es_por_todo_su_costo(self):
        """`costo_del_lote.md` («n = c»): perder las 3 plantas de un lote de $10,01 asienta $10,01 enteros y el lote queda en $0,00."""
        lote = self.lote(cantidad=3, costo="10.01")
        merma = self.registrar(lote, {self.e.sectores["crecimiento"]: 3})
        self.assertEqual(self.lineas(AsientoContable.objects.get(origen_id=merma.pk))[0][2], Decimal("10.01"))
        self.assertEqual(Lote.objects.get(pk=lote.pk).costo_acumulado, Decimal("0.00"))
        verificar_invariantes_contables()

    def test_post_e_una_merma_de_costo_cero_se_registra_y_no_asienta(self):
        """D-92 punto 5 y H11: un lote sin costo (siembra gratuita) pierde plantas sin generar asiento, y la merma se registra igual."""
        lote = self.lote(cantidad=10, costo="0.00")
        self.registrar(lote, {self.e.sectores["crecimiento"]: 4})
        self.assertEqual(Merma.objects.count(), 1)
        self.assertEqual(AsientoContable.objects.count(), 0)

    def test_post_e_la_descripcion_del_asiento_es_la_de_la_merma(self):
        """El asiento lleva la descripción legible de la merma («Merma de 12 plantas por plaga.»), que es lo que lee el Contador en el libro."""
        lote = self.lote(cantidad=100)
        merma = self.registrar(lote, {self.e.sectores["crecimiento"]: 12})
        self.assertEqual(AsientoContable.objects.get(origen_id=merma.pk).descripcion_asiento, merma.descripcion_evento)

    def test_post_e_la_ficha_del_asiento_muestra_la_merma_y_su_lote_sin_enlace(self):
        """CON-04a, «enlace al origen»: la ficha del libro nombra la merma y su lote, sin dirección (el Contador no abre la bitácora)."""
        from contabilidad import extensiones as extensiones_de_contabilidad

        lote = self.lote(cantidad=100)
        merma = self.registrar(lote, {self.e.sectores["crecimiento"]: 12})
        texto, url = extensiones_de_contabilidad.enlace_de_origen(AsientoContable.objects.get().origen)
        self.assertEqual(texto, f"Merma del lote {lote.codigo} · {merma.descripcion_evento}")
        self.assertIsNone(url)

    def test_post_m_el_asiento_va_entre_los_afectados_del_registro_de_auditoria_y_en_sus_datos(self):
        """Postcondición m y D-92 punto 3: `registro_merma` nombra el asiento entre sus afectados y en `datos`; el asiento y su movimiento los audita
        `contabilidad` (sin duplicar)."""
        lote = self.lote(cantidad=100)
        merma = self.registrar(lote, {self.e.sectores["crecimiento"]: 12})
        asiento = AsientoContable.objects.get(origen_id=merma.pk)
        registro = RegistroAuditoria.objects.get(accion="registro_merma")
        self.assertIn(("contabilidad.asientocontable", asiento.pk), {(a["modelo"], a["id"]) for a in registro.afectados})
        self.assertEqual(registro.detalle["datos"]["asiento"]["id"], asiento.pk)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_asiento_contable").count(), 1)

    def test_garantia_si_falla_el_asiento_no_queda_nada_de_la_merma(self):
        """D-22 y `docs/patrones/asientos.md` §4: si el asiento falla, se revierte la merma entera: sin merma, lote igual, sin alertas ni auditoría."""
        lote = self.lote(cantidad=100)
        with mock.patch.object(servicio_de_asientos, "registrar_asiento_automatico", side_effect=RuntimeError("falla del asiento")):
            with self.assertRaises(RuntimeError):
                self.registrar(lote, {self.e.sectores["crecimiento"]: 12})
        self.nada_se_escribio(lote)
        self.assertEqual(AsientoContable.objects.count(), 0)

    def test_garantia_un_rechazo_no_crea_asientos(self):
        """Un rechazo (más plantas que las del sector) no deja asiento ni abre ejercicio."""
        lote = self.lote(cantidad=10)
        ejercicios_antes = EjercicioContable.objects.count()  # CON-05: la clase trae el ejercicio del helper; lo que se verifica es que el rechazo no crea ninguno
        rechazo(lambda: self.registrar(lote, {self.e.sectores["crecimiento"]: 11}))
        self.assertEqual((AsientoContable.objects.count(), EjercicioContable.objects.count()), (0, ejercicios_antes))
