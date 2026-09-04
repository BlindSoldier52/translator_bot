from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from webpanel.auth import SESSION_KEY, verify_admin_login
from webpanel.templating import templates

router = APIRouter()


@router.get("/login")
async def login_form(request: Request):
	if request.session.get(SESSION_KEY):
		return RedirectResponse("/", status_code=303)
	return templates.TemplateResponse(request, "login.html", {"admin": None})


@router.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
	outcome = await verify_admin_login(request, username, password)
	if outcome.admin is None:
		error = outcome.lock_message() if outcome.is_locked() else "Incorrect username or password."
		return templates.TemplateResponse(
			request,
			"login.html",
			{"admin": None, "error": error, "submitted_username": username},
			status_code=429 if outcome.is_locked() else 401,
		)

	request.session.clear()
	request.session[SESSION_KEY] = outcome.admin.id
	return RedirectResponse("/", status_code=303)


@router.post("/logout")
async def logout(request: Request):
	request.session.clear()
	return RedirectResponse("/login", status_code=303)
