from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select

from shared.db import session_scope
from shared.models import AnnouncementDelivery, Feedback, Group, User
from webpanel.auth import get_current_admin, require_admin_or_redirect
from webpanel.templating import templates

router = APIRouter()


@router.get("/users")
async def list_users(request: Request):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	async with session_scope() as session:
		users = (await session.scalars(select(User).order_by(User.username))).all()

	return templates.TemplateResponse(request, "users.html", {"admin": admin, "users": users})


@router.post("/users/{user_id}/block")
async def block_user(request: Request, user_id: int):
	return await set_user_blocked(request, user_id, True)


@router.post("/users/{user_id}/unblock")
async def unblock_user(request: Request, user_id: int):
	return await set_user_blocked(request, user_id, False)


async def set_user_blocked(request: Request, user_id: int, blocked: bool):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	async with session_scope() as session:
		user = await session.get(User, user_id)
		if user is not None:
			user.is_blocked = blocked

	return RedirectResponse("/users", status_code=303)


@router.get("/users/{user_id}/delete")
async def confirm_delete_user(request: Request, user_id: int):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	async with session_scope() as session:
		user = await session.get(User, user_id)
		if user is None:
			return RedirectResponse("/users", status_code=303)

		groups = (
			await session.scalars(select(Group).where(Group.owner_user_id == user_id).order_by(Group.title))
		).all()
		feedback_count = len(
			(await session.scalars(select(Feedback.id).where(Feedback.user_id == user_id))).all()
		)

	return templates.TemplateResponse(
		request,
		"user_delete.html",
		{"admin": admin, "user": user, "groups": groups, "feedback_count": feedback_count},
	)


@router.post("/users/{user_id}/delete")
async def delete_user(request: Request, user_id: int):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	await erase_user(user_id)
	return RedirectResponse("/users", status_code=303)


async def erase_user(user_id: int) -> bool:
	"""Delete the account and everything that belongs only to it.

	Groups the account set up are kept, so the rest of the group doesn't lose
	its settings. They are detached and deactivated instead, and any current
	admin can bring one back with /reauthenticate.
	"""
	async with session_scope() as session:
		user = await session.get(User, user_id)
		if user is None:
			return False

		groups = (await session.scalars(select(Group).where(Group.owner_user_id == user_id))).all()
		for group in groups:
			group.owner_user_id = None
			group.is_active = False

		await session.execute(delete(Feedback).where(Feedback.user_id == user_id))
		await session.execute(delete(AnnouncementDelivery).where(AnnouncementDelivery.user_id == user_id))
		await session.delete(user)
		return True
