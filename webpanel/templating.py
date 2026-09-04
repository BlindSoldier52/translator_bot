from pathlib import Path

from fastapi.templating import Jinja2Templates

from webpanel.csrf import csrf_input

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
templates.env.globals["csrf_input"] = csrf_input
