// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for full license information.

export type ServiceAckWaitInfo = {
  onRemove: (latency: number, userData?: { [key: string]: any }) => void;
  addEpochTime: number;
  serviceAckType: ServiceAckType;
  userData?: any;
};

export const enum ServiceAckType {
  TELEMETRY_SERVICE_ACK = 0,
  ADD_REPORTED_PROPERTY_SERVICE_ACK,
  REMOVE_REPORTED_PROPERTY_SERVICE_ACK,
}

export class ServiceAckWaitList {
  constructor() {
    this.waitList = new Map<string, ServiceAckWaitInfo>();
  }

  add(
    serviceAckId: string,
    serviceAckType: ServiceAckType,
    onRemove: (latency: number, userData?: { [key: string]: any }) => void,
    userData?: { [key: string]: any }
  ) {
    this.waitList.set(serviceAckId, {
      onRemove: onRemove,
      addEpochTime: Date.now(),
      serviceAckType: serviceAckType,
      userData: userData,
    });

    switch (serviceAckType) {
      case ServiceAckType.TELEMETRY_SERVICE_ACK:
        ++this.pendingTelemetryServiceAcks;
        break;
      case ServiceAckType.ADD_REPORTED_PROPERTY_SERVICE_ACK:
        ++this.pendingAddReportedPropertyServiceAcks;
        break;
      case ServiceAckType.REMOVE_REPORTED_PROPERTY_SERVICE_ACK:
        ++this.pendingRemoveReportedPropertyServiceAck;
        break;
    }
  }

  remove(serviceAckId: string) {
    if (!this.waitList.has(serviceAckId)) {
      return false;
    }
    const info = this.waitList.get(serviceAckId);
    switch (info.serviceAckType) {
      case ServiceAckType.TELEMETRY_SERVICE_ACK:
        --this.pendingTelemetryServiceAcks;
        break;
      case ServiceAckType.ADD_REPORTED_PROPERTY_SERVICE_ACK:
        --this.pendingAddReportedPropertyServiceAcks;
        break;
      case ServiceAckType.REMOVE_REPORTED_PROPERTY_SERVICE_ACK:
        --this.pendingRemoveReportedPropertyServiceAck;
        break;
    }
    process.nextTick(
      info.onRemove,
      Date.now() - info.addEpochTime,
      info.userData
    );
    this.waitList.delete(serviceAckId);
    return true;
  }

  getPendingTelemetryServiceAcks() {
    return this.pendingTelemetryServiceAcks;
  }
  getPendingAddReportedPropertyServiceAcks() {
    return this.pendingAddReportedPropertyServiceAcks;
  }
  getPendingRemoveReportedPropertyServiceAcks() {
    return this.pendingRemoveReportedPropertyServiceAck;
  }

  private pendingTelemetryServiceAcks = 0;
  private pendingAddReportedPropertyServiceAcks = 0;
  private pendingRemoveReportedPropertyServiceAck = 0;
  private waitList: Map<string, ServiceAckWaitInfo>;
}
