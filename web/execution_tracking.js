// Capture local choices when a prompt is submitted, before it waits in the queue.
const trackers = new WeakMap();

export function trackQueuedRevision(api, node, revision) {
    let tracker = trackers.get(api);
    if (!tracker) {
        tracker = { subscribers: new Map(), queued: new Map(), inflight: new Set() };
        trackers.set(api, tracker);
        const original = api.queuePrompt;
        if (typeof original === "function") {
            api.queuePrompt = async function (...args) {
                const output = args[1]?.output;
                const saved = new Map((args[1]?.workflow?.nodes || []).map(n => [String(n.id), n.properties?.lp_selection_revision]));
                const snapshots = new Map();
                for (const [owner, read] of tracker.subscribers) {
                    if (Object.hasOwn(output || {}, String(owner.id))) snapshots.set(owner, saved.get(String(owner.id)) ?? read());
                }
                let finish;
                const done = new Promise(resolve => { finish = resolve; });
                tracker.inflight.add(done);
                try {
                    const response = await original.apply(this, args);
                    for (const owner of snapshots.keys()) if (!tracker.subscribers.has(owner)) snapshots.delete(owner);
                    if (response?.prompt_id && snapshots.size) {
                        tracker.queued.set(response.prompt_id, snapshots);
                        while (tracker.queued.size > 128) tracker.queued.delete(tracker.queued.keys().next().value);
                    }
                    return response;
                } finally {
                    tracker.inflight.delete(done);
                    finish();
                }
            };
        }
    }
    tracker.subscribers.set(node, revision);
    return {
        async get(promptId) {
            // A fast server may send execution events before the HTTP response.
            await Promise.all([...tracker.inflight]);
            return tracker.queued.get(promptId)?.get(node);
        },
        dispose() {
            tracker.subscribers.delete(node);
            for (const snapshots of tracker.queued.values()) snapshots.delete(node);
        },
    };
}
