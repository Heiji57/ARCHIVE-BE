from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

# src/app/shared/infrastructure/email/templates.py
# parents[0]=email, [1]=infrastructure, [2]=shared, [3]=app, [4]=src, [5]=project root
_TEMPLATES_DIR = Path(__file__).resolve().parents[5] / "static" / "emails"


@lru_cache
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_email(template_name: str, **context: object) -> str:
    return _env().get_template(template_name).render(**context)
