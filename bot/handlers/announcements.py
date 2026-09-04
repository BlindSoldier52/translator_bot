import asyncio
import datetime
import logging

from sqlalchemy import select
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.constants import ANNOUNCEMENT_MAX_ATTEMPTS, ANNOUNCEMENT_SEND_THROTTLE_SECONDS
from shared.db import session_scope
from shared.models import Announcement, AnnouncementDelivery, User

logger = logging.getLogger(__name__)


async def pending_deliveries() -> list[tuple[int, int, str]]:
	"""Read what still has to go out, as plain values, so nothing is held open while sending."""
	async with session_scope() as session:
		deliveries = (
			await session.scalars(
				select(AnnouncementDelivery)
				.where(
					AnnouncementDelivery.status == "pending",
					AnnouncementDelivery.attempts < ANNOUNCEMENT_MAX_ATTEMPTS,
				)
				.order_by(AnnouncementDelivery.id)
			)
		).all()
		if not deliveries:
			return []

		announcements = {
			announcement.id: announcement.body
			for announcement in (
				await session.scalars(
					select(Announcement).where(
						Announcement.id.in_({delivery.announcement_id for delivery in deliveries})
					)
				)
			).all()
		}
		users = {
			user.id: user
			for user in (
				await session.scalars(
					select(User).where(User.id.in_({delivery.user_id for delivery in deliveries}))
				)
			).all()
		}

		sendable = []
		for delivery in deliveries:
			user = users.get(delivery.user_id)
			body = announcements.get(delivery.announcement_id)
			if user is None or body is None or user.is_blocked:
				delivery.status = "failed"
				continue
			sendable.append((delivery.id, user.telegram_user_id, body))
		return sendable


async def record_attempt(delivery_id: int, delivered: bool) -> None:
	"""Persist one delivery's outcome on its own, so a later failure cannot undo it."""
	async with session_scope() as session:
		delivery = await session.get(AnnouncementDelivery, delivery_id)
		if delivery is None:
			return
		delivery.attempts += 1
		if delivered:
			delivery.status = "sent"
			delivery.sent_at = datetime.datetime.now(datetime.timezone.utc)
		elif delivery.attempts >= ANNOUNCEMENT_MAX_ATTEMPTS:
			delivery.status = "failed"


async def send_pending_announcements(context: ContextTypes.DEFAULT_TYPE) -> None:
	for delivery_id, telegram_user_id, body in await pending_deliveries():
		delivered = True
		try:
			await context.bot.send_message(telegram_user_id, body)
		except TelegramError:
			delivered = False
			logger.info("Could not deliver announcement %s to chat %s", delivery_id, telegram_user_id)
		await record_attempt(delivery_id, delivered)
		await asyncio.sleep(ANNOUNCEMENT_SEND_THROTTLE_SECONDS)
