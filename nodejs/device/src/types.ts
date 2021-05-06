// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for full license information.

export type ThiefSettings = {
  thiefAllowedClientLibraryExceptionCount: number;
  operationTimeoutInSeconds: number;
  operationTimeoutAllowedFailureCount: number;
  pairingRequestTimeoutIntervalInSeconds: number;
  pairingRequestSendIntervalInSeconds: number;
  sendMessageOperationsPerSecond: number;
  receiveC2dIntervalInSeconds: number;
  receiveC2dAllowedMissingMessageCount: number;
  twinUpdateIntervalInSeconds: number;
  metricsUpdateIntervalInSeconds: number;
};

export type ThiefPairingProperties = {
  requestedServicePool?: string;
  serviceInstanceId: null | string;
  runId: string;
};

export type TestReportedProperties = {
  thief: {
    testContent: {
      reportedPropertyTest: {
        [key: string]: any;
      };
    };
    sessionMetrics: SessionMetrics;
    testMetrics: TestMetrics;
  };
};

export type ThiefC2dMessage = {
  thief: {
    runId: string;
    serviceInstanceId: string;
    cmd: string;
    testC2dMessageIndex?: number;
    serviceAcks?: string[];
  };
};

export type AzureMonitorCustomProperties = {
  sdkLanguageVersion: string;
  sdkLanguage: string;
  sdkVersion: string;
  osType: string;
  poolId: string;
  hub?: string;
  transport: string;
  deviceId: string;
  runId: string;
};

export type SessionMetrics = {
  exitReason?: string;
  lastUpdateTimeUtc: string;
  runStartUtc: string;
  runState: "Waiting" | "Running" | "Failed" | "Complete" | "Interrupted";
  runTime: string;
};

export type TestMetrics = {
  receiveC2dCountMissing: number;
  receiveC2dCountReceived: number;
  reportedPropertiesCountAdded: number;
  reportedPropertiesCountRemoved: number;
  reportedPropertiesCountTimedOut: number;
  sendMessageCountSent: number;
  sendMessageCountNotReceivedByServiceApp: number;
  clientLibraryCountExceptions: number;
  getTwinCountSucceeded: number;
  getTwinCountTimedOut: number;
  desiredPropertyPatchCountReceived: number;
  desiredPropertyPatchCountTimedOut: number;
};

export const enum Signal {
  SIGHUP = 1,
  SIGINT = 2,
  SIGTERM = 15,
}
