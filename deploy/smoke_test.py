"""Synthetic CSV submission through the real HTTP API and compute worker.

Run via manage.py shell inside the Django container. No real battery data.
"""
import io
import json
import os
import time
import zipfile
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

import requests
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils.timezone import now
from competitions.models import Competition, CompetitionParticipant, Phase, PhaseTaskInstance, Submission
from datasets.models import Data
from leaderboards.models import Column, Leaderboard
from tasks.models import Task

SCORER = '''import csv, json, math, pathlib, sys
root, output = map(pathlib.Path, sys.argv[1:])
def read(path):
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ["sample_id", "target"]:
            raise ValueError("Expected columns: sample_id,target")
        values = {}
        for row in reader:
            key, value = row["sample_id"], float(row["target"])
            if key in values or not math.isfinite(value):
                raise ValueError("Duplicate ID or non-finite prediction")
            values[key] = value
        return values
ref = read(root / "ref" / "reference.csv")
pred = read(root / "res" / "predictions.csv")
if set(ref) != set(pred) or not ref:
    raise ValueError("Sample IDs must match reference")
rmse = math.sqrt(sum((ref[k] - pred[k])**2 for k in ref) / len(ref))
output.mkdir(parents=True, exist_ok=True)
(output / "scores.json").write_text(json.dumps({"rmse": rmse}))
print("RMSE:", rmse)
'''

def bundle(kind, files, user):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    data = Data(created_by=user, type=kind, name="Local smoke test " + kind,
                is_public=False, upload_completed_successfully=True)
    data.data_file.save("smoke.zip", ContentFile(buf.getvalue()), save=True)
    return data

user = get_user_model().objects.get(username=os.environ["DJANGO_SUPERUSER_USERNAME"])
competition, created = Competition.objects.get_or_create(
    title="AI4Batt Cup — Local CSV smoke test", created_by=user,
    defaults={"published": False, "docker_image": "ai4batt/scoring:v1.33",
              "description": "Synthetic deployment test only; not the official competition.",
              "can_participants_make_submissions_public": False},
)
if created:
    ref = bundle(Data.REFERENCE_DATA, {"reference.csv": "sample_id,target\na,1\nb,2\nc,3\n"}, user)
    scoring = bundle(Data.SCORING_PROGRAM, {
        "metadata.yaml": "command: python /app/program/scoring.py /app/input /app/output\n",
        "scoring.py": SCORER,
    }, user)
    task = Task.objects.create(name="Synthetic regression", created_by=user,
                               reference_data=ref, scoring_program=scoring, is_public=False)
    board = Leaderboard.objects.create(title="RMSE", key="rmse", submission_rule=Leaderboard.FORCE_BEST)
    Column.objects.create(leaderboard=board, title="RMSE", key="rmse", index=0, sorting="asc", precision=6)
    phase = Phase.objects.create(competition=competition, index=0, name="Local test",
                                  start=now() - timedelta(days=1), status=Phase.CURRENT,
                                  leaderboard=board, execution_time_limit=60,
                                  hide_output=True, hide_prediction_output=True, hide_score_output=True,
                                  max_submissions_per_day=100)
    PhaseTaskInstance.objects.create(phase=phase, task=task, order_index=0)
else:
    phase = competition.phases.get(index=0)
competition.docker_image = "ai4batt/scoring:v1.33"
competition.save(update_fields=["docker_image"])
CompetitionParticipant.objects.get_or_create(user=user, competition=competition,
                                             defaults={"status": CompetitionParticipant.APPROVED})

session = requests.Session()
base = "http://minio:8000"
response = session.post(base + "/api/api-token-auth/", json={
    "username": user.username, "password": os.environ["DJANGO_SUPERUSER_PASSWORD"]}, timeout=15)
response.raise_for_status()
session.headers["Authorization"] = "Token " + response.json()["token"]

for label, csv, expected in [
    ("shuffled-perfect", "sample_id,target\nc,3\na,1\nb,2\n", 0.0),
    ("offset", "sample_id,target\na,2\nb,3\nc,4\n", 1.0),
]:
    data = bundle(Data.SUBMISSION, {"predictions.csv": csv}, user)
    response = session.post(base + "/api/submissions/", json={"phase": phase.pk, "data": str(data.key)}, timeout=15)
    response.raise_for_status()
    pk = response.json()["id"]
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        sub = Submission.objects.get(pk=pk)
        if sub.status in (Submission.FINISHED, Submission.FAILED):
            break
        time.sleep(2)
    if sub.status != Submission.FINISHED:
        raise RuntimeError(f"Submission {pk}: {sub.status}: {sub.status_details}")
    score = float(sub.scores.get(column__key="rmse").score)
    assert abs(score - expected) < 1e-9, (label, score, expected)
    assert sub.scoring_result and sub.scoring_result.size > 0
    # The reference object must reject an unsigned request.
    url = sub.task.reference_data.data_file.url
    unsigned = urlunsplit(urlsplit(url)._replace(query=""))
    assert requests.get(unsigned, timeout=15).status_code == 403
    print(json.dumps({"test": label, "submission": pk, "status": sub.status,
                      "rmse": score, "private_reference": "403 without signature",
                      "result_saved": True}, ensure_ascii=False))
print("Smoke test passed. Competition URL: http://localhost:8080/competitions/" + str(competition.pk) + "/")
