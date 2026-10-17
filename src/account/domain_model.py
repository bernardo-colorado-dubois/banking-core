from src.main.database import Base
from src.user.domain_model import User, Scope
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, MetaData, Numeric, Table, UniqueConstraint, Uuid
from sqlalchemy import DDL, Enum as SqlEnum, Row, case, event, func, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, joinedload, Session
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List
from uuid import UUID, uuid4

# §4.1 The label does not change the accounting behavior
class AccountClass(Enum):
  NOSTRO = "NOSTRO"   # the bank's own account
  VOSTRO = "VOSTRO"   # client account

# §4.2 The nature of each of a ledger's two accounts
class Nature(Enum):
  CREDIT = "CREDIT"   # what the bank owes the holder (liability)
  DEBIT = "DEBIT"     # the money the bank holds for it (asset)

# §5 Tells a withdrawal apart from an outgoing transfer
class TransactionType(Enum):
  DEPOSIT = "DEPOSIT"
  WITHDRAWAL = "WITHDRAWAL"
  TRANSFER = "TRANSFER"
  REVERSAL = "REVERSAL"

class EntryType(Enum):
  DEBIT = "DEBIT"
  CREDIT = "CREDIT"

# §4.2 What the API calls an account: a credit account and a debit account
# that always balance with each other
class Ledger(Base):

  __tablename__ = 'ledgers'
  __table_args__ = (
    CheckConstraint(
      "(account_class = 'VOSTRO' AND holder_id IS NOT NULL) OR (account_class = 'NOSTRO' AND holder_id IS NULL)",
      name='holder_by_class',
    ),
    # The alias tells apart the ledgers of the same holder; with a null holder
    # it covers the NOSTRO ledgers among themselves
    UniqueConstraint('holder_id', 'alias', postgresql_nulls_not_distinct=True),
  )

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  account_class: Mapped[AccountClass] = mapped_column(nullable=False)
  alias: Mapped[str] = mapped_column(nullable=False)
  holder_id: Mapped[UUID | None] = mapped_column(ForeignKey('users.id'), nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
  holder: Mapped[User | None] = relationship()
  accounts: Mapped[List["Account"]] = relationship(back_populates='ledger', lazy='selectin')

  # §4.2 A ledger is always opened with its two accounts, in the same commit
  @classmethod
  def open(cls,account_class:AccountClass,alias:str,**holder)->"Ledger":
    return cls(
      account_class=account_class,
      alias=alias,
      accounts=[Account(nature=Nature.CREDIT), Account(nature=Nature.DEBIT)],
      **holder
    )

  def account(self,nature:Nature)->"Account":
    return next(account for account in self.accounts if account.nature == nature)

  # §7 Evaluation: the ledger's scope relative to the authenticated user
  def scope_for(self,user_id:UUID)->Scope:
    if self.account_class == AccountClass.NOSTRO:
      return Scope.NOSTRO
    return Scope.OWN if self.holder_id == user_id else Scope.VOSTRO

class Account(Base):

  __tablename__ = 'accounts'
  __table_args__ = (
    # One account of each nature per ledger (§4.2)
    UniqueConstraint('ledger_id', 'nature'),
  )

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  ledger_id: Mapped[UUID] = mapped_column(ForeignKey('ledgers.id'), nullable=False)
  nature: Mapped[Nature] = mapped_column(nullable=False)
  ledger: Mapped[Ledger] = relationship(back_populates='accounts')

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
  def deposit(cls,ledger:Ledger,amount:Decimal)->"Transaction":
    return cls(type=TransactionType.DEPOSIT, movements=inflow(ledger, amount))

  @classmethod
  def withdrawal(cls,ledger:Ledger,amount:Decimal)->"Transaction":
    return cls(type=TransactionType.WITHDRAWAL, movements=outflow(ledger, amount))

  # Each ledger goes through its own two accounts: 4 movements
  @classmethod
  def transfer(cls,source:Ledger,destination:Ledger,amount:Decimal)->"Transaction":
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

  def validate(self,ledgers:List[Ledger],balances:dict[UUID,Decimal])->None:
    """§6 invariants. `ledgers` are the involved ledgers and `balances` holds
    the current balance of each one."""
    # 4. Positive amounts
    if any(movement.amount <= 0 for movement in self.movements):
      raise ValueError('The amount must be greater than zero')

    # 5. In a transfer, source and destination are different
    if self.type == TransactionType.TRANSFER and len({ledger.id for ledger in ledgers}) != 2:
      raise ValueError('The source and destination accounts must be different')

    # 1. Transaction balance: debits = credits
    if sum(movement.signed_amount for movement in self.movements) != 0:
      raise ValueError('The transaction is not balanced')

    # Every movement belongs to one of the ledgers' accounts
    ids = {account.id for ledger in ledgers for account in ledger.accounts}
    if any(movement.account_id not in ids for movement in self.movements):
      raise ValueError('The transaction has movements outside its accounts')

    for ledger in ledgers:
      change = self.change(ledger)
      # 2. Per-ledger balance: assets = liabilities. The debit account changes
      # by debits − credits, the opposite of credits − debits
      if change != -self.signed_change(ledger.account(Nature.DEBIT).id):
        raise ValueError('The ledger is not balanced')
      # 3. No negative balances
      if balances[ledger.id] + change < 0:
        raise ValueError('Insufficient funds')

  # §4.3 Change in a ledger's balance: credits − debits on its credit account
  def change(self,ledger:Ledger)->Decimal:
    return self.signed_change(ledger.account(Nature.CREDIT).id)

  def signed_change(self,account_id:UUID)->Decimal:
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
  # before acquiring the ledger lock (§10). With the actual insert time,
  # a ledger's movements stay in the order in which they were applied
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False)
  transaction: Mapped[Transaction] = relationship(back_populates='movements')

  # §4.3 credits − debits
  @property
  def signed_amount(self)->Decimal:
    return self.amount if self.entry_type == EntryType.CREDIT else -self.amount

# Money comes into the ledger: debit to its debit account, credit to its credit account (§5)
def inflow(ledger:Ledger,amount:Decimal)->List[Movement]:
  return [
    Movement(account_id=ledger.account(Nature.DEBIT).id, entry_type=EntryType.DEBIT, amount=amount),
    Movement(account_id=ledger.account(Nature.CREDIT).id, entry_type=EntryType.CREDIT, amount=amount),
  ]

# Money leaves the ledger: debit to its credit account, credit to its debit account (§5)
def outflow(ledger:Ledger,amount:Decimal)->List[Movement]:
  return [
    Movement(account_id=ledger.account(Nature.CREDIT).id, entry_type=EntryType.DEBIT, amount=amount),
    Movement(account_id=ledger.account(Nature.DEBIT).id, entry_type=EntryType.CREDIT, amount=amount),
  ]

# A ledger's history: each movement of its credit account with the balance it left.
# The running balance is computed in SQL (§4.3: credits − debits), not in Python
CREATE_LEDGER_HISTORY = """
CREATE OR REPLACE VIEW ledger_history AS
SELECT
  m.id AS movement_id,
  a.ledger_id,
  m.transaction_id,
  t.type,
  m.entry_type,
  m.amount,
  SUM(CASE WHEN m.entry_type = 'CREDIT' THEN m.amount ELSE -m.amount END)
    OVER (PARTITION BY a.ledger_id ORDER BY m.created_at, m.id) AS balance,
  m.created_at
FROM movements m
JOIN transactions t ON t.id = m.transaction_id
JOIN accounts a ON a.id = m.account_id
WHERE a.nature = 'CREDIT'
"""

# The view is created and dropped together with the tables (create_all and drop_all)
event.listen(Base.metadata, 'after_create', DDL(CREATE_LEDGER_HISTORY))
event.listen(Base.metadata, 'before_drop', DDL('DROP VIEW IF EXISTS ledger_history'))

# Lives in a separate MetaData so create_all does not create it as a table
ledger_history = Table(
  'ledger_history', MetaData(),
  Column('movement_id', Uuid, primary_key=True),
  Column('ledger_id', Uuid),
  Column('transaction_id', Uuid),
  Column('type', SqlEnum(TransactionType)),
  Column('entry_type', SqlEnum(EntryType)),
  Column('amount', Numeric(18, 2)),
  Column('balance', Numeric(18, 2)),
  Column('created_at', DateTime(timezone=True)),
)

class LedgerRepository:

  def __init__(self,session:Session) -> None:
    self.session = session

  def find_by_id(self,id:UUID)->Ledger|None:
    return self.session.query(Ledger).filter(Ledger.id==id).one_or_none()

  # Oldest to newest, with the holder already loaded
  def find_all(self)->List[Ledger]:
    return self.session.query(Ledger).options(joinedload(Ledger.holder)).order_by(Ledger.created_at, Ledger.id).all()

  def find_by_holder_and_alias(self,holder_id:UUID|None,alias:str)->Ledger|None:
    return self.session.query(Ledger).filter(
      Ledger.holder_id.is_not_distinct_from(holder_id),
      Ledger.alias==alias
    ).one_or_none()

  # §10 Locks the rows before computing balances; ordering by id avoids deadlocks.
  # The ledger's lock covers its two accounts. It is released by the commit in
  # save_transaction or by close
  def find_by_ids_for_update(self,ids:List[UUID])->List[Ledger]:
    return self.session.query(Ledger).filter(Ledger.id.in_(ids)).order_by(Ledger.id).with_for_update().all()

  # The ledgers that own the given accounts, locked as in find_by_ids_for_update
  def find_by_account_ids_for_update(self,account_ids:List[UUID])->List[Ledger]:
    ledger_ids = select(Account.ledger_id).where(Account.id.in_(account_ids))
    return self.session.query(Ledger).filter(Ledger.id.in_(ledger_ids)).order_by(Ledger.id).with_for_update().all()

  # §4.3 The balance is not stored: credits − debits on the ledger's credit account
  def balance(self,id:UUID)->Decimal:
    signed_amount = case((Movement.entry_type==EntryType.CREDIT, Movement.amount), else_=-Movement.amount)
    balance = self.session.query(func.coalesce(func.sum(signed_amount), 0)).join(
      Account, Account.id==Movement.account_id
    ).filter(
      Account.ledger_id==id,
      Account.nature==Nature.CREDIT
    ).scalar()
    return Decimal(balance).quantize(Decimal('0.01'))

  # Balance of every ledger in a single query; ledgers without movements are missing
  def balances(self)->dict[UUID,Decimal]:
    signed_amount = case((Movement.entry_type==EntryType.CREDIT, Movement.amount), else_=-Movement.amount)
    rows = self.session.query(Account.ledger_id, func.sum(signed_amount)).join(
      Account, Account.id==Movement.account_id
    ).filter(
      Account.nature==Nature.CREDIT
    ).group_by(Account.ledger_id).all()
    return {ledger_id: Decimal(balance).quantize(Decimal('0.01')) for ledger_id, balance in rows}

  # Oldest movement to newest; the balance on the last row is the current one
  def history(self,id:UUID)->List[Row]:
    return self.session.execute(
      select(ledger_history)
        .where(ledger_history.c.ledger_id==id)
        .order_by(ledger_history.c.created_at, ledger_history.c.movement_id)
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

  # A new holder and the ledger's two accounts are saved in cascade, in the
  # same transaction as the ledger (§4.2, §8.3)
  def save(self,ledger:Ledger)->None:
    try:
      self.session.add(ledger)
      self.session.commit()
    except:
      self.session.rollback()
      raise
    finally:
      self.session.close()
