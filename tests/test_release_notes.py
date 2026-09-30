from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from scripts.release_notes import build_release_notes, clean_manual_notes, MAX_COMMITS

SHA = "a"*40
REPO = "example/mouse"


def release(tag, date="2026-09-30T01:00:00Z", draft=False, prerelease=False):
    return {"tag_name": tag, "published_at": date, "draft": draft, "prerelease": prerelease}


def commit(number, title):
    return {"sha": f"{number:040x}", "commit": {"message": title}}


class ReleaseNotesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.installation = Path(self.temp.name)/"INSTALL.md"
        self.installation.write_text("## 下载与安装\n\nWindows ZIP / EXE，Mac ZIP / DMG。", encoding="utf-8")

    def build(self, api, manual="", tag="v1.0.4"):
        return build_release_notes(REPO, tag, SHA, manual, api, self.installation)

    def test_manual_notes_precede_installation_and_do_not_fetch_commits(self):
        api = Mock(side_effect=AssertionError("Manual notes should not query history"))
        text = self.build(api, "- 新增删除记录\r\n- 修复点击；字面量 $(echo test)")
        self.assertIn("- 新增删除记录\n- 修复点击；字面量 $(echo test)", text)
        self.assertLess(text.index("## 更新内容"), text.index("## 下载与安装"))
        api.assert_not_called()

    def test_automatic_notes_use_latest_published_release_and_subjects(self):
        api = Mock(side_effect=[
            [release("v1.0.2"), release("v1.0.3", "2026-09-30T02:00:00Z"),
             release("v9.0.0", "2026-09-30T03:00:00Z", draft=True)],
            {"status":"ahead", "total_commits":2,
             "commits":[commit(1, "feat: 新增删除记录\n不展示正文"), commit(2, "fix: 修复点击")]}])
        text = self.build(api)
        self.assertIn("v1.0.3", text)
        self.assertIn("新增删除记录", text)
        self.assertIn("修复点击", text)
        self.assertNotIn("不展示正文", text)
        self.assertIn(f"compare/v1.0.3...{SHA}", text)

    def test_identical_commit_is_not_reported_as_new_changes(self):
        api = Mock(side_effect=[[release("v1.0.3")], {"status":"identical"}])
        self.assertIn("没有新增代码提交", self.build(api))

    def test_first_release_uses_commit_history(self):
        api = Mock(side_effect=[[], [commit(1, "初始化项目")]])
        text = self.build(api)
        self.assertIn("首次发布", text)
        self.assertIn("初始化项目", text)

    def test_diverged_release_is_skipped(self):
        api = Mock(side_effect=[
            [release("v2.0.0", "2026-09-30T03:00:00Z"), release("v1.0.3")],
            {"status":"diverged"},
            {"status":"ahead", "total_commits":1, "commits":[commit(1,"修复")]}])
        text = self.build(api)
        self.assertIn("相较于 **v1.0.3**", text)
        self.assertNotIn("相较于 **v2.0.0**", text)

    def test_stable_release_skips_prereleases(self):
        api = Mock(side_effect=[
            [release("v1.1.0-rc.1", "2026-09-30T03:00:00Z", prerelease=True), release("v1.0.3")],
            {"status":"identical"}])
        self.assertIn("相较于 **v1.0.3**", self.build(api))

    def test_compare_pagination_and_truncation(self):
        api = Mock(side_effect=[[release("v1.0.3")],
            {"status":"ahead", "total_commits":201, "commits":[commit(i+1, f"变更 {i+1}") for i in range(100)]},
            {"commits":[commit(i+1, f"变更 {i+1}") for i in range(100,200)]}])
        text = self.build(api)
        self.assertIn(f"仅展示前 {MAX_COMMITS} 条", text)
        self.assertIn("变更 200", text)
        self.assertTrue(api.call_args.args[0].endswith("page=2"))

    def test_titles_are_literal_not_active_markdown(self):
        api = Mock(side_effect=[[], [commit(1, "[链接](https://example.test) <script>")]])
        text = self.build(api)
        self.assertIn(r"\[链接\]", text)
        self.assertIn("&lt;script&gt;", text)

    def test_api_failure_does_not_silently_publish_empty_changes(self):
        with self.assertRaises(RuntimeError):
            self.build(Mock(side_effect=RuntimeError("GitHub unavailable")))

    def test_note_validation(self):
        self.assertEqual(clean_manual_notes(" \r\n "), "")
        for invalid in ("a\x00b", "x"*10001):
            with self.assertRaises(ValueError): clean_manual_notes(invalid)
