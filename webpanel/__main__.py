"""Entry point for the admin panel: `python -m webpanel`.

Binding is done here, from PANEL_HOST/PANEL_PORT, so the configured address is the
address actually listened on rather than something a service file repeats by hand.
"""

import uvicorn

from shared.config import get_settings


def main() -> None:
	settings = get_settings()
	uvicorn.run(
		"webpanel.main:app",
		host=settings.panel_host,
		port=settings.panel_port,
		proxy_headers=True,
		forwarded_allow_ips=settings.trusted_proxies,
		log_level=settings.log_level.lower(),
		access_log=False,
	)


if __name__ == "__main__":
	main()
