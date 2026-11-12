/*
 * Round-robin sharding. Playwright 1.64.1 slices a shard contiguously by file order, so the heavy
 * sheet.spec.ts block landed in one shard and ran past the CI job limit. This reporter takes over
 * with --shard=N/M: test i of the full list (Playwright's own order, the same in every job) runs in
 * shard (i mod M) + 1. Without --shard it does nothing.
 */
import type { FullConfig, Reporter, Suite, TestRun } from "@playwright/test/reporter";

export default class ShardReporter implements Reporter {
  preprocess({
    config,
    suite,
    testRun,
  }: {
    config: FullConfig;
    suite: Suite;
    testRun: TestRun;
  }): Promise<void> {
    const shard = config.shard;
    if (shard === null) return Promise.resolve();
    testRun.skipSharding();
    suite.allTests().forEach((test, i) => {
      if (i % shard.total !== shard.current - 1) testRun.exclude(test);
    });
    return Promise.resolve();
  }
}
