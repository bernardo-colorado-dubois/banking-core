from dependency_injector.containers import DeclarativeContainer 
from dependency_injector.providers import Singleton, Factory, Configuration

from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from src.user.domain_model import UserRepository, RoleRepository
from src.user.application_service import UserCreator, UserSignup, UserLogin, UserAuthenticator, PasswordChanger

class DIContainer(DeclarativeContainer):

  config = Configuration()

  engine = Singleton(create_engine, config.connection_string)
  session = Factory(Session, bind=engine, expire_on_commit=False)

  user_repository = Factory(UserRepository, session=session)
  role_repository = Factory(RoleRepository, session=session)

  user_creator = Factory(
    UserCreator,
    repository=user_repository,
    role_repository=role_repository
  )
  user_signup = Factory(UserSignup, user_creator=user_creator)
  user_login = Factory(
    UserLogin,
    repository=user_repository,
    jwt_secret=config.jwt_secret,
    jwt_minutes=config.jwt_expiracion_minutos
  )
  user_authenticator = Factory(
    UserAuthenticator,
    repository=user_repository,
    jwt_secret=config.jwt_secret
  )
  password_changer = Factory(PasswordChanger, repository=user_repository)
