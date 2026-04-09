#!/usr/bin/env python3
"""
Sync Jira ticket statuses → status.json

Reads all AEP ticket keys tracked in the dashboard, queries Jira for
their current status and labels, and writes status.json to the repo root.

Required env vars:
  JIRA_EMAIL   - your Atlassian account email
  JIRA_TOKEN   - Atlassian API token (https://id.atlassian.com/manage-profile/security/api-tokens)
"""
import json
import os
import sys
from datetime import datetime, timezone

import requests

JIRA_BASE = "https://foratravel.atlassian.net"
BETA_LABEL = "via-beta-blocker"

KEYS = [
    "AEP-3311","AEP-3312","AEP-3313","AEP-3314","AEP-3315","AEP-3316",
    "AEP-3320","AEP-3321","AEP-3322","AEP-3323","AEP-3324","AEP-3325",
    "AEP-3326","AEP-3327","AEP-3328","AEP-3329","AEP-3330","AEP-3331",
    "AEP-3332","AEP-3333","AEP-3334","AEP-3335","AEP-3336","AEP-3337",
    "AEP-3338","AEP-3339","AEP-3340","AEP-3341","AEP-3342","AEP-3343",
    "AEP-3344","AEP-3345","AEP-3347","AEP-3348","AEP-3349","AEP-3350",
    "AEP-3351","AEP-3352","AEP-3356","AEP-3357","AEP-3358","AEP-3359",
    "AEP-3360","AEP-3361","AEP-3362","AEP-3363","AEP-3364","AEP-3365",
    "AEP-3366","AEP-3369","AEP-3370","AEP-3373","AEP-3374","AEP-3375",
    "AEP-3376","AEP-3377","AEP-3378","AEP-3379","AEP-3380","AEP-3382",
    "AEP-3383","AEP-3424","AEP-3425","AEP-3426","AEP-3513","AEP-3519",
    "AEP-3549","AEP-3572","AEP-3574","AEP-3695","AEP-3722","AEP-3738",
    "AEP-3780","AEP-3781","AEP-3782","AEP-3921","AEP-3988","AEP-4033",
    "AEP-4051","AEP-4052","AEP-4105","AEP-4106","AEP-4123","AEP-4124",
    "AEP-4125","AEP-4126","AEP-4127","AEP-4128","AEP-4175","AEP-4185",
    "AEP-4186","AEP-4224","AEP-4241","AEP-4256","AEP-4257","AEP-4258",
    "AEP-4267","AEP-4268","AEP-4269","AEP-4284","AEP-4351","AEP-4470",
    "AEP-4502","AEP-4525","AEP-4537","AEP-4539","AEP-4541","AEP-4542",
    "AEP-4569","AEP-4595","AEP-4596","AEP-4597","AEP-4600","AEP-4601",
    "AEP-4627","AEP-4629","AEP-4630","AEP-4631","AEP-4636","AEP-4696",
    "AEP-4701","AEP-4706","AEP-4716","AEP-4797","AEP-4798","AEP-4801",
    "AEP-4803","AEP-4805","AEP-4806","AEP-4808","AEP-4810","AEP-4811",
    "AEP-4812","AEP-4813","AEP-4814","AEP-4815","AEP-4817","AEP-4819",
    "AEP-4820","AEP-4822","AEP-4823","AEP-4824","AEP-4826","AEP-4827",
    "AEP-4828","AEP-4829","AEP-4833","AEP-4837","AEP-4839","AEP-4841",
    "AEP-4842","AEP-4874","AEP-4875","AEP-4881","AEP-4892","AEP-4893",
    "AEP-4894","AEP-5006","AEP-5015","AEP-5016","AEP-5017","AEP-5018",
    "AEP-5019","AEP-5028","AEP-5029","AEP-5036","AEP-5037","AEP-5050",
    "AEP-5066","AEP-5068","AEP-5092","AEP-5138","AEP-5140","AEP-5272",
    "AEP-5273","AEP-5275","AEP-5276","AEP-5277","AEP-5278","AEP-5279",
    "AEP-5280","AEP-5281","AEP-5356","AEP-5357","AEP-5360","AEP-5368",
    "AEP-5369","AEP-5370","AEP-5373","AEP-5374","AEP-5375","AEP-5376",
    "AEP-5377","AEP-5378","AEP-5379","AEP-5384","AEP-5443","AEP-5444",
    "AEP-5445","AEP-5446","AEP-5447",
]

# Jira status name → doc status string
STATUS_MAP = {
    "Done":                 "Done",
    "Closed":               "Closed",
    "In Progress":          "In Progress",
    "Needs Input":          "Needs Input",
    "To Do":                "To Do",
    "To do":                "To Do",
    "Next Sprint":          "To Do",
    "Wont Do":              "Wont Do",
    "Won't Do":             "Wont Do",
    "See Child Issues":     "See Child Issues",
    "In Review":            "In Review",
    "Addressing Feedback":  "In Review",
    "Building Phase":       "Building Phase",
}


def fetch_batch(keys: list[str], auth: tuple) -> dict:
    jql = f"key in ({','.join(keys)}) ORDER BY key ASC"
    results = {}
    start = 0
    while True:
        resp = requests.get(
            f"{JIRA_BASE}/rest/api/3/search",
            auth=auth,
            params={
                "jql": jql,
                "fields": "status,labels",
                "maxResults": 100,
                "startAt": start,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        issues = data.get("issues", [])
        for issue in issues:
            key = issue["key"]
            raw_status = issue["fields"]["status"]["name"]
            labels = issue["fields"].get("labels", [])
            results[key] = {
                "status": STATUS_MAP.get(raw_status, raw_status),
                "beta": BETA_LABEL in labels,
            }
        start += len(issues)
        if start >= data.get("total", 0):
            break
    return results


def main() -> None:
    email = os.environ.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_TOKEN")
    if not email or not token:
        print("ERROR: JIRA_EMAIL and JIRA_TOKEN env vars required", file=sys.stderr)
        sys.exit(1)

    auth = (email, token)
    all_statuses = {}
    batch_size = 50

    for i in range(0, len(KEYS), batch_size):
        batch = KEYS[i : i + batch_size]
        print(f"Fetching {batch[0]}…{batch[-1]} ({len(batch)} tickets)")
        all_statuses.update(fetch_batch(batch, auth))

    output = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(all_statuses),
        "statuses": all_statuses,
    }

    out_path = os.path.join(os.path.dirname(__file__), "..", "status.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote status.json — {len(all_statuses)} tickets")


if __name__ == "__main__":
    main()
