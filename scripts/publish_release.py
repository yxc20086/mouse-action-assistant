"""只发布本次已验证的提交和文件；新标签在构建成功后创建。"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.parse

from scripts.release_assets import ASSETS
from scripts.release_plan import check_remote, github_api, normalize_version
from scripts.release_notes import build_release_notes


def verify_bundle(directory, tag, sha):
    directory = Path(directory)
    version = normalize_version(tag)
    if tag != "v"+version or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("发布版本或提交无效")
    names = {name.replace("MouseActionAssistant-", "MouseActionAssistant-"+tag+"-", 1) for name in ASSETS}
    names.add("build-info.json")
    if {p.name for p in directory.iterdir()} != names | {"SHA256SUMS.txt"}:
        raise ValueError("发布附件不齐全或存在额外文件")
    info = json.loads((directory/"build-info.json").read_text(encoding="utf-8"))
    if info.get("version") != tag or info.get("commit") != sha or info.get("app_version") != version:
        raise ValueError("附件版本或提交与发布计划不一致")
    hashes = {}
    for line in (directory/"SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if name not in names or name in hashes or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("校验清单无效")
        hashes[name] = digest
    if set(hashes) != names:
        raise ValueError("校验清单不完整")
    for name, expected in hashes.items():
        path = directory/name
        if path.is_symlink() or not path.is_file():
            raise ValueError("发布附件必须是普通文件")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024*1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError(f"附件校验失败：{name}")
    return [directory/name for name in sorted(names | {"SHA256SUMS.txt"})]


def publish(directory, plan, repository, api=github_api, run=subprocess.run, release_notes=""):
    if plan["publish"] != "true":
        raise ValueError("未勾选发布，禁止创建 Release")
    files = verify_bundle(directory, plan["tag"], plan["sha"])
    check_remote(plan, repository, api)
    tag = plan["tag"]
    # 先完成说明生成，API 读取失败时不提前占用版本标签。
    notes = build_release_notes(repository, tag, plan["sha"], release_notes, api)
    if plan["create_tag"] == "true":
        # Git refs API 会拒绝已存在的标签，不能覆盖并发创建的版本。
        api(f"repos/{repository}/git/refs", method="POST",
            data={"ref": "refs/tags/"+tag, "sha": plan["sha"]})
    commit = api(f"repos/{repository}/commits/{urllib.parse.quote(tag, safe='')}")
    if not commit or commit.get("sha") != plan["sha"]:
        raise ValueError("发布前标签发生变化，已停止")
    with tempfile.TemporaryDirectory(prefix="mouse-release-notes-") as temporary:
        notes_file = Path(temporary)/"release-notes.md"
        notes_file.write_text(notes, encoding="utf-8")
        args = ["gh", "release", "create", tag, *map(str, files), "--repo", repository,
                "--verify-tag", "--title", "鼠标动作助手 "+tag, "--notes-file", str(notes_file)]
        if "-" in tag:
            args.extend(["--prerelease", "--latest=false"])
        run(args, check=True)


if __name__ == "__main__":
    publish("release-assets", {"tag": os.environ["RELEASE_TAG"], "sha": os.environ["RELEASE_SHA"],
                              "publish": os.environ["DO_PUBLISH"], "create_tag": os.environ["CREATE_TAG"]},
            os.environ["GITHUB_REPOSITORY"], release_notes=os.environ.get("UPDATE_NOTES", ""))
