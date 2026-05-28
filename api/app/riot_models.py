"""Pydantic response models for the Riot-backed routes.

Kept separate from ``main.py`` so the search feature's schema is easy to find
and reuse (T005+). Additive — does not alter existing request/response models.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SummonerResult(BaseModel):
    """Resolved player returned by ``GET /riot/summoner``.

    Combines account-v1 (puuid + Riot ID) with summoner-v4 (profile level +
    icon). Profile fields are optional so the route still returns a useful body
    if summoner-v4 omits them.
    """

    puuid: str = Field(..., description="Globally-unique player id (account-v1).")
    game_name: str = Field(..., description="Riot ID name part (before the #).")
    tag_line: str = Field(..., description="Riot ID tag part (after the #).")
    platform: str = Field(
        ..., description="Platform routing value used for the lookup (e.g. euw1)."
    )
    summoner_level: Optional[int] = Field(
        None, description="Account level from summoner-v4, if available."
    )
    profile_icon_id: Optional[int] = Field(
        None, description="Profile icon id from summoner-v4, if available."
    )


class PlayerSuggestion(BaseModel):
    """One fuzzy-matched player name returned by ``GET /riot/suggest``.

    Drawn from the ``player_name_suggestions`` materialized view (distinct real
    ``(riot_id_name, riot_id_tagline)`` pairs from ``player_stats``). ``games`` is
    a popularity count used only as a ranking tie-breaker, surfaced so the UI can
    show a subtle "N games" hint. This is a LOCAL-DB suggestion, not a resolved
    Riot account — selecting one still runs the real ``/riot/summoner`` lookup.
    """

    game_name: str = Field(..., description="Riot ID name part (riot_id_name).")
    tag_line: Optional[str] = Field(
        None, description="Riot ID tag part (riot_id_tagline), may be empty/None."
    )
    games: int = Field(
        0, description="Number of recorded games for this (name, tag) pair."
    )


class PlayerSuggestionsResponse(BaseModel):
    """Response body for ``GET /riot/suggest`` — ranked fuzzy name suggestions.

    Always returns an object with a ``suggestions`` list (possibly empty) so the
    autocomplete dropdown never has to special-case a missing body. A short query
    (< 2 chars) or any DB hiccup yields an empty list rather than an error, so
    suggestions can never break the search page.
    """

    suggestions: List[PlayerSuggestion] = Field(
        default_factory=list,
        description="Fuzzy name suggestions, best match first.",
    )


class MatchSummary(BaseModel):
    """One recent match summarised from the target player's point of view.

    Produced by ``summarize_match_for_player`` from a match-v5 detail payload
    and returned (as a list) by ``GET /riot/matches``. Only the fields the
    history list needs are surfaced; the per-game prediction (T006) re-fetches /
    reuses the full detail via the shared client method.
    """

    match_id: str = Field(..., description="match-v5 match id (e.g. EUW1_123).")
    champion_name: Optional[str] = Field(
        None,
        description="The player's champion DISPLAY name (Data-Dragon form), or "
        "None if the championId could not be resolved.",
    )
    win: Optional[bool] = Field(
        None, description="Whether the player's team won this match."
    )
    queue_id: Optional[int] = Field(
        None, description="Riot queueId (e.g. 420 ranked solo, 400 draft)."
    )
    game_duration: Optional[int] = Field(
        None, description="Game length in seconds (info.gameDuration)."
    )
    game_creation: Optional[int] = Field(
        None,
        description="Match start as a Unix epoch in MILLISECONDS "
        "(info.gameCreation), or None if absent.",
    )
    game_mode: Optional[str] = Field(
        None, description="Riot gameMode string (e.g. CLASSIC)."
    )


class MatchHistoryResponse(BaseModel):
    """Response body for ``GET /riot/matches`` — a player's recent matches."""

    puuid: str = Field(..., description="The player the history belongs to.")
    platform: str = Field(
        ..., description="Platform routing value used for the lookup (e.g. euw1)."
    )
    count: int = Field(..., description="Number of match summaries returned.")
    matches: List[MatchSummary] = Field(
        default_factory=list, description="Per-player match summaries, newest first."
    )


class MatchPrediction(BaseModel):
    """The draft model's prediction for one finished match (winner + probs).

    Mirrors the inference API's ``PredictionResponse`` but lives here so the
    Riot route layer does not have to import it. ``winner`` is the model's
    favoured side; ``model_accuracy`` is the draft model's own reported accuracy
    (roughly baseline by nature).
    """

    winner: str = Field(..., description="Model-favoured side ('Blue Team'/'Red Team').")
    blue_win_probability: float = Field(..., description="Predicted blue win probability.")
    red_win_probability: float = Field(..., description="Predicted red win probability.")
    confidence: float = Field(..., description="max(blue, red) probability.")
    model_used: str = Field(..., description="Model key used (e.g. 'draft').")
    model_accuracy: Optional[float] = Field(
        None, description="The model's reported accuracy, if available."
    )


class MatchActualResult(BaseModel):
    """What ACTUALLY happened in the match (read straight from match-v5)."""

    winner_side: Optional[str] = Field(
        None,
        description="Side that really won ('Blue Team'/'Red Team'), or None if "
        "the detail does not record a winner.",
    )
    player_won: Optional[bool] = Field(
        None,
        description="Whether the target player's team won this match, or None if "
        "the player is absent from the detail.",
    )


class MatchPredictionResponse(BaseModel):
    """Response body for ``GET /riot/match/{matchId}/prediction`` (T006).

    Combines the reconstructed draft (10 champion display names by role), the
    model's PREDICTED outcome and the ACTUAL result so the UI can show a clear
    "predicted correctly / incorrectly" comparison. ``fallback_used`` flags that
    one or more lanes were assigned by the deterministic order-fallback (Riot
    lane data missing / ambiguous) so the UI can mark lanes as approximate.
    """

    match_id: str = Field(..., description="match-v5 match id (e.g. EUW1_123).")
    puuid: str = Field(..., description="The player the prediction was scoped to.")
    platform: str = Field(
        ..., description="Platform routing value used for the lookup (e.g. euw1)."
    )
    draft: Dict[str, str] = Field(
        ...,
        description="The 10 reconstructed picks: blue_top..red_support -> champion "
        "display name.",
    )
    predicted: MatchPrediction = Field(..., description="The model's prediction.")
    actual: MatchActualResult = Field(..., description="The real match result.")
    fallback_used: bool = Field(
        False,
        description="True when any lane slot was filled by the order-fallback "
        "(lane assignment is approximate).",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Non-fatal reconstruction notices.",
    )


class TimelineCheckpoint(BaseModel):
    """One minute checkpoint in a match's win-probability progression.

    Produced by ``build_timeline_prediction`` for each of minutes 5/10/15/20
    that has a timeline frame. ``predicted`` is the matching ``at{minute}``
    model's output for the reconstructed game state at that minute, and
    ``gold_diff`` is the blue−red total gold (positive = blue ahead) surfaced so
    the UI can show the swing alongside the win probability.
    """

    minute: int = Field(..., description="Game minute of this checkpoint (5/10/15/20).")
    gold_diff: float = Field(
        ..., description="Total gold difference (blue − red) at this minute."
    )
    predicted: MatchPrediction = Field(
        ..., description="The at{minute} model's prediction for this game state."
    )


class MatchTimelinePredictionResponse(BaseModel):
    """Response body for ``GET /riot/match/{matchId}/timeline-prediction``.

    Charts how the timeline win-prob models (at5/at10/at15/at20) read the game
    as it unfolds, reconstructed from the match-v5 timeline, alongside the
    ACTUAL result so the UI can mark which checkpoints called the eventual
    winner correctly. Short games carry fewer checkpoints (only the minutes
    whose timeline frame exists).
    """

    match_id: str = Field(..., description="match-v5 match id (e.g. EUW1_123).")
    puuid: str = Field(..., description="The player the prediction was scoped to.")
    platform: str = Field(
        ..., description="Platform routing value used for the lookup (e.g. euw1)."
    )
    game_duration: Optional[int] = Field(
        None, description="Game length in seconds (info.gameDuration)."
    )
    actual: MatchActualResult = Field(..., description="The real match result.")
    checkpoints: List[TimelineCheckpoint] = Field(
        default_factory=list,
        description="Per-minute win-probability checkpoints, earliest minute first.",
    )


class LivePredictionResponse(BaseModel):
    """Response body for ``GET /riot/live/{puuid}/prediction`` (Slice 4).

    Two shapes, distinguished by ``in_game`` (both returned with HTTP 200):

    * ``in_game = false`` — the player is NOT in a live game right now (Riot
      spectator-v5 returned 404). All live-prediction fields stay ``None``; the
      UI shows a graceful "no live game" empty state.
    * ``in_game = true`` — the player IS in a live game. ``draft`` /
      ``predicted`` are populated from the spectator data run through the draft
      model. There is NO actual result (the game is in progress), so this
      response intentionally has no ``actual`` block. ``fallback_used`` is
      expected to be ``True`` because spectator-v5 carries no lane/role data, so
      lane assignment is approximate.
    """

    in_game: bool = Field(
        ..., description="True when the player is currently in a live game."
    )
    puuid: str = Field(..., description="The player the lookup was scoped to.")
    platform: str = Field(
        ..., description="Platform routing value used for the lookup (e.g. euw1)."
    )
    game_id: Optional[str] = Field(
        None, description="The live game's id (spectator-v5 gameId), if in game."
    )
    queue_id: Optional[int] = Field(
        None, description="The live game's Riot queueId (gameQueueConfigId)."
    )
    draft: Optional[Dict[str, str]] = Field(
        None,
        description="The 10 reconstructed picks: blue_top..red_support -> "
        "champion display name (only when in game).",
    )
    predicted: Optional[MatchPrediction] = Field(
        None,
        description="The draft model's prediction for the live game (only when "
        "in game). No actual result — the game is in progress.",
    )
    fallback_used: bool = Field(
        False,
        description="True when lane slots were filled by the order-fallback. "
        "Always True for spectator data (no lane info), so lanes are approximate.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Non-fatal reconstruction notices.",
    )
