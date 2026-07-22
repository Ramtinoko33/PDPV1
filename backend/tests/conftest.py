"""Shared pytest fixtures for backend tests.

Motor clients bind to the event loop they were created on; use a session
scoped loop so all async tests share the same loop.
"""
import os
import pytest


def pytest_configure(config):
    """Configure asyncio to use session-scoped loops."""
    # Programmatic equivalent of pytest.ini asyncio_mode = auto + session scope.
    # In pytest-asyncio >= 0.23, set via ini option:
    config.addinivalue_line("markers", "asyncio: async test")


# Configure session-wide asyncio defaults via env (readable by pytest-asyncio).
os.environ.setdefault("TELEGRAM_INTERNAL_BOT_TOKEN", "TEST_TOKEN_1234")


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
