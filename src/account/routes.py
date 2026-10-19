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

def text(data: dict, field: str) -> str | None:
  """Returns the field without surrounding whitespace, or None if missing or empty."""
  value = data.get(field)
  if not isinstance(value, str) or not value.strip():
    return None
  return value.strip()

def account_dict(account: AccountDetail) -> dict:
  return dict(
    id=str(account.id),
    account_class=account.account_class.value,
    alias=account.alias,
    holder=account.holder,
    holder_id=str(account.holder_id) if account.holder_id else None,
    created_at=account.created_at.isoformat()
  )

def account_json(account: AccountDetail):
  return jsonify(account_dict(account))

# List of accounts with their holder and current balance (§7): every NOSTRO and VOSTRO, or the client's own
@blueprint.route("/", methods=["GET"])
@authenticated()
@inject
def list_accounts(
  actor: AuthenticatedUser,
  account_lister: AccountLister = Provide[DIContainer.account_lister]
):
  return jsonify(accounts=[account_dict(account) | dict(balance=str(account.balance)) for account in account_lister.invoke(actor)])

# §8.3 Client signup with their first VOSTRO account
@blueprint.route("/client", methods=["POST"])
@authenticated()
@inject
def signup_client(
  actor: AuthenticatedUser,
  client_signup: ClientSignup = Provide[DIContainer.client_signup]
):
  data = json_body()
  email = text(data, 'email')
  name = text(data, 'name')
  alias = text(data, 'alias')
  password = data.get('password')
  if email is None or name is None or alias is None or not isinstance(password, str) or not password:
    return jsonify(error='email, password, name and alias are required'), 400

  # The DTO leaves active and must_change_password set to true (§8, signup rules)
  try:
    account = client_signup.invoke(actor, UserCreate(email=email, password=password, role='CLIENT', name=name), alias)
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return account_json(account), 201

# §8.4 Additional VOSTRO account for an existing client
@blueprint.route("/vostro", methods=["POST"])
@authenticated()
@inject
def open_vostro(
  actor: AuthenticatedUser,
  vostro_account_opener: VostroAccountOpener = Provide[DIContainer.vostro_account_opener]
):
  data = json_body()
  email = text(data, 'email')
  alias = text(data, 'alias')
  if email is None or alias is None:
    return jsonify(error='email and alias are required'), 400

  try:
    account = vostro_account_opener.invoke(actor, email, alias)
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return account_json(account), 201

# §8.13 NOSTRO account opening
@blueprint.route("/nostro", methods=["POST"])
@authenticated()
@inject
def open_nostro(
  actor: AuthenticatedUser,
  nostro_account_opener: NostroAccountOpener = Provide[DIContainer.nostro_account_opener]
):
  data = json_body()
  alias = text(data, 'alias')
  if alias is None:
    return jsonify(error='alias is required'), 400

  try:
    account = nostro_account_opener.invoke(actor, alias)
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return account_json(account), 201

# Amounts travel as text with 2 decimals, never as float (§4.4)
def operation_json(result: OperationResult):
  return jsonify(
    transaction_id=str(result.transaction_id),
    type=result.type.value,
    amount=str(result.amount),
    account_id=str(result.account_id),
    destination_account_id=str(result.destination_account_id) if result.destination_account_id else None,
    balance=str(result.balance),
    created_at=result.created_at.isoformat()
  )

# §8.5 and §8.10 Deposit
@blueprint.route("/<uuid:account_id>/deposit", methods=["POST"])
@authenticated()
@inject
def deposit(
  account_id: UUID,
  actor: AuthenticatedUser,
  account_funder: AccountFunder = Provide[DIContainer.account_funder]
):
  data = json_body()
  if 'amount' not in data:
    return jsonify(error='amount is required'), 400

  try:
    result = account_funder.invoke(actor, account_id, data['amount'])
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return operation_json(result), 201

# §8.6 and §8.11 Withdrawal
@blueprint.route("/<uuid:account_id>/withdrawal", methods=["POST"])
@authenticated()
@inject
def withdraw(
  account_id: UUID,
  actor: AuthenticatedUser,
  account_withdrawer: AccountWithdrawer = Provide[DIContainer.account_withdrawer]
):
  data = json_body()
  if 'amount' not in data:
    return jsonify(error='amount is required'), 400

  try:
    result = account_withdrawer.invoke(actor, account_id, data['amount'])
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return operation_json(result), 201

# §8.7 and §8.12 Transfer: the account in the path is the source
@blueprint.route("/<uuid:account_id>/transfer", methods=["POST"])
@authenticated()
@inject
def transfer(
  account_id: UUID,
  actor: AuthenticatedUser,
  account_transfer: AccountTransfer = Provide[DIContainer.account_transfer]
):
  data = json_body()
  if 'amount' not in data or 'destination_account_id' not in data:
    return jsonify(error='destination_account_id and amount are required'), 400

  try:
    destination_account_id = UUID(data['destination_account_id'])
  except (ValueError, TypeError, AttributeError):
    return jsonify(error='destination_account_id is not valid'), 400

  try:
    result = account_transfer.invoke(actor, account_id, destination_account_id, data['amount'])
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return operation_json(result), 201

# §8.8 and §8.9 Balance inquiry: the movement history with the balance after each one.
# There is no overall balance in the header; the current one is the last movement's
@blueprint.route("/<uuid:account_id>/balance", methods=["GET"])
@authenticated()
@inject
def balance(
  account_id: UUID,
  actor: AuthenticatedUser,
  account_balance_reader: AccountBalanceReader = Provide[DIContainer.account_balance_reader]
):
  try:
    balance = account_balance_reader.invoke(actor, account_id)
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return jsonify(
    account_id=str(balance.account_id),
    account_class=balance.account_class.value,
    alias=balance.alias,
    movements=[
      dict(
        movement_id=str(movement.movement_id),
        transaction_id=str(movement.transaction_id),
        type=movement.type.value,
        entry_type=movement.entry_type.value,
        amount=str(movement.amount),
        balance=str(movement.balance),
        created_at=movement.created_at.isoformat()
      )
      for movement in balance.movements
    ]
  )

# §8.15 Reversal. No body: the transaction in the path is fully reversed
@blueprint.route("/transaction/<uuid:transaction_id>/reversal", methods=["POST"])
@authenticated()
@inject
def reverse(
  transaction_id: UUID,
  actor: AuthenticatedUser,
  transaction_reverser: TransactionReverser = Provide[DIContainer.transaction_reverser]
):
  try:
    result = transaction_reverser.invoke(actor, transaction_id)
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return jsonify(
    transaction_id=str(result.transaction_id),
    type='REVERSAL',
    original_transaction_id=str(result.original_transaction_id),
    original_type=result.original_type.value,
    amount=str(result.amount),
    accounts=[dict(account_id=str(account_id), balance=str(balance)) for account_id, balance in result.balances.items()],
    created_at=result.created_at.isoformat()
  ), 201
