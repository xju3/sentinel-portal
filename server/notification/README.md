# Notification Service

Independent MQTT-driven WeChat notification consumer for diagnosis alert events.

The diagnosis service owns only diagnosis persistence and fault publication. It
publishes every committed fault event directly to MQTT. This service owns all
notification timing, recipient resolution, deduplication, channel delivery, and
delivery status.

## Processing flow

1. Subscribe to `sentinel/notification/wechat` with MQTT QoS 1, a stable client
   id, a persistent MQTT 3.1.1 session, and manual acknowledgements.
2. Apply notification timing policy (including bearing-fault continuity).
3. Resolve the current device category and process-device relation from MySQL.
   The event snapshot is used only when a current relation is missing, followed
   by a MySQL lookup using `sensor_sn`. Redis `sensor_meta` is not required.
4. Merge category and process-device recipients by `employee.id`, retaining only
   enabled associations, active employees, and non-empty `wx_user_id` values.
5. Insert a durable delivery row. The unique key
   `(device_id, overall_level, employee_id, notification_date)` enforces one
   delivery per Beijing calendar day.
6. Reuse `pub.services.wx.wx_service.WxService.send_template_message`.

Malformed MQTT events are acknowledged and discarded. Database or WeChat
processing failures are recorded when possible and left unacknowledged for
broker redelivery. `notification_delivery` is the notification module's
per-recipient idempotency and retry ledger.

## Configuration

The service uses the shared `.env` settings. Relevant variables are:

- `MYSQL_URL`, `REDIS_URL`
- `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`
- `MQTT_NOTIFICATION_TOPIC`, `MQTT_NOTIFICATION_CLIENT_ID`
- `WX_APP_ID`, `WX_APP_SECRET`, `WX_TEMPLATE_ID`, `WX_TEMPLATE_URL`
- `NOTIFICATION_TIMEZONE` (defaults to `Asia/Shanghai`)
- `BEARING_NOTIFICATION_CONFIRMATION_COUNT`,
  `BEARING_NOTIFICATION_WINDOW_HOURS`, `BEARING_NOTIFICATION_IMMEDIATE_LEVEL`

The schema is also available as
`server/pub/sql/20260729_add_diagnosis_notification_delivery.sql`.
