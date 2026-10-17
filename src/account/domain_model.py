from src.main.database import Base
from src.user.domain_model import User, Scope
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, MetaData, Numeric, Table, Uuid
from sqlalchemy import DDL, Enum as SqlEnum, Row, case, event, func, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, joinedload, Session
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List
from uuid import UUID, uuid4

# §4.1 NOSTRO and VOSTRO only tell the holder apart; CONTRA is the asset
# that mirrors each of them (§4.2)
class AccountClass(Enum):
  NOSTRO = "NOSTRO"   # the bank's own account
  VOSTRO = "VOSTRO"   # client account
  CONTRA = "CONTRA"   # contra account of a NOSTRO or VOSTRO account

# §5 Tells a withdrawal apart from an outgoing transfer
class TransactionType(Enum):
  DEPOSIT = "DEPOSIT"
  WITHDRAWAL = "WITHDRAWAL"
  TRANSFER = "TRANSFER"
  REVERSAL = "REVERSAL"

class EntryType(Enum):
  DEBIT = "DEBIT"
  CREDIT = "CREDIT"

class Account(Base):

  __tablename__ = 'accounts'
  __table_args__ = (
    CheckConstraint(
      "(account_class = 'VOSTRO' AND holder_id IS NOT NULL) OR (account_class IN ('NOSTRO', 'CONTRA') AND holder_id IS NULL)",
      name='holder_by_class',
    ),
    # A contra account has no alias and no contra of its own (§4.2)
    CheckConstraint(
      "(account_class = 'CONTRA') = (alias IS NULL AND contra_account_id IS NULL)",
      name='contra_by_class',
    ),
    # The alias tells apart the accounts of the same holder; with a null holder
    # it covers the NOSTRO accounts among themselves. Contra accounts are left out
    Index(
      'accounts_holder_id_alias_key', 'holder_id', 'alias',
      unique=True,
      postgresql_nulls_not_distinct=True,
      postgresql_where="account_class <> 'CONTRA'",
    ),
  )

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  account_class: Mapped[AccountClass] = mapped_column(nullable=False)
  alias: Mapped[str | None] = mapped_column(nullable=True)
  holder_id: Mapped[UUID | None] = mapped_column(ForeignKey('users.id'), nullable=True)
  # §4.2 Created together with the account, in the same commit
  contra_account_id: Mapped[UUID | None] = mapped_column(ForeignKey('accounts.id'), unique=True, nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
  holder: Mapped[User | None] = relationship()
  contra: Mapped["Account | None"] = relationship(remote_side=[id])

  # §4.2 Every NOSTRO or VOSTRO account is opened with its contra account
  @classmethod
  def open(cls,account_class:AccountClass,alias:str,**holder)->"Account":
    return cls(account_class=account_class, alias=alias, contra=cls(account_class=AccountClass.CONTRA), **holder)

  # §7 Evaluation: the account's scope relative to the authenticated user
  def scope_for(self,user_id:UUID)->Scope:
    if self.account_class == AccountClass.NOSTRO:
      return Scope.NOSTRO
    return Scope.OWN if self.holder_id == user_id else Scope.VOSTRO

class Transaction(Base):

  __tablename__ = 'transactions'
  __table_args__ = (
    # Only a reversal references another transaction (§8.15)
    CheckConstraint(
      "(type = 'REVERSAL') = (original_transaction_id IS NOT NULL)",
      name='original_by_type',
    ),
  )

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  type: Mapped[TransactionType] = mapped_column(nullable=False)
  # Unique: a transaction is reversed only once (§8.15)
  original_transaction_id: Mapped[UUID | None] = mapped_column(ForeignKey('transactions.id'), unique=True, nullable=True)
  description: Mapped[str | None] = mapped_column(nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
  movements: Mapped[List["Movement"]] = relationship(back_populates='transaction')

  # §5 Each operation builds its movements; a balance is never touched directly
  @classmethod
  def deposit(cls,account:Account,amount:Decimal)->"Transaction":
    return cls(type=TransactionType.DEPOSIT, movements=inflow(account, amount))

  @classmethod
  def withdrawal(cls,account:Account,amount:Decimal)->"Transaction":
    return cls(type=TransactionType.WITHDRAWAL, movements=outflow(account, amount))

  # Each account goes through its own contra account: 4 movements
  @classmethod
  def transfer(cls,source:Account,destination:Account,amount:Decimal)->"Transaction":
    return cls(
      type=TransactionType.TRANSFER,
      movements=outflow(source, amount) + inflow(destination, amount)
    )

  # The same movements as the original with the opposite entry type (§8.15).
  # The original is not touched: movements are immutable (§4.4)
  @classmethod
  def reversal(cls,original:"Transaction")->"Transaction":
    return cls(
      type=TransactionType.REVERSAL,
      original_transaction_id=original.id,
      movements=[
        Movement(
          account_id=movement.account_id,
          entry_type=EntryType.DEBIT if movement.entry_type == EntryType.CREDIT else EntryType.CREDIT,
          amount=movement.amount
        )
        for movement in original.movements
      ]
    )

  def validate(self,accounts:List[Account],balances:dict[UUID,Decimal])->None:
    """§6 invariants. `accounts` are the involved NOSTRO and VOSTRO accounts and
    `balances` holds the current balance of each one."""
    # 4. Positive amounts
    if any(movement.amount <= 0 for movement in self.movements):
      raise ValueError('The amount must be greater than zero')

    # 5. In a transfer, source and destination are different
    if self.type == TransactionType.TRANSFER and len({account.id for account in accounts}) != 2:
      raise ValueError('The source and destination accounts must be different')

    # 1. Transaction balance: debits = credits
    if sum(movement.signed_amount for movement in self.movements) != 0:
      raise ValueError('The transaction is not balanced')

    # Every movement belongs to one of the accounts or to its contra account
    ids = {account.id for account in accounts} | {account.contra_account_id for account in accounts}
    if any(movement.account_id not in ids for movement in self.movements):
      raise ValueError('The transaction has movements outside its accounts')

    for account in accounts:
      change = self.change(account.id)
      # 2. Per-account balance: assets = liabilities. The contra account has the
      # debit nature, so it changes by credits − debits with the opposite sign
      if change != -self.change(account.contra_account_id):
        raise ValueError('The account does not match its contra account')
      # 3. No negative balances
      if balances[account.id] + change < 0:
        raise ValueError('Insufficient funds')

  # §4.3 Change in a NOSTRO or VOSTRO account's balance: credits − debits
  def change(self,account_id:UUID)->Decimal:
    return sum(
      (movement.signed_amount for movement in self.movements if movement.account_id == account_id),
      Decimal(0)
    )

# §4.4 Immutable: never edited or deleted
class Movement(Base):

  __tablename__ = 'movements'
  __table_args__ = (
    CheckConstraint('amount > 0', name='positive_amount'),
  )

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  transaction_id: Mapped[UUID] = mapped_column(ForeignKey('transactions.id'), nullable=False)
  account_id: Mapped[UUID] = mapped_column(ForeignKey('accounts.id'), nullable=False)
  entry_type: Mapped[EntryType] = mapped_column(nullable=False)
  amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
  # clock_timestamp() and not now(): now() is the time the DB transaction started,
  # before acquiring the account lock (§10). With the actual insert time,
  # an account's movements stay in the order in which they were applied
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False)
  transaction: Mapped[Transaction] = relationship(back_populates='movements')

  # §4.3 balance = credits − debits
  @property
  def signed_amount(self)->Decimal:
    return self.amount if self.entry_type == EntryType.CREDIT else -self.amount

# Money comes into the account: debit to the contra account, credit to the account (§5)
def inflow(account:Account,amount:Decimal)->List[Movement]:
  return [
    Movement(account_id=account.contra_account_id, entry_type=EntryType.DEBIT, amount=amount),
    Movement(account_id=account.id, entry_type=EntryType.CREDIT, amount=amount),
  ]

# Money leaves the account: debit to the account, credit to the contra account (§5)
def outflow(account:Account,amount:Decimal)->List[Movement]:
  return [
    Movement(account_id=account.id, entry_type=EntryType.DEBIT, amount=amount),
    Movement(account_id=account.contra_account_id, entry_type=EntryType.CREDIT, amount=amount),
  ]

# A NOSTRO or VOSTRO account's history: each movement with the balance it left.
# The running balance is computed in SQL (§4.3: credits − debits), not in Python
CREATE_ACCOUNT_HISTORY = """
CREATE OR REPLACE VIEW account_history AS
SELECT
  m.id AS movement_id,
  m.account_id,
  m.transaction_id,
  t.type,
  m.entry_type,
  m.amount,
  SUM(CASE WHEN m.entry_type = 'CREDIT' THEN m.amount ELSE -m.amount END)
    OVER (PARTITION BY m.account_id ORDER BY m.created_at, m.id) AS balance,
  m.created_at
FROM movements m
JOIN transactions t ON t.id = m.transaction_id
JOIN accounts a ON a.id = m.account_id
WHERE a.account_class <> 'CONTRA'
"""

# The view is created and dropped together with the tables (create_all and drop_all)
event.listen(Base.metadata, 'after_create', DDL(CREATE_ACCOUNT_HISTORY))
event.listen(Base.metadata, 'before_drop', DDL('DROP VIEW IF EXISTS account_history'))

# Lives in a separate MetaData so create_all does not create it as a table
account_history = Table(
  'account_history', MetaData(),
  Column('movement_id', Uuid, primary_key=True),
  Column('account_id', Uuid),
  Column('transaction_id', Uuid),
  Column('type', SqlEnum(TransactionType)),
  Column('entry_type', SqlEnum(EntryType)),
  Column('amount', Numeric(18, 2)),
  Column('balance', Numeric(18, 2)),
  Column('created_at', DateTime(timezone=True)),
)

class AccountRepository:

  def __init__(self,session:Session) -> None:
    self.session = session

  # Contra accounts are not reached through the API (§4.2): every lookup by id leaves them out
  def find_by_id(self,id:UUID)->Account|None:
    return self.session.query(Account).filter(
      Account.id==id,
      Account.account_class!=AccountClass.CONTRA
    ).one_or_none()

  # Oldest to newest, with the holder already loaded
  def find_all(self)->List[Account]:
    return self.session.query(Account).options(joinedload(Account.holder)).filter(
      Account.account_class!=AccountClass.CONTRA
    ).order_by(Account.created_at, Account.id).all()

  def find_by_holder_and_alias(self,holder_id:UUID|None,alias:str)->Account|None:
    return self.session.query(Account).filter(
      Account.holder_id.is_not_distinct_from(holder_id),
      Account.alias==alias
    ).one_or_none()

  # §10 Locks the rows before computing balances; ordering by id avoids deadlocks.
  # Only NOSTRO and VOSTRO accounts are locked: a contra account never moves
  # without its account. The lock is released by the commit in save_transaction or by close
  def find_by_ids_for_update(self,ids:List[UUID])->List[Account]:
    return self.session.query(Account).filter(
      Account.id.in_(ids),
      Account.account_class!=AccountClass.CONTRA
    ).order_by(Account.id).with_for_update().all()

  # §4.3 The balance is not stored: credits − debits of a NOSTRO or VOSTRO account
  def balance(self,id:UUID)->Decimal:
    signed_amount = case((Movement.entry_type==EntryType.CREDIT, Movement.amount), else_=-Movement.amount)
    balance = self.session.query(func.coalesce(func.sum(signed_amount), 0)).filter(
      Movement.account_id==id
    ).scalar()
    return Decimal(balance).quantize(Decimal('0.01'))

  # Balance of every NOSTRO and VOSTRO account in a single query; accounts without movements are missing
  def balances(self)->dict[UUID,Decimal]:
    signed_amount = case((Movement.entry_type==EntryType.CREDIT, Movement.amount), else_=-Movement.amount)
    rows = self.session.query(Movement.account_id, func.sum(signed_amount)).join(
      Account, Account.id==Movement.account_id
    ).filter(
      Account.account_class!=AccountClass.CONTRA
    ).group_by(Movement.account_id).all()
    return {account_id: Decimal(balance).quantize(Decimal('0.01')) for account_id, balance in rows}

  # Oldest movement to newest; the balance on the last row is the current one
  def history(self,id:UUID)->List[Row]:
    return self.session.execute(
      select(account_history)
        .where(account_history.c.account_id==id)
        .order_by(account_history.c.created_at, account_history.c.movement_id)
    ).all()

  def find_transaction_by_id(self,id:UUID)->Transaction|None:
    return self.session.query(Transaction).filter(Transaction.id==id).one_or_none()

  def find_reversal_of(self,id:UUID)->Transaction|None:
    return self.session.query(Transaction).filter(Transaction.original_transaction_id==id).one_or_none()

  def close(self)->None:
    self.session.close()

  # All movements go in a single commit: either all are recorded or none (§5)
  def save_transaction(self,transaction:Transaction)->None:
    try:
      self.session.add(transaction)
      self.session.commit()
    except:
      self.session.rollback()
      raise
    finally:
      self.session.close()

  # A new holder and the contra account are saved in cascade, in the same
  # transaction as the account (§4.2, §8.3)
  def save(self,account:Account)->None:
    try:
      self.session.add(account)
      self.session.commit()
    except:
      self.session.rollback()
      raise
    finally:
      self.session.close()
