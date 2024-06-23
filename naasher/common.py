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
import sys
import logging
import click
import copy
import traceback as tb

from pathlib import Path
from typing import Any, Literal, Callable

MODULE_PATH = Path(__file__).parent.absolute()


class ColorizedLogFormatter(logging.Formatter):
    level_name_colors = {
        logging.DEBUG: lambda level_name: click.style(str(level_name), fg="cyan"),
        logging.INFO: lambda level_name: click.style(str(level_name), fg="green"),
        logging.WARNING: lambda level_name: click.style(str(level_name), fg="yellow"),
        logging.ERROR: lambda level_name: click.style(str(level_name), fg="red"),
        logging.CRITICAL: lambda level_name: click.style(
            str(level_name), fg="bright_red"
        ),
    }

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        style: Literal["%", "{", "$"] = "%",
    ):
        super().__init__(fmt, datefmt, style)

    def color_level_name(self, level_name: str, level_no: int) -> str:
        def default(level_name: str) -> str:
            return str(level_name)  # pragma: no cover

        func = self.level_name_colors.get(level_no, default)
        return func(level_name)

    def formatMessage(self, record: logging.LogRecord) -> str:
        current_exception_class, exception, _ = sys.exc_info()
        exception_message = "<none>"
        exc_class_name = "<none>"
        petit_traceback = "<none>"
        if exception is not None:
            exception_message = click.style(str(exception), fg="bright_cyan")
        if current_exception_class is not None:
            exc_class_name = click.style(
                (
                    current_exception_class.__name__
                    + (
                        exception.__cause__.__class__.__name__
                        if exception and exception.__cause__
                        else ""
                    )
                ),
                fg="bright_cyan",
            )
        traceback_items = []
        while exception is not None:
            if exception.__traceback__:
                for s in tb.extract_tb(exception.__traceback__):
                    f = Path(s.filename)
                    if not f.is_relative_to(MODULE_PATH.parent):
                        traceback_items.append("...")
                        continue
                    traceback_items.append(
                        f"{os.path.relpath(str(f), os.getcwd())}:{s.lineno}"
                    )
            exception = exception.__cause__ or exception.__context__
        if traceback_items:
            execution_count = 1
            for i in range(len(traceback_items) - 1, 0, -1):
                if traceback_items[i] == traceback_items[i - 1]:
                    execution_count += 1
                    del traceback_items[i]
                else:
                    if execution_count > 1:
                        traceback_items[i] = (
                            f"{traceback_items[i]} (x{execution_count})"
                        )
                    execution_count = 1
            petit_traceback = click.style(
                "\n=> ".join(
                    " => ".join(traceback_items[i : i + 4])
                    for i in range(0, len(traceback_items), 4)
                ),
                fg="cyan",
            )
        recordcopy = copy.copy(record)
        levelname = recordcopy.levelname
        seperator = " " * (8 - len(levelname))
        levelname = self.color_level_name(levelname, recordcopy.levelno)
        recordcopy.__dict__["exc_class_name"] = exc_class_name
        recordcopy.__dict__["petit_traceback"] = petit_traceback
        recordcopy.__dict__["exception_message"] = exception_message
        if "color_message" in recordcopy.__dict__:
            recordcopy.msg = recordcopy.__dict__["color_message"]
            recordcopy.__dict__["message"] = recordcopy.getMessage()
        recordcopy.__dict__["levelprefix"] = f"{levelname}:{seperator}"
        return "\n".join(
            l if i == 0 else f"{' ' * 10}{l}"
            for i, l in enumerate(super().formatMessage(recordcopy).split("\n"))
        )


LOG_HANDLER = logging.StreamHandler()
LOG_HANDLER.setFormatter(ColorizedLogFormatter("%(levelprefix)s %(message)s"))
LOG_HANDLER.addFilter(lambda r: r.levelno < logging.ERROR)
ERR_LOG_HANDLER = logging.StreamHandler()
ERR_LOG_HANDLER.setFormatter(
    ColorizedLogFormatter(
        "%(levelprefix)s %(message)s\n%(exc_class_name)s %(exception_message)s\nin %(petit_traceback)s"
    )
)
ERR_LOG_HANDLER.addFilter(lambda r: r.levelno >= logging.ERROR)
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(LOG_HANDLER)
LOGGER.addHandler(ERR_LOG_HANDLER)
LOGGER.setLevel(logging.INFO)
