"""Utilitarios de renderizacao de textos configuraveis."""
import re


def render_text_template(template_str, ctx):
    """Renderiza variaveis no formato {campo} e, opcionalmente, sintaxe Jinja."""
    text = str(template_str or "")
    values = {key: ("" if value is None else value) for key, value in (ctx or {}).items()}

    def replace_brace_var(match):
        key = match.group(1)
        return str(values.get(key, match.group(0)))

    rendered = re.sub(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})", replace_brace_var, text)

    if "{{" in rendered or "{%" in rendered:
        try:
            from jinja2 import Template
            return Template(rendered).render(**values)
        except Exception:
            return rendered
    return rendered
