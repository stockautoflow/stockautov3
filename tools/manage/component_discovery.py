# tools/manage/component_discovery.py
import os
from pathlib import Path

def discover_components(script_dir: str = "scripts") -> dict:
    """
    指定されたディレクトリをスキャンし、'create_*.py'という命名規則の
    コンポーネントスクリプトを検出する。
    """
    components = {}
    # スクリプトからの相対パスではなく、絶対パスで処理するように変更
    # manage.pyから渡されるscript_dirが絶対パスであることを想定
    if not os.path.isdir(script_dir):
        return components

    for entry in os.scandir(script_dir):
        if entry.is_file() and entry.name.startswith("create_") and entry.name.endswith(".py"):
            component_name = entry.name[7:-3]
            components[component_name] = str(Path(entry.path).resolve())
    
    return components