"""解析网页发版输入，在耗时构建前拒绝非法或已占用的版本。"""
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from scripts.release_assets import VERSION


def normalize_version(value):
    if not isinstance(value, str):
        raise ValueError("版本号必须是文本")
    value = value.strip()
    tag = value if value.startswith("v") else "v" + value
    match = VERSION.fullmatch(tag)
    if not match or any(int(part) > 65535 for part in match.groups()[:3]):
        raise ValueError("请输入 1.0.3 或 1.0.3-rc.1 格式的版本号，每段数字不超过 65535")
    return tag[1:]


def resolve_plan(event, ref_type, ref_name, input_version, input_publish, default_version, sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("缺少有效构建提交")
    if input_publish not in (True, False, "true", "false", ""):
        raise ValueError("发布选项必须是布尔值")
    manual = event == "workflow_dispatch"
    requested = input_publish is True or input_publish == "true"
    tagged_push = event == "push" and ref_type == "tag"
    publish = tagged_push or (manual and requested)
    if manual and requested:
        if ref_type != "branch":
            raise ValueError("网页发布请选择 main 等代码分支，不要选择已存在的标签")
        if not input_version.strip():
            raise ValueError("勾选发布时必须填写新版本号")
    if tagged_push or (ref_type == "tag" and not input_version.strip()):
        value = ref_name
    elif manual and input_version.strip():
        value = input_version
    else:
        value = default_version
    version = normalize_version(value)
    if tagged_push and ref_name != "v"+version:
        raise ValueError("发布标签必须以 v 开头")
    return {"app_version": version, "tag": "v"+version if publish else "",
            "publish": "true" if publish else "false",
            "create_tag": "true" if manual and publish else "false", "sha": sha}


def github_api(endpoint, method="GET", data=None):
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    request = urllib.request.Request(base+"/"+endpoint, method=method,
        data=json.dumps(data).encode("utf-8") if data is not None else None,
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                 "Accept": "application/vnd.github+json", "Content-Type": "application/json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if method == "GET" and error.code == 404:
            return None
        raise RuntimeError(f"GitHub 请求失败（HTTP {error.code}），未执行覆盖操作") from None


def check_remote(plan, repository, api=github_api):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("仓库标识无效")
    if plan["publish"] != "true":
        return
    tag = urllib.parse.quote(plan["tag"], safe="")
    if api(f"repos/{repository}/releases/tags/{tag}") is not None:
        raise ValueError(f"{plan['tag']} 已有 Release，请使用新版本号")
    if plan["create_tag"] == "true":
        if api(f"repos/{repository}/git/ref/tags/{tag}") is not None:
            raise ValueError(f"{plan['tag']} 标签已存在，请使用新版本号")
    else:
        commit = api(f"repos/{repository}/commits/{tag}")
        if not commit or commit.get("sha") != plan["sha"]:
            raise ValueError("标签与本次构建提交不一致，已阻止发布")


def main():
    plan = resolve_plan(os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_REF_TYPE"],
                        os.environ["GITHUB_REF_NAME"], os.environ.get("INPUT_VERSION", ""),
                        os.environ.get("INPUT_PUBLISH", "false"),
                        Path("VERSION").read_text(encoding="utf-8"), os.environ["GITHUB_SHA"])
    check_remote(plan, os.environ["GITHUB_REPOSITORY"])
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        for key, value in plan.items():
            output.write(f"{key}={value}\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write(f"## {'正式发布' if plan['publish'] == 'true' else '仅打包'}\n\n"
                      f"应用版本：{plan['app_version']}\n\n构建提交：{plan['sha']}\n")
    print(json.dumps(plan, ensure_ascii=False))


if __name__ == "__main__":
    main()
