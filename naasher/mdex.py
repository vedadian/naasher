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

from typing import Any

from .js import temml  # type:ignore

MATH_EXPR_PATTERN = r"\$(?:[^\$\s]|\\\$)((?:[^\$]|\\\$)*(?:[^\$\s]|\\\$))?\$"
HTML_FORMATTER_STYLE = "algol_nu"

def create_md_renderer():
    import re
    from html import unescape as unescape_html
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.formatters import HtmlFormatter
    from commonmark.node import Node
    from commonmark.common import unescape_string
    from commonmark.blocks import Block, BlockStarts, peek, is_space_or_tab
    from commonmark.inlines import InlineParser
    from commonmark import Parser, HtmlRenderer

    # Dirty hack for a library that deserves it >:(
    import commonmark.blocks

    commonmark.blocks.reMaybeSpecial = re.compile(r"^[#\$`~*+_=<>0-9-]")
    import commonmark.inlines

    commonmark.inlines.reMain = re.compile(r'^[^\n\$`\[\]\\!<&*_\'"]+', re.MULTILINE)

    reMathExprHere = re.compile(f"^{MATH_EXPR_PATTERN}")
    reSideNoteHere = re.compile(r"^\[>[^\]]+\]")
    reMathFence = re.compile(r"^\${3,}(?!.*\$)")
    reClosingMathFence = re.compile(r"^(?:\${3,})(?= *$)")

    class MathBlock(Block):
        accepts_lines = True

        @staticmethod
        def continue_(parser: Any, container: Any):
            ln: str = parser.current_line
            indent = parser.indent
            if container.is_fenced:
                match = (
                    indent <= 3
                    and len(ln) >= parser.next_nonspace + 1
                    and ln[parser.next_nonspace] == container.fence_char
                    and re.search(reClosingMathFence, ln[parser.next_nonspace :])
                )
                if match and len(match.group()) >= container.fence_length:
                    # closing fence - we're at end of line, so we can return
                    parser.finalize(container, parser.line_number)
                    return 2
                else:
                    # skip optional spaces of fence offset
                    i = container.fence_offset
                    while i > 0 and is_space_or_tab(peek(ln, parser.offset)):
                        parser.advance_offset(1, True)
                        i -= 1
            return 0

        @staticmethod
        def finalize(parser: Any, block: Any):
            if block.is_fenced:
                # first line becomes info string
                content = block.string_content
                newline_pos = content.index("\n")
                first_line = content[0:newline_pos]
                rest = content[newline_pos + 1 :]
                block.info = unescape_string(first_line.strip())
                block.literal = rest

            block.string_content = None

        @staticmethod
        def can_contain(t):
            return False

    class BlockStartsEx(BlockStarts):

        METHODS = [
            "fenced_math_block",
        ] + BlockStarts.METHODS

        @staticmethod
        def fenced_math_block(parser, container=None):
            if not parser.indented:
                m = re.search(reMathFence, parser.current_line[parser.next_nonspace :])
                if m:
                    fence_length = len(m.group())
                    parser.close_unmatched_blocks()
                    container = parser.add_child("math_block", parser.next_nonspace)
                    container.is_fenced = True
                    container.fence_length = fence_length
                    container.fence_char = m.group()[0]
                    container.fence_offset = parser.indent
                    parser.advance_next_nonspace()
                    parser.advance_offset(fence_length, False)
                    return 2

            return 0

    class InlineParserEx(InlineParser):

        def parseDollarSign(self, block):
            mathexpr = self.match(reMathExprHere)
            if mathexpr is None:
                return False
            node = Node("math", self.pos)
            node.literal = mathexpr[1:-1]
            block.append_child(node)
            return True

        def parseSidenote(self, block):
            sidenote = self.match(reSideNoteHere)
            if sidenote is None:
                return False
            node = Node("sidenote", self.pos)
            node.literal = sidenote[2:-1]
            block.append_child(node)
            return True

        def peek(self, offset: int = 0) -> str:
            old_pos = self.pos
            self.pos += offset
            result = super().peek()
            self.pos = old_pos
            return result

        def parseInline(self, block: Node):
            c = self.peek()
            res = False
            if c == "$":
                res = self.parseDollarSign(block)
            elif c == "[" and self.peek(1) == ">":
                res = self.parseSidenote(block)
            if not res:
                res = super().parseInline(block)
            return res

    class ParserEx(Parser):
        def __init__(self, options={}) -> None:
            options.update({"smart": True})
            super().__init__(options=options)
            self.inline_parser = InlineParserEx(options=options)
            self.block_starts = BlockStartsEx()

    ParserEx.blocks = {"math_block": MathBlock}  # type:ignore
    ParserEx.blocks.update(Parser.blocks)  # type:ignore

    class HtmlRendererEx(HtmlRenderer):

        def tagd(
            self,
            name: str,
            attrs: dict[str, Any] | None = None,
            selfclosing: bool = False,
        ):
            self.tag(
                name, [(k, v) for k, v in attrs.items()] if attrs else None, selfclosing
            )

        def image(self, node, entering):
            if entering:
                self.tag("figure")
                super().image(node, entering)
            else:
                super().image(node, entering)
                if node.title:
                    self.tag("figcaption")
                    self.lit(self.escape(node.title))
                    self.tag("/figcaption")
                self.tag("/figure")

        def code_block(self, node, entering):
            lexer = (
                get_lexer_by_name(node.info) if node.info else guess_lexer(node.literal)
            )
            self.cr()
            self.lit(highlight(node.literal, lexer, HtmlFormatter(style=HTML_FORMATTER_STYLE)))
            self.cr()

        def math(self, node, entering):
            self.tagd("span", {"class": "inline-math"})
            self.lit(temml(node.literal, {"displayMode": False}))
            self.tag("/span")

        def sidenote(self, node, entering):
            self.tagd("span", {"class": "sidenote"})
            self.tagd("span", {"class": "sidenote_content"})
            self.lit(self.escape(unescape_html(node.literal)))
            self.tag("/span")
            self.tag("/span")

        def math_block(self, node, entering):
            self.cr()
            self.tagd("div", {"class": "block-math"})
            self.lit(temml(node.literal, {"displayMode": True}))
            self.tag("/div")
            self.cr()

    def renderer(markdown: str) -> str:
        ast = renderer.__parser.parse(markdown)
        return renderer.__html.render(ast)

    renderer.__parser = ParserEx({})
    renderer.__html = HtmlRendererEx({})

    return renderer


def get_stylesheet() -> str:
    try:
        result = get_stylesheet.__cached
    except:
        from pygments.formatters import HtmlFormatter

        result = get_stylesheet.__cached = HtmlFormatter(style=HTML_FORMATTER_STYLE).get_style_defs()
    return result
