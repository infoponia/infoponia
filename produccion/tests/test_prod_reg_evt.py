# Pruebas de PROD-REG-EVT · Registrar Evento (PRD-03, paso 5; docs/casos_de_uso/produccion/bitacora.md, «PROD-REG-EVT · decisiones de aplicación»).
# Se escriben ANTES que el servicio y deben fallar; el estudiante las revisa antes de implementar.
#
# CONTRATO que fijan estas pruebas (produccion/servicios/bitacora.py, nuevo; usa `alcance.py`):
# - datos_de_evento(actor, invernadero_id=None) -> PropuestaDeEvento(invernaderos, invernadero, lotes, sectores): `invernaderos` son los activos del actor
#   (`alcance.invernaderos_del_actor`); `invernadero` es el elegido: el pedido, o el único si hay uno solo (regla 1), o `None`. Con invernadero elegido,
#   `lotes` son los ACTIVOS (`[(lote_id, codigo, variedad)]`) y `sectores` los que no están inactivos, también los fuera de servicio (`[(sector_id, nombre)]`;
#   regla 3). No escribe. `sin_permiso` / `invernadero_inactivo` / `Http404` como `alcance.invernadero_del_actor`.
# - DatosDeEvento(invernadero_id, descripcion, lote_id=None, sector_id=None) y registrar_evento(actor, datos) -> Bitacora (tipo «otro evento», sin hijo).
#
# Códigos y campos de `ErrorDeProduccion`: sin_permiso; invernadero_inactivo; descripcion_obligatoria y descripcion_larga (campo descripcion, 500; regla 2);
# lote_no_activo (campo lote: finalizado o de otro invernadero); sector_no_elegible (campo sector: inactivo o de otro invernadero).
# Bloqueos: cuentas → invernadero → sector (si se eligió; lo pide el orden global: un sector se bloquea antes que un lote) → lote. El sector se bloquea
# con `select_for_update`, no con `bloquear_sectores`, porque este acepta un sector fuera de servicio y aquel lo rechaza.
#
# Una prueba por regla 1 a 7 y por postcondición a y b. No hay alertas ni notificaciones (regla 6).

from decimal import Decimal

from django.http import Http404
from django.test import TestCase
from django.urls import get_resolver
from django.utils import timezone

from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, perezoso
from maestros.models import Alerta, Invernadero, SectorProduccion
from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo, crear_invernadero, crear_sector
from produccion.errores import ErrorDeProduccion
from produccion.models import Bitacora, Lote
from produccion.tests.fabricas import invernadero_con_produccion, lote_activo

bitacora = perezoso("produccion.servicios.bitacora")

HOY = timezone.localdate()


def rechazo(llamada):
    """Ejecuta `llamada()` y devuelve el `ErrorDeProduccion` que lanza; si no lanza ninguno, la prueba falla."""
    try:
        llamada()
    except ErrorDeProduccion as error:
        return error
    raise AssertionError("Se esperaba un ErrorDeProduccion y no se lanzó ninguno.")


class Base(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()
        cls.lote = lote_activo(cls.e, cantidad=30, sector="germinacion")

    def datos(self, descripcion="Corte de energía de 40 minutos", **cambios):
        base = dict(invernadero_id=self.e.invernadero.pk, descripcion=descripcion)
        base.update(cambios)
        return bitacora.DatosDeEvento(**base)

    def registrar(self, actor=None, **cambios):
        return bitacora.registrar_evento(actor or self.e.capataz, self.datos(**cambios))

    def nada_se_escribio(self):
        self.assertFalse(Bitacora.objects.filter(tipo_evento="otro_evento").exists())
        self.assertFalse(RegistroAuditoria.objects.filter(accion="registro_evento").exists())


class DatosDeEventoTests(Base):
    def test_regla_1_con_un_solo_invernadero_viene_elegido(self):
        """Regla 1: el invernadero se elige entre los activos del actor; si hay uno solo, viene elegido."""
        propuesta = bitacora.datos_de_evento(self.e.capataz)
        self.assertEqual([i.pk for i in propuesta.invernaderos], [self.e.invernadero.pk])
        self.assertEqual(propuesta.invernadero.pk, self.e.invernadero.pk)

    def test_regla_1_con_varios_invernaderos_no_se_elige_ninguno_hasta_que_se_pide(self):
        """Regla 1: con más de uno, el Sistema no elige; con el pedido, trae lotes y sectores de ese."""
        otro = crear_invernadero("Otro", agronomo=self.e.agronomo)
        propuesta = bitacora.datos_de_evento(self.e.agronomo)
        self.assertEqual({i.pk for i in propuesta.invernaderos}, {self.e.invernadero.pk, otro.pk})
        self.assertIsNone(propuesta.invernadero)
        self.assertEqual((propuesta.lotes, propuesta.sectores), ([], []))
        elegido = bitacora.datos_de_evento(self.e.agronomo, otro.pk)
        self.assertEqual(elegido.invernadero.pk, otro.pk)

    def test_regla_3_ofrece_los_lotes_activos_y_los_sectores_no_inactivos_incluidos_los_fuera_de_servicio(self):
        """Regla 3: el lote se elige entre los activos del invernadero; el sector, entre los que no están inactivos (puede ser uno fuera de servicio)."""
        terminado = lote_activo(self.e, cantidad=10, sector="crecimiento")
        Lote.objects.filter(pk=terminado.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)
        fuera = self.e.sectores["maduracion"]
        SectorProduccion.objects.filter(pk=fuera.pk).update(estado_sector="fuera_de_servicio")
        inactivo = crear_sector(self.e.invernadero, nombre="Baja", tipo="germinacion", estado="inactivo")
        propuesta = bitacora.datos_de_evento(self.e.capataz, self.e.invernadero.pk)
        self.assertEqual([l[0] for l in propuesta.lotes], [self.lote.pk])
        sectores = {s[0] for s in propuesta.sectores}
        self.assertIn(fuera.pk, sectores)
        self.assertNotIn(inactivo.pk, sectores)

    def test_regla_1_invernadero_ajeno_inactivo_o_inexistente_y_cuentas_sin_acceso(self):
        """Regla 1 y precondición a: un invernadero ajeno es `sin_permiso`; uno inactivo, `invernadero_inactivo`; uno inexistente, 404; el Gerente no registra."""
        ajeno = crear_invernadero("Ajeno", agronomo=crear_agronomo(email="otro@infoponia.com"))
        self.assertEqual(rechazo(lambda: bitacora.datos_de_evento(self.e.capataz, ajeno.pk)).codigo, "sin_permiso")
        self.assertEqual(rechazo(lambda: bitacora.datos_de_evento(crear_gerente(), self.e.invernadero.pk)).codigo, "sin_permiso")
        with self.assertRaises(Http404):
            bitacora.datos_de_evento(self.e.capataz, 999999)
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(rechazo(lambda: bitacora.datos_de_evento(self.e.capataz, self.e.invernadero.pk)).codigo, "invernadero_inactivo")

    def test_regla_precondicion_b_sin_invernaderos_activos_la_lista_esta_vacia(self):
        """Precondición b: sin ningún invernadero activo a su cargo o asignado, no hay nada que elegir (la pantalla lo informa)."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        propuesta = bitacora.datos_de_evento(self.e.agronomo)
        self.assertEqual((propuesta.invernaderos, propuesta.invernadero), ([], None))


class RegistrarEventoTests(Base):
    def test_flujo_principal_el_capataz_registra_un_evento_del_invernadero(self):
        """Flujo principal: el evento queda registrado y se devuelve el registro de bitácora."""
        evento = self.registrar()
        self.assertIsInstance(evento, Bitacora)
        self.assertEqual(Bitacora.objects.get(tipo_evento="otro_evento").pk, evento.pk)

    def test_post_a_el_evento_es_de_tipo_otro_evento_con_fecha_hora_descripcion_y_responsable_actuales(self):
        """Postcondición a y regla 4: tipo «otro evento», la fecha y la hora actuales (nunca retroactivas), la descripción y el actor como responsable;
        asociado al invernadero y, como no se indicaron, sin lote ni sector."""
        antes = timezone.localtime().time()
        evento = self.registrar(descripcion="  Corte de energía  ")
        despues = timezone.localtime().time()
        guardado = Bitacora.objects.get(pk=evento.pk)
        self.assertEqual((guardado.tipo_evento, guardado.descripcion_evento), ("otro_evento", "Corte de energía"))
        self.assertEqual((guardado.responsable_id, guardado.fecha_bitacora, guardado.invernadero_id), (self.e.capataz.pk, HOY, self.e.invernadero.pk))
        self.assertTrue(antes <= guardado.hora_bitacora <= despues)
        self.assertEqual((guardado.lote_id, guardado.sectores.count()), (None, 0))

    def test_post_a_el_agronomo_tambien_registra_y_queda_como_responsable(self):
        """Actores: Agrónomo y Capataz. Con el Agrónomo, él es el responsable."""
        evento = self.registrar(actor=self.e.agronomo)
        self.assertEqual(Bitacora.objects.get(pk=evento.pk).responsable_id, self.e.agronomo.pk)

    def test_regla_3_con_lote_y_sector_opcionales_y_sin_exigir_que_el_lote_este_en_el_sector(self):
        """Regla 3: se asocian al lote activo y a un solo sector; no se exige que el lote esté en ese sector (el lote está en germinación; el sector es otro)."""
        sector = self.e.sectores["maduracion"]
        evento = self.registrar(lote_id=self.lote.pk, sector_id=sector.pk)
        guardado = Bitacora.objects.get(pk=evento.pk)
        self.assertEqual(guardado.lote_id, self.lote.pk)
        self.assertEqual([s.pk for s in guardado.sectores.all()], [sector.pk])

    def test_regla_3_un_sector_fuera_de_servicio_se_acepta(self):
        """Regla 3 y decisión de aplicación: el sector puede ser uno fuera de servicio (solo los inactivos se rechazan)."""
        fuera = self.e.sectores["maduracion"]
        SectorProduccion.objects.filter(pk=fuera.pk).update(estado_sector="fuera_de_servicio")
        evento = self.registrar(sector_id=fuera.pk)
        self.assertEqual([s.pk for s in Bitacora.objects.get(pk=evento.pk).sectores.all()], [fuera.pk])

    def test_regla_3_un_sector_inactivo_o_de_otro_invernadero_se_rechaza(self):
        """Regla 3: el sector se elige entre los del invernadero que no estén inactivos."""
        inactivo = crear_sector(self.e.invernadero, nombre="Baja", tipo="germinacion", estado="inactivo")
        ajeno = crear_sector(crear_invernadero("Otro", agronomo=self.e.agronomo), nombre="Ajeno", tipo="germinacion")
        for sector in (inactivo, ajeno):
            error = rechazo(lambda: self.registrar(sector_id=sector.pk))
            self.assertEqual((error.codigo, error.campo), ("sector_no_elegible", "sector"))
        self.nada_se_escribio()

    def test_regla_3_un_lote_finalizado_o_de_otro_invernadero_se_rechaza(self):
        """Regla 3: el lote se elige entre los lotes ACTIVOS del invernadero."""
        terminado = lote_activo(self.e, cantidad=10, sector="crecimiento")
        Lote.objects.filter(pk=terminado.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)
        otro = invernadero_con_produccion("Otro Invernadero", sufijo="2")
        de_otro = lote_activo(otro, cantidad=10)
        for lote in (terminado, de_otro):
            error = rechazo(lambda: self.registrar(lote_id=lote.pk))
            self.assertEqual((error.codigo, error.campo), ("lote_no_activo", "lote"))
        self.nada_se_escribio()

    def test_regla_2_la_descripcion_es_obligatoria(self):
        """Regla 2: la descripción es obligatoria: vacía o solo espacios, error en el campo."""
        for vacia in ("", "   "):
            error = rechazo(lambda: self.registrar(descripcion=vacia))
            self.assertEqual((error.codigo, error.campo), ("descripcion_obligatoria", "descripcion"))
        self.nada_se_escribio()

    def test_regla_2_la_descripcion_admite_hasta_500_caracteres(self):
        """Regla 2: hasta 500 caracteres; con 501, error."""
        self.registrar(descripcion="a" * 500)
        error = rechazo(lambda: self.registrar(descripcion="a" * 501))
        self.assertEqual((error.codigo, error.campo), ("descripcion_larga", "descripcion"))
        self.assertEqual(Bitacora.objects.filter(tipo_evento="otro_evento").count(), 1)

    def test_regla_1_un_capataz_ajeno_un_agronomo_ajeno_el_gerente_y_una_cuenta_inactiva_se_rechazan(self):
        """Precondición a y regla 1: solo el Capataz que abarca el invernadero y el Agrónomo a cargo, con la cuenta activa."""
        gerente = crear_gerente()
        for actor in (crear_capataz_activo(email="ajeno@infoponia.com"), crear_agronomo(email="otro@infoponia.com"), gerente):
            self.assertEqual(rechazo(lambda: self.registrar(actor=actor)).codigo, "sin_permiso")
        capataz = self.e.capataz
        capataz.is_active = False
        capataz.save()
        self.assertEqual(rechazo(lambda: self.registrar(actor=capataz)).codigo, "sin_permiso")
        self.nada_se_escribio()

    def test_regla_1_un_invernadero_inactivo_se_rechaza(self):
        """Precondición b y regla 4 de PROD-BAJ-INV: un invernadero inactivo no admite operaciones nuevas."""
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(rechazo(lambda: self.registrar()).codigo, "invernadero_inactivo")
        self.nada_se_escribio()

    def test_regla_6_no_genera_alertas_ni_notificaciones(self):
        """Regla 6: el registro no genera alertas ni notificaciones."""
        self.registrar(lote_id=self.lote.pk)
        self.assertEqual((Alerta.objects.count(), Notificacion.objects.count()), (0, 0))

    def test_post_b_un_solo_registro_de_auditoria_con_quien_actuo_y_el_identificador_del_registro(self):
        """Postcondición b y D-36: UN registro `registro_evento` con el usuario, el registro de bitácora y, si se indicaron, el lote y el sector."""
        sector = self.e.sectores["maduracion"]
        evento = self.registrar(lote_id=self.lote.pk, sector_id=sector.pk)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="registro_evento").count(), 1)
        registro = RegistroAuditoria.objects.get(accion="registro_evento")
        self.assertEqual(registro.usuario_id, self.e.capataz.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        self.assertTrue({("produccion.bitacora", evento.pk), ("produccion.lote", self.lote.pk), ("maestros.sectorproduccion", sector.pk)} <= afectados)
        self.assertEqual(registro.detalle["cambios"]["descripcion_evento"]["despues"], "Corte de energía de 40 minutos")

    def test_post_b_la_lectura_no_audita(self):
        """D-36: `datos_de_evento` no escribe auditoría."""
        bitacora.datos_de_evento(self.e.capataz, self.e.invernadero.pk)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="registro_evento").exists())

    def test_regla_5_un_registro_de_bitacora_no_se_modifica_ni_se_elimina_no_hay_servicio_ni_vista_que_lo_haga(self):
        """Regla 5: un registro de bitácora no se modifica ni se elimina. No existe ningún servicio de `bitacora` que lo haga y ninguna ruta de la
        aplicación edita o borra un registro de bitácora (si hay un error, se registra otro evento que lo aclare)."""
        modulos = [n for n in dir(bitacora) if not n.startswith("_")]
        for nombre in modulos:
            self.assertFalse(any(v in nombre for v in ("modificar", "editar", "eliminar", "borrar", "baja", "anular")), nombre)

        def nombres(patrones, prefijo=""):
            for patron in patrones:
                if hasattr(patron, "url_patterns"):
                    yield from nombres(patron.url_patterns, prefijo + str(patron.pattern))
                else:
                    yield f"{prefijo}{patron.pattern}", getattr(patron, "name", None) or ""

        for ruta, nombre in nombres(get_resolver().url_patterns):
            if "bitacora" in ruta.lower() or "evento" in ruta.lower() or "bitacora" in nombre or "evento" in nombre:
                self.assertFalse(any(v in (ruta + nombre).lower() for v in ("editar", "modificar", "eliminar", "borrar", "baja")), (ruta, nombre))

    def test_regla_todo_o_nada_un_error_de_validacion_no_deja_nada(self):
        """Todo o nada: un lote inválido junto con un sector válido no deja ni el registro ni la auditoría."""
        otro = invernadero_con_produccion("Otro Invernadero", sufijo="2")
        error = rechazo(lambda: self.registrar(lote_id=lote_activo(otro, cantidad=10).pk, sector_id=self.e.sectores["maduracion"].pk))
        self.assertEqual(error.codigo, "lote_no_activo")
        self.nada_se_escribio()
