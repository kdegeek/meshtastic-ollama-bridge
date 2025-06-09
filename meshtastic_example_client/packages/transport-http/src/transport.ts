import type { Types } from "@meshtastic/core";

export class TransportHTTP implements Types.Transport {
  private _toDevice: WritableStream<Uint8Array>;
  private _fromDevice: ReadableStream<Types.DeviceOutput>;
  private url: string;
  private receiveBatchRequests: boolean;
  private fetchInterval: number;
  private fetchTimeout: number; // Timeout for each fetch request

  public static async create(
    address: string,
    tls?: boolean,
    maxRetries: number = 3,
    retryDelay: number = 1000,
  ): Promise<TransportHTTP> {
    const connectionUrl = `${tls ? "https" : "http"}://${address}`;
    for (let i = 0; i < maxRetries; i++) {
      try {
        await fetch(`${connectionUrl}/json/report`);
        // If the fetch is successful, resolve and return a new instance
        await Promise.resolve();
        return new TransportHTTP(connectionUrl);
      } catch (error) {
        console.error(
          `Connection attempt ${i + 1} failed: ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
        if (i < maxRetries - 1) {
          await new Promise((resolve) => setTimeout(resolve, retryDelay));
        } else {
          // If all retries fail, throw an error
          throw new Error(
            `Failed to connect to the radio after ${maxRetries} attempts: ${
              error instanceof Error ? error.message : String(error)
            }`,
          );
        }
      }
    }
    // This line should theoretically be unreachable due to the loop structure
    // and the throw in the else block, but to satisfy TypeScript's need for
    // a return path or a throw.
    throw new Error("Failed to connect to the radio after all retries.");
  }

  constructor(url: string, fetchInterval?: number) {
    this.url = url;
    this.receiveBatchRequests = false;
    this.fetchInterval = fetchInterval ?? 3000; // Use provided value or default to 3000
    this.fetchTimeout = 5000; // Default timeout for each fetch request

    this._toDevice = new WritableStream<Uint8Array>({
      write: async (chunk) => {
        await this.writeToRadio(chunk);
      },
    });

    let controller: ReadableStreamDefaultController<Types.DeviceOutput>;

    this._fromDevice = new ReadableStream<Types.DeviceOutput>({
      start: (ctrl) => {
        controller = ctrl;
      },
    });

    setInterval(async () => {
      await this.readFromRadio(controller);
    }, this.fetchInterval);
  }

  private async readFromRadio(
    controller: ReadableStreamDefaultController<Types.DeviceOutput>,
  ): Promise<void> {
    try {
      let readBuffer = new ArrayBuffer(1);
      while (readBuffer.byteLength > 0) {
        const response = await fetch(
          `${this.url}/api/v1/fromradio?all=${
            this.receiveBatchRequests ? "true" : "false"
          }`,
          {
            method: "GET",
            headers: {
              Accept: "application/x-protobuf",
            },
            signal: AbortSignal.timeout(this.fetchTimeout), // Add AbortSignal for timeout
          },
        );

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        readBuffer = await response.arrayBuffer();

        if (readBuffer.byteLength > 0) {
          controller.enqueue({
            type: "packet",
            data: new Uint8Array(readBuffer),
          });
        }
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "TimeoutError") {
        console.error("Fetch timed out in readFromRadio:", error);
        // Handle timeout specifically if needed, e.g., by trying again or notifying the user
        // For now, just re-throw as a specific error or let the generic handler below catch it.
      } else {
        console.error("Failed to read from radio:", error);
      }
      // Optionally, you could enqueue an error object to the stream
      // controller.enqueue({ type: "error", error });
      // Or close the stream
      // controller.error(error);
      // Re-throw the error or a new one to indicate failure.
      throw new Error(
        `Failed to read from radio: ${
          error instanceof Error ? error.message : String(error)
        }`,
      );
    }
  }

  private async writeToRadio(data: Uint8Array): Promise<void> {
    try {
      const response = await fetch(`${this.url}/api/v1/toradio`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/x-protobuf",
        },
        body: data,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
    } catch (error) {
      console.error("Failed to write to radio:", error);
      throw new Error(`Failed to write to radio: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  get toDevice(): WritableStream<Uint8Array> {
    return this._toDevice;
  }

  get fromDevice(): ReadableStream<Types.DeviceOutput> {
    return this._fromDevice;
  }
}
