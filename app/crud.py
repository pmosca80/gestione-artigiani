from app.models import DocumentoPDF

from app.models import ImpostazioniAzienda

from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models import Cliente, Lavoro, Materiale, MovimentoMagazzino, MaterialeUsatoLavoro, ImpostazioniAzienda, DocumentoPDF
from app.models import MovimentoMagazzino


def get_clienti(db: Session, cerca: str = "", utente_id: int | None = None):
    query = db.query(Cliente)

    if utente_id is not None:
        query = query.filter(Cliente.utente_id == utente_id)

    if cerca:
        cerca_like = f"%{cerca}%"
        query = query.filter(
            or_(
                Cliente.nome.ilike(cerca_like),
                Cliente.cognome.ilike(cerca_like),
                Cliente.telefono.ilike(cerca_like),
            )
        )

    return query.order_by(Cliente.id.desc()).all()


def crea_cliente(db: Session, nome: str, cognome: str, telefono: str, utente_id: int):
    nuovo_cliente = Cliente(
        utente_id=utente_id,
        tipo_cliente="privato",
        nome=nome,
        cognome=cognome,
        telefono=telefono,
        data_creazione=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    db.add(nuovo_cliente)
    db.commit()
    db.refresh(nuovo_cliente)
    return nuovo_cliente


def get_cliente_by_id(db: Session, cliente_id: int, utente_id: int | None = None):
    query = db.query(Cliente).filter(Cliente.id == cliente_id)

    if utente_id is not None:
        query = query.filter(Cliente.utente_id == utente_id)

    return query.first()


def aggiorna_cliente(db: Session, cliente_id: int, nome: str, cognome: str, telefono: str):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if cliente:
        cliente.nome = nome
        cliente.cognome = cognome
        cliente.telefono = telefono
        db.commit()
        db.refresh(cliente)
    return cliente


def elimina_cliente(db: Session, cliente_id: int):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        return None

    lavori_collegati = db.query(Lavoro).filter(Lavoro.cliente_id == cliente_id).count()
    if lavori_collegati > 0:
        return "bloccato"

    db.delete(cliente)
    db.commit()
    return cliente


def get_lavori(db: Session, stato: str = "", utente_id: int | None = None):
    query = db.query(Lavoro)

    if utente_id is not None:
        query = query.filter(Lavoro.utente_id == utente_id)

    if stato:
        query = query.filter(Lavoro.stato == stato)

    return query.order_by(Lavoro.id.desc()).all()

def get_lavori_by_cliente(db: Session, cliente_id: int, utente_id: int | None = None):
    query = db.query(Lavoro).filter(Lavoro.cliente_id == cliente_id)

    if utente_id is not None:
        query = query.filter(Lavoro.utente_id == utente_id)

    return query.order_by(Lavoro.id.desc()).all()


def get_lavoro_by_id(db: Session, lavoro_id: int, utente_id: int | None = None):
    query = db.query(Lavoro).filter(Lavoro.id == lavoro_id)

    if utente_id is not None:
        query = query.filter(Lavoro.utente_id == utente_id)

    return query.first()


def crea_lavoro(
    db: Session,
    cliente_id: int,
    data_lavoro: str,
    titolo: str,
    descrizione: str,
    importo_preventivato: float | None,
    importo_consuntivo: float | None,
    note_consuntivo: str,
    utente_id: int
):
    nuovo_lavoro = Lavoro(
        utente_id=utente_id,
        cliente_id=cliente_id,
        data_lavoro=data_lavoro,
        titolo=titolo,
        descrizione=descrizione,
        stato="da_fare",
        priorita="normale",
        importo_preventivato=importo_preventivato,
        importo_consuntivo=importo_consuntivo,
        note_consuntivo=note_consuntivo,
        data_creazione=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    db.add(nuovo_lavoro)
    db.commit()
    db.refresh(nuovo_lavoro)
    return nuovo_lavoro


def aggiorna_lavoro(
    db: Session,
    lavoro_id: int,
    data_lavoro: str,
    titolo: str,
    descrizione: str,
    stato: str,
    importo_preventivato: float | None,
    importo_consuntivo: float | None,
    ore_lavoro: float = 0,
    costo_orario: float = 0,
    note_consuntivo: str = ""
):
    lavoro = db.query(Lavoro).filter(Lavoro.id == lavoro_id).first()

    if lavoro:
        lavoro.data_lavoro = data_lavoro
        lavoro.titolo = titolo
        lavoro.descrizione = descrizione
        lavoro.stato = stato

        lavoro.importo_preventivato = importo_preventivato
        lavoro.importo_consuntivo = importo_consuntivo

        lavoro.ore_lavoro = ore_lavoro
        lavoro.costo_orario = costo_orario

        lavoro.note_consuntivo = note_consuntivo

        # calcoli automatici
        lavoro.totale_manodopera = ore_lavoro * costo_orario

        totale_materiali = lavoro.totale_materiali or 0

        lavoro.importo_consuntivo = (
            totale_materiali + lavoro.totale_manodopera
        )

        preventivo = lavoro.importo_preventivato or 0

        lavoro.margine = (
            preventivo - lavoro.importo_consuntivo
        )

        db.commit()
        db.refresh(lavoro)

    return lavoro


def elimina_lavoro(db: Session, lavoro_id: int):
    lavoro = db.query(Lavoro).filter(Lavoro.id == lavoro_id).first()
    if lavoro:
        db.delete(lavoro)
        db.commit()
    return lavoro


def get_dashboard_stats(db: Session, utente_id: int | None = None):
    query_clienti = db.query(Cliente)
    query_lavori = db.query(Lavoro)

    if utente_id is not None:
        query_clienti = query_clienti.filter(Cliente.utente_id == utente_id)
        query_lavori = query_lavori.filter(Lavoro.utente_id == utente_id)

    lavori = query_lavori.all()

    return {
        "clienti_totali": query_clienti.count(),
        "lavori_da_fare": query_lavori.filter(Lavoro.stato == "da_fare").count(),
        "lavori_in_corso": query_lavori.filter(Lavoro.stato == "in_corso").count(),
        "lavori_completati": query_lavori.filter(Lavoro.stato == "completato").count(),
        "totale_preventivato": sum(l.importo_preventivato or 0 for l in lavori),
        "totale_consuntivo": sum(l.importo_consuntivo or 0 for l in lavori),
    }
from app.models import Materiale

def get_materiali(db: Session, utente_id: int, cerca: str = ""):
    query = db.query(Materiale).filter(Materiale.utente_id == utente_id)

    if cerca:
        cerca_like = f"%{cerca}%"
        query = query.filter(
            or_(
                Materiale.nome.ilike(cerca_like),
                Materiale.categoria.ilike(cerca_like),
            )
        )

    return query.order_by(Materiale.id.desc()).all()


def crea_materiale(
    db: Session,
    utente_id: int,
    nome: str,
    categoria: str,
    unita_misura: str,
    quantita: float,
    scorta_minima: float,
    note: str
):
    nuovo = Materiale(
        utente_id=utente_id,
        nome=nome,
        categoria=categoria,
        unita_misura=unita_misura,
        quantita=quantita,
        scorta_minima=scorta_minima,
        note=note,
        data_creazione=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    db.add(nuovo)
    db.commit()
    db.refresh(nuovo)

    return nuovo

def aggiungi_movimento(
    db: Session,
    utente_id: int,
    materiale_id: int,
    tipo: str,
    quantita: float,
    note: str
):
    materiale = db.query(Materiale).filter(Materiale.id == materiale_id).first()

    if not materiale:
        return None

    if tipo == "carico":
        materiale.quantita += quantita
    elif tipo == "scarico":
        materiale.quantita -= quantita

    movimento = MovimentoMagazzino(
        utente_id=utente_id,
        materiale_id=materiale_id,
        tipo=tipo,
        quantita=quantita,
        note=note,
        data_movimento=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    db.add(movimento)
    db.commit()

def get_movimenti_magazzino(db: Session, utente_id: int):
    return (
        db.query(MovimentoMagazzino)
        .filter(MovimentoMagazzino.utente_id == utente_id)
        .order_by(MovimentoMagazzino.id.desc())
        .all()
    )


def get_movimenti_by_materiale(db: Session, utente_id: int, materiale_id: int):
    return (
        db.query(MovimentoMagazzino)
        .filter(
            MovimentoMagazzino.utente_id == utente_id,
            MovimentoMagazzino.materiale_id == materiale_id
        )
        .order_by(MovimentoMagazzino.id.desc())
        .all()
    )

def get_materiali_usati_lavoro(db: Session, utente_id: int, lavoro_id: int):
    return (
        db.query(MaterialeUsatoLavoro)
        .filter(
            MaterialeUsatoLavoro.utente_id == utente_id,
            MaterialeUsatoLavoro.lavoro_id == lavoro_id
        )
        .order_by(MaterialeUsatoLavoro.id.desc())
        .all()
    )


def aggiungi_materiale_a_lavoro(
    db: Session,
    utente_id: int,
    lavoro_id: int,
    materiale_id: int,
    quantita: float,
    costo_unitario: float,
    note: str
):
    materiale = (
        db.query(Materiale)
        .filter(Materiale.id == materiale_id, Materiale.utente_id == utente_id)
        .first()
    )

    lavoro = (
        db.query(Lavoro)
        .filter(Lavoro.id == lavoro_id, Lavoro.utente_id == utente_id)
        .first()
    )

    if not materiale or not lavoro:
        return None

    if materiale.quantita < quantita:
        return "scorta_insufficiente"

    materiale.quantita -= quantita

    usato = MaterialeUsatoLavoro(
        utente_id=utente_id,
        lavoro_id=lavoro_id,
        materiale_id=materiale_id,
        quantita=quantita,
        costo_unitario=costo_unitario,
        note=note,
        data_creazione=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    movimento = MovimentoMagazzino(
        utente_id=utente_id,
        materiale_id=materiale_id,
        tipo="scarico",
        quantita=quantita,
        note=f"Scarico per lavoro ID {lavoro_id}. {note}",
        data_movimento=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    db.add(usato)
    db.add(movimento)
    db.commit()
    db.refresh(usato)

    return usato
def get_dashboard_pro(db: Session, utente_id: int):
    clienti_totali = db.query(Cliente).filter(Cliente.utente_id == utente_id).count()

    lavori = db.query(Lavoro).filter(Lavoro.utente_id == utente_id).all()
    materiali = db.query(Materiale).filter(Materiale.utente_id == utente_id).all()

    return {
        "clienti_totali": clienti_totali,
        "lavori_totali": len(lavori),
        "lavori_da_fare": sum(1 for l in lavori if l.stato == "da_fare"),
        "lavori_in_corso": sum(1 for l in lavori if l.stato == "in_corso"),
        "lavori_completati": sum(1 for l in lavori if l.stato == "completato"),
        "lavori_annullati": sum(1 for l in lavori if l.stato == "annullato"),
        "totale_preventivato": sum(l.importo_preventivato or 0 for l in lavori),
        "totale_consuntivo": sum(l.importo_consuntivo or 0 for l in lavori),
        "differenza": sum(l.importo_consuntivo or 0 for l in lavori) - sum(l.importo_preventivato or 0 for l in lavori),
        "materiali_totali": len(materiali),
        "materiali_sotto_scorta": [
            m for m in materiali
            if (m.quantita or 0) <= (m.scorta_minima or 0)
        ],
        "numero_materiali_sotto_scorta": len([
            m for m in materiali
            if (m.quantita or 0) <= (m.scorta_minima or 0)
        ]),
    }

def get_impostazioni_azienda(db: Session, utente_id: int):
    impostazioni = (
        db.query(ImpostazioniAzienda)
        .filter(ImpostazioniAzienda.utente_id == utente_id)
        .first()
    )

    if not impostazioni:
        impostazioni = ImpostazioniAzienda(
            utente_id=utente_id,
            nome_azienda="La tua azienda",
            partita_iva="",
            indirizzo="",
            telefono="",
            email="",
            ultimo_numero_pdf=0
        )
        db.add(impostazioni)
        db.commit()
        db.refresh(impostazioni)

    return impostazioni


def genera_numero_pdf(db: Session, utente_id: int):
    impostazioni = get_impostazioni_azienda(db, utente_id)
    impostazioni.ultimo_numero_pdf += 1
    db.commit()
    db.refresh(impostazioni)
    return impostazioni.ultimo_numero_pdf
def salva_documento_pdf(
    db: Session,
    utente_id: int,
    lavoro_id: int,
    numero: int,
    nome_file: str,
    percorso_file: str
):
    documento = DocumentoPDF(
        utente_id=utente_id,
        lavoro_id=lavoro_id,
        numero=numero,
        nome_file=nome_file,
        percorso_file=percorso_file,
        data_creazione=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    db.add(documento)
    db.commit()
    db.refresh(documento)

    return documento


def get_documenti_pdf(db: Session, utente_id: int):
    return (
        db.query(DocumentoPDF)
        .filter(DocumentoPDF.utente_id == utente_id)
        .order_by(DocumentoPDF.id.desc())
        .all()
    )


def get_documenti_pdf_by_lavoro(db: Session, utente_id: int, lavoro_id: int):
    return (
        db.query(DocumentoPDF)
        .filter(
            DocumentoPDF.utente_id == utente_id,
            DocumentoPDF.lavoro_id == lavoro_id
        )
        .order_by(DocumentoPDF.id.desc())
        .all()
    )


def get_documento_pdf_by_id(db: Session, utente_id: int, documento_id: int):
    return (
        db.query(DocumentoPDF)
        .filter(
            DocumentoPDF.id == documento_id,
            DocumentoPDF.utente_id == utente_id
        )
        .first()
    )

def calcola_totale_materiali_lavoro(db: Session, utente_id: int, lavoro_id: int):
    materiali_usati = get_materiali_usati_lavoro(db, utente_id, lavoro_id)

    totale = 0

    for riga in materiali_usati:
        totale += (riga.quantita or 0) * (riga.costo_unitario or 0)

    return totale

def get_dashboard_pro(db: Session, utente_id: int):
    lavori = db.query(Lavoro).filter(
        Lavoro.utente_id == utente_id
    ).all()

    lavori_totali = len(lavori)
    lavori_aperti = 0
    lavori_completati = 0

    totale_preventivi = 0
    totale_consuntivi = 0
    totale_materiali = 0
    totale_manodopera = 0
    margine_totale = 0

    for lavoro in lavori:
        if lavoro.stato == "completato":
            lavori_completati += 1
        else:
            lavori_aperti += 1

        totale_preventivi += lavoro.importo_preventivato or 0
        totale_consuntivi += lavoro.importo_consuntivo or 0
        totale_materiali += lavoro.totale_materiali or 0
        totale_manodopera += lavoro.totale_manodopera or 0
        margine_totale += lavoro.margine or 0

    percentuale_completati = 0
    if lavori_totali > 0:
        percentuale_completati = round((lavori_completati / lavori_totali) * 100, 1)

        lavori_ordinati = sorted(
        lavori,
        key=lambda l: l.margine or 0,
        reverse=True
    )

    lavori_ordinati = sorted(
        lavori,
        key=lambda l: l.margine or 0,
        reverse=True
    )
    
    lavori_migliori = lavori_ordinati[:5]
    lavori_peggiori = sorted(
        lavori,
        key=lambda l: l.margine or 0
    )[:5]

    materiali_scorte_basse = db.query(Materiale).filter(
        Materiale.utente_id == utente_id,
        Materiale.quantita <= Materiale.scorta_minima
    ).all()

    mese_corrente = datetime.now().strftime("%Y-%m")

    lavori_mese = [
        lavoro for lavoro in lavori
        if lavoro.data_creazione and lavoro.data_creazione.startswith(mese_corrente)
    ]

    lavori_mese_count = len(lavori_mese)

    preventivi_mese = sum(l.importo_preventivato or 0 for l in lavori_mese)
    consuntivi_mese = sum(l.importo_consuntivo or 0 for l in lavori_mese)
    margine_mese = sum(l.margine or 0 for l in lavori_mese)

    ultimi_lavori = sorted(
        lavori,
        key=lambda l: l.data_creazione or "",
        reverse=True
    )[:5]

    return {
        "lavori_totali": lavori_totali,
        "lavori_aperti": lavori_aperti,
        "lavori_completati": lavori_completati,
        "percentuale_completati": percentuale_completati,

        "totale_preventivi": totale_preventivi,
        "totale_consuntivi": totale_consuntivi,
        "totale_materiali": totale_materiali,
        "totale_manodopera": totale_manodopera,
        "margine_totale": margine_totale,
        "lavori_migliori": lavori_migliori,
        "lavori_peggiori": lavori_peggiori,
        "materiali_scorte_basse": materiali_scorte_basse,
        "lavori_mese_count": lavori_mese_count,
        "preventivi_mese": preventivi_mese,
        "consuntivi_mese": consuntivi_mese,
        "margine_mese": margine_mese,
        "ultimi_lavori": ultimi_lavori,
    }