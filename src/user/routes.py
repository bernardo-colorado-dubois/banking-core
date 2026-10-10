from flask import Blueprint, jsonify, request
from dependency_injector.wiring import inject, Provide

from src.main.container import DIContainer
from src.main.middleware import authenticated
from src.main.utils import json_body
from src.user.application_service import UserSignup, UserLogin, UserProfileReader, PasswordChanger
from src.user.dto import UserCreate, AuthenticatedUser

blueprint = Blueprint("user", __name__)

# Perfil del usuario autenticado. Se permite con la contraseña pendiente
# para que el cliente pueda leer debe_cambiar_password (§7)
@blueprint.route("/")
@authenticated(permitir_password_pendiente=True)
@inject
def profile(
  actor: AuthenticatedUser,
  user_profile_reader: UserProfileReader = Provide[DIContainer.user_profile_reader]
):
  perfil = user_profile_reader.invoque(actor)
  return jsonify(
    id=str(perfil.id),
    email=perfil.email,
    rol=perfil.rol,
    activo=perfil.activo,
    debe_cambiar_password=perfil.debe_cambiar_password,
    creado_en=perfil.creado_en.isoformat()
  )

# §7 Autenticación: email y contraseña a cambio del access token
@blueprint.route("/login", methods=["POST"])
@inject
def login(user_login: UserLogin = Provide[DIContainer.user_login]):
  data = json_body()
  email = data.get('email')
  password = data.get('password')
  if not isinstance(email, str) or not email.strip() or not isinstance(password, str) or not password:
    return jsonify(error='email y password son obligatorios'), 400

  token, user = user_login.invoque(email.strip(), password)
  return jsonify(token=token, debe_cambiar_password=user.debe_cambiar_password)

# Cambio de contraseña: lo único permitido mientras debe_cambiar_password sea true (§7)
@blueprint.route("/password", methods=["POST"])
@authenticated(permitir_password_pendiente=True)
@inject
def change_password(
  actor: AuthenticatedUser,
  password_changer: PasswordChanger = Provide[DIContainer.password_changer]
):
  data = json_body()
  password_actual = data.get('password_actual')
  password_nueva = data.get('password_nueva')
  if not isinstance(password_actual, str) or not password_actual or not isinstance(password_nueva, str) or not password_nueva:
    return jsonify(error='password_actual y password_nueva son obligatorios'), 400

  try:
    password_changer.invoque(actor, password_actual, password_nueva)
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return jsonify(debe_cambiar_password=False)

def signup(rol: str, email, password, actor: AuthenticatedUser, user_signup: UserSignup):
  if not isinstance(email, str) or not email.strip() or not isinstance(password, str) or not password:
    return jsonify(error='email y password son obligatorios'), 400

  # El DTO deja activo y debe_cambiar_password en true (§8, reglas de alta)
  try:
    user = user_signup.invoque(actor, UserCreate(email=email.strip(), password=password, rol=rol))
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return jsonify(
    id=str(user.id),
    email=user.email,
    rol=rol,
    activo=user.activo,
    debe_cambiar_password=user.debe_cambiar_password
  ), 201

# §8.1 Alta de administrador
@blueprint.route("/admin", methods=["POST"])
@authenticated()
@inject
def signup_admin(
  actor: AuthenticatedUser,
  user_signup: UserSignup = Provide[DIContainer.user_signup]
):
  data = json_body()
  email = data.get('email')
  password = data.get('password')

  return signup('ADMIN', email, password, actor, user_signup)

# §8.2 Alta de operador
@blueprint.route("/operador", methods=["POST"])
@authenticated()
@inject
def signup_operador(
  actor: AuthenticatedUser,
  user_signup: UserSignup = Provide[DIContainer.user_signup]
):
  data = json_body()
  email = data.get('email')
  password = data.get('password')

  return signup('OPERADOR', email, password, actor, user_signup)
