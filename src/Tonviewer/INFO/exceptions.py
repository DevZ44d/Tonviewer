"""
exceptions.py — Custom exceptions for the Fragment scraper and NFT client.

Hierarchy:
    FragmentError                   (base for all Fragment errors)
    ├── FragmentFetchError          (network / HTTP failure after retries)
    ├── FragmentBlockedError        (Cloudflare 403 hard block)
    ├── FragmentParseError          (HTML parsing / unexpected markup)
    └── FragmentLookupError         (base for username-level errors)
        ├── UserNotFoundError       (username does not exist on Fragment)
        └── WalletNotFoundError     (username exists, but no wallet linked)

    NFTError                        (base for all NFT client errors)
    ├── NFTFetchError               (TonAPI pagination / HTTP failure)
    └── AddressResolutionError      (cannot resolve @username → wallet)
"""

from __future__ import annotations


class FragmentError(Exception):
    """
    Base class for all Fragment scraper errors.
    Catch this to handle any Fragment-related failure in one place.

    Example:
        try:
            result = await client.get_username("@monk")
        except FragmentError as e:
            print(f"Fragment error: {e}")
    """



class FragmentFetchError(FragmentError):
    """
    Raised when a network or HTTP error persists after all configured retries.

    Wraps the original exception via __cause__ so you can inspect it if needed.

    Attributes:
        url:      The URL that failed (optional, set by the client).
        attempts: Number of retry attempts made before giving up.

    Example:
        except FragmentFetchError as e:
            print(e)           # Fragment fetch failed after 3 attempts: ...
            print(e.__cause__) # The original httpx / network exception
    """

    def __init__(
        self,
        message: str,
        *,
        url: str | None = None,
        attempts: int | None = None,
    ) -> None:
        self.url      = url
        self.attempts = attempts
        super().__init__(message)

    def __str__(self) -> str:
        base = super().__str__()
        parts: list[str] = [base]
        if self.url:
            parts.append(f"URL: {self.url}")
        if self.attempts is not None:
            parts.append(f"Attempts: {self.attempts}")
        return "  |  ".join(parts)


class FragmentBlockedError(FragmentFetchError):
    """
    Raised when Fragment / Cloudflare returns a hard 403 block.

    This is never retried — a 403 means the request was rejected at the
    WAF level and retrying the same IP / User-Agent will keep failing.

    Recovery options:
        • Rotate User-Agent string.
        • Use a residential proxy: FragmentClient(proxy="http://user:pass@host:port")
        • Add a delay between requests to avoid rate-limit triggers.

    Example:
        except FragmentBlockedError:
            print("Blocked by Cloudflare — rotate IP or use a proxy")
    """

    def __init__(self, message: str = "Cloudflare 403 block", *, url: str | None = None) -> None:
        super().__init__(message, url=url, attempts=1)



class FragmentParseError(FragmentError):
    """
    Raised when the HTML returned by Fragment cannot be parsed as expected.

    Usually means Fragment updated its markup. Use ``debug=True`` on
    ``get_username()`` to save the raw HTML and inspect which selectors
    stopped matching.

    Attributes:
        username: The username being parsed when the error occurred.
        hint:     Optional short description of what failed to parse.

    Example:
        except FragmentParseError as e:
            print(f"Markup changed for @{e.username}: {e.hint}")
    """

    def __init__(
        self,
        message: str,
        *,
        username: str | None = None,
        hint: str | None = None,
    ) -> None:
        self.username = username
        self.hint     = hint
        super().__init__(message)

    def __str__(self) -> str:
        base = super().__str__()
        if self.hint:
            return f"{base}  (hint: {self.hint})"
        return base


class FragmentLookupError(FragmentError):
    """
    Base class for username-level lookup failures.
    Catch this to handle both UserNotFoundError and WalletNotFoundError
    without caring which one it is.

    Attributes:
        username: The username that caused the error (without leading @).

    Example:
        except FragmentLookupError as e:
            print(f"@{e.username} lookup failed: {e}")
    """

    def __init__(self, username: str, message: str | None = None) -> None:
        self.username: str = username.lstrip("@")
        super().__init__(message or f"@{self.username}")

    def __str__(self) -> str:
        return super().__str__()


class UserNotFoundError(FragmentLookupError):
    """
    Raised when the requested username has no page on Fragment.com.

    This means the username was never listed, auctioned, or sold on Fragment —
    it may still be available to register directly via Telegram.

    Example:
        except UserNotFoundError as e:
            print(f"@{e.username} is not on Fragment")
    """

    def __init__(self, username: str) -> None:
        clean = username.lstrip("@")
        super().__init__(clean, f"Username '@{clean}' was not found on Fragment.com")


class WalletNotFoundError(FragmentLookupError):
    """
    Raised when a username exists on Fragment but has no linked TON wallet.

    Common reasons:
        • The username is currently On Auction (no buyer yet).
        • The username was sold but the owner hasn't linked a wallet.
        • Fragment updated its HTML and the wallet link selector broke.

    Attributes:
        username: The username that has no wallet.
        status:   The Fragment status string at time of lookup (e.g. "On Auction").

    Example:
        except WalletNotFoundError as e:
            print(f"@{e.username} has no wallet (status: {e.status})")
    """

    def __init__(self, username: str, *, status: str | None = None) -> None:
        self.status: str | None = status
        clean   = username.lstrip("@")
        status_part = f" (status: {status})" if status else ""
        super().__init__(
            clean,
            f"Username '@{clean}' exists on Fragment but has no wallet linked{status_part}",
        )



class NFTError(Exception):
    """
    Base class for all NFT client errors.
    Catch this to handle any NFT-related failure in one place.

    Example:
        try:
            result = await client.get_nfts("@monk")
        except NFTError as e:
            print(f"NFT error: {e}")
    """


class NFTFetchError(NFTError):
    """
    Raised when TonAPI returns a non-recoverable HTTP error while paginating
    through a wallet's NFT list.

    Partial results fetched before the error may still be usable — check
    the ``offset`` attribute to see how many items were retrieved.

    Attributes:
        address: The wallet address being queried when the error occurred.
        offset:  The pagination offset at the time of failure (how many
                 items were already fetched successfully before the error).
        cause:   The underlying httpx exception (also available as __cause__).

    Example:
        except NFTFetchError as e:
            print(f"Failed fetching NFTs for {e.address} at offset {e.offset}")
            print(f"Caused by: {e.cause}")
    """

    def __init__(
        self,
        address: str,
        *,
        offset: int = 0,
        cause: BaseException | None = None,
    ) -> None:
        self.address = address
        self.offset  = offset
        self.cause   = cause
        super().__init__(
            f"TonAPI NFT fetch failed for '{address}' at offset {offset}"
            + (f": {cause}" if cause else "")
        )


class AddressResolutionError(NFTError):
    """
    Raised when a @username cannot be resolved to a TON wallet address.

    Common reasons:
        • Username is not listed on Fragment at all.
        • Username is "On Auction" or "Available" — no owner yet.
        • Username was sold but owner hasn't linked a wallet.
        • Fragment returned an unexpected status.

    Attributes:
        identifier: The original @username or address that failed to resolve.
        reason:     Human-readable explanation of why resolution failed.

    Example:
        except AddressResolutionError as e:
            print(f"Cannot resolve {e.identifier}: {e.reason}")
    """

    def __init__(self, identifier: str, reason: str | None = None) -> None:
        self.identifier = identifier
        self.reason     = reason or "could not resolve to a TON wallet address"
        super().__init__(f"{identifier!r}: {self.reason}")