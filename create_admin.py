from src.main.container import DIContainer
from src.main.database import Base
from src.user.domain_model import Role,Permission,Accion,Alcance
from src.user.dto import UserCreate
from dotenv import load_dotenv
import os

# Cargar variables de entorno siempre
load_dotenv()

# Acceder a las variables de entorno
database_url = os.getenv("DATABASE_URL")
admin_email = os.getenv("ADMIN_EMAIL")
admin_password = os.getenv("ADMIN_PASSWORD")

# Inicializar el contenedor
container = DIContainer()
container.config.connection_string.override(database_url)
engine = container.engine()

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)

# Semilla fija de roles y permisos (§9, Datos semilla)
operaciones = [Accion.VER, Accion.FONDEAR, Accion.RETIRAR, Accion.TRANSFERIR]
roles = {
  'CLIENTE': [(accion, Alcance.PROPIAS) for accion in operaciones],
  'OPERADOR': [(accion, Alcance.NOSTRO) for accion in operaciones] + [
    (Accion.ABRIR_CUENTA, Alcance.NOSTRO),
    (Accion.VER, Alcance.VOSTRO),
    (Accion.ABRIR_CUENTA, Alcance.VOSTRO),
  ],
  'ADMIN': [(accion, alcance) for alcance in (Alcance.VOSTRO, Alcance.NOSTRO) for accion in operaciones] + [
    (Accion.ABRIR_CUENTA, Alcance.VOSTRO),
    (Accion.ABRIR_CUENTA, Alcance.NOSTRO),
    (Accion.GESTIONAR_USUARIOS, None),
  ],
}

session = container.session()
permisos = {}
for nombre, claves in roles.items():
  for clave in claves:
    if clave not in permisos:
      permisos[clave] = Permission(accion=clave[0], alcance=clave[1])
  session.add(Role(nombre=nombre, permisos=[permisos[clave] for clave in claves]))
session.commit()
session.close()

admins = [
  UserCreate(
    email=admin_email,
    password=admin_password,
    rol='ADMIN',
    activo=True,
    debe_cambiar_password=True
  )
]

service = container.user_creator()

for admin in admins:
  service.invoque(dto=admin)
