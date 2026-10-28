import assert from "node:assert/strict";
import { test } from "node:test";
import { trackQueuedRevision } from "../web/execution_tracking.js";

test("Records each node's submitted revision, rather than its later live choice", async () => {
    const api = { async queuePrompt() { return {prompt_id: "one"}; } };
    let revision = 5;
    const tracked = trackQueuedRevision(api, {id: 1}, () => revision);
    await api.queuePrompt(0, {output: {1: {}}, workflow: {nodes: [{id: 1, properties: {lp_selection_revision: 3}}]}});
    revision = 8;
    assert.equal(await tracked.get("one"), 3);
    tracked.dispose();
});

test("Captures metadata-free submissions independently for multiple nodes", async () => {
    const api = { async queuePrompt() { return {prompt_id: "two"}; } };
    let revision = 7;
    const first = trackQueuedRevision(api, {id: 1}, () => revision);
    const second = trackQueuedRevision(api, {id: 2}, () => 11);
    const excluded = trackQueuedRevision(api, {id: 3}, () => 90);
    await api.queuePrompt(0, {output: {1: {}, 2: {}}});
    revision = 20;
    assert.equal(await first.get("two"), 7);
    assert.equal(await second.get("two"), 11);
    assert.equal(await excluded.get("two"), undefined);
    first.dispose(); second.dispose(); excluded.dispose();
});

test("Execution arriving before the HTTP response waits for its snapshot", async () => {
    let respond;
    const api = { queuePrompt() { return new Promise(resolve => { respond = resolve; }); } };
    const tracked = trackQueuedRevision(api, {id: 1}, () => 4);
    const queued = api.queuePrompt(0, {output: {1: {}}});
    let completed = false;
    const snapshot = tracked.get("fast").then(value => { completed = true; return value; });
    await Promise.resolve();
    assert.equal(completed, false);
    respond({prompt_id: "fast"});
    await queued;
    assert.equal(await snapshot, 4);
    tracked.dispose();
});

test("Failed submissions preserve the original error and release snapshot waiters", async () => {
    let reject;
    const api = { queuePrompt() { return new Promise((_, fail) => { reject = fail; }); } };
    const tracked = trackQueuedRevision(api, {id: 1}, () => 4);
    const queued = api.queuePrompt(0, {output: {1: {}}});
    const rejected = assert.rejects(queued, /queue unavailable/);
    const snapshot = tracked.get("failed");
    reject(new Error("queue unavailable"));
    await rejected;
    assert.equal(await snapshot, undefined);
    tracked.dispose();
});

test("Removing a node during submission discards its captured state", async () => {
    let respond;
    const api = { queuePrompt() { return new Promise(resolve => { respond = resolve; }); } };
    const tracked = trackQueuedRevision(api, {id: 1}, () => 4);
    const queued = api.queuePrompt(0, {output: {1: {}}});
    tracked.dispose();
    respond({prompt_id: "removed"});
    await queued;
    assert.equal(await tracked.get("removed"), undefined);
});
