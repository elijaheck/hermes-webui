# EckOS on Hermes WebUI Implementation Plan

> **For Hermes:** Use Codex-first implementation with strict TDD and independent review per slice.

**Goal:** Add an opt-in `/eckos` voice-first operating mode to Hermes WebUI while preserving Hermes as the only session, memory, tool, approval, and execution runtime.

**Architecture:** `/eckos` is an alternate projection of the existing authenticated WebUI shell. It reuses the current browser session state, `/api/chat/start`, run-journal/session SSE, approval and clarification contracts, profile scoping, workspace authority, cron/MCP projections, and existing Hermes tool execution. EckOS contributes only presentation, true Realtime WebRTC voice, and a later approval-bound Hermes-to-Codex Computer Use tool path.

**Tech stack:** Existing Python server and vanilla JavaScript/CSS only; no frontend framework, bundler, second daemon, or duplicate durable store.

---

## Contract routing

**Task type:** Additive UI mode, session routing, later Realtime transport, later tool integration.

**Relevant public docs:**
- `AGENTS.md`
- `CONTRIBUTING.md`
- `docs/CONTRACTS.md`
- `docs/rfcs/session-sse-contract-v1.md`
- `docs/rfcs/canonical-session-resolution.md`
- `docs/rfcs/hermes-run-adapter-contract.md`
- `docs/rfcs/live-to-final-assistant-replies.md`
- `docs/rfcs/webui-pending-intent-controls.md`
- `docs/architecture/stable-assistant-turn-anchor-phase0.md`
- `ARCHITECTURE.md`
- `TESTING.md`
- `docs/UIUX-GUIDE.md`
- `DESIGN.md`

**State invariants:**
- No EckOS session/task/approval/event database.
- Existing `Session` + state.db reconciliation remains session truth.
- Run-journal events are projected, never copied into an N+1 activity store.
- Voice never resolves approvals or executes browser-side MCP/Computer Use calls.
- Existing live-to-final, Queue/Steer/Stop, replay, profile, and workspace semantics remain unchanged.

## Source mapping

| Concern | Existing authority |
|---|---|
| Shell/auth | `api/routes.py::handle_get`, `_render_index_shell_base`; `api/auth.py`; request profile context in `api/profiles.py` |
| Session truth/navigation | `api/models.py::Session`; `GET /api/session`; `GET /api/sessions`; `static/sessions.js` route/localStorage resolution |
| Turns | `POST /api/chat/start`; `api/streaming.py`; existing browser `send()` path |
| Live/replay events | run journal + `GET /api/sessions/{session_id}/events`; `static/messages.js`; `static/assistant_turn_anchors.js` |
| Approvals | `/api/approval/pending`, `/stream`, `/respond`; `showApprovalCard()` and `respondApproval()` |
| Clarification | `/api/clarify/pending`, `/stream`, `/respond`; current clarification card functions |
| Agents/subagents | `/api/sessions` parent/lineage/source fields plus `delegate_task` and `subagent_progress` tool events |
| Cron | `GET /api/crons` and existing detail/mutation routes |
| MCP | `GET /api/mcp/servers`, `GET /api/mcp/tools`; runtime discovery after active profile selection |
| Workspace | `Session.workspace`; trusted workspace helpers and current workspace APIs/UI |
| Usage | `/api/session/usage` and live `metering` events |
| Profile | `/api/profile/active`, `/api/profiles`, `/api/profile/switch` |

## Registered panel model

Presentation state may select, order, hide, and focus only these registered real-data projections:

- `conversation`: current session/messages/assistant-turn anchors
- `activity`: current run journal and rendered activity scene
- `approvals`: current approval projection/card
- `clarifications`: current clarification projection/card
- `agents`: real child/delegated sessions and delegated tool events
- `cron`: `/api/crons`
- `mcp`: `/api/mcp/servers` and `/api/mcp/tools`
- `workspace`: current session workspace projection
- `usage`: session usage plus live metering
- `profile`: active profile

Unknown panel IDs fail closed. Panel ordering is presentation-only and cannot mutate Hermes records.

---

### Task 1: Add `/eckos` shell and mode-preserving session routing

**Objective:** Serve the existing authenticated WebUI shell at `/eckos` and preserve EckOS mode while selecting/reloading sessions.

**Files:**
- Modify: `api/routes.py`
- Modify: `static/index.html`
- Modify: `static/sessions.js`
- Modify: `static/sw.js`
- Create: `tests/test_eckos_mode.py`

**Steps:**
1. Add failing route tests proving `/eckos` and `/eckos/` return the authenticated normal shell without adding a second HTML app.
2. Add failing static tests proving the mode is identified before paint and session navigation uses `/eckos?session=<id>` in EckOS mode.
3. Run the focused tests and observe RED.
4. Add `/eckos` to the existing shell route; set `document.documentElement.dataset.mode = "eckos"` from `location.pathname` before CSS paints.
5. Make `_sessionUrlForSid()` preserve EckOS mode while keeping normal `/session/<id>` behavior unchanged.
6. Update service-worker shell assets only if a new asset is introduced.
7. Run focused GREEN tests and `git diff --check`.
8. Commit: `feat: add additive EckOS WebUI mode route`.

### Task 2: Add the first real-data EckOS dashboard projection

**Objective:** Render a focused EckOS dashboard around the same active conversation and existing action-required cards.

**Files:**
- Modify: `static/index.html`
- Create: `static/eckos.js`
- Modify: `static/style.css`
- Modify: `static/sw.js`
- Modify: `static/i18n.js` only for user-facing copy that requires localization
- Modify: `tests/test_eckos_mode.py`

**Steps:**
1. Add failing source/DOM tests for a closed panel registry, unknown-ID rejection, conversation-first layout, bottom transcript/composer, and approval/clarification visibility.
2. Run tests and observe RED.
3. Implement a small registry and pure normalization function in `static/eckos.js`.
4. Reuse existing DOM/state rather than duplicating messages, approvals, clarifications, or session activity.
5. Provide presentation-only commands to focus/reorder registered panels; expose a narrow `window.EckOS.applyDashboard()` for later Realtime tool results and tests.
6. Add scoped `[data-mode="eckos"]` CSS using existing tokens; verify desktop, narrow, and phone widths.
7. Keep normal WebUI behavior bit-for-bit outside EckOS mode.
8. Run focused tests, JS syntax/runtime lint, and `git diff --check`.
9. Commit: `feat: project live Hermes state in EckOS mode`.

### Task 3: Prove native Hermes continuity

**Objective:** Show that `/eckos` uses the same session, normal send path, native run journal, and approval/clarification cards.

**Files:**
- Modify: `tests/test_eckos_mode.py`
- Modify: `TESTING.md`
- Modify: `ARCHITECTURE.md`

**Steps:**
1. Add route/session tests for active-session restore and `/eckos?session=` continuity.
2. Add source contract assertions that EckOS calls existing `send()`/session APIs rather than a new agent endpoint.
3. Run neighboring approval, clarification, session SSE, run-journal, subagent, MCP, and mobile tests.
4. Run a browser smoke against isolated `HERMES_HOME` and `HERMES_WEBUI_STATE_DIR` on a non-production port.
5. Capture desktop and phone-width before/after evidence.
6. Document the mode and rollback (`feature branch/worktree removal`; production :8787 unchanged).
7. Commit: `test: prove EckOS uses native Hermes contracts`.

### Task 4: Add true Realtime WebRTC voice

**Objective:** Add full-duplex OpenAI Realtime audio as a transport over the same EckOS/Hermes session surface.

**Files (expected):**
- Modify: `api/routes.py`
- Create: `api/eckos_realtime.py`
- Modify: `static/eckos.js`
- Modify: `static/style.css`
- Create/update: `tests/test_eckos_realtime.py`
- Modify: `ARCHITECTURE.md`, `TESTING.md`, `.env.example` only for non-secret variable names

**Steps:**
1. Verify the current official `/v1/realtime/calls` SDP/session contract before coding.
2. Add failing tests for authentication, CSRF, request size, server-only key use, no-cache response, upstream timeout/error redaction, and disabled/not-configured behavior.
3. Implement a bounded server-side SDP proxy; never return or log API keys.
4. Port only the reference WebRTC primitives: `RTCPeerConnection`, microphone track, remote audio, `oai-events` data channel, semantic VAD, transcript events, barge-in, mute, explicit voice states, reconnect, teardown.
5. Bound and debounce trusted Hermes context refreshes; do not treat Realtime state as durable memory.
6. Realtime tools may only recompose the registered dashboard or prepare text/intents for normal Hermes paths. They may not resolve approvals, execute MCP calls, or perform GUI actions.
7. Verify Mac Safari/Chrome and a physical iPhone; label physical/live gates honestly.
8. Commit in small TDD slices.

### Task 5: Route spoken Hermes work into the active session

**Objective:** Make “Ask Hermes” and “Have Hermes” visible and traceable in the same active session.

**Files:** determined after Task 4 review, primarily `static/eckos.js` and existing chat/session surfaces.

**Steps:**
1. Use existing composer/send/run contracts; do not create an external `hermes-client` bridge.
2. Preserve active profile, session, workspace, model, toolset, approval, Queue/Steer/Stop, and replay semantics.
3. Show attribution and traceability through the normal transcript/activity anchors.
4. Verify reload/reconnect and completion after voice teardown.

### Task 6: Add approval-bound Codex Computer Use

**Objective:** Implement the chain Hermes plan → existing approval callback/card → Codex Computer Use → Hermes verification.

**Architecture requirement:** This must be a registered Hermes-agent tool/plugin that enters the existing approval callback. A browser REST endpoint or Realtime tool cannot execute GUI actions directly.

**Steps:**
1. Write a separate reviewed design for the Hermes tool/plugin boundary.
2. Add strict TDD for serialized turns, read-only inspection, exact-plan binding, cancellation, denied permissions, bounded output, timeout, untrusted screen content, and no scope expansion.
3. Reuse current WebUI approval cards and responses.
4. Require Codex’s own target-app approval and macOS permissions.
5. Verify one read-only inspection and one harmless confirmed action with fresh before/after observation.

### Task 7: Retarget the native shell only after parity

**Objective:** Point the existing Swift shell from port 3011 to `http://127.0.0.1:8787/eckos` only after browser parity and physical validation.

**Non-goals until then:** no LaunchAgent retirement, no deletion of `packages/hermes-core`, no port-8717 shutdown, no claim of TV/iPhone parity without physical evidence.

---

## First-slice verification matrix

Run through repo-native tooling:

```bash
./scripts/test.sh -q tests/test_eckos_mode.py
./scripts/test.sh -q \
  tests/test_issue4812_session_sse_stream.py \
  tests/test_run_journal_routes.py \
  tests/test_live_to_final_anchor_visible_order.py \
  tests/test_approval_sse.py \
  tests/test_clarify_sse.py \
  tests/test_5307_subagent_child_transcript.py \
  tests/test_issue696_mcp_visibility_panel.py \
  tests/test_issue697_mcp_tool_inventory.py \
  tests/test_mobile_layout.py \
  tests/test_issue5539_mobile_approval_card_height.py
npm run lint:runtime
python tests/browser_smoke.py
git diff --check
```

Use isolated state for runtime/browser checks:

```bash
HERMES_HOME=/tmp/hermes-webui-eckos-agent-home \
HERMES_WEBUI_STATE_DIR=/tmp/hermes-webui-eckos-state \
HERMES_WEBUI_PORT=8789 \
python3 bootstrap.py
```

## First-slice definition of done

- `/eckos` is additive and authenticated.
- Normal WebUI is unchanged.
- Session selection/reload stays in EckOS mode.
- Conversation remains the source-of-truth transcript.
- Registered dashboard panels display only existing Hermes projections.
- Unknown panels fail closed.
- Existing approvals and clarifications remain visible and actionable.
- Existing native run/replay/session behavior is reused rather than copied.
- Desktop/mobile evidence and rollback are documented.
- Production port 8787 and the experimental EckOS services remain untouched.
