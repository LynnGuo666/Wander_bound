"""Legacy feature tests run as one authenticated owner; account tests use real sessions."""
import pytest

from pyserver.accounts import AccountStore, current_user


@pytest.fixture(autouse=True)
def legacy_test_account(request, monkeypatch):
    if request.module.__name__.endswith("test_private_client_contracts"):
        yield
        return
    user = {"id": "legacy-feature-test", "username": "test", "role": "admin"}
    reset = current_user.set(user)
    original = AccountStore.authenticate
    known = {"legacy-test", "contract-test-token", "develop-token", "test-media-token", "test-token"}

    def authenticate(self, token):
        return user if token in known else original(self, token)

    monkeypatch.setattr(AccountStore, "authenticate", authenticate)
    try:
        yield
    finally:
        current_user.reset(reset)
