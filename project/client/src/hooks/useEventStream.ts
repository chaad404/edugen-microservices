import { useEffect, useRef, useState } from "react";

import { labApi, streamUrl } from "../api/lab";
import type { LabEvent } from "../api/types";

export type StreamStatus = "connecting" | "live" | "reconnecting" | "off";

const EVENT_TYPES = [
  "experiment.created", "job.dispatched", "job.generated", "job.succeeded", "job.failed",
  "job.evaluation_delayed", "experiment.completed", "study.created", "study.published",
  "review.rating.submitted", "review.answer.submitted", "review.feedback.submitted",
];

/**
 * Server-Sent Events of one Lab channel (course chapter 9.3). EventSource cannot send an Authorization
 * header, so a short-lived stream ticket goes in the URL. The last event ID is remembered: after a broken
 * connection or an expired ticket the stream is reopened with a fresh ticket from that ID, so no event is missed.
 */
export function useEventStream(channel: string | null, onEvent: (event: LabEvent) => void): StreamStatus {
  const [status, setStatus] = useState<StreamStatus>(channel ? "connecting" : "off");
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    if (!channel) return;
    let source: EventSource | null = null;
    let timer: number | undefined;
    let lastId = 0;
    let failures = 0;
    let stopped = false;

    const open = async () => {
      try {
        const { ticket } = await labApi.streamTicket(channel);
        if (stopped) return;
        source = new EventSource(streamUrl(channel, ticket, lastId));
        source.onopen = () => {
          failures = 0;
          setStatus("live");
        };
        const receive = (message: MessageEvent) => {
          lastId = Number(message.lastEventId) || lastId;
          handler.current({ id: lastId, type: message.type, data: JSON.parse(message.data) });
        };
        EVENT_TYPES.forEach((type) => source!.addEventListener(type, receive as EventListener));
        source.onerror = () => {
          // CLOSED: the browser gave up (e.g. the ticket expired); otherwise it is retrying by itself
          if (source?.readyState === EventSource.CLOSED) retry();
          else setStatus("reconnecting");
        };
      } catch {
        retry();
      }
    };

    const retry = () => {
      source?.close();
      if (stopped) return;
      setStatus("reconnecting");
      failures += 1;
      const delay = Math.min(30_000, 1000 * 2 ** failures) * (0.5 + Math.random() / 2); // backoff with jitter
      timer = window.setTimeout(open, delay);
    };

    setStatus("connecting");
    open();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      source?.close();
    };
  }, [channel]);

  return status;
}
