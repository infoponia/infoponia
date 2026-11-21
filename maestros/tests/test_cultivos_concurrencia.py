# Pruebas de concurrencia de los servicios de cultivo (MAE-03; docs/patrones/bloqueos.md, docs/casos_de_uso/maestros/cultivos.md,
# «Bloqueos»): dos altas iguales, dos renombres a la vez y la baja contra una variedad creada. Dos hilos, dos conexiones, el orden
# fijado con ``primera`` (core/tests/concurrencia.py). Son ``TransactionTestCase``: su ``flush`` vacía todas las tablas al
# terminar, incluidos los cinco tipos de etapa, así que la clase hereda de ``ConDatosDeMaestros`` (los recarga antes de la clase)
# y cada prueba los vuelve a asegurar en ``setUp`` (docs/patrones/datos_de_migracion.md).

from types import SimpleNamespace

from django.db import transaction
from django.test import TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from maestros.models import Cultivo, Variedad
from maestros.servicios import cultivos
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    asegurar_datos_de_maestros,
    crear_agronomo,
    crear_cultivo,
)

# Punto de parada que usa ``detener_antes_de`` para frenar a la primera operación justo antes de terminar.
pausa = SimpleNamespace(punto=lambda: None)


@tag("concurrencia")
class CultivosConcurrenciaTests(ConDatosDeMaestros, TransactionTestCase):
    """Bloqueos de ``alta_cultivo``, ``modificar_cultivo`` y ``baja_cultivo``."""

    def setUp(self):
        asegurar_datos_de_maestros()  # el flush de la prueba anterior vació los tipos de etapa
        self.agronomo = crear_agronomo()
        self.otro = crear_agronomo(email="otro@infoponia.com")

    def test_pre_b_dos_altas_con_el_mismo_nombre_crean_un_solo_cultivo(self):
        """PROD-ALT-CLT regla 2: la segunda alta espera a que la primera confirme y se rechaza con ``nombre_repetido`` (la
        restricción única de la base lo respalda: sin ella ni validación, las dos pasarían). Nunca un error 500."""
        resultados = correr_a_la_vez(
            lambda: cultivos.alta_cultivo(self.agronomo, nombre="Lechuga"),
            lambda: cultivos.alta_cultivo(self.otro, nombre="lechuga"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["nombre_repetido"])
        self.assertEqual(Cultivo.objects.count(), 1)

    def test_regla_2_dos_renombres_a_la_vez_del_mismo_cultivo_gana_el_ultimo(self):
        """Cultivos, «Bloqueos»: gana el último, calculado contra lo leído DESPUÉS de bloquear (misma convención que
        ``modificar_invernadero``). El «antes» del registro del segundo es el «después» del primero; no se rechaza."""
        cultivo = crear_cultivo("Lechuga")
        resultados = correr_a_la_vez(
            lambda: cultivos.modificar_cultivo(self.agronomo, cultivo.pk, nombre="Lechuga A"),
            lambda: cultivos.modificar_cultivo(self.otro, cultivo.pk, nombre="Lechuga B"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        cultivo.refresh_from_db()
        self.assertEqual(cultivo.nombre_cultivo, "Lechuga B")
        cambios = [
            (r.usuario_id, r.detalle["cambios"]["nombre"])
            for r in RegistroAuditoria.objects.filter(accion="modificacion_cultivo").order_by("id")
        ]
        self.assertEqual(
            cambios,
            [
                (self.agronomo.pk, {"antes": "Lechuga", "despues": "Lechuga A"}),
                (self.otro.pk, {"antes": "Lechuga A", "despues": "Lechuga B"}),
            ],
        )

    def test_regla_2_dos_renombres_de_cultivos_distintos_al_mismo_nombre_dejan_uno_solo(self):
        """PROD-MOD-CLT precondición b: el segundo renombre espera el índice único, y el ``IntegrityError`` se traduce a
        ``nombre_repetido`` (nunca un 500)."""
        uno, otro = crear_cultivo("Lechuga"), crear_cultivo("Acelga")
        resultados = correr_a_la_vez(
            lambda: cultivos.modificar_cultivo(self.agronomo, uno.pk, nombre="Verdura"),
            lambda: cultivos.modificar_cultivo(self.otro, otro.pk, nombre="verdura"),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["nombre_repetido"])
        self.assertEqual(Cultivo.objects.filter(nombre_cultivo__iexact="verdura").count(), 1)

    def test_pre_c_la_baja_espera_a_quien_crea_una_variedad_y_se_rechaza(self):
        """PROD-BAJ-CLT precondición c y regla 2: quien crea una variedad (INV-03) bloquea el cultivo antes (cultivo -> variedad,
        ``docs/tareas/inventario/INV-03-variedades-y-semillas.md``); la baja espera a que confirme y entonces ve la variedad
        activa. Sin el bloqueo del cultivo en la baja, no esperaría, no vería lo que no se confirmó y daría de baja un cultivo
        con una variedad activa. El creador es falso: bloquea la fila y crea la variedad."""
        cultivo = crear_cultivo("Lechuga")

        def crear_variedad_bloqueando_el_cultivo():
            with transaction.atomic():
                Cultivo.objects.select_for_update(no_key=True).get(pk=cultivo.pk)
                Variedad.objects.create(cultivo=cultivo, nombre_variedad="Crespa", perfil_familia="hoja_verde")
                pausa.punto()  # acá se detiene: todavía no confirmó

        resultados = correr_a_la_vez(
            crear_variedad_bloqueando_el_cultivo,
            lambda: cultivos.baja_cultivo(self.agronomo, cultivo.pk),
            primera="a",
            detener_antes_de=(pausa, "punto"),
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["variedades_activas"])
        cultivo.refresh_from_db()
        self.assertEqual(cultivo.estado_cultivo, "activo")

    def test_pre_b_dos_bajas_a_la_vez_dan_de_baja_una_sola_vez(self):
        """PROD-BAJ-CLT precondición b: la segunda baja espera el bloqueo del cultivo, lo lee inactivo y se rechaza con
        ``cultivo_inactivo``; queda un solo registro de baja."""
        cultivo = crear_cultivo("Lechuga")
        resultados = correr_a_la_vez(
            lambda: cultivos.baja_cultivo(self.agronomo, cultivo.pk),
            lambda: cultivos.baja_cultivo(self.otro, cultivo.pk),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["cultivo_inactivo"])
        self.assertEqual(RegistroAuditoria.objects.filter(accion="baja_cultivo").count(), 1)
