export type thiefSettings = {
  thiefMaxRunDurationInSeconds: number, //ignored for now
  thiefPropertyUpdateIntervalInSeconds: number,
  thiefWatchdogFailureIntervalInSeconds: number, //ignored for now
  thiefAllowedClientLibraryExceptionCount: number,
  pairingRequestTimeoutIntervalInSeconds: number,
  pairingRequestSendIntervalInSeconds: number,
  sendMessageOperationsPerSecond: number,
  sendMessageAllowedFailureCount: number,
  receiveC2dIntervalInSeconds: number,
  receiveC2dAllowedMissingMessageCount: number,
  reportedPropertiesUpdateIntervalInSeconds: number,
  reportedPropertiesAllowedFailureCount: number,
}