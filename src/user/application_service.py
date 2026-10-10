from uuid import UUID

from src.user.domain_model import User, UserRepository, RoleRepository, Accion
from src.user.dto import UserCreate, AuthenticatedUser, UserProfile
from src.main.errors import AuthenticationError, PermissionDenied
from src.main.utils import MAX_PASSWORD_BYTES, hash_password, check_password, create_token, decode_token

class UserCreator:

  def __init__(self,repository:UserRepository,role_repository:RoleRepository) -> None:
    self.repository = repository
    self.role_repository = role_repository

  def invoque(self,dto:UserCreate)->User:
    # Las lecturas no cierran la sesión: se cierra aquí para devolver la conexión al pool
    try:
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
    finally:
      self.repository.close()
      self.role_repository.close()

class UserSignup:
  """Alta de administrador y de operador (§8.1 y §8.2)."""

  ROLES = ('ADMIN', 'OPERADOR')

  def __init__(self,user_creator:UserCreator) -> None:
    self.user_creator = user_creator

  def invoque(self,actor:AuthenticatedUser,dto:UserCreate)->User:
    if not actor.tiene_permiso(Accion.GESTIONAR_USUARIOS):
      raise PermissionDenied('No tiene permiso para gestionar usuarios')

    # Los clientes se dan de alta junto con su cuenta (§8.3), no por aquí
    if dto.rol not in self.ROLES:
      raise ValueError(f'No se puede dar de alta un usuario con el rol {dto.rol}')

    return self.user_creator.invoque(dto)

class UserLogin:

  def __init__(self,repository:UserRepository,jwt_secret:str,jwt_minutes:int) -> None:
    self.repository = repository
    self.jwt_secret = jwt_secret
    self.jwt_minutes = jwt_minutes

  def invoque(self,email:str,password:str)->tuple[str,User]:
    try:
      user = self.repository.find_by_email(email)

      # Mismo error en los tres casos para no revelar qué emails existen
      if user is None or not user.activo or not check_password(password, user.password_hash):
        raise AuthenticationError('Credenciales inválidas')

      token = create_token(str(user.id), user.rol.nombre, self.jwt_secret, self.jwt_minutes)
      return token, user
    finally:
      self.repository.close()

class UserAuthenticator:
  """Traduce el token a un usuario autenticado (id, rol, permisos)."""

  def __init__(self,repository:UserRepository,jwt_secret:str) -> None:
    self.repository = repository
    self.jwt_secret = jwt_secret

  def invoque(self,token:str|None,permitir_password_pendiente:bool=False)->AuthenticatedUser:
    payload = decode_token(token, self.jwt_secret) if token else None
    if payload is None:
      raise AuthenticationError('Token inválido o expirado')

    try:
      user_id = UUID(payload['sub'])
    except ValueError:
      raise AuthenticationError('Token inválido o expirado')

    # Se consulta en cada solicitud: una desactivación o un cambio de rol
    # surten efecto sin esperar a que expire el token (§7)
    try:
      user = self.repository.find_by_id(user_id)
      if user is None or not user.activo:
        raise AuthenticationError('Token inválido o expirado')

      # Con la contraseña inicial solo se permite cambiarla (§7)
      if user.debe_cambiar_password and not permitir_password_pendiente:
        raise PermissionDenied('Debe cambiar su contraseña antes de operar')

      return AuthenticatedUser(
        id=user.id,
        rol=user.rol.nombre,
        permisos=frozenset((permiso.accion, permiso.alcance) for permiso in user.rol.permisos)
      )
    finally:
      self.repository.close()

class UserProfileReader:
  """Perfil del usuario autenticado, sin datos sensibles."""

  def __init__(self,repository:UserRepository) -> None:
    self.repository = repository

  def invoque(self,actor:AuthenticatedUser)->UserProfile:
    try:
      user = self.repository.find_by_id(actor.id)
      if user is None:
        raise AuthenticationError('Token inválido o expirado')

      # El DTO se arma antes de cerrar la sesión: el rol se carga de forma diferida
      return UserProfile(
        id=user.id,
        email=user.email,
        rol=user.rol.nombre,
        activo=user.activo,
        debe_cambiar_password=user.debe_cambiar_password,
        creado_en=user.creado_en
      )
    finally:
      self.repository.close()

class PasswordChanger:

  def __init__(self,repository:UserRepository) -> None:
    self.repository = repository

  def invoque(self,actor:AuthenticatedUser,password_actual:str,password_nueva:str)->None:
    try:
      user = self.repository.find_by_id(actor.id)
      if user is None or not check_password(password_actual, user.password_hash):
        raise ValueError('La contraseña actual no es correcta')

      if len(password_nueva.encode('utf-8')) > MAX_PASSWORD_BYTES:
        raise ValueError(f'La contraseña no puede exceder {MAX_PASSWORD_BYTES} bytes')

      if password_nueva == password_actual:
        raise ValueError('La contraseña nueva debe ser distinta de la actual')

      user.password_hash = hash_password(password_nueva)
      user.debe_cambiar_password = False
      self.repository.update(user)
    finally:
      self.repository.close()
