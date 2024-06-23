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

import inspect
import argparse

from typing import Any, Callable
from pathlib import Path

from .common import LOGGER
from .build import build_static_site


class Application(object):
    def __init__(self, name: str):
        self.name = name
        self.commands: dict[str | None, Callable[..., Any]] = {}
        self.parsers: dict[str | None, argparse.ArgumentParser] = {}
        self.default_command: str | None = None
        self.parser_for_help = argparse.ArgumentParser(self.name)

    def add_command(self, f: Callable[..., Any]):
        signature = inspect.signature(f)

        namespaces = [
            argparse.ArgumentParser(f"{self.name} {f.__name__}"),
            self.parser_for_help.add_argument_group(f"`{f.__name__}` parameters"),
        ]
        for namespace in namespaces:
            for name, p in signature.parameters.items():
                namespace.add_argument(
                    f"--{name}",
                    type=p.annotation,
                    default=p.default,
                    required=p.default == inspect.Parameter.empty,
                )
        if self.default_command is None:
            self.default_command = f.__name__
        self.parsers[f.__name__] = namespaces[0]
        self.commands[f.__name__] = f

    def run(self):
        try:
            command_parser = argparse.ArgumentParser(self.name, add_help=False)
            command_parser.add_argument(
                "command",
                nargs="?",
                choices=self.commands.keys(),
                default=self.default_command,
            )
            command_parser.add_argument("-h", "--help", action="store_true")
            for p in self.parsers.values():
                p.add_argument(
                    "command",
                    nargs="?",
                    choices=self.commands.keys(),
                    default=self.default_command,
                )
            known_args = command_parser.parse_known_args()[0]
            if known_args.help:
                self.parser_for_help.print_help()
                self.parser_for_help.exit()
            args = self.parsers[known_args.command].parse_args()
            self.commands[known_args.command](
                **{k: v for k, v in args.__dict__.items() if k != "command"}
            )
        except Exception as e:
            LOGGER.error(f"Error running the CLI application `{self.name}`")


def start_development_server(static_site_dir: str = "build", host: str = "127.0.0.1", port: int = 8000):
    import socket
    import contextlib
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    class DualStackServer(ThreadingHTTPServer):

        def server_bind(self):
            # suppress exception when protocol is IPv4
            with contextlib.suppress(Exception):
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            return super().server_bind()

        def finish_request(self, request, client_address):
            SimpleHTTPRequestHandler(
                request,
                client_address,
                self,
                directory=str(Path(static_site_dir).absolute()),
            )

    SimpleHTTPRequestHandler.protocol_version = "HTTP/1.0"
    with DualStackServer((host, port), SimpleHTTPRequestHandler) as httpd:
        host, port = httpd.socket.getsockname()[:2]
        url_host = f"[{host}]" if ":" in host else host
        print(f"Serving HTTP on {host} port {port} " f"(http://{url_host}:{port}/) ...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nKeyboard interrupt received, exiting.")


app = Application("publish")
app.add_command(build_static_site)
app.add_command(start_development_server)
app.run()
