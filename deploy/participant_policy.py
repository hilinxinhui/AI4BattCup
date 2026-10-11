"""Participant-only access policy, layered over Codabench's object permissions."""
import json

from django.http import JsonResponse, QueryDict
from django.core.exceptions import ValidationError
from django.utils.deprecation import MiddlewareMixin
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ParticipantOnlyMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        user = request.user
        # Inspect token identity without turning token requests into CSRF-protected sessions.
        if request.headers.get("Authorization", "").startswith("Token "):
            try:
                identity = TokenAuthentication().authenticate(request)
            except AuthenticationFailed:
                identity = None
            if identity:
                user = identity[0]
        if user.is_authenticated and (user.is_staff or user.is_superuser):
            return None

        match = request.resolver_match
        namespace = match.namespace
        name = match.url_name or ""
        denied_pages = {
            "competitions": {"management", "create", "edit", "upload", "competition_create_group"},
            "datasets": {"management", "create"},
            "tasks": {"task_management", "upload_task"},
            "queues": {"management"},
            "profiles": {"organization_create", "organization_edit", "organization_accept_invite"},
            "pages": {"server_status", "monitor_queues"},
        }
        if (name in denied_pages.get(namespace, set())
                or namespace in {"admin", "analytics"}
                or request.path.startswith("/su/")
                or (namespace == "competitions" and "/groups/" in request.path)):
            return self.deny()

        if not request.path.startswith("/api/"):
            return None

        cls = getattr(view_func, "cls", None)
        class_name = cls.__name__ if cls else ""
        action = getattr(view_func, "actions", {}).get(request.method.lower(), "")
        # Upstream exposes a migration/rerun action using GET; it is still administrative.
        if action in {"rerun_submissions", "creation_status"} or request.path.startswith("/api/analytics/"):
            return self.deny()
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return None
        if request.path in {"/api/api-token-auth/", "/api/api-auth/login/", "/api/api-auth/logout/"}:
            return None

        try:
            if request.content_type == "application/json":
                payload = json.loads(request.body or b"{}")
            elif request.content_type == "application/x-www-form-urlencoded":
                payload = QueryDict(request.body, encoding=request.encoding or "utf-8")
            else:
                payload = request.POST
        except (ValueError, UnicodeDecodeError):
            return self.deny()
        if not isinstance(payload, dict) and not hasattr(payload, "get"):
            return self.deny()

        # Workers report status and scores without a user account, using a per-submission secret.
        if not user.is_authenticated:
            worker_update = class_name == "SubmissionViewSet" and action in {"update", "partial_update"}
            worker_scores = request.path.startswith("/api/upload_submission_scores/")
            if (worker_update or worker_scores) and payload.get("secret"):
                from competitions.models import Submission
                pk = view_kwargs.get("pk", view_kwargs.get("submission_pk"))
                try:
                    valid = Submission.objects.filter(pk=pk, secret=payload["secret"]).exists()
                except (ValueError, TypeError, ValidationError):
                    valid = False
                if valid:
                    return None
            return self.deny()

        if class_name == "CompetitionViewSet" and action == "register":
            return None  # Upstream controls registration approval and private competition access.
        if class_name == "SubmissionViewSet":
            if action == "create":
                allowed = {"phase", "data", "tasks", "fact_sheet_answers", "organization", "queue"}
                if set(payload) - allowed:
                    return self.deny()
                if "queue" in payload:
                    from competitions.models import Phase
                    try:
                        phase = Phase.objects.select_related("competition").get(pk=payload.get("phase"))
                    except (Phase.DoesNotExist, ValueError, TypeError, ValidationError):
                        return self.deny()
                    if payload["queue"] != phase.competition.queue_id:
                        return self.deny()
                from datasets.models import Data
                try:
                    own_submission = Data.objects.filter(
                        key=payload.get("data"), created_by=user, type=Data.SUBMISSION,
                        is_public=False, upload_completed_successfully=True,
                    ).exists()
                except (ValueError, TypeError, ValidationError):
                    own_submission = False
                return None if own_submission else self.deny()
            if action == "submission_leaderboard_connection":
                return None  # Upstream checks submission ownership and leaderboard rules.
        if class_name == "DataViewSet" and action == "create":
            # Submission uploads use the dataset API internally; they are not reusable datasets.
            allowed = {"type", "name", "description", "request_sassy_file_name", "file_size", "is_public", "competition"}
            private = payload.get("is_public", False) in (False, "false", "False", "0", 0)
            if payload.get("type") == "submission" and private and not (set(payload) - allowed):
                return None
        if request.path.startswith("/api/datasets/completed/"):
            from datasets.models import Data
            own_submission = Data.objects.filter(
                key=view_kwargs.get("key"), created_by=user, type=Data.SUBMISSION, is_public=False,
            ).exists()
            if own_submission:
                return None
        return self.deny()

    @staticmethod
    def deny():
        return JsonResponse({"detail": "普通用户仅可参与比赛，不能创建或管理比赛、数据集及平台资源。"}, status=403)
