from app.models import DocumentoPDF, Garanzia
import math
import secrets
import calendar
from datetime import datetime, timedelta
from app.models import ImpostazioniAzienda

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from app.models import (
    Cliente,
    Lavoro,
    Materiale,
    MovimentoMagazzino,
    MaterialeUsatoLavoro,
    ImpostazioniAzienda,
    DocumentoPDF,
    CaricoMateriale,
    FotoLavoro,
    PagamentoLavoro,
    AllegatoLavoro,
    FatturaEmessa,
    TemplatePreventivo,
    VocePreventivo,
    SessioneLavoro,
    VocePrimaNota,
    ListinoVoce,
    SalLavoro,
    RapportinoLavoro,
    PromemoriaCliente,
    TimesheetCollab,
)
from app.models import MovimentoMagazzino


def get_clienti(
    db: Session,
    cerca: str = "",
    utente_id: int | None = None,
    pagina: int = 1,
    per_pagina: int = 20,
):
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

    totale = query.count()

    offset = (pagina - 1) * per_pagina
    clienti = query.offset(offset).limit(per_pagina).all()

    for cliente in clienti:
        totale_residuo = (
            db.query(func.sum(Lavoro.residuo_pagamento))
            .filter(
                Lavoro.cliente_id == cliente.id,
                Lavoro.utente_id == utente_id,
                Lavoro.residuo_pagamento > 0
            )
            .scalar()
        ) or 0
        cliente.totale_residuo = totale_residuo

    clienti.sort(key=lambda c: c.totale_residuo or 0, reverse=True)

    return {
        "items": clienti,
        "totale": totale,
        "pagina": pagina,
        "per_pagina": per_pagina,
        "pagine_totali": math.ceil(totale / per_pagina) if totale > 0 else 1,
    }

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


def aggiorna_cliente(
    db: Session,
    cliente_id: int,
    utente_id: int,
    tipo_cliente: str = "privato",
    nome: str = "",
    cognome: str = "",
    ragione_sociale: str = "",
    telefono: str = "",
    email: str = "",
    indirizzo: str = "",
    citta: str = "",
    provincia: str = "",
    cap: str = "",
    partita_iva: str = "",
    codice_fiscale: str = "",
    codice_destinatario: str = "",
    pec_destinatario: str = "",
    note: str = "",
):
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id,
        Cliente.utente_id == utente_id
    ).first()
    if cliente:
        cliente.tipo_cliente = tipo_cliente
        cliente.nome = nome
        cliente.cognome = cognome
        cliente.ragione_sociale = ragione_sociale
        cliente.telefono = telefono
        cliente.email = email
        cliente.indirizzo = indirizzo
        cliente.citta = citta
        cliente.provincia = provincia
        cliente.cap = cap
        cliente.partita_iva = partita_iva
        cliente.codice_fiscale = codice_fiscale
        cliente.codice_destinatario = codice_destinatario
        cliente.pec_destinatario = pec_destinatario
        cliente.note = note
        db.commit()
        db.refresh(cliente)
    return cliente


def elimina_cliente(db: Session, cliente_id: int, utente_id: int):
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id,
        Cliente.utente_id == utente_id
    ).first()

    if not cliente:
        return None

    lavori_collegati = db.query(Lavoro).filter(Lavoro.cliente_id == cliente_id).count()
    if lavori_collegati > 0:
        return "bloccato"

    db.delete(cliente)
    db.commit()
    return cliente


def get_lavori(
    db: Session,
    stato: str = "",
    utente_id: int | None = None,
    pagamento: str = "",
    scaduti: str = "",
    ricerca: str = "",
    ordinamento: str = "recenti",
    cliente_id: int | None = None,
    pagina: int = 1,
    per_pagina: int = 20,
):
    query = db.query(Lavoro)

    if utente_id is not None:
        query = query.filter(Lavoro.utente_id == utente_id)

    if cliente_id is not None:
        query = query.filter(Lavoro.cliente_id == cliente_id)

    if stato:
        query = query.filter(Lavoro.stato == stato)

    oggi = datetime.now().strftime("%Y-%m-%d")

    if pagamento == "da_incassare":
        query = query.filter(Lavoro.residuo_pagamento > 0)
    elif pagamento == "scaduti":
        query = query.filter(
            Lavoro.residuo_pagamento > 0,
            Lavoro.data_scadenza_pagamento != None,
            Lavoro.data_scadenza_pagamento < oggi
        )
    elif pagamento:
        query = query.filter(Lavoro.stato_pagamento == pagamento)

    if scaduti == "1":
        query = query.filter(
            Lavoro.data_scadenza_pagamento < oggi,
            Lavoro.stato_pagamento != "pagato"
        )

    join_fatto = False

    if ricerca:
        query = query.join(Cliente)
        join_fatto = True
        query = query.filter(
            or_(
                Cliente.nome.ilike(f"%{ricerca}%"),
                Cliente.cognome.ilike(f"%{ricerca}%"),
                Lavoro.titolo.ilike(f"%{ricerca}%"),
                Lavoro.descrizione.ilike(f"%{ricerca}%")
            )
        )

    if ordinamento == "vecchi":
        query = query.order_by(Lavoro.id.asc())
    elif ordinamento == "importo":
        query = query.order_by(Lavoro.totale_documento.desc())
    elif ordinamento == "residuo":
        query = query.order_by(Lavoro.residuo_pagamento.desc())
    elif ordinamento == "cliente":
        if not join_fatto:
            query = query.join(Cliente)
        query = query.order_by(Cliente.cognome.asc())
    else:
        query = query.order_by(Lavoro.id.desc())

    totale = query.count()

    offset = (pagina - 1) * per_pagina
    lavori = query.offset(offset).limit(per_pagina).all()

    oggi_data = datetime.now()
    for lavoro in lavori:
        lavoro.giorni_ritardo = 0
        if lavoro.data_scadenza_pagamento and lavoro.stato_pagamento != "pagato":
            try:
                scadenza = datetime.strptime(lavoro.data_scadenza_pagamento, "%Y-%m-%d")
                differenza = (oggi_data - scadenza).days
                if differenza > 0:
                    lavoro.giorni_ritardo = differenza
            except:
                pass

    return {
        "items": lavori,
        "totale": totale,
        "pagina": pagina,
        "per_pagina": per_pagina,
        "pagine_totali": math.ceil(totale / per_pagina) if totale > 0 else 1,
    }

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
    db,
    cliente_id,
    data_lavoro,
    titolo,
    descrizione,
    stato,
    importo_preventivato,
    importo_consuntivo,
    aliquota_iva,
    sconto,
    note_consuntivo,
    utente_id
):

    numero_preventivo = None

    if stato in ["preventivo", "preventivo_inviato", "preventivo_accettato"]:
        numero_preventivo = genera_numero_preventivo(db, utente_id)

    nuovo_lavoro = Lavoro(
        cliente_id=cliente_id,
        utente_id=utente_id,
        data_lavoro=data_lavoro,
        titolo=titolo,
        numero_preventivo=numero_preventivo,
        descrizione=descrizione,
        stato=stato,
        importo_preventivato=importo_preventivato,
        importo_consuntivo=importo_consuntivo,
        aliquota_iva=aliquota_iva,
        sconto=sconto,
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
    utente_id: int,
    data_lavoro: str,
    titolo: str,
    descrizione: str,
    stato: str,
    importo_preventivato: float | None,
    importo_consuntivo: float | None,
    ore_lavoro: float = 0,
    costo_orario: float = 0,
    aliquota_iva: float = 22,
    sconto: float = 0,
    importo_pagato: float = 0,
    data_scadenza_pagamento: str = "",
    note_consuntivo: str = "",
    numero_fattura: int | None = None,
    data_fattura: str = "",
    ritenuta_acconto: bool = False,
    aliquota_ritenuta: float = 20.0,
):
    lavoro = db.query(Lavoro).filter(
        Lavoro.id == lavoro_id,
        Lavoro.utente_id == utente_id
    ).first()

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

        lavoro.aliquota_iva = aliquota_iva
        lavoro.sconto = sconto

        lavoro.importo_pagato = importo_pagato

        lavoro.data_scadenza_pagamento = data_scadenza_pagamento
        if numero_fattura:
            lavoro.numero_fattura = numero_fattura
        if data_fattura:
            lavoro.data_fattura = data_fattura
        lavoro.ritenuta_acconto = ritenuta_acconto
        lavoro.aliquota_ritenuta = aliquota_ritenuta

        # calcoli automatici
        lavoro.totale_manodopera = ore_lavoro * costo_orario

        totale_materiali = lavoro.totale_materiali or 0

        imponibile = totale_materiali + lavoro.totale_manodopera

        iva = imponibile * ((aliquota_iva or 0) / 100)

        totale_documento = imponibile + iva - (sconto or 0)

        lavoro.importo_consuntivo = imponibile
        lavoro.totale_iva = iva
        lavoro.totale_documento = totale_documento

        preventivo = lavoro.importo_preventivato or 0

        costo_reale = totale_materiali + lavoro.totale_manodopera

        lavoro.margine = totale_documento - costo_reale

        lavoro.residuo_pagamento = max(0.0, lavoro.totale_documento - importo_pagato)

        if importo_pagato <= 0:
            lavoro.stato_pagamento = "da_pagare"
        elif importo_pagato < lavoro.totale_documento:
            lavoro.stato_pagamento = "acconto"
        else:
            lavoro.stato_pagamento = "pagato"

        db.commit()
        db.refresh(lavoro)

    return lavoro


def elimina_lavoro(db: Session, lavoro_id: int):
    lavoro = db.query(Lavoro).filter(
        Lavoro.id == lavoro_id,
        Lavoro.utente_id == utente_id
    ).first()
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
    prezzo_acquisto_pieno: float,
    prezzo_acquisto_scontato: float,
    prezzo_vendita_default: float,
    note: str
):
    nuovo = Materiale(
        utente_id=utente_id,
        nome=nome,
        categoria=categoria,
        unita_misura=unita_misura,
        quantita=quantita,
        scorta_minima=scorta_minima,

        prezzo_acquisto_pieno=prezzo_acquisto_pieno,
        prezzo_acquisto_scontato=prezzo_acquisto_scontato,
        prezzo_vendita_default=prezzo_vendita_default,

        note=note,
        data_creazione=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    db.add(nuovo)
    db.commit()
    db.refresh(nuovo)
    
    carico = CaricoMateriale(
        utente_id=utente_id,
        materiale_id=nuovo.id,
        quantita_iniziale=quantita,
        quantita_residua=quantita,
        prezzo_acquisto=prezzo_acquisto_scontato or prezzo_acquisto_pieno or 0,
        prezzo_vendita_default=prezzo_vendita_default or 0,
        note="Carico iniziale",
        data_carico=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    db.add(carico)
    db.commit()

    return nuovo

def crea_carico_materiale(
    db: Session,
    utente_id: int,
    materiale_id: int,
    quantita: float,
    prezzo_acquisto: float,
    prezzo_vendita_default: float,
    note: str = ""
):
    materiale = (
        db.query(Materiale)
        .filter(
            Materiale.id == materiale_id,
            Materiale.utente_id == utente_id
        )
        .first()
    )

    if not materiale:
        return None

    carico = CaricoMateriale(
        utente_id=utente_id,
        materiale_id=materiale_id,

        quantita_iniziale=quantita,
        quantita_residua=quantita,

        prezzo_acquisto=prezzo_acquisto,
        prezzo_vendita_default=prezzo_vendita_default,

        note=note,
        data_carico=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    materiale.quantita += quantita

    movimento = MovimentoMagazzino(
        utente_id=utente_id,
        materiale_id=materiale_id,
        tipo="carico",
        quantita=quantita,
        note=f"Carico magazzino - € {prezzo_acquisto}",
        data_movimento=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    db.add(carico)
    db.add(movimento)

    db.commit()
    db.refresh(carico)

    return carico

def get_carichi_materiale(
    db: Session,
    utente_id: int,
    materiale_id: int
):
    return (
        db.query(CaricoMateriale)
        .filter(
            CaricoMateriale.utente_id == utente_id,
            CaricoMateriale.materiale_id == materiale_id,
            CaricoMateriale.quantita_residua > 0
        )
        .order_by(CaricoMateriale.id.asc())
        .all()
    )

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
    prezzo_unitario_cliente: float = 0,
    note: str = ""
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
    
    carico = (
        db.query(CaricoMateriale)
        .filter(
            CaricoMateriale.utente_id == utente_id,
            CaricoMateriale.materiale_id == materiale_id,
            CaricoMateriale.quantita_residua > 0
        )
        .order_by(CaricoMateriale.id.asc())
        .first()
    )

    if not carico:
        return "scorta_insufficiente"

    if carico.quantita_residua < quantita:
        return "scorta_insufficiente"

    carico.quantita_residua -= quantita
    costo_unitario = carico.prezzo_acquisto or 0
    materiale.quantita -= quantita

    usato = MaterialeUsatoLavoro(
        utente_id=utente_id,
        lavoro_id=lavoro_id,
        materiale_id=materiale_id,
        carico_id=carico.id,
        quantita=quantita,
        costo_unitario=costo_unitario,
        prezzo_unitario_cliente=prezzo_unitario_cliente,
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

def salva_impostazioni_azienda(
    db: Session,
    utente_id: int,
    nome_azienda: str,
    partita_iva: str,
    indirizzo: str,
    telefono: str,
    email: str,
    logo_path: str = None,
    codice_fiscale: str = "",
    regime_fiscale: str = "RF01",
    cap: str = "",
    citta: str = "",
    provincia: str = "",
    pec_indirizzo: str = "",
    pec_smtp_host: str = "",
    pec_smtp_port: int = 465,
    pec_smtp_password: str = "",
):
    azienda = db.query(ImpostazioniAzienda).filter(
        ImpostazioniAzienda.utente_id == utente_id
    ).first()

    if not azienda:
        azienda = ImpostazioniAzienda(utente_id=utente_id)
        db.add(azienda)

    azienda.nome_azienda = nome_azienda
    azienda.partita_iva = partita_iva
    azienda.codice_fiscale = codice_fiscale
    azienda.regime_fiscale = regime_fiscale or "RF01"
    azienda.indirizzo = indirizzo
    azienda.cap = cap
    azienda.citta = citta
    azienda.provincia = provincia
    azienda.telefono = telefono
    azienda.email = email

    if logo_path:
        azienda.logo_path = logo_path

    if pec_indirizzo is not None:
        azienda.pec_indirizzo = pec_indirizzo.strip() or None
    if pec_smtp_host is not None:
        azienda.pec_smtp_host = pec_smtp_host.strip() or None
    if pec_smtp_port:
        azienda.pec_smtp_port = int(pec_smtp_port)
    if pec_smtp_password is not None:
        azienda.pec_smtp_password = pec_smtp_password.strip() or None

    db.commit()
    db.refresh(azienda)
    return azienda

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

    totale_costo = 0
    totale_cliente = 0

    for riga in materiali_usati:
        quantita = riga.quantita or 0
        costo = riga.costo_unitario or 0
        prezzo_cliente = riga.prezzo_unitario_cliente or 0

        totale_costo += quantita * costo
        totale_cliente += quantita * prezzo_cliente

    return {
        "totale_costo": totale_costo,
        "totale_cliente": totale_cliente,
        "utile_materiali": totale_cliente - totale_costo
    }

def get_dashboard_pro(db: Session, utente_id: int):

    oggi = datetime.now().strftime("%Y-%m-%d")

    lavori = db.query(Lavoro).filter(
        Lavoro.utente_id == utente_id
    ).all()

    lavori_scaduti = [
        l for l in lavori
        if l.data_scadenza_pagamento
        and l.data_scadenza_pagamento < oggi
        and l.stato_pagamento != "pagato"
    ]

    totale_scaduto = sum(
        l.residuo_pagamento or 0
        for l in lavori_scaduti
    )

    lavori_totali = len(lavori)

    lavori_da_fare = sum(1 for l in lavori if l.stato == "da_fare")
    lavori_in_corso = sum(1 for l in lavori if l.stato == "in_corso")
    lavori_completati = sum(1 for l in lavori if l.stato == "completato")
    lavori_annullati = sum(1 for l in lavori if l.stato == "annullato")

    lavori_aperti = lavori_da_fare + lavori_in_corso

    totale_preventivi = sum(l.importo_preventivato or 0 for l in lavori)
    totale_consuntivi = sum(l.importo_consuntivo or 0 for l in lavori)
    totale_documenti = sum(l.totale_documento or 0 for l in lavori)

    totale_materiali = sum(l.totale_materiali or 0 for l in lavori)
    totale_manodopera = sum(l.totale_manodopera or 0 for l in lavori)
    margine_totale = sum(l.margine or 0 for l in lavori)

    costi_reali_totali = totale_materiali + totale_manodopera

    percentuale_completati = 0
    if lavori_totali > 0:
        percentuale_completati = round((lavori_completati / lavori_totali) * 100, 1)

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

    clienti = db.query(Cliente).filter(
        Cliente.utente_id == utente_id
    ).all()

    top_clienti = []

    for cliente in clienti:

        totale_cliente = sum(
            l.totale_documento or 0
            for l in lavori
            if l.cliente_id == cliente.id
        )

        top_clienti.append({
            "cliente": cliente,
            "totale": totale_cliente
        })

    top_clienti.sort(
        key=lambda x: x["totale"],
        reverse=True
    )

    top_clienti = top_clienti[:5]

    top_clienti_residuo = []

    for cliente in clienti:

        residuo_cliente = sum(
            l.residuo_pagamento or 0
            for l in lavori
            if l.cliente_id == cliente.id
        )

        if residuo_cliente > 0:
            top_clienti_residuo.append({
                "cliente": cliente,
                "residuo": residuo_cliente
            })

    top_clienti_residuo.sort(
        key=lambda x: x["residuo"],
        reverse=True
    )

    top_clienti_residuo = top_clienti_residuo[:5]

    clienti_totali = len(clienti)

    clienti_con_residuo = 0

    for cliente in clienti:
        residuo_cliente = sum(
            l.residuo_pagamento or 0
            for l in lavori
            if l.cliente_id == cliente.id
        )

        if residuo_cliente > 0:
            clienti_con_residuo += 1

    preventivi_mese = sum(l.importo_preventivato or 0 for l in lavori_mese)
    consuntivi_mese = sum(l.importo_consuntivo or 0 for l in lavori_mese)
    totale_documenti_mese = sum(l.totale_documento or 0 for l in lavori_mese)
    costi_mese = sum((l.totale_materiali or 0) + (l.totale_manodopera or 0) for l in lavori_mese)
    margine_mese = sum(l.margine or 0 for l in lavori_mese)

    ultimi_lavori = sorted(
        lavori,
        key=lambda l: l.data_creazione or "",
        reverse=True
    )[:5]

    totale_incassato = sum(l.importo_pagato or 0 for l in lavori)
    totale_da_incassare = sum(l.residuo_pagamento or 0 for l in lavori)

    lavori_pagati = sum(1 for l in lavori if l.stato_pagamento == "pagato")
    lavori_acconto = sum(1 for l in lavori if l.stato_pagamento == "acconto")
    lavori_da_pagare = sum(1 for l in lavori if l.stato_pagamento == "da_pagare")
    
    oggi = datetime.now().strftime("%Y-%m-%d")

    lavori_scaduti = [
        lavoro for lavoro in lavori
        if (
            lavoro.data_scadenza_pagamento
            and lavoro.data_scadenza_pagamento < oggi
            and lavoro.stato_pagamento != "pagato"
        )
    ]

    totale_scaduti = len(lavori_scaduti)

    totale_insoluti = sum(
        (l.residuo_pagamento or 0)
        for l in lavori_scaduti
    )
    
    totale_da_incassare_dashboard = (
        db.query(func.sum(Lavoro.residuo_pagamento))
        .filter(
            Lavoro.utente_id == utente_id,
            Lavoro.residuo_pagamento > 0
        )
        .scalar()
    ) or 0

    lavori_urgenti = [
        l for l in lavori
        if (l.residuo_pagamento or 0) > 0
    ]

    lavori_urgenti.sort(
        key=lambda l: (
            l.data_scadenza_pagamento or "9999-12-31",
            -(l.residuo_pagamento or 0)
        )
    )

    lavori_urgenti = lavori_urgenti[:5]

    materiali_totali = db.query(Materiale).filter(
        Materiale.utente_id == utente_id
    ).count()

    valore_magazzino = sum(
        (m.quantita or 0) * (m.prezzo_acquisto_scontato or m.prezzo_acquisto_pieno or 0)
        for m in db.query(Materiale).filter(Materiale.utente_id == utente_id).all()
    )

    documenti_pdf = db.query(DocumentoPDF).filter(
        DocumentoPDF.utente_id == utente_id
    ).all()

    numero_documenti_pdf = len(documenti_pdf)
    
    ultimi_pagamenti = (
        db.query(PagamentoLavoro)
        .filter(PagamentoLavoro.utente_id == utente_id)
        .order_by(PagamentoLavoro.id.desc())
        .limit(5)
        .all()
    )

    ultimi_movimenti_magazzino = (
        db.query(MovimentoMagazzino)
        .filter(MovimentoMagazzino.utente_id == utente_id)
        .order_by(MovimentoMagazzino.id.desc())
        .limit(5)
        .all()
    )

    materiali_usati = (
        db.query(MaterialeUsatoLavoro)
        .filter(MaterialeUsatoLavoro.utente_id == utente_id)
        .all()
    )

    riepilogo_materiali_usati = {}

    for riga in materiali_usati:
        materiale = db.query(Materiale).filter(Materiale.id == riga.materiale_id).first()

        if materiale:
            nome = materiale.nome

            if nome not in riepilogo_materiali_usati:
                riepilogo_materiali_usati[nome] = {
                    "nome": nome,
                    "quantita": 0,
                    "valore": 0
                }

            riepilogo_materiali_usati[nome]["quantita"] += riga.quantita or 0
            riepilogo_materiali_usati[nome]["valore"] += (riga.quantita or 0) * (riga.costo_unitario or 0)

    materiali_piu_usati = sorted(
        riepilogo_materiali_usati.values(),
        key=lambda x: x["quantita"],
        reverse=True
    )[:5]

    clienti_da_sollecitare = []

    for cliente in clienti:
        lavori_cliente_scaduti = [
            l for l in lavori
            if l.cliente_id == cliente.id
            and (l.residuo_pagamento or 0) > 0
            and l.data_scadenza_pagamento
            and l.data_scadenza_pagamento < oggi
        ]

        totale_residuo_scaduto = sum(
            l.residuo_pagamento or 0
            for l in lavori_cliente_scaduti
        )

        if totale_residuo_scaduto > 0:
            clienti_da_sollecitare.append({
                "cliente": cliente,
                "totale": totale_residuo_scaduto,
                "numero_lavori": len(lavori_cliente_scaduti)
            })

    clienti_da_sollecitare.sort(
        key=lambda x: x["totale"],
        reverse=True
    )

    clienti_da_sollecitare = clienti_da_sollecitare[:5]

    valore_medio_lavoro = 0
    margine_medio_lavoro = 0

    if lavori_totali > 0:
        valore_medio_lavoro = totale_documenti / lavori_totali
        margine_medio_lavoro = margine_totale / lavori_totali

    impostazioni = get_impostazioni_azienda(db, utente_id)
    obiettivo_mensile = impostazioni.obiettivo_mensile or 5000

    percentuale_obiettivo_mese = 0
    if obiettivo_mensile > 0:
        percentuale_obiettivo_mese = min(
            round((totale_documenti_mese / obiettivo_mensile) * 100, 1),
            100
        )

    mesi = {}

    for lavoro in lavori:
        if lavoro.data_creazione:
            mese = lavoro.data_creazione[:7]  # es. 2026-05

            if mese not in mesi:
                mesi[mese] = {
                    "fatturato": 0,
                    "costi": 0,
                    "margine": 0
                }

            mesi[mese]["fatturato"] += lavoro.totale_documento or 0
            mesi[mese]["costi"] += (lavoro.totale_materiali or 0) + (lavoro.totale_manodopera or 0)
            mesi[mese]["margine"] += lavoro.margine or 0

    mesi_ordinati = sorted(mesi.keys())[-12:]

    grafico_mesi_labels = mesi_ordinati
    grafico_mesi_fatturato = [mesi[m]["fatturato"] for m in mesi_ordinati]
    grafico_mesi_costi = [mesi[m]["costi"] for m in mesi_ordinati]
    grafico_mesi_margine = [mesi[m]["margine"] for m in mesi_ordinati]

    scadenzario = [
        lavoro for lavoro in lavori
        if lavoro.data_scadenza_pagamento
        and (lavoro.residuo_pagamento or 0) > 0
        and lavoro.stato_pagamento != "pagato"
    ]

    scadenzario.sort(
        key=lambda l: l.data_scadenza_pagamento or "9999-12-31"
    )

    scadenzario = scadenzario[:10]

    # ── Confronto mese precedente ─────────────────────────────────────────────
    from datetime import date as _date_kpi, timedelta as _td_kpi
    _today = _date_kpi.today()
    if _today.month == 1:
        _mese_prec = f"{_today.year - 1}-12"
    else:
        _mese_prec = f"{_today.year}-{_today.month - 1:02d}"

    lavori_mese_prec = [l for l in lavori if l.data_creazione and l.data_creazione.startswith(_mese_prec)]
    totale_documenti_mese_prec = sum(l.totale_documento or 0 for l in lavori_mese_prec)
    margine_mese_prec = sum(l.margine or 0 for l in lavori_mese_prec)

    if totale_documenti_mese_prec > 0:
        delta_fatturato_pct = round(
            (totale_documenti_mese - totale_documenti_mese_prec) / totale_documenti_mese_prec * 100, 1
        )
    elif totale_documenti_mese > 0:
        delta_fatturato_pct = 100.0
    else:
        delta_fatturato_pct = 0.0

    # ── Lavori in scadenza questa settimana ───────────────────────────────────
    _fine_sett = (_today + _td_kpi(days=7)).isoformat()
    _oggi_iso = _today.isoformat()
    lavori_scadenza_settimana = sorted(
        [l for l in lavori
         if l.data_scadenza_pagamento
         and _oggi_iso <= l.data_scadenza_pagamento <= _fine_sett
         and (l.residuo_pagamento or 0) > 0],
        key=lambda l: l.data_scadenza_pagamento
    )

    # ── % incassi per stato ───────────────────────────────────────────────────
    pct_pagato_val = round(lavori_pagati / lavori_totali * 100, 1) if lavori_totali else 0.0
    pct_parziale_val = round(lavori_acconto / lavori_totali * 100, 1) if lavori_totali else 0.0
    pct_da_pagare_val = round(lavori_da_pagare / lavori_totali * 100, 1) if lavori_totali else 0.0

    # ── FatturaPA stats anno corrente ─────────────────────────────────────────
    fatture_anno_list = db.query(FatturaEmessa).filter(
        FatturaEmessa.utente_id == utente_id,
        FatturaEmessa.anno == _today.year
    ).all()
    fatture_anno_count = len(fatture_anno_list)
    fatturato_fatturapa_anno = sum(f.importo_totale or 0 for f in fatture_anno_list)
    fatture_mese_count = sum(
        1 for f in fatture_anno_list
        if f.data_emissione and f.data_emissione.startswith(mese_corrente)
    )

    # ── Preventivi (stati preventivo/preventivo_inviato/preventivo_accettato) ──
    _stati_preventivo = {"preventivo", "preventivo_inviato", "preventivo_accettato"}
    lavori_preventivi = sum(1 for l in lavori if l.stato in _stati_preventivo)

    # ── Previsione incassi prossimi 30/60/90 giorni ───────────────────────────
    _d30 = (_today + _td_kpi(days=30)).isoformat()
    _d60 = (_today + _td_kpi(days=60)).isoformat()
    _d90 = (_today + _td_kpi(days=90)).isoformat()
    _oggi_iso = _today.isoformat()

    def _prev_incassi(fine: str) -> float:
        return sum(
            l.residuo_pagamento or 0
            for l in lavori
            if l.data_scadenza_pagamento
            and _oggi_iso <= l.data_scadenza_pagamento <= fine
            and (l.residuo_pagamento or 0) > 0
        )

    prev_incassi_30g = round(_prev_incassi(_d30), 2)
    prev_incassi_60g = round(_prev_incassi(_d60), 2)
    prev_incassi_90g = round(_prev_incassi(_d90), 2)

    # ── Confronto anno corrente vs anno precedente ────────────────────────────
    _anno_corr = str(_today.year)
    _anno_prec = str(_today.year - 1)
    fatturato_anno_corrente = sum(
        l.totale_documento or 0 for l in lavori
        if (l.data_creazione or "").startswith(_anno_corr)
    )
    fatturato_anno_prec = sum(
        l.totale_documento or 0 for l in lavori
        if (l.data_creazione or "").startswith(_anno_prec)
    )
    if fatturato_anno_prec > 0:
        delta_anno_pct = round(
            (fatturato_anno_corrente - fatturato_anno_prec) / fatturato_anno_prec * 100, 1
        )
    elif fatturato_anno_corrente > 0:
        delta_anno_pct = 100.0
    else:
        delta_anno_pct = 0.0

    # ── Grafico 12 mesi anno corrente con obiettivo mensile ───────────────────
    _mesi_anno = [f"{_anno_corr}-{m:02d}" for m in range(1, 13)]
    grafico_anno_labels = _mesi_anno
    grafico_anno_fatturato = [
        round(sum(l.totale_documento or 0 for l in lavori if (l.data_creazione or "").startswith(m)), 2)
        for m in _mesi_anno
    ]
    grafico_anno_obiettivo = [round(obiettivo_mensile, 2)] * 12

    # ── Lavori di oggi ────────────────────────────────────────────────────────
    _stati_operativi = {"da_fare", "in_corso"}
    lavori_oggi = sorted(
        [l for l in lavori if l.data_lavoro == oggi and l.stato in _stati_operativi],
        key=lambda l: (0 if l.stato == "in_corso" else 1, l.id)
    )

    return {
        "lavori_oggi": lavori_oggi,
        "lavori_totali": lavori_totali,
        "lavori_da_fare": lavori_da_fare,
        "lavori_in_corso": lavori_in_corso,
        "lavori_aperti": lavori_aperti,
        "lavori_completati": lavori_completati,
        "lavori_annullati": lavori_annullati,
        "percentuale_completati": percentuale_completati,

        "totale_preventivi": totale_preventivi,
        "totale_consuntivi": totale_consuntivi,
        "totale_documenti": totale_documenti,
        "totale_materiali": totale_materiali,
        "totale_manodopera": totale_manodopera,
        "costi_reali_totali": costi_reali_totali,
        "margine_totale": margine_totale,

        "lavori_migliori": lavori_migliori,
        "lavori_peggiori": lavori_peggiori,
        "materiali_scorte_basse": materiali_scorte_basse,

        "lavori_mese_count": lavori_mese_count,
        "clienti_totali": clienti_totali,
        "clienti_con_residuo": clienti_con_residuo,
        "top_clienti": top_clienti,
        "top_clienti_residuo": top_clienti_residuo,
        "lavori_urgenti": lavori_urgenti,
        "preventivi_mese": preventivi_mese,
        "consuntivi_mese": consuntivi_mese,
        "totale_documenti_mese": totale_documenti_mese,
        "costi_mese": costi_mese,
        "margine_mese": margine_mese,

        "ultimi_lavori": ultimi_lavori,
        "totale_incassato": totale_incassato,
        "totale_da_incassare": totale_da_incassare,
        "lavori_pagati": lavori_pagati,
        "lavori_acconto": lavori_acconto,
        "lavori_da_pagare": lavori_da_pagare,
        "lavori_scaduti": lavori_scaduti,
        "totale_scaduti": totale_insoluti,
        "totale_scaduto": totale_insoluti,
        "totale_insoluti": totale_insoluti,
        "materiali_totali": materiali_totali,
        "valore_magazzino": valore_magazzino,
        "numero_documenti_pdf": numero_documenti_pdf,
        "ultimi_pagamenti": ultimi_pagamenti,
        "ultimi_movimenti_magazzino": ultimi_movimenti_magazzino,
        "materiali_piu_usati": materiali_piu_usati,
        "clienti_da_sollecitare": clienti_da_sollecitare,
        "valore_medio_lavoro": valore_medio_lavoro,
        "margine_medio_lavoro": margine_medio_lavoro,
        "obiettivo_mensile": obiettivo_mensile,
        "percentuale_obiettivo_mese": percentuale_obiettivo_mese,
        "grafico_mesi_labels": grafico_mesi_labels,
        "grafico_mesi_fatturato": grafico_mesi_fatturato,
        "grafico_mesi_costi": grafico_mesi_costi,
        "grafico_mesi_margine": grafico_mesi_margine,
        "scadenzario": scadenzario,
        "totale_documenti_mese_prec": totale_documenti_mese_prec,
        "margine_mese_prec": margine_mese_prec,
        "delta_fatturato_pct": delta_fatturato_pct,
        "lavori_scadenza_settimana": lavori_scadenza_settimana,
        "pct_pagato_val": pct_pagato_val,
        "pct_parziale_val": pct_parziale_val,
        "pct_da_pagare_val": pct_da_pagare_val,
        "fatture_anno_count": fatture_anno_count,
        "fatturato_fatturapa_anno": fatturato_fatturapa_anno,
        "fatture_mese_count": fatture_mese_count,
        "lavori_preventivi": lavori_preventivi,
        "prev_incassi_30g": prev_incassi_30g,
        "prev_incassi_60g": prev_incassi_60g,
        "prev_incassi_90g": prev_incassi_90g,
        "fatturato_anno_corrente": fatturato_anno_corrente,
        "fatturato_anno_prec": fatturato_anno_prec,
        "delta_anno_pct": delta_anno_pct,
        "grafico_anno_labels": grafico_anno_labels,
        "grafico_anno_fatturato": grafico_anno_fatturato,
        "grafico_anno_obiettivo": grafico_anno_obiettivo,
    }

def get_tutti_carichi_disponibili(db: Session, utente_id: int):
    return (
        db.query(CaricoMateriale)
        .filter(
            CaricoMateriale.utente_id == utente_id,
            CaricoMateriale.quantita_residua > 0
        )
        .order_by(CaricoMateriale.id.asc())
        .all()
    )

def get_tutti_carichi_materiale(db: Session, utente_id: int, materiale_id: int):
    return (
        db.query(CaricoMateriale)
        .filter(
            CaricoMateriale.utente_id == utente_id,
            CaricoMateriale.materiale_id == materiale_id
        )
        .order_by(CaricoMateriale.id.desc())
        .all()
    )

def salva_foto_lavoro(
    db: Session,
    utente_id: int,
    lavoro_id: int,
    nome_file: str,
    percorso_file: str,
    descrizione: str = ""
):
    foto = FotoLavoro(
        utente_id=utente_id,
        lavoro_id=lavoro_id,
        nome_file=nome_file,
        percorso_file=percorso_file,
        descrizione=descrizione,
        data_creazione=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    db.add(foto)
    db.commit()
    db.refresh(foto)

    return foto


def elimina_foto_lavoro(db: Session, foto_id: int, utente_id: int):
    from pathlib import Path
    foto = db.query(FotoLavoro).filter(FotoLavoro.id == foto_id, FotoLavoro.utente_id == utente_id).first()
    if foto:
        try:
            if foto.percorso_file and foto.percorso_file.startswith("http"):
                from app.services.cloudinary_service import elimina_immagine
                elimina_immagine(foto.percorso_file)
            else:
                Path(foto.percorso_file).unlink(missing_ok=True)
        except Exception:
            pass
        db.delete(foto)
        db.commit()


def get_foto_lavoro(db: Session, utente_id: int, lavoro_id: int):
    return (
        db.query(FotoLavoro)
        .filter(
            FotoLavoro.utente_id == utente_id,
            FotoLavoro.lavoro_id == lavoro_id
        )
        .order_by(FotoLavoro.id.desc())
        .all()
    )

def get_pagamenti_lavoro(db: Session, utente_id: int, lavoro_id: int):
    return (
        db.query(PagamentoLavoro)
        .filter(
            PagamentoLavoro.utente_id == utente_id,
            PagamentoLavoro.lavoro_id == lavoro_id
        )
        .order_by(PagamentoLavoro.data_pagamento.desc())
        .all()
    )


def aggiungi_pagamento_lavoro(
    db: Session,
    utente_id: int,
    lavoro_id: int,
    data_pagamento: str,
    importo: float,
    metodo: str,
    note: str
):
    lavoro = (
        db.query(Lavoro)
        .filter(
            Lavoro.id == lavoro_id,
            Lavoro.utente_id == utente_id
        )
        .first()
    )

    if not lavoro:
        return None

    ultimo_numero = (
        db.query(PagamentoLavoro)
        .filter(PagamentoLavoro.utente_id == utente_id)
        .order_by(PagamentoLavoro.numero_ricevuta.desc())
        .first()
    )

    if ultimo_numero and ultimo_numero.numero_ricevuta:
        nuovo_numero = ultimo_numero.numero_ricevuta + 1
    else:
        nuovo_numero = 1

    pagamento = PagamentoLavoro(
        utente_id=utente_id,
        lavoro_id=lavoro_id,
        numero_ricevuta=nuovo_numero,
        data_pagamento=data_pagamento,
        importo=importo,
        metodo=metodo,
        note=note,
        data_creazione=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    db.add(pagamento)
    db.commit()

    aggiorna_totale_pagamenti_lavoro(db, utente_id, lavoro_id)

    db.refresh(pagamento)
    return pagamento


def aggiorna_totale_pagamenti_lavoro(db: Session, utente_id: int, lavoro_id: int):
    lavoro = (
        db.query(Lavoro)
        .filter(
            Lavoro.id == lavoro_id,
            Lavoro.utente_id == utente_id
        )
        .first()
    )

    if not lavoro:
        return None

    pagamenti = get_pagamenti_lavoro(db, utente_id, lavoro_id)

    totale_pagato = sum(p.importo or 0 for p in pagamenti)
    totale_documento = lavoro.totale_documento or 0

    lavoro.importo_pagato = totale_pagato
    lavoro.residuo_pagamento = max(0.0, totale_documento - totale_pagato)

    if totale_pagato <= 0:
        lavoro.stato_pagamento = "da_pagare"
    elif totale_pagato < totale_documento:
        lavoro.stato_pagamento = "acconto"
    else:
        lavoro.stato_pagamento = "pagato"

    db.commit()
    db.refresh(lavoro)

    return lavoro

def elimina_pagamento_lavoro(
    db: Session,
    utente_id: int,
    pagamento_id: int
):
    pagamento = (
        db.query(PagamentoLavoro)
        .filter(
            PagamentoLavoro.id == pagamento_id,
            PagamentoLavoro.utente_id == utente_id
        )
        .first()
    )

    if not pagamento:
        return None

    lavoro_id = pagamento.lavoro_id

    db.delete(pagamento)
    db.commit()

    aggiorna_totale_pagamenti_lavoro(
        db,
        utente_id,
        lavoro_id
    )

    return lavoro_id

def get_pagamento_lavoro_by_id(
    db: Session,
    utente_id: int,
    pagamento_id: int
):
    return (
        db.query(PagamentoLavoro)
        .filter(
            PagamentoLavoro.id == pagamento_id,
            PagamentoLavoro.utente_id == utente_id
        )
        .first()
    )

def get_totali_lavori(lavori):
    totale_documenti = sum(l.totale_documento or 0 for l in lavori)
    totale_pagato = sum(l.importo_pagato or 0 for l in lavori)
    totale_residuo = sum(l.residuo_pagamento or 0 for l in lavori)

    return {
        "totale_documenti": totale_documenti,
        "totale_pagato": totale_pagato,
        "totale_residuo": totale_residuo
    }

def elimina_materiale_usato_lavoro(
    db: Session,
    utente_id: int,
    usato_id: int
):
    usato = (
        db.query(MaterialeUsatoLavoro)
        .filter(
            MaterialeUsatoLavoro.id == usato_id,
            MaterialeUsatoLavoro.utente_id == utente_id
        )
        .first()
    )

    if not usato:
        return None

    lavoro_id = usato.lavoro_id
    materiale_id = usato.materiale_id
    quantita = usato.quantita or 0
    carico_id = usato.carico_id

    materiale = db.query(Materiale).filter(
        Materiale.id == materiale_id,
        Materiale.utente_id == utente_id
    ).first()

    if materiale:
        materiale.quantita += quantita

    if carico_id:
        carico = db.query(CaricoMateriale).filter(
            CaricoMateriale.id == carico_id,
            CaricoMateriale.utente_id == utente_id
        ).first()

        if carico:
            carico.quantita_residua += quantita

    movimento = MovimentoMagazzino(
        utente_id=utente_id,
        materiale_id=materiale_id,
        tipo="carico",
        quantita=quantita,
        note=f"Ripristino per eliminazione materiale usato nel lavoro ID {lavoro_id}",
        data_movimento=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    db.add(movimento)
    db.delete(usato)
    db.commit()

    return lavoro_id

def modifica_materiale_usato_lavoro(
    db: Session,
    utente_id: int,
    usato_id: int,
    quantita: float,
    prezzo_unitario_cliente: float,
    note: str
):
    usato = (
        db.query(MaterialeUsatoLavoro)
        .filter(
            MaterialeUsatoLavoro.id == usato_id,
            MaterialeUsatoLavoro.utente_id == utente_id
        )
        .first()
    )

    if not usato:
        return None

    lavoro_id = usato.lavoro_id
    differenza = quantita - (usato.quantita or 0)

    materiale = (
        db.query(Materiale)
        .filter(
            Materiale.id == usato.materiale_id,
            Materiale.utente_id == utente_id
        )
        .first()
    )

    if differenza > 0:
        if not materiale or materiale.quantita < differenza:
            return None

        materiale.quantita -= differenza

        movimento = MovimentoMagazzino(
            utente_id=utente_id,
            materiale_id=usato.materiale_id,
            tipo="scarico",
            quantita=differenza,
            note=f"Scarico aggiuntivo per modifica materiale usato nel lavoro ID {lavoro_id}",
            data_movimento=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        db.add(movimento)

        if usato.carico_id:
            carico = (
                db.query(CaricoMateriale)
                .filter(
                    CaricoMateriale.id == usato.carico_id,
                    CaricoMateriale.utente_id == utente_id
                )
                .first()
            )

            if carico:
                if carico.quantita_residua < differenza:
                    return None

                carico.quantita_residua -= differenza

    elif differenza < 0:
        ritorno = abs(differenza)

        movimento = MovimentoMagazzino(
            utente_id=utente_id,
            materiale_id=usato.materiale_id,
            tipo="carico",
            quantita=ritorno,
            note=f"Ripristino per modifica materiale usato nel lavoro ID {lavoro_id}",
            data_movimento=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        db.add(movimento)

        if materiale:
            materiale.quantita += ritorno

        if usato.carico_id:
            carico = (
                db.query(CaricoMateriale)
                .filter(
                    CaricoMateriale.id == usato.carico_id,
                    CaricoMateriale.utente_id == utente_id
                )
                .first()
            )

            if carico:
                carico.quantita_residua += ritorno

    usato.quantita = quantita
    usato.prezzo_unitario_cliente = prezzo_unitario_cliente
    usato.note = note

    db.commit()

    return lavoro_id

def get_riepilogo_cliente(db: Session, cliente_id: int, utente_id: int):
    lavori = (
        db.query(Lavoro)
        .filter(
            Lavoro.cliente_id == cliente_id,
            Lavoro.utente_id == utente_id
        )
        .all()
    )

    oggi = datetime.now().strftime("%Y-%m-%d")

    totale_lavori = len(lavori)
    totale_documenti = sum(l.totale_documento or 0 for l in lavori)
    totale_pagato = sum(l.importo_pagato or 0 for l in lavori)
    totale_residuo = sum(l.residuo_pagamento or 0 for l in lavori)

    lavori_scaduti = [
        l for l in lavori
        if l.data_scadenza_pagamento
        and l.data_scadenza_pagamento < oggi
        and (l.residuo_pagamento or 0) > 0
    ]

    totale_scaduto = sum(l.residuo_pagamento or 0 for l in lavori_scaduti)

    percentuale_incasso = 0
    if totale_documenti > 0:
        percentuale_incasso = round(
            (totale_pagato / totale_documenti) * 100,
            1
        )

    # Ultima visita: ultimo lavoro non-preventivo, non-annullato, già avvenuto (data <= oggi)
    stati_visita = {"completato", "in_corso", "da_fare"}
    lavori_reali = sorted(
        [l for l in lavori if l.stato in stati_visita and l.data_lavoro and l.data_lavoro <= oggi],
        key=lambda l: l.data_lavoro,
        reverse=True,
    )
    ultima_visita = None
    if lavori_reali:
        ul = lavori_reali[0]
        ultima_visita = {"data": ul.data_lavoro, "titolo": ul.titolo, "id": ul.id}

    # Fatturato ultimi 12 mesi
    from datetime import date as _date, timedelta as _timedelta
    un_anno_fa = (_date.today() - _timedelta(days=365)).strftime("%Y-%m-%d")
    fatturato_12mesi = sum(
        l.totale_documento or 0
        for l in lavori
        if l.data_lavoro and l.data_lavoro >= un_anno_fa and (l.totale_documento or 0) > 0
    )

    # Cliente dal: data del primo lavoro
    date_lavori = sorted([l.data_lavoro for l in lavori if l.data_lavoro])
    cliente_dal = date_lavori[0] if date_lavori else None

    # Lavori completati
    n_lavori_completati = sum(1 for l in lavori if l.stato == "completato")

    # Puntualità — conta pagamenti aperti oltre scadenza (dato attuale, non storico)
    n_ritardi = len(lavori_scaduti)
    if n_ritardi == 0:
        puntualita_rating = "ok"
        puntualita_label = "Paga puntuale"
    elif n_ritardi <= 2:
        puntualita_rating = "warn"
        puntualita_label = f"{n_ritardi} pagament{'o' if n_ritardi == 1 else 'i'} scadut{'o' if n_ritardi == 1 else 'i'}"
    else:
        puntualita_rating = "risk"
        puntualita_label = f"{n_ritardi} pagamenti scaduti"

    return {
        "totale_lavori": totale_lavori,
        "totale_documenti": totale_documenti,
        "totale_pagato": totale_pagato,
        "totale_residuo": totale_residuo,
        "lavori_scaduti": lavori_scaduti,
        "totale_scaduto": totale_scaduto,
        "percentuale_incasso": percentuale_incasso,
        "ultima_visita": ultima_visita,
        "fatturato_12mesi": fatturato_12mesi,
        "cliente_dal": cliente_dal,
        "n_lavori_completati": n_lavori_completati,
        "puntualita_rating": puntualita_rating,
        "puntualita_label": puntualita_label,
    }

def get_documenti_pdf_by_cliente(db: Session, utente_id: int, cliente_id: int):
    return (
        db.query(DocumentoPDF)
        .join(Lavoro, DocumentoPDF.lavoro_id == Lavoro.id)
        .filter(
            DocumentoPDF.utente_id == utente_id,
            Lavoro.cliente_id == cliente_id
        )
        .order_by(DocumentoPDF.id.desc())
        .all()
    )

def get_pagamenti_by_cliente(db: Session, utente_id: int, cliente_id: int):
    return (
        db.query(PagamentoLavoro)
        .join(Lavoro, PagamentoLavoro.lavoro_id == Lavoro.id)
        .filter(
            PagamentoLavoro.utente_id == utente_id,
            Lavoro.cliente_id == cliente_id
        )
        .order_by(PagamentoLavoro.data_pagamento.desc())
        .all()
    )

def salva_allegato_lavoro(
    db: Session,
    utente_id: int,
    lavoro_id: int,
    nome_file: str,
    percorso_file: str,
    tipo_file: str = "",
    descrizione: str = ""
):
    allegato = AllegatoLavoro(
        utente_id=utente_id,
        lavoro_id=lavoro_id,
        nome_file=nome_file,
        percorso_file=percorso_file,
        tipo_file=tipo_file,
        descrizione=descrizione,
        data_creazione=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    db.add(allegato)
    db.commit()
    db.refresh(allegato)

    return allegato


def get_allegati_lavoro(
    db: Session,
    utente_id: int,
    lavoro_id: int
):
    return (
        db.query(AllegatoLavoro)
        .filter(
            AllegatoLavoro.utente_id == utente_id,
            AllegatoLavoro.lavoro_id == lavoro_id
        )
        .order_by(AllegatoLavoro.id.desc())
        .all()
    )
def get_allegato_by_id(
    db: Session,
    allegato_id: int,
    utente_id: int
):
    return (
        db.query(AllegatoLavoro)
        .filter(
            AllegatoLavoro.id == allegato_id,
            AllegatoLavoro.utente_id == utente_id
        )
        .first()
    )


def elimina_allegato(
    db: Session,
    allegato_id: int,
    utente_id: int
):
    allegato = get_allegato_by_id(
        db,
        allegato_id,
        utente_id
    )

    if not allegato:
        return None

    db.delete(allegato)
    db.commit()

    return True

def get_tutti_allegati(
    db: Session,
    utente_id: int
):
    return (
        db.query(AllegatoLavoro)
        .filter(AllegatoLavoro.utente_id == utente_id)
        .order_by(AllegatoLavoro.id.desc())
        .all()
    )
def get_or_create_cal_token(db: Session, utente_id: int) -> str:
    import secrets
    from app.models import Utente as _Utente
    utente = db.query(_Utente).filter(_Utente.id == utente_id).first()
    if not utente:
        return ""
    if not getattr(utente, "cal_token", None):
        utente.cal_token = secrets.token_urlsafe(32)
        db.commit()
    return utente.cal_token


def get_agenda_scadenzario(db: Session, utente_id: int):
    oggi = datetime.now().strftime("%Y-%m-%d")

    data_oggi = datetime.now()
    data_7_giorni = data_oggi + timedelta(days=7)
    limite_7_giorni = data_7_giorni.strftime("%Y-%m-%d")

    lavori = (
        db.query(Lavoro)
        .filter(Lavoro.utente_id == utente_id)
        .all()
    )

    lavori_oggi = [
        l for l in lavori
        if l.data_lavoro == oggi
    ]

    lavori_aperti = [
        l for l in lavori
        if l.stato in ["da_fare", "in_corso"]
    ]

    pagamenti_scaduti = [
        l for l in lavori
        if l.data_scadenza_pagamento
        and l.data_scadenza_pagamento < oggi
        and (l.residuo_pagamento or 0) > 0
    ]

    prossime_scadenze = [
        l for l in lavori
        if l.data_scadenza_pagamento
        and l.data_scadenza_pagamento >= oggi
        and (l.residuo_pagamento or 0) > 0
    ]

    prossimi_7_giorni = [
        l for l in lavori
        if l.data_scadenza_pagamento
        and oggi <= l.data_scadenza_pagamento <= limite_7_giorni
        and (l.residuo_pagamento or 0) > 0
    ]

    lavori_priorita_alta = [
        l for l in lavori
        if l.stato in ["da_fare", "in_corso"]
        and l.priorita == "alta"
    ]

    prossime_scadenze.sort(
        key=lambda l: l.data_scadenza_pagamento or "9999-12-31"
    )

    prossimi_7_giorni.sort(
        key=lambda l: l.data_scadenza_pagamento or "9999-12-31"
    )

    pagamenti_scaduti.sort(
        key=lambda l: l.data_scadenza_pagamento or "9999-12-31"
    )

    lavori_aperti.sort(
        key=lambda l: (
            l.data_lavoro or "9999-12-31",
            l.priorita or "normale"
        )
    )

    lavori_priorita_alta.sort(
        key=lambda l: l.data_lavoro or "9999-12-31"
    )

    totale_scaduti = sum(
        l.residuo_pagamento or 0
        for l in pagamenti_scaduti
    )

    totale_prossime_scadenze = sum(
        l.residuo_pagamento or 0
        for l in prossime_scadenze
    )

    totale_7_giorni = sum(
        l.residuo_pagamento or 0
        for l in prossimi_7_giorni
    )

    return {
        "oggi": oggi,
        "lavori_oggi": lavori_oggi,
        "lavori_aperti": lavori_aperti,
        "pagamenti_scaduti": pagamenti_scaduti,
        "prossime_scadenze": prossime_scadenze[:10],
        "prossimi_7_giorni": prossimi_7_giorni,
        "lavori_priorita_alta": lavori_priorita_alta,
    }
def get_analisi_economica(db: Session, utente_id: int):

    lavori = (
        db.query(Lavoro)
        .filter(Lavoro.utente_id == utente_id)
        .all()
    )

    totale_documenti = sum(
        l.totale_documento or 0
        for l in lavori
    )

    totale_incassato = sum(
        l.importo_pagato or 0
        for l in lavori
    )

    totale_residuo = sum(
        l.residuo_pagamento or 0
        for l in lavori
    )

    totale_margine = sum(
        l.margine or 0
        for l in lavori
    )

    lavori_perdita = [
        l for l in lavori
        if (l.margine or 0) < 0
    ]

    percentuale_incasso = 0
    percentuale_margine = 0

    if totale_documenti > 0:
        percentuale_incasso = round(
            (totale_incassato / totale_documenti) * 100,
            1
        )

        percentuale_margine = round(
            (totale_margine / totale_documenti) * 100,
            1
        )

    top_lavori_redditizi = sorted(
        lavori,
        key=lambda l: l.margine or 0,
        reverse=True
    )[:10]

    lavori_da_incassare = [
        l for l in lavori
        if (l.residuo_pagamento or 0) > 0
    ]

    lavori_da_incassare.sort(
        key=lambda l: l.residuo_pagamento or 0,
        reverse=True
    )

    return {
        "totale_documenti": totale_documenti,
        "totale_incassato": totale_incassato,
        "totale_residuo": totale_residuo,
        "totale_margine": totale_margine,
        "lavori_perdita": lavori_perdita,
        "percentuale_incasso": percentuale_incasso,
        "percentuale_margine": percentuale_margine,
        "top_lavori_redditizi": top_lavori_redditizi,
        "lavori_da_incassare": lavori_da_incassare[:10],
    }
def get_notifiche_dashboard(
    db: Session,
    utente_id: int
):
    oggi = datetime.now().strftime("%Y-%m-%d")

    lavori = (
        db.query(Lavoro)
        .filter(Lavoro.utente_id == utente_id)
        .all()
    )

    materiali = (
        db.query(Materiale)
        .filter(Materiale.utente_id == utente_id)
        .all()
    )

    pagamenti_scaduti = sum(
        1 for l in lavori
        if l.data_scadenza_pagamento
        and l.data_scadenza_pagamento < oggi
        and (l.residuo_pagamento or 0) > 0
    )

    lavori_oggi = sum(
        1 for l in lavori
        if l.data_lavoro == oggi
    )

    scorte_basse = sum(
        1 for m in materiali
        if (m.quantita or 0) <= (m.scorta_minima or 0)
    )

    lavori_aperti = sum(
        1 for l in lavori
        if l.stato in ["da_fare", "in_corso"]
    )

    oggi_str = oggi

    garanzie = db.query(Garanzia).filter(Garanzia.utente_id == utente_id).all()
    tra_30 = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    garanzie_scadenza = sum(
        1 for g in garanzie
        if g.data_scadenza and g.data_scadenza <= tra_30
    )

    return {
        "pagamenti_scaduti": pagamenti_scaduti,
        "lavori_oggi": lavori_oggi,
        "scorte_basse": scorte_basse,
        "lavori_aperti": lavori_aperti,
        "garanzie_scadenza": garanzie_scadenza,
    }


def _aggiungi_mesi(data_str: str, mesi: int) -> str:
    d = datetime.strptime(data_str, "%Y-%m-%d")
    target_month = d.month + mesi
    target_year = d.year + (target_month - 1) // 12
    target_month = ((target_month - 1) % 12) + 1
    max_day = calendar.monthrange(target_year, target_month)[1]
    return f"{target_year:04d}-{target_month:02d}-{min(d.day, max_day):02d}"


def crea_garanzia(
    db: Session,
    utente_id: int,
    cliente_id: int,
    lavoro_id: int | None,
    descrizione: str,
    data_installazione: str,
    durata_mesi: int,
    note: str,
) -> Garanzia:
    g = Garanzia(
        utente_id=utente_id,
        cliente_id=cliente_id,
        lavoro_id=lavoro_id or None,
        descrizione=descrizione,
        data_installazione=data_installazione,
        durata_mesi=durata_mesi,
        data_scadenza=_aggiungi_mesi(data_installazione, durata_mesi),
        note=note or None,
        data_creazione=datetime.now().strftime("%Y-%m-%d"),
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def get_garanzie(db: Session, utente_id: int):
    return (
        db.query(Garanzia)
        .filter(Garanzia.utente_id == utente_id)
        .order_by(Garanzia.data_scadenza)
        .all()
    )


def get_garanzia(db: Session, garanzia_id: int, utente_id: int):
    return db.query(Garanzia).filter(
        Garanzia.id == garanzia_id,
        Garanzia.utente_id == utente_id,
    ).first()


def elimina_garanzia(db: Session, garanzia_id: int, utente_id: int):
    g = get_garanzia(db, garanzia_id, utente_id)
    if g:
        db.delete(g)
        db.commit()


def get_garanzie_tutte(db: Session):
    return db.query(Garanzia).all()


def genera_token_firma(db: Session, lavoro_id: int, utente_id: int):
    lavoro = get_lavoro_by_id(db, lavoro_id, utente_id)
    if not lavoro:
        return None
    if not lavoro.token_firma:
        lavoro.token_firma = secrets.token_urlsafe(24)
        db.commit()
        db.refresh(lavoro)
    return lavoro


def get_lavoro_by_token_firma(db: Session, token: str):
    return db.query(Lavoro).filter(Lavoro.token_firma == token).first()
def genera_numero_preventivo(db: Session, utente_id: int):
    impostazioni = get_impostazioni_azienda(db, utente_id)

    anno = datetime.now().year

    impostazioni.ultimo_numero_preventivo += 1

    numero = impostazioni.ultimo_numero_preventivo

    db.commit()
    db.refresh(impostazioni)

    return f"PREV-{anno}-{numero:04d}"
def get_dashboard_preventivi(db: Session, utente_id: int):
    lavori = (
        db.query(Lavoro)
        .filter(
            Lavoro.utente_id == utente_id,
            Lavoro.stato.in_([
                "preventivo",
                "preventivo_inviato",
                "preventivo_accettato"
            ])
        )
        .all()
    )

    preventivi_creati = [
        l for l in lavori
        if l.stato == "preventivo"
    ]

    preventivi_inviati = [
        l for l in lavori
        if l.stato == "preventivo_inviato"
    ]

    preventivi_accettati = [
        l for l in lavori
        if l.stato == "preventivo_accettato"
    ]

    totale_preventivi = sum(
        l.importo_preventivato or 0
        for l in lavori
    )

    totale_accettati = sum(
        l.importo_preventivato or 0
        for l in preventivi_accettati
    )

    conversione_economica = 0

    if totale_preventivi > 0:
        conversione_economica = round(
            (totale_accettati / totale_preventivi) * 100,
            1
        )

    tasso_conversione = 0

    if len(lavori) > 0:
        tasso_conversione = round(
            (len(preventivi_accettati) / len(lavori)) * 100,
            1
        )

    ordine_stati = {
        "preventivo": 1,
        "preventivo_inviato": 2,
        "preventivo_accettato": 3,
    }

    lavori.sort(
        key=lambda l: (
            ordine_stati.get(l.stato, 99),
            -(l.id or 0)
        )
    )

    preventivi_da_inviare = len([
        l for l in lavori
        if l.stato == "preventivo"
    ])

    preventivi_in_attesa = len([
        l for l in lavori
        if l.stato == "preventivo_inviato"
    ])

    preventivi_7_giorni = 0
    preventivi_15_giorni = 0
    preventivi_30_giorni = 0

    oggi = datetime.now()

    for lavoro in preventivi_inviati:

        if not lavoro.data_invio_preventivo:
            continue

        try:

            data_invio = datetime.strptime(
                lavoro.data_invio_preventivo,
                "%Y-%m-%d"
            )

            giorni = (oggi - data_invio).days

            if giorni >= 7:
                preventivi_7_giorni += 1

            if giorni >= 15:
                preventivi_15_giorni += 1

            if giorni >= 30:
                preventivi_30_giorni += 1

        except:
            pass

    return {
        "preventivi_totali": len(lavori),
        "preventivi_creati": len(preventivi_creati),
        "preventivi_inviati": len(preventivi_inviati),
        "preventivi_accettati": len(preventivi_accettati),
        "totale_preventivi": totale_preventivi,
        "totale_accettati": totale_accettati,
        "preventivi_da_inviare": preventivi_da_inviare,
        "preventivi_in_attesa": preventivi_in_attesa,
        "conversione_economica": conversione_economica,
        "tasso_conversione": tasso_conversione,
        "preventivi_7_giorni": preventivi_7_giorni,
        "preventivi_15_giorni": preventivi_15_giorni,
        "preventivi_30_giorni": preventivi_30_giorni,
        "preventivi": lavori,
    }

def get_classifica_clienti(db: Session, utente_id: int):

    clienti = (
        db.query(Cliente)
        .filter(
            Cliente.utente_id == utente_id
        )
        .all()
    )

    risultati = []

    for cliente in clienti:

        totale = sum(
            (l.totale_documento or 0)
            for l in cliente.lavori
        )

        numero_lavori = len(cliente.lavori)

        risultati.append({
            "cliente": cliente,
            "totale": totale,
            "numero_lavori": numero_lavori
        })

    risultati.sort(
        key=lambda x: x["totale"],
        reverse=True
    )

    return risultati[:10]

def get_lavori_piu_redditizi(
    db: Session,
    utente_id: int
):

    lavori = (
        db.query(Lavoro)
        .filter(
            Lavoro.utente_id == utente_id,
            Lavoro.stato == "completato"
        )
        .all()
    )

    lavori.sort(
        key=lambda l: l.margine or 0,
        reverse=True
    )

    return lavori[:10]


# ========================
# REGISTRO FATTURE
# ========================

def genera_numero_fattura(db: Session, utente_id: int) -> tuple[int, int]:
    """Ritorna (anno, numero) con reset automatico ogni anno."""
    impostazioni = get_impostazioni_azienda(db, utente_id)
    anno_corrente = datetime.now().year
    if (impostazioni.ultimo_anno_fattura or 0) != anno_corrente:
        impostazioni.ultimo_numero_fattura = 0
        impostazioni.ultimo_anno_fattura = anno_corrente
    impostazioni.ultimo_numero_fattura = (impostazioni.ultimo_numero_fattura or 0) + 1
    db.commit()
    db.refresh(impostazioni)
    return anno_corrente, impostazioni.ultimo_numero_fattura


def salva_fattura_emessa(
    db: Session,
    utente_id: int,
    lavoro_id: int,
    numero: int,
    anno: int,
    data_emissione: str,
    imponibile: float,
    iva: float,
    totale: float,
    nome_file: str,
    regime: str = "RF01",
) -> FatturaEmessa:
    existing = (
        db.query(FatturaEmessa)
        .filter(FatturaEmessa.lavoro_id == lavoro_id, FatturaEmessa.utente_id == utente_id)
        .first()
    )
    if existing:
        existing.nome_file = nome_file
        existing.data_emissione = data_emissione
        existing.importo_imponibile = imponibile
        existing.importo_iva = iva
        existing.importo_totale = totale
        db.commit()
        db.refresh(existing)
        return existing

    fattura = FatturaEmessa(
        utente_id=utente_id,
        lavoro_id=lavoro_id,
        numero=numero,
        anno=anno,
        data_emissione=data_emissione,
        importo_imponibile=imponibile,
        importo_iva=iva,
        importo_totale=totale,
        nome_file=nome_file,
        regime=regime,
        stato="emessa",
        data_creazione=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(fattura)
    db.commit()
    db.refresh(fattura)
    return fattura


def get_fatture_registro(db: Session, utente_id: int, anno: int | None = None):
    q = (
        db.query(FatturaEmessa)
        .filter(FatturaEmessa.utente_id == utente_id)
    )
    if anno:
        q = q.filter(FatturaEmessa.anno == anno)
    return q.order_by(FatturaEmessa.numero.asc()).all()


def get_anni_fatture(db: Session, utente_id: int):
    rows = (
        db.query(func.distinct(FatturaEmessa.anno))
        .filter(FatturaEmessa.utente_id == utente_id)
        .order_by(FatturaEmessa.anno.desc())
        .all()
    )
    return [r[0] for r in rows]


def aggiorna_stato_fattura(db: Session, fattura_id: int, utente_id: int, nuovo_stato: str):
    f = (
        db.query(FatturaEmessa)
        .filter(FatturaEmessa.id == fattura_id, FatturaEmessa.utente_id == utente_id)
        .first()
    )
    if f:
        f.stato = nuovo_stato
        db.commit()
        db.refresh(f)
    return f

# ========================
# TEMPLATE PREVENTIVI
# ========================

def get_template_preventivi(db: Session, utente_id: int):
    return (
        db.query(TemplatePreventivo)
        .filter(TemplatePreventivo.utente_id == utente_id)
        .order_by(TemplatePreventivo.nome)
        .all()
    )

def get_template_preventivo(db: Session, template_id: int, utente_id: int):
    return (
        db.query(TemplatePreventivo)
        .filter(
            TemplatePreventivo.id == template_id,
            TemplatePreventivo.utente_id == utente_id,
        )
        .first()
    )

def crea_template_preventivo(
    db: Session,
    utente_id: int,
    nome: str,
    titolo: str = "",
    descrizione: str = "",
    importo_preventivato: float = 0,
    aliquota_iva: float = 22,
    sconto: float = 0,
    note_consuntivo: str = "",
) -> TemplatePreventivo:
    t = TemplatePreventivo(
        utente_id=utente_id,
        nome=nome,
        titolo=titolo,
        descrizione=descrizione,
        importo_preventivato=importo_preventivato,
        aliquota_iva=aliquota_iva,
        sconto=sconto,
        note_consuntivo=note_consuntivo,
        creato_il=datetime.now().strftime("%Y-%m-%d"),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t

def aggiorna_template_preventivo(
    db: Session,
    template_id: int,
    utente_id: int,
    nome: str,
    titolo: str = "",
    descrizione: str = "",
    importo_preventivato: float = 0,
    aliquota_iva: float = 22,
    sconto: float = 0,
    note_consuntivo: str = "",
) -> TemplatePreventivo | None:
    t = get_template_preventivo(db, template_id, utente_id)
    if not t:
        return None
    t.nome = nome
    t.titolo = titolo
    t.descrizione = descrizione
    t.importo_preventivato = importo_preventivato
    t.aliquota_iva = aliquota_iva
    t.sconto = sconto
    t.note_consuntivo = note_consuntivo
    db.commit()
    db.refresh(t)
    return t

def elimina_template_preventivo(db: Session, template_id: int, utente_id: int) -> bool:
    t = get_template_preventivo(db, template_id, utente_id)
    if not t:
        return False
    db.delete(t)
    db.commit()
    return True


# ========================
# VOCI PREVENTIVO
# ========================

def get_voci_preventivo(db: Session, utente_id: int, lavoro_id: int):
    return (
        db.query(VocePreventivo)
        .filter(VocePreventivo.lavoro_id == lavoro_id, VocePreventivo.utente_id == utente_id)
        .order_by(VocePreventivo.ordine, VocePreventivo.id)
        .all()
    )

def get_voce_preventivo(db: Session, voce_id: int, utente_id: int):
    return db.query(VocePreventivo).filter(VocePreventivo.id == voce_id, VocePreventivo.utente_id == utente_id).first()

def crea_voce_preventivo(db: Session, utente_id: int, lavoro_id: int, descrizione: str, quantita: float, unita_misura: str, prezzo_unitario: float, ordine: int = 0):
    voce = VocePreventivo(
        lavoro_id=lavoro_id, utente_id=utente_id,
        descrizione=descrizione, quantita=quantita,
        unita_misura=unita_misura, prezzo_unitario=prezzo_unitario,
        ordine=ordine,
    )
    db.add(voce)
    db.commit()
    db.refresh(voce)
    return voce

def elimina_voce_preventivo(db: Session, voce_id: int, utente_id: int) -> bool:
    voce = get_voce_preventivo(db, voce_id, utente_id)
    if not voce:
        return False
    db.delete(voce)
    db.commit()
    return True

def calcola_totale_voci(db: Session, utente_id: int, lavoro_id: int) -> float:
    voci = get_voci_preventivo(db, utente_id, lavoro_id)
    return sum((v.quantita or 0) * (v.prezzo_unitario or 0) for v in voci)


def get_sessione_aperta(db: Session, utente_id: int, lavoro_id: int):
    return (
        db.query(SessioneLavoro)
        .filter(
            SessioneLavoro.utente_id == utente_id,
            SessioneLavoro.lavoro_id == lavoro_id,
            SessioneLavoro.fine == None,
        )
        .first()
    )


def apri_sessione(db: Session, utente_id: int, lavoro_id: int) -> SessioneLavoro:
    s = SessioneLavoro(
        utente_id=utente_id,
        lavoro_id=lavoro_id,
        inizio=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        fine=None,
        ore_calcolate=None,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def chiudi_sessione(db: Session, sessione_id: int, utente_id: int):
    s = db.query(SessioneLavoro).filter(
        SessioneLavoro.id == sessione_id,
        SessioneLavoro.utente_id == utente_id,
    ).first()
    if not s:
        return None
    fine = datetime.now()
    inizio = datetime.strptime(s.inizio, "%Y-%m-%d %H:%M:%S")
    ore = (fine - inizio).total_seconds() / 3600
    s.fine = fine.strftime("%Y-%m-%d %H:%M:%S")
    s.ore_calcolate = round(ore, 2)
    db.commit()
    db.refresh(s)
    return s


def get_sessioni_lavoro(db: Session, utente_id: int, lavoro_id: int):
    return (
        db.query(SessioneLavoro)
        .filter(
            SessioneLavoro.utente_id == utente_id,
            SessioneLavoro.lavoro_id == lavoro_id,
        )
        .order_by(SessioneLavoro.inizio.desc())
        .all()
    )


# ========================
# PRIMA NOTA
# ========================

def get_prima_nota(
    db: Session,
    utente_id: int,
    anno: int | None = None,
    mese: int | None = None,
):
    q = db.query(VocePrimaNota).filter(VocePrimaNota.utente_id == utente_id)
    if anno:
        q = q.filter(VocePrimaNota.data.like(f"{anno}-%"))
    if mese:
        mese_str = f"{anno or '%'}-{mese:02d}"
        q = q.filter(VocePrimaNota.data.like(f"{mese_str}-%"))
    return q.order_by(VocePrimaNota.data.desc(), VocePrimaNota.id.desc()).all()


def crea_voce_prima_nota(
    db: Session,
    utente_id: int,
    data: str,
    descrizione: str,
    importo: float,
    tipo: str,
    categoria: str | None,
) -> VocePrimaNota:
    voce = VocePrimaNota(
        utente_id=utente_id,
        data=data,
        descrizione=descrizione,
        importo=importo,
        tipo=tipo,
        categoria=categoria or None,
        data_creazione=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(voce)
    db.commit()
    db.refresh(voce)
    return voce


def elimina_voce_prima_nota(db: Session, voce_id: int, utente_id: int) -> bool:
    voce = db.query(VocePrimaNota).filter(
        VocePrimaNota.id == voce_id,
        VocePrimaNota.utente_id == utente_id,
    ).first()
    if not voce:
        return False
    db.delete(voce)
    db.commit()
    return True


# ========================
# LISTINO PREZZI
# ========================

def get_listino(db: Session, utente_id: int):
    return (
        db.query(ListinoVoce)
        .filter(ListinoVoce.utente_id == utente_id)
        .order_by(ListinoVoce.categoria, ListinoVoce.descrizione)
        .all()
    )


def get_listino_voce(db: Session, voce_id: int, utente_id: int):
    return db.query(ListinoVoce).filter(
        ListinoVoce.id == voce_id,
        ListinoVoce.utente_id == utente_id,
    ).first()


def crea_listino_voce(
    db: Session,
    utente_id: int,
    descrizione: str,
    unita_misura: str,
    prezzo_unitario: float,
    categoria: str,
) -> ListinoVoce:
    voce = ListinoVoce(
        utente_id=utente_id,
        descrizione=descrizione,
        unita_misura=unita_misura or "",
        prezzo_unitario=prezzo_unitario,
        categoria=categoria or "",
        data_creazione=datetime.now().strftime("%Y-%m-%d"),
    )
    db.add(voce)
    db.commit()
    db.refresh(voce)
    return voce


def aggiorna_listino_voce(
    db: Session,
    voce_id: int,
    utente_id: int,
    descrizione: str,
    unita_misura: str,
    prezzo_unitario: float,
    categoria: str,
):
    voce = get_listino_voce(db, voce_id, utente_id)
    if not voce:
        return None
    voce.descrizione = descrizione
    voce.unita_misura = unita_misura or ""
    voce.prezzo_unitario = prezzo_unitario
    voce.categoria = categoria or ""
    db.commit()
    db.refresh(voce)
    return voce


def elimina_listino_voce(db: Session, voce_id: int, utente_id: int) -> bool:
    voce = get_listino_voce(db, voce_id, utente_id)
    if not voce:
        return False
    db.delete(voce)
    db.commit()
    return True


# ========================
# SAL — STATO AVANZAMENTO LAVORI
# ========================

def get_sal_lavoro(db: Session, utente_id: int, lavoro_id: int):
    return (
        db.query(SalLavoro)
        .filter(SalLavoro.utente_id == utente_id, SalLavoro.lavoro_id == lavoro_id)
        .order_by(SalLavoro.numero)
        .all()
    )

def get_sal_by_id(db: Session, sal_id: int, utente_id: int):
    return db.query(SalLavoro).filter(
        SalLavoro.id == sal_id, SalLavoro.utente_id == utente_id
    ).first()

def crea_sal(db: Session, utente_id: int, lavoro_id: int, data: str,
             percentuale: float, importo_richiesto: float, descrizione: str, note: str):
    numero = db.query(SalLavoro).filter(
        SalLavoro.utente_id == utente_id, SalLavoro.lavoro_id == lavoro_id
    ).count() + 1
    sal = SalLavoro(
        lavoro_id=lavoro_id, utente_id=utente_id, numero=numero,
        data=data, percentuale=percentuale, importo_richiesto=importo_richiesto,
        descrizione=descrizione or "", note=note or "",
        stato="emesso", data_creazione=datetime.now().strftime("%Y-%m-%d"),
    )
    db.add(sal); db.commit(); db.refresh(sal); return sal

def segna_sal_pagato(db: Session, sal_id: int, utente_id: int):
    sal = get_sal_by_id(db, sal_id, utente_id)
    if not sal:
        return None
    sal.stato = "pagato" if sal.stato == "emesso" else "emesso"
    db.commit(); db.refresh(sal); return sal

def elimina_sal(db: Session, sal_id: int, utente_id: int) -> bool:
    sal = get_sal_by_id(db, sal_id, utente_id)
    if not sal:
        return False
    db.delete(sal); db.commit(); return True


# ========================
# RAPPORTINI DI LAVORO
# ========================

def get_rapportini_lavoro(db: Session, utente_id: int, lavoro_id: int):
    return (
        db.query(RapportinoLavoro)
        .filter(RapportinoLavoro.utente_id == utente_id, RapportinoLavoro.lavoro_id == lavoro_id)
        .order_by(RapportinoLavoro.data.desc())
        .all()
    )

def get_rapportino_by_id(db: Session, rapportino_id: int, utente_id: int):
    return db.query(RapportinoLavoro).filter(
        RapportinoLavoro.id == rapportino_id, RapportinoLavoro.utente_id == utente_id
    ).first()

def crea_rapportino(db: Session, utente_id: int, lavoro_id: int, data: str,
                    ore_lavorate: float, descrizione_attivita: str,
                    materiali_note: str, note: str):
    r = RapportinoLavoro(
        lavoro_id=lavoro_id, utente_id=utente_id, data=data,
        ore_lavorate=ore_lavorate or 0, descrizione_attivita=descrizione_attivita,
        materiali_note=materiali_note or "", note=note or "",
        data_creazione=datetime.now().strftime("%Y-%m-%d"),
    )
    db.add(r); db.commit(); db.refresh(r); return r

def elimina_rapportino(db: Session, rapportino_id: int, utente_id: int) -> bool:
    r = get_rapportino_by_id(db, rapportino_id, utente_id)
    if not r:
        return False
    db.delete(r); db.commit(); return True


# ─── PROMEMORIA MANUTENZIONI ───────────────────────────────────────────────

def get_promemoria(db: Session, utente_id: int, solo_attivi: bool = False):
    q = db.query(PromemoriaCliente).filter(PromemoriaCliente.utente_id == utente_id)
    if solo_attivi:
        q = q.filter(PromemoriaCliente.stato == "attivo")
    return q.order_by(PromemoriaCliente.data_promemoria.asc()).all()

def get_promemoria_imminenti(db: Session, utente_id: int, giorni: int = 30):
    from datetime import date, timedelta
    oggi = date.today()
    limite = (oggi + timedelta(days=giorni)).isoformat()
    return (
        db.query(PromemoriaCliente)
        .filter(
            PromemoriaCliente.utente_id == utente_id,
            PromemoriaCliente.stato == "attivo",
            PromemoriaCliente.data_promemoria <= limite,
        )
        .order_by(PromemoriaCliente.data_promemoria.asc())
        .all()
    )

def get_promemoria_by_id(db: Session, promemoria_id: int, utente_id: int):
    return (
        db.query(PromemoriaCliente)
        .filter(PromemoriaCliente.id == promemoria_id, PromemoriaCliente.utente_id == utente_id)
        .first()
    )

def crea_promemoria(db: Session, utente_id: int, titolo: str, data_promemoria: str,
                    tipo: str = "manutenzione", note: str = "", cliente_id: int | None = None):
    p = PromemoriaCliente(
        utente_id=utente_id, cliente_id=cliente_id or None,
        titolo=titolo, note=note or "", data_promemoria=data_promemoria,
        tipo=tipo, stato="attivo",
        data_creazione=datetime.now().strftime("%Y-%m-%d"),
    )
    db.add(p); db.commit(); db.refresh(p); return p

def completa_promemoria(db: Session, promemoria_id: int, utente_id: int):
    p = get_promemoria_by_id(db, promemoria_id, utente_id)
    if not p:
        return None
    p.stato = "completato" if p.stato == "attivo" else "attivo"
    db.commit(); db.refresh(p); return p

def elimina_promemoria(db: Session, promemoria_id: int, utente_id: int) -> bool:
    p = get_promemoria_by_id(db, promemoria_id, utente_id)
    if not p:
        return False
    db.delete(p); db.commit(); return True


# ─── PORTALE CLIENTE (token pubblico) ──────────────────────────────────────

def genera_token_portale_cliente(db: Session, cliente_id: int, utente_id: int):
    cliente = get_cliente_by_id(db, cliente_id, utente_id)
    if not cliente:
        return None
    cliente.token_portale = secrets.token_urlsafe(24)
    db.commit(); db.refresh(cliente)
    return cliente

def get_cliente_by_token_portale(db: Session, token: str):
    return db.query(Cliente).filter(Cliente.token_portale == token).first()


# ─── TIMESHEET COLLABORATORI ────────────────────────────────────────────────

def get_timesheet_lavoro(db: Session, utente_id: int, lavoro_id: int):
    return (
        db.query(TimesheetCollab)
        .filter(TimesheetCollab.utente_id == utente_id, TimesheetCollab.lavoro_id == lavoro_id)
        .order_by(TimesheetCollab.data.desc())
        .all()
    )

def crea_timesheet_entry(db: Session, utente_id: int, lavoro_id: int,
                         nome_operaio: str, data: str, ore: float,
                         costo_orario: float, note: str):
    entry = TimesheetCollab(
        utente_id=utente_id,
        lavoro_id=lavoro_id,
        nome_operaio=nome_operaio.strip(),
        data=data,
        ore=ore,
        costo_orario=costo_orario,
        note=note.strip(),
        data_creazione=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    db.add(entry); db.commit(); db.refresh(entry)
    return entry

def elimina_timesheet_entry(db: Session, entry_id: int, utente_id: int) -> bool:
    entry = db.query(TimesheetCollab).filter(
        TimesheetCollab.id == entry_id, TimesheetCollab.utente_id == utente_id
    ).first()
    if not entry:
        return False
    db.delete(entry); db.commit(); return True

def get_collaboratori_utente(db: Session, utente_id: int):
    """Restituisce i collaboratori (sub-account) del titolare."""
    return db.query(Utente).filter(Utente.titolare_id == utente_id).all()

def calcola_budget_realtime(db: Session, utente_id: int, lavoro_id: int, materiali_usati=None):
    """Calcola costo materiali reale (da costo_unitario) e costo manodopera da timesheet."""
    if materiali_usati is None:
        materiali_usati = get_materiali_usati_lavoro(db, utente_id, lavoro_id)
    costo_mat = sum((m.quantita or 0) * (m.costo_unitario or 0) for m in materiali_usati)

    entries = get_timesheet_lavoro(db, utente_id, lavoro_id)
    costo_man = sum((e.ore or 0) * (e.costo_orario or 0) for e in entries)
    ore_tot = sum(e.ore or 0 for e in entries)

    return {
        "costo_materiali_reale": round(costo_mat, 2),
        "costo_manodopera_timesheet": round(costo_man, 2),
        "ore_totali_timesheet": round(ore_tot, 2),
        "totale_speso": round(costo_mat + costo_man, 2),
    }
