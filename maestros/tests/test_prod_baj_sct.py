# Pruebas de PROD-BAJ-SCT · Baja Sector (docs/casos_de_uso/maestros/sectores.md) y de la postcondición f de PROD-BAJ-INV
# (la baja de un invernadero pasa sus sectores a inactivos, con un log por sector). Cita D-22 y D-36 (auditoría).
#
# Servicios que se prueban (maestros/servicios/sectores.py), tomados del módulo dentro de cada prueba:
#   baja_sector(actor, sector_id, *, advertencia_confirmada=False) -> sector
#     - Precondición c: el sector no está activo ni fuera de servicio -> ValidationError general ``sector_inactivo``.
#     - Precondiciones d y e y reglas 2 y 3: los impedimentos de ``registrar_impedimento_de_baja_de_sector`` (se informan
#       TODOS juntos, un error por impedimento con su código) y no se cambia nada.
#     - Regla 4: si deja al invernadero sin sectores activos de ese tipo y no viene ``advertencia_confirmada``,
#       FaltaConfirmarAdvertencia(avisos).
#   impedimentos_para_baja(actor, sector_id) -> list[Impedimento]: solo lectura, para la ventana.
# Puntos de extensión con registrantes falsos: ``_IMPEDIMENTOS_DE_SECTOR``, ``_EFECTOS_DE_BAJA_DE_SECTOR``.

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from maestros.extensiones import Impedimento
from maestros.models import SectorProduccion
from maestros.servicios import invernaderos, sectores
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    codigos_de,
    con_extension,
    crear_agronomo,
    crear_agronomo_con_invernadero,
    crear_invernadero,
    crear_sector,
    error_de,
    tipo_etapa,
)

BAJA = RegistroAuditoria.Accion.BAJA_SECTOR


def ocupados(sector):
    """Un impedimento de prueba: el sector tiene lotes que lo ocupan."""
    return [Impedimento("agujeros_ocupados", "Tiene 3 agujeros ocupados por L-1.", "Sacalo de servicio.")]


def comprometidos(sector):
    """Un impedimento de prueba: tiene órdenes que lo reservan."""
    return [Impedimento("agujeros_comprometidos", "Tiene 5 agujeros reservados por OT-2.", "Cancelá la orden.")]


def con_hardware(sector):
    """Un impedimento de prueba: tiene hardware activo."""
    return [Impedimento("hardware_activo", "Tiene el equipo Sensor 1.", "Quitale el sector.")]


class ProdBajSctServicioTests(ConDatosDeMaestros, TestCase):
    """Precondiciones, reglas y postcondiciones de PROD-BAJ-SCT."""

    def setUp(self):
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero()
        self.otro_germinacion = crear_sector(self.invernadero, "G-2", "germinacion")  # evita la advertencia de la regla 4
        self.sector = crear_sector(self.invernadero, "G-1", "germinacion")

    def baja(self, sector=None, actor=None, **extra):
        return sectores.baja_sector(actor or self.agronomo, (sector or self.sector).pk, **extra)

    # ---- precondiciones ----

    def test_pre_a_un_gerente_no_da_de_baja(self):
        """PROD-BAJ-SCT precondición a: solo un Agrónomo activo."""
        with self.assertRaises(PermissionDenied):
            self.baja(actor=crear_gerente())

    def test_pre_b_el_agronomo_de_otro_invernadero_no_da_de_baja(self):
        """PROD-BAJ-SCT precondición b: el invernadero tiene que estar a cargo del actor."""
        with self.assertRaises(PermissionDenied):
            self.baja(actor=crear_agronomo(email="otro@infoponia.com"))

    def test_pre_b_un_invernadero_inactivo_se_rechaza(self):
        """PROD-BAJ-SCT precondición b: el invernadero está activo."""
        self.invernadero.estado_invernadero = "inactivo"
        self.invernadero.save()
        self.assertEqual(codigos_de(error_de(self.baja), NON_FIELD_ERRORS), ["invernadero_inactivo"])

    def test_pre_c_un_sector_ya_dado_de_baja_se_rechaza(self):
        """PROD-BAJ-SCT precondición c: el sector está activo o fuera de servicio."""
        ya = crear_sector(self.invernadero, "G-3", estado="inactivo")
        self.assertEqual(codigos_de(error_de(lambda: self.baja(sector=ya)), NON_FIELD_ERRORS), ["sector_inactivo"])

    def test_pre_c_un_sector_fuera_de_servicio_se_puede_dar_de_baja(self):
        """PROD-BAJ-SCT precondición c: activo o fuera de servicio."""
        fuera = crear_sector(self.invernadero, "F-1", "crecimiento", estado="fuera_de_servicio")
        self.assertEqual(self.baja(sector=fuera).estado_sector, "inactivo")

    def test_pre_a_un_sector_que_no_existe_da_404(self):
        """Un id inexistente da 404."""
        with self.assertRaises(Http404):
            sectores.baja_sector(self.agronomo, 999999)

    def test_pre_d_con_agujeros_ocupados_no_se_da_de_baja(self):
        """PROD-BAJ-SCT precondición d y regla 2: lo informa el registrante de `produccion`; no cambia nada."""
        with con_extension("_IMPEDIMENTOS_DE_SECTOR", ocupados):
            error = error_de(self.baja)
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["agujeros_ocupados"])
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.estado_sector, "activo")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=BAJA).exists())

    def test_pre_e_con_hardware_activo_no_se_da_de_baja(self):
        """PROD-BAJ-SCT precondición e y regla 3: lo informa el registrante de `iot`."""
        with con_extension("_IMPEDIMENTOS_DE_SECTOR", con_hardware):
            self.assertEqual(codigos_de(error_de(self.baja), NON_FIELD_ERRORS), ["hardware_activo"])

    def test_regla_2_se_informan_todos_los_impedimentos_juntos(self):
        """PROD-BAJ-SCT reglas 2 y 3: no se queda con el primero."""
        with con_extension("_IMPEDIMENTOS_DE_SECTOR", ocupados, comprometidos, con_hardware):
            error = error_de(self.baja)
        self.assertEqual(
            sorted(codigos_de(error, NON_FIELD_ERRORS)), ["agujeros_comprometidos", "agujeros_ocupados", "hardware_activo"]
        )

    def test_regla_2_el_mensaje_dice_que_pasa_y_como_resolverlo(self):
        """PROD-BAJ-SCT regla 2: cada impedimento lleva su texto y cómo resolverlo."""
        with con_extension("_IMPEDIMENTOS_DE_SECTOR", ocupados):
            error = error_de(self.baja)
        mensaje = error.error_dict[NON_FIELD_ERRORS][0].message
        self.assertIn("Tiene 3 agujeros ocupados por L-1.", mensaje)
        self.assertIn("Sacalo de servicio.", mensaje)

    def test_regla_2_los_impedimentos_para_la_ventana_se_leen_sin_cambiar_nada(self):
        """La ventana de baja lista los impedimentos antes de confirmar (solo lectura, sin auditar)."""
        with con_extension("_IMPEDIMENTOS_DE_SECTOR", ocupados, con_hardware):
            impedimentos = sectores.impedimentos_para_baja(self.agronomo, self.sector.pk)
        self.assertEqual([i.codigo for i in impedimentos], ["agujeros_ocupados", "hardware_activo"])
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.estado_sector, "activo")
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_2_sin_registrantes_no_hay_impedimentos(self):
        """«Cómo se aplica»: sin registrantes, ningún impedimento."""
        self.assertEqual(sectores.impedimentos_de_baja_de_sector(self.sector), [])

    # ---- regla 1 y postcondiciones ----

    def test_regla_1_la_baja_es_logica_y_conserva_el_sector(self):
        """PROD-BAJ-SCT regla 1: el sector conserva sus datos y su historial."""
        self.baja()
        self.sector.refresh_from_db()
        self.assertEqual((self.sector.estado_sector, self.sector.nombre_sector, self.sector.cant_agujeros_total), ("inactivo", "G-1", 100))
        self.assertTrue(SectorProduccion.objects.filter(pk=self.sector.pk).exists())

    def test_post_a_el_sector_deja_de_contar_como_capacidad(self):
        """PROD-BAJ-SCT postcondición a y regla 5: un sector dado de baja no cuenta; uno fuera de servicio, sí."""
        solo, _ = crear_agronomo_con_invernadero("Solo", email="solo@infoponia.com")
        inv = crear_invernadero("Otro", agronomo=solo)
        unico = crear_sector(inv, "U-1")
        fuera = crear_sector(inv, "U-2", "crecimiento", estado="fuera_de_servicio")
        sectores.baja_sector(solo, unico.pk, advertencia_confirmada=True)
        self.assertTrue(inv.tiene_sectores())  # el fuera de servicio sigue contando
        sectores.baja_sector(solo, fuera.pk, advertencia_confirmada=True)
        self.assertFalse(inv.tiene_sectores())

    def test_post_b_si_estaba_fuera_de_servicio_se_llama_al_efecto_de_baja_dentro_de_la_transaccion(self):
        """PROD-BAJ-SCT postcondición b: cerrar el registro «Fuera de servicio» es de PRD-04, por el punto
        ``registrar_efecto_de_baja_de_sector``: una vez, con (actor, sector), dentro de la transacción."""
        llamadas = []

        def efecto(actor, sector):
            llamadas.append((actor, sector.pk, connection.in_atomic_block))

        fuera = crear_sector(self.invernadero, "F-1", "crecimiento", estado="fuera_de_servicio")
        with con_extension("_EFECTOS_DE_BAJA_DE_SECTOR", efecto):
            self.baja(sector=fuera)
        self.assertEqual(llamadas, [(self.agronomo, fuera.pk, True)])

    def test_post_b_sin_registrantes_la_baja_funciona_igual(self):
        """API, lote 5: sin registrantes la baja funciona."""
        self.assertEqual(self.baja().estado_sector, "inactivo")

    def test_post_b_si_el_efecto_falla_no_queda_nada(self):
        """D-22: todo o nada."""

        def falla(actor, sector):
            raise RuntimeError("falla de prueba")

        with con_extension("_EFECTOS_DE_BAJA_DE_SECTOR", falla), self.assertRaises(RuntimeError):
            self.baja()
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.estado_sector, "activo")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=BAJA).exists())

    def test_post_c_audita_la_baja_con_el_cambio_de_estado(self):
        """PROD-BAJ-SCT postcondición c y D-36: usuario, rol, sector y cambio de estado."""
        self.baja()
        registro = RegistroAuditoria.objects.get(accion=BAJA)
        self.assertEqual((registro.usuario_id, registro.rol), (self.agronomo.pk, "agronomo"))
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "activo", "despues": "inactivo"})
        self.assertEqual({a["id"] for a in registro.afectados}, {self.sector.pk, self.invernadero.pk})

    def test_post_c_la_baja_de_un_sector_fuera_de_servicio_audita_el_estado_anterior(self):
        """D-36: el valor anterior es «fuera_de_servicio»."""
        fuera = crear_sector(self.invernadero, "F-1", "crecimiento", estado="fuera_de_servicio")
        self.baja(sector=fuera)
        cambios = RegistroAuditoria.objects.get(accion=BAJA).detalle["cambios"]["estado"]
        self.assertEqual(cambios, {"antes": "fuera_de_servicio", "despues": "inactivo"})

    # ---- regla 4: advertencia ----

    def test_regla_4_dar_de_baja_el_ultimo_sector_activo_del_tipo_pide_confirmar(self):
        """PROD-BAJ-SCT regla 4: advierte sin bloquear, igual que en la regla 4 de PROD-MOD-SCT."""
        unico = crear_sector(self.invernadero, "M-1", "maduracion")
        with self.assertRaises(sectores.FaltaConfirmarAdvertencia) as contexto:
            self.baja(sector=unico)
        self.assertTrue(contexto.exception.avisos)
        unico.refresh_from_db()
        self.assertEqual(unico.estado_sector, "activo")

    def test_regla_4_con_la_advertencia_confirmada_se_da_de_baja(self):
        """PROD-BAJ-SCT regla 4: el Agrónomo puede continuar igual."""
        unico = crear_sector(self.invernadero, "M-1", "maduracion")
        self.assertEqual(self.baja(sector=unico, advertencia_confirmada=True).estado_sector, "inactivo")

    def test_regla_4_no_advierte_si_queda_otro_sector_activo_del_tipo(self):
        """PROD-BAJ-SCT regla 4: solo si el invernadero queda sin sectores activos de ese tipo."""
        self.assertEqual(self.baja().estado_sector, "inactivo")  # queda G-2

    def test_regla_4_el_aviso_incluye_los_de_los_registrantes(self):
        """PROD-BAJ-SCT regla 4: lotes y siembras afectados salen del punto de extensión."""
        from maestros.extensiones import Aviso

        propio = Aviso("Siembras a realizar afectadas: OT-3.", 1)
        unico = crear_sector(self.invernadero, "M-1", "maduracion")
        with con_extension("_AVISOS_DE_CAMBIO_DE_TIPO", lambda inv, tipo: [propio]):
            with self.assertRaises(sectores.FaltaConfirmarAdvertencia) as contexto:
                self.baja(sector=unico)
        self.assertIn(propio, contexto.exception.avisos)

    def test_regla_4_un_impedimento_gana_a_la_advertencia(self):
        """Los impedimentos bloquean antes de pedir la confirmación: no se advierte lo que no se puede hacer."""
        unico = crear_sector(self.invernadero, "M-1", "maduracion")
        with con_extension("_IMPEDIMENTOS_DE_SECTOR", ocupados):
            self.assertEqual(codigos_de(error_de(lambda: self.baja(sector=unico)), NON_FIELD_ERRORS), ["agujeros_ocupados"])


class ProdBajInvSectoresTests(ConDatosDeMaestros, TestCase):
    """Postcondición f de PROD-BAJ-INV (docs/casos_de_uso/maestros/invernaderos.md; sectores.md, «Decisiones de aplicación»):
    al dar de baja el invernadero, sus sectores pasan a inactivos, con un log de auditoría por sector."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero()

    def test_post_f_los_sectores_activos_y_fuera_de_servicio_pasan_a_inactivos(self):
        """PROD-BAJ-INV postcondición b/f: todos los sectores del invernadero quedan inactivos."""
        activo = crear_sector(self.invernadero, "A-1")
        fuera = crear_sector(self.invernadero, "F-1", "crecimiento", estado="fuera_de_servicio")
        invernaderos.baja_invernadero(self.gerente, self.invernadero.pk)
        for sector in (activo, fuera):
            sector.refresh_from_db()
            self.assertEqual(sector.estado_sector, "inactivo")

    def test_post_f_deja_un_log_por_sector_con_la_accion_baja_sector(self):
        """PROD-BAJ-INV postcondición f: un log por sector, con la acción ``baja_sector`` y el cambio de estado."""
        activo = crear_sector(self.invernadero, "A-1")
        fuera = crear_sector(self.invernadero, "F-1", "crecimiento", estado="fuera_de_servicio")
        invernaderos.baja_invernadero(self.gerente, self.invernadero.pk)
        registros = RegistroAuditoria.objects.filter(accion=BAJA)
        self.assertEqual(registros.count(), 2)
        estados = {
            registro.afectados[0]["id"]: registro.detalle["cambios"]["estado"] for registro in registros
        }
        self.assertEqual(estados[activo.pk], {"antes": "activo", "despues": "inactivo"})
        self.assertEqual(estados[fuera.pk], {"antes": "fuera_de_servicio", "despues": "inactivo"})
        self.assertTrue(all(r.usuario_id == self.gerente.pk for r in registros))

    def test_post_f_un_sector_ya_dado_de_baja_no_genera_otro_log(self):
        """Un sector inactivo no cambia: no se audita."""
        crear_sector(self.invernadero, "B-1", estado="inactivo")
        invernaderos.baja_invernadero(self.gerente, self.invernadero.pk)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=BAJA).exists())

    def test_post_f_no_toca_los_sectores_de_otros_invernaderos(self):
        """Solo los sectores del invernadero que se da de baja."""
        ajeno = crear_sector(crear_invernadero("Otro", agronomo=self.agronomo), "X-1")
        invernaderos.baja_invernadero(self.gerente, self.invernadero.pk)
        ajeno.refresh_from_db()
        self.assertEqual(ajeno.estado_sector, "activo")

    def test_regla_6_reactivar_el_invernadero_no_reactiva_sus_sectores(self):
        """PROD-BAJ-INV regla 6: los reactiva el Agrónomo con PROD-MOD-SCT."""
        sector = crear_sector(self.invernadero, "A-1")
        invernaderos.baja_invernadero(self.gerente, self.invernadero.pk)
        invernaderos.reactivar_invernadero(self.gerente, self.invernadero.pk)
        sector.refresh_from_db()
        self.assertEqual(sector.estado_sector, "inactivo")
        self.assertEqual(sectores.reactivar_sector(self.agronomo, sector.pk).estado_sector, "activo")

    def test_post_f_la_baja_sin_sectores_sigue_funcionando(self):
        """Un invernadero sin sectores se da de baja como antes."""
        self.assertFalse(invernaderos.baja_invernadero(self.gerente, self.invernadero.pk).activo)
        self.assertFalse(RegistroAuditoria.objects.filter(accion=BAJA).exists())

    def test_post_f_si_la_baja_se_rechaza_los_sectores_siguen_activos(self):
        """D-22: todo o nada; con un impedimento del invernadero no cambia ningún sector."""
        from maestros.extensiones import Impedimento as Imp

        sector = crear_sector(self.invernadero, "A-1")
        with con_extension("_IMPEDIMENTOS", lambda inv: [Imp("lotes_activos", "Tiene lotes.", "Cosechalos.")]):
            error_de(lambda: invernaderos.baja_invernadero(self.gerente, self.invernadero.pk))
        sector.refresh_from_db()
        self.assertEqual(sector.estado_sector, "activo")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=BAJA).exists())

    def test_post_f_el_tipo_de_etapa_no_cambia(self):
        """La baja solo cambia el estado."""
        sector = crear_sector(self.invernadero, "A-1", "floracion")
        invernaderos.baja_invernadero(self.gerente, self.invernadero.pk)
        sector.refresh_from_db()
        self.assertEqual(sector.tipo_etapa, tipo_etapa("floracion"))


class AvisosParaBajaTests(ConDatosDeMaestros, TestCase):
    """``avisos_para_baja``: la advertencia de la regla 4 de PROD-BAJ-SCT para mostrarla en la ventana antes de confirmar (solo
    lectura; la ventana es la confirmación)."""

    def setUp(self):
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero()

    def test_regla_4_el_ultimo_sector_activo_del_tipo_tiene_avisos(self):
        """PROD-BAJ-SCT regla 4: el encabezado y la recomendación."""
        unico = crear_sector(self.invernadero, "M-1", "maduracion")
        avisos = sectores.avisos_para_baja(self.agronomo, unico.pk)
        self.assertIn("es el último sector activo de Maduración", avisos[0].texto)
        self.assertIn("Se recomienda registrar otro sector", avisos[0].texto)

    def test_regla_4_con_otro_sector_activo_del_tipo_no_hay_avisos(self):
        """PROD-BAJ-SCT regla 4: solo si el invernadero queda sin sectores activos de ese tipo."""
        crear_sector(self.invernadero, "G-2", "germinacion")
        self.assertEqual(sectores.avisos_para_baja(self.agronomo, crear_sector(self.invernadero, "G-1", "germinacion").pk), [])

    def test_regla_4_un_sector_fuera_de_servicio_no_tiene_avisos(self):
        """Solo un sector activo deja de contar como sector activo del tipo."""
        fuera = crear_sector(self.invernadero, "F-1", "crecimiento", estado="fuera_de_servicio")
        self.assertEqual(sectores.avisos_para_baja(self.agronomo, fuera.pk), [])

    def test_regla_4_no_cambia_nada_ni_audita(self):
        """Solo lectura."""
        unico = crear_sector(self.invernadero, "M-1", "maduracion")
        sectores.avisos_para_baja(self.agronomo, unico.pk)
        unico.refresh_from_db()
        self.assertEqual(unico.estado_sector, "activo")
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_pre_a_un_gerente_no_pide_los_avisos(self):
        """Precondición a: solo el Agrónomo hace la baja."""
        unico = crear_sector(self.invernadero, "M-1", "maduracion")
        with self.assertRaises(PermissionDenied):
            sectores.avisos_para_baja(crear_gerente(), unico.pk)
