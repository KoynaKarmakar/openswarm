"""
BankAdapter interface — the ONLY way agents interact with banking data.

Mock implementation: adapters/mock_adapter.py (synthetic data)
IDBI Sandbox implementation: adapters/idbi_adapter.py (raises NotImplementedError)

No code outside this module is allowed to call mock data directly.
When IDBI Sandbox access is granted, only idbi_adapter.py needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class IdentityRecord:
    customer_id: str
    full_name_redacted: str       # initials only — e.g. "R.K." — never full name
    kyc_status: str               # VERIFIED | PENDING | REJECTED | EXPIRED
    kyc_verified_at: datetime | None
    risk_tier: str                # A | B | C | D
    co_lending_eligible: bool
    did_credential: dict          # W3C VC-style dict, no raw PII


@dataclass
class AccountSummary:
    account_id: str
    account_type: str
    balance: float
    is_frozen: bool
    kyc_status: str


@dataclass
class TransactionSummary:
    transaction_id: str
    amount: float
    transaction_type: str
    status: str
    merchant_name: str | None
    location: str | None
    created_at: datetime
    fraud_score: float | None


class BankAdapter(ABC):
    """Abstract interface — all agents call this, never concrete implementations."""

    @abstractmethod
    async def verify_identity(self, customer_id: str) -> IdentityRecord:
        """Return KYC status and DID-ready credential for a customer."""
        ...

    @abstractmethod
    async def get_account(self, account_id: str) -> AccountSummary:
        """Return account summary (balance, type, freeze status, KYC)."""
        ...

    @abstractmethod
    async def get_transactions(
        self, account_id: str, limit: int = 20
    ) -> list[TransactionSummary]:
        """Return recent transactions, ordered newest-first."""
        ...

    @abstractmethod
    async def check_kyc_status(self, customer_id: str) -> str:
        """Return KYC status string: VERIFIED | PENDING | REJECTED | EXPIRED."""
        ...
