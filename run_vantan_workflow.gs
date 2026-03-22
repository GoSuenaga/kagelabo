/**
 * バンタン運用データワークフロー起動スクリプト
 *
 * バージョン: 2.0.0
 * 更新日: 2026-03-17
 *
 * 概要:
 * - スプシに✓を入れる → メニュー「Vantan」→「✓の行を実行」で、Difyの動画生成ワークフローを実行
 * - 実行後、ステータス列とURL列を自動で書き込む
 *
 * ■ Dify API の設定（API設定シートのB列にコピペするだけ）
 * 1. Dify で該当ワークフローを開く
 * 2. 右上「API アクセス」または「公開」→「API」タブを開く
 * 3. 「エンドポイント」のURL → API設定シートの DIFY_API_URL のB列（末尾は /v1 まで）
 * 4. 「API キー」を発行 → API設定シートの DIFY_API_KEY のB列
 */

var VANTAN_SPREADSHEET_ID = '1yQHYqnhVG1rTiQKHjznMM4NBIP43e03p1dxJpy3rubc';
var VANTAN_SHEET_OPERATION = '運用データ';
var VANTAN_SHEET_API_CONFIG = 'API設定';

// 列インデックス（0始まり） - setup_vantan_spreadsheet.gs のヘッダーと一致させること
var COL = {
  CHECK: 0,          // A: チェック
  SCHOOL_NAME: 1,    // B: スクール名称
  TARGET: 2,         // C: ターゲット（人物属性）
  OVERVIEW: 3,       // D: スクール概要
  APPEAL: 4,         // E: 訴求ポイント
  KEY_MSG: 5,        // F: キーメッセージ
  KEYWORDS: 6,       // G: 演出キーワード
  SEASON: 7,         // H: 季節
  VOICE: 8,          // I: ナレーション属性
  SCRIPT: 9,         // J: ナレーション台本
  LOGO_URL: 10,      // K: ロゴURL
  ANNOTATION: 11,    // L: 注釈
  REFLECTION: 12,    // M: 反映率
  STATUS: 13,        // N: ステータス
  VIDEO_URL: 14      // O: 動画URL
};

var NUM_COLS = 15; // A〜O列

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Vantan')
    .addItem('✓の行を実行', 'runCheckedRows')
    .addToUi();
}

function runCheckedRows() {
  var ss = SpreadsheetApp.openById(VANTAN_SPREADSHEET_ID);
  var sheet = ss.getSheetByName(VANTAN_SHEET_OPERATION);
  if (!sheet) {
    throw new Error('シート「' + VANTAN_SHEET_OPERATION + '」が見つかりません。');
  }

  var apiConfig = getDifyApiConfig(ss);
  var apiUrl = apiConfig.url;
  var apiKey = apiConfig.key;

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  var startRow = 2;
  var values = sheet.getRange(startRow, 1, lastRow - 1, NUM_COLS).getValues();

  for (var i = 0; i < values.length; i++) {
    var row = values[i];
    var check = String(row[COL.CHECK]).trim();
    var status = String(row[COL.STATUS]).trim();

    if (check !== '✓') continue;
    if (status === '完了') continue;

    var rowNum = startRow + i;

    // Dify ワークフロー入力変数を組み立て
    var inputs = {
      product_name: String(row[COL.SCHOOL_NAME] || '').trim(),
      subject: String(row[COL.TARGET] || '20代女性').trim(),
      school_overview: String(row[COL.OVERVIEW] || '').trim(),
      appeal_points: String(row[COL.APPEAL] || '').trim(),
      key_message: String(row[COL.KEY_MSG] || '').trim(),
      keywords: String(row[COL.KEYWORDS] || '').trim(),
      season: String(row[COL.SEASON] || '春夏').trim(),
      voice_type: String(row[COL.VOICE] || '女性1').trim(),
      script: String(row[COL.SCRIPT] || '').trim(),
      logo_url: String(row[COL.LOGO_URL] || '').trim(),
      annotation_text: String(row[COL.ANNOTATION] || '').trim(),
      reflection_rate: Number(row[COL.REFLECTION]) || 50
    };

    sheet.getRange(rowNum, COL.STATUS + 1).setValue('実行中');
    SpreadsheetApp.flush();

    try {
      var result = callDifyWorkflow(apiUrl, apiKey, inputs);
      sheet.getRange(rowNum, COL.STATUS + 1, 1, 2).setValues([['完了', result.videoUrl]]);
    } catch (e) {
      sheet.getRange(rowNum, COL.STATUS + 1).setValue('エラー: ' + String(e).substring(0, 80));
    }
  }
}

/**
 * API設定シートから Dify の URL と Key を取得
 */
function getDifyApiConfig(ss) {
  var sheet = ss.getSheetByName(VANTAN_SHEET_API_CONFIG);
  if (!sheet) {
    throw new Error('シート「' + VANTAN_SHEET_API_CONFIG + '」が見つかりません。');
  }

  var lastRow = sheet.getLastRow();
  if (lastRow < 1) {
    throw new Error('API設定シートにデータがありません。');
  }

  var values = sheet.getRange(1, 1, lastRow, 2).getValues();
  var url = null;
  var key = null;

  for (var i = 0; i < values.length; i++) {
    var name = String(values[i][0]).trim();
    var value = String(values[i][1]).trim();
    if (name === 'DIFY_API_URL') url = value;
    else if (name === 'DIFY_API_KEY') key = value;
  }

  if (!url) throw new Error('API設定に DIFY_API_URL が未設定です。');
  if (!key) throw new Error('API設定に DIFY_API_KEY が未設定です。');

  return { url: url, key: key };
}

/**
 * Dify ワークフロー実行 API を呼び出す
 * https://docs.dify.ai/guides/workflow/api
 *
 * POST {base_url}/v1/workflows/run
 * Body: { "inputs": {...}, "response_mode": "blocking", "user": "..." }
 */
function callDifyWorkflow(baseUrl, apiKey, inputs) {
  var endpoint = baseUrl.replace(/\/+$/, '') + '/workflows/run';

  var body = {
    inputs: inputs,
    response_mode: 'blocking',
    user: 'vantan-spreadsheet'
  };

  var options = {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'Authorization': 'Bearer ' + apiKey
    },
    payload: JSON.stringify(body),
    muteHttpExceptions: true
  };

  var response = UrlFetchApp.fetch(endpoint, options);
  var code = response.getResponseCode();
  var responseText = response.getContentText();

  if (code < 200 || code >= 300) {
    throw new Error('Dify API ' + code + ': ' + responseText.substring(0, 200));
  }

  var json;
  try {
    json = JSON.parse(responseText);
  } catch (e) {
    throw new Error('JSONパース失敗: ' + responseText.substring(0, 200));
  }

  // Dify blocking mode レスポンス:
  // { "data": { "outputs": { "result": "動画URL" }, "status": "succeeded" } }
  var videoUrl = '';
  if (json.data && json.data.outputs) {
    videoUrl = json.data.outputs.result || '';
  }

  if (json.data && json.data.status === 'failed') {
    var errMsg = (json.data.error || 'ワークフロー実行失敗').substring(0, 100);
    throw new Error(errMsg);
  }

  return {
    raw: json,
    videoUrl: videoUrl
  };
}
