#include <esp_now.h>
#include <WiFi.h>
#include <esp_wifi.h>

// Packet structure
typedef struct struct_message {
  // IMU
  float rool;
  float pitch;
  float heading;
  float altitude;
  float ambientTemp;

  // GPS
  float timestamp = NAN;  // Initial value
  bool fix;
  float latitude;
  float longitude;
  float angle;

  // CA
  float ampHrs;
  float voltage;
  float current;
  float speed;
  float miles;

  // Analog
  float throttle;
  float brake;
  float motorTemp;
  float batt1;
  float batt2;
  float batt3;
  float batt4;
} struct_message;

// Create a struct_message called carData
struct_message carData;

// callback function that will be executed when data is received
void OnDataRecv(const uint8_t *mac, const uint8_t *incomingData, int len) {
  // Copy the data over to the local carData struct
  memcpy(&carData, incomingData, sizeof(carData));

  // Pass the data to the pi
  Serial.print("$DATA,");

  // IMU
  Serial.print(carData.rool);
  Serial.print(",");
  Serial.print(carData.pitch);
  Serial.print(",");
  Serial.print(carData.heading);
  Serial.print(",");
  Serial.print(carData.altitude);
  Serial.print(",");
  Serial.print(carData.ambientTemp);
  Serial.print(",");

  // GPS
  Serial.print(carData.timestamp);
  Serial.print(",");
  Serial.print(carData.fix ? "true" : "false");
  Serial.print(",");
  Serial.print(carData.latitude);
  Serial.print(",");
  Serial.print(carData.longitude);
  Serial.print(",");
  Serial.print(carData.angle);
  Serial.print(",");

  // CA
  Serial.print(carData.ampHrs);
  Serial.print(",");
  Serial.print(carData.voltage);
  Serial.print(",");
  Serial.print(carData.current);
  Serial.print(",");
  Serial.print(carData.speed);
  Serial.print(",");
  Serial.print(carData.miles);
  Serial.print(",");

  // Analog
  Serial.print(carData.throttle);
  Serial.print(",");
  Serial.print(carData.brake);
  Serial.print(",");
  Serial.print(carData.motorTemp);
  Serial.print(",");
  Serial.print(carData.batt1);
  Serial.print(",");
  Serial.print(carData.batt2);
  Serial.print(",");
  Serial.print(carData.batt3);
  Serial.print(",");
  Serial.println(carData.batt4);
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
