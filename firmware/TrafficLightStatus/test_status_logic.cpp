#include "StatusLogic.h"

#include <cassert>
#include <cstring>

int main() {
  assert(parseStatus("idle") == Status::Idle);
  assert(parseStatus("busy\n") == Status::Busy);
  assert(parseStatus("attention\r\n") == Status::Attention);
  assert(parseStatus("thinking\n") == Status::Busy);
  assert(parseStatus("tool\r\n") == Status::Busy);
  assert(parseStatus("done") == Status::Idle);
  assert(parseStatus("error") == Status::Attention);
  assert(parseStatus("offline") == Status::Attention);
  assert(parseStatus("unknown") == Status::Unknown);

  LightState busyStart = resolveStatusLights(Status::Busy, 0, 1200);
  assert(!busyStart.red);
  assert(busyStart.yellow);
  assert(!busyStart.green);

  LightState busyLater = resolveStatusLights(Status::Busy, 1200, 1200);
  assert(!busyLater.red);
  assert(busyLater.yellow);
  assert(!busyLater.green);

  assert(resolveStatusWithCommandTimeout(Status::Busy, 1000, 1500, 1000) == Status::Busy);
  assert(resolveStatusWithCommandTimeout(Status::Busy, 1000, 2501, 1000) == Status::Idle);
  assert(resolveStatusWithCommandTimeout(Status::Attention, 1000, 2501, 1000) == Status::Idle);
  assert(resolveStatusWithCommandTimeout(Status::Idle, 1000, 2501, 1000) == Status::Idle);

  char text[] = "  thinking\r\n";
  trimInPlace(text);
  assert(std::strcmp(text, "thinking") == 0);

  return 0;
}
