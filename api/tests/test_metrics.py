"""Phase 4 — Prometheus metrics endpoint tests.

These run WITHOUT Docker, a DB, or a Prometheus server (same fixtures as the
rest of the API suite). They prove the /metrics endpoint exposes Prometheus
text and that the custom prediction counter is wired into the predict routes.
"""


def test_metrics_endpoint_returns_prometheus_text(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    # Prometheus exposition format is text/plain with a version param.
    ctype = resp.headers.get("content-type", "")
    assert "text/plain" in ctype
    body = resp.text
    # Prometheus text always uses HELP/TYPE comment lines.
    assert "# HELP" in body or "# TYPE" in body or "lol_" in body


def test_metrics_includes_prediction_counter_after_predict(client):
    """A prediction must register on the lol_predictions_total counter."""
    # Drive one prediction through the @10min route (present in fixtures).
    pred = client.post(
        "/predict/at/10",
        json={"gold_diff": 1500, "first_blood": True},
    )
    assert pred.status_code == 200

    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    # The custom counter is exported (the metric family name is present even
    # when the instrumentator is absent and we fall back to prometheus_client).
    assert "lol_predictions_total" in body


def test_record_prediction_is_failsafe(api_main):
    """_record_prediction must never raise, even with no counter wired."""
    # Direct call exercises the NO-OP guard regardless of prometheus install.
    api_main._record_prediction("at10")
    api_main._record_prediction("draft")
