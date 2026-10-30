import pytest

from code_review_assistant.domain.policies.diff_lines import added_line_numbers


def test_added_line_numbers_handles_multiple_hunks() -> None:
    patch = """\
diff --git a/src/example.cs b/src/example.cs
--- a/src/example.cs
+++ b/src/example.cs
@@ -1,3 +1,4 @@
 context
-old
+new
+added
 context
@@ -10,2 +11,2 @@
-old
+new
 context
"""

    assert added_line_numbers(patch) == frozenset({2, 3, 11})


def test_deletion_only_hunk_has_no_added_lines() -> None:
    patch = """\
@@ -4,2 +4,0 @@
-removed one
-removed two
"""

    assert added_line_numbers(patch) == frozenset()


@pytest.mark.parametrize(
    "patch",
    [
        "@@ invalid @@\n+added\n",
        "@@ -1,2 +1,2 @@\n-old\n+new\n",
        "@@ -1,1 +1,1 @@\n context\n+extra\n",
    ],
)
def test_rejects_malformed_or_truncated_hunks(patch: str) -> None:
    with pytest.raises(ValueError):
        added_line_numbers(patch)