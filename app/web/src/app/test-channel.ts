/*
 * A small in-memory BroadcastChannel for tests. jsdom has none. Messages reach every other
 * channel with the same name, never the sender, like the real one.
 */
type Listener = (event: MessageEvent) => void;

export class FakeChannel {
  static open = new Set<FakeChannel>();
  readonly name: string;
  private listeners = new Set<Listener>();

  constructor(name: string) {
    this.name = name;
    FakeChannel.open.add(this);
  }

  postMessage(data: unknown): void {
    for (const channel of FakeChannel.open) {
      if (channel === this || channel.name !== this.name) continue;
      for (const listener of channel.listeners) listener(new MessageEvent("message", { data }));
    }
  }

  addEventListener(_type: "message", listener: Listener): void {
    this.listeners.add(listener);
  }

  close(): void {
    FakeChannel.open.delete(this);
    this.listeners.clear();
  }

  static reset(): void {
    FakeChannel.open.clear();
  }

  /** The cast the access client needs, since the fake covers only what it uses. */
  asChannel(): BroadcastChannel {
    return this as unknown as BroadcastChannel;
  }
}
