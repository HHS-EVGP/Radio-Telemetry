#include <esp_now.h>
#include <WiFi.h>
#include <esp_wifi.h>

// Packet structure
typedef struct struct_message {
  double timestamp = NAN;  // Initial value

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
  float rool;
  float pitch;
  float heading;
  float altitude;
} struct_message;

// Create a struct_message called carData
struct_message carData;

// Helper to convert a packet to a string
String packetToString(const struct_message &msg) {
  String s = "";
  s += String(msg.timestamp) + ",";
  s += String(msg.ampHrs) + ",";
  s += String(msg.voltage) + ",";
  s += String(msg.current) + ",";
  s += String(msg.speed) + ",";
  s += String(msg.miles) + ",";
  s += (msg.fix ? "True" : "False") + String(",");
  s += String(msg.gpsX) + ",";
  s += String(msg.gpsY) + ",";
  s += String(msg.throttle) + ",";
  s += String(msg.brake) + ",";
  s += String(msg.motorTemp) + ",";
  s += String(msg.batt1) + ",";
  s += String(msg.batt2) + ",";
  s += String(msg.batt3) + ",";
  s += String(msg.batt4) + ",";
  s += String(msg.ambientTemp) + ",";
  s += String(msg.rool) + ",";
  s += String(msg.pitch) + ",";
  s += String(msg.heading) + ",";
  s += String(msg.altitude) + ",";

  return s;
}

// callback function that will be executed when data is received
void OnDataRecv(const uint8_t *mac, const uint8_t *incomingData, int len) {
  // Copy the data over to the local carData struct
  memcpy(&carData, incomingData, sizeof(carData));

  // Pass the data to the pi
  Serial.print("$DATA,");
  Serial.println(packetToString(carData));
}

void setup() {
  // Initialize serial connection to the pi
  Serial.begin(9600);

  // Enter Long range mode
  WiFi.mode(WIFI_STA);
  esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_LR);

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
