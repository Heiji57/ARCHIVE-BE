from pydantic import BaseModel, Field

from app.settings.application.use_cases.list_country_timezones import (
    CountryTimezoneListResult,
)


class CountryTimezonesResponse(BaseModel):
    country: str
    timezones: list[str]
    multi: bool = Field(
        description="다중 tz 국가 여부. true 면 사용자가 timezone 을 직접 선택해야 함."
    )

    @classmethod
    def from_result(cls, r: CountryTimezoneListResult) -> "CountryTimezonesResponse":
        return cls(country=r.country, timezones=r.timezones, multi=r.multi)
