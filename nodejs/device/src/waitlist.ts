// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for full license information.

import { TimeoutError } from "./errors";

export const enum OperationType {
  TELEMETRY = 0,
  ADD_REPORTED_PROPERTY,
  REMOVE_REPORTED_PROPERTY,
}

export type OperationResult = {
  id: string;
  latency: number;
};

type OperationWaitlistInfo = {
  addEpochTime: number;
  operationType: OperationType;
  resolve: (value: OperationResult | PromiseLike<OperationResult>) => void;
  timer?: NodeJS.Timeout;
};

export class OperationWaitlist {
  constructor() {
    this.waitlist = new Map<string, OperationWaitlistInfo>();
  }

  addOperation(id: string, operationType: OperationType, timeoutMs?: number) {
    return new Promise<OperationResult>((resolve, reject) => {
      this.waitlist.set(id, {
        addEpochTime: Date.now(),
        operationType: operationType,
        resolve: resolve,
        ...(timeoutMs && {
          timer: setTimeout(() => {
            if (this.waitlist.delete(id)) {
              reject(new TimeoutError(`Operation ID ${id} timed out.`));
            }
          }, timeoutMs),
        }),
      });
      ++this.pendingOperations[operationType];
    });
  }

  completeOperation(id: string) {
    let operationInfo: OperationWaitlistInfo;
    if (!(operationInfo = this.waitlist.get(id))) {
      return false;
    }
    clearTimeout(operationInfo.timer);
    const result = {
      id: id,
      latency: Date.now() - operationInfo.addEpochTime,
    };
    --this.pendingOperations[operationInfo.operationType];
    this.waitlist.delete(id);
    operationInfo.resolve(result);
    return true;
  }

  getPendingOperations(operationType: OperationType) {
    return this.pendingOperations[operationType];
  }

  private waitlist: Map<string, OperationWaitlistInfo>;
  private pendingOperations = {
    [OperationType.TELEMETRY]: 0,
    [OperationType.ADD_REPORTED_PROPERTY]: 0,
    [OperationType.REMOVE_REPORTED_PROPERTY]: 0,
  };
}
