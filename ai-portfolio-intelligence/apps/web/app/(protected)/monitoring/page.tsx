"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import {
  acknowledgeMonitoringEvent,
  flushMonitoringNotifications,
  getMonitoringEvents,
  getMonitoringNotifications,
  getOptionsExpiryCalendar,
  resolveMonitoringEvent,
  snoozeMonitoringEvent,
} from "@/lib/api";
import {
  isDesktopRuntimeAvailable,
  pollDesktopOsNotifications,
  startDesktopNotificationPolling,
} from "@/lib/desktop-api";
import { useClientResource } from "@/lib/use-client-resource";

function MonitoringContent() {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;
  const [refreshKey, setRefreshKey] = useState(0);
  const [note, setNote] = useState<string | null>(null);
  const { data, error, loading } = useClientResource(
    () =>
      Promise.all([
        getMonitoringEvents(accountId),
        getOptionsExpiryCalendar(accountId).catch(() => ({ events: [], count: 0 })),
        getMonitoringNotifications(accountId).catch(() => ({ notifications: [], desktop_inbox: [] })),
      ]),
    [accountId, refreshKey],
  );

  useEffect(() => {
    if (!isDesktopRuntimeAvailable()) return;
    return startDesktopNotificationPolling(45_000);
  }, []);
  if (loading) return <PageLoading />;
  if (error) return <PageErrorBanner message={error} />;

  const [eventsPayload, expiryPayload, notificationsPayload] = data ?? [
    { events: [] },
    { events: [] },
    { notifications: [], desktop_inbox: [] },
  ];
  const events = Array.isArray(eventsPayload?.events)
    ? (eventsPayload.events as Array<Record<string, unknown>>)
    : [];
  const expiry = Array.isArray(expiryPayload?.events)
    ? (expiryPayload.events as Array<Record<string, unknown>>)
    : [];
  const notifications = Array.isArray(notificationsPayload?.notifications)
    ? (notificationsPayload.notifications as Array<Record<string, unknown>>)
    : [];

  async function onAck(eventId: string) {
    await acknowledgeMonitoringEvent(eventId);
    setNote(`Acknowledged ${eventId}`);
    setRefreshKey((k) => k + 1);
  }

  async function onResolve(eventId: string) {
    await resolveMonitoringEvent(eventId);
    setNote(`Resolved ${eventId}`);
    setRefreshKey((k) => k + 1);
  }

  async function onSnooze(eventId: string) {
    const until = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    await snoozeMonitoringEvent(eventId, until);
    setNote(`Snoozed ${eventId} until ${until}`);
    setRefreshKey((k) => k + 1);
  }

  async function onFlush() {
    const result = await flushMonitoringNotifications();
    setNote(`Flushed ${String(result.count ?? 0)} notifications to desktop inbox`);
    const poll = await pollDesktopOsNotifications();
    if (poll?.shown) {
      setNote((prev) => `${prev || ""} · OS notifications shown: ${poll.shown}`);
    }
    setRefreshKey((k) => k + 1);
  }

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Monitoring</p>
        <h2 className="text-3xl font-semibold">Inbox and option risks</h2>
      </div>
      <Disclaimer />
      {note ? <p className="text-sm text-zinc-600">{note}</p> : null}
      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-md border border-line bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-semibold">Monitoring events</h3>
            <button
              type="button"
              className="rounded-md border border-line px-2 py-1 text-xs hover:bg-panel"
              onClick={onFlush}
            >
              Flush inbox
            </button>
          </div>
          <div className="grid gap-2 text-sm">
            {events.length === 0 ? (
              <p className="text-zinc-600">No persisted monitoring events yet.</p>
            ) : (
              events.slice(0, 20).map((event, idx) => {
                const eventId = String(event.event_id || idx);
                return (
                  <div key={eventId} className="rounded-md border border-line p-3">
                    <div className="font-medium">{String(event.rule_type || event.type || "event")}</div>
                    <p className="text-xs text-zinc-600">
                      {String(event.message || "")} · status {String(event.status || "open")}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="rounded border border-line px-2 py-1 text-xs hover:bg-panel"
                        onClick={() => onAck(eventId)}
                      >
                        Acknowledge
                      </button>
                      <button
                        type="button"
                        className="rounded border border-line px-2 py-1 text-xs hover:bg-panel"
                        onClick={() => onSnooze(eventId)}
                      >
                        Snooze 24h
                      </button>
                      <button
                        type="button"
                        className="rounded border border-line px-2 py-1 text-xs hover:bg-panel"
                        onClick={() => onResolve(eventId)}
                      >
                        Resolve
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-3 font-semibold">Option expiry calendar</h3>
          <div className="grid gap-2 text-sm">
            {expiry.length === 0 ? (
              <p className="text-zinc-600">No option positions with expiry dates.</p>
            ) : (
              expiry.map((event, idx) => (
                <div key={`${event.symbol}-${idx}`} className="rounded-md border border-line p-3">
                  <div className="font-medium">
                    {String(event.symbol)} · DTE {String(event.dte ?? "—")} · {String(event.priority)}
                  </div>
                  <p className="text-xs text-zinc-600">
                    American exercise and broker-equivalent margin remain withheld.
                  </p>
                </div>
              ))
            )}
          </div>
          <h3 className="mb-3 mt-6 font-semibold">Notification outbox</h3>
          <div className="grid gap-2 text-sm">
            {notifications.length === 0 ? (
              <p className="text-zinc-600">No pending notifications.</p>
            ) : (
              notifications.slice(0, 10).map((item, idx) => (
                <div key={String(item.id || idx)} className="rounded-md border border-line p-3">
                  <div className="font-medium">{String(item.title || "notification")}</div>
                  <p className="text-xs text-zinc-600">{String(item.body || item.status || "")}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </section>
      <Link className="text-sm text-accent hover:underline" href="/decisions">
        Open decision queue
      </Link>
    </div>
  );
}

export default function MonitoringPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <MonitoringContent />
    </Suspense>
  );
}
