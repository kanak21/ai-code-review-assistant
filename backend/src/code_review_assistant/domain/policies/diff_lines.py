import re

_HUNK_HEADER = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$"
)

_METADATA_PREFIXES = (
    "diff --git ",
    "index ",
    "--- ",
    "+++ ",
    "new file mode ",
    "deleted file mode ",
    "similarity index ",
    "rename from ",
    "rename to ",
    "old mode ",
    "new mode ",
    "Binary files ",
    "GIT binary patch",
)


def added_line_numbers(patch: str) -> frozenset[int]:
    """Return new-file line numbers added by a unified diff."""
    if not isinstance(patch, str):
        raise ValueError("patch must be text")

    added: set[int] = set()
    in_hunk = False
    old_line = 0
    new_line = 0
    old_remaining = 0
    new_remaining = 0

    for line in patch.splitlines():
        if line.startswith("@@"):
            if in_hunk and (old_remaining or new_remaining):
                raise ValueError("incomplete diff hunk")

            match = _HUNK_HEADER.fullmatch(line)
            if match is None:
                raise ValueError("malformed diff hunk header")

            old_line = int(match.group(1))
            old_remaining = int(match.group(2) or 1)
            new_line = int(match.group(3))
            new_remaining = int(match.group(4) or 1)
            in_hunk = old_remaining > 0 or new_remaining > 0
            continue

        if in_hunk:
            if line == r"\ No newline at end of file":
                continue

            if line.startswith(" "):
                if old_remaining == 0 or new_remaining == 0:
                    raise ValueError("diff hunk contains more lines than declared")
                old_line += 1
                new_line += 1
                old_remaining -= 1
                new_remaining -= 1
            elif line.startswith("-"):
                if old_remaining == 0:
                    raise ValueError("diff hunk contains more old lines than declared")
                old_line += 1
                old_remaining -= 1
            elif line.startswith("+"):
                if new_remaining == 0:
                    raise ValueError("diff hunk contains more new lines than declared")
                added.add(new_line)
                new_line += 1
                new_remaining -= 1
            else:
                raise ValueError("malformed diff hunk line")

            if old_remaining == 0 and new_remaining == 0:
                in_hunk = False
            continue

        if line == "" or line == r"\ No newline at end of file":
            continue
        if line.startswith(_METADATA_PREFIXES):
            continue
        raise ValueError("unexpected content outside diff hunk")

    if in_hunk and (old_remaining or new_remaining):
        raise ValueError("incomplete diff hunk")

    return frozenset(added)