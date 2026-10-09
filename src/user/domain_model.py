from src.main.database import Base
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Table, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from datetime import datetime
from enum import Enum
from typing import List
from uuid import UUID, uuid4

class Accion(Enum):
  VER = "VER"
  FONDEAR = "FONDEAR"
  RETIRAR = "RETIRAR"
  TRANSFERIR = "TRANSFERIR"
  ABRIR_CUENTA = "ABRIR_CUENTA"
  GESTIONAR_USUARIOS = "GESTIONAR_USUARIOS"

class Alcance(Enum):
  PROPIAS = "PROPIAS"   # cuentas cuyo titular es el usuario autenticado
  VOSTRO = "VOSTRO"     # cualquier cuenta de cliente
  NOSTRO = "NOSTRO"     # cuentas del banco

rol_permisos = Table(
  'rol_permisos',
  Base.metadata,
  Column('rol_id', ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
  Column('permiso_id', ForeignKey('permisos.id', ondelete='CASCADE'), primary_key=True),
)

class Permission(Base):

  __tablename__ = 'permisos'
  __table_args__ = (
    UniqueConstraint('accion', 'alcance', postgresql_nulls_not_distinct=True),
    CheckConstraint(
      "(accion = 'GESTIONAR_USUARIOS' AND alcance IS NULL) OR (accion <> 'GESTIONAR_USUARIOS' AND alcance IS NOT NULL)",
      name='alcance_segun_accion',
    ),
    CheckConstraint("accion <> 'ABRIR_CUENTA' OR alcance <> 'PROPIAS'", name='abrir_cuenta_sin_propias'),
  )

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  accion: Mapped[Accion] = mapped_column(nullable=False)
  alcance: Mapped[Alcance | None] = mapped_column(nullable=True)

class Role(Base):

  __tablename__ = 'roles'

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  nombre: Mapped[str] = mapped_column(unique=True, nullable=False)
  descripcion: Mapped[str | None] = mapped_column(nullable=True)
  permisos: Mapped[List[Permission]] = relationship(secondary=rol_permisos)

class User(Base):

  __tablename__ = 'usuarios'

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  email: Mapped[str] = mapped_column(unique=True, nullable=False)
  password_hash: Mapped[str] = mapped_column(nullable=False)
  rol_id: Mapped[UUID] = mapped_column(ForeignKey('roles.id'), nullable=False)
  activo: Mapped[bool] = mapped_column(default=True, nullable=False)
  debe_cambiar_password: Mapped[bool] = mapped_column(default=False, nullable=False)
  creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
  rol: Mapped[Role] = relationship()


class RoleRepository:

  def __init__(self,session:Session) -> None:
    self.session = session

  def find_all(self):
    return self.session.query(Role).all()

  def find_by_name(self,nombre:str)->Role|None:
    return self.session.query(Role).filter(Role.nombre==nombre).one_or_none()

  def close(self)->None:
    self.session.close()


class UserRepository:

  def __init__(self,session:Session) -> None:
    self.session = session

  def find_all(self):
    return self.session.query(User).all()

  def find_by_id(self,id:UUID)->User|None:
    return self.session.query(User).filter(User.id==id).one_or_none()

  def find_by_email(self,email:str)->User|None:
    return self.session.query(User).filter(User.email==email).one_or_none()

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
