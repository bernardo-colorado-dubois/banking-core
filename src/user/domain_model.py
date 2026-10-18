from src.main.database import Base
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Table, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, joinedload, Session
from datetime import datetime
from enum import Enum
from typing import List
from uuid import UUID, uuid4

class Action(Enum):
  VIEW = "VIEW"
  DEPOSIT = "DEPOSIT"
  WITHDRAW = "WITHDRAW"
  TRANSFER = "TRANSFER"
  OPEN_ACCOUNT = "OPEN_ACCOUNT"
  REVERSE = "REVERSE"
  MANAGE_USERS = "MANAGE_USERS"

class Scope(Enum):
  OWN = "OWN"           # accounts held by the authenticated user
  VOSTRO = "VOSTRO"     # any client account
  NOSTRO = "NOSTRO"     # the bank's own accounts

role_permissions = Table(
  'role_permissions',
  Base.metadata,
  Column('role_id', ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
  Column('permission_id', ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True),
)

class Permission(Base):

  __tablename__ = 'permissions'
  __table_args__ = (
    UniqueConstraint('action', 'scope', postgresql_nulls_not_distinct=True),
    CheckConstraint(
      "(action = 'MANAGE_USERS' AND scope IS NULL) OR (action <> 'MANAGE_USERS' AND scope IS NOT NULL)",
      name='scope_by_action',
    ),
    CheckConstraint("action <> 'OPEN_ACCOUNT' OR scope <> 'OWN'", name='open_account_without_own'),
  )

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  action: Mapped[Action] = mapped_column(nullable=False)
  scope: Mapped[Scope | None] = mapped_column(nullable=True)

class Role(Base):

  __tablename__ = 'roles'

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  name: Mapped[str] = mapped_column(unique=True, nullable=False)
  description: Mapped[str | None] = mapped_column(nullable=True)
  permissions: Mapped[List[Permission]] = relationship(secondary=role_permissions)

class User(Base):

  __tablename__ = 'users'

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  email: Mapped[str] = mapped_column(unique=True, nullable=False)
  # Required for clients (§8.3): shown as the holder of their accounts
  name: Mapped[str | None] = mapped_column(nullable=True)
  password_hash: Mapped[str] = mapped_column(nullable=False)
  role_id: Mapped[UUID] = mapped_column(ForeignKey('roles.id'), nullable=False)
  active: Mapped[bool] = mapped_column(default=True, nullable=False)
  must_change_password: Mapped[bool] = mapped_column(default=False, nullable=False)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
  role: Mapped[Role] = relationship()


class RoleRepository:

  def __init__(self,session:Session) -> None:
    self.session = session

  def find_all(self):
    return self.session.query(Role).all()

  def find_by_name(self,name:str)->Role|None:
    return self.session.query(Role).filter(Role.name==name).one_or_none()

  def close(self)->None:
    self.session.close()


class UserRepository:

  def __init__(self,session:Session) -> None:
    self.session = session

  # Oldest to newest, with the role loaded in the same query
  def find_all(self)->List[User]:
    return self.session.query(User).options(joinedload(User.role)).order_by(User.created_at, User.id).all()

  def find_by_id(self,id:UUID)->User|None:
    return self.session.query(User).filter(User.id==id).one_or_none()

  def find_by_email(self,email:str)->User|None:
    return self.session.query(User).filter(User.email==email).one_or_none()

  def find_by_email_for_update(self,email:str)->User|None:
    return self.session.query(User).filter(User.email==email).with_for_update().one_or_none()

  # Locks the active admins' rows, ordered by id so locks never cross (§7)
  def find_active_admins_for_update(self)->List[User]:
    return (
      self.session.query(User)
      .join(User.role)
      .filter(Role.name=='ADMIN', User.active.is_(True))
      .order_by(User.id)
      .with_for_update(of=User)
      .all()
    )

  def close(self)->None:
    self.session.close()

  def update(self,user:User)->None:
    try:
      self.session.commit()
    except:
      self.session.rollback()
      raise
    finally:
      self.session.close()

  def save(self,user:User)->None:
    try:
      self.session.add(user)
      self.session.commit()
    except:
      self.session.rollback()
      raise
    finally:
      self.session.close()
