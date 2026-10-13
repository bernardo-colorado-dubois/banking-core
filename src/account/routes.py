from uuid import UUID

from flask import Blueprint, jsonify
from dependency_injector.wiring import inject, Provide

from src.main.container import DIContainer
from src.main.middleware import authenticated
from src.main.utils import json_body
from src.account.application_service import ClientSignup, VostroAccountOpener, NostroAccountOpener
from src.account.application_service import AccountFunder, AccountWithdrawer, AccountTransfer, AccountBalanceReader
from src.account.application_service import AccountLister, TransactionReverser
from src.account.dto import AccountDetail, OperationResult
from src.user.dto import UserCreate, AuthenticatedUser

blueprint = Blueprint("account", __name__)

def texto(data: dict, campo: str) -> str | None:
  """Devuelve el campo sin espacios alrededor, o None si falta o viene vacío."""
  valor = data.get(campo)
  if not isinstance(valor, str) or not valor.strip():
    return None
  return valor.strip()

def account_dict(account: AccountDetail) -> dict:
  return dict(
    id=str(account.id),
    clase=account.clase.value,
    alias=account.alias,
    titular=account.titular,
    titular_id=str(account.titular_id) if account.titular_id else None,
    creada_en=account.creada_en.isoformat()
  )

def account_json(account: AccountDetail):
  return jsonify(account_dict(account))

# Lista de todas las cuentas, NOSTRO y VOSTRO, con su titular y su saldo actual (§7)
@blueprint.route("/", methods=["GET"])
@authenticated()
@inject
def list_accounts(
  actor: AuthenticatedUser,
  account_lister: AccountLister = Provide[DIContainer.account_lister]
):
  return jsonify(cuentas=[account_dict(account) | dict(saldo=str(account.saldo)) for account in account_lister.invoque(actor)])

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

# Los montos viajan como texto con 2 decimales, nunca como float (§4.4)
def operation_json(result: OperationResult):
  return jsonify(
    transaccion_id=str(result.transaccion_id),
    tipo=result.tipo.value,
    monto=str(result.monto),
    cuenta_id=str(result.cuenta_id),
    cuenta_destino_id=str(result.cuenta_destino_id) if result.cuenta_destino_id else None,
    saldo=str(result.saldo),
    creada_en=result.creada_en.isoformat()
  )

# §8.5 y §8.10 Fondeo
@blueprint.route("/<uuid:cuenta_id>/fondeo", methods=["POST"])
@authenticated()
@inject
def fund(
  cuenta_id: UUID,
  actor: AuthenticatedUser,
  account_funder: AccountFunder = Provide[DIContainer.account_funder]
):
  data = json_body()
  if 'monto' not in data:
    return jsonify(error='monto es obligatorio'), 400

  try:
    result = account_funder.invoque(actor, cuenta_id, data['monto'])
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return operation_json(result), 201

# §8.6 y §8.11 Retiro
@blueprint.route("/<uuid:cuenta_id>/retiro", methods=["POST"])
@authenticated()
@inject
def withdraw(
  cuenta_id: UUID,
  actor: AuthenticatedUser,
  account_withdrawer: AccountWithdrawer = Provide[DIContainer.account_withdrawer]
):
  data = json_body()
  if 'monto' not in data:
    return jsonify(error='monto es obligatorio'), 400

  try:
    result = account_withdrawer.invoque(actor, cuenta_id, data['monto'])
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return operation_json(result), 201

# §8.7 y §8.12 Transferencia: la cuenta de la ruta es el origen
@blueprint.route("/<uuid:cuenta_id>/transferencia", methods=["POST"])
@authenticated()
@inject
def transfer(
  cuenta_id: UUID,
  actor: AuthenticatedUser,
  account_transfer: AccountTransfer = Provide[DIContainer.account_transfer]
):
  data = json_body()
  if 'monto' not in data or 'cuenta_destino_id' not in data:
    return jsonify(error='cuenta_destino_id y monto son obligatorios'), 400

  try:
    cuenta_destino_id = UUID(data['cuenta_destino_id'])
  except (ValueError, TypeError, AttributeError):
    return jsonify(error='cuenta_destino_id no es válido'), 400

  try:
    result = account_transfer.invoque(actor, cuenta_id, cuenta_destino_id, data['monto'])
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return operation_json(result), 201

# §8.8 y §8.9 Consulta de saldo: el historial de movimientos con el saldo tras cada uno.
# No hay saldo global en la cabecera; el actual es el del último movimiento
@blueprint.route("/<uuid:cuenta_id>/saldo", methods=["GET"])
@authenticated()
@inject
def balance(
  cuenta_id: UUID,
  actor: AuthenticatedUser,
  account_balance_reader: AccountBalanceReader = Provide[DIContainer.account_balance_reader]
):
  try:
    saldo = account_balance_reader.invoque(actor, cuenta_id)
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return jsonify(
    cuenta_id=str(saldo.cuenta_id),
    clase=saldo.clase.value,
    alias=saldo.alias,
    movimientos=[
      dict(
        movimiento_id=str(movimiento.movimiento_id),
        transaccion_id=str(movimiento.transaccion_id),
        tipo=movimiento.tipo.value,
        naturaleza=movimiento.naturaleza.value,
        monto=str(movimiento.monto),
        saldo=str(movimiento.saldo),
        creado_en=movimiento.creado_en.isoformat()
      )
      for movimiento in saldo.movimientos
    ]
  )

# §8.15 Reverso. No lleva cuerpo: la transacción de la ruta se reversa completa
@blueprint.route("/transaccion/<uuid:transaccion_id>/reverso", methods=["POST"])
@authenticated()
@inject
def reverse(
  transaccion_id: UUID,
  actor: AuthenticatedUser,
  transaction_reverser: TransactionReverser = Provide[DIContainer.transaction_reverser]
):
  try:
    result = transaction_reverser.invoque(actor, transaccion_id)
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return jsonify(
    transaccion_id=str(result.transaccion_id),
    tipo='REVERSO',
    transaccion_original_id=str(result.transaccion_original_id),
    tipo_original=result.tipo_original.value,
    monto=str(result.monto),
    cuentas=[dict(cuenta_id=str(cuenta_id), saldo=str(saldo)) for cuenta_id, saldo in result.saldos.items()],
    creada_en=result.creada_en.isoformat()
  ), 201
