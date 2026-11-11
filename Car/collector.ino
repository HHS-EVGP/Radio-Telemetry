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
#include <Preferences.h>

// Change this to REDCAR/BLUECAR to select car settings
#define BLUECAR

#ifdef BLUECAR
#define CAR_ID "blue_445"
#endif
#ifdef REDCAR
#define CAR_ID "red_111"
#endif

// Echo the raw GPS and CA serial data to the USB serial
const bool uartDebug = true;

// Assign a unique ID to the IMU sensors
Adafruit_10DOF dof = Adafruit_10DOF();
Adafruit_LSM303_Accel_Unified accel = Adafruit_LSM303_Accel_Unified(30301);
Adafruit_LSM303_Mag_Unified mag = Adafruit_LSM303_Mag_Unified(30302);
Adafruit_BMP085_Unified bmp = Adafruit_BMP085_Unified(18001);

// Use the average sea level pressure
float seaLevelPressure = SENSORS_PRESSURE_SEALEVELHPA;

// GPS module on Serial2
Adafruit_GPS gps(&Serial2);

// Cycle Analyst (CA) serial
HardwareSerial caSerial(1);

// caBuffer collects characters as they arrive. Once a full, valid line is
// received it is copied to caLine, so new characters can't overwrite it before
// it is parsed
#define CA_BUF_SIZE 120
char caBuffer[CA_BUF_SIZE];
char caLine[CA_BUF_SIZE];
uint8_t caIndex = 0;
bool haveCA = false;

// Define ADCs
ADS1xx5_7semi adc1(0x48);
ADS1xx5_7semi adc2(0x49);

// Timestamp holders (from millis())
unsigned long uartWarnTimer = 0;

// Last time read from the GPS, and the millis() when it was read. Used to
// estimate the timestamp when a GPS message can't be parsed
double lastGPSTimestamp = NAN;
unsigned long lastGPSMillis = 0;

// Log file name
const String logFileName = "/evdata.txt";

// Pins
const int sdChipSelect = 5;
const int dataLight = 25;
const int errorLight = 26;

// Thermistor values
const float seriesResistor = 13000.0; // Ohms
const float adcMaxReading = 32767.0;  // Highest raw reading of the ADCs
// Steinhart-Hart coefficients
const float steinhartA = 1.009249522e-03;
const float steinhartB = 2.378405444e-04;
const float steinhartC = 2.019202697e-07;

// Energy totals, saved to the ESP32's internal flash so a reboot mid race picks up where it left off
Preferences energyPrefs;
const float caResetAh = 0.5;                    // A drop in amp hours bigger than this means the CA was reset
const unsigned long energySaveInterval = 30000; // ms between saves to flash
unsigned long energySaveTimer = 0;
double wattHrsTotal = 0; // Kept as a double so small steps aren't lost to rounding
float lastAmpHrs = NAN;
float lastVoltage = NAN;

// Battery estimate: fit voltage = restVoltage - resistance * current over windows of data
// (from the 2025-26 race analysis, this showed the voltage collapse about 8 minutes early)
const unsigned long battWindow = 30000; // ms of data per estimate
const int battMinSamples = 40;
const float battMinCurrentStd = 4; // Amps, needs enough change in current to see the sag
const float battMinR2 = 0.6;       // How cleanly the line has to fit
unsigned long battWindowStart = 0;
int battCount = 0;
double battSumI = 0, battSumV = 0, battSumII = 0, battSumVV = 0, battSumIV = 0;

// Receiver mac address
uint8_t broadcastAddress[] = {0x68, 0xFE, 0x71, 0x0B, 0x6D, 0x68};

// Packet structure
// The receiver copies the raw bytes of this struct, so it MUST stay identical
// (field order and types) to the TelemetryPacket in BaseStation/receiver.ino
typedef struct TelemetryPacket
{
  // Car ID is a fixed array of bytes since a regular String is just a pointer
  char id[12] = CAR_ID;

  double timestamp = NAN; // Unix time in seconds, NAN until the GPS gives a time

  // CA
  float ampHrs;
  float voltage;
  float current;
  float speed;
  float distance;

  // Calculated on the car from the CA data
  float wattHrs = 0;       // Integrated from voltage and the CA's amp hours, saved to flash
  float restVoltage = NAN; // Estimated open circuit voltage, NAN until the first good estimate
  float resistance = NAN;  // Estimated pack + wiring resistance in ohms

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

// The current data that all functions update
TelemetryPacket carData;

// Information needed to talk to the receiver
esp_now_peer_info_t peerInfo;

// Helper functions
void fatalError(String message)
{
  Serial.println(message);

  digitalWrite(errorLight, HIGH);
  while (true)
  {
    delay(100);
  }
}

void warning(String message)
{
  Serial.println(message);

  // "You have a message"
  digitalWrite(errorLight, HIGH);
  delay(20);
  digitalWrite(errorLight, LOW);
}

void initIMU()
{
  if (!accel.begin())
  {
    fatalError("IMU Accelerometer Initialization Error");
  }
  if (!mag.begin())
  {
    fatalError("IMU Magnetometer Initialization Error");
  }
  if (!bmp.begin())
  {
    fatalError("IMU Barometer Initialization Error");
  }
}

void getIMU()
{
  // Get Sensor Events
  sensors_event_t accelEvent;
  sensors_event_t magEvent;
  sensors_event_t bmpEvent;
  sensors_vec_t orientation;

  // Pitch and roll
  accel.getEvent(&accelEvent);
  if (dof.accelGetOrientation(&accelEvent, &orientation))
  {
    carData.roll = orientation.roll;
    carData.pitch = orientation.pitch;
  }
  else
  {
    warning("No Accelerometer Value!");
    carData.roll = carData.pitch = NAN;
  }

  // TODO: Acceleration calibrated based on pitch and roll

  // Heading
  mag.getEvent(&magEvent);
  if (dof.magGetOrientation(SENSOR_AXIS_Z, &magEvent, &orientation))
  {
    carData.heading = orientation.heading;
  }
  else
  {
    warning("No Magnetometer value!");
    carData.heading = NAN;
  }

  // Altitude and temperature
  bmp.getEvent(&bmpEvent);
  if (bmpEvent.pressure)
  {
    // Get ambient temperature in C
    float temperature;
    bmp.getTemperature(&temperature);

    // Convert atmospheric pressure, SLP and temp to altitude
    carData.ambientTemp = temperature;
    carData.altitude = bmp.pressureToAltitude(seaLevelPressure, bmpEvent.pressure, temperature);
  }
  else
  {
    warning("No Altitude or Temperature value!");
    carData.altitude = carData.ambientTemp = NAN;
  }
}

// Expects the TZ environment variable to be set to UTC (done in setup())
double toUnixTimestamp(
    int year, int month, int day,
    int hour, int minute, int seconds,
    int milliseconds)
{
  struct tm t = {0};

  t.tm_year = year + 100; // Adafruit GPS gives year as 0-99; t.tm_year is years since 1900
  t.tm_mon = month - 1;   // mktime expects months starting at 0
  t.tm_mday = day;
  t.tm_hour = hour;
  t.tm_min = minute;
  t.tm_sec = seconds;

  time_t unixSec = mktime(&t);

  // Return timestamp in seconds
  return (double)unixSec + (milliseconds / 1000.0);
}

double degToRad(double deg)
{
  return (deg / 180) * M_PI;
}

void getGPS()
{
  // Attempt to parse gps message
  bool parsed = gps.parse(gps.lastNMEA());

  // Give a warning if the parse fails after the first second
  // (The gps module spits out some system info at first)
  if (!parsed && millis() > 1000)
  {
    warning("GPS Parse Error!");
  }

  // The year stays 0 until the GPS module has gotten the date from a satellite
  if (parsed && gps.year != 0)
  {
    lastGPSTimestamp = toUnixTimestamp(gps.year, gps.month, gps.day,
                                       gps.hour, gps.minute, gps.seconds,
                                       gps.milliseconds);
    lastGPSMillis = millis();
    carData.timestamp = lastGPSTimestamp;
  }
  else if (!isnan(lastGPSTimestamp))
  {
    // Estimate the timestamp from how long it has been since the last GPS time
    carData.timestamp = lastGPSTimestamp + (millis() - lastGPSMillis) / 1000.0;
  }
  // Otherwise we have never had a GPS time, so the timestamp stays NAN

  carData.fix = parsed && gps.fix;
  if (!carData.fix)
  {
    carData.gpsX = NAN;
    carData.gpsY = NAN;
    return;
  }

  // Convert latitude and longitude to radians
  double latRad = degToRad(gps.latitudeDegrees);
  double lonRad = degToRad(gps.longitudeDegrees);

  // Mercator project latitude and longitude into x and y (meters)
  // 6378100 meters is the IAU nominal "zero tide" equatorial radius of the earth
  carData.gpsX = 6378100 * lonRad;
  carData.gpsY = 6378100 * log(tan((M_PI / 4) + (latRad / 2))); // in c++ log is natural log
}

// Count the tabs in a CA line. A valid line has exactly 4 (5 values)
bool verifyTabs(const char *buff)
{
  int count = 0;

  while (*buff != '\0')
  {
    if (*buff == '\t')
    {
      count++;
    }
    buff++;
  }

  return (count == 4);
}

// Read any available characters from the CA, setting haveCA when a full line is ready
void readCA()
{
  while (caSerial.available())
  {
    char c = caSerial.read();

    // Skip carriage returns
    if (c == '\r')
      continue;

    if (c == '\n')
    {
      // Null terminate the string and reset the buffer index
      caBuffer[caIndex] = '\0';
      caIndex = 0;

      // Log CA message if needed
      if (uartDebug)
      {
        Serial.println(caBuffer);
      }

      if (verifyTabs(caBuffer))
      {
        strcpy(caLine, caBuffer);
        haveCA = true;
      }
      else
      {
        warning("Invalid CA String");
      }
    }
    else if (caIndex < CA_BUF_SIZE - 1)
    {                          // If we have room in the buffer
      caBuffer[caIndex++] = c; // add c to the buffer while increasing the index
    }
  }
}

void getCA()
{
  // Input format:
  // ampHrs\tvoltage\tcurrent\tspeed\tdistance

  // One by one, search for the tab delimiter and extract the values
  char *value = strtok(caLine, "\t");
  if (value != NULL)
    carData.ampHrs = atof(value);

  value = strtok(NULL, "\t"); // Using NULL means to start where we left off
  if (value != NULL)
    carData.voltage = atof(value);

  value = strtok(NULL, "\t");
  if (value != NULL)
    carData.current = atof(value);

  value = strtok(NULL, "\t");
  if (value != NULL)
    carData.speed = atof(value);

  value = strtok(NULL, "\t");
  if (value != NULL)
    carData.distance = atof(value);

  // This line has been used, wait for the next one
  haveCA = false;
}

void initEnergy()
{
  energyPrefs.begin("energy", false);
  wattHrsTotal = energyPrefs.getDouble("wattHrs", 0);
  lastAmpHrs = energyPrefs.getFloat("ampHrs", NAN);
  carData.wattHrs = wattHrsTotal;
}

// Integrate voltage over the change in the CA's amp hours. Using the CA's own amp
// hour counter means CA lines that are skipped, or time the car was off, still count
void updateEnergy()
{
  float ampHrs = carData.ampHrs;
  float voltage = carData.voltage;
  if (isnan(ampHrs) || isnan(voltage))
    return;

  if (isnan(lastAmpHrs) || ampHrs < lastAmpHrs - caResetAh)
  {
    // No saved total, or the CA's amp hours were reset, so start over
    wattHrsTotal = ampHrs * voltage;
  }
  else
  {
    // Average with the last voltage, or use this one if the car just started
    float avgVoltage = isnan(lastVoltage) ? voltage : (voltage + lastVoltage) / 2;
    wattHrsTotal += (ampHrs - lastAmpHrs) * avgVoltage;
  }

  lastAmpHrs = ampHrs;
  lastVoltage = voltage;
  carData.wattHrs = wattHrsTotal;

  // Save the values to flash if it's time
  if (millis() - energySaveTimer >= energySaveInterval)
  {
    energyPrefs.putDouble("wattHrs", wattHrsTotal);
    energyPrefs.putFloat("ampHrs", ampHrs);
    energySaveTimer = millis();
  }
}

void resetBatteryWindow()
{
  battCount = 0;
  battSumI = battSumV = battSumII = battSumVV = battSumIV = 0;
  battWindowStart = millis();
}

// Collect current and voltage, and update the estimate at the end of each window
// The last good estimate is kept until a new one passes the checks
void updateBatteryEstimate()
{
  float current = carData.current;
  float voltage = carData.voltage;

  // Use a linear regression of the relationship between voltage and current
  // over the window to estimate resistance and sagging voltage
  // The slope of the line is -resistance, and the point at 0 current is the resting voltage
  if (!isnan(current) && !isnan(voltage) && voltage > 5)
  {
    battCount++;
    battSumI += current;
    battSumV += voltage;
    battSumII += current * current;
    battSumVV += voltage * voltage;
    battSumIV += current * voltage;
  }

  if (millis() - battWindowStart < battWindow)
    return;

  if (battCount >= battMinSamples)
  {
    double meanI = battSumI / battCount;
    double meanV = battSumV / battCount;
    double sii = battSumII - battCount * meanI * meanI;
    double svv = battSumVV - battCount * meanV * meanV;
    double siv = battSumIV - battCount * meanI * meanV;

    if (sqrt(sii / battCount) >= battMinCurrentStd && svv > 0 && siv * siv / (sii * svv) >= battMinR2)
    {
      double slope = siv / sii;
      carData.restVoltage = meanV - slope * meanI;
      carData.resistance = -slope;
    }
  }

  resetBatteryWindow();
}

void initADCs()
{
  if (!adc1.begin())
  {
    fatalError("ADC1 Initialization Error");
  }

  if (!adc2.begin())
  {
    fatalError("ADC2 Initialization Error");
  }

  // Set the voltage measurement range between 0 and 4.096v
  adc1.setRefV(PGA_4_096V);
  adc2.setRefV(PGA_4_096V);
}

// Convert a raw ADC reading of a thermistor voltage divider into degrees C
// This assumes the divider is powered by the ADC's full scale voltage (4.096v) // TODO: Fix this
float thermistor(float rawReading)
{
  if (rawReading <= 0)
  {
    return NAN;
  }

  float resistance = seriesResistor * (adcMaxReading / rawReading - 1);

  // Steinhart-Hart equation gives the temperature in Kelvin
  float logR = logf(resistance);
  float kelvin = 1.0f / (steinhartA + steinhartB * logR + steinhartC * powf(logR, 3));

  return kelvin - 273.15; // Convert to Celsius
}

void getAnalog()
{
  // Throttle and brake
  // The ADC goes from 0 to 32767, map values are changed to fit the sensor range
  // The output is 0 to 1000 (the brake sensor reads backwards, so it's flipped)
  carData.throttle = map(adc2.readRawCH(0), 0, 21298, 0, 1000);
  carData.brake = map(adc2.readRawCH(1), 420, 2600, 1000, 0);

  // Temperatures
  carData.motorTemp = thermistor(adc2.readRawCH(2));
  carData.batt1 = thermistor(adc1.readRawCH(0));
  carData.batt2 = thermistor(adc1.readRawCH(1));
  carData.batt3 = thermistor(adc1.readRawCH(2));
  carData.batt4 = thermistor(adc1.readRawCH(3));
}

void initSD()
{
  if (!SD.begin(sdChipSelect))
  {
    fatalError("SD Initialization Error");
  }
}

// Helper to convert a packet to a CSV line
String packetToString(const TelemetryPacket &packet)
{
  String s = "";
  s += String(packet.id) + ",";
  s += String(packet.timestamp) + ",";
  s += String(packet.ampHrs) + ",";
  s += String(packet.voltage) + ",";
  s += String(packet.current) + ",";
  s += String(packet.speed) + ",";
  s += String(packet.distance) + ",";
  s += String(packet.wattHrs) + ",";
  s += String(packet.restVoltage, 3) + ",";
  s += String(packet.resistance, 4) + ",";
  s += (packet.fix ? "True" : "False") + String(",");
  s += String(packet.gpsX) + ",";
  s += String(packet.gpsY) + ",";
  s += String(packet.throttle) + ",";
  s += String(packet.brake) + ",";
  s += String(packet.motorTemp) + ",";
  s += String(packet.batt1) + ",";
  s += String(packet.batt2) + ",";
  s += String(packet.batt3) + ",";
  s += String(packet.batt4) + ",";
  s += String(packet.ambientTemp) + ",";
  s += String(packet.roll) + ",";
  s += String(packet.pitch) + ",";
  s += String(packet.heading) + ",";
  s += String(packet.altitude);

  return s;
}

void writeData()
{
  // Open the file. Note that only one file can be open at a time
  File dataFile = SD.open(logFileName, FILE_APPEND);

  if (dataFile)
  {
    digitalWrite(dataLight, HIGH);

    dataFile.println(packetToString(carData)); // Append the file
    dataFile.close();

    digitalWrite(dataLight, LOW);
  }
  else
  {
    fatalError("Error opening data file");
  }
}

void onDataSent(const uint8_t *macAddr, esp_now_send_status_t status)
{
  Serial.println(status == ESP_NOW_SEND_SUCCESS ? "Delivery Success" : "Delivery Fail");
}

void initRF()
{
  // Wifi mode for esp-now
  WiFi.mode(WIFI_STA);

  // Start wifi to set configuration
  if (esp_wifi_start() != ESP_OK)
  {
    fatalError("WiFi start failed");
  }

  // Set low data rate mode
  esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_LR);

  // Override data rate to lowest possible
  // esp_wifi_config_espnow_rate(WIFI_IF_STA, WIFI_PHY_RATE_LORA_250K);

  // Set max power (units of 0.25 dBm, so 80 = 20 dBm)
  esp_wifi_set_max_tx_power(80);

  // Init ESP-NOW
  if (esp_now_init() != ESP_OK)
  {
    fatalError("Error initializing ESP-NOW");
  }

  // Register for send callback to get status of packet delivery
  // (The cast covers the callback signature differing between ESP32 core versions,
  // the first argument isn't used)
  esp_now_register_send_cb(esp_now_send_cb_t(onDataSent));

  // Register peer
  memcpy(peerInfo.peer_addr, broadcastAddress, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  // Add peer
  if (esp_now_add_peer(&peerInfo) != ESP_OK)
  {
    fatalError("Failed to add esp_now peer");
  }
}

void transmitData()
{
  // Send it!
  digitalWrite(dataLight, HIGH);
  esp_err_t result = esp_now_send(broadcastAddress, (uint8_t *)&carData, sizeof(carData));
  digitalWrite(dataLight, LOW);

  if (result != ESP_OK)
  {
    warning("Error transmitting data");
  }
}

void OnDataSent(const uint8_t *mac_addr, esp_now_send_status_t status)
{
  Serial.println(status == ESP_NOW_SEND_SUCCESS ? "Delivery Success" : "Delivery Fail");
}

void setup()
{
  // Start usb serial
  Serial.begin(115200);

  // Pin modes (set first so errors during setup can light the error light)
  pinMode(errorLight, OUTPUT);
  pinMode(dataLight, OUTPUT);

  // GPS times are UTC, so make mktime() work in UTC
  setenv("TZ", "UTC0", 1);
  tzset();

  // Set up esp-now
  initRF();

  // Start CA Serial
  caSerial.begin(9600, SERIAL_8N1, 27, 14); // use pins 27 and 14

  // Start GPS serial
  Serial2.begin(9600, SERIAL_8N1, 16, 17); // use pins 16 and 17 (EP 8 and 7)
  gps.begin(9600);

  // Configure gps module
  delay(500);                                   // Wait for the gps to boot
  gps.sendCommand(PMTK_SET_NMEA_OUTPUT_RMCGGA); // Output RMC and GGA
  gps.sendCommand(PMTK_SET_NMEA_UPDATE_5HZ);    // Output at 5 hz

  // Start IMU, SD, and ADC Connections
  initIMU();
  initSD();
  initADCs();

  // Load the saved energy totals and start the first battery estimate window
  initEnergy();
  resetBatteryWindow();

  // Throw away anything received during setup
  while (caSerial.available())
    caSerial.read();
  while (Serial2.available())
    Serial2.read();
}

void loop()
{
  // Timing is based off of GPS and CA messages
  // Each loop reads incoming characters until both have a complete message
  readCA();
  char c = gps.read();

  // Log gps message if needed
  if (uartDebug && c)
  {
    Serial.write(c);
  }

  // If we don't have a CA or a GPS message, wait
  if (!gps.newNMEAreceived() || !haveCA)
  {
    // Send a warning if it has been over a second since complete data
    if (millis() - uartWarnTimer >= 1000)
    {
      warning("Over 1 second since last full UART!");
      uartWarnTimer = millis(); // Reset the uart warning timer
    }
    return;
  }

  // Log when we got complete UART data
  uartWarnTimer = millis();

  // Get data
  getIMU();
  getGPS();
  getCA();
  getAnalog();

  // Values calculated from the CA data
  updateEnergy();
  updateBatteryEstimate();

  // Output the data for debug
  Serial.println(packetToString(carData));
  Serial.println();

  // Transmit and write data
  writeData();
  transmitData();
}
