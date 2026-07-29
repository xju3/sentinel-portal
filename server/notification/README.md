# Notification Service

Independent MQTT-driven WeChat notification consumer for diagnosis alert events.

## Processing flow

1. Subscribe to `sentinel/notification/wechat` with MQTT QoS 1, a stable client
   id, a persistent MQTT 3.1.1 session, and manual acknowledgements.
2. Resolve the current device category and process-device relation from MySQL.
   The event snapshot is used only when a current relation is missing, followed
   by a MySQL lookup using `sensor_sn`. Redis `sensor_meta` is not required.
3. Merge category and process-device recipients by `employee.id`, retaining only
   enabled associations, active employees, and non-empty `wx_user_id` values.
4. Insert a durable delivery row. The unique key
   `(device_id, overall_level, employee_id, notification_date)` enforces one
   delivery per Beijing calendar day.
5. Reuse `pub.services.wx.wx_service.WxService.send_template_message`.

Malformed MQTT events are acknowledged and discarded. Unexpected database
processing failures are left unacknowledged for broker redelivery. A handled
WeChat failure is recorded as `FAILED`, acknowledged, and continues to occupy
the daily unique slot.

## Configuration

The service uses the shared `.env` settings. Relevant variables are:

- `MYSQL_URL`, `REDIS_URL`
- `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`
- `MQTT_NOTIFICATION_TOPIC`, `MQTT_NOTIFICATION_CLIENT_ID`
- `WX_APP_ID`, `WX_APP_SECRET`, `WX_TEMPLATE_ID`, `WX_TEMPLATE_URL`
- `NOTIFICATION_TIMEZONE` (defaults to `Asia/Shanghai`)

The schema is also available as
`server/pub/sql/20260729_add_diagnosis_notification_delivery.sql`.
