from functools import wraps
from dependency_injector.wiring import inject, Provide

from src.main.container import DIContainer
from src.main.utils import bearer_token
from src.user.application_service import UserAuthenticator

def authenticated(permitir_password_pendiente: bool = False):
  """Exige un token válido y pasa el usuario autenticado a la ruta como `actor`."""
  def decorator(view):
    @wraps(view)
    @inject
    def wrapper(*args, authenticator: UserAuthenticator = Provide[DIContainer.user_authenticator], **kwargs):
      actor = authenticator.invoque(bearer_token(), permitir_password_pendiente)
      return view(*args, actor=actor, **kwargs)
    return wrapper
  return decorator
