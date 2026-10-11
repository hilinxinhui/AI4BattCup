"""Keep upstream routes; support organizer-created accounts without email addresses."""
from functools import wraps
from urls import urlpatterns
from api.views.competitions import CompetitionViewSet
from competitions import emails


original_register = CompetitionViewSet.register


@wraps(original_register)
def register_with_optional_email(self, request, *args, **kwargs):
    if request.user.email is None:
        request.user.email = ""  # In-memory only; do not invent or persist an address.
    return original_register(self, request, *args, **kwargs)


CompetitionViewSet.register = register_with_optional_email
original_send_mail = emails.codalab_send_mail


@wraps(original_send_mail)
def send_to_available_addresses(*args, to_email=None, **kwargs):
    recipients = to_email if isinstance(to_email, list) else [to_email]
    recipients = [address for address in recipients if address]
    if recipients:
        return original_send_mail(*args, to_email=recipients, **kwargs)


emails.codalab_send_mail = send_to_available_addresses
