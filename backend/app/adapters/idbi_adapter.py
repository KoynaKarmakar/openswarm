"""
IDBIBankAdapter — production adapter for IDBI Sandbox APIs.

Status: STUB — raises NotImplementedError on all methods.
When IDBI Sandbox access is granted, implement each method by calling
the corresponding IDBI API endpoint. The interface is identical to
MockBankAdapter — no other code in the codebase changes.

IDBI Sandbox base URL: https://developer.idbibankapi.com/sandbox  (placeholder)
Authentication: OAuth2 client credentials flow (to be configured in .env)
"""

from __future__ import annotations

from app.adapters.base import AccountSummary, BankAdapter, IdentityRecord, TransactionSummary


class IDBIBankAdapter(BankAdapter):

    async def verify_identity(self, customer_id: str) -> IdentityRecord:
        raise NotImplementedError(
            "IDBIBankAdapter.verify_identity: awaiting IDBI Sandbox API access. "
            "Endpoint: POST /v1/customer/identity/verify"
        )

    async def get_account(self, account_id: str) -> AccountSummary:
        raise NotImplementedError(
            "IDBIBankAdapter.get_account: awaiting IDBI Sandbox API access. "
            "Endpoint: GET /v1/accounts/{account_id}"
        )

    async def get_transactions(self, account_id: str, limit: int = 20) -> list[TransactionSummary]:
        raise NotImplementedError(
            "IDBIBankAdapter.get_transactions: awaiting IDBI Sandbox API access. "
            "Endpoint: GET /v1/accounts/{account_id}/transactions?limit={limit}"
        )

    async def check_kyc_status(self, customer_id: str) -> str:
        raise NotImplementedError(
            "IDBIBankAdapter.check_kyc_status: awaiting IDBI Sandbox API access. "
            "Endpoint: GET /v1/customer/{customer_id}/kyc"
        )
