"""Publish the SOH-26 information entry without enabling submissions."""
import json
from pathlib import Path
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.timezone import now
from competitions.models import Competition, CompetitionParticipant, Page, Phase
from leaderboards.models import Leaderboard

config = json.loads(Path("/tmp/soh26.json").read_text(encoding="utf-8"))
owner = get_user_model().objects.get(username=config["owner"])
with transaction.atomic():
    comp, created = Competition.objects.get_or_create(title=config["title"], defaults={
        "created_by": owner, "description": config["description"],
        "competition_type": config["competition_type"], "published": config["published"],
        "registration_auto_approve": False, "auto_run_submissions": False,
        "can_participants_make_submissions_public": False,
        "make_programs_available": False, "make_input_data_available": False,
        "docker_image": "ai4batt/scoring:v1.33",
    })
    if created:
        # Codabench's detail UI requires a phase. This closed information phase is not a competition schedule.
        stamp = now()
        board = Leaderboard.objects.create(title="结果（待配置）", key="soh26-results")
        Phase.objects.create(competition=comp, index=0, name="信息发布（暂不接受提交）",
            description="此阶段仅展示赛事信息。正式提交阶段将在数据和评测规则确定后配置。",
            start=stamp, end=stamp, status=Phase.PREVIOUS, leaderboard=board,
            hide_output=True, hide_prediction_output=True, hide_score_output=True)
        Page.objects.create(competition=comp, index=0, title="比赛说明", content=(
            "# 2026 SOHChallenge (SOH-26)\n\n"
            + config["description"]
            + "\n\n当前仅发布比赛信息，暂不接受预测提交。\n\n"
              "计划采用 CSV 预测结果评测，具体格式和评分指标待公布。"))
        CompetitionParticipant.objects.update_or_create(user=owner, competition=comp,
            defaults={"status": CompetitionParticipant.APPROVED})
    print(json.dumps({"id": comp.pk, "title": comp.title, "published": comp.published,
                      "created": created, "accepting_submissions": any(p.is_active for p in comp.phases.all()),
                      "url": f"http://localhost:8080/competitions/{comp.pk}/"}, ensure_ascii=False))
