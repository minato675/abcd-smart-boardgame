#include <SoftwareSerial.h>
#include <Adafruit_NeoPixel.h>

// =====================================================
// 캐비닛 설정
// =====================================================

// 1번 캐비닛은 1, 2번 캐비닛은 2로 변경
const int CABINET_ID = 1;

// =====================================================
// 핀 설정
// =====================================================

const int DOOR_SENSOR_PIN = 2;  // 마그네틱 센서 NC
const int LOCK_PIN        = 3;  // MOSFET PWM
const int LED_PIN         = 6;  // WS2812B DI

const int BT_RX_PIN = 10;       // Arduino RX ← Bluetooth TX
const int BT_TX_PIN = 11;       // Arduino TX → Bluetooth RX

const int LED_COUNT = 12;

// =====================================================
// 장치 객체
// =====================================================

SoftwareSerial bluetooth(BT_RX_PIN, BT_TX_PIN);

Adafruit_NeoPixel leds(
  LED_COUNT,
  LED_PIN,
  NEO_GRB + NEO_KHZ800
);

// =====================================================
// 동작 시간 설정
// =====================================================

// 잠금장치 최대 작동 시간
const unsigned long LOCK_ACTIVE_TIME_MS = 3000;

// 문이 열린 상태로 너무 오래 유지되는 시간
const unsigned long DOOR_OPEN_WARNING_MS = 60000;

// 센서 채터링 방지 시간
const unsigned long SENSOR_DEBOUNCE_MS = 100;

// =====================================================
// 잠금장치 출력 설정
// =====================================================

// 현재 MOSFET이 HIGH일 때 잠금 해제되는 것을 기준으로 작성
const int LOCK_OPEN_SIGNAL   = HIGH;
const int LOCK_CLOSED_SIGNAL = LOW;

// =====================================================
// 마그네틱 센서 설정
// =====================================================

// COM → GND
// NC  → D2
// INPUT_PULLUP 사용 기준
//
// 일반적으로:
// 문 닫힘 = LOW
// 문 열림 = HIGH
//
// 실제 센서 동작이 반대라면 아래 두 값을 서로 바꿔주세요.

const int DOOR_CLOSED_SIGNAL = LOW;
const int DOOR_OPEN_SIGNAL   = HIGH;

// =====================================================
// 캐비닛 상태
// =====================================================

enum CabinetState {
  STATE_DEFAULT,
  STATE_WAITING_FOR_OPEN,
  STATE_WAITING_FOR_CLOSE
};

enum ProcessMode {
  MODE_NONE,
  MODE_RECEIVE,
  MODE_RETURN
};

CabinetState currentState = STATE_DEFAULT;
ProcessMode currentMode = MODE_NONE;

// =====================================================
// 상태 변수
// =====================================================

unsigned long lockStartedTime = 0;
unsigned long doorOpenedTime = 0;

bool lockPowerOn = false;
bool doorOpenWarningSent = false;

// 센서 디바운싱용
int lastRawDoorState = DOOR_CLOSED_SIGNAL;
int stableDoorState = DOOR_CLOSED_SIGNAL;

unsigned long lastSensorChangeTime = 0;

// Bluetooth 수신 문자열
String receivedCommand = "";

// =====================================================
// 초기 설정
// =====================================================

void setup() {
  Serial.begin(9600);
  bluetooth.begin(9600);

  pinMode(DOOR_SENSOR_PIN, INPUT_PULLUP);
  pinMode(LOCK_PIN, OUTPUT);

  digitalWrite(LOCK_PIN, LOCK_CLOSED_SIGNAL);

  leds.begin();
  leds.setBrightness(50);

  // 센서 초기 상태 읽기
  lastRawDoorState = digitalRead(DOOR_SENSOR_PIN);
  stableDoorState = lastRawDoorState;

  setDefaultState();

  sendCallback("SYSTEM_STARTED");

  // 전원이 켜질 때 문이 열려 있으면 알림
  if (isDoorOpen()) {
    sendCallback("STARTUP_DOOR_OPEN");
  }
}

// =====================================================
// 반복 실행
// =====================================================

void loop() {
  readBluetoothCommand();
  updateDoorSensor();
  updateCabinetState();
}

// =====================================================
// Bluetooth 명령 수신
// =====================================================

void readBluetoothCommand() {
  while (bluetooth.available()) {
    char receivedChar = bluetooth.read();

    // 줄바꿈을 명령 종료로 사용
    if (receivedChar == '\n' || receivedChar == '\r') {
      receivedCommand.trim();

      if (receivedCommand.length() > 0) {
        processCommand(receivedCommand);
      }

      receivedCommand = "";
    } else {
      receivedCommand += receivedChar;

      // 비정상적으로 긴 문자열 방지
      if (receivedCommand.length() > 100) {
        receivedCommand = "";
        sendCallback("INVALID_COMMAND");
      }
    }
  }
}

// =====================================================
// 명령 처리
// =====================================================

void processCommand(String command) {
  command.trim();
  command.toUpperCase();

  Serial.print("Received: ");
  Serial.println(command);

  // 캐비닛 번호가 포함된 명령인지 확인
  String cabinetPrefix =
    "CABINET:" + String(CABINET_ID) + "|COMMAND:";

  bool cabinetCommand = command.startsWith(cabinetPrefix);

  bool receiveCommand =
    command == "RECEIVE" ||
    command == cabinetPrefix + "RECEIVE";

  bool returnCommand =
    command == "RETURN" ||
    command == cabinetPrefix + "RETURN";

  bool statusCommand =
    command == "STATUS" ||
    command == cabinetPrefix + "STATUS";

  // 다른 캐비닛 번호로 온 명령
  if (command.startsWith("CABINET:") && !cabinetCommand) {
    sendCallback("COMMAND_REJECTED", "WRONG_CABINET");
    return;
  }

  // 상태 조회는 작업 중에도 실제 문 상태를 변경하지 않고 응답한다.
  if (statusCommand) {
    sendStatusCallback();
    return;
  }

  // 현재 다른 프로세스가 진행 중인 경우
  if (currentState != STATE_DEFAULT) {
    sendCallback("COMMAND_REJECTED", "BUSY");
    return;
  }

  // 문이 이미 열려 있는 경우
  if (isDoorOpen()) {
    sendCallback("COMMAND_REJECTED", "DOOR_ALREADY_OPEN");
    return;
  }

  if (receiveCommand) {
    startProcess(MODE_RECEIVE);
  } else if (returnCommand) {
    startProcess(MODE_RETURN);
  } else {
    sendCallback("INVALID_COMMAND");
  }
}

// =====================================================
// 수령 또는 반납 프로세스 시작
// =====================================================

void startProcess(ProcessMode mode) {
  currentMode = mode;
  currentState = STATE_WAITING_FOR_OPEN;

  doorOpenWarningSent = false;

  if (currentMode == MODE_RECEIVE) {
    setLedBlue();
  } else if (currentMode == MODE_RETURN) {
    setLedRed();
  }

  unlockCabinet();

  sendCallback("COMMAND_ACCEPTED");
}

// =====================================================
// 캐비닛 상태 처리
// =====================================================

void updateCabinetState() {
  unsigned long currentTime = millis();

  switch (currentState) {
    // -------------------------------------------------
    // 기본 상태
    // -------------------------------------------------
    case STATE_DEFAULT:
      // 기본 상태에서는 별도 동작 없음
      break;

    // -------------------------------------------------
    // 문 열림 대기
    // -------------------------------------------------
    case STATE_WAITING_FOR_OPEN:

      // 문이 실제로 열렸을 때
      if (isDoorOpen()) {
        turnOffLockPower();

        currentState = STATE_WAITING_FOR_CLOSE;
        doorOpenedTime = currentTime;
        doorOpenWarningSent = false;

        sendCallback("DOOR_OPENED");
        break;
      }

      // 잠금장치 보호를 위해 최대 3초 후 전원 차단
      if (
        lockPowerOn &&
        currentTime - lockStartedTime >= LOCK_ACTIVE_TIME_MS
      ) {
        turnOffLockPower();

        sendCallback("OPEN_TIMEOUT");

        // LED와 상태를 기본값으로 복귀
        setDefaultState();
      }

      break;

    // -------------------------------------------------
    // 문 닫힘 대기
    // -------------------------------------------------
    case STATE_WAITING_FOR_CLOSE:

      // 문이 닫혔을 때
      if (isDoorClosed()) {
        sendCallback("DOOR_CLOSED");

        setDefaultState();
        break;
      }

      // 문이 너무 오래 열려 있는 경우
      if (
        !doorOpenWarningSent &&
        currentTime - doorOpenedTime >= DOOR_OPEN_WARNING_MS
      ) {
        sendCallback("DOOR_OPEN_TOO_LONG");
        doorOpenWarningSent = true;
      }

      break;
  }
}

// =====================================================
// 마그네틱 센서 디바운싱
// =====================================================

void updateDoorSensor() {
  int rawState = digitalRead(DOOR_SENSOR_PIN);
  unsigned long currentTime = millis();

  // 센서 신호가 변한 경우
  if (rawState != lastRawDoorState) {
    lastRawDoorState = rawState;
    lastSensorChangeTime = currentTime;
  }

  // 일정 시간 같은 신호가 유지되면 실제 상태로 인정
  if (
    currentTime - lastSensorChangeTime >= SENSOR_DEBOUNCE_MS &&
    stableDoorState != rawState
  ) {
    stableDoorState = rawState;
  }
}

bool isDoorOpen() {
  return stableDoorState == DOOR_OPEN_SIGNAL;
}

bool isDoorClosed() {
  return stableDoorState == DOOR_CLOSED_SIGNAL;
}

// =====================================================
// 잠금장치 제어
// =====================================================

void unlockCabinet() {
  digitalWrite(LOCK_PIN, LOCK_OPEN_SIGNAL);

  lockPowerOn = true;
  lockStartedTime = millis();
}

void turnOffLockPower() {
  digitalWrite(LOCK_PIN, LOCK_CLOSED_SIGNAL);
  lockPowerOn = false;
}

// =====================================================
// 기본 상태 복귀
// =====================================================

void setDefaultState() {
  turnOffLockPower();

  setLedWhite();

  currentState = STATE_DEFAULT;
  currentMode = MODE_NONE;

  doorOpenWarningSent = false;
}

// =====================================================
// LED 제어
// =====================================================

void setAllLeds(uint8_t red, uint8_t green, uint8_t blue) {
  for (int i = 0; i < LED_COUNT; i++) {
    leds.setPixelColor(i, leds.Color(red, green, blue));
  }

  leds.show();
}

// 은은한 백색
void setLedWhite() {
  setAllLeds(40, 40, 40);
}

// 수령: 청색
void setLedBlue() {
  setAllLeds(0, 0, 150);
}

// 반납: 적색
void setLedRed() {
  setAllLeds(150, 0, 0);
}

// =====================================================
// Callback 전송
// =====================================================

void sendCallback(String eventName) {
  String message =
    "CABINET:" + String(CABINET_ID) +
    "|MODE:" + getModeName() +
    "|EVENT:" + eventName;

  bluetooth.println(message);
  Serial.println(message);
}

void sendCallback(String eventName, String reason) {
  String message =
    "CABINET:" + String(CABINET_ID) +
    "|MODE:" + getModeName() +
    "|EVENT:" + eventName +
    "|REASON:" + reason;

  bluetooth.println(message);
  Serial.println(message);
}

void sendStatusCallback() {
  String stateName = isDoorOpen() ? "OPEN" : "CLOSED";

  String message =
    "CABINET:" + String(CABINET_ID) +
    "|MODE:NONE" +
    "|EVENT:STATUS" +
    "|STATE:" + stateName;

  bluetooth.println(message);
  Serial.println(message);
}

// =====================================================
// 현재 프로세스 이름 반환
// =====================================================

String getModeName() {
  switch (currentMode) {
    case MODE_RECEIVE:
      return "RECEIVE";

    case MODE_RETURN:
      return "RETURN";

    default:
      return "NONE";
  }
}