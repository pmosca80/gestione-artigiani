import os
from datetime import date as _date_type, datetime as _datetime_type

from sqlalchemy import Boolean, Column, Integer, String, Text, ForeignKey, Float, Date, DateTime, Index, func
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import relationship, declared_attr
from app.database import Base


def _get_fernet():
    key = os.environ.get("FERNET_KEY", "")
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        return None


class FlexDate(TypeDecorator):
    """Colonna DATE che accetta sia stringhe ISO sia oggetti date in scrittura."""
    impl = Date
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if not value:
            return None
        if isinstance(value, _date_type):
            return value
        return _date_type.fromisoformat(str(value)[:10])

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            return _date_type.fromisoformat(value[:10])
        return value


class FlexDateTime(TypeDecorator):
    """Colonna DATETIME che accetta sia stringhe ISO sia oggetti datetime/date in scrittura."""
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if not value:
            return None
        if isinstance(value, _datetime_type):
            return value
        if isinstance(value, _date_type):
            return _datetime_type(value.year, value.month, value.day)
        try:
            return _datetime_type.fromisoformat(str(value).replace(" ", "T")[:26])
        except Exception:
            return None

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, _datetime_type):
            return value
        try:
            return _datetime_type.fromisoformat(str(value).replace(" ", "T")[:26])
        except Exception:
            return value


class EncryptedString(TypeDecorator):
    """Cifra il valore con Fernet (FERNET_KEY env var); fallback plaintext se la chiave manca."""
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if not value:
            return value
        f = _get_fernet()
        if not f:
            return value
        return f.encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if not value:
            return value
        f = _get_fernet()
        if not f:
            return value
        try:
            return f.decrypt(value.encode()).decode()
        except Exception:
            return value  # valore precedente in chiaro: restituito as-is


class TimestampMixin:
    """Aggiunge data_aggiornamento aggiornato automaticamente ad ogni UPDATE ORM."""
    @declared_attr
    def data_aggiornamento(cls):
        return Column(DateTime(timezone=True), nullable=True,
                      server_default=func.now(), onupdate=func.now())


# ========================
# UTENTE
# ========================

class Utente(TimestampMixin, Base):
    __tablename__ = "utenti"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    data_registrazione = Column(FlexDate, nullable=True)
    attivo = Column(Integer, nullable=False, default=1)

    piano = Column(String, nullable=True, default="free")
    pro_scadenza = Column(FlexDate, nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)

    # Promo lancio: primo anno gratis, poi 50% a vita, per i primi 100 che
    # si registrano (flag assegnato una sola volta in fase di registrazione,
    # vedi auth.py). Il primo sconto si applica al checkout; il secondo
    # (post anno gratuito) lo applica il job app/services/fondatore.py,
    # che usa fondatore_sconto_applicato per non ripetere la chiamata Stripe.
    piano_fondatore = Column(Boolean, nullable=False, default=False)
    fondatore_sconto_applicato = Column(Boolean, nullable=False, default=False)

    onboarding_done = Column(Boolean, nullable=False, default=False)

    email = Column(String, nullable=True)
    email_verificato = Column(Boolean, nullable=False, default=False)
    token_verifica = Column(String, nullable=True)
    token_reset = Column(String, nullable=True)
    token_reset_scadenza = Column(String, nullable=True)
    accetta_termini = Column(Boolean, nullable=True, default=False)

    # Multi-utente: NULL = titolare, impostato = collaboratore
    titolare_id = Column(Integer, ForeignKey("utenti.id"), nullable=True)
    ruolo = Column(String, nullable=True, default="titolare")  # "titolare" | "collaboratore"

    # 2FA — TOTP (Google Authenticator / Authy)
    totp_secret = Column(EncryptedString, nullable=True)
    totp_abilitato = Column(Boolean, nullable=False, default=False)

    # Backoff esponenziale anti brute-force per-account su /login
    tentativi_falliti_login = Column(Integer, nullable=False, default=0)
    bloccato_fino = Column(String, nullable=True)


# ========================
# CLIENTE
# ========================

class Cliente(TimestampMixin, Base):
    __tablename__ = "clienti"
    __table_args__ = (
        Index("ix_clienti_utente_id", "utente_id"),
    )

    id = Column(Integer, primary_key=True, index=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"))

    tipo_cliente = Column(String, nullable=False, default="privato")

    nome = Column(String, nullable=True)
    cognome = Column(String, nullable=True)

    ragione_sociale = Column(String, nullable=True)

    telefono = Column(String, nullable=True)
    email = Column(String, nullable=True)

    indirizzo = Column(String, nullable=True)
    citta = Column(String, nullable=True)
    provincia = Column(String, nullable=True)
    cap = Column(String, nullable=True)

    partita_iva = Column(String, nullable=True)
    codice_fiscale = Column(String, nullable=True)
    codice_destinatario = Column(String, nullable=True)
    pec_destinatario = Column(String, nullable=True)

    note = Column(Text, nullable=True)

    token_portale = Column(String, nullable=True)
    token_portale_scadenza = Column(Date, nullable=True)

    data_creazione = Column(FlexDateTime, nullable=False)

    lavori = relationship(
        "Lavoro",
        back_populates="cliente",
        cascade="all, delete-orphan"
    )


# ========================
# LAVORO
# ========================

class Lavoro(TimestampMixin, Base):
    __tablename__ = "lavori"
    __table_args__ = (
        Index("ix_lavori_utente_id", "utente_id"),
        Index("ix_lavori_utente_stato", "utente_id", "stato"),
        Index("ix_lavori_utente_stato_fattura", "utente_id", "stato_fattura"),
        Index("ix_lavori_cliente_id", "cliente_id"),
    )

    id = Column(Integer, primary_key=True, index=True)

    cliente_id = Column(Integer, ForeignKey("clienti.id"), nullable=False)
    utente_id = Column(Integer, ForeignKey("utenti.id"))

    data_lavoro = Column(FlexDate, nullable=False)
    titolo = Column(String, nullable=False)
    numero_preventivo = Column(String, nullable=True)
    data_invio_preventivo = Column(FlexDate, nullable=True)
    data_accettazione_preventivo = Column(FlexDate, nullable=True)
    descrizione = Column(Text, nullable=True)

    stato = Column(String, nullable=False, default="da_fare")
    priorita = Column(String, nullable=False, default="normale")

    importo_preventivato = Column(Float, nullable=True)
    importo_consuntivo = Column(Float, nullable=True)

    ore_lavoro = Column(Float, default=0)
    costo_orario = Column(Float, default=0)
    totale_materiali = Column(Float, default=0)
    totale_manodopera = Column(Float, default=0)
    margine = Column(Float, default=0)
    aliquota_iva = Column(Float, default=22)
    sconto = Column(Float, default=0)
    totale_iva = Column(Float, default=0)
    totale_documento = Column(Float, default=0)
    stato_pagamento = Column(String, default="da_pagare")
    importo_pagato = Column(Float, default=0)
    residuo_pagamento = Column(Float, default=0)
    data_scadenza_pagamento = Column(FlexDate, nullable=True)
    numero_fattura = Column(Integer, nullable=True)
    data_fattura = Column(FlexDate, nullable=True)
    stato_fattura = Column(String, nullable=True)

    note_consuntivo = Column(Text, nullable=True)

    ritenuta_acconto = Column(Boolean, nullable=False, default=False)
    aliquota_ritenuta = Column(Float, nullable=True, default=20.0)

    token_firma = Column(String, nullable=True)
    firma_nome_cliente = Column(String, nullable=True)
    firma_ip = Column(String, nullable=True)

    data_fine_prevista = Column(FlexDate, nullable=True)

    # Multi-tenancy collaboratori: NULL = visibile solo al titolare, altrimenti
    # il lavoro è visibile/modificabile solo dal collaboratore assegnato.
    assegnato_a_id = Column(Integer, ForeignKey("utenti.id"), nullable=True)

    data_creazione = Column(FlexDateTime, nullable=False)

    cliente = relationship("Cliente", back_populates="lavori")
    fatture_emesse = relationship("FatturaEmessa", back_populates="lavoro", cascade="all, delete-orphan")


class Fornitore(TimestampMixin, Base):
    __tablename__ = "fornitori"

    id = Column(Integer, primary_key=True, index=True)
    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)

    nome = Column(String, nullable=False)
    partita_iva = Column(String, nullable=True)
    codice_fiscale = Column(String, nullable=True)
    telefono = Column(String, nullable=True)
    email = Column(String, nullable=True)
    indirizzo = Column(String, nullable=True)
    citta = Column(String, nullable=True)
    provincia = Column(String, nullable=True)
    cap = Column(String, nullable=True)
    sito_web = Column(String, nullable=True)
    categoria = Column(String, nullable=True)  # es. "elettrica", "idraulica", "materiali edili"
    note = Column(Text, nullable=True)

    data_creazione = Column(FlexDateTime, nullable=False)


class Materiale(TimestampMixin, Base):
    __tablename__ = "materiali"
    __table_args__ = (
        Index("ix_materiali_utente_id", "utente_id"),
    )

    id = Column(Integer, primary_key=True, index=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)

    nome = Column(String, nullable=False)
    categoria = Column(String, nullable=True)
    unita_misura = Column(String, nullable=True, default="pz")

    quantita = Column(Float, nullable=False, default=0)
    scorta_minima = Column(Float, nullable=True, default=0)

    prezzo_acquisto_pieno = Column(Float, default=0)
    prezzo_acquisto_scontato = Column(Float, default=0)
    prezzo_vendita_default = Column(Float, default=0)

    fornitore_id = Column(Integer, ForeignKey("fornitori.id"), nullable=True)
    note = Column(Text, nullable=True)
    data_creazione = Column(FlexDateTime, nullable=False)

    fornitore = relationship("Fornitore")


class CaricoMateriale(Base):
    __tablename__ = "carichi_materiale"

    id = Column(Integer, primary_key=True, index=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    materiale_id = Column(Integer, ForeignKey("materiali.id"), nullable=False)

    quantita_iniziale = Column(Float, nullable=False, default=0)
    quantita_residua = Column(Float, nullable=False, default=0)

    prezzo_acquisto = Column(Float, nullable=False, default=0)
    prezzo_vendita_default = Column(Float, nullable=False, default=0)

    note = Column(Text, nullable=True)
    data_carico = Column(FlexDate, nullable=False)


class MovimentoMagazzino(Base):
    __tablename__ = "movimenti_magazzino"

    id = Column(Integer, primary_key=True, index=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    materiale_id = Column(Integer, ForeignKey("materiali.id"), nullable=False)

    tipo = Column(String, nullable=False)  # carico / scarico
    quantita = Column(Float, nullable=False)

    note = Column(Text, nullable=True)
    data_movimento = Column(FlexDate, nullable=False)


class MaterialeUsatoLavoro(Base):
    __tablename__ = "materiali_usati_lavoro"

    id = Column(Integer, primary_key=True, index=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=False)
    materiale_id = Column(Integer, ForeignKey("materiali.id"), nullable=False)

    carico_id = Column(Integer, ForeignKey("carichi_materiale.id"), nullable=True)

    quantita = Column(Float, nullable=False)
    costo_unitario = Column(Float, default=0)
    prezzo_unitario_cliente = Column(Float, default=0)
    note = Column(Text, nullable=True)

    data_creazione = Column(FlexDateTime, nullable=False)


class ImpostazioniAzienda(TimestampMixin, Base):
    __tablename__ = "impostazioni_azienda"

    id = Column(Integer, primary_key=True, index=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)

    nome_azienda = Column(String, nullable=True)
    partita_iva = Column(String, nullable=True)
    codice_fiscale = Column(String, nullable=True)
    regime_fiscale = Column(String, nullable=True, default="RF01")
    indirizzo = Column(String, nullable=True)
    cap = Column(String, nullable=True)
    citta = Column(String, nullable=True)
    provincia = Column(String, nullable=True)
    telefono = Column(String, nullable=True)
    email = Column(String, nullable=True)

    ultimo_numero_pdf = Column(Integer, nullable=False, default=0)
    ultimo_numero_preventivo = Column(Integer, nullable=False, default=0)
    ultimo_numero_fattura = Column(Integer, nullable=False, default=0)
    ultimo_anno_fattura = Column(Integer, nullable=True)
    obiettivo_mensile = Column(Float, default=5000)
    logo_path = Column(String, nullable=True)

    aliquota_iva_default = Column(Float, nullable=True, default=22)

    # PEC per invio diretto a SDI
    pec_indirizzo = Column(String, nullable=True)
    pec_smtp_host = Column(String, nullable=True)
    pec_smtp_port = Column(Integer, nullable=True, default=465)
    pec_smtp_password = Column(EncryptedString, nullable=True)
    invio_automatico_sdi = Column(Boolean, nullable=False, default=False)


class DocumentoPDF(Base):
    __tablename__ = "documenti_pdf"

    id = Column(Integer, primary_key=True, index=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=False)

    numero = Column(Integer, nullable=False)
    nome_file = Column(String, nullable=False)
    percorso_file = Column(String, nullable=False)

    data_creazione = Column(FlexDateTime, nullable=False)


class FotoLavoro(Base):
    __tablename__ = "foto_lavori"

    id = Column(Integer, primary_key=True, index=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=False)

    nome_file = Column(String, nullable=False)
    percorso_file = Column(String, nullable=False)

    descrizione = Column(Text, nullable=True)
    data_creazione = Column(FlexDateTime, nullable=False)


class PagamentoLavoro(Base):
    __tablename__ = "pagamenti_lavoro"

    id = Column(Integer, primary_key=True, index=True)
    numero_ricevuta = Column(Integer, nullable=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=False)

    data_pagamento = Column(FlexDate, nullable=False)
    importo = Column(Float, default=0)

    metodo = Column(String, nullable=True)
    note = Column(Text, nullable=True)

    data_creazione = Column(FlexDateTime, nullable=False)


class AllegatoLavoro(Base):
    __tablename__ = "allegati_lavoro"

    id = Column(Integer, primary_key=True, index=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=False)

    nome_file = Column(String, nullable=False)
    percorso_file = Column(String, nullable=False)
    tipo_file = Column(String, nullable=True)

    descrizione = Column(Text, nullable=True)
    data_creazione = Column(FlexDateTime, nullable=False)


class FatturaEmessa(TimestampMixin, Base):
    __tablename__ = "fatture_emesse"
    __table_args__ = (
        Index("ix_fatture_emesse_utente_id", "utente_id"),
        Index("ix_fatture_emesse_utente_anno", "utente_id", "anno"),
    )

    id = Column(Integer, primary_key=True, index=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=False)

    numero = Column(Integer, nullable=False)
    anno = Column(Integer, nullable=False)
    data_emissione = Column(FlexDate, nullable=False)

    importo_imponibile = Column(Float, default=0)
    importo_iva = Column(Float, default=0)
    importo_bollo = Column(Float, default=0, nullable=True)
    importo_totale = Column(Float, default=0)

    nome_file = Column(String, nullable=True)
    regime = Column(String, nullable=True, default="RF01")
    stato = Column(String, nullable=False, default="emessa")
    reminder_inviato = Column(Integer, default=0, nullable=False)

    tipo_documento = Column(String, nullable=True, default="TD01")
    fattura_rif_numero = Column(Integer, nullable=True)
    fattura_rif_anno = Column(Integer, nullable=True)

    data_creazione = Column(FlexDateTime, nullable=False)

    stripe_payment_link_id = Column(String, nullable=True)
    stripe_payment_link_url = Column(String, nullable=True)

    lavoro = relationship("Lavoro", back_populates="fatture_emesse")


class TemplatePreventivo(TimestampMixin, Base):
    __tablename__ = "template_preventivi"

    id = Column(Integer, primary_key=True, index=True)
    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    nome = Column(String, nullable=False)
    titolo = Column(String, default="")
    descrizione = Column(Text, default="")
    importo_preventivato = Column(Float, default=0)
    aliquota_iva = Column(Float, default=22)
    sconto = Column(Float, default=0)
    note_consuntivo = Column(Text, default="")
    creato_il = Column(FlexDateTime, nullable=True)


class VocePreventivo(TimestampMixin, Base):
    __tablename__ = "voci_preventivo"
    __table_args__ = (
        Index("ix_voci_preventivo_lavoro_id", "lavoro_id"),
        Index("ix_voci_preventivo_utente_id", "utente_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=False)
    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    descrizione = Column(String, nullable=False)
    quantita = Column(Float, default=1)
    unita_misura = Column(String, default="")
    prezzo_unitario = Column(Float, default=0)
    ordine = Column(Integer, default=0)


class SessioneLavoro(Base):
    __tablename__ = "sessioni_lavoro"

    id = Column(Integer, primary_key=True, index=True)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=False)
    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    inizio = Column(FlexDateTime, nullable=False)
    fine = Column(FlexDateTime, nullable=True)
    ore_calcolate = Column(Float, nullable=True)


class Garanzia(TimestampMixin, Base):
    __tablename__ = "garanzie"
    __table_args__ = (
        Index("ix_garanzie_utente_id", "utente_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    cliente_id = Column(Integer, ForeignKey("clienti.id"), nullable=False)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=True)

    descrizione = Column(String, nullable=False)
    data_installazione = Column(FlexDate, nullable=False)
    durata_mesi = Column(Integer, nullable=False, default=24)
    data_scadenza = Column(FlexDate, nullable=False)
    note = Column(Text, nullable=True)

    reminder_30g_inviato = Column(Integer, default=0)
    reminder_7g_inviato = Column(Integer, default=0)

    data_creazione = Column(FlexDateTime, nullable=False)

    cliente = relationship("Cliente")
    lavoro = relationship("Lavoro")


class VocePrimaNota(TimestampMixin, Base):
    __tablename__ = "prima_nota"
    __table_args__ = (
        Index("ix_prima_nota_utente_id", "utente_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)

    data = Column(FlexDate, nullable=False)
    descrizione = Column(String, nullable=False)
    importo = Column(Float, nullable=False)
    tipo = Column(String, nullable=False, default="uscita")  # "entrata" | "uscita"
    categoria = Column(String, nullable=True)
    fornitore_id = Column(Integer, ForeignKey("fornitori.id"), nullable=True)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=True)
    cliente_id = Column(Integer, ForeignKey("clienti.id"), nullable=True)

    aliquota_iva = Column(Float, nullable=True, default=0.0)
    importo_iva = Column(Float, nullable=True, default=0.0)

    data_creazione = Column(FlexDateTime, nullable=False)

    fornitore = relationship("Fornitore")
    lavoro = relationship("Lavoro")
    cliente = relationship("Cliente")


class FatturaAcquisto(TimestampMixin, Base):
    __tablename__ = "fatture_acquisto"
    __table_args__ = (
        Index("ix_fatture_acquisto_utente_id", "utente_id"),
        Index("ix_fatture_acquisto_utente_anno", "utente_id", "anno"),
    )

    id = Column(Integer, primary_key=True, index=True)
    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    fornitore_id = Column(Integer, ForeignKey("fornitori.id"), nullable=True)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=True)

    numero_fattura = Column(String, nullable=True)
    data_fattura = Column(FlexDate, nullable=False)
    anno = Column(Integer, nullable=False)
    data_scadenza = Column(FlexDate, nullable=True)

    descrizione = Column(String, nullable=False)
    categoria = Column(String, nullable=True)

    importo_imponibile = Column(Float, default=0)
    aliquota_iva = Column(Float, default=22)
    importo_iva = Column(Float, default=0)
    importo_totale = Column(Float, default=0)

    stato_pagamento = Column(String, nullable=False, default="da_pagare")
    data_pagamento = Column(FlexDate, nullable=True)
    metodo_pagamento = Column(String, nullable=True)

    note = Column(Text, nullable=True)
    data_creazione = Column(FlexDateTime, nullable=False)

    fornitore = relationship("Fornitore")
    lavoro = relationship("Lavoro")


class ListinoVoce(TimestampMixin, Base):
    __tablename__ = "listino_voci"

    id = Column(Integer, primary_key=True, index=True)
    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    descrizione = Column(String, nullable=False)
    unita_misura = Column(String, nullable=True, default="")
    prezzo_unitario = Column(Float, nullable=False, default=0)
    categoria = Column(String, nullable=True, default="")
    data_creazione = Column(FlexDateTime, nullable=False)


class SalLavoro(TimestampMixin, Base):
    __tablename__ = "sal_lavoro"

    id = Column(Integer, primary_key=True, index=True)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=False)
    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    numero = Column(Integer, nullable=False, default=1)
    data = Column(FlexDate, nullable=False)
    percentuale = Column(Float, nullable=False, default=0)
    importo_richiesto = Column(Float, nullable=False, default=0)
    descrizione = Column(Text, nullable=True, default="")
    note = Column(Text, nullable=True, default="")
    stato = Column(String, nullable=False, default="emesso")  # emesso / pagato
    data_creazione = Column(FlexDateTime, nullable=False)


class RapportinoLavoro(TimestampMixin, Base):
    __tablename__ = "rapportini_lavoro"

    id = Column(Integer, primary_key=True, index=True)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=False)
    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    data = Column(FlexDate, nullable=False)
    ore_lavorate = Column(Float, nullable=True, default=0)
    descrizione_attivita = Column(Text, nullable=False)
    materiali_note = Column(Text, nullable=True, default="")
    note = Column(Text, nullable=True, default="")
    data_creazione = Column(FlexDateTime, nullable=False)


class PromemoriaCliente(TimestampMixin, Base):
    __tablename__ = "promemoria_clienti"
    __table_args__ = (
        Index("ix_promemoria_utente_id", "utente_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    cliente_id = Column(Integer, ForeignKey("clienti.id"), nullable=True)
    titolo = Column(String, nullable=False)
    note = Column(Text, nullable=True, default="")
    data_promemoria = Column(FlexDate, nullable=False)
    tipo = Column(String, nullable=False, default="manutenzione")
    stato = Column(String, nullable=False, default="attivo")
    data_creazione = Column(FlexDateTime, nullable=False)

    cliente = relationship("Cliente")


class TimesheetCollab(TimestampMixin, Base):
    __tablename__ = "timesheet_collab"

    id = Column(Integer, primary_key=True, index=True)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=False)
    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    nome_operaio = Column(String, nullable=False)
    collaboratore_id = Column(Integer, ForeignKey("utenti.id"), nullable=True)
    data = Column(FlexDate, nullable=False)
    ore = Column(Float, nullable=False, default=0)
    costo_orario = Column(Float, nullable=True, default=0)
    note = Column(Text, nullable=True, default="")
    data_creazione = Column(FlexDateTime, nullable=False)

    collaboratore = relationship("Utente", foreign_keys=[collaboratore_id])


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    endpoint = Column(Text, nullable=False)
    subscription_json = Column(Text, nullable=False)
    creata_il = Column(FlexDateTime, nullable=False)


class InvitoAccount(Base):
    __tablename__ = "inviti_account"

    id = Column(Integer, primary_key=True, index=True)
    titolare_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    token = Column(String, nullable=False, unique=True)
    scadenza = Column(FlexDate, nullable=False)
    usato = Column(Integer, default=0)
    data_creazione = Column(FlexDateTime, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_utente_ts", "utente_id", "timestamp"),
    )

    id = Column(Integer, primary_key=True)
    timestamp = Column(String, nullable=False)

    utente_id = Column(Integer, nullable=False)       # titolare (proprietario dei dati)
    attore_id = Column(Integer, nullable=False)       # utente che ha eseguito l'azione
    attore_username = Column(String, nullable=False)  # denormalizzato per resilienza

    azione = Column(String, nullable=False)           # es. "emette_fattura", "pagamento_fattura"
    tabella = Column(String, nullable=False)          # es. "fatture_emesse", "lavori"
    record_id = Column(Integer, nullable=True)

    dettaglio = Column(Text, nullable=True)           # JSON con valori rilevanti
    ip = Column(String, nullable=True)
