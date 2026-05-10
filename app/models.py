from sqlalchemy import Column, Integer, String, Text, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.database import Base


# ========================
# CLIENTE
# ========================

class Utente(Base):
    __tablename__ = "utenti"

    id = Column(Integer, primary_key=True, index=True)
    
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)

class Cliente(Base):
    __tablename__ = "clienti"

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

    note = Column(Text, nullable=True)

    data_creazione = Column(String, nullable=False)

    # relazione con lavori
    lavori = relationship(
        "Lavoro",
        back_populates="cliente",
        cascade="all, delete-orphan"
    )


# ========================
# LAVORO
# ========================
class Lavoro(Base):
    __tablename__ = "lavori"

    id = Column(Integer, primary_key=True, index=True)

    cliente_id = Column(Integer, ForeignKey("clienti.id"), nullable=False)
    utente_id = Column(Integer, ForeignKey("utenti.id"))

    data_lavoro = Column(String, nullable=False)
    titolo = Column(String, nullable=False)
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

    note_consuntivo = Column(Text, nullable=True)

    data_creazione = Column(String, nullable=False)

    cliente = relationship("Cliente", back_populates="lavori")
    
class Materiale(Base):
    __tablename__ = "materiali"

    id = Column(Integer, primary_key=True, index=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)

    nome = Column(String, nullable=False)
    categoria = Column(String, nullable=True)
    unita_misura = Column(String, nullable=True, default="pz")

    quantita = Column(Float, nullable=False, default=0)
    scorta_minima = Column(Float, nullable=True, default=0)

    note = Column(Text, nullable=True)
    data_creazione = Column(String, nullable=False)

class MovimentoMagazzino(Base):
    __tablename__ = "movimenti_magazzino"

    id = Column(Integer, primary_key=True, index=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    materiale_id = Column(Integer, ForeignKey("materiali.id"), nullable=False)

    tipo = Column(String, nullable=False)  # carico / scarico
    quantita = Column(Float, nullable=False)

    note = Column(Text, nullable=True)
    data_movimento = Column(String, nullable=False)

class MaterialeUsatoLavoro(Base):
    __tablename__ = "materiali_usati_lavoro"

    id = Column(Integer, primary_key=True, index=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=False)
    materiale_id = Column(Integer, ForeignKey("materiali.id"), nullable=False)

    quantita = Column(Float, nullable=False)
    costo_unitario = Column(Float, nullable=True, default=0)
    note = Column(Text, nullable=True)

    data_creazione = Column(String, nullable=False)

class ImpostazioniAzienda(Base):
    __tablename__ = "impostazioni_azienda"

    id = Column(Integer, primary_key=True, index=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)

    nome_azienda = Column(String, nullable=True)
    partita_iva = Column(String, nullable=True)
    indirizzo = Column(String, nullable=True)
    telefono = Column(String, nullable=True)
    email = Column(String, nullable=True)

    ultimo_numero_pdf = Column(Integer, nullable=False, default=0)

class DocumentoPDF(Base):
    __tablename__ = "documenti_pdf"

    id = Column(Integer, primary_key=True, index=True)

    utente_id = Column(Integer, ForeignKey("utenti.id"), nullable=False)
    lavoro_id = Column(Integer, ForeignKey("lavori.id"), nullable=False)

    numero = Column(Integer, nullable=False)
    nome_file = Column(String, nullable=False)
    percorso_file = Column(String, nullable=False)

    data_creazione = Column(String, nullable=False)