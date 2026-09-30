"""录制记录库：每条记录独立、原子写入，不覆盖已有轨迹文件。"""
import copy
import json
import math
import os
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from platform_support import recordings_directory


def validate_events(events):
    if not isinstance(events, list) or not events:
        raise ValueError("文件中没有可用的录制事件")
    previous = -1
    for event in events:
        if not isinstance(event, dict) or event.get("type") not in ("move", "click_down", "click_up", "scroll"):
            raise ValueError("轨迹包含不支持的事件")
        for key in ("time", "x", "y"):
            value = event.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"轨迹的 {key} 必须是有限数值")
        if event["time"] < previous or event["time"] < 0:
            raise ValueError("轨迹时间顺序不正确")
        previous = event["time"]
        if event["type"].startswith("click") and event.get("button", "left") not in ("left", "right", "middle"):
            raise ValueError("不支持的鼠标按键")
        if event["type"] == "scroll":
            for key in ("dx", "dy"):
                value = event.get(key, 0)
                if not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("滚动距离无效")


class RecordStore:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else recordings_directory()
        self.records = {}
        self.warnings = []
        self.lock = threading.RLock()
        if self.directory.exists():
            for path in self.directory.glob("*.json"):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                    validate_events(record["events"])
                    if record["id"] != path.stem:
                        raise ValueError("记录标识不匹配")
                    if not isinstance(record.get("name"), str) or not isinstance(record.get("created_at"), str):
                        raise ValueError("记录名称或时间无效")
                    record.setdefault("diagnostics", {})
                    record["saved"] = True
                    self.records[record["id"]] = record
                except Exception as error:
                    self.warnings.append(f"未加载 {path.name}：{error}（原文件保留）")

    def add(self, events, diagnostics=None, name=None):
        validate_events(events)
        now = datetime.now().astimezone()
        record = {"id": uuid.uuid4().hex, "name": name or ("录制 " + now.strftime("%m-%d %H:%M:%S")),
                  "created_at": now.isoformat(), "events": copy.deepcopy(events),
                  "diagnostics": copy.deepcopy(diagnostics or {}), "saved": False}
        with self.lock:
            self.records[record["id"]] = record
            temporary = None
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                                                 prefix=".record-", suffix=".tmp", delete=False) as handle:
                    temporary = Path(handle.name)
                    json.dump(record, handle, ensure_ascii=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.directory / (record["id"] + ".json"))
                record["saved"] = True
            except OSError as error:
                record["save_error"] = str(error)
            finally:
                if temporary and temporary.exists():
                    temporary.unlink()
        return self.get(record["id"])

    def get(self, record_id):
        with self.lock:
            if record_id not in self.records:
                raise ValueError("录制记录不存在")
            return copy.deepcopy(self.records[record_id])

    def rename(self, record_id, name):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("名称不能为空")
        name = name.strip()
        if len(name) > 80 or any(ord(char) < 32 for char in name):
            raise ValueError("名称最多 80 个字符，且不能包含换行")
        with self.lock:
            record = self.get(record_id)
            record["name"] = name
            record["saved"] = True
            record.pop("save_error", None)
            temporary = None
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                                                 prefix=".rename-", suffix=".tmp", delete=False) as handle:
                    temporary = Path(handle.name)
                    json.dump(record, handle, ensure_ascii=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.directory / (record_id + ".json"))
                self.records[record_id] = record
            finally:
                if temporary and temporary.exists():
                    temporary.unlink()
            return self.get(record_id)

    def list(self):
        with self.lock:
            result = []
            for record in sorted(self.records.values(), key=lambda r: r["created_at"], reverse=True):
                events = record["events"]
                result.append({key: record[key] for key in ("id", "name", "created_at", "saved")})
                result[-1]["recorded_at"] = record["created_at"]
                result[-1]["time_label"] = "保存时间"
                try:
                    started = record.get("diagnostics", {}).get("started_at")
                    result[-1]["recorded_at"] = datetime.strptime(started, "%Y-%m-%dT%H:%M:%S%z").isoformat()
                    result[-1]["time_label"] = "录制时间"
                except (TypeError, ValueError, AttributeError):
                    pass
                result[-1]["summary"] = {"total_events": len(events),
                    "click_count": sum(e["type"] == "click_down" for e in events),
                    "duration": round(events[-1]["time"], 2)}
            return result

    def delete(self, record_id):
        """从列表移除记录，将已有文件移入私有回收目录以便找回。"""
        with self.lock:
            self.get(record_id)  # 只接受库中已存在的标识，不使用调用方传入的路径。
            path = self.directory / (record_id + ".json")
            recovered_path = None
            if path.exists():
                trash = self.directory / ".trash"
                trash.mkdir(parents=True, exist_ok=True)
                recovered_path = trash / (record_id + "-" + uuid.uuid4().hex + ".json")
                os.replace(path, recovered_path)
            del self.records[record_id]
            return {"recoverable": recovered_path is not None}
