#include <Servo.h>
#include <stdlib.h>
#include <string.h>

Servo arm;
bool armed = false;
int currentAngle = 90, targetAngle = 90, servoPin = 9, lowAngle = 70, highAngle = 110;
unsigned long lastCommand = 0, lastStep = 0;
char buffer[96]; byte length = 0; bool overflowed = false;

void report() {
  Serial.print("STATE "); Serial.print(armed ? 1 : 0);
  Serial.print(' '); Serial.print(currentAngle); Serial.print(' '); Serial.print(targetAngle);
  Serial.print(' '); Serial.print(servoPin); Serial.print(' '); Serial.print(lowAngle);
  Serial.print(' '); Serial.println(highAngle);
}

void stopArm() { armed = false; targetAngle = currentAngle; }

bool number(char *token, int &value) {
  if (!token || !*token) return false;
  char *end; long parsed = strtol(token, &end, 10);
  if (*end || parsed < 0 || parsed > 180) return false;
  value = (int)parsed; return true;
}

void handle(char *line) {
  if (!strcmp(line, "HELLO")) { Serial.println("READY PHYSICAL_AI_ARM_V1"); return; }
  if (!strcmp(line, "STOP")) { stopArm(); report(); return; }
  if (!strcmp(line, "STATUS")) { report(); return; }
  if (!strcmp(line, "PING")) { lastCommand = millis(); report(); return; }
  char *command = strtok(line, " ");
  if (command && !strcmp(command, "ARM")) {
    int pin, low, high, home;
    bool valid = number(strtok(NULL, " "), pin) && number(strtok(NULL, " "), low)
      && number(strtok(NULL, " "), high) && number(strtok(NULL, " "), home);
    if (!valid || strtok(NULL, " ") || pin < 2 || pin > 19 || low >= high || home < low || home > high) {
      Serial.println("ERR invalid ARM settings"); return;
    }
    if (arm.attached()) arm.detach();
    servoPin = pin; lowAngle = low; highAngle = high; currentAngle = targetAngle = home;
    // Set the requested pulse before attaching. No movement command is sent at boot.
    arm.write(currentAngle); arm.attach(servoPin);
    armed = true; lastCommand = lastStep = millis(); report(); return;
  }
  if (command && !strcmp(command, "TARGET")) {
    int angle;
    if (!number(strtok(NULL, " "), angle) || strtok(NULL, " ") || angle < lowAngle || angle > highAngle) {
      Serial.println("ERR target out of range"); return;
    }
    if (!armed) { Serial.println("ERR arm is stopped"); return; }
    targetAngle = angle; lastCommand = millis(); report(); return;
  }
  Serial.println("ERR unknown command");
}

void setup() {
  Serial.begin(115200);
  Serial.println("READY PHYSICAL_AI_ARM_V1");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      if (!overflowed) { buffer[length] = 0; handle(buffer); }
      else Serial.println("ERR command too long");
      length = 0; overflowed = false;
    } else if (c != '\r') {
      if (length < sizeof(buffer)-1) buffer[length++] = c;
      else overflowed = true;
    }
  }
  unsigned long now = millis();
  if (armed && now-lastCommand > 1200) stopArm();
  if (armed && now-lastStep >= 30) {
    lastStep = now;
    if (currentAngle < targetAngle) currentAngle++;
    else if (currentAngle > targetAngle) currentAngle--;
    arm.write(currentAngle);
  }
  // STOP/watchdog retain the last pulse to hold position; they do not cut servo power.
}
