from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from shared.db import session_scope
from shared.models import Group, User
from shared.translation import COMMON_LANGUAGES
from webpanel.auth import get_current_admin, require_admin_or_redirect
from webpanel.templating import templates

router = APIRouter()


@router.get("/groups")
async def list_groups(request: Request):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	async with session_scope() as session:
		rows = (
			await session.execute(
				select(Group, User.username)
				.outerjoin(User, User.id == Group.owner_user_id)
				.order_by(Group.title)
			)
		).all()

	groups = [
		{
			"id": group.id,
			"title": group.title,
			"owner_username": owner_username,
			"primary_language": group.primary_language,
			"language_label": COMMON_LANGUAGES.get(group.primary_language, "Detecting automatically..."),
			"is_active": group.is_active,
			"is_blocked": group.is_blocked,
			"daily_message_limit": group.daily_message_limit,
		}
		for group, owner_username in rows
	]

	return templates.TemplateResponse(
		request, "groups.html", {"admin": admin, "groups": groups, "languages": COMMON_LANGUAGES}
	)


@router.post("/groups/{group_id}/language")
async def update_group_language(request: Request, group_id: int, language_code: str = Form(...)):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	if language_code not in COMMON_LANGUAGES:
		return RedirectResponse("/groups", status_code=303)

	async with session_scope() as session:
		group = await session.get(Group, group_id)
		if group is not None:
			group.primary_language = language_code
			group.language_mode = "manual"
			group.language_votes = {}
			group.language_sample_count = 0

	return RedirectResponse("/groups", status_code=303)


@router.post("/groups/{group_id}/limit")
async def update_group_limit(request: Request, group_id: int, daily_message_limit: str = Form(...)):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	value = daily_message_limit.strip()
	limit = None
	if value:
		try:
			limit = int(value)
		except ValueError:
			return RedirectResponse("/groups", status_code=303)
		if limit < 1:
			return RedirectResponse("/groups", status_code=303)

	async with session_scope() as session:
		group = await session.get(Group, group_id)
		if group is not None:
			group.daily_message_limit = limit

	return RedirectResponse("/groups", status_code=303)


@router.post("/groups/{group_id}/block")
async def block_group(request: Request, group_id: int):
	return await set_group_blocked(request, group_id, True)


@router.post("/groups/{group_id}/unblock")
async def unblock_group(request: Request, group_id: int):
	return await set_group_blocked(request, group_id, False)


async def set_group_blocked(request: Request, group_id: int, blocked: bool):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	async with session_scope() as session:
		group = await session.get(Group, group_id)
		if group is not None:
			group.is_blocked = blocked

	return RedirectResponse("/groups", status_code=303)
