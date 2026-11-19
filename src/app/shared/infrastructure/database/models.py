"""모든 ORM 모델을 한 번에 등록한다 — `Base.metadata` 가 외래 키 대상을 모두 알게.

모델은 쓰일 때 import 되므로, 한 프로세스가 어떤 모델을 쓰지 않으면 그 테이블이 metadata 에
없다. 그러면 그 테이블을 가리키는 외래 키를 가진 모델을 flush 할 때 NoReferencedTableError 가
난다(예: 워커가 calendars 모델 없이 todos 를 INSERT). API(`main.py`)·워커(`celery_app.py`)·
Alembic(`migrations/env.py`)이 시작할 때 이 모듈을 import 한다. 새 모델을 만들면 여기에 더한다.
"""

import app.ai.infrastructure.persistence.models.ai_settings_model  # noqa: F401
import app.ai.infrastructure.persistence.models.conversation_model  # noqa: F401
import app.ai.infrastructure.persistence.models.learning_model  # noqa: F401
import app.ai.infrastructure.persistence.models.suggestion_model  # noqa: F401
import app.auth.infrastructure.persistence.models.oauth_connection_model  # noqa: F401
import app.calendars.infrastructure.persistence.models.calendar_model  # noqa: F401
import app.data.infrastructure.persistence.models.export_model  # noqa: F401
import app.github.infrastructure.persistence.models.github_repository_model  # noqa: F401
import app.github.infrastructure.persistence.models.retrospective_push_model  # noqa: F401
import app.google_calendar.infrastructure.persistence.models.calendar_connection_model  # noqa: F401
import app.google_calendar.infrastructure.persistence.models.calendar_event_model  # noqa: F401
import app.notification.infrastructure.persistence.models.notification_model  # noqa: F401
import app.retrospective.infrastructure.persistence.models.folder_model  # noqa: F401
import app.retrospective.infrastructure.persistence.models.journal_entry_model  # noqa: F401
import app.retrospective.infrastructure.persistence.models.retro_summary_model  # noqa: F401
import app.retrospective.infrastructure.persistence.models.retro_template_model  # noqa: F401
import app.retrospective.infrastructure.persistence.models.summary_template_model  # noqa: F401
import app.settings.infrastructure.persistence.models.user_settings_model  # noqa: F401
import app.todo.infrastructure.persistence.models.todo_model  # noqa: F401
import app.todo.infrastructure.persistence.models.user_tag_model  # noqa: F401
import app.topic.infrastructure.persistence.models.chunk_model  # noqa: F401
import app.topic.infrastructure.persistence.models.topic_model  # noqa: F401
import app.user.infrastructure.persistence.models.country_history_model  # noqa: F401
import app.user.infrastructure.persistence.models.user_model  # noqa: F401
