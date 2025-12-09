#include <SPI.h>
#include <SD.h>
#include <Wire.h>
#include <time.h>
#include <math.h>

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

// CA Serial
HardwareSerial CA(2);
String caBuffer;

// Log file name
const String fileName = "EVGPData.txt";

// Pins
const int chipSelect = 29;

const int errorLight = 10;
const int writeLight = 11;
const int radioLight = 12;

const int throttlePin = 3;
const int brakePin = 4;
const int motorPin = 5;
const int batt1Pin = 6;
const int batt2Pin = 7;
const int batt3Pin = 8;
const int batt4Pin = 9;

// Thermistor values
const float R1 = 13000.0;
const float c1 = 1.009249522e-03;
const float c2 = 2.378405444e-04;
const float c3 = 2.019202697e-07;

// Receiver mac address
uint8_t broadcastAddress[] = { 0x68, 0xfe, 0x71, 0x0c, 0x84, 0x60 };

// Packet structure
typedef struct struct_message {
  // IMU
  float rool;
  float pitch;
  float heading;
  float altitude;
  float ambientTemp;

  // GPS
  double timestamp = NAN;  // Initial value
  bool fix;
  double gpsX;
  double gpsY;
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

esp_now_peer_info_t peerInfo;

// Helper functions
void fatalError(String message) {
  Serial.println(message);

  digitalWrite(errorLight, HIGH);
  while (true)
    ;
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

    carData.ambientTemp = temperature;
    carData.altitude = altitude;
  } else {
    warning("No Altitude or Temperature value!");
    carData.altitude = carData.ambientTemp = NAN;
  }
}

double toUnixTimestamp(
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
  return (double)unixSec + (milliseconds / 1000.0f);
}

double degToRad(double deg) {
  return (deg / 180) * M_PI;
}

void getGPS() {
  // Attempt to parse gps message
  if (!GPS.parse(GPS.lastNMEA())) {
    warning("GPS Parse Error!");

    // Add 1/100 a second to the timestamp (Very low risk for conflict with the next data point)
    if (carData.timestamp != NAN) {  // Would be NAN if we're on our first data point
      carData.timestamp += 0.01;     // This ensures every datapoint has a timestamp
    }

    // Set neutral values
    carData.fix = false;
    carData.gpsX = NAN;
    carData.gpsY = NAN;
    carData.angle = NAN;
  }

  // Populate varibles
  carData.timestamp = toUnixTimestamp(GPS.year, GPS.month, GPS.day,
                                      GPS.hour, GPS.minute, GPS.seconds,
                                      GPS.milliseconds);

  carData.fix = GPS.fix;
  carData.angle = GPS.angle;

  // Convert latitude and longitude to radians
  double latRad = degToRad(GPS.latitudeDegrees);
  double lonRad = degToRad(GPS.longitudeDegrees);

  // Mercator project latitude and longitude into x and y
  double x = 6378100 * lonRad;
  double y = 6378100 * log(tan((M_PI / 4) * (latRad / 2))); // in c++, log is ln
  // 6378100 meters is the IAU nominal "zero tide" eqatorial radius of the earth

  carData.gpsX = x;
  carData.gpsY = y;
}

void getCA(String caBuffer) {
  // Input from CA is: ampHrs|voltage|current|speed|miles\n

  // Find the index of each pipe
  int p1 = caBuffer.indexOf('|');
  int p2 = caBuffer.indexOf('|', p1 + 1);  // Look for pipe, starting at p1 + 1
  int p3 = caBuffer.indexOf('|', p2 + 1);
  int p4 = caBuffer.indexOf('|', p3 + 1);

  // Define variables based on indexes
  carData.ampHrs = caBuffer.substring(0, p1).toFloat();
  carData.voltage = caBuffer.substring(p1 + 1, p2).toFloat();
  carData.current = caBuffer.substring(p2 + 1, p3).toFloat();
  carData.speed = caBuffer.substring(p3 + 1, p4).toFloat();
  carData.miles = caBuffer.substring(p4 + 1).toFloat();  // toFloat() ignores the \n
}

float thermistor(float value) {
  value *= 1024 / 32768;
  float R2 = R1 * (1023 / value - 1);
  float T = 1.0f / (c1 + c2 * logf(R2) + c3 * powf(logf(R2), 3));
  T -= 273.15;  // Convert to Celcius

  return T;
}

void getAnalog() {
  // Throttle and brake
  carData.throttle = map(analogRead(throttlePin), 0, 4095, 0, 1000);
  carData.brake = map(analogRead(brakePin), 0, 4095, 0, 1000);

  // Temperatures
  carData.motorTemp = thermistor(analogRead(motorPin));
  carData.batt1 = thermistor(analogRead(batt1Pin));
  carData.batt2 = thermistor(analogRead(batt2Pin));
  carData.batt3 = thermistor(analogRead(batt3Pin));
  carData.batt4 = thermistor(analogRead(batt4Pin));
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
  s += String(msg.ambientTemp) + ",";
  s += (msg.fix ? "true" : "false") + String(",");
  s += String(msg.gpsX) + ",";
  s += String(msg.gpsY) + ",";
  s += String(msg.angle);
  s += String(msg.ampHrs);
  s += String(msg.voltage);
  s += String(msg.current);
  s += String(msg.speed);
  s += String(msg.miles);
  s += String(msg.throttle);
  s += String(msg.brake);
  s += String(msg.motorTemp);
  s += String(msg.batt1);
  s += String(msg.batt2);
  s += String(msg.batt3);
  s += String(msg.batt4);

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
  digitalWrite(radioLight, HIGH);
  esp_err_t result = esp_now_send(broadcastAddress, (uint8_t *)&carData, sizeof(carData));
  digitalWrite(radioLight, LOW);

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

  // Wifi mode for esp-now
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


  // Start CA Serial
  CA.begin(9600);

  // Start GPS serial
  GPS.begin(9600);

  // Configure gps module
  GPS.sendCommand(PMTK_SET_NMEA_OUTPUT_RMCGGA);
  GPS.sendCommand(PMTK_SET_NMEA_UPDATE_5HZ);

  // Pin modes
  pinMode(errorLight, OUTPUT);
  pinMode(writeLight, OUTPUT);
  pinMode(radioLight, OUTPUT);

  pinMode(throttlePin, INPUT);
  pinMode(brakePin, INPUT);
  pinMode(motorPin, INPUT);
  pinMode(batt1Pin, INPUT);
  pinMode(batt2Pin, INPUT);
  pinMode(batt3Pin, INPUT);
  pinMode(batt4Pin, INPUT);

  // Start IMU and SD connections
  initIMU();
  initSD();
}

void loop() {
  // Read CA (GPS is read in the background)
  char caChar = CA.read();
  caBuffer += caChar;

  // If we don't have a CA or a GPS message, wait
  if (!GPS.newNMEAreceived() || caChar != '\n') {
    return;
  }

  //Get data
  getIMU();
  getGPS();
  getCA(caBuffer);
  getAnalog();


  // Transmit and write data
  writeData();
  transmitData();
}
