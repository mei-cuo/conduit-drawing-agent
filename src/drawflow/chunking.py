"""Heading-aware parent chunks and overlapping recursive child chunks."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_markdown(path: Path, source: str, child_size=420, overlap=80):
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    headings = []
    content = []
    sections = []
    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if match:
            if content:
                sections.append((" / ".join(headings) or path.stem, "\n".join(content)))
            depth = len(match[1])
            headings = headings[: depth - 1] + [match[2]]
            content = [line]
        else:
            content.append(line)
    if content:
        sections.append((" / ".join(headings) or path.stem, "\n".join(content)))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=child_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )
    output = []
    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1800, chunk_overlap=0, separators=["\n\n", "\n", "。", " ", ""]
    )
    sections = [
        (heading, part) for heading, body in sections for part in parent_splitter.split_text(body)
    ]
    for ordinal, (heading, body) in enumerate(sections):
        if not body.strip():
            continue
        parent_id = hashlib.sha256(f"{source}:{ordinal}:{body}".encode()).hexdigest()
        for index, part in enumerate(splitter.split_text(body)):
            chunk_id = hashlib.sha256(f"{parent_id}:{index}:{part}".encode()).hexdigest()
            output.append(
                dict(
                    id=chunk_id,
                    source=source,
                    heading=heading,
                    text=part,
                    parent_id=parent_id,
                    parent_text=body,
                    content_hash=hashlib.sha256(text.encode()).hexdigest(),
                    child_index=index,
                )
            )
    return output
