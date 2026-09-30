"""生成发布更新内容。手动说明优先，否则按可比较的上一发布汇总真实提交。"""
import argparse
import os
from pathlib import Path
import re
import urllib.parse

from scripts.release_plan import github_api, normalize_version, clean_manual_notes, read_version_notes

MAX_COMMITS = 200


def escape_title(value):
    # 提交标题是数据，防止标题中的 Markdown/HTML 变成发布页链接或标题。
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("@", "&#64;")
    return re.sub(r"([\\`*_{}\[\]()#+!|~])", r"\\\1", value)


def commit_lines(commits, repository):
    lines, seen = [], set()
    for item in commits:
        sha = item.get("sha", "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha) or sha in seen:
            continue
        seen.add(sha)
        subject = item.get("commit", {}).get("message", "").splitlines()
        title = (subject[0].strip() if subject else "") or "未提供提交标题"
        if len(title) > 300:
            title = title[:300] + "…"
        lines.append(f"- {escape_title(title)} ([{sha[:7]}](https://github.com/{repository}/commit/{sha}))")
    return lines


def published_releases(repository, api):
    releases = []
    for page in range(1, 21):
        batch = api(f"repos/{repository}/releases?per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError("无法读取历史发布，已停止生成更新说明")
        releases.extend(item for item in batch if not item.get("draft") and item.get("published_at") and item.get("tag_name"))
        if len(batch) < 100:
            return sorted(releases, key=lambda item: item["published_at"], reverse=True)
    raise ValueError("历史发布过多，请手动填写本次更新说明")


def automatic_changes(repository, tag, sha, api):
    history = published_releases(repository, api)
    for release in history:
        previous = release["tag_name"]
        if previous == tag or ("-" not in tag and release.get("prerelease")):
            continue
        base = urllib.parse.quote(previous, safe="")
        endpoint = f"repos/{repository}/compare/{base}...{sha}"
        comparison = api(endpoint+"?per_page=100&page=1")
        if comparison is None:
            continue  # 历史标签可能已删除。
        status = comparison.get("status")
        if status in ("behind", "diverged"):
            continue  # 不把其他发布分支的差异当成本次变更。
        if status not in ("ahead", "identical"):
            raise ValueError("GitHub 返回了无法识别的版本比较结果")
        link = f"[完整变更](https://github.com/{repository}/compare/{base}...{sha})"
        heading = f"相较于 **{escape_title(previous)}**："
        if status == "identical":
            return f"{heading}\n\n与上一版本使用相同源码提交，没有新增代码提交。\n\n{link}"
        commits = list(comparison.get("commits", []))
        total = comparison.get("total_commits", len(commits))
        page = 2
        while len(commits) < min(total, MAX_COMMITS):
            more = api(endpoint+f"?per_page=100&page={page}")
            batch = more.get("commits", []) if more else []
            if not batch:
                raise ValueError("版本提交列表不完整，请重试或手动填写更新说明")
            commits.extend(batch)
            page += 1
        lines = commit_lines(commits[:MAX_COMMITS], repository)
        if not lines:
            raise ValueError("本次版本存在差异，但未取得可用提交记录")
        suffix = f"\n\n提交较多，仅展示前 {MAX_COMMITS} 条。" if total > MAX_COMMITS else ""
        return heading+"\n\n"+"\n".join(lines)+suffix+"\n\n"+link

    # 首次发布，或历史发布不属于当前提交的历史：展示当前提交历史并明确说明。
    commits = []
    for page in range(1, 3):
        batch = api(f"repos/{repository}/commits?sha={sha}&per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError("无法读取首次发布的提交记录")
        commits.extend(batch)
        if len(batch) < 100:
            break
    lines = commit_lines(commits[:MAX_COMMITS], repository)
    if not lines:
        raise ValueError("未取得可用的提交记录")
    heading = "首次发布，以下根据提交记录自动生成：" if not history else "没有找到可比较的历史发布，以下列出当前提交历史："
    suffix = f"\n\n最多展示 {MAX_COMMITS} 条提交。" if len(commits) >= MAX_COMMITS else ""
    return heading+"\n\n"+"\n".join(lines)+suffix+f"\n\n[提交历史](https://github.com/{repository}/commits/{sha})"


def build_release_notes(repository, tag, sha, manual_notes="", api=github_api, installation_path=".github/RELEASE_NOTES.md", notes_directory="release-notes"):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("仓库或构建提交无效")
    if tag != "v"+normalize_version(tag):
        raise ValueError("版本标签无效")
    manual = clean_manual_notes(manual_notes) or read_version_notes(tag, notes_directory)
    changes = manual or automatic_changes(repository, tag, sha, api)
    installation = Path(installation_path).read_text(encoding="utf-8").strip()
    return ("## 更新内容\n\n"+changes+
            f"\n\n构建提交：[{sha[:7]}](https://github.com/{repository}/commit/{sha})\n\n---\n\n"+
            installation+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="release-notes-preview.md")
    args = parser.parse_args()
    tag = os.environ.get("RELEASE_TAG") or "v"+normalize_version(os.environ["APP_VERSION"])
    text = build_release_notes(os.environ["GITHUB_REPOSITORY"], tag, os.environ["GITHUB_SHA"],
                               os.environ.get("UPDATE_NOTES", ""))
    Path(args.output).write_text(text, encoding="utf-8")
    print("Release notes preview generated")
