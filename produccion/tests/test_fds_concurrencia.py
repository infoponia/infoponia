# Pruebas de concurrencia de PROD-PNR-FDS (PRD-04, paso 4; docs/patrones/bloqueos.md, sección `produccion`, «Lote 5»; requisitos especiales
# de docs/casos_de_uso/produccion/sector_fuera_de_servicio.md: «el control de concurrencia impide que dos operaciones simultáneas superen los
# agujeros libres de un sector de destino o dejen a un lote con cantidad negativa»). Orden de bloqueos de poner un sector fuera de servicio:
# cuentas → invernadero → variedades → sectores (origen, destinos y los de las órdenes a cancelar, por id) → insumos de las reservas → lotes
# (por id) → órdenes, ocupaciones y reservas.
#
# Dos hilos, dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py). Son ``TransactionTestCase``: su ``flush`` vacía todas
# las tablas al terminar, así que cada prueba arma su invernadero con geografía propia y vuelve a asegurar los datos
# (docs/patrones/datos_de_migracion.md). Un rechazo es un ``ErrorDeProduccion`` o una ``ValidationError`` de `maestros`: nunca un 500.
# Incluye la prueba que PRD-03 dejó pendiente: «merma contra poner el sector fuera de servicio» (docs/disparadores.md, «Cuando exista PRD-03 o PRD-04», punto 3).



from datetime import timedelta

from django.core.cache import cache
from django.test import TransactionTestCase, tag
from django.utils import timezone

from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos, ejercicios
from contabilidad.tests.fabricas import asegurar_plan_de_cuentas, ejercicio, ejercicio_abierto, verificar_invariantes_contables
from core.tests.fabricas import crear_cuenta
from core.models import Contador, Notificacion, RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario, perezoso
from maestros.models import SectorProduccion
from maestros.servicios import sectores as api_sectores
from maestros.tests.fabricas import asegurar_datos_de_maestros, crear_sector
from produccion.models import FueraDeServicio, Lote, Merma, OcupacionSector, OrdenTrabajo, Siembra
from produccion.servicios import sectores_fuera_de_servicio as fds
from produccion.servicios import transiciones
from produccion.tests.fabricas import (
    codigos_del_rechazo,
    invernadero_con_produccion,
    lote_activo,
    lote_con_ciclo,
    orden_de_siembra,
    orden_de_transicion,
    separar,
)
from produccion.tests.test_prod_cnc_trn import datos as datos_de_concrecion
from produccion.tests.test_prod_pnf_smb import datos as datos_de_siembra
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

mermas = perezoso("produccion.servicios.mermas")
siembras = perezoso("produccion.servicios.siembras")

ACCION = RegistroAuditoria.Accion.FUERA_DE_SERVICIO_SECTOR


@tag("concurrencia")
class FueraDeServicioConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Poner un sector fuera de servicio contra lo que pasa a la vez sobre el mismo sector, lote o destino."""

    def armar(self, plantas=40):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()  # el flush de la prueba anterior vació los tipos de etapa y las categorías
        asegurar_plan_de_cuentas()  # CON-04a: las mermas asientan; el flush de la prueba anterior vació el plan
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento; el flush de esta TransactionTestCase lo vacía en cada prueba
        self.e = invernadero_con_produccion(geografia_propia=True)
        self.germ = self.e.sectores["germinacion"]
        self.lote = lote_activo(self.e, cantidad=plantas) if plantas else None

    def poner(self, sector=None, actor=None, **campos):
        """`poner_fuera_de_servicio` del sector (por omisión `germ`), con la causa «plaga» para el lote del escenario."""
        base = dict(sector_id=(sector or self.germ).pk, motivo="Rotura", fecha=timezone.localdate())
        if self.lote is not None and "causas" not in campos:
            base["causas"] = ((self.lote.pk, "plaga", ""),)
        base.update(campos)
        datos = fds.DatosDeFueraDeServicio(**base)
        return lambda: fds.poner_fuera_de_servicio(actor or self.e.agronomo, datos)

    def test_regla_dos_puestas_fuera_de_servicio_del_mismo_sector_una_gana_y_la_otra_ve_el_estado_actual(self):
        """Poner fuera de servicio dos veces el mismo sector: la segunda espera el invernadero, relee el sector ya «fuera de servicio» y se
        rechaza (`sector_no_activo` o `cambio_simultaneo`), sin 500. Un solo registro, una sola notificación y una sola auditoría."""
        self.armar(plantas=0)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.poner(), self.poner(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn(codigos_del_rechazo(rechazos[0])[0], {"sector_no_activo", "cambio_simultaneo"})
        self.assertEqual(FueraDeServicio.objects.count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=ACCION).count(), 1)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.capataz).count(), 1)
        self.assertEqual(SectorProduccion.objects.get(pk=self.germ.pk).estado_sector, "fuera_de_servicio")

    def test_regla_dos_reubicaciones_sobre_el_ultimo_agujero_del_mismo_destino_una_gana_y_la_otra_se_rechaza(self):
        """Requisito especial: dos sectores se ponen fuera de servicio a la vez y reubican en el mismo destino con un solo agujero libre.
        La segunda espera, relee los libres del destino y se rechaza con `cantidad_invalida`; el destino no supera su capacidad."""
        self.armar(plantas=0)
        otro_origen = crear_sector(self.e.invernadero, "Germinación B", "germinacion", 100)
        destino = crear_sector(self.e.invernadero, "Destino", "germinacion", 1)
        uno = lote_activo(self.e, cantidad=1)
        dos = lote_activo(self.e, cantidad=1)
        OcupacionSector.objects.filter(lote=dos).update(sector=otro_origen)
        a = self.poner(causas=(), reubicaciones=((uno.pk, destino.pk, 1),))
        b = self.poner(sector=otro_origen, causas=(), reubicaciones=((dos.pk, destino.pk, 1),))
        exitos, rechazos, otros = separar(correr_a_la_vez(a, b, primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["cantidad_invalida"])
        self.assertEqual(api_sectores.agujeros_de([destino])[destino.pk].ocupados, 1)
        self.assertEqual(FueraDeServicio.objects.count(), 1)

    def test_regla_poner_fuera_de_servicio_primero_la_planificacion_se_rechaza_y_el_sector_no_queda_comprometido(self):
        """Contra una planificación sobre el sector, la puesta fuera de servicio primera: la planificación espera el invernadero, relee el
        sector ya fuera de servicio y se rechaza (no recibe órdenes); no queda ninguna siembra nueva."""
        self.armar(plantas=0)
        planificar = lambda: siembras.planificar_siembra(self.e.agronomo, datos_de_siembra(self.e, cantidad=10))
        exitos, rechazos, otros = separar(correr_a_la_vez(self.poner(), planificar, primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(Siembra.objects.count(), 0)
        agujeros = api_sectores.agujeros_de([self.germ])[self.germ.pk]
        self.assertEqual((agujeros.ocupados, agujeros.comprometidos), (0, 0))

    def test_regla_la_planificacion_primero_la_puesta_fuera_de_servicio_cancela_la_orden_nueva(self):
        """Contra una planificación sobre el sector, la planificación primera: la puesta fuera de servicio espera, relee y cancela también la
        orden nueva (sin lo visto no hay conflicto): el sector queda sin comprometidos (garantía «nunca fuera de servicio con agujeros»)."""
        self.armar(plantas=0)
        planificar = lambda: siembras.planificar_siembra(self.e.agronomo, datos_de_siembra(self.e, cantidad=10))
        exitos, rechazos, otros = separar(correr_a_la_vez(planificar, self.poner(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(OrdenTrabajo.objects.get().estado_orden, "cancelada")
        agujeros = api_sectores.agujeros_de([self.germ])[self.germ.pk]
        self.assertEqual((agujeros.ocupados, agujeros.comprometidos), (0, 0))

    def test_ext_14a_la_planificacion_primero_si_la_persona_vio_otras_ordenes_pide_volver_a_cargar(self):
        """Extensión 14a: con lo que la persona vio (ninguna orden), la orden que apareció en el medio es un `cambio_simultaneo`: nada se registra."""
        self.armar(plantas=0)
        planificar = lambda: siembras.planificar_siembra(self.e.agronomo, datos_de_siembra(self.e, cantidad=10))
        resultados = correr_a_la_vez(planificar, self.poner(ordenes_vistas=()), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["cambio_simultaneo"])
        self.assertEqual(SectorProduccion.objects.get(pk=self.germ.pk).estado_sector, "activo")
        self.assertEqual(FueraDeServicio.objects.count(), 0)

    def test_regla_una_merma_primero_la_puesta_fuera_de_servicio_con_lo_visto_pide_volver_a_cargar(self):
        """«Merma contra poner el sector fuera de servicio» (pendiente de PRD-03), merma primera: la puesta espera, relee el lote con 35
        plantas y, como la persona vio 40, se rechaza con `cambio_simultaneo`. El sector sigue activo."""
        self.armar(plantas=40)
        merma = lambda: mermas.registrar_merma(
            self.e.capataz, mermas.DatosDeMerma(lote_id=self.lote.pk, cantidades=((self.germ.pk, 5),), causa="plaga")
        )
        poner = self.poner(plantas_vistas=((self.lote.pk, 40),))
        exitos, rechazos, otros = separar(correr_a_la_vez(merma, poner, primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["cambio_simultaneo"])
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 35)
        self.assertEqual(SectorProduccion.objects.get(pk=self.germ.pk).estado_sector, "activo")

    def test_regla_una_merma_primero_sin_lo_visto_la_puesta_toma_las_plantas_que_quedan(self):
        """Merma primera y sin lo visto: la puesta fuera de servicio relee y registra como merma las 35 plantas que quedan; el lote no
        queda negativo ni con agujeros ocupados en el sector."""
        self.armar(plantas=40)
        merma = lambda: mermas.registrar_merma(
            self.e.capataz, mermas.DatosDeMerma(lote_id=self.lote.pk, cantidades=((self.germ.pk, 5),), causa="plaga")
        )
        exitos, rechazos, otros = separar(correr_a_la_vez(merma, self.poner(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        lote = Lote.objects.get(pk=self.lote.pk)
        self.assertEqual((lote.cantidad_actual, lote.estado_lote), (0, "finalizado"))
        self.assertEqual(sorted(Merma.objects.values_list("cant_merma", flat=True)), [5, 35])

    def test_regla_la_puesta_fuera_de_servicio_primero_la_merma_se_rechaza_y_el_lote_no_queda_negativo(self):
        """«Merma contra poner el sector fuera de servicio», puesta primera: la merma espera, relee las ocupaciones en cero y se rechaza
        (`cambio_simultaneo`: el sector ya no está activo; o `cantidad_invalida` o `lote_no_activo`); el lote queda en 0, nunca negativo."""
        self.armar(plantas=40)
        merma = lambda: mermas.registrar_merma(
            self.e.capataz, mermas.DatosDeMerma(lote_id=self.lote.pk, cantidades=((self.germ.pk, 5),), causa="plaga")
        )
        exitos, rechazos, otros = separar(correr_a_la_vez(self.poner(), merma, primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn(codigos_del_rechazo(rechazos[0])[0], {"cambio_simultaneo", "cantidad_invalida", "lote_no_activo"})
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 0)

    def test_regla_concretar_una_transicion_primero_la_puesta_fuera_de_servicio_con_lo_visto_pide_volver_a_cargar(self):
        """Contra concretar una transición, la concreción primera: el lote ya está en Floración y el sector de Crecimiento quedó sin sus
        plantas: lo que la persona vio (50 plantas ahí) ya no es lo vigente, `cambio_simultaneo`; el sector sigue activo."""
        self.armar(plantas=0)
        crecimiento = self.e.sectores["crecimiento"]
        lote = lote_con_ciclo(self.e, cantidad=50, etapa="crecimiento")
        orden = orden_de_transicion(self.e, lote)
        concretar = lambda: transiciones.concretar_transicion(self.e.capataz, orden.pk, datos_de_concrecion(cantidad=50))
        causas = ((lote.pk, "plaga", ""),)
        poner = self.poner(sector=crecimiento, causas=causas, plantas_vistas=((lote.pk, 50),))
        exitos, rechazos, otros = separar(correr_a_la_vez(concretar, poner, primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["cambio_simultaneo"])
        self.assertEqual(SectorProduccion.objects.get(pk=crecimiento.pk).estado_sector, "activo")
        self.assertEqual(estado_de(orden), "concretada")

    def test_regla_la_puesta_fuera_de_servicio_primero_la_concrecion_de_la_transicion_se_rechaza(self):
        """Contra concretar una transición, la puesta fuera de servicio primera: reubica 20 y pierde 30 plantas del lote; la concreción espera,
        relee el lote con 20 plantas y, como el Capataz vio 50, se rechaza con `cambio_simultaneo`. La transición sigue «a realizar»."""
        self.armar(plantas=0)
        crecimiento = self.e.sectores["crecimiento"]
        otro = crear_sector(self.e.invernadero, "Crecimiento 2", "crecimiento", 100)
        lote = lote_con_ciclo(self.e, cantidad=50, etapa="crecimiento")
        orden = orden_de_transicion(self.e, lote)
        poner = self.poner(
            sector=crecimiento, reubicaciones=((lote.pk, otro.pk, 20),), causas=((lote.pk, "plaga", ""),),
        )
        concretar = lambda: transiciones.concretar_transicion(self.e.capataz, orden.pk, datos_de_concrecion(cantidad=50))
        exitos, rechazos, otros = separar(correr_a_la_vez(poner, concretar, primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos_del_rechazo(rechazos[0]), ["cambio_simultaneo"])
        self.assertEqual(estado_de(orden), "a_realizar")
        self.assertEqual(Lote.objects.get(pk=lote.pk).cantidad_actual, 20)


def estado_de(orden):
    """El estado actual de la orden en la base."""
    return OrdenTrabajo.objects.get(pk=orden.pk).estado_orden


@tag("concurrencia")
class FueraDeServicioAsientoConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """CON-04a · el asiento de la merma de un fuera de servicio bloquea el ejercicio AL FINAL (D-86 punto 2) y NUNCA rechaza por la fecha (D-102). La
    merma lleva la fecha EFECTIVA, que puede caer en el ejercicio que se está cerrando. Las fechas son relativas a hoy porque el servicio toma «hoy»
    del reloj."""

    def armar(self, escenario=None):
        cache.clear()  # el responsable contable no debe quedar en un caché de otra prueba
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        asegurar_plan_de_cuentas()  # el flush de este TransactionTestCase vacía el plan en cada prueba
        self.e = invernadero_con_produccion(geografia_propia=True)
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")

    def con_ejercicios(self):
        """El ejercicio en cierre cubre desde hace 400 días hasta hace unos 36; el abierto empieza hace 20 días y contiene a hoy."""
        self.en_cierre = ejercicio(EjercicioContable.Estado.EN_CIERRE, timezone.localdate() - timedelta(days=400))
        self.abierto = ejercicio_abierto(timezone.localdate() - timedelta(days=20))

    def lote(self, escenario=None, dias=60):
        """Un lote de 40 plantas sembrado hace `dias` días en el sector de germinación del escenario."""
        e = escenario or self.e
        lote = lote_activo(e, cantidad=40)
        lote.siembra.fecha_siembra = timezone.localdate() - timedelta(days=dias)
        lote.siembra.save(update_fields=["fecha_siembra"])
        return lote

    def poner_en(self, escenario, lote, dias_atras=0):
        datos = fds.DatosDeFueraDeServicio(
            sector_id=escenario.sectores["germinacion"].pk,
            motivo="Rotura",
            fecha=timezone.localdate() - timedelta(days=dias_atras),
            causas=((lote.pk, "plaga", ""),),
        )
        return lambda: fds.poner_fuera_de_servicio(escenario.agronomo, datos)

    def cierre(self):
        return lambda: ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

    def sin_errores(self, resultados):
        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])

    def test_d102_el_cierre_primero_y_poner_fuera_de_servicio_con_fecha_en_el_ejercicio_en_cierre_espera_y_el_asiento_va_al_abierto(self):
        """El sector se pone fuera de servicio con una fecha efectiva dentro del ejercicio en cierre. El cierre tiene esa fila tomada; la operación
        espera, la relee ya «cerrada», elige de nuevo y el asiento de la merma va al abierto, con la fecha de hoy y la aclaración de la fecha real."""
        self.armar()
        self.con_ejercicios()
        lote = self.lote()
        resultados = correr_a_la_vez(self.cierre(), self.poner_en(self.e, lote, dias_atras=38), primera="a")
        self.sin_errores(resultados)
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.ejercicio_id, asiento.fecha_asiento), (self.abierto.pk, timezone.localdate()))
        self.assertIn("Fecha del hecho", asiento.descripcion_asiento)
        self.assertEqual(SectorProduccion.objects.get(pk=self.e.sectores["germinacion"].pk).estado_sector, "fuera_de_servicio")
        verificar_invariantes_contables()

    def test_d102_poner_fuera_de_servicio_primero_con_fecha_en_el_ejercicio_en_cierre_y_el_cierre_a_la_vez_el_asiento_queda_en_el_ejercicio_en_cierre(self):
        """La operación ya creó su asiento en el ejercicio en cierre (tiene su fila tomada); el cierre espera y cierra el ejercicio con ese asiento
        adentro. Los dos terminan bien."""
        self.armar()
        self.con_ejercicios()
        lote = self.lote()
        resultados = correr_a_la_vez(self.poner_en(self.e, lote, dias_atras=38), self.cierre(), primera="a")
        self.sin_errores(resultados)
        asiento = AsientoContable.objects.get()
        self.assertEqual((asiento.ejercicio_id, asiento.numero_asiento), (self.en_cierre.pk, 1))
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)
        verificar_invariantes_contables()

    def test_regla_d86_el_ejercicio_es_lo_ultimo_que_poner_fuera_de_servicio_bloquea(self):
        """D-86 punto 2: la operación A (invernadero Norte) se detiene justo ANTES de bloquear el ejercicio, con todos sus bloqueos de producción ya
        tomados; la B (otro invernadero, sin filas en común) asienta completa y toma el N.º 1. Si A hubiera bloqueado el ejercicio antes, B esperaría
        y el orden sería el inverso."""
        self.armar()
        ejercicio_abierto(timezone.localdate() - timedelta(days=20))
        otro = invernadero_con_produccion(nombre="Invernadero Sur", sufijo="b", geografia_propia=True)
        lote_a, lote_b = self.lote(), self.lote(otro)
        resultados = correr_a_la_vez(
            self.poner_en(self.e, lote_a), self.poner_en(otro, lote_b), primera="a", detener_antes_de=(asientos, "_bloquear_ejercicio")
        )
        self.sin_errores(resultados)
        numero = lambda lote: AsientoContable.objects.get(origen__bitacora__merma__lote=lote).numero_asiento
        self.assertEqual((numero(lote_b), numero(lote_a)), (1, 2))
        verificar_invariantes_contables()

    def test_regla_h8_dos_puestas_fuera_de_servicio_a_la_vez_toman_numeros_consecutivos_sin_hueco(self):
        """H8: dos sectores del mismo invernadero se ponen fuera de servicio a la vez (se serializan por el invernadero) y asientan con los números 1 y 2."""
        self.armar()
        ejercicio_abierto(timezone.localdate() - timedelta(days=20))
        lote_a = self.lote()
        otro_sector = crear_sector(self.e.invernadero, "Germinación B", "germinacion", 100)
        lote_b = lote_activo(self.e, cantidad=40, sector="germinacion")
        OcupacionSector.objects.filter(lote=lote_b).update(sector=otro_sector)
        lote_b.siembra.fecha_siembra = timezone.localdate() - timedelta(days=60)
        lote_b.siembra.save(update_fields=["fecha_siembra"])
        datos_b = fds.DatosDeFueraDeServicio(sector_id=otro_sector.pk, motivo="Rotura", fecha=timezone.localdate(), causas=((lote_b.pk, "plaga", ""),))
        resultados = correr_a_la_vez(self.poner_en(self.e, lote_a), lambda: fds.poner_fuera_de_servicio(self.e.agronomo, datos_b), primera="a")
        self.sin_errores(resultados)
        self.assertEqual(sorted(AsientoContable.objects.values_list("numero_asiento", flat=True)), [1, 2])
        verificar_invariantes_contables()
