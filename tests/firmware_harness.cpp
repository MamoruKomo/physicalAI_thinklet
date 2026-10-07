#include <cassert>
#include <cstdint>
#include <deque>
#include <sstream>
#include <string>
using byte = uint8_t;
unsigned long clockMs = 0;
unsigned long millis() { return clockMs; }
struct SerialStub {
  std::deque<char> input;
  std::ostringstream output;
  void begin(int) {}
  int available() { return input.size(); }
  char read() { char c = input.front(); input.pop_front(); return c; }
  template<class T> void print(T v) { output << v; }
  template<class T> void println(T v) { output << v << '\n'; }
} Serial;
#include "../arduino/brightness_arm/brightness_arm.ino"
void command(const std::string& text) {
  for(char c : text + "\n") Serial.input.push_back(c);
  loop();
}
int main() {
  setup(); assert(!arm.attached()); assert(!armed);
  command("HELLO"); assert(Serial.output.str().find("READY PHYSICAL_AI_ARM_V1") != std::string::npos);
  command("TARGET 100"); assert(!armed && !arm.attached());
  command("ARM 1 70 110 90"); assert(!armed && !arm.attached());
  command("ARM 9 70 110 190"); assert(!armed && !arm.attached());
  command("ARM 9 70 110 90 extra"); assert(!armed && !arm.attached());
  command("ARM 9 70 110 90"); assert(armed && arm.attached() && currentAngle == 90);
  command("TARGET 180"); assert(targetAngle == 90);
  command("TARGET 110"); assert(targetAngle == 110);
  clockMs = 29; loop(); assert(currentAngle == 90);
  clockMs = 30; loop(); assert(currentAngle == 91 && arm.lastAngle == 91);
  clockMs = 1201; loop(); assert(!armed && targetAngle == 91 && arm.attached());
  clockMs = 2000; command("PING"); loop(); assert(!armed && currentAngle == 91);
  command("TARGET 100"); assert(!armed && targetAngle == 91);
  command("ARM 9 70 110 90"); command("TARGET 70"); command("STOP");
  clockMs += 100; loop(); assert(!armed && currentAngle == 90 && targetAngle == 90);
  command(std::string(120, 'X')); assert(Serial.output.str().find("ERR command too long") != std::string::npos);
}
