# Pruebas de concurrencia de los servicios de variedades (INV-03, paso 4; docs/patrones/bloqueos.md, docs/patrones/stock.md sección 5 y
# docs/casos_de_uso/inventario/variedades.md, «Bloqueos»): dos altas con el mismo nombre y el alta contra la baja del cultivo. Dos hilos,
# dos conexiones, el orden fijado con ``primera`` (core/tests/concurrencia.py). Son ``TransactionTestCase``: su ``flush`` vacía todas las
# tablas al terminar (también las categorías del sistema y los tipos de etapa), así que la clase hereda de ``ConDatosDeInventario`` y cada
# prueba vuelve a asegurar esos datos en ``setUp`` (docs/patrones/datos_de_migracion.md). El paso 5 suma los cruces de modificación; el 6, los de la baja.

from django.test import TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from inventario.models import Insumo, InsumoInvernadero, Semilla
from inventario.servicios import insumos_invernadero
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    asegurar_datos_de_inventario,
    existencia,
    perezoso,
    variedad_con_semilla,
)
from inventario.tests.test_prod_alt_var import datos
from inventario.tests.test_prod_mod_var import datos_de
from maestros.models import Cultivo, Variedad
from maestros.servicios import cultivos
from maestros.tests.fabricas import (
    asegurar_datos_de_maestros,
    crear_agronomo,
    crear_cultivo,
    crear_invernadero_con_geografia_propia,
)

variedades = perezoso("inventario.servicios.variedades")


@tag("concurrencia")
class VariedadesConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Bloqueos de ``alta_variedad``: cultivo → (variedad, semilla). Quien crea una variedad bloquea antes la fila del cultivo."""

    def setUp(self):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()  # el flush de la prueba anterior vació los tipos de etapa y las categorías
        self.agronomo = crear_agronomo()
        self.otro = crear_agronomo(email="otro@infoponia.com")
        self.cultivo = crear_cultivo("Lechuga")

    def test_regla_2_dos_altas_con_el_mismo_nombre_crean_una_sola_variedad(self):
        """PROD-ALT-VAR regla 2: la segunda alta espera el bloqueo del cultivo, ve el nombre ya usado y se rechaza con
        ``nombre_repetido``. Sin el bloqueo del cultivo ni la restricción única de la base, las dos pasarían; con la restricción
        sola, el segundo recibiría un ``IntegrityError`` sin traducir (un 500). Nunca un error no capturado."""
        resultados = correr_a_la_vez(
            lambda: variedades.alta_variedad(self.agronomo, self.cultivo.pk, datos(nombre="Butterhead")),
            lambda: variedades.alta_variedad(self.otro, self.cultivo.pk, datos(nombre="butterhead")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["nombre_repetido"])
        self.assertEqual((Variedad.objects.count(), Semilla.objects.count()), (1, 1))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_variedad").count(), 1)

    def test_regla_2_dos_altas_con_nombres_distintos_se_crean_las_dos(self):
        """El bloqueo del cultivo serializa las altas pero no las rechaza: dos nombres distintos conviven."""
        resultados = correr_a_la_vez(
            lambda: variedades.alta_variedad(self.agronomo, self.cultivo.pk, datos(nombre="Butterhead")),
            lambda: variedades.alta_variedad(self.otro, self.cultivo.pk, datos(nombre="Crespa")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(Variedad.objects.count(), 2)

    def test_pre_b_la_baja_del_cultivo_espera_al_alta_y_se_rechaza_porque_ve_la_variedad(self):
        """PROD-BAJ-CLT precondición c y «Cultivos: bloqueo»: quien crea una variedad bloquea el cultivo ANTES de insertarla; la baja
        espera a que confirme, cuenta las variedades activas después de bloquear y se rechaza con ``variedades_activas``. Sin ese
        bloqueo el ``INSERT`` solo toma ``FOR KEY SHARE`` (no choca con el de la baja) y se daría de baja un cultivo con una variedad."""
        resultados = correr_a_la_vez(
            lambda: variedades.alta_variedad(self.agronomo, self.cultivo.pk, datos()),
            lambda: cultivos.baja_cultivo(self.otro, self.cultivo.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["variedades_activas"])
        self.assertEqual(Cultivo.objects.get(pk=self.cultivo.pk).estado_cultivo, "activo")
        self.assertEqual(Variedad.objects.count(), 1)

    def test_pre_b_el_alta_espera_a_la_baja_del_cultivo_y_se_rechaza_porque_lo_ve_inactivo(self):
        """PROD-ALT-VAR precondición b: el alta verifica que el cultivo siga activo DESPUÉS de bloquearlo; si la baja confirmó primero,
        se rechaza con ``cultivo_inactivo`` y no crea nada (ni variedad, ni ciclo, ni semilla)."""
        resultados = correr_a_la_vez(
            lambda: cultivos.baja_cultivo(self.otro, self.cultivo.pk),
            lambda: variedades.alta_variedad(self.agronomo, self.cultivo.pk, datos()),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["cultivo_inactivo"])
        self.assertEqual(Cultivo.objects.get(pk=self.cultivo.pk).estado_cultivo, "inactivo")
        self.assertEqual((Variedad.objects.count(), Semilla.objects.count()), (0, 0))


@tag("concurrencia")
class ModificarVariedadConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Bloqueos de ``modificar_variedad`` (paso 5): cultivo -> variedad -> insumo de la semilla (docs/patrones/stock.md, sección 5).

    La segunda y la tercera prueba usan funciones de pasos que vienen después: ``baja_variedad`` (paso 6) y el renombre de las semillas que
    registra ``InventarioConfig.ready()`` para ``modificar_cultivo`` (paso 7). Hasta entonces fallan por eso, no por el bloqueo."""

    def setUp(self):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.ana = crear_agronomo("ana@infoponia.com", nombre="Ana", apellido="Pérez")
        self.beto = crear_agronomo("beto@infoponia.com", nombre="Beto", apellido="Gómez")
        self.cultivo = crear_cultivo("Lechuga")
        self.crespa = variedad_con_semilla(self.cultivo, "Crespa")
        self.lisa = variedad_con_semilla(self.cultivo, "Lisa")

    def test_pre_c_dos_modificaciones_al_mismo_nombre_dejan_una_sola(self):
        """PROD-MOD-VAR precondición c: dos variedades del mismo cultivo que se renombran al mismo nombre a la vez. Las dos toman el
        cultivo primero: la segunda espera, ve el nombre ya usado y se rechaza con ``nombre_repetido`` (la restricción única la respalda;
        nunca un ``IntegrityError`` sin traducir). Sin el bloqueo del cultivo en la modificación, las dos validarían contra lo viejo."""
        resultados = correr_a_la_vez(
            lambda: variedades.modificar_variedad(self.ana, self.crespa.pk, datos_de(self.crespa, nombre="Butterhead")),
            lambda: variedades.modificar_variedad(self.beto, self.lisa.pk, datos_de(self.lisa, nombre="butterhead")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["nombre_repetido"])
        self.assertEqual(Variedad.objects.filter(nombre_variedad__iexact="butterhead").count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="modificacion_variedad").count(), 1)

    def test_regla_9_una_modificacion_contra_una_baja_ve_la_variedad_inactiva(self):
        """PROD-MOD-VAR regla 9 y PROD-BAJ-VAR: la baja confirma primero; la modificación, que esperaba el bloqueo de la variedad, la
        relee inactiva y se rechaza con ``variedad_inactiva`` sin cambiar nada ni notificar."""
        resultados = correr_a_la_vez(
            lambda: variedades.baja_variedad(self.ana, self.crespa.pk),
            lambda: variedades.modificar_variedad(self.beto, self.crespa.pk, datos_de(self.crespa, nombre="Butterhead")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["variedad_inactiva"])
        self.assertEqual(Variedad.objects.get(pk=self.crespa.pk).nombre_variedad, "Crespa")
        self.assertEqual(Insumo.objects.get(pk=self.crespa.semilla.pk).nombre_insumo, "Semilla Lechuga Crespa")

    def test_post_b_el_renombre_del_cultivo_contra_el_de_la_variedad_deja_la_semilla_coherente(self):
        """PROD-MOD-CLT regla 3 y PROD-MOD-VAR regla 6: las dos operaciones toman el cultivo primero, así que se serializan. Gane quien
        gane, la semilla termina llamándose «Semilla {cultivo final} {variedad final}» (no queda con el nombre de uno y el cultivo del otro)."""
        resultados = correr_a_la_vez(
            lambda: cultivos.modificar_cultivo(self.ana, self.cultivo.pk, nombre="Lechuga común"),
            lambda: variedades.modificar_variedad(self.beto, self.crespa.pk, datos_de(self.crespa, nombre="Butterhead")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        cultivo, variedad = Cultivo.objects.get(pk=self.cultivo.pk), Variedad.objects.get(pk=self.crespa.pk)
        self.assertEqual((cultivo.nombre_cultivo, variedad.nombre_variedad), ("Lechuga común", "Butterhead"))
        self.assertEqual(Insumo.objects.get(pk=self.crespa.semilla.pk).nombre_insumo, "Semilla Lechuga común Butterhead")
        self.assertEqual(Insumo.objects.get(pk=self.lisa.semilla.pk).nombre_insumo, "Semilla Lechuga común Lisa")


@tag("concurrencia")
class BajaVariedadConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Bloqueos de ``baja_variedad`` (paso 6): invernaderos de la semilla -> cultivo -> variedad -> insumo (docs/patrones/stock.md, sección 5).
    ``habilitar_insumo`` (INV-02) bloquea invernadero -> insumo -> existencia: el orden es compatible, no hay ciclo."""

    def setUp(self):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.ana = crear_agronomo("ana@infoponia.com", nombre="Ana", apellido="Pérez")
        self.beto = crear_agronomo("beto@infoponia.com", nombre="Beto", apellido="Gómez")
        self.norte = crear_invernadero_con_geografia_propia("Invernadero Norte", agronomo=self.ana)
        self.sur = crear_invernadero_con_geografia_propia("Invernadero Sur", agronomo=self.beto)
        self.variedad = variedad_con_semilla(crear_cultivo("Lechuga"), "Crespa")

    def test_pre_c_dos_bajas_a_la_vez_dan_de_baja_una_sola_vez(self):
        """PROD-BAJ-VAR precondición c: la segunda baja espera el bloqueo del cultivo y de la variedad, la lee inactiva y se rechaza con
        ``variedad_inactiva``; queda un solo registro de baja."""
        resultados = correr_a_la_vez(
            lambda: variedades.baja_variedad(self.ana, self.variedad.pk),
            lambda: variedades.baja_variedad(self.beto, self.variedad.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["variedad_inactiva"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion="baja_variedad").count(), 1)

    def test_pre_b_una_habilitacion_que_confirma_mientras_la_baja_espera_se_rechaza_con_cambio_simultaneo(self):
        """docs/patrones/bloqueos.md y stock.md, sección 5: la baja leyó las existencias antes de bloquear; si mientras esperaba el insumo
        otro pedido habilitó la semilla en un invernadero que no bloqueó, relee, lo ve y se rechaza con ``cambio_simultaneo`` (no
        reintenta: reintentar bloquearía el invernadero después del insumo, fuera de orden). La variedad sigue activa."""
        resultados = correr_a_la_vez(
            lambda: insumos_invernadero.habilitar_insumo(self.ana, self.variedad.semilla.pk, self.norte.pk, "0", "10"),
            lambda: variedades.baja_variedad(self.ana, self.variedad.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["cambio_simultaneo"])
        self.assertEqual(Variedad.objects.get(pk=self.variedad.pk).estado_variedad, "activo")
        self.assertEqual(InsumoInvernadero.objects.count(), 1)

    def test_post_b_una_habilitacion_que_espera_a_la_baja_ve_la_semilla_inactiva(self):
        """PROD-BAJ-VAR postcondición b: la baja confirma primero; la habilitación, que esperaba el bloqueo del insumo, lo relee inactivo
        y se rechaza con ``insumo_inactivo`` (la semilla dada de baja deja de ofrecerse para pedirse y habilitarse)."""
        existencia(self.variedad.semilla, self.norte)
        resultados = correr_a_la_vez(
            lambda: variedades.baja_variedad(self.ana, self.variedad.pk),
            lambda: insumos_invernadero.habilitar_insumo(self.beto, self.variedad.semilla.pk, self.sur.pk, "0", "10"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["insumo_inactivo"])
        self.assertEqual(InsumoInvernadero.objects.count(), 1)


@tag("concurrencia")
class RenombreDelCultivoConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Paso 7: el renombre del cultivo (``modificar_cultivo``) contra el alta de una variedad. Los dos toman el cultivo primero."""

    def setUp(self):
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.ana = crear_agronomo("ana@infoponia.com", nombre="Ana", apellido="Pérez")
        self.beto = crear_agronomo("beto@infoponia.com", nombre="Beto", apellido="Gómez")
        self.cultivo = crear_cultivo("Lechuga")
        self.crespa = variedad_con_semilla(self.cultivo, "Crespa")

    def test_post_a_un_alta_que_espera_al_renombre_del_cultivo_crea_su_semilla_con_el_nombre_nuevo(self):
        """PROD-MOD-CLT regla 3 y PROD-ALT-VAR postcondición c: el alta espera el bloqueo del cultivo, lo lee ya renombrado y su semilla
        nace como «Semilla {cultivo nuevo} {variedad}»; la semilla de la variedad anterior también quedó renombrada."""
        resultados = correr_a_la_vez(
            lambda: cultivos.modificar_cultivo(self.ana, self.cultivo.pk, nombre="Lechuga común"),
            lambda: variedades.alta_variedad(self.beto, self.cultivo.pk, datos(nombre="Butterhead")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(
            sorted(Semilla.objects.values_list("nombre_insumo", flat=True)),
            ["Semilla Lechuga común Butterhead", "Semilla Lechuga común Crespa"],
        )
