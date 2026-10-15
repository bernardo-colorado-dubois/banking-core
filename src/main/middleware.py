from functools import wraps
from dependency_injector.wiring import inject, Provide

from src.main.container import DIContainer
from src.main.utils import bearer_token
from src.user.application_service import UserAuthenticator

def authenticated(allow_pending_password: bool = False):
  """Requires a valid token and passes the authenticated user to the view as `actor`."""
  def decorator(view):
    @wraps(view)
    @inject
    def wrapper(*args, authenticator: UserAuthenticator = Provide[DIContainer.user_authenticator], **kwargs):
      actor = authenticator.invoke(bearer_token(), allow_pending_password)
      return view(*args, actor=actor, **kwargs)
    return wrapper
  return decorator
