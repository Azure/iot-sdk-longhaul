// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for full license information.

export type ThiefSettings = {
  thiefMaxRunDurationInSeconds: number; //ignored for now
  thiefPropertyUpdateIntervalInSeconds: number;
  thiefWatchdogFailureIntervalInSeconds: number; //ignored for now
  thiefAllowedClientLibraryExceptionCount: number;
  pairingRequestTimeoutIntervalInSeconds: number;
  pairingRequestSendIntervalInSeconds: number;
  sendMessageOperationsPerSecond: number;
  sendMessageAllowedFailureCount: number;
  receiveC2dIntervalInSeconds: number;
  receiveC2dAllowedMissingMessageCount: number;
  reportedPropertiesUpdateIntervalInSeconds: number;
  reportedPropertiesAllowedFailureCount: number;
};

export type ThiefPairingProperties = {
  requestedServicePool?: string;
  serviceInstanceId: null | string;
  runId: string;
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

export const enum Signal {
  SIGHUP = 1,
  SIGINT = 2,
  SIGTERM = 15,
}
