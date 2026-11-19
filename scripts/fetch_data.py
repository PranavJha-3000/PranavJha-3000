#!/usr/bin/env python3
"""Refresh data/contributions.json from the GitHub GraphQL API.

Runs `gh api graphql`, so it needs GH_TOKEN (or a local `gh auth login`).
The default Actions token sees public contributions only; set a STATS_TOKEN
secret (a PAT with read:user) if you want private contributions counted.
"""
import datetime as dt
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = json.loads((ROOT / "data/profile.json").read_text("utf-8"))
LEVEL = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

repo_fields = "name description homepageUrl primaryLanguage { name }"
aliases = "\n".join(
    f'r{i}: repository(owner: $login, name: "{f["name"]}") {{ {repo_fields} }}'
    for i, f in enumerate(P["featured"])
)
QUERY = f"""
query($login: String!) {{
  user(login: $login) {{
    contributionsCollection {{ contributionCalendar {{ totalContributions
      weeks {{ contributionDays {{ date contributionCount contributionLevel }} }} }} }}
  }}
  {aliases}
}}"""

raw = subprocess.run(
    ["gh", "api", "graphql", "-f", f"query={QUERY}", "-F", f"login={P['username']}"],
    check=True, capture_output=True, text=True, encoding="utf-8",
).stdout
data = json.loads(raw)["data"]
cal = data["user"]["contributionsCollection"]["contributionCalendar"]
days = [[d["date"], d["contributionCount"], LEVEL[d["contributionLevel"]]]
        for w in cal["weeks"] for d in w["contributionDays"]]
repos = {}
for i, f in enumerate(P["featured"]):
    r = data[f"r{i}"]
    repos[f["name"]] = {
        "language": (r.get("primaryLanguage") or {}).get("name"),
        "homepage": r.get("homepageUrl") or None,
        "description": r.get("description"),
    }

out = {
    "username": P["username"],
    "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
    "total": cal["totalContributions"],
    "days": days,
    "repos": repos,
}
(ROOT / "data/contributions.json").write_text(json.dumps(out, separators=(",", ":")) + "\n", "utf-8")
print(f"{len(days)} days, {cal['totalContributions']} contributions, {len(repos)} repos")
