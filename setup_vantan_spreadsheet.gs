/**
 * バンタンスプレッドシート初期設定
 * 既存スプレッドシートに2シート（運用データ・API設定）を作成・設定する
 *
 * バージョン: 2.0.0
 * 更新日: 2026-03-17
 *
 * 列構成は run_vantan_workflow.gs の COL 定数と一致させること
 */
function setupVantanSpreadsheet() {
  var SPREADSHEET_ID = '1yQHYqnhVG1rTiQKHjznMM4NBIP43e03p1dxJpy3rubc';
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);

  setupSheet1OperationData(ss);
  setupSheet2ApiConfig(ss);

  Logger.log('セットアップ完了');
}

/**
 * シート1：運用データ
 * GASから Dify API に渡すデータはこの1シートに全て入れる
 */
function setupSheet1OperationData(ss) {
  var sheetName = '運用データ';
  var sheet = getOrCreateSheet(ss, sheetName);

  sheet.clear();
  var headers = [
    'チェック',           // A: ✓を入れると実行対象
    'スクール名称',       // B: = Dify product_name
    'ターゲット',         // C: = Dify subject (20代女性 etc.)
    'スクール概要',       // D: = Dify school_overview
    '訴求ポイント',       // E: = Dify appeal_points
    'キーメッセージ',     // F: = Dify key_message
    '演出キーワード',     // G: = Dify keywords
    '季節',               // H: = Dify season (春夏/秋冬)
    'ナレーション属性',   // I: = Dify voice_type
    'ナレーション台本',   // J: = Dify script (スラッシュ区切り・空欄でGemini自動生成)
    'ロゴURL',            // K: = Dify logo_url
    '注釈',               // L: = Dify annotation_text
    '反映率',             // M: = Dify reflection_rate (デフォルト50)
    'ステータス',         // N: 自動入力（実行中/完了/エラー）
    '動画URL'             // O: 自動入力
  ];

  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length)
    .setBackground('#434343')
    .setFontColor('#ffffff')
    .setFontWeight('bold');
  sheet.setFrozenRows(1);

  // 列幅調整
  sheet.setColumnWidth(1, 70);   // チェック
  sheet.setColumnWidth(2, 180);  // スクール名称
  sheet.setColumnWidth(3, 100);  // ターゲット
  sheet.setColumnWidth(4, 250);  // スクール概要
  sheet.setColumnWidth(5, 200);  // 訴求ポイント
  sheet.setColumnWidth(6, 150);  // キーメッセージ
  sheet.setColumnWidth(7, 150);  // 演出キーワード
  sheet.setColumnWidth(8, 70);   // 季節
  sheet.setColumnWidth(9, 120);  // ナレーション属性
  sheet.setColumnWidth(10, 300); // ナレーション台本
  sheet.setColumnWidth(11, 250); // ロゴURL
  sheet.setColumnWidth(12, 200); // 注釈
  sheet.setColumnWidth(13, 70);  // 反映率
  sheet.setColumnWidth(14, 80);  // ステータス
  sheet.setColumnWidth(15, 350); // 動画URL

  // ターゲット列にプルダウン
  var targetRule = SpreadsheetApp.newDataValidation()
    .requireValueInList(['20代女性', '30代女性', '40代女性', '50代女性', '20代男性', '30代男性', '40代男性', '50代男性'])
    .setAllowInvalid(false)
    .build();
  sheet.getRange(2, 3, 100, 1).setDataValidation(targetRule);

  // 季節列にプルダウン
  var seasonRule = SpreadsheetApp.newDataValidation()
    .requireValueInList(['春夏', '秋冬'])
    .setAllowInvalid(false)
    .build();
  sheet.getRange(2, 8, 100, 1).setDataValidation(seasonRule);

  // ナレーション属性列にプルダウン
  var voiceRule = SpreadsheetApp.newDataValidation()
    .requireValueInList(['女性1', '女の子1', '女の子2', '男性', '男の子', 'おじさん', '怪獣', 'キャラクター'])
    .setAllowInvalid(false)
    .build();
  sheet.getRange(2, 9, 100, 1).setDataValidation(voiceRule);

  // 反映率にデフォルト値50
  sheet.getRange(2, 13, 100, 1).setValue(50);
}

/**
 * シート2：API設定
 * Dify の URL と Key だけ入れればOK
 */
function setupSheet2ApiConfig(ss) {
  var sheetName = 'API設定';
  var sheet = getOrCreateSheet(ss, sheetName);

  sheet.clear();
  var items = [
    ['DIFY_API_URL', '（例: https://api.dify.ai/v1）'],
    ['DIFY_API_KEY', '（Difyで発行したAPIキーを貼り付け）']
  ];

  sheet.getRange(1, 1, items.length, 2).setValues(items);
  sheet.getRange(1, 1, items.length, 1)
    .setBackground('#434343')
    .setFontColor('#ffffff')
    .setFontWeight('bold');

  sheet.setColumnWidth(1, 200);
  sheet.setColumnWidth(2, 500);
}

function getOrCreateSheet(ss, name) {
  var sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
  }
  return sheet;
}
