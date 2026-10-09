from bcrypt import hashpw, gensalt, checkpw

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
