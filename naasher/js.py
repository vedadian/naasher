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
from py_mini_racer import MiniRacer

from .common import LOGGER

def __create_js_interface(name: str, spec: dict):
    console_members = { "log": "info", "warn": "warning", "error": "error" }
    context = MiniRacer()
    console_script = "function console_impl(t) { return function() { this[t].push([...arguments].map(e => `${e}`).join('|')) } }; console = { };"
    for m in console_members.keys():
        console_script += f"console.{m}__ = []; console.{m} = console_impl('{m}__');"
    console_script += "console.clear = function() {"
    for m in console_members.keys():
        console_script += f"this.{m}__ = [];"
    console_script += "}"
    context.eval(console_script)
    with open(os.path.join(os.path.dirname(__file__), f"./js/{name}.min.js")) as f:
        context.eval(f.read())
    def call_show_logs(*args, **kwargs):
        context.eval("console.clear();")
        result = context.call(spec["entry"], *args, **kwargs)
        for m, n in console_members.items():
            for l in context.eval(f"console.{m}__"): # type: ignore
                getattr(LOGGER, n)(l)
        return result
    def interface(*args, **kwargs__):
        kwargs=spec["defaults"]
        kwargs.update(kwargs__)
        return call_show_logs(*args, **kwargs)
    return interface


for name, spec in {
    "csso": {
        "defaults": {},
        "entry": "csso.minify"
    },
    "uglifyjs3": {
        "defaults": {
            "mangle": True,
            "compress": {
                "sequences": True,
                "dead_code": True,
                "conditionals": True,
                "booleans": True,
                "unused": True,
                "if_return": True,
                "join_vars": True,
                "drop_console": True,
            },
        },
        "entry": "minify"
    },
    "temml": {
        "defaults": { },
        "entry": "temml.renderToString"
    },
}.items():
    globals()[name] = __create_js_interface(name, spec)

del __create_js_interface