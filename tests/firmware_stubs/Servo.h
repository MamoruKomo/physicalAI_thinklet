#pragma once
class Servo {
  bool connected = false;
public:
  int lastAngle = -1;
  void write(int angle) { lastAngle = angle; }
  void attach(int) { connected = true; }
  void detach() { connected = false; }
  bool attached() { return connected; }
};
