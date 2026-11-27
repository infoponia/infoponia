# Pruebas de PROD-PNR-FDS · Poner Sector Fuera de Servicio (PRD-04, paso 4): `resumen_de_fuera_de_servicio` y `poner_fuera_de_servicio`
# (produccion/servicios/sectores_fuera_de_servicio.py). Una prueba por regla y por postcondición a a k de
# docs/casos_de_uso/produccion/sector_fuera_de_servicio.md; los nombres siguen `.claude/rules/pruebas.md`. CON-04a: el asiento de cada merma
# (precondiciones c y d: se cumplen solas, D-92 punto 2) se prueba en `AsientosDeLasMermasTests`.
#
# CONTRATO que fijan estas pruebas (el estudiante lo revisa antes de implementar; se anota en el Cierre y en temas_abiertos.md):
#   DatosDeFueraDeServicio(sector_id, motivo="", fecha=None, reubicaciones=(), causas=(), plantas_vistas=None, libres_vistos=None,
#                          ordenes_vistas=None)
#     reubicaciones: ((lote_id, sector_destino_id, plantas), ...)      causas: ((lote_id, causa, descripcion), ...)
#     plantas_vistas: ((lote_id, plantas_en_el_sector), ...)   libres_vistos: ((sector_destino_id, libres), ...)   ordenes_vistas: (orden_id, ...)
#     Lo «visto» es lo que la persona vio al armar el formulario; si ya no es lo vigente, `cambio_simultaneo` (extensión 14a). `None` no lo verifica.
#   resumen_de_fuera_de_servicio(actor, datos) -> ResumenDeFueraDeServicio (no escribe ni bloquea; verifica los pasos 6 a 12)
#   poner_fuera_de_servicio(actor, datos) -> FueraDeServicio (todo o nada; un registro `fuera_de_servicio_sector`; UNA notificación)
#   Errores (`ErrorDeProduccion.codigo` y `.campo`): motivo_obligatorio y motivo_largo (motivo), fecha_invalida (fecha; datos con la mínima),
#   cantidad_invalida y sector_no_elegible (campo `reubicacion_<lote>_<destino>`), causa_obligatoria, causa_invalida y descripcion_larga
#   (campo `causa_<lote>`), cambio_simultaneo, sector_no_activo, sin_permiso, invernadero_inactivo.

from datetime import timedelta
from unittest import mock

from django.db import connection
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from decimal import Decimal

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import AsientoContable, EjercicioContable, MovimientoContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.tests.fabricas import PlanDeCuentasMixin, ejercicio_abierto, verificar_invariantes_contables
from core import notificaciones
from core.models import Notificacion, RegistroAuditoria
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.models import ConfiguracionOperativa, Invernadero, SectorProduccion
from maestros.servicios import sectores as api_sectores
from maestros.tests.fabricas import asegurar_datos_de_maestros, crear_agronomo, crear_sector
from produccion.errores import ErrorDeProduccion
from produccion.models import (
    AlertaDeMerma,
    Bitacora,
    FueraDeServicio,
    Lote,
    Merma,
    OcupacionSector,
    OrdenTrabajo,
    Reubicacion,
    ReservaInsumo,
)
from produccion.servicios import lotes as api_lotes
from produccion.servicios import mermas
from produccion.servicios import sectores_fuera_de_servicio as fds
from produccion.tests.fabricas import (
    invernadero_con_produccion,
    lote_activo,
    orden_de_siembra,
    orden_de_transicion,
    variedad_con_stock,
)
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

ACCION = RegistroAuditoria.Accion.FUERA_DE_SERVICIO_SECTOR


class PruebaDeFueraDeServicio(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """Un invernadero con un sector por etapa (`germ` es el de origen) y ayudas para armar datos."""

    @classmethod
    def setUpTestData(cls):
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        cls.e = invernadero_con_produccion()
        cls.germ = cls.e.sectores["germinacion"]
        cls.hoy = timezone.localdate()

    def sector(self, nombre, agujeros=100, tipo="germinacion", estado="activo"):
        """Un sector más del invernadero, registrado en el escenario con su nombre en minúsculas y guiones bajos."""
        creado = crear_sector(self.e.invernadero, nombre, tipo, agujeros, estado)
        self.e.sectores[nombre.lower().replace(" ", "_")] = creado
        return creado

    def datos(self, **campos):
        """Datos válidos por omisión: el sector `germ`, un motivo y la fecha de hoy."""
        base = dict(sector_id=self.germ.pk, motivo="Se rompió el canal de retorno", fecha=self.hoy)
        base.update(campos)
        return fds.DatosDeFueraDeServicio(**base)

    def error(self, funcion, datos=None, actor="agronomo"):
        """El `ErrorDeProduccion` que lanza `funcion(actor, datos)` (por omisión el Agrónomo del escenario; `None` es «nadie»), y verifica
        que no haya quedado nada creado."""
        with self.assertRaises(ErrorDeProduccion) as contexto:
            funcion(self.e.agronomo if actor == "agronomo" else actor, datos or self.datos())
        self.assertFalse(FueraDeServicio.objects.exists())
        self.assertEqual(SectorProduccion.objects.get(pk=self.germ.pk).estado_sector, "activo")
        return contexto.exception

    def poner(self, **campos):
        """`poner_fuera_de_servicio` del Agrónomo con los datos por omisión y `campos`."""
        return fds.poner_fuera_de_servicio(self.e.agronomo, self.datos(**campos))


class QuienLoEjecutaTests(PruebaDeFueraDeServicio):
    """Precondiciones a y b y regla «Quién lo ejecuta»."""

    def test_pre_a_solo_el_agronomo_a_cargo_puede(self):
        """Regla «Quién lo ejecuta»: el Capataz, un Agrónomo ajeno y nadie reciben `sin_permiso`."""
        ajeno = crear_agronomo(email="ajeno@infoponia.com")
        for actor in (self.e.capataz, ajeno, None):
            with self.subTest(actor=actor):
                self.assertEqual(self.error(fds.poner_fuera_de_servicio, actor=actor).codigo, "sin_permiso")

    def test_pre_b_un_agronomo_dado_de_baja_no_puede(self):
        """Precondición a: la cuenta debe seguir activa (se lee de la base)."""
        type(self.e.agronomo).objects.filter(pk=self.e.agronomo.pk).update(is_active=False)
        self.assertEqual(self.error(fds.poner_fuera_de_servicio).codigo, "sin_permiso")

    def test_regla_sector_que_se_puede_poner_fuera_de_servicio_solo_uno_activo(self):
        """Regla «Sector que se puede poner fuera de servicio»: uno fuera de servicio o dado de baja, `sector_no_activo`."""
        for estado in ("fuera_de_servicio", "inactivo"):
            otro = self.sector(f"Otro {estado}", estado=estado)
            with self.assertRaises(ErrorDeProduccion) as contexto:
                fds.poner_fuera_de_servicio(self.e.agronomo, self.datos(sector_id=otro.pk))
            self.assertEqual(contexto.exception.codigo, "sector_no_activo")

    def test_regla_un_sector_inexistente_es_404(self):
        """Un sector que no existe da 404."""
        with self.assertRaises(Http404):
            fds.poner_fuera_de_servicio(self.e.agronomo, self.datos(sector_id=0))

    def test_regla_un_invernadero_inactivo_no_admite_operaciones_nuevas(self):
        """Regla 4 de PROD-BAJ-INV: `invernadero_inactivo`."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(self.error(fds.poner_fuera_de_servicio).codigo, "invernadero_inactivo")


class MotivoYFechaTests(PruebaDeFueraDeServicio):
    """Pasos 5 y 6: motivo y fecha efectiva (extensiones 6a, 6b y 6c)."""

    def test_ext_6a_el_motivo_es_obligatorio(self):
        """Extensión 6a: vacío o solo espacios, `motivo_obligatorio` en el campo `motivo`."""
        for motivo in ("", "   "):
            error = self.error(fds.poner_fuera_de_servicio, self.datos(motivo=motivo))
            self.assertEqual((error.codigo, error.campo), ("motivo_obligatorio", "motivo"))

    def test_regla_motivo_de_hasta_300_caracteres(self):
        """«Decisiones de aplicación»: el motivo tiene hasta 300 caracteres; más, `motivo_largo`; 300 exactos, sí."""
        error = self.error(fds.poner_fuera_de_servicio, self.datos(motivo="x" * 301))
        self.assertEqual((error.codigo, error.campo), ("motivo_largo", "motivo"))
        self.assertEqual(self.poner(motivo="x" * 300).motivo_fuera_de_servicio, "x" * 300)

    def test_ext_6b_la_fecha_posterior_a_hoy_se_rechaza(self):
        """Extensión 6b: `fecha_invalida` en el campo `fecha`."""
        error = self.error(fds.poner_fuera_de_servicio, self.datos(fecha=self.hoy + timedelta(days=1)))
        self.assertEqual((error.codigo, error.campo), ("fecha_invalida", "fecha"))

    def test_ext_6b_la_fecha_es_obligatoria(self):
        """La fecha efectiva se indica siempre (la pantalla propone hoy): sin ella, `fecha_invalida`."""
        error = self.error(fds.poner_fuera_de_servicio, self.datos(fecha=None))
        self.assertEqual((error.codigo, error.campo), ("fecha_invalida", "fecha"))

    def test_ext_6c_la_fecha_anterior_a_la_minima_informa_la_minima_y_de_donde_sale(self):
        """Extensión 6c: `fecha_invalida` con la fecha mínima y qué la determina en `datos`."""
        lote = lote_activo(self.e, cantidad=10)
        lote.siembra.fecha_siembra = self.hoy - timedelta(days=5)
        lote.siembra.save(update_fields=["fecha_siembra"])
        error = self.error(fds.poner_fuera_de_servicio, self.datos(fecha=self.hoy - timedelta(days=6), causas=((lote.pk, "plaga", ""),)))
        self.assertEqual((error.codigo, error.campo), ("fecha_invalida", "fecha"))
        self.assertEqual(error.datos["fecha_minima"], self.hoy - timedelta(days=5))
        self.assertIn(f"llegada del lote {lote.codigo}", error.datos["origen"])

    def test_regla_fecha_efectiva_valida_la_minima_y_hoy_se_aceptan_y_la_hora_es_la_actual(self):
        """Regla «Fecha efectiva válida»: la mínima exacta es válida; la fecha queda como `fecha_bitacora` y la hora es la actual."""
        lote = lote_activo(self.e, cantidad=10)
        lote.siembra.fecha_siembra = self.hoy - timedelta(days=5)
        lote.siembra.save(update_fields=["fecha_siembra"])
        registro = self.poner(fecha=self.hoy - timedelta(days=5), causas=((lote.pk, "plaga", ""),))
        self.assertEqual(registro.fecha_efectiva, self.hoy - timedelta(days=5))
        self.assertLessEqual(abs((timezone.localtime().hour * 60 + timezone.localtime().minute) - (registro.hora_bitacora.hour * 60 + registro.hora_bitacora.minute)), 2)


class ReubicacionYMermaTests(PruebaDeFueraDeServicio):
    """Pasos 7 a 12: reubicación, plantas sin reubicar y su causa."""

    def armar(self, plantas=40):
        """Un lote de `plantas` en `germ` y dos destinos de Germinación con 100 agujeros."""
        self.lote = lote_activo(self.e, cantidad=plantas, costo="100.00")
        self.lote.siembra.fecha_siembra = self.hoy - timedelta(days=10)  # llegó hace diez días: admite una fecha efectiva de ayer
        self.lote.siembra.save(update_fields=["fecha_siembra"])
        self.g2 = self.sector("Germinación 2")
        self.g3 = self.sector("Germinación 3")

    def test_ext_8a_la_cantidad_debe_ser_un_entero_mayor_o_igual_que_cero(self):
        """Extensión 8a: negativa, no entera o booleana, `cantidad_invalida` en el campo `reubicacion_<lote>_<destino>`."""
        self.armar()
        for cantidad in (-1, 2.5, "7", True):
            with self.subTest(cantidad=cantidad):
                datos = self.datos(reubicaciones=((self.lote.pk, self.g2.pk, cantidad),), causas=((self.lote.pk, "plaga", ""),))
                error = self.error(fds.poner_fuera_de_servicio, datos)
                self.assertEqual((error.codigo, error.campo), ("cantidad_invalida", f"reubicacion_{self.lote.pk}_{self.g2.pk}"))

    def test_ext_8b_la_cantidad_no_supera_los_agujeros_libres_del_destino_e_informa_cuantos_quedan(self):
        """Extensión 8b: más que los libres del destino, `cantidad_invalida` con `libres` en `datos`."""
        self.armar()
        chico = self.sector("Chico", agujeros=10)
        datos = self.datos(reubicaciones=((self.lote.pk, chico.pk, 11),), causas=((self.lote.pk, "plaga", ""),))
        error = self.error(fds.poner_fuera_de_servicio, datos)
        self.assertEqual((error.codigo, error.datos["libres"]), ("cantidad_invalida", 10))

    def test_ext_8b_cuenta_lo_ya_asignado_al_mismo_destino_desde_otros_lotes(self):
        """Extensión 8b: dos lotes al mismo destino no pueden pasarse de sus libres sumados."""
        self.armar(plantas=8)
        otro = lote_activo(self.e, cantidad=8)
        justo = self.sector("Justo", agujeros=10)
        datos = self.datos(
            reubicaciones=((self.lote.pk, justo.pk, 6), (otro.pk, justo.pk, 6)),
            causas=((self.lote.pk, "plaga", ""), (otro.pk, "plaga", "")),
        )
        error = self.error(fds.poner_fuera_de_servicio, datos)
        self.assertEqual((error.codigo, error.campo), ("cantidad_invalida", f"reubicacion_{otro.pk}_{justo.pk}"))
        self.assertEqual(error.datos["libres"], 4)

    def test_ext_8c_el_total_reubicado_no_supera_las_plantas_del_lote_en_el_sector(self):
        """Extensión 8c: más que las plantas del lote ahí, `cantidad_invalida` con las plantas del lote en `datos`."""
        self.armar()
        datos = self.datos(reubicaciones=((self.lote.pk, self.g2.pk, 30), (self.lote.pk, self.g3.pk, 11)))
        error = self.error(fds.poner_fuera_de_servicio, datos)
        self.assertEqual((error.codigo, error.datos["plantas"]), ("cantidad_invalida", 40))

    def test_regla_destino_elegible_uno_de_otro_tipo_fuera_de_servicio_o_con_otro_perfil_se_rechaza(self):
        """Regla «Sector de destino elegible»: `sector_no_elegible` para uno que no cumple (otro tipo, estado o perfil)."""
        self.armar()
        otra_variedad, _ = variedad_con_stock(self.e, nombre="De fruto", perfil="frutos_grandes")
        con_otro_perfil = self.sector("Con otro perfil")
        OcupacionSector.objects.filter(lote=lote_activo(self.e, cantidad=3, variedad=otra_variedad)).update(sector=con_otro_perfil)
        malos = [self.e.sectores["crecimiento"], self.sector("Fuera", estado="fuera_de_servicio"), con_otro_perfil, self.germ]
        for destino in malos:
            with self.subTest(destino=destino.nombre_sector):
                datos = self.datos(reubicaciones=((self.lote.pk, destino.pk, 5),), causas=((self.lote.pk, "plaga", ""),))
                self.assertEqual(self.error(fds.poner_fuera_de_servicio, datos).codigo, "sector_no_elegible")

    def test_regla_destino_elegible_no_cuenta_como_libres_los_comprometidos_por_las_ordenes_que_se_cancelan(self):
        """«Decisiones de aplicación»: los agujeros que comprometen las órdenes que se cancelan NO se cuentan como libres."""
        self.armar()
        destino = self.sector("Reservado", agujeros=20)
        siembra = orden_de_siembra(self.e, plantines=10, sector="germinacion", con_reserva=False)
        OcupacionSector.objects.create(orden=siembra, sector=destino, cant_agujeros_planificados=15)
        datos = self.datos(reubicaciones=((self.lote.pk, destino.pk, 6),), causas=((self.lote.pk, "plaga", ""),))
        error = self.error(fds.poner_fuera_de_servicio, datos)
        self.assertEqual((error.codigo, error.datos["libres"]), ("cantidad_invalida", 5))

    def test_ext_12a_un_lote_con_plantas_sin_reubicar_necesita_causa(self):
        """Extensión 12a: `causa_obligatoria` en `causa_<lote>`. Un lote totalmente reubicado no la necesita."""
        self.armar()
        datos = self.datos(reubicaciones=((self.lote.pk, self.g2.pk, 39),))
        error = self.error(fds.poner_fuera_de_servicio, datos)
        self.assertEqual((error.codigo, error.campo), ("causa_obligatoria", f"causa_{self.lote.pk}"))
        self.poner(reubicaciones=((self.lote.pk, self.g2.pk, 40),))  # todas reubicadas: sin causa

    def test_regla_causa_de_la_merma_sin_descarte_por_seleccion_y_de_la_lista(self):
        """Regla «Causa de la merma»: sin «descarte por selección» ni valores fuera de la lista: `causa_invalida`."""
        self.armar()
        for causa in ("descarte_por_seleccion", "inventada"):
            with self.subTest(causa=causa):
                error = self.error(fds.poner_fuera_de_servicio, self.datos(causas=((self.lote.pk, causa, ""),)))
                self.assertEqual((error.codigo, error.campo), ("causa_invalida", f"causa_{self.lote.pk}"))

    def test_regla_la_descripcion_de_la_merma_tiene_hasta_300_caracteres(self):
        """Descripción opcional de hasta 300 caracteres: más, `descripcion_larga`."""
        self.armar()
        error = self.error(fds.poner_fuera_de_servicio, self.datos(causas=((self.lote.pk, "plaga", "x" * 301),)))
        self.assertEqual((error.codigo, error.campo), ("descripcion_larga", f"causa_{self.lote.pk}"))

    def test_post_c_una_reubicacion_por_lote_con_una_ocupacion_nueva_por_destino(self):
        """Postcondición c: por cada lote reubicado, una `Reubicacion` (lote, invernadero, sector de origen, fecha efectiva, hora actual,
        el Agrónomo) con una ocupación por destino con planificados = ocupados = plantas reubicadas y el lote."""
        self.armar()
        ayer = self.hoy - timedelta(days=1)
        self.poner(fecha=ayer, reubicaciones=((self.lote.pk, self.g2.pk, 25), (self.lote.pk, self.g3.pk, 10)), causas=((self.lote.pk, "plaga", ""),))
        reubicacion = Reubicacion.objects.get()
        self.assertEqual(
            (reubicacion.lote_id, reubicacion.invernadero_id, reubicacion.fecha_bitacora, reubicacion.responsable_id, reubicacion.tipo_evento),
            (self.lote.pk, self.e.invernadero.pk, ayer, self.e.agronomo.pk, "reubicacion"),
        )
        self.assertEqual([s.pk for s in reubicacion.sectores.all()], [self.germ.pk])
        ocupaciones = {o.sector_id: o for o in reubicacion.ocupaciones.all()}
        self.assertEqual(set(ocupaciones), {self.g2.pk, self.g3.pk})
        for sector, cantidad in ((self.g2, 25), (self.g3, 10)):
            o = ocupaciones[sector.pk]
            self.assertEqual((o.cant_agujeros_planificados, o.cant_agujeros_ocupados, o.lote_id, o.orden_id), (cantidad, cantidad, self.lote.pk, None))
        for texto in (self.lote.codigo, "25", "10", self.g2.nombre_sector, self.g3.nombre_sector, self.germ.nombre_sector):
            self.assertIn(texto, reubicacion.descripcion_evento)

    def test_post_c_varios_lotes_a_un_mismo_destino_una_reubicacion_por_lote(self):
        """D-51 y Bitacora.lote: dos lotes reubicados, dos `Reubicacion` (cada lote trazado en su bitácora), un solo registro fuera de servicio."""
        self.armar(plantas=10)
        otro = lote_activo(self.e, cantidad=7)
        self.poner(reubicaciones=((self.lote.pk, self.g2.pk, 10), (otro.pk, self.g2.pk, 7)))
        self.assertEqual(sorted(Reubicacion.objects.values_list("lote_id", flat=True)), sorted([self.lote.pk, otro.pk]))
        self.assertEqual(FueraDeServicio.objects.count(), 1)
        self.assertEqual(OcupacionSector.objects.filter(sector=self.g2, reubicacion__isnull=False).count(), 2)
        self.assertEqual(api_sectores.agujeros_de([self.g2])[self.g2.pk].ocupados, 17)

    def test_post_c_ni_la_etapa_ni_la_fecha_de_entrada_ni_la_cantidad_del_lote_cambian(self):
        """Garantía de éxito y postcondición c: la reubicación no cambia la etapa del lote, su fecha de entrada a la etapa ni su cantidad."""
        self.armar()
        antes = Lote.objects.get(pk=self.lote.pk)
        entrada = api_lotes.fecha_de_entrada_a_la_etapa(antes)
        self.poner(reubicaciones=((self.lote.pk, self.g2.pk, 40),))
        despues = Lote.objects.get(pk=self.lote.pk)
        self.assertEqual((despues.etapa_id, despues.cantidad_actual, despues.costo_acumulado, despues.estado_lote), (antes.etapa_id, 40, antes.costo_acumulado, "activo"))
        self.assertEqual(api_lotes.fecha_de_entrada_a_la_etapa(despues), entrada)

    def test_post_d_la_ocupacion_de_origen_queda_en_cero_y_conserva_el_lote(self):
        """Postcondición d: la ocupación del lote en el sector pasó a cero agujeros ocupados y conserva su lote."""
        self.armar()
        self.poner(reubicaciones=((self.lote.pk, self.g2.pk, 15),), causas=((self.lote.pk, "plaga", ""),))
        origen = OcupacionSector.objects.get(lote=self.lote, sector=self.germ)
        self.assertEqual((origen.cant_agujeros_ocupados, origen.lote_id), (0, self.lote.pk))

    def test_post_e_las_plantas_sin_reubicar_son_una_merma_en_la_etapa_actual_asociada_al_sector(self):
        """Postcondición e y «Ejecución del caso de uso que lo extiende»: una `Merma` con las plantas sin reubicar, la causa y la descripción,
        en la etapa actual del lote, con el sector en `sectores`, la fecha efectiva y el Agrónomo; baja la cantidad y el costo del lote."""
        self.armar()
        ayer = self.hoy - timedelta(days=1)
        self.poner(fecha=ayer, reubicaciones=((self.lote.pk, self.g2.pk, 30),), causas=((self.lote.pk, "plaga", "Pulgón"),))
        merma = Merma.objects.get()
        self.assertEqual((merma.cant_merma, merma.causa, merma.etapa_id, merma.fecha_bitacora, merma.responsable_id), (10, "plaga", self.lote.etapa_id, ayer, self.e.agronomo.pk))
        self.assertIn("Pulgón", merma.descripcion_evento)
        self.assertEqual([s.pk for s in merma.sectores.all()], [self.germ.pk])
        lote = Lote.objects.get(pk=self.lote.pk)
        self.assertEqual((lote.cantidad_actual, str(lote.costo_acumulado)), (30, "75.00"))  # 10 plantas × 2,50

    def test_post_e_el_agujero_de_la_ocupacion_de_origen_lo_libera_este_caso_de_uso_no_la_merma(self):
        """«Ejecución del caso de uso que lo extiende»: no se aplica la postcondición c de la merma (no se pasa `por_sector`): el origen
        queda en cero por la puesta en cero, y la merma no baja dos veces los agujeros."""
        self.armar()
        with mock.patch.object(mermas, "aplicar_merma", wraps=mermas.aplicar_merma) as espia:
            self.poner(causas=((self.lote.pk, "plaga", ""),))
        argumentos = espia.call_args.kwargs
        self.assertIsNone(argumentos.get("por_sector"))
        self.assertEqual(argumentos["sector_ids"], [self.germ.pk])
        self.assertEqual(OcupacionSector.objects.get(lote=self.lote, sector=self.germ).cant_agujeros_ocupados, 0)

    def test_post_e_la_merma_pasa_las_ordenes_que_se_cancelan_como_excluidas(self):
        """Extensión 10a de PROD-REG-MRM: las plantas comprometidas se evalúan sin contar las órdenes que esta operación cancela."""
        self.armar()
        siembra = orden_de_siembra(self.e, plantines=10, sector="germinacion", con_reserva=False)
        with mock.patch.object(mermas, "aplicar_merma", wraps=mermas.aplicar_merma) as espia:
            self.poner(causas=((self.lote.pk, "plaga", ""),))
        self.assertEqual(list(espia.call_args.kwargs["ordenes_excluidas"]), [siembra.pk])

    def test_post_e_el_umbral_de_merma_se_aplica_normalmente_y_la_merma_suma_a_la_acumulada(self):
        """«Ejecución del caso de uso que lo extiende»: la extensión 10b (umbral) se aplica normalmente: pasa el máximo, alerta."""
        self.armar()
        ConfiguracionOperativa.objects.update(porc_merma_maxima=10)
        self.poner(causas=((self.lote.pk, "plaga", ""),))
        self.assertEqual(AlertaDeMerma.objects.filter(merma__lote=self.lote).count(), 1)
        self.assertEqual(mermas.merma_acumulada(self.lote).to_integral_value(), 100)

    def test_ext_8d_todas_reubicadas_no_registra_ninguna_merma(self):
        """Extensión 8d: si se reubican todas las plantas de todos los lotes, no hay merma."""
        self.armar()
        self.poner(reubicaciones=((self.lote.pk, self.g2.pk, 40),))
        self.assertFalse(Merma.objects.exists())

    def test_ext_6e_un_lote_sin_destinos_elegibles_se_registra_entero_como_merma(self):
        """Extensión 6e: sin destinos elegibles las plantas del lote se registran como merma; el lote queda finalizado."""
        self.armar()
        SectorProduccion.objects.filter(pk__in=[self.g2.pk, self.g3.pk]).update(estado_sector="inactivo")
        self.poner(causas=((self.lote.pk, "enfermedad", ""),))
        lote = Lote.objects.get(pk=self.lote.pk)
        self.assertEqual((lote.cantidad_actual, lote.estado_lote, str(lote.costo_acumulado)), (0, "finalizado", "0.00"))
        self.assertEqual(Merma.objects.get().cant_merma, 40)


class OrdenesYSectorTests(PruebaDeFueraDeServicio):
    """Postcondiciones a, b, f, g y h y las garantías de éxito."""

    def test_post_a_el_sector_pasa_a_fuera_de_servicio(self):
        """Postcondición a."""
        self.poner()
        self.assertEqual(SectorProduccion.objects.get(pk=self.germ.pk).estado_sector, "fuera_de_servicio")

    def test_post_b_el_registro_fuera_de_servicio(self):
        """Postcondición b: fecha efectiva, hora actual, motivo, el Agrónomo, fecha de reactivación vacía; asociado al sector y al invernadero."""
        ayer = self.hoy - timedelta(days=1)
        registro = self.poner(fecha=ayer)
        self.assertEqual(
            (registro.fecha_efectiva, registro.motivo_fuera_de_servicio, registro.responsable_id, registro.fecha_fin, registro.sector_id,
             registro.invernadero_id, registro.tipo_evento),
            (ayer, "Se rompió el canal de retorno", self.e.agronomo.pk, None, self.germ.pk, self.e.invernadero.pk, "fuera_de_servicio"),
        )
        self.assertEqual([s.pk for s in registro.sectores.all()], [self.germ.pk])
        self.assertIsNotNone(registro.hora_bitacora)

    def test_ext_6d_un_sector_sin_plantas_ni_ordenes_solo_cambia_de_estado(self):
        """Extensión 6d y «Sector sin plantas»: ni reubicaciones, ni mermas, ni cancelaciones, ni ocupaciones nuevas."""
        self.poner()
        self.assertFalse(Reubicacion.objects.exists() or Merma.objects.exists() or OcupacionSector.objects.exists())
        self.assertEqual(Notificacion.objects.filter(destinatario=self.e.capataz).count(), 1)

    def test_post_f_las_ordenes_con_agujeros_comprometidos_se_cancelan_con_su_motivo_y_se_liberan_sus_reservas(self):
        """Postcondición f y regla «Órdenes afectadas»: siembra y transición «a realizar» canceladas con el motivo compuesto «Sector fuera de
        servicio: <sector>. <motivo>», sus reservas «canceladas» y sus agujeros en otros sectores liberados. Las concretadas o canceladas
        no se tocan."""
        otro = self.sector("Germinación 2")
        siembra = orden_de_siembra(self.e, plantines=15, sector="germinacion")
        OcupacionSector.objects.create(orden=siembra, sector=otro, cant_agujeros_planificados=5)
        lote = lote_activo(self.e, cantidad=20, sector="crecimiento", etapa="crecimiento")
        transicion = orden_de_transicion(self.e, lote, distribucion={"floracion": 20})  # no toca el sector: no se cancela
        concretada = orden_de_siembra(self.e, plantines=4, sector="germinacion", estado="concretada", con_reserva=False)
        self.poner()
        siembra.refresh_from_db()
        self.assertEqual(
            (siembra.estado_orden, siembra.motivo_cancelacion, siembra.fecha_resolucion_orden),
            ("cancelada", "Sector fuera de servicio: Sector germinacion. Se rompió el canal de retorno", self.hoy),
        )
        self.assertEqual(set(ReservaInsumo.objects.filter(orden=siembra).values_list("estado", flat=True)), {"cancelada"})
        self.assertEqual(api_sectores.agujeros_de([otro])[otro.pk].comprometidos, 0)
        self.assertEqual(OrdenTrabajo.objects.get(pk=transicion.pk).estado_orden, "a_realizar")
        self.assertEqual(OrdenTrabajo.objects.get(pk=concretada.pk).estado_orden, "concretada")

    def test_post_f_se_cancela_tambien_una_transicion_con_agujeros_en_el_sector(self):
        """Postcondición f: una transición «a realizar» cuyo destino es el sector que sale de servicio se cancela."""
        lote = lote_activo(self.e, cantidad=20)
        transicion = orden_de_transicion(self.e, lote, distribucion={"crecimiento": 20})
        fds.poner_fuera_de_servicio(self.e.agronomo, self.datos(sector_id=self.e.sectores["crecimiento"].pk))
        self.assertEqual(OrdenTrabajo.objects.get(pk=transicion.pk).estado_orden, "cancelada")

    def test_post_f_el_motivo_compuesto_se_recorta_a_300_con_puntos_suspensivos_y_el_completo_queda_en_el_registro(self):
        """Regla de `cancelar_orden.md`: el motivo compuesto pasa de 300: la cancelación lo recorta con «…»; el registro conserva el completo."""
        siembra = orden_de_siembra(self.e, plantines=5, sector="germinacion", con_reserva=False)
        registro = self.poner(motivo="m" * 300)
        siembra.refresh_from_db()
        self.assertEqual((len(siembra.motivo_cancelacion), siembra.motivo_cancelacion[-1]), (300, "…"))
        self.assertEqual(registro.motivo_fuera_de_servicio, "m" * 300)

    def test_post_g_el_sector_queda_sin_agujeros_ocupados_ni_comprometidos(self):
        """Postcondición g (invariante): con lotes reubicados o perdidos y órdenes canceladas, el sector queda en cero y en cero."""
        g2 = self.sector("Germinación 2")
        lote = lote_activo(self.e, cantidad=30)
        orden_de_siembra(self.e, plantines=9, sector="germinacion", con_reserva=False)
        self.poner(reubicaciones=((lote.pk, g2.pk, 20),), causas=((lote.pk, "plaga", ""),))
        agujeros = api_sectores.agujeros_de([self.germ, g2])
        self.assertEqual((agujeros[self.germ.pk].ocupados, agujeros[self.germ.pk].comprometidos), (0, 0))
        self.assertEqual(agujeros[g2.pk].ocupados, 20)

    def test_post_h_una_sola_notificacion_al_capataz_con_el_sector_la_fecha_el_motivo_y_las_ordenes_canceladas(self):
        """Postcondición h y regla «Notificación al Capataz»: UNA con todo, no una por orden (las cancelaciones no avisan)."""
        uno = orden_de_siembra(self.e, plantines=5, sector="germinacion", con_reserva=False)
        dos = orden_de_siembra(self.e, plantines=6, sector="germinacion", con_reserva=False)
        ayer = self.hoy - timedelta(days=1)
        self.poner(fecha=ayer)
        avisos = Notificacion.objects.filter(destinatario=self.e.capataz)
        self.assertEqual(avisos.count(), 1)
        aviso = avisos.get()
        for texto in ("Sector germinacion", ayer.strftime("%d/%m/%Y"), "Se rompió el canal de retorno", uno.codigo, dos.codigo):
            self.assertIn(texto, f"{aviso.titulo} {aviso.detalle}")
        self.assertLessEqual(len(aviso.detalle), 500)
        self.assertEqual(Notificacion.objects.exclude(destinatario=self.e.capataz).count(), 0)

    def test_ext_15a_sin_capataz_activo_no_se_notifica_y_la_operacion_sigue(self):
        """Extensión 15a: sin Capataz activo no se envía la notificación; la puesta fuera de servicio se registra igual."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(capataz=None)
        self.poner()
        self.assertFalse(Notificacion.objects.exists())
        self.assertEqual(SectorProduccion.objects.get(pk=self.germ.pk).estado_sector, "fuera_de_servicio")

    def test_ext_15a_un_capataz_dado_de_baja_tampoco_recibe_la_notificacion(self):
        """Extensión 15a: «activo» es la cuenta activa."""
        type(self.e.capataz).objects.filter(pk=self.e.capataz.pk).update(is_active=False)
        self.poner()
        self.assertFalse(Notificacion.objects.exists())


class AuditoriaYAtomicidadTests(PruebaDeFueraDeServicio):
    """Postcondiciones i, j y k y las garantías mínimas."""

    def armar(self):
        """Un lote de 40 en `germ` con un destino, una siembra a realizar y una transición a realizar hacia el sector."""
        self.lote = lote_activo(self.e, cantidad=40)
        self.g2 = self.sector("Germinación 2")
        self.siembra = orden_de_siembra(self.e, plantines=8, sector="germinacion")

    def test_post_i_j_k_un_solo_registro_de_auditoria_con_todo_lo_tocado(self):
        """Postcondiciones i, j y k y D-36 (D-51 punto 9): UN registro `fuera_de_servicio_sector` con el sector (estado antes → después), el
        registro fuera de servicio, cada reubicación, las ocupaciones creadas y modificadas, las mermas, las órdenes y los lotes."""
        self.armar()
        registro = self.poner(reubicaciones=((self.lote.pk, self.g2.pk, 25),), causas=((self.lote.pk, "plaga", ""),))
        self.assertEqual(RegistroAuditoria.objects.filter(accion=ACCION).count(), 1)
        auditoria = RegistroAuditoria.objects.get(accion=ACCION)
        self.assertEqual((auditoria.usuario_id, auditoria.rol), (self.e.agronomo.pk, "agronomo"))
        afectados = {(a["modelo"], a["id"]) for a in auditoria.afectados}
        esperados = {
            ("maestros.sectorproduccion", self.germ.pk),
            ("maestros.sectorproduccion", self.g2.pk),
            ("produccion.fueradeservicio", registro.pk),
            ("produccion.reubicacion", Reubicacion.objects.get().pk),
            ("produccion.merma", Merma.objects.get().pk),
            ("produccion.lote", self.lote.pk),
            ("produccion.ocupacionsector", OcupacionSector.objects.get(reubicacion__isnull=False).pk),
            ("produccion.ocupacionsector", OcupacionSector.objects.get(lote=self.lote, sector=self.germ).pk),
        }
        self.assertTrue(esperados <= afectados, esperados - afectados)
        self.assertIn(self.siembra.pk, {i for _, i in afectados})
        self.assertEqual(auditoria.detalle["cambios"]["estado"], {"antes": "activo", "despues": "fuera_de_servicio"})
        cambios = auditoria.detalle["cambios"]
        self.assertEqual(cambios["agujeros_comprometidos"]["despues"], [f"{self.germ.nombre_sector}: 0"])
        self.assertIn(f"{self.lote.codigo}: 40", cambios["cantidad_actual"]["antes"])
        self.assertIn(f"{self.lote.codigo}: 25", cambios["cantidad_actual"]["despues"])

    def test_post_j_ninguna_otra_accion_de_auditoria_ni_una_por_orden(self):
        """Un registro por caso de uso (D-36): ni `cancelacion_orden` ni `registro_merma` aparte. CON-04a: lo único que se suma son los registros del asiento de la merma y de su movimiento, que
        audita `contabilidad` (D-86 punto 4). CON-05: el ejercicio ya no lo abre la autorrecuperación (H9) y el que deja `iniciar_contabilidad_para_pruebas` no audita."""
        self.armar()
        self.poner(causas=((self.lote.pk, "plaga", ""),))
        acciones = set(RegistroAuditoria.objects.values_list("accion", flat=True))
        self.assertEqual(acciones, {ACCION, "alta_asiento_contable", "alta_movimiento_contable"})
        self.assertEqual(RegistroAuditoria.objects.filter(accion=ACCION).count(), 1)

    def test_garantia_todo_o_nada_si_falla_la_notificacion_no_queda_nada(self):
        """Garantías mínimas: si el caso de uso falla, el sector sigue activo y no queda registro, reubicación, ocupación, merma,
        cancelación, notificación ni auditoría."""
        self.armar()
        datos = self.datos(reubicaciones=((self.lote.pk, self.g2.pk, 25),), causas=((self.lote.pk, "plaga", ""),))
        with mock.patch.object(notificaciones, "notificar", side_effect=RuntimeError("falla")), self.assertRaises(RuntimeError):
            fds.poner_fuera_de_servicio(self.e.agronomo, datos)
        self.assertEqual(SectorProduccion.objects.get(pk=self.germ.pk).estado_sector, "activo")
        self.assertFalse(FueraDeServicio.objects.exists() or Reubicacion.objects.exists() or Merma.objects.exists())
        self.assertFalse(OcupacionSector.objects.filter(reubicacion__isnull=False).exists())
        self.assertEqual(OrdenTrabajo.objects.get(pk=self.siembra.pk).estado_orden, "a_realizar")
        self.assertEqual(Lote.objects.get(pk=self.lote.pk).cantidad_actual, 40)
        self.assertEqual(OcupacionSector.objects.get(lote=self.lote, sector=self.germ).cant_agujeros_ocupados, 40)
        self.assertFalse(Notificacion.objects.exists() or RegistroAuditoria.objects.filter(accion=ACCION).exists())

    def test_garantia_un_error_de_validacion_no_deja_nada_creado(self):
        """Garantías mínimas: un rechazo (aquí, destino no elegible) no crea nada."""
        self.armar()
        datos = self.datos(reubicaciones=((self.lote.pk, self.e.sectores["crecimiento"].pk, 5),), causas=((self.lote.pk, "plaga", ""),))
        self.error(fds.poner_fuera_de_servicio, datos)
        self.assertFalse(Bitacora.objects.filter(tipo_evento__in=["reubicacion", "merma", "fuera_de_servicio"]).exists())

    def test_ext_14a_si_cambiaron_las_plantas_del_lote_los_libres_o_las_ordenes_vuelve_con_lo_vigente(self):
        """Extensión 14a: lo que la persona vio ya no es lo vigente: `cambio_simultaneo` con lo vigente en `datos`, sin registrar nada."""
        self.armar()
        causas = ((self.lote.pk, "plaga", ""),)
        casos = {
            "plantas": dict(plantas_vistas=((self.lote.pk, 39),)),
            "libres": dict(libres_vistos=((self.g2.pk, 99),), reubicaciones=((self.lote.pk, self.g2.pk, 5),)),
            "ordenes": dict(ordenes_vistas=()),
        }
        for nombre, extra in casos.items():
            with self.subTest(cambio=nombre):
                error = self.error(fds.poner_fuera_de_servicio, self.datos(causas=causas, **extra))
                self.assertEqual(error.codigo, "cambio_simultaneo")
                self.assertIn("plantas", error.datos)
                self.assertIn("ordenes", error.datos)
        # lo vigente y lo visto coinciden: se registra
        self.poner(
            causas=causas, plantas_vistas=((self.lote.pk, 40),), libres_vistos=((self.g2.pk, 100),), ordenes_vistas=(self.siembra.pk,)
        )
        self.assertTrue(FueraDeServicio.objects.exists())


class ResumenTests(PruebaDeFueraDeServicio):
    """Paso 12: el resumen no escribe y trae lo que se confirma."""

    def test_paso_12_el_resumen_muestra_la_merma_las_reubicaciones_y_las_ordenes_sin_escribir(self):
        """Paso 12: por lote, lo que se reubica y dónde, lo que se registra como merma con su causa y su valor, y las órdenes que se cancelan."""
        lote = lote_activo(self.e, cantidad=40, costo="100.00")
        g2 = self.sector("Germinación 2")
        siembra = orden_de_siembra(self.e, plantines=6, sector="germinacion", con_reserva=False)
        resumen = fds.resumen_de_fuera_de_servicio(
            self.e.agronomo, self.datos(reubicaciones=((lote.pk, g2.pk, 30),), causas=((lote.pk, "plaga", ""),))
        )
        self.assertEqual((resumen.sector.pk, resumen.motivo, resumen.fecha), (self.germ.pk, "Se rompió el canal de retorno", self.hoy))
        fila = resumen.lotes[0]
        self.assertEqual((fila.lote.pk, fila.plantas, fila.sin_reubicar, fila.causa, str(fila.valor_de_la_merma)), (lote.pk, 40, 10, "plaga", "25.00"))
        self.assertEqual([(s.pk, q) for s, q in fila.reubicaciones], [(g2.pk, 30)])
        self.assertEqual([o.orden.pk for o in resumen.ordenes], [siembra.pk])
        self.assertEqual(resumen.total_de_la_merma, 10)
        self.assertFalse(FueraDeServicio.objects.exists() or Merma.objects.exists() or Reubicacion.objects.exists())
        self.assertEqual(SectorProduccion.objects.get(pk=self.germ.pk).estado_sector, "activo")
        self.assertEqual(Lote.objects.get(pk=lote.pk).cantidad_actual, 40)

    def test_paso_12_el_resumen_repite_las_verificaciones(self):
        """Paso 12: las mismas verificaciones que al confirmar: un lote con plantas sin reubicar y sin causa, `causa_obligatoria`."""
        lote = lote_activo(self.e, cantidad=10)
        with self.assertRaises(ErrorDeProduccion) as contexto:
            fds.resumen_de_fuera_de_servicio(self.e.agronomo, self.datos())
        self.assertEqual((contexto.exception.codigo, contexto.exception.campo), ("causa_obligatoria", f"causa_{lote.pk}"))

    def test_ext_4a_el_resumen_trae_el_aviso_del_ultimo_sector_de_su_tipo(self):
        """Extensión 4a: el resumen repite la advertencia (no bloquea)."""
        resumen = fds.resumen_de_fuera_de_servicio(self.e.agronomo, self.datos())
        self.assertTrue(resumen.avisos)
        self.sector("Germinación 2")
        self.assertEqual(fds.resumen_de_fuera_de_servicio(self.e.agronomo, self.datos()).avisos, [])


class AsientosDeLasMermasTests(PruebaDeFueraDeServicio):
    """CON-04a · PROD-PNR-FDS (D-92 puntos 2 a 6, 9 y «Lo que todavía no está programado»): un asiento por cada merma de las plantas sin reubicar,
    originado en la merma, Debe Pérdidas por Mermas / Haber Productos en Proceso por su costo, con la fecha EFECTIVA del fuera de servicio. La
    reubicación y la cancelación de órdenes no asientan."""

    def armar(self):
        """Dos lotes en `germ` (40 plantas a $100,00 y 20 a $60,00), dos destinos, una siembra a realizar que se cancela y un ejercicio abierto."""
        self.l1 = lote_activo(self.e, cantidad=40, costo="100.00")
        self.l2 = lote_activo(self.e, cantidad=20, costo="60.00")
        for lote in (self.l1, self.l2):
            lote.siembra.fecha_siembra = self.hoy - timedelta(days=10)  # llegaron hace diez días: admiten una fecha efectiva de ayer
            lote.siembra.save(update_fields=["fecha_siembra"])
        self.g2 = self.sector("Germinación 2")
        self.g3 = self.sector("Germinación 3")
        self.siembra = orden_de_siembra(self.e, plantines=8, sector="germinacion")
        self.ayer = self.hoy - timedelta(days=1)
        self.abierto = ejercicio_abierto(self.hoy - timedelta(days=30))

    def lineas(self, asiento):
        return sorted(
            (m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento)
            for m in MovimientoContable.objects.filter(asiento=asiento).select_related("cuenta")
        )

    def causas(self, *lotes):
        return tuple((lote.pk, "plaga", "") for lote in lotes)

    def test_post_e_un_asiento_por_cada_merma_con_su_costo_la_fecha_efectiva_y_la_merma_como_origen(self):
        """Dos lotes que no se reubican (40 de $100,00 y 20 de $60,00) son dos mermas y dos asientos: Debe Pérdidas por Mermas / Haber Productos en
        Proceso por $100,00 y $60,00 (el costo entero de cada lote), con la fecha efectiva (ayer), en el ejercicio que la contiene."""
        self.armar()
        self.poner(fecha=self.ayer, causas=self.causas(self.l1, self.l2))
        self.assertEqual(Merma.objects.count(), 2)
        self.assertEqual(AsientoContable.objects.count(), 2)
        for merma, importe in ((Merma.objects.get(lote=self.l1), Decimal("100.00")), (Merma.objects.get(lote=self.l2), Decimal("60.00"))):
            asiento = AsientoContable.objects.get(origen_id=merma.pk)
            self.assertEqual((asiento.fecha_asiento, asiento.ejercicio_id), (self.ayer, self.abierto.pk))
            self.assertEqual(self.lineas(asiento), sorted([(cuentas.PERDIDAS_POR_MERMAS, DEBE, importe), (cuentas.PRODUCTOS_EN_PROCESO, HABER, importe)]))
        self.assertEqual(sorted(AsientoContable.objects.values_list("numero_asiento", flat=True)), [1, 2])
        verificar_invariantes_contables()

    def test_post_e_la_reubicacion_y_la_cancelacion_de_ordenes_no_asientan(self):
        """Reubicar todas las plantas no genera merma ni asiento; cancelar la siembra «a realizar» tampoco."""
        self.armar()
        self.poner(reubicaciones=((self.l1.pk, self.g2.pk, 40), (self.l2.pk, self.g3.pk, 20)))
        self.assertEqual(OrdenTrabajo.objects.get(pk=self.siembra.pk).estado_orden, "cancelada")
        self.assertEqual((Merma.objects.count(), AsientoContable.objects.count()), (0, 0))

    def test_post_e_solo_las_plantas_sin_reubicar_se_asientan_por_su_costo_proporcional(self):
        """Se reubican 30 de las 40 plantas del primer lote: la merma de las 10 restantes cuesta $25,00 (100 × 10 ÷ 40) y es lo que se asienta; la
        reubicación no suma nada."""
        self.armar()
        self.poner(reubicaciones=((self.l1.pk, self.g2.pk, 30),), causas=self.causas(self.l1, self.l2))
        asiento = AsientoContable.objects.get(origen_id=Merma.objects.get(lote=self.l1).pk)
        self.assertEqual(self.lineas(asiento), sorted([(cuentas.PERDIDAS_POR_MERMAS, DEBE, Decimal("25.00")), (cuentas.PRODUCTOS_EN_PROCESO, HABER, Decimal("25.00"))]))
        self.assertEqual(AsientoContable.objects.count(), 2)  # el de l1 y el de l2
        verificar_invariantes_contables()

    def test_post_e_un_sector_sin_lotes_no_asienta(self):
        """Un sector vacío se pone fuera de servicio sin mermas ni asientos."""
        self.poner()
        self.assertEqual((Merma.objects.count(), AsientoContable.objects.count()), (0, 0))

    def test_post_e_una_merma_de_costo_cero_no_asienta_y_el_sector_pasa_a_fuera_de_servicio(self):
        """D-92 punto 5 y H11: un lote sin costo se pierde sin asiento y sin fallar."""
        self.armar()
        Lote.objects.filter(pk=self.l2.pk).update(costo_acumulado=Decimal("0.00"))
        self.poner(reubicaciones=((self.l1.pk, self.g2.pk, 40),), causas=self.causas(self.l2))
        self.assertEqual(Merma.objects.count(), 1)
        self.assertEqual(AsientoContable.objects.count(), 0)
        self.assertEqual(SectorProduccion.objects.get(pk=self.germ.pk).estado_sector, "fuera_de_servicio")

    def test_post_e_la_descripcion_del_asiento_es_la_de_la_merma(self):
        """El asiento lleva la descripción legible de su merma, que es lo que lee el Contador en el libro."""
        self.armar()
        self.poner(causas=self.causas(self.l1, self.l2))
        merma = Merma.objects.get(lote=self.l1)
        self.assertEqual(AsientoContable.objects.get(origen_id=merma.pk).descripcion_asiento, merma.descripcion_evento)

    def test_post_i_los_asientos_van_entre_los_afectados_del_registro_de_auditoria_y_en_sus_datos(self):
        """Postcondición i y D-92 punto 3: `fuera_de_servicio_sector` nombra cada asiento entre sus afectados y en `datos`; sin mermas, no trae `asientos`."""
        self.armar()
        self.poner(causas=self.causas(self.l1, self.l2))
        auditoria = RegistroAuditoria.objects.get(accion=ACCION)
        afectados = {(a["modelo"], a["id"]) for a in auditoria.afectados}
        for asiento in AsientoContable.objects.all():
            self.assertIn(("contabilidad.asientocontable", asiento.pk), afectados)
        self.assertEqual(len(auditoria.detalle["datos"]["asientos"]), 2)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_asiento_contable").count(), 2)

    def test_post_i_sin_mermas_el_registro_no_trae_asientos(self):
        self.poner()
        self.assertNotIn("asientos", RegistroAuditoria.objects.get(accion=ACCION).detalle["datos"])

    def test_garantia_si_falla_el_segundo_asiento_no_queda_nada_del_fuera_de_servicio(self):
        """D-22: si el asiento de la segunda merma falla, el sector sigue activo y no queda registro, reubicación, merma, asiento ni auditoría; la
        orden sigue «a realizar» y los lotes no cambian."""
        self.armar()
        real = servicio_de_asientos.registrar_asiento_automatico
        llamadas = []

        def falla_en_la_segunda(*args, **kwargs):
            llamadas.append(1)
            if len(llamadas) == 2:
                raise RuntimeError("falla del asiento")
            return real(*args, **kwargs)

        datos = self.datos(causas=self.causas(self.l1, self.l2))
        with mock.patch.object(servicio_de_asientos, "registrar_asiento_automatico", side_effect=falla_en_la_segunda):
            with self.assertRaises(RuntimeError):
                fds.poner_fuera_de_servicio(self.e.agronomo, datos)
        self.assertEqual(len(llamadas), 2)
        self.assertEqual(SectorProduccion.objects.get(pk=self.germ.pk).estado_sector, "activo")
        self.assertFalse(FueraDeServicio.objects.exists() or Merma.objects.exists() or AsientoContable.objects.exists())
        self.assertEqual(OrdenTrabajo.objects.get(pk=self.siembra.pk).estado_orden, "a_realizar")
        self.assertEqual(Lote.objects.get(pk=self.l1.pk).cantidad_actual, 40)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=ACCION).exists())

    def test_garantia_un_rechazo_no_crea_asientos_ni_abre_el_ejercicio(self):
        """Un rechazo (motivo obligatorio) no deja asientos ni abre un ejercicio."""
        self.armar()
        EjercicioContable.objects.all().delete()
        self.error(fds.poner_fuera_de_servicio, self.datos(motivo="", causas=self.causas(self.l1, self.l2)))
        self.assertEqual((AsientoContable.objects.count(), EjercicioContable.objects.count()), (0, 0))
