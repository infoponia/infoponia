# Pruebas de PROD-MOD-INV · Modificar Invernadero, la parte de los transportistas (MAE-05, D-55; docs/casos_de_uso/maestros/
# invernaderos.md: postcondición g y reglas 8 a 11 *(MAE-05)*) y de lo que cita: D-22 y D-36 (auditoría en la misma
# transacción, con el formato de «cambios»), D-39 (los inactivos no cuentan), D-40 (orden de bloqueos), D-42 (notificaciones)
# y la regla 5 de PROD-MOD-INV (un invernadero inactivo no se modifica).
#
# Servicios que se prueban (maestros/servicios/transportistas.py), tomados del módulo dentro de cada prueba (``servicio()``):
#   candidatos(actor, invernadero_id) -> list[Candidato(transportista, invernadero)]
#     Regla 8: los Transportistas ACTIVOS que no trabajan para ese invernadero, cada uno con su invernadero actual o ``None``.
#     Sin invernadero primero; después por nombre del invernadero y por apellido y nombre. Solo lectura. Gerente activo
#     (PermissionDenied); invernadero inexistente (Http404); inactivo (error general ``invernadero_inactivo``).
#   agregar_transportista(actor, invernadero_id, transportista_id, *, traslado_confirmado=False) -> TransportistaInvernadero
#     Rechazos (ValidationError general, con código): ``transportista_inactivo``, ``ya_pertenece``, ``invernadero_inactivo``.
#     Un id que no es de un Transportista -> Http404. Un traslado sin confirmar lanza ``FaltaConfirmarTraslado`` (con
#     ``.origen``, el invernadero de origen) y no cambia nada; confirmado, pide ``impedimentos_de_transportista`` y, si hay
#     alguno, rechaza con SUS códigos (reglas 9 y 10) sin cambiar nada.
#   quitar_transportista(actor, invernadero_id, transportista_id) -> Transportista
#     Rechazos: ``invernadero_inactivo`` (regla 5), ``no_pertenece`` y los códigos de los impedimentos. Un Transportista
#     inactivo se puede quitar (los impedimentos se piden igual).
#   impedimentos_para_quitar(actor, invernadero_id, transportista_id) -> list[Impedimento]  (solo lectura, para la ventana)
# Los impedimentos de las reglas 9 y 10 los registra `comercial`: acá, con registrantes falsos
# (``con_extension("_IMPEDIMENTOS_DE_TRANSPORTISTA", ...)``).

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase

from core.models import Notificacion, RegistroAuditoria, referencia
from core.tests.fabricas import afectado, crear_gerente
from maestros.extensiones import Impedimento
from maestros.models import Alerta, Invernadero, TransportistaInvernadero
from maestros.tests.fabricas import (
    ConGeoref,
    asignar_transportista,
    codigos_de,
    con_extension,
    crear_agronomo,
    crear_invernadero,
    crear_transportista,
    error_de,
)

MODIFICACION = RegistroAuditoria.Accion.MODIFICACION_INVERNADERO

EN_RUTA = Impedimento("transportista_en_ruta", "Está en ruta.", "Esperá a que finalice la ruta.")
CON_ENTREGAS = Impedimento("transportista_con_entregas", "Tiene 2 entregas a realizar.", "Reasignalas antes.")


def servicio():
    """El módulo de servicios de transportistas (se importa acá para que cada prueba falle sola mientras no exista)."""
    from maestros.servicios import transportistas

    return transportistas


def registrante_falso(*impedimentos):
    """Un registrante de ``impedimentos_de_transportista`` que devuelve siempre ``impedimentos``; anota a quién se lo
    preguntaron en ``.preguntados``."""

    def registrante(transportista):
        registrante.preguntados.append(transportista.pk)
        return list(impedimentos)

    registrante.preguntados = []
    return registrante


class TransportistasBase(ConGeoref, TestCase):
    """Un Gerente, dos invernaderos activos y dos Transportistas activos sin invernadero."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.norte = crear_invernadero("Norte")
        self.sur = crear_invernadero("Sur")
        self.diego = crear_transportista("diego@infoponia.com", nombre="Diego", apellido="Ferreyra")
        self.carla = crear_transportista("carla@infoponia.com", nombre="Carla", apellido="Sosa")

    def foto(self):
        """Todo lo que un rechazo no puede cambiar: las filas, los registros de auditoría y las notificaciones."""
        return (
            sorted(TransportistaInvernadero.objects.values_list("transportista_id", "invernadero_id", "desde")),
            RegistroAuditoria.objects.count(),
            Notificacion.objects.count(),
        )

    def auditoria_de(self, invernadero):
        """Los registros ``modificacion_invernadero`` en los que figura ``invernadero`` entre los afectados."""
        return RegistroAuditoria.objects.filter(
            accion=MODIFICACION, afectados__contains=[{"modelo": "maestros.invernadero", "id": invernadero.pk}]
        )

    def fila(self, transportista):
        return TransportistaInvernadero.objects.filter(transportista_id=transportista.pk).first()


class CandidatosTests(TransportistasBase):
    """Regla 8: a quién se ofrece."""

    def test_regla_8_ofrece_los_activos_sin_invernadero_y_los_de_otros_con_su_invernadero(self):
        """PROD-MOD-INV regla 8: se ofrecen los activos que no trabajan para este invernadero (los sin invernadero y los
        de otros, mostrando a cuál pertenecen); sin invernadero primero, después por invernadero y por nombre."""
        ana = crear_transportista("ana@infoponia.com", nombre="Ana", apellido="Álvarez")
        asignar_transportista(self.carla, self.sur)
        asignar_transportista(ana, self.sur)

        lista = servicio().candidatos(self.gerente, self.norte.pk)

        self.assertEqual(
            [(c.transportista.pk, c.invernadero.pk if c.invernadero else None) for c in lista],
            [(self.diego.pk, None), (ana.pk, self.sur.pk), (self.carla.pk, self.sur.pk)],
        )

    def test_regla_8_no_ofrece_a_los_inactivos_ni_a_los_que_ya_trabajan_para_este_invernadero(self):
        """PROD-MOD-INV regla 8 y nota «Cómo se aplica»: un inactivo no se ofrece para agregar; tampoco quien ya es de este
        invernadero."""
        crear_transportista("inactivo@infoponia.com", activo=False)
        asignar_transportista(self.carla, self.norte)

        lista = servicio().candidatos(self.gerente, self.norte.pk)

        self.assertEqual([c.transportista.pk for c in lista], [self.diego.pk])

    def test_regla_8_solo_un_gerente_activo_consulta_los_candidatos(self):
        """PROD-MOD-INV precondición a: el Agrónomo y un Gerente inactivo no consultan (SEG-13)."""
        with self.assertRaises(PermissionDenied):
            servicio().candidatos(crear_agronomo(), self.norte.pk)
        with self.assertRaises(PermissionDenied):
            servicio().candidatos(crear_gerente("viejo@infoponia.com", activo=False), self.norte.pk)

    def test_regla_8_un_invernadero_inactivo_no_ofrece_candidatos(self):
        """PROD-MOD-INV regla 5: uno inactivo no se modifica; también se rechaza la consulta (``invernadero_inactivo``)."""
        inactivo = crear_invernadero("Este", activo=False)
        error = error_de(lambda: servicio().candidatos(self.gerente, inactivo.pk))
        self.assertEqual(codigos_de(error), ["invernadero_inactivo"])

    def test_regla_8_un_invernadero_inexistente_da_404(self):
        """D-28: un id inexistente da 404."""
        with self.assertRaises(Http404):
            servicio().candidatos(self.gerente, self.norte.pk + 1000)


class AgregarTransportistaTests(TransportistasBase):
    """Regla 8 y postcondición g: agregar a quien no tiene invernadero, rechazos y quién puede hacerlo."""

    def agregar(self, transportista=None, invernadero=None, **extra):
        return servicio().agregar_transportista(
            self.gerente, (invernadero or self.norte).pk, (transportista or self.diego).pk, **extra
        )

    def test_post_g_agregar_a_uno_sin_invernadero_crea_la_fila_con_desde(self):
        """PROD-MOD-INV postcondición g: el Transportista agregado queda asociado al invernadero (R155), con ``desde``."""
        fila = self.agregar()

        self.assertEqual((fila.transportista_id, fila.invernadero_id), (self.diego.pk, self.norte.pk))
        self.assertIsNotNone(self.fila(self.diego).desde)
        self.assertEqual([t.pk for t in self.norte.transportistas()], [self.diego.pk])

    def test_post_g_agregar_notifica_al_transportista_con_el_texto_aprobado(self):
        """PROD-MOD-INV postcondición g: el agregado recibe una notificación («Trabajás para {invernadero}»)."""
        self.agregar()

        notificacion = Notificacion.objects.get()
        self.assertEqual(notificacion.destinatario_id, self.diego.pk)
        self.assertEqual(notificacion.titulo, "Trabajás para Norte")
        self.assertEqual(notificacion.detalle, "Desde ahora podés recibir entregas de Norte.")

    def test_post_g_agregar_audita_un_registro_con_el_antes_y_el_despues(self):
        """PROD-MOD-INV postcondición g y f, D-36: un ``modificacion_invernadero`` con los afectados (el invernadero y la
        cuenta) y ``cambios.transportistas`` con la lista de referencias antes y después."""
        self.agregar()

        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual(
            registro.afectados,
            [{"modelo": "maestros.invernadero", "id": self.norte.pk, "texto": "Norte"}, afectado(self.diego)],
        )
        self.assertEqual(
            registro.detalle,
            {"cambios": {"transportistas": {"antes": [], "despues": [referencia(self.diego)]}}},
        )

    def test_post_g_agregar_a_uno_con_otros_deja_la_lista_completa_en_el_registro(self):
        """D-36: «antes» y «despues» son las listas completas de transportistas del invernadero, por apellido y nombre."""
        asignar_transportista(self.carla, self.norte)

        self.agregar()

        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertEqual(
            registro.detalle["cambios"]["transportistas"],
            {"antes": [referencia(self.carla)], "despues": [referencia(self.diego), referencia(self.carla)]},
        )

    def test_regla_8_agregar_a_uno_inactivo_se_rechaza_y_no_cambia_nada(self):
        """PROD-MOD-INV regla 8: solo se agrega a los activos (``transportista_inactivo``)."""
        inactivo = crear_transportista("inactivo@infoponia.com", activo=False)
        antes = self.foto()

        error = error_de(lambda: self.agregar(inactivo))

        self.assertEqual(codigos_de(error), ["transportista_inactivo"])
        self.assertEqual(self.foto(), antes)

    def test_regla_8_agregar_a_quien_ya_trabaja_para_ese_invernadero_se_rechaza(self):
        """PROD-MOD-INV regla 8: no se agrega a quien ya es del invernadero (``ya_pertenece``)."""
        asignar_transportista(self.diego, self.norte)
        antes = self.foto()

        error = error_de(lambda: self.agregar())

        self.assertEqual(codigos_de(error), ["ya_pertenece"])
        self.assertEqual(self.foto(), antes)

    def test_regla_5_agregar_a_un_invernadero_inactivo_se_rechaza(self):
        """PROD-MOD-INV regla 5: un invernadero inactivo no se modifica (``invernadero_inactivo``)."""
        inactivo = crear_invernadero("Este", activo=False)
        antes = self.foto()

        error = error_de(lambda: self.agregar(invernadero=inactivo))

        self.assertEqual(codigos_de(error), ["invernadero_inactivo"])
        self.assertEqual(self.foto(), antes)

    def test_regla_8_agregar_un_id_que_no_es_de_un_transportista_da_404(self):
        """Regla 8: solo los Transportistas se agregan; una cuenta de otro rol (o un id inexistente) da 404."""
        agronomo = crear_agronomo()
        with self.assertRaises(Http404):
            servicio().agregar_transportista(self.gerente, self.norte.pk, agronomo.pk)
        with self.assertRaises(Http404):
            servicio().agregar_transportista(self.gerente, self.norte.pk, self.diego.pk + 1000)
        with self.assertRaises(Http404):
            servicio().agregar_transportista(self.gerente, self.norte.pk + 1000, self.diego.pk)

    def test_pre_a_ni_el_agronomo_ni_un_gerente_inactivo_agregan(self):
        """PROD-MOD-INV precondición a: solo un Gerente activo (SEG-13)."""
        antes = self.foto()
        for actor in (crear_agronomo(), crear_gerente("viejo@infoponia.com", activo=False)):
            with self.assertRaises(PermissionDenied):
                servicio().agregar_transportista(actor, self.norte.pk, self.diego.pk)
        self.assertEqual(self.foto(), antes)

    def test_regla_11_agregar_no_toca_nada_mas(self):
        """PROD-MOD-INV regla 11: agregar solo crea la fila: no cambia el invernadero ni su personal, ni la cuenta, ni las
        filas de los demás, ni crea alertas."""
        agronomo = crear_agronomo()
        norte = crear_invernadero("Norte 2", agronomo=agronomo)
        asignar_transportista(self.carla, self.sur)
        antes = (
            Invernadero.objects.filter(pk=norte.pk).values().get(),
            self.fila(self.carla).invernadero_id,
            Alerta.objects.count(),
            self.diego.__class__.objects.filter(pk=self.diego.pk).values().get(),
        )

        self.agregar(invernadero=norte)

        self.assertEqual(
            (
                Invernadero.objects.filter(pk=norte.pk).values().get(),
                self.fila(self.carla).invernadero_id,
                Alerta.objects.count(),
                self.diego.__class__.objects.filter(pk=self.diego.pk).values().get(),
            ),
            antes,
        )

    def test_regla_9_agregar_a_uno_sin_invernadero_no_pide_impedimentos(self):
        """Reglas 9 y 10 (D-55, punto 4): los impedimentos solo cuentan al quitar o trasladar; quien no tiene invernadero no
        deja nada atrás."""
        registrante = registrante_falso(EN_RUTA)
        with con_extension("_IMPEDIMENTOS_DE_TRANSPORTISTA", registrante):
            self.agregar()
        self.assertEqual(registrante.preguntados, [])
        self.assertEqual(self.fila(self.diego).invernadero_id, self.norte.pk)


class TrasladoTests(TransportistasBase):
    """Reglas 8, 9 y 10 y postcondición g: pasar a un Transportista de un invernadero a otro."""

    def setUp(self):
        super().setUp()
        asignar_transportista(self.diego, self.sur)

    def trasladar(self, **extra):
        return servicio().agregar_transportista(self.gerente, self.norte.pk, self.diego.pk, **extra)

    def test_regla_8_un_traslado_sin_confirmar_avisa_del_origen_y_no_cambia_nada(self):
        """PROD-MOD-INV regla 8: elegir a uno de otro invernadero lo traslada y el Sistema lo informa antes de confirmar:
        ``FaltaConfirmarTraslado`` con el origen, sin cambiar nada."""
        antes = self.foto()

        with self.assertRaises(servicio().FaltaConfirmarTraslado) as contexto:
            self.trasladar()

        self.assertEqual(contexto.exception.origen.pk, self.sur.pk)
        self.assertEqual(self.foto(), antes)

    def test_regla_8_un_traslado_sin_confirmar_no_pide_los_impedimentos(self):
        """Regla 8: primero se avisa del traslado; los impedimentos se piden recién al confirmar (reglas 9 y 10)."""
        registrante = registrante_falso(EN_RUTA)
        with con_extension("_IMPEDIMENTOS_DE_TRANSPORTISTA", registrante):
            with self.assertRaises(servicio().FaltaConfirmarTraslado):
                self.trasladar()
        self.assertEqual(registrante.preguntados, [])

    def test_post_g_el_traslado_confirmado_cambia_el_invernadero_y_desde(self):
        """PROD-MOD-INV postcondición g: el trasladado dejó de pertenecer al otro invernadero y quedó asociado al nuevo."""
        desde_antes = self.fila(self.diego).desde

        self.trasladar(traslado_confirmado=True)

        fila = self.fila(self.diego)
        self.assertEqual(fila.invernadero_id, self.norte.pk)
        self.assertGreater(fila.desde, desde_antes)
        self.assertEqual(TransportistaInvernadero.objects.count(), 1)
        self.assertEqual(self.sur.transportistas(), [])

    def test_post_g_el_traslado_notifica_con_el_texto_aprobado(self):
        """PROD-MOD-INV postcondición g: «Te pasaron a {destino}» / «Dejás de trabajar para {origen}. Desde ahora podés
        recibir entregas de {destino}.»"""
        self.trasladar(traslado_confirmado=True)

        notificacion = Notificacion.objects.get()
        self.assertEqual(notificacion.destinatario_id, self.diego.pk)
        self.assertEqual(notificacion.titulo, "Te pasaron a Norte")
        self.assertEqual(
            notificacion.detalle, "Dejás de trabajar para Sur. Desde ahora podés recibir entregas de Norte."
        )

    def test_post_g_un_traslado_deja_dos_registros_de_auditoria_uno_por_invernadero(self):
        """PROD-MOD-INV postcondición g y f: en un traslado cambian dos invernaderos y queda un log en cada uno, con las
        listas de transportistas de cada uno."""
        self.trasladar(traslado_confirmado=True)

        self.assertEqual(RegistroAuditoria.objects.filter(accion=MODIFICACION).count(), 2)
        destino = self.auditoria_de(self.norte).get()
        origen = self.auditoria_de(self.sur).get()
        self.assertEqual(
            destino.detalle["cambios"]["transportistas"], {"antes": [], "despues": [referencia(self.diego)]}
        )
        self.assertEqual(
            origen.detalle["cambios"]["transportistas"], {"antes": [referencia(self.diego)], "despues": []}
        )
        for registro, invernadero in ((destino, self.norte), (origen, self.sur)):
            self.assertEqual(registro.afectados[0]["id"], invernadero.pk)
            self.assertIn(afectado(self.diego), registro.afectados)

    def test_regla_9_un_traslado_con_entregas_a_realizar_se_rechaza_y_no_cambia_nada(self):
        """PROD-MOD-INV regla 9: no se traslada a un Transportista con entregas a realizar; el rechazo lleva el código del
        registrante (los registra `comercial`)."""
        antes = self.foto()
        with con_extension("_IMPEDIMENTOS_DE_TRANSPORTISTA", registrante_falso(CON_ENTREGAS)):
            error = error_de(lambda: self.trasladar(traslado_confirmado=True))

        self.assertEqual(codigos_de(error), ["transportista_con_entregas"])
        self.assertEqual(self.foto(), antes)

    def test_regla_10_un_traslado_de_quien_esta_en_ruta_se_rechaza_y_no_cambia_nada(self):
        """PROD-MOD-INV regla 10: no se traslada a un Transportista en ruta."""
        antes = self.foto()
        with con_extension("_IMPEDIMENTOS_DE_TRANSPORTISTA", registrante_falso(EN_RUTA)):
            error = error_de(lambda: self.trasladar(traslado_confirmado=True))

        self.assertEqual(codigos_de(error), ["transportista_en_ruta"])
        self.assertEqual(self.foto(), antes)

    def test_regla_9_los_impedimentos_de_todos_los_registrantes_van_juntos(self):
        """Regla 2 de PROD-BAJ-INV aplicada acá: se informan todos, sin quedarse con el primero."""
        with con_extension(
            "_IMPEDIMENTOS_DE_TRANSPORTISTA", registrante_falso(EN_RUTA), registrante_falso(CON_ENTREGAS)
        ):
            error = error_de(lambda: self.trasladar(traslado_confirmado=True))
        self.assertEqual(codigos_de(error), ["transportista_en_ruta", "transportista_con_entregas"])

    def test_regla_9_sin_registrantes_el_traslado_no_se_bloquea(self):
        """D-55, punto 4: mientras `comercial` no exista, no hay entregas ni rutas y nada bloquea."""
        with con_extension("_IMPEDIMENTOS_DE_TRANSPORTISTA"):
            self.trasladar(traslado_confirmado=True)
        self.assertEqual(self.fila(self.diego).invernadero_id, self.norte.pk)

    def test_regla_8_se_puede_sacar_a_un_transportista_de_un_invernadero_inactivo(self):
        """Regla 8 y D-39: el origen no pide estar activo; un invernadero dado de baja que conserva a un Transportista (cuenta
        reactivada después) no lo retiene. Solo el destino tiene que estar activo."""
        Invernadero.objects.filter(pk=self.sur.pk).update(estado_invernadero="inactivo")

        self.trasladar(traslado_confirmado=True)

        self.assertEqual(self.fila(self.diego).invernadero_id, self.norte.pk)
        self.assertEqual(self.auditoria_de(self.sur).count(), 1)

    def test_regla_5_no_se_traslada_a_un_invernadero_inactivo(self):
        """PROD-MOD-INV regla 5: el destino tiene que estar activo (``invernadero_inactivo``)."""
        Invernadero.objects.filter(pk=self.norte.pk).update(estado_invernadero="inactivo")
        antes = self.foto()

        error = error_de(lambda: self.trasladar(traslado_confirmado=True))

        self.assertEqual(codigos_de(error), ["invernadero_inactivo"])
        self.assertEqual(self.foto(), antes)

    def test_regla_8_confirmar_el_traslado_a_donde_ya_trabaja_se_rechaza(self):
        """Regla 8: ``ya_pertenece`` también vale con el traslado confirmado."""
        error = error_de(
            lambda: servicio().agregar_transportista(self.gerente, self.sur.pk, self.diego.pk, traslado_confirmado=True)
        )
        self.assertEqual(codigos_de(error), ["ya_pertenece"])


class QuitarTransportistaTests(TransportistasBase):
    """Reglas 5, 9 y 10 y postcondición g: quitar."""

    def setUp(self):
        super().setUp()
        asignar_transportista(self.diego, self.norte)
        asignar_transportista(self.carla, self.norte)
        Notificacion.objects.all().delete()

    def quitar(self, transportista=None, invernadero=None):
        return servicio().quitar_transportista(
            self.gerente, (invernadero or self.norte).pk, (transportista or self.diego).pk
        )

    def test_post_g_quitar_borra_la_fila_y_deja_al_transportista_sin_invernadero(self):
        """PROD-MOD-INV postcondición g: el quitado quedó sin invernadero; los demás siguen."""
        self.quitar()

        self.assertIsNone(self.fila(self.diego))
        self.assertEqual([t.pk for t in self.norte.transportistas()], [self.carla.pk])

    def test_post_g_quitar_notifica_con_el_texto_aprobado(self):
        """PROD-MOD-INV postcondición g: «Ya no trabajás para {invernadero}»."""
        self.quitar()

        notificacion = Notificacion.objects.get()
        self.assertEqual(notificacion.destinatario_id, self.diego.pk)
        self.assertEqual(notificacion.titulo, "Ya no trabajás para Norte")
        self.assertEqual(
            notificacion.detalle, "No vas a recibir entregas hasta que te agreguen a otro invernadero."
        )

    def test_post_g_quitar_audita_con_el_antes_y_el_despues(self):
        """PROD-MOD-INV postcondición g y f, D-36: ``cambios.transportistas`` con las listas antes y después."""
        self.quitar()

        registro = RegistroAuditoria.objects.get(accion=MODIFICACION)
        self.assertEqual(
            registro.afectados,
            [{"modelo": "maestros.invernadero", "id": self.norte.pk, "texto": "Norte"}, afectado(self.diego)],
        )
        self.assertEqual(
            registro.detalle["cambios"]["transportistas"],
            {"antes": [referencia(self.diego), referencia(self.carla)], "despues": [referencia(self.carla)]},
        )

    def test_regla_9_quitar_con_entregas_a_realizar_se_rechaza_y_no_cambia_nada(self):
        """PROD-MOD-INV regla 9: no se quita a un Transportista con entregas a realizar."""
        antes = self.foto()
        with con_extension("_IMPEDIMENTOS_DE_TRANSPORTISTA", registrante_falso(CON_ENTREGAS)):
            error = error_de(self.quitar)

        self.assertEqual(codigos_de(error), ["transportista_con_entregas"])
        self.assertEqual(self.foto(), antes)

    def test_regla_10_quitar_a_quien_esta_en_ruta_se_rechaza_y_no_cambia_nada(self):
        """PROD-MOD-INV regla 10: no se quita a un Transportista en ruta."""
        antes = self.foto()
        with con_extension("_IMPEDIMENTOS_DE_TRANSPORTISTA", registrante_falso(EN_RUTA)):
            error = error_de(self.quitar)

        self.assertEqual(codigos_de(error), ["transportista_en_ruta"])
        self.assertEqual(self.foto(), antes)

    def test_regla_9_sin_registrantes_quitar_no_se_bloquea(self):
        """D-55, punto 4: sin `comercial` no hay impedimentos."""
        with con_extension("_IMPEDIMENTOS_DE_TRANSPORTISTA"):
            self.quitar()
        self.assertIsNone(self.fila(self.diego))

    def test_regla_9_un_transportista_inactivo_se_puede_quitar_pero_se_piden_los_impedimentos(self):
        """Nota «Cómo se aplica» de PROD-MOD-INV y D-55 (punto 8): un inactivo vinculado se puede quitar; los impedimentos
        se piden igual."""
        from core.models import Usuario

        Usuario.objects.filter(pk=self.diego.pk).update(is_active=False)
        registrante = registrante_falso()
        with con_extension("_IMPEDIMENTOS_DE_TRANSPORTISTA", registrante):
            self.quitar()

        self.assertIsNone(self.fila(self.diego))
        self.assertEqual(registrante.preguntados, [self.diego.pk])

    def test_regla_5_no_se_quita_en_un_invernadero_inactivo(self):
        """PROD-MOD-INV regla 5: un invernadero inactivo no se modifica (``invernadero_inactivo``)."""
        Invernadero.objects.filter(pk=self.norte.pk).update(estado_invernadero="inactivo")
        antes = self.foto()

        error = error_de(self.quitar)

        self.assertEqual(codigos_de(error), ["invernadero_inactivo"])
        self.assertEqual(self.foto(), antes)

    def test_regla_8_no_se_quita_a_quien_no_trabaja_para_ese_invernadero(self):
        """Postcondición g: solo se quita a quien pertenece al invernadero (``no_pertenece``), sea de otro o de ninguno."""
        asignar_transportista(crear_transportista("otro@infoponia.com"), self.sur)
        sin_invernadero = crear_transportista("libre@infoponia.com")
        antes = self.foto()

        for transportista, invernadero in ((sin_invernadero, self.norte), (self.diego, self.sur)):
            error = error_de(lambda: self.quitar(transportista, invernadero))
            self.assertEqual(codigos_de(error), ["no_pertenece"])
        self.assertEqual(self.foto(), antes)

    def test_pre_a_ni_el_agronomo_ni_un_gerente_inactivo_quitan(self):
        """PROD-MOD-INV precondición a: solo un Gerente activo (SEG-13)."""
        antes = self.foto()
        for actor in (crear_agronomo(), crear_gerente("viejo@infoponia.com", activo=False)):
            with self.assertRaises(PermissionDenied):
                servicio().quitar_transportista(actor, self.norte.pk, self.diego.pk)
        self.assertEqual(self.foto(), antes)

    def test_regla_8_quitar_un_id_que_no_es_de_un_transportista_da_404(self):
        """Un id de otro rol o inexistente da 404."""
        with self.assertRaises(Http404):
            servicio().quitar_transportista(self.gerente, self.norte.pk, crear_agronomo().pk)
        with self.assertRaises(Http404):
            servicio().quitar_transportista(self.gerente, self.norte.pk + 1000, self.diego.pk)


class ImpedimentosParaQuitarTests(TransportistasBase):
    """La ventana de «Quitar»: solo lectura."""

    def setUp(self):
        super().setUp()
        asignar_transportista(self.diego, self.norte)

    def test_regla_9_la_ventana_informa_todos_los_impedimentos_sin_cambiar_nada(self):
        """Reglas 9 y 10: ``impedimentos_para_quitar`` devuelve los de todos los registrantes y no cambia nada."""
        antes = self.foto()
        with con_extension(
            "_IMPEDIMENTOS_DE_TRANSPORTISTA", registrante_falso(EN_RUTA), registrante_falso(CON_ENTREGAS)
        ):
            impedimentos = servicio().impedimentos_para_quitar(self.gerente, self.norte.pk, self.diego.pk)

        self.assertEqual([i.codigo for i in impedimentos], ["transportista_en_ruta", "transportista_con_entregas"])
        self.assertEqual(self.foto(), antes)

    def test_regla_9_sin_registrantes_no_hay_impedimentos(self):
        """D-55, punto 4: sin registrantes, lista vacía."""
        with con_extension("_IMPEDIMENTOS_DE_TRANSPORTISTA"):
            self.assertEqual(servicio().impedimentos_para_quitar(self.gerente, self.norte.pk, self.diego.pk), [])

    def test_regla_5_un_invernadero_inactivo_o_quien_no_pertenece_se_rechaza(self):
        """Los mismos rechazos que ``quitar_transportista``: ``invernadero_inactivo`` y ``no_pertenece``."""
        error = error_de(lambda: servicio().impedimentos_para_quitar(self.gerente, self.norte.pk, self.carla.pk))
        self.assertEqual(codigos_de(error), ["no_pertenece"])
        Invernadero.objects.filter(pk=self.norte.pk).update(estado_invernadero="inactivo")
        error = error_de(lambda: servicio().impedimentos_para_quitar(self.gerente, self.norte.pk, self.diego.pk))
        self.assertEqual(codigos_de(error), ["invernadero_inactivo"])

    def test_pre_a_solo_un_gerente_activo_consulta(self):
        """PROD-MOD-INV precondición a (SEG-13)."""
        with self.assertRaises(PermissionDenied):
            servicio().impedimentos_para_quitar(crear_agronomo(), self.norte.pk, self.diego.pk)
