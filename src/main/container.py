from dependency_injector.containers import DeclarativeContainer 
from dependency_injector.providers import Singleton, Factory, Configuration

from sqlalchemy.orm import Session
from sqlalchemy import create_engine

class DIContainer(DeclarativeContainer):

  config = Configuration()

  engine = Singleton(create_engine, config.connection_string)
  session = Factory(Session, bind=engine)
