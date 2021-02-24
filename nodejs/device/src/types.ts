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

export enum Signal {
  SIGHUP = 1,
  SIGINT = 2,
  SIGTERM = 15,
}
