"""Async Riot Games API client (account-v1 + summoner-v4).

This module is the ONLY place that talks to ``api.riotgames.com``. It is
deliberately small and additive — it does not touch the existing inference
routes. The key (``RIOT_API_KEY``) is read server-side via ``os.getenv`` and is
NEVER exposed to the browser.

Two Riot routing schemes are used:

* **account-v1** uses *regional* routing clusters: ``americas | asia | europe |
  sea``. Riot IDs (gameName#tagLine) resolve to a ``puuid`` here.
* **summoner-v4** uses *platform* routing: ``euw1 | eun1 | na1 | kr | ...``.
  Given a ``puuid`` it returns the summoner profile (level, icon, ...).

The caller passes a *platform* (e.g. ``euw1``); :func:`regional_for_platform`
maps it to the right regional cluster for the account-v1 call.

Errors are normalised to :class:`RiotError` subclasses carrying an HTTP status
so the FastAPI route can translate them into clean JSON responses without
leaking Riot internals or the key:

* missing/empty key            -> :class:`RiotKeyMissingError`  (route -> 503)
* 404 from Riot                -> :class:`RiotNotFoundError`    (route -> 404)
* 429 from Riot                -> :class:`RiotRateLimitError`   (route -> 429)
* any other 4xx/5xx / network  -> :class:`RiotUpstreamError`    (route -> 502)

Tests inject an ``httpx.MockTransport`` (no ``respx`` dependency) by passing a
``transport=`` to :class:`RiotClient`, so the whole surface is exercised
offline with recorded fixtures.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

# Bounded so a slow/unreachable Riot edge can never hang a request thread.
DEFAULT_TIMEOUT_SECONDS = 8.0

# Default platform when the route caller does not specify a region. Mirrors the
# ``RIOT_PLATFORM`` env var (EUW by default — this project's primary region).
DEFAULT_PLATFORM = os.getenv("RIOT_PLATFORM", "euw1")

# platform (summoner-v4) -> regional cluster (account-v1).
#
# NOTE on Oceania (oc1): Riot has historically accepted both ``americas`` and
# ``sea`` for OCE account-v1 lookups. We pick ``sea`` here (current Riot
# guidance groups OCE with the SEA cluster); if an operator finds OCE 404s on a
# live key they can override via ``RIOT_REGION``/per-call region. Documented so
# T010 (live verification) knows this is a deliberate, reversible choice.
_PLATFORM_TO_REGIONAL = {
    # Europe
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    # Americas
    "na1": "americas",
    "br1": "americas",
    "la1": "americas",
    "la2": "americas",
    # Asia
    "kr": "asia",
    "jp1": "asia",
    # Southeast Asia
    "oc1": "sea",
    "ph2": "sea",
    "sg2": "sea",
    "th2": "sea",
    "tw2": "sea",
    "vn2": "sea",
}

VALID_REGIONAL_CLUSTERS = {"americas", "asia", "europe", "sea"}


def regional_for_platform(platform: str) -> str:
    """Map a platform routing value (``euw1``) to its regional cluster.

    Falls back to ``europe`` for an unknown platform (this project's default
    region) rather than raising, so a typo degrades to a best-effort lookup
    instead of a hard 500. The caller validates ``platform`` separately.
    """
    return _PLATFORM_TO_REGIONAL.get((platform or "").lower().strip(), "europe")


# ──────────────────────────────────────────
# Error types (each carries an HTTP status for the route to reuse)
# ──────────────────────────────────────────

class RiotError(Exception):
    """Base error for Riot client failures, carrying an HTTP ``status``."""

    status: int = 502

    def __init__(self, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        if status is not None:
            self.status = status


class RiotKeyMissingError(RiotError):
    """``RIOT_API_KEY`` is unset/empty — the route turns this into HTTP 503."""

    status = 503


class RiotNotFoundError(RiotError):
    """Riot returned 404 (no such Riot ID / summoner)."""

    status = 404


class RiotRateLimitError(RiotError):
    """Riot returned 429 (rate limited)."""

    status = 429


class RiotUpstreamError(RiotError):
    """Any other Riot 4xx/5xx or a network/transport failure (-> HTTP 502)."""

    status = 502


# ──────────────────────────────────────────
# Client
# ──────────────────────────────────────────

class RiotClient:
    """Thin async wrapper over the two Riot endpoints this feature needs.

    Parameters
    ----------
    api_key:
        Overrides ``RIOT_API_KEY`` (mostly for tests). When ``None`` the key is
        read lazily from the environment on each call so a key set after import
        is still picked up.
    transport:
        Optional ``httpx`` transport. Tests pass an ``httpx.MockTransport`` to
        serve recorded fixtures without any network access.
    timeout:
        Per-request timeout (seconds).
    retries:
        How many times to RETRY a *transient* failure (network/timeout, a 5xx,
        or a short-window 429). ``0`` (the default) preserves the original
        fail-fast behaviour, so the offline test suite is unaffected; the app's
        :func:`get_riot_client` opts in. 404 and other 4xx are never retried.
    backoff_base / retry_max_sleep:
        Exponential backoff base and per-attempt sleep cap (seconds). A 429
        whose ``Retry-After`` exceeds ``retry_max_sleep`` is surfaced rather than
        slept on, so a request never hangs on Riot's per-2-min window.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        retries: int = 0,
        backoff_base: float = 0.25,
        retry_max_sleep: float = 2.0,
    ) -> None:
        self._api_key = api_key
        self._transport = transport
        self._timeout = timeout
        self._retries = max(0, int(retries))
        self._backoff_base = backoff_base
        self._retry_max_sleep = retry_max_sleep

    # -- internals ---------------------------------------------------------

    def _resolve_key(self) -> str:
        key = self._api_key if self._api_key is not None else os.getenv("RIOT_API_KEY", "")
        key = (key or "").strip()
        if not key:
            raise RiotKeyMissingError("Riot API key not configured.")
        return key

    def _backoff_seconds(self, attempt: int) -> float:
        """Exponential backoff for retry ``attempt`` (0-based), capped."""
        return min(self._retry_max_sleep, self._backoff_base * (2 ** attempt))

    @staticmethod
    def _retry_after_seconds(resp: httpx.Response) -> Optional[float]:
        """Parse a Riot ``Retry-After`` header (seconds) if present and numeric."""
        raw = resp.headers.get("Retry-After")
        if not raw:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    async def _get_json_any(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """GET ``url`` with the auth header and normalise errors to RiotError.

        Returns the decoded JSON body as-is — which may be a dict (account-v1,
        summoner-v4, match detail) OR a list (match-v5 ``.../ids`` returns a bare
        JSON array of match-id strings). ``params`` are appended as the query
        string when provided (used by the match-id endpoint for
        ``start/count/queue``).

        Transient failures (network/timeout, 5xx, or a short-window 429) are
        retried up to ``self._retries`` times with capped exponential backoff;
        404 and other 4xx are raised immediately (a retry won't change them).
        """
        key = self._resolve_key()
        headers = {"X-Riot-Token": key}
        attempt = 0
        while True:
            try:
                async with httpx.AsyncClient(
                    transport=self._transport, timeout=self._timeout
                ) as client:
                    resp = await client.get(url, headers=headers, params=params)
            except httpx.HTTPError as exc:  # network / transport / timeout
                if attempt < self._retries:
                    await asyncio.sleep(self._backoff_seconds(attempt))
                    attempt += 1
                    continue
                raise RiotUpstreamError(f"Riot request failed: {exc}") from exc

            status = resp.status_code
            if status == 404:
                raise RiotNotFoundError("Riot resource not found.", status=404)
            if status == 429:
                # Retry the short per-second burst limit; honour Retry-After but
                # don't sleep past the cap (the per-2-min window) — surface it.
                if attempt < self._retries:
                    wait = self._retry_after_seconds(resp)
                    if wait is None:
                        wait = self._backoff_seconds(attempt)
                    if wait <= self._retry_max_sleep:
                        await asyncio.sleep(wait)
                        attempt += 1
                        continue
                raise RiotRateLimitError("Riot API rate limit exceeded.", status=429)
            if status >= 500:
                if attempt < self._retries:
                    await asyncio.sleep(self._backoff_seconds(attempt))
                    attempt += 1
                    continue
                raise RiotUpstreamError(f"Riot API returned {status}.", status=502)
            if status >= 400:
                # Other 4xx (400/401/403/415, ...) are client errors a retry
                # won't fix — fail fast, same as before.
                raise RiotUpstreamError(f"Riot API returned {status}.", status=502)

            try:
                return resp.json()
            except ValueError as exc:  # pragma: no cover - malformed upstream body
                raise RiotUpstreamError("Riot API returned a non-JSON body.") from exc

    async def _get_json(self, url: str) -> Dict[str, Any]:
        """GET ``url`` expecting a JSON object (account-v1 / summoner-v4)."""
        return await self._get_json_any(url)

    # -- public API --------------------------------------------------------

    async def get_account_by_riot_id(
        self, game_name: str, tag_line: str, platform: str = DEFAULT_PLATFORM
    ) -> Dict[str, Any]:
        """Resolve a Riot ID (gameName#tagLine) to ``{puuid, gameName, tagLine}``.

        Uses account-v1 on the *regional* cluster derived from ``platform``.
        """
        regional = regional_for_platform(platform)
        # Riot IDs may contain spaces / unicode; percent-encode each path segment
        # (safe="" so '/' inside a name is also escaped, not treated as a path sep).
        path_game = quote(game_name, safe="")
        path_tag = quote(tag_line, safe="")
        url = (
            f"https://{regional}.api.riotgames.com"
            f"/riot/account/v1/accounts/by-riot-id/{path_game}/{path_tag}"
        )
        return await self._get_json(url)

    async def get_summoner_by_puuid(
        self, puuid: str, platform: str = DEFAULT_PLATFORM
    ) -> Dict[str, Any]:
        """Fetch the summoner profile for a ``puuid`` via summoner-v4.

        Uses *platform* routing (``euw1`` etc.) directly.
        """
        plat = (platform or DEFAULT_PLATFORM).lower().strip()
        url = (
            f"https://{plat}.api.riotgames.com"
            f"/lol/summoner/v4/summoners/by-puuid/{quote(puuid, safe='')}"
        )
        return await self._get_json(url)

    async def get_match_ids_by_puuid(
        self,
        puuid: str,
        platform: str = DEFAULT_PLATFORM,
        count: int = 20,
        queue: Optional[int] = None,
        start: int = 0,
    ) -> List[str]:
        """Fetch a page of recent match-ids for a ``puuid`` via match-v5.

        Uses *regional* routing (derived from ``platform``) — match-v5 lives on
        the regional clusters (``europe`` etc.), NOT the platform host.

        Parameters
        ----------
        count:
            Page size (Riot caps this at 100; we clamp to ``1..100``).
        queue:
            Optional Riot ``queueId`` filter (e.g. 420 ranked solo). When
            ``None`` Riot returns matches across all queues and the caller
            filters by queue after fetching detail.
        start:
            Pagination offset.

        Returns a list of match-id strings (possibly empty). A non-list body is
        treated as an upstream error so a malformed response never silently
        becomes "no games".
        """
        regional = regional_for_platform(platform)
        params: Dict[str, Any] = {
            "start": max(0, int(start)),
            "count": max(1, min(100, int(count))),
        }
        if queue is not None:
            params["queue"] = int(queue)
        url = (
            f"https://{regional}.api.riotgames.com"
            f"/lol/match/v5/matches/by-puuid/{quote(puuid, safe='')}/ids"
        )
        data = await self._get_json_any(url, params=params)
        if not isinstance(data, list):
            raise RiotUpstreamError("Riot match-id response was not a list.")
        return [str(mid) for mid in data]

    async def get_active_game_by_puuid(
        self, puuid: str, platform: str = DEFAULT_PLATFORM
    ) -> Optional[Dict[str, Any]]:
        """Fetch the player's CURRENT live game via spectator-v5, or ``None``.

        Uses *PLATFORM* routing (``euw1`` etc.) directly — spectator-v5 lives on
        the platform host, NOT a regional cluster (contrast with match-v5).

        Riot returns **404 when the player is not in an active game**, which is
        the normal "no live game" case rather than an error. This method maps
        that single 404 to ``None`` so the route can cleanly report
        ``in_game: false`` (HTTP 200). Every OTHER failure keeps its normalised
        error class — 429 -> :class:`RiotRateLimitError`, missing key ->
        :class:`RiotKeyMissingError`, any other 4xx/5xx / network ->
        :class:`RiotUpstreamError` — so a real upstream problem stays
        distinguishable from "not in game" and never silently becomes ``None``.

        Returns
        -------
        Optional[dict]
            The Riot ``CurrentGameInfo`` payload (``gameId``,
            ``gameQueueConfigId``, ``participants`` with ``championId`` /
            ``teamId`` but NO ``teamPosition``, ...) when the player is in a
            game, or ``None`` when they are not (Riot 404).
        """
        plat = (platform or DEFAULT_PLATFORM).lower().strip()
        url = (
            f"https://{plat}.api.riotgames.com"
            f"/lol/spectator/v5/active-games/by-summoner/{quote(puuid, safe='')}"
        )
        try:
            return await self._get_json(url)
        except RiotNotFoundError:
            # Player is simply not in a live game — a normal signal, not a fault.
            return None

    async def get_match_detail(
        self, match_id: str, platform: str = DEFAULT_PLATFORM
    ) -> Dict[str, Any]:
        """Fetch full match detail for a ``match_id`` via match-v5.

        Uses *regional* routing (derived from ``platform``).

        SHARED surface (T005 match summary + T006 per-game draft prediction):
        the **entire** Riot payload is returned unmodified, so callers get the
        full ``info.participants`` (each with ``puuid / championId /
        championName / teamId / win / teamPosition``), the match-level
        ``info.queueId / gameDuration / gameCreation / gameMode``, and
        ``info.teams`` with their ``bans``. T006 can feed
        ``info.participants`` straight into ``reconstruct_draft`` while T005
        summarises a single player's row — neither needs a second request.
        """
        regional = regional_for_platform(platform)
        url = (
            f"https://{regional}.api.riotgames.com"
            f"/lol/match/v5/matches/{quote(match_id, safe='')}"
        )
        return await self._get_json(url)

    async def get_match_timeline(
        self, match_id: str, platform: str = DEFAULT_PLATFORM
    ) -> Dict[str, Any]:
        """Fetch the match-v5 TIMELINE for a ``match_id`` via match-v5.

        Uses *regional* routing (derived from ``platform``), exactly like
        :meth:`get_match_detail` — the timeline lives on the same regional
        clusters (``europe`` etc.), NOT the platform host.

        The returned payload is the full Riot timeline, unmodified:
        ``info.frames[]`` sampled at 60000ms intervals (so ``frames[i]`` is the
        state at minute ``i``), each frame carrying ``participantFrames["1".."10"]``
        (``totalGold`` + position/level/...) and an ``events[]`` list
        (``CHAMPION_KILL`` / ``BUILDING_KILL`` / ``ELITE_MONSTER_KILL`` / ...).
        Participant ids 1–5 are team 100 (blue) and 6–10 are team 200 (red),
        matching the detail's ``info.participants[].participantId``. Callers
        reconstruct the per-minute game state from this together with the match
        detail (for the role mapping).
        """
        regional = regional_for_platform(platform)
        url = (
            f"https://{regional}.api.riotgames.com"
            f"/lol/match/v5/matches/{quote(match_id, safe='')}/timeline"
        )
        return await self._get_json(url)
