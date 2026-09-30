"""汇总通过测试的双平台产物；校验完整后才能进入发布步骤。"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import zipfile

ASSETS = ("MouseActionAssistant-windows-x64-setup.exe", "MouseActionAssistant-macos-arm64.zip",
          "MouseActionAssistant-macos-arm64.dmg")
VERSION = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?\Z")


def build_version(ref_type, ref_name, sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("构建提交必须是完整 Git SHA")
    if ref_type == "tag":
        if not VERSION.fullmatch(ref_name):
            raise ValueError("版本标签需为 v1.0.0 或 v1.0.0-rc.1 这类格式")
        return ref_name
    return "snapshot-" + sha[:12]


def prepare(source, output, ref_type, ref_name, sha, run_url):
    source, output = Path(source), Path(output)
    version = build_version(ref_type, ref_name, sha)
    # 先检查全部产物，防止只发布一个平台或不完整文件。
    for name in ASSETS:
        path = source/name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"缺少构建产物：{name}")
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                if not archive.namelist() or archive.testzip() is not None:
                    raise ValueError(f"ZIP 校验失败：{name}")
        if path.suffix == ".exe":
            with path.open("rb") as handle:
                header = handle.read(64)
                if len(header) < 64 or header[:2] != b"MZ":
                    raise ValueError(f"无效的 Windows 安装程序：{name}")
                handle.seek(int.from_bytes(header[60:64], "little"))
                if handle.read(4) != b"PE\x00\x00":
                    raise ValueError(f"无效的 PE 可执行文件：{name}")
    output.mkdir(parents=True, exist_ok=False)
    for name in ASSETS:
        destination = name.replace("MouseActionAssistant-", "MouseActionAssistant-"+version+"-", 1)
        shutil.copy2(source/name, output/destination)
    (output/"build-info.json").write_text(json.dumps({"version": version, "commit": sha, "workflow_run": run_url},
                                                   ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    checksums = []
    for path in sorted(output.iterdir()):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024*1024), b""):
                digest.update(block)
        checksums.append(f"{digest.hexdigest()}  {path.name}")
    (output/"SHA256SUMS.txt").write_text("\n".join(checksums)+"\n", encoding="utf-8")
    return version


if __name__ == "__main__":
    version = prepare("downloaded", "release-assets", os.environ["GITHUB_REF_TYPE"],
                      os.environ["GITHUB_REF_NAME"], os.environ["GITHUB_SHA"],
                      f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}")
    print(f"Release assets prepared: {version}")
