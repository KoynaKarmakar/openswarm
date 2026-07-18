import os
import pytest

# Point at a test-only env so we never accidentally hit real infra
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_DB", "veritas_test")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_not_for_production")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("OPENAI_API_KEY", "test")
