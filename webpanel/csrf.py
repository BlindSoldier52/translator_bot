import logging
import secrets

from fastapi import HTTPException, Request
from markupsafe import Markup, escape

logger = logging.getLogger(__name__)

SESSION_KEY = "csrf_token"
FIELD_NAME = "csrf_token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def issue_token(request: Request) -> str:
	token = request.session.get(SESSION_KEY)
	if not token:
		token = secrets.token_urlsafe(32)
		request.session[SESSION_KEY] = token
	return token


def csrf_input(request: Request) -> Markup:
	return Markup(f'<input type="hidden" name="{FIELD_NAME}" value="{escape(issue_token(request))}">')


async def verify_csrf(request: Request) -> None:
	if request.method in SAFE_METHODS:
		return

	expected = request.session.get(SESSION_KEY)
	form = await request.form()
	supplied = form.get(FIELD_NAME)

	if not expected or not isinstance(supplied, str) or not secrets.compare_digest(expected, supplied):
		logger.warning("Rejected a %s to %s with a bad CSRF token", request.method, request.url.path)
		raise HTTPException(status_code=403, detail="Your session expired. Reload the page and try again.")
