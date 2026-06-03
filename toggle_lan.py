"""
Управление ai-toir: firewall-правило + процесс serve.py.

Подкоманды:
  on / off / toggle         — открыть/закрыть порт 8000 (Firewall, требует админа)
  status                    — общее состояние: firewall + serve.py
  serve-on                  — запустить serve.py в фоне
  serve-off                 — остановить serve.py (по PID в serve.pid)
  serve-status              — запущен ли serve.py
  restart                   — kill+start serve.py (без перезапуска firewall)

Все команды, требующие записи (изменение правила, kill процесса) — автоUAC.

serve.py пишет PID в serve.pid при старте (мы сохраняем) и удаляет при штатной
остановке. На Windows PID процесса python (а не ScriptBlock) берём из
Get-CimInstance Win32_Process по ParentProcessId или по командной строке.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

RULE_NAME = "ai-toir serve.py"
PORT = 8000
BASE = Path(__file__).parent
SERVE_PID_FILE = BASE / "serve.pid"
SERVE_LOG = BASE / "serve.log"
SERVE_ERR = BASE / "serve.err"
SERVE_CMD = "serve.py"


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> int:
    """Перезапускает себя с UAC и выходит (вывод ребёнка мы не видим)."""
    params = " ".join(f'"{a}"' for a in sys.argv)
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 0
    )
    if rc <= 32:
        print("Не удалось получить права администратора (UAC отклонён?).", file=sys.stderr)
        return 1
    return 0


def run(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout.strip(), p.stderr.strip()


# ---------- Firewall ----------

def ensure_rule() -> None:
    rc, out, _ = run([
        "powershell", "-NoProfile", "-Command",
        f"(Get-NetFirewallRule -DisplayName '{RULE_NAME}' -ErrorAction SilentlyContinue) -ne $null"
    ])
    if rc == 0 and out.strip().lower() == "true":
        return
    print(f"Создаю правило '{RULE_NAME}' для порта {PORT}...")
    rc, out, err = run([
        "powershell", "-NoProfile", "-Command",
        f"New-NetFirewallRule -DisplayName '{RULE_NAME}' -Direction Inbound "
        f"-Action Allow -Protocol TCP -LocalPort {PORT} -Profile Domain,Private -Enabled True"
    ])
    if rc != 0:
        print(f"ОШИБКА: правило не создано ({err})", file=sys.stderr)
        sys.exit(1)
    print("  создано.")


def get_fw_status() -> str:
    rc, out, _ = run([
        "powershell", "-NoProfile", "-Command",
        f"(Get-NetFirewallRule -DisplayName '{RULE_NAME}' -ErrorAction SilentlyContinue).Enabled"
    ])
    if rc != 0 or not out.strip():
        return "?"
    return "on" if "True" in out else "off" if "False" in out else "?"


def set_fw_enabled(enabled: bool) -> None:
    val = "True" if enabled else "False"
    rc, out, err = run([
        "powershell", "-NoProfile", "-Command",
        f"Set-NetFirewallRule -DisplayName '{RULE_NAME}' -Enabled {val}"
    ])
    if rc != 0:
        print(f"ОШИБКА: {err or out}", file=sys.stderr)
        sys.exit(1)


# ---------- serve.py ----------

def is_serve_listening() -> bool:
    rc, out, _ = run([
        "powershell", "-NoProfile", "-Command",
        f"(Get-NetTCPConnection -LocalPort {PORT} -State Listen -ErrorAction SilentlyContinue) -ne $null"
    ])
    return rc == 0 and out.strip().lower() == "true"


def find_serve_pids() -> list[int]:
    """Возвращает PID'ы python-процессов, у которых в командной строке есть serve.py.

    Используем WMI — он показывает полную CommandLine (в т.ч. аргументы скрипта),
    в отличие от Get-Process, который их не отдаёт.
    Имя процесса — python.exe или python3.13.exe (WindowsApps alias).
    """
    rc, out, _ = run([
        "powershell", "-NoProfile", "-Command",
        f"Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='python3.13.exe'\" | "
        f"Where-Object {{ $_.CommandLine -and $_.CommandLine -like '*{SERVE_CMD}*' }} | "
        f"Select-Object -ExpandProperty ProcessId"
    ])
    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def start_serve() -> None:
    if is_serve_listening() or find_serve_pids():
        print("serve.py уже запущен — ничего не делаю.")
        return
    print("Запускаю serve.py в фоне...")
    # PYTHONIOENCODING=utf-8 — иначе cp1251 в stderr на Windows
    # -RedirectStandardOutput/Error — логи
    ps = (
        f"$env:PYTHONIOENCODING='utf-8'; "
        f"$p = Start-Process python -ArgumentList '{SERVE_CMD}' "
        f"-RedirectStandardOutput '{SERVE_LOG}' -RedirectStandardError '{SERVE_ERR}' "
        f"-WindowStyle Hidden -PassThru; "
        f"$p.Id | Out-File -Encoding utf8 '{SERVE_PID_FILE}'"
    )
    rc, out, err = run(["powershell", "-NoProfile", "-Command", ps])
    if rc != 0:
        print(f"ОШИБКА запуска: {err or out}", file=sys.stderr)
        sys.exit(1)
    print(f"  запущен, PID в {SERVE_PID_FILE.name}.")


def stop_serve() -> None:
    pids = find_serve_pids()
    if not pids:
        print("serve.py не запущен.")
        if SERVE_PID_FILE.exists():
            try: SERVE_PID_FILE.unlink()
            except OSError: pass
        return
    print(f"Останавливаю serve.py (PID: {', '.join(map(str, pids))})...")
    rc, out, err = run([
        "powershell", "-NoProfile", "-Command",
        f"Stop-Process -Id {','.join(map(str, pids))} -Force -ErrorAction SilentlyContinue"
    ])
    if rc != 0:
        print(f"ОШИБКА: {err or out}", file=sys.stderr)
        sys.exit(1)
    if SERVE_PID_FILE.exists():
        try: SERVE_PID_FILE.unlink()
        except OSError: pass
    print("  остановлен.")


def serve_status() -> str:
    pids = find_serve_pids()
    if pids:
        return f"работает (PID {', '.join(map(str, pids))})"
    return "не работает"


# ---------- main ----------

def main() -> int:
    args = sys.argv[1:]
    cmd = args[0].lower() if args else "status"

    fw_cmds = {"on", "off", "toggle"}
    serve_cmds = {"serve-on", "serve-off", "restart"}
    needs_admin = cmd in fw_cmds or cmd in serve_cmds

    if needs_admin and not is_admin():
        print("Запрашиваю права администратора (UAC)...")
        return relaunch_as_admin()

    # ----- read-only serve status (no admin) -----
    if cmd == "serve-status":
        print(f"serve.py: {serve_status()}")
        return 0

    # ----- status (no admin) -----
    if cmd == "status":
        ensure_rule()
        fw = get_fw_status()
        sv = serve_status()
        print(f"Firewall: {fw}   serve.py: {sv}")
        return 0

    # ----- serve.py (admin) -----
    if cmd in serve_cmds:
        if cmd == "serve-on":
            start_serve()
        elif cmd == "serve-off":
            stop_serve()
        elif cmd == "restart":
            stop_serve()
            start_serve()
        print(f"  итого: serve.py — {serve_status()}")
        return 0

    # ----- firewall (admin) -----
    if cmd not in fw_cmds:
        print(__doc__)
        return 1

    ensure_rule()
    current = get_fw_status()
    if cmd == "on":
        target = True
    elif cmd == "off":
        target = False
    else:  # toggle
        target = current != "on"

    if (current == "on") == target:
        print(f"Firewall уже {'включён' if target else 'выключен'} — ничего не делаю.")
        return 0

    set_fw_enabled(target)
    new = "включён" if target else "выключен"
    print(f"Firewall: {new}.   serve.py: {serve_status()}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
