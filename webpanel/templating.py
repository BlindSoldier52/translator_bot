from pathlib import Path

from fastapi.templating import Jinja2Templates

from shared.config import get_settings
from webpanel.csrf import csrf_input

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
templates.env.globals["csrf_input"] = csrf_input
templates.env.globals["source_url"] = get_settings().source_url
