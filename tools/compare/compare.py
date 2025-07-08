import yaml
import difflib
from pathlib import Path
from datetime import datetime

# --- 定数定義 ---
CONFIG_FILE = 'compare_list.yml'
LOG_DIR = 'log'
# 詳細な差分を表示する行数の上限
DIFF_DETAIL_THRESHOLD = 100
# 比較対象のファイルパターン
FILE_PATTERNS = [
    'detail_*',
    'summary_*',
    'trade_history_*',
    'all_detail_*',
    'all_recommend_*',
    'all_summary_*',
    'all_trade_history_*',
]

# --- グローバル変数 (ログファイルパス) ---
log_file_path = None

def log_message(status: str, message: str, detail: str = ""):
    """コンソールとログファイルにメッセージを出力する"""
    global log_file_path
    
    console_msg = f"[{status}] {message}"
    print(console_msg)
    
    if log_file_path:
        with log_file_path.open('a', encoding='utf-8') as f:
            f.write(console_msg + "\n")
            if detail:
                f.write(detail + "\n\n")

def compare_files(source_file: Path, target_file: Path):
    """2つのファイルを比較し、結果をログに出力する"""
    log_subject = f"{source_file}  <->  {target_file}"
    try:
        with source_file.open('r', encoding='utf-8') as f1:
            source_content = f1.read()
        with target_file.open('r', encoding='utf-8') as f2:
            target_content = f2.read()
            
    except Exception as e:
        log_message("ERROR", log_subject, detail=f"  -> ファイル読み込みエラー: {e}")
        return

    # 1. 高速な完全一致チェック
    if source_content == target_content:
        log_message("OK", log_subject)
        return

    # ▼▼▼ 変更箇所 ▼▼▼
    # 内容が異なる場合、まず高速なSequenceMatcherで差分行数を計算
    source_lines = source_content.splitlines()
    target_lines = target_content.splitlines()
    
    matcher = difflib.SequenceMatcher(None, source_lines, target_lines, autojunk=False)
    
    diff_line_count = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            # 置換は旧ファイル(+)と新ファイル(-)の両方の行数をカウント
            diff_line_count += (i2 - i1) + (j2 - j1)
        elif tag == 'delete':
            diff_line_count += (i2 - i1)
        elif tag == 'insert':
            diff_line_count += (j2 - j1)

    # 2. 差分行数に応じて処理を分岐
    if diff_line_count <= DIFF_DETAIL_THRESHOLD:
        # しきい値以下の場合は、詳細な差分をDifferで生成
        differ = difflib.Differ()
        diff_result = list(differ.compare(source_lines, target_lines))
        diff_lines = [line for line in diff_result if line.startswith('+ ') or line.startswith('- ')]
        diff_detail = "\n".join(diff_lines)
        log_message("NG", log_subject, detail=diff_detail)
    else:
        # しきい値を超える場合は、概要メッセージのみ表示
        summary = f"  -> 差分が{DIFF_DETAIL_THRESHOLD}行を超えています ({diff_line_count}行)。詳細な差分表示はスキップします。"
        log_message("NG", log_subject, detail=summary)
    # ▲▲▲ 変更箇所 ▲▲▲


def main():
    """メイン処理"""
    global log_file_path

    # 1. ログフォルダとログファイルの準備
    log_dir = Path(LOG_DIR)
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = log_dir / f"compare_{timestamp}.log"
    
    print(f"ログファイル: {log_file_path}")
    print("-" * 40)

    # 2. 設定ファイルの読み込み
    config_path = Path(CONFIG_FILE)
    if not config_path.is_file():
        log_message("ERROR", f"設定ファイル ({CONFIG_FILE}) が見つかりません。")
        return

    try:
        with config_path.open('r', encoding='utf-8') as f:
            compare_list = yaml.safe_load(f)
        if not isinstance(compare_list, list):
            raise yaml.YAMLError("設定ファイルはリスト形式で記述してください。")
    except yaml.YAMLError as e:
        log_message("ERROR", f"{CONFIG_FILE} の形式が正しくありません。", detail=str(e))
        return
    
    if not compare_list:
        log_message("INFO", "比較対象が設定されていません。")
        return

    # 3. 比較処理の実行
    for item in compare_list:
        source_dir = Path(item.get('source', ''))
        target_dir = Path(item.get('target', ''))

        if not source_dir.is_dir() or not target_dir.is_dir():
            if not source_dir.is_dir():
                log_message("ERROR", f"比較元ディレクトリが存在しません: {source_dir}")
            if not target_dir.is_dir():
                log_message("ERROR", f"比較先ディレクトリが存在しません: {target_dir}")
            continue
        
        header = f"比較中: {source_dir} <-> {target_dir}"
        print(f"\n{header}")
        with log_file_path.open('a', encoding='utf-8') as f:
            f.write(f"\n# {header}\n")
        
        for pattern in FILE_PATTERNS:
            source_files = list(source_dir.glob(pattern))
            target_files = list(target_dir.glob(pattern))

            if len(source_files) == 1 and len(target_files) == 1:
                compare_files(source_files[0], target_files[0])
            elif len(source_files) > 1 or len(target_files) > 1:
                detail = (f"  -> 比較対象を特定できません。\n"
                          f"     - source ({len(source_files)}件): {[f.name for f in source_files]}\n"
                          f"     - target ({len(target_files)}件): {[f.name for f in target_files]}")
                log_message("WARN", f"パターン '{pattern}'", detail=detail)
            elif len(source_files) > 0 and len(target_files) == 0:
                detail = f"  -> {source_dir} にはファイルがありますが、{target_dir} には見つかりません。"
                log_message("SKIP", f"パターン '{pattern}'", detail=detail)
            elif len(source_files) == 0 and len(target_files) > 0:
                detail = f"  -> {target_dir} にはファイルがありますが、{source_dir} には見つかりません。"
                log_message("SKIP", f"パターン '{pattern}'", detail=detail)
            else:
                pass

    print("-" * 40)
    print("比較処理が完了しました。")

if __name__ == "__main__":
    main()