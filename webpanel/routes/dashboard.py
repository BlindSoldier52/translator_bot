from datetime import date

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from shared.config import get_settings
from shared.db import session_scope
from shared.models import AppSettings, DailyCounter, Group, User
from webpanel.auth import get_current_admin, require_admin_or_redirect
from webpanel.templating import templates

router = APIRouter()


@router.get("/")
async def dashboard(request: Request):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	async with session_scope() as session:
		settings_row = await session.get(AppSettings, 1)
		daily_limit = settings_row.daily_message_limit if settings_row else get_settings().default_daily_message_limit

		counter = await session.get(DailyCounter, date.today())
		today_count = counter.translated_count if counter else 0

		active_groups_count = await session.scalar(
			select(func.count()).select_from(Group).where(Group.is_active == True, Group.is_blocked == False)  # noqa: E712
		)
		blocked_groups_count = await session.scalar(
			select(func.count()).select_from(Group).where(Group.is_blocked == True)  # noqa: E712
		)
		total_users_count = await session.scalar(select(func.count()).select_from(User))

	return templates.TemplateResponse(
		request,
		"dashboard.html",
		{
			"admin": admin,
			"today_count": today_count,
			"daily_limit": daily_limit,
			"active_groups_count": active_groups_count or 0,
			"blocked_groups_count": blocked_groups_count or 0,
			"total_users_count": total_users_count or 0,
		},
	)
