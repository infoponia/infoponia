# Pruebas de CMP-REV-VNC · Revisar Vencimientos de Insumos (docs/casos_de_uso/inventario/vencimientos.md; D-56; INV-02, paso 7).
#
# Servicio que se prueba (inventario/servicios/vencimientos.py), tomado del módulo dentro de cada prueba:
#   revisar_vencimientos(hoy=None) -> Resultado(revisados, creadas, resueltas, fallas)
#     ``hoy`` (un ``date``; sin él, la de ``America/Argentina/Buenos_Aires``) permite simular cualquier día: nunca lee la fecha por su cuenta salvo ese
#     valor por omisión. ``revisados``: invernaderos cuya revisión terminó; ``creadas`` y ``resueltas``: listas de ``Alerta``; ``fallas``: lista de
#     ``(invernadero_id, error)`` de los invernaderos cuya transacción falló (se deshace entera y los demás siguen).
#     - Regla 2: se revisan los lotes con fecha de vencimiento y cantidad disponible > 0 de un ``InsumoInvernadero`` activo de un invernadero activo; el
#       faltante sin lote no vence. Regla 3: por vencer = faltan entre 0 y ``dias_aviso_vencimiento`` días (el día del vencimiento todavía se usa).
#       Regla 4: vencido desde el día siguiente. Regla 5: a lo sumo una alerta ACTIVA por lote y tipo (``inv_insumo_por_vencer`` e ``inv_insumo_vencido``,
#       clave ``lote:<id>``). Regla 1: idempotente; la lógica mira el estado de cada lote contra ``hoy``, no el día anterior.
#     - Regla 6: va solo al Agrónomo del invernadero; sin Agrónomo activo NO se genera nada (esto difiere de la API de alertas, D-41) y el lote se revisa de
#       nuevo al día siguiente. Regla 7: una alerta de vencimiento se resuelve cuando el lote llega a cero. Regla 8: no modifica stock. Regla 9: ni bitácora ni asiento.
#     - Regla 10: ``dias_aviso_vencimiento`` se lee UNA vez al empezar la corrida. Regla 11: reevalúa «bajo el mínimo» de cada insumo con algún lote vencido con
#       cantidad > 0; si el mínimo es > 0, está bajo el mínimo y no tiene alerta activa, la crea (con las condiciones de la regla 6); NO la resuelve.
#     - Postcondición d (D-27, D-36): un registro ``alerta_de_vencimiento`` por alerta creada, con ``usuario=None`` (rol «infoponia»), el invernadero y el insumo
#       como afectados y la alerta en ``datos.alertas_creadas``; la «por vencer» que se resuelve al vencer el lote va en el mismo registro.
#     - Una transacción por invernadero (con ``bloquear_invernadero_para_alertas`` y relectura de los lotes); las alertas se crean con la API
#       (``maestros.servicios.alertas.asegurar_alerta_de_estado``, llamada como atributo del módulo para poder simularle una falla).

from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase, TransactionTestCase, tag

from core.models import ROL_INFOPONIA, RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez, separar
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    asegurar_datos_de_inventario,
    existencia,
    faltante,
    insumo,
    lote,
    origen_falso,
    perezoso,
    tipo_de_insumo,
    verificar_invariantes,
)
from inventario.tests.test_salida_por_consumo import consumo_simulado
from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas
from maestros.servicios import configuracion
from maestros.tests.fabricas import (
    asegurar_datos_de_maestros,
    crear_agronomo,
    crear_alerta,
    crear_invernadero,
    crear_invernadero_con_geografia_propia,
)

vencimientos = perezoso("inventario.servicios.vencimientos")
HOY = date(2026, 12, 10)
POR_VENCER = "inv_insumo_por_vencer"
VENCIDO = "inv_insumo_vencido"
BAJO_MINIMO = "inv_insumo_bajo_minimo"
ALERTA_DE_VENCIMIENTO = RegistroAuditoria.Accion.ALERTA_DE_VENCIMIENTO
D = Decimal


def en(dias):
    """La fecha ``dias`` días después de ``HOY`` (negativo: antes)."""
    return HOY + timedelta(days=dias)


class CmpRevVncTests(ConDatosDeInventario, TestCase):
    def setUp(self):
        self.agronomo = crear_agronomo(nombre="Ana", apellido="Gómez")
        self.norte = crear_invernadero("Invernadero Norte", agronomo=self.agronomo)
        self.insumo = insumo("Nutriente A", tipo=tipo_de_insumo("Nutrientes"), unidad="l", controla_vencimiento=True)
        self.iin = existencia(self.insumo, self.norte, minimo=0)

    def revisar(self, hoy=HOY):
        return vencimientos.revisar_vencimientos(hoy)

    def alertas(self, tipo=None):
        consulta = Alerta.objects.all()
        return consulta.filter(tipo_alerta=tipo) if tipo else consulta

    def activas(self, tipo):
        return self.alertas(tipo).filter(estado_alerta="activa")

    # ---- regla 3 y postcondición a: por vencer ----

    def test_post_a_un_lote_por_vencer_genera_una_alerta_para_el_agronomo(self):
        """Postcondición a y regla 3: un lote por vencer sin alerta activa genera «insumo por vencer» para el Agrónomo del invernadero."""
        l = lote(self.iin, 12, vence=en(7))
        resultado = self.revisar()
        alerta = self.activas(POR_VENCER).get()
        self.assertEqual((alerta.clave_estado, alerta.agronomo_id, alerta.para_gerente, alerta.invernadero_id), (f"lote:{l.pk}", self.agronomo.pk, False, self.norte.pk))
        self.assertEqual(alerta.nivel_severidad, Alerta.Severidad.ADVERTENCIA)
        self.assertEqual([a.pk for a in resultado.creadas], [alerta.pk])

    def test_post_a_la_descripcion_identifica_insumo_lote_cantidad_y_fecha(self):
        """Regla 5 de 8.23: insumo, lote, cantidad disponible y fecha de vencimiento (``descripcion_alerta``)."""
        l = lote(self.iin, 12, vence=date(2026, 12, 17))
        self.revisar()
        self.assertEqual(
            self.activas(POR_VENCER).get().descripcion_alerta,
            f"Nutriente A · lote {l.pk} · 12 L disponibles · vence el 17/12/2026",
        )

    def test_regla_3_el_borde_de_los_quince_dias_cuenta_y_el_dia_dieciseis_no(self):
        """Regla 3: faltan entre 0 y 15 días (valor inicial, MD-89): 15 sí, 16 no."""
        justo = lote(self.iin, 1, vence=en(15))
        lote(self.iin, 1, vence=en(16))
        self.revisar()
        self.assertEqual([a.clave_estado for a in self.activas(POR_VENCER)], [f"lote:{justo.pk}"])

    def test_regla_3_y_4_el_dia_del_vencimiento_esta_por_vencer_y_todavia_no_vencido(self):
        """Regla 3: «el día del vencimiento el lote todavía puede usarse»: sigue por vencer (0 días) y no es vencido."""
        lote(self.iin, 1, vence=en(0))
        self.revisar()
        self.assertEqual((self.activas(POR_VENCER).count(), self.activas(VENCIDO).count()), (1, 0))

    def test_regla_5_si_ya_hay_una_alerta_activa_del_lote_no_se_crea_otra(self):
        """Regla 5: a lo sumo una alerta activa por lote y tipo."""
        lote(self.iin, 1, vence=en(3))
        self.revisar()
        resultado = self.revisar()
        self.assertEqual(self.activas(POR_VENCER).count(), 1)
        self.assertEqual(resultado.creadas, [])

    # ---- regla 4 y postcondición b: vencido ----

    def test_post_b_un_lote_vencido_genera_la_alerta_de_vencido_critica(self):
        """Postcondición b y regla 4: vencido desde el día siguiente a su fecha: «insumo vencido» para el Agrónomo, crítica."""
        l = lote(self.iin, 5, vence=en(-1))
        self.revisar()
        alerta = self.activas(VENCIDO).get()
        self.assertEqual((alerta.clave_estado, alerta.agronomo_id, alerta.nivel_severidad), (f"lote:{l.pk}", self.agronomo.pk, Alerta.Severidad.CRITICA))
        self.assertEqual(self.activas(POR_VENCER).count(), 0)

    def test_post_b_el_lote_que_pasa_de_por_vencer_a_vencido_resuelve_la_primera_y_crea_la_segunda(self):
        """Postcondición b: la alerta «por vencer» del mismo lote pasa a resuelta y se crea la de vencido, en la misma corrida."""
        l = lote(self.iin, 5, vence=en(2))
        self.revisar(HOY)
        por_vencer = self.activas(POR_VENCER).get()
        resultado = self.revisar(en(3))  # venció ayer
        por_vencer.refresh_from_db()
        self.assertEqual(por_vencer.estado_alerta, "resuelta")
        self.assertIsNotNone(por_vencer.fecha_resolucion)
        self.assertEqual(self.activas(VENCIDO).get().clave_estado, f"lote:{l.pk}")
        self.assertEqual(([a.tipo_alerta for a in resultado.creadas], [a.pk for a in resultado.resueltas]), ([VENCIDO], [por_vencer.pk]))

    # ---- regla 2: qué se revisa ----

    def test_regla_2_no_se_revisan_los_lotes_sin_vencimiento_ni_el_faltante_ni_los_agotados(self):
        """Regla 2: solo lotes con fecha de vencimiento y cantidad disponible mayor que cero; el faltante no vence."""
        sin_fecha = existencia(insumo("Bolsas", tipo=self.iin.insumo.tipo_insumo, unidad="unidad"), self.norte)
        lote(sin_fecha, 9)
        lote(self.iin, 0, vence=en(-5), ingresada=4)
        faltante(self.iin, 3)
        self.assertEqual((self.revisar().creadas, self.alertas().count()), ([], 0))

    def test_regla_2_un_invernadero_inactivo_o_un_insumo_deshabilitado_no_se_revisan(self):
        """Precondición b: insumo activo en invernadero activo."""
        lote(self.iin, 5, vence=en(-2))
        inactivo = crear_invernadero("Viejo", agronomo=self.agronomo)
        en_viejo = existencia(insumo("Otro", tipo=self.iin.insumo.tipo_insumo, unidad="l", controla_vencimiento=True), inactivo)
        lote(en_viejo, 5, vence=en(-2))
        inactivo.estado_invernadero = "inactivo"
        inactivo.save(update_fields=["estado_invernadero"])
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(estado_insumo_invernadero="inactivo")
        self.assertEqual(self.revisar().creadas, [])
        self.assertEqual(self.alertas().count(), 0)

    # ---- regla 1: idempotente y con recuperación ----

    def test_regla_1_correrlo_dos_veces_el_mismo_dia_no_duplica_nada(self):
        """Regla 1 y D-56 punto 4: idempotente (alertas y auditoría)."""
        lote(self.iin, 5, vence=en(-1))
        lote(self.iin, 5, vence=en(4))
        self.revisar()
        antes = (self.alertas().count(), RegistroAuditoria.objects.filter(accion=ALERTA_DE_VENCIMIENTO).count())
        segunda = self.revisar()
        self.assertEqual((self.alertas().count(), RegistroAuditoria.objects.filter(accion=ALERTA_DE_VENCIMIENTO).count()), antes)
        self.assertEqual((segunda.creadas, segunda.resueltas), ([], []))

    def test_regla_1_un_dia_salteado_alerta_lo_que_corresponde_a_esa_fecha_sin_repetir_lo_ya_alertado(self):
        """Regla 1: si un día no corrió, la próxima revisión alerta lo que corresponda a esa fecha: la lógica mira el estado contra ``hoy``."""
        l = lote(self.iin, 5, vence=en(10))
        self.revisar(HOY)  # a 10 días: por vencer
        self.assertEqual(self.activas(POR_VENCER).count(), 1)
        # se saltan los días 1 a 11; el día 12 el lote ya venció
        self.revisar(en(12))
        self.assertEqual((self.activas(POR_VENCER).count(), self.activas(VENCIDO).count()), (0, 1))
        self.assertEqual(self.alertas(POR_VENCER).count(), 1)  # no se repitió la de por vencer
        self.assertEqual(self.alertas(VENCIDO).get().clave_estado, f"lote:{l.pk}")

    def test_regla_1_un_lote_que_nunca_se_alerto_y_ya_esta_vencido_se_alerta_como_vencido_directo(self):
        """Recuperación: sin pasar por «por vencer»."""
        lote(self.iin, 5, vence=en(10))
        self.revisar(en(20))
        self.assertEqual((self.alertas(POR_VENCER).count(), self.activas(VENCIDO).count()), (0, 1))

    # ---- regla 6: sin Agrónomo ----

    def test_regla_6_sin_agronomo_no_se_genera_ninguna_alerta_ni_va_al_gerente(self):
        """Regla 6 (manda el CU, L7; difiere de D-41): sin Agrónomo no se genera ninguna alerta, ni siquiera para el Gerente."""
        sin = crear_invernadero("Sin agronomo")
        lote(existencia(insumo("Otro", tipo=self.iin.insumo.tipo_insumo, unidad="l", controla_vencimiento=True), sin), 5, vence=en(-1))
        resultado = self.revisar()
        self.assertEqual((self.alertas().count(), resultado.creadas), (0, []))

    def test_regla_6_un_agronomo_inactivo_tampoco_cuenta(self):
        """«Sin Agrónomo activo»: una cuenta de baja no recibe alertas."""
        lote(self.iin, 5, vence=en(-1))
        self.agronomo.is_active = False
        self.agronomo.save(update_fields=["is_active"])
        self.assertEqual(self.revisar().creadas, [])

    def test_regla_6_al_asignar_un_agronomo_la_proxima_corrida_genera_la_que_corresponde(self):
        """Regla 6: el lote se revisa de nuevo al día siguiente; cuando se asigna un Agrónomo, se genera la que corresponda."""
        sin = crear_invernadero("Sin agronomo")
        otro = existencia(insumo("Otro", tipo=self.iin.insumo.tipo_insumo, unidad="l", controla_vencimiento=True), sin)
        lote(otro, 5, vence=en(-1))
        self.revisar()
        self.assertEqual(self.alertas().count(), 0)
        sin.agronomo = crear_agronomo(email="nuevo@infoponia.com")
        sin.save(update_fields=["agronomo"])
        self.revisar(en(1))
        self.assertEqual(self.activas(VENCIDO).get().agronomo_id, sin.agronomo_id)

    # ---- regla 7 y postcondición c: lotes agotados ----

    def test_post_c_las_alertas_de_vencimiento_de_un_lote_agotado_pasan_a_resueltas(self):
        """Postcondición c y regla 7: si el lote llegó a cero, la corrida resuelve sus alertas de vencimiento que quedaran activas."""
        agotado = lote(self.iin, 0, vence=en(-1), ingresada=4)
        a = crear_alerta(self.norte, VENCIDO, para_gerente=False, agronomo=self.agronomo, clave_estado=f"lote:{agotado.pk}")
        b = crear_alerta(self.norte, POR_VENCER, para_gerente=False, agronomo=self.agronomo, clave_estado=f"lote:{agotado.pk}")
        resultado = self.revisar()
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual((a.estado_alerta, b.estado_alerta), ("resuelta", "resuelta"))
        self.assertEqual({x.pk for x in resultado.resueltas}, {a.pk, b.pk})

    def test_post_c_un_lote_agotado_en_un_invernadero_sin_otros_lotes_a_revisar_tambien_se_resuelve(self):
        """La resolución no depende de que el invernadero tenga más lotes a revisar."""
        agotado = lote(self.iin, 0, vence=en(5), ingresada=4)
        a = crear_alerta(self.norte, POR_VENCER, para_gerente=False, agronomo=self.agronomo, clave_estado=f"lote:{agotado.pk}")
        self.revisar()
        a.refresh_from_db()
        self.assertEqual(a.estado_alerta, "resuelta")

    def test_regla_7_un_lote_con_stock_conserva_su_alerta(self):
        """Mientras la cantidad disponible sea mayor que cero, la alerta sigue."""
        lote(self.iin, 5, vence=en(-1))
        self.revisar()
        self.revisar(en(1))
        self.assertEqual(self.activas(VENCIDO).count(), 1)

    # ---- postcondición d: auditoría ----

    def test_post_d_cada_alerta_creada_deja_un_registro_con_origen_sistema(self):
        """Postcondición d y D-27: un registro por alerta creada, ``usuario=None`` (rol «infoponia»), con el invernadero y el insumo como
        afectados y la alerta en ``datos.alertas_creadas``."""
        lote(self.iin, 5, vence=en(-1))
        lote(self.iin, 5, vence=en(3))
        self.revisar()
        registros = list(RegistroAuditoria.objects.filter(accion=ALERTA_DE_VENCIMIENTO))
        self.assertEqual(len(registros), 2)
        for registro in registros:
            self.assertEqual((registro.usuario, registro.rol), (None, ROL_INFOPONIA))
            modelos = {(a["modelo"], a["id"]) for a in registro.afectados}
            self.assertIn(("maestros.invernadero", self.norte.pk), modelos)
            self.assertIn(("inventario.insumo", self.insumo.pk), modelos)
        creadas = {r["id"] for registro in registros for r in registro.detalle["datos"]["alertas_creadas"]}
        self.assertEqual(creadas, {a.pk for a in self.alertas()})

    def test_post_d_la_por_vencer_que_se_resuelve_al_vencer_va_en_el_mismo_registro(self):
        """Postcondición b y d: la resolución de la «por vencer» figura en ``datos.alertas_resueltas`` del registro de la de vencido."""
        lote(self.iin, 5, vence=en(2))
        self.revisar(HOY)
        por_vencer = self.activas(POR_VENCER).get()
        self.revisar(en(3))
        registro = RegistroAuditoria.objects.filter(accion=ALERTA_DE_VENCIMIENTO).latest("id")
        self.assertEqual([r["id"] for r in registro.detalle["datos"]["alertas_resueltas"]], [por_vencer.pk])

    # ---- regla 8 y 9: no toca stock ----

    def test_regla_8_y_9_no_modifica_el_stock_ni_escribe_movimientos(self):
        """Regla 8: no modifica el stock ni descarta lo vencido (lo da de baja el Agrónomo con un ajuste)."""
        l = lote(self.iin, 5, vence=en(-3))
        antes = (MovimientoInsumo.objects.count(), LoteInsumo.objects.count())
        self.revisar()
        l.refresh_from_db()
        self.assertEqual(l.cantidad_disponible, D("5"))
        self.assertEqual((MovimientoInsumo.objects.count(), LoteInsumo.objects.count()), antes)
        verificar_invariantes(self.iin)

    # ---- regla 10 ----

    def test_regla_10_un_cambio_de_dias_aviso_rige_desde_la_proxima_corrida(self):
        """Regla 10: el nuevo valor de ``dias_aviso_vencimiento`` rige desde la próxima revisión."""
        lote(self.iin, 5, vence=en(20))
        self.revisar()
        self.assertEqual(self.alertas().count(), 0)  # 20 > 15
        config = configuracion.obtener()
        config.dias_aviso_vencimiento = 25
        config.save()
        self.revisar()
        self.assertEqual(self.activas(POR_VENCER).count(), 1)

    def test_regla_10_achicar_el_aviso_no_resuelve_una_alerta_ya_generada(self):
        """El CU solo resuelve al vencer o agotarse el lote: reducir los días no la resuelve."""
        lote(self.iin, 5, vence=en(10))
        self.revisar()
        config = configuracion.obtener()
        config.dias_aviso_vencimiento = 5
        config.save()
        self.revisar()
        self.assertEqual(self.activas(POR_VENCER).count(), 1)

    # ---- regla 11: bajo el mínimo ----

    def preparar_bajo_el_minimo(self, minimo="20"):
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(cant_min_insumo=D(minimo))
        lote(self.iin, 10, vence=en(-1))  # vencido: no cuenta en el stock libre

    def test_post_e_un_insumo_con_lote_vencido_que_queda_bajo_el_minimo_genera_la_alerta(self):
        """Postcondición e y regla 11: stock libre (sin lotes vencidos) + tránsito < mínimo y sin alerta activa: se genera para el Agrónomo."""
        self.preparar_bajo_el_minimo()
        resultado = self.revisar()
        alerta = self.activas(BAJO_MINIMO).get()
        self.assertEqual((alerta.clave_estado, alerta.agronomo_id), (f"insumo:{self.iin.pk}", self.agronomo.pk))
        self.assertIn(alerta.pk, [a.pk for a in resultado.creadas])

    def test_post_e_la_alerta_bajo_el_minimo_tambien_deja_su_registro_de_auditoria(self):
        """Postcondición d: un registro por alerta generada, también la de la regla 11."""
        self.preparar_bajo_el_minimo()
        self.revisar()
        alerta = self.activas(BAJO_MINIMO).get()
        registros = [r for r in RegistroAuditoria.objects.filter(accion=ALERTA_DE_VENCIMIENTO) if alerta.pk in [x["id"] for x in r.detalle["datos"]["alertas_creadas"]]]
        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0].usuario, None)

    def test_regla_11_no_duplica_la_alerta_bajo_el_minimo_ya_activa(self):
        """Regla 11: «no tiene alerta activa de ese tipo»."""
        self.preparar_bajo_el_minimo()
        self.revisar()
        self.revisar()
        self.assertEqual(self.activas(BAJO_MINIMO).count(), 1)

    def test_regla_11_esta_corrida_no_resuelve_la_alerta_bajo_el_minimo(self):
        """Regla 11: «Esta revisión no resuelve esa alerta»: se resuelve al registrar la recepción."""
        self.preparar_bajo_el_minimo()
        previa = crear_alerta(self.norte, BAJO_MINIMO, para_gerente=False, agronomo=self.agronomo, clave_estado=f"insumo:{self.iin.pk}")
        lote(self.iin, 100, vence=en(300))  # ya no está bajo el mínimo
        self.revisar()
        previa.refresh_from_db()
        self.assertEqual(previa.estado_alerta, "activa")

    def test_regla_11_solo_si_el_insumo_tiene_algun_lote_vencido_con_stock(self):
        """Regla 11: se reevalúa «cada insumo que tiene algún lote vencido con cantidad disponible mayor que cero»: sin uno, no se crea."""
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(cant_min_insumo=D("20"))
        lote(self.iin, 3, vence=en(100))  # bajo el mínimo, pero ningún lote vencido
        self.revisar()
        self.assertEqual(self.alertas(BAJO_MINIMO).count(), 0)

    def test_regla_11_con_minimo_cero_no_alerta(self):
        """Regla 11: «si el stock mínimo es mayor que cero»."""
        self.preparar_bajo_el_minimo(minimo="0")
        self.revisar()
        self.assertEqual(self.alertas(BAJO_MINIMO).count(), 0)

    def test_regla_11_si_el_stock_vigente_alcanza_el_minimo_no_alerta(self):
        """No está bajo el mínimo: el stock libre cubre."""
        self.preparar_bajo_el_minimo(minimo="20")
        lote(self.iin, 30, vence=en(300))
        self.revisar()
        self.assertEqual(self.alertas(BAJO_MINIMO).count(), 0)

    def test_regla_11_sin_agronomo_no_se_genera_la_alerta_bajo_el_minimo(self):
        """Regla 11: con las mismas condiciones de la regla 6."""
        sin = crear_invernadero("Sin agronomo")
        iin = existencia(insumo("Otro", tipo=self.iin.insumo.tipo_insumo, unidad="l", controla_vencimiento=True), sin, minimo=20)
        lote(iin, 10, vence=en(-1))
        self.revisar()
        self.assertEqual(self.alertas().count(), 0)

    # ---- una transacción por invernadero ----

    def con_dos_invernaderos(self):
        self.sur = crear_invernadero("Invernadero Sur", agronomo=self.agronomo)
        self.iin_sur = existencia(insumo("Otro", tipo=self.iin.insumo.tipo_insumo, unidad="l", controla_vencimiento=True), self.sur)
        lote(self.iin, 5, vence=en(3))
        lote(self.iin_sur, 5, vence=en(3))

    def test_una_falla_en_un_invernadero_se_deshace_y_no_impide_revisar_los_demas(self):
        """D-56 puntos 4 y 5 y «Bloqueos y concurrencia»: una transacción por invernadero; una falla se informa y los demás se revisan."""
        self.con_dos_invernaderos()
        real = api_alertas.asegurar_alerta_de_estado

        def falla_en_el_norte(invernadero_id, *args, **kwargs):
            alerta = real(invernadero_id, *args, **kwargs)  # ya la creó...
            if invernadero_id == self.norte.pk:
                raise RuntimeError("falla simulada")  # ...y falla después: todo el invernadero se deshace
            return alerta

        with mock.patch.object(api_alertas, "asegurar_alerta_de_estado", side_effect=falla_en_el_norte):
            resultado = self.revisar()
        self.assertEqual([(i, str(e)) for i, e in resultado.fallas], [(self.norte.pk, "falla simulada")])
        self.assertEqual(resultado.revisados, 1)
        self.assertEqual(self.alertas().filter(invernadero=self.norte).count(), 0)
        self.assertEqual(self.alertas().filter(invernadero=self.sur).count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=ALERTA_DE_VENCIMIENTO).count(), 1)

    def test_sin_fallas_el_resultado_cuenta_los_invernaderos_revisados(self):
        """``revisados`` cuenta los invernaderos que terminaron bien; ``fallas`` queda vacía."""
        self.con_dos_invernaderos()
        resultado = self.revisar()
        self.assertEqual((resultado.revisados, resultado.fallas, len(resultado.creadas)), (2, [], 2))

    def test_los_invernaderos_se_revisan_en_orden_de_id(self):
        """«En orden de id» (bloqueos y concurrencia)."""
        self.con_dos_invernaderos()
        orden = []
        real = api_alertas.bloquear_invernadero_para_alertas

        def registrar(invernadero_id):
            orden.append(invernadero_id)
            return real(invernadero_id)

        with mock.patch.object(api_alertas, "bloquear_invernadero_para_alertas", side_effect=registrar):
            self.revisar()
        vistos = [i for n, i in enumerate(orden) if i not in orden[:n]]
        self.assertEqual(vistos, sorted(vistos))

    def test_sin_hoy_usa_la_fecha_del_invernadero(self):
        """Regla 1: sin ``hoy``, la fecha de ``America/Argentina/Buenos_Aires`` (``stock.hoy()``)."""
        from django.utils import timezone

        lote(self.iin, 5, vence=timezone.localdate() - timedelta(days=1))
        vencimientos.revisar_vencimientos()
        self.assertEqual(self.activas(VENCIDO).count(), 1)


@tag("concurrencia")
class CmpRevVncConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """«Es seguro correrlo mientras alguien consume o ajusta: el consumo y el ajuste toman el mismo invernadero»: la revisión toma el invernadero
    y vuelve a leer sus lotes antes de decidir."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero_con_geografia_propia("Invernadero Uno", agronomo=self.agronomo)
        self.iin = existencia(insumo("Nutriente A", tipo=tipo_de_insumo("Nutrientes"), unidad="l", controla_vencimiento=True), self.invernadero)
        self.lote = lote(self.iin, 5, vence=en(-1))
        self.origen = origen_falso()

    def revisar(self):
        return vencimientos.revisar_vencimientos(HOY)

    def test_dos_corridas_a_la_vez_no_duplican_alertas_ni_auditoria(self):
        """La segunda corrida espera el invernadero, ve la alerta ya creada y no crea otra."""
        resultados = correr_a_la_vez(self.revisar, self.revisar, primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(Alerta.objects.filter(tipo_alerta=VENCIDO, estado_alerta="activa").count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=ALERTA_DE_VENCIMIENTO).count(), 1)

    def test_un_consumo_que_agota_el_lote_primero_hace_que_la_revision_no_alerte(self):
        """El consumo va primero y agota el lote; la revisión espera el invernadero, relee el lote en 0 y no lo alerta."""
        resultados = correr_a_la_vez(
            lambda: consumo_simulado(self.agronomo, self.iin, [(self.lote.pk, D("5"))], self.origen),
            self.revisar,
            primera="a",
        )
        _, _, otros = separar(resultados)
        self.assertEqual(otros, [])
        self.assertEqual(resultados["b"].creadas, [])
        self.assertEqual(Alerta.objects.filter(tipo_alerta=VENCIDO).count(), 0)

    def test_la_revision_primero_y_un_consumo_despues_dejan_la_alerta_resuelta(self):
        """La revisión va primero y crea la alerta; el consumo espera, agota el lote y su reevaluación la resuelve (regla 7)."""
        resultados = correr_a_la_vez(
            self.revisar,
            lambda: consumo_simulado(self.agronomo, self.iin, [(self.lote.pk, D("5"))], self.origen),
            primera="a",
        )
        _, _, otros = separar(resultados)
        self.assertEqual(otros, [])
        self.assertEqual(Alerta.objects.get(tipo_alerta=VENCIDO).estado_alerta, "resuelta")
