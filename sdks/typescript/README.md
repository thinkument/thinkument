# Thinkument TypeScript & Node.js SDK (`@thinkument/sdk`)

Official TypeScript and Node.js client library for the **Thinkument** open cognitive coordination platform ($P \times SM \times C \times W$). Auto-generated from canonical OpenAPI 3.1 specification (`openapi.v1.json`).

## Installation

```bash
npm install @thinkument/sdk
```

## Quickstart

### 1. Connect to Local Studio Daemon ($0.00 / Offline)
Start your local cognitive studio with `thinkument dev` (or `npx @thinkument/cli dev`), then connect:
```typescript
import { ThinkumentClient } from '@thinkument/sdk';

const client = new ThinkumentClient({ baseUrl: 'http://localhost:5052' });
```

### 2. Connect to Sovereign Cloud
```typescript
const client = new ThinkumentClient({
  baseUrl: 'https://api.thinkument.com',
  apiKey: process.env.THINKUMENT_API_KEY
});
```

## Core Workflows

### Launch a Session
```typescript
const session = await client.sessions.create({
  appPack: 'starter',
  title: 'Interactive Authoring Session'
});
console.log(`Created session ${session.sessionId} at ${session.url}`);
```

### Interactive Trident Dispatch
```typescript
const result = await session.dispatch({
  signal: 'next',
  data: { input: 'Synthesize quarterly trajectory' },
  role: 'author'
});
console.log(`Step ${result.stepIndex}: ${result.status}`);
```

### Event Stream Observability
```typescript
const events = await session.events({ channel: 'theta', sinceSeq: 0 });
for (const ev of events) {
  console.log(`Event [${ev.seq}] on ${ev.channel}:`, ev.data);
}
```

### React / Next.js Component Example
```tsx
import { useEffect, useState } from 'react';
import { ThinkumentClient } from '@thinkument/sdk';

export function ThinkumentWidgetViewer({ sessionId }: { sessionId: string }) {
  const [status, setStatus] = useState<string>('initializing');

  useEffect(() => {
    const client = new ThinkumentClient({ baseUrl: 'http://localhost:5052' });
    client.sessions.get(sessionId).then(s => setStatus(s.status));
  }, [sessionId]);

  return <div>Session Status: {status}</div>;
}
```

## License
Apache-2.0
