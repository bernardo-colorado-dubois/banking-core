class AuthenticationError(Exception):
  """Invalid credentials or token (401)."""

class PermissionDenied(Exception):
  """The authenticated user lacks the required permission (403)."""
