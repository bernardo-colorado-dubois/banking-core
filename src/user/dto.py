from dataclasses import dataclass

from src.main.utils import MAX_PASSWORD_BYTES

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
