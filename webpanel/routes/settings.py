from fastapi import APIRouter, Form, Request
from sqlalchemy import delete

from shared.db import session_scope
from shared.models import AppSettings, GroupMaintenanceNotice
from webpanel.auth import get_current_admin, require_admin_or_redirect
from webpanel.templating import templates

router = APIRouter()


@router.get("/settings")
async def settings_form(request: Request):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	async with session_scope() as session:
		settings_row = await session.get(AppSettings, 1)
		daily_message_limit = settings_row.daily_message_limit if settings_row else 500
		maintenance_enabled = settings_row.maintenance_enabled if settings_row else False
		maintenance_message = (settings_row.maintenance_message if settings_row else None) or ""

	return templates.TemplateResponse(
		request,
		"settings.html",
		{
			"admin": admin,
			"daily_message_limit": daily_message_limit,
			"maintenance_enabled": maintenance_enabled,
			"maintenance_message": maintenance_message,
		},
	)


@router.post("/settings")
async def settings_submit(
	request: Request,
	daily_message_limit: int = Form(...),
	maintenance_enabled: bool = Form(False),
	maintenance_message: str = Form(""),
):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	if daily_message_limit < 1:
		return templates.TemplateResponse(
			request,
			"settings.html",
			{
				"admin": admin,
				"daily_message_limit": daily_message_limit,
				"maintenance_enabled": maintenance_enabled,
				"maintenance_message": maintenance_message,
				"error": "The daily limit must be at least 1.",
			},
			status_code=400,
		)

	cleaned_message = maintenance_message.strip() or None

	async with session_scope() as session:
		settings_row = await session.get(AppSettings, 1)
		was_enabled = settings_row.maintenance_enabled if settings_row else False

		if settings_row is None:
			settings_row = AppSettings(
				id=1,
				daily_message_limit=daily_message_limit,
				maintenance_enabled=maintenance_enabled,
				maintenance_message=cleaned_message,
			)
			session.add(settings_row)
		else:
			settings_row.daily_message_limit = daily_message_limit
			settings_row.maintenance_enabled = maintenance_enabled
			settings_row.maintenance_message = cleaned_message

		if maintenance_enabled and not was_enabled:
			await session.execute(delete(GroupMaintenanceNotice))

	return templates.TemplateResponse(
		request,
		"settings.html",
		{
			"admin": admin,
			"daily_message_limit": daily_message_limit,
			"maintenance_enabled": maintenance_enabled,
			"maintenance_message": maintenance_message,
			"saved": True,
		},
	)
