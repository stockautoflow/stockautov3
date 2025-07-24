import yaml
import difflib
from pathlib import Path
from datetime import datetime
import sys
import os

# --- 表示用の設定 ---
class AnsiColors:
    """コンソール出力に色を付けるためのANSIエスケープコード"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    GREY = '\033[90m'
    ENDC = '\033[0m'

    @staticmethod
    def initialize():
        """WindowsでANSIエスケープコードを有効にする"""
        if sys.platform == "win32":
            os.system("")

class ComparisonStats:
    """比較結果をカウントするためのクラス"""
    def __init__(self):
        self.ok = 0
        self.ng = 0
        self.skip = 0
        self.warn = 0
        self.error = 0
        self.info = 0

    def increment(self, status: str):
        status_map = {
            "OK": "ok", "NG": "ng", "SKIP": "skip",
            "WARN": "warn", "ERROR": "error", "INFO": "info"
        }
        attr = status_map.get(status.upper())
        if attr:
            setattr(self, attr, getattr(self, attr) + 1)

# --- 定数定義 ---
CONFIG_FILE = 'compare_list.yml'
LOG_DIR = 'log'
DIFF_DETAIL_THRESHOLD = 100
CONSOLE_DIFF_THRESHOLD = 10
FILE_PATTERNS = [
    'detail_*', 'summary_*', 'trade_history_*',
    'all_detail_*', 'all_recommend_*', 'all_summary_*', 'all_trade_history_*'
]
log_file_path = None

def log_message(stats: ComparisonStats, status: str, message: str, detail: str = "", indent_level=1):
    """視覚的に整形されたメッセージをコンソールとログファイルに出力する"""
    global log_file_path
    stats.increment(status)

    indent = "  " * indent_level
    status_map = {
        "OK":    (AnsiColors.GREEN,  "✅"), "NG":    (AnsiColors.RED,    "❌"),
        "SKIP":  (AnsiColors.GREY,   "⏭️ "), "WARN":  (AnsiColors.YELLOW, "⚠️ "),
        "ERROR": (AnsiColors.RED,    "🛑"), "INFO":  (AnsiColors.BLUE,   "ℹ️ ")
    }
    color, emoji = status_map.get(status, (AnsiColors.ENDC, ""))

    # コンソールへの出力 (色付き)
    console_msg = f"{indent}{color}{emoji} [{status}]{AnsiColors.ENDC} {message}"
    print(console_msg)
    if detail and status not in ["OK", "NG"]:
        for line in detail.splitlines():
            print(f"{indent}  {AnsiColors.GREY}{line}{AnsiColors.ENDC}")

    # ログファイルへの出力 (プレーンテキスト)
    file_msg = f"[{status}] {message}"
    if log_file_path:
        with log_file_path.open('a', encoding='utf-8') as f:
            f.write("  " * (indent_level -1) + file_msg + "\n")
            if detail:
                f.write(detail + "\n\n")

def print_diff(diff_detail: str, indent_level=2):
    """色付けされた差分をコンソールに表示する"""
    indent = "  " * indent_level
    print(f"{indent}┌─── 差分詳細 ───────")
    for line in diff_detail.splitlines():
        color = AnsiColors.GREEN if line.startswith('+ ') else AnsiColors.RED
        print(f"{indent}│ {color}{line}{AnsiColors.ENDC}")
    print(f"{indent}└────────────────────")

def print_summary(stats: ComparisonStats):
    """最終的な集計レポートを表示する"""
    total = stats.ok + stats.ng + stats.skip + stats.warn + stats.error
    print("\n" + "="*50)
    print("📋 比較結果サマリー")
    print("="*50)
    print(f"  {AnsiColors.GREEN}✅ 一致 (OK)    :{stats.ok:>5} 件{AnsiColors.ENDC}")
    print(f"  {AnsiColors.RED}❌ 不一致 (NG)  :{stats.ng:>5} 件{AnsiColors.ENDC}")
    print(f"  {AnsiColors.GREY}⏭️ スキップ     :{stats.skip:>5} 件{AnsiColors.ENDC}")
    print(f"  {AnsiColors.YELLOW}⚠️ 警告 (WARN)  :{stats.warn:>5} 件{AnsiColors.ENDC}")
    print(f"  {AnsiColors.RED}🛑 エラー       :{stats.error:>5} 件{AnsiColors.ENDC}")
    print("-"*50)
    print(f"  合計           :{total:>5} 件")
    print("="*50)

def compare_files(stats: ComparisonStats, source_file: Path, target_file: Path):
    """2つのファイルを比較し、結果をログに出力する"""
    log_subject = f"{source_file.name}  <->  {target_file.name}"
    try:
        source_content = source_file.read_text(encoding='utf-8')
        target_content = target_file.read_text(encoding='utf-8')
    except Exception as e:
        log_message(stats, "ERROR", log_subject, detail=f"ファイル読み込みエラー: {e}", indent_level=2)
        return

    if source_content == target_content:
        log_message(stats, "OK", log_subject, indent_level=2)
        return

    source_lines = source_content.splitlines()
    target_lines = target_content.splitlines()
    matcher = difflib.SequenceMatcher(None, source_lines, target_lines, autojunk=False)
    diff_line_count = sum(max(i2-i1, j2-j1) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != 'equal')

    if diff_line_count <= DIFF_DETAIL_THRESHOLD:
        differ = difflib.Differ()
        diff_result = list(differ.compare(source_lines, target_lines))
        diff_lines = [line for line in diff_result if line.startswith(('+ ', '- '))]
        diff_detail = "\n".join(diff_lines)
        log_message(stats, "NG", log_subject, detail=diff_detail, indent_level=2)
        if 0 < diff_line_count <= CONSOLE_DIFF_THRESHOLD:
            print_diff(diff_detail, indent_level=2)
    else:
        summary = f"差分が{DIFF_DETAIL_THRESHOLD}行を超えています ({diff_line_count}行)。詳細はログファイルを確認してください。"
        log_message(stats, "NG", log_subject, detail=summary, indent_level=2)

def find_latest_file(files: list[Path]) -> Path | None:
    if not files: return None
    return max(files, key=lambda f: f.stat().st_mtime)

def find_latest_subdir(parent_dir: Path) -> Path | None:
    try:
        subdirs = [d for d in parent_dir.iterdir() if d.is_dir() and d.name != 'source']
        if not subdirs: return None
        return max(subdirs, key=lambda d: d.stat().st_ctime)
    except FileNotFoundError:
        return None

def main():
    """メイン処理"""
    global log_file_path
    AnsiColors.initialize()
    stats = ComparisonStats()

    log_dir = Path(LOG_DIR)
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = log_dir / f"compare_{timestamp}.log"
    print(f"ログファイル: {log_file_path}")

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            compare_list = yaml.safe_load(f)
        if not isinstance(compare_list, list): raise yaml.YAMLError()
    except Exception:
        log_message(stats, "ERROR", f"設定ファイル '{CONFIG_FILE}' の読み込みに失敗しました。")
        print_summary(stats)
        return

    for item in compare_list:
        source_dir = Path(item.get('source', ''))
        target_dir = Path(item.get('target', ''))
        print("\n" + "─"*60)
        print(f"▶ 比較セット開始: {source_dir.name} <-> {target_dir.name}")

        if item.get('target_find_latest_subdir', False):
            latest_subdir = find_latest_subdir(target_dir)
            if latest_subdir:
                log_message(stats, "INFO", f"最新の比較先フォルダ '{latest_subdir.name}' を使用します。")
                target_dir = latest_subdir
            else:
                log_message(stats, "ERROR", f"'source'を除くサブディレクトリが見つかりませんでした: {target_dir}")
                continue

        if not source_dir.is_dir() or not target_dir.is_dir():
            log_message(stats, "ERROR", "指定されたディレクトリのいずれかが存在しません。", f"Source: {source_dir}\nTarget: {target_dir}")
            continue

        for pattern in FILE_PATTERNS:
            source_files = list(source_dir.glob(pattern))
            target_files = list(target_dir.glob(pattern))
            
            source_file = source_files[0] if len(source_files) == 1 else None
            if len(source_files) > 1:
                log_message(stats, "WARN", f"パターン '{pattern}' の比較元が複数あります。スキップします。", indent_level=2)
                continue

            target_file = None
            if len(target_files) == 1:
                target_file = target_files[0]
            elif len(target_files) > 1:
                target_file = find_latest_file(target_files)
                log_message(stats, "INFO", f"最新ファイル '{target_file.name}' を比較先として使用します。", indent_level=2)

            if source_file and target_file:
                compare_files(stats, source_file, target_file)
            elif (source_file or target_file):
                log_message(stats, "SKIP", f"パターン '{pattern}' のファイルが片方にしか存在しません。", indent_level=2)

    print_summary(stats)

if __name__ == "__main__":
    main()