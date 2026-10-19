from decimal import Decimal, InvalidOperation
from uuid import UUID

from src.account.domain_model import Ledger, LedgerRepository, AccountClass, TransactionType, Transaction
from src.account.dto import AccountDetail, AccountSummary, AccountBalance, AccountMovement, OperationResult, ReversalResult
from src.user.domain_model import User, UserRepository, RoleRepository, Action, Scope
from src.user.dto import UserCreate, AuthenticatedUser
from src.main.errors import PermissionDenied
from src.main.utils import hash_password

class ClientSignup:
  """Client signup with their first VOSTRO account (§8.3)."""

  def __init__(self,repository:LedgerRepository,user_repository:UserRepository,role_repository:RoleRepository) -> None:
    self.repository = repository
    self.user_repository = user_repository
    self.role_repository = role_repository

  def invoke(self,actor:AuthenticatedUser,dto:UserCreate,alias:str)->AccountDetail:
    # Does not require MANAGE_USERS: the signup is covered by OPEN_ACCOUNT:VOSTRO (§7)
    if not actor.has_permission(Action.OPEN_ACCOUNT, Scope.VOSTRO):
      raise PermissionDenied('You do not have permission to open client accounts')

    try:
      if self.user_repository.find_by_email(dto.email) is not None:
        raise ValueError(f'A user with the email {dto.email} already exists')

      role = self.role_repository.find_by_name('CLIENT')
      if role is None:
        raise ValueError('The role CLIENT does not exist')

      # Only the hash is persisted, never the plain-text password
      user = User(
        email=dto.email,
        name=dto.name,
        password_hash=hash_password(dto.password),
        role_id=role.id,
        active=dto.active,
        must_change_password=dto.must_change_password
      )
      # User, ledger and its two accounts go in a single commit: all are created or none is
      ledger = Ledger.open(AccountClass.VOSTRO, alias, holder=user)
      self.repository.save(ledger)

      return AccountDetail(
        id=ledger.id,
        account_class=ledger.account_class,
        alias=ledger.alias,
        holder=user.name,
        holder_id=user.id,
        created_at=ledger.created_at
      )
    finally:
      self.repository.close()
      self.user_repository.close()
      self.role_repository.close()

class VostroAccountOpener:
  """Additional VOSTRO account for an existing client (§8.4)."""

  def __init__(self,repository:LedgerRepository,user_repository:UserRepository) -> None:
    self.repository = repository
    self.user_repository = user_repository

  def invoke(self,actor:AuthenticatedUser,email:str,alias:str)->AccountDetail:
    if not actor.has_permission(Action.OPEN_ACCOUNT, Scope.VOSTRO):
      raise PermissionDenied('You do not have permission to open client accounts')

    try:
      user = self.user_repository.find_by_email(email)
      if user is None:
        raise ValueError(f'No user exists with the email {email}')

      # Cannot be expressed with a CHECK: validated here (§9)
      if user.role.name != 'CLIENT':
        raise ValueError(f'The user {email} is not a client')

      if not user.active:
        raise ValueError(f'The user {email} is inactive')

      if self.repository.find_by_holder_and_alias(user.id, alias) is not None:
        raise ValueError(f'The client already has an account with the alias {alias}')

      ledger = Ledger.open(AccountClass.VOSTRO, alias, holder_id=user.id)
      self.repository.save(ledger)

      return AccountDetail(
        id=ledger.id,
        account_class=ledger.account_class,
        alias=ledger.alias,
        holder=user.name,
        holder_id=user.id,
        created_at=ledger.created_at
      )
    finally:
      self.repository.close()
      self.user_repository.close()

class NostroAccountOpener:
  """NOSTRO account opening (§8.13)."""

  def __init__(self,repository:LedgerRepository,bank_name:str) -> None:
    self.repository = repository
    self.bank_name = bank_name

  def invoke(self,actor:AuthenticatedUser,alias:str)->AccountDetail:
    if not actor.has_permission(Action.OPEN_ACCOUNT, Scope.NOSTRO):
      raise PermissionDenied('You do not have permission to open bank accounts')

    try:
      if self.repository.find_by_holder_and_alias(None, alias) is not None:
        raise ValueError(f'A bank account with the alias {alias} already exists')

      # No holder user: the holder is the bank's name (§7)
      ledger = Ledger.open(AccountClass.NOSTRO, alias, holder_id=None)
      self.repository.save(ledger)

      return AccountDetail(
        id=ledger.id,
        account_class=ledger.account_class,
        alias=ledger.alias,
        holder=self.bank_name,
        holder_id=None,
        created_at=ledger.created_at
      )
    finally:
      self.repository.close()

class AccountLister:
  """Accounts with their holder and current balance (§7): every account, or only the actor's own. Modifies nothing."""

  def __init__(self,repository:LedgerRepository,bank_name:str) -> None:
    self.repository = repository
    self.bank_name = bank_name

  def invoke(self,actor:AuthenticatedUser)->list[AccountSummary]:
    # The full list includes accounts of both classes: VIEW is required on both scopes.
    # Whoever only has VIEW on OWN gets their own accounts, so a client can find them
    sees_all = actor.has_permission(Action.VIEW, Scope.VOSTRO) and actor.has_permission(Action.VIEW, Scope.NOSTRO)
    if not sees_all and not actor.has_permission(Action.VIEW, Scope.OWN):
      raise PermissionDenied('You do not have permission to view the account list')

    try:
      if sees_all:
        ledgers = self.repository.find_all()
        balances = self.repository.balances()
      else:
        ledgers = self.repository.find_by_holder(actor.id)
        balances = self.repository.balances([ledger.id for ledger in ledgers])
      return [
        AccountSummary(
          id=ledger.id,
          account_class=ledger.account_class,
          alias=ledger.alias,
          # No holder user: the holder is the bank's name (§7)
          holder=ledger.holder.name if ledger.holder else self.bank_name,
          holder_id=ledger.holder_id,
          created_at=ledger.created_at,
          # An account without movements has a zero balance
          balance=balances.get(ledger.id, Decimal('0.00'))
        )
        for ledger in ledgers
      ]
    finally:
      self.repository.close()

# NUMERIC(18,2): up to 16 integer digits
MAX_AMOUNT = Decimal('9999999999999999.99')

def parse_amount(value)->Decimal:
  """Rules shared by the operations (§8): Decimal greater than zero with at most 2 decimals."""
  # Never float (§4.4): a JSON number is converted from its text, not from its binary value
  if isinstance(value, bool) or not isinstance(value, (str, int, float)):
    raise ValueError('The amount is not valid')
  try:
    amount = Decimal(str(value).strip())
  except InvalidOperation:
    raise ValueError('The amount is not valid')

  if not amount.is_finite():
    raise ValueError('The amount is not valid')
  if amount <= 0:
    raise ValueError('The amount must be greater than zero')
  if amount != amount.quantize(Decimal('0.01')):
    raise ValueError('The amount allows at most 2 decimals')
  if amount > MAX_AMOUNT:
    raise ValueError('The amount exceeds the maximum allowed')
  return amount.quantize(Decimal('0.01'))

def authorize(actor:AuthenticatedUser,action:Action,ledger:Ledger)->None:
  """Requires the (action, scope) permission for the account's scope relative to the actor (§7)."""
  if not actor.has_permission(action, ledger.scope_for(actor.id)):
    raise PermissionDenied('You do not have permission for this operation on the account')

class AccountFunder:
  """Deposit (§8.5 and §8.10): external money comes into the account."""

  def __init__(self,repository:LedgerRepository) -> None:
    self.repository = repository

  def invoke(self,actor:AuthenticatedUser,account_id:UUID,amount)->OperationResult:
    amount = parse_amount(amount)
    try:
      # The account is locked before computing its balance (§10)
      ledgers = self.repository.find_by_ids_for_update([account_id])
      if not ledgers:
        raise ValueError('The account does not exist')
      ledger = ledgers[0]
      authorize(actor, Action.DEPOSIT, ledger)

      balance = self.repository.balance(ledger.id)
      transaction = Transaction.deposit(ledger, amount)
      transaction.validate([ledger], {ledger.id: balance})
      self.repository.save_transaction(transaction)

      return OperationResult(
        transaction_id=transaction.id,
        type=transaction.type,
        amount=amount,
        account_id=ledger.id,
        destination_account_id=None,
        balance=balance + amount,
        created_at=transaction.created_at
      )
    finally:
      self.repository.close()

class AccountWithdrawer:
  """Withdrawal (§8.6 and §8.11): money leaves the account to outside the bank."""

  def __init__(self,repository:LedgerRepository) -> None:
    self.repository = repository

  def invoke(self,actor:AuthenticatedUser,account_id:UUID,amount)->OperationResult:
    amount = parse_amount(amount)
    try:
      ledgers = self.repository.find_by_ids_for_update([account_id])
      if not ledgers:
        raise ValueError('The account does not exist')
      ledger = ledgers[0]
      authorize(actor, Action.WITHDRAW, ledger)

      # Without enough funds, validate rejects the withdrawal (§6)
      balance = self.repository.balance(ledger.id)
      transaction = Transaction.withdrawal(ledger, amount)
      transaction.validate([ledger], {ledger.id: balance})
      self.repository.save_transaction(transaction)

      return OperationResult(
        transaction_id=transaction.id,
        type=transaction.type,
        amount=amount,
        account_id=ledger.id,
        destination_account_id=None,
        balance=balance - amount,
        created_at=transaction.created_at
      )
    finally:
      self.repository.close()

class AccountTransfer:
  """Transfer between accounts of the same bank (§8.7 and §8.12)."""

  def __init__(self,repository:LedgerRepository) -> None:
    self.repository = repository

  def invoke(self,actor:AuthenticatedUser,source_id:UUID,destination_id:UUID,amount)->OperationResult:
    amount = parse_amount(amount)
    if source_id == destination_id:
      raise ValueError('The source and destination accounts must be different')

    try:
      # Both accounts are always locked in the same order, by id (§10)
      ledgers = {ledger.id: ledger for ledger in self.repository.find_by_ids_for_update([source_id, destination_id])}
      source = ledgers.get(source_id)
      if source is None:
        raise ValueError('The source account does not exist')

      # The permission is evaluated on the source account; the destination only has to exist (§7)
      authorize(actor, Action.TRANSFER, source)
      destination = ledgers.get(destination_id)
      if destination is None:
        raise ValueError('The destination account does not exist')

      balance = self.repository.balance(source.id)
      transaction = Transaction.transfer(source, destination, amount)
      transaction.validate([source, destination], {source.id: balance, destination.id: self.repository.balance(destination.id)})
      self.repository.save_transaction(transaction)

      return OperationResult(
        transaction_id=transaction.id,
        type=transaction.type,
        amount=amount,
        account_id=source.id,
        destination_account_id=destination.id,
        balance=balance - amount,
        created_at=transaction.created_at
      )
    finally:
      self.repository.close()

class TransactionReverser:
  """Reversal of a deposit, a withdrawal or a transfer (§8.15)."""

  def __init__(self,repository:LedgerRepository) -> None:
    self.repository = repository

  def invoke(self,actor:AuthenticatedUser,transaction_id:UUID)->ReversalResult:
    # Without any reversal permission, whether the transaction exists is not revealed
    if not any(action == Action.REVERSE for action, _ in actor.permissions):
      raise PermissionDenied('You do not have permission to reverse transactions')

    try:
      original = self.repository.find_transaction_by_id(transaction_id)
      if original is None:
        raise ValueError('The transaction does not exist')

      # The ledgers that own the original's accounts are locked in id order (§10).
      # Two concurrent reversals of the same transaction run one after the other
      ledgers = self.repository.find_by_account_ids_for_update([movement.account_id for movement in original.movements])
      for ledger in ledgers:
        authorize(actor, Action.REVERSE, ledger)

      if original.type == TransactionType.REVERSAL:
        raise ValueError('A reversal cannot be reversed')

      # Queried with the ledgers already locked
      if self.repository.find_reversal_of(original.id) is not None:
        raise ValueError('The transaction has already been reversed')

      balances = {ledger.id: self.repository.balance(ledger.id) for ledger in ledgers}
      transaction = Transaction.reversal(original)
      # §6.3 applies as well: if the money is no longer in the account, the reversal is rejected
      transaction.validate(ledgers, balances)

      result = dict(
        original_transaction_id=original.id,
        original_type=original.type,
        amount=original.movements[0].amount,
        balances={ledger.id: balances[ledger.id] + transaction.change(ledger) for ledger in ledgers}
      )
      self.repository.save_transaction(transaction)

      return ReversalResult(transaction_id=transaction.id, created_at=transaction.created_at, **result)
    finally:
      self.repository.close()

class AccountBalanceReader:
  """Balance inquiry with its movement history (§8.8 and §8.9). Modifies nothing."""

  def __init__(self,repository:LedgerRepository) -> None:
    self.repository = repository

  def invoke(self,actor:AuthenticatedUser,account_id:UUID)->AccountBalance:
    try:
      ledger = self.repository.find_by_id(account_id)
      if ledger is None:
        raise ValueError('The account does not exist')
      authorize(actor, Action.VIEW, ledger)

      movements = [
        AccountMovement(
          movement_id=row.movement_id,
          transaction_id=row.transaction_id,
          type=row.type,
          entry_type=row.entry_type,
          amount=row.amount,
          balance=row.balance,
          created_at=row.created_at
        )
        for row in self.repository.history(ledger.id)
      ]
      return AccountBalance(
        account_id=ledger.id,
        account_class=ledger.account_class,
        alias=ledger.alias,
        movements=movements
      )
    finally:
      self.repository.close()
