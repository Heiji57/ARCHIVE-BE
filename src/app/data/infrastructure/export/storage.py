"""내보내기 파일 저장 — 비공개 로컬 디렉토리(`EXPORT_DIR`, 기본 exports/). `/static` 아래가 아니다.

내려받기는 서명 토큰이 붙은 `GET /exports/{id}/download` 로만 한다.
"""

from pathlib import Path


class LocalExportStorage:
    def __init__(self, directory: str) -> None:
        self._dir = Path(directory)

    def path(self, key: str) -> Path:
        return self._dir / Path(key).name  # 경로 탈출 방지

    def prepare(self, key: str) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        return self.path(key)

    def remove(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)
