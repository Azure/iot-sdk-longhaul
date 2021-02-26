// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for full license information.
import { SeverityLevel } from "applicationinsights/out/Declarations/Contracts";
import TelemetryClient from "applicationinsights/out/Library/TelemetryClient";
import { format } from "util";

export const enum LoggerSeverityLevel {
  INFO = 1,
  WARN = 2,
  ERROR = 3,
  CRITICAL = 4,
}

export type LoggerSettings = {
  consoleEnabled: boolean;
  consoleSeverityLevel?: LoggerSeverityLevel;
  appInsightsEnabled: boolean;
  appInsightsSeverityLevel?: LoggerSeverityLevel;
  appInsightsClient?: TelemetryClient;
};

export class Logger {
  constructor(settings: LoggerSettings) {
    if (settings.consoleEnabled) {
      if (!settings.consoleSeverityLevel) {
        throw new Error(
          "consoleSeverityLevel must be set if console logging is enabled."
        );
      }
      this.consoleEnabled = true;
      this.consoleSeverityLevel = settings.consoleSeverityLevel;
    }
    if (settings.appInsightsEnabled) {
      if (!settings.appInsightsSeverityLevel || !settings.appInsightsClient) {
        throw new Error(
          "appInsightsSeverityLevel and appInsightsClient must be set if Application Insights logging is enabled."
        );
      }
      this.appInsightsEnabled = true;
      this.appInsightsSeverityLevel = settings.appInsightsSeverityLevel;
      this.appInsightsClient = settings.appInsightsClient;
    }
  }

  info = this.log.bind(this, LoggerSeverityLevel.INFO);
  warn = this.log.bind(this, LoggerSeverityLevel.WARN);
  error = this.log.bind(this, LoggerSeverityLevel.ERROR);
  critical = this.log.bind(this, LoggerSeverityLevel.CRITICAL);

  private log(severity: LoggerSeverityLevel, ...args: any[]) {
    const message =
      this.severityLevelToString(severity) + ": " + format(...args);
    if (this.consoleEnabled && this.consoleSeverityLevel <= severity) {
      process.stderr.write(message + "\n");
    }
    if (this.appInsightsEnabled && this.appInsightsSeverityLevel <= severity) {
      this.appInsightsClient.trackTrace({
        message: message,
        severity: this.severityLevelToAppInsightsSeverity(severity),
      });
    }
  }

  private severityLevelToString(severity: LoggerSeverityLevel) {
    switch (severity) {
      case LoggerSeverityLevel.INFO:
        return "INFO";
      case LoggerSeverityLevel.WARN:
        return "WARN";
      case LoggerSeverityLevel.ERROR:
        return "ERROR";
      case LoggerSeverityLevel.CRITICAL:
        return "CRITICAL";
    }
  }
  private severityLevelToAppInsightsSeverity(severity: LoggerSeverityLevel) {
    switch (severity) {
      case LoggerSeverityLevel.INFO:
        return SeverityLevel.Information;
      case LoggerSeverityLevel.WARN:
        return SeverityLevel.Warning;
      case LoggerSeverityLevel.ERROR:
        return SeverityLevel.Error;
      case LoggerSeverityLevel.CRITICAL:
        return SeverityLevel.Critical;
    }
  }

  private consoleEnabled: boolean;
  private consoleSeverityLevel: LoggerSeverityLevel;
  private appInsightsEnabled: boolean;
  private appInsightsSeverityLevel: LoggerSeverityLevel;
  private appInsightsClient: TelemetryClient;
}
