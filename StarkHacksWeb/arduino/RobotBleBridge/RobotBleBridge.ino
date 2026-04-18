#include <ArduinoBLE.h>

const char *deviceName = "OBSERVE-Robot";
BLEService robotService("19B10000-E8F2-537E-4F6C-D104768A1214");
BLEStringCharacteristic speechCharacteristic(
  "19B10001-E8F2-537E-4F6C-D104768A1214",
  BLERead | BLENotify,
  244
);
BLEStringCharacteristic commandCharacteristic(
  "19B10002-E8F2-537E-4F6C-D104768A1214",
  BLEWrite | BLEWriteWithoutResponse,
  244
);
BLEStringCharacteristic statusCharacteristic(
  "19B10003-E8F2-537E-4F6C-D104768A1214",
  BLERead | BLENotify,
  244
);

String serialLine = "";
unsigned long lastStatusMs = 0;

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 4000) {
  }

  if (!BLE.begin()) {
    Serial.println("BLE start failed");
    while (true) {
    }
  }

  BLE.setLocalName(deviceName);
  BLE.setDeviceName(deviceName);
  BLE.setAdvertisedService(robotService);

  robotService.addCharacteristic(speechCharacteristic);
  robotService.addCharacteristic(commandCharacteristic);
  robotService.addCharacteristic(statusCharacteristic);
  BLE.addService(robotService);

  speechCharacteristic.writeValue("{\"text\":\"OBSERV-E robot is ready.\",\"priority\":\"normal\",\"eventType\":\"startup\"}");
  statusCharacteristic.writeValue("{\"text\":\"BLE ready\"}");

  BLE.advertise();
  Serial.println("OBSERVE-Robot BLE ready");
}

void loop() {
  BLEDevice central = BLE.central();

  if (central) {
    Serial.print("Central connected: ");
    Serial.println(central.address());
    statusCharacteristic.writeValue("{\"text\":\"Web app connected\"}");

    while (central.connected()) {
      BLE.poll();
      forwardSerialToBle();
      readWebCommands();
      sendHeartbeat();
    }

    Serial.println("Central disconnected");
    statusCharacteristic.writeValue("{\"text\":\"Web app disconnected\"}");
  } else {
    BLE.poll();
    forwardSerialToBle();
    readWebCommands();
    sendHeartbeat();
  }
}

void forwardSerialToBle() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      serialLine.trim();
      if (serialLine.length() > 0) {
        speechCharacteristic.writeValue(serialLine.c_str());
      }
      serialLine = "";
    } else if (c != '\r') {
      serialLine += c;
    }
  }
}

void readWebCommands() {
  if (commandCharacteristic.written()) {
    String command = commandCharacteristic.value();
    Serial.print("WEB_COMMAND: ");
    Serial.println(command);
    statusCharacteristic.writeValue("{\"text\":\"Received web command\"}");
  }
}

void sendHeartbeat() {
  if (millis() - lastStatusMs > 15000) {
    lastStatusMs = millis();
    statusCharacteristic.writeValue("{\"text\":\"Robot heartbeat ok\"}");
  }
}
