from flask import Blueprint, jsonify
from dependency_injector.wiring import inject, Provide

from src.main.container import DIContainer
from src.main.middleware import authenticated
from src.main.utils import json_body
from src.account.application_service import ClientSignup, VostroAccountOpener, NostroAccountOpener
from src.account.dto import AccountDetail
from src.user.dto import UserCreate, AuthenticatedUser

blueprint = Blueprint("account", __name__)

@blueprint.route("/")
def hello_account():
  return jsonify(mensaje="Hello, Account!")

def texto(data: dict, campo: str) -> str | None:
  """Devuelve el campo sin espacios alrededor, o None si falta o viene vacío."""
  valor = data.get(campo)
  if not isinstance(valor, str) or not valor.strip():
    return None
  return valor.strip()

def account_json(account: AccountDetail):
  return jsonify(
    id=str(account.id),
    clase=account.clase.value,
    alias=account.alias,
    titular=account.titular,
    titular_id=str(account.titular_id) if account.titular_id else None,
    creada_en=account.creada_en.isoformat()
  )

# §8.3 Alta de cliente con su primera cuenta VOSTRO
@blueprint.route("/cliente", methods=["POST"])
@authenticated()
@inject
def signup_cliente(
  actor: AuthenticatedUser,
  client_signup: ClientSignup = Provide[DIContainer.client_signup]
):
  data = json_body()
  email = texto(data, 'email')
  nombre = texto(data, 'nombre')
  alias = texto(data, 'alias')
  password = data.get('password')
  if email is None or nombre is None or alias is None or not isinstance(password, str) or not password:
    return jsonify(error='email, password, nombre y alias son obligatorios'), 400

  # El DTO deja activo y debe_cambiar_password en true (§8, reglas de alta)
  try:
    account = client_signup.invoque(actor, UserCreate(email=email, password=password, rol='CLIENTE', nombre=nombre), alias)
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return account_json(account), 201

# §8.4 Cuenta VOSTRO adicional para un cliente existente
@blueprint.route("/vostro", methods=["POST"])
@authenticated()
@inject
def open_vostro(
  actor: AuthenticatedUser,
  vostro_account_opener: VostroAccountOpener = Provide[DIContainer.vostro_account_opener]
):
  data = json_body()
  email = texto(data, 'email')
  alias = texto(data, 'alias')
  if email is None or alias is None:
    return jsonify(error='email y alias son obligatorios'), 400

  try:
    account = vostro_account_opener.invoque(actor, email, alias)
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return account_json(account), 201

# §8.13 Apertura de cuenta NOSTRO
@blueprint.route("/nostro", methods=["POST"])
@authenticated()
@inject
def open_nostro(
  actor: AuthenticatedUser,
  nostro_account_opener: NostroAccountOpener = Provide[DIContainer.nostro_account_opener]
):
  data = json_body()
  alias = texto(data, 'alias')
  if alias is None:
    return jsonify(error='alias es obligatorio'), 400

  try:
    account = nostro_account_opener.invoque(actor, alias)
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return account_json(account), 201
