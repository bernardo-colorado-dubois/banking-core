from src.main.database import Base
from src.user.domain_model import User, Alcance
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, MetaData, Numeric, Table, UniqueConstraint, Uuid
from sqlalchemy import DDL, Enum as SqlEnum, Row, case, event, func, select
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

  # §7 Evaluación: el alcance de la cuenta frente al usuario autenticado
  def alcance_para(self,usuario_id:UUID)->Alcance:
    if self.clase == ClaseCuenta.NOSTRO:
      return Alcance.NOSTRO
    return Alcance.PROPIAS if self.titular_id == usuario_id else Alcance.VOSTRO

class Transaction(Base):

  __tablename__ = 'transacciones'

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  tipo: Mapped[TipoTransaccion] = mapped_column(nullable=False)
  descripcion: Mapped[str | None] = mapped_column(nullable=True)
  creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
  movimientos: Mapped[List["Movement"]] = relationship(back_populates='transaccion')

  # §5 Cada operación arma sus movimientos; nunca se toca un saldo directamente
  @classmethod
  def fondeo(cls,cuenta_id:UUID,monto:Decimal)->"Transaction":
    return cls(tipo=TipoTransaccion.FONDEO, movimientos=entrada(cuenta_id, monto))

  @classmethod
  def retiro(cls,cuenta_id:UUID,monto:Decimal)->"Transaction":
    return cls(tipo=TipoTransaccion.RETIRO, movimientos=salida(cuenta_id, monto))

  # Cada lado pasa por su propia contrapartida: 4 movimientos
  @classmethod
  def transferencia(cls,origen_id:UUID,destino_id:UUID,monto:Decimal)->"Transaction":
    return cls(
      tipo=TipoTransaccion.TRANSFERENCIA,
      movimientos=salida(origen_id, monto) + entrada(destino_id, monto)
    )

  def validar(self,saldos:dict[UUID,Decimal])->None:
    """Invariantes de §6. `saldos` trae el saldo actual del principal de cada cuenta involucrada."""
    # 4. Montos positivos
    if any(movimiento.monto <= 0 for movimiento in self.movimientos):
      raise ValueError('El monto debe ser mayor que cero')

    # 5. En una transferencia, origen y destino son distintos
    cuentas = {movimiento.cuenta_id for movimiento in self.movimientos}
    if self.tipo == TipoTransaccion.TRANSFERENCIA and len(cuentas) != 2:
      raise ValueError('La cuenta origen y la cuenta destino deben ser distintas')

    # 1. Balance de la transacción: débitos = créditos
    if sum(movimiento.importe for movimiento in self.movimientos) != 0:
      raise ValueError('La transacción no está balanceada')

    for cuenta_id in cuentas:
      principal = self.variacion(cuenta_id, Lado.PRINCIPAL)
      # 2. Balance por cuenta: principal + contrapartida = 0
      if principal + self.variacion(cuenta_id, Lado.CONTRAPARTIDA) != 0:
        raise ValueError('La cuenta no cuadra con su contrapartida')
      # 3. Sin saldos negativos en el principal
      if saldos[cuenta_id] + principal < 0:
        raise ValueError('Fondos insuficientes')

  def variacion(self,cuenta_id:UUID,lado:Lado)->Decimal:
    return sum(
      (movimiento.importe for movimiento in self.movimientos
        if movimiento.cuenta_id == cuenta_id and movimiento.lado == lado),
      Decimal(0)
    )

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
  # clock_timestamp() y no now(): now() es la hora en que empezó la transacción de BD,
  # antes de obtener el bloqueo de la cuenta (§10). Con la hora real de inserción,
  # los movimientos de una cuenta quedan en el orden en que se aplicaron
  creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False)
  transaccion: Mapped[Transaction] = relationship(back_populates='movimientos')

  # §4.3 saldo = créditos − débitos
  @property
  def importe(self)->Decimal:
    return self.monto if self.naturaleza == Naturaleza.CREDITO else -self.monto

# Entra dinero a la cuenta: débito a la contrapartida, crédito al principal (§5)
def entrada(cuenta_id:UUID,monto:Decimal)->List[Movement]:
  return [
    Movement(cuenta_id=cuenta_id, lado=Lado.CONTRAPARTIDA, naturaleza=Naturaleza.DEBITO, monto=monto),
    Movement(cuenta_id=cuenta_id, lado=Lado.PRINCIPAL, naturaleza=Naturaleza.CREDITO, monto=monto),
  ]

# Sale dinero de la cuenta: débito al principal, crédito a la contrapartida (§5)
def salida(cuenta_id:UUID,monto:Decimal)->List[Movement]:
  return [
    Movement(cuenta_id=cuenta_id, lado=Lado.PRINCIPAL, naturaleza=Naturaleza.DEBITO, monto=monto),
    Movement(cuenta_id=cuenta_id, lado=Lado.CONTRAPARTIDA, naturaleza=Naturaleza.CREDITO, monto=monto),
  ]

# Historial de una cuenta: cada movimiento del principal con el saldo que dejó.
# El saldo acumulado se calcula en SQL (§4.3: créditos − débitos), no en Python
CREAR_HISTORIAL = """
CREATE OR REPLACE VIEW historial_cuentas AS
SELECT
  m.id AS movimiento_id,
  m.cuenta_id,
  m.transaccion_id,
  t.tipo,
  m.naturaleza,
  m.monto,
  SUM(CASE WHEN m.naturaleza = 'CREDITO' THEN m.monto ELSE -m.monto END)
    OVER (PARTITION BY m.cuenta_id ORDER BY m.creado_en, m.id) AS saldo,
  m.creado_en
FROM movimientos m
JOIN transacciones t ON t.id = m.transaccion_id
WHERE m.lado = 'PRINCIPAL'
"""

# La vista se crea y se borra junto con las tablas (create_all y drop_all)
event.listen(Base.metadata, 'after_create', DDL(CREAR_HISTORIAL))
event.listen(Base.metadata, 'before_drop', DDL('DROP VIEW IF EXISTS historial_cuentas'))

# Va en un MetaData aparte para que create_all no la cree como tabla
historial_cuentas = Table(
  'historial_cuentas', MetaData(),
  Column('movimiento_id', Uuid, primary_key=True),
  Column('cuenta_id', Uuid),
  Column('transaccion_id', Uuid),
  Column('tipo', SqlEnum(TipoTransaccion)),
  Column('naturaleza', SqlEnum(Naturaleza)),
  Column('monto', Numeric(18, 2)),
  Column('saldo', Numeric(18, 2)),
  Column('creado_en', DateTime(timezone=True)),
)

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

  # §10 Bloquea las filas antes de calcular saldos; el orden por id evita deadlocks.
  # El bloqueo se libera con el commit de save_transaction o con close
  def find_by_ids_for_update(self,ids:List[UUID])->List[Account]:
    return self.session.query(Account).filter(Account.id.in_(ids)).order_by(Account.id).with_for_update().all()

  # §4.3 El saldo no se almacena: créditos − débitos del principal
  def balance(self,id:UUID)->Decimal:
    importe = case((Movement.naturaleza==Naturaleza.CREDITO, Movement.monto), else_=-Movement.monto)
    saldo = self.session.query(func.coalesce(func.sum(importe), 0)).filter(
      Movement.cuenta_id==id,
      Movement.lado==Lado.PRINCIPAL
    ).scalar()
    return Decimal(saldo).quantize(Decimal('0.01'))

  # Del movimiento más antiguo al más reciente; el saldo de la última fila es el actual
  def history(self,id:UUID)->List[Row]:
    return self.session.execute(
      select(historial_cuentas)
        .where(historial_cuentas.c.cuenta_id==id)
        .order_by(historial_cuentas.c.creado_en, historial_cuentas.c.movimiento_id)
    ).all()

  def close(self)->None:
    self.session.close()

  # Todos los movimientos van en un solo commit: se registran todos o ninguno (§5)
  def save_transaction(self,transaction:Transaction)->None:
    try:
      self.session.add(transaction)
      self.session.commit()
    except:
      self.session.rollback()
      raise
    finally:
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
