"""Chapter 16: the alerts, runbooks and drills stay in
step with the code."""

import re
from pathlib import Path

import yaml
from tools.drills import DRILLS

ROOT = Path(__file__).parent.parent
RULES = yaml.safe_load(
    (ROOT / "ops" / "alerts.yml").read_text()
)
ALERTS = [r for g in RULES["groups"] for r in g["rules"]]
PROMQL_WORDS = {
    "sum", "rate", "by", "le", "and", "max", "min",
    "increase", "histogram_quantile", "max_over_time",
    "min_over_time", "status", "route", "outcome",
    "reason", "e6",
}


def metric_names(expr: str) -> set[str]:
    expr = re.sub(r"\[\w+\]", "", expr)  # [5m], [1h]
    expr = re.sub(r'"[^"]*"', "", expr)  # label values
    words = set(re.findall(r"[a-z_][a-z0-9_]*", expr))
    names = set()
    for word in words - PROMQL_WORDS:
        for suffix in ("_bucket", "_count", "_sum"):
            word = word.removesuffix(suffix)
        names.add(word)
    return names


async def test_alerts_use_metrics_that_exist(client):
    from prometheus_client import REGISTRY

    import secondloop.worker  # noqa: F401  its gauges

    exported = {m.name for m in REGISTRY.collect()}
    exported |= {f"{n}_total" for n in exported}
    for alert in ALERTS:
        missing = metric_names(alert["expr"]) - exported
        assert not missing, (alert["alert"], missing)


def test_every_alert_has_a_runbook():
    for alert in ALERTS:
        path = ROOT / alert["annotations"]["runbook"]
        assert path.exists(), alert["alert"]


def test_drills_cover_the_incidents():
    covered = {chapter for chapter, _, _ in DRILLS}
    assert {5, 6, 7, 8, 9, 10, 11, 13, 14, 15} <= covered
