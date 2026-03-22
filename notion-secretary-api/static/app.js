'use strict';

const API     = location.origin;
const VERSION = 'v0.9';
const BUILD   = '2026-03-23';

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

const upcomingModal = document.getElementById('upcomingModal');
const upcomingBody  = document.getElementById('upcomingBody');
const upcomingClose = document.getElementById('upcomingClose');
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
/** ウェルカム用: 端末ロケールの「今日」と現在時刻（秘書の第一声用） */
function fmtWelcomeClock() {
  const d = new Date();
  const dateStr = d.toLocaleDateString('ja-JP', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
  });
  const timeStr = d.toLocaleTimeString('ja-JP', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
  return { dateStr, timeStr };
}
function todayStr() { return new Date().toISOString().slice(0,10); }
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
function addMsg(role, html, cls='') {
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
  scrollEnd();
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
  const { dateStr, timeStr } = fmtWelcomeClock();
  addMsg('kage', `
    <div class="welcome">
      <div class="welcome-clock" aria-label="今日の日付と現在時刻">
        <div class="wc-label">本日</div>
        <div class="wc-date">${esc(dateStr)}</div>
        <div class="wc-time">${esc(timeStr)}</div>
      </div>
      <strong>${g}、ボス。</strong><br>
      影がNotionの管理をサポートいたします。<br><br>
      📝 メモ・💡 アイデア → 保存<br>
      📅 予定ボタン → 日時つきで保存<br>
      🧠 整理ボタン → タスクを整理<br>
      🐛 バグボタン → 不具合をNotionに記録<br>
      📆 右上カレンダー → 今後の予定確認
    </div>
  `);
}

// ── API ───────────────────────────────────────────
async function post(path, body) {
  const r = await fetch(`${API}${path}`,{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
async function get(path) {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// ── Response renderer ─────────────────────────────
const BADGE = { memo:'📝 メモ', idea:'💡 アイデア', task:'✅ タスク', schedule:'📅 予定', profile:'🧠 記憶', done:'🗑️ 完了', debug:'🐛 バグ報告' };

function renderResponse(data, originalText) {
  const { intent, message, saved } = data;

  if (saved === true || ['memo','idea','task','schedule','profile','debug'].includes(intent)) {
    const b = BADGE[intent] ? `<span class="badge-intent">${BADGE[intent]}</span><br>` : '';
    addMsg('kage', `${b}${esc(message||'保存しました。')}<br><span class="badge-save">✓ Notion保存済み</span>`, 'saved');
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

  addMsg('kage', esc(message||'承知しました。'));
}

// ── Think result renderer ─────────────────────────
function renderThinkResult(text) {
  const sections = text.split(/(?=【)/);
  let html = '';

  for (const section of sections) {
    const trimmed = section.trim();
    if (!trimmed) continue;

    const match = trimmed.match(/^【(.+?)】(.*)$/s);
    if (match) {
      const title = match[1];
      const body = match[2].trim();
      html += '<div class="think-section-title">' + esc(title) + '</div>';

      if (title === '今すぐ') {
        html += '<div class="think-highlight">' + esc(body) + '</div>';
      } else {
        const lines = body.split('\n').filter(l => l.trim());
        for (const line of lines) {
          html += '<div class="think-item">' + esc(line) + '</div>';
        }
      }
    } else {
      html += '<div class="think-item">' + esc(trimmed) + '</div>';
    }
  }

  addMsg('kage', '<div class="think-section">' + (html || esc(text)) + '</div>');
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
    thumb.style.cssText = 'max-height:80px;border-radius:6px;margin-top:4px;display:block';
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
    await post('/schedule',{title,date,memo});
    hideTyping();
    addMsg('kage',`📅 <strong>${esc(title)}</strong><br>${fmtDate(date)}<br><span class="badge-save">✓ Notion保存済み</span>`,'saved');
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
    const data = await get('/opening');
    hideTyping();
    if (data.line) {
      addMsg('kage', `<div class="opening-line"><span class="opening-kicker">影</span>${esc(data.line)}</div>`);
    }
  } catch (e) {
    hideTyping();
    addMsg('kage', '<div class="opening-line"><span class="opening-kicker">影</span>本日もよろしくお願いいたします。</div>');
  }
}

// ── Morning briefing ──────────────────────────────
async function showMorningBriefing() {
  const today = todayStr();
  const lastBriefing = localStorage.getItem('kage_morning');
  if (lastBriefing === today) return;

  showTyping();
  try {
    const data = await get('/morning');
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
      addMsg('kage', '<div class="think-section">' + (html || esc(data.message)) + '</div>');
    }
    localStorage.setItem('kage_morning', today);
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
})();
