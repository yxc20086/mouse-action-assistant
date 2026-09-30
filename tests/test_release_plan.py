import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
import zipfile

from scripts.release_plan import resolve_plan, check_remote, normalize_version
from scripts.release_assets import ASSETS, prepare
from scripts.publish_release import publish, verify_bundle

SHA = "a"*40
REPO = "example/mouse-assistant"


class ReleasePlanTests(unittest.TestCase):
    def test_manual_publish_uses_input_not_version_file(self):
        plan = resolve_plan("workflow_dispatch", "branch", "main", "v1.0.3", True, "1.0.2", SHA)
        self.assertEqual(plan["app_version"], "1.0.3")
        self.assertEqual(plan["tag"], "v1.0.3")
        self.assertEqual(plan["publish"], "true")
        self.assertEqual(plan["create_tag"], "true")

    def test_manual_build_never_publishes_even_on_tag(self):
        for ref_type, ref in (("branch", "main"), ("tag", "v1.0.3")):
            plan = resolve_plan("workflow_dispatch", ref_type, ref, "", False, "1.0.2", SHA)
            self.assertEqual(plan["publish"], "false")
            api = Mock()
            check_remote(plan, REPO, api)
            api.assert_not_called()

    def test_tag_push_still_publishes(self):
        plan = resolve_plan("push", "tag", "v1.0.3", "", False, "1.0.2", SHA)
        self.assertEqual(plan["app_version"], "1.0.3")
        self.assertEqual(plan["publish"], "true")
        self.assertEqual(plan["create_tag"], "false")

    def test_missing_and_invalid_input_rejected(self):
        for version in ("", "1.0", "1.0.3;echo x", "../../bad", "65536.0.0"):
            with self.assertRaises(ValueError):
                resolve_plan("workflow_dispatch", "branch", "main", version, True, "1.0.2", SHA)
        with self.assertRaises(ValueError):
            resolve_plan("workflow_dispatch", "tag", "v1.0.3", "1.0.4", True, "1.0.2", SHA)

    def test_existing_tag_or_release_rejected(self):
        plan = resolve_plan("workflow_dispatch", "branch", "main", "1.0.3", True, "1.0.2", SHA)
        for responses in ([{"id": 1}], [None, {"ref": "refs/tags/v1.0.3"}]):
            with self.assertRaises(ValueError): check_remote(plan, REPO, Mock(side_effect=responses))

    def test_api_error_is_not_treated_as_available_version(self):
        plan = resolve_plan("workflow_dispatch", "branch", "main", "1.0.3", True, "1.0.2", SHA)
        with self.assertRaises(RuntimeError):
            check_remote(plan, REPO, Mock(side_effect=RuntimeError("HTTP 403")))


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name in ASSETS:
            path = root/name
            if path.suffix == ".zip":
                with zipfile.ZipFile(path, "w") as archive: archive.writestr("test", "data")
            elif path.suffix == ".exe":
                path.write_bytes(b"MZ"+b"\x00"*58+(64).to_bytes(4, "little")+b"PE\x00\x00")
            else: path.write_bytes(b"dmg-test-fixture")
        self.output = root/"assets"
        prepare(root, self.output, "tag", "v1.0.3", SHA, "https://example.test/run", "1.0.3")
        self.plan = resolve_plan("workflow_dispatch", "branch", "main", "1.0.3", True, "1.0.2", SHA)

    def test_create_tag_only_after_validated_bundle(self):
        api = Mock(side_effect=[None, None, {"ref":"refs/tags/v1.0.3"}, {"sha":SHA}])
        run = Mock()
        publish(self.output, self.plan, REPO, api, run, release_notes="测试更新")
        api.assert_any_call(f"repos/{REPO}/git/refs", method="POST", data={"ref":"refs/tags/v1.0.3", "sha":SHA})
        args = run.call_args.args[0]
        self.assertIn("--verify-tag", args)
        self.assertNotIn("--clobber", args)
        self.assertIn("v1.0.3", args)

    def test_bad_hash_cannot_create_tag(self):
        target = next(self.output.glob("*.exe")); target.write_bytes(b"tampered")
        api, run = Mock(), Mock()
        with self.assertRaises(ValueError): publish(self.output, self.plan, REPO, api, run, release_notes="测试更新")
        api.assert_not_called(); run.assert_not_called()

    def test_wrong_commit_and_version_rejected(self):
        with self.assertRaises(ValueError): verify_bundle(self.output, "v1.0.3", "b"*40)
        with self.assertRaises(ValueError): verify_bundle(self.output, "v1.0.4", SHA)

    def test_unchecked_publish_has_no_external_writes(self):
        self.plan["publish"] = "false"
        api, run = Mock(), Mock()
        with self.assertRaises(ValueError): publish(self.output, self.plan, REPO, api, run, release_notes="测试更新")
        api.assert_not_called(); run.assert_not_called()

    def test_concurrent_tag_creation_cannot_be_overwritten(self):
        api = Mock(side_effect=[None, None, RuntimeError("already exists")]); run = Mock()
        with self.assertRaises(RuntimeError): publish(self.output, self.plan, REPO, api, run, release_notes="测试更新")
        run.assert_not_called()

    def test_pushed_tag_does_not_create_another_tag(self):
        self.plan["create_tag"] = "false"
        api = Mock(side_effect=[None, {"sha":SHA}, {"sha":SHA}]); run = Mock()
        publish(self.output, self.plan, REPO, api, run, release_notes="测试更新")
        self.assertTrue(all("method" not in call.kwargs for call in api.call_args_list))
        run.assert_called_once()

    def test_changed_tag_prevents_release(self):
        api = Mock(side_effect=[None, None, {}, {"sha":"b"*40}]); run = Mock()
        with self.assertRaises(ValueError): publish(self.output, self.plan, REPO, api, run, release_notes="测试更新")
        run.assert_not_called()

    def test_release_uses_generated_notes_file(self):
        api = Mock(side_effect=[None, None, {}, {"sha":SHA}])
        content = []
        def run(args, **kwargs):
            content.append(Path(args[args.index("--notes-file")+1]).read_text(encoding="utf-8"))
        publish(self.output, self.plan, REPO, api, run, release_notes="新增用户填写的更新说明")
        self.assertIn("## 更新内容\n\n新增用户填写的更新说明", content[0])
        self.assertIn("## 下载与安装", content[0])

    def test_notes_failure_happens_before_tag_creation(self):
        api = Mock(side_effect=[None, None, RuntimeError("history unavailable")]); run = Mock()
        with self.assertRaises(RuntimeError): publish(self.output, self.plan, REPO, api, run)
        self.assertFalse(any(call.kwargs.get("method") == "POST" for call in api.call_args_list))
        run.assert_not_called()
