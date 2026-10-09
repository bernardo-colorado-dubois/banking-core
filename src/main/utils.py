from bcrypt import hashpw, gensalt, checkpw
from datetime import datetime, timedelta, timezone
from flask import request
import jwt

# bcrypt solo admite contraseñas de hasta 72 bytes (no caracteres)
MAX_PASSWORD_BYTES = 72

def hash_password(password: str) -> str:
  """Hash a password using bcrypt."""
  return hashpw(password.encode('utf-8'), gensalt()).decode('utf-8')

def check_password(password: str, hashed: str) -> bool:
  """Check if a password matches the hashed password."""
  try:
    return checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
  except ValueError:
    # Contraseña de más de 72 bytes o hash que no es bcrypt: no coincide
    return False

def create_token(user_id: str, rol: str, secret: str, minutes: int) -> str:
  """Create a signed HS256 access token with the user id and role name."""
  now = datetime.now(timezone.utc)
  payload = {'sub': user_id, 'rol': rol, 'iat': now, 'exp': now + timedelta(minutes=minutes)}
  return jwt.encode(payload, secret, algorithm='HS256')

def decode_token(token: str, secret: str) -> dict | None:
  """Return the token payload, or None if it is invalid or expired."""
  try:
    return jwt.decode(token, secret, algorithms=['HS256'], options={'require': ['sub', 'exp']})
  except jwt.InvalidTokenError:
    return None

def bearer_token() -> str | None:
  """Read the token from the Authorization: Bearer <token> header."""
  scheme, _, token = request.headers.get('Authorization', '').partition(' ')
  if scheme.lower() != 'bearer' or not token.strip():
    return None
  return token.strip()

def json_body() -> dict:
  """Read the request body as a JSON object ({} if it is not one)."""
  data = request.get_json(silent=True)
  return data if isinstance(data, dict) else {}
