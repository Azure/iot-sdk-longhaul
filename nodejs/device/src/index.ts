// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for full license information.
import {
  ThiefSettings,
  Signal,
  ThiefPairingProperties,
  ThiefC2dMessage,
  AzureMonitorCustomProperties,
  SessionMetrics,
  TestReportedProperties,
  TestMetrics,
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
import { OperationWaitlist, OperationType, OperationResult } from "./waitlist";

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
  hub: process.env.THIEF_IOTHUB_NAME,
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
  thiefMaxRunDurationInSeconds: 0, //ignored for now
  thiefPropertyUpdateIntervalInSeconds: 30,
  thiefWatchdogFailureIntervalInSeconds: 300, //ignored for now
  thiefAllowedClientLibraryExceptionCount: 10,
  pairingRequestTimeoutIntervalInSeconds: 900,
  pairingRequestSendIntervalInSeconds: 30,
  sendMessageOperationsPerSecond: 1,
  sendMessageAllowedFailureCount: 1000,
  receiveC2dIntervalInSeconds: 20,
  receiveC2dAllowedMissingMessageCount: 100,
  reportedPropertiesUpdateIntervalInSeconds: 10,
  reportedPropertiesUpdateAllowedFailureCount: 50,
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
      appInsights.defaultClient.commonProperties.serviceInstanceId = this.serviceInstanceId;
      appInsights.defaultClient.trackEvent({ name: "PairingComplete" });
      this.cancelPairingAttempt = undefined;
      return logger.info("Pairing with service complete.");
    }
    this.cancelPairingAttempt = undefined;
    throw new TimeoutError(
      `Pairing failed after trying for ${settings.pairingRequestTimeoutIntervalInSeconds} seconds`
    );
  }

  private incrementClientErrors() {
    appInsights.defaultClient.trackMetric({
      name: "ClientLibraryCountExceptions",
      value: ++this.testMetrics.clientLibraryCountExceptions,
    });
    if (
      this.testMetrics.clientLibraryCountExceptions >
      settings.thiefAllowedClientLibraryExceptionCount
    ) {
      throw new Error(
        `The number of client errors exceeds thiefAllowedClientLibraryExceptionCount of ${settings.thiefAllowedClientLibraryExceptionCount}.`
      );
    }
  }

  private startListeningC2dMessages(): [Promise<void>, () => void] {
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
        try {
          this.incrementClientErrors();
        } catch (err) {
          cleanUpAndReject(err);
        }
      };

      const handleCompleteC2dError = (err: Error) => {
        logger.error(`Error when completing C2D message: ${err}`);
        try {
          this.incrementClientErrors();
        } catch (err) {
          cleanUpAndReject(err);
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
        obj.thief.serviceAcks.forEach((id: string) => {
          if (!this.operationWaitlist.completeOperation(id)) {
            logger.warn(
              `Received unknown operation ID ${id}. Perhaps the operation timed out or was already completed.`
            );
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
          this.lastReceiveC2dTime = Date.now();
          appInsights.defaultClient.trackMetric({
            name: "ReceiveC2dCountReceived",
            value: ++this.testMetrics.receiveC2dCountReceived,
          });
        } else if (
          this.maxReceivedIndex + 1 ===
          obj.thief.testC2dMessageIndex
        ) {
          logger.info(
            `Received next testC2dMessageIndex: ${++this.maxReceivedIndex}`
          );
          const now = Date.now();
          appInsights.defaultClient.trackMetric({
            name: "LatencyBetweenC2dInSeconds",
            value: (now - this.lastReceiveC2dTime) / 1000,
          });
          this.lastReceiveC2dTime = now;
          appInsights.defaultClient.trackMetric({
            name: "ReceiveC2dCountReceived",
            value: ++this.testMetrics.receiveC2dCountReceived,
          });
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
          const now = Date.now();
          appInsights.defaultClient.trackMetric({
            name: "LatencyBetweenC2dInSeconds",
            value: (now - this.lastReceiveC2dTime) / 1000,
          });
          this.lastReceiveC2dTime = now;
          this.maxReceivedIndex = obj.thief.testC2dMessageIndex;
          appInsights.defaultClient.trackMetric({
            name: "ReceiveC2dCountMissing",
            value: (this.testMetrics.receiveC2dCountMissing += missing.length),
          });
          appInsights.defaultClient.trackMetric({
            name: "ReceiveC2dCountReceived",
            value: ++this.testMetrics.receiveC2dCountReceived,
          });
          if (
            (this.testMetrics.receiveC2dCountMissing += missing.length) >
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

  private startSendingTelemetry(): [Promise<void>, () => void] {
    logger.info("Starting telemetry sending.");
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
        logger.warn("Telemetry sending canceled.");
        cleanUpAndReject(new Canceled());
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
          .then(() => {
            this.operationWaitlist.addCallbackBasedOperation(
              serviceAckId,
              OperationType.TELEMETRY,
              {},
              (result: OperationResult) => {
                logger.info(
                  `Received serviceAck with serviceAckId ${result.id}`
                );
                appInsights.defaultClient.trackMetric({
                  name: "SendMessageCountNotReceivedByServiceApp",
                  value: this.operationWaitlist.getPendingOperations(
                    OperationType.TELEMETRY
                  ),
                });
                appInsights.defaultClient.trackMetric({
                  name: "LatencySendMessageToServiceAckInSeconds",
                  value: result.latency / 1000,
                });
              }
            );
            appInsights.defaultClient.trackMetric({
              name: "SendMessageCountSent",
              value: ++this.testMetrics.sendMessageCountSent,
            });
            appInsights.defaultClient.trackMetric({
              name: "SendMessageCountNotReceivedByServiceApp",
              value: this.operationWaitlist.getPendingOperations(
                OperationType.TELEMETRY
              ),
            });
            if (
              this.operationWaitlist.getPendingOperations(
                OperationType.TELEMETRY
              ) > settings.sendMessageAllowedFailureCount
            ) {
              cleanUpAndReject(
                new Error(
                  `The number of pending telemetry service acks being exceeds sendMessageAllowedFailureCount of ${settings.sendMessageAllowedFailureCount}.`
                )
              );
            }
          })
          .catch((err) => {
            logger.error(
              `Error sending message with serviceAckId ${serviceAckId}: ${err}`
            );
            try {
              this.incrementClientErrors();
            } catch (err) {
              cleanUpAndReject(err);
            }
          })
          .finally(() => {
            appInsights.defaultClient.trackMetric({
              name: "SendMessageCountUnacked",
              value: --this.testMetrics.sendMessageCountUnacked,
            });
          });
        appInsights.defaultClient.trackMetric({
          name: "SendMessageCountUnacked",
          value: ++this.testMetrics.sendMessageCountUnacked,
        });
      }, 1000 * settings.sendMessageOperationsPerSecond);
    });
    return [promise, cancel];
  }

  private updateThiefReportedProperties: () => Promise<void> = () => {
    const now = new Date();
    this.sessionMetrics.lastUpdateTimeUtc = now.toISOString();
    this.sessionMetrics.runTime = msToDurationString(
      now.getTime() - this.runStart.getTime()
    );
    const thiefPropertyPatch = {
      thief: {
        sessionMetrics: this.sessionMetrics,
        testMetrics: this.testMetrics,
      },
    };
    logger.info("Updating thief reported props: %j", thiefPropertyPatch);
    return promisify(this.twin.properties.reported.update)(thiefPropertyPatch);
  };

  private startSendingThiefReportedProperties(): [Promise<void>, () => void] {
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
        this.updateThiefReportedProperties().catch((err) => {
          logger.error(`Updating thief reported properties failed: ${err}`);
          try {
            this.incrementClientErrors();
          } catch (err) {
            cleanUpAndReject(err);
          }
        });
      }, 1000 * settings.thiefPropertyUpdateIntervalInSeconds);
    });
    return [promise, cancel];
  }

  private startTestingReportedProperties(): [Promise<void>, () => void] {
    logger.info("Starting reported properties testing.");
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
        logger.warn("Reported properties testing cancelled.");
        cleanUpAndReject(new Canceled());
      };

      const onPropertyRemovedAck = (result: OperationResult) => {
        logger.info(
          `Remove of reported property ${result.userData.propName} verified by service`
        );
        appInsights.defaultClient.trackMetric({
          name: "ReportedPropertiesCountRemovedButNotVerifiedByServiceApp",
          value: (this.testMetrics.reportedPropertiesCountRemovedButNotVerifiedByServiceApp = this.operationWaitlist.getPendingOperations(
            OperationType.REMOVE_REPORTED_PROPERTY
          )),
        });
        appInsights.defaultClient.trackMetric({
          name: "LatencyRemoveReportedPropertyToServiceAckInSeconds",
          value: result.latency / 1000,
        });
      };

      const onPropertyAddedAck = (result: OperationResult) => {
        logger.info(
          `Add of reported property ${result.userData.propName} verified by service`
        );
        appInsights.defaultClient.trackMetric({
          name: "ReportedPropertiesCountAddedButNotVerifiedByServiceApp",
          value: (this.testMetrics.reportedPropertiesCountAddedButNotVerifiedByServiceApp = this.operationWaitlist.getPendingOperations(
            OperationType.ADD_REPORTED_PROPERTY
          )),
        });
        appInsights.defaultClient.trackMetric({
          name: "LatencyAddReportedPropertyToServiceAckInSeconds",
          value: result.latency / 1000,
        });
        const patch: TestReportedProperties = {
          thief: {
            testContent: {
              reportedPropertyTest: {},
            },
          },
        };
        patch.thief.testContent.reportedPropertyTest[
          result.userData.propName
        ] = null;
        logger.info(`Removing test property ${result.userData.propName}`);
        promisify(this.twin.properties.reported.update)(patch)
          .then(() => {
            this.operationWaitlist.addCallbackBasedOperation(
              result.userData.removeAckId,
              OperationType.REMOVE_REPORTED_PROPERTY,
              { propName: result.userData.propName },
              onPropertyRemovedAck
            );
            appInsights.defaultClient.trackMetric({
              name: "ReportedPropertiesCountRemoved",
              value: ++this.testMetrics.reportedPropertiesCountRemoved,
            });
            appInsights.defaultClient.trackMetric({
              name: "ReportedPropertiesCountRemovedButNotVerifiedByServiceApp",
              value: (this.testMetrics.reportedPropertiesCountRemovedButNotVerifiedByServiceApp = this.operationWaitlist.getPendingOperations(
                OperationType.REMOVE_REPORTED_PROPERTY
              )),
            });
            const pendingCount =
              this.operationWaitlist.getPendingOperations(
                OperationType.ADD_REPORTED_PROPERTY
              ) +
              this.operationWaitlist.getPendingOperations(
                OperationType.REMOVE_REPORTED_PROPERTY
              );
            if (
              pendingCount >
              settings.reportedPropertiesUpdateAllowedFailureCount
            ) {
              cleanUpAndReject(
                new Error(
                  `The number of pending twin reported property add+remove service acks exceeds reportedPropertiesUpdateAllowedFailureCount of ${settings.reportedPropertiesUpdateAllowedFailureCount}.`
                )
              );
            }
          })
          .catch(() => {
            logger.error(
              `Removing test property ${result.userData.propName} failed.`
            );
            try {
              this.incrementClientErrors();
            } catch (err) {
              cleanUpAndReject(err);
            }
          });
      };

      let propertyIndex = 1;
      const interval = setInterval(() => {
        const addServiceAckId = uuidv4();
        const removeServiceAckId = uuidv4();
        const propertyName = `prop_${propertyIndex++}`;
        const patch: TestReportedProperties = {
          thief: {
            testContent: {
              reportedPropertyTest: {},
            },
          },
        };
        patch.thief.testContent.reportedPropertyTest[propertyName] = {
          addServiceAckId: addServiceAckId,
          removeServiceAckId: removeServiceAckId,
        };
        logger.info(`Adding test property ${propertyName}`);
        promisify(this.twin.properties.reported.update)(patch)
          .then(() => {
            this.operationWaitlist.addCallbackBasedOperation(
              addServiceAckId,
              OperationType.ADD_REPORTED_PROPERTY,
              {
                propName: propertyName,
                removeAckId: removeServiceAckId,
              },
              onPropertyAddedAck
            );
            appInsights.defaultClient.trackMetric({
              name: "ReportedPropertiesCountAdded",
              value: ++this.testMetrics.reportedPropertiesCountAdded,
            });
            appInsights.defaultClient.trackMetric({
              name: "ReportedPropertiesCountAddedButNotVerifiedByServiceApp",
              value: (this.testMetrics.reportedPropertiesCountAddedButNotVerifiedByServiceApp = this.operationWaitlist.getPendingOperations(
                OperationType.ADD_REPORTED_PROPERTY
              )),
            });
            const pendingCount =
              this.operationWaitlist.getPendingOperations(
                OperationType.ADD_REPORTED_PROPERTY
              ) +
              this.operationWaitlist.getPendingOperations(
                OperationType.REMOVE_REPORTED_PROPERTY
              );
            if (
              pendingCount >
              settings.reportedPropertiesUpdateAllowedFailureCount
            ) {
              cleanUpAndReject(
                new Error(
                  `The number of pending twin reported property add+remove service acks exceeds reportedPropertiesUpdateAllowedFailureCount of ${settings.reportedPropertiesUpdateAllowedFailureCount}.`
                )
              );
            }
          })
          .catch(() => {
            logger.error(`Adding test property ${propertyName} failed.`);
            try {
              this.incrementClientErrors();
            } catch (err) {
              cleanUpAndReject(err);
            }
          });
      }, 1000 * settings.reportedPropertiesUpdateIntervalInSeconds);
    });

    return [promise, cancel];
  }

  private async startTestOperations() {
    const promises = [];
    let startSendingThiefReportedPropertiesPromise: Promise<void>;
    [
      startSendingThiefReportedPropertiesPromise,
      this.cancelSendingThiefReportedProperties,
    ] = this.startSendingThiefReportedProperties();
    promises.push(
      startSendingThiefReportedPropertiesPromise.catch((err) => {
        if (!(err instanceof Canceled)) {
          throw err;
        }
      })
    );

    let startListeningC2dMessagesPromise: Promise<void>;
    [
      startListeningC2dMessagesPromise,
      this.cancelListeningC2dMessages,
    ] = this.startListeningC2dMessages();
    promises.push(
      startListeningC2dMessagesPromise.catch((err) => {
        if (!(err instanceof Canceled)) {
          throw err;
        }
      })
    );

    let startSendingTelemetryPromise: Promise<void>;
    [
      startSendingTelemetryPromise,
      this.cancelSendingTelemetry,
    ] = this.startSendingTelemetry();
    promises.push(
      startSendingTelemetryPromise.catch((err) => {
        if (!(err instanceof Canceled)) {
          throw err;
        }
      })
    );

    let startTestingReportedPropertiesPromise: Promise<void>;
    [
      startTestingReportedPropertiesPromise,
      this.cancelTestingReportedProperties,
    ] = this.startTestingReportedProperties();
    promises.push(
      startTestingReportedPropertiesPromise.catch((err) => {
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
      this.sessionMetrics.runState = "Failed";
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
      this.sessionMetrics.runState = "Interrupted";
    }

    if (this.cancelPairingAttempt) {
      this.cancelPairingAttempt();
    }
    if (this.cancelSendingTelemetry) {
      this.cancelSendingTelemetry();
    }
    if (this.cancelSendingThiefReportedProperties) {
      this.cancelSendingThiefReportedProperties();
    }
    if (this.cancelListeningC2dMessages) {
      this.cancelListeningC2dMessages();
    }
    if (this.cancelTestingReportedProperties) {
      this.cancelTestingReportedProperties();
    }

    appInsights.defaultClient.trackEvent({
      name: "EndingRun",
      properties: { exitReason: exitReasonString },
    });
    this.updateThiefReportedProperties().catch((err: Error) => {
      logger.error(`Updating thief reported properties failed: ${err}`);
    });

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
      runState: "Running",
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

  private cancelSendingThiefReportedProperties: () => void;
  private cancelSendingTelemetry: () => void;
  private cancelListeningC2dMessages: () => void;
  private cancelPairingAttempt: () => void;
  private cancelTestingReportedProperties: () => void;
  private runStart: Date;
  private sessionMetrics: SessionMetrics;
  private testMetrics: TestMetrics;
  private operationWaitlist: OperationWaitlist;
  private maxReceivedIndex: number;
  private lastReceiveC2dTime: number;
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
    this.operationWaitlist = new OperationWaitlist();
    this.testMetrics = {
      receiveC2dCountMissing: 0,
      receiveC2dCountReceived: 0,
      reportedPropertiesCountAdded: 0,
      reportedPropertiesCountAddedButNotVerifiedByServiceApp: 0,
      reportedPropertiesCountRemoved: 0,
      reportedPropertiesCountRemovedButNotVerifiedByServiceApp: 0,
      clientLibraryCountExceptions: 0,
      sendMessageCountNotReceivedByServiceApp: 0,
      sendMessageCountSent: 0,
      sendMessageCountUnacked: 0,
    };
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
