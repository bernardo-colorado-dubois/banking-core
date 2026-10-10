from src.main.database import Base
from src.user.domain_model import User
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List
from uuid import UUID, uuid4

# §4.1 La etiqueta no cambia el comportamiento contable
class ClaseCuenta(Enum):
  NOSTRO = "NOSTRO"   # cuenta propia del banco
  VOSTRO = "VOSTRO"   # cuenta de cliente

# §5 Distingue un retiro de una transferencia saliente
class TipoTransaccion(Enum):
  FONDEO = "FONDEO"
  RETIRO = "RETIRO"
  TRANSFERENCIA = "TRANSFERENCIA"

# §4.2 Los dos lados del libro de una cuenta
class Lado(Enum):
  PRINCIPAL = "PRINCIPAL"
  CONTRAPARTIDA = "CONTRAPARTIDA"

class Naturaleza(Enum):
  DEBITO = "DEBITO"
  CREDITO = "CREDITO"

class Account(Base):

  __tablename__ = 'cuentas'
  __table_args__ = (
    CheckConstraint(
      "(clase = 'VOSTRO' AND titular_id IS NOT NULL) OR (clase = 'NOSTRO' AND titular_id IS NULL)",
      name='titular_segun_clase',
    ),
    # El alias distingue las cuentas de un mismo titular; con titular nulo
    # cubre a las NOSTRO entre sí
    UniqueConstraint('titular_id', 'alias', postgresql_nulls_not_distinct=True),
  )

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  clase: Mapped[ClaseCuenta] = mapped_column(nullable=False)
  alias: Mapped[str] = mapped_column(nullable=False)
  titular_id: Mapped[UUID | None] = mapped_column(ForeignKey('usuarios.id'), nullable=True)
  creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
  titular: Mapped[User | None] = relationship()

class Transaction(Base):

  __tablename__ = 'transacciones'

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  tipo: Mapped[TipoTransaccion] = mapped_column(nullable=False)
  descripcion: Mapped[str | None] = mapped_column(nullable=True)
  creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
  movimientos: Mapped[List["Movement"]] = relationship(back_populates='transaccion')

# §4.4 Inmutables: nunca se editan ni se borran
class Movement(Base):

  __tablename__ = 'movimientos'
  __table_args__ = (
    CheckConstraint('monto > 0', name='monto_positivo'),
  )

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  transaccion_id: Mapped[UUID] = mapped_column(ForeignKey('transacciones.id'), nullable=False)
  cuenta_id: Mapped[UUID] = mapped_column(ForeignKey('cuentas.id'), nullable=False)
  lado: Mapped[Lado] = mapped_column(nullable=False)
  naturaleza: Mapped[Naturaleza] = mapped_column(nullable=False)
  monto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
  creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
  transaccion: Mapped[Transaction] = relationship(back_populates='movimientos')


class AccountRepository:

  def __init__(self,session:Session) -> None:
    self.session = session

  def find_by_id(self,id:UUID)->Account|None:
    return self.session.query(Account).filter(Account.id==id).one_or_none()

  def find_by_titular_and_alias(self,titular_id:UUID|None,alias:str)->Account|None:
    return self.session.query(Account).filter(
      Account.titular_id.is_not_distinct_from(titular_id),
      Account.alias==alias
    ).one_or_none()

  def close(self)->None:
    self.session.close()

  # Un titular nuevo se guarda en cascada, en la misma transacción que la cuenta (§8.3)
  def save(self,account:Account)->None:
    try:
      self.session.add(account)
      self.session.commit()
    except:
      self.session.rollback()
      raise
    finally:
      self.session.close()
