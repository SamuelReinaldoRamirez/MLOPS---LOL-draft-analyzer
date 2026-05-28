# Production Web UI for the LoL Draft Models

## Objective

Build a clean, production-facing web UI — separate from the existing presentation Streamlit — that lets any non-technical user run the deployed LoL draft models (via the prod API) and get predictions, and make it reachable as a public web app.

## Original Request

> je veux une interface utilisateur clean pour que n'importe qui puisse utiliser les modele en prod. Autre que le streamlit de presentation

(A clean UI so anyone can use the models in production — other than the presentation Streamlit.)

## Intake Summary

- Input shape: `open_ended`
- Audience: non-technical end users / general public (the public web)
- Authority: `requested` (public deployment of the frontend + API needs hosting credentials → that specific slice is `needs_approval`)
- Proof type: `demo`
- Completion proof: a non-technical user opens the public UI, submits a draft, and receives a prediction served by the prod model path; browser walkthrough passes.
- Goal oracle: end-to-end browser walkthrough of the deployed UI hitting the real prod API + model version.
- Likely misfire: building another demo/Streamlit-style clone disconnected from the real prod API/model versioning, or shipping a frontend whose API is not actually publicly reachable.
- Blind spots considered: prod API contract & model versioning; CORS between the React/Next.js frontend and FastAPI; public hosting + credentials + basic auth/abuse protection; the model's real input/output shape (draft -> win prob / pick-ban recommendation).
- Existing plan facts: none provided; repo already contains `api/`, `streamlit/`, `training/`, `mlflow/`, `monitoring/`, `k8s/`, `docker-compose.yml`.

## Goal Oracle

The oracle for this goal is:

`A non-technical user opens the deployed web UI in a browser, enters a draft, and receives a model prediction that is served by the production API/model path (not mocked).`

Planning, scaffolding, or a passing local build is not enough. The goal finishes only when a final Judge/PM audit maps receipts and verification back to this oracle and records `full_outcome_complete: true`.

## Goal Kind

`open_ended`

## Decisions (from intake)

- UI stack: **Modern web — React / Next.js** consuming the FastAPI.
- Access: **Public web** (anyone), which implies the prod API must also be publicly reachable.
- Board surface: local live GoalBuddy board.

## Current Tranche

Continuous execution: discover the prod API contract and deployment surface, then build the new web UI in vertical slices (scaffold -> working prediction screen wired to the real API contract -> polish/UX -> public deployment), verifying each slice, reviewing only at phase/risk/final boundaries, until a non-technical user can use the prod models through the clean UI.

## Non-Negotiable Constraints

- Do not modify or break the existing presentation Streamlit app; the new UI is additive.
- The UI must call the real prod API / model serving path, not a mock, for the completion proof.
- Do not commit secrets or hosting credentials; deployment credentials are an operator-provided input.
- Keep the new frontend isolated (its own directory) so it does not entangle the training/serving code.

## Stop Rule

Stop only when a final audit proves the full original outcome is complete (oracle satisfied).

Do not stop after planning, discovery, or Judge selection. Do not stop after a single verified slice while safe local follow-up remains. The public-deploy slice may be blocked on hosting credentials — if so, mark that exact slice blocked with a receipt and continue all local build/UX/wiring work that can still advance the goal.

## Slice Sizing

Safe means bounded, explicit, verified, and reversible — not tiny. A good task is the largest safe useful slice (e.g., a working prediction screen wired to the API), not one more wrapper or config file.

## Canonical Board

Machine truth lives at `docs/goals/prod-web-ui/state.yaml`. If this charter and `state.yaml` disagree, `state.yaml` wins.

## Run Command

```text
/goal Follow docs/goals/prod-web-ui/goal.md.
```

## PM Loop

1. Read this charter.
2. Read `state.yaml`.
3. Run the GoalBuddy update checker; mention a newer version without blocking.
4. Re-check intake: original request, input shape, authority, proof, blind spots, likely misfire.
5. Work only on the active board task.
6. Assign Scout, Judge, Worker, or PM per the task.
7. Write a compact receipt.
8. Update the board.
9. If safe local work remains, choose the next largest reversible Worker package and continue.
10. Escalate follow-ups/credentials needs as repo artifacts or operator questions; record decisions in receipts.
11. Review only at phase/risk/rejected-verification/ambiguity/final boundaries.
12. Finish only with a Judge/PM audit recording `full_outcome_complete: true` mapped to the oracle.
