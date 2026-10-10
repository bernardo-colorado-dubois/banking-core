from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from src.account.domain_model import ClaseCuenta, Naturaleza, TipoTransaccion

@dataclass(frozen=True)
class AccountDetail:
  id: UUID
  clase: ClaseCuenta
  alias: str
  # Nombre del cliente en VOSTRO, nombre del banco en NOSTRO (§7)
  titular: str
  titular_id: UUID | None
  creada_en: datetime

@dataclass(frozen=True)
class AccountMovement:
  movimiento_id: UUID
  transaccion_id: UUID
  tipo: TipoTransaccion
  naturaleza: Naturaleza
  monto: Decimal
  # Saldo del principal después de este movimiento
  saldo: Decimal
  creado_en: datetime

@dataclass(frozen=True)
class AccountBalance:
  cuenta_id: UUID
  clase: ClaseCuenta
  alias: str
  # Del más antiguo al más reciente; el saldo actual es el del último movimiento
  movimientos: list[AccountMovement]

@dataclass(frozen=True)
class OperationResult:
  transaccion_id: UUID
  tipo: TipoTransaccion
  monto: Decimal
  cuenta_id: UUID
  # Solo en transferencias
  cuenta_destino_id: UUID | None
  # Saldo del principal de `cuenta_id` después de la operación
  saldo: Decimal
  creada_en: datetime
