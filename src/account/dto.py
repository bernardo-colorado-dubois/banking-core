from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from src.account.domain_model import AccountClass, EntryType, TransactionType

@dataclass(frozen=True)
class AccountDetail:
  id: UUID
  account_class: AccountClass
  alias: str
  # Client's name for VOSTRO, bank's name for NOSTRO (§7)
  holder: str
  holder_id: UUID | None
  created_at: datetime

@dataclass(frozen=True)
class AccountSummary(AccountDetail):
  # Current balance (§4.3)
  balance: Decimal

@dataclass(frozen=True)
class AccountMovement:
  movement_id: UUID
  transaction_id: UUID
  type: TransactionType
  entry_type: EntryType
  amount: Decimal
  # The account's balance after this movement
  balance: Decimal
  created_at: datetime

@dataclass(frozen=True)
class AccountBalance:
  account_id: UUID
  account_class: AccountClass
  alias: str
  # Oldest to newest; the current balance is the last movement's
  movements: list[AccountMovement]

@dataclass(frozen=True)
class OperationResult:
  transaction_id: UUID
  type: TransactionType
  amount: Decimal
  account_id: UUID
  # Only in transfers
  destination_account_id: UUID | None
  # Balance of `account_id` after the operation
  balance: Decimal
  created_at: datetime

@dataclass(frozen=True)
class ReversalResult:
  transaction_id: UUID
  original_transaction_id: UUID
  original_type: TransactionType
  amount: Decimal
  # Balance of each account of the original transaction after the reversal
  balances: dict[UUID, Decimal]
  created_at: datetime
