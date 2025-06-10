#include <Wire.h>

#define UART_cycle_RX_PIN 16
#define UART_cycle_TX_PIN 17
#define UART_gps_RX_PIN 5
#define UART_gps_TX_PIN 18

HardwareSerial UART_cycle(1);
HardwareSerial UART_gps(2);

String gpsBuffer = "";
String cycleBuffer = "";

String gpsSendBuffer = "";
String cycleSendBuffer = "";

uint8_t currentCommand = 0;

void setup() {
  Serial.begin(9600);
  UART_cycle.begin(9600, SERIAL_8N1, UART_cycle_RX_PIN, UART_cycle_TX_PIN);
  UART_gps.begin(9600, SERIAL_8N1, UART_gps_RX_PIN, UART_gps_TX_PIN);
  Wire.begin(0x08);

  Wire.onReceive(receiveEvent);
  Wire.onRequest(requestEvent);

  Serial.println("ESP32 UART to Serial Monitor");
}

void loop() {
  // GPS data
  while (UART_gps.available()) {
    char c = UART_gps.read();
    gpsBuffer += c;
    if (c == '\n') {
      if (gpsBuffer.startsWith("$GNRM")){
        Serial.print("GPS: ");
        Serial.print(gpsBuffer);
        gpsSendBuffer = gpsBuffer;
        gpsLastHeld = gpsBuffer;
      }
      gpsBuffer = "";
    }
  }

  // Cycle data
  while (UART_cycle.available()) {
    char c = UART_cycle.read();
    cycleBuffer += c;
    if (c == '\n') {
      Serial.print("Cycle: ");
      Serial.print(cycleBuffer);
      cycleSendBuffer = cycleBuffer;
      cycleLastHeld = cycleBuffer;
      cycleBuffer = "";
    }
  }
  
  delay(75);
}

void receiveEvent(int howMany) {
  if (howMany > 0) {
    currentCommand = Wire.read(); // Read command byte from Pi
  }
}

void requestEvent() {
  Serial.print("Request of: ");
  const char* response = "Unknown";
  if (currentCommand == 0x01) {
    response = cycleSendBuffer.c_str();  // Corrected!
    Serial.print("A! -> ");
  } else if (currentCommand == 0x02) {
    response = gpsSendBuffer.c_str();  // Corrected!
    Serial.print("B! -> ");
  }

  Wire.write((const uint8_t*)response, strlen(response));  // Send exact length
  Serial.println(response);
}
