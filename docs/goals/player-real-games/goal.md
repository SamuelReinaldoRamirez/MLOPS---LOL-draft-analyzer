# Player Real-Games: Search Summoner, View Match History, Run Draft Models on Real Games

## Objective

Let any user search their LoL pseudo (Riot ID), select it, browse their real match history, and run the deployed draft models on their **real** games — both **past games** (reconstruct the draft from a finished match → model prediction vs the actual result) and **live games** (spectator draft of an in-progress match → model prediction). Built on top of the existing Next.js `frontend/` + FastAPI `api/` and the prod model path.

## Original Request

> Je veux que les users puissent rechercher leur pseudo et le sélectionner, voir leur historique de games et utiliser les modèles sur leurs games réelles.

(Users can search and select their summoner name, view their game history, and run the models on their real games.)

## Intake Summary

- Input shape: `specific` (concrete feature) with incomplete evidence → Scout first.
- Audience: end users / players who want model insight on their own real games.
- Authority: `requested`. Riot API is reported **already integrated** (key inferred available); the live/spectator slice depends on the player actually being in a game (task-level blocker, not a goal blocker).
- Proof type: `demo` (browser walkthrough against real Riot data + the real prod model path).
- Completion proof: a user opens the UI, searches a Riot ID, selects it, sees their real match history, and gets a real model prediction for a past game (predicted vs actual) **and** for a live game when one exists (graceful "no live game" state otherwise).
- Goal oracle: end-to-end browser walkthrough — real summoner search → real match history → model prediction on a real past game (predicted win prob vs actual result) → model prediction on a live game when available — all served by the real API + prod model path, not mocked.
- Likely misfire: a mock/static summoner search disconnected from real Riot data; an incorrectly reconstructed draft so the model receives garbage input; or quietly shipping only past-games and dropping the live-game requirement.
- Blind spots considered: the real state of the "already integrated" Riot API (which endpoints, region routing, key location, rate limits); mapping a `match-v5` game's participants/bans to the model's 10-champion draft contract (`POST /predict/draft`, `champion_id_map`); spectator-v5 only returns data when the player is mid-game (intermittently un-demoable); public rate-limit/abuse exposure with a personal Riot key.
- Existing plan facts: none provided. Reuse the verified prod-web-ui foundation — Next.js `frontend/`, FastAPI `api/` with `POST /predict/draft`, CORS, docker-compose. This is a **separate goal** from `prod-web-ui` (which is finished except the credential-gated public deploy).

## Goal Oracle

The oracle for this goal is:

`A user opens the deployed web UI, searches and selects a real Riot ID, sees their real match history, and receives real draft-model predictions: a past game shows predicted win probability vs the actual result, and a live game (when one exists) shows a prediction from the spectator draft — all served by the real API + prod model path.`

Discovery, scaffolding, or a passing local build is not enough. The goal finishes only when a final Judge/PM audit maps receipts and verification back to this oracle and records `full_outcome_complete: true`.

## Goal Kind

`specific`

## Current Tranche

Continuous execution. Discover the real Riot integration + model contract, then build successive verified vertical slices: (1) summoner search + select on real Riot data, (2) real match history view, (3) past-game model application (reconstructed draft → predicted vs actual), (4) live-game model application via spectator with a graceful no-game state. Verify each against the oracle; review at phase/risk boundaries; advance until the full outcome is complete.

## Non-Negotiable Constraints

- Use **real** Riot data and the **real** prod model path — no mocked summoner search or fabricated predictions in the shipped flow.
- The draft fed to the model must be a faithful reconstruction of the real match's champions (correct team sides; validated against the model's `champion_id_map`).
- Build on the existing `frontend/` (Next.js) and `api/` (FastAPI); do not fork a second disconnected UI.
- Live-game absence is a graceful UI state, never a crash or a fake game.
- Keep the Riot API key server-side; never expose it to the browser.

## Stop Rule

Stop only when a final audit proves the full original outcome is complete.

Do not stop after Scout/Judge selection if a safe Worker slice can be activated. Do not stop after one verified slice while safe local follow-up remains. Mark a slice blocked (with a receipt) only when it truly needs owner input, credentials, a live game, or a policy decision — then continue every other safe local slice.

## Slice Sizing

Safe means bounded, explicit, verified, and reversible — not tiny. A good Worker slice is a working vertical: a real search screen, a real history view, a real past-game prediction, a real live-game prediction. Avoid chains of tiny wrapper/contract/proof-only tasks; put repeated same-shape work into one package.

## Canonical Board

Machine truth lives at:

`docs/goals/player-real-games/state.yaml`

If this charter and `state.yaml` disagree, `state.yaml` wins.

## Run Command

```text
/goal Follow docs/goals/player-real-games/goal.md.
```

## PM Loop

On every `/goal` continuation:

1. Read this charter.
2. Read `state.yaml`.
3. Run the GoalBuddy update checker when available; mention a newer version without blocking.
4. Re-check the intake: request, input shape, authority, proof, blind spots, likely misfire.
5. Work only on the active board task.
6. Assign Scout / Judge / Worker / PM per the task.
7. Write a compact receipt.
8. Update the board.
9. If safe local work remains, choose the next largest reversible Worker package and continue unless blocked.
10. Turn discovered follow-ups into approved repo issues/PRs or ask the operator.
11. Review at phase, risk, rejected-verification, ambiguity, or final-completion boundaries — not every small Worker.
12. Finish only with a Judge/PM audit receipt that maps receipts + verification back to the original outcome and records `full_outcome_complete: true`.
