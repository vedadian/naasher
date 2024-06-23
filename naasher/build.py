# =================================================================================
#  Copyright (c) 2024 Behrooz Vedadian

#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:

#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.

#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE.
# =================================================================================

import os
import re
import ast
import json
import inspect

from typing import cast, Any, Callable, Iterable, Generator
from datetime import datetime

from pathlib import Path
from bs4 import BeautifulSoup as bs4, ResultSet, Tag
from jinja2 import Environment, FileSystemLoader, Template, select_autoescape
from markupsafe import Markup, escape

from .mdex import (
    create_md_renderer,
    get_stylesheet as get_md_stylesheet,
    MATH_EXPR_PATTERN,
)
from .jdatetime import jstrftime, jalali_to_gregorian
from .common import LOGGER
from .js import temml, csso, uglifyjs3  # type: ignore

reCssFontFace = re.compile(r"@font\-face\s*\{[^\{\}]+\}")
reCssFontFaceUrl = re.compile(r"url\(([^\(\)]+)\)")
reMathExpr = re.compile(MATH_EXPR_PATTERN)

render_markdown = create_md_renderer()


class Keys:
    HTML5 = "html5"
    TEMPLATE = "template"
    DEFAULT_TEMPLATE = "default_template"
    CHILD = "child"
    DIR_LISTING_TEMPLATE = "dir_listing_template"
    UTF8 = "utf-8"
    HTML_PARSER = "html.parser"
    HEAD = "head"
    BODY = "body"
    LINK = "link"
    SCRIPT = "script"
    TYPE = "type"
    STYLE = "style"
    TEXT_CSS = "text/css"
    JAVASCRIPT = "javascript"
    SRC = "src"
    REL = "rel"
    STYLE_SHEET = "stylesheet"
    HREF = "href"


class DictWrapper(object):
    def __init__(self, n: str, d: dict):
        self.wrapped_dict_name = n
        self.wrapped_dict = {k: DictWrapper.__wrap(f"{n}.{k}", v) for k, v in d.items()}

    def __contains__(self, key: str):
        return key in self.wrapped_dict

    def __getitem__(self, key: str):
        result = self.wrapped_dict[key]
        if isinstance(result, dict):
            return DictWrapper(f"{self.wrapped_dict_name}.{key}", result)
        return result

    @staticmethod
    def __wrap(n, o):
        if isinstance(o, DictWrapper):
            return o
        elif isinstance(o, tuple):
            return tuple(DictWrapper.__wrap(f"{n}.{i}", e) for i, e in enumerate(o))
        elif isinstance(o, list):
            return [DictWrapper.__wrap(f"{n}.{i}", e) for i, e in enumerate(o)]
        elif isinstance(o, dict):
            return DictWrapper(n, o)
        return o

    @staticmethod
    def __unwrap(o):
        if isinstance(o, tuple):
            return tuple(DictWrapper.__unwrap(e) for e in o)
        elif isinstance(o, list):
            return [DictWrapper.__unwrap(e) for e in o]
        elif isinstance(o, DictWrapper):
            return {k: DictWrapper.__unwrap(v) for k, v in o.wrapped_dict.items()}
        return o

    def items(self):
        for k, v in self.wrapped_dict.items():
            yield k, DictWrapper.__unwrap(v)

    def values(self):
        for v in self.wrapped_dict.values():
            yield DictWrapper.__unwrap(v)


def read_meta(path: Path) -> dict[str, Any]:

    def normalize(k: str, v: Any) -> Any:
        if k.endswith("date"):
            vv = cast(str, v)
            is_solar_hijri = False
            for suffix in ("SHC", "JC"):
                if vv.endswith(suffix):
                    is_solar_hijri = True
                    vv = vv[: -len(suffix)]
                    break
            if is_solar_hijri:
                m = re.match(r"^(\d\d(\d\d)?)-(\d\d?)-(\d\d?)(T.*)?$", vv)
                if not m:
                    LOGGER.warning(f"Invalid date string: `{v}`")
                    return None
                y, four_digit_year, m, d, rest = m.groups()
                y, m, d = (int(e) for e in (y, m, d))
                if not four_digit_year:
                    y += 1400
                (y, m, d), _ = jalali_to_gregorian(y, m, d)
                v = f"{y}-{m:02}-{d:02}{rest or ''}"
            return datetime.fromisoformat(v)
        return v

    meta = json.loads(path.read_text(encoding=Keys.UTF8))
    meta = {k: normalize(k, v) for k, v in meta.items()}
    return meta


def build_static_site(
    source_dir: str = "source",
    theme_dir: str = "theme",
    build_dir: str = "build",
    force_recreation: bool = False,
):

    SOURCE_PATH = Path(source_dir).absolute()
    THEME_PATH = Path(theme_dir).absolute()
    BUILD_PATH = Path(build_dir).absolute()

    jinja_env = Environment(
        loader=FileSystemLoader(str(THEME_PATH)),
        autoescape=select_autoescape(["html", "css", "js"]),
    )

    def write_bytes(path: Path, get_bytes: Callable[[], bytes]):
        if (
            not force_recreation or path.suffix not in [".html", ".css"]
        ) and path.exists():
            LOGGER.info(f"Keeping existing `{path.relative_to(BUILD_PATH)}`")
        else:
            try:
                content = get_bytes()
                if content is not None:
                    if path.exists():
                        LOGGER.warning(f"Recreating `{path.relative_to(BUILD_PATH)}`")
                    else:
                        LOGGER.info(f"Creating `{path.relative_to(BUILD_PATH)}`")
                    path.write_bytes(content)
                else:
                    LOGGER.warning(
                        f"`Content reader returned `None` trying to populate `{path.relative_to(BUILD_PATH)}`"
                    )
            except Exception as e:
                LOGGER.error(
                    f"Exception trying to populate `{path.relative_to(BUILD_PATH)}`"
                )

    def id__(p: Path):
        return p.relative_to(SOURCE_PATH).as_posix()

    static_site_data: dict[str, tuple[dict, dict]] = {}
    missing_resources: set[str] = set()

    def create_utility_function_dict():
        nonlocal static_site_data
        nonlocal missing_resources

        def find_url(citeria: str):
            try:
                k = next(k for k in static_site_data.keys() if citeria in k)
                return f"/{k}"
            except StopIteration:
                return "?error=url_could_not_be_found"

        def find_info(id: str):
            meta, _ = static_site_data["."]
            if id in meta:
                return meta[id]
            return "?error=info_could_not_be_found"

        def find_lang(id: str):
            return find_url(id)

        def handle_math(text: str):
            result = Markup()
            i = 0
            while i < len(text):
                m = re.search(reMathExpr, text[i:])
                if not m:
                    break
                result += escape(
                    text[i : i + m.start()].replace("&nbsp;", "\u00A0")
                ) + Markup(temml(m.group()[1:-1]))
                i += m.end()
            if i < len(text):
                result += escape(text[i:].replace("&nbsp;", "\u00A0"))
            return result

        def short_gregorian(d: datetime):
            return jstrftime(d, "%b, %u %Y")

        def short_solar_hijri(d: datetime):
            return jstrftime(d, "%x %B %YSHC")

        def get_author(meta: dict[str, Any]) -> str:
            if "author" in meta:
                return meta["author"]
            if "author" in static_site_data["."][0]:
                return static_site_data["."][0]["author"]
            return "Behrooz Vedadian"

        def sort_by_date(iterable: Iterable):

            def __find_date(item: Any) -> tuple[bool, Any]:
                if hasattr(item, "date"):
                    return True, getattr(item, "date")
                try:
                    return True, item["date"]
                except (TypeError, KeyError):
                    pass
                if (
                    isinstance(item, tuple)
                    or isinstance(item, list)
                    or isinstance(item, Generator)
                ):
                    for subitem in item:
                        succeeded, value = __find_date(subitem)
                        if succeeded:
                            return True, value
                return False, 0

            def __key(item: Any) -> datetime:
                min_datetime = datetime.fromordinal(1)
                succeeded, value = __find_date(item)
                if succeeded:
                    return value or min_datetime
                return min_datetime

            if isinstance(iterable, type({}.items())):
                result = sorted(((k, v) for k, v in iterable), key=__key, reverse=True)
            else:
                result = sorted(iterable, key=__key, reverse=True)
            return result

        def get_theme_resource(
            names: list[str] | str | None,
            default: str | None = None,
            suffix: str | None = None,
        ):
            if names:
                for name in names if isinstance(names, list) else [names]:
                    resource = next(THEME_PATH.glob(f"**/{name}{suffix or ''}"), None)
                    if resource:
                        return "/" + str(resource.relative_to(THEME_PATH))
                missing_resources.add(f"{name}{suffix or ''}")
            if default:
                resource = next(THEME_PATH.glob(f"**/{default}{suffix or ''}"), None)
                if resource:
                    return "/" + str(resource.relative_to(THEME_PATH))
            return "#"

        def shield(f: Callable[..., Any]) -> Any:
            def wrapper(*args, **kwargs):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    LOGGER.error(f"Exception in utility function `{f.__name__}`")
                    return None

            wrapper.__f__ = f
            wrapper.__name__ = f.__name__
            return wrapper

        return {
            name: shield(value)
            for name, value in locals().items()
            if callable(value) and value != shield
        }

    utility_funcs: dict[str, Callable[..., Any]] = create_utility_function_dict()
    for n, f in utility_funcs.items():
        args, *_ = inspect.getfullargspec(f.__f__)
        if len(args) > 0:
            jinja_env.filters[n] = f

    def render_template(
        template: Template,
        item_id: str,
        is_html: bool,
        relative_path: str,
        css: list[str],
        js: list[str],
        farsi: bool = False,
    ):
        meta, mds = static_site_data[item_id]

        def nav_items():
            url = None
            for p in ["home"] + relative_path.split("/"):
                if url is None:
                    url = ""
                    yield "/", p
                else:
                    url = f"{url}/{p}"
                    yield url, p

        result = template.render(
            static_site_data=DictWrapper("static_site_data", static_site_data),
            children=DictWrapper(
                "children",
                {
                    k: v
                    for k, v in static_site_data.items()
                    if k.startswith(item_id) and len(k) > len(item_id)
                },
            ),
            meta=DictWrapper("meta", meta),
            mds=DictWrapper("mds", mds),
            item_id=item_id,
            nav_items=nav_items,
            **utility_funcs,
        )
        if not is_html:
            return result.encode(Keys.UTF8)
        result = bs4(result, features=Keys.HTML_PARSER)
        html_head = result.find(Keys.HEAD)
        html_body = cast(Tag, result.find(Keys.BODY))
        if html_head and css:
            for item in css:
                new_css_node = result.new_tag(Keys.LINK)
                new_css_node[Keys.REL] = Keys.STYLE_SHEET
                new_css_node[Keys.HREF] = f"{relative_path}/{item}"
                html_head.append(new_css_node)
        if html_body:
            if farsi:
                for n in html_body.find_all(text=True):
                    do_not_change_digits = False
                    p = n.parent
                    while p:
                        if p.name.lower() in ["section", "pre"]:
                            do_not_change_digits = True
                            break
                        p = p.parent
                    if do_not_change_digits:
                        p = n.parent
                        while p:
                            if p.name.lower() in ["math"]:
                                do_not_change_digits = False
                                break
                            p = p.parent
                    if do_not_change_digits:
                        continue
                    value = n.string
                    if value:
                        n.replace_with(
                            re.sub(
                                "[0-9]",
                                lambda m: chr(ord(m.group(0)) - ord("0") + ord("۰")),
                                value,
                            )
                        )
            if js:
                for item in js:
                    new_js_node = result.new_tag(Keys.SCRIPT)
                    new_js_node[Keys.TYPE] = Keys.JAVASCRIPT
                    new_js_node[Keys.SRC] = f"{relative_path}/{item}"
                    html_body.append(new_js_node)
        if html_head and mds:
            new_css_node = result.new_tag(Keys.STYLE)
            new_css_node[Keys.TYPE] = Keys.TEXT_CSS
            new_css_node.string = csso(get_md_stylesheet())["css"]
            html_head.append(new_css_node)
        result = result.encode(encoding=Keys.UTF8, formatter="html5")
        return result

    def render_template_by_template_name(
        name: str, item_id: str, relative_path: str, css: list[str], js: list[str]
    ):
        result = render_template(
            jinja_env.get_template(f"{name}.html"),
            item_id,
            True,
            relative_path,
            css,
            js,
            name.endswith("_fa"),
        )
        return result

    def render_template_file(template: Path, item_id: str):
        return render_template(
            jinja_env.from_string(template.read_text()),
            item_id,
            False,
            str(template.relative_to(SOURCE_PATH)),
            [],
            [],
        )

    def gather_data_from_source_tree(p: Path):
        nonlocal static_site_data
        meta = {}
        mds = {}
        for c in p.iterdir():
            if not c.is_file():
                continue
            if c.name == "meta.json":
                meta = read_meta(c)
            elif c.suffix == ".md":
                mds[c.stem] = render_markdown(c.read_text())
        static_site_data[id__(p)] = (meta, mds)
        for c in p.iterdir():
            if not c.is_file():
                gather_data_from_source_tree(c)

    dependencies: list[str] = []

    def generate_static_site_item(
        p: Path, default_template_name: str, default_dir_listing_template_name: str
    ):
        item_id = id__(p)
        meta, mds = static_site_data[item_id]
        child_default_template_name = default_template_name
        if f"{Keys.CHILD}_{Keys.TEMPLATE}" in meta:
            child_default_template_name = meta[f"{Keys.CHILD}_{Keys.TEMPLATE}"]
            LOGGER.info(f"Default template changed to `{child_default_template_name}`")
        child_default_dir_listing_template_name = default_dir_listing_template_name
        if f"{Keys.CHILD}_{Keys.DIR_LISTING_TEMPLATE}" in meta:
            child_default_dir_listing_template_name = meta[
                f"{Keys.CHILD}_{Keys.DIR_LISTING_TEMPLATE}"
            ]
            LOGGER.info(
                f"Default dir listing template changed to `{child_default_dir_listing_template_name}`"
            )
        relative_path = p.relative_to(SOURCE_PATH)
        o = BUILD_PATH / relative_path
        o.mkdir(mode=0o755, parents=True, exist_ok=True)
        css = []
        js = []
        for c in p.iterdir():
            if not c.is_file():
                generate_static_site_item(
                    c,
                    child_default_template_name,
                    child_default_dir_listing_template_name,
                )
                continue
            is_binary_file = True
            if c.name == "meta.json":
                is_binary_file = False
                continue
            elif c.suffix == ".md":
                is_binary_file = False
                continue
            if c.suffix == ".js":
                is_binary_file = False
                js.append(c.name)
            elif c.suffix == ".css":
                is_binary_file = False
                css.append(c.name)
            oc = o / c.name

            write_bytes(
                oc,
                (
                    c.read_bytes
                    if is_binary_file
                    else lambda: render_template_file(c, item_id)
                ),
            )

        if meta or mds:
            template_name = default_template_name
            if Keys.TEMPLATE in meta:
                template_name = meta[Keys.TEMPLATE]
        else:
            template_name = default_dir_listing_template_name
            if Keys.DIR_LISTING_TEMPLATE in meta:
                template_name = meta[Keys.DIR_LISTING_TEMPLATE]

        def create_index_html_contents():
            html = render_template_by_template_name(
                template_name, item_id, relative_path.as_posix(), css, js
            )
            html = bs4(html, Keys.HTML_PARSER)
            html_head: Tag | None = html.find(Keys.HEAD)  # type: ignore
            html_body: Tag | None = html.find(Keys.BODY)  # type: ignore
            if html_head:
                all_links: ResultSet[Tag] = html_head.find_all(Keys.LINK)
                for link in all_links:
                    if (
                        Keys.HREF in link.attrs
                        and Keys.REL in link.attrs
                        and Keys.STYLE_SHEET in link[Keys.REL]
                        and link[Keys.HREF].strip().startswith("/")  # type: ignore
                    ):
                        dependency = link[Keys.HREF].strip()[1:]  # type: ignore
                        dependencies.append(dependency)

            if html_body:
                all_elements_with_src: ResultSet[Tag] = html_body.find_all(
                    attrs={Keys.SRC: True}
                )
                for element_with_src in all_elements_with_src:
                    if element_with_src[Keys.SRC].strip().startswith("/"):  # type: ignore
                        dependencies.append(element_with_src[Keys.SRC].strip()[1:])  # type: ignore
            return str(html).encode(encoding=Keys.UTF8)

        write_bytes((o / "index.html"), create_index_html_contents)

    gather_data_from_source_tree(SOURCE_PATH)

    root_meta, _ = static_site_data.get(".", ({}, None))
    generate_static_site_item(
        SOURCE_PATH,
        root_meta.get("default_template", "default_template"),
        root_meta.get("default_dir_listing_template", "default_dir_listing_template"),
    )

    def get_referenced_font_paths(css_contents: bytes):
        font_urls: set[str] = set()
        for fontface_def in re.findall(
            reCssFontFace,
            css_contents.decode(Keys.UTF8),
        ):
            for m in re.finditer(reCssFontFaceUrl, fontface_def):
                font_url = m.group(1)
                if font_url.startswith(("'", '"')):
                    font_url = ast.literal_eval(font_url)
                font_urls.add(font_url)
        base_font_path = Path(dependency).parent
        return ((base_font_path / u).as_posix() for u in font_urls)

    def get_font_css_content_reader(json_file: Path):
        def get_fontface_def(
            parent: Path,
            file: str,
            keys: dict[str, str | int | float],
            common: dict[str, str | int | float],
        ):
            font_family = keys.get("font-family", common.get("font-family"))
            if not font_family:
                return None
            src_items = [f'local("{font_family}")']
            for suffix, type__ in [
                (".woff2", "woff2"),
                (".woff", "woff"),
                (".ttf", "truetype"),
                ("otf", "opentype"),
            ]:
                f = (parent / f"{file}{suffix}").absolute()
                if f.exists():
                    src_items.append(
                        f'url("{f.relative_to(parent)}") format("{type__}")'
                    )
            if len(src_items) < 2:
                return None
            src_items = ",\n       ".join(src_items)
            font_rule = ";\n  ".join(
                f"{k}: {v}" for k, v in {**common, **keys, "src": src_items}.items()
            )
            return f"@font-face {{\n  {font_rule};\n}}"

        def read_bytes():
            description = json.loads(json_file.read_text())
            parent = json_file.parent
            common: dict[str, str | int | float] = {
                k: v for k, v in description.items() if k != "files"
            }
            lines = list(
                filter(
                    None,
                    (
                        get_fontface_def(parent, file, keys, common)
                        for file, keys in description["files"].items()
                    ),
                )
            )
            if not lines:
                raise ValueError(
                    f"No consumable fonts were found in `{json_file.relative_to(THEME_PATH)}`"
                )
            LOGGER.info(
                f"Stylesheet corresponding to `{json_file.relative_to(THEME_PATH)}` created"
            )

            return "\n".join(lines).encode(encoding=Keys.UTF8)

        return read_bytes

    next_level_dependencies = list(set(dependencies))
    while next_level_dependencies:
        dependencies = next_level_dependencies
        next_level_dependencies = []
        for dependency in dependencies:
            d = THEME_PATH / dependency
            o = BUILD_PATH / dependency
            if not force_recreation and o.exists():
                LOGGER.info(f"Keeping existing `{o.relative_to(BUILD_PATH)}`")
            else:
                read_bytes: Callable[[], bytes] | None = None
                if not d.exists():
                    if d.suffix == ".css" and d.with_suffix(".json").exists():
                        read_bytes = get_font_css_content_reader(d.with_suffix(".json"))
                else:
                    read_bytes = d.read_bytes
                if read_bytes is None:
                    LOGGER.warning(
                        f"A dependency for the static site was missing from the theme ({dependency})"
                    )
                    continue
                if d.suffix == ".css":
                    css_contents = read_bytes()
                    next_level_dependencies.extend(
                        get_referenced_font_paths(css_contents)
                    )
                    read_bytes = lambda: css_contents
                o.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                write_bytes(o, read_bytes)

        for resource in missing_resources:
            LOGGER.warning(
                f"Resource `{resource}` was referenced and could not be found in the theme"
            )


if __name__ == "__main__":
    LOGGER.error("This module must not be called directly")
