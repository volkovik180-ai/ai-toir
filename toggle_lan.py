"""
Включение/выключение LAN-доступа к ai-toir (порт 8000).
Управляет правилом Windows Firewall "ai-toir serve.py".

Использование:
    python toggle_lan.py on       # открыть порт 8000 для LAN
    python toggle_lan.py off      # закрыть
    python toggle_lan.py status   # показать текущее состояние
    python toggle_lan.py         # toggle (вкл<->выкл)

Если запущен не от администратора — автоматически перезапускает себя
с UAC-подтверждением (нужно лишь нажать "Да" в окне UAC).

При первом запуске создаёт правило автоматически.
"""
from __future__ import annotations

import ctypes
import subprocess
import sys

RULE_NAME = "ai-toir serve.py"
PORT = 8000


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> int:
    """Перезапускает себя с UAC и возвращает код возврата дочернего процесса."""
    params = " ".join(f'"{a}"' for a in sys.argv)
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 0
    )
    if rc <= 32:
        print("Не удалось получить права администратора (UAC отклонён?).", file=sys.stderr)
        return 1
    # После запуска дочернего процесса в новом окне мы не видим его вывод;
    # предполагаем успех, если ShellExecuteW вернул > 32.
    return 0


def run(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def ensure_rule() -> None:
    rc, out, _ = run([
        "powershell", "-NoProfile", "-Command",
        f"(Get-NetFirewallRule -DisplayName '{RULE_NAME}' -ErrorAction SilentlyContinue) -ne $null"
    ])
    if rc == 0 and out.strip().lower() == "true":
        return
    # Создаём (вызывающий код уже проверил, что мы под админом)
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


def get_status() -> str:
    rc, out, _ = run([
        "powershell", "-NoProfile", "-Command",
        f"(Get-NetFirewallRule -DisplayName '{RULE_NAME}' -ErrorAction SilentlyContinue).Enabled"
    ])
    if rc != 0 or not out.strip():
        return "?"
    if "True" in out:
        return "on"
    if "False" in out:
        return "off"
    return "?"


def is_serve_running() -> bool:
    rc, out, _ = run([
        "powershell", "-NoProfile", "-Command",
        f"(Get-NetTCPConnection -LocalPort {PORT} -State Listen -ErrorAction SilentlyContinue) -ne $null"
    ])
    return rc == 0 and out.strip().lower() == "true"


def set_enabled(enabled: bool) -> None:
    val = "True" if enabled else "False"
    rc, out, err = run([
        "powershell", "-NoProfile", "-Command",
        f"Set-NetFirewallRule -DisplayName '{RULE_NAME}' -Enabled {val}"
    ])
    if rc != 0:
        print(f"ОШИБКА: {err or out}", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    # Команды, требующие записи (создание/изменение правила), требуют админа.
    args = sys.argv[1:]
    cmd = args[0].lower() if args else "toggle"
    needs_admin = cmd in ("on", "off", "toggle")

    if needs_admin and not is_admin():
        print("Запрашиваю права администратора (UAC)...")
        return relaunch_as_admin()

    if cmd == "status":
        ensure_rule()
        s = get_status()
        print(f"Firewall: {s}   serve.py: {'работает' if is_serve_running() else 'НЕ работает'}")
        return 0

    if cmd not in ("on", "off", "toggle"):
        print(__doc__)
        return 1

    ensure_rule()
    current = get_status()
    if cmd == "on":
        target = True
    elif cmd == "off":
        target = False
    else:  # toggle
        target = current != "on"

    if (current == "on") == target:
        print(f"Уже {'включён' if target else 'выключен'} — ничего не делаю.")
        return 0

    set_enabled(target)
    new = "включён" if target else "выключен"
    print(f"Порт {PORT}: {new}.   serve.py: {'работает' if is_serve_running() else 'НЕ работает'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
