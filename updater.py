"""
Auto-updater silencioso para el Sistema de Medición.

Al iniciar la aplicación, en un hilo en segundo plano:
  - Si no hay internet: no hace nada (silencioso).
  - Si hay internet: descarga el archivo VERSION del repositorio público en GitHub.
  - Si la versión remota es mayor que la local, descarga el ZIP de la rama main.
  - Una vez completada la descarga, pregunta al usuario si desea actualizar.
  - Si el usuario acepta: extrae el ZIP, reemplaza los archivos del programa
    (preservando datos locales: .db, .meg, autosave.json) y solicita reiniciar.

Requiere solo la biblioteca estándar de Python.
"""

import os
import sys
import io
import json
import shutil
import zipfile
import tempfile
import threading
import urllib.request
import urllib.error

GITHUB_USER = "festivill"
GITHUB_REPO = "medicion"
GITHUB_BRANCH = "main"

VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/VERSION"
ZIP_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"

NET_TIMEOUT = 5  # segundos para chequeo rápido de versión
DOWNLOAD_TIMEOUT = 60  # segundos para descarga del ZIP

PRESERVE_PATTERNS = (
    ".db", ".meg", ".bak", ".tar.gz",
)
PRESERVE_NAMES = {
    "autosave.json",
    ".git",
    "__pycache__",
}


def _app_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _read_local_version():
    path = os.path.join(_app_dir(), "VERSION")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return "0.0.0"


def _parse_version(s):
    s = (s or "").strip().lstrip("vV")
    parts = []
    for chunk in s.split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:4])


def _fetch_remote_version():
    try:
        req = urllib.request.Request(
            VERSION_URL,
            headers={"User-Agent": "medicion45-updater"},
        )
        with urllib.request.urlopen(req, timeout=NET_TIMEOUT) as resp:
            data = resp.read().decode("utf-8", errors="ignore").strip()
            return data.splitlines()[0].strip() if data else None
    except Exception:
        return None


def _download_zip():
    try:
        req = urllib.request.Request(
            ZIP_URL,
            headers={"User-Agent": "medicion45-updater"},
        )
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
            buf = io.BytesIO()
            shutil.copyfileobj(resp, buf)
            buf.seek(0)
            return buf.getvalue()
    except Exception:
        return None


def _should_preserve(rel_path):
    name = os.path.basename(rel_path)
    if name in PRESERVE_NAMES:
        return True
    for part in rel_path.replace("\\", "/").split("/"):
        if part in PRESERVE_NAMES:
            return True
    for pat in PRESERVE_PATTERNS:
        if name.endswith(pat):
            return True
    return False


def _apply_update(zip_bytes, app_dir):
    """Extrae el ZIP a una carpeta temporal y copia los archivos al app_dir.
    Preserva archivos de datos locales. Devuelve (ok, mensaje)."""
    tmp_root = tempfile.mkdtemp(prefix="medicion45_upd_")
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zf.extractall(tmp_root)

        entries = [e for e in os.listdir(tmp_root) if os.path.isdir(os.path.join(tmp_root, e))]
        if not entries:
            return False, "El paquete descargado no contiene archivos."
        src_root = os.path.join(tmp_root, entries[0])

        for dirpath, dirnames, filenames in os.walk(src_root):
            dirnames[:] = [d for d in dirnames if d not in PRESERVE_NAMES]
            rel_dir = os.path.relpath(dirpath, src_root)
            target_dir = app_dir if rel_dir == "." else os.path.join(app_dir, rel_dir)
            os.makedirs(target_dir, exist_ok=True)
            for fname in filenames:
                rel_file = fname if rel_dir == "." else os.path.join(rel_dir, fname)
                if _should_preserve(rel_file):
                    continue
                src_file = os.path.join(dirpath, fname)
                dst_file = os.path.join(target_dir, fname)
                try:
                    shutil.copy2(src_file, dst_file)
                except PermissionError:
                    try:
                        if os.path.exists(dst_file):
                            os.replace(src_file, dst_file)
                    except Exception as e:
                        return False, f"No se pudo reemplazar {rel_file}: {e}"
                except Exception as e:
                    return False, f"Error copiando {rel_file}: {e}"
        return True, "Actualización aplicada correctamente."
    finally:
        try:
            shutil.rmtree(tmp_root, ignore_errors=True)
        except Exception:
            pass


def _ask_and_apply(root, zip_bytes, remote_version, local_version):
    """Se ejecuta en el hilo principal de Tk: pregunta al usuario y aplica."""
    try:
        from tkinter import messagebox
    except Exception:
        return

    msg = (
        f"Hay una nueva versión disponible.\n\n"
        f"   Versión instalada: {local_version}\n"
        f"   Versión disponible: {remote_version}\n\n"
        f"La actualización ya fue descargada.\n"
        f"¿Desea instalarla ahora?"
    )
    try:
        accept = messagebox.askyesno("Actualización disponible", msg, parent=root)
    except Exception:
        accept = False

    if not accept:
        return

    ok, info = _apply_update(zip_bytes, _app_dir())
    if ok:
        try:
            messagebox.showinfo(
                "Actualización completa",
                "La actualización se aplicó correctamente.\n"
                "Cierre y vuelva a abrir el programa para usar la nueva versión.",
                parent=root,
            )
        except Exception:
            pass
    else:
        try:
            messagebox.showwarning(
                "Actualización incompleta",
                f"No fue posible aplicar la actualización:\n\n{info}",
                parent=root,
            )
        except Exception:
            pass


def _worker(root):
    try:
        local_v = _read_local_version()
        remote_v = _fetch_remote_version()
        if not remote_v:
            return  # sin internet o sin respuesta: silencioso
        if _parse_version(remote_v) <= _parse_version(local_v):
            return  # ya estamos al día
        zip_bytes = _download_zip()
        if not zip_bytes:
            return  # falló la descarga: silencioso
        try:
            root.after(0, lambda: _ask_and_apply(root, zip_bytes, remote_v, local_v))
        except Exception:
            pass
    except Exception:
        return


def check_for_updates_async(root, delay_ms=1500):
    """Lanza el chequeo en segundo plano. No bloquea la UI.
    Si no hay internet o cualquier error, falla en silencio."""
    def _start():
        t = threading.Thread(target=_worker, args=(root,), daemon=True)
        t.start()
    try:
        root.after(delay_ms, _start)
    except Exception:
        _start()
