# -*- coding: utf-8 -*-
"""Разбивает RELEASES.md на отдельные файлы заметок: release-notes/<версия>.md.

gh release edit --notes-file берёт файл целиком, поэтому каждой версии нужен
свой файл, иначе в релиз 1.1.0 попадают заметки 1.2.0.
"""

import re
from pathlib import Path

root = Path(__file__).resolve().parent.parent
text = (root / "RELEASES.md").read_text(encoding="utf-8")

parts = re.split(r"(?m)^## MicToggle ", text)
chunks = parts[1:]
out = root / "release-notes"
out.mkdir(exist_ok=True)

for chunk in chunks:
    version = chunk.split(None, 1)[0].strip()
    body = "## MicToggle " + chunk
    if not body.endswith("\n"):
        body += "\n"
    (out / f"{version}.md").write_text(body.rstrip() + "\n", encoding="utf-8")
    print(version, len(body), "символов")