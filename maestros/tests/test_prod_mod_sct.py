# Pruebas de PROD-MOD-SCT · Modificar Sector (docs/casos_de_uso/maestros/sectores.md): datos, volver a activar un sector fuera de
# servicio y reactivar uno dado de baja. Cita D-22 y D-36 (auditoría), D-28 (sin cambios no se audita) y D-40 (bloqueos).
#
# Servicios que se prueban (maestros/servicios/sectores.py), tomados del módulo dentro de cada prueba:
#   modificar_sector(actor, sector_id, *, nombre, tipo_etapa_id, cant_agujeros_total, advertencia_confirmada=False) -> sector
#     - Regla 4: si el cambio de tipo deja al invernadero sin sectores activos del tipo anterior y no viene
#       ``advertencia_confirmada``, lanza FaltaConfirmarAdvertencia(avisos) y no cambia nada.
#   reactivar_sector(actor, sector_id) y volver_a_servicio_sector(actor, sector_id).
# Puntos de extensión con registrantes falsos: ``_AGUJEROS``, ``_AVISOS_DE_CAMBIO_DE_TIPO`` y ``_VUELTAS_A_SERVICIO``.

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import TestCase

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from maestros.extensiones import Aviso
from maestros.models import SectorProduccion
from maestros.servicios import sectores
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    codigos_de,
    con_agujeros,
    con_extension,
    crear_agronomo,
    crear_agronomo_con_invernadero,
    crear_ciclo,
    crear_cultivo,
    crear_invernadero,
    crear_sector,
    crear_variedad,
    error_de,
    tipo_etapa,
)

MODIFICACION = RegistroAuditoria.Accion.MODIFICACION_SECTOR
REACTIVACION = RegistroAuditoria.Accion.REACTIVACION_SECTOR


class ProdModSctServicioTests(ConDatosDeMaestros, TestCase):
    """Reglas, precondiciones y postcondiciones de PROD-MOD-SCT (modificar datos)."""

    def setUp(self):
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero()
        self.sector = crear_sector(self.invernadero, "C-1", "germinacion", 100)

    def modificar(self, sector=None, actor=None, **datos):
        """Llama al servicio con los datos actuales del sector; ``datos`` pisa cualquiera."""
        sector = sector or self.sector
        sector.refresh_from_db()
        datos = {
            "nombre": sector.nombre_sector,
            "tipo_etapa_id": sector.tipo_etapa_id,
            "cant_agujeros_total": sector.cant_agujeros_total,
        } | datos
        return sectores.modificar_sector(actor or self.agronomo, sector.pk, **datos)

    # ---- precondiciones ----

    def test_pre_a_un_gerente_no_modifica(self):
        """PROD-MOD-SCT precondición a: solo un Agrónomo activo."""
        with self.assertRaises(PermissionDenied):
            self.modificar(actor=crear_gerente(), nombre="Otro")

    def test_pre_b_el_agronomo_de_otro_invernadero_no_modifica(self):
        """PROD-MOD-SCT precondición b: el invernadero tiene que estar a cargo del actor."""
        with self.assertRaises(PermissionDenied):
            self.modificar(actor=crear_agronomo(email="otro@infoponia.com"), nombre="Otro")

    def test_pre_b_un_invernadero_inactivo_se_rechaza(self):
        """PROD-MOD-SCT precondición b: el invernadero está activo."""
        self.invernadero.estado_invernadero = "inactivo"
        self.invernadero.save()
        error = error_de(lambda: self.modificar(nombre="Otro"))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["invernadero_inactivo"])

    def test_pre_a_un_sector_que_no_existe_da_404(self):
        """Un id inexistente da 404."""
        with self.assertRaises(Http404):
            sectores.modificar_sector(
                self.agronomo, 999999, nombre="X", tipo_etapa_id=tipo_etapa().pk, cant_agujeros_total=5
            )

    def test_pre_c_el_nombre_nuevo_no_puede_repetirse_en_el_invernadero(self):
        """PROD-MOD-SCT precondición c y regla 1: se respeta la regla 2 de PROD-ALT-SCT (sin distinguir mayúsculas)."""
        crear_sector(self.invernadero, "C-2")
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(nombre="c-2")), "nombre"), ["nombre_repetido"])

    def test_pre_c_el_nombre_repetido_cuenta_tambien_entre_los_dados_de_baja(self):
        """Regla 2 de PROD-ALT-SCT, citada por la regla 1 de PROD-MOD-SCT."""
        crear_sector(self.invernadero, "C-2", estado="inactivo")
        self.assertEqual(codigos_de(error_de(lambda: self.modificar(nombre="C-2")), "nombre"), ["nombre_repetido"])

    def test_pre_c_cambiar_solo_las_mayusculas_del_propio_nombre_se_permite(self):
        """El sector no choca consigo mismo."""
        self.assertEqual(self.modificar(nombre="c-1").nombre_sector, "c-1")

    def test_pre_c_un_nombre_igual_al_de_un_sector_de_otro_invernadero_se_permite(self):
        """Regla 2 de PROD-ALT-SCT: dos invernaderos pueden repetir nombres."""
        crear_sector(crear_invernadero("Otro", agronomo=self.agronomo), "C-9")
        self.assertEqual(self.modificar(nombre="C-9").nombre_sector, "C-9")

    # ---- regla 1: qué se puede cambiar ----

    def test_regla_1_el_nombre_se_cambia_siempre(self):
        """PROD-MOD-SCT regla 1: el nombre, siempre, aunque el sector tenga agujeros ocupados."""
        with con_agujeros(ocupados=40, comprometidos=10):
            self.assertEqual(self.modificar(nombre="Nuevo").nombre_sector, "Nuevo")

    def test_regla_1_la_cantidad_se_puede_subir_siempre(self):
        """PROD-MOD-SCT regla 1: subir el total no tiene piso."""
        with con_agujeros(ocupados=60, comprometidos=40):
            self.assertEqual(self.modificar(cant_agujeros_total=500).cant_agujeros_total, 500)

    def test_regla_1_la_cantidad_baja_hasta_ocupados_mas_comprometidos(self):
        """PROD-MOD-SCT regla 1: el mínimo es la suma de ocupados y comprometidos; en el piso, se permite."""
        with con_agujeros(ocupados=30, comprometidos=20):
            self.assertEqual(self.modificar(cant_agujeros_total=50).cant_agujeros_total, 50)

    def test_regla_1_por_debajo_del_minimo_se_rechaza(self):
        """PROD-MOD-SCT regla 1: un agujero menos que el piso es un error del campo."""
        with con_agujeros(ocupados=30, comprometidos=20):
            error = error_de(lambda: self.modificar(cant_agujeros_total=49))
        self.assertEqual(codigos_de(error, "cant_agujeros_total"), ["por_debajo_del_minimo"])
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.cant_agujeros_total, 100)

    def test_regla_1_la_cantidad_tiene_que_ser_un_entero_mayor_que_cero(self):
        """Regla 4 de PROD-ALT-SCT, citada por MOD."""
        for invalida in (0, "x", ""):
            with self.subTest(invalida=invalida):
                error = error_de(lambda: self.modificar(cant_agujeros_total=invalida))
                self.assertEqual(len(codigos_de(error, "cant_agujeros_total")), 1)

    def test_regla_1_el_tipo_se_cambia_si_no_hay_ocupados_ni_comprometidos(self):
        """PROD-MOD-SCT regla 1: con otro sector activo del mismo tipo no hay advertencia y el cambio se guarda."""
        crear_sector(self.invernadero, "C-2", "germinacion")
        sector = self.modificar(tipo_etapa_id=tipo_etapa("crecimiento").pk)
        self.assertEqual(sector.tipo_etapa.codigo, "crecimiento")

    def test_regla_1_el_tipo_queda_bloqueado_con_agujeros_ocupados_o_comprometidos(self):
        """PROD-MOD-SCT regla 1: si los tiene, el campo queda bloqueado y el cambio se rechaza."""
        for ocupados, comprometidos in ((1, 0), (0, 1)):
            with self.subTest(ocupados=ocupados, comprometidos=comprometidos), con_agujeros(ocupados, comprometidos):
                error = error_de(lambda: self.modificar(tipo_etapa_id=tipo_etapa("crecimiento").pk))
                self.assertEqual(codigos_de(error, "tipo_etapa"), ["tipo_bloqueado"])
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.tipo_etapa.codigo, "germinacion")

    def test_regla_1_con_agujeros_ocupados_se_puede_guardar_si_el_tipo_no_cambia(self):
        """El bloqueo es del cambio de tipo: reenviar el mismo tipo no lo es."""
        with con_agujeros(ocupados=10):
            self.assertEqual(self.modificar(nombre="Otro").nombre_sector, "Otro")

    def test_regla_1_el_invernadero_no_se_cambia_nunca(self):
        """PROD-MOD-SCT regla 1: el servicio no recibe un invernadero y el sector conserva el suyo."""
        self.modificar(nombre="Otro")
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.invernadero, self.invernadero)

    # ---- reglas 2, 3 y 6: estados ----

    def test_regla_2_un_sector_fuera_de_servicio_se_modifica_y_sigue_fuera_de_servicio(self):
        """PROD-MOD-SCT regla 2."""
        fuera = crear_sector(self.invernadero, "C-2", estado="fuera_de_servicio")
        self.modificar(sector=fuera, nombre="C-2 bis")
        fuera.refresh_from_db()
        self.assertEqual((fuera.nombre_sector, fuera.estado_sector), ("C-2 bis", "fuera_de_servicio"))

    def test_regla_2_modificar_un_sector_activo_lo_deja_activo(self):
        """PROD-MOD-SCT regla 2 y 6: modificar no cambia el estado."""
        self.assertEqual(self.modificar(nombre="Otro").estado_sector, "activo")

    def test_regla_3_un_sector_dado_de_baja_no_se_modifica(self):
        """PROD-MOD-SCT regla 3: solo se reactiva."""
        baja = crear_sector(self.invernadero, "C-2", estado="inactivo")
        error = error_de(lambda: self.modificar(sector=baja, nombre="Otro"))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["sector_inactivo"])

    # ---- regla 4: advertencia del cambio de tipo ----

    def test_regla_4_cambiar_el_tipo_del_ultimo_sector_de_la_etapa_pide_confirmar(self):
        """PROD-MOD-SCT regla 4: advierte sin bloquear y no cambia nada hasta que se confirma."""
        with self.assertRaises(sectores.FaltaConfirmarAdvertencia) as contexto:
            self.modificar(tipo_etapa_id=tipo_etapa("crecimiento").pk)
        self.assertTrue(contexto.exception.avisos)
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.tipo_etapa.codigo, "germinacion")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_regla_4_con_la_advertencia_confirmada_el_cambio_se_guarda(self):
        """PROD-MOD-SCT regla 4: «el Agrónomo puede continuar igual»."""
        sector = self.modificar(tipo_etapa_id=tipo_etapa("crecimiento").pk, advertencia_confirmada=True)
        self.assertEqual(sector.tipo_etapa.codigo, "crecimiento")

    def test_regla_4_no_advierte_si_queda_otro_sector_activo_del_tipo_anterior(self):
        """PROD-MOD-SCT regla 4: solo cuando el invernadero queda sin sectores activos de ese tipo."""
        crear_sector(self.invernadero, "C-2", "germinacion")
        self.modificar(tipo_etapa_id=tipo_etapa("crecimiento").pk)

    def test_regla_4_un_sector_fuera_de_servicio_del_mismo_tipo_no_evita_la_advertencia(self):
        """Regla 4: se cuentan los sectores activos (un sector fuera de servicio no recibe plantas)."""
        crear_sector(self.invernadero, "C-2", "germinacion", estado="fuera_de_servicio")
        with self.assertRaises(sectores.FaltaConfirmarAdvertencia):
            self.modificar(tipo_etapa_id=tipo_etapa("crecimiento").pk)

    def test_regla_4_un_sector_de_otro_invernadero_no_evita_la_advertencia(self):
        """Regla 4: los sectores son del invernadero."""
        crear_sector(crear_invernadero("Otro", agronomo=self.agronomo), "C-9", "germinacion")
        with self.assertRaises(sectores.FaltaConfirmarAdvertencia):
            self.modificar(tipo_etapa_id=tipo_etapa("crecimiento").pk)

    def test_regla_4_un_sector_fuera_de_servicio_que_cambia_de_tipo_no_advierte(self):
        """Regla 4: solo un sector activo deja de contar como sector activo del tipo anterior."""
        fuera = crear_sector(self.invernadero, "C-2", "floracion", estado="fuera_de_servicio")
        self.modificar(sector=fuera, tipo_etapa_id=tipo_etapa("crecimiento").pk)

    def test_regla_4_el_aviso_incluye_las_variedades_que_dejan_de_poder_sembrarse(self):
        """PROD-MOD-SCT regla 4 y «Cómo se aplica»: variedades activas cuyo ciclo incluye el tipo anterior."""
        cultivo = crear_cultivo("Lechuga")
        crear_ciclo(crear_variedad(cultivo, "Crespa"), "germinacion", "maduracion")
        crear_ciclo(crear_variedad(cultivo, "Lisa", activa=False), "germinacion", "maduracion")  # inactiva: no cuenta
        crear_ciclo(crear_variedad(cultivo, "Rizada"), "crecimiento", "maduracion")  # sin germinación: no cuenta
        with self.assertRaises(sectores.FaltaConfirmarAdvertencia) as contexto:
            self.modificar(tipo_etapa_id=tipo_etapa("crecimiento").pk)
        textos = " ".join(a.texto for a in contexto.exception.avisos)
        self.assertIn("Lechuga Crespa", textos)
        self.assertNotIn("Lisa", textos)
        self.assertNotIn("Rizada", textos)

    def test_regla_4_el_aviso_suma_los_de_los_registrantes(self):
        """PROD-MOD-SCT regla 4: lotes y siembras afectados salen de ``registrar_aviso_de_cambio_de_tipo``."""
        propio = Aviso("Lotes que todavía tienen que pasar por Germinación: L-1.", 1)
        with con_extension("_AVISOS_DE_CAMBIO_DE_TIPO", lambda invernadero, tipo: [propio]):
            with self.assertRaises(sectores.FaltaConfirmarAdvertencia) as contexto:
                self.modificar(tipo_etapa_id=tipo_etapa("crecimiento").pk)
        self.assertIn(propio, contexto.exception.avisos)

    def test_regla_4_cambiar_solo_el_nombre_no_advierte(self):
        """La advertencia es del cambio de tipo."""
        self.modificar(nombre="Otro")

    # ---- reglas 5 y 6: volver a servicio y reactivar ----

    def test_regla_5_volver_a_activar_un_sector_fuera_de_servicio_no_tiene_validaciones(self):
        """PROD-MOD-SCT regla 5 y postcondición b: el sector queda activo."""
        fuera = crear_sector(self.invernadero, "C-2", estado="fuera_de_servicio")
        self.assertEqual(sectores.volver_a_servicio_sector(self.agronomo, fuera.pk).estado_sector, "activo")

    def test_regla_5_reactivar_un_sector_dado_de_baja_no_tiene_validaciones(self):
        """PROD-MOD-SCT regla 5 y postcondición c."""
        baja = crear_sector(self.invernadero, "C-2", estado="inactivo")
        self.assertEqual(sectores.reactivar_sector(self.agronomo, baja.pk).estado_sector, "activo")

    def test_regla_5_volver_a_servicio_solo_vale_para_un_sector_fuera_de_servicio(self):
        """Un sector activo o dado de baja no «vuelve a servicio»."""
        for estado in ("activo", "inactivo"):
            with self.subTest(estado=estado):
                otro = crear_sector(self.invernadero, f"X-{estado}", estado=estado)
                error = error_de(lambda: sectores.volver_a_servicio_sector(self.agronomo, otro.pk))
                self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["sector_no_fuera_de_servicio"])

    def test_regla_5_reactivar_solo_vale_para_un_sector_dado_de_baja(self):
        """Un sector activo o fuera de servicio no se reactiva."""
        for estado in ("activo", "fuera_de_servicio"):
            with self.subTest(estado=estado):
                otro = crear_sector(self.invernadero, f"Y-{estado}", estado=estado)
                error = error_de(lambda: sectores.reactivar_sector(self.agronomo, otro.pk))
                self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["sector_no_inactivo"])

    def test_regla_3_reactivar_exige_el_invernadero_activo(self):
        """«Cómo se aplica»: la reactivación solo vale con el invernadero activo (``invernadero_inactivo``)."""
        baja = crear_sector(self.invernadero, "C-2", estado="inactivo")
        self.invernadero.estado_invernadero = "inactivo"
        self.invernadero.save()
        error = error_de(lambda: sectores.reactivar_sector(self.agronomo, baja.pk))
        self.assertEqual(codigos_de(error, NON_FIELD_ERRORS), ["invernadero_inactivo"])

    def test_regla_5_el_gerente_y_el_agronomo_ajeno_no_reactivan_ni_vuelven_a_servicio(self):
        """Precondiciones a y b, también para la reactivación y la vuelta a servicio."""
        baja = crear_sector(self.invernadero, "C-2", estado="inactivo")
        fuera = crear_sector(self.invernadero, "C-3", estado="fuera_de_servicio")
        for actor in (crear_gerente(), crear_agronomo(email="otro@infoponia.com")):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    sectores.reactivar_sector(actor, baja.pk)
                with self.assertRaises(PermissionDenied):
                    sectores.volver_a_servicio_sector(actor, fuera.pk)

    # ---- postcondiciones ----

    def test_post_a_se_actualizan_los_datos_indicados(self):
        """PROD-MOD-SCT postcondición a: el nombre, el tipo de etapa o la cantidad total de agujeros."""
        crear_sector(self.invernadero, "C-2", "germinacion")
        self.modificar(nombre="Nuevo", tipo_etapa_id=tipo_etapa("floracion").pk, cant_agujeros_total=250)
        self.sector.refresh_from_db()
        self.assertEqual(
            (self.sector.nombre_sector, self.sector.tipo_etapa.codigo, self.sector.cant_agujeros_total),
            ("Nuevo", "floracion", 250),
        )

    def test_post_b_volver_a_servicio_llama_a_los_registrantes_dentro_de_la_transaccion(self):
        """PROD-MOD-SCT postcondición b: el registro «Fuera de servicio» y la bitácora son de PRD-04, por el punto
        ``registrar_efecto_de_vuelta_a_servicio``; se llama una vez con (actor, sector), ya activo, dentro de la transacción."""
        llamadas = []

        def efecto(actor, sector):
            llamadas.append((actor, sector.pk, sector.estado_sector, connection.in_atomic_block))

        fuera = crear_sector(self.invernadero, "C-2", estado="fuera_de_servicio")
        with con_extension("_VUELTAS_A_SERVICIO", efecto):
            sectores.volver_a_servicio_sector(self.agronomo, fuera.pk)
        self.assertEqual(llamadas, [(self.agronomo, fuera.pk, "activo", True)])

    def test_post_b_si_un_registrante_falla_el_sector_sigue_fuera_de_servicio(self):
        """D-22: todo o nada; si el efecto falla, no queda el cambio de estado ni el registro de auditoría."""

        def falla(actor, sector):
            raise RuntimeError("falla de prueba")

        fuera = crear_sector(self.invernadero, "C-2", estado="fuera_de_servicio")
        with con_extension("_VUELTAS_A_SERVICIO", falla), self.assertRaises(RuntimeError):
            sectores.volver_a_servicio_sector(self.agronomo, fuera.pk)
        fuera.refresh_from_db()
        self.assertEqual(fuera.estado_sector, "fuera_de_servicio")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_post_c_reactivar_deja_el_sector_activo_y_audita_la_reactivacion(self):
        """PROD-MOD-SCT postcondición c y d: acción ``reactivacion_sector`` con el cambio de estado."""
        baja = crear_sector(self.invernadero, "C-2", estado="inactivo")
        sectores.reactivar_sector(self.agronomo, baja.pk)
        registro = RegistroAuditoria.objects.get(accion=REACTIVACION)
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "inactivo", "despues": "activo"})
        self.assertEqual({a["id"] for a in registro.afectados}, {baja.pk, self.invernadero.pk})

    def test_post_d_modificar_audita_solo_los_campos_que_cambiaron(self):
        """PROD-MOD-SCT postcondición d y D-36: usuario, rol, sector y los cambios con antes y después."""
        self.modificar(nombre="Nuevo", cant_agujeros_total=150)
        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertEqual(registro.usuario_id, self.agronomo.pk)
        self.assertEqual(registro.rol, "agronomo")
        self.assertEqual(
            registro.detalle["cambios"],
            {
                "nombre": {"antes": "C-1", "despues": "Nuevo"},
                "cant_agujeros_total": {"antes": 100, "despues": 150},
            },
        )

    def test_post_d_el_cambio_de_tipo_se_audita_con_referencias(self):
        """D-36: el tipo de etapa va como referencia con su texto."""
        crear_sector(self.invernadero, "C-2", "germinacion")
        self.modificar(tipo_etapa_id=tipo_etapa("crecimiento").pk)
        cambio = RegistroAuditoria.objects.get(accion=MODIFICACION).detalle["cambios"]["tipo_etapa"]
        self.assertEqual((cambio["antes"]["texto"], cambio["despues"]["texto"]), ("Germinación", "Crecimiento"))

    def test_post_d_volver_a_servicio_audita_el_cambio_de_estado(self):
        """PROD-MOD-SCT postcondición d: acción ``modificacion_sector`` con ``fuera_de_servicio`` -> ``activo``."""
        fuera = crear_sector(self.invernadero, "C-2", estado="fuera_de_servicio")
        sectores.volver_a_servicio_sector(self.agronomo, fuera.pk)
        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "fuera_de_servicio", "despues": "activo"})

    def test_d28_guardar_sin_cambios_no_escribe_ni_audita(self):
        """D-28: una modificación sin cambios no guarda ni audita."""
        self.modificar()
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_d28_el_nombre_con_espacios_al_borde_no_cuenta_como_cambio(self):
        """El servicio recorta: «  C-1  » es el mismo nombre."""
        self.modificar(nombre="  C-1  ")
        self.assertFalse(RegistroAuditoria.objects.filter(accion=MODIFICACION).exists())

    def test_flujo_principal_modificar_y_volver_a_consultar(self):
        """PROD-MOD-SCT, flujo principal: lo guardado se ve en la consulta."""
        self.modificar(nombre="Nuevo")
        nombres = [s.nombre_sector for s in sectores.consultar_sectores(self.agronomo, self.invernadero.pk)]
        self.assertEqual(nombres, ["Nuevo"])
        self.assertEqual(SectorProduccion.objects.count(), 1)
