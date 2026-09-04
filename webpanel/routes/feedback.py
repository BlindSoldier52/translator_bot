from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from shared.db import session_scope
from shared.models import Feedback, User
from webpanel.auth import get_current_admin, require_admin_or_redirect
from webpanel.templating import templates

router = APIRouter()


@router.get("/feedback")
async def list_feedback(request: Request):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	async with session_scope() as session:
		rows = (
			await session.execute(
				select(Feedback, User.username)
				.join(User, User.id == Feedback.user_id)
				.order_by(Feedback.created_at.desc())
			)
		).all()

	feedback_items = [
		{
			"id": item.id,
			"username": username,
			"message": item.message,
			"created_at": item.created_at,
			"is_reviewed": item.is_reviewed,
		}
		for item, username in rows
	]

	return templates.TemplateResponse(
		request, "feedback.html", {"admin": admin, "feedback_items": feedback_items}
	)


@router.post("/feedback/{feedback_id}/review")
async def review_feedback(request: Request, feedback_id: int):
	return await set_feedback_reviewed(request, feedback_id, True)


@router.post("/feedback/{feedback_id}/unreview")
async def unreview_feedback(request: Request, feedback_id: int):
	return await set_feedback_reviewed(request, feedback_id, False)


async def set_feedback_reviewed(request: Request, feedback_id: int, reviewed: bool):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	async with session_scope() as session:
		item = await session.get(Feedback, feedback_id)
		if item is not None:
			item.is_reviewed = reviewed

	return RedirectResponse("/feedback", status_code=303)
