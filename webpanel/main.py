from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from shared.config import get_settings
from webpanel.csrf import verify_csrf
from webpanel.routes import announcements, auth_routes, dashboard, feedback, groups, settings, users

settings_obj = get_settings()

# The panel ships no JavaScript at all, so everything but its own stylesheet is denied.
SECURITY_HEADERS = {
	"Content-Security-Policy": (
		"default-src 'none'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
		"form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
	),
	"X-Content-Type-Options": "nosniff",
	"X-Frame-Options": "DENY",
	"Referrer-Policy": "strict-origin-when-cross-origin",
	"Strict-Transport-Security": "max-age=31536000; includeSubDomains",
	"Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
	"Cross-Origin-Opener-Policy": "same-origin",
}

app = FastAPI(title="Translator Bot Admin", dependencies=[Depends(verify_csrf)])


@app.middleware("http")
async def add_security_headers(request, call_next):
	"""Set the headers here rather than only in nginx, so they hold however this is served."""
	response = await call_next(request)
	for name, value in SECURITY_HEADERS.items():
		response.headers.setdefault(name, value)
	return response


app.add_middleware(
	SessionMiddleware,
	secret_key=settings_obj.session_secret_key,
	session_cookie="translator_bot_admin_session",
	same_site="lax",
	https_only=True,
	max_age=60 * 60 * 12,
)

if settings_obj.panel_allowed_hosts.strip() != "*":
	app.add_middleware(
		TrustedHostMiddleware,
		allowed_hosts=[
			host.strip() for host in settings_obj.panel_allowed_hosts.split(",") if host.strip()
		],
	)

app.mount(
	"/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static"
)

app.include_router(auth_routes.router)
app.include_router(dashboard.router)
app.include_router(groups.router)
app.include_router(users.router)
app.include_router(settings.router)
app.include_router(announcements.router)
app.include_router(feedback.router)
