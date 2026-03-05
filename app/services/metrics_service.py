"""
MetricsService — Dynamic metrics analysis for agent comparison.

Analyzes run history (blackboard snapshots) for user-requested metrics.
- First 10 runs: check if metric field exists
- If yes: analyze remaining runs
- If no: mark "unavailable"
- Results cached 7 days via SearchSessionDAO
- Sample size < 30 labeled "indicative only"
"""

from __future__ import annotations

from typing import Any

from app.dao.agent_dao import AgentDAO
from app.dao.search_session_dao import SearchSessionDAO


class MetricsService:

    def __init__(self) -> None:
        self._agent_dao = AgentDAO()
        self._search_dao = SearchSessionDAO()

    def start_analysis(
        self,
        user_id: str,
        agent_ids: list[str],
        metrics: list[str],
    ) -> dict[str, Any]:
        """
        Start a metrics analysis session. Returns session_id for polling.
        """
        session = self._search_dao.create(user_id, agent_ids, metrics)
        # Run analysis synchronously for now (async via Lambda in production)
        result = self._analyze(agent_ids, metrics)
        self._search_dao.update(session["sessionId"], {
            "metricResults": result["metric_results"],
            "missingMetrics": result["missing_metrics"],
            "status": "complete",
        })
        session.update(result)
        session["status"] = "complete"
        return session

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get cached analysis results."""
        return self._search_dao.get(session_id)

    def _analyze(
        self,
        agent_ids: list[str],
        metrics: list[str],
    ) -> dict[str, Any]:
        """
        Analyze run history for requested metrics across agents.
        """
        metric_results: dict[str, dict[str, Any]] = {}
        all_missing: list[str] = []

        for agent_id in agent_ids:
            agent_metrics = self._analyze_agent(agent_id, metrics)
            metric_results[agent_id] = agent_metrics["results"]
            for m in agent_metrics["missing"]:
                if m not in all_missing:
                    all_missing.append(m)

        return {
            "metric_results": metric_results,
            "missing_metrics": all_missing,
        }

    def _analyze_agent(
        self,
        agent_id: str,
        metrics: list[str],
    ) -> dict[str, Any]:
        """
        Analyze a single agent's run history for requested metrics.
        """
        # Fetch runs (up to 100)
        runs = self._agent_dao.get_runs(agent_id, limit=100)
        if not runs:
            return {
                "results": {m: {"status": "no_data"} for m in metrics},
                "missing": metrics,
            }

        results: dict[str, Any] = {}
        missing: list[str] = []

        for metric in metrics:
            # Phase 1: check first 10 runs for field existence
            sample_runs = runs[:10]
            field_found = self._check_field_exists(sample_runs, metric)

            if not field_found:
                results[metric] = {"status": "unavailable"}
                missing.append(metric)
                continue

            # Phase 2: analyze all runs
            values = self._extract_metric_values(runs, metric)
            if not values:
                results[metric] = {"status": "unavailable"}
                missing.append(metric)
                continue

            sample_size = len(values)
            avg = sum(values) / sample_size if values else 0

            results[metric] = {
                "status": "available",
                "value": round(avg, 4),
                "sample_size": sample_size,
                "indicative_only": sample_size < 30,
            }

        return {"results": results, "missing": missing}

    @staticmethod
    def _check_field_exists(runs: list[dict], metric: str) -> bool:
        """Check if a metric field exists in any of the sample runs."""
        for run in runs:
            blackboard = run.get("blackboard", {})
            for key, entry in blackboard.items():
                if key == "agent_input":
                    continue
                value = entry.get("value", {}) if isinstance(entry, dict) else {}
                if isinstance(value, dict) and metric in value:
                    return True
        return False

    @staticmethod
    def _extract_metric_values(runs: list[dict], metric: str) -> list[float]:
        """Extract numeric metric values from run blackboards."""
        values = []
        for run in runs:
            if run.get("status") != "success":
                continue
            blackboard = run.get("blackboard", {})
            for key, entry in blackboard.items():
                if key == "agent_input":
                    continue
                value = entry.get("value", {}) if isinstance(entry, dict) else {}
                if isinstance(value, dict) and metric in value:
                    v = value[metric]
                    if isinstance(v, (int, float)):
                        values.append(float(v))
                    elif isinstance(v, bool):
                        values.append(1.0 if v else 0.0)
                    break  # one value per run
        return values
