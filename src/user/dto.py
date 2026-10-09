from dataclasses import dataclass
from uuid import UUID

from src.main.utils import MAX_PASSWORD_BYTES
from src.user.domain_model import Accion, Alcance

@dataclass
class UserCreate:
  email: str
  password: str
  rol: str
  activo: bool = True
  debe_cambiar_password: bool = True

  def __post_init__(self) -> None:
    if len(self.password.encode('utf-8')) > MAX_PASSWORD_BYTES:
      raise ValueError(f'La contraseña no puede exceder {MAX_PASSWORD_BYTES} bytes')

@dataclass(frozen=True)
class AuthenticatedUser:
  id: UUID
  rol: str
  permisos: frozenset[tuple[Accion, Alcance | None]]

  def tiene_permiso(self, accion: Accion, alcance: Alcance | None = None) -> bool:
    return (accion, alcance) in self.permisos
