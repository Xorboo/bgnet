#!/usr/bin/env python3
"""Checks for the markdown preprocessing in mkepub.py.

Run it with:

    python tools/test_mkepub.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mkepub import SRC, preprocess  # noqa: E402


def test_link_macros():
    out = preprocess("See [fl[the site|https://example.com]] now.")
    assert out == "See [the site](https://example.com) now.", out
    assert preprocess("[flrfc[RFC 793|793]]") == \
        "[RFC 793](https://tools.ietf.org/html/rfc793)"
    assert preprocess("[flx[server.c|server.c]]") == \
        "[server.c](https://beej.us/guide/bgnet/examples/server.c)"
    assert preprocess("[flw[ELIZA|ELIZA]]") == \
        "[ELIZA](https://en.wikipedia.org/wiki/ELIZA)"


def test_index_and_hyphenation_macros_go_away():
    assert preprocess("a [i[Blocking]] b") == "a  b"
    assert preprocess("a [i[Blocking]<] b") == "a  b"
    assert preprocess("a [i[`send()` function]i] b") == "a  b"
    assert preprocess("a [i[`sigaction()`\nfunction]] b") == "a  b"
    assert preprocess("say [nh[getaddrinfo]] loud") == "say getaddrinfo loud"


def test_misplaced_bracket_is_reported():
    # This is how bgnet_part_0500_syscalls.md:315 read before the fix. The
    # brackets close one word early. preprocess() must say so rather than
    # match on to the next "]]" and drop the prose in between.
    broken = "a [i[`connect()`] function] b and [i[Port]] c"
    try:
        preprocess(broken)
    except SystemExit as e:
        assert "unhandled macro" in str(e), e
    else:
        raise AssertionError("a misplaced bracket went unreported")


def test_page_breaks_and_image_type():
    assert preprocess("[[manbreak]]") == '<div class="pagebreak"></div>'
    assert preprocess("![Cs.](cs.pdf)") == "![Cs.](cs.png)"


def test_code_block_puts_every_line_in_its_own_element():
    out = preprocess("```{.c}\nint a;\n  b < c;\n```")
    assert '<pre class="code">' in out, out
    assert '<span class="cl">int a;</span>' in out, out
    # Indentation is kept and the angle bracket is escaped.
    assert '<span class="cl">  b &lt; c;</span>' in out, out


def test_indented_fences_stay_markdown():
    # These sit inside list items, where raw HTML would confuse the parser.
    out = preprocess("1. Item:\n\n   ```{.c}\n   int a;\n   ```\n")
    assert "<pre" not in out, out


def test_whole_source_leaves_no_macros():
    parts = sorted(SRC.glob("bgnet_part_*.md"))
    assert parts, "no source markdown found"
    for part in parts:
        # preprocess() itself exits on any macro form it does not know.
        out = preprocess(part.read_text(encoding="utf-8"))
        assert "[i[" not in out, part
        assert "]i]" not in out, part


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all checks passed")
