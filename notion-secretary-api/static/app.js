// Go_KAGE Frontend
const API = location.origin;
let attachedImage = null;   // {base64, mimeType, dataUrl}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

async function sendMessage() {
  const input = document.getElementById("msgInput");
  const text = input.value.trim();
  if (!text && !attachedImage) return;

  // Show user message
  const userHtml = escapeHtml(text);
  if (attachedImage) {
    addMessage("user", userHtml + '<img src="' + attachedImage.dataUrl + '" alt="attached">');
  } else {
    addMessage("user", userHtml);
  }

  input.value = "";
  autoResize(input);

  const body = { message: text || "この画像について教えて" };
  if (attachedImage) {
    body.image = attachedImage.base64;
    body.mime_type = attachedImage.mimeType;
  }
  removeImage();

  const loadingEl = addMessage("bot", "...", "loading");

  try {
    const res = await fetch(API + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    loadingEl.remove();
    addMessage("bot", escapeHtml(data.message || data.detail || "エラーが発生しました"));
  } catch (e) {
    loadingEl.remove();
    addMessage("bot", "通信エラーが発生しました");
  }
}

// ---------------------------------------------------------------------------
// Think (整理ボタン)
// ---------------------------------------------------------------------------

async function doThink() {
  const btn = document.getElementById("thinkBtn");
  btn.disabled = true;
  btn.textContent = "考え中...";

  const loadingEl = addMessage("bot", "Notionデータを分析中...", "loading");

  try {
    const res = await fetch(API + "/think", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const data = await res.json();
    loadingEl.remove();
    renderThinkResult(data.message || "データなし");
  } catch (e) {
    loadingEl.remove();
    addMessage("bot", "整理に失敗しました。通信エラーです。");
  } finally {
    btn.disabled = false;
    btn.textContent = "\u{1F9E0} 整理";
  }
}

function renderThinkResult(text) {
  const chatArea = document.getElementById("chatArea");
  const div = document.createElement("div");
  div.className = "think-result";

  // Parse sections
  const sections = text.split(/(?=【)/);
  let html = "";

  for (const section of sections) {
    const trimmed = section.trim();
    if (!trimmed) continue;

    const match = trimmed.match(/^【(.+?)】(.*)$/s);
    if (match) {
      const title = match[1];
      const body = match[2].trim();
      html += '<div class="section-title">' + escapeHtml(title) + "</div>";

      if (title === "今すぐやること") {
        html += '<div class="highlight">' + escapeHtml(body) + "</div>";
      } else {
        const lines = body.split("\n").filter((l) => l.trim());
        for (const line of lines) {
          html += '<div class="item">' + escapeHtml(line) + "</div>";
        }
      }
    } else {
      html += '<div class="item">' + escapeHtml(trimmed) + "</div>";
    }
  }

  div.innerHTML = html || '<div class="item">' + escapeHtml(text) + "</div>";
  chatArea.appendChild(div);
  chatArea.scrollTop = chatArea.scrollHeight;
}

// ---------------------------------------------------------------------------
// Image
// ---------------------------------------------------------------------------

function handleImage(event) {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = function (e) {
    const dataUrl = e.target.result;
    const base64 = dataUrl.split(",")[1];
    attachedImage = {
      base64: base64,
      mimeType: file.type || "image/jpeg",
      dataUrl: dataUrl,
    };

    document.getElementById("previewImg").src = dataUrl;
    document.getElementById("imagePreview").classList.add("active");
  };
  reader.readAsDataURL(file);
  event.target.value = "";
}

function removeImage() {
  attachedImage = null;
  document.getElementById("imagePreview").classList.remove("active");
  document.getElementById("previewImg").src = "";
}

// ---------------------------------------------------------------------------
// UI Helpers
// ---------------------------------------------------------------------------

function addMessage(role, html, extraClass) {
  const chatArea = document.getElementById("chatArea");
  const div = document.createElement("div");
  div.className = "msg " + role + (extraClass ? " " + extraClass : "");
  div.innerHTML = html;
  chatArea.appendChild(div);
  chatArea.scrollTop = chatArea.scrollHeight;
  return div;
}

function escapeHtml(text) {
  const d = document.createElement("div");
  d.textContent = text;
  return d.innerHTML;
}

function autoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

// Enter to send (Shift+Enter for newline)
document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById("msgInput");
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
});
