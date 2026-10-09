# Runs every 10 minutes from the scheduler.
#
# Re-enqueues deliveries that failed, and pages on-call when one endpoint has
# more than 100 failed deliveries. Rows in any other status are ignored.
ALERT_THRESHOLD = 100


def run(db, queue, pager):
    rows = db.fetch_all(
        "SELECT id, endpoint_id FROM webhook_deliveries "
        "WHERE status = 'failed' AND updated_at < now() - interval '10 minutes'"
    )
    per_endpoint = {}
    for row in rows:
        queue.enqueue("webhooks", {"delivery_id": row["id"]})
        per_endpoint[row["endpoint_id"]] = per_endpoint.get(row["endpoint_id"], 0) + 1
    for endpoint_id, count in per_endpoint.items():
        if count > ALERT_THRESHOLD:
            pager.page(f"endpoint {endpoint_id}: {count} failed webhook deliveries")
