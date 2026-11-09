#include <esp_now.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <ArduinoJson.h>
#include <math.h>

// Packet structure
// The packet's raw bytes are copied into this struct, so it MUST stay identical
// (field order and types) to the TelemetryPacket in Car/collector.ino
typedef struct TelemetryPacket {
  char id[12];
  double timestamp;  // Unix time in seconds, NAN if the car has no GPS time

  // CA
  float ampHrs;
  float voltage;
  float current;
  float speed;
  float distance;

  // GPS
  bool fix;
  double gpsX;
  double gpsY;

  // Analog
  float throttle;
  float brake;
  float motorTemp;
  float batt1;
  float batt2;
  float batt3;
  float batt4;

  // IMU
  float ambientTemp;
  float roll;
  float pitch;
  float heading;
  float altitude;
} TelemetryPacket;


// The most recently received packet
TelemetryPacket carData;

// Callback function that will be executed when data is received
// Each packet is printed to serial as one line of JSON for station.py
void onDataRecv(const uint8_t *mac, const uint8_t *incomingData, int len) {
  // Ignore anything that isn't a telemetry packet
  if (len != sizeof(carData)) {
    Serial.println("Received packet with the wrong size");
    return;
  }

  // Copy the data over to the local carData struct
  memcpy(&carData, incomingData, sizeof(carData));
  carData.id[sizeof(carData.id) - 1] = '\0';  // Make sure the id is terminated

  // Create a json document with all the data
  // NAN values are serialized as null
  JsonDocument doc;
  doc["id"] = carData.id;

  // ArduinoJson writes large doubles in scientific notation, losing the
  // fractional seconds, so the timestamp is sent as integer milliseconds
  // station.py converts it back to seconds
  if (isnan(carData.timestamp)) {
    doc["timestamp"] = nullptr;
  } else {
    // llround ensures this conversin rounds up for accuracy if needed
    doc["timestamp"] = (uint64_t)llround(carData.timestamp * 1000);
  }

  doc["ampHrs"] = carData.ampHrs;
  doc["voltage"] = carData.voltage;
  doc["current"] = carData.current;
  doc["speed"] = carData.speed;
  doc["distance"] = carData.distance;
  doc["fix"] = carData.fix;
  doc["gpsX"] = carData.gpsX;
  doc["gpsY"] = carData.gpsY;
  doc["throttle"] = carData.throttle;
  doc["brake"] = carData.brake;
  doc["motorTemp"] = carData.motorTemp;
  doc["batt1"] = carData.batt1;
  doc["batt2"] = carData.batt2;
  doc["batt3"] = carData.batt3;
  doc["batt4"] = carData.batt4;
  doc["ambientTemp"] = carData.ambientTemp;
  doc["roll"] = carData.roll;
  doc["pitch"] = carData.pitch;
  doc["heading"] = carData.heading;
  doc["altitude"] = carData.altitude;

  // Print the json to serial
  String serialData;
  serializeJson(doc, serialData);
  Serial.println(serialData);
}

void setup() {
  // Initialize serial connection to the base station computer
  Serial.begin(115200);

  // Wifi Mode
  WiFi.mode(WIFI_STA);

  // Start wifi to set configuration
  if (esp_wifi_start() != ESP_OK) {
    Serial.println("WiFi start failed");
    ESP.restart();
  }

  // Set low data rate mode
  esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_LR);

  // Set max power (units of 0.25 dBm, so 80 = 20 dBm)
  esp_wifi_set_max_tx_power(80);

  // Start ESP-NOW
  if (esp_now_init() != ESP_OK) {
    Serial.println("Error initializing ESP-NOW");
    ESP.restart();
  }

  // Register for receive callback
  // (The cast covers the callback signature differing between ESP32 core versions,
  // the first argument isn't used)
  esp_now_register_recv_cb(esp_now_recv_cb_t(onDataRecv));
}

void loop() {
  // Nothing to do, packets are handled by the esp-now callback
}
