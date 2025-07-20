import subprocess
import re
import os
import requests

from requests.auth import HTTPBasicAuth

# === Load Last Deployed SHA ===

# === Find new commits ===

print("triggering github action...")

result = subprocess.run(
    ["git", "log", f"main..develop", "--pretty=%H"],
    capture_output=True,
    text=True,
)

new_commits = [sha for sha in result.stdout.strip().split("\n") if sha]

if not new_commits:
    print("No new commits since last deployed.")
    exit(0)

print(f"Found new commits: {new_commits}")

# === For each commit, find PR ===
release_plans = []
testing_plans = []
rollback_plans = []

token = os.environ['GITHUB_TOKEN']
repo = os.environ['GITHUB_REPOSITORY']

for sha in new_commits:
    print(f"Checking commit {sha}")
    r = requests.get(
        f"https://api.github.com/repos/{repo}/commits/{sha}/pulls",
        headers={
            "Accept": "application/vnd.github.groot-preview+json",
            "Authorization": f"Bearer {token}"
        }
    )
    prs = r.json()
    if not prs:
        print(f"No PR found for {sha}")
        continue

    pr = prs[0]  # Take first PR
    pr_body = pr.get('body', '')

    release = re.search(r"## Release Plan\n(.+?)\n##", pr_body, re.DOTALL)
    test = re.search(r"## Testing Plan\n(.+?)\n##", pr_body, re.DOTALL)
    rollback = re.search(r"## Rollback Plan\n(.+?)($|\n##)", pr_body, re.DOTALL)

    if release:
        release_plans.append(release.group(1).strip())
    if test:
        testing_plans.append(test.group(1).strip())
    if rollback:
        rollback_plans.append(rollback.group(1).strip())

if not (release_plans or testing_plans or rollback_plans):
    print("No plans found in any PRs.")
    exit(0)

# === Merge plans ===
merged_release = "\n\n".join(release_plans) if release_plans else "N/A"
merged_testing = "\n\n".join(testing_plans) if testing_plans else "N/A"
merged_rollback = "\n\n".join(rollback_plans) if rollback_plans else "N/A"

desc = f"""
Merged Release Card

**Commits:**  
{', '.join(new_commits)}

**Release Plan**
{merged_release}

**Testing Plan**
{merged_testing}

**Rollback Plan**
{merged_rollback}
"""

# === Create Jira Issue ===
jira_url = f"{os.environ['JIRA_BASE_URL']}/rest/api/3/issue"
auth = HTTPBasicAuth(os.environ['JIRA_EMAIL'], os.environ['JIRA_API_TOKEN'])
headers = {"Accept": "application/json", "Content-Type": "application/json"}

payload = {
  "fields": {
    "project": {"key": os.environ['JIRA_PROJECT_KEY']},
    "summary": f"Release: {new_commits[0][:7]}...{new_commits[-1][:7]}",
    "description": desc,
    "issuetype": {"name": "Task"}
  }
}

response = requests.post(jira_url, json=payload, auth=auth, headers=headers)
print(response.status_code, response.text)

if response.status_code == 201:
    print("✅ Jira card created!")
else:
    print("❌ Failed to create Jira card")