#!/usr/bin/env python3
"""
sync_agents.py

Syncs agent config files in agents/*.yaml to Claude Managed Agents.

- If a config file has no entry in agents/.ids.json, it is created
  (agents.create) and the new agent_id is recorded.
- If a config file already has an agent_id, it is updated
  (agents.update). Updates bump the agent's version automatically;
  already-running sessions keep the version they were pinned to.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python sync_agents.py              # sync all agents/*.yaml
    python sync_agents.py --dry-run    # show what would happen, no API calls

Requires:
    pip install anthropic pyyaml
"""

import argparse
import json
import sys
from pathlib import Path

import yaml
import anthropic

AGENTS_DIR = Path(__file__).parent
IDS_FILE = AGENTS_DIR / ".ids.json"
BETAS = ["managed-agents-2026-04-01"]


def load_ids() -> dict:
    if IDS_FILE.exists():
        return json.loads(IDS_FILE.read_text())
    return {}


def save_ids(ids: dict) -> None:
    IDS_FILE.write_text(json.dumps(ids, indent=2) + "\n")


def load_agent_config(path: Path) -> dict:
    with open(path) as f:
        raw = yaml.safe_load(f)
    # Only pass through fields the API accepts.
    allowed_keys = {
        "name",
        "model",
        "system",
        "description",
        "tools",
        "mcp_servers",
        "skills",
        "multiagent",
        "metadata",
    }
    return {k: v for k, v in raw.items() if k in allowed_keys and v is not None}


def sync_agent(client: anthropic.Anthropic, path: Path, ids: dict, dry_run: bool) -> None:
    config = load_agent_config(path)
    key = path.name
    agent_id = ids.get(key)

    if agent_id:
        print(f"[update] {key} -> {agent_id}")
        if not dry_run:
            # update() requires the current version for optimistic concurrency;
            # retrieve it first, then the update bumps to a new version.
            current = client.beta.agents.retrieve(agent_id, betas=BETAS)
            agent = client.beta.agents.update(
                agent_id, version=current.version, betas=BETAS, **config
            )
            print(f"         v{current.version} -> v{agent.version}")
    else:
        print(f"[create] {key}")
        if not dry_run:
            agent = client.beta.agents.create(betas=BETAS, **config)
            ids[key] = agent.id
            print(f"         created {agent.id} (version {agent.version})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    yaml_files = sorted(AGENTS_DIR.glob("*.yaml"))
    if not yaml_files:
        print("No agent YAML files found in agents/.")
        sys.exit(1)

    ids = load_ids()
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    for path in yaml_files:
        sync_agent(client, path, ids, args.dry_run)

    if not args.dry_run:
        save_ids(ids)
        print(f"\nUpdated {IDS_FILE.name}")


if __name__ == "__main__":
    main()
