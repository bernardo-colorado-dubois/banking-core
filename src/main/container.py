from dependency_injector.containers import DeclarativeContainer 
from dependency_injector.providers import Singleton, Factory, Configuration

from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from src.user.domain_model import UserRepository, RoleRepository
from src.account.domain_model import AccountRepository
from src.account.application_service import ClientSignup, VostroAccountOpener, NostroAccountOpener
from src.account.application_service import AccountFunder, AccountWithdrawer, AccountTransfer, AccountBalanceReader
from src.user.application_service import UserCreator, UserSignup, UserLogin, UserAuthenticator, UserProfileReader, PasswordChanger

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
  user_profile_reader = Factory(UserProfileReader, repository=user_repository)
  password_changer = Factory(PasswordChanger, repository=user_repository)

  account_repository = Factory(AccountRepository, session=session)

  client_signup = Factory(
    ClientSignup,
    repository=account_repository,
    user_repository=user_repository,
    role_repository=role_repository
  )
  vostro_account_opener = Factory(
    VostroAccountOpener,
    repository=account_repository,
    user_repository=user_repository
  )
  nostro_account_opener = Factory(
    NostroAccountOpener,
    repository=account_repository,
    banco_nombre=config.banco_nombre
  )
  account_funder = Factory(AccountFunder, repository=account_repository)
  account_withdrawer = Factory(AccountWithdrawer, repository=account_repository)
  account_transfer = Factory(AccountTransfer, repository=account_repository)
  account_balance_reader = Factory(AccountBalanceReader, repository=account_repository)
