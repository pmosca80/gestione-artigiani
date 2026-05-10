from pydantic import BaseModel, EmailStr
from typing import Optional


class ClienteBase(BaseModel):
    tipo_cliente: str = "privato"
    nome: Optional[str] = None
    cognome: Optional[str] = None
    ragione_sociale: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[EmailStr] = None
    indirizzo: Optional[str] = None
    citta: Optional[str] = None
    provincia: Optional[str] = None
    cap: Optional[str] = None
    note: Optional[str] = None


class ClienteCreate(ClienteBase):
    pass


class ClienteOut(ClienteBase):
    id: int
    data_creazione: str

    class Config:
        from_attributes = True