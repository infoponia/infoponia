# Pruebas del cargador de datos de verificación de `produccion` (`produccion/verificacion.py`; CLAUDE.md, «Datos para la verificación a mano»): deja el invernadero con su
# Agrónomo y su Capataz, un lote activo con plantas en dos sectores, la merma previa a una planta del umbral, la transición «a realizar», los insumos en cada estado y un
# invernadero vacío; es idempotente, llama a los servicios (queda la auditoría), no borra nada y no pasa la contraseña por la salida ni por la auditoría.

from decimal import Decimal

from django.test import TestCase

from core.models import RegistroAuditoria, Usuario
from core.tests.fabricas import crear_gerente
from core.verificacion import ErrorDeCarga
from inventario.models import InsumoInvernadero, LoteInsumo
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Invernadero
from produccion import verificacion as cargador
from produccion.models import Lote, Merma, OcupacionSector, OrdenTrabajo, TransicionEtapa
from produccion.servicios import aplicaciones, bitacora

CLAVE = "Prueba-98765x"


class ProduccionVerificacionTests(ConDatosDeInventario, TestCase):
    def setUp(self):
        crear_gerente()

    def test_d_verificacion_sin_gerente_activo_se_detiene_con_un_mensaje_claro(self):
        Usuario.objects.filter(rol="gerente").update(is_active=False)
        with self.assertRaises(ErrorDeCarga):
            cargador.cargar(CLAVE)

    def test_d_verificacion_deja_el_invernadero_con_agronomo_capataz_lote_merma_y_transicion(self):
        """La primera corrida arma lo que pide la verificación a mano de PRD-03 (pasos 2 a 9)."""
        resumen = cargador.cargar(CLAVE)
        invernadero = Invernadero.objects.get(nombre_invernadero="Verificación Producción")
        self.assertEqual((invernadero.agronomo.email, invernadero.capataz.email), ("agronomo@prueba4.local", "capataz@prueba4.local"))
        self.assertTrue(Usuario.objects.get(email="agronomo@prueba4.local").check_password(CLAVE))
        lote = Lote.objects.get(invernadero=invernadero)
        self.assertEqual((lote.estado_lote, lote.cantidad_inicial, lote.cantidad_actual), ("activo", 100, 86))
        self.assertEqual(OcupacionSector.objects.filter(lote=lote, cant_agujeros_ocupados__gt=0).count(), 2)  # plantas en dos sectores
        self.assertEqual(Merma.objects.get(lote=lote).cant_merma, 14)
        transicion = TransicionEtapa.objects.get(lote=lote)
        self.assertEqual(transicion.estado_orden, OrdenTrabajo.Estado.A_REALIZAR)
        self.assertIn("agronomo@prueba4.local · Agrónomo", resumen.cuentas)
        self.assertIn("capataz@prueba4.local · Capataz", resumen.cuentas)

    def test_d_verificacion_deja_los_insumos_en_cada_estado_que_hay_que_probar(self):
        """Un insumo como gasto, uno como costo de los lotes, uno en unidades y uno con vencimiento y dos lotes."""
        cargador.cargar(CLAVE)
        invernadero = Invernadero.objects.get(nombre_invernadero="Verificación Producción")
        agronomo = Usuario.objects.get(email="agronomo@prueba4.local")
        filas = {f.nombre: f for f in aplicaciones.insumos_aplicables(agronomo, invernadero.pk)}
        self.assertEqual(set(filas), {"Detergente", "Guantes", "Abono verde (prueba)", "Nutriente líquido (prueba)"})
        self.assertEqual((filas["Detergente"].destino, filas["Abono verde (prueba)"].destino), ("gasto", "costo_de_los_lotes"))
        self.assertEqual(filas["Guantes"].unidad, "unidad")
        self.assertEqual([(l[1]) for l in filas["Nutriente líquido (prueba)"].lotes], [Decimal("4"), Decimal("10")])
        self.assertTrue(filas["Nutriente líquido (prueba)"].controla_vencimiento)

    def test_d_verificacion_el_invernadero_vacio_no_tiene_lotes_ni_insumos_ni_sectores(self):
        """Extensiones 4a, 4b y 6b: el segundo invernadero del Agrónomo está vacío."""
        cargador.cargar(CLAVE)
        vacio = Invernadero.objects.get(nombre_invernadero="Verificación Producción Vacío")
        agronomo = Usuario.objects.get(email="agronomo@prueba4.local")
        self.assertFalse(Lote.objects.filter(invernadero=vacio).exists())
        self.assertEqual(aplicaciones.insumos_aplicables(agronomo, vacio.pk), [])
        self.assertEqual(aplicaciones.sectores_de_aplicacion(agronomo, vacio.pk), [])

    def test_d_verificacion_la_bitacora_muestra_siembra_merma_y_los_registros_de_la_carga(self):
        """La pestaña «Bitácora» ya tiene qué mostrar: la siembra, la merma previa y el consumo de la semilla."""
        cargador.cargar(CLAVE)
        invernadero = Invernadero.objects.get(nombre_invernadero="Verificación Producción")
        pagina = bitacora.consultar_bitacora(Usuario.objects.get(email="agronomo@prueba4.local"), invernadero.pk)
        tipos = {r.tipo for dia in pagina.dias for r in dia.registros}
        self.assertTrue({"siembra", "merma"} <= tipos)

    def test_d_verificacion_es_idempotente_y_no_duplica_nada(self):
        """Una segunda corrida reutiliza todo: mismas filas, sin cuentas nuevas y sin nada creado."""
        cargador.cargar(CLAVE)
        contadores = lambda: (Usuario.objects.count(), Lote.objects.count(), Merma.objects.count(), TransicionEtapa.objects.count(), InsumoInvernadero.objects.count(), LoteInsumo.objects.count(), Invernadero.objects.count())
        antes = contadores()
        resumen = cargador.cargar(CLAVE)
        self.assertEqual(contadores(), antes)
        self.assertEqual(resumen.creado, ())

    def test_d_verificacion_audita_con_los_servicios_y_no_deja_la_contrasena_en_ningun_lado(self):
        """Carga llamando a los servicios: queda la auditoría (siembra, merma, ajustes) y la contraseña no aparece en la salida ni en la auditoría."""
        resumen = cargador.cargar(CLAVE)
        acciones = set(RegistroAuditoria.objects.values_list("accion", flat=True))
        self.assertTrue({"planificacion_siembra", "concrecion_siembra", "registro_merma", "planificacion_transicion", "ajuste_stock"} <= acciones)
        self.assertNotIn(CLAVE, str(resumen))
        self.assertFalse(any(CLAVE in str(r.detalle) for r in RegistroAuditoria.objects.all()))
