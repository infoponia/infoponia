# Pruebas de la carga de las secciones 1 a 11 de ``docs/demo/datos_de_la_demo.md`` (DAT-01, paso 2). Cargan UNA vez (``setUpTestData``) con
# el candado sustituido (se llama a ``carga.cargar`` directo, sin pasar por el comando) y comprueban los valores de la tabla de datos.
# Los secretos de las pruebas se inventan en cada corrida: ninguna contraseña queda escrita en el archivo.

import secrets
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from comercial.models import Cliente, DireccionCliente, Vehiculo
from compras.models import Proveedor
from contabilidad.models import EjercicioContable
from contabilidad.tests.fabricas import PlanDeCuentasMixin
from core.models import RegistroAuditoria, Usuario
from demo import carga
from inventario import alertas as alertas_de_inventario
from inventario.models import InsumoInvernadero, LoteInsumo, Semilla, TipoInsumo
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import (
    Alerta,
    ConfiguracionOperativa,
    DireccionUrbana,
    EtapaProductiva,
    Invernadero,
    PerfilOrganizacion,
    SectorProduccion,
    TransportistaInvernadero,
    Variedad,
)

BASE = "ejemplo"


class CargaBaseTests(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """DAT-01 paso 2: con el candado sustituido, se carga todo lo que existe en el repo, con los valores del archivo de datos."""

    @classmethod
    def setUpTestData(cls):
        cls.hoy = timezone.localdate()
        cls.contrasena = secrets.token_urlsafe(12)
        cls.contexto = carga.Contexto(hoy=cls.hoy, base=BASE, contrasena=cls.contrasena)
        cls.lineas = carga.cargar(cls.contexto)

    def _norte(self):
        return Invernadero.objects.get(nombre_invernadero="Norte")

    def _existencia(self, invernadero, nombre):
        return InsumoInvernadero.objects.get(invernadero__nombre_invernadero=invernadero, insumo__nombre_insumo=nombre)

    def _stock(self, invernadero, nombre):
        lotes = LoteInsumo.objects.filter(insumo_invernadero=self._existencia(invernadero, nombre))
        return sum(lote.cantidad_disponible for lote in lotes)

    # ---- salida ----

    def test_dat_01_una_linea_por_seccion_en_el_orden_del_archivo(self):
        """DAT-01 paso 3: una línea por sección (1 a 11), en el orden del archivo de datos aunque se ejecuten en otro."""
        numeros = [int(linea.split(". ")[0].split(": ")[1]) for linea in self.lineas]
        self.assertEqual(numeros, list(range(1, 15)))

    def test_dat_01_ninguna_seccion_se_saltea_porque_todo_existe_en_el_repo(self):
        """DAT-01 paso 0: todas las secciones tienen su servicio; nada se saltea."""
        self.assertTrue(all(linea.startswith("Cargado: ") for linea in self.lineas), self.lineas)

    def test_dat_01_las_lineas_no_incluyen_la_contrasena(self):
        """Decisión de la demo, punto 6: la contraseña no sale en ninguna línea."""
        self.assertFalse(any(self.contrasena in linea for linea in self.lineas))

    # ---- sección 4: cuentas ----

    def test_dat_01_diez_cuentas_cada_una_con_su_rol(self):
        """Sección 4: 10 cuentas con el rol y el correo de la tabla."""
        esperadas = {
            "gerente1": Usuario.Rol.GERENTE,
            "agronomo1": Usuario.Rol.AGRONOMO,
            "agronomo2": Usuario.Rol.AGRONOMO,
            "capataz1": Usuario.Rol.CAPATAZ,
            "capataz2": Usuario.Rol.CAPATAZ,
            "vendedor1": Usuario.Rol.VENDEDOR,
            "transportista1": Usuario.Rol.TRANSPORTISTA,
            "transportista2": Usuario.Rol.TRANSPORTISTA,
            "tecnico1": Usuario.Rol.TECNICO,
            "contador1": Usuario.Rol.CONTADOR,
        }
        self.assertEqual(Usuario.objects.exclude(rol="").count(), 10)
        for clave, rol in esperadas.items():
            cuenta = Usuario.objects.get(email=f"{BASE}+{clave}@gmail.com")
            self.assertEqual(cuenta.rol, rol, clave)

    def test_dat_01_las_cuentas_estan_activas_con_la_contrasena_de_la_variable_y_sin_temporal(self):
        """Sección 4: activas, con la contraseña de la variable y sin contraseña temporal ni invitación pendiente."""
        for cuenta in Usuario.objects.exclude(rol=""):
            self.assertTrue(cuenta.is_active, cuenta.email)
            self.assertTrue(cuenta.check_password(self.contrasena), cuenta.email)
            self.assertIsNone(cuenta.fecha_contrasena_temporal, cuenta.email)
            self.assertIsNone(cuenta.fecha_invitacion, cuenta.email)

    def test_dat_01_los_nueve_que_no_son_gerente_quedan_auditados_por_el_servicio(self):
        """Decisión de la demo, punto 3: las altas por servicio dejan su registro de auditoría (el Gerente, por ORM, no)."""
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ALTA).count(), 9)

    # ---- secciones 1 y 2 ----

    def test_dat_01_el_perfil_de_la_organizacion_tiene_los_valores_de_la_tabla(self):
        """Sección 1."""
        perfil = PerfilOrganizacion.objects.get(singleton=1)
        self.assertEqual(perfil.nombre_organizacion, "Huerta Hidropónica del Paraná")
        self.assertEqual(perfil.cuit_organizacion, "30712345604")
        self.assertEqual(perfil.telefono_organizacion, "3764 412345")
        self.assertEqual(perfil.email_organizacion, f"{BASE}+organizacion1@gmail.com")
        self.assertEqual(perfil.direccion_organizacion, "Ruta Nacional 12 km 1335, Candelaria, Misiones")

    def test_dat_01_los_cuatro_valores_de_la_configuracion_operativa(self):
        """Sección 2: solo cambian estos cuatro; el resto queda en su valor inicial."""
        configuracion = ConfiguracionOperativa.objects.get(singleton=1)
        self.assertEqual(configuracion.dias_pre_reserva_suministro, 7)
        self.assertEqual(configuracion.cant_reintentos_comando, 1)
        self.assertEqual(configuracion.segundos_intervalo_reintento, 10)
        self.assertEqual(configuracion.cant_lecturas_confirmacion, 2)
        self.assertEqual(configuracion.dias_horizonte_cosecha, 30)  # uno que no se toca

    # ---- sección 5 ----

    def test_dat_01_dos_invernaderos_con_su_personal(self):
        """Sección 5: Norte (agronomo1, capataz1, vendedor1, tecnico1) y Sur (agronomo2, capataz2, vendedor1, sin Técnico)."""
        norte, sur = self._norte(), Invernadero.objects.get(nombre_invernadero="Sur")
        self.assertEqual(
            (norte.agronomo.email, norte.capataz.email, norte.vendedor.email, norte.tecnico.email),
            tuple(f"{BASE}+{clave}@gmail.com" for clave in ("agronomo1", "capataz1", "vendedor1", "tecnico1")),
        )
        self.assertEqual(
            (sur.agronomo.email, sur.capataz.email, sur.vendedor.email),
            tuple(f"{BASE}+{clave}@gmail.com" for clave in ("agronomo2", "capataz2", "vendedor1")),
        )
        self.assertIsNone(sur.tecnico)

    def test_dat_01_siete_sectores_con_su_tipo_de_etapa_y_sus_agujeros(self):
        """Sección 5: los 7 sectores, todos activos."""
        sectores = {
            (s.invernadero.nombre_invernadero, s.nombre_sector): (s.tipo_etapa.codigo, s.cant_agujeros_total)
            for s in SectorProduccion.objects.select_related("invernadero", "tipo_etapa")
        }
        self.assertEqual(
            sectores,
            {
                ("Norte", "Germinación N1"): ("germinacion", 400),
                ("Norte", "Crecimiento N1"): ("crecimiento", 600),
                ("Norte", "Maduración N1"): ("maduracion", 600),
                ("Norte", "Maduración N2"): ("maduracion", 400),
                ("Sur", "Germinación S1"): ("germinacion", 300),
                ("Sur", "Crecimiento S1"): ("crecimiento", 400),
                ("Sur", "Maduración S1"): ("maduracion", 400),
            },
        )
        self.assertFalse(SectorProduccion.objects.exclude(estado_sector=SectorProduccion.Estado.ACTIVO).exists())

    def test_dat_01_cada_transportista_trabaja_en_su_invernadero(self):
        """Sección 5: transportista1 en Norte y transportista2 en Sur."""
        asignados = {
            t.transportista.email: t.invernadero.nombre_invernadero for t in TransportistaInvernadero.objects.all()
        }
        self.assertEqual(
            asignados, {f"{BASE}+transportista1@gmail.com": "Norte", f"{BASE}+transportista2@gmail.com": "Sur"}
        )

    # ---- sección 6 ----

    def test_dat_01_tres_variedades_con_su_ciclo_y_su_semilla(self):
        """Sección 6: las 3 variedades con sus días por etapa y la semilla que crea el sistema."""
        ciclos = {
            v.nombre_variedad: {e.tipo_etapa.codigo: e.duracion_estimada_dias for e in EtapaProductiva.objects.filter(ciclo__variedad=v)}
            for v in Variedad.objects.all()
        }
        self.assertEqual(
            ciclos,
            {
                "Criolla": {"germinacion": 10, "crecimiento": 20, "maduracion": 14},
                "Morada": {"germinacion": 10, "crecimiento": 20, "maduracion": 14},
                "Genovesa": {"germinacion": 10, "crecimiento": 25, "maduracion": 10},
            },
        )
        self.assertEqual(Semilla.objects.count(), 3)

    def test_dat_01_los_rangos_de_la_variedad_criolla(self):
        """Sección 6: temperatura 16–27, humedad 60–85, luz 20000–45000, fotoperíodo 10–16, postcosecha 7 y peso 250."""
        v = Variedad.objects.get(nombre_variedad="Criolla")
        self.assertEqual((v.temp_ambiente_min, v.temp_ambiente_max), (Decimal("16"), Decimal("27")))
        self.assertEqual((v.humedad_min, v.humedad_max), (Decimal("60"), Decimal("85")))
        self.assertEqual((v.intensidad_luz_min, v.intensidad_luz_max), (Decimal("20000"), Decimal("45000")))
        self.assertEqual((v.fotoperiodo_min, v.fotoperiodo_max), (Decimal("10"), Decimal("16")))
        self.assertEqual((v.duracion_post_cosecha, v.peso_promedio_planta), (7, 250))
        self.assertEqual(v.perfil_familia, "hoja_verde")

    # ---- sección 7 ----

    def test_dat_01_dos_categorias_nuevas_que_no_son_del_sistema(self):
        """Sección 7: Nutrientes y Sanidad vegetal, con consumo directo como costo de los lotes."""
        nuevas = TipoInsumo.objects.filter(es_del_sistema=False)
        self.assertEqual(
            {(t.nombre_tipo_insumo, t.consumo_directo) for t in nuevas},
            {("Nutrientes", "como_costo_de_los_lotes"), ("Sanidad vegetal", "como_costo_de_los_lotes")},
        )

    def test_dat_01_las_existencias_de_norte_tienen_el_stock_de_la_tabla(self):
        """Sección 7: stock de Norte tras la carga inicial."""
        esperado = {
            "Bandeja de cartón x 12": Decimal("150"),
            "Bolsa compostable 30x40": Decimal("400"),
            "Solución nutritiva A": Decimal("12"),
            "Fungicida biológico": Decimal("8"),
            "Nodo ESP32": Decimal("2"),
            "Motor de ventana": Decimal("2"),
        }
        for nombre, cantidad in esperado.items():
            self.assertEqual(self._stock("Norte", nombre), cantidad, nombre)

    def test_dat_01_las_existencias_de_sur_tienen_el_stock_de_la_tabla(self):
        """Sección 7: stock de Sur (la semilla de Albahaca la nombra el sistema, así que se busca por su variedad)."""
        self.assertEqual(self._stock("Sur", "Bandeja de cartón x 12"), Decimal("100"))
        self.assertEqual(self._stock("Sur", "Solución nutritiva A"), Decimal("40"))
        genovesa = Semilla.objects.get(variedad__nombre_variedad="Genovesa")
        lotes = LoteInsumo.objects.filter(insumo_invernadero__insumo=genovesa, insumo_invernadero__invernadero__nombre_invernadero="Sur")
        self.assertEqual(sum(lote.cantidad_disponible for lote in lotes), Decimal("1000"))

    def test_dat_01_las_semillas_tienen_minimo_precio_y_vencimiento_de_la_tabla(self):
        """Sección 7: semilla de Criolla en Norte, mínimo 200, precio 15,00, 2000 unidades que vencen HOY+90."""
        criolla = Semilla.objects.get(variedad__nombre_variedad="Criolla")
        existencia = InsumoInvernadero.objects.get(insumo=criolla, invernadero__nombre_invernadero="Norte")
        self.assertEqual(existencia.cant_min_insumo, Decimal("200"))
        self.assertEqual(existencia.referencia_precio, Decimal("15.00"))
        lote = existencia.lotes.get()
        self.assertEqual((lote.cantidad_disponible, lote.fecha_vencimiento), (Decimal("2000"), self.hoy + timedelta(days=90)))

    def test_dat_01_el_fungicida_tiene_dos_lotes_y_uno_vence_en_tres_dias(self):
        """Sección 7: Fungicida biológico de Norte, 3 l que vencen HOY+3 y 5 l que vencen HOY+120 (dos ajustes de carga inicial)."""
        lotes = self._existencia("Norte", "Fungicida biológico").lotes.order_by("fecha_vencimiento")
        self.assertEqual(
            [(lote.cantidad_disponible, lote.fecha_vencimiento) for lote in lotes],
            [(Decimal("3"), self.hoy + timedelta(days=3)), (Decimal("5"), self.hoy + timedelta(days=120))],
        )

    def test_dat_01_la_solucion_nutritiva_de_norte_esta_por_debajo_del_minimo_con_su_alerta(self):
        """Sección 7: 12 l contra un mínimo de 20: queda la alerta de stock bajo activa; la de Sur (40 contra 15) no tiene."""
        existencia = self._existencia("Norte", "Solución nutritiva A")
        self.assertEqual(existencia.cant_min_insumo, Decimal("20"))
        self.assertLess(self._stock("Norte", "Solución nutritiva A"), existencia.cant_min_insumo)
        activas = Alerta.objects.filter(
            tipo_alerta=alertas_de_inventario.INSUMO_BAJO_MINIMO,
            estado_alerta=Alerta.Estado.ACTIVA,
            clave_estado=f"insumo:{existencia.pk}",
        )
        self.assertEqual(activas.count(), 1)
        sur = self._existencia("Sur", "Solución nutritiva A")
        self.assertFalse(Alerta.objects.filter(estado_alerta=Alerta.Estado.ACTIVA, clave_estado=f"insumo:{sur.pk}").exists())

    def test_dat_01_los_siete_repuestos_de_hardware_estan_en_norte_con_su_precio(self):
        """Sección 7: cada repuesto, mínimo 0, 2 unidades y el precio de la tabla."""
        precios = {
            "Nodo ESP32": "18000",
            "Sensor DHT22": "6500",
            "Sensor de luz BH1750": "4800",
            "Sonda DS18B20": "3900",
            "Sensor de nivel flotante": "5200",
            "Ventilador 12 V": "15000",
            "Motor de ventana": "27000",
        }
        for nombre, precio in precios.items():
            existencia = self._existencia("Norte", nombre)
            self.assertEqual(existencia.cant_min_insumo, 0, nombre)
            self.assertEqual(existencia.referencia_precio, Decimal(precio), nombre)
            self.assertEqual(self._stock("Norte", nombre), Decimal("2"), nombre)

    # ---- secciones 8, 9 y 10 ----

    def test_dat_01_tres_proveedores_con_sus_especialidades(self):
        """Sección 8: proveedor1 y proveedor3 comparten la especialidad Nutrientes (los que invita el pedido automático)."""
        self.assertEqual(Proveedor.objects.count(), 3)
        p1 = Proveedor.objects.get(cuit_proveedor="30718889908")
        p3 = Proveedor.objects.get(cuit_proveedor="20334445551")
        self.assertEqual(p1.email_proveedor, f"{BASE}+proveedor1@gmail.com")
        self.assertEqual(
            set(p1.especialidades.values_list("nombre_tipo_insumo", flat=True)), {"Nutrientes", "Sanidad vegetal", "Semillas"}
        )
        self.assertEqual((p3.nombre_proveedor, p3.apellido_proveedor), ("Ramón", "Ojeda"))
        self.assertEqual(set(p3.especialidades.values_list("nombre_tipo_insumo", flat=True)), {"Nutrientes", "Envases"})
        p2 = Proveedor.objects.get(cuit_proveedor="30713334401")
        self.assertEqual(set(p2.especialidades.values_list("nombre_tipo_insumo", flat=True)), {"Repuestos de hardware"})

    def test_dat_01_tres_clientes_cada_uno_con_su_direccion(self):
        """Sección 9: 3 clientes, cada uno con una dirección urbana activa."""
        self.assertEqual(Cliente.objects.count(), 3)
        esperadas = {"30714567809": ("Av. Uruguay", "2450"), "30711223300": ("Av. Las Heras", "1180"), "27315558889": ("Calle Junín", "1745")}
        for cuit, (calle, numero) in esperadas.items():
            cliente = Cliente.objects.get(cuit_cliente=cuit)
            relacion = DireccionCliente.objects.get(cliente=cliente)
            hija = DireccionUrbana.objects.get(pk=relacion.direccion_id)
            self.assertEqual((hija.calle, hija.numero_calle), (calle, numero), cuit)
        self.assertEqual(Cliente.objects.get(cuit_cliente="27315558889").apellido_cliente, "Villalba")

    def test_dat_01_dos_vehiculos_con_su_transportista(self):
        """Sección 10: AE123BC (transportista1, 800 kg) y AF456DE (transportista2, 500 kg)."""
        self.assertEqual(Vehiculo.objects.count(), 2)
        hilux = Vehiculo.objects.get(patente="AE123BC")
        self.assertEqual((hilux.tipo_vehiculo, hilux.marca, hilux.modelo, hilux.capacidad_carga), ("camioneta", "Toyota", "Hilux", Decimal("800")))
        self.assertEqual(hilux.transportista.email, f"{BASE}+transportista1@gmail.com")
        self.assertEqual(Vehiculo.objects.get(patente="AF456DE").transportista.email, f"{BASE}+transportista2@gmail.com")

    # ---- sección 11 ----

    def test_dat_01_el_ejercicio_empieza_el_primer_dia_del_mes_aunque_la_carga_de_stock_genere_asientos(self):
        """Sección 11 y decisión del estudiante: el ejercicio se crea ANTES de la carga de stock, que asienta con la fecha de hoy."""
        ejercicio = EjercicioContable.objects.get()
        self.assertEqual(ejercicio.fecha_inicio_ejercicio, date(self.hoy.year, self.hoy.month, 1))
        self.assertTrue(ejercicio.asientos.filter(fecha_asiento=self.hoy).exists())  # los de la carga inicial de stock
