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
  userData: { [key: string]: any };
};

type OperationWaitlistInfo = {
  onComplete: ((err: TimeoutError, result: OperationResult) => void) | ((result: OperationResult) => void);
  addEpochTime: number;
  operationType: OperationType;
  userData: { [key: string]: any };
  timer?: NodeJS.Timeout;
};

export class OperationWaitlist {
  constructor() {
    this.waitlist = new Map<string, OperationWaitlistInfo>();
  }

  addCallbackBasedOperation(
    id: string,
    operationType: OperationType,
    userData: { [key: string]: any },
    onComplete: (result: OperationResult) => void
  ): void;
  addCallbackBasedOperation(
    id: string,
    operationType: OperationType,
    userData: { [key: string]: any },
    timeoutMs: number,
    onComplete: (err: TimeoutError, result: OperationResult) => void
  ): void;
  addCallbackBasedOperation(
    id: string,
    operationType: OperationType,
    userData: { [key: string]: any },
    callbackOrTimeout: ((result: OperationResult) => void) | number,
    errorCallback?: (err: TimeoutError, result: OperationResult) => void
  ) {
    const callback = typeof callbackOrTimeout === "function" ? callbackOrTimeout : errorCallback;
    this.waitlist.set(id, {
      onComplete: callback,
      addEpochTime: Date.now(),
      operationType: operationType,
      userData: userData,
      ...(typeof callbackOrTimeout === "number" && {
        timer: setTimeout(() => {
          if (this.waitlist.delete(id)) {
            (callback as (err: TimeoutError, result: OperationResult) => void)(
              new TimeoutError(`Operation ID ${id} timed out.`),
              null
            );
          }
        }, callbackOrTimeout),
      }),
    });
    ++this.pendingOperations[operationType];
  }

  addPromiseBasedOperation(
    id: string,
    operationType: OperationType,
    userData: { [key: string]: any },
    timeoutMs?: number
  ) {
    return new Promise<OperationResult>((resolve, reject) => {
      const promiseCallback = (err: TimeoutError, result: OperationResult) => {
        if (err) {
          reject(err);
        } else {
          resolve(result);
        }
      };
      if (timeoutMs) {
        this.addCallbackBasedOperation(id, operationType, userData, timeoutMs, promiseCallback);
      } else {
        this.addCallbackBasedOperation(id, operationType, userData, promiseCallback.bind(null, null));
      }
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
      userData: operationInfo.userData,
    };
    if (operationInfo.timer) {
      (operationInfo.onComplete as (err: TimeoutError, result: OperationResult) => void)(null, result);
    } else {
      (operationInfo.onComplete as (result: OperationResult) => void)(result);
    }
    --this.pendingOperations[operationInfo.operationType];
    this.waitlist.delete(id);
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
