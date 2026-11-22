# Prueba de la migración `maestros/0009_variedad_condiciones` (INV-03, paso 1): con la tabla de variedades vacía agrega las columnas y
# las restricciones; con variedades cargadas a mano se detiene con un mensaje claro en vez de inventarles rangos. Lleva la etiqueta
# «migracion»: desarma y vuelve a armar el esquema de la base de pruebas (en local se excluye; el CI la corre).

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, tag

ANTERIOR = ("maestros", "0008_transportista_invernadero")
ESTA = ("maestros", "0009_variedad_condiciones")


@tag("migracion")
class MigracionVariedadTests(TransactionTestCase):
    """Migra hacia atrás y hacia adelante con el modelo histórico. Al terminar, deja la base en la última migración."""

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def migrar(self, destino):
        executor = MigrationExecutor(connection)
        executor.migrate([destino])
        executor.loader.build_graph()
        return executor.loader.project_state([destino]).apps

    def test_d49_con_la_tabla_vacia_agrega_las_columnas(self):
        """D-49: sin variedades cargadas, la 0009 agrega los rangos, la postcosecha y el peso."""
        self.migrar(ANTERIOR)
        apps = self.migrar(ESTA)
        columnas = {campo.name for campo in apps.get_model("maestros", "Variedad")._meta.get_fields()}
        self.assertTrue({"temp_ambiente_min", "fotoperiodo_max", "duracion_post_cosecha", "peso_promedio_planta"} <= columnas)

    def test_d49_con_variedades_de_prueba_se_detiene_con_un_mensaje_claro(self):
        """INV-03, paso 1: con N variedades cargadas a mano, la migración lanza RuntimeError con la cantidad y qué hacer."""
        apps = self.migrar(ANTERIOR)
        cultivo = apps.get_model("maestros", "Cultivo").objects.create(nombre_cultivo="Lechuga", estado_cultivo="activo")
        Variedad = apps.get_model("maestros", "Variedad")
        Variedad.objects.create(cultivo=cultivo, nombre_variedad="Crespa", perfil_familia="hoja_verde", estado_variedad="activo")
        with self.assertRaisesMessage(
            RuntimeError, "Hay 1 variedades de prueba cargadas a mano: borralas desde /admin/ antes de migrar"
        ):
            self.migrar(ESTA)
        # La tabla quedó intacta: se borra para que el tearDown pueda migrar hasta el final.
        Variedad.objects.all().delete()
