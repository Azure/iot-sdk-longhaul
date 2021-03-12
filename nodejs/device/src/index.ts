// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for full license information.
import {
  ThiefSettings,
  Signal,
  ThiefPairingProperties,
  ThiefC2dMessage,
  AzureMonitorCustomProperties,
  SessionMetics,
} from "./types";
import { Canceled, TimeoutError } from "./errors";
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
import { msToDurationString } from "./duration";

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
      (err: Error) => {
        throw new Error(`DPS registration failed: ${err}`);
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
    await hubClient.open().catch((err: Error) => {
      throw new Error(`Opening client failed: ${err}`);
    });
    return hubClient;
  }

  private pairingAttempt(): [Promise<ThiefPairingProperties>, () => void] {
    let cancel: () => void;
    const promise = new Promise<ThiefPairingProperties>((resolve, reject) => {
      let cleanedUp = false;
      const cleanUp = () => {
        cleanedUp = true;
        this.twin.removeListener("properties.desired.thief.pairing", listener);
        clearTimeout(pairingAttemptTimer);
      };
      cancel = () => {
        if (cleanedUp) {
          return;
        }
        logger.warn("Pairing canceled.");
        cleanUp();
        reject(new Canceled());
      };
      const listener = (received: ThiefPairingProperties) => {
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
        cleanUp();
        resolve(received);
      };
      const on_timeout = () => {
        cleanUp();
        reject(
          new TimeoutError(
            "Pairing desired properties event not received in time."
          )
        );
      };
      this.twin.on("properties.desired.thief.pairing", listener);
      const pairingAttemptTimer = setTimeout(
        on_timeout,
        1000 * settings.pairingRequestSendIntervalInSeconds
      );
    });
    return [promise, cancel];
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

    const startTime = Date.now();

    while (
      Date.now() - startTime <=
      1000 * settings.pairingRequestTimeoutIntervalInSeconds
    ) {
      appInsights.defaultClient.trackEvent({ name: "SendingPairingRequest" });
      logger.info("Updating pairing reported props: %j", pairingRequestPatch);
      let pairingAttemptPromise: Promise<ThiefPairingProperties>;
      [
        pairingAttemptPromise,
        this.cancelPairingAttempt,
      ] = this.pairingAttempt();
      await promisify(this.twin.properties.reported.update)(
        pairingRequestPatch
      ).catch((err: Error) => {
        throw new Error(`Updating reported properties failed: ${err}`);
      });
      let patch: ThiefPairingProperties;
      try {
        patch = await pairingAttemptPromise;
      } catch (err) {
        if (err instanceof TimeoutError) {
          logger.warn(
            `Pairing response timed out after waiting for ${settings.pairingRequestSendIntervalInSeconds} seconds. Requesting again.`
          );
          continue;
        } else {
          throw err;
        }
      }
      this.serviceInstanceId = patch.serviceInstanceId;
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
      logger.info("Accepting pairing: %j", pairingAcceptPatch);
      await promisify(this.twin.properties.reported.update)(
        pairingAcceptPatch
      ).catch((err: Error) => {
        throw new Error(`Updating reported properties failed: ${err}`);
      });
      appInsights.defaultClient.trackEvent({ name: "PairingComplete" });
      return logger.info("Pairing with service complete.");
    }

    throw new TimeoutError(
      `Pairing failed after trying for ${settings.pairingRequestTimeoutIntervalInSeconds} seconds`
    );
  }

  private handleC2dMessages(): [Promise<void>, () => void] {
    let cancel: () => void;
    const promise = new Promise<void>((_, reject) => {
      let cleanedUp = false;
      const cleanUpAndReject = (err: Error) => {
        cleanedUp = true;
        this.client.removeListener("message", c2dMessageListener);
        reject(err);
      };
      cancel = () => {
        if (cleanedUp) {
          return;
        }
        logger.warn("C2D message handling canceled.");
        cleanUpAndReject(new Canceled());
      };
      const handleRejectC2dError = (err: Error) => {
        if (err instanceof NotImplementedError) {
          return;
        }
        logger.error(`Error when rejecting C2D message: ${err}`);
        if (
          ++this.clientLibraryExceptionCount >
          settings.thiefAllowedClientLibraryExceptionCount
        ) {
          cleanUpAndReject(
            new Error(
              `The number of client errors exceeds thiefAllowedClientLibraryExceptionCount of ${settings.thiefAllowedClientLibraryExceptionCount}.`
            )
          );
        }
      };

      const handleCompleteC2dError = (err: Error) => {
        logger.error(`Error when completing C2D message: ${err}`);
        if (
          ++this.clientLibraryExceptionCount >
          settings.thiefAllowedClientLibraryExceptionCount
        ) {
          cleanUpAndReject(
            new Error(
              `The number of client errors exceeds thiefAllowedClientLibraryExceptionCount of ${settings.thiefAllowedClientLibraryExceptionCount}.`
            )
          );
        }
      };

      const handleServiceAckResponseMessage = (
        obj: ThiefC2dMessage,
        msg: Message
      ) => {
        if (!Array.isArray(obj.thief.serviceAcks)) {
          this.client.reject(msg).catch(handleRejectC2dError);
          return logger.warn("Issue with serviceAcks property. Rejecting.");
        }
        this.client.complete(msg).catch(handleCompleteC2dError);
        logger.info(`Received serviceAckIds: ${obj.thief.serviceAcks}`);
        obj.thief.serviceAcks.forEach((id: string) => {
          if (this.serviceAckWaitList.has(id)) {
            this.serviceAckWaitList.delete(id);
          } else {
            logger.warn(`Received unknown serviceAckId: ${id}`);
          }
        });
      };

      // Does not deal with out-of-order messages.
      // For example, if we get index 5 and then 7, we assume 6 is lost.
      const handleTestC2dMessage = (obj: ThiefC2dMessage, msg: Message) => {
        if (
          Number.isNaN(obj.thief.testC2dMessageIndex) ||
          typeof obj.thief.testC2dMessageIndex !== "number"
        ) {
          this.client.reject(msg).catch(handleRejectC2dError);
          return logger.warn(
            "Issue with testC2dMessageIndex property. Rejecting."
          );
        }

        this.client.complete(msg).catch(handleCompleteC2dError);
        if (!this.maxReceivedIndex && this.maxReceivedIndex !== 0) {
          logger.info(
            `Received initial testC2dMessageIndex: ${(this.maxReceivedIndex =
              obj.thief.testC2dMessageIndex)}`
          );
        } else if (
          this.maxReceivedIndex + 1 ===
          obj.thief.testC2dMessageIndex
        ) {
          logger.info(
            `Received next testC2dMessageIndex: ${++this.maxReceivedIndex}`
          );
        } else if (this.maxReceivedIndex < obj.thief.testC2dMessageIndex) {
          const missing = Array.from(
            {
              length: obj.thief.testC2dMessageIndex - this.maxReceivedIndex - 1,
            },
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
            cleanUpAndReject(
              new Error(
                `The number of missing C2D messages exceeds receiveC2dAllowedMissingMessageCount of ${settings.receiveC2dAllowedMissingMessageCount}.`
              )
            );
          }
        } else {
          logger.warn(`Received old index: ${obj.thief.testC2dMessageIndex}`);
        }
      };

      const c2dMessageListener = (msg: Message) => {
        process.nextTick(() => {
          let obj: ThiefC2dMessage;
          try {
            obj = JSON.parse(msg.getData().toString());
          } catch {
            this.client.reject(msg).catch(handleRejectC2dError);
            return logger.error(
              "Failed to parse received C2D message. Rejecting."
            );
          }
          if (
            !obj.thief ||
            obj.thief.runId !== runId ||
            obj.thief.serviceInstanceId !== this.serviceInstanceId
          ) {
            this.client.reject(msg).catch(handleRejectC2dError);
            logger.warn(
              "C2D received, but it's not for us: %j. Rejecting.",
              obj
            );
          } else if (obj.thief.cmd === "serviceAckResponse") {
            handleServiceAckResponseMessage(obj, msg);
          } else if (obj.thief.cmd === "testC2d") {
            handleTestC2dMessage(obj, msg);
          } else {
            this.client.reject(msg).catch(handleRejectC2dError);
            logger.error("Unknown command received: %j. Rejecting", obj);
          }
        });
      };

      this.client.on("message", c2dMessageListener);
    });
    return [promise, cancel];
  }

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
      (err: Error) => {
        throw new Error(`Updating reported properties failed: ${err}`);
      }
    );
  }

  private sendTelemetry(): [Promise<void>, () => void] {
    logger.info("Starting telemetry sending.");
    let cancel: () => void;
    const promise = new Promise<void>((_, reject) => {
      let cleanedUp = false;
      let cleanupAndReject = (err: Error) => {
        cleanedUp = true;
        clearInterval(interval);
        reject(err);
      };
      cancel = () => {
        if (cleanedUp) {
          return;
        }
        logger.warn("Telemetry sending canceled.");
        cleanupAndReject(new Canceled());
      };
      const interval = setInterval(() => {
        const serviceAckId = uuidv4();
        const now = new Date();
        this.sessionMetrics.lastUpdateTimeUtc = now.toISOString();
        this.sessionMetrics.runTime = msToDurationString(
          now.getTime() - this.runStart.getTime()
        );
        const message = new Message(
          JSON.stringify({
            thief: {
              cmd: "serviceAckRequest",
              serviceInstanceId: this.serviceInstanceId,
              runId: runId,
              serviceAckId: serviceAckId,
              serviceAckType: "telemetry",
              sessionMetrics: this.sessionMetrics,
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
              this.serviceAckWaitList.size >
              settings.sendMessageAllowedFailureCount
            ) {
              cleanupAndReject(
                new Error(
                  `The number of service acks being waited on exceeds sendMessageAllowedFailureCount of ${settings.sendMessageAllowedFailureCount}.`
                )
              );
            }
          });
      }, 1000 * settings.sendMessageOperationsPerSecond);
    });
    return [promise, cancel];
  }

  private sendThiefReportedProperties(): [Promise<void>, () => void] {
    logger.info("Starting thief reported property sending.");
    let cancel: () => void;
    const promise = new Promise<void>((_, reject) => {
      let cleanedUp = false;
      let cleanUpAndReject = (err: Error) => {
        cleanedUp = true;
        clearInterval(interval);
        reject(err);
      };
      cancel = () => {
        if (cleanedUp) {
          return;
        }
        logger.warn("Thief reported properties sending canceled.");
        cleanUpAndReject(new Canceled());
      };

      const interval = setInterval(() => {
        const now = new Date();
        this.sessionMetrics.lastUpdateTimeUtc = now.toISOString();
        this.sessionMetrics.runTime = msToDurationString(
          now.getTime() - this.runStart.getTime()
        );
        const thiefPropertyPatch = {
          thief: { sessionMetrics: this.sessionMetrics },
        };
        logger.info("Updating thief reported props: %j", thiefPropertyPatch);
        promisify(this.twin.properties.reported.update)(
          thiefPropertyPatch
        ).catch((err: Error) => {
          logger.error(`Updating thief reported properties failed: ${err}`); //TODO: add a counter for these errors
        });
      }, 1000 * settings.thiefPropertyUpdateIntervalInSeconds);
    });
    return [promise, cancel];
  }

  private async startTestOperations() {
    const promises = [];
    let sendThiefReportedPropertiesPromise: Promise<void>;
    [
      sendThiefReportedPropertiesPromise,
      this.cancelSendThiefReportedProperties,
    ] = this.sendThiefReportedProperties();
    promises.push(
      sendThiefReportedPropertiesPromise.catch((err) => {
        if (!(err instanceof Canceled)) {
          throw err;
        }
      })
    );

    let sendTelemetryPromise: Promise<void>;
    [sendTelemetryPromise, this.cancelSendTelemetry] = this.sendTelemetry();
    promises.push(
      sendTelemetryPromise.catch((err) => {
        if (!(err instanceof Canceled)) {
          throw err;
        }
      })
    );

    let handleC2dMessagesPromise: Promise<void>;
    [
      handleC2dMessagesPromise,
      this.cancelHandleC2dMessages,
    ] = this.handleC2dMessages();
    promises.push(
      handleC2dMessagesPromise.catch((err) => {
        if (!(err instanceof Canceled)) {
          throw err;
        }
      })
    );

    promises.push(this.startC2dMessageSending());

    await Promise.all(promises);
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

    if (this.cancelPairingAttempt) {
      this.cancelPairingAttempt();
    }
    if (this.cancelSendTelemetry) {
      this.cancelSendTelemetry();
    }
    if (this.cancelSendThiefReportedProperties) {
      this.cancelSendThiefReportedProperties();
    }
    if (this.cancelHandleC2dMessages) {
      this.cancelHandleC2dMessages();
    }

    if (this.client) {
      logger.info("Closing device client.");
      this.client
        .close()
        .then(() => logger.info("Device client closed."))
        .catch((err: Error) => logger.error(`Error closing client: ${err}`))
        .finally(() => process.exit(code));
      return;
    }
    process.exit(code);
  }

  async startDeviceApp() {
    this.runStart = new Date();
    this.sessionMetrics = {
      lastUpdateTimeUtc: this.runStart.toISOString(),
      runStartUtc: this.runStart.toISOString(),
      runState: "running",
      runTime: msToDurationString(0),
    };
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
    } catch (err) {
      this.stopDeviceApp(err);
    }
  }

  private cancelSendThiefReportedProperties: () => void;
  private cancelSendTelemetry: () => void;
  private cancelHandleC2dMessages: () => void;
  private cancelPairingAttempt: () => void;
  private runStart: Date;
  private sessionMetrics: SessionMetics;
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
