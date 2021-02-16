// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for full license information.
import { thiefSettings } from './thiefSettings'
import { TimeoutError } from './timeout'
import { Mqtt as ProvisioningTransport } from 'azure-iot-provisioning-device-mqtt';
import { Mqtt as IotHubTransport } from 'azure-iot-device-mqtt';
import { SymmetricKeySecurityClient } from 'azure-iot-security-symmetric-key';
import { ProvisioningDeviceClient } from 'azure-iot-provisioning-device';
import { Client, Message, Twin } from 'azure-iot-device';
import { createHmac } from 'crypto';
import { v4 as uuidv4 } from 'uuid';
import { promisify } from 'util';

const provisioningHost = process.env.THIEF_DEVICE_PROVISIONING_HOST;
const idScope = process.env.THIEF_DEVICE_ID_SCOPE;
const groupSymmetricKey = process.env.THIEF_DEVICE_GROUP_SYMMETRIC_KEY;
const registrationId = process.env.THIEF_DEVICE_ID;
const requestedServicePool = process.env.THIEF_REQUESTED_SERVICE_POOL;
const runId = uuidv4();
if (!provisioningHost || !idScope || !groupSymmetricKey || !registrationId || !requestedServicePool) {
  throw new Error('Required environment variable is undefined.');
}

/* TODO:
  - Getting unhandledPromiseRejection when pairing times out
  - App doesn't terminate if the device app fails.
*/

const settings: thiefSettings = {
    thiefMaxRunDurationInSeconds: 0,
    thiefPropertyUpdateIntervalInSeconds: 30,
    thiefWatchdogFailureIntervalInSeconds: 300,
    thiefAllowedClientLibraryExceptionCount: 10,
    pairingRequestTimeoutIntervalInSeconds: 900,
    pairingRequestSendIntervalInSeconds: 30,
    sendMessageOperationsPerSecond: 1,
    sendMessageAllowedFailureCount: 1000,
    receiveC2dIntervalInSeconds: 20,
    receiveC2dAllowedMissingMessageCount: 100,
    reportedPropertiesUpdateIntervalInSeconds: 10,
    reportedPropertiesAllowedFailureCount: 50,
}

class DeviceApp {
  private async createDeviceClientUsingDpsGroupKey() {
    const deviceKey = createHmac('SHA256', Buffer.from(groupSymmetricKey, 'base64')).update(registrationId, 'utf8').digest('base64');
    const provisioningSecurityClient = new SymmetricKeySecurityClient(registrationId, deviceKey);
    const provisioningClient = ProvisioningDeviceClient.create(provisioningHost, idScope, new ProvisioningTransport(), provisioningSecurityClient);
    const registrationResultPromise = provisioningClient.register();
    if (!registrationResultPromise) {
      throw new Error('.register() did not return a promise when it should have.');
    }
    const registrationResult = await registrationResultPromise.catch(e => {throw new Error('DPS registration failed: ' + e.message)});
    const connectionString = 'HostName=' + registrationResult.assignedHub + ';DeviceId=' + registrationResult.deviceId + ';SharedAccessKey=' + deviceKey;
    const hubClient = Client.fromConnectionString(connectionString, IotHubTransport);
    await hubClient.open().catch(e => {throw new Error('Opening client failed: ' + e.message)});
    return hubClient;
  }

  private pairWithService() {
    console.info('Starting pairing operation.');
    const pairingRequestPatch = {
      thief: {
        pairing: {
          requestedServicePool: requestedServicePool,
          serviceInstanceId: null,
          runId: runId
        }
      }
    };

    let attemptTimer: NodeJS.Timeout;
    const pairWithServiceAttemptRecursive = () => {
      return new Promise<void>((res, rej) => {
        console.info('Updating pairing reported props: %j', pairingRequestPatch);
        promisify(this.twin.properties.reported.update)(pairingRequestPatch)
          .then(() => {
            // Register an event listener to listen for response from service app
            this.twin.on('properties.desired.thief.pairing', received => {
              if (this.serviceInstanceId) {
                console.info('Already paired. Ignoring');
              }
              else if (!received.runId || !received.serviceInstanceId) {
               console.info('runId and/or serviceId is missing. Ignoring.');
              }
              else if (received.runId !== runId) {
                console.info(`runId mismatch. Ignoring. (received ${received.runId}, expected ${runId})`);
              }
              else {
                console.info(`Service app ${received.serviceInstanceId} claimed this device instance`);
                this.twin.removeAllListeners('properties.desired.thief.pairing');
                clearTimeout(attemptTimer);
                this.serviceInstanceId = received.serviceInstanceId;
                const pairingAcceptPatch = {
                  thief: {
                    pairing: {
                      serviceInstanceId: received.serviceInstanceId,
                      runId: runId
                    }
                  }
                };
                console.info('Updating pairing reported props: %j', pairingAcceptPatch);
                promisify(this.twin.properties.reported.update)(pairingAcceptPatch)
                  .then(res)
                  .catch(e => rej(new Error('Updating reported properties failed: ' + e.message)));
              }
            });

            // If it's taking too long for a service app to response to our pairing request,
            // retry by recursively calling pairWithServiceAttemptRecursive()
            attemptTimer = setTimeout(() => {
              console.info('Pairing response timeout. Requesting again.');
              this.twin.removeAllListeners('properties.desired.thief.pairing');
              pairWithServiceAttemptRecursive().then(res).catch(e => rej(e));
            }, 1000 * this.settings.pairingRequestSendIntervalInSeconds);
          })
          .catch(e => rej(new Error('Updating reported properties failed: ' + e.message)));
      });
    }

    return new Promise<void>((res, rej) => {      
      // Call pairWithServiceAttemptRecursive. If its returned promise settles, handle accordingly.
      pairWithServiceAttemptRecursive().then(() => {
        console.info("Pairing with service complete.")
        clearTimeout(pairingTimer);
        res();
      }).catch(e => rej(e));

      // If the promise takes too long to settle, kill the pairing operation and reject.
      const pairingTimer = setTimeout(() => {
        this.twin.removeAllListeners('properties.desired.thief.pairing');
        clearTimeout(attemptTimer);
        rej(new TimeoutError(`No response to pairing requests after trying for ${this.settings.pairingRequestTimeoutIntervalInSeconds} seconds.`));
      }, 1000 * this.settings.pairingRequestTimeoutIntervalInSeconds);
    });
  }

  // Does not deal with out-of-order messages.
  // For example, If we get index 5 and then 7, we assume 6 is lost.
  private handleTestC2dMessage(obj) {
    if (Number.isNaN(obj.thief.testC2dMessageIndex) || typeof obj.thief.testC2dMessageIndex !== 'number') {
      console.warn('Issue with testC2dMessageIndex property');
    }
    else if (!this.maxReceivedIndex && this.maxReceivedIndex !== 0) {
      console.info(`Received initial testC2dMessageIndex: ${this.maxReceivedIndex = obj.thief.testC2dMessageIndex}`);
    }
    else if (this.maxReceivedIndex + 1 === obj.thief.testC2dMessageIndex) {
      console.info(`Received next testC2dMessageIndex: ${++this.maxReceivedIndex}`);
    }
    else if (this.maxReceivedIndex < obj.thief.testC2dMessageIndex) {
      const missing = Array.from({length: obj.thief.testC2dMessageIndex - this.maxReceivedIndex - 1}, (_, i) => 1 + i + this.maxReceivedIndex); 
      console.warn(`Received testC2dMessageIndex ${obj.thief.testC2dMessageIndex}, but never received indices ${missing}`);
      this.maxReceivedIndex = obj.thief.testC2dMessageIndex;
      if ((this.c2dMissingMessageCount += missing.length) > this.settings.receiveC2dAllowedMissingMessageCount) {
        console.error(`The number of missing C2D messages exceeds receiveC2dAllowedMissingMessageCount of ${this.settings.receiveC2dAllowedMissingMessageCount}. Exiting.`)
        //TODO: exit program
      }
    }
    else {
      console.warn(`Received old index: ${obj.thief.testC2dMessageIndex}`);
    }
  }

  private handleServiceAckResponseMessage(obj) {
    if (!Array.isArray(obj.thief.serviceAcks)) {
      return console.warn('Issue with serviceAcks property.');
    }
    console.info(`Received serviceAckIds: ${obj.thief.serviceAcks}`);
    obj.thief.serviceAcks.forEach(id => {
      if (this.serviceAckWaitList.has(id)) {
        this.serviceAckWaitList.delete(id);
      }
      else {
        console.warn(`Received unknown serviceAckId: ${id}`);
      }
    });
  }

  private registerMessageListener() {
    this.client.on('message', msg => {
      let obj;
      try {
        obj = JSON.parse(msg.getData());
      }
      catch {
        return console.warn('Failed to parse received C2D message.')
      }

      if (!obj.thief || obj.thief.runId !== runId || obj.thief.serviceInstanceId !== this.serviceInstanceId) {
        console.warn("C2D received, but it's not for us: %j", obj);
      }
      else if (obj.thief.cmd === 'serviceAckResponse') {
        this.handleServiceAckResponseMessage(obj);
      }
      else if (obj.thief.cmd === 'testC2d') {
        this.handleTestC2dMessage(obj);
      }
      else {
        console.warn('Unknown command received: %j', obj);
      }
    });
  }

  private startC2dMessageSending(): Promise<void> {
    const patch = {
      thief: {
        testControl: {
          c2d: {
            messageIntervalInSeconds: this.settings.receiveC2dIntervalInSeconds,
            send: true
          }
        }
      } 
    }
    console.info('Enabling C2D message testing: %j', patch);
    return promisify(this.twin.properties.reported.update)(patch);
  }

  private startTelemetrySending() {
    this.telemetrySendingInterval = setInterval(() => {
      if (this.serviceAckWaitList.size > this.settings.sendMessageAllowedFailureCount) {
        console.error(`The number of service acks being waited on exceeds sendMessageAllowedFailureCount of ${this.settings.sendMessageAllowedFailureCount}. Exiting.`);
        //TODO kill the program
      }

      const serviceAckId = uuidv4();
      const message = new Message(JSON.stringify({
        thief: {
          cmd: 'serviceAckRequest',
          serviceInstanceId: this.serviceInstanceId,
          runId: runId,
          serviceAckId: serviceAckId,
          serviceAckType: 'telemetry'
        }
      }));
      this.client.sendEvent(message)
        .catch(() => {console.warn('Error sending message with serviceAckId: ' + serviceAckId)})
        .finally(() => {this.serviceAckWaitList.add(serviceAckId)});
    }, 1000 * this.settings.sendMessageOperationsPerSecond);
  }

  private async startTestOperations() {
    this.registerMessageListener();
    this.startC2dMessageSending().catch(e => {throw new Error('Starting C2D message sending failed: ' + e.message)});
    this.startTelemetrySending();
  }

  async main(settings: thiefSettings) {
    this.settings = settings;
    this.telemetrySendingInterval; //avoid tsc complaining about not reading this value
    this.client = await this.createDeviceClientUsingDpsGroupKey().catch(e => {throw new Error('Creating device client failed: ' + e.message)});
    this.twin = await this.client.getTwin().catch(e => {throw new Error('Getting twin failed: ' + e.message)});
    await this.pairWithService().catch(e => {throw new Error('Pairing with service failed: ' + e.message)});
    await this.startTestOperations().catch(e => {throw new Error('Testing operation failed: ' + e.message)});
  }
  
  private telemetrySendingInterval: NodeJS.Timeout;
  private serviceAckWaitList: Set<string>;
  private maxReceivedIndex: number;
  private c2dMissingMessageCount: number;
  private serviceInstanceId: string;
  private settings: thiefSettings;
  private client: Client;
  private twin: Twin;

  private static instance: DeviceApp;
  static getInstance() {
    if (!this.instance) {
      this.instance = new DeviceApp();
    }
    return this.instance;
  }
  private constructor(){
    this.serviceAckWaitList = new Set();
    this.c2dMissingMessageCount = 0;
  }
}

DeviceApp.getInstance().main(settings).catch(e => {throw new Error('Device app failed: ' + e.message)});