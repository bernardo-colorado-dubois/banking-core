class AuthenticationError(Exception):
  """Credenciales o token inválidos (401)."""

class PermissionDenied(Exception):
  """El usuario autenticado no tiene el permiso requerido (403)."""
