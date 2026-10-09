from dataclasses import dataclass

@dataclass
class UserCreate:
  email: str
  password: str
  rol: str
  activo: bool = True
  debe_cambiar_password: bool = True
