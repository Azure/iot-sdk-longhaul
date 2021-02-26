// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for full license information.
import {
  ThiefSettings,
  Signal,
  ThiefPairingProperties,
  ThiefC2dMessage,
  AzureMonitorCustomProperties,
} from "./types";
import { TimeoutError } from "./timeout";
import { Logger, LoggerSeverityLevel } from "./logger";
import { Mqtt as ProvisioningTransport } from "azure-iot-provisioning-device-mqtt";
import { Mqtt as IotHubTransport } from "azure-iot-device-mqtt";
import { SymmetricKeySecurityClient } from "azure-iot-security-symmetric-key";
import { ProvisioningDeviceClient } from "azure-iot-provisioning-device";
import { Client, Message, Twin } from "azure-iot-device";
import { NotImplementedError } from "azure-iot-common/dist/errors";
import * as appInsights from "applicationinsights";
import { EventTelemetry } from "applicationinsights/out/Declarations/Contracts";
import { createHmac } from "crypto";
import { v4 as uuidv4 } from "uuid";
import { promisify } from "util";
import * as os from "os";

const provisioningHost = process.env.THIEF_DEVICE_PROVISIONING_HOST;
const idScope = process.env.THIEF_DEVICE_ID_SCOPE;
const groupSymmetricKey = process.env.THIEF_DEVICE_GROUP_SYMMETRIC_KEY;
const registrationId = process.env.THIEF_DEVICE_ID;
const requestedServicePool = process.env.THIEF_REQUESTED_SERVICE_POOL;
const appInsightsInstrumentationKey =
  process.env.THIEF_APP_INSIGHTS_INSTRUMENTATION_KEY;
const runId = uuidv4();
let runReason = process.argv[2]
  ? process.argv[2]
  : process.env.THIEF_RUN_REASON;
if (
  !provisioningHost ||
  !idScope ||
  !groupSymmetricKey ||
  !registrationId ||
  !requestedServicePool ||
  !appInsightsInstrumentationKey
) {
  throw new Error("Required environment variable is undefined.");
}

const azureMonitorProperties: AzureMonitorCustomProperties = {
  sdkLanguageVersion: process.versions.node,
  sdkLanguage: "node.js",
  sdkVersion: require("azure-iot-device/package.json").version,
  osType: os.type(),
  poolId: requestedServicePool,
  transport: "mqtt",
  deviceId: registrationId,
  runId: runId,
};

appInsights
  .setup(appInsightsInstrumentationKey)
  .setAutoCollectConsole(false, false)
  .setAutoCollectRequests(false)
  .setAutoCollectDependencies(false)
  .setAutoDependencyCorrelation(false);
appInsights.defaultClient.context.tags[
  appInsights.defaultClient.context.keys.cloudRole
] = "device";
appInsights.defaultClient.context.tags[
  appInsights.defaultClient.context.keys.cloudRoleInstance
] = runId;
appInsights.start();
appInsights.defaultClient.commonProperties = azureMonitorProperties;

const logger = new Logger({
  consoleEnabled: true,
  consoleSeverityLevel: LoggerSeverityLevel.INFO,
  appInsightsEnabled: true,
  appInsightsSeverityLevel: LoggerSeverityLevel.WARN,
  appInsightsClient: appInsights.defaultClient,
});

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
    logger.info("Starting DPS registration.");
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
    logger.info(
      `DPS registration complete. Assigned hub: ${registrationResult.assignedHub}`
    );
    appInsights.defaultClient.commonProperties["hub"] =
      registrationResult.assignedHub;
    const connectionString = `HostName=${registrationResult.assignedHub};DeviceId=${registrationResult.deviceId};SharedAccessKey=${deviceKey}`;
    const hubClient = Client.fromConnectionString(
      connectionString,
      IotHubTransport
    );
    logger.info("Connecting to IoT Hub.");
    await hubClient.open().catch((e: Error) => {
      throw new Error(`Opening client failed: ${e}`);
    });
    return hubClient;
  }

  private onReceivePairingPatch(): Promise<ThiefPairingProperties> {
    return new Promise((resolve, reject) => {
      const listener = (received: any) => {
        appInsights.defaultClient.trackEvent({
          name: "ReceivedPairingResponse",
        });
        if (!received.runId || !received.serviceInstanceId) {
          return logger.warn(
            "runId and/or serviceInstanceId is missing. Ignoring."
          );
        }
        if (received.runId !== runId) {
          return logger.warn(
            `runId mismatch. Ignoring. (received ${received.runId}, expected ${runId})`
          );
        }
        logger.info(
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
        1000 * settings.pairingRequestSendIntervalInSeconds
      );
    });
  }

  private async pairWithService() {
    logger.info("Starting pairing operation.");
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
      1000 * settings.pairingRequestTimeoutIntervalInSeconds
    ) {
      appInsights.defaultClient.trackEvent({ name: "SendingPairingRequest" });
      logger.info("Updating pairing reported props: %j", pairingRequestPatch);
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
          logger.warn(
            `Pairing response timed out after waiting for ${settings.pairingRequestSendIntervalInSeconds} seconds. Requesting again.`
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
      appInsights.defaultClient.trackEvent({ name: "PairingComplete" });
      return logger.info("Pairing with service complete.");
    }

    throw new TimeoutError(
      `Pairing failed after trying for ${settings.pairingRequestTimeoutIntervalInSeconds} seconds`
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
      return logger.warn("Issue with testC2dMessageIndex property. Rejecting.");
    }

    this.client.complete(msg).catch(this.handleCompleteC2dError);
    if (!this.maxReceivedIndex && this.maxReceivedIndex !== 0) {
      logger.info(
        `Received initial testC2dMessageIndex: ${(this.maxReceivedIndex =
          obj.thief.testC2dMessageIndex)}`
      );
    } else if (this.maxReceivedIndex + 1 === obj.thief.testC2dMessageIndex) {
      logger.info(
        `Received next testC2dMessageIndex: ${++this.maxReceivedIndex}`
      );
    } else if (this.maxReceivedIndex < obj.thief.testC2dMessageIndex) {
      const missing = Array.from(
        { length: obj.thief.testC2dMessageIndex - this.maxReceivedIndex - 1 },
        (_, i) => 1 + i + this.maxReceivedIndex
      );
      logger.warn(
        `Received testC2dMessageIndex ${obj.thief.testC2dMessageIndex}, but never received indices ${missing}`
      );
      this.maxReceivedIndex = obj.thief.testC2dMessageIndex;
      if (
        (this.c2dMissingMessageCount += missing.length) >
        settings.receiveC2dAllowedMissingMessageCount
      ) {
        this.stopDeviceApp(
          new Error(
            `The number of missing C2D messages exceeds receiveC2dAllowedMissingMessageCount of ${settings.receiveC2dAllowedMissingMessageCount}.`
          )
        );
      }
    } else {
      logger.warn(`Received old index: ${obj.thief.testC2dMessageIndex}`);
    }
  }

  private handleServiceAckResponseMessage(obj: ThiefC2dMessage, msg: Message) {
    if (!Array.isArray(obj.thief.serviceAcks)) {
      this.client.reject(msg).catch(this.handleRejectC2dError);
      return logger.warn("Issue with serviceAcks property. Rejecting.");
    }
    logger.info(`Received serviceAckIds: ${obj.thief.serviceAcks}`);
    obj.thief.serviceAcks.forEach((id: string) => {
      if (this.serviceAckWaitList.has(id)) {
        this.serviceAckWaitList.delete(id);
      } else {
        logger.warn(`Received unknown serviceAckId: ${id}`);
      }
    });
    this.client.reject(msg).catch(this.handleRejectC2dError);
  }

  private handleRejectC2dError = (e: Error) => {
    if (e instanceof NotImplementedError) {
      return;
    }
    logger.error(`Error when rejecting C2D message: ${e}`);
    if (
      ++this.clientLibraryExceptionCount >
      settings.thiefAllowedClientLibraryExceptionCount
    ) {
      this.stopDeviceApp(
        new Error(
          `The number of client errors exceeds thiefAllowedClientLibraryExceptionCount of ${settings.thiefAllowedClientLibraryExceptionCount}.`
        )
      );
    }
  };

  private handleCompleteC2dError = (e: Error) => {
    logger.error(`Error when completing C2D message: ${e}`);
    if (
      ++this.clientLibraryExceptionCount >
      settings.thiefAllowedClientLibraryExceptionCount
    ) {
      this.stopDeviceApp(
        new Error(
          `The number of client errors exceeds thiefAllowedClientLibraryExceptionCount of ${settings.thiefAllowedClientLibraryExceptionCount}.`
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
      return logger.error("Failed to parse received C2D message. Rejecting.");
    }

    if (
      !obj.thief ||
      obj.thief.runId !== runId ||
      obj.thief.serviceInstanceId !== this.serviceInstanceId
    ) {
      this.client.reject(msg).catch(this.handleRejectC2dError);
      logger.warn("C2D received, but it's not for us: %j. Rejecting.", obj);
    } else if (obj.thief.cmd === "serviceAckResponse") {
      this.handleServiceAckResponseMessage(obj, msg);
    } else if (obj.thief.cmd === "testC2d") {
      this.handleTestC2dMessage(obj, msg);
    } else {
      this.client.reject(msg).catch(this.handleRejectC2dError);
      logger.error("Unknown command received: %j. Rejecting", obj);
    }
  };

  private async startC2dMessageSending() {
    const patch = {
      thief: {
        testControl: {
          c2d: {
            messageIntervalInSeconds: settings.receiveC2dIntervalInSeconds,
            send: true,
          },
        },
      },
    };
    logger.info("Enabling C2D message testing: %j", patch);
    await promisify(this.twin.properties.reported.update)(patch).catch(
      (e: Error) => {
        throw new Error(`Updating reported properties failed: ${e}`);
      }
    );
  }

  private onTelemetrySendInterval = () => {
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
    logger.info(`Sending message with serviceAckId: ${serviceAckId}`);
    this.client
      .sendEvent(message)
      .catch(() => {
        logger.error(
          `Error sending message with serviceAckId: ${serviceAckId}`
        );
      })
      .finally(() => {
        this.serviceAckWaitList.add(serviceAckId);
        if (
          this.serviceAckWaitList.size > settings.sendMessageAllowedFailureCount
        ) {
          return this.stopDeviceApp(
            new Error(
              `The number of service acks being waited on exceeds sendMessageAllowedFailureCount of ${settings.sendMessageAllowedFailureCount}.`
            )
          );
        }
      });
  };

  private async startTestOperations() {
    this.client.on("message", this.c2dMessageListener);
    logger.info("Starting telemetry sending.");
    this.telemetrySendingInterval = setInterval(
      this.onTelemetrySendInterval,
      1000 * settings.sendMessageOperationsPerSecond
    );
    await this.startC2dMessageSending().catch((e: Error) => {
      throw new Error(`Starting C2D message sending failed: ${e}`);
    });
  }

  stopDeviceApp(reason?: Signal | Error) {
    let code: number;
    let exitReasonString: string;
    if (reason instanceof Error) {
      code = 1;
      exitReasonString = `Stopping device app due to error: ${reason}`;
      logger.critical(exitReasonString);
    } else {
      code = 128 + reason;
      const signal =
        reason === Signal.SIGHUP
          ? "SIGHUP"
          : reason === Signal.SIGINT
          ? "SIGINT"
          : "SIGKILL";
      exitReasonString = `Stopping device app due to signal ${signal}`;
      logger.warn(exitReasonString);
    }
    appInsights.defaultClient.trackEvent({
      name: "EndingRun",
      properties: { exitReason: exitReasonString },
    });

    clearInterval(this.telemetrySendingInterval);
    clearTimeout(this.pairingAttemptTimer);
    clearTimeout(this.pairingTimer);
    if (this.twin) {
      this.twin.removeAllListeners();
    }
    if (this.client) {
      this.client.removeAllListeners();

      logger.info("Closing device client.");
      this.client
        .close()
        .then(() => logger.info("Device client closed."))
        .catch((e: Error) => logger.error(`Error closing client: ${e}`))
        .finally(() => process.exit(code));
      return;
    }
    process.exit(code);
  }

  async startDeviceApp() {
    logger.info("Starting device app.");
    const startingRunEvent: EventTelemetry = { name: "StartingRun" };
    if (runReason) {
      startingRunEvent.properties = { runReason: runReason };
    }
    appInsights.defaultClient.trackEvent(startingRunEvent);
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
  .startDeviceApp()
  .catch(() => logger.critical("Device app failed."));
