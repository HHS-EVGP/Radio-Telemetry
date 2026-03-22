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
#include <7semi_ADS1xx5.h>

#include <esp_now.h>
#include <WiFi.h>
#include <esp_wifi.h>

#define UARTdebug true

// Assign a unique ID to the IMU sensors
Adafruit_10DOF dof = Adafruit_10DOF();
Adafruit_LSM303_Accel_Unified accel = Adafruit_LSM303_Accel_Unified(30301);
Adafruit_LSM303_Mag_Unified mag = Adafruit_LSM303_Mag_Unified(30302);
Adafruit_BMP085_Unified bmp = Adafruit_BMP085_Unified(18001);

// Use the average sea level pressure
float seaLevelPressure = SENSORS_PRESSURE_SEALEVELHPA;

// Define the gps serial
Adafruit_GPS GPS(&Serial2);

// CA Serial and buffer
HardwareSerial CA(1);

#define CA_BUF_SIZE 120
char CABuffer[CA_BUF_SIZE];
uint8_t CAIndex = 0;
bool haveCA = false;

// Define ADCs
ADS1xx5_7semi adc1(0x48);
ADS1xx5_7semi adc2(0x49);

// Timestamp Holders
unsigned long UARTwarnTimer = 0;
unsigned long lastValidGPS = 0;

// Log file name
const String fileName = "/evdata.txt";

// Pins
const int chipSelect = 5;
const int dataLight = 25;
const int errorLight = 26;

// Thermistor values
const float R1 = 13000.0;
const float c1 = 1.009249522e-03;
const float c2 = 2.378405444e-04;
const float c3 = 2.019202697e-07;

// Receiver mac address
uint8_t broadcastAddress[] = { 0x68, 0xfe, 0x71, 0x0c, 0x84, 0x60 };

// Packet structure
typedef struct struct_message {
  uint64_t timestamp = NAN;  // Initial value

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

// The current data that all functions update
struct_message carData;

// Information needed to talk to the receiver
esp_now_peer_info_t peerInfo;

// Helper functions
void fatalError(String message) {
  Serial.println(message);

  digitalWrite(errorLight, HIGH);
  while (true) {
    delay(100);
  }
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

  // Pitch and roll
  accel.getEvent(&accel_event);
  if (dof.accelGetOrientation(&accel_event, &orientation)) {
    carData.roll = orientation.roll;
    carData.pitch = orientation.pitch;
  } else {
    warning("No Accelerometer Value!");
    carData.roll = carData.pitch = NAN;
  }

  // TODO: Acceleration callibrated based on pitch and roll

  // Heading
  mag.getEvent(&mag_event);
  if (dof.magGetOrientation(SENSOR_AXIS_Z, &mag_event, &orientation)) {
    carData.heading = orientation.heading;
  } else {
    warning("No Magnometer value!");
    carData.heading = NAN;
  }

  // Altitude and temperature
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

uint64_t toUnixTimestamp(
  int year, int month, int day,
  int hour, int minute, int seconds,
  int milliseconds) {

  struct tm t = { 0 };

  t.tm_year = year + 100;  // adafruit gps gives year as 0-99; t.tm_year is years since 1900
  t.tm_mon = month - 1;    // mktime expects moths starting at 0
  t.tm_mday = day;
  t.tm_hour = hour;
  t.tm_min = minute;
  t.tm_sec = seconds;

  // Set to UTC
  setenv("TZ", "UTC0", 1);
  tzset();

  time_t unixSec = mktime(&t);

  // Return timestamp in milliseconds
  return (uint64_t)unixSec * 1000 + milliseconds;
}

double degToRad(double deg) {
  return (deg / 180) * M_PI;
}

void getGPS() {
  // Attempt to parse gps message
  if (!GPS.parse(GPS.lastNMEA())) {
    // Give a warning if the parse fails after the first second
    // (The gps module spits out some system info at first)
    if (millis() > 1000) {
      warning("GPS Parse Error!");
    }

    // Derive the timestamp from how long it has been since the last GPS point
    if (carData.timestamp != NAN) {  // Timestamp would be NAN if we're on our first data point
      carData.timestamp = millis() - lastValidGPS + carData.timestamp;
    }

    // Set neutral values
    carData.fix = false;
    carData.gpsX = NAN;
    carData.gpsY = NAN;

    return;
  }

  // Timestamp when we got valid GPS data
  lastValidGPS = millis();

  // Populate varibles
  carData.timestamp = toUnixTimestamp(GPS.year, GPS.month, GPS.day,
                                      GPS.hour, GPS.minute, GPS.seconds,
                                      GPS.milliseconds);

  carData.fix = GPS.fix;

  // Convert latitude and longitude to radians
  double latRad = degToRad(GPS.latitudeDegrees);
  double lonRad = degToRad(GPS.longitudeDegrees);

  // Mercator project latitude and longitude into x and y
  double x = 6378100 * lonRad;
  double y = 6378100 * log(tan((M_PI / 4) + (latRad / 2)));  // in c++ log is natural log
  // 6378100 meters is the IAU nominal "zero tide" equatorial radius of the earth

  carData.gpsX = x;
  carData.gpsY = y;
}

void readCA() {
  if (CA.available()) {
    char c = CA.read();

    // Skip carrage returns
    if (c == '\r') return;

    if (c == '\n') {
      // Null terminate the string
      CABuffer[CAIndex] = '\0';
      // Reset the buffer index
      CAIndex = 0;

      // Log CA message if needed
      if (UARTdebug) {
        Serial.println(CABuffer);
      }

      // Verify that we have five |s in our message
      if (verifyPipes(CABuffer)) {
        haveCA = true;
      } else {
        warning("Invalid CA String");
      }

    } else if (CAIndex < CA_BUF_SIZE - 1) {  // If we have room in the buffer
      CABuffer[CAIndex++] = c;               // add c to the buffer while increasing the index
    }
  }
}

bool verifyPipes(char *buff) {
  int count = 0;

  while (*buff != '\0') {
    if (*buff == '|') {
      count++;
    }
    buff++;
  }

  return (count == 4);  // true if count is 4
}

void getCA(char *caBuffer) {
  // Input from CA is: ampHrs|voltage|current|speed|miles\n

  // One by one, search for the | delemiter and extract the variables
  char *value = strtok(caBuffer, "|");
  if (value != NULL) carData.ampHrs = atof(value);

  value = strtok(NULL, "|");  // Using NULL means to start where we left off
  if (value != NULL) carData.voltage = atof(value);

  value = strtok(NULL, "|");
  if (value != NULL) carData.current = atof(value);

  value = strtok(NULL, "|");
  if (value != NULL) carData.speed = atof(value);

  value = strtok(NULL, "|");
  if (value != NULL) carData.miles = atof(value);

  // Reset haveCA
  haveCA = false;
}

void initADCs() {
  if (!adc1.begin()) {
    fatalError("ADC1 Initialization Error");
  }

  if (!adc2.begin()) {
    fatalError("ADC2 Initialization Error");
  }

  // Set the voltage measurment range between 0 and 4.096v
  adc1.setRefV(PGA_4_096V);
  adc2.setRefV(PGA_4_096V);
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
  carData.throttle = map(adc2.readRawCH(0), 0, 32767, 0, 1000);
  carData.brake = map(adc2.readRawCH(1), 0, 32767, 0, 1000);

  // Temperatures
  carData.motorTemp = thermistor(adc2.readRawCH(2));
  carData.batt1 = thermistor(adc1.readRawCH(0));
  carData.batt2 = thermistor(adc1.readRawCH(1));
  carData.batt3 = thermistor(adc1.readRawCH(2));
  carData.batt4 = thermistor(adc1.readRawCH(3));
}

void initSD() {
  if (!SD.begin(chipSelect)) {
    fatalError("SD Initialization Error");
  }
}

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
  s += String(msg.roll) + ",";
  s += String(msg.pitch) + ",";
  s += String(msg.heading) + ",";
  s += String(msg.altitude);

  return s;
}

void writeData() {
  // open the file. note that only one file can be open at a time
  File dataFile = SD.open(fileName, FILE_APPEND);

  // if the file is available, write to it:
  if (dataFile) {
    digitalWrite(dataLight, HIGH);

    dataFile.println(packetToString(carData));  // Append the file
    dataFile.close();

    digitalWrite(dataLight, LOW);
  } else {
    fatalError("Error opening data file");
  }
}

void initRF() {
  // Wifi mode for esp-now
  WiFi.mode(WIFI_STA);

  // Start wifi to set configuration
  if (esp_wifi_start() != ESP_OK) {
    fatalError("WiFi start failed");
  }

  // Set low data rate mode
  esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_LR);

  // Override data rate to lowest possible
  //esp_wifi_config_espnow_rate(WIFI_IF_STA, WIFI_PHY_RATE_LORA_250K);

  // Set max power
  esp_wifi_set_max_tx_power(80);  //20 dbm

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
}

void transmitData() {
  // Send it!
  digitalWrite(dataLight, HIGH);
  esp_err_t result = esp_now_send(broadcastAddress, (uint8_t *)&carData, sizeof(carData));
  digitalWrite(dataLight, LOW);

  if (result != ESP_OK) {
    warning("Error transmitting data");
  }
}

void OnDataSent(const uint8_t *mac_addr, esp_now_send_status_t status) {
  Serial.println(status == ESP_NOW_SEND_SUCCESS ? "Delivery Success" : "Delivery Fail");
}


void setup() {
  // Start usb serial
  Serial.begin(115200);

  // Set up esp-now
  initRF();

  // Start CA Serial
  CA.begin(9600, SERIAL_8N1, 27, 14);  // use pins 27 and 14

  // Start Seral2 for gps
  Serial2.begin(9600, SERIAL_8N1, 16, 17);  // use pins 16 and 17 (EP 8 and 7)
  GPS.begin(9600);

  // Configure gps module
  delay(500);                                    // Give the gps time to boot
  GPS.sendCommand(PMTK_SET_NMEA_OUTPUT_RMCGGA);  // Output RMC and GGA
  GPS.sendCommand(PMTK_SET_NMEA_UPDATE_5HZ);     // Output at 5 hz

  // Pin modes
  pinMode(errorLight, OUTPUT);
  pinMode(dataLight, OUTPUT);

  // Start IMU, SD, and ADC Connections
  initIMU();
  initSD();
  initADCs();
}

void loop() {
  // Timing is based off of GPS and CA mesasges
  readCA();
  char c = GPS.read();

  // Log gps message if needed
  if (UARTdebug && c) {
    Serial.write(c);
  }

  // If we don't have a CA or a GPS message, wait
  if (!GPS.newNMEAreceived() || !haveCA) {
    // Send a warning if it has been over a second since complete data
    if (millis() - UARTwarnTimer >= 1000) {
      warning("Over 1 second since last full UART!");
      UARTwarnTimer = millis();  // Restet the uart warning timer
    }
    return;
  }

  // Log when we got complete UART data
  UARTwarnTimer = millis();

  //Get data
  getIMU();
  getGPS();
  getCA(CABuffer);
  getAnalog();

  // Output the data for debug
  Serial.println(packetToString(carData));
  Serial.println();

  // Transmit and write data
  writeData();
  transmitData();
}
