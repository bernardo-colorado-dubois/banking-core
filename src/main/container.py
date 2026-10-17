from dependency_injector.containers import DeclarativeContainer 
from dependency_injector.providers import Singleton, Factory, Configuration

from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from src.user.domain_model import UserRepository, RoleRepository
from src.account.domain_model import LedgerRepository
from src.account.application_service import ClientSignup, VostroAccountOpener, NostroAccountOpener
from src.account.application_service import AccountFunder, AccountWithdrawer, AccountTransfer, AccountBalanceReader
from src.account.application_service import AccountLister, TransactionReverser
from src.user.application_service import UserCreator, UserSignup, UserLogin, UserAuthenticator, UserProfileReader, PasswordChanger
from src.user.application_service import UserDeactivator

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
    jwt_minutes=config.jwt_expiration_minutes
  )
  user_authenticator = Factory(
    UserAuthenticator,
    repository=user_repository,
    jwt_secret=config.jwt_secret
  )
  user_profile_reader = Factory(UserProfileReader, repository=user_repository)
  password_changer = Factory(PasswordChanger, repository=user_repository)
  user_deactivator = Factory(UserDeactivator, repository=user_repository)

  ledger_repository = Factory(LedgerRepository, session=session)

  client_signup = Factory(
    ClientSignup,
    repository=ledger_repository,
    user_repository=user_repository,
    role_repository=role_repository
  )
  vostro_account_opener = Factory(
    VostroAccountOpener,
    repository=ledger_repository,
    user_repository=user_repository
  )
  nostro_account_opener = Factory(
    NostroAccountOpener,
    repository=ledger_repository,
    bank_name=config.bank_name
  )
  account_lister = Factory(
    AccountLister,
    repository=ledger_repository,
    bank_name=config.bank_name
  )
  account_funder = Factory(AccountFunder, repository=ledger_repository)
  account_withdrawer = Factory(AccountWithdrawer, repository=ledger_repository)
  account_transfer = Factory(AccountTransfer, repository=ledger_repository)
  account_balance_reader = Factory(AccountBalanceReader, repository=ledger_repository)
  transaction_reverser = Factory(TransactionReverser, repository=ledger_repository)
