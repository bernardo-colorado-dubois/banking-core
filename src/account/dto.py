from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.account.domain_model import ClaseCuenta

@dataclass(frozen=True)
class AccountDetail:
  id: UUID
  clase: ClaseCuenta
  alias: str
  # Nombre del cliente en VOSTRO, nombre del banco en NOSTRO (§7)
  titular: str
  titular_id: UUID | None
  creada_en: datetime
