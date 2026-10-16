"""A tiny document model with two serialisers.

Screens are built once as blocks, then serialised either as a Bot API 10.1 Rich
Message (``<h1>``, ``<p>``, ``<blockquote>``) or as a classic HTML message
(``parse_mode=HTML``). The transport (:mod:`bot.ui`) picks one and falls back to
classic if Telegram refuses the rich form.

Every string put into a block is already HTML: escape dynamic text with :func:`esc`.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


@dataclass(frozen=True, slots=True)
class Heading:
    text: str
    level: int = 1


@dataclass(frozen=True, slots=True)
class Para:
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Quote:
    lines: tuple[str, ...]
    expandable: bool = False


@dataclass
class Doc:
    blocks: list[Heading | Para | Quote] = field(default_factory=list)

    def h(self, text: str, level: int = 1) -> Doc:
        self.blocks.append(Heading(text, level))
        return self

    def p(self, *lines: str) -> Doc:
        kept = tuple(line for line in lines if line is not None)
        if kept:
            self.blocks.append(Para(kept))
        return self

    def quote(self, *lines: str, expandable: bool = False) -> Doc:
        kept = tuple(line for line in lines if line)
        if kept:
            self.blocks.append(Quote(kept, expandable))
        return self

    def extend(self, other: Doc) -> Doc:
        self.blocks.extend(other.blocks)
        return self

    # ── serialisers ────────────────────────────────────────────────────────

    def classic(self) -> str:
        parts: list[str] = []
        for block in self.blocks:
            if isinstance(block, Heading):
                parts.append(f"<b>{block.text}</b>" if block.level <= 2 else f"<b><i>{block.text}</i></b>")
            elif isinstance(block, Para):
                parts.append("\n".join(block.lines))
            else:
                tag = "blockquote expandable" if block.expandable else "blockquote"
                parts.append(f"<{tag}>" + "\n".join(block.lines) + "</blockquote>")
        return "\n\n".join(parts).strip() or "…"

    def rich(self) -> str:
        parts: list[str] = []
        for block in self.blocks:
            if isinstance(block, Heading):
                level = min(max(block.level, 1), 6)
                parts.append(f"<h{level}>{block.text}</h{level}>")
            elif isinstance(block, Para):
                parts.append("<p>" + "<br/>".join(block.lines) + "</p>")
            else:
                parts.append("<blockquote>" + "<br/>".join(block.lines) + "</blockquote>")
        return "".join(parts) or "<p>…</p>"
