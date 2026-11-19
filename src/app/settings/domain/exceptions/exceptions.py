from app.shared.domain.exceptions.base import BaseAppException


class SettingsUiPrefsTooLargeException(BaseAppException):
    """uiPreferences 직렬화 크기가 상한(8KB)을 넘음."""

    code = "SETTINGS_UI_PREFS_TOO_LARGE"
