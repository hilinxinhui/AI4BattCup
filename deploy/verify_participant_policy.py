"""HTTP permission checks and a real synthetic participant submission.

Run in manage.py shell with POLICY_TEST_USERNAME/POLICY_TEST_PASSWORD set.
"""
import io
import json
import os
import re
import time
import zipfile
import uuid

import requests
from django.contrib.auth import get_user_model
from competitions.models import Competition, CompetitionParticipant, Submission

base = "http://minio:8000"
username = os.environ["POLICY_TEST_USERNAME"]
password = os.environ["POLICY_TEST_PASSWORD"]
user = get_user_model().objects.get(username=username)
assert not user.is_staff and not user.is_superuser
client = requests.Session()
r = client.post(base + "/api/api-token-auth/", json={"username": username, "password": password}, timeout=15)
r.raise_for_status()
client.headers["Authorization"] = "Token " + r.json()["token"]

for path in ["/competitions/create/", "/competitions/upload/", "/competitions/", "/datasets/create/",
             "/datasets/", "/tasks/", "/queues/", "/profiles/organization/create/", "/admin/"]:
    r = client.get(base + path, timeout=15)
    assert r.status_code == 403, (path, r.status_code)
for path in ["/api/competitions/", "/api/tasks/", "/api/queues/", "/api/phases/",
             "/api/leaderboards/", "/api/organizations/", "/api/participants/"]:
    r = client.post(base + path, json={}, timeout=15)
    assert r.status_code == 403, (path, r.status_code)
for kind in ["public_data", "reference_data", "scoring_program", "competition_bundle", "solution"]:
    r = client.post(base + "/api/datasets/", json={"type": kind}, timeout=15)
    assert r.status_code == 403, (kind, r.status_code)
r = client.post(base + "/api/datasets/", json={"type": "submission", "is_public": True}, timeout=15)
assert r.status_code == 403
print("Participant management pages and resource mutation APIs: denied (403).")

for path in ["/", "/competitions/public/", "/datasets/public/"]:
    r = client.get(base + path, timeout=15)
    assert r.status_code == 200, (path, r.status_code)

competition = Competition.objects.get(title="AI4Batt Cup — Local CSV smoke test")
registration_comp = Competition.objects.create(
    title="Local registration policy test " + uuid.uuid4().hex[:8], created_by=competition.created_by,
    published=False, registration_auto_approve=False,
    description="Synthetic permission test only.")
r = client.post(base + f"/api/competitions/{registration_comp.pk}/register/",
                params={"secret_key": str(registration_comp.secret_key)}, json={}, timeout=15)
assert r.status_code == 201 and r.json()["participant_status"] == "pending", (r.status_code, r.text)
print("Participant registration remains available; approval is still required.")
phase = competition.phases.get(index=0)
CompetitionParticipant.objects.update_or_create(
    user=user, competition=competition, defaults={"status": CompetitionParticipant.APPROVED})
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("predictions.csv", "sample_id,target\nc,3\na,1\nb,2\n")
content = buf.getvalue()
r = client.post(base + "/api/datasets/", json={
    "type": "submission", "name": "Participant permission test " + uuid.uuid4().hex[:8],
    "request_sassy_file_name": "predictions.zip", "file_size": len(content), "is_public": False,
    "competition": competition.pk,
}, timeout=15)
assert r.status_code == 201, (r.status_code, r.text)
upload = r.json()
r = requests.put(upload["sassy_url"], data=content, headers={"Content-Type": "application/zip"}, timeout=15)
r.raise_for_status()
r = client.put(base + "/api/datasets/completed/" + upload["key"] + "/", json={}, timeout=15)
assert r.status_code == 200, (r.status_code, r.text)
r = client.post(base + "/api/submissions/", json={"phase": phase.pk, "data": upload["key"],
                "tasks": list(phase.tasks.values_list("pk", flat=True)), "organization": None,
                "queue": competition.queue_id, "fact_sheet_answers": {}}, timeout=15)
assert r.status_code == 201, (r.status_code, r.text)
pk = r.json()["id"]
deadline = time.monotonic() + 120
while time.monotonic() < deadline:
    sub = Submission.objects.get(pk=pk)
    if sub.status in (Submission.FINISHED, Submission.FAILED):
        break
    time.sleep(2)
assert sub.status == Submission.FINISHED, (sub.status, sub.status_details)
assert float(sub.scores.get(column__key="rmse").score) == 0.0
r = client.get(base + f"/api/submissions/{pk}/", timeout=15)
assert r.status_code == 200 and r.json()["status"] == Submission.FINISHED
r = client.patch(base + f"/api/submissions/{pk}/", json={"status": "Finished", "scores": []}, timeout=15)
assert r.status_code == 403
print("Participant upload, submission, worker callbacks and own result: passed (RMSE 0).")

# Session authentication must enforce the same policy and hide organizer navigation.
session = requests.Session()
login = session.get(base + "/accounts/login/", timeout=15)
csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', login.text).group(1)
r = session.post(base + "/accounts/login/", data={"username": username, "password": password,
                  "csrfmiddlewaretoken": csrf}, headers={"Origin": "http://localhost:8080"}, timeout=15)
assert session.cookies.get("sessionid")
home = session.get(base + "/", timeout=15)
assert "My Resources" not in home.text and "Create Organization" not in home.text
assert session.get(base + "/competitions/create/", timeout=15).status_code == 403
print("Participant session navigation and direct URL restrictions: passed.")

admin = requests.Session()
r = admin.post(base + "/api/api-token-auth/", json={
    "username": os.environ["DJANGO_SUPERUSER_USERNAME"],
    "password": os.environ["DJANGO_SUPERUSER_PASSWORD"]}, timeout=15)
r.raise_for_status()
admin.headers["Authorization"] = "Token " + r.json()["token"]
r = admin.post(base + "/api/tasks/", json={}, timeout=15)
assert r.status_code == 400, (r.status_code, r.text)  # Reaches the normal serializer, without creating anything.
print("Administrator creation API remains available.")
