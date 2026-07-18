"""
MockBankAdapter — BankAdapter backed by synthetic JSON seed data.
All agents call the BankAdapter interface; this file is the ONLY place
that reads from seed_data/. When IDBI Sandbox access arrives,
swap this for idbi_adapter.py — no other code changes needed.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.adapters.base import AccountSummary, BankAdapter, IdentityRecord, TransactionSummary

logger = logging.getLogger("veritas.adapter.mock")

HERE = Path(__file__).parent
SEED = HERE.parent.parent.parent / "seed_data"  # veritas-fabric/seed_data/


def _load(filename: str) -> list[dict]:
    path = SEED / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Seed data not found: {path}. Run seed_data/generate_and_train.py first."
        )
    with open(path) as f:
        return json.load(f)


class MockBankAdapter(BankAdapter):
    """
    Loads synthetic data once at construction.
    Thread-safe for reads (no mutable state after __init__).
    """

    def __init__(self):
        customers = _load("synthetic_customers.json")
        accounts = _load("synthetic_accounts.json")
        transactions = _load("synthetic_transactions.json")

        self._customers: dict[str, dict] = {c["customer_id"]: c for c in customers}
        self._accounts: dict[str, dict] = {a["account_id"]: a for a in accounts}
        self._account_by_number: dict[str, dict] = {
            a["account_number"]: a for a in accounts
        }
        self._txn_by_account: dict[str, list[dict]] = defaultdict(list)
        for t in transactions:
            self._txn_by_account[t["account_id"]].append(t)

        # Sort each account's transactions newest-first
        for acc_id in self._txn_by_account:
            self._txn_by_account[acc_id].sort(key=lambda t: t["created_at"], reverse=True)

        logger.info(
            "MockBankAdapter loaded: %d customers, %d accounts, %d transactions",
            len(self._customers), len(self._accounts),
            sum(len(v) for v in self._txn_by_account.values()),
        )

    async def verify_identity(self, customer_id: str) -> IdentityRecord:
        cust = self._customers.get(customer_id)
        if cust is None:
            raise ValueError(f"Customer not found: {customer_id}")

        kyc_verified_at = None
        if cust.get("kyc_verified_at"):
            kyc_verified_at = datetime.fromisoformat(cust["kyc_verified_at"])

        did_credential = {
            "@context": ["https://www.w3.org/ns/credentials/v2"],
            "type": ["VerifiableCredential", "BankingIdentityCredential"],
            "issuer": "did:idbi:veritas-fabric-v1",
            "issuanceDate": datetime.now(timezone.utc).isoformat(),
            "credentialSubject": {
                "id": f"did:customer:{customer_id}",
                "kyc_status": cust["kyc_status"],
                "risk_tier": cust["risk_tier"],
                "co_lending_eligible": cust["co_lending_eligible"],
                "kyc_verified_at": cust.get("kyc_verified_at"),
                "kyc_expires_at": cust.get("kyc_expires_at"),
                "issuing_institution": "IDBI_BANK",
            },
        }

        return IdentityRecord(
            customer_id=customer_id,
            full_name_redacted=cust["full_name_redacted"],
            kyc_status=cust["kyc_status"],
            kyc_verified_at=kyc_verified_at,
            risk_tier=cust["risk_tier"],
            co_lending_eligible=cust["co_lending_eligible"],
            did_credential=did_credential,
        )

    async def get_account(self, account_id: str) -> AccountSummary:
        acc = self._accounts.get(account_id)
        if acc is None:
            raise ValueError(f"Account not found: {account_id}")
        return AccountSummary(
            account_id=account_id,
            account_type=acc["account_type"],
            balance=float(acc["balance"]),
            is_frozen=acc["is_frozen"],
            kyc_status=acc["kyc_status"],
        )

    async def get_transactions(self, account_id: str, limit: int = 20) -> list[TransactionSummary]:
        txns = self._txn_by_account.get(account_id, [])
        result = []
        for t in txns[:limit]:
            result.append(TransactionSummary(
                transaction_id=t["transaction_id"],
                amount=float(t["amount"]),
                transaction_type=t["transaction_type"],
                status=t["status"],
                merchant_name=t.get("merchant_name"),
                location=t.get("location"),
                created_at=datetime.fromisoformat(t["created_at"]),
                fraud_score=t.get("fraud_score"),
            ))
        return result

    async def check_kyc_status(self, customer_id: str) -> str:
        cust = self._customers.get(customer_id)
        if cust is None:
            raise ValueError(f"Customer not found: {customer_id}")
        return cust["kyc_status"]

    def get_raw_transaction(self, transaction_id: str) -> dict | None:
        """Direct access for fraud feature extraction — only used internally."""
        for txns in self._txn_by_account.values():
            for t in txns:
                if t["transaction_id"] == transaction_id:
                    return t
        return None

    def get_account_stats(self, account_id: str) -> dict:
        """Return mean/std amount for z-score feature engineering."""
        txns = self._txn_by_account.get(account_id, [])
        if not txns:
            return {"mean_amount": 5000.0, "std_amount": 2000.0}
        amounts = [t["amount"] for t in txns]
        import numpy as np
        return {
            "mean_amount": float(np.mean(amounts)),
            "std_amount": float(np.std(amounts)) or 1.0,
        }

    def get_customer_for_account(self, account_id: str) -> dict | None:
        """Return raw customer dict for an account, or None if not found."""
        acc = self._accounts.get(account_id)
        if acc is None:
            return None
        return self._customers.get(acc["customer_id"])
