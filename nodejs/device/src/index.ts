// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for full license information.
import {
  ThiefSettings,
  Signal,
  ThiefPairingProperties,
  ThiefC2dMessage,
} from "./types";
import { TimeoutError } from "./timeout";
import { Mqtt as ProvisioningTransport } from "azure-iot-provisioning-device-mqtt";
import { Mqtt as IotHubTransport } from "azure-iot-device-mqtt";
import { SymmetricKeySecurityClient } from "azure-iot-security-symmetric-key";
import { ProvisioningDeviceClient } from "azure-iot-provisioning-device";
import { Client, Message, Twin } from "azure-iot-device";
import { createHmac } from "crypto";
import { v4 as uuidv4 } from "uuid";
import { promisify } from "util";
import { NotImplementedError } from "azure-iot-common/dist/errors";

const provisioningHost = process.env.THIEF_DEVICE_PROVISIONING_HOST;
const idScope = process.env.THIEF_DEVICE_ID_SCOPE;
const groupSymmetricKey = process.env.THIEF_DEVICE_GROUP_SYMMETRIC_KEY;
const registrationId = process.env.THIEF_DEVICE_ID;
const requestedServicePool = process.env.THIEF_REQUESTED_SERVICE_POOL;
const runId = uuidv4();
if (
  !provisioningHost ||
  !idScope ||
  !groupSymmetricKey ||
  !registrationId ||
  !requestedServicePool
) {
  throw new Error("Required environment variable is undefined.");
}

const settings: ThiefSettings = {
  thiefMaxRunDurationInSeconds: 0,
  thiefPropertyUpdateIntervalInSeconds: 30,
  thiefWatchdogFailureIntervalInSeconds: 300,
  thiefAllowedClientLibraryExceptionCount: 10,
  pairingRequestTimeoutIntervalInSeconds: 900,
  pairingRequestSendIntervalInSeconds: 30,
  sendMessageOperationsPerSecond: 1,
  sendMessageAllowedFailureCount: 1000,
  receiveC2dIntervalInSeconds: 20,
  receiveC2dAllowedMissingMessageCount: 100,
  reportedPropertiesUpdateIntervalInSeconds: 10,
  reportedPropertiesAllowedFailureCount: 50,
};

class DeviceApp {
  private async createDeviceClientUsingDpsGroupKey() {
    const deviceKey = createHmac(
      "SHA256",
      Buffer.from(groupSymmetricKey, "base64")
    )
      .update(registrationId, "utf8")
      .digest("base64");
    const provisioningSecurityClient = new SymmetricKeySecurityClient(
      registrationId,
      deviceKey
    );
    const provisioningClient = ProvisioningDeviceClient.create(
      provisioningHost,
      idScope,
      new ProvisioningTransport(),
      provisioningSecurityClient
    );
    const registrationResultPromise = provisioningClient.register();
    if (!registrationResultPromise) {
      throw new Error(
        ".register() did not return a promise when it should have."
      );
    }
    const registrationResult = await registrationResultPromise.catch(
      (e: Error) => {
        throw new Error(`DPS registration failed: ${e}`);
      }
    );
    const connectionString =
      "HostName=" +
      registrationResult.assignedHub +
      ";DeviceId=" +
      registrationResult.deviceId +
      ";SharedAccessKey=" +
      deviceKey;
    const hubClient = Client.fromConnectionString(
      connectionString,
      IotHubTransport
    );
    await hubClient.open().catch((e: Error) => {
      throw new Error(`Opening client failed: ${e}`);
    });
    return hubClient;
  }

  private onReceivePairingPatch(): Promise<ThiefPairingProperties> {
    return new Promise((resolve, reject) => {
      const listener = (received: any) => {
        if (!received.runId || !received.serviceInstanceId) {
          return console.warn(
            "runId and/or serviceInstanceId is missing. Ignoring."
          );
        }
        if (received.runId !== runId) {
          return console.warn(
            `runId mismatch. Ignoring. (received ${received.runId}, expected ${runId})`
          );
        }
        console.info(
          `Service app ${received.serviceInstanceId} claimed this device instance`
        );
        this.serviceInstanceId = received.serviceInstanceId;
        this.twin.removeListener("properties.desired.thief.pairing", listener);
        clearTimeout(timer);
        resolve(received);
      };
      const on_timeout = () => {
        this.twin.removeListener("properties.desired.thief.pairing", listener);
        reject(
          new TimeoutError(
            "Pairing desired properties event not received in time."
          )
        );
      };
      this.twin.on("properties.desired.thief.pairing", listener);
      const timer = setTimeout(
        on_timeout,
        1000 * this.settings.pairingRequestSendIntervalInSeconds
      );
    });
  }

  private async pairWithService() {
    console.info("Starting pairing operation.");
    const pairingRequestPatch: {
      thief: { pairing: ThiefPairingProperties };
    } = {
      thief: {
        pairing: {
          requestedServicePool: requestedServicePool,
          serviceInstanceId: null,
          runId: runId,
        },
      },
    };

    const startTime = new Date().getTime();

    while (
      new Date().getTime() - startTime <=
      1000 * this.settings.pairingRequestTimeoutIntervalInSeconds
    ) {
      console.info("Updating pairing reported props: %j", pairingRequestPatch);
      const patchReceived = this.onReceivePairingPatch();
      await promisify(this.twin.properties.reported.update)(
        pairingRequestPatch
      ).catch((e: Error) => {
        throw new Error(`Updating reported properties failed: ${e}`);
      });
      let patch: ThiefPairingProperties;
      try {
        patch = await patchReceived;
      } catch (e) {
        if (e instanceof TimeoutError) {
          console.info(
            `Pairing response timed out after waiting for ${this.settings.pairingRequestSendIntervalInSeconds} seconds. Requesting again.`
          );
          continue;
        } else {
          throw e;
        }
      }
      const pairingAcceptPatch: {
        thief: { pairing: ThiefPairingProperties };
      } = {
        thief: {
          pairing: {
            serviceInstanceId: patch.serviceInstanceId,
            runId: runId,
          },
        },
      };

      await promisify(this.twin.properties.reported.update)(
        pairingAcceptPatch
      ).catch((e: Error) => {
        throw new Error(`Updating reported properties failed: ${e}`);
      });

      return console.info("Pairing with service complete.");
    }

    throw new TimeoutError(
      `Pairing failed after trying for ${this.settings.pairingRequestTimeoutIntervalInSeconds} seconds`
    );
  }

  // Does not deal with out-of-order messages.
  // For example, if we get index 5 and then 7, we assume 6 is lost.
  private handleTestC2dMessage(obj: ThiefC2dMessage, msg: Message) {
    if (
      Number.isNaN(obj.thief.testC2dMessageIndex) ||
      typeof obj.thief.testC2dMessageIndex !== "number"
    ) {
      this.client.reject(msg).catch(this.handleRejectC2dError);
      return console.warn(
        "Issue with testC2dMessageIndex property. Rejecting."
      );
    }

    this.client.complete(msg).catch(this.handleCompleteC2dError);
    if (!this.maxReceivedIndex && this.maxReceivedIndex !== 0) {
      console.info(
        `Received initial testC2dMessageIndex: ${(this.maxReceivedIndex =
          obj.thief.testC2dMessageIndex)}`
      );
    } else if (this.maxReceivedIndex + 1 === obj.thief.testC2dMessageIndex) {
      console.info(
        `Received next testC2dMessageIndex: ${++this.maxReceivedIndex}`
      );
    } else if (this.maxReceivedIndex < obj.thief.testC2dMessageIndex) {
      const missing = Array.from(
        { length: obj.thief.testC2dMessageIndex - this.maxReceivedIndex - 1 },
        (_, i) => 1 + i + this.maxReceivedIndex
      );
      console.warn(
        `Received testC2dMessageIndex ${obj.thief.testC2dMessageIndex}, but never received indices ${missing}`
      );
      this.maxReceivedIndex = obj.thief.testC2dMessageIndex;
      if (
        (this.c2dMissingMessageCount += missing.length) >
        this.settings.receiveC2dAllowedMissingMessageCount
      ) {
        this.stopDeviceApp(
          new Error(
            `The number of missing C2D messages exceeds receiveC2dAllowedMissingMessageCount of ${this.settings.receiveC2dAllowedMissingMessageCount}.`
          )
        );
      }
    } else {
      console.warn(`Received old index: ${obj.thief.testC2dMessageIndex}`);
    }
  }

  private handleServiceAckResponseMessage(obj: ThiefC2dMessage, msg: Message) {
    if (!Array.isArray(obj.thief.serviceAcks)) {
      this.client.reject(msg).catch(this.handleRejectC2dError);
      return console.warn("Issue with serviceAcks property. Rejecting.");
    }
    console.info(`Received serviceAckIds: ${obj.thief.serviceAcks}`);
    obj.thief.serviceAcks.forEach((id: string) => {
      if (this.serviceAckWaitList.has(id)) {
        this.serviceAckWaitList.delete(id);
      } else {
        console.warn(`Received unknown serviceAckId: ${id}`);
      }
    });
    this.client.reject(msg).catch(this.handleRejectC2dError);
  }

  private handleRejectC2dError = (e: Error) => {
    if (e instanceof NotImplementedError) {
      return;
    }
    console.warn(`Error when rejecting C2D message: ${e}`);
    if (
      ++this.clientLibraryExceptionCount >
      this.settings.thiefAllowedClientLibraryExceptionCount
    ) {
      this.stopDeviceApp(
        new Error(
          `The number of client errors exceeds thiefAllowedClientLibraryExceptionCount of ${this.settings.thiefAllowedClientLibraryExceptionCount}.`
        )
      );
    }
  };

  private handleCompleteC2dError = (e: Error) => {
    console.warn(`Error when completing C2D message: ${e}`);
    if (
      ++this.clientLibraryExceptionCount >
      this.settings.thiefAllowedClientLibraryExceptionCount
    ) {
      this.stopDeviceApp(
        new Error(
          `The number of client errors exceeds thiefAllowedClientLibraryExceptionCount of ${this.settings.thiefAllowedClientLibraryExceptionCount}.`
        )
      );
    }
  };

  private c2dMessageListener = (msg: Message) => {
    let obj: ThiefC2dMessage;
    try {
      obj = JSON.parse(msg.getData().toString());
    } catch {
      this.client.reject(msg).catch(this.handleRejectC2dError);
      return console.warn("Failed to parse received C2D message. Rejecting.");
    }

    if (
      !obj.thief ||
      obj.thief.runId !== runId ||
      obj.thief.serviceInstanceId !== this.serviceInstanceId
    ) {
      this.client.reject(msg).catch(this.handleRejectC2dError);
      console.warn("C2D received, but it's not for us: %j. Rejecting.", obj);
    } else if (obj.thief.cmd === "serviceAckResponse") {
      this.handleServiceAckResponseMessage(obj, msg);
    } else if (obj.thief.cmd === "testC2d") {
      this.handleTestC2dMessage(obj, msg);
    } else {
      this.client.reject(msg).catch(this.handleRejectC2dError);
      console.warn("Unknown command received: %j. Rejecting", obj);
    }
  };

  private async startC2dMessageSending() {
    const patch = {
      thief: {
        testControl: {
          c2d: {
            messageIntervalInSeconds: this.settings.receiveC2dIntervalInSeconds,
            send: true,
          },
        },
      },
    };
    console.info("Enabling C2D message testing: %j", patch);
    await promisify(this.twin.properties.reported.update)(patch).catch(
      (e: Error) => {
        throw new Error(`Updating reported properties failed: ${e}`);
      }
    );
  }

  private onTelemetrySendInterval = () => {
    if (
      this.serviceAckWaitList.size >
      this.settings.sendMessageAllowedFailureCount
    ) {
      return this.stopDeviceApp(
        new Error(
          `The number of service acks being waited on exceeds sendMessageAllowedFailureCount of ${this.settings.sendMessageAllowedFailureCount}.`
        )
      );
    }

    const serviceAckId = uuidv4();
    const message = new Message(
      JSON.stringify({
        thief: {
          cmd: "serviceAckRequest",
          serviceInstanceId: this.serviceInstanceId,
          runId: runId,
          serviceAckId: serviceAckId,
          serviceAckType: "telemetry",
        },
      })
    );
    this.client
      .sendEvent(message)
      .catch(() => {
        console.warn(
          "Error sending message with serviceAckId: " + serviceAckId
        );
      })
      .finally(() => {
        this.serviceAckWaitList.add(serviceAckId);
      });
  };

  private async startTestOperations() {
    this.client.on("message", this.c2dMessageListener);
    console.info("Starting telemetry sending.");
    this.telemetrySendingInterval = setInterval(
      this.onTelemetrySendInterval,
      1000 * this.settings.sendMessageOperationsPerSecond
    );
    await this.startC2dMessageSending().catch((e: Error) => {
      throw new Error(`Starting C2D message sending failed: ${e}`);
    });
  }

  stopDeviceApp(reason?: Signal | Error) {
    let code: number;
    if (reason instanceof Error) {
      code = 1;
      console.error(`Stopping device app due to error: ${reason}`);
    } else {
      code = 128 + reason;
      const signal =
        reason === Signal.SIGHUP
          ? "SIGHUP"
          : reason === Signal.SIGINT
          ? "SIGINT"
          : "SIGKILL";
      console.warn("Stopping device app due to signal" + signal);
    }

    clearInterval(this.telemetrySendingInterval);
    clearTimeout(this.pairingAttemptTimer);
    clearTimeout(this.pairingTimer);
    if (this.twin) {
      this.twin.removeAllListeners();
    }
    if (this.client) {
      this.client.removeAllListeners();
      console.log("Closing device client.");
      this.client
        .close()
        .then(() => console.log("Device client closed."))
        .catch((e: Error) => console.error(`Error closing client: ${e}`))
        .finally(() => process.exit(code));
      return;
    }
    process.exit(code);
  }

  async startDeviceApp(settings: ThiefSettings) {
    console.info("Starting device app.");
    this.settings = settings;
    try {
      this.client = await this.createDeviceClientUsingDpsGroupKey();
      this.twin = await this.client.getTwin();
      await this.pairWithService();
      await this.startTestOperations();
    } catch (e) {
      this.stopDeviceApp(e);
    }
  }

  private pairingTimer: NodeJS.Timeout;
  private pairingAttemptTimer: NodeJS.Timeout;
  private telemetrySendingInterval: NodeJS.Timeout;
  private serviceAckWaitList: Set<string>;
  private maxReceivedIndex: number;
  private c2dMissingMessageCount: number;
  private clientLibraryExceptionCount: number;
  private serviceInstanceId: string;
  private settings: ThiefSettings;
  private client: Client;
  private twin: Twin;

  private static instance: DeviceApp;
  static getInstance() {
    if (!this.instance) {
      this.instance = new DeviceApp();
    }
    return this.instance;
  }
  private constructor() {
    this.serviceAckWaitList = new Set();
    this.c2dMissingMessageCount = 0;
  }
}

process.on("SIGHUP", () =>
  DeviceApp.getInstance().stopDeviceApp(Signal.SIGHUP)
);
process.on("SIGINT", () =>
  DeviceApp.getInstance().stopDeviceApp(Signal.SIGINT)
);
process.on("SIGTERM", () =>
  DeviceApp.getInstance().stopDeviceApp(Signal.SIGTERM)
);

DeviceApp.getInstance()
  .startDeviceApp(settings)
  .catch(() => console.error("Device app failed."));
