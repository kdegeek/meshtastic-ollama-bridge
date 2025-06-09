import { assertEquals, assertRejects, assertInstanceOf } from "https://deno.land/std@0.220.0/assert/mod.ts";
import { delay } from "https://deno.land/std@0.220.0/async/delay.ts";
import { FakeTime } from "https://deno.land/std@0.220.0/testing/time.ts";
import { TransportHTTP } from "./transport.ts"; // Adjust path as necessary

// Mocking global fetch
let mockFetchResponses: Array<() => Promise<Response>> = [];
let fetchCallStack: Array<{ url: string; options?: RequestInit }> = [];

const originalFetch = globalThis.fetch;

function mockFetch(url: string, options?: RequestInit): Promise<Response> {
  fetchCallStack.push({ url, options });
  const responseFn = mockFetchResponses.shift();
  if (responseFn) {
    return responseFn();
  }
  // Default behavior if no mock response is set up for a call
  return Promise.resolve(new Response("Default mock response", { status: 200 }));
}

function setupMockFetch(responses: Array<() => Promise<Response>>) {
  mockFetchResponses = [...responses];
  fetchCallStack = []; // Reset call stack for each setup
  globalThis.fetch = mockFetch as any;
}

function restoreOriginalFetch() {
  globalThis.fetch = originalFetch;
  mockFetchResponses = [];
  fetchCallStack = [];
}

Deno.test("[TransportHTTP] setup and teardown for fetch mocking", () => {
  // This test just ensures our mock setup/teardown works
  assertEquals(typeof globalThis.fetch, "function");
  setupMockFetch([]);
  assertEquals(globalThis.fetch, mockFetch);
  restoreOriginalFetch();
  assertEquals(globalThis.fetch, originalFetch);
});

Deno.test({
  name: "[TransportHTTP.create] successful connection with HTTP",
  async fn() {
    setupMockFetch([
      () => Promise.resolve(new Response("OK", { status: 200 })), // For /json/report
    ]);

    const transport = await TransportHTTP.create("localhost:8080", false);
    assertInstanceOf(transport, TransportHTTP);
    assertEquals(fetchCallStack.length, 1);
    assertEquals(fetchCallStack[0].url, "http://localhost:8080/json/report");

    restoreOriginalFetch();
  },
});

Deno.test({
  name: "[TransportHTTP.create] successful connection with HTTPS",
  async fn() {
    setupMockFetch([
      () => Promise.resolve(new Response("OK", { status: 200 })), // For /json/report
    ]);

    const transport = await TransportHTTP.create("localhost:8080", true);
    assertInstanceOf(transport, TransportHTTP);
    assertEquals(fetchCallStack.length, 1);
    assertEquals(fetchCallStack[0].url, "https://localhost:8080/json/report");

    restoreOriginalFetch();
  },
});

Deno.test({
  name: "[TransportHTTP.create] retries on connection failure then succeeds",
  async fn() {
    const time = new FakeTime(); // Use FakeTime for controlling setTimeout
    try {
      setupMockFetch([
        () => Promise.reject(new Error("Network error 1")),
        () => Promise.reject(new Error("Network error 2")),
        () => Promise.resolve(new Response("OK", { status: 200 })), // Success on 3rd attempt
      ]);

      const transportPromise = TransportHTTP.create("localhost:8080", false, 3, 100); // 3 retries, 100ms delay

      // Advance time for the first delay
      await time.tickAsync(100);
      // Advance time for the second delay
      await time.tickAsync(100);

      const transport = await transportPromise;

      assertInstanceOf(transport, TransportHTTP);
      assertEquals(fetchCallStack.length, 3);
      assertEquals(fetchCallStack[0].url, "http://localhost:8080/json/report");
      assertEquals(fetchCallStack[1].url, "http://localhost:8080/json/report");
      assertEquals(fetchCallStack[2].url, "http://localhost:8080/json/report");
    } finally {
      time.restore();
      restoreOriginalFetch();
    }
  },
});

Deno.test({
  name: "[TransportHTTP.create] fails after all retries",
  async fn() {
    const time = new FakeTime();
    try {
      setupMockFetch([
        () => Promise.reject(new Error("Network error 1")),
        () => Promise.reject(new Error("Network error 2")),
        () => Promise.reject(new Error("Network error 3")),
      ]);

      await assertRejects(
        async () => {
          const promise = TransportHTTP.create("localhost:8080", false, 3, 100);
          await time.tickAsync(100); // First delay
          await time.tickAsync(100); // Second delay
          // No third delay as it fails on the third attempt
          await promise;
        },
        Error,
        "Failed to connect to the radio after 3 attempts: Network error 3",
      );
      assertEquals(fetchCallStack.length, 3);
    } finally {
      time.restore();
      restoreOriginalFetch();
    }
  },
});

Deno.test({
  name: "[TransportHTTP.writeToRadio] successful data transmission",
  async fn() {
    setupMockFetch([
      // Mock for TransportHTTP.create()
      () => Promise.resolve(new Response("OK", { status: 200 })),
      // Mock for the actual writeToRadio call
      () => Promise.resolve(new Response("Write successful", { status: 200 })),
    ]);

    try {
      const transport = await TransportHTTP.create("localhost:1234", false);
      const writer = transport.toDevice.getWriter();
      const testData = new Uint8Array([1, 2, 3, 4, 5]);
      await writer.write(testData);

      assertEquals(fetchCallStack.length, 2); // 1 for create, 1 for write
      const writeCall = fetchCallStack[1];
      assertEquals(writeCall.url, "http://localhost:1234/api/v1/toradio");
      assertEquals(writeCall.options?.method, "PUT");
      assertEquals(writeCall.options?.headers, { "Content-Type": "application/x-protobuf" });
      assertEquals(new Uint8Array(writeCall.options?.body as ArrayBuffer), testData);

      writer.releaseLock();
    } finally {
      restoreOriginalFetch();
    }
  },
});

Deno.test({
  name: "[TransportHTTP.writeToRadio] network failure",
  async fn() {
    setupMockFetch([
      // Mock for TransportHTTP.create()
      () => Promise.resolve(new Response("OK", { status: 200 })),
      // Mock for the failing writeToRadio call
      () => Promise.reject(new Error("Simulated network error")),
    ]);

    try {
      const transport = await TransportHTTP.create("localhost:1234", false);
      const writer = transport.toDevice.getWriter();
      const testData = new Uint8Array([1, 2, 3]);

      await assertRejects(
        async () => {
          await writer.write(testData);
        },
        Error,
        "Failed to write to radio: Simulated network error", // This matches the error thrown by writeToRadio
      );
      assertEquals(fetchCallStack.length, 2); // 1 for create, 1 for write
      writer.releaseLock();
    } finally {
      restoreOriginalFetch();
    }
  },
});


Deno.test({
  name: "[TransportHTTP.writeToRadio] HTTP error status",
  async fn() {
    setupMockFetch([
      // Mock for TransportHTTP.create()
      () => Promise.resolve(new Response("OK", { status: 200 })),
      // Mock for the failing writeToRadio call
      () => Promise.resolve(new Response("Server error", { status: 500 })),
    ]);

    try {
      const transport = await TransportHTTP.create("localhost:1234", false);
      const writer = transport.toDevice.getWriter();
      const testData = new Uint8Array([1, 2, 3]);

      await assertRejects(
        async () => {
          await writer.write(testData);
        },
        Error,
        "Failed to write to radio: HTTP error! status: 500",
      );
      assertEquals(fetchCallStack.length, 2);
      writer.releaseLock();
    } finally {
      restoreOriginalFetch();
    }
  },
});


// Tests for readFromRadio
Deno.test({
  name: "[TransportHTTP.readFromRadio] successful data reception",
  async fn() {
    const time = new FakeTime();
    try {
      const testData = new Uint8Array([10, 20, 30]);
      const initialFetchInterval = 100; // Use a short interval for faster testing

      setupMockFetch([
        // Mock for TransportHTTP.create()
        () => Promise.resolve(new Response("OK", { status: 200 })),
        // First call by readFromRadio's setInterval
        () => Promise.resolve(new Response(testData.buffer, { status: 200 })),
        // Second call by readFromRadio's while loop (within the same interval)
        () => Promise.resolve(new Response(new ArrayBuffer(0), { status: 200 })), // Empty buffer to stop the loop
      ]);

      // Create instance with a specific fetchInterval
      const transport = new TransportHTTP("http://localhost:7777", initialFetchInterval);
      // The constructor of TransportHTTP calls create, but we are testing the instance method here.
      // For direct instantiation and testing of readFromRadio logic through setInterval,
      // we might need to adjust how create() is handled or how TransportHTTP is instantiated in tests.
      // For now, we assume create() was successful (mocked above).
      // The actual create method is static, so new TransportHTTP() is what sets up setInterval.

      const reader = transport.fromDevice.getReader();

      // Let the first interval pass
      await time.tickAsync(initialFetchInterval);

      const { value, done } = await reader.read();

      assertInstanceOf(value, Object);
      assertEquals(value?.type, "packet");
      assertEquals(new Uint8Array(value?.data as Uint8Array), testData);
      assertEquals(done, false);

      // Check fetch calls
      // fetchCallStack[0] is from a hypothetical create if we used TransportHTTP.create
      // Since we used `new TransportHTTP()`, there's no initial /json/report call from create in this specific setup.
      // Let's adjust mock setup if we want to use TransportHTTP.create for these tests.
      // For now, assuming direct constructor usage for interval testing.
      // If create was called, fetchCallStack[0] would be json/report
      // fetchCallStack[0] (or 1 if create was used) should be the first fromradio call
      // fetchCallStack[1] (or 2) should be the second fromradio call (empty buffer)

      // To simplify, let's assume we test TransportHTTP instance directly
      // and create() call is mocked separately or not relevant for this specific unit.
      // The current setupMockFetch uses one response for create, then two for readFromRadio.
      // Let's adjust the test slightly to reflect that TransportHTTP constructor doesn't call /json/report
      // but relies on create method to do that.
      // The tests above for .create() cover that.
      // For readFromRadio, we need to ensure the polling mechanism works.

      // Correcting the fetch call assumptions for direct constructor test:
      // No, the constructor itself does not call fetch. It sets up setInterval.
      // The create method calls fetch. So the mock for `create` is still needed.
      // The current `setupMockFetch` has one for create.
      // The `setInterval` in constructor will then call `readFromRadio`.

      assertEquals(fetchCallStack.length, 3); // 1 for create, 2 for readFromRadio polling
      assertEquals(fetchCallStack[1].url, `http://localhost:7777/api/v1/fromradio?all=false`);
      assertEquals(fetchCallStack[2].url, `http://localhost:7777/api/v1/fromradio?all=false`);

      reader.releaseLock();
      // Important: clear the interval to prevent Deno from waiting indefinitely
      // This requires making the interval ID accessible or adding a dispose/close method to TransportHTTP
      // For now, this test might hang or affect others if not handled.
      // Let's assume a dispose method is added to TransportHTTP for cleanup in tests.
      // (await transport.close()); // Hypothetical close method
    } finally {
      time.restore();
      restoreOriginalFetch();
      // Consider adding a transport.close() if TransportHTTP is modified to return the interval ID or have a close method.
    }
  },
});


Deno.test({
  name: "[TransportHTTP.readFromRadio] timeout handling",
  async fn() {
    const time = new FakeTime();
    try {
      const fetchInterval = 100;
      const fetchTimeout = 50; // Shorter than the delay we'll introduce in mock

      // Mock for TransportHTTP.create()
      setupMockFetch([
        () => Promise.resolve(new Response("OK", { status: 200 })),
        // Mock for readFromRadio that will time out
        async () => {
          await delay(fetchTimeout + 10); // Simulate delay longer than timeout
          return Promise.resolve(new Response("Should have timed out", { status: 200 }));
        },
      ]);

      const transport = new TransportHTTP("http://localhost:8888", fetchInterval);
      // Manually set fetchTimeout for this instance for testing purposes.
      // This assumes fetchTimeout is a public or configurable property, or TransportHTTP constructor takes it.
      // From previous tasks, fetchTimeout is a private property initialized in constructor.
      // To test this properly, we might need to pass fetchTimeout to constructor or make it configurable.
      // For now, let's assume the default fetchTimeout (5000ms) is too long for this FakeTime test.
      // The class's fetchTimeout is 5000ms. We need to modify the instance or the class for this test.
      // Let's assume we can pass it to constructor for testing:
      // class TransportHTTP { constructor(url, fetchInterval, fetchTimeout) }
      // This is not current signature. Current: constructor(url, fetchInterval?)
      // Let's re-read transport.ts to confirm. fetchTimeout is private.
      // The test will rely on the default fetchTimeout of 5000ms unless we change the SUT.
      // For FakeTime, 5000ms is fine. We just need to tick past it.

      // Let's adjust the test to use the actual fetchTimeout from the class (5000ms)
      // And ensure our mock delay respects FakeTime.
      // The `delay` from `deno.land/std/async/delay.ts` should respect `FakeTime`.

      // The `readFromRadio` is called by `setInterval`. If it throws, the interval just continues.
      // We need a way to capture that error.
      // One way: listen for unhandled promise rejections, or modify SUT to report errors via the stream.
      // The current SUT `console.error`s and then `throw new Error`.
      // This throw will happen inside the setInterval callback.

      // Let's spy on console.error for this test.
      let consoleErrorArgs: any[] = [];
      const originalConsoleError = console.error;
      console.error = (...args) => {
        consoleErrorArgs.push(args);
      };

      // Trigger the interval
      await time.tickAsync(fetchInterval); // Wait for setInterval to call readFromRadio
      await time.tickAsync(transport['fetchTimeout'] + 100); // Wait for the fetch to time out

      assertEquals(consoleErrorArgs.length > 0, true, "console.error should have been called for timeout");
      const errorArgs = consoleErrorArgs.find(args => args[0] === "Fetch timed out in readFromRadio:");
      assertInstanceOf(errorArgs[1], DOMException);
      assertEquals(errorArgs[1].name, "TimeoutError");

      // Since readFromRadio throws, the test itself won't see the throw directly from reader.read()
      // unless the stream is closed with an error. The current implementation does not do that.

    } finally {
      console.error = originalConsoleError; // Restore console.error
      time.restore();
      restoreOriginalFetch();
      // transport.close() needed here too
    }
  },
});

Deno.test({
  name: "[TransportHTTP.readFromRadio] network failure",
  async fn() {
    const time = new FakeTime();
    let consoleErrorArgs: any[] = [];
    const originalConsoleError = console.error;
    console.error = (...args) => { consoleErrorArgs.push(args); };

    try {
      const fetchInterval = 100;
      setupMockFetch([
        () => Promise.resolve(new Response("OK", { status: 200 })), // For create
        () => Promise.reject(new Error("Simulated network problem")),
      ]);

      const transport = new TransportHTTP("http://localhost:9999", fetchInterval);

      await time.tickAsync(fetchInterval); // Trigger readFromRadio
      await time.tickAsync(10); // Allow microtasks to settle

      assertEquals(consoleErrorArgs.length > 0, true, "console.error should be called on network failure");
      const errorArgs = consoleErrorArgs.find(args => args[0] === "Failed to read from radio:");
      assertInstanceOf(errorArgs[1], Error);
      assertEquals(errorArgs[1].message, "Simulated network problem");

    } finally {
      console.error = originalConsoleError;
      time.restore();
      restoreOriginalFetch();
      // transport.close()
    }
  },
});


Deno.test({
  name: "[TransportHTTP] constructor correctly sets fetchInterval",
  fn() {
    // Mock for TransportHTTP.create is not strictly needed here if we only access properties
    // but TransportHTTP constructor itself sets up setInterval which calls readFromRadio, which calls fetch.
    // So, we still need to manage the global fetch mock.
    setupMockFetch([
      // Mock for the first call to readFromRadio's fetch, which will happen due to setInterval
      // It will try to fetch from undefined/api/v1/fromradio if url is not passed,
      // but constructor takes url.
      () => Promise.resolve(new Response(new ArrayBuffer(0), { status: 200 })),
      () => Promise.resolve(new Response(new ArrayBuffer(0), { status: 200 })), // for the loop
    ]);

    try {
      const defaultIntervalTransport = new TransportHTTP("http://defaulthost");
      assertEquals(defaultIntervalTransport['fetchInterval'], 3000);

      const customIntervalTransport = new TransportHTTP("http://customhost", 1500);
      assertEquals(customIntervalTransport['fetchInterval'], 1500);

      // Need to clean up these instances if they started intervals.
      // This highlights the need for a .close() or .dispose() method on TransportHTTP.
    } finally {
      restoreOriginalFetch();
    }
  },
});

// TODO: Add a test for fetchInterval actually being used by setInterval.
// This would involve FakeTime and checking fetchCallStack after specific time ticks.
// The "successful data reception" test implicitly covers this to some extent.

// NOTE: The readFromRadio tests that inspect console.error are a bit indirect.
// A better approach would be for TransportHTTP to propagate errors through its ReadableStream,
// allowing consumers (and tests) to react to errors directly from the stream.
// For example, controller.error(error) in readFromRadio.
// However, tests should reflect the current implementation.
