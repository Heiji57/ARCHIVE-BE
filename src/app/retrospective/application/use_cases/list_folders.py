from app.retrospective.domain.models.folder import Folder
from app.retrospective.domain.repositories.repository import IFolderRepository

# 페이지네이션 대신 두는 안전장치. 경로 조립에는 전체 집합이 필요해서(조상이
# 몇 번째 페이지에 있을지 알 수 없다) 페이지로 자를 수 없는 대신, 병리적인
# 폴더 수에서 응답이 무한정 커지는 것만 막는다. 폴더당 약 170B 이므로 2000개면
# raw 약 340KB 가 상한이다. 잘리면 클라이언트의 경로 조립이 모르는 id 에서
# 멈추고 부분 경로만 보여주므로, 칩이 조용히 degrade 할 뿐 깨지지 않는다.
MAX_FOLDERS = 2000


class ListFoldersUseCase:
    """GET /folders — 사용자의 전체 폴더를 평평한 목록으로.

    용도는 id → 이름 → 조상 사슬 해결이다. 검색처럼 폴더를 가로지르는 목록에서
    각 결과의 소속 경로("A › B › C")를 조립하려면 한 번도 열어본 적 없는 폴더의
    이름이 필요한데, GET /folders/contents 는 직계 하위만 주므로 조상을 알 수 없다.

    폴더 카드 뱃지용 개수(folderCount/entryCount)는 담지 않는다 — 전체 폴더에
    집계를 걸게 되는데 이 응답의 소비처는 그 값을 쓰지 않는다(뱃지는
    GET /folders/contents 가 주는 값을 그대로 쓴다).
    """

    def __init__(self, folder_repo: IFolderRepository) -> None:
        self._folder_repo = folder_repo

    async def execute(self, user_id: str) -> list[Folder]:
        return await self._folder_repo.find_all(user_id, MAX_FOLDERS)
