"""Create private local credentials; never overwrite an existing .env."""

from pathlib import Path
import secrets

p = Path(".env")
if p.exists():
    raise SystemExit(".env가 이미 있습니다. 덮어쓰지 않습니다.")
s = Path(".env.example").read_text()
for key, length in [
    ("DB_PASSWORD", 24),
    ("ADMIN_PASSWORD", 24),
    ("SESSION_SECRET", 32),
]:
    s = s.replace(key + "=\n", key + "=" + secrets.token_hex(length) + "\n")
p.write_text(s)
p.chmod(0o600)
print(".env 생성 완료. 관리자 비밀번호는 로컬 .env에서 확인하세요.")
