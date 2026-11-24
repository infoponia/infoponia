# Pruebas de lo que `compras` registra en otras apps por los pedidos (CMP-02b, paso 3; A4 de D-37, D-87 punto 5 y docs/api/extensiones_de_maestros.md y
# docs/api/extensiones_de_inventario.md). Cada registrante de lectura lleva las tres pruebas mínimas (con datos, sin datos y sin consultas por fila):
#   - ``asignaciones_de_cuenta(cuenta)`` → ``[Asignacion]``: lo que la ventana de baja de una cuenta dice de sus pedidos en curso (regla 4 de USR-BAJ-USR).
#   - ``contar_traspaso(invernadero, rol, saliente, entrante)`` → ``[]`` siempre: los pedidos que se cancelan no los «recibe» nadie.
#   - ``aviso_de_traspaso(invernadero, rol, saliente, entrante)`` → ``list[str]``: lo que se cancela al cambiar el Agrónomo (punto nuevo de maestros).
#   - ``impedimento_de_deshabilitacion(insumo_invernadero)`` → ``list[Impedimento]`` con el código ``pedido_en_curso`` y la URL de la ficha del pedido (H20).
# Los que escriben se prueban con datos y sin datos y por la integración con los servicios reales (cuyos registrantes toma ``CompraConfig.ready()``):
#   - ``efecto_de_baja_de_cuenta(actor, cuenta)`` → ``Efecto``: cancela los pedidos «en cotización» del Agrónomo con la causa ``agronomo_inactivo`` (MD-62, H17).
#   - ``traspasar_pedidos(actor, invernadero, rol, saliente, entrante)`` → ``list[Pedido]``: cancela con ``agronomo_sin_invernadero`` los del saliente con algún
#     detalle a ese invernadero.
# El módulo se toma dentro de cada prueba (``perezoso``).


from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from compras.models import Pedido
from compras.tests.fabricas import detalle_de_pedido, enlace_de, invitar, proveedor
from compras.tests.fabricas import pedido as armar_pedido
from core import servicios as servicios_de_core
from core.extensiones import Asignacion, Efecto
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.servicios import insumos_invernadero
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, perezoso
from maestros.models import Invernadero
from maestros.servicios import invernaderos
from maestros.tests.fabricas import crear_agronomo, crear_agronomo_con_invernadero, crear_invernadero
from maestros.tests.test_prod_mod_inv import datos_de

registrantes = perezoso("compras.servicios.registrantes")


class RegistrantesBase(ConDatosDeInventario, TestCase):
    """Ana con dos invernaderos (Norte y Norte 2), Beto con Sur y un Gerente. Una lechuga habilitada en cada uno."""

    def setUp(self):
        self.ana, self.norte = crear_agronomo_con_invernadero("Norte", email="ana@infoponia.com")
        self.norte2 = crear_invernadero("Norte 2", agronomo=self.ana)
        self.beto, self.sur = crear_agronomo_con_invernadero("Sur", email="beto@infoponia.com")
        self.gerente = crear_gerente()
        self.lechuga = insumo("Lechuga", unidad="unidad")
        self.en_norte = existencia(self.lechuga, self.norte, minimo=20, precio="12.50")
        self.en_norte2 = existencia(self.lechuga, self.norte2, minimo=20, precio="12.50")
        self.en_sur = existencia(self.lechuga, self.sur, minimo=10, precio="11.00")
        self.prv = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com")

    def pedido_de(self, agronomo, *existencias, estado="en_cotizacion", dias=3):
        """Un pedido de ``agronomo`` con un detalle por cada existencia, con un invitado y su enlace vigente."""
        causa = "manual" if estado == "cancelado" else None
        creado = armar_pedido(agronomo, dias_al_limite=dias, estado=estado, causa=causa, motivo="x" if causa else "")
        for e in existencias:
            detalle_de_pedido(creado, e, cantidad="5")
        enlace_de(invitar(creado, self.prv))
        return creado

    def estado(self, pedido):
        pedido.refresh_from_db()
        return pedido.estado_pedido, pedido.causa_cancelacion


class AsignacionesDeCuentaTests(RegistrantesBase):
    """`registrar_asignaciones_de_cuenta`: la ventana de baja de un Agrónomo dice cuántos pedidos se cancelan (regla 4 de USR-BAJ-USR, D-43)."""

    def test_con_datos_un_agronomo_con_pedidos_en_cotizacion_los_cuenta_y_dice_que_pasa(self):
        """Con datos: cuenta solo los pedidos «en cotización» del Agrónomo y avisa que se cancelan solos y que se avisa a los proveedores."""
        self.pedido_de(self.ana, self.en_norte)
        self.pedido_de(self.ana, self.en_norte2)
        self.pedido_de(self.ana, self.en_norte, estado="cerrado")
        self.pedido_de(self.beto, self.en_sur)
        asignaciones = registrantes.asignaciones_de_cuenta(self.ana)
        self.assertEqual(len(asignaciones), 1)
        self.assertIsInstance(asignaciones[0], Asignacion)
        self.assertEqual((asignaciones[0].texto, asignaciones[0].cantidad), ("Pedidos de cotización en curso", 2))
        self.assertIn("cancelan solos", asignaciones[0].que_pasa)
        self.assertIn("correo", asignaciones[0].que_pasa)

    def test_sin_datos_no_dice_nada(self):
        """Sin datos: un Agrónomo sin pedidos en curso, y cualquier otro rol, no tienen nada asignado en compras."""
        self.pedido_de(self.ana, self.en_norte, estado="cancelado")
        for cuenta in (self.ana, self.beto, self.gerente, crear_capataz()):
            with self.subTest(cuenta=cuenta):
                self.assertEqual(registrantes.asignaciones_de_cuenta(cuenta), [])

    def test_sin_consultas_por_fila_la_cantidad_de_consultas_no_depende_de_la_de_pedidos(self):
        """Sin consultas por fila: con 1 o con 4 pedidos, la misma cantidad de consultas."""
        self.pedido_de(self.ana, self.en_norte)
        with CaptureQueriesContext(connection) as con_uno:
            registrantes.asignaciones_de_cuenta(self.ana)
        for _ in range(3):
            self.pedido_de(self.ana, self.en_norte)
        with CaptureQueriesContext(connection) as con_cuatro:
            registrantes.asignaciones_de_cuenta(self.ana)
        self.assertEqual(len(con_cuatro), len(con_uno))


class EfectoDeBajaDeCuentaTests(RegistrantesBase):
    """`registrar_efecto_de_baja_de_cuenta` (MD-62, regla 5 de 8.22, H17): la baja de un Agrónomo cancela sus pedidos en cotización."""

    def test_con_datos_cancela_los_pedidos_en_cotizacion_del_agronomo_y_los_informa(self):
        """Con datos: solo los suyos y «en cotización»; el efecto devuelve los pedidos como afectados y como ``datos.pedidos_cancelados``."""
        uno = self.pedido_de(self.ana, self.en_norte)
        dos = self.pedido_de(self.ana, self.en_norte2)
        cerrado = self.pedido_de(self.ana, self.en_norte, estado="cerrado")
        ajeno = self.pedido_de(self.beto, self.en_sur)
        self.ana.is_active = False
        self.ana.save()
        efecto = registrantes.efecto_de_baja_de_cuenta(self.gerente, self.ana)
        self.assertIsInstance(efecto, Efecto)
        self.assertEqual(sorted(p.pk for p in efecto.afectados), sorted([uno.pk, dos.pk]))
        self.assertEqual(sorted(r["id"] for r in efecto.datos["pedidos_cancelados"]), sorted([uno.pk, dos.pk]))
        self.assertEqual((self.estado(uno), self.estado(dos)), (("cancelado", "agronomo_inactivo"), ("cancelado", "agronomo_inactivo")))
        self.assertEqual((self.estado(cerrado)[0], self.estado(ajeno)[0]), ("cerrado", "en_cotizacion"))

    def test_sin_datos_no_cancela_nada_y_devuelve_un_efecto_vacio(self):
        """Sin datos: una cuenta que no es Agrónomo o un Agrónomo sin pedidos en curso no cambia nada."""
        pedido = self.pedido_de(self.beto, self.en_sur)
        for cuenta in (self.ana, self.gerente, crear_capataz()):
            with self.subTest(cuenta=cuenta):
                efecto = registrantes.efecto_de_baja_de_cuenta(self.gerente, cuenta)
                self.assertEqual((list(efecto.afectados), efecto.datos), ([], {}))
        self.assertEqual(self.estado(pedido)[0], "en_cotizacion")

    def test_la_baja_de_la_cuenta_cancela_los_pedidos_y_los_deja_en_su_registro(self):
        """Integración con ``baja_usuario``: se cancela con la causa y el texto fijos, la auditoría de la baja lista los pedidos y el Gerente que dio la baja no recibe aviso (H21)."""
        pedido = self.pedido_de(self.ana, self.en_norte)
        servicios_de_core.baja_usuario(self.gerente, self.ana.pk)
        pedido.refresh_from_db()
        self.assertEqual((pedido.estado_pedido, pedido.causa_cancelacion, pedido.motivo_cancelacion), ("cancelado", "agronomo_inactivo", "Agrónomo inactivo"))
        registro = RegistroAuditoria.objects.get(accion="baja", usuario=self.gerente)
        self.assertIn(pedido.pk, [a["id"] for a in registro.afectados if a["modelo"] == "compras.pedido"])
        self.assertEqual([r["id"] for r in registro.detalle["datos"]["pedidos_cancelados"]], [pedido.pk])
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_pedido", usuario__isnull=True, rol="infoponia").count(), 1)
        self.assertFalse(Notificacion.objects.filter(destinatario=self.gerente, titulo__contains="cancelado").exists())

    def test_la_baja_de_otra_cuenta_no_toca_los_pedidos(self):
        """Integración: dar de baja a un Capataz no cancela ningún pedido."""
        capataz = crear_capataz(email="cap@infoponia.com")
        pedido = self.pedido_de(self.ana, self.en_norte)
        servicios_de_core.baja_usuario(self.gerente, capataz.pk)
        self.assertEqual(self.estado(pedido)[0], "en_cotizacion")

    def test_la_ventana_de_baja_informa_cuantos_pedidos_se_cancelaran(self):
        """Regla 4 de USR-BAJ-USR (integración con ``core.extensiones``): la lista de lo asignado incluye los pedidos en curso."""
        from core import extensiones

        self.pedido_de(self.ana, self.en_norte)
        textos = [(a.texto, a.cantidad) for a in extensiones.asignaciones_de_cuenta(self.ana)]
        self.assertIn(("Pedidos de cotización en curso", 1), textos)


class TraspasoDelAgronomoTests(RegistrantesBase):
    """`registrar_traspaso` con el rol ``agronomo`` (MD-62, H17): los pedidos del saliente con algún detalle a ese invernadero se cancelan."""

    def test_contar_no_cuenta_nada_porque_nadie_recibe_pedidos_cancelados(self):
        """``contar`` siempre ``[]``: la ventana no puede decir que el Agrónomo entrante «recibe» pedidos que se cancelan."""
        self.pedido_de(self.ana, self.en_norte)
        nuevo = crear_agronomo(email="nuevo@infoponia.com")
        self.assertEqual(registrantes.contar_traspaso(self.norte, "agronomo", self.ana, nuevo), [])

    def test_aviso_con_datos_dice_cuantos_pedidos_se_cancelan_y_de_quien(self):
        """Con datos: «Se cancelan N pedidos de cotización en curso de {saliente} con destino a este invernadero…», solo los que tienen un detalle ahí."""
        self.pedido_de(self.ana, self.en_norte)
        self.pedido_de(self.ana, self.en_norte, self.en_norte2)
        self.pedido_de(self.ana, self.en_norte2)
        self.pedido_de(self.ana, self.en_norte, estado="cerrado")
        nuevo = crear_agronomo(email="nuevo@infoponia.com")
        (texto,) = registrantes.aviso_de_traspaso(self.norte, "agronomo", self.ana, nuevo)
        self.assertIn("2 pedidos de cotización en curso", texto)
        self.assertIn(self.ana.get_full_name() or self.ana.email, texto)
        self.assertIn("correo", texto)

    def test_aviso_en_singular_con_un_solo_pedido(self):
        """Con un pedido el texto va en singular."""
        self.pedido_de(self.ana, self.en_norte)
        (texto,) = registrantes.aviso_de_traspaso(self.norte, "agronomo", self.ana, None)
        self.assertIn("1 pedido de cotización en curso", texto)

    def test_aviso_sin_datos_no_dice_nada(self):
        """Sin datos: otro rol, sin Agrónomo saliente o sin pedidos en ese invernadero, el aviso es vacío."""
        self.pedido_de(self.ana, self.en_norte2)
        nuevo = crear_agronomo(email="nuevo@infoponia.com")
        self.assertEqual(registrantes.aviso_de_traspaso(self.norte, "agronomo", self.ana, nuevo), [])
        self.assertEqual(registrantes.aviso_de_traspaso(self.norte2, "capataz", self.ana, nuevo), [])
        self.assertEqual(registrantes.aviso_de_traspaso(self.norte2, "agronomo", None, nuevo), [])

    def test_aviso_sin_consultas_por_fila(self):
        """Sin consultas por fila: la misma cantidad de consultas con 1 o con 4 pedidos."""
        self.pedido_de(self.ana, self.en_norte)
        with CaptureQueriesContext(connection) as con_uno:
            registrantes.aviso_de_traspaso(self.norte, "agronomo", self.ana, None)
        for _ in range(3):
            self.pedido_de(self.ana, self.en_norte)
        with CaptureQueriesContext(connection) as con_cuatro:
            registrantes.aviso_de_traspaso(self.norte, "agronomo", self.ana, None)
        self.assertEqual(len(con_cuatro), len(con_uno))

    def test_traspasar_cancela_los_del_saliente_con_un_detalle_en_ese_invernadero(self):
        """Con datos: se cancelan (causa ``agronomo_sin_invernadero``) los pedidos de Ana con algún detalle a Norte, aunque tengan otros destinos; no los que solo
        van a Norte 2, ni los de otro Agrónomo, ni los que ya no están en cotización. Devuelve los pedidos cancelados para la auditoría."""
        solo_norte = self.pedido_de(self.ana, self.en_norte)
        ambos = self.pedido_de(self.ana, self.en_norte, self.en_norte2)
        solo_norte2 = self.pedido_de(self.ana, self.en_norte2)
        cerrado = self.pedido_de(self.ana, self.en_norte, estado="cerrado")
        ajeno = self.pedido_de(self.beto, self.en_sur)
        nuevo = crear_agronomo(email="nuevo@infoponia.com")
        cancelados = registrantes.traspasar_pedidos(self.gerente, self.norte, "agronomo", self.ana, nuevo)
        self.assertEqual(sorted(p.pk for p in cancelados), sorted([solo_norte.pk, ambos.pk]))
        self.assertEqual((self.estado(solo_norte), self.estado(ambos)), (("cancelado", "agronomo_sin_invernadero"),) * 2)
        self.assertEqual((self.estado(solo_norte2)[0], self.estado(cerrado)[0], self.estado(ajeno)[0]), ("en_cotizacion", "cerrado", "en_cotizacion"))

    def test_traspasar_sin_datos_o_con_otro_rol_no_hace_nada(self):
        """Sin datos: otro rol, o sin Agrónomo saliente, devuelve ``[]`` y no cambia nada."""
        pedido = self.pedido_de(self.ana, self.en_norte)
        nuevo = crear_agronomo(email="nuevo@infoponia.com")
        self.assertEqual(registrantes.traspasar_pedidos(self.gerente, self.norte, "capataz", self.ana, nuevo), [])
        self.assertEqual(registrantes.traspasar_pedidos(self.gerente, self.norte, "agronomo", None, nuevo), [])
        self.assertEqual(self.estado(pedido)[0], "en_cotizacion")

    def test_cambiar_el_agronomo_del_invernadero_avisa_y_cancela_y_lo_deja_en_el_registro(self):
        """Integración con ``modificar_invernadero``: sin confirmar, el aviso de la ventana trae el texto de compras; confirmado, cancela y deja los pedidos entre los
        afectados de ``modificacion_invernadero``."""
        solo_norte = self.pedido_de(self.ana, self.en_norte)
        solo_norte2 = self.pedido_de(self.ana, self.en_norte2)
        nuevo = crear_agronomo(email="nuevo@infoponia.com")
        datos = datos_de(self.norte) | {"agronomo_id": nuevo.pk}
        with self.assertRaises(invernaderos.FaltaConfirmarPersonal) as contexto:
            invernaderos.modificar_invernadero(self.gerente, self.norte.pk, **datos)
        (cambio,) = [c for c in contexto.exception.aviso if c["rol"] == "agronomo"]
        self.assertEqual(len(cambio["avisos"]), 1)
        self.assertIn("1 pedido de cotización en curso", cambio["avisos"][0])
        self.assertEqual(cambio["recibe"], [])
        self.assertEqual(self.estado(solo_norte)[0], "en_cotizacion")
        invernaderos.modificar_invernadero(self.gerente, self.norte.pk, **datos, personal_confirmado=True)
        self.assertEqual(self.estado(solo_norte), ("cancelado", "agronomo_sin_invernadero"))
        self.assertEqual(self.estado(solo_norte2)[0], "en_cotizacion")
        registro = RegistroAuditoria.objects.get(accion="modificacion_invernadero")
        self.assertIn(solo_norte.pk, [a["id"] for a in registro.afectados if a["modelo"] == "compras.pedido"])

    def test_quitar_al_agronomo_sin_reemplazo_tambien_avisa_y_cancela(self):
        """Integración: con el rol que queda vacío (sin Agrónomo entrante) la ventana igual avisa y los pedidos se cancelan; el aviso de campana va al Gerente (H21)."""
        pedido = self.pedido_de(self.ana, self.en_norte)
        datos = datos_de(self.norte) | {"agronomo_id": None}
        with self.assertRaises(invernaderos.FaltaConfirmarPersonal) as contexto:
            invernaderos.modificar_invernadero(self.gerente, self.norte.pk, **datos)
        (cambio,) = [c for c in contexto.exception.aviso if c["rol"] == "agronomo"]
        self.assertTrue(cambio["queda_vacio"])
        self.assertIn("1 pedido de cotización en curso", cambio["avisos"][0])
        invernaderos.modificar_invernadero(self.gerente, self.norte.pk, **datos, personal_confirmado=True)
        self.assertEqual(self.estado(pedido), ("cancelado", "agronomo_sin_invernadero"))
        self.assertFalse(Notificacion.objects.filter(destinatario=self.gerente, titulo__contains="cancelado").exists())  # el Gerente es quien actuó


class ImpedimentoDeDeshabilitacionTests(RegistrantesBase):
    """`registrar_impedimento_de_deshabilitacion` (H20, D-87 punto 5): un pedido «en cotización» impide deshabilitar el insumo en ese invernadero."""

    def test_con_datos_un_impedimento_por_pedido_con_su_enlace(self):
        """Con datos: código ``pedido_en_curso``, texto con el pedido y la fecha límite, cómo resolverlo y la URL de la ficha del pedido."""
        uno = self.pedido_de(self.ana, self.en_norte, dias=3)
        dos = self.pedido_de(self.ana, self.en_norte, dias=5)
        impedimentos = registrantes.impedimento_de_deshabilitacion(self.en_norte)
        self.assertEqual(sorted(i.codigo for i in impedimentos), ["pedido_en_curso"] * 2)
        por_url = {i.url: i for i in impedimentos}
        for pedido in (uno, dos):
            impedimento = por_url[reverse("compras:pedido_ficha", args=[pedido.pk])]
            self.assertEqual(impedimento.texto, f"Está en el pedido {pedido}, en cotización hasta el {pedido.fecha_limite_cotizaciones:%d/%m}.")
            self.assertTrue(impedimento.como_resolver)

    def test_sin_datos_un_pedido_cerrado_o_cancelado_o_de_otro_insumo_no_impide(self):
        """Sin datos: solo cuentan los pedidos «en cotización» con ese ``InsumoInvernadero``."""
        self.pedido_de(self.ana, self.en_norte, estado="cerrado")
        self.pedido_de(self.ana, self.en_norte, estado="cancelado")
        self.pedido_de(self.ana, self.en_norte2)
        self.assertEqual(registrantes.impedimento_de_deshabilitacion(self.en_norte), [])

    def test_sin_consultas_por_fila(self):
        """Sin consultas por fila: la misma cantidad de consultas con 1 o con 4 pedidos."""
        self.pedido_de(self.ana, self.en_norte)
        with CaptureQueriesContext(connection) as con_uno:
            registrantes.impedimento_de_deshabilitacion(self.en_norte)
        for _ in range(3):
            self.pedido_de(self.ana, self.en_norte)
        with CaptureQueriesContext(connection) as con_cuatro:
            registrantes.impedimento_de_deshabilitacion(self.en_norte)
        self.assertEqual(len(con_cuatro), len(con_uno))

    def test_deshabilitar_el_insumo_con_un_pedido_en_curso_se_rechaza_con_el_codigo(self):
        """Integración con CMP-DSH-IIN (precondición e, regla 2): el servicio real rechaza con ``pedido_en_curso``; al cancelar el pedido, se puede."""
        pedido = self.pedido_de(self.ana, self.en_norte)
        with self.assertRaises(ValidationError) as contexto:
            insumos_invernadero.deshabilitar_insumo(self.ana, self.en_norte.pk)
        self.assertIn("pedido_en_curso", [e.code for e in contexto.exception.error_dict[NON_FIELD_ERRORS]])
        self.en_norte.refresh_from_db()
        self.assertEqual(self.en_norte.estado_insumo_invernadero, "activo")
        Pedido.objects.filter(pk=pedido.pk).update(
            estado_pedido="cancelado", causa_cancelacion="manual", motivo_cancelacion="x", fecha_cierre_pedido=timezone.localdate()
        )
        insumos_invernadero.deshabilitar_insumo(self.ana, self.en_norte.pk)
        self.en_norte.refresh_from_db()
        self.assertEqual(self.en_norte.estado_insumo_invernadero, "inactivo")

    def test_dar_de_baja_el_invernadero_con_un_pedido_en_curso_se_rechaza_con_el_enlace_al_pedido(self):
        """Integración con PROD-BAJ-INV (precondición f): inventario junta los impedimentos de deshabilitación, y la URL del pedido llega a la ventana."""
        pedido = self.pedido_de(self.ana, self.en_norte)
        impedimentos = invernaderos.impedimentos_para_baja(self.gerente, self.norte.pk)
        en_curso = [i for i in impedimentos if i.codigo == "pedido_en_curso"]
        self.assertEqual([i.url for i in en_curso], [reverse("compras:pedido_ficha", args=[pedido.pk])])
        with self.assertRaises(ValidationError):
            invernaderos.baja_invernadero(self.gerente, self.norte.pk)
        self.assertEqual(Invernadero.objects.get(pk=self.norte.pk).estado_invernadero, "activo")



# ---------------------------------------------------------------------------------------------------------------------------------
# CMP-03, paso 4: el impedimento ``orden_de_compra_aprobada`` (H20, D-87 punto 5; disparador «Nacidos en CMP-02b», punto 1). ``impedimento_de_deshabilitacion``
# suma, por cada orden **no terminada** (pendiente de aprobación, aprobada o parcialmente recibida) con una línea a ese ``InsumoInvernadero``, un impedimento con
# el código ``orden_de_compra_aprobada`` (el código queda igual para no tocar ``inventario``). Es distinto del impedimento del proveedor ``orden_no_terminada``
# (``compras/servicios/proveedores.py``). La URL de la ficha de la orden la suma el paso 6, cuando existe esa pantalla.
# ---------------------------------------------------------------------------------------------------------------------------------

from compras.tests.fabricas import cotizacion_de, orden_de  # noqa: E402


class OrdenDeCompraImpideDeshabilitarTests(RegistrantesBase):
    """`registrar_impedimento_de_deshabilitacion` (H20): una orden no terminada con una línea a ese insumo en ese invernadero."""

    def orden_de_norte(self, estado="pendiente_aprobacion", iin=None, lineas=1):
        """Una orden en ``estado`` de un pedido de Ana con ``lineas`` líneas al ``iin`` (por omisión, la lechuga de Norte)."""
        iin = iin or self.en_norte
        pedido = armar_pedido(self.ana)
        detalle = detalle_de_pedido(pedido, iin, cantidad="5")
        cotizaciones = [cotizacion_de(pedido, self.prv, [(detalle, 5, "50.00", 2)])]
        return orden_de(pedido, cotizaciones, estado=estado, gerente=self.gerente, motivo="No hay presupuesto." if estado == "rechazada" else "")

    def test_con_datos_un_impedimento_por_orden_no_terminada(self):
        """Con datos: pendiente, aprobada y parcialmente recibida impiden; el texto nombra la orden y su estado, y trae cómo resolverlo."""
        ordenes_ = {estado: self.orden_de_norte(estado) for estado in ("pendiente_aprobacion", "aprobada", "parcialmente_recibida")}
        impedimentos = registrantes.impedimento_de_deshabilitacion(self.en_norte)
        self.assertEqual([i.codigo for i in impedimentos], ["orden_de_compra_aprobada"] * 3)
        for orden in ordenes_.values():
            (propio,) = [i for i in impedimentos if str(orden) in i.texto]
            self.assertIn(orden.get_estado_orden_compra_display().lower(), propio.texto.lower())
            self.assertTrue(propio.como_resolver)

    def test_sin_datos_una_orden_terminada_o_de_otro_insumo_no_impide(self):
        """Sin datos: rechazada, recibida y recibida con faltante ya terminaron; una orden del insumo de otro invernadero no impide este."""
        for estado in ("rechazada", "recibida", "recibida_con_faltante"):
            self.orden_de_norte(estado)
        self.orden_de_norte(iin=self.en_norte2)
        self.assertEqual(registrantes.impedimento_de_deshabilitacion(self.en_norte), [])

    def test_una_orden_con_varias_lineas_al_mismo_insumo_impide_una_sola_vez(self):
        """Una orden, un impedimento: dos proveedores con líneas al mismo ``InsumoInvernadero`` no lo duplican."""
        pedido = armar_pedido(self.ana)
        detalle = detalle_de_pedido(pedido, self.en_norte, cantidad="10")
        otro = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        orden_de(pedido, [cotizacion_de(pedido, self.prv, [(detalle, 5, "50.00", 2)]), cotizacion_de(pedido, otro, [(detalle, 5, "60.00", 3)])])
        self.assertEqual([i.codigo for i in registrantes.impedimento_de_deshabilitacion(self.en_norte)], ["orden_de_compra_aprobada"])

    def test_el_pedido_en_curso_y_la_orden_no_terminada_son_impedimentos_distintos(self):
        """H20: el insumo en un pedido «en cotización» (``pedido_en_curso``) y en una orden no terminada (``orden_de_compra_aprobada``) se informan por separado."""
        self.pedido_de(self.ana, self.en_norte)
        self.orden_de_norte()
        self.assertEqual(sorted(i.codigo for i in registrantes.impedimento_de_deshabilitacion(self.en_norte)), ["orden_de_compra_aprobada", "pedido_en_curso"])

    def test_sin_consultas_por_fila(self):
        """Sin consultas por fila: la misma cantidad de consultas con 1 o con 4 órdenes."""
        self.orden_de_norte()
        with CaptureQueriesContext(connection) as con_una:
            registrantes.impedimento_de_deshabilitacion(self.en_norte)
        for _ in range(3):
            self.orden_de_norte()
        with CaptureQueriesContext(connection) as con_cuatro:
            registrantes.impedimento_de_deshabilitacion(self.en_norte)
        self.assertEqual(len(con_cuatro), len(con_una))

    def test_deshabilitar_el_insumo_con_una_orden_pendiente_se_rechaza_con_el_codigo(self):
        """Integración con CMP-DSH-IIN (precondición e, regla 2): el servicio real rechaza con ``orden_de_compra_aprobada``; con la orden rechazada, se puede."""
        orden = self.orden_de_norte()
        with self.assertRaises(ValidationError) as contexto:
            insumos_invernadero.deshabilitar_insumo(self.ana, self.en_norte.pk)
        self.assertIn("orden_de_compra_aprobada", [e.code for e in contexto.exception.error_dict[NON_FIELD_ERRORS]])
        self.en_norte.refresh_from_db()
        self.assertEqual(self.en_norte.estado_insumo_invernadero, "activo")
        type(orden).objects.filter(pk=orden.pk).update(
            estado_orden_compra="rechazada", gerente=self.gerente, fecha_resolucion=timezone.localdate(), motivo_rechazo="No hay presupuesto."
        )
        insumos_invernadero.deshabilitar_insumo(self.ana, self.en_norte.pk)
        self.en_norte.refresh_from_db()
        self.assertEqual(self.en_norte.estado_insumo_invernadero, "inactivo")

    def test_dar_de_baja_el_invernadero_con_una_orden_aprobada_se_rechaza(self):
        """Integración con PROD-BAJ-INV (precondición f): la orden aprobada sin recibir llega a la ventana de baja del invernadero."""
        self.orden_de_norte("aprobada")
        codigos = [i.codigo for i in invernaderos.impedimentos_para_baja(self.gerente, self.norte.pk)]
        self.assertIn("orden_de_compra_aprobada", codigos)
        with self.assertRaises(ValidationError):
            invernaderos.baja_invernadero(self.gerente, self.norte.pk)
        self.assertEqual(Invernadero.objects.get(pk=self.norte.pk).estado_invernadero, "activo")
