"""Compiled regex patterns shared between parser and highlighter."""

import re

# Wikilinks: [[target]] or [[target|alias]]
WIKILINK = re.compile(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')

# Tags: #tag or #parent/child (not preceded by &, word char, or inside code)
TAG = re.compile(r'(?<!\w)#([\w][\w/-]*)')

# Markdown headings
HEADING = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

# Bold: **text** or __text__
BOLD = re.compile(r'(\*\*|__)(.+?)\1')

# Italic: *text* or _text_ (not bold)
ITALIC = re.compile(r'(?<!\*)(\*)((?!\*).*?)\1(?!\*)|(?<!_)(_)((?!_).*?)\3(?!_)')

# Inline code: `code`
INLINE_CODE = re.compile(r'(`)((?!`).+?)\1')

# Code fence start/end: ``` or ```language
CODE_FENCE = re.compile(r'^(`{3,})(.*)?$', re.MULTILINE)

# Blockquote
BLOCKQUOTE = re.compile(r'^(>\s?)+(.*)$', re.MULTILINE)

# Unordered list
UNORDERED_LIST = re.compile(r'^(\s*)([-*+])\s+(.*)$', re.MULTILINE)

# Ordered list
ORDERED_LIST = re.compile(r'^(\s*)(\d+\.)\s+(.*)$', re.MULTILINE)

# Horizontal rule
HORIZONTAL_RULE = re.compile(r'^(-{3,}|\*{3,}|_{3,})\s*$', re.MULTILINE)

# Markdown links: [text](url)
MD_LINK = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

# Image links: ![alt](path)
IMAGE_LINK = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

# Checklist items: - [ ] or - [x] (also with * or +)
CHECKLIST = re.compile(r'^(\s*[-*+]\s+)\[([ xX])\]\s+', re.MULTILINE)
