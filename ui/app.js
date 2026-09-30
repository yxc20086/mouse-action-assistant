/* 鼠标动作助手：记录库。界面不参与系统鼠标监听。 */
let currentSpeed = 1, isRecording = false, isPlaying = false, busy = false;
let records = [], selectedId = null, initialized = false;
const api = () => window.pywebview && window.pywebview.api;
const el = id => document.getElementById(id);
let editingRecordId = null, renameSaving = false;
let restartPending = false;
let deletingRecordId = null, deletePending = false;
function formatRecordTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  const pad = n => String(n).padStart(2, "0");
  return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) +
    " " + pad(date.getHours()) + ":" + pad(date.getMinutes()) + ":" + pad(date.getSeconds());
}

function showToast(message, type = "info") {
  let container = el("toastContainer");
  if (!container) {
    container = document.createElement("div");
    container.id = "toastContainer"; container.className = "toast-container";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = "toast-item " + type + " show"; toast.textContent = message;
  container.appendChild(toast); setTimeout(() => toast.remove(), 5000);
}
function updateMetrics(summary = {}) {
  el("metricEvents").textContent = summary.total_events || 0;
  el("metricClicks").textContent = summary.click_count || 0;
  el("metricDuration").textContent = (summary.duration || 0).toFixed(1) + "s";
  el("eventCount").textContent = summary.total_events || 0;
  el("recordTimer").textContent = (summary.duration || 0).toFixed(1) + "s";
}
function renderRecords() {
  const list = el("recordList"), previousScroll = list.scrollTop || 0;
  list.replaceChildren();
  el("recordCount").textContent = records.length + " 条记录";
  if (!records.length) {
    const empty = document.createElement("div"); empty.className = "records-empty";
    empty.textContent = "暂无录制记录\n点击下方“开始录制”，或导入已有 JSON 轨迹。";
    list.appendChild(empty);
  }
  for (const record of records) {
    const row = document.createElement("div");
    row.className = "record-row" + (record.id === selectedId ? " selected" : "");
    const label = document.createElement("label"); label.className = "record-selector";
    const radio = document.createElement("input");
    radio.type = "radio"; radio.name = "record"; radio.checked = record.id === selectedId;
    radio.disabled = isRecording || isPlaying || busy;
    radio.setAttribute("aria-label", "选择 " + record.name);
    radio.addEventListener("change", () => selectRecord(record.id));
    const content = document.createElement("div"); content.className = "record-content";
    const name = document.createElement("strong"); name.textContent = record.name;
    const info = document.createElement("small");
    info.textContent = record.summary.duration.toFixed(1) + " 秒 · " + record.summary.click_count +
      " 次点击 · " + record.summary.total_events + " 个动作 · " + (record.saved ? "已保存" : "仅暂存，请导出");
    const time = document.createElement("small"); time.className = "record-time";
    time.textContent = (record.time_label || "保存时间") + "：" + formatRecordTime(record.recorded_at || record.created_at);
    name.title = record.name;
    content.append(name, time, info); label.append(radio, content);
    const play = document.createElement("button"); play.type = "button";
    play.className = "record-play"; play.textContent = "▶ 回放";
    play.disabled = isRecording || isPlaying || busy;
    play.setAttribute("aria-label", "回放 " + record.name);
    play.addEventListener("click", () => startPlayback(record.id));
    const rename = document.createElement("button"); rename.type = "button";
    rename.className = "record-play record-rename"; rename.textContent = "改名";
    rename.disabled = isRecording || isPlaying || busy;
    rename.setAttribute("aria-label", "重命名 " + record.name);
    rename.addEventListener("click", () => openRename(record.id));
    const remove = document.createElement("button"); remove.type = "button";
    remove.className = "record-play record-delete"; remove.textContent = "删除";
    remove.disabled = isRecording || isPlaying || busy;
    remove.setAttribute("aria-label", "删除 " + record.name);
    remove.addEventListener("click", () => openDeleteRecord(record.id));
    row.append(label, play, rename, remove); list.appendChild(row);
  }
  list.scrollTop = previousScroll;
  const selected = records.find(record => record.id === selectedId);
  el("selectedName").textContent = selected ? selected.name : "尚未选择记录";
  el("playBtn").disabled = busy || isRecording || (!isPlaying && !selected);
  el("recordBtn").disabled = busy || isPlaying;
  el("restartPermissionBtn").disabled = busy || isRecording || isPlaying || restartPending;
  document.querySelectorAll(".file-actions button").forEach(button => {
    button.disabled = busy || isRecording || isPlaying;
  });
}
function openRename(id) {
  if (isRecording || isPlaying || busy) return;
  const record = records.find(item => item.id === id);
  if (!record) return;
  editingRecordId = id;
  el("renameInput").value = record.name;
  el("renameError").textContent = "";
  el("renameModal").classList.remove("hidden");
  el("renameInput").focus(); el("renameInput").select();
}
function openDeleteRecord(id) {
  if (isRecording || isPlaying || busy || restartPending) return;
  const record = records.find(item => item.id === id);
  if (!record) return;
  deletingRecordId = id;
  el("deleteRecordName").textContent = record.name;
  el("deleteRecordError").textContent = "";
  el("deleteRecordModal").classList.remove("hidden");
  el("deleteRecordCancel").focus();
}
function closeDeleteRecord() {
  if (deletePending) return;
  deletingRecordId = null;
  el("deleteRecordModal").classList.add("hidden");
}
async function confirmDeleteRecord() {
  if (!deletingRecordId || deletePending || busy || !api()) return;
  if (isRecording || isPlaying) {
    el("deleteRecordError").textContent = "请先停止录制或回放，再删除记录"; return;
  }
  deletePending = true; busy = true;
  el("deleteRecordConfirm").disabled = true;
  el("deleteRecordCancel").disabled = true;
  renderRecords();
  try {
    const result = await api().delete_record(deletingRecordId);
    if (!result.success) throw new Error(result.error);
    deletePending = false; closeDeleteRecord();
    await refreshRecords();
    showToast(result.recoverable ? "记录已移除，原文件保留在记录库的回收目录" : "记录已删除", "success");
  } catch (error) {
    el("deleteRecordError").textContent = String(error.message || error);
    showToast(String(error.message || error), "error");
  } finally {
    deletePending = false; busy = false;
    el("deleteRecordConfirm").disabled = false;
    el("deleteRecordCancel").disabled = false;
    renderRecords();
  }
}
function closeRename() {
  if (renameSaving) return;
  el("renameModal").classList.add("hidden"); editingRecordId = null;
}
async function saveRename() {
  if (!editingRecordId || renameSaving) return;
  const name = el("renameInput").value.trim();
  if (!name || Array.from(name).length > 80) {
    el("renameError").textContent = "请输入 1～80 个字符的名称"; return;
  }
  renameSaving = true;
  el("renameSave").disabled = true;
  try {
    const result = await api().rename_record(editingRecordId, name);
    if (!result.success) throw new Error(result.error);
    await refreshRecords();
    renameSaving = false; closeRename();
    showToast("名称已保存", "success");
  } catch (error) {
    el("renameError").textContent = String(error.message || error);
  } finally { renameSaving = false; el("renameSave").disabled = false; }
}
async function refreshRecords() {
  const data = await api().get_records(); records = data.records; selectedId = data.selected_id;
  isRecording = data.state === "RECORDING";
  isPlaying = data.state === "COUNTDOWN" || data.state === "PLAYING";
  if (!isRecording) updateMetrics(data.summary);
  renderRecords();
  if (!initialized) (data.warnings || []).forEach(message => showToast(message, "warning"));
}
async function runAction(action) {
  if (busy || !api()) return;
  busy = true; renderRecords();
  try { await action(); } catch (error) { showToast(String(error.message || error), "error"); }
  finally { busy = false; renderRecords(); }
}
function selectRecord(id) {
  if (isRecording || isPlaying) return;
  runAction(async () => {
    const result = await api().select_record(id);
    if (!result.success) throw new Error(result.error);
    await refreshRecords();
  });
}
window.onStateChange = function(state, data = {}) {
  if (state === "ERROR") {
    if (restartPending) {
      restartPending = false; busy = false;
      el("restartPermissionBtn").textContent = "重启应用使授权生效";
      el("permissionRefreshStatus").textContent = data.message || "重启失败，请重试";
      renderRecords();
    }
    showToast(data.message || "操作失败", "error"); return;
  }
  if (state === "PERMISSION_DENIED") { openPermissionSettings(); return; }
  isRecording = state === "RECORDING";
  isPlaying = state === "COUNTDOWN" || state === "PLAYING";
  el("recordBtn").classList.toggle("recording", isRecording);
  el("recordBtnText").textContent = isRecording ? "停止并保存录制 (F7)" : "开始录制 (F7 / Ctrl+R)";
  el("playBtn").classList.toggle("playing", isPlaying);
  el("playBtnText").textContent = isPlaying ? "停止回放 (Esc)" : "回放选中记录 (F8 / Ctrl+P)";
  el("hudOverlay").classList.toggle("hidden", state !== "COUNTDOWN");
  if (state === "COUNTDOWN") el("hudNumber").textContent = data.seconds;
  if (state === "RECORDING") {
    updateMetrics();
    el("recordStatus").textContent = "正在录制，窗口已自动最小化。按 F7 停止、保存并恢复窗口。";
  } else if (state === "PLAYING") {
    el("recordStatus").textContent = "正在回放 · 第 " + data.current + " / " + (data.total || "∞") + " 轮 · Esc 急停";
  } else if (state === "IDLE") {
    el("recordStatus").textContent = "录制结束后自动保存。选中记录，再点击回放。";
    refreshRecords().catch(error => showToast(String(error), "error"));
  }
  if (data.warning) showToast(data.warning, "warning");
  renderRecords();
};
function toggleRecord() {
  runAction(async () => {
    if (isRecording) await api().stop_recording();
    else {
      const result = await api().start_recording();
      if (!result || !result.success) throw new Error(result && result.error || "录制启动失败");
    }
  });
}
function startPlayback(id) {
  if (isRecording || isPlaying) return;
  runAction(async () => {
    const result = await api().start_playback({
      record_id: id,
      loop_count: el("infiniteLoop").checked ? 0 : Math.max(1, Number(el("loopCount").value) || 1),
      speed_factor: currentSpeed,
      countdown_seconds: Math.max(0, Number(el("countdownSec").value) || 0),
      loop_interval: Math.max(0, Number(el("loopInterval").value) || 0),
      auto_minimize: el("autoMinimize").checked
    });
    if (!result.success) throw new Error(result.error);
    selectedId = id; await refreshRecords();
  });
}
function togglePlay() {
  if (isPlaying) api().stop_playback().catch(error => showToast(String(error), "error"));
  else startPlayback(selectedId);
}
function toggleInfinite() { el("loopCount").disabled = el("infiniteLoop").checked; }
function setSpeed(speed, button) {
  currentSpeed = speed;
  document.querySelectorAll(".chip").forEach(chip => chip.classList.remove("active"));
  button.classList.add("active");
}
function saveTrackFile() {
  runAction(async () => { if (await api().save_track_file()) showToast("选中记录已导出", "success"); });
}
function loadTrackFile() {
  runAction(async () => {
    const result = await api().load_track_file();
    if (result.error) throw new Error(result.error);
    if (result.warning) showToast(result.warning, "warning");
    await refreshRecords();
  });
}
function openPermissionSettings() {
  el("permModal").classList.remove("hidden");
  checkPermission();
}
function closePermModal() { el("permModal").classList.add("hidden"); }
function openInputSettings() { api().open_input_settings(); }
function openAccessibilitySettings() { api().open_permission_settings(); }
async function restartForPermissions() {
  if (restartPending || !api()) return;
  if (busy || isRecording || isPlaying || editingRecordId || renameSaving || deletingRecordId) {
    showToast("请先停止录制或回放，并完成名称编辑，再重启应用", "warning"); return;
  }
  restartPending = true; busy = true; renderRecords();
  el("restartPermissionBtn").textContent = "正在重启…";
  el("permissionRefreshStatus").textContent = "正在关闭当前版本，随后自动重新打开并检测权限。已保存记录会保留。";
  try {
    const result = await api().restart_app();
    if (!result.success) throw new Error(result.error);
  } catch (error) {
    restartPending = false; busy = false;
    el("restartPermissionBtn").textContent = "重启应用使授权生效";
    el("permissionRefreshStatus").textContent = String(error.message || error);
    showToast(String(error.message || error), "error");
    renderRecords();
  }
}
let permissionCheckPending = false;
function setPermissionButton(id, name, value) {
  const label = value === true ? "已授权" : value === false ? "未授权" :
    typeof value === "string" ? value : "检测异常";
  const level = value === true ? "granted" : value === false ? "denied" :
    (label === "检测中…" || label === "等待连接") ? "checking" : "error";
  el(id).className = "modal-btn permission-action " + level;
  el(id).textContent = "打开" + name + " · " + label;
}
function setPermissionButtonsPending(label) {
  setPermissionButton("inputPermissionBtn", "输入监控", label);
  setPermissionButton("accessibilityPermissionBtn", "辅助功能", label);
}
async function checkPermission() {
  if (permissionCheckPending || restartPending) return;
  if (!api()) {
    el("permText").textContent = "等待权限服务连接";
    setPermissionButtonsPending("等待连接");
    return;
  }
  permissionCheckPending = true;
  setPermissionButtonsPending("检测中…");
  el("refreshPermissionBtn").textContent = "正在检测…";
  el("refreshPermissionBtn").disabled = true;
  let timeout;
  try {
    const status = await Promise.race([
      api().get_permissions(),
      new Promise((resolve, reject) => { timeout = setTimeout(() => reject(new Error("权限检测超时")), 5000); })
    ]);
    if (restartPending) return;
    const granted = key => status[key] === true;
    const label = key => granted(key) ? "已生效" : status[key] === false ? "未生效" : "检测异常";
    const trusted = granted("accessibility") && granted("listen_events") && granted("post_events");
    setPermissionButton("inputPermissionBtn", "输入监控", status.listen_events);
    setPermissionButton("accessibilityPermissionBtn", "辅助功能", status.accessibility);
    const detail = "输入监控：" + label("listen_events") + "；辅助功能：" + label("accessibility") + "；模拟点击：" + label("post_events");
    el("permBadge").className = "perm-badge " + (trusted ? "granted" : "denied");
    el("permBadge").title = detail + "。点击查看详情并刷新。";
    el("permText").textContent = trusted ? "录制与回放已授权" : "权限未全部生效 · 点击查看";
    el("permissionDetails").textContent = detail;
    el("permissionRefreshStatus").textContent = "刚刚检查 · " + (trusted ? "当前进程已获得全部权限。" : "若系统开关已开启，请用 ⌘Q 完全退出，再从应用程序重新打开。刷新无法代替系统要求的重启。");
    if (trusted) closePermModal();
  } catch (error) {
    setPermissionButtonsPending("检测失败");
    el("permBadge").className = "perm-badge checking";
    el("permText").textContent = "权限检测失败 · 点击重试";
    el("permissionDetails").textContent = "暂时无法读取权限状态，不代表权限已被撤销。";
    el("permissionRefreshStatus").textContent = String(error.message || error);
  } finally {
    clearTimeout(timeout);
    permissionCheckPending = false;
    el("refreshPermissionBtn").textContent = "刷新权限状态";
    el("refreshPermissionBtn").disabled = restartPending;
  }
}
window.addEventListener("focus", () => checkPermission());
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") checkPermission();
});
window.addEventListener("keydown", event => {
  if (deletingRecordId && event.key === "Escape") {
    event.preventDefault(); closeDeleteRecord();
  }
  if (editingRecordId) {
    if (event.key === "Enter") { event.preventDefault(); saveRename(); }
    if (event.key === "Escape") { event.preventDefault(); closeRename(); }
  }
  if (event.key === "Escape" && isPlaying) api().stop_playback();
});
window.addEventListener("DOMContentLoaded", () => {
  renderRecords();
  async function poll() {
    try {
      if (api()) {
        if (!initialized) {
          await refreshRecords(); await checkPermission(); initialized = true;
        }
        const updates = await api().get_updates();
        for (const update of updates) {
          if (update.state) window.onStateChange(update.state, update.data);
          else if (isRecording && update.event.count !== undefined) {
            el("eventCount").textContent = update.event.count;
            el("recordTimer").textContent = update.event.time.toFixed(1) + "s";
          }
        }
      }
    } catch (error) { console.error(error); }
    finally { setTimeout(poll, 100); }
  }
  poll(); setInterval(() => checkPermission().catch(console.error), 2000);
});
