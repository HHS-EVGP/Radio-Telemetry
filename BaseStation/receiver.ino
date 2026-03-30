#include <esp_now.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <ArduinoJson.h>

// Packet structure
typedef struct struct_message {
  double timestamp;

  // CA
  float ampHrs;
  float voltage;
  float current;
  float speed;
  float miles;

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
} struct_message;


// Create a struct_message called carData
struct_message carData;

// callback function that will be executed when data is received
void OnDataRecv(const uint8_t *mac, const uint8_t *incomingData, int len) {
  // Copy the data over to the local carData struct
  memcpy(&carData, incomingData, sizeof(carData));

  // Convert timestamp to milliseconds to make ArduinoJson happy
  uint64_t milliStamp = carData.timestamp * 100;

  // Create a json document with all the data
  JsonDocument doc;
  doc["timestamp"] = milliStamp;
  doc["ampHrs"] = carData.ampHrs;
  doc["voltage"] = carData.voltage;
  doc["current"] = carData.current;
  doc["speed"] = carData.speed;
  doc["miles"] = carData.miles;
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
  // Initialize serial connection to the pi
  Serial.begin(115200);

  // Wifi Mode
  WiFi.mode(WIFI_STA);

  // Start wifi to set configuration
  if (esp_wifi_start() != ESP_OK) {
      Serial.println("WiFi start failed");
      return;
  }

  // Set lowa data rate mode
  esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_LR);

  // Set max power
  esp_wifi_set_max_tx_power(80); //~20 dbm

  // Start ESP-NOW
  if (esp_now_init() != ESP_OK) {
    Serial.println("Error initializing ESP-NOW");
    ESP.restart();
  }

  // Register for recveir callback
  esp_now_register_recv_cb(esp_now_recv_cb_t(OnDataRecv));
}

void loop() {
  // Wait for an interupt from esp-now
}
