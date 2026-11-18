export const U = (
  kind = "MANUAL",
) => ({
  kind,
  current_frame_id: "f",
  current_span: "s",
});

export const start = (
  seq,
  id = `d${seq}`,
  kind = "MANUAL",
  {
    identityId = "test-dispatcher",
    role = "writer",
  } = {},
) => ({
  kind: "controller_loop_event_v1",
  event_seq: seq,
  event_id: `e${seq}`,
  dispatch_id: id,
  dispatcher_identity_id: identityId,
  dispatcher_role: role,
  phase: "start",
  action: "STEP",
  payload: {
    U: U(kind),
  },
});

export const end = (
  seq,
  id,
  {
    kind = "MANUAL",
    outcome = "success",
    lastError = null,
    identityId = "test-dispatcher",
    role = "writer",
  } = {},
) => ({
  kind: "controller_loop_event_v1",
  event_seq: seq,
  event_id: `e${seq}`,
  dispatch_id: id,
  dispatcher_identity_id: identityId,
  dispatcher_role: role,
  phase: "end",
  action: "STEP",
  payload: {
    U: {
      ...U(kind),
      last_error: lastError,
    },
    outcome,
    result: {
      last_error: lastError,
    },
  },
});

export const info = (seq) => ({
  kind: "datum_lifecycle_event_v1",
  event_seq: seq,
  event_id: `e${seq}`,
  payload: {
    message: seq,
  },
});

export const page = (
  events,
  after,
  next,
  latest = next,
  extra = {},
) => ({
  events,
  after_event_seq: after,
  next_after_event_seq: next,
  session_latest_event_seq: latest,
  ...extra,
});