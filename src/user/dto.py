from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.main.utils import MAX_PASSWORD_BYTES
from src.user.domain_model import Action, Scope, User

@dataclass
class UserCreate:
  email: str
  password: str
  role: str
  active: bool = True
  must_change_password: bool = True
  name: str | None = None

  def __post_init__(self) -> None:
    if len(self.password.encode('utf-8')) > MAX_PASSWORD_BYTES:
      raise ValueError(f'The password cannot exceed {MAX_PASSWORD_BYTES} bytes')

@dataclass(frozen=True)
class UserProfile:
  """Non-sensitive user data: never includes the password hash."""
  id: UUID
  email: str
  name: str | None
  role: str
  active: bool
  must_change_password: bool
  created_at: datetime

  # Built before closing the session: the role is lazy-loaded
  @classmethod
  def of(cls, user: User) -> 'UserProfile':
    return cls(
      id=user.id,
      email=user.email,
      name=user.name,
      role=user.role.name,
      active=user.active,
      must_change_password=user.must_change_password,
      created_at=user.created_at
    )

@dataclass(frozen=True)
class AuthenticatedUser:
  id: UUID
  role: str
  permissions: frozenset[tuple[Action, Scope | None]]
  must_change_password: bool

  def has_permission(self, action: Action, scope: Scope | None = None) -> bool:
    return (action, scope) in self.permissions
