from src.main.container import DIContainer
from src.main.database import Base
from src.user.domain_model import Role,Permission,Action,Scope
from src.user.dto import UserCreate
from dotenv import load_dotenv
import os

# Always load environment variables
load_dotenv()

# Read environment variables
database_url = os.getenv("DATABASE_URL")
admin_email = os.getenv("ADMIN_EMAIL")
admin_password = os.getenv("ADMIN_PASSWORD")

# Initialize the container
container = DIContainer()
container.config.connection_string.override(database_url)
engine = container.engine()

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)

# Fixed seed of roles and permissions (§9, Seed data)
operations = [Action.VIEW, Action.DEPOSIT, Action.WITHDRAW, Action.TRANSFER]
roles = {
  'CLIENT': [(action, Scope.OWN) for action in operations],
  'OPERATOR': [(action, Scope.NOSTRO) for action in operations] + [
    (Action.OPEN_ACCOUNT, Scope.NOSTRO),
    (Action.VIEW, Scope.VOSTRO),
    (Action.OPEN_ACCOUNT, Scope.VOSTRO),
  ],
  'ADMIN': [(action, scope) for scope in (Scope.VOSTRO, Scope.NOSTRO) for action in operations] + [
    (Action.OPEN_ACCOUNT, Scope.VOSTRO),
    (Action.OPEN_ACCOUNT, Scope.NOSTRO),
    (Action.REVERSE, Scope.VOSTRO),
    (Action.REVERSE, Scope.NOSTRO),
    (Action.MANAGE_USERS, None),
  ],
}

session = container.session()
permissions = {}
for name, keys in roles.items():
  for key in keys:
    if key not in permissions:
      permissions[key] = Permission(action=key[0], scope=key[1])
  session.add(Role(name=name, permissions=[permissions[key] for key in keys]))
session.commit()
session.close()

admins = [
  UserCreate(
    email=admin_email,
    password=admin_password,
    role='ADMIN',
    active=True,
    must_change_password=True
  )
]

service = container.user_creator()

for admin in admins:
  service.invoke(dto=admin)
