from src.account.domain_model import Account, AccountRepository, ClaseCuenta
from src.account.dto import AccountDetail
from src.user.domain_model import User, UserRepository, RoleRepository, Accion, Alcance
from src.user.dto import UserCreate, AuthenticatedUser
from src.main.errors import PermissionDenied
from src.main.utils import hash_password

class ClientSignup:
  """Alta de cliente con su primera cuenta VOSTRO (§8.3)."""

  def __init__(self,repository:AccountRepository,user_repository:UserRepository,role_repository:RoleRepository) -> None:
    self.repository = repository
    self.user_repository = user_repository
    self.role_repository = role_repository

  def invoque(self,actor:AuthenticatedUser,dto:UserCreate,alias:str)->AccountDetail:
    # No requiere GESTIONAR_USUARIOS: el alta va cubierta por ABRIR_CUENTA:VOSTRO (§7)
    if not actor.tiene_permiso(Accion.ABRIR_CUENTA, Alcance.VOSTRO):
      raise PermissionDenied('No tiene permiso para abrir cuentas de clientes')

    try:
      if self.user_repository.find_by_email(dto.email) is not None:
        raise ValueError(f'Ya existe un usuario con el email {dto.email}')

      rol = self.role_repository.find_by_name('CLIENTE')
      if rol is None:
        raise ValueError('No existe el rol CLIENTE')

      # Solo se persiste el hash, nunca la contraseña en claro
      user = User(
        email=dto.email,
        nombre=dto.nombre,
        password_hash=hash_password(dto.password),
        rol_id=rol.id,
        activo=dto.activo,
        debe_cambiar_password=dto.debe_cambiar_password
      )
      # Usuario y cuenta van en un solo commit: se crean ambos o ninguno
      account = Account(clase=ClaseCuenta.VOSTRO, alias=alias, titular=user)
      self.repository.save(account)

      return AccountDetail(
        id=account.id,
        clase=account.clase,
        alias=account.alias,
        titular=user.nombre,
        titular_id=user.id,
        creada_en=account.creada_en
      )
    finally:
      self.repository.close()
      self.user_repository.close()
      self.role_repository.close()

class VostroAccountOpener:
  """Cuenta VOSTRO adicional para un cliente que ya existe (§8.4)."""

  def __init__(self,repository:AccountRepository,user_repository:UserRepository) -> None:
    self.repository = repository
    self.user_repository = user_repository

  def invoque(self,actor:AuthenticatedUser,email:str,alias:str)->AccountDetail:
    if not actor.tiene_permiso(Accion.ABRIR_CUENTA, Alcance.VOSTRO):
      raise PermissionDenied('No tiene permiso para abrir cuentas de clientes')

    try:
      user = self.user_repository.find_by_email(email)
      if user is None:
        raise ValueError(f'No existe un usuario con el email {email}')

      # No se puede expresar con un CHECK: se valida aquí (§9)
      if user.rol.nombre != 'CLIENTE':
        raise ValueError(f'El usuario {email} no es un cliente')

      if not user.activo:
        raise ValueError(f'El usuario {email} está inactivo')

      if self.repository.find_by_titular_and_alias(user.id, alias) is not None:
        raise ValueError(f'El cliente ya tiene una cuenta con el alias {alias}')

      account = Account(clase=ClaseCuenta.VOSTRO, alias=alias, titular_id=user.id)
      self.repository.save(account)

      return AccountDetail(
        id=account.id,
        clase=account.clase,
        alias=account.alias,
        titular=user.nombre,
        titular_id=user.id,
        creada_en=account.creada_en
      )
    finally:
      self.repository.close()
      self.user_repository.close()

class NostroAccountOpener:
  """Apertura de cuenta NOSTRO (§8.13)."""

  def __init__(self,repository:AccountRepository,banco_nombre:str) -> None:
    self.repository = repository
    self.banco_nombre = banco_nombre

  def invoque(self,actor:AuthenticatedUser,alias:str)->AccountDetail:
    if not actor.tiene_permiso(Accion.ABRIR_CUENTA, Alcance.NOSTRO):
      raise PermissionDenied('No tiene permiso para abrir cuentas del banco')

    try:
      if self.repository.find_by_titular_and_alias(None, alias) is not None:
        raise ValueError(f'Ya existe una cuenta del banco con el alias {alias}')

      # Sin usuario titular: el titular es el nombre del banco (§7)
      account = Account(clase=ClaseCuenta.NOSTRO, alias=alias, titular_id=None)
      self.repository.save(account)

      return AccountDetail(
        id=account.id,
        clase=account.clase,
        alias=account.alias,
        titular=self.banco_nombre,
        titular_id=None,
        creada_en=account.creada_en
      )
    finally:
      self.repository.close()
