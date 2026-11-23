import os
import platform
import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parent


import os
import platform
import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main():
    version_file = ROOT / ".python-version"
    expected = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "3.14.7"
    current = platform.python_version()

    # Flask 3.1+ 需 Python 3.10+
    if sys.version_info < (3, 10):
        print(f"錯誤：本專案需要 Python 3.10 以上版本，目前環境為 Python {current}。", file=sys.stderr)
        return 1

    if current != expected:
        print(f"提示：專案建議版本為 Python {expected}，目前使用 Python {current}，繼續執行...", flush=True)

    # 統一使用標準 .venv 資料夾，便於 VS Code 自動偵測
    environment = ROOT / ".venv"
    interpreter = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    python = environment / interpreter

    try:
        if not python.is_file():
            print("正在建立 Python 虛擬環境 (.venv)...", flush=True)
            venv.EnvBuilder(with_pip=True).create(environment)

        print("正在檢查與安裝依賴套件 (requirements.txt)...", flush=True)
        subprocess.run(
            [python, "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.txt"],
            check=True,
            cwd=ROOT,
        )
        print("\n=======================================================", flush=True)
        print("專案啟動成功！請在瀏覽器打開：http://127.0.0.1:5000/", flush=True)
        print("=======================================================\n", flush=True)
        return subprocess.call([python, "app.py"], cwd=ROOT)
    except subprocess.CalledProcessError as error:
        print(f"依賴安裝或啟動失敗，錯誤碼: {error.returncode}", file=sys.stderr)
        return error.returncode
    except KeyboardInterrupt:
        print("\n專案已停止運作。")
        return 0


if __name__ == "__main__":
    sys.exit(main())
