"""What `docker-compose.prod.yml` may attach to the US Code compose project's
network, and under what name (ADR-0024), and the project name each compose
file carries (ADR-0025). Docker registers a service's name and its container's
name as DNS aliases on every network the container joins, so a service of this
project named like one of that project's services answers for it there."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
FOREIGN = "uscode-redesign_default"
# The US Code site's `docker-compose.prod.yml`, read on 2026-09-09.
USCODE_SERVICES = {"db", "opensearch", "redis", "api", "frontend", "proxy"}
DEV_PROJECT = "statutes-linkedlegislation"
PROD_PROJECT = "statutes-at-large"


def _load(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text())


@pytest.fixture(scope="module")
def compose() -> dict:
    return _load("docker-compose.prod.yml")


def networks_of(service: dict) -> set[str]:
    networks = service.get("networks") or {}
    return set(networks) if isinstance(networks, dict) else set(networks)


def test_only_the_relay_joins_the_us_code_projects_network(compose: dict) -> None:
    joined = {name for name, service in compose["services"].items() if FOREIGN in networks_of(service)}
    assert joined == {"search-relay"}
    assert compose["networks"][FOREIGN] == {"external": True}


def test_nothing_on_that_network_carries_a_name_that_project_uses(compose: dict) -> None:
    assert "search-relay" not in USCODE_SERVICES
    for name, service in compose["services"].items():
        if FOREIGN in networks_of(service):
            assert name not in USCODE_SERVICES
            assert f"{compose['name']}-{name}-1" not in USCODE_SERVICES


def test_the_api_is_on_this_projects_network_alone(compose: dict) -> None:
    assert networks_of(compose["services"]["api"]) <= {"default"}
    assert compose["services"]["api"]["environment"]["SEARCH_URL"] == "https://search-relay:9200"


def test_the_relay_publishes_no_ports_and_is_bounded(compose: dict) -> None:
    relay = compose["services"]["search-relay"]
    assert "ports" not in relay
    assert relay["mem_limit"] == "32m"
    assert relay["restart"] == "unless-stopped"
    assert relay["image"].startswith("alpine/socat:") and relay["image"] != "alpine/socat:latest"


def test_the_dev_project_is_named_for_every_checkout() -> None:
    """Every checkout and worktree shares the dev database on 5434."""
    assert _load("docker-compose.yml")["name"] == DEV_PROJECT


def test_the_box_keeps_the_project_name_it_runs_under(compose: dict) -> None:
    """`~/statutes-at-large` on the box, run without `-p`. Another name would
    start a second project beside the first, its proxy also answering as
    `statutes-proxy` on `edge`."""
    assert compose["name"] == PROD_PROJECT


def test_the_edge_override_takes_the_dev_projects_name() -> None:
    """`docker-compose.edge.yml` is layered over `docker-compose.yml`; a name
    here would move the dev proxy into another project."""
    assert "name" not in _load("docker-compose.edge.yml")
