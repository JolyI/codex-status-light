#pragma once

#include <cstring>

enum class Status {
  Unknown,
  Idle,
  Busy,
  Attention,
};

inline bool isSpaceChar(char value) {
  return value == ' ' || value == '\t' || value == '\r' || value == '\n';
}

inline void trimInPlace(char *text) {
  if (!text) {
    return;
  }

  char *start = text;
  while (*start && isSpaceChar(*start)) {
    start++;
  }

  char *end = start + std::strlen(start);
  while (end > start && isSpaceChar(*(end - 1))) {
    end--;
  }
  *end = '\0';

  if (start != text) {
    char *dst = text;
    while (*start) {
      *dst++ = *start++;
    }
    *dst = '\0';
  }
}

inline Status parseStatus(const char *rawText) {
  if (!rawText) {
    return Status::Unknown;
  }

  char text[24];
  std::strncpy(text, rawText, sizeof(text) - 1);
  text[sizeof(text) - 1] = '\0';
  trimInPlace(text);

  if (std::strcmp(text, "idle") == 0) {
    return Status::Idle;
  }
  if (std::strcmp(text, "busy") == 0) {
    return Status::Busy;
  }
  if (std::strcmp(text, "attention") == 0) {
    return Status::Attention;
  }
  if (std::strcmp(text, "thinking") == 0) {
    return Status::Busy;
  }
  if (std::strcmp(text, "tool") == 0) {
    return Status::Busy;
  }
  if (std::strcmp(text, "done") == 0) {
    return Status::Idle;
  }
  if (std::strcmp(text, "error") == 0) {
    return Status::Attention;
  }
  if (std::strcmp(text, "offline") == 0) {
    return Status::Attention;
  }
  return Status::Unknown;
}
