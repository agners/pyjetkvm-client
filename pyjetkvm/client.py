"""JetKVM client library for JetKVM local HTTP API."""

from types import TracebackType
from typing import Any, Self

from aiohttp import ClientSession, CookieJar


class JetKVMClient:
    """Async client for communicating with a JetKVM device over local HTTP API."""

    def __init__(self, base_url: str) -> None:
        """Initialize the JetKVM client with a base URL."""
        self.base_url: str = base_url.rstrip("/")
        self.session: ClientSession | None = None

    async def __aenter__(self) -> Self:
        """Enter async context and initialize the HTTP session."""
        self.session = ClientSession(cookie_jar=CookieJar(unsafe=True))
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Exit async context and close the HTTP session."""
        if self.session:
            await self.session.close()

    async def is_setup(self) -> bool:
        """Return True if the JetKVM device is already configured."""
        async with self.session.get(f"{self.base_url}/device/status") as res:
            res.raise_for_status()
            data: dict[str, Any] = await res.json()
            return data.get("isSetup", False)

    async def login(self, password: str) -> dict[str, Any]:
        """Authenticate with a local password and store the session cookie."""
        async with self.session.post(
            f"{self.base_url}/auth/login-local",
            json={"password": password},
        ) as res:
            if res.status == 401:
                raise ValueError("Invalid password")
            res.raise_for_status()
            return await res.json()

    async def get_device_info(self) -> dict[str, Any]:
        """Return basic device information after login."""
        async with self.session.get(f"{self.base_url}/device") as res:
            if res.status == 401:
                raise PermissionError("Not authenticated")
            res.raise_for_status()
            return await res.json()

    async def logout(self) -> dict[str, Any]:
        """Log out of the device and clear session cookies."""
        async with self.session.post(f"{self.base_url}/auth/logout") as res:
            res.raise_for_status()
            await self.session.cookie_jar.clear()
            return await res.json()
