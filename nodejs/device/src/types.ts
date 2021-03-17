// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for full license information.

export type ThiefSettings = {
  thiefMaxRunDurationInSeconds: number;
  thiefPropertyUpdateIntervalInSeconds: number;
  thiefWatchdogFailureIntervalInSeconds: number;
  thiefAllowedClientLibraryExceptionCount: number;
  pairingRequestTimeoutIntervalInSeconds: number;
  pairingRequestSendIntervalInSeconds: number;
  sendMessageOperationsPerSecond: number;
  sendMessageAllowedFailureCount: number;
  receiveC2dIntervalInSeconds: number;
  receiveC2dAllowedMissingMessageCount: number;
  reportedPropertiesUpdateIntervalInSeconds: number;
  reportedPropertiesUpdateAllowedFailureCount: number;
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
  runState: "Waiting" | "Running" | "Failed" | "Complete" | "Interrupted"; //TODO: should this be uppercase or lowercase?
  runTime: string;
};

export type TestMetrics = {
  receiveC2dCountMissing: number;
  receiveC2dCountReceived: number;
  reportedPropertiesCountAdded: number;
  reportedPropertiesCountAddedButNotVerifiedByServiceApp: number;
  reportedPropertiesCountRemoved: number;
  reportedPropertiesCountRemovedButNotVerifiedByServiceApp: number;
  clientLibraryCountExceptions: number;
  sendMessageCountNotReceivedByServiceApp: number;
  sendMessageCountSent: number;
  sendMessageCountUnacked: number;
};

export const enum Signal {
  SIGHUP = 1,
  SIGINT = 2,
  SIGTERM = 15,
}
