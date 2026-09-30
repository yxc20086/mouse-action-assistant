// 无浏览器依赖的 DOM 契约测试，不执行真实鼠标事件。
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
class Element {
  constructor() {
    this.children = []; this.handlers = {}; this.value = '0'; this.checked = false;
    const classes = new Set();
    this.classList = {
      add: name => classes.add(name),
      remove: name => classes.delete(name),
      contains: name => classes.has(name),
      toggle(name, force) {
        const enabled = force === undefined ? !classes.has(name) : force;
        if (enabled) classes.add(name); else classes.delete(name);
        return enabled;
      }
    };
  }
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.append(child); }
  replaceChildren(...children) { this.children = children; }
  setAttribute() {}
  addEventListener(name, callback) { this.handlers[name] = callback; }
  remove() {}
  focus() {}
  select() {}
}
const html = fs.readFileSync('ui/index.html', 'utf8');
const elements = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m => [m[1], new Element()]));
const rows = [
  {id:'a', name:'第一条', saved:true, summary:{duration:1, click_count:1, total_events:10}},
  {id:'b', name:'第二条', saved:true, summary:{duration:2, click_count:2, total_events:20}},
];
let selected = 'b', played, recordingArgs, restartCalls = 0, deleteCalls = 0;
const bridge = {
  delete_record: async id => {
    deleteCalls++;
    rows.splice(rows.findIndex(row=>row.id===id), 1);
    if (selected===id) selected=rows[0]?.id || null;
    return {success:true, recoverable:true};
  },
  restart_app: async () => {restartCalls++; return {success:true};},
  start_recording: async (...args) => {recordingArgs=args; return {success:true};},
  rename_record: async (id, name) => {rows.find(r=>r.id===id).name=name; return {success:true};},
  get_permissions: async () => ({accessibility:true, listen_events:true, post_events:true}),
  get_records: async () => ({records:rows, selected_id:selected, state:'IDLE', summary:rows.find(r=>r.id===selected).summary}),
  select_record: async id => {selected=id; return {success:true};},
  start_playback: async config => {played=config; selected=config.record_id; return {success:true};},
};
const context = vm.createContext({console, setTimeout() {}, clearTimeout() {}, setInterval() {},
  window:{pywebview:{api:bridge}, addEventListener() {}},
  document:{getElementById:id=>elements[id]||null, createElement:()=>new Element(),
    querySelectorAll:()=>[], body:new Element(), addEventListener() {}},
});
vm.runInContext(fs.readFileSync('ui/app.js','utf8'), context);
(async () => {
  vm.runInContext('renderRecords()', context);
  assert.equal(elements.recordList.children.length, 1);
  assert.equal(elements.playBtn.disabled, true);
  await vm.runInContext('refreshRecords()', context);
  assert.equal(elements.recordList.children.length, 2);
  assert.equal(elements.selectedName.textContent, '第二条');
  assert.equal(elements.playBtn.disabled, false);
  elements.recordList.scrollTop = 120;
  vm.runInContext('renderRecords()', context);
  assert.equal(elements.recordList.scrollTop, 120, '刷新列表保留滚动位置');
  vm.runInContext('selectRecord("a")', context);
  await new Promise(setImmediate);
  assert.equal(elements.selectedName.textContent, '第一条');
  vm.runInContext('openRename("a")', context);
  elements.renameInput.value = '我的菜单操作';
  await vm.runInContext('saveRename()', context);
  assert.equal(elements.selectedName.textContent, '我的菜单操作');
  vm.runInContext('openRename("a")', context);
  elements.renameInput.value = '  ';
  await vm.runInContext('saveRename()', context);
  assert.ok(elements.renameError.textContent.includes('1～80'));
  vm.runInContext('closeRename()', context);
  assert.equal(vm.runInContext('formatRecordTime("invalid")', context), '时间未知');
  rows.push({id:'c', name:'删除测试', saved:true, summary:{duration:1, click_count:1, total_events:2}});
  await vm.runInContext('refreshRecords()', context);
  vm.runInContext('openDeleteRecord("c")', context);
  assert.equal(deleteCalls, 0, '打开确认框不能立即删除');
  assert.equal(elements.deleteRecordName.textContent, '删除测试');
  vm.runInContext('closeDeleteRecord()', context);
  assert.equal(rows.length, 3, '取消删除应保留记录');
  const deleteImplementation = bridge.delete_record;
  bridge.delete_record = async () => ({success:false, error:'保存目录只读'});
  vm.runInContext('openDeleteRecord("c")', context);
  await vm.runInContext('confirmDeleteRecord()', context);
  assert.equal(rows.length, 3);
  assert.ok(elements.deleteRecordError.textContent.includes('只读'));
  bridge.delete_record = deleteImplementation;
  await vm.runInContext('confirmDeleteRecord()', context);
  assert.equal(deleteCalls, 1);
  assert.equal(rows.length, 2);
  assert.equal(elements.deleteRecordModal.classList.contains('hidden'), true);
  vm.runInContext('startPlayback("b")', context);
  await new Promise(setImmediate);
  assert.equal(played.record_id, 'b');
  assert.equal(Object.hasOwn(played, 'playback_mode'), false);
  assert.equal(Object.hasOwn(played, 'target_pid'), false);
  assert.ok(!html.includes('targetWindowSelect'));
  assert.ok(!html.includes('刷新列表'));
  assert.ok(!fs.readFileSync('ui/app.js', 'utf8').includes('get_window_list'));
  vm.runInContext('toggleRecord()', context);
  await new Promise(setImmediate);
  assert.deepEqual(recordingArgs, []);
  assert.ok(!html.includes('playbackMode'));
  assert.ok(!html.includes('后台控件'));
  vm.runInContext('window.onStateChange("RECORDING")', context);
  assert.equal(elements.playBtn.disabled, true);
  for (const row of elements.recordList.children) {
    assert.equal(row.children[0].children[0].disabled, true);
    assert.equal(row.children[1].disabled, true);
  }
  assert.ok(!html.includes('<canvas'));
  const css = fs.readFileSync('ui/style.css', 'utf8');
  const listStyle = css.match(/\.record-list\s*\{([^}]+)\}/)[1];
  assert.match(listStyle, /overflow-y:\s*auto/, '只有记录列表内部滚动');
  assert.match(listStyle, /min-height:\s*0/);
  assert.match(css.match(/body\s*\{([^}]+)\}/)[1], /overflow:\s*hidden/);
  assert.match(css.match(/\.app-layout\s*\{([^}]+)\}/)[1], /minmax\(0,\s*1fr\)/);
  assert.match(css.match(/\.record-row\s*\{([^}]+)\}/)[1], /padding:\s*8px 12px/);
  assert.match(css.match(/\.record-row\s*\{([^}]+)\}/)[1], /flex-shrink:\s*0/);
  elements.permModal.classList.remove('hidden');
  await vm.runInContext('checkPermission()', context);
  assert.equal(elements.permText.textContent, '录制与回放已授权');
  assert.equal(elements.permModal.classList.contains('hidden'), true, '全部授权后关闭权限弹窗');
  assert.equal(elements.inputPermissionBtn.textContent, '打开输入监控 · 已授权');
  assert.equal(elements.accessibilityPermissionBtn.textContent, '打开辅助功能 · 已授权');
  elements.permModal.classList.remove('hidden');
  bridge.get_permissions = async () => ({accessibility:false, listen_events:false, post_events:false});
  const pending = vm.runInContext('checkPermission()', context);
  assert.equal(elements.inputPermissionBtn.textContent, '打开输入监控 · 检测中…');
  assert.equal(elements.refreshPermissionBtn.disabled, true);
  await pending;
  assert.equal(elements.inputPermissionBtn.textContent, '打开输入监控 · 未授权');
  assert.equal(elements.accessibilityPermissionBtn.textContent, '打开辅助功能 · 未授权');
  assert.equal(elements.refreshPermissionBtn.disabled, false);
  assert.equal(elements.permModal.classList.contains('hidden'), false);
  bridge.get_permissions = async () => ({accessibility:true, listen_events:false, post_events:true});
  await vm.runInContext('checkPermission()', context);
  assert.ok(elements.permissionDetails.textContent.includes('输入监控：未生效'));
  assert.ok(elements.permissionRefreshStatus.textContent.includes('完全退出'));
  assert.equal(elements.permModal.classList.contains('hidden'), false, '部分权限未生效时保留弹窗');
  assert.equal(elements.inputPermissionBtn.textContent, '打开输入监控 · 未授权');
  assert.equal(elements.accessibilityPermissionBtn.textContent, '打开辅助功能 · 已授权');
  bridge.get_permissions = async () => ({accessibility:true, listen_events:{error:'unavailable'}, post_events:true});
  await vm.runInContext('checkPermission()', context);
  assert.equal(elements.inputPermissionBtn.textContent, '打开输入监控 · 检测异常');
  assert.equal(elements.accessibilityPermissionBtn.textContent, '打开辅助功能 · 已授权');
  bridge.get_permissions = async () => {throw new Error('bridge failed');};
  await vm.runInContext('checkPermission()', context);
  assert.equal(elements.permText.textContent, '权限检测失败 · 点击重试');
  assert.equal(elements.permModal.classList.contains('hidden'), false, '检测失败时保留弹窗');
  assert.equal(elements.inputPermissionBtn.textContent, '打开输入监控 · 检测失败');
  assert.equal(elements.accessibilityPermissionBtn.textContent, '打开辅助功能 · 检测失败');
  bridge.get_permissions = async () => ({accessibility:true, listen_events:true, post_events:true});
  await vm.runInContext('checkPermission()', context);
  assert.equal(elements.permText.textContent, '录制与回放已授权');
  assert.equal(elements.permModal.classList.contains('hidden'), true, '重新检测成功后关闭弹窗');
  assert.equal(elements.inputPermissionBtn.textContent, '打开输入监控 · 已授权');
  assert.equal(elements.accessibilityPermissionBtn.textContent, '打开辅助功能 · 已授权');
  assert.ok(!html.includes('permissionOverall'));
  await vm.runInContext('restartForPermissions()', context);
  assert.equal(restartCalls, 0, '录制过程中不能重启');
  vm.runInContext('isRecording = false; isPlaying = false;', context);
  bridge.restart_app = async () => ({success:false, error:'存在未自动保存的记录'});
  await vm.runInContext('restartForPermissions()', context);
  assert.equal(elements.restartPermissionBtn.disabled, false);
  assert.ok(elements.permissionRefreshStatus.textContent.includes('未自动保存'));
  bridge.restart_app = async () => {restartCalls++; return {success:true};};
  await vm.runInContext('restartForPermissions()', context);
  await vm.runInContext('restartForPermissions()', context);
  assert.equal(restartCalls, 1, '避免重复重启');
  assert.equal(elements.restartPermissionBtn.textContent, '正在重启…');
  assert.equal(elements.restartPermissionBtn.disabled, true);
  console.log('UI tests passed: empty, list, select, targeted playback, busy guards, no canvas');
})().catch(error => {console.error(error); process.exitCode=1;});
