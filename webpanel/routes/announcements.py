from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select

from shared.db import session_scope
from shared.models import Announcement, AnnouncementDelivery, User
from webpanel.auth import get_current_admin, require_admin_or_redirect
from webpanel.templating import templates

router = APIRouter()

ANNOUNCEMENT_MAX_LEN = 4000


@router.get("/announcements")
async def list_announcements(request: Request):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	async with session_scope() as session:
		rows = (
			await session.execute(
				select(
					Announcement,
					func.count(AnnouncementDelivery.id).label("total"),
					func.count(AnnouncementDelivery.id).filter(AnnouncementDelivery.status == "sent").label("sent"),
					func.count(AnnouncementDelivery.id).filter(AnnouncementDelivery.status == "failed").label("failed"),
				)
				.outerjoin(AnnouncementDelivery, AnnouncementDelivery.announcement_id == Announcement.id)
				.group_by(Announcement.id)
				.order_by(Announcement.created_at.desc())
			)
		).all()

	announcements = [
		{
			"id": announcement.id,
			"body": announcement.body,
			"created_at": announcement.created_at,
			"total": total,
			"sent": sent,
			"failed": failed,
			"pending": total - sent - failed,
		}
		for announcement, total, sent, failed in rows
	]

	return templates.TemplateResponse(
		request, "announcements.html", {"admin": admin, "announcements": announcements}
	)


@router.get("/announcements/new")
async def new_announcement_form(request: Request):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	return templates.TemplateResponse(request, "announcements_new.html", {"admin": admin})


@router.post("/announcements")
async def create_announcement(request: Request, body: str = Form(...)):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	text = body.strip()
	if not text:
		return templates.TemplateResponse(
			request,
			"announcements_new.html",
			{"admin": admin, "body": body, "error": "Announcement text cannot be empty."},
			status_code=400,
		)
	if len(text) > ANNOUNCEMENT_MAX_LEN:
		return templates.TemplateResponse(
			request,
			"announcements_new.html",
			{
				"admin": admin,
				"body": body,
				"error": f"Announcement is too long ({len(text)} characters, max {ANNOUNCEMENT_MAX_LEN}).",
			},
			status_code=400,
		)

	async with session_scope() as session:
		announcement = Announcement(body=text, created_by_admin_id=admin.id)
		session.add(announcement)
		await session.flush()

		user_ids = (await session.scalars(select(User.id).where(User.is_blocked == False))).all()  # noqa: E712
		session.add_all(
			[
				AnnouncementDelivery(announcement_id=announcement.id, user_id=user_id)
				for user_id in user_ids
			]
		)

	return RedirectResponse("/announcements", status_code=303)


@router.get("/announcements/{announcement_id}")
async def announcement_detail(request: Request, announcement_id: int):
	admin = await get_current_admin(request)
	redirect = require_admin_or_redirect(admin)
	if redirect:
		return redirect

	async with session_scope() as session:
		announcement = await session.get(Announcement, announcement_id)
		if announcement is None:
			return RedirectResponse("/announcements", status_code=303)

		rows = (
			await session.execute(
				select(AnnouncementDelivery, User.username)
				.join(User, User.id == AnnouncementDelivery.user_id)
				.where(AnnouncementDelivery.announcement_id == announcement_id)
				.order_by(AnnouncementDelivery.status, User.username)
			)
		).all()

	deliveries = [
		{
			"username": username,
			"status": delivery.status,
			"sent_at": delivery.sent_at,
		}
		for delivery, username in rows
	]

	return templates.TemplateResponse(
		request,
		"announcement_detail.html",
		{"admin": admin, "announcement": announcement, "deliveries": deliveries},
	)
