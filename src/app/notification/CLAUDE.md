# Notification 모듈 컨벤션

이 디렉토리(`src/app/notification/`)에서 작업할 때 적용되는 컨벤션.

- **알림 생성은 `Notifier` 한 곳으로**: `application/services/notifier.py`. 요청 경로는 DI(`Notifier`)로, 워커는 같은 세션의 리포지토리로 직접 만든다(`generate_summary._notify`, `reminders._notifier`). `Notification.create` + `repo.save` 를 직접 부르지 않는다 — 수신 설정·방해 금지를 빠뜨린다.
- **종류별 수신**: `user_settings.notification_prefs` 에서 꺼진 종류(`due`/`summary`/`schedule`/`sync`/`ai`)는 **만들지 않는다**(`notify` 가 None). `system` 은 끌 수 없다.
- **방해 금지**: `quiet_hours` 안이면 저장은 하되 `deliver_after` = 끝나는 시각(UTC). 목록은 `deliver_after IS NULL OR <= now` 만, SSE 즉시 전송은 호출자가 `should_push_now()` 일 때만. `worker.flush_quiet_notifications`(5분)가 시각이 지난 알림을 SSE 로 보낸 **뒤** `deliver_after` 를 비운다(최소 한 번 전송). 같은 종류 묶기는 2차 범위.
- **`link`**: 누르면 이동할 곳(JSONB) — `{kind: todo|topic|summary|export, id}`, `{kind: due}`, `{kind: day_close}`. SSE 페이로드(`stream_payload`)와 목록 응답은 같은 모양.
- **예약 알림**(`worker/tasks/reminders.py`): 마감 알림(일하는 날 첫 근무 시각, "오늘 마감 n·지난 마감 n", 둘 다 0 이면 안 보냄), 하루 마무리(`day_end_reminder.at`). 5분 beat 이지만 판정은 "시각이 지났고 1시간 안" + "오늘 아직 안 보냄"(`user_settings.last_*_date`) — 엄격한 5분 창이면 한 번 늦은 beat 에 그날 알림이 사라진다. 날짜 표시는 알림이 꺼진 종류여도 찍는다(다시 판정하지 않게). 사용자별 트랜잭션·예외 격리.
