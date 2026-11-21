# Pruebas de CMP-MOD-INS · Modificar Insumo (docs/casos_de_uso/inventario/insumos.md). Cita D-28, D-36, D-40 y D-42.
#
# Servicios que se prueban (inventario/servicios/insumos.py), tomados del módulo dentro de cada prueba:
#   modificar_insumo(actor, insumo_id, *, nombre, tipo_insumo_id, unidad, descripcion="", controla_vencimiento=False) -> Insumo
#     - Precondición a: Agrónomo activo. Precondición b y regla 1: ``actor`` puede gestionar el insumo (es el Agrónomo de algún
#       invernadero que lo usa; si ninguno lo usa, cualquiera); si no, ``insumo_en_uso_por_otros`` (error general, con los
#       invernaderos y sus Agrónomos). Precondición c y regla 4: no es una semilla (``insumo_semilla``).
#       Precondición d: el nombre nuevo no lo tiene otro insumo (``nombre_repetido``). Regla 6: uno inactivo se rechaza con ``insumo_inactivo``.
#     - Regla 2: las reglas 2 a 6 de CMP-ALT-INS (los mismos campos y códigos).
#     - Regla 3, campo por campo (solo si el valor CAMBIA): ``unidad`` -> ``unidad_bloqueada`` si algún LoteInsumo o MovimientoInsumo del
#       insumo en cualquier invernadero; ``controla_vencimiento`` -> ``vencimiento_bloqueado`` si algún lote tiene cantidad distinta de
#       cero (incluido el faltante); ``categoria`` -> ``categoria_del_sistema`` (la actual es del sistema), ``categoria_destino_del_sistema``,
#       ``categoria_inactiva``, ``reservas_activas`` (destino con otro consumo directo y reservas).
#     - Regla 5 y postcondición b: UNA llamada a ``notificar_a_varios`` (título «Cambió el insumo <nombre anterior>», detalle «<Nombre
#       Apellido> modificó sus datos en el catálogo. Revisá si afecta a tus invernaderos.») al Agrónomo de cada otro invernadero que lo
#       usa, sin el actor y sin repetir cuentas.
#     - D-28: sin cambios no se escribe, no se audita y no se avisa. Postcondición d: un registro ``modificacion_insumo``.
#   a_quienes_avisara(actor, insumo_id) -> list[Invernadero]: los invernaderos cuyo Agrónomo recibirá el aviso (regla 5: lo informa la
#       pantalla antes de confirmar).
#   reactivar_insumo(actor, insumo_id) -> Insumo: regla 6; ``categoria_inactiva``, ``insumo_semilla``, ``insumo_no_inactivo``.

from datetime import date
from decimal import Decimal

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.http import Http404
from django.test import TestCase, TransactionTestCase, tag

from core.models import Notificacion, RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from inventario.extensiones import OrdenQueReserva
from inventario.models import Insumo, InsumoInvernadero
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    ajuste_simulado,
    asegurar_datos_de_inventario,
    categoria_del_sistema,
    existencia,
    faltante,
    insumo,
    lote,
    perezoso,
    reservas_de_prueba,
    tipo_de_insumo,
)
from maestros.tests.fabricas import (
    asegurar_datos_de_maestros,
    codigos_de,
    crear_agronomo,
    crear_invernadero,
    crear_invernadero_con_geografia_propia,
    error_de,
)

insumos = perezoso("inventario.servicios.insumos")
MODIFICACION = RegistroAuditoria.Accion.MODIFICACION_INSUMO
REACTIVACION = RegistroAuditoria.Accion.REACTIVACION_INSUMO


class CmpModInsServicioTests(ConDatosDeInventario, TestCase):
    """Precondiciones, reglas y postcondiciones de CMP-MOD-INS."""

    def setUp(self):
        self.agronomo = crear_agronomo(nombre="Ana", apellido="Gómez")
        self.tipo = tipo_de_insumo("Limpieza", "como_gasto")
        self.insumo = insumo("Detergente", tipo=self.tipo, unidad="l", descripcion="5 L")

    def datos(self, **cambios):
        base = {
            "nombre": self.insumo.nombre_insumo,
            "tipo_insumo_id": self.insumo.tipo_insumo_id,
            "unidad": self.insumo.unidad_medida_insumo,
            "descripcion": self.insumo.descripcion_insumo,
            "controla_vencimiento": self.insumo.controla_vencimiento,
        }
        return base | cambios

    def modificar(self, actor=None, objetivo=None, **cambios):
        return insumos.modificar_insumo(actor or self.agronomo, (objetivo or self.insumo).pk, **self.datos(**cambios))

    def usado_por(self, nombre, agronomo, objetivo=None):
        """Un invernadero activo, a cargo de ``agronomo`` (o sin Agrónomo), que tiene el insumo habilitado."""
        invernadero = crear_invernadero(nombre, **({"agronomo": agronomo} if agronomo else {}))
        existencia(objetivo or self.insumo, invernadero)
        return invernadero

    # ---- precondición a ----

    def test_pre_a_gerente_capataz_y_administrador_no_modifican(self):
        """CMP-MOD-INS precondición a: solo un Agrónomo activo."""
        for cuenta in (crear_gerente(), crear_capataz(), crear_administrador()):
            with self.subTest(rol=type(cuenta).__name__):
                with self.assertRaises(PermissionDenied):
                    self.modificar(actor=cuenta, nombre="Otro")

    def test_pre_a_un_insumo_que_no_existe_da_404(self):
        """D-28: un id inexistente da 404."""
        with self.assertRaises(Http404):
            insumos.modificar_insumo(self.agronomo, 999999, **self.datos())

    # ---- precondición b y regla 1: quién puede gestionarlo ----

    def test_regla_1_si_ningun_invernadero_lo_usa_cualquier_agronomo_lo_modifica(self):
        """CMP-MOD-INS regla 1: «si ningún invernadero lo usa, cualquier Agrónomo activo»."""
        self.assertEqual(self.modificar(nombre="Detergente líquido").nombre_insumo, "Detergente líquido")

    def test_regla_1_el_agronomo_de_un_invernadero_que_lo_usa_lo_modifica(self):
        """CMP-MOD-INS regla 1: lo modifica el Agrónomo de algún invernadero que lo usa."""
        self.usado_por("Invernadero Norte", self.agronomo)
        self.usado_por("Invernadero Sur", crear_agronomo(email="otro@infoponia.com"))
        self.assertEqual(self.modificar(nombre="Detergente líquido").nombre_insumo, "Detergente líquido")

    def test_pre_b_quien_no_es_agronomo_de_ningun_invernadero_que_lo_usa_no_lo_modifica_y_se_le_informa_quien_lo_usa(self):
        """CMP-MOD-INS precondición b y regla 1 (verificación a mano 8): el error nombra los invernaderos y sus Agrónomos."""
        ajeno = crear_agronomo(email="ajeno@infoponia.com", nombre="Luis", apellido="Paz")
        self.usado_por("Invernadero Norte", ajeno)
        self.usado_por("Invernadero Sur", None)
        error = error_de(lambda: self.modificar(nombre="Otro"))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["insumo_en_uso_por_otros"])
        self.assertIn("Invernadero Norte (Luis Paz)", error.messages[0])
        self.assertIn("Invernadero Sur (sin Agrónomo)", error.messages[0])
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.nombre_insumo, "Detergente")

    def test_regla_1_no_cuentan_un_invernadero_inactivo_ni_una_habilitacion_inactiva(self):
        """CMP-MOD-INS regla 1: «un invernadero usa el insumo si está activo y lo tiene habilitado»."""
        ajeno = crear_agronomo(email="ajeno@infoponia.com")
        inactivo = crear_invernadero("Invernadero Cerrado", activo=False, agronomo=ajeno)
        existencia(self.insumo, inactivo)
        deshabilitado = crear_invernadero("Invernadero Norte", agronomo=ajeno)
        existencia(self.insumo, deshabilitado, activo=False)
        self.assertEqual(self.modificar(nombre="Otro").nombre_insumo, "Otro")

    # ---- precondición c y regla 4: semillas; regla 6: inactivo ----

    def test_pre_c_una_semilla_no_se_modifica_desde_este_caso_de_uso(self):
        """CMP-MOD-INS precondición c y regla 4: su nombre cambia con su cultivo o variedad y su categoría es fija."""
        semilla = insumo("Semilla Lechuga Crespa", tipo=categoria_del_sistema("semillas"), unidad="unidad", controla_vencimiento=True)
        error = error_de(lambda: self.modificar(objetivo=semilla, nombre="Otro", tipo_insumo_id=semilla.tipo_insumo_id, unidad="unidad", controla_vencimiento=True))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["insumo_semilla"])

    def test_regla_6_un_insumo_inactivo_no_se_modifica_solo_se_reactiva(self):
        """CMP-MOD-INS regla 6: ``insumo_inactivo``."""
        inactivo = insumo("Viejo", tipo=self.tipo, activo=False)
        error = error_de(lambda: self.modificar(objetivo=inactivo, nombre="Nuevo"))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["insumo_inactivo"])

    # ---- precondición d y regla 2: el nombre y los demás datos ----

    def test_pre_d_el_nombre_de_otro_insumo_se_rechaza_sin_distinguir_mayusculas_ni_espacios(self):
        """CMP-MOD-INS precondición d: no existe otro insumo con el nombre nuevo (activo o inactivo)."""
        insumo("Lavandina", tipo=self.tipo, activo=False)
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(nombre=" lavandina")), "nombre"), ["nombre_repetido"])

    def test_pre_d_cambiar_solo_las_mayusculas_del_propio_nombre_no_es_un_repetido(self):
        """CMP-MOD-INS precondición d: «otro insumo»: el propio no cuenta."""
        self.assertEqual(self.modificar(nombre="DETERGENTE").nombre_insumo, "DETERGENTE")

    def test_regla_2_se_validan_los_datos_como_en_el_alta(self):
        """CMP-MOD-INS regla 2: reglas 2 a 6 de CMP-ALT-INS, todos los errores de campo juntos."""
        error = error_de(lambda: self.modificar(nombre="", tipo_insumo_id=None, unidad="docena", descripcion="d" * 301))
        self.assertEqual(sorted(error.error_dict), ["categoria", "descripcion", "nombre", "unidad"])

    # ---- regla 3: campo por campo ----

    def test_regla_3_el_nombre_y_la_descripcion_se_cambian_siempre_aunque_haya_stock(self):
        """CMP-MOD-INS regla 3: nombre y descripción, siempre."""
        lote(existencia(self.insumo, crear_invernadero("Invernadero Uno", agronomo=self.agronomo)), 5)
        cambiado = self.modificar(nombre="Detergente líquido", descripcion="10 L")
        self.assertEqual((cambiado.nombre_insumo, cambiado.descripcion_insumo), ("Detergente líquido", "10 L"))

    def test_regla_3_la_unidad_se_cambia_si_nunca_tuvo_stock_ni_movimientos(self):
        """CMP-MOD-INS regla 3: «solo si el insumo nunca tuvo stock ni movimientos en ningún invernadero» (existencias vacías no cuentan)."""
        existencia(self.insumo, crear_invernadero("Invernadero Uno", agronomo=self.agronomo))
        self.assertEqual(self.modificar(unidad="kg").unidad_medida_insumo, "kg")

    def test_regla_3_la_unidad_no_se_cambia_si_hubo_un_lote_aunque_este_en_cero(self):
        """CMP-MOD-INS regla 3 y verificación a mano 6: ``unidad_bloqueada``, con el motivo, en el campo ``unidad``."""
        lote(existencia(self.insumo, crear_invernadero("Invernadero Uno", agronomo=self.agronomo)), 0, ingresada=3)
        error = error_de(lambda: self.modificar(unidad="kg"))
        self.assertEqual(codigos_de(error, "unidad"), ["unidad_bloqueada"])
        self.assertIn("stock o movimientos", error.messages[0])
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.unidad_medida_insumo, "l")

    def test_regla_3_la_unidad_no_se_cambia_si_hubo_stock_en_otro_invernadero_aunque_inactivo(self):
        """CMP-MOD-INS regla 3: «en ningún invernadero» (también una habilitación inactiva)."""
        lote(existencia(self.insumo, crear_invernadero("Invernadero Uno", agronomo=self.agronomo), activo=False), 2)
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(unidad="g")), "unidad"), ["unidad_bloqueada"])

    def test_regla_3_dejar_la_misma_unidad_con_stock_no_es_un_error(self):
        """CMP-MOD-INS regla 3: solo se bloquea el CAMBIO."""
        lote(existencia(self.insumo, crear_invernadero("Invernadero Uno", agronomo=self.agronomo)), 2)
        self.assertEqual(self.modificar(unidad="l", nombre="Otro").nombre_insumo, "Otro")

    def test_regla_3_controla_vencimiento_se_cambia_sin_stock(self):
        """CMP-MOD-INS regla 3: «solo si el insumo no tiene stock en ningún invernadero» (un lote agotado no cuenta)."""
        lote(existencia(self.insumo, crear_invernadero("Invernadero Uno", agronomo=self.agronomo)), 0, ingresada=3)
        self.assertTrue(self.modificar(controla_vencimiento=True).controla_vencimiento)

    def test_regla_3_controla_vencimiento_no_se_cambia_con_stock_y_dice_cuanto_hay(self):
        """CMP-MOD-INS regla 3: ``vencimiento_bloqueado`` en su campo, con el stock total y la unidad."""
        lote(existencia(self.insumo, crear_invernadero("Invernadero Uno", agronomo=self.agronomo)), "2.5")
        error = error_de(lambda: self.modificar(controla_vencimiento=True))
        self.assertEqual(codigos_de(error, "controla_vencimiento"), ["vencimiento_bloqueado"])
        self.assertIn("2.500", error.messages[0])

    def test_regla_3_controla_vencimiento_no_se_cambia_con_stock_negativo(self):
        """CMP-MOD-INS regla 3: tiene stock distinto de cero también el faltante sin lote (negativo)."""
        faltante(existencia(self.insumo, crear_invernadero("Invernadero Uno", agronomo=self.agronomo)), 2)
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(controla_vencimiento=True)), "controla_vencimiento"), ["vencimiento_bloqueado"])

    def test_regla_3_la_categoria_no_se_cambia_si_es_del_sistema(self):
        """CMP-MOD-INS regla 3: «la categoría no se cambia si es del sistema»."""
        sobres = insumo("Sobres", tipo=categoria_del_sistema("envases"), unidad="unidad")
        error = error_de(lambda: self.modificar(objetivo=sobres, nombre="Sobres", tipo_insumo_id=self.tipo.pk, unidad="unidad"))
        self.assertEqual(codigos_de(error, "categoria"), ["categoria_del_sistema"])

    def test_regla_3_un_insumo_de_una_categoria_del_sistema_cambia_su_nombre_sin_tocar_la_categoria(self):
        """CMP-MOD-INS regla 3: el nombre se cambia siempre; dejar la misma categoría del sistema no es un error."""
        sobres = insumo("Sobres", tipo=categoria_del_sistema("envases"), unidad="unidad")
        cambiado = self.modificar(objetivo=sobres, nombre="Bolsas", tipo_insumo_id=sobres.tipo_insumo_id, unidad="unidad")
        self.assertEqual(cambiado.nombre_insumo, "Bolsas")

    def test_regla_3_no_se_puede_pasar_a_una_categoria_del_sistema(self):
        """CMP-MOD-INS regla 3: «ni se puede pasar a una del sistema» (ni a Semillas)."""
        for codigo in ("envases", "semillas", "infraestructura"):
            with self.subTest(codigo=codigo):
                destino = categoria_del_sistema(codigo)
                error = error_de(lambda: self.modificar(tipo_insumo_id=destino.pk))
                self.assertEqual(codigos_de(error, "categoria"), ["categoria_destino_del_sistema"])

    def test_regla_3_no_se_puede_pasar_a_una_categoria_inactiva_ni_inexistente(self):
        """CMP-MOD-INS regla 2 y regla 4 de CMP-ALT-INS: el destino es una categoría activa."""
        inactiva = tipo_de_insumo("Vieja", activo=False)
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(tipo_insumo_id=inactiva.pk)), "categoria"), ["categoria_inactiva"])
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(tipo_insumo_id=999999)), "categoria"), ["invalida"])

    def test_regla_3_pasar_a_otra_categoria_comun_cambia_la_categoria(self):
        """CMP-MOD-INS regla 3 y verificación a mano 7: el insumo pasa de categoría."""
        destino = tipo_de_insumo("Higiene", "como_gasto")
        self.assertEqual(self.modificar(tipo_insumo_id=destino.pk).tipo_insumo_id, destino.pk)

    def test_regla_3_con_reservas_no_se_pasa_a_una_categoria_con_otro_consumo_directo(self):
        """CMP-MOD-INS regla 3: «ni a una con otro consumo directo si el insumo tiene cantidades reservadas por órdenes a realizar»."""
        destino = tipo_de_insumo("Nutrientes", "como_costo_de_los_lotes")
        iin = existencia(self.insumo, crear_invernadero("Invernadero Uno", agronomo=self.agronomo))
        orden = OrdenQueReserva(7, "Siembra 7", Decimal("2"), date(2026, 12, 1), "/o/7/")
        with reservas_de_prueba(reservado={iin.pk: 2}, ordenes={iin.pk: [orden]}):
            error = error_de(lambda: self.modificar(tipo_insumo_id=destino.pk))
        self.assertEqual(codigos_de(error, "categoria"), ["reservas_activas"])
        self.assertIn("Siembra 7", " ".join(error.messages))
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.tipo_insumo_id, self.tipo.pk)

    def test_regla_3_con_reservas_si_se_pasa_a_una_categoria_con_el_mismo_consumo_directo(self):
        """CMP-MOD-INS regla 3: solo bloquea ir a OTRO consumo directo."""
        destino = tipo_de_insumo("Higiene", "como_gasto")
        iin = existencia(self.insumo, crear_invernadero("Invernadero Uno", agronomo=self.agronomo))
        with reservas_de_prueba(reservado={iin.pk: 2}):
            self.assertEqual(self.modificar(tipo_insumo_id=destino.pk).tipo_insumo_id, destino.pk)

    def test_regla_3_cada_campo_bloqueado_da_su_propio_error_y_los_demas_se_validan_juntos(self):
        """CMP-MOD-INS regla 3: «cada campo bloqueado muestra por qué»: los errores de campo vienen todos juntos."""
        lote(existencia(self.insumo, crear_invernadero("Invernadero Uno", agronomo=self.agronomo)), 4)
        destino = tipo_de_insumo("Higiene")
        error = error_de(lambda: self.modificar(unidad="kg", controla_vencimiento=True, nombre="", tipo_insumo_id=destino.pk))
        self.assertEqual(sorted(error.error_dict), ["controla_vencimiento", "nombre", "unidad"])

    def test_regla_3_un_error_no_cambia_nada_ni_audita_ni_avisa(self):
        """Todo o nada: con un campo bloqueado no se cambia ni el nombre."""
        lote(existencia(self.insumo, crear_invernadero("Invernadero Uno", agronomo=self.agronomo)), 4)
        error_de(lambda: self.modificar(nombre="Otro", unidad="kg"))
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.nombre_insumo, "Detergente")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    # ---- regla 5 y postcondición b: avisos ----

    def preparar_avisos(self):
        """Mi invernadero, uno de ``otro`` (con dos invernaderos) y uno sin Agrónomo; todos usan el insumo."""
        self.otro = crear_agronomo(email="otro@infoponia.com", nombre="Luis", apellido="Paz")
        self.mio = self.usado_por("Invernadero Mio", self.agronomo)
        self.norte = self.usado_por("Invernadero Norte", self.otro)
        self.este = self.usado_por("Invernadero Este", self.otro)
        self.sin_agronomo = self.usado_por("Invernadero Oeste", None)

    def test_post_b_los_agronomos_de_otros_invernaderos_reciben_un_aviso_con_el_cambio(self):
        """CMP-MOD-INS postcondición b y verificación a mano 8: título y detalle aprobados, sin el actor."""
        self.preparar_avisos()
        self.modificar(nombre="Detergente líquido")
        avisos = Notificacion.objects.all()
        self.assertEqual([a.destinatario_id for a in avisos], [self.otro.pk])
        self.assertEqual(avisos[0].titulo, "Cambió el insumo Detergente")
        self.assertEqual(
            avisos[0].detalle, "Ana Gómez modificó sus datos en el catálogo. Revisá si afecta a tus invernaderos."
        )

    def test_post_b_un_agronomo_con_dos_invernaderos_recibe_un_solo_aviso_y_el_actor_ninguno(self):
        """CMP-MOD-INS regla 5 y docs/api/notificaciones.md regla 5: una sola llamada a ``notificar_a_varios`` (sin repetir cuentas,
        sin el actor, y un invernadero sin Agrónomo no genera aviso)."""
        self.preparar_avisos()
        self.modificar(descripcion="otra")
        self.assertEqual(Notificacion.objects.filter(destinatario_id=self.otro.pk).count(), 1)
        self.assertEqual(Notificacion.objects.filter(destinatario_id=self.agronomo.pk).count(), 0)
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_post_b_no_avisa_a_un_agronomo_inactivo_ni_de_invernaderos_que_no_lo_usan(self):
        """CMP-MOD-INS postcondición b: solo «los otros invernaderos que tienen el insumo habilitado» (activo)."""
        ajeno = crear_agronomo(email="ajeno@infoponia.com")
        crear_invernadero("Invernadero Que No Lo Usa", agronomo=ajeno)
        self.modificar(nombre="Otro")
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_regla_5_a_quienes_avisara_informa_los_invernaderos_antes_de_confirmar_y_no_cambia_nada(self):
        """CMP-MOD-INS regla 5: la pantalla pide la lista (sin el actor, por nombre) y no cambia nada."""
        self.preparar_avisos()
        a_avisar = insumos.a_quienes_avisara(self.agronomo, self.insumo.pk)
        self.assertEqual([i.nombre_invernadero for i in a_avisar], ["Invernadero Este", "Invernadero Norte"])
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_regla_5_el_aviso_no_bloquea_el_cambio(self):
        """CMP-MOD-INS regla 5: «El aviso no bloquea el cambio»: no hace falta confirmar."""
        self.preparar_avisos()
        self.assertEqual(self.modificar(nombre="Detergente líquido").nombre_insumo, "Detergente líquido")

    def test_regla_5_sin_cambios_no_se_avisa(self):
        """D-28: sin cambios no hay nada que avisar."""
        self.preparar_avisos()
        self.modificar()
        self.assertEqual(Notificacion.objects.count(), 0)

    # ---- regla 6: reactivar ----

    def test_regla_6_reactivar_deja_el_insumo_activo_y_sin_habilitar_en_ningun_invernadero(self):
        """CMP-MOD-INS postcondición c y regla 6 (verificación a mano 5 de BAJ): las habilitaciones siguen inactivas."""
        viejo = insumo("Viejo", tipo=self.tipo, activo=False)
        iin = existencia(viejo, crear_invernadero("Invernadero Uno", agronomo=self.agronomo), activo=False)
        reactivado = insumos.reactivar_insumo(self.agronomo, viejo.pk)
        iin.refresh_from_db()
        self.assertEqual((reactivado.estado_insumo, iin.estado_insumo_invernadero), ("activo", "inactivo"))

    def test_regla_6_reactivar_exige_la_categoria_activa(self):
        """CMP-MOD-INS regla 6: «solo si su categoría está activa»."""
        inactiva = tipo_de_insumo("Vieja", activo=False)
        viejo = insumo("Viejo", tipo=inactiva, activo=False)
        error = error_de(lambda: insumos.reactivar_insumo(self.agronomo, viejo.pk))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["categoria_inactiva"])
        viejo.refresh_from_db()
        self.assertEqual(viejo.estado_insumo, "inactivo")

    def test_regla_6_reactivar_un_insumo_activo_o_una_semilla_se_rechaza_y_exige_agronomo(self):
        """Protecciones de ``reactivar_insumo``: ``insumo_no_inactivo``, ``insumo_semilla``, rol y 404."""
        self.assertEqual(codigos_de(error_de(lambda: insumos.reactivar_insumo(self.agronomo, self.insumo.pk)), NON_FIELD_ERRORS), ["insumo_no_inactivo"])
        semilla = insumo("Semilla X", tipo=categoria_del_sistema("semillas"), unidad="unidad", activo=False)
        self.assertEqual(codigos_de(error_de(lambda: insumos.reactivar_insumo(self.agronomo, semilla.pk)), NON_FIELD_ERRORS), ["insumo_semilla"])
        with self.assertRaises(PermissionDenied):
            insumos.reactivar_insumo(crear_gerente(), semilla.pk)
        with self.assertRaises(Http404):
            insumos.reactivar_insumo(self.agronomo, 999999)

    # ---- D-28 y postcondiciones ----

    def test_d28_sin_cambios_no_se_escribe_ni_se_audita(self):
        """D-28: guardar los mismos valores (aunque cambien los espacios) no escribe ni deja registro."""
        self.modificar(nombre="  Detergente ", descripcion=" 5 L ")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_post_a_se_actualizan_los_datos_indicados(self):
        """CMP-MOD-INS postcondición a."""
        destino = tipo_de_insumo("Higiene")
        cambiado = self.modificar(nombre="Jabón", descripcion="", tipo_insumo_id=destino.pk, unidad="kg", controla_vencimiento=True)
        cambiado.refresh_from_db()
        self.assertEqual(
            (cambiado.nombre_insumo, cambiado.descripcion_insumo, cambiado.tipo_insumo_id, cambiado.unidad_medida_insumo, cambiado.controla_vencimiento),
            ("Jabón", "", destino.pk, "kg", True),
        )

    def test_post_d_audita_solo_lo_que_cambio_con_antes_y_despues(self):
        """CMP-MOD-INS postcondición d y D-36: usuario, rol, insumo y los cambios (la categoría, como referencia)."""
        destino = tipo_de_insumo("Higiene")
        self.modificar(nombre="Jabón", tipo_insumo_id=destino.pk, controla_vencimiento=True)
        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertEqual((registro.usuario_id, registro.rol), (self.agronomo.pk, "agronomo"))
        self.assertEqual([a["id"] for a in registro.afectados], [self.insumo.pk])
        self.assertEqual(
            registro.detalle["cambios"],
            {
                "nombre": {"antes": "Detergente", "despues": "Jabón"},
                "categoria": {
                    "antes": {"id": self.tipo.pk, "texto": "Limpieza"},
                    "despues": {"id": destino.pk, "texto": "Higiene"},
                },
                "controla_vencimiento": {"antes": False, "despues": True},
            },
        )

    def test_post_d_audita_la_reactivacion_con_su_propia_accion(self):
        """CMP-MOD-INS postcondición d: ``reactivacion_insumo`` con el cambio de estado."""
        viejo = insumo("Viejo", tipo=self.tipo, activo=False)
        insumos.reactivar_insumo(self.agronomo, viejo.pk)
        registro = RegistroAuditoria.objects.get(accion=REACTIVACION)
        self.assertEqual(registro.detalle["cambios"], {"estado": {"antes": "inactivo", "despues": "activo"}})
        self.assertEqual([a["id"] for a in registro.afectados], [viejo.pk])


@tag("concurrencia")
class CmpModInsConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Bloqueos de ``modificar_insumo`` (D-40; docs/patrones/stock.md sección 5: invernaderos → categoría → insumo → existencias).
    Hereda de ``ConDatosDeInventario`` y asegura los datos de inventario y de maestros en cada prueba (el ``flush`` los vacía); los
    invernaderos se arman con su propia geografía por la misma razón."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        self.uno = crear_agronomo()
        self.otro = crear_agronomo(email="otro@infoponia.com")
        self.tipo = tipo_de_insumo("Limpieza")
        self.insumo = insumo("Detergente", tipo=self.tipo, unidad="l")
        self.invernadero = crear_invernadero_con_geografia_propia("Invernadero Uno", agronomo=self.uno)
        self.existencia = existencia(self.insumo, self.invernadero)

    def datos(self, **cambios):
        return {"nombre": "Detergente", "tipo_insumo_id": self.tipo.pk, "unidad": "l", "descripcion": "", "controla_vencimiento": False} | cambios

    def test_regla_3_la_unidad_no_cambia_si_un_ajuste_carga_stock_a_la_vez(self):
        """CMP-MOD-INS regla 3: quien carga stock bloquea el invernadero antes; la modificación espera, ve el lote y rechaza el
        cambio de unidad con ``unidad_bloqueada`` (sin esto cambiaría la unidad de un insumo que ya tiene stock)."""
        resultados = correr_a_la_vez(
            lambda: ajuste_simulado(self.otro, self.existencia, 5),
            lambda: insumos.modificar_insumo(self.uno, self.insumo.pk, **self.datos(unidad="kg")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["unidad_bloqueada"])
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.unidad_medida_insumo, "l")

    def test_pre_d_dos_renombres_de_insumos_distintos_al_mismo_nombre_dejan_uno_solo(self):
        """CMP-MOD-INS precondición d: el segundo espera el índice único y recibe ``nombre_repetido`` (nunca un 500)."""
        otro_insumo = insumo("Lavandina", tipo=self.tipo)
        resultados = correr_a_la_vez(
            lambda: insumos.modificar_insumo(self.uno, self.insumo.pk, **self.datos(nombre="Jabón")),
            lambda: insumos.modificar_insumo(self.otro, otro_insumo.pk, **self.datos(nombre="jabón", unidad="l")),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["nombre_repetido"])
        self.assertEqual(Insumo.objects.filter(nombre_insumo__iexact="jabón").count(), 1)
