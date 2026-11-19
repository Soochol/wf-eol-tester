from __future__ import annotations

import re
from typing import Optional

_VALID = re.compile(r"^[\w-]+$")
_PATH_CHARS = ".\\/"
MAX_NAME_LENGTH = 64


def profile_name_error(text: str) -> Optional[str]:
    name = text.strip()
    if not name:
        return "프로파일 이름을 입력하세요"
    if any(char in name for char in _PATH_CHARS):
        return "점과 경로 구분자는 쓸 수 없습니다. 확장자(.yaml)는 붙이지 마세요"
    if len(name) > MAX_NAME_LENGTH:
        return f"이름은 {MAX_NAME_LENGTH}자 이하여야 합니다"
    if not _VALID.match(name):
        return "글자, 숫자, _, -만 쓸 수 있습니다"
    return None
