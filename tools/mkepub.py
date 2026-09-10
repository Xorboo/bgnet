#!/usr/bin/env python3
"""Build an e-ink friendly EPUB of Beej's Guide from the markdown source.

Needs Python 3, Calibre's ebook-convert, and Chrome or Edge to draw the two
diagrams. Each is found on PATH or in its usual install directory. Run it
from anywhere:

    python tools/mkepub.py

The EPUB lands in stage/bgnet.epub.
"""

import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
BUILD = ROOT / "stage" / "epub-build"
OUT = ROOT / "stage" / "bgnet.epub"

# Pulled from src/Makefile.
META = {
    "title": "Beej's Guide to Network Programming",
    "authors": "Brian \u201cBeej Jorgensen\u201d Hall",
    "comments": "Using Internet Sockets",
}

# Beej's markdown extensions. See src/README.md for the definitions.
LINK_PREFIX = {
    "fl": "",
    "flx": "https://beej.us/guide/bgnet/examples/",
    "flr": "https://beej.us/guide/url/",
    "flrfc": "https://tools.ietf.org/html/rfc",
    "flw": "https://en.wikipedia.org/wiki/",
    "flm": "https://man7.org/linux/man-pages/man3/",
}

# Link and hyphenation macros: the body is on one line and holds no "]".
MACRO = re.compile(r"\[(fl|flx|flr|flrfc|flw|flm|nh)\[([^\]]*)\]\]")
# Index macros. The body can wrap across lines but never holds a bracket, and
# the flags after it are only ibIBT<>. Both limits matter: a macro with a
# misplaced bracket then fails to match, and the check in preprocess() reports
# it. A looser pattern would instead run on to the next "]]" and silently eat
# the prose in between.
INDEX = re.compile(r"\[i\[[^\[\]]+\][ibIBT<>]*\]", re.DOTALL)
# Anything left over means a macro form this script does not know about.
LEFTOVER = re.compile(r"\[(?:fl|flx|flr|flrfc|flw|flm|nh|i)\[")
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
MANBREAK = re.compile(r"^\[\[manbreak\]\]\s*$", re.MULTILINE)
PAGEBREAK = re.compile(r"^\[\[pagebreak\]\]\s*$", re.MULTILINE)
IMAGE_PDF = re.compile(r"(!\[[^\]]*\]\([^)]+?)\.pdf(\s|\))")
# Top-level fenced code blocks. Indented fences sit inside list items, where
# raw HTML confuses the markdown parser, so leave those to the parser.
FENCE = re.compile(r"^```[^\n]*\n(.*?)^```[ \t]*$", re.DOTALL | re.MULTILINE)

PAGEBREAK_HTML = '<div class="pagebreak"></div>'


def code_block(match):
    """Emit a code block whose lines each sit in their own element.

    A 6-inch screen cannot hold a 72-character source line, so about a fifth
    of them wrap. One element per line lets the stylesheet indent the wrapped
    remainder, which shows the reader where a line continues.
    """
    lines = match.group(1).split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    body = "".join(
        '<span class="cl">%s</span>\n' % html.escape(ln or " ") for ln in lines)
    return '\n<pre class="code">%s</pre>\n' % body


def expand(match):
    """Turn one Beej link or hyphenation macro into plain markdown."""
    kind, body = match.group(1), match.group(2)
    if kind == "nh":
        return body  # Hyphenation hints are for LaTeX only.
    text, _, target = body.partition("|")
    if kind == "flm":
        target = target + ".3.html"
    return "[%s](%s%s)" % (text, LINK_PREFIX[kind], target)


def preprocess(text):
    text = COMMENT.sub("", text)
    text = MANBREAK.sub(PAGEBREAK_HTML, text)
    text = PAGEBREAK.sub(PAGEBREAK_HTML, text)
    text = INDEX.sub("", text)  # Index entries have no meaning in an EPUB.
    text = MACRO.sub(expand, text)
    left = LEFTOVER.search(text)
    if left:
        raise SystemExit("unhandled macro at %r" % text[left.start():left.start() + 60])
    # The source points at the print-ready PDF diagrams. Kindle readers do not
    # show SVG, so the build uses PNG copies of the same drawings.
    text = IMAGE_PDF.sub(r"\1.png\2", text)
    text = FENCE.sub(code_block, text)
    return text


def find_tool(name, *guesses):
    found = shutil.which(name)
    if found:
        return found
    for guess in guesses:
        if Path(guess).exists():
            return guess
    return None


def find_ebook_convert():
    found = find_tool(
        "ebook-convert", r"C:\Program Files\Calibre2\ebook-convert.exe")
    if not found:
        sys.exit("ebook-convert not found. Install Calibre or put it on PATH.")
    return found


def find_browser():
    return find_tool(
        "chrome",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    )


SVG_SIZE = re.compile(r'\b(width|height)="([0-9.]+)[a-z]*"')

# The diagrams are as wide as a Kindle Oasis screen, so they stay sharp.
DIAGRAM_WIDTH = 1264


def rasterize(browser, svg, png):
    """Draw an SVG into a PNG with headless Chrome.

    Calibre's own SVG renderer fills these Inkscape drawings solid black, and
    the SVGs carry no viewBox, so a plain screenshot ignores any size given to
    the root element. Wrapping the file in an <img> makes it scale properly.
    """
    dims = dict(SVG_SIZE.findall(svg.read_text(encoding="utf-8")))
    ratio = float(dims["height"]) / float(dims["width"])
    height = max(1, round(DIAGRAM_WIDTH * ratio))
    wrapper = png.with_suffix(".wrap.html")
    wrapper.write_text(
        "<style>html,body{margin:0;padding:0;background:#fff}"
        "img{display:block;width:%dpx}</style>"
        '<img src="%s">' % (DIAGRAM_WIDTH, svg.resolve().as_uri()),
        encoding="utf-8")
    subprocess.run([
        browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--default-background-color=FFFFFFFF",
        "--window-size=%d,%d" % (DIAGRAM_WIDTH, height),
        "--screenshot=%s" % png.resolve(),
        str(wrapper.resolve()),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wrapper.unlink()
    if not png.exists():
        sys.exit("failed to draw %s" % svg)


# E-ink readability notes. Source code lines go up to 72 characters, so the
# monospace size is set to fit that many on a 6-inch screen at a normal body
# font size. Anything longer wraps instead of clipping. Body text is flush
# left because justifying prose this full of inline code opens ugly gaps.
CSS = """
body { font-family: serif; line-height: 1.5; text-align: left;
       margin: 0 0.3em; }
h1 { font-size: 1.5em; page-break-before: always; text-align: left;
     margin: 0 0 1em 0; }
h2 { font-size: 1.2em; text-align: left; page-break-after: avoid; }
h3, h4 { font-size: 1.05em; text-align: left; page-break-after: avoid; }
p { margin: 0.6em 0; widows: 2; orphans: 2; }
pre { font-family: monospace; font-size: 0.72em; line-height: 1.25;
      white-space: normal; word-wrap: break-word; text-align: left;
      margin: 1em 0; padding: 0.3em 0.4em; border-left: 2px solid #999; }
span.cl { display: block; padding-left: 1.4em; text-indent: -1.4em;
          white-space: pre-wrap; word-wrap: break-word; }
code { font-family: monospace; font-size: 0.88em; word-wrap: break-word;
       hyphens: none; }
pre code { font-size: 1em; }
table { font-size: 0.72em; width: 100%; border-collapse: collapse;
        margin: 1em 0; }
th, td { text-align: left; vertical-align: top; padding: 0.2em 0.3em;
         border-bottom: 1px solid #ccc; word-wrap: break-word; }
img { max-width: 100%; }
blockquote { margin: 1em 1.2em; font-style: italic; }
ul, ol { padding-left: 1.3em; margin: 0.6em 0; }
li { margin: 0.2em 0; }
/* Links keep the body colour. Grey text on a grey screen reads badly, and
   this guide puts cross-references in the middle of sentences. */
a { text-decoration: none; color: inherit; }
div.pagebreak { page-break-before: always; }
.footnote { font-size: 0.85em; }
"""


def main():
    parts = sorted(SRC.glob("bgnet_part_*.md"))
    if not parts:
        sys.exit("No source markdown found in %s" % SRC)

    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)

    combined = "\n\n".join(preprocess(p.read_text(encoding="utf-8")) for p in parts)
    md_path = BUILD / "bgnet.md"
    md_path.write_text(combined, encoding="utf-8")

    browser = find_browser()
    if not browser:
        sys.exit("Chrome or Edge not found. One of them draws the diagrams.")
    for svg in SRC.glob("*.svg"):
        rasterize(browser, svg, BUILD / (svg.stem + ".png"))

    css_path = BUILD / "eink.css"
    css_path.write_text(CSS, encoding="utf-8")

    cover = ROOT / "website" / "bgnetcover.png"

    cmd = [
        find_ebook_convert(), str(md_path), str(OUT),
        "--markdown-extensions", "extra,smarty,sane_lists",
        "--extra-css", str(css_path),
        "--chapter", "//h:h1",
        "--chapter-mark", "pagebreak",
        "--level1-toc", "//h:h1",
        "--level2-toc", "//h:h2",
        "--toc-title", "Contents",
        "--epub-inline-toc",
        "--page-breaks-before", "/",
        "--disable-font-rescaling",
        "--title", META["title"],
        "--authors", META["authors"],
        "--comments", META["comments"],
        "--language", "en",
    ]
    if cover.exists():
        cmd += ["--cover", str(cover)]

    print("Building %s" % OUT)
    subprocess.run(cmd, check=True)
    print("Done: %s (%.1f KB)" % (OUT, OUT.stat().st_size / 1024))


if __name__ == "__main__":
    main()
