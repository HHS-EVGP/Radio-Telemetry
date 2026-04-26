// This program is meant to be run on an arduino with a second harware serial, such as the micro,
// to stand in place of the cycle analyst when the car is not available 

unsigned long txTime = 0;

void setup() {
  Serial.begin(115200);
  Serial1.begin(9600);
}

void loop() {
  if (millis() - txTime >= 200) {
    Serial1.println("1\t1\t3\t4\t5");
    Serial.println("'data' sent");
    txTime = millis();
  }
}
