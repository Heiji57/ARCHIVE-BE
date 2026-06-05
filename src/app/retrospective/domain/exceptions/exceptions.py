from app.shared.domain.exceptions.base import BaseAppException


class JournalEntryNotFoundException(BaseAppException):
    code = "JOURNAL_ENTRY_NOT_FOUND"


class JournalEntryAlreadyExistsException(BaseAppException):
    code = "JOURNAL_ENTRY_ALREADY_EXISTS"


class RetroSummaryNotFoundException(BaseAppException):
    code = "RETRO_SUMMARY_NOT_FOUND"


class SummaryAlreadyInProgressException(BaseAppException):
    code = "RETRO_SUMMARY_ALREADY_IN_PROGRESS"


class SummaryInvalidStateException(BaseAppException):
    code = "RETRO_SUMMARY_INVALID_STATE"
