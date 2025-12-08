#include <SPI.h>
#include <SD.h>
#include <Wire.h>
#include <time.h>

#include <Adafruit_Sensor.h>
#include <Adafruit_LSM303_U.h>
#include <Adafruit_BMP085_U.h>
#include <Adafruit_L3GD20_U.h>
#include <Adafruit_10DOF.h>
#include <Adafruit_GPS.h>

#include <esp_now.h>
#include <WiFi.h>
#include <esp_wifi.h>


// Assign a unique ID to the IMU sensors
Adafruit_10DOF dof = Adafruit_10DOF();
Adafruit_LSM303_Accel_Unified accel = Adafruit_LSM303_Accel_Unified(30301);
Adafruit_LSM303_Mag_Unified mag = Adafruit_LSM303_Mag_Unified(30302);
Adafruit_BMP085_Unified bmp = Adafruit_BMP085_Unified(18001);

// Sea Level Pressure
float seaLevelPressure = SENSORS_PRESSURE_SEALEVELHPA;

// Connect to the GPS helper on the hardware port
#define GPSSerial Serial1
Adafruit_GPS GPS(&GPSSerial);

// fileName
const String fileName = "EVGPData.txt";

// Pins
const int chipSelect = 10;
const int errorLight = 6;
const int writeLight = 7;
const int txLight = 8;

// Receiver mac address
uint8_t broadcastAddress[] = { 0x68, 0xfe, 0x71, 0x0c, 0x84, 0x60 };

// Packet structure
typedef struct struct_message {
  // IMU
  float rool;
  float pitch;
  float heading;
  float altitude;
  float temperature;

  // GPS
  float timestamp = NAN; // Initial value
  bool fix;
  float latitude;
  float longitude;
  float speed;
  float angle;
} struct_message;

// Create a struct_message called carData
struct_message carData;

esp_now_peer_info_t peerInfo;

// Helper functions
void fatalError(String message) {
  Serial.println(message);

  digitalWrite(errorLight, HIGH);
  while (true);
}

void warning(String message) {
  Serial.println(message);

  // "You have a message"
  digitalWrite(errorLight, HIGH);
  delay(20);
  digitalWrite(errorLight, LOW);
}

void initIMU() {
  if (!accel.begin()) {
    fatalError("IMU Accelerometer Initialization Error");
  }
  if (!mag.begin()) {
    fatalError("IMU Magnometer Initialization Error");
  }
  if (!bmp.begin()) {
    fatalError("IMU Barometer Initialization Error");
  }
}

void getIMU() {
  // Get Sensor Events
  sensors_event_t accel_event;
  sensors_event_t mag_event;
  sensors_event_t bmp_event;
  sensors_vec_t orientation;

  // Pitch and rool
  accel.getEvent(&accel_event);
  if (dof.accelGetOrientation(&accel_event, &orientation)) {
    carData.rool = orientation.roll;
    carData.pitch = orientation.pitch;
  } else {
    warning("No Accelerometer Value!");
    carData.rool = carData.pitch = NAN;
  }

  // Heading
  mag.getEvent(&mag_event);
  if (dof.magGetOrientation(SENSOR_AXIS_Z, &mag_event, &orientation)) {
    carData.heading = orientation.heading;
  } else {
    warning("No Magnometer value!");
    carData.heading = NAN;
  }

  // Altitude
  bmp.getEvent(&bmp_event);
  if (bmp_event.pressure) {
    // Get ambient temperature in C
    float temperature;
    bmp.getTemperature(&temperature);

    // Convert atmospheric pressure, SLP and temp to altitude
    float altitude;
    altitude = bmp.pressureToAltitude(seaLevelPressure, bmp_event.pressure, temperature);

    carData.temperature = temperature;
    carData.altitude = altitude;
  } else {
    warning("No Altitude or Temperature value!");
    carData.altitude = carData.temperature = NAN;
  }
}

float toUnixTimestamp(
  int year, int month, int day,
  int hour, int minute, int seconds,
  int milliseconds) {

  struct tm t = { 0 };

  t.tm_year = year + 2000;  // adafruit gps gives year as 0-99
  t.tm_mon = month - 1;     // mktime expects moths starting at 0
  t.tm_mday = day;
  t.tm_hour = hour;
  t.tm_min = minute;
  t.tm_sec = seconds;

  // Set to UTC
  setenv("TZ", "UTC0", 1);
  tzset();

  time_t unixSec = mktime(&t);

  // Add milliseconds
  return (float)unixSec + (milliseconds / 1000.0f);
}

void getGPS() {
  // Populate varibles
  carData.timestamp = toUnixTimestamp(GPS.year, GPS.month, GPS.day,
                                      GPS.hour, GPS.minute, GPS.seconds,
                                      GPS.milliseconds);

  carData.fix = GPS.fix;
  carData.latitude = GPS.latitude;
  carData.longitude = GPS.longitude;
  carData.speed = GPS.speed;
  carData.angle = GPS.angle;
}

void initSD() {
  if (!SD.begin(chipSelect)) {
    fatalError("SD Initialization Error");
  }
}

String packetToString(const struct_message &msg) {
  String s = "";
  s += String(msg.timestamp);
  s += String(msg.rool) + ",";
  s += String(msg.pitch) + ",";
  s += String(msg.heading) + ",";
  s += String(msg.altitude) + ",";
  s += String(msg.temperature) + ",";
  s += (msg.fix ? "1" : "0");
  s += ",";
  s += String(msg.latitude) + ",";
  s += String(msg.longitude) + ",";
  s += String(msg.speed) + ",";
  s += String(msg.angle);

  return s;
}

void writeData() {
  // open the file. note that only one file can be open at a time
  File dataFile = SD.open(fileName, FILE_WRITE);

  // if the file is available, write to it:
  if (dataFile) {
    digitalWrite(writeLight, HIGH);

    dataFile.println(packetToString(carData));
    dataFile.close();

    digitalWrite(writeLight, LOW);
  }
  // if the file isn't open, pop up an error:
  else {
    fatalError("Error opening data file");
  }
}

void transmitData() {
  // Send it!
  esp_err_t result = esp_now_send(broadcastAddress, (uint8_t *)&carData, sizeof(carData));

  if (result == ESP_OK) {
    Serial.println("Data sent with success");
  } else {
    warning("Error transmitting data");
  }
}

void OnDataSent(const uint8_t *mac_addr, esp_now_send_status_t status) {
  Serial.println(status == ESP_NOW_SEND_SUCCESS ? "Delivery Success" : "Delivery Fail");
}


void setup() {
  // Start usb serial
  Serial.begin(115200);

  // esp_now config
  WiFi.mode(WIFI_STA);

  // Enter Long range mode
  esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_LR);

  // Init ESP-NOW
  if (esp_now_init() != ESP_OK) {
    fatalError("Error initializing ESP-NOW");
  }

  // Register for send callback to get status of packet delivery
  esp_now_register_send_cb(esp_now_send_cb_t(OnDataSent));

  // Register peer
  memcpy(peerInfo.peer_addr, broadcastAddress, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  // Add peer
  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    fatalError("Failed to add esp_now peer");
  }


  // Start GPS serial
  GPS.begin(9600);

  // Configure gps module
  GPS.sendCommand(PMTK_SET_NMEA_OUTPUT_RMCGGA);
  GPS.sendCommand(PMTK_SET_NMEA_UPDATE_5HZ);

  // Pin modes
  pinMode(errorLight, OUTPUT);
  pinMode(writeLight, OUTPUT);
  pinMode(txLight, OUTPUT);

  // Start IMU and SD connections
  initIMU();
  initSD();
}

void loop() {
  // Base the timimg off of a GPS and CA input
  char gpsChar = GPS.read();
  if (!GPS.newNMEAreceived()) {
    return;
  }
  if (!GPS.parse(GPS.lastNMEA())) {
    warning("GPS Parse Error!");

    // Add 1/100 a second to the timestamp
    if (carData.timestamp == NAN){
      return; // This means we are still on our first data point
    }
    // This ensures every datapoint has a timestamp
    carData.timestamp += 0.01;

    // Set none values for each field
    carData.fix = false;
    carData.latitude = NAN;
    carData.longitude = NAN;
    carData.speed = NAN;
    carData.angle = NAN;
  }

  //Get data
  getIMU();
  getGPS();


  // Transmit and write data
  writeData();
  transmitData();
}

/*
Still need to add
  CA
  analog pins
*/
