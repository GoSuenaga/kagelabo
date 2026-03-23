'use strict';

const API = location.origin;

let sessionId = sessionStorage.getItem('kage_session') || null;

// DOM
const chatArea      = document.getElementById('chatArea');
const msgInput      = document.getElementById('msgInput');
const btnSend       = document.getElementById('btnSend');
const btnUpcoming   = document.getElementById('btnUpcoming');
const btnReload     = document.getElementById('btnReload');

const schedModal    = document.getElementById('scheduleModal');
const schedTitle    = document.getElementById('schedTitle');
const schedDate     = document.getElementById('schedDate');
const schedMemo     = document.getElementById('schedMemo');
const modalSave     = document.getElementById('modalSave');
const modalCancel   = document.getElementById('modalCancel');

const minutesModal  = document.getElementById('minutesModal');
const minTitle      = document.getElementById('minTitle');
const minWhen       = document.getElementById('minWhen');
const minBody       = document.getElementById('minBody');
const minutesSave   = document.getElementById('minutesSave');
const minutesCancel = document.getElementById('minutesCancel');

const upcomingModal = document.getElementById('upcomingModal');
const upcomingBody  = document.getElementById('upcomingBody');
const upcomingClose = document.getElementById('upcomingClose');
const btnDebugList  = document.getElementById('btnDebugList');
const debugModal    = document.getElementById('debugModal');
const debugBody     = document.getElementById('debugBody');
const debugClose    = document.getElementById('debugClose');
const headerDate    = document.getElementById('headerDate');
const btnModel      = document.getElementById('btnModel');
const modelModal    = document.getElementById('modelModal');
const modelList     = document.getElementById('modelList');
const modelClose    = document.getElementById('modelClose');

let currentModel = 'gemini-2.5-flash';

// ── Helpers ───────────────────────────────────────
function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fmtDateHeader() {
  const d = new Date();
  return d.toLocaleDateString('ja-JP',{year:'numeric',month:'long',day:'numeric',weekday:'short'});
}
function todayStr() { return new Date().toISOString().slice(0,10); }
/** datetime-local 用（端末ローカル、タイムゾーンオフセット補正） */
function nowLocalDatetimeInputValue() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}
function fmtDate(s) {
  if (!s) return '';
  const d = new Date(s);
  if (isNaN(d)) return s;
  return d.toLocaleDateString('ja-JP',{month:'short',day:'numeric',weekday:'short'});
}
function scrollEnd() {
  requestAnimationFrame(() => chatArea.scrollTo({top:chatArea.scrollHeight,behavior:'smooth'}));
}

// ── Chat render ───────────────────────────────────
/**
 * @param {string} role
 * @param {string} html
 * @param {string} [cls]
 * @param {{ noScroll?: boolean }} [opts] 起動時など、先頭を見せたいとき true
 */
function addMsg(role, html, cls = '', opts = {}) {
  const noScroll = opts && opts.noScroll === true;
  const row = document.createElement('div');
  row.className = `row ${role}`;
  if (role === 'kage') {
    const av = document.createElement('div');
    av.className = 'avatar'; av.textContent = '影';
    row.appendChild(av);
  }
  const bbl = document.createElement('div');
  bbl.className = `bubble ${cls}`;
  bbl.innerHTML = html;
  row.appendChild(bbl);
  chatArea.appendChild(row);
  if (!noScroll) scrollEnd();
  return bbl;
}
function addUser(text) { addMsg('user', esc(text)); }

let typingEl = null;
function showTyping() {
  const row = document.createElement('div');
  row.className = 'row kage'; row.id = 'typing';
  const av = document.createElement('div');
  av.className = 'avatar'; av.textContent = '影';
  row.appendChild(av);
  const bbl = document.createElement('div');
  bbl.className = 'bubble';
  bbl.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
  row.appendChild(bbl);
  chatArea.appendChild(row);
  typingEl = row; scrollEnd();
}
function hideTyping() { typingEl && (typingEl.remove(), typingEl = null); }

// ── Welcome ───────────────────────────────────────
function showWelcome() {
  const h = new Date().getHours();
  const g = h < 12 ? 'おはようございます' : h < 18 ? 'お疲れ様です' : 'お疲れ様です';
  const body =
    h < 12
      ? '今日のメモ・予定・タスクも、議事録の整理も、ここからで大丈夫です。遠慮なく話しかけてください。'
      : h < 18
        ? '午後の予定や残タスクを一緒に整えたり、議事録を預けたりしても構いません。何でも話しかけてください。'
        : '今日を締める前に、メモや明日の予定だけでも置いていってください。こちらにいますので、何でも話しかけてください。';
  // 日付はヘッダー、時刻はOSステータスバーに任せ、ウェルカムでは日時を出さない（重複削減）
  addMsg(
    'kage',
    `
    <div class="welcome welcome--compact">
      <p class="welcome-lead"><strong>${g}、ボス。</strong> ${body}</p>
      <details class="welcome-details">
        <summary class="welcome-details-sum">使い方ヒント（タップで開く）</summary>
        <div class="welcome-details-body">
          <p class="welcome-details-lead">影が Notion の管理をサポートいたします。</p>
          <ul class="welcome-hint-list">
            <li>📝 メモ・💡 アイデア → 保存</li>
            <li>📋 議事録 → Notion に蓄積。DBの列はサーバがNotionから自動認識（型さえ合っていれば列名は日本語でも可）。長文は要約＋原文保存可</li>
            <li>📅 予定ボタン → 日時つきで保存</li>
            <li>🧠 整理ボタン → タスクを整理</li>
            <li>🐛 バグボタン → 不具合を Notion に記録</li>
            <li>✅ 仕事タスク → Tasks に保存（所要時間が無いと聞き返します）</li>
            <li>💤 「おやすみ」「おはよう」→ 睡眠ログ</li>
            <li>🚪 「行ってきます」「ただいま」→ 健康メモ</li>
            <li>📆 右上カレンダー → 今後の予定確認</li>
          </ul>
          <p class="welcome-details-foot">長い連絡は貼り付けでタスク化できます。社内短文・返信文案の相談も OK です。</p>
        </div>
      </details>
    </div>
  `,
    '',
    { noScroll: true }
  );
}

// ── API ───────────────────────────────────────────
/** FastAPI の { detail: string | array } やプレーンテキストから人向けメッセージを取り出す */
async function fetchErrorMessage(r) {
  const ct = (r.headers.get('content-type') || '').toLowerCase();
  try {
    if (ct.includes('application/json')) {
      const j = await r.json();
      if (typeof j.detail === 'string') return j.detail;
      if (Array.isArray(j.detail)) {
        const parts = j.detail
          .map((x) => (x && (x.msg || x.message)) || '')
          .filter(Boolean);
        if (parts.length) return parts.join(' ');
      }
    } else {
      const t = await r.text();
      if (t && t.length < 800) return t.trim();
    }
  } catch (_) { /* ignore */ }
  return `HTTP ${r.status}`;
}

async function post(path, body) {
  const r = await fetch(`${API}${path}`,{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error(await fetchErrorMessage(r));
  return r.json();
}
async function get(path) {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(await fetchErrorMessage(r));
  return r.json();
}

// ── Response renderer ─────────────────────────────
const BADGE = {
  memo:'📝 メモ', minutes:'📋 議事録', idea:'💡 アイデア', task:'✅ タスク', schedule:'📅 予定', profile:'🧠 記憶',
  done:'🗑️ 完了', debug:'🐛 バグ報告',
  sleep_bedtime:'💤 就寝', sleep_wake:'🌅 起床', health_go:'🚪 外出', health_back:'🏠 帰宅',
  task:'✅ タスク',
  news_feedback:'📰 ニュース好み',
};

function scheduleDupEncode(obj) {
  return btoa(unescape(encodeURIComponent(JSON.stringify(obj))));
}
function scheduleDupDecode(b64) {
  return JSON.parse(decodeURIComponent(escape(atob(b64))));
}

/** 予定の重複確認（チャット・予定モーダル共通） */
function renderScheduleDupConfirm(data) {
  const prop = data.schedule_proposed || {};
  const cands = data.schedule_candidates || [];
  const pb = scheduleDupEncode(prop);
  const cb = scheduleDupEncode(cands);
  let list = '<ul class="sched-dup-list">';
  cands.forEach(c => {
    const pct = Math.round((Number(c.similarity) || 0) * 100);
    const snip =
      c.memo && c.memo.length
        ? '<br><span class="sched-dup-memo">' +
          esc(c.memo.length > 140 ? c.memo.slice(0, 140) + '…' : c.memo) +
          '</span>'
        : '';
    list +=
      '<li><strong>' +
      esc(c.title || '') +
      '</strong> <span class="sched-dup-sim">（類似 ' +
      pct +
      '%）</span>' +
      snip +
      '</li>';
  });
  list += '</ul>';
  const html =
    '<div class="schedule-dup-wrap">' +
    (BADGE.schedule ? '<span class="badge-intent">' + BADGE.schedule + '</span><br>' : '') +
    esc(data.message || 'この予定は重複していませんか？') +
    list +
    '<p class="sched-dup-hint">秘書として、登録前に念のためお伺いしています。</p>' +
    '<div class="confirm-row schedule-dup-actions">' +
    '<button type="button" class="cfm-btn" data-sched-dup="merge" data-proposed-b64="' +
    esc(pb) +
    '" data-cands-b64="' +
    esc(cb) +
    '">重複している（まとめる）</button>' +
    '<button type="button" class="cfm-btn cfm-btn-secondary" data-sched-dup="new" data-proposed-b64="' +
    esc(pb) +
    '">重複していない（新規）</button>' +
    '</div></div>';
  addMsg('kage', html, 'warn');
}

function renderResponse(data, originalText) {
  const { intent, message, saved } = data;

  if (data.need_schedule_confirmation && data.schedule_candidates && data.schedule_proposed) {
    renderScheduleDupConfirm(data);
    return;
  }

  if (intent === 'task') {
    const b = BADGE.task ? `<span class="badge-intent">${BADGE.task}</span><br>` : '';
    const foot = saved === true
      ? '<br><span class="badge-save">✓ Notion Tasks に記録しました</span>'
      : '<br><span class="badge-save dim-save">※ 所要時間の入力待ち、または保存できませんでした</span>';
    addMsg('kage', `${b}${esc(message||'')}${foot}`, saved === true ? 'saved' : 'warn');
    return;
  }

  if (['sleep_bedtime','sleep_wake','health_go','health_back'].includes(intent)) {
    const b = BADGE[intent] ? `<span class="badge-intent">${BADGE[intent]}</span><br>` : '';
    const foot = saved
      ? '<br><span class="badge-save">✓ Notionに記録しました</span>'
      : '<br><span class="badge-save dim-save">※ この端末のセッションのみ、またはNotion未保存です</span>';
    addMsg('kage', `${b}${esc(message||'')}${foot}`, 'saved');
    return;
  }

  // memo / profile / debug などは saved===true のときだけ「保存済み」表示（失敗時の誤表示防止）
  if (['memo','minutes','idea','task','schedule','profile','debug'].includes(intent)) {
    const b = BADGE[intent] ? `<span class="badge-intent">${BADGE[intent]}</span><br>` : '';
    const foot = saved === true
      ? '<br><span class="badge-save">✓ Notion保存済み</span>'
      : '<br><span class="badge-save dim-save">※ Notionに保存できませんでした（再試行またはコピーログで共有ください）</span>';
    addMsg('kage', `${b}${esc(message||'')}${foot}`, saved === true ? 'saved' : 'error');
    return;
  }

  if (['unknown','unknown_question','unclear'].includes(intent)) {
    addMsg('kage', `
      ${esc(message||'どのように保存しますか？')}
      <div class="confirm-row">
        <button class="cfm-btn" data-confirm="memo"  data-orig="${esc(originalText||'')}">📝 メモ</button>
        <button class="cfm-btn" data-confirm="idea"  data-orig="${esc(originalText||'')}">💡 アイデア</button>
        <button class="cfm-btn" data-confirm="skip">キャンセル</button>
      </div>
    `, 'warn');
    return;
  }

  if (intent === 'done' && data.candidates && data.candidates.length > 0) {
    let html = esc(message) + '<div class="confirm-row" style="flex-direction:column;gap:6px;margin-top:8px">';
    data.candidates.forEach(c => {
      html += `<button class="cfm-btn archive-btn" data-pageid="${esc(c.page_id)}" data-title="${esc(c.title)}" style="text-align:left;padding:8px 12px">🗑️ ${esc(c.title)}（${esc(c.db)}）</button>`;
    });
    html += '</div>';
    addMsg('kage', html);
    return;
  }

  if (intent === 'think') {
    addMsg(
      'kage',
      '<div class="think-section think-single-layout">' + buildThinkHtml(message || '') + '</div>'
    );
    return;
  }

  if (intent === 'news_feedback') {
    const b = `<span class="badge-intent">${BADGE.news_feedback}</span><br>`;
    const foot =
      saved === true
        ? '<br><span class="badge-save">✓ Notionメモ（[ニュースFB]）に反映しました</span>'
        : '';
    addMsg('kage', `${b}${esc(message || '')}${foot}`, saved === true ? 'saved' : '');
    return;
  }

  addMsg('kage', esc(message||'承知しました。'));
}

// ── Think: シングルタスク強調 + その他は折りたたみ ──
const THINK_HERO_TITLES = new Set(['今すぐ', '今すぐやること', 'まずやること', '最優先']);

function parseThinkSections(text) {
  const parts = String(text).split(/(?=【)/);
  const out = [];
  for (const section of parts) {
    const t = section.trim();
    if (!t) continue;
    const m = t.match(/^【(.+?)】(.*)$/s);
    if (m) out.push({ title: m[1].trim(), body: m[2].trim() });
    else out.push({ title: '_raw', body: t });
  }
  return out;
}

/** 先頭の箇条書き1行を取り出し、残りを返す */
function partitionFirstBullet(body) {
  const lines = body.split('\n').map(l => l.trim()).filter(Boolean);
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^[・•*＊\-]\s*(.+)$/);
    if (m) return { first: m[1].trim(), restLines: lines.slice(i + 1) };
  }
  if (lines.length === 1) return { first: lines[0], restLines: [] };
  if (lines.length > 1) return { first: lines[0], restLines: lines.slice(1) };
  return { first: (body || '').trim(), restLines: [] };
}

function countNonEmptyLines(body) {
  if (!body || !body.trim()) return 0;
  return body.split('\n').map(l => l.trim()).filter(Boolean).length;
}

function renderThinkRestSections(sections) {
  let h = '';
  for (const s of sections) {
    if (!s.body || !s.body.trim()) continue;
    if (s.title !== '_raw') {
      h += '<div class="think-more-sec-title">' + esc(s.title) + '</div>';
    }
    const lines = s.body.split('\n').map(l => l.trim()).filter(Boolean);
    for (const line of lines) {
      h += '<div class="think-item think-item-dim">' + esc(line) + '</div>';
    }
  }
  return h;
}

/** 整理結果HTML（いまやること大 + その他は details） */
function buildThinkHtml(text) {
  const sections = parseThinkSections(text);
  if (!sections.length) {
    return '<div class="think-item">' + esc(String(text).trim()) + '</div>';
  }

  let kageFoot = '';
  const work = [];
  for (const s of sections) {
    if (s.title === '影より') {
      kageFoot = s.body;
      continue;
    }
    work.push({ title: s.title, body: s.body });
  }

  let heroText = '';
  let heroIdx = -1;
  let trimmedBodies = null;

  for (let i = 0; i < work.length; i++) {
    if (!THINK_HERO_TITLES.has(work[i].title)) continue;
    const { first, restLines } = partitionFirstBullet(work[i].body);
    if (first) {
      heroText = first;
      heroIdx = i;
      trimmedBodies = work.map((s, j) =>
        j === i ? { title: s.title, body: restLines.join('\n') } : { title: s.title, body: s.body }
      );
      break;
    }
  }

  if (!heroText) {
    for (let i = 0; i < work.length; i++) {
      const { first, restLines } = partitionFirstBullet(work[i].body);
      if (first) {
        heroText = first;
        heroIdx = i;
        trimmedBodies = work.map((s, j) =>
          j === i ? { title: s.title, body: restLines.join('\n') } : { title: s.title, body: s.body }
        );
        break;
      }
    }
  }

  if (!heroText) {
    return '<div class="think-item">' + esc(String(text).trim()) + '</div>';
  }

  const restSections = trimmedBodies
    .map((s, i) => {
      if (i !== heroIdx) return s;
      const b = (s.body || '').trim();
      return b ? s : null;
    })
    .filter(Boolean);

  const itemCount = restSections.reduce((n, s) => n + countNonEmptyLines(s.body), 0);
  const restHtml = renderThinkRestSections(restSections);

  let html = '';
  html += '<div class="think-hero-block">';
  html += '<div class="think-hero-label">いまやること</div>';
  html += '<div class="think-hero-text">' + esc(heroText) + '</div>';
  html += '</div>';

  if (itemCount > 0 && restHtml) {
    html += '<details class="think-more">';
    html +=
      '<summary><span class="think-more-summary-main">その他の候補・メモ <span class="think-more-count">' +
      esc(String(itemCount)) +
      '件</span></span></summary>';
    html += '<div class="think-more-body">' + restHtml + '</div>';
    html += '</details>';
  }

  if (kageFoot && kageFoot.trim()) {
    html += '<div class="think-kage-foot">' + esc(kageFoot.trim()) + '</div>';
  }

  return html;
}

function renderThinkResult(text) {
  addMsg(
    'kage',
    '<div class="think-section think-single-layout">' + buildThinkHtml(text) + '</div>'
  );
}

// ── Send ──────────────────────────────────────────
async function handleSend() {
  const text = msgInput.value.trim();
  if (!text && !pendingImage) return;
  const displayText = text || '(画像を送信)';
  addUser(displayText);
  if (pendingImage) {
    const thumb = document.createElement('img');
    thumb.src = previewImg.src;
    thumb.className = 'user-sent-image';
    chatArea.lastElementChild.querySelector('.bubble').appendChild(thumb);
  }
  msgInput.value = ''; autoResize();
  showTyping();
  try {
    const body = {message: text || 'この画像について教えて'};
    if (sessionId) body.session_id = sessionId;
    if (pendingImage) {
      body.image = pendingImage;
      body.mime_type = pendingMime || 'image/jpeg';
    }
    pendingImage = null; pendingMime = null;
    imagePreview.classList.add('hidden'); previewImg.src = '';
    const data = await post('/chat', body);
    if (data.session_id) {
      sessionId = data.session_id;
      sessionStorage.setItem('kage_session', sessionId);
    }
    hideTyping();
    renderResponse(data, text);
  } catch(e) {
    hideTyping();
    addMsg('kage',`ボス、通信エラーが発生しました。`,'error');
  }
}

// ── Quick actions ─────────────────────────────────
document.querySelectorAll('.qa').forEach(btn => {
  btn.addEventListener('click', async () => {
    const a = btn.dataset.action;
    if (a === 'schedule') { openSched(); return; }
    if (a === 'minutes') { openMinutes(); return; }
    if (a === 'brain') { handleThink(); return; }
    if (a === 'cleanup') { handleCleanup(); return; }
    const prefix = { memo:'メモ: ', idea:'アイデア: ', bug:'バグ: ' }[a];
    if (prefix) {
      msgInput.value = prefix;
      msgInput.focus();
      const end = msgInput.value.length;
      msgInput.setSelectionRange(end, end);
      autoResize();
    }
  });
});

// ── Think (整理ボタン) — /think エンドポイント使用 ──
async function handleThink() {
  addUser('整理して');
  showTyping();
  try {
    const data = await post('/think', {});
    hideTyping();
    renderThinkResult(data.message || 'ボス、データがありません。');
  } catch(e) {
    hideTyping();
    addMsg('kage','ボス、整理に失敗しました。通信エラーです。','error');
  }
}

// ── Cleanup (片付けボタン) ────────────────────────
async function handleCleanup() {
  addUser('片付けて');
  showTyping();
  try {
    const data = await get('/cleanup');
    hideTyping();
    const items = data.candidates || [];
    if (!items.length) {
      addMsg('kage', '片付けるものはありません。すっきりしてますね。');
      return;
    }
    let html = `${items.length}件のアイテムがあります。不要なものをタップしてアーカイブできます。<div class="confirm-row" style="flex-direction:column;gap:6px;margin-top:8px">`;
    items.forEach(c => {
      const label = c.db === 'Schedule' ? '📅' : c.db === 'Tasks' ? '✅' : '📝';
      html += `<button class="cfm-btn archive-btn" data-pageid="${esc(c.page_id)}" data-title="${esc(c.title)}" style="text-align:left;padding:8px 12px">${label} ${esc(c.title)} <span style="color:var(--dim);font-size:11px">${c.created||''}</span></button>`;
    });
    html += '</div>';
    addMsg('kage', html);
  } catch(e) {
    hideTyping();
    addMsg('kage', '片付けリストの取得に失敗しました。', 'error');
  }
}

// ── Confirm bubble buttons ────────────────────────
chatArea.addEventListener('click', async e => {
  const mergePick = e.target.closest('[data-sched-merge-pick]');
  if (mergePick) {
    e.preventDefault();
    let proposed;
    try {
      proposed = scheduleDupDecode(mergePick.dataset.proposedB64);
    } catch (err) {
      addMsg('kage', 'データの読み取りに失敗しました。もう一度予定から登録してください。', 'error');
      return;
    }
    const pageId = mergePick.dataset.pageId;
    if (!pageId || !proposed) return;
    mergePick.closest('.schedule-dup-actions')?.querySelectorAll('button').forEach(b => (b.disabled = true));
    showTyping();
    try {
      const data = await post('/schedule', {
        title: proposed.title,
        date: proposed.date,
        memo: proposed.memo || '',
        merge_into_page_id: pageId,
      });
      hideTyping();
      if (data.saved) {
        addMsg(
          'kage',
          `📅 <strong>${esc(proposed.title)}</strong><br>${fmtDate(proposed.date)}<br>${esc(data.message || '既存の予定にまとめました。')}<br><span class="badge-save">✓ Notion保存済み</span>`,
          'saved'
        );
      } else {
        addMsg('kage', esc(data.message || 'まとめに失敗しました。'), 'error');
      }
    } catch (err) {
      hideTyping();
      addMsg('kage', 'ボス、通信エラーでまとめられませんでした。', 'error');
    }
    return;
  }

  const schedDup = e.target.closest('[data-sched-dup]');
  if (schedDup) {
    e.preventDefault();
    let proposed;
    let cands = [];
    try {
      proposed = scheduleDupDecode(schedDup.dataset.proposedB64);
      if (schedDup.dataset.candsB64) cands = scheduleDupDecode(schedDup.dataset.candsB64);
    } catch (err) {
      addMsg('kage', 'データの読み取りに失敗しました。', 'error');
      return;
    }
    const act = schedDup.dataset.schedDup;
    const actions = schedDup.closest('.schedule-dup-actions');
    actions?.querySelectorAll('button').forEach(b => (b.disabled = true));
    if (act === 'new') {
      showTyping();
      try {
        const data = await post('/schedule', {
          title: proposed.title,
          date: proposed.date,
          memo: proposed.memo || '',
          confirm_not_duplicate: true,
        });
        hideTyping();
        if (data.saved) {
          addMsg(
            'kage',
            `📅 <strong>${esc(proposed.title)}</strong><br>${fmtDate(proposed.date)}<br>${esc(data.message || '新規に登録しました。')}<br><span class="badge-save">✓ Notion保存済み</span>`,
            'saved'
          );
        } else {
          addMsg('kage', esc(data.message || '保存に失敗しました。'), 'error');
        }
      } catch (err) {
        hideTyping();
        addMsg('kage', 'ボス、通信エラーです。', 'error');
      }
      return;
    }
    if (act === 'merge') {
      if (!cands.length) {
        addMsg('kage', '候補が見つかりませんでした。', 'error');
        return;
      }
      if (cands.length === 1) {
        showTyping();
        try {
          const data = await post('/schedule', {
            title: proposed.title,
            date: proposed.date,
            memo: proposed.memo || '',
            merge_into_page_id: cands[0].page_id,
          });
          hideTyping();
          if (data.saved) {
            addMsg(
              'kage',
              `📅 <strong>${esc(proposed.title)}</strong><br>${fmtDate(proposed.date)}<br>${esc(data.message || 'まとめました。')}<br><span class="badge-save">✓ Notion保存済み</span>`,
              'saved'
            );
          } else {
            addMsg('kage', esc(data.message || 'まとめに失敗しました。'), 'error');
          }
        } catch (err) {
          hideTyping();
          addMsg('kage', 'ボス、通信エラーです。', 'error');
        }
        return;
      }
      const wrap = schedDup.closest('.schedule-dup-wrap');
      const row = wrap?.querySelector('.schedule-dup-actions');
      if (!row) return;
      const pb = scheduleDupEncode(proposed);
      row.innerHTML =
        '<p class="sched-dup-hint">どの予定にまとめますか？（タイトルをタップ）</p><div class="confirm-row" style="flex-direction:column;gap:6px;margin-top:8px">' +
        cands
          .map(
            c =>
              '<button type="button" class="cfm-btn" data-sched-merge-pick data-page-id="' +
              esc(c.page_id) +
              '" data-proposed-b64="' +
              esc(pb) +
              '" style="text-align:left">' +
              esc(c.title) +
              '</button>'
          )
          .join('') +
        '</div>';
      return;
    }
    return;
  }

  const btn = e.target.closest('[data-confirm]');
  if (!btn) return;
  const act  = btn.dataset.confirm;
  const orig = btn.dataset.orig || '';
  btn.closest('.confirm-row')?.remove();
  if (act === 'skip') { addMsg('kage','承知しました。'); return; }
  if (!orig) return;
  showTyping();
  try {
    if (act === 'memo') {
      await post('/memo',{title:orig,content:''});
      hideTyping(); addMsg('kage',`📝 メモとして保存しました。<br><span class="badge-save">✓ Notion保存済み</span>`,'saved');
    } else if (act === 'idea') {
      await post('/idea',{title:orig,content:''});
      hideTyping(); addMsg('kage',`💡 アイデアとして保存しました。<br><span class="badge-save">✓ Notion保存済み</span>`,'saved');
    }
  } catch(e) {
    hideTyping(); addMsg('kage',`ボス、保存に失敗しました。`,'error');
  }
});

// ── Schedule modal ────────────────────────────────
function openSched() {
  schedDate.value = todayStr();
  schedTitle.value = schedMemo.value = '';
  schedModal.classList.add('open');
  setTimeout(()=>schedTitle.focus(),300);
}
function closeSched() { schedModal.classList.remove('open'); }

async function saveSched() {
  const title = schedTitle.value.trim();
  const date  = schedDate.value.trim();
  const memo  = schedMemo.value.trim();
  if (!title||!date) {
    schedTitle.style.borderColor = !title ? 'var(--red)' : '';
    schedDate.style.borderColor  = !date  ? 'var(--red)' : '';
    return;
  }
  schedTitle.style.borderColor = schedDate.style.borderColor = '';
  modalSave.disabled = true;
  closeSched();
  addUser(`予定: ${title}（${date}）${memo?' — '+memo:''}`);
  showTyping();
  try {
    const data = await post('/schedule', { title, date, memo });
    hideTyping();
    if (data.need_schedule_confirmation && data.schedule_candidates && data.schedule_proposed) {
      renderScheduleDupConfirm(data);
    } else if (data.saved) {
      addMsg(
        'kage',
        `📅 <strong>${esc(title)}</strong><br>${fmtDate(date)}<br>${esc(data.message || '')}<br><span class="badge-save">✓ Notion保存済み</span>`,
        'saved'
      );
    } else {
      addMsg('kage', esc(data.message || '保存できませんでした。'), 'error');
    }
  } catch(e) {
    hideTyping(); addMsg('kage',`ボス、保存に失敗しました。`,'error');
  } finally { modalSave.disabled = false; }
}

modalSave.addEventListener('click', saveSched);
modalCancel.addEventListener('click', closeSched);
schedModal.addEventListener('click', e => { if(e.target===schedModal) closeSched(); });
[schedTitle,schedDate,schedMemo].forEach(el =>
  el.addEventListener('keydown', e => { if(e.key==='Enter'){e.preventDefault();saveSched();} })
);

// ── Minutes modal（議事録）────────────────────────
function openMinutes() {
  if (!minTitle || !minWhen || !minutesModal) return;
  minWhen.value = nowLocalDatetimeInputValue();
  minTitle.value = '';
  if (minBody) minBody.value = '';
  minutesModal.classList.add('open');
  setTimeout(() => minTitle.focus(), 300);
}
function closeMinutes() { minutesModal && minutesModal.classList.remove('open'); }

async function saveMinutes() {
  if (!minTitle || !minWhen) return;
  const title = minTitle.value.trim();
  const when = minWhen.value.trim();
  const content = (minBody && minBody.value.trim()) || '';
  if (!title || !when) {
    minTitle.style.borderColor = !title ? 'var(--red)' : '';
    minWhen.style.borderColor = !when ? 'var(--red)' : '';
    return;
  }
  minTitle.style.borderColor = minWhen.style.borderColor = '';
  minutesSave.disabled = true;
  closeMinutes();
  addUser(`議事録: ${title}（${when}）`);
  showTyping();
  try {
    await post('/minutes', { title, when, content });
    hideTyping();
    addMsg('kage',`📋 <strong>${esc(title)}</strong><br>${esc(when)}<br><span class="badge-save">✓ 議事録 DB に保存しました</span>`,'saved');
  } catch (e) {
    hideTyping();
    const detail = esc(String(e.message || e));
    addMsg(
      'kage',
      `ボス、議事録の保存に失敗しました。<br><small style="opacity:.9">${detail}</small>` +
        `<br><small style="opacity:.75">※ Notion の議事録DBは <strong>名前＝タイトル型・内容＝テキスト型</strong>（<code>create_minutes_database.py</code> と同じ）。型エラーなら Notion 側を直すのが一番すっきりします。<code>minutes_db_configured</code> が false のときは <code>NOTION_DB_MINUTES</code> を設定してください。</small>`,
      'error'
    );
  } finally { minutesSave.disabled = false; }
}

if (minutesSave && minutesCancel && minutesModal) {
  minutesSave.addEventListener('click', saveMinutes);
  minutesCancel.addEventListener('click', closeMinutes);
  minutesModal.addEventListener('click', e => { if (e.target === minutesModal) closeMinutes(); });
}

// ── Upcoming modal ────────────────────────────────
btnUpcoming.addEventListener('click', async () => {
  upcomingModal.classList.add('open');
  upcomingBody.innerHTML = '<div class="dots"><span></span><span></span><span></span></div>';
  try {
    const data = await get('/upcoming?days=14');
    renderUpcomingModal(data);
  } catch(e) {
    upcomingBody.innerHTML = `<p class="empty-msg">取得できませんでした。</p>`;
  }
});

function renderUpcomingModal(data) {
  let items = Array.isArray(data) ? data
    : data?.schedules || data?.results || data?.data || [];
  if (!items.length) {
    upcomingBody.innerHTML = '<p class="empty-msg">ボス、直近14日の予定はありません。</p>';
    return;
  }
  let h = '<div class="upcoming-list" style="padding-bottom:4px">';
  items.slice(0,20).forEach(s => {
    const t = s.title||s.Title||s.name||'';
    const d = s.date||s.Date||s.scheduled_at||'';
    const m = s.memo||s.Memo||s.note||'';
    h += `<div class="upcoming-item">
      <div class="item-date">${fmtDate(d)}</div>
      <div class="item-title">${esc(t)}</div>
      ${m?`<div class="item-memo">${esc(m)}</div>`:''}
    </div>`;
  });
  h += '</div>';
  upcomingBody.innerHTML = h;
}

upcomingClose.addEventListener('click', () => upcomingModal.classList.remove('open'));
upcomingModal.addEventListener('click', e => { if(e.target===upcomingModal) upcomingModal.classList.remove('open'); });

// ── Debug log modal（Notion デバッグDB・運用ステータス） ──
/** @type {string} フィルタ: __all__ | 未対応 | 対応中 | 完了 */
let debugListFilter = '__all__';
if (btnDebugList && debugModal && debugBody) {
  async function fetchDebugList() {
    const q = debugListFilter && debugListFilter !== '__all__'
      ? `&status=${encodeURIComponent(debugListFilter)}`
      : '';
    return get(`/debug/recent?limit=40${q}`);
  }
  function renderDebugModal(data) {
    if (data.error) {
      debugBody.innerHTML = `<p class="empty-msg">${esc(data.error)}</p>`;
      return;
    }
    const items = data.items || [];
    const filters = [
      { key: '__all__', label: 'すべて' },
      { key: '未対応', label: '未対応' },
      { key: '対応中', label: '対応中' },
      { key: '完了', label: '完了' },
    ];
    let tb = '<div class="debug-toolbar">';
    filters.forEach(f => {
      const on = debugListFilter === f.key ? ' active' : '';
      tb += `<button type="button" class="debug-filter-btn${on}" data-dbg-filter="${esc(f.key)}">${esc(f.label)}</button>`;
    });
    tb += '</div>';

    if (!items.length) {
      debugBody.innerHTML = tb + '<p class="empty-msg">該当するログがありません。</p>';
      return;
    }
    let h = tb + `<p class="debug-count">${items.length}件（新しい順）</p>`;
    items.forEach(it => {
      const meta = [
        it.status ? esc(it.status) : '',
        it.date ? `日付 ${esc(it.date)}` : '',
        it.created ? esc(it.created) : '',
      ].filter(Boolean).join(' · ');
      const pid = esc(it.page_id || '');
      h += `<div class="debug-item" data-pageid="${pid}">
        <div class="debug-meta">${meta || '—'}</div>
        <div class="debug-item-title">${esc(it.title || '(無題)')}</div>
        ${it.content ? `<div class="debug-content">${esc(it.content)}</div>` : ''}
        ${it.has_context ? `<details class="debug-details"><summary>会話コンテキスト</summary><pre>${esc(it.context || '')}</pre></details>` : ''}
        <div class="debug-actions">
          <span class="debug-actions-label">ステータス</span>
          <button type="button" class="debug-status-btn" data-pageid="${pid}" data-status="未対応">未対応</button>
          <button type="button" class="debug-status-btn" data-pageid="${pid}" data-status="対応中">対応中</button>
          <button type="button" class="debug-status-btn" data-pageid="${pid}" data-status="完了">完了</button>
        </div>
      </div>`;
    });
    debugBody.innerHTML = h;
  }

  btnDebugList.addEventListener('click', async () => {
    debugModal.classList.add('open');
    debugBody.innerHTML = '<div class="dots"><span></span><span></span><span></span></div>';
    try {
      renderDebugModal(await fetchDebugList());
    } catch (e) {
      debugBody.innerHTML = '<p class="empty-msg">取得できませんでした。</p>';
    }
  });

  debugModal.addEventListener('click', async (e) => {
    if (e.target === debugModal) debugModal.classList.remove('open');

    const fb = e.target.closest('.debug-filter-btn');
    if (fb) {
      e.preventDefault();
      e.stopPropagation();
      debugListFilter = fb.dataset.dbgFilter || '__all__';
      debugBody.innerHTML = '<div class="dots"><span></span><span></span><span></span></div>';
      try {
        renderDebugModal(await fetchDebugList());
      } catch (err) {
        debugBody.innerHTML = '<p class="empty-msg">取得できませんでした。</p>';
      }
      return;
    }

    const sb = e.target.closest('.debug-status-btn');
    if (sb) {
      e.preventDefault();
      e.stopPropagation();
      const pageId = sb.dataset.pageid;
      const st = sb.dataset.status;
      sb.disabled = true;
      try {
        await post('/debug/status', { page_id: pageId, status: st });
        renderDebugModal(await fetchDebugList());
      } catch (err) {
        sb.disabled = false;
        alert('ステータス更新に失敗しました');
      }
    }
  });

  debugClose.addEventListener('click', () => debugModal.classList.remove('open'));
}

// ── Model modal ───────────────────────────────────
btnModel.addEventListener('click', async () => {
  modelModal.classList.add('open');
  modelList.innerHTML = '<div class="dots"><span></span><span></span><span></span></div>';
  try {
    const data = await get('/models');
    currentModel = data.current || currentModel;
    renderModelList(data);
  } catch(e) {
    modelList.innerHTML = `<p class="empty-msg">取得できませんでした。</p>`;
  }
});

function renderModelList(data) {
  const models = data.models || [];
  let h = '';
  models.forEach(m => {
    const active = m.id === data.current ? 'active' : '';
    const check  = m.id === data.current ? '<span class="model-check">✓</span>' : '';
    h += `
      <div class="model-item ${active}" data-model="${esc(m.id)}">
        <div>
          <div class="model-name">${esc(m.label)}</div>
          <div class="model-desc">${esc(m.id)}</div>
        </div>
        ${check}
      </div>`;
  });
  modelList.innerHTML = h;

  modelList.querySelectorAll('.model-item').forEach(el => {
    el.addEventListener('click', async () => {
      const modelId = el.dataset.model;
      try {
        await post(`/models/${modelId}`, {});
        currentModel = modelId;
        modelList.querySelectorAll('.model-item').forEach(i => {
          i.classList.toggle('active', i.dataset.model === modelId);
          const chk = i.querySelector('.model-check');
          if (chk) chk.remove();
        });
        el.insertAdjacentHTML('beforeend','<span class="model-check">✓</span>');
        addMsg('kage', `🤖 モデルを <strong>${esc(modelId)}</strong> に切り替えました。`);
        modelModal.classList.remove('open');
      } catch(e) {
        addMsg('kage', `ボス、切り替えに失敗しました。`, 'error');
        modelModal.classList.remove('open');
      }
    });
  });
}

modelClose.addEventListener('click', () => modelModal.classList.remove('open'));
modelModal.addEventListener('click', e => { if(e.target===modelModal) modelModal.classList.remove('open'); });

// ── Reload button ─────────────────────────────────
btnReload.addEventListener('click', () => {
  btnReload.classList.add('spinning');
  setTimeout(() => location.reload(), 300);
});

// ── Archive button handler ────────────────────────
chatArea.addEventListener('click', async e => {
  const btn = e.target.closest('.archive-btn');
  if (!btn) return;
  const pageId = btn.dataset.pageid;
  const title = btn.dataset.title;
  btn.disabled = true; btn.textContent = '処理中…';
  try {
    await post('/archive', {page_id: pageId});
    btn.textContent = `✓ ${title} をアーカイブしました`;
    btn.style.opacity = '0.5';
  } catch(e) {
    btn.textContent = `✗ 失敗: ${title}`;
  }
});

// ── Image input ───────────────────────────────────
const btnImage    = document.getElementById('btnImage');
const imageInput  = document.getElementById('imageInput');
const imagePreview = document.getElementById('imagePreview');
const previewImg  = document.getElementById('previewImg');
const removeImage = document.getElementById('removeImage');

let pendingImage = null;
let pendingMime  = null;

btnImage.addEventListener('click', () => imageInput.click());

imageInput.addEventListener('change', e => {
  const file = e.target.files[0];
  if (!file) return;
  pendingMime = file.type || 'image/jpeg';
  const reader = new FileReader();
  reader.onload = () => {
    const base64 = reader.result.split(',')[1];
    pendingImage = base64;
    previewImg.src = reader.result;
    imagePreview.classList.remove('hidden');
  };
  reader.readAsDataURL(file);
  imageInput.value = '';
});

removeImage.addEventListener('click', () => {
  pendingImage = null;
  pendingMime = null;
  imagePreview.classList.add('hidden');
  previewImg.src = '';
});

// ── Voice input (Web Speech API) ──────────────────
const btnMic = document.getElementById('btnMic');
let recognition = null;
let isRecording = false;

if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRecognition();
  recognition.lang = 'ja-JP';
  recognition.interimResults = true;
  recognition.continuous = false;

  recognition.onresult = (e) => {
    let transcript = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      transcript += e.results[i][0].transcript;
    }
    msgInput.value = transcript;
    autoResize();
  };

  recognition.onend = () => {
    isRecording = false;
    btnMic.classList.remove('recording');
  };

  recognition.onerror = () => {
    isRecording = false;
    btnMic.classList.remove('recording');
  };

  btnMic.addEventListener('click', () => {
    if (isRecording) {
      recognition.stop();
    } else {
      isRecording = true;
      btnMic.classList.add('recording');
      recognition.start();
    }
  });
} else {
  btnMic.style.display = 'none';
}

// ── Input resize ──────────────────────────────────
function autoResize() {
  msgInput.style.height = 'auto';
  msgInput.style.height = Math.min(msgInput.scrollHeight, 110) + 'px';
}
msgInput.addEventListener('input', autoResize);
msgInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
});
btnSend.addEventListener('click', handleSend);

// ── Copy chat log ─────────────────────────────────
document.getElementById('btnCopyPageUrl')?.addEventListener('click', async () => {
  let url = String(location.href).split('#')[0];
  try {
    const h = await get('/health');
    if (h.kage_public_url) {
      url = String(h.kage_public_url).replace(/\/$/, '') + '/';
    }
  } catch (e) { /* 現在のURL */ }
  try {
    await navigator.clipboard.writeText(url);
  } catch (e) {
    const ta = document.createElement('textarea');
    ta.value = url;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
  addMsg(
    'kage',
    'このページのURLをコピーしました。<br><span style="font-size:12px;word-break:break-all;color:var(--dim)">' +
      esc(url) +
      '</span><br><span style="font-size:12px;color:var(--muted)">Notionに貼り付けてご利用ください。</span>'
  );
});

document.getElementById('btnCopyLog').addEventListener('click', () => {
  const rows = chatArea.querySelectorAll('.row');
  const lines = [];
  rows.forEach(row => {
    const isUser = row.classList.contains('user');
    const bubble = row.querySelector('.bubble');
    if (!bubble) return;
    const text = bubble.innerText.trim();
    if (!text) return;
    lines.push(isUser ? `ボス: ${text}` : `影: ${text}`);
  });
  const log = `--- KAGE会話ログ ${new Date().toLocaleString('ja-JP')} ---\n${lines.join('\n')}\n--- END ---`;
  navigator.clipboard.writeText(log).then(() => {
    addMsg('kage', 'ボス、会話ログをクリップボードにコピーしました。');
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = log; document.body.appendChild(ta);
    ta.select(); document.execCommand('copy');
    document.body.removeChild(ta);
    addMsg('kage', 'ボス、会話ログをコピーしました。');
  });
});

// ── Opening line（起動時・Notionを踏まえたひと言） ──
async function showOpeningLine() {
  showTyping();
  try {
    let openUrl = '/opening';
    if (!sessionId) openUrl += '?bootstrap_session=1';
    else openUrl += '?session_id=' + encodeURIComponent(sessionId);
    const data = await get(openUrl);
    hideTyping();
    if (data.session_id) {
      sessionId = data.session_id;
      sessionStorage.setItem('kage_session', sessionId);
    }
    if (data.line) {
      addMsg(
        'kage',
        `<div class="opening-line"><span class="opening-kicker">影</span>${esc(data.line)}</div>`,
        '',
        { noScroll: true }
      );
    }
  } catch (e) {
    hideTyping();
    addMsg(
      'kage',
      '<div class="opening-line"><span class="opening-kicker">影</span>本日もよろしくお願いいたします。</div>',
      '',
      { noScroll: true }
    );
  }
}

// ── Morning briefing ──────────────────────────────
async function showMorningBriefing() {
  const today = todayStr();
  const lastBriefing = localStorage.getItem('kage_morning');
  if (lastBriefing === today) return;

  showTyping();
  try {
    let mUrl = '/morning';
    if (sessionId) mUrl += '?session_id=' + encodeURIComponent(sessionId);
    const data = await get(mUrl);
    hideTyping();
    if (data.message) {
      const sections = data.message.split(/(?=【)/);
      let html = '';
      for (const section of sections) {
        const trimmed = section.trim();
        if (!trimmed) continue;
        const match = trimmed.match(/^【(.+?)】(.*)$/s);
        if (match) {
          html += '<div class="think-section-title">' + esc(match[1]) + '</div>';
          const lines = match[2].trim().split('\n').filter(l => l.trim());
          for (const line of lines) {
            html += '<div class="think-item">' + esc(line) + '</div>';
          }
        } else {
          html += '<div class="think-item">' + esc(trimmed) + '</div>';
        }
      }
      let newsBlock = '';
      if (data.news && data.news.enabled && data.news.items && data.news.items.length) {
        let sum =
          '📰 本日のRSSリンク（' + esc(String(data.news.items.length)) + '件）';
        const top = data.news.interest && data.news.interest.top_terms;
        if (top && top.length) {
          sum +=
            ' · 興味: ' +
            esc(top.slice(0, 6).join(', ')) +
            (top.length > 6 ? '…' : '');
        }
        newsBlock =
          '<details class="morning-news-links"><summary>' +
          sum +
          '</summary><div class="morning-news-body">';
        data.news.items.slice(0, 10).forEach(it => {
          const t = esc(it.title || '');
          const u = esc(it.link || '#');
          newsBlock +=
            '<div class="morning-news-row"><a href="' +
            u +
            '" target="_blank" rel="noopener noreferrer">' +
            t +
            '</a><span class="morning-news-src">' +
            esc(it.source || '') +
            '</span></div>';
        });
        newsBlock += '</div></details>';
      }
      addMsg(
        'kage',
        '<div class="think-section">' + (html || esc(data.message)) + '</div>' + newsBlock,
        '',
        { noScroll: true }
      );
      if (data.news_feedback_prompt) {
        addMsg(
          'kage',
          '<div class="news-feedback-invite">ひとつだけ教えてください。今朝のニュースの出し方、'
            + '「もっと見たいテーマ」と「減らしたいテーマ」はありますか？'
            + '<span class="news-feedback-hint">（「特にない」でも大丈夫です）</span></div>',
          '',
          { noScroll: true }
        );
      }
      if (!String(data.message).includes('APIキーが未設定')) {
        localStorage.setItem('kage_morning', today);
      }
    }
  } catch(e) {
    hideTyping();
  }
}

// ── Init ──────────────────────────────────────────
(async function bootKage() {
  if (headerDate) headerDate.textContent = fmtDateHeader();
  showWelcome();
  await showOpeningLine();
  await showMorningBriefing();
  // 長い起動メッセージで末尾へ飛ぶと日付・時刻が見切れるので、常に先頭から読めるようにする
  requestAnimationFrame(() => {
    chatArea.scrollTop = 0;
  });
})();
