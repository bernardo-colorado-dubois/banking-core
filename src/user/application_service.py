from uuid import UUID

from src.user.domain_model import User, UserRepository, RoleRepository, Action
from src.user.dto import UserCreate, AuthenticatedUser, UserProfile
from src.main.errors import AuthenticationError, PermissionDenied
from src.main.utils import MAX_PASSWORD_BYTES, hash_password, check_password, create_token, decode_token

class UserCreator:

  def __init__(self,repository:UserRepository,role_repository:RoleRepository) -> None:
    self.repository = repository
    self.role_repository = role_repository

  def invoke(self,dto:UserCreate)->User:
    # Reads don't close the session: it is closed here to return the connection to the pool
    try:
      if self.repository.find_by_email(dto.email) is not None:
        raise ValueError(f'A user with the email {dto.email} already exists')

      role = self.role_repository.find_by_name(dto.role)
      if role is None:
        raise ValueError(f'The role {dto.role} does not exist')

      # Only the hash is persisted, never the plain-text password
      user = User(
        email=dto.email,
        name=dto.name,
        password_hash=hash_password(dto.password),
        role_id=role.id,
        active=dto.active,
        must_change_password=dto.must_change_password
      )
      self.repository.save(user)
      return user
    finally:
      self.repository.close()
      self.role_repository.close()

class UserSignup:
  """Admin and operator signup (§8.1 and §8.2)."""

  ROLES = ('ADMIN', 'OPERATOR')

  def __init__(self,user_creator:UserCreator) -> None:
    self.user_creator = user_creator

  def invoke(self,actor:AuthenticatedUser,dto:UserCreate)->User:
    if not actor.has_permission(Action.MANAGE_USERS):
      raise PermissionDenied('You do not have permission to manage users')

    # Clients sign up together with their account (§8.3), not here
    if dto.role not in self.ROLES:
      raise ValueError(f'Cannot sign up a user with the role {dto.role}')

    return self.user_creator.invoke(dto)

class UserLogin:

  def __init__(self,repository:UserRepository,jwt_secret:str,jwt_minutes:int) -> None:
    self.repository = repository
    self.jwt_secret = jwt_secret
    self.jwt_minutes = jwt_minutes

  def invoke(self,email:str,password:str)->tuple[str,User]:
    try:
      user = self.repository.find_by_email(email)

      # Same error in all three cases so as not to reveal which emails exist
      if user is None or not user.active or not check_password(password, user.password_hash):
        raise AuthenticationError('Invalid credentials')

      token = create_token(str(user.id), user.role.name, self.jwt_secret, self.jwt_minutes)
      return token, user
    finally:
      self.repository.close()

class UserAuthenticator:
  """Translates the token into an authenticated user (id, role, permissions)."""

  def __init__(self,repository:UserRepository,jwt_secret:str) -> None:
    self.repository = repository
    self.jwt_secret = jwt_secret

  def invoke(self,token:str|None,allow_pending_password:bool=False)->AuthenticatedUser:
    payload = decode_token(token, self.jwt_secret) if token else None
    if payload is None:
      raise AuthenticationError('Invalid or expired token')

    try:
      user_id = UUID(payload['sub'])
    except ValueError:
      raise AuthenticationError('Invalid or expired token')

    # Looked up on every request: a deactivation or a role change
    # takes effect without waiting for the token to expire (§7)
    try:
      user = self.repository.find_by_id(user_id)
      if user is None or not user.active:
        raise AuthenticationError('Invalid or expired token')

      # With the initial password the only thing allowed is changing it (§7)
      if user.must_change_password and not allow_pending_password:
        raise PermissionDenied('You must change your password before operating')

      return AuthenticatedUser(
        id=user.id,
        role=user.role.name,
        permissions=frozenset((permission.action, permission.scope) for permission in user.role.permissions),
        must_change_password=user.must_change_password
      )
    finally:
      self.repository.close()

class UserLister:
  """List of every user, without sensitive data. Modifies nothing."""

  def __init__(self,repository:UserRepository) -> None:
    self.repository = repository

  def invoke(self,actor:AuthenticatedUser)->list[UserProfile]:
    if not actor.has_permission(Action.MANAGE_USERS):
      raise PermissionDenied('You do not have permission to view the user list')

    try:
      return [UserProfile.of(user) for user in self.repository.find_all()]
    finally:
      self.repository.close()

class UserProfileReader:
  """Profile of a user, without sensitive data: one's own, or anyone's with MANAGE_USERS."""

  def __init__(self,repository:UserRepository) -> None:
    self.repository = repository

  def invoke(self,actor:AuthenticatedUser,user_id:UUID)->UserProfile:
    # With the initial password one can only read one's own profile (§7)
    if user_id != actor.id:
      if actor.must_change_password:
        raise PermissionDenied('You must change your password before operating')
      if not actor.has_permission(Action.MANAGE_USERS):
        raise PermissionDenied('You do not have permission to view this user')

    try:
      user = self.repository.find_by_id(user_id)
      if user is None:
        raise ValueError(f'No user exists with the id {user_id}')

      return UserProfile.of(user)
    finally:
      self.repository.close()

class PasswordChanger:

  def __init__(self,repository:UserRepository) -> None:
    self.repository = repository

  def invoke(self,actor:AuthenticatedUser,current_password:str,new_password:str)->None:
    try:
      user = self.repository.find_by_id(actor.id)
      if user is None or not check_password(current_password, user.password_hash):
        raise ValueError('The current password is incorrect')

      if len(new_password.encode('utf-8')) > MAX_PASSWORD_BYTES:
        raise ValueError(f'The password cannot exceed {MAX_PASSWORD_BYTES} bytes')

      if new_password == current_password:
        raise ValueError('The new password must be different from the current one')

      user.password_hash = hash_password(new_password)
      user.must_change_password = False
      self.repository.update(user)
    finally:
      self.repository.close()

class UserDeactivator:
  """User deactivation (§8.14)."""

  def __init__(self,repository:UserRepository) -> None:
    self.repository = repository

  def invoke(self,actor:AuthenticatedUser,email:str)->UserProfile:
    if not actor.has_permission(Action.MANAGE_USERS):
      raise PermissionDenied('You do not have permission to manage users')

    try:
      # Active admins are locked first: two concurrent deactivations run
      # one after the other and the second one sees the result of the first (§7)
      admins = self.repository.find_active_admins_for_update()

      user = self.repository.find_by_email_for_update(email)
      if user is None:
        raise ValueError(f'No user exists with the email {email}')

      if not user.active:
        raise ValueError(f'The user {email} is already inactive')

      # At least one active admin (§7)
      if user in admins and len(admins) == 1:
        raise ValueError('Cannot deactivate the only active admin')

      user.active = False

      profile = UserProfile.of(user)
      self.repository.update(user)
      return profile
    finally:
      self.repository.close()
