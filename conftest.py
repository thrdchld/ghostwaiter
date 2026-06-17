"""
conftest.py – konfigurasi pytest global.
Dipanggil otomatis oleh pytest sebelum test apapun berjalan.
"""
import os
import tempfile

# Buat satu temp dir bersama untuk seluruh sesi test API
# (test_storage.py membuat temp dir sendiri per test)
_SESSION_TEMP = tempfile.mkdtemp(prefix="gw_test_")
os.environ.setdefault("DATA_DIR", _SESSION_TEMP)
os.environ.setdefault("APP_PASSWORD", "")  # nonaktifkan auth
