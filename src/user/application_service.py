from src.user.domain_model import User, UserRepository, RoleRepository
from src.user.dto import UserCreate
from src.main.utils import hash_password

class UserCreator:

  def __init__(self,repository:UserRepository,role_repository:RoleRepository) -> None:
    self.repository = repository
    self.role_repository = role_repository

  def invoque(self,dto:UserCreate)->User:
    if self.repository.find_by_email(dto.email) is not None:
      raise ValueError(f'Ya existe un usuario con el email {dto.email}')

    rol = self.role_repository.find_by_name(dto.rol)
    if rol is None:
      raise ValueError(f'No existe el rol {dto.rol}')

    # Solo se persiste el hash, nunca la contraseña en claro
    user = User(
      email=dto.email,
      password_hash=hash_password(dto.password),
      rol_id=rol.id,
      activo=dto.activo,
      debe_cambiar_password=dto.debe_cambiar_password
    )
    self.repository.save(user)
    return user
